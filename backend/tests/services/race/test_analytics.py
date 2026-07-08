"""Tests del módulo ``app.services.race.analytics`` (Paso 5 Fase 1.7).

Estrategia: el ``FakeAsyncSession`` del ``conftest.py`` ya emula AsyncSession.
Aquí construimos un dataset mínimo determinístico (1 series + 4 events + 1
categoría INF_A + 1 competitor TyR + 4 race_results + 2 non-TyR) y validamos
las 4 funciones analíticas.

Cobertura ≥13 tests (workflow §5.3):
- ``athlete_progression`` (4 tests)
- ``podium_gap`` (3 tests)
- ``club_ranking`` (4 tests)
- ``projection`` (5 tests: n=4 low, n=6 medium, n=10 high, sin datos, n=1)
- JSON-serializability (1 test integrador)
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Optional

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_category import CategoryGender, CategoryTier, RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.services.race.analytics import (
    athlete_progression,
    club_ranking,
    podium_gap,
    projection,
)
from tests.services.race.conftest import FakeAsyncSession, _Store


# ---------------------------------------------------------------------------
# Helpers de seed
# ---------------------------------------------------------------------------


_SEASON = 2026

# Categoría INF_A (corresponde al seed pero la duplicamos local; usaremos la
# del fixture original ``fake_session`` cuando sea posible, y un seed alterno
# cuando necesitamos control adicional).

_INF_A_CODE = "INF_A"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed_series(store: _Store, season: int = _SEASON) -> RaceSeries:
    """Crea ``RaceSeries`` Copa Valle <season>."""
    sid = store.next_id("series")
    s = RaceSeries(
        id=sid,
        name="Copa Valle de Ciclomontañismo",
        season_year=season,
        organizer="Liga",
        points_scheme_code="copa_valle_2026",
    )
    store.series[sid] = s
    return s


def _seed_events(
    store: _Store, series_id: int, count: int = 4, base_date: date = date(2026, 1, 31)
) -> list[RaceEvent]:
    """Crea ``count`` ``RaceEvent`` para la series.

    Las fechas son consecutivas (~1 mes de separación) para validar el orden
    cronológico de ``athlete_progression``.
    """
    events: list[RaceEvent] = []
    for i in range(1, count + 1):
        eid = store.next_id("events")
        ev = RaceEvent(
            id=eid,
            series_id=series_id,
            sequence_number=i,
            name=f"VALIDA {i}",
            event_date=date(base_date.year, base_date.month, 1).replace(
                month=min(base_date.month + (i - 1), 12)
            ),
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
    points: int,
    status: ResultStatus = ResultStatus.FINISHED,
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
        created_by_user_id=1,
    )
    store.results[rid] = r
    return r


def _get_cat(store: _Store, code: str) -> RaceCategory:
    for c in store.categories.values():
        if c.code == code:
            return c
    raise KeyError(code)


@pytest.fixture
def analytics_session(fake_session: FakeAsyncSession) -> FakeAsyncSession:
    """Fixture sobre ``fake_session`` con dataset Paso 5:

    - 1 RaceSeries Copa Valle 2026.
    - 4 RaceEvents V-I..V-IV.
    - 1 competitor TyR confirmado (athlete_id=42) con resultados en INF_A.
    - 2 competitors non-TyR (control: no aparecen en club_ranking).
    - 4 race_results del TyR (uno por válida) con posiciones [3, 2, 2, 1]
      y tiempos [1_800_000, 1_700_000, 1_650_000, 1_600_000] ms.
    - Rivales para que existan P1 cuando el TyR no es P1 y un P3 cuando
      el TyR es P2/P3.
    """
    store = fake_session.store
    series = _seed_series(store, season=_SEASON)
    events = _seed_events(store, series.id, count=4)
    inf_a = _get_cat(store, _INF_A_CODE)

    # Competidor TyR confirmado (athlete_id != None).
    tyr = _seed_competitor(store, "Thiago Duque", athlete_id=42)
    # Dos competidores non-TyR: uno SIEMPRE P1 (rival rápido), otro variable.
    rival_p1 = _seed_competitor(store, "Rival Uno", athlete_id=None, club_text="Otro Club")
    rival_p3 = _seed_competitor(store, "Rival Tres", athlete_id=None, club_text="Otro Club B")

    # V1: TyR P3 1800ms (1800s), rival_p1 P1 1500s, rival_p3 P2 1700s.
    # V2: TyR P2 1700s, rival_p1 P1 1500s, rival_p3 P3 1750s.
    # V3: TyR P2 1650s, rival_p1 P1 1500s, rival_p3 P3 1720s.
    # V4: TyR P1 1600s, rival_p1 P2 1620s, rival_p3 P3 1700s.
    tyr_plan = [
        (1, 3, 1_800_000, 30),
        (2, 2, 1_700_000, 36),
        (3, 2, 1_650_000, 36),
        (4, 1, 1_600_000, 40),
    ]
    rival_p1_plan = [
        (1, 1, 1_500_000, 40),
        (2, 1, 1_500_000, 40),
        (3, 1, 1_500_000, 40),
        (4, 2, 1_620_000, 36),
    ]
    rival_p3_plan = [
        (1, 2, 1_700_000, 36),
        (2, 3, 1_750_000, 30),
        (3, 3, 1_720_000, 30),
        (4, 3, 1_700_000, 30),
    ]
    for plan, comp in [
        (tyr_plan, tyr),
        (rival_p1_plan, rival_p1),
        (rival_p3_plan, rival_p3),
    ]:
        for valida_num, pos, t_ms, pts in plan:
            ev = events[valida_num - 1]
            athlete_id = comp.athlete_id if comp is tyr else None
            _seed_result(
                store,
                event_id=ev.id,
                category_id=inf_a.id,
                competitor_id=comp.id,
                athlete_id=athlete_id,
                position=pos,
                race_time_ms=t_ms,
                points=pts,
            )

    return fake_session


# ===========================================================================
# 1. athlete_progression
# ===========================================================================


class TestAthleteProgression:
    @pytest.mark.asyncio
    async def test_returns_four_rows_sorted_by_event_date(
        self, analytics_session: FakeAsyncSession
    ):
        """4 válidas → 4 filas, orden ascendente por event_date."""
        tyr = next(
            c for c in analytics_session.store.competitors.values()
            if c.display_name == "Thiago Duque"
        )
        df = await athlete_progression(analytics_session, competitor_id=tyr.id)
        assert len(df) == 4
        # valida_num debe estar en orden ascendente porque event_date sigue ese orden
        assert list(df["valida_num"]) == [1, 2, 3, 4]
        assert list(df["position"]) == [3, 2, 2, 1]

    @pytest.mark.asyncio
    async def test_gap_to_winner_ms_calculated_correctly(
        self, analytics_session: FakeAsyncSession
    ):
        """gap_to_winner_ms = race_time_ms - P1_time. P1 → 0, otros > 0."""
        tyr = next(
            c for c in analytics_session.store.competitors.values()
            if c.display_name == "Thiago Duque"
        )
        df = await athlete_progression(analytics_session, competitor_id=tyr.id)
        # V1: TyR=1800, P1=1500 → gap=300000ms
        # V2: TyR=1700, P1=1500 → gap=200000ms
        # V3: TyR=1650, P1=1500 → gap=150000ms
        # V4: TyR=1600, P1=1600 (es él mismo) → gap=0
        assert list(df["gap_to_winner_ms"]) == [300_000, 200_000, 150_000, 0]

    @pytest.mark.asyncio
    async def test_gap_to_winner_pct_calculated_correctly(
        self, analytics_session: FakeAsyncSession
    ):
        """gap_to_winner_pct = (gap_ms / p1_ms) * 100."""
        tyr = next(
            c for c in analytics_session.store.competitors.values()
            if c.display_name == "Thiago Duque"
        )
        df = await athlete_progression(analytics_session, competitor_id=tyr.id)
        # V1: 300000/1500000 = 0.20 → 20.0
        # V2: 200000/1500000 ≈ 13.333
        # V4: 0/1600000 = 0.0
        assert df["gap_to_winner_pct"].iloc[0] == pytest.approx(20.0)
        assert df["gap_to_winner_pct"].iloc[1] == pytest.approx(13.333, abs=0.01)
        assert df["gap_to_winner_pct"].iloc[3] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_empty_when_competitor_has_no_results(
        self, analytics_session: FakeAsyncSession
    ):
        """Si el competidor no tiene results → DataFrame vacío con columnas."""
        df = await athlete_progression(analytics_session, competitor_id=99999)
        assert df.empty
        # Pero las columnas deben estar presentes para que .to_dict("records") sea estable.
        expected_cols = {
            "valida_num", "event_date", "category_code", "position",
            "race_time_ms", "points_awarded", "gap_to_winner_ms", "gap_to_winner_pct",
            "series_kind", "series_level", "location",
        }
        assert expected_cols == set(df.columns)


# ===========================================================================
# 2. podium_gap
# ===========================================================================


class TestPodiumGap:
    @pytest.mark.asyncio
    async def test_position_and_gap_to_p3_per_valida(
        self, analytics_session: FakeAsyncSession
    ):
        """TyR aparece en 4 válidas: pos 3, 2, 2, 1.

        - gap_to_p1: V1=300k, V2=200k, V3=150k, V4=0.
        - gap_to_p3: V1: TyR=P3 con time=1800k, P3=1800k → 0.
                     V2: TyR=P2 1700k, P3=1750k → -50k (negativo = mejor).
                     V3: TyR=P2 1650k, P3=1720k → -70k.
                     V4: TyR=P1 1600k, P3=1700k → -100k.
        """
        inf_a = _get_cat(analytics_session.store, _INF_A_CODE)
        df = await podium_gap(analytics_session, category_id=inf_a.id, season=_SEASON)
        # Solo 1 competitor TyR → 4 filas (una por válida).
        assert len(df) == 4
        assert list(df["position"]) == [3, 2, 2, 1]
        assert list(df["gap_to_p1_ms"]) == [300_000, 200_000, 150_000, 0]
        assert list(df["gap_to_p3_ms"]) == [0, -50_000, -70_000, -100_000]

    @pytest.mark.asyncio
    async def test_null_row_when_tyr_did_not_participate(
        self, analytics_session: FakeAsyncSession
    ):
        """Agregamos una V-V (válida 5) sin participación del TyR → fila NULL."""
        store = analytics_session.store
        # Crear V-5 con resultados de rivales pero no del TyR.
        v5_id = store.next_id("events")
        store.events[v5_id] = RaceEvent(
            id=v5_id,
            series_id=1,
            sequence_number=5,
            name="V-5",
            event_date=date(2026, 8, 1),
            location="X",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=1,
        )
        inf_a = _get_cat(store, _INF_A_CODE)
        # Rival ocupa P1 y P3 en V-5.
        rival_p1 = next(c for c in store.competitors.values() if c.display_name == "Rival Uno")
        rival_p3 = next(c for c in store.competitors.values() if c.display_name == "Rival Tres")
        _seed_result(
            store, event_id=v5_id, category_id=inf_a.id, competitor_id=rival_p1.id,
            athlete_id=None, position=1, race_time_ms=1_500_000, points=40,
        )
        _seed_result(
            store, event_id=v5_id, category_id=inf_a.id, competitor_id=rival_p3.id,
            athlete_id=None, position=3, race_time_ms=1_700_000, points=30,
        )

        df = await podium_gap(analytics_session, category_id=inf_a.id, season=_SEASON)
        assert len(df) == 5  # 1 TyR x 5 válidas
        # La fila V-5 del TyR debe ser NULL.
        v5_row = df[df["valida_num"] == 5].iloc[0]
        assert pd.isna(v5_row["position"])
        assert pd.isna(v5_row["gap_to_p1_ms"])
        assert pd.isna(v5_row["gap_to_p3_ms"])

    @pytest.mark.asyncio
    async def test_empty_when_no_tyr_in_category(
        self, fake_session: FakeAsyncSession
    ):
        """Sin TyR (athlete_id NULL) → DataFrame vacío."""
        store = fake_session.store
        _seed_series(store)
        events = _seed_events(store, series_id=1, count=2)
        inf_a = _get_cat(store, _INF_A_CODE)
        # Solo un competidor con athlete_id=None.
        c = _seed_competitor(store, "Sin Match", athlete_id=None, club_text="Trocha y Ruta")
        for ev in events:
            _seed_result(
                store, event_id=ev.id, category_id=inf_a.id,
                competitor_id=c.id, athlete_id=None, position=1,
                race_time_ms=1_500_000, points=40,
            )
        df = await podium_gap(fake_session, category_id=inf_a.id, season=_SEASON)
        assert df.empty


# ===========================================================================
# 3. club_ranking
# ===========================================================================


class TestClubRanking:
    @pytest.mark.asyncio
    async def test_by_category_only_counts_tyr_with_athlete_id(
        self, analytics_session: FakeAsyncSession
    ):
        """Sólo competitors con athlete_id NOT NULL suman puntos."""
        ranking = await club_ranking(analytics_session, season=_SEASON)
        # 4 races para TyR INF_A → 30+36+36+40 = 142
        inf_a_bucket = [b for b in ranking["by_category"] if b["category_code"] == _INF_A_CODE]
        assert len(inf_a_bucket) == 1
        assert inf_a_bucket[0]["total_points"] == 142
        # 1 win (V4), 2 podiums (V4 P1 + V2 P2 + V3 P2 + V1 P3) — todas son podio.
        assert inf_a_bucket[0]["podiums"] == 4
        assert inf_a_bucket[0]["wins"] == 1
        assert inf_a_bucket[0]["active_riders"] == 1

    @pytest.mark.asyncio
    async def test_total_points_equals_sum_of_by_category(
        self, analytics_session: FakeAsyncSession
    ):
        """``total_points`` = sum(by_category.total_points)."""
        ranking = await club_ranking(analytics_session, season=_SEASON)
        sum_cat = sum(b["total_points"] for b in ranking["by_category"])
        assert ranking["total_points"] == sum_cat
        assert ranking["total_wins"] == 1
        assert ranking["total_podiums"] == 4

    @pytest.mark.asyncio
    async def test_distribution_by_tier_counts_unique_riders(
        self, analytics_session: FakeAsyncSession
    ):
        """INF_A pertenece al tier 'menores' → 1 rider único en menores."""
        ranking = await club_ranking(analytics_session, season=_SEASON)
        dist = ranking["distribution_by_tier"]
        assert dist["menores"] == 1
        assert dist["juvenil"] == 0
        assert dist["adulto"] == 0
        assert dist["master"] == 0
        assert ranking["active_riders"] == 1

    @pytest.mark.asyncio
    async def test_empty_when_no_events_in_season(
        self, fake_session: FakeAsyncSession
    ):
        """Sin events en la temporada → estructura vacía pero válida."""
        ranking = await club_ranking(fake_session, season=2099)
        assert ranking["by_category"] == []
        assert ranking["total_points"] == 0
        assert ranking["total_podiums"] == 0
        assert ranking["total_wins"] == 0
        assert ranking["active_riders"] == 0
        assert ranking["distribution_by_tier"] == {
            "menores": 0, "juvenil": 0, "adulto": 0, "master": 0,
        }


# ===========================================================================
# 4. projection
# ===========================================================================


class TestProjection:
    @pytest.mark.asyncio
    async def test_projection_with_n4_marks_confidence_low(
        self, analytics_session: FakeAsyncSession
    ):
        """n=4 historiales (V1..V4) → ``confidence='low'``."""
        store = analytics_session.store
        tyr = next(c for c in store.competitors.values() if c.display_name == "Thiago Duque")
        # Crear V-5 evento (target) y proyectar.
        v5_id = store.next_id("events")
        store.events[v5_id] = RaceEvent(
            id=v5_id, series_id=1, sequence_number=5,
            name="V-5", event_date=date(2026, 8, 1), location="X",
            is_championship=False, status=RaceEventStatus.COMPLETED,
            created_by_user_id=1,
        )
        out = await projection(analytics_session, competitor_id=tyr.id, next_event_id=v5_id)
        assert out["n_samples"] == 4
        assert out["confidence"] == "low"
        assert out["expected_position"] is not None
        # Tendencia descendente (P3→P1) → proyectada V-5 ≈ 0 pero clipada a 1.0.
        assert out["expected_position"] >= 1.0
        assert out["expected_race_time_ms"] is not None

    @pytest.mark.asyncio
    async def test_projection_with_n6_marks_confidence_medium(
        self, analytics_session: FakeAsyncSession
    ):
        """Agregamos V-5, V-6 con resultados → n=6 → medium."""
        store = analytics_session.store
        tyr = next(c for c in store.competitors.values() if c.display_name == "Thiago Duque")
        inf_a = _get_cat(store, _INF_A_CODE)

        for vn in (5, 6):
            eid = store.next_id("events")
            store.events[eid] = RaceEvent(
                id=eid, series_id=1, sequence_number=vn,
                name=f"V-{vn}", event_date=date(2026, 8 + vn - 5, 1),
                location="X", is_championship=False,
                status=RaceEventStatus.COMPLETED, created_by_user_id=1,
            )
            _seed_result(
                store, event_id=eid, category_id=inf_a.id, competitor_id=tyr.id,
                athlete_id=42, position=1, race_time_ms=1_580_000, points=40,
            )

        # V-7 = target
        v7_id = store.next_id("events")
        store.events[v7_id] = RaceEvent(
            id=v7_id, series_id=1, sequence_number=7,
            name="V-7", event_date=date(2026, 10, 1),
            location="X", is_championship=False,
            status=RaceEventStatus.COMPLETED, created_by_user_id=1,
        )
        out = await projection(analytics_session, competitor_id=tyr.id, next_event_id=v7_id)
        assert out["n_samples"] == 6
        assert out["confidence"] == "medium"

    @pytest.mark.asyncio
    async def test_projection_with_n10_marks_confidence_high(
        self, fake_session: FakeAsyncSession
    ):
        """Construimos un dataset desde cero con 10 results FINISHED para 1 competidor."""
        store = fake_session.store
        _seed_series(store)
        inf_a = _get_cat(store, _INF_A_CODE)
        tyr = _seed_competitor(store, "Atleta Largo", athlete_id=1)
        for vn in range(1, 11):
            eid = store.next_id("events")
            store.events[eid] = RaceEvent(
                id=eid, series_id=1, sequence_number=vn,
                name=f"V-{vn}", event_date=date(2026, 1, 1).replace(
                    month=min(vn, 12)
                ),
                location="X", is_championship=False,
                status=RaceEventStatus.COMPLETED, created_by_user_id=1,
            )
            _seed_result(
                store, event_id=eid, category_id=inf_a.id,
                competitor_id=tyr.id, athlete_id=1,
                position=5, race_time_ms=1_700_000, points=20,
            )
        # Target: V-11.
        target_id = store.next_id("events")
        store.events[target_id] = RaceEvent(
            id=target_id, series_id=1, sequence_number=11,
            name="V-11", event_date=date(2026, 12, 15),
            location="X", is_championship=False,
            status=RaceEventStatus.COMPLETED, created_by_user_id=1,
        )
        out = await projection(fake_session, competitor_id=tyr.id, next_event_id=target_id)
        assert out["n_samples"] == 10
        assert out["confidence"] == "high"

    @pytest.mark.asyncio
    async def test_projection_returns_none_fields_if_no_results(
        self, fake_session: FakeAsyncSession
    ):
        """Competidor sin results → todos los campos derivados son None,
        n_samples=0, confidence='low'."""
        store = fake_session.store
        _seed_series(store)
        events = _seed_events(store, series_id=1, count=1)
        out = await projection(
            fake_session, competitor_id=99999, next_event_id=events[0].id
        )
        assert out["n_samples"] == 0
        assert out["confidence"] == "low"
        assert out["expected_position"] is None
        assert out["expected_position_range"] is None
        assert out["expected_race_time_ms"] is None

    @pytest.mark.asyncio
    async def test_projection_with_n1_edge_case(
        self, fake_session: FakeAsyncSession
    ):
        """n=1 → confidence low, expected_position igual al único punto."""
        store = fake_session.store
        _seed_series(store)
        events = _seed_events(store, series_id=1, count=2)
        inf_a = _get_cat(store, _INF_A_CODE)
        c = _seed_competitor(store, "Único", athlete_id=10)
        _seed_result(
            store, event_id=events[0].id, category_id=inf_a.id,
            competitor_id=c.id, athlete_id=10, position=4,
            race_time_ms=1_700_000, points=24,
        )
        out = await projection(fake_session, competitor_id=c.id, next_event_id=events[1].id)
        assert out["n_samples"] == 1
        assert out["confidence"] == "low"
        # Con un solo punto y std=0, expected_position = 4 (no negativo, no clipped).
        assert out["expected_position"] == 4.0
        assert out["expected_position_range"] == [4.0, 4.0]


# ===========================================================================
# 5. JSON-serializability
# ===========================================================================


class TestSerialization:
    @pytest.mark.asyncio
    async def test_dataframes_are_json_serializable(
        self, analytics_session: FakeAsyncSession
    ):
        """Todos los DataFrames + dicts deben ser JSON-serializables vía
        ``.to_dict('records')`` (criterio workflow §5 checklist)."""
        tyr = next(
            c for c in analytics_session.store.competitors.values()
            if c.display_name == "Thiago Duque"
        )
        inf_a = _get_cat(analytics_session.store, _INF_A_CODE)

        df_prog = await athlete_progression(analytics_session, competitor_id=tyr.id)
        df_gap = await podium_gap(
            analytics_session, category_id=inf_a.id, season=_SEASON
        )
        ranking = await club_ranking(analytics_session, season=_SEASON)
        # Para projection necesitamos target; reusamos V-1 (no importa por el
        # propósito de este test de serialización).
        any_event = next(iter(analytics_session.store.events.values()))
        proj = await projection(
            analytics_session, competitor_id=tyr.id, next_event_id=any_event.id
        )

        # Convertir y serializar. Int64 nullable y NaN deben mapearse OK
        # vía orient='records'. Pandas ≥2 emite None para NA, json.dumps lo acepta.
        records_prog = _records(df_prog)
        records_gap = _records(df_gap)
        json.dumps(records_prog)
        json.dumps(records_gap)
        json.dumps(ranking)
        json.dumps(proj)


# Necesitamos pandas para el isna() del test 2.2; importamos aquí para no
# poluir el módulo top-level.
import pandas as pd  # noqa: E402


def _records(df):
    """Convierte DataFrame a list[dict] reemplazando pd.NA → None.

    Pandas 2+ a veces emite ``<NA>`` en ``to_dict('records')`` para columnas
    Int64; ``json.dumps`` falla con TypeError. Esta función las convierte
    explícitamente a ``None``.
    """
    out = []
    for rec in df.to_dict(orient="records"):
        clean = {}
        for k, v in rec.items():
            if v is pd.NA or (isinstance(v, float) and pd.isna(v)):
                clean[k] = None
            elif hasattr(v, "item"):  # numpy scalars
                clean[k] = v.item()
            else:
                clean[k] = v
        out.append(clean)
    return out
