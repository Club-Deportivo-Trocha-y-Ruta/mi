"""Tests del hotfix "identidad de válida" (2026-09-16, ver
``~/.claude/plans/multicopa-identidad-valida.md``) para
``app/models/athlete_ai_insight.py``.

Cubre:

- :func:`compute_insight_scope_key` — helper puro, sin DB (season summary,
  válida anclada a evento, válida legada sin evento, sentinel ``valida_num
  IS NULL``).
- El listener ``before_insert``/``before_update`` de ``AthleteAiInsight``
  fija ``insight_scope_key`` automáticamente — ningún caller (ORM
  ``AthleteAiInsight(...)`` + ``db.add``) necesita setearlo a mano.
- El nuevo UNIQUE parcial ``uq_insights_active_scope (athlete_id,
  insight_scope_key, is_active)`` reemplaza a ``uq_insights_active_terna``:
  dos insights activos del mismo atleta/temporada/``valida_num`` pero de
  DOS EVENTOS distintos (dos copas corriendo el mismo número de válida)
  ahora coexisten — exactamente el bug real que motivó el hotfix. El mismo
  ``event_id`` repetido sigue siendo un choque (IntegrityError). El
  agregado de temporada (``valida_num=0``) conserva su unicidad de siempre
  (una sola fila activa por atleta/temporada, sin importar copa).

Estrategia: SQLite async in-memory, mismo patrón que
``tests/services/race/test_insights_history.py`` — reusa las fixtures
compartidas de ``tests/fixtures/race_history_fixtures.py``.
"""
from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.athlete_ai_insight import compute_insight_scope_key
from app.models.user import UserRole
from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
    create_race_event,
    create_race_series,
    create_user,
)
from tests.helpers.audit_tables import AUDIT_TABLES


# ---------------------------------------------------------------------------
# compute_insight_scope_key — helper puro, sin DB
# ---------------------------------------------------------------------------


def test_scope_key_season_summary_ignores_event_id():
    """``valida_num == 0`` (season_summary) siempre colapsa a
    ``season:{season}`` — incluso si por algún motivo viniera con event_id
    (no debería pasar en la práctica, pero la regla de orden lo garantiza:
    UNA sola fila activa por atleta/temporada sin importar copa)."""
    assert compute_insight_scope_key(season=2026, valida_num=0, event_id=None) == "season:2026"
    assert compute_insight_scope_key(season=2026, valida_num=0, event_id=999) == "season:2026"


def test_scope_key_event_anchored_valida():
    """Válida con ``event_id`` resuelto (camino nuevo, post-hotfix) →
    ``event:{event_id}`` — no ambiguo entre copas aunque compartan
    ``valida_num``."""
    assert compute_insight_scope_key(season=2026, valida_num=4, event_id=43) == "event:43"
    # Dos copas, mismo valida_num=4, mismo season, pero distinto event_id →
    # claves DISTINTAS (esto es lo que arregla el bug real).
    assert compute_insight_scope_key(
        season=2026, valida_num=4, event_id=43
    ) != compute_insight_scope_key(season=2026, valida_num=4, event_id=99)


def test_scope_key_legacy_valida_without_event_id():
    """Insight legado (v1/v2 pre-hotfix) sin ``event_id`` → cae al
    comportamiento histórico por ``(season, valida_num)``."""
    assert compute_insight_scope_key(season=2026, valida_num=4, event_id=None) == "valida:2026:4"


def test_scope_key_legacy_valida_num_none_sentinel():
    """``valida_num=None`` (analíticas multi-temporada futuras, no
    implementado) usa el sentinel literal ``"none"``."""
    assert (
        compute_insight_scope_key(season=2026, valida_num=None, event_id=None)
        == "valida:2026:none"
    )


