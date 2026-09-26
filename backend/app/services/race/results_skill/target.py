"""Resolución de destino (local/producción) para el CLI de resultados.

Amendment 2026-09-26, T145 — ``contracts/results-skill-cli.md`` § Target
rules. Este módulo es la ÚNICA frontera entre el portátil del operador y la
base de datos de producción: ``resolve_target`` decide, antes de que
``scripts/race_results.py`` toque una fila, si el destino es local (default,
sin fricción) o producción (requiere ``--target production --confirm
produccion`` más un stack completo — SFTP configurado y cabeza de Alembic
igual a la del repositorio).

Orden de importación (crítico): para producción, las claves de
``backend/.env.production`` (solo ``MYSQL_*``, ``HOSTINGER_SFTP_*`` y
``HOSTINGER_PUBLIC_BASE_URL``) se cargan en ``os.environ`` **antes** de que
el proceso importe cualquier módulo ``app.*`` — así, cuando
``scripts/race_results.py`` importe más tarde ``app.services.race.
import_staging`` (que a su vez importa ``app.config``), el singleton
``Settings`` que se construya en ese momento ya ve las credenciales de
producción, sin que este módulo mismo dependa de ``app.config`` para tomar
sus propias decisiones (host local, comparación de par, SFTP, cabeza de
Alembic) — esas decisiones se calculan aquí a partir de los archivos
parseados directamente, nunca del singleton de ``app.config`` (que en un
proceso de pruebas puede ya estar cacheado desde antes de esta llamada).

Nunca se imprime un valor cargado de ninguno de los dos archivos —
``scrub()`` lo reemplaza por ``***`` en cualquier texto que vaya a stdout,
stderr o una excepción.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

#: Allow-list de hosts locales (contracts/results-skill-cli.md § Target rules).
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "mysql", "host.docker.internal"})

#: Prefijos/claves permitidos de ``.env.production`` — nada más se carga.
_PRODUCTION_KEY_PREFIXES = ("MYSQL_", "HOSTINGER_SFTP_")
_PRODUCTION_EXTRA_KEYS = ("HOSTINGER_PUBLIC_BASE_URL",)

#: Forzados sobre el entorno de producción (contracts/results-skill-cli.md):
#: nunca se activa IA ni Strava, y `APP_ENV` nunca se pone en "production"
#: (evita los `field_validator` de producción de `app.config.Settings`, que
#: exigen JWT/CORS reales que este subconjunto de claves no trae).
_FORCED_ENV = {
    "APP_ENV": "development",
    "AI_ENABLED": "false",
    "STRAVA_ENABLED": "false",
}

#: Palabra de confirmación exigida para producción.
CONFIRM_WORD = "produccion"

_SFTP_REQUIRED_KEYS = (
    "HOSTINGER_SFTP_HOST",
    "HOSTINGER_SFTP_USER",
    "HOSTINGER_SFTP_PASS",
    "HOSTINGER_SFTP_REMOTE_DIR",
)


class TargetError(Exception):
    """Destino rechazado. El mensaje ya viene depurado de secretos.

    ``code`` distingue, para el CLI, el desajuste de cabeza de Alembic
    (``"schema_head_mismatch"``, exit 11 en ``results-skill-cli.md``) de
    cualquier otro rechazo de destino (exit 9) — es el único caso con su
    propio código de salida en el contrato.
    """

    def __init__(self, message: str, *, code: str = "target_refused") -> None:
        super().__init__(message)
        self.code = code


ScrubFn = Callable[[str], str]


@dataclass
class Target:
    """Destino resuelto — lo que ``stage``/``compare`` necesitan para abrir
    una sesión, nunca los valores crudos que la produjeron."""

    name: str  # "local" | "production"
    is_production: bool
    engine: AsyncEngine
    session_factory: Callable[[], AsyncSession]
    sftp_configured: bool
    scrub: ScrubFn

    def session(self) -> AsyncSession:
        return self.session_factory()


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parser mínimo ``KEY=VALUE`` (sin dependencia de ``python-dotenv``,
    ausente de ``requirements.txt``). Ignora comentarios y líneas vacías;
    quita comillas simples/dobles envolventes."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def _wanted_production_keys(values: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in values.items():
        if key.startswith(_PRODUCTION_KEY_PREFIXES) or key in _PRODUCTION_EXTRA_KEYS:
            out[key] = value
    return out


def make_scrubber(*value_sources: dict[str, str]) -> ScrubFn:
    """Reemplaza en ``text`` cada valor no vacío de los diccionarios dados,
    de más largo a más corto (para que un secreto que es substring de otro
    no deje residuo)."""
    secrets: set[str] = set()
    for values in value_sources:
        for value in values.values():
            if value:
                secrets.add(value)
    ordered = sorted(secrets, key=len, reverse=True)

    def scrub(text_: str) -> str:
        out = text_
        for secret in ordered:
            out = out.replace(secret, "***")
        return out

    return scrub


def _mysql_pair(values: dict[str, str], *, host_key: str = "MYSQL_HOST", db_key: str = "MYSQL_DB") -> tuple[str, str]:
    return values.get(host_key, ""), values.get(db_key, "")


def _sftp_configured(values: dict[str, str]) -> bool:
    return all(values.get(key) for key in _SFTP_REQUIRED_KEYS)


def _database_url(values: dict[str, str]) -> str:
    from urllib.parse import quote_plus

    host = values.get("MYSQL_HOST", "")
    port = values.get("MYSQL_PORT", "3306")
    user = values.get("MYSQL_USER", "")
    password = values.get("MYSQL_PASS", "")
    db = values.get("MYSQL_DB", "")
    return (
        f"mysql+aiomysql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{db}"
    )


def _repo_alembic_head(env_dir: Path) -> str:
    """Cabeza única del árbol de migraciones del repositorio (nunca la de
    un documento — ``alembic heads`` debe devolver exactamente una, regla
    del proyecto)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(env_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(env_dir / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    if len(heads) != 1:
        raise TargetError(
            f"El árbol de migraciones tiene {len(heads)} cabezas; se espera exactamente una."
        )
    return heads[0]


async def _read_alembic_version(engine: AsyncEngine) -> Optional[str]:
    async with engine.connect() as conn:
        try:
            result = await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        except Exception:  # noqa: BLE001 — tabla ausente u otra falla de esquema
            return None
        row = result.first()
        return row[0] if row else None


#: Fábrica de engine para la verificación de cabeza de Alembic en
#: producción — función de módulo (no un método) para que las pruebas la
#: sustituyan por ``monkeypatch.setattr(target, "create_target_engine", ...)``
#: sin tocar una base MySQL real.
def create_target_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


async def _resolve_local(prod_values: dict[str, str], env_dir: Path, scrub: ScrubFn) -> Target:
    from app.config import settings
    from app.database import AsyncSessionLocal, engine as app_engine

    if settings.app_env == "production":
        raise TargetError(
            "Destino local rechazado: APP_ENV=production en el entorno activo."
        )
    if settings.mysql_host not in LOCAL_HOSTS:
        raise TargetError(
            scrub(
                "Destino local rechazado: MYSQL_HOST no está en la lista local permitida."
            )
        )
    prod_pair = _mysql_pair(prod_values)
    if prod_pair == (settings.mysql_host, settings.mysql_db) and prod_pair != ("", ""):
        raise TargetError(
            "Destino local rechazado: el par (MYSQL_HOST, MYSQL_DB) coincide con producción."
        )

    return Target(
        name="local",
        is_production=False,
        engine=app_engine,
        session_factory=lambda: AsyncSessionLocal(),
        sftp_configured=_sftp_configured(
            {
                "HOSTINGER_SFTP_HOST": settings.hostinger_sftp_host,
                "HOSTINGER_SFTP_USER": settings.hostinger_sftp_user,
                "HOSTINGER_SFTP_PASS": settings.hostinger_sftp_pass,
                "HOSTINGER_SFTP_REMOTE_DIR": settings.hostinger_sftp_remote_dir,
            }
        ),
        scrub=scrub,
    )


async def _resolve_production(
    prod_values: dict[str, str], confirm: Optional[str], env_dir: Path, scrub: ScrubFn
) -> Target:
    if confirm != CONFIRM_WORD:
        raise TargetError(
            f"Destino producción rechazado: falta --confirm {CONFIRM_WORD}."
        )
    if not prod_values:
        raise TargetError(
            "Destino producción rechazado: no se encontró backend/.env.production."
        )
    if not _sftp_configured(prod_values):
        raise TargetError(
            "Destino producción rechazado: configuración de SFTP incompleta en .env.production."
        )

    # Carga en el entorno del proceso — antes de que cualquier módulo
    # ``app.*`` sea importado por el resto del script (ver docstring del
    # módulo). Efecto real solo en el proceso real del CLI; en pruebas el
    # singleton de ``app.config`` puede ya estar cacheado desde antes.
    os.environ.update(prod_values)
    os.environ.update(_FORCED_ENV)

    database_url = _database_url(prod_values)
    engine = create_target_engine(database_url)

    repo_head = _repo_alembic_head(env_dir)
    db_version = await _read_alembic_version(engine)
    if db_version != repo_head:
        await engine.dispose()
        raise TargetError(
            "Destino producción rechazado: alembic_version de la base no coincide "
            "con la cabeza del repositorio.",
            code="schema_head_mismatch",
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return Target(
        name="production",
        is_production=True,
        engine=engine,
        session_factory=lambda: session_factory(),
        sftp_configured=True,
        scrub=scrub,
    )


async def resolve_target(
    target: Optional[str], confirm: Optional[str], env_dir: Path | str
) -> Target:
    """Resuelve el destino ``local`` (default) o ``production``.

    ``env_dir`` es el directorio que contiene ``.env.production`` y
    ``alembic.ini`` — en producción real es ``backend/``; las pruebas pasan
    un directorio temporal con un ``.env.production`` sintético.
    """
    name = (target or "local").strip().lower()
    if name not in ("local", "production"):
        raise TargetError(f"--target desconocido: {target!r} (use 'local' o 'production').")

    env_dir_path = Path(env_dir)
    prod_values = _wanted_production_keys(_parse_env_file(env_dir_path / ".env.production"))
    scrub = make_scrubber(prod_values)

    if name == "local":
        return await _resolve_local(prod_values, env_dir_path, scrub)
    return await _resolve_production(prod_values, confirm, env_dir_path, scrub)
