"""Tests unitarios del módulo ``app.services.race.queries`` (F1 race-results v2).

Cobertura: loaders crudos, df builders y primitivas agenticas (``athlete_exists``,
``fetch_results_for_athlete``, ``fetch_podium_context``). Re-usa el
``FakeAsyncSession`` del ``conftest.py`` race.

Estrategia de seed: dataset minimal determinístico — 1 series, 4 events,
1 categoría INF_A, 1 atleta TyR + 2 rivales, 4 resultados por válida.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

import pandas as pd
import pytest

from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.services.race.queries import (
    athlete_exists,
    categories_to_df,
    events_to_df,
    fetch_podium_context,
    fetch_results_for_athlete,
    load_categories,
    load_competitors,
    load_events,
    load_results,
    load_series,
    results_to_df,
)
from tests.services.race.conftest import FakeAsyncSession, _Store


_SEASON = 2026
_OTHER_SEASON = 2025
_INF_A_CODE = "INF_A"
_ATHLETE_ID = 42


# ---------------------------------------------------------------------------
# Helpers de seed
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed_series(store: _Store, season: int = _SEASON) -> RaceSeries:
    sid = store.next_id("series")
    s = RaceSeries(
        id=sid,
        name=f"Copa Valle {season}",
        season_year=season,
        organizer="Liga",
        points_scheme_code="copa_valle_2026",
    )
    store.series[sid] = s
    return s


def _seed_events(store: _Store, series_id: int, count: int = 4) -> list[RaceEvent]:
    events: list[RaceEvent] = []
    for i in range(1, count + 1):
        eid = store.next_id("events")
        ev = RaceEvent(
            id=eid,
            series_id=series_id,
            sequence_number=i,
            name=f"VALIDA {i}",
            event_date=date(2026, i, 15),
            location="X",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=1,
        )
        store.events[eid] = ev
        events.append(ev)
    return events


def _seed_competitor(
    store: _Store,
    display_name: str,
    *,
    athlete_id: Optional[int] = None,
    club_text: str = "Club Trocha y Ruta",
) -> RaceCompetitor:
    cid = store.next_id("competitors")
    c = RaceCompetitor(
        id=cid,
        normalized_name=display_name.lower(),
        display_name=display_name,
        club_text=club_text,
        athlete_id=athlete_id,
    )
    store.competitors[cid] = c
    return c


def _seed_result(
    store: _Store,
    *,
    event_id: int,
    category_id: int,
    competitor_id: int,
    athlete_id: Optional[int],
    position: Optional[int],
    race_time_ms: Optional[int],
    points: int = 0,
    status: ResultStatus = ResultStatus.FINISHED,
    deleted_at: Optional[datetime] = None,
) -> RaceResult:
    rid = store.next_id("results")
    r = RaceResult(
        id=rid,
        event_id=event_id,
        category_id=category_id,
        competitor_id=competitor_id,
        athlete_id=athlete_id,
        position=position,
        status=status,
        race_time_ms=race_time_ms,
        points_awarded=points,
        deleted_at=deleted_at,
        created_by_user_id=1,
    )
    store.results[rid] = r
    return r


def _get_inf_a_id(store: _Store) -> int:
    for c in store.categories.values():
        if c.code == _INF_A_CODE:
            return c.id
    raise KeyError(_INF_A_CODE)


# ---------------------------------------------------------------------------
# Fixture: dataset compartido por todos los tests
# ---------------------------------------------------------------------------


@pytest.fixture
def race_db(fake_session: FakeAsyncSession) -> FakeAsyncSession:
    """4 válidas Copa Valle 2026, INF_A, 1 TyR + 2 rivales, 4 resultados x 3."""
    store = fake_session.store
    series = _seed_series(store, season=_SEASON)
    events = _seed_events(store, series.id, count=4)
    cat_id = _get_inf_a_id(store)

    tyr = _seed_competitor(store, "Thiago Duque", athlete_id=_ATHLETE_ID)
    rival_p1 = _seed_competitor(
        store, "Rival Uno", athlete_id=None, club_text="Otro Club"
    )
    rival_other = _seed_competitor(
        store, "Rival Dos", athlete_id=None, club_text="Otro Club B"
    )

    # Posiciones TyR por válida: [3, 2, 2, 1] (evolución hacia el podio).
    tyr_positions = [3, 2, 2, 1]
    tyr_times = [1_800_000, 1_700_000, 1_650_000, 1_600_000]
    for ev, pos, t in zip(events, tyr_positions, tyr_times):
        _seed_result(
            store,
            event_id=ev.id,
            category_id=cat_id,
            competitor_id=tyr.id,
            athlete_id=_ATHLETE_ID,
            position=pos,
            race_time_ms=t,
            points=10,
        )
        # Rival siempre P1 (1_500_000 ms) excepto V4 donde TyR gana.
        if pos != 1:
            _seed_result(
                store,
                event_id=ev.id,
                category_id=cat_id,
                competitor_id=rival_p1.id,
                athlete_id=None,
                position=1,
                race_time_ms=1_500_000,
            )
        # Rival P2 cuando TyR es P3 (V1), o P3 cuando TyR es P2 (V2/V3).
        _seed_result(
            store,
            event_id=ev.id,
            category_id=cat_id,
            competitor_id=rival_other.id,
            athlete_id=None,
            position=2 if pos == 3 else (3 if pos in (2, 1) else None),
            race_time_ms=1_700_000,
        )

    return fake_session


# ---------------------------------------------------------------------------
# Loaders crudos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_results_filtra_deleted_at(race_db: FakeAsyncSession) -> None:
    """``load_results`` excluye filas con ``deleted_at`` not null."""
    # Marcar 1 resultado como eliminado.
    store = race_db.store
    first_id = next(iter(store.results))
    store.results[first_id].deleted_at = _now()

    res = await load_results(race_db)
    assert all(r.deleted_at is None for r in res)
    assert len(res) == len(store.results) - 1


@pytest.mark.asyncio
async def test_load_events_devuelve_todos(race_db: FakeAsyncSession) -> None:
    events = await load_events(race_db)
    assert len(events) == 4
    assert {e.sequence_number for e in events} == {1, 2, 3, 4}


@pytest.mark.asyncio
async def test_load_categories_devuelve_26_seedeadas(
    fake_session: FakeAsyncSession,
) -> None:
    cats = await load_categories(fake_session)
    assert len(cats) == 26
    assert any(c.code == _INF_A_CODE for c in cats)


@pytest.mark.asyncio
async def test_load_competitors_3(race_db: FakeAsyncSession) -> None:
    comps = await load_competitors(race_db)
    assert len(comps) == 3
    # 1 TyR confirmado + 2 con athlete_id None.
    confirmed = [c for c in comps if c.athlete_id is not None]
    assert len(confirmed) == 1
    assert confirmed[0].athlete_id == _ATHLETE_ID


@pytest.mark.asyncio
async def test_load_series_1(race_db: FakeAsyncSession) -> None:
    series = await load_series(race_db)
    assert len(series) == 1
    assert series[0].season_year == _SEASON


# ---------------------------------------------------------------------------
# DataFrame builders
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_events_to_df_columnas_y_iso(race_db: FakeAsyncSession) -> None:
    events = await load_events(race_db)
    df = events_to_df(events)
    assert list(df.columns) == ["event_id", "series_id", "valida_num", "event_date"]
    # Fechas serializadas como ISO string (no datetime.date).
    assert all(isinstance(d, str) for d in df["event_date"])
    assert df.iloc[0]["event_date"] == "2026-01-15"


def test_events_to_df_vacio() -> None:
    df = events_to_df([])
    assert df.empty
    assert list(df.columns) == ["event_id", "series_id", "valida_num", "event_date"]


@pytest.mark.asyncio
async def test_categories_to_df_tier_str(fake_session: FakeAsyncSession) -> None:
    cats = await load_categories(fake_session)
    df = categories_to_df(cats)
    # tier serializa como string (enum.value), no objeto Enum.
    tiers = df["tier"].dropna().unique().tolist()
    assert all(isinstance(t, str) for t in tiers)
    assert "menores" in tiers


@pytest.mark.asyncio
async def test_results_to_df_status_str_y_nullable_time(
    race_db: FakeAsyncSession,
) -> None:
    results = await load_results(race_db)
    df = results_to_df(results)
    # status como string, no enum.
    assert all(isinstance(s, str) for s in df["status"].dropna())
    # race_time_ms es numérico (Python int) o NaN.
    assert df["race_time_ms"].notna().all()


# ---------------------------------------------------------------------------
# athlete_exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_athlete_exists_true(race_db: FakeAsyncSession) -> None:
    assert await athlete_exists(race_db, _ATHLETE_ID) is True


@pytest.mark.asyncio
async def test_athlete_exists_false_id_inexistente(
    race_db: FakeAsyncSession,
) -> None:
    assert await athlete_exists(race_db, 99_999) is False


@pytest.mark.asyncio
async def test_athlete_exists_ignora_deleted(race_db: FakeAsyncSession) -> None:
    """Si todos los resultados del atleta están deleted → False."""
    store = race_db.store
    for r in store.results.values():
        if r.athlete_id == _ATHLETE_ID:
            r.deleted_at = _now()
    assert await athlete_exists(race_db, _ATHLETE_ID) is False


# ---------------------------------------------------------------------------
# fetch_results_for_athlete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_results_for_athlete_season_y_orden(
    race_db: FakeAsyncSession,
) -> None:
    res = await fetch_results_for_athlete(race_db, _ATHLETE_ID, _SEASON)
    assert len(res) == 4
    # Orden cronológico → sequence_number ascendente (fechas crecen con i).
    valida_nums = [
        next(e.sequence_number for e in race_db.store.events.values() if e.id == r.event_id)
        for r in res
    ]
    assert valida_nums == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_fetch_results_for_athlete_filtro_valida_nums(
    race_db: FakeAsyncSession,
) -> None:
    res = await fetch_results_for_athlete(
        race_db, _ATHLETE_ID, _SEASON, valida_nums=[2, 4]
    )
    assert len(res) == 2
    valida_nums = sorted(
        next(e.sequence_number for e in race_db.store.events.values() if e.id == r.event_id)
        for r in res
    )
    assert valida_nums == [2, 4]


@pytest.mark.asyncio
async def test_fetch_results_for_athlete_season_inexistente(
    race_db: FakeAsyncSession,
) -> None:
    res = await fetch_results_for_athlete(race_db, _ATHLETE_ID, _OTHER_SEASON)
    assert res == []


@pytest.mark.asyncio
async def test_fetch_results_for_athlete_id_inexistente(
    race_db: FakeAsyncSession,
) -> None:
    res = await fetch_results_for_athlete(race_db, 99_999, _SEASON)
    assert res == []


# ---------------------------------------------------------------------------
# fetch_podium_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_podium_context_v1_podio_completo(
    race_db: FakeAsyncSession,
) -> None:
    """V1: rival_p1 P1 (1_500_000ms), rival_other P2 (1_700_000ms), TyR P3 (1_800_000ms)."""
    store = race_db.store
    event_v1 = next(e for e in store.events.values() if e.sequence_number == 1)
    cat_id = _get_inf_a_id(store)

    ctx = await fetch_podium_context(race_db, cat_id, event_v1.id)
    assert ctx["category_id"] == cat_id
    assert ctx["event_id"] == event_v1.id
    assert ctx["finishers_count"] == 3
    podium = ctx["podium"]
    assert [p["position"] for p in podium] == [1, 2, 3]
    assert podium[0]["race_time_ms"] == 1_500_000
    assert podium[2]["race_time_ms"] == 1_800_000


@pytest.mark.asyncio
async def test_fetch_podium_context_evento_inexistente(
    race_db: FakeAsyncSession,
) -> None:
    cat_id = _get_inf_a_id(race_db.store)
    ctx = await fetch_podium_context(race_db, cat_id, event_id=9999)
    assert ctx["podium"] == []
    assert ctx["finishers_count"] == 0


@pytest.mark.asyncio
async def test_fetch_podium_context_solo_p1_p2(race_db: FakeAsyncSession) -> None:
    """V4: TyR P1 (1_600_000), rival_other P3 None de tiempo. Solo cuentan FINISHED.

    Construimos un evento adicional con solo 2 finishers (P1 y P2).
    """
    store = race_db.store
    series_id = next(iter(store.series))
    new_event = RaceEvent(
        id=store.next_id("events"),
        series_id=series_id,
        sequence_number=99,
        name="EXTRA",
        event_date=date(2026, 7, 1),
        location="X",
        is_championship=False,
        status=RaceEventStatus.COMPLETED,
        created_by_user_id=1,
    )
    store.events[new_event.id] = new_event
    cat_id = _get_inf_a_id(store)
    comp_p1 = next(iter(store.competitors))
    comp_p2 = list(store.competitors.keys())[1]
    _seed_result(
        store,
        event_id=new_event.id,
        category_id=cat_id,
        competitor_id=comp_p1,
        athlete_id=None,
        position=1,
        race_time_ms=1_000_000,
    )
    _seed_result(
        store,
        event_id=new_event.id,
        category_id=cat_id,
        competitor_id=comp_p2,
        athlete_id=None,
        position=2,
        race_time_ms=1_100_000,
    )

    ctx = await fetch_podium_context(race_db, cat_id, new_event.id)
    assert ctx["finishers_count"] == 2
    positions = [p["position"] for p in ctx["podium"]]
    assert positions == [1, 2]


@pytest.mark.asyncio
async def test_fetch_podium_context_ignora_dnf(race_db: FakeAsyncSession) -> None:
    """Resultados DNF/DSQ no entran al podium (solo FINISHED)."""
    store = race_db.store
    series_id = next(iter(store.series))
    ev = RaceEvent(
        id=store.next_id("events"),
        series_id=series_id,
        sequence_number=98,
        name="DNF_ONLY",
        event_date=date(2026, 8, 1),
        location="X",
        is_championship=False,
        status=RaceEventStatus.COMPLETED,
        created_by_user_id=1,
    )
    store.events[ev.id] = ev
    cat_id = _get_inf_a_id(store)
    comp = next(iter(store.competitors))
    _seed_result(
        store,
        event_id=ev.id,
        category_id=cat_id,
        competitor_id=comp,
        athlete_id=None,
        position=None,
        race_time_ms=None,
        status=ResultStatus.DNF,
    )
    ctx = await fetch_podium_context(race_db, cat_id, ev.id)
    assert ctx["finishers_count"] == 0
    assert ctx["podium"] == []
