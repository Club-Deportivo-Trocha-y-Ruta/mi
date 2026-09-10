"""Gasto de IA por entrenador — ``contracts/scope-ai-imports.md`` §7.1 y §11.1.

``spend_by_user_last_30d`` agrupa el costo de la ventana móvil por quien lanzó
el análisis (``agent_runs.requested_by_user_id``), con respaldo a
``athlete_ai_insights.generated_by_user_id`` cuando el insight nació sin run
enlazado. La invariante que sostiene toda la superficie (FR-029, US6 AC4) es de
reconciliación: **la suma de las filas iguala el total del guard de
presupuesto**; un ``JOIN`` interno la rompería en silencio.

Arnés: SQLite in-memory real, no un doble de sesión — la agregación es SQL
crudo con ``JSON_EXTRACT`` y un ``LEFT JOIN``, así que un fake que despache por
substrings del SQL verificaría el fake, no la query.

Dos arneses, a propósito:

- ``session`` usa el esquema REAL (``Base.metadata``). Ahí
  ``athlete_ai_insights.generated_by_user_id`` y
  ``agent_runs.requested_by_user_id`` son ambos ``NOT NULL``, así que el
  ``COALESCE`` de §7.1 nunca puede dar ``NULL``: con el esquema de hoy toda
  fila queda atribuida.
- ``legacy_session`` relaja esas dos columnas con DDL propio para ejercitar el
  cubo "Sin atribuir" que el contrato exige (§7.1, §11.1-16). Es la forma de
  una fila anterior a la restricción o de un esquema futuro que la afloje.

Privacidad (Ley 1581): esta superficie sólo expone nombres de staff adulto y
montos en dólares. Ningún menor aparece aquí.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Optional

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.agent_run import AgentRun  # noqa: F401  (registra agent_runs)
from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.user import UserRole
from app.services.race.ai.budget_guard import (
    UNATTRIBUTED_LABEL,
    _sum_cost_last_30d,
    spend_by_user_last_30d,
)

pytestmark = pytest.mark.asyncio


COACH_A_ID = 10
COACH_B_ID = 11
#: Aparece como actor en ``agent_runs`` pero NO tiene fila en ``users``:
#: nombre irresoluble (§4.1).
COACH_BORRADO_ID = 99

COACH_A_NAME = "Ana Ficticia Coach"
COACH_B_NAME = "Beto Ficticio Coach"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_next_id = {"run": 0, "insight": 0}


# ---------------------------------------------------------------------------
# Arnés con el esquema real
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """Sesión SQLite con las tablas reales que toca la agregación."""
    # Importes sólo para registrar los modelos en ``Base.metadata``.
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.club import Club as _Cl  # noqa: F401
    from app.models.user import User as _U  # noqa: F401

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in ("users", "clubs", "athletes", "agent_runs", "athlete_ai_insights")
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

    _next_id["run"] = 0
    _next_id["insight"] = 0
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await _seed_staff(s)
        await s.commit()
        yield s
    await engine.dispose()


async def _seed_staff(s: AsyncSession) -> None:
    """Dos entrenadores ficticios. El id 99 se deja SIN fila a propósito."""
    from app.models.user import User

    for uid, first, last in (
        (COACH_A_ID, "Ana Ficticia", "Coach"),
        (COACH_B_ID, "Beto Ficticio", "Coach"),
    ):
        s.add(
            User(
                id=uid,
                email=f"coach{uid}@test.local",
                hashed_password="x",
                first_name=first,
                last_name=last,
                role=UserRole.coach,
                is_active=True,
                can_login=True,
                created_at=_utc_now(),
            )
        )
    await s.flush()


_INSERT_RUN = """
INSERT INTO agent_runs (
    id, external_run_id, graph_name, prompt_version, started_at,
    status, requested_by_user_id, checkpoint_thread_id, created_at, updated_at
) VALUES (
    :id, :rid, 'race-analyst', 'race_analyst_v3', :now,
    'completed', :uid, :rid, :now, :now
)
"""


async def _add_run(s: AsyncSession, *, requested_by: Optional[int]) -> int:
    """Inserta una fila de ``agent_runs`` y devuelve su id."""
    _next_id["run"] += 1
    run_id = _next_id["run"]
    now = _utc_now()
    await s.execute(
        text(_INSERT_RUN),
        {"id": run_id, "rid": f"run-{run_id}", "uid": requested_by, "now": now},
    )
    return run_id


async def _add_insight(
    s: AsyncSession,
    *,
    cost: float,
    generated_by: Optional[int],
    agent_run_id: Optional[int] = None,
    generated_at: Optional[datetime] = None,
) -> None:
    """Inserta un ``athlete_ai_insights`` con su costo en el snapshot.

    Vía ORM para heredar los valores por defecto del modelo (``confidence``,
    ``is_active``, …) en vez de repetir aquí la lista de columnas obligatorias.
    """
    _next_id["insight"] += 1
    s.add(
        AthleteAiInsight(
            id=_next_id["insight"],
            athlete_id=1,
            agent_run_id=agent_run_id,
            generated_by_user_id=generated_by,
            season=2026,
            use_case="race_analysis",
            summary_text="Texto sintetico",
            recommendations_json=[],
            metrics_snapshot_json={"aggregate": {"cost_usd_total": cost}},
            principles_cited_json=[],
            model="modelo-ficticio",
            prompt_version="race_analyst_v3",
            generated_at=generated_at or _utc_now(),
            # ``created_at`` / ``updated_at`` tienen server_default de MySQL,
            # que SQLite no provee: se ponen a mano en este arnés.
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
    )
    await s.flush()


def _by_uid(rows) -> dict[Optional[int], object]:
    return {r.user_id: r for r in rows}


# ---------------------------------------------------------------------------
# Arnés "legado": las dos FK de atribución aflojadas a NULL
# ---------------------------------------------------------------------------


_LEGACY_DDL = (
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        first_name TEXT,
        last_name TEXT
    )
    """,
    """
    CREATE TABLE agent_runs (
        id INTEGER PRIMARY KEY,
        requested_by_user_id INTEGER
    )
    """,
    """
    CREATE TABLE athlete_ai_insights (
        id INTEGER PRIMARY KEY,
        agent_run_id INTEGER,
        generated_by_user_id INTEGER,
        metrics_snapshot_json TEXT,
        generated_at TIMESTAMP
    )
    """,
)


