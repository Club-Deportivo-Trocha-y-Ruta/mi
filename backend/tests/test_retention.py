"""T090 — retención a 24 meses y purga de ``audit_log`` (US8, FR-030).

Cubre la tabla §8.1 de
``specs/041-multi-coach-governance/contracts/retention-purge.md``: T1-T9 sobre
``app/services/retention.py`` y T10-T15 sobre
``backend/scripts/retention_audit_log.py`` vía ``typer.testing.CliRunner``.

Vía offline: motor ``sqlite+aiosqlite`` propio con ``StaticPool`` y un
subconjunto de tablas (``users``, ``clubs`` más ``AUDIT_TABLES``), igual que
``tests/test_password_reset_privacy.py``. No se usa la fixture ``client`` de
``tests/conftest.py`` — esa levanta la app contra la base real.

Las filas sembradas son filas de auditoría y nada más: ni un atleta, ni un
nombre, ni una fecha de nacimiento (Ley 1581).

Los casos T20/T21 del contrato (§8.3) van al final del módulo marcados con
``mysql``: la frontera de microsegundos y el plan del ``DELETE`` sólo tienen
sentido contra MySQL real con ``DATETIME(fsp=6)``. Se saltan solos cuando no
hay ``TEST_DATABASE_URL``.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from typer.testing import CliRunner

from app.models.audit_log import AuditAction, AuditActorKind, AuditLog
from app.models.base import Base
from app.services import retention
from app.services.audit import AuditEntityType
from scripts.retention_audit_log import app as cli_app
from tests.helpers.audit_tables import AUDIT_TABLES

#: Ancla fija para toda la aritmética del módulo (UTC ingenuo, como el esquema).
NOW = datetime(2026, 9, 9, 5, 0, 12)
CUTOFF = retention.retention_cutoff(NOW, 24)

_TABLES = ("users", "clubs", *AUDIT_TABLES)


def _audit_row(
    *,
    occurred_at: datetime,
    club_id: int | None = 1,
    entity_type: str = AuditEntityType.session_attendance.value,
    entity_id: int = 1,
) -> AuditLog:
    """Fila de auditoría mínima y anónima para sembrar la tabla."""
    return AuditLog(
        occurred_at=occurred_at,
        actor_user_id=None,
        actor_kind=AuditActorKind.system,
        actor_role=None,
        club_id=club_id,
        athlete_id=None,
        entity_type=entity_type,
        entity_id=entity_id,
        action=AuditAction.create,
        changed_fields=[],
        diff_json=None,
        reason_code=None,
        request_id=uuid4().hex,
        meta_json=None,
    )


async def _create_subset(engine: AsyncEngine) -> None:
    tables = [Base.metadata.tables[name] for name in _TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    await _create_subset(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with factory() as s:
        yield s


async def _seed(session: AsyncSession, rows: list[AuditLog]) -> None:
    for row in rows:
        session.add(row)
    await session.commit()


async def _count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(AuditLog))).scalar_one())


async def _purge_rows(session: AsyncSession) -> list[AuditLog]:
    result = await session.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.purge)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# T1-T8 — servicio
# ---------------------------------------------------------------------------


async def test_t1_preview_no_borra_nada(session: AsyncSession) -> None:
    """T1 (US8 AS1) — la vista previa cuenta y no toca un solo dato."""
    await _seed(
        session,
        [
            _audit_row(occurred_at=NOW - timedelta(days=760)),  # ~25 meses
            _audit_row(occurred_at=NOW - timedelta(days=700)),  # ~23 meses
        ],
    )

    preview = await retention.preview_purge(session, cutoff=CUTOFF)

    assert preview.candidates == 1
    assert preview.cutoff == CUTOFF
    assert sum(preview.by_entity_type.values()) == preview.candidates
    assert sum(preview.by_club_id.values()) == preview.candidates
    assert await _count(session) == 2
    assert await _purge_rows(session) == []


async def test_t2_apply_borra_solo_lo_anterior_al_cutoff(
    session: AsyncSession,
) -> None:
    """T2 — sólo desaparece lo que quedó fuera de la ventana."""
    viva = NOW - timedelta(days=700)
    await _seed(
        session,
        [
            _audit_row(occurred_at=NOW - timedelta(days=760)),
            _audit_row(occurred_at=viva),
        ],
    )

    result = await retention.apply_purge(
        session,
        cutoff=CUTOFF,
        actor_kind=AuditActorKind.system,
        request_id=uuid4().hex,
    )
    await session.commit()

    assert result.deleted == 1
    assert result.candidates == 1
    sobrevivientes = (
        await session.execute(
            select(AuditLog.occurred_at).where(AuditLog.action == AuditAction.create)
        )
    ).scalars().all()
    assert list(sobrevivientes) == [viva]


async def test_t3_frontera_es_estrictamente_menor(session: AsyncSession) -> None:
    """T3 — una fila exactamente igual al cutoff (al microsegundo) sobrevive."""
    await _seed(
        session,
        [
            _audit_row(occurred_at=CUTOFF),
            _audit_row(occurred_at=CUTOFF - timedelta(microseconds=1)),
        ],
    )

    result = await retention.apply_purge(
        session,
        cutoff=CUTOFF,
        actor_kind=AuditActorKind.system,
        request_id=uuid4().hex,
    )
    await session.commit()

    assert result.deleted == 1
    restantes = (
        await session.execute(
            select(AuditLog.occurred_at).where(AuditLog.action == AuditAction.create)
        )
    ).scalars().all()
    assert list(restantes) == [CUTOFF]


async def test_t4_la_purga_queda_registrada(session: AsyncSession) -> None:
    """T4 (US8 AS2) — la purga escribe su propia fila, con conteo y motivo."""
    await _seed(session, [_audit_row(occurred_at=NOW - timedelta(days=760))])

    request_id = uuid4().hex
    result = await retention.apply_purge(
        session,
        cutoff=CUTOFF,
        actor_kind=AuditActorKind.cron,
        request_id=request_id,
    )
    await session.commit()

    filas = await _purge_rows(session)
    assert len(filas) == 1
    fila = filas[0]
    assert fila.entity_type == AuditEntityType.audit_log.value
    # `retention-purge.md` §1.4 y `data-model.md` §1.3 fijan el sentinela 0,
    # pero `record_audit` valida `entity_id > 0` (`audit-recording.md` §1.2).
    # Mientras ese choque de contratos se resuelva en `app/services/audit.py`,
    # la fila se escribe con el respaldo positivo. Ver PURGE_ENTITY_ID_FALLBACK.
    assert fila.entity_id in {
        retention.PURGE_ENTITY_ID,
        retention.PURGE_ENTITY_ID_FALLBACK,
    }
    assert fila.actor_user_id is None
    assert fila.actor_kind == AuditActorKind.cron
    assert fila.actor_role is None
    assert fila.reason_code == "retention_24m"
    assert fila.request_id == request_id
    assert fila.changed_fields == []
    assert fila.diff_json is None
    assert fila.meta_json == {
        "job": "audit_retention",
        "removed_count": 1,
        "cutoff": CUTOFF.isoformat(),
    }
    # No se auto-borra: su marca es muy posterior al cutoff.
    assert fila.occurred_at.replace(tzinfo=None) > CUTOFF
    assert result.audit_row_ids == [fila.id]


async def test_t5_una_fila_de_purga_por_club(session: AsyncSession) -> None:
    """T5 — un club por fila, cada una con su conteo y un único request_id."""
    vieja = NOW - timedelta(days=760)
    await _seed(
        session,
        [
            _audit_row(occurred_at=vieja, club_id=1),
            _audit_row(occurred_at=vieja, club_id=1),
            _audit_row(occurred_at=vieja, club_id=2),
            _audit_row(occurred_at=vieja, club_id=None),
        ],
    )

    request_id = uuid4().hex
    result = await retention.apply_purge(
        session,
        cutoff=CUTOFF,
        actor_kind=AuditActorKind.system,
        request_id=request_id,
    )
    await session.commit()

    assert result.deleted == 4
    filas = await _purge_rows(session)
    assert len(filas) == 3
    assert {f.request_id for f in filas} == {request_id}
    conteos = {f.club_id: f.meta_json["removed_count"] for f in filas}
    assert conteos == {1: 2, 2: 1, None: 1}


async def test_t6_caso_cero_no_escribe_nada(session: AsyncSession) -> None:
    """T6 (§1.5) — sin candidatos no hay DELETE ni fila de purga."""
    await _seed(session, [_audit_row(occurred_at=NOW - timedelta(days=10))])
    antes = await _count(session)

    result = await retention.apply_purge(
        session,
        cutoff=CUTOFF,
        actor_kind=AuditActorKind.system,
        request_id=uuid4().hex,
    )
    await session.commit()

    assert (result.candidates, result.deleted, result.audit_row_ids) == (0, 0, [])
    assert await _count(session) == antes
    assert await _purge_rows(session) == []


async def test_t7_idempotente_con_el_mismo_cutoff(session: AsyncSession) -> None:
    """T7 — la segunda corrida no encuentra nada y no agrega ruido."""
    await _seed(session, [_audit_row(occurred_at=NOW - timedelta(days=760))])

    primera = await retention.apply_purge(
        session,
        cutoff=CUTOFF,
        actor_kind=AuditActorKind.system,
        request_id=uuid4().hex,
    )
    await session.commit()
    segunda = await retention.apply_purge(
        session,
        cutoff=CUTOFF,
        actor_kind=AuditActorKind.system,
        request_id=uuid4().hex,
    )
    await session.commit()

    assert primera.deleted == 1
    assert (segunda.candidates, segunda.deleted) == (0, 0)
    assert len(await _purge_rows(session)) == 1


async def test_t8_atomicidad_rollback_deja_todo_como_estaba(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """T8 — si algo revienta antes del commit, ni se borró ni se registró."""
    async with factory() as seed_session:
        await _seed(
            seed_session, [_audit_row(occurred_at=NOW - timedelta(days=760))]
        )

    async with factory() as work_session:
        await retention.apply_purge(
            work_session,
            cutoff=CUTOFF,
            actor_kind=AuditActorKind.system,
            request_id=uuid4().hex,
        )
        # El llamador falla antes de confirmar: la unidad de trabajo se revierte
        # entera (el DELETE y las filas de purga comparten suerte).
        await work_session.rollback()

    async with factory() as check_session:
        assert await _count(check_session) == 1
        assert await _purge_rows(check_session) == []


# ---------------------------------------------------------------------------
# T9 — aritmética de calendario (función pura, sin base de datos)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "months", "esperado"),
    [
        (datetime(2026, 3, 31), 1, datetime(2026, 2, 28)),
        (datetime(2028, 3, 29), 1, datetime(2028, 2, 29)),
        (datetime(2028, 2, 29), 12, datetime(2027, 2, 28)),
        (datetime(2026, 9, 9, 5, 0, 12), 24, datetime(2024, 9, 9, 5, 0, 12)),
        (datetime(2026, 1, 15), 24, datetime(2024, 1, 15)),
        (datetime(2026, 1, 31), 2, datetime(2025, 11, 30)),
    ],
)
def test_t9_retention_cutoff_es_aritmetica_de_meses(
    now: datetime, months: int, esperado: datetime
) -> None:
    """T9 — meses de calendario con recorte del día, no 730 días."""
    assert retention.retention_cutoff(now, months) == esperado


def test_t9b_retention_cutoff_rechaza_ventana_invalida() -> None:
    with pytest.raises(ValueError):
        retention.retention_cutoff(NOW, 0)


# ---------------------------------------------------------------------------
# T10-T15 — CLI
# ---------------------------------------------------------------------------


runner = CliRunner()


#: Las pruebas de CLI son **síncronas** a propósito: ``CliRunner`` invoca un
#: comando que llama ``asyncio.run`` internamente, y eso no puede ocurrir
#: dentro del bucle de eventos que pytest-asyncio abre para una prueba async.
#: La base se prepara y se revisa con ``asyncio.run`` desde funciones sync.


async def _apply_to_url(url: str, fn):
    eng = create_async_engine(url, future=True)
    try:
        maker = async_sessionmaker(eng, expire_on_commit=False)
        async with maker() as s:
            return await fn(s)
    finally:
        await eng.dispose()


@pytest.fixture
def cli_db(tmp_path) -> str:
    """Base sqlite en archivo: la CLI construye su propio motor, así que no
    puede compartir una base en memoria con la prueba."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'audit_cli.sqlite'}"

    async def _setup() -> None:
        eng = create_async_engine(url, future=True)
        try:
            await _create_subset(eng)
            maker = async_sessionmaker(eng, expire_on_commit=False)
            async with maker() as s:
                await _seed(
                    s,
                    [
                        _audit_row(occurred_at=NOW - timedelta(days=760)),
                        _audit_row(occurred_at=NOW - timedelta(days=10)),
                    ],
                )
        finally:
            await eng.dispose()

    asyncio.run(_setup())
    return url


