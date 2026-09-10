"""Purga de retención a 24 meses para ``audit_log`` (FR-030 / US8).

Política
========
``audit_log`` guarda 24 meses de historia sobre ``occurred_at``. Nada dentro de
la aplicación borra una fila: este script es el único removedor, y se apoya en
``app/services/retention.py``, la única excepción a la regla append-only de
FR-004.

La seguridad viene del **default**, no de acordarse de una bandera: sin
``--apply`` el script solo cuenta. La purga real es un paso aparte que además
exige reutilizar el cutoff que la vista previa ya publicó.

La purga deja su propia constancia: una fila ``audit_log·purge`` por cada club
afectado, con el conteo removido, la marca de corte y el slug del trabajo.
Nunca se imprime el contenido de las filas borradas — solo conteos (Ley 1581).

Uso
===

    cd backend
    source .venv/bin/activate

    # Vista previa (default, seguro): NO toca datos.
    python -m scripts.retention_audit_log

    # Purga real.
    python -m scripts.retention_audit_log --apply

    # Lo que corre el workflow: reutiliza el cutoff de la vista previa.
    python -m scripts.retention_audit_log --apply \\
        --cutoff 2024-09-09T05:00:12 --actor-kind cron

Salidas
=======
- **stdout**: exactamente una línea JSON, siempre, en toda corrida exitosa::

      {"candidates": 143, "deleted": 143, "cutoff": "2024-09-09T05:00:12"}

  En simulación ``deleted`` es siempre ``0``. Nada más sale por stdout, así que
  otro proceso puede parsearla directo (con ``set -o pipefail`` y revisando el
  código de salida antes de parsear).
- **stderr**: la bitácora del operador, con prefijo de marca de tiempo.

La URL de la base **nunca** se imprime: solo ``host/base``. Los registros de
GitHub Actions los lee cualquier colaborador del repositorio y la contraseña de
producción vive dentro de esa URL.

Códigos de salida
=================
- ``0`` — vista previa o purga completadas (incluido el caso cero).
- ``1`` — fallo de conexión, rechazo de validación o excepción no controlada.
- ``2`` — error de argumentos de Typer/Click (``--actor-kind`` desconocido,
  ``--months 0``).

Documentado en: ``docs/19-multi-coach-governance/runbook.md`` sección 5.
"""
from __future__ import annotations

import asyncio
import enum
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import typer

app = typer.Typer(add_completion=False, help=__doc__)


DEFAULT_RETENTION_MONTHS = 24

#: Únicos drivers aceptados: la purga es async de punta a punta.
_ALLOWED_DRIVERS = ("mysql+aiomysql", "sqlite+aiosqlite")


class ActorKind(str, enum.Enum):
    """``actor_kind`` de la fila de purga. No existe ``user``: una CLI no tiene
    sesión autenticada y escribir un ``actor_user_id`` sería inventar una
    atribución que nadie verificó."""

    system = "system"
    cron = "cron"


class Refusal(Exception):
    """Rechazo de validación: aborta con código 1 y un mensaje para el operador.

    Todo rechazo ocurre **antes** de crear el motor, así que una invocación
    inválida jamás abre una conexión contra producción.
    """


