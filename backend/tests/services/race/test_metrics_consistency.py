"""Feature 045 (T018, SC-002) — every surface reports the same race metrics.

Historial, Evolución, Detalle de competencia (coach y familia) y el contexto del
analista de IA obtienen Parrilla, Percentil, Brecha vs. mediana, Brecha vs.
1.ª posición y Brecha vs. podio del motor único (``field_metrics``). Este test
siembra UNA categoría realista y exige que cada superficie devuelva, para cada
atleta, exactamente los valores del oráculo escrito a mano de abajo.

Por qué un oráculo a mano y no "comparar superficies entre sí": si el motor
cambiara de fórmula, las cuatro superficies seguirían coincidiendo y ninguna
comparación cruzada lo notaría. Las cifras del oráculo salen de la fórmula de
``specs/045-competitions-one-place/data-model.md`` §1 (comentadas en la tabla).

Escenarios (mismo evento, tres categorías):

* ``BIG``     — 6 cronometrados + 1 MINUS_LAPS + 1 DNF. Parrilla = 7,
                cronometrados = 6; el MINUS_LAPS cuenta en Parrilla pero no
                tiene percentil ni brechas.
* ``SMALL``   — 4 cronometrados (< ``MIN_FIELD``): percentil y brecha vs.
                mediana son ``None`` en TODAS las superficies; las brechas
                oficiales (1.ª posición / podio) no llevan puerta de tamaño
                (research R-04) y siguen calculándose.
* ``UNTIMED`` — 5 cronometrados + 1 FINISHED sin tiempo ("clasificado sin
                tiempo" de las actas históricas, migración 044): cuenta en
                Parrilla pero no es comparable en tiempo.

Agregar una superficie = un adaptador ``async (env, rider) -> dict`` y una
entrada en ``SURFACES``. Todos los nombres son ficticios (Ley 1581).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, AsyncGenerator, Awaitable, Callable, Optional

import pandas as pd
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.race_result import ResultStatus
from app.models.user import UserRole
from app.schemas.athlete_race_analysis import EvolutionMetric
from app.services.race.ai.db import set_db_factory
from app.services.race.ai.nodes import compute_metrics as analyst_node
from app.services.race.analytics_charts import build_evolution
from app.services.race.field_metrics import MIN_FIELD
from app.services.race.history import build_history_points
from app.services.race.queries import (
    load_categories,
    load_events,
    load_results,
    load_series,
)
from app.services.race.results_read import get_event_results
from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
)
from tests.helpers.audit_tables import AUDIT_TABLES

SEASON = 2026
CLUB_ID = 1
COACH_USER_ID = 10
SERIES_ID = 41
EVENT_ID = 4100

BIG, SMALL, UNTIMED = "big", "small", "untimed"
_CATEGORY_ID = {BIG: 71, SMALL: 72, UNTIMED: 73}
_CATEGORY_CODE = {BIG: "INF_M_T018", SMALL: "INF_F_T018", UNTIMED: "JUV_M_T018"}

# ---------------------------------------------------------------------------
# Escenario: quién corre, con qué tiempo y si es del club
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rider:
    label: str
    category: str
    position: Optional[int]
    status: ResultStatus = ResultStatus.FINISHED
    race_time_ms: Optional[int] = None
    laps_behind: Optional[int] = None
    club: bool = True  # False → rival ajeno: solo entra al denominador del campo


_F, _ML, _DNF = ResultStatus.FINISHED, ResultStatus.MINUS_LAPS, ResultStatus.DNF

RIDERS: tuple[Rider, ...] = (
    # BIG — tiempos 200/205/210/220/230/240 s; p2 y p5 son rivales ajenos.
    Rider("p1", BIG, 1, _F, 200_000),
    Rider("p2", BIG, 2, _F, 205_000, club=False),
    Rider("p3", BIG, 3, _F, 210_000),
    Rider("p4", BIG, 4, _F, 220_000),
    Rider("p5", BIG, 5, _F, 230_000, club=False),
    Rider("p6", BIG, 6, _F, 240_000),
    Rider("minus_laps", BIG, 7, _ML, laps_behind=1),
    Rider("dnf", BIG, None, _DNF),
    # SMALL — 4 cronometrados; s2 es rival ajeno.
    Rider("s1", SMALL, 1, _F, 300_000),
    Rider("s2", SMALL, 2, _F, 312_000, club=False),
    Rider("s3", SMALL, 3, _F, 324_000),
    Rider("s4", SMALL, 4, _F, 336_000),
    # UNTIMED — 5 cronometrados + 1 FINISHED sin tiempo; u2/u4/u5 ajenos.
    Rider("u1", UNTIMED, 1, _F, 400_000),
    Rider("u2", UNTIMED, 2, _F, 410_000, club=False),
    Rider("u3", UNTIMED, 3, _F, 420_000),
    Rider("u4", UNTIMED, 4, _F, 430_000, club=False),
    Rider("u5", UNTIMED, 5, _F, 440_000, club=False),
    Rider("u_untimed", UNTIMED, 6, _F, None),
)

_RIDER_INDEX = {r.label: i for i, r in enumerate(RIDERS, start=1)}
_ATHLETE_BASE, _COMPETITOR_BASE = 300, 700  # ids distintos a propósito


def _athlete_id(rider: Rider) -> Optional[int]:
    return _ATHLETE_BASE + _RIDER_INDEX[rider.label] if rider.club else None


def _competitor_id(rider: Rider) -> int:
    return _COMPETITOR_BASE + _RIDER_INDEX[rider.label]


def _club_riders(category: str) -> list[Rider]:
    return [r for r in RIDERS if r.category == category and r.club]


# ---------------------------------------------------------------------------
# Oráculo (a mano). Fórmulas de data-model.md §1 sobre los tiempos de arriba.
#
# BIG:  t_min=200 000, t_max=240 000, mediana=(210 000+220 000)/2=215 000,
#       P1=200 000, P3=210 000.
#       percentil = round(100·(1−(t−200 000)/40 000))
#       vs. mediana = 100·(t−215 000)/215 000; vs. P1 = 100·(t−200 000)/200 000;
#       vs. P3 = 100·(t−210 000)/210 000 (1 decimal).
# SMALL: sin percentil ni mediana (4 < MIN_FIELD). P1=300 000, P3=324 000.
# UNTIMED: t_min=400 000, t_max=440 000, mediana=420 000, P1=400 000, P3=420 000.
# ---------------------------------------------------------------------------

_NONE_TIME_METRICS: dict[str, Any] = {
    "percentile": None,
    "gap_to_median_pct": None,
    "gap_to_winner_pct": None,
    "gap_to_winner_ms": None,
    "gap_to_podium_pct": None,
    "gap_to_podium_ms": None,
}


def _big(position: int, pct: float, med: float, win: float, win_ms: int, pod: float, pod_ms: int):
    return {
        "field_size": 7, "timed_finishers": 6, "position": position,
        "percentile": pct, "gap_to_median_pct": med,
        "gap_to_winner_pct": win, "gap_to_winner_ms": win_ms,
        "gap_to_podium_pct": pod, "gap_to_podium_ms": pod_ms,
    }


def _small(position: int, win: float, win_ms: int, pod: float, pod_ms: int):
    return {
        "field_size": 4, "timed_finishers": 4, "position": position,
        "percentile": None, "gap_to_median_pct": None,  # 4 < MIN_FIELD
        "gap_to_winner_pct": win, "gap_to_winner_ms": win_ms,
        "gap_to_podium_pct": pod, "gap_to_podium_ms": pod_ms,
    }


EXPECTED: dict[str, dict[str, Any]] = {
    #        pos  pctl  vs med  vs P1  ms P1   vs P3  ms P3
    "p1": _big(1, 100.0, -7.0, 0.0, 0, -4.8, -10_000),
    "p2": _big(2, 88.0, -4.7, 2.5, 5_000, -2.4, -5_000),  # 87.5 → 88
    "p3": _big(3, 75.0, -2.3, 5.0, 10_000, 0.0, 0),
    "p4": _big(4, 50.0, 2.3, 10.0, 20_000, 4.8, 10_000),
    "p5": _big(5, 25.0, 7.0, 15.0, 30_000, 9.5, 20_000),
    "p6": _big(6, 0.0, 11.6, 20.0, 40_000, 14.3, 30_000),
    # Terminó con vueltas de menos: cuenta en Parrilla, no es comparable en tiempo.
    "minus_laps": {"field_size": 7, "timed_finishers": 6, "position": 7, **_NONE_TIME_METRICS},
    "dnf": {"field_size": 7, "timed_finishers": 6, "position": None, **_NONE_TIME_METRICS},
    "s1": _small(1, 0.0, 0, -7.4, -24_000),
    "s2": _small(2, 4.0, 12_000, -3.7, -12_000),
    "s3": _small(3, 8.0, 24_000, 0.0, 0),
    "s4": _small(4, 12.0, 36_000, 3.7, 12_000),
    "u1": {
        "field_size": 6, "timed_finishers": 5, "position": 1, "percentile": 100.0,
        "gap_to_median_pct": -4.8, "gap_to_winner_pct": 0.0, "gap_to_winner_ms": 0,
        "gap_to_podium_pct": -4.8, "gap_to_podium_ms": -20_000,
    },
    "u3": {
        "field_size": 6, "timed_finishers": 5, "position": 3, "percentile": 50.0,
        "gap_to_median_pct": 0.0, "gap_to_winner_pct": 5.0, "gap_to_winner_ms": 20_000,
        "gap_to_podium_pct": 0.0, "gap_to_podium_ms": 0,
    },
    "u_untimed": {"field_size": 6, "timed_finishers": 5, "position": 6, **_NONE_TIME_METRICS},
}

# ---------------------------------------------------------------------------
# Entorno: sqlite en memoria sembrada con el escenario
# ---------------------------------------------------------------------------

_TABLES = (
    "users", "clubs", "athletes", "race_series", "race_events", "race_categories",
    "race_competitors", "race_results", "race_course_variants",
    "race_course_category_setups", *AUDIT_TABLES,
)


@dataclass
class Env:
    factory: async_sessionmaker[AsyncSession]
    session: AsyncSession
    results: list
    events: list
    series: list
    categories: list


async def _seed(session: AsyncSession) -> None:
    await create_club(session, club_id=CLUB_ID, name="Club Ficticio T018", code="t018")
    await create_user(session, user_id=COACH_USER_ID, role=UserRole.coach)
    await create_race_series(session, series_id=SERIES_ID, season_year=SEASON, name="Copa Ficticia T018")
    await create_race_event(
        session, event_id=EVENT_ID, series_id=SERIES_ID, sequence_number=1,
        name="Válida ficticia", event_date=date(2026, 3, 1), created_by_user_id=COACH_USER_ID,
    )
    for category, category_id in _CATEGORY_ID.items():
        await create_race_category(
            session, category_id=category_id, code=_CATEGORY_CODE[category],
            label=f"Categoría ficticia {category}",
        )
    for rider in RIDERS:
        athlete_id = _athlete_id(rider)
        if athlete_id is not None:
            user_id = 1000 + athlete_id
            await create_user(session, user_id=user_id, role=UserRole.parent, can_login=False)
            await create_athlete(
                session, athlete_id=athlete_id, first_name=f"Ficticio {rider.label}",
                last_name="Prueba", birth_date=date(2013, 1, 1), club_id=CLUB_ID,
                user_id=user_id, created_by=COACH_USER_ID,
            )
        await create_race_competitor(
            session, competitor_id=_competitor_id(rider),
            normalized_name=f"ficticio {rider.label}", display_name=f"Ficticio {rider.label}",
            club_text="Club Ficticio T018" if rider.club else "Club Rival Ficticio",
            athlete_id=athlete_id,
        )
        result = await create_race_result(
            session, event_id=EVENT_ID, category_id=_CATEGORY_ID[rider.category],
            competitor_id=_competitor_id(rider), athlete_id=athlete_id,
            position=rider.position, status=rider.status, race_time_ms=rider.race_time_ms,
            bib_number=_RIDER_INDEX[rider.label], created_by_user_id=COACH_USER_ID,
        )
        if rider.laps_behind is not None:
            result.laps_behind = rider.laps_behind
    await session.commit()


@pytest_asyncio.fixture
async def env() -> AsyncGenerator[Env, None]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _seed(session)
        # El analista abre sus propias sesiones desde la fábrica inyectada.
        set_db_factory(factory)
        try:
            yield Env(
                factory=factory,
                session=session,
                results=await load_results(session),
                events=await load_events(session),
                series=await load_series(session),
                categories=await load_categories(session),
            )
        finally:
            set_db_factory(None)
    await engine.dispose()


# ---------------------------------------------------------------------------
# Adaptadores: una superficie → dict normalizado (nombres canónicos del motor)
# ---------------------------------------------------------------------------

_FAMILY_KEYS = frozenset(
    {"field_size", "timed_finishers", "position", "percentile", "gap_to_median_pct"}
)
_WINNER_PCT = frozenset({"gap_to_winner_pct"})
_PODIUM_PCT = frozenset({"gap_to_podium_pct"})
_MS_GAPS = frozenset({"gap_to_winner_ms", "gap_to_podium_ms"})


async def _read_history(env: Env, rider: Rider) -> dict[str, Any]:
    points = build_history_points(
        env.results, env.events, env.series, env.categories,
        athlete_id=_athlete_id(rider), series_kind="all",
    )
    (point,) = [p for p in points if p.event_id == EVENT_ID]
    return {
        "field_size": point.field_size,
        "timed_finishers": point.timed_finishers,
        "position": point.position,
        "percentile": point.percentile,
        "gap_to_median_pct": point.gap_to_median_pct,
        "gap_to_winner_pct": point.gap_to_winner_pct,
        "gap_to_podium_pct": point.gap_to_podium_pct,
    }


async def _read_evolution(env: Env, rider: Rider) -> dict[str, Any]:
    """Evolución no expone ``timed_finishers`` ni la brecha vs. podio; la brecha
    vs. 1.ª posición en ms viaja en el ``value`` de ``podium_gap_ms`` (nombre
    heredado: siempre midió contra el ganador)."""
    kwargs = {"athlete_id": _athlete_id(rider), "season": SEASON}
    by_percentile = await build_evolution(env.session, metric=EvolutionMetric.PERCENTILE, **kwargs)
    by_gap_ms = await build_evolution(env.session, metric=EvolutionMetric.PODIUM_GAP_MS, **kwargs)
    (point,) = by_percentile.series
    (gap_point,) = by_gap_ms.series
    return {
        "field_size": point.field_size,
        "position": point.position,
        "percentile": point.percentile,
        "gap_to_median_pct": point.gap_to_median_pct,
        "gap_to_winner_pct": point.gap_pct,
        "gap_to_winner_ms": gap_point.value,
    }


def _row_metrics(payload: Any, rider: Rider) -> dict[str, Any]:
    (row,) = [
        r
        for category in payload.categories
        for r in category.rows
        if r.competitor_id == _competitor_id(rider)
    ]
    return row.metrics.model_dump()


async def _read_results_coach(env: Env, rider: Rider) -> dict[str, Any]:
    return _row_metrics(await get_event_results(env.session, EVENT_ID), rider)


async def _read_results_family(env: Env, rider: Rider) -> dict[str, Any]:
    payload = await get_event_results(env.session, EVENT_ID, allowed_athlete_ids={_athlete_id(rider)})
    return _row_metrics(payload, rider)


async def _read_analyst(env: Env, rider: Rider) -> dict[str, Any]:
    """Contexto del analista (``compute_metrics``). Sus dos consumidores —
    ``field_context`` y ``metrics["field"]``— son el mismo objeto; se exige.
    ``athlete_progression``/``podium_gap`` no son parte de lo medido aquí y se
    reemplazan por vacíos (mismo patrón que ``nodes/test_compute_metrics.py``)."""
    update = await analyst_node.compute_metrics(
        {"competitor_id": _competitor_id(rider), "category_id": _CATEGORY_ID[rider.category], "season": SEASON}
    )
    assert update["metrics"]["field"] == update["field_context"]
    m = update["field_context"][EVENT_ID]
    return {
        "field_size": m["field_size"],
        "timed_finishers": m["timed_finishers"],
        "position": m["position"],
        "percentile": m["percentile"],
        "gap_to_median_pct": m["gap_to_median_pct"],
        "gap_to_winner_pct": m["gap_pct"],  # nombre heredado de la 037
        "gap_to_winner_ms": m["gap_to_p1_ms"],
        "gap_to_podium_pct": m["gap_to_podium_pct"],
        "gap_to_podium_ms": m["gap_to_p3_ms"],
    }


@dataclass(frozen=True)
class Surface:
    name: str
    read: Callable[[Env, Rider], Awaitable[dict[str, Any]]]
    keys: frozenset[str]  # lo que la superficie DEBE exponer (y nada más)


SURFACES: tuple[Surface, ...] = (
    Surface("history", _read_history, _FAMILY_KEYS | _WINNER_PCT | _PODIUM_PCT),
    Surface(
        "evolution", _read_evolution,
        (_FAMILY_KEYS - {"timed_finishers"}) | _WINNER_PCT | {"gap_to_winner_ms"},
    ),
    Surface("results_coach", _read_results_coach, _FAMILY_KEYS | _WINNER_PCT | _PODIUM_PCT | _MS_GAPS),
    Surface("results_family", _read_results_family, _FAMILY_KEYS),
    Surface("analyst", _read_analyst, _FAMILY_KEYS | _WINNER_PCT | _PODIUM_PCT | _MS_GAPS),
)


@pytest.fixture(autouse=True)
def _analyst_without_progression(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _empty_progression(_db: Any, _competitor_id: int) -> pd.DataFrame:
        return pd.DataFrame()

    async def _empty_podium(_db: Any, _category_id: int, _season: int) -> pd.DataFrame:
        return pd.DataFrame()

    monkeypatch.setattr(analyst_node, "athlete_progression", _empty_progression)
    monkeypatch.setattr(analyst_node, "podium_gap", _empty_podium)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_scenario_shape_matches_the_spec() -> None:
    """Guarda del escenario: nadie debilita la siembra sin que este test lo note."""
    big = [r for r in RIDERS if r.category == BIG]
    assert sum(r.status == _F and r.race_time_ms is not None for r in big) == 6
    assert sum(r.status == _ML for r in big) == 1
    assert sum(r.status == _DNF for r in big) == 1
    small = [r for r in RIDERS if r.category == SMALL]
    assert sum(r.race_time_ms is not None for r in small) == MIN_FIELD - 1
    assert {r.label for r in RIDERS if r.club} <= set(EXPECTED)
    assert all(_club_riders(c) for c in (BIG, SMALL, UNTIMED))


@pytest.mark.parametrize("category", [BIG, SMALL, UNTIMED])
@pytest.mark.parametrize("surface", SURFACES, ids=lambda s: s.name)
@pytest.mark.asyncio
async def test_surface_reports_the_engine_values_for_every_athlete(
    env: Env, surface: Surface, category: str
) -> None:
    """Cada superficie devuelve, por atleta, exactamente los valores del oráculo.

    Acumula todas las discrepancias para que el fallo muestre qué atleta y qué
    campo difieren (``(obtenido, esperado)``)."""
    mismatches: dict[str, dict[str, tuple[Any, Any]]] = {}
    for rider in _club_riders(category):
        got = await surface.read(env, rider)
        assert set(got) == surface.keys, f"{surface.name}: expone {sorted(got)}"
        diff = {
            key: (got[key], EXPECTED[rider.label][key])
            for key in got
            if got[key] != EXPECTED[rider.label][key]
        }
        if diff:
            mismatches[rider.label] = diff
    assert not mismatches, f"{surface.name}/{category}: {mismatches}"


@pytest.mark.asyncio
async def test_below_min_field_no_surface_exposes_percentile_or_median_gap(env: Env) -> None:
    """Con 4 cronometrados (< MIN_FIELD) ninguna superficie da percentil ni
    brecha vs. mediana — pero sí Parrilla, y las brechas oficiales siguen."""
    for surface in SURFACES:
        for rider in _club_riders(SMALL):
            got = await surface.read(env, rider)
            assert got["percentile"] is None, (surface.name, rider.label)
            assert got["gap_to_median_pct"] is None, (surface.name, rider.label)
            assert got["field_size"] == 4, (surface.name, rider.label)
            if "gap_to_winner_pct" in got:  # la familia nunca lo recibe
                assert got["gap_to_winner_pct"] is not None, (surface.name, rider.label)


@pytest.mark.asyncio
async def test_minus_laps_is_counted_in_the_field_but_never_compared_in_time(env: Env) -> None:
    """El MINUS_LAPS suma a Parrilla (7) y no tiene percentil ni brechas, y su
    presencia no altera el percentil del resto (6 cronometrados, no 7)."""
    minus_laps = next(r for r in RIDERS if r.label == "minus_laps")
    slowest = next(r for r in RIDERS if r.label == "p6")
    for surface in SURFACES:
        lapped = await surface.read(env, minus_laps)
        assert lapped["field_size"] == 7, surface.name
        assert lapped["percentile"] is None, surface.name
        assert lapped.get("gap_to_winner_pct") is None, surface.name  # la familia no lo recibe
        assert (await surface.read(env, slowest))["percentile"] == 0.0, surface.name