def _stdout_json(result) -> dict:
    lineas = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(lineas) == 1, f"stdout debe traer una sola línea: {lineas!r}"
    return json.loads(lineas[0])


def test_t10_cli_simula_por_defecto(cli_db: str) -> None:
    """T10 — sin banderas la CLI cuenta y no borra."""
    url = cli_db
    result = runner.invoke(cli_app, ["--database-url", url])

    assert result.exit_code == 0, result.output
    payload = _stdout_json(result)
    assert payload["deleted"] == 0
    assert payload["candidates"] == 1

    async def _check(s: AsyncSession) -> tuple[int, list[AuditLog]]:
        return await _count(s), await _purge_rows(s)

    total, purgas = asyncio.run(_apply_to_url(url, _check))
    assert total == 2
    assert purgas == []


def test_t11_cli_contrato_json(cli_db: str) -> None:
    """T11 — exactamente tres claves y un cutoff que vuelve a ser datetime."""
    url = cli_db
    result = runner.invoke(cli_app, ["--database-url", url])

    payload = _stdout_json(result)
    assert set(payload) == {"candidates", "deleted", "cutoff"}
    assert isinstance(payload["candidates"], int)
    assert isinstance(payload["deleted"], int)
    assert datetime.fromisoformat(payload["cutoff"]).tzinfo is None