def _emit(label: str, msg: str) -> None:
    """Bitácora del operador con prefijo de marca de tiempo, por **stderr**.

    Va a stderr a propósito: stdout queda como canal limpio para el JSON, de
    modo que el workflow pueda hacer ``... > preview.json`` y aun así mostrar
    una bitácora legible.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    typer.echo(f"[{ts}] {label:7} {msg}", err=True)


def _scrub(text: str, secret: str | None) -> str:
    """Tapa la contraseña si alguna excepción de terceros llegara a citarla."""
    if secret and secret in text:
        return text.replace(secret, "***")
    return text


def _months_was_explicit() -> bool:
    """¿El operador escribió ``--months`` a mano? Solo para decidir el WARN."""
    try:
        import click
        from click.core import ParameterSource

        ctx = click.get_current_context(silent=True)
        if ctx is None:
            return False
        return ctx.get_parameter_source("months") == ParameterSource.COMMANDLINE
    except Exception:  # noqa: BLE001 - un WARN nunca debe tumbar la corrida
        return False


def _parse_cutoff(raw: str) -> datetime:
    """Convierte el ``--cutoff`` recibido a UTC ingenuo."""
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise Refusal(
            "--cutoff debe ser una marca de tiempo ISO-8601 en UTC "
            "(ej. 2024-09-09T05:00:12)."
        ) from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _resolve_cutoff(
    *, months: int, raw_cutoff: str | None, now: datetime
) -> datetime:
    """Decide el cutoff efectivo y valida que no invada la ventana viva.

    ``--cutoff`` le gana a ``--months``, pero ``--months`` sigue definiendo la
    ventana contra la cual se valida: un cutoff tecleado a mano solo puede
    correr la frontera **más hacia el pasado**, nunca hacia datos vivos.
    """
    from app.services.retention import retention_cutoff

    computed = retention_cutoff(now, months)
    if raw_cutoff is None:
        return computed

    if _months_was_explicit():
        _emit(
            "WARN",
            "se recibieron --cutoff y --months: manda --cutoff; "
            "--months solo valida la ventana.",
        )

    requested = _parse_cutoff(raw_cutoff)
    if requested > now:
        raise Refusal("El cutoff solicitado está en el futuro. Se cancela la purga.")
    if requested > computed:
        raise Refusal(
            f"El cutoff solicitado ({requested.isoformat()}) está dentro de la "
            f"ventana de retención de {months} meses. Se cancela la purga."
        )
    return requested


def _resolve_database_url(database_url: str | None) -> str:
    """Resuelve la URL de la base y valida el driver.

    ``app.config`` se importa **solo** cuando no llegó ninguna URL, para que una
    corrida de CI con URL explícita nunca construya ``Settings()`` ni necesite
    un ``.env``.
    """
    url = database_url
    if not url:
        try:
            from app.config import settings

            url = settings.database_url
        except Exception as exc:  # cualquier fallo termina en el mismo rechazo
            raise Refusal(
                "No se pudo resolver la base de datos. Define "
                "AUDIT_RETENTION_DATABASE_URL o corre desde backend/ con .env."
            ) from exc
    if not url:
        raise Refusal(
            "No se pudo resolver la base de datos. Define "
            "AUDIT_RETENTION_DATABASE_URL o corre desde backend/ con .env."
        )

    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import ArgumentError

    try:
        parsed = make_url(url)
    except ArgumentError as exc:
        raise Refusal(
            "--database-url debe usar un driver async: 'mysql+aiomysql://' o "
            "'sqlite+aiosqlite://'."
        ) from exc
    if parsed.drivername not in _ALLOWED_DRIVERS:
        raise Refusal(
            "--database-url debe usar un driver async: 'mysql+aiomysql://' o "
            "'sqlite+aiosqlite://'."
        )
    return url


def _describe_database(url: str) -> str:
    """``host/base`` y nada más — jamás la URL cruda ni la contraseña."""
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    return f"{parsed.host or 'local'}/{parsed.database or '-'}"


async def _run(
    *,
    url: str,
    cutoff: datetime,
    months: int,
    apply: bool,
    actor_kind: ActorKind,
) -> dict[str, Any]:
    """Ejecuta la vista previa y, si corresponde, la purga. Devuelve el JSON.

    Los imports van diferidos, como en ``scripts/retention_ai_insights.py``,
    para que ``--help`` funcione sin venv y sin cargar SQLAlchemy ni Settings.

    No se importa ``AsyncSessionLocal`` de ``app.database``: ese módulo arma su
    motor en tiempo de import a partir de ``settings.database_url``, así que
    ``--database-url`` quedaría silenciosamente ignorado. Este script crea el
    suyo y lo desecha en un ``finally``.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.audit_log import AuditActorKind, AuditLog  # noqa: F401
    from app.services import retention

    _emit(
        "INFO",
        "modo = SIMULACIÓN (usa --apply para ejecutar)"
        if not apply
        else "modo = APLICAR (se ejecutará el DELETE)",
    )
    _emit(
        "INFO",
        f"ventana de retención = {months} meses (cutoff = {cutoff.isoformat()})",
    )
    _emit("INFO", f"base de datos = {_describe_database(url)}")

    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            preview = await retention.preview_purge(session, cutoff=cutoff)
            _emit("INFO", f"candidatos a purgar: {preview.candidates}")
            for entity_type, count in sorted(
                preview.by_entity_type.items(), key=lambda kv: (-kv[1], kv[0])
            ):
                _emit("ROW", f"entity_type={entity_type} candidatos={count}")

            if preview.candidates == 0:
                _emit(
                    "OK",
                    "0 filas anteriores al cutoff. No hay nada que purgar.",
                )

            if not apply:
                if preview.candidates:
                    _emit("DRY", "no se ejecuta DELETE. Usa --apply para aplicar.")
                return {
                    "candidates": preview.candidates,
                    "deleted": 0,
                    "cutoff": preview.cutoff.isoformat(),
                }

            result = await retention.apply_purge(
                session,
                cutoff=cutoff,
                actor_kind=AuditActorKind(actor_kind.value),
                request_id=uuid4().hex,
            )
            await session.commit()

            if result.deleted:
                detalle = ", ".join(
                    f"club_id={club_id if club_id is not None else 'NULL'}, "
                    f"removed_count={count}"
                    for club_id, count in sorted(
                        preview.by_club_id.items(),
                        key=lambda kv: (kv[0] is None, kv[0] or 0),
                    )
                )
                _emit(
                    "DONE",
                    f"{result.deleted} filas eliminadas; registro de purga "
                    f"creado ({detalle})",
                )
            return {
                "candidates": result.candidates,
                "deleted": result.deleted,
                "cutoff": result.cutoff.isoformat(),
            }
    finally:
        await engine.dispose()


