"""``app_stack_spend_by_user_last_30d`` — feature 042, T069 (FR-022/FR-023).

Contexto: T069 extiende el módulo de gasto por entrenador de la feature 041
(``services/race/ai/budget_guard.py``) con una segunda serie, separada de la
del stack "race": el gasto del stack ``app/services/ai`` (feature 042),
leído directamente de las columnas de trazabilidad de
``athlete_ai_explanations`` (``cost_usd``, ``generated_by_user_id``,
``generated_at``) en vez del ``JSON_EXTRACT`` sobre ``athlete_ai_insights``
que usa la hermana ``spend_by_user_last_30d``.

Este módulo cubre:
- las filas legado (``schema_version IS NULL``, previas a la feature 042)
  nunca cuentan como gasto trazado de este stack (T15-16);
- el repliegue por club (hallazgo H3) se aplica también a esta serie
  (T17-18);
- cada fila trae ``stack="app"`` y nunca se mezcla con la serie "race"
  (T19-20);
- FR-023, el invariante crítico: sembrar filas en ``athlete_ai_explanations``
  NUNCA mueve el gasto que ve el guard de ``RACE_AI_BUDGET_USD_30D``, que
  lee exclusivamente ``athlete_ai_insights`` (T21-22).

Arnés: motor SQLite en memoria propio (patrón de
``tests/test_spend_by_user.py``) con sólo las tablas que este módulo
necesita — no se usa la fixture ``client``/``mysql_session``.

Privacidad (Ley 1581): esta superficie sólo expone nombres de staff adulto
(coach/admin) y montos en dólares; el atleta y la medición ficticios sólo
existen para satisfacer las FK NOT NULL de ``athlete_ai_explanations`` y no
viajan en ninguna aserción.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator, Optional

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.agent_run import AgentRun  # noqa: F401  (registra agent_runs)
from app.models.ai_explanation import AthleteAIExplanation
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.athlete import Athlete, Sex
from app.models.athlete_ai_insight import AthleteAiInsight  # noqa: F401  (registra athlete_ai_insights)
from app.models.club import Club
from app.models.user import User, UserRole
from app.services.race.ai.budget_guard import (
    OTHER_CLUBS_LABEL,
    UNATTRIBUTED_LABEL,
    _sum_cost_last_30d,
    app_stack_spend_by_user_last_30d,
    check_budget,
)

pytestmark = pytest.mark.asyncio

CLUB_ID = 1

COACH_A_ID = 10  # entrenador propio — quien hace la petición
OTHER_COACH_ID = 20  # entrenador ajeno — debe replegarse en H3

ATHLETE_USER_ID = 90
ATHLETE_ID = 900

COACH_A_NAME = "Ana Ficticia Coach"
OTHER_COACH_NAME = "Otro Club Ficticio Coach"

_TABLES = (
    "users",
    "clubs",
    "athletes",
    "anthropometric_records",
    "athlete_ai_explanations",
    # Sólo para la prueba FR-023: el guard de race lee esta tabla y no debe
    # fallar por "no such table" al confirmar que el gasto "app" no la toca.
    "athlete_ai_insights",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed_scenario(session: AsyncSession) -> None:
    """Un club, dos entrenadores (uno propio, uno ajeno) y un atleta ficticio."""
    session.add(Club(id=CLUB_ID, name="Club Ficticio 042", code="f042-a", is_active=True))
    await session.flush()

    for uid, first, last, role in (
        (COACH_A_ID, "Ana Ficticia", "Coach", UserRole.coach),
        (OTHER_COACH_ID, "Otro Club Ficticio", "Coach", UserRole.coach),
        (ATHLETE_USER_ID, "Atleta", "Ficticio", UserRole.parent),
    ):
        session.add(
            User(
                id=uid,
                email=f"user{uid}@test.local",
                hashed_password="x",
                first_name=first,
                last_name=last,
                role=role,
                is_active=True,
                can_login=(role != UserRole.parent),
                created_at=_utc_now(),
            )
        )
    await session.flush()

    session.add(
        Athlete(
            id=ATHLETE_ID,
            user_id=ATHLETE_USER_ID,
            first_name="Atleta",
            last_name="Ficticio",
            birth_date=date(2013, 6, 20),
            sex=Sex.M,
            club_id=CLUB_ID,
            created_by=COACH_A_ID,
        )
    )
    await session.flush()
    await session.commit()


_next_id = {"record": 0, "expl": 0}


async def _add_record(session: AsyncSession) -> int:
    _next_id["record"] += 1
    record_id = _next_id["record"]
    session.add(
        AnthropometricRecord(
            id=record_id,
            athlete_id=ATHLETE_ID,
            evaluation_date=date(2026, 3, 1),
            weight_kg=Decimal("40.00"),
            standing_height_cm=Decimal("150.0"),
            sitting_height_cm=Decimal("78.0"),
            leg_length_cm=Decimal("72.0"),
            leg_sitting_ratio=Decimal("0.9231"),
            maturity_offset=Decimal("0.50"),
            age_at_phv=Decimal("12.20"),
            maturation_status=MaturationStatus.circa_phv,
            evaluated_by=COACH_A_ID,
        )
    )
    await session.flush()
    return record_id


async def _add_explanation(
    session: AsyncSession,
    *,
    cost: Optional[float],
    generated_by: int,
    schema_version: Optional[str] = "v2",
    generated_at: Optional[datetime] = None,
) -> None:
    """Una fila de ``athlete_ai_explanations``.

    ``schema_version=None`` simula una fila legado (previa a la feature
    042, p.ej. ``phv_explainer``): nunca trae ``cost_usd`` — mismo estado
    que produce hoy el código en producción.
    """
    record_id = await _add_record(session)
    _next_id["expl"] += 1
    session.add(
        AthleteAIExplanation(
            id=_next_id["expl"],
            athlete_id=ATHLETE_ID,
            anthropometric_record_id=record_id,
            use_case="anthropometric_record_explainer",
            text="Texto sintetico de prueba.",
            model="modelo-ficticio",
            provider="fake",
            generated_at=generated_at or _utc_now(),
            age_group="10-15",
            maturation_status="circa_phv",
            schema_version=schema_version,
            cost_usd=(Decimal(str(cost)) if cost is not None else None),
            generated_by_user_id=generated_by,
        )
    )
    await session.flush()


def _by_uid(rows) -> dict[Optional[int], object]:
    return {r.user_id: r for r in rows}


# ===========================================================================
# Serie separada + label "app" (FR-022)
# ===========================================================================


async def test_filas_v2_se_agregan_por_entrenador_con_stack_app(session_factory):
    async with session_factory() as session:
        await _seed_scenario(session)
        await _add_explanation(session, cost=0.010000, generated_by=COACH_A_ID)
        await _add_explanation(session, cost=0.020000, generated_by=COACH_A_ID)
        await session.commit()

        rows = await app_stack_spend_by_user_last_30d(session, visible_user_ids=None)

        assert len(rows) == 1
        row = rows[0]
        assert row.user_id == COACH_A_ID
        assert row.display_name == COACH_A_NAME
        assert row.run_count == 2
        assert abs(row.cost_usd_total - 0.03) < 1e-6
        assert row.stack == "app"


async def test_filas_legado_sin_schema_version_no_cuentan(session_factory):
    """Una fila ``phv_explainer`` (033, previa a 042) no tiene las nueve
    columnas de trazabilidad — ``schema_version`` y ``cost_usd`` son NULL.
    No debe aparecer como gasto de este stack."""
    async with session_factory() as session:
        await _seed_scenario(session)
        await _add_explanation(
            session, cost=None, generated_by=COACH_A_ID, schema_version=None
        )
        await session.commit()

        rows = await app_stack_spend_by_user_last_30d(session, visible_user_ids=None)

        assert rows == []


async def test_ventana_de_dias_excluye_filas_viejas(session_factory):
    async with session_factory() as session:
        await _seed_scenario(session)
        old = _utc_now().replace(year=_utc_now().year - 1)
        await _add_explanation(session, cost=0.05, generated_by=COACH_A_ID, generated_at=old)
        await session.commit()

        rows = await app_stack_spend_by_user_last_30d(session, days=30, visible_user_ids=None)

        assert rows == []


# ===========================================================================
# Repliegue por club (hallazgo H3) aplicado también a este stack
# ===========================================================================


async def test_repliega_staff_ajeno_sin_nombrarlo(session_factory):
    async with session_factory() as session:
        await _seed_scenario(session)
        await _add_explanation(session, cost=0.10, generated_by=COACH_A_ID)
        await _add_explanation(session, cost=0.40, generated_by=OTHER_COACH_ID)
        await session.commit()

        rows = await app_stack_spend_by_user_last_30d(
            session, visible_user_ids={COACH_A_ID}
        )

        por_uid = _by_uid(rows)
        assert por_uid[COACH_A_ID].display_name == COACH_A_NAME
        assert OTHER_COACH_ID not in por_uid
        assert OTHER_COACH_NAME not in {r.display_name for r in rows}

        folded = next(r for r in rows if r.display_name == OTHER_CLUBS_LABEL)
        assert folded.user_id is None
        assert folded.run_count == 1
        assert abs(folded.cost_usd_total - 0.40) < 1e-6
        assert folded.stack == "app"
        assert UNATTRIBUTED_LABEL not in {r.display_name for r in rows}


async def test_admin_ve_todo_sin_repliegue(session_factory):
    async with session_factory() as session:
        await _seed_scenario(session)
        await _add_explanation(session, cost=0.10, generated_by=COACH_A_ID)
        await _add_explanation(session, cost=0.40, generated_by=OTHER_COACH_ID)
        await session.commit()

        rows = await app_stack_spend_by_user_last_30d(session, visible_user_ids=None)

        names = {r.display_name for r in rows}
        assert COACH_A_NAME in names
        assert OTHER_COACH_NAME in names
        assert OTHER_CLUBS_LABEL not in names


# ===========================================================================
# FR-023 — jamás alimenta el guard de RACE_AI_BUDGET_USD_30D
# ===========================================================================


async def test_gasto_del_stack_app_nunca_mueve_el_guard_de_race(session_factory):
    """Sembrar gasto "app" no debe mover ni un centavo el total que lee el
    budget guard de race (tabla distinta) — ni bloquear un run de race."""
    async with session_factory() as session:
        await _seed_scenario(session)
        # Gasto "app" muy por encima de cualquier presupuesto razonable.
        await _add_explanation(session, cost=999.0, generated_by=COACH_A_ID)
        await session.commit()

        total_race = await _sum_cost_last_30d(session)
        assert total_race == 0.0

        # El guard de race sigue OK con un presupuesto ínfimo: no hay NADA
        # en athlete_ai_insights, así que jamás dispara BudgetExceededError
        # por el gasto que acabamos de sembrar en el otro stack.
        await check_budget(session, max_cost_usd_30d=0.01)


async def test_reconciliacion_se_sostiene_tambien_acotada(session_factory):
    """El repliegue de esta serie también SUMA, nunca descarta (misma
    invariante que la hermana race, FR-029/US6 AC4)."""
    async with session_factory() as session:
        await _seed_scenario(session)
        await _add_explanation(session, cost=0.125, generated_by=COACH_A_ID)
        await _add_explanation(session, cost=0.625, generated_by=OTHER_COACH_ID)
        await session.commit()

        rows_unscoped = await app_stack_spend_by_user_last_30d(
            session, visible_user_ids=None
        )
        rows_scoped = await app_stack_spend_by_user_last_30d(
            session, visible_user_ids={COACH_A_ID}
        )

        total_unscoped = sum(r.cost_usd_total for r in rows_unscoped)
        total_scoped = sum(r.cost_usd_total for r in rows_scoped)
        assert abs(total_unscoped - total_scoped) < 1e-6
        assert abs(total_unscoped - 0.75) < 1e-6