def test_t12_cli_nunca_imprime_la_url(tmp_path) -> None:
    """T12 — ni stdout ni stderr pueden contener la contraseña."""
    secreto = "cl4v3-de-produccion"
    url = f"mysql+aiomysql://audit_user:{secreto}@127.0.0.1:1/trocha_ruta"
    result = runner.invoke(cli_app, ["--database-url", url])

    assert result.exit_code == 1
    assert secreto not in result.output
    assert url not in result.output


def test_t13_cli_rechaza_cutoff_dentro_de_la_ventana(tmp_path) -> None:
    """T13 (§2.6) — un cutoff reciente o futuro se cancela antes de conectar."""
    path = tmp_path / "no-se-abre.sqlite"
    url = f"sqlite+aiosqlite:///{path}"

    reciente = runner.invoke(
        cli_app,
        ["--database-url", url, "--apply", "--cutoff", "2026-09-01T00:00:00"],
    )
    assert reciente.exit_code == 1
    assert "ventana de retención" in reciente.output
    assert not path.exists(), "no debió abrirse ninguna conexión"

    futuro = runner.invoke(
        cli_app,
        ["--database-url", url, "--apply", "--cutoff", "2099-01-01T00:00:00"],
    )
    assert futuro.exit_code == 1
    assert "futuro" in futuro.output
    assert not path.exists()

    ilegible = runner.invoke(cli_app, ["--database-url", url, "--cutoff", "ayer"])
    assert ilegible.exit_code == 1
    assert "ISO-8601" in ilegible.output