# ---------------------------------------------------------------------------
# Fixtures SQLite (mismo patrón que test_insights_history.py)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "athletes",
            "race_series",
            "race_events",
            "athlete_ai_insights",
            *AUDIT_TABLES,
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Sesión + seed mínimo: club + coach + 1 atleta + 2 copas (2026) con
    ambas una válida ``sequence_number=4`` — reproduce el escenario real
    del bug (Copa Valle V4 vs Copa Let's Go V4 del mismo atleta)."""
    async with session_factory() as s:
        await create_club(s, club_id=1)
        await create_user(s, user_id=10, role=UserRole.coach)
        await create_user(s, user_id=144, role=UserRole.athlete, can_login=False)
        await create_athlete(s, athlete_id=144, club_id=1, user_id=144)
        await create_race_series(s, series_id=1, season_year=2026, name="Copa Valle de Ciclomontanismo")
        await create_race_series(s, series_id=2, season_year=2026, name="Copa Let's Go Interdepartamental XCO")
        await s.commit()
        yield s


# ---------------------------------------------------------------------------
# Listener before_insert/before_update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_listener_fills_scope_key_on_insert_without_caller_setting_it(session):
    """Ningún caller pasa ``insight_scope_key`` explícitamente (igual que
    ``persist_insight.py`` / ``create_insight`` fixture) — el listener
    ``before_insert`` lo calcula solo al hacer flush."""
    event = await create_race_event(session, event_id=43, series_id=2, sequence_number=4)
    insight = await create_insight(
        session, athlete_id=144, season=2026, valida_num=4, event_id=event.id, is_active=1
    )
    assert insight.insight_scope_key == "event:43"


@pytest.mark.asyncio
async def test_listener_recomputes_scope_key_on_update(session):
    """``before_update`` recalcula la clave si ``event_id`` cambia después
    de creada la fila (ej. una corrección administrativa)."""
    event_a = await create_race_event(session, event_id=43, series_id=1, sequence_number=4)
    event_b = await create_race_event(session, event_id=99, series_id=2, sequence_number=4)
    insight = await create_insight(
        session, athlete_id=144, season=2026, valida_num=4, event_id=event_a.id, is_active=1
    )
    assert insight.insight_scope_key == "event:43"

    insight.event_id = event_b.id
    await session.flush()
    assert insight.insight_scope_key == "event:99"


# ---------------------------------------------------------------------------
# uq_insights_active_scope — el fix real
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_active_insights_same_valida_num_different_event_coexist(session):
    """El bug real: Copa Valle V4 (event_id=43) y Copa Let's Go V4
    (event_id=99) del MISMO atleta, ambas activas simultáneamente. Con el
    UNIQUE viejo (``athlete_id, season, valida_num, is_active``) esto era
    imposible — la segunda INSERT chocaba con la primera. Con
    ``insight_scope_key`` (``event:43`` vs ``event:99``) ambas coexisten."""
    copa_valle_event = await create_race_event(
        session, event_id=43, series_id=1, sequence_number=4, name="Copa Valle V4"
    )
    lets_go_event = await create_race_event(
        session, event_id=99, series_id=2, sequence_number=4, name="Copa Let's Go V4"
    )

    copa_valle_insight = await create_insight(
        session,
        athlete_id=144,
        season=2026,
        valida_num=4,
        event_id=copa_valle_event.id,
        is_active=1,
    )
    lets_go_insight = await create_insight(
        session,
        athlete_id=144,
        season=2026,
        valida_num=4,
        event_id=lets_go_event.id,
        is_active=1,
    )
    await session.commit()

    assert copa_valle_insight.insight_scope_key == "event:43"
    assert lets_go_insight.insight_scope_key == "event:99"
    # Ambas siguen activas — ninguna se pisó a la otra.
    await session.refresh(copa_valle_insight)
    assert copa_valle_insight.is_active == 1
    assert copa_valle_insight.deprecated_at is None


@pytest.mark.asyncio
async def test_same_event_id_twice_active_raises_integrity_error(session):
    """Dos insights activos anclados al MISMO evento siguen chocando — el
    fix no relaja la unicidad dentro de una misma válida, solo entre
    copas distintas."""
    event = await create_race_event(session, event_id=43, series_id=1, sequence_number=4)
    await create_insight(
        session, athlete_id=144, season=2026, valida_num=4, event_id=event.id, is_active=1
    )
    # create_insight ya hace flush() internamente — el choque del UNIQUE lo
    # dispara ese flush, no un commit posterior.
    with pytest.raises(IntegrityError):
        await create_insight(
            session, athlete_id=144, season=2026, valida_num=4, event_id=event.id, is_active=1
        )


@pytest.mark.asyncio
async def test_season_summary_uniqueness_unchanged(session):
    """El agregado de temporada (``valida_num=0``, sin ``event_id``) sigue
    permitiendo solo UNA fila activa por atleta/temporada — sin importar
    cuántas copas corrió esa temporada. No debe regresar por el hotfix."""
    await create_insight(
        session, athlete_id=144, season=2026, valida_num=0, use_case="season_summary_v2",
        event_id=None, is_active=1,
    )
    # create_insight ya hace flush() internamente — el choque del UNIQUE lo
    # dispara ese flush, no un commit posterior.
    with pytest.raises(IntegrityError):
        await create_insight(
            session, athlete_id=144, season=2026, valida_num=0, use_case="season_summary_v2",
            event_id=None, is_active=1,
        )