@pytest_asyncio.fixture
async def legacy_session() -> AsyncGenerator[AsyncSession, None]:
    """Esquema mínimo con ``generated_by_user_id`` y ``requested_by_user_id``
    anulables — el único escenario en que el ``COALESCE`` de §7.1 puede dar
    ``NULL`` y aparecer el cubo "Sin atribuir".
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        for ddl in _LEGACY_DDL:
            await conn.execute(text(ddl))
        await conn.execute(
            text(
                "INSERT INTO users (id, first_name, last_name) "
                "VALUES (:id, 'Ana Ficticia', 'Coach')"
            ),
            {"id": COACH_A_ID},
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _add_legacy_insight(
    s: AsyncSession,
    *,
    insight_id: int,
    cost: float,
    agent_run_id: Optional[int] = None,
    generated_by: Optional[int] = None,
) -> None:
    await s.execute(
        text(
            """
            INSERT INTO athlete_ai_insights (
                id, agent_run_id, generated_by_user_id,
                metrics_snapshot_json, generated_at
            ) VALUES (:id, :arid, :gby, :metrics, :gat)
            """
        ),
        {
            "id": insight_id,
            "arid": agent_run_id,
            "gby": generated_by,
            "metrics": json.dumps({"aggregate": {"cost_usd_total": cost}}),
            "gat": _utc_now(),
        },
    )


# ===========================================================================
# 15. Reparto entre dos entrenadores
# ===========================================================================


async def test_tres_insights_de_dos_coaches_dan_dos_filas(session):
    """§11.1-15: el reparto por entrenador es exacto, con nombre y conteo."""
    run_a1 = await _add_run(session, requested_by=COACH_A_ID)
    run_a2 = await _add_run(session, requested_by=COACH_A_ID)
    run_b = await _add_run(session, requested_by=COACH_B_ID)
    await _add_insight(session, cost=0.20, agent_run_id=run_a1, generated_by=COACH_A_ID)
    await _add_insight(session, cost=0.30, agent_run_id=run_a2, generated_by=COACH_A_ID)
    await _add_insight(session, cost=0.05, agent_run_id=run_b, generated_by=COACH_B_ID)
    await session.commit()

    rows = await spend_by_user_last_30d(session)

    assert len(rows) == 2
    # ``ORDER BY cost DESC``: primero quien más gastó.
    assert [r.user_id for r in rows] == [COACH_A_ID, COACH_B_ID]

    por_uid = _by_uid(rows)
    assert por_uid[COACH_A_ID].display_name == COACH_A_NAME
    assert por_uid[COACH_A_ID].run_count == 2
    assert abs(por_uid[COACH_A_ID].cost_usd_total - 0.50) < 1e-6
    assert por_uid[COACH_B_ID].display_name == COACH_B_NAME
    assert por_uid[COACH_B_ID].run_count == 1
    assert abs(por_uid[COACH_B_ID].cost_usd_total - 0.05) < 1e-6


async def test_el_run_manda_sobre_generated_by_user_id(session):
    """La clave de atribución es quien LANZÓ el run (R-24), no quien lo generó.

    Un insight cuyo run es del coach A pero cuya columna
    ``generated_by_user_id`` apunta al coach B se atribuye a A.
    """
    run_a = await _add_run(session, requested_by=COACH_A_ID)
    await _add_insight(session, cost=0.42, agent_run_id=run_a, generated_by=COACH_B_ID)
    await session.commit()

    rows = await spend_by_user_last_30d(session)

    assert [r.user_id for r in rows] == [COACH_A_ID]


async def test_insight_sin_run_se_atribuye_por_generated_by_user_id(session):
    """``agent_run_id`` es nullable: el ``COALESCE`` de §7.1 salva la fila.

    Un ``JOIN`` interno la dejaría fuera y rompería la reconciliación.
    """
    run_a = await _add_run(session, requested_by=COACH_A_ID)
    await _add_insight(session, cost=0.10, agent_run_id=run_a, generated_by=COACH_A_ID)
    await _add_insight(session, cost=0.40, agent_run_id=None, generated_by=COACH_A_ID)
    await session.commit()

    rows = await spend_by_user_last_30d(session)

    assert len(rows) == 1
    assert rows[0].user_id == COACH_A_ID
    assert rows[0].run_count == 2
    assert abs(rows[0].cost_usd_total - 0.50) < 1e-6


# ===========================================================================
# 16. Invariante de reconciliación (FR-029, US6 AC4)
# ===========================================================================


async def test_la_suma_por_entrenador_iguala_el_total_del_guard(session):
    """§11.1-16: ninguna fila se pierde por el camino.

    El escenario incluye a propósito los casos que un ``JOIN`` interno o una
    resolución de nombres descuidada dejarían fuera: un insight sin run
    enlazado, uno cuyo run apunta a un id que ya no existe en ``users``, y uno
    cuyo ``agent_run_id`` apunta a un run inexistente.
    """
    run_a = await _add_run(session, requested_by=COACH_A_ID)
    run_b = await _add_run(session, requested_by=COACH_B_ID)
    run_borrado = await _add_run(session, requested_by=COACH_BORRADO_ID)

    await _add_insight(session, cost=0.125, agent_run_id=run_a, generated_by=COACH_A_ID)
    await _add_insight(session, cost=0.250, agent_run_id=run_b, generated_by=COACH_B_ID)
    await _add_insight(
        session, cost=0.375, agent_run_id=run_borrado, generated_by=COACH_A_ID
    )
    # Sin run enlazado: cae al respaldo por ``generated_by_user_id``.
    await _add_insight(session, cost=0.500, agent_run_id=None, generated_by=COACH_B_ID)
    # Run enlazado que ya no existe: el LEFT JOIN da NULL y también cae al
    # respaldo. Con un JOIN interno esta fila desaparecería.
    await _add_insight(session, cost=0.625, agent_run_id=4242, generated_by=COACH_B_ID)
    await session.commit()

    rows = await spend_by_user_last_30d(session)
    total_guard = await _sum_cost_last_30d(session)

    assert abs(sum(r.cost_usd_total for r in rows) - total_guard) < 1e-6
    assert abs(total_guard - 1.875) < 1e-6
    assert sum(r.run_count for r in rows) == 5
    assert {r.user_id for r in rows} == {COACH_A_ID, COACH_B_ID, COACH_BORRADO_ID}


async def test_actor_que_ya_no_resuelve_es_usuario_no_disponible(session):
    """§4.1: con la FK puesta nunca sale un identificador crudo (FR-013)."""
    run_borrado = await _add_run(session, requested_by=COACH_BORRADO_ID)
    await _add_insight(
        session, cost=0.15, agent_run_id=run_borrado, generated_by=COACH_A_ID
    )
    await session.commit()

    rows = await spend_by_user_last_30d(session)

    assert len(rows) == 1
    assert rows[0].user_id == COACH_BORRADO_ID
    assert rows[0].display_name == "Usuario no disponible"
    assert rows[0].display_name != f"user#{COACH_BORRADO_ID}"


async def test_con_el_esquema_de_hoy_toda_fila_queda_atribuida(session):
    """Guardia de regresión sobre el esquema, no sobre la query.

    ``athlete_ai_insights.generated_by_user_id`` y
    ``agent_runs.requested_by_user_id`` son ``NOT NULL``, así que el
    ``COALESCE`` de §7.1 no puede dar ``NULL`` y el cubo "Sin atribuir" no
    aparece nunca en producción. Si esta prueba empieza a fallar es porque
    alguna de las dos columnas se aflojó — y entonces la fila ``user_id: null``
    del contrato pasa a ser alcanzable de verdad.
    """
    from app.models.agent_run import AgentRun as _Run
    from app.models.athlete_ai_insight import AthleteAiInsight as _Insight

    assert _Insight.__table__.c["generated_by_user_id"].nullable is False
    assert _Run.__table__.c["requested_by_user_id"].nullable is False

    run_a = await _add_run(session, requested_by=COACH_A_ID)
    await _add_insight(session, cost=0.10, agent_run_id=run_a, generated_by=COACH_A_ID)
    await _add_insight(session, cost=0.20, agent_run_id=None, generated_by=COACH_B_ID)
    await session.commit()

    rows = await spend_by_user_last_30d(session)

    assert all(r.user_id is not None for r in rows)
    assert all(r.display_name != UNATTRIBUTED_LABEL for r in rows)


async def test_existe_el_cubo_sin_atribuir(legacy_session):
    """§7.1: ``uid`` nulo → ``user_id`` en ``None`` y etiqueta "Sin atribuir".

    Requiere el arnés con las columnas de atribución anulables: ver la nota
    del docstring del módulo y ``test_con_el_esquema_de_hoy_toda_fila_queda_atribuida``.
    """
    await legacy_session.execute(
        text(
            "INSERT INTO agent_runs (id, requested_by_user_id) VALUES (1, NULL)"
        )
    )
    await _add_legacy_insight(legacy_session, insight_id=1, cost=0.30, agent_run_id=1)
    await _add_legacy_insight(legacy_session, insight_id=2, cost=0.20)
    await _add_legacy_insight(
        legacy_session, insight_id=3, cost=0.05, generated_by=COACH_A_ID
    )
    await legacy_session.commit()

    rows = await spend_by_user_last_30d(legacy_session)

    por_uid = _by_uid(rows)
    assert None in por_uid, "falta el cubo sin atribuir"
    sin_atribuir = por_uid[None]
    assert sin_atribuir.display_name == UNATTRIBUTED_LABEL == "Sin atribuir"
    assert sin_atribuir.run_count == 2
    assert abs(sin_atribuir.cost_usd_total - 0.50) < 1e-6

    # La reconciliación se mantiene con el cubo incluido.
    total_guard = await _sum_cost_last_30d(legacy_session)
    assert abs(sum(r.cost_usd_total for r in rows) - total_guard) < 1e-6
    assert por_uid[COACH_A_ID].display_name == COACH_A_NAME


# ===========================================================================
# 17. Ventana vacía y recorte por fecha
# ===========================================================================


async def test_ventana_vacia_devuelve_lista_vacia(session):
    """§11.1-17: sin insights, ``[]`` — no una fila de ceros."""
    assert await spend_by_user_last_30d(session) == []
    assert await _sum_cost_last_30d(session) == 0.0


async def test_los_insights_fuera_de_la_ventana_no_cuentan(session):
    """El corte es el mismo ``generated_at >= :cutoff`` del guard."""
    run_a = await _add_run(session, requested_by=COACH_A_ID)
    run_b = await _add_run(session, requested_by=COACH_B_ID)
    await _add_insight(session, cost=0.40, agent_run_id=run_a, generated_by=COACH_A_ID)
    await _add_insight(
        session,
        cost=9.99,
        agent_run_id=run_b,
        generated_by=COACH_B_ID,
        generated_at=_utc_now() - timedelta(days=45),
    )
    await session.commit()

    rows = await spend_by_user_last_30d(session)

    assert [r.user_id for r in rows] == [COACH_A_ID]
    assert abs(sum(r.cost_usd_total for r in rows) - 0.40) < 1e-6
    # Y la reconciliación sigue en pie con la misma ventana de 30 días.
    total_guard = await _sum_cost_last_30d(session)
    assert abs(sum(r.cost_usd_total for r in rows) - total_guard) < 1e-6


async def test_el_parametro_days_recorta_la_ventana(session):
    """``days`` es el único mando de la ventana; 30 es su valor por defecto."""
    run_a = await _add_run(session, requested_by=COACH_A_ID)
    run_b = await _add_run(session, requested_by=COACH_B_ID)
    await _add_insight(session, cost=0.10, agent_run_id=run_a, generated_by=COACH_A_ID)
    await _add_insight(
        session,
        cost=0.90,
        agent_run_id=run_b,
        generated_by=COACH_B_ID,
        generated_at=_utc_now() - timedelta(days=10),
    )
    await session.commit()

    assert len(await spend_by_user_last_30d(session, days=30)) == 2
    recorte = await spend_by_user_last_30d(session, days=7)
    assert [r.user_id for r in recorte] == [COACH_A_ID]