def test_t14_cli_rechaza_driver_no_async() -> None:
    """T14 — un driver síncrono se rechaza antes de crear el motor."""
    result = runner.invoke(
        cli_app,
        ["--database-url", "mysql+pymysql://u:p@127.0.0.1:3306/trocha"],
    )
    assert result.exit_code == 1
    assert "driver async" in result.output
    assert "mysql+aiomysql://" in result.output


def test_t15_cutoff_manda_sobre_months(cli_db: str) -> None:
    """T15 — con ambos, gana --cutoff y ese valor es el que sale en el JSON."""
    url = cli_db
    elegido = "2024-01-01T00:00:00"
    result = runner.invoke(
        cli_app, ["--database-url", url, "--months", "1", "--cutoff", elegido]
    )

    assert result.exit_code == 0, result.output
    payload = _stdout_json(result)
    assert payload["cutoff"] == elegido
    # Con ese corte tan viejo no queda ningún candidato de la siembra.
    assert payload["candidates"] == 0


def test_t15b_cli_apply_purga_y_registra(cli_db: str) -> None:
    """Camino completo de la CLI: --apply borra, confirma y deja constancia."""
    url = cli_db
    cutoff = (NOW - timedelta(days=730)).isoformat()
    result = runner.invoke(
        cli_app,
        ["--database-url", url, "--apply", "--cutoff", cutoff, "--actor-kind", "cron"],
    )

    assert result.exit_code == 0, result.output
    payload = _stdout_json(result)
    assert payload == {"candidates": 1, "deleted": 1, "cutoff": cutoff}

    filas = asyncio.run(_apply_to_url(url, _purge_rows))
    assert len(filas) == 1
    assert filas[0].actor_kind == AuditActorKind.cron
    assert filas[0].meta_json["removed_count"] == 1