@app.command()
def main(
    apply: bool = typer.Option(
        False,
        "--apply/--dry-run",
        help=(
            "Ejecutar el DELETE. Sin la bandera corre en simulación "
            "(default seguro)."
        ),
    ),
    months: int = typer.Option(
        DEFAULT_RETENTION_MONTHS,
        "--months",
        help=(
            "Ventana de retención en meses de calendario. Default 24 (política "
            "oficial). Bajarlo es solo para depurar en local: nunca contra "
            "producción."
        ),
        min=1,
    ),
    cutoff: str | None = typer.Option(
        None,
        "--cutoff",
        help=(
            "Marca de corte ISO-8601 en UTC. Reemplaza el cutoff calculado para "
            "que el paso que confirma reutilice verbatim el de la vista previa."
        ),
    ),
    actor_kind: ActorKind = typer.Option(
        ActorKind.system,
        "--actor-kind",
        help="Actor de la fila de purga: 'system' (a mano) o 'cron' (agendado).",
    ),
    database_url: str | None = typer.Option(
        None,
        "--database-url",
        envvar="AUDIT_RETENTION_DATABASE_URL",
        help=(
            "URL async de SQLAlchemy. Si falta, se toma la configuración de la "
            "aplicación. Nunca se imprime."
        ),
    ),
) -> None:
    """Punto de entrada CLI."""
    password: str | None = None
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        effective_cutoff = _resolve_cutoff(
            months=months, raw_cutoff=cutoff, now=now
        )
        url = _resolve_database_url(database_url)

        from sqlalchemy.engine import make_url

        password = make_url(url).password
        payload = asyncio.run(
            _run(
                url=url,
                cutoff=effective_cutoff,
                months=months,
                apply=apply,
                actor_kind=actor_kind,
            )
        )
    except Refusal as exc:
        _emit("ERROR", str(exc))
        raise typer.Exit(code=1)
    except KeyboardInterrupt:
        _emit("ABORT", "interrumpido por el operador; no se hizo ningún commit.")
        raise typer.Exit(code=1)
    except Exception as exc:  # noqa: BLE001 - cualquier fallo aborta con exit 1
        _emit("ERROR", _scrub(f"{type(exc).__name__}: {exc}", password))
        raise typer.Exit(code=1)

    typer.echo(json.dumps(payload))
    _emit(
        "EXIT",
        f"candidates={payload['candidates']} deleted={payload['deleted']} "
        f"apply={'true' if apply else 'false'}",
    )
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
