"""Tests para cerrar gaps de cobertura misceláneos (Paso 7).

Cubre:
- ``normalizer._strip_diacritics_lower`` con input vacío (L112).
- ``matcher._calc_age_decimal`` con birth_date futuro (L89).
- ``matcher._full_name_of`` con athlete sin first_name ni last_name (L182-186 zona).
- ``analytics._load_competitors`` (función no usada en producción aún — L83-84).
- ``analytics.athlete_progression`` cuando no hay results en absoluto (L193).
- ``analytics.athlete_progression`` cuando no hay finished (L209 winners empty).
- ``analytics.podium_gap`` con events_in_season vacío (L310).
- ``analytics.podium_gap`` con df_cat vacío (L321).
- ``analytics.podium_gap`` pivot table sin P1 o sin P3 (L347-348/349-350).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import pytest

from app.models.race_category import CategoryGender, CategoryTier, RaceCategory
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.services.race.analytics import (
    _load_competitors,
    athlete_progression,
    podium_gap,
)
from app.services.race.matcher import (
    _calc_age_decimal,
    _full_name_of,
    match_athletes,
)
from app.services.race.normalizer import _strip_diacritics_lower


# ===========================================================================
# normalizer._strip_diacritics_lower
# ===========================================================================


class TestStripDiacriticsLower:
    def test_empty_input(self):
        assert _strip_diacritics_lower("") == ""

    def test_none_input(self):
        assert _strip_diacritics_lower(None) == ""  # type: ignore[arg-type]

    def test_unicode_lowered(self):
        assert _strip_diacritics_lower("MATÍAS  GARCÍA") == "matias garcia"


# ===========================================================================
# matcher._calc_age_decimal
# ===========================================================================


class TestCalcAgeDecimal:
    def test_none_birth_date_returns_none(self):
        assert _calc_age_decimal(None, date(2026, 5, 17)) is None

    def test_future_birth_date_returns_none(self):
        """Atleta con birth_date posterior a la referencia → None (no edad negativa)."""
        assert _calc_age_decimal(date(2027, 1, 1), date(2026, 5, 17)) is None

    def test_normal_age_computed(self):
        age = _calc_age_decimal(date(2016, 5, 17), date(2026, 5, 17))
        assert age == 10.0


# ===========================================================================
# matcher._full_name_of con athlete degenerado
# ===========================================================================


@dataclass
class _BareAthlete:
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    birth_date: Optional[date] = None


class TestFullNameOf:
    def test_only_first_name(self):
        a = _BareAthlete(id=1, first_name="Sofia")
        assert _full_name_of(a) == "Sofia"

    def test_only_last_name(self):
        a = _BareAthlete(id=1, last_name="Duque")
        assert _full_name_of(a) == "Duque"

    def test_both_empty_returns_empty(self):
        a = _BareAthlete(id=1)
        assert _full_name_of(a) == ""


class TestMatcherWithDegenerateAthletes:
    def test_athlete_without_names_skipped(self):
        """Atleta con first_name/last_name vacíos no entra al ranking."""
        result = match_athletes(
            competitor_name="Thiago Duque",
            competitor_club="Club Trocha y Ruta",
            athletes=[_BareAthlete(id=1)],  # sin nombres
        )
        assert result == []


# ===========================================================================
# analytics._load_competitors (función huérfana, se cubre por completitud)
# ===========================================================================


class TestLoadCompetitors:
    @pytest.mark.asyncio
    async def test_load_empty(self, fake_session):
        out = await _load_competitors(fake_session)
        assert out == []


# ===========================================================================
# analytics.athlete_progression — branches no cubiertas
# ===========================================================================


class TestAthleteProgressionBranches:
    @pytest.mark.asyncio
    async def test_returns_empty_df_when_no_results_at_all(self, fake_session):
        """Sin race_results en absoluto → DataFrame vacío con columnas."""
        df = await athlete_progression(fake_session, competitor_id=1)
        assert df.empty
        assert "valida_num" in df.columns

    @pytest.mark.asyncio
    async def test_with_results_but_no_finished_returns_empty_winners(self, fake_session):
        """Si hay results pero ninguno FINISHED → winners DataFrame vacío,
        gap queda NaN, el competitor aún tiene su fila pero con NaN."""
        from tests.services.race.test_analytics import (
            _get_cat,
            _seed_competitor,
            _seed_events,
            _seed_result,
            _seed_series,
        )
        store = fake_session.store
        _seed_series(store)
        events = _seed_events(store, series_id=1, count=2)
        inf_a = _get_cat(store, "INF_A")
        c = _seed_competitor(store, "Sólo DNF", athlete_id=10)
        _seed_result(
            store, event_id=events[0].id, category_id=inf_a.id,
            competitor_id=c.id, athlete_id=10, position=None,
            race_time_ms=None, points=1, status=ResultStatus.DNF,
        )
        _seed_result(
            store, event_id=events[1].id, category_id=inf_a.id,
            competitor_id=c.id, athlete_id=10, position=None,
            race_time_ms=None, points=1, status=ResultStatus.DSQ,
        )
        df = await athlete_progression(fake_session, competitor_id=c.id)
        assert len(df) == 2
        # gap_to_winner_ms es <NA> (Int64 nullable) por race_time_ms None
        # y winners vacíos
        assert df["gap_to_winner_ms"].isna().all()


# ===========================================================================
# analytics.podium_gap — branches no cubiertas
# ===========================================================================


class TestPodiumGapBranches:
    @pytest.mark.asyncio
    async def test_no_events_in_season_returns_empty_df(self, fake_session):
        """``RaceSeries.season_year`` no coincide → DataFrame vacío."""
        from tests.services.race.test_analytics import (
            _get_cat,
            _seed_events,
            _seed_series,
        )
        store = fake_session.store
        _seed_series(store, season=2025)  # serie de 2025
        _seed_events(store, series_id=1, count=2)  # eventos en 2025
        inf_a = _get_cat(store, "INF_A")
        # Pedimos season=2099 (no existe serie)
        df = await podium_gap(fake_session, category_id=inf_a.id, season=2099)
        assert df.empty

    @pytest.mark.asyncio
    async def test_no_results_in_category_returns_empty(self, fake_session):
        """Serie + eventos OK pero ninguna fila en la categoría pedida → vacío."""
        from tests.services.race.test_analytics import (
            _get_cat,
            _seed_events,
            _seed_series,
        )
        store = fake_session.store
        _seed_series(store)
        _seed_events(store, series_id=1, count=2)
        inf_a_f = _get_cat(store, "INF_A_F")
        df = await podium_gap(fake_session, category_id=inf_a_f.id, season=2026)
        assert df.empty

    @pytest.mark.asyncio
    async def test_pivot_handles_missing_p3(self, fake_session):
        """Una válida donde sólo hay P1 (sin P3) — el pivot agrega P3=NaN."""
        from tests.services.race.test_analytics import (
            _get_cat,
            _seed_competitor,
            _seed_events,
            _seed_result,
            _seed_series,
        )
        store = fake_session.store
        _seed_series(store)
        events = _seed_events(store, series_id=1, count=1)
        inf_a = _get_cat(store, "INF_A")
        # Sólo 1 corredor TyR que es P1; sin P3 en la categoría
        tyr = _seed_competitor(store, "Único TyR", athlete_id=42)
        _seed_result(
            store, event_id=events[0].id, category_id=inf_a.id,
            competitor_id=tyr.id, athlete_id=42, position=1,
            race_time_ms=1_500_000, points=40,
        )
        df = await podium_gap(fake_session, category_id=inf_a.id, season=2026)
        assert len(df) == 1
        # P3 ausente → gap_to_p3_ms es NaN (<NA>)
        assert df["gap_to_p3_ms"].iloc[0] is None or df["gap_to_p3_ms"].isna().iloc[0]

    @pytest.mark.asyncio
    async def test_pivot_handles_missing_p1(self, fake_session):
        """Caso límite raro: nadie quedó P1 (todos DNF salvo P3).

        Esto puede ocurrir cuando un evento tuvo problemas masivos. El pivot
        retorna columna `1` ausente → se agrega como NaN.
        """
        from tests.services.race.test_analytics import (
            _get_cat,
            _seed_competitor,
            _seed_events,
            _seed_result,
            _seed_series,
        )
        store = fake_session.store
        _seed_series(store)
        events = _seed_events(store, series_id=1, count=1)
        inf_a = _get_cat(store, "INF_A")
        tyr = _seed_competitor(store, "TyR P3", athlete_id=42)
        # Solo un P3 — sin P1 ni P2
        _seed_result(
            store, event_id=events[0].id, category_id=inf_a.id,
            competitor_id=tyr.id, athlete_id=42, position=3,
            race_time_ms=1_700_000, points=30,
        )
        df = await podium_gap(fake_session, category_id=inf_a.id, season=2026)
        assert len(df) == 1
        # gap_to_p1_ms NaN porque no hay P1
        assert df["gap_to_p1_ms"].isna().iloc[0]
        # gap_to_p3_ms = 0 (él mismo es P3)
        assert df["gap_to_p3_ms"].iloc[0] == 0