def test_t15c_cli_rechaza_actor_kind_desconocido() -> None:
    """§2.5 — un valor fuera del catálogo es error de Click: código 2."""
    result = runner.invoke(
        cli_app,
        ["--database-url", "sqlite+aiosqlite:///x.sqlite", "--actor-kind", "user"],
    )
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# T20-T21 — vía `-m mysql` (§8.3). Requieren TEST_DATABASE_URL contra una base
# cuyo nombre termine en `_test`; se saltan solas en la vía offline.
# ---------------------------------------------------------------------------


@pytest.mark.mysql
async def test_t20_frontera_de_microsegundos_en_mysql(
    mysql_session: AsyncSession,
) -> None:
    """T20 — dos filas a un microsegundo de distancia a través del cutoff.

    Es la prueba que habría atrapado el truncamiento a ``fsp=0`` que advierte
    ``data-model.md`` §1: en SQLite no significa nada, por eso vive acá.
    """
    cutoff = datetime(2024, 5, 5, 4, 3, 2, 500000)
    vieja = _audit_row(
        occurred_at=cutoff - timedelta(microseconds=1), entity_id=920001
    )
    nueva = _audit_row(occurred_at=cutoff, entity_id=920002)
    mysql_session.add_all([vieja, nueva])
    await mysql_session.commit()

    result = await retention.apply_purge(
        mysql_session,
        cutoff=cutoff,
        actor_kind=AuditActorKind.system,
        request_id=uuid4().hex,
    )
    await mysql_session.commit()

    assert result.deleted == 1
    restantes = (
        await mysql_session.execute(
            select(AuditLog.entity_id).where(
                AuditLog.entity_id.in_([920001, 920002])
            )
        )
    ).scalars().all()
    assert list(restantes) == [920002]


@pytest.mark.mysql
async def test_t21_plan_del_delete_es_aceptable(
    mysql_session: AsyncSession,
) -> None:
    """T21 — documenta el plan del ``DELETE``, sin exigir un índice.

    ``occurred_at`` no está indexado a propósito (``data-model.md`` §1.1): la
    purga es mensual y fuera del camino de request, así que el escaneo completo
    de §7 es una decisión, no un descuido. La prueba sólo verifica que el plan
    se puede obtener y deja el tipo de acceso en el mensaje.
    """
    from sqlalchemy import text as sa_text

    cutoff = datetime(2024, 5, 5, 4, 3, 2)
    plan = (
        await mysql_session.execute(
            sa_text("EXPLAIN DELETE FROM audit_log WHERE occurred_at < :cutoff"),
            {"cutoff": cutoff},
        )
    ).fetchall()

    assert plan, "EXPLAIN DELETE no devolvió filas"
    assert plan is not None, f"plan del DELETE = {plan!r}"
