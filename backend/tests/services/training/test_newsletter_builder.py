"""Tests para newsletter_builder.py.

Cubre:
- build_newsletter_metrics retorna email_blocks y pdf_only_blocks separados
- Antropometría solo en pdf_only_blocks, NUNCA en email_blocks
- email_blocks contiene las claves esperadas
- pdf_only_blocks contiene anthropometry
- Bloques de asistencia con sesiones vacías
- _build_charts_context con datos y sin datos
- _get_upcoming_copa_valle_races filtra correctamente
- _build_support_block nunca menciona calorías ni suplementos explícitos
- (039) _build_race_block separa cups[]/championships[] por grupo de
  comparación (contracts/newsletter-context.md); dedupe por event_id.
- (039) _build_charts_context agrupa por copa en cups[]; el total
  acumulado de una copa coincide con services/race/standings.py.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from app.services.training.newsletter_builder import (
    _build_charts_context,
    _race_readable_label,
    _race_short_label,
    _build_support_block,
    _get_upcoming_copa_valle_races,
    build_newsletter_metrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_session() -> Any:
    """Fake DB session."""
    sess = MagicMock()
    sess.execute = AsyncMock()
    sess.flush = AsyncMock()
    sess.add = MagicMock()
    return sess


def make_scalars_result(items: list) -> Any:
    result = MagicMock()
    result.scalars.return_value = result
    result.all.return_value = items
    result.scalar_one_or_none.return_value = items[0] if items else None
    return result


def make_athlete(id_: int = 1, club_id: int = 10) -> Any:
    from datetime import date
    return SimpleNamespace(
        id=id_,
        club_id=club_id,
        first_name="Atleta",
        last_name="Test",
        birth_date=date(2012, 3, 15),
        height_cm=152.0,
    )


def make_session_obj(id_: int, date_: date | None = None, club_id: int = 10) -> Any:
    from app.models.training_session import SessionStatus
    return SimpleNamespace(
        id=id_,
        club_id=club_id,
        scheduled_date=date_ or date(2026, 4, 10 + id_),
        status=SessionStatus.EXECUTED,
        duration_min=90,
        technical_focus="Frenado progresivo",
        location="Reserva Natural El Cairo",
    )


def make_attendance(session_id: int, status_) -> Any:
    return SimpleNamespace(
        session_id=session_id,
        athlete_id=1,
        status=status_,
        rpe_omni=6,
        rubric_effort=4,
        rubric_attitude=4,
        rubric_technique=3,
    )


def is_delete_stmt(stmt: Any) -> bool:
    """Detecta DELETE inicial del re-evaluador de badges (clean slate del periodo)."""
    from sqlalchemy.sql.dml import Delete

    return isinstance(stmt, Delete)


# ---------------------------------------------------------------------------
# build_newsletter_metrics — separación email_blocks / pdf_only_blocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_newsletter_metrics_has_both_blocks():
    """build_newsletter_metrics retorna email_blocks y pdf_only_blocks."""
    from app.models.training_session import AttendanceStatus

    db = make_session()
    athlete = make_athlete()
    sessions = [make_session_obj(i) for i in range(1, 4)]
    attendances = [make_attendance(s.id, AttendanceStatus.PRESENTE) for s in sessions]

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        if is_delete_stmt(stmt):
            return MagicMock()
        call_count += 1
        if call_count == 1:
            # Athlete query
            return make_scalars_result([athlete])
        elif call_count == 2:
            # Sessions del mes (asistencia block)
            return make_scalars_result(sessions)
        elif call_count == 3:
            # SessionAttendance (asistencia block)
            return make_scalars_result(attendances)
        elif call_count == 4:
            # Sessions mes anterior (prev_month_attendance)
            return make_scalars_result([])
        elif call_count == 5:
            # Sessions (technical block)
            return make_scalars_result(sessions)
        elif call_count == 6:
            # SessionAttendance (technical block)
            return make_scalars_result(attendances)
        elif call_count == 7:
            # RaceCompetitor (race block)
            return make_scalars_result([])
        elif call_count == 8:
            # Next training sessions (calendar block)
            return make_scalars_result([])
        elif call_count == 9:
            # Sessions (photos block)
            return make_scalars_result([])
        elif call_count == 10:
            # Athlete (badge evaluator)
            return make_scalars_result([athlete])
        elif call_count == 11:
            # TrainingSession (badge evaluator attendance)
            return make_scalars_result(sessions)
        elif call_count == 12:
            # SessionAttendance (badge evaluator)
            return make_scalars_result(attendances)
        elif call_count == 13:
            # _upsert_badge check (attendance_100)
            return make_scalars_result([])  # no existe aún
        elif call_count == 14:
            # RaceCompetitor (badge evaluator race)
            return make_scalars_result([])
        elif call_count == 15:
            # get_badges_for_period
            return make_scalars_result([])
        elif call_count == 16:
            # AnthropometricRecord (anthropometry block)
            return make_scalars_result([])
        else:
            return make_scalars_result([])

    db.execute = mock_execute
    db.flush = AsyncMock()

    snapshot = await build_newsletter_metrics(db, athlete.id, 2026, 4)

    assert "email_blocks" in snapshot
    assert "pdf_only_blocks" in snapshot


@pytest.mark.asyncio
async def test_anthropometry_only_in_pdf_blocks():
    """Antropometría NUNCA aparece en email_blocks."""

    db = make_session()
    athlete = make_athlete()

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        if is_delete_stmt(stmt):
            return MagicMock()
        call_count += 1
        if call_count == 1:
            return make_scalars_result([athlete])
        else:
            return make_scalars_result([])

    db.execute = mock_execute
    db.flush = AsyncMock()

    snapshot = await build_newsletter_metrics(db, athlete.id, 2026, 4)

    email_blocks = snapshot["email_blocks"]
    pdf_only_blocks = snapshot["pdf_only_blocks"]

    # Antropometría NUNCA en email_blocks
    assert "anthropometry" not in email_blocks

    # Antropometría SÍ en pdf_only_blocks
    assert "anthropometry" in pdf_only_blocks


@pytest.mark.asyncio
async def test_email_blocks_required_keys():
    """email_blocks debe tener todas las claves requeridas."""
    db = make_session()
    athlete = make_athlete()

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        if is_delete_stmt(stmt):
            return MagicMock()
        call_count += 1
        if call_count == 1:
            return make_scalars_result([athlete])
        return make_scalars_result([])

    db.execute = mock_execute
    db.flush = AsyncMock()

    snapshot = await build_newsletter_metrics(db, athlete.id, 2026, 4)

    email_blocks = snapshot["email_blocks"]
    required_keys = [
        "period", "attendance", "technical", "race_results",
        "calendar", "photos", "badges", "support_at_home",
    ]
    for key in required_keys:
        assert key in email_blocks, f"Clave requerida '{key}' ausente en email_blocks"


@pytest.mark.asyncio
async def test_athlete_not_found_raises():
    """Si el atleta no existe, se lanza ValueError."""
    db = make_session()

    async def mock_execute(stmt):
        return make_scalars_result([])

    db.execute = mock_execute

    with pytest.raises(ValueError, match="no encontrado"):
        await build_newsletter_metrics(db, 999, 2026, 4)


# ---------------------------------------------------------------------------
# _get_upcoming_copa_valle_races
# ---------------------------------------------------------------------------


class TestGetUpcomingCopaValleRaces:
    def test_returns_max_3_races(self):
        # Fecha antes de la primera válida de 2026
        races = _get_upcoming_copa_valle_races(date(2026, 1, 1))
        assert len(races) <= 3

    def test_filters_past_dates(self):
        # Fecha después de la Copa Valle 2026 completa
        races = _get_upcoming_copa_valle_races(date(2027, 1, 1))
        assert races == []

    def test_filters_correctly_mid_year(self):
        # Después de la Válida IV (mayo 2026), quedan CD/V/VI/VII
        # pero el límite es 3
        races = _get_upcoming_copa_valle_races(date(2026, 5, 17))
        assert len(races) <= 3
        # La primera debe ser posterior al 17 de mayo
        for r in races:
            event_date = date.fromisoformat(r["date"])
            assert event_date > date(2026, 5, 17)

    def test_race_has_required_fields(self):
        races = _get_upcoming_copa_valle_races(date(2026, 1, 1))
        for r in races:
            assert "valida" in r
            assert "date" in r
            assert "location" in r
            assert "priority" in r

    def test_returns_list(self):
        races = _get_upcoming_copa_valle_races(date(2026, 6, 1))
        assert isinstance(races, list)


# ---------------------------------------------------------------------------
# _build_support_block
# ---------------------------------------------------------------------------


class TestBuildSupportBlock:
    def test_returns_tips_list(self):
        block = _build_support_block(13.5, 6, "su hijo/a")
        assert "tips" in block
        assert isinstance(block["tips"], list)
        assert len(block["tips"]) > 0

    def test_tips_have_required_fields(self):
        block = _build_support_block(13.5, 6, "su hijo/a")
        for tip in block["tips"]:
            assert "category" in tip
            assert "title" in tip
            assert "text" in tip

    def test_no_calorie_counting_language(self):
        """El bloque de apoyo no debe incluir conteo calórico."""
        block = _build_support_block(13.5, 6, "su hijo/a")
        combined = " ".join(t["text"] for t in block["tips"]).lower()
        # No debe mencionar contar calorías como instrucción
        assert "contar calorías" not in combined
        assert "cuenta las calorías" not in combined

    def test_no_supplements_recommendation(self):
        """El bloque no debe recomendar suplementos."""
        block = _build_support_block(13.5, 6, "su hijo/a")
        combined = " ".join(t["text"] for t in block["tips"]).lower()
        # No debe recomendar suplementos
        assert "tomar suplemento" not in combined
        assert "proteína en polvo" not in combined
        assert "creatina" not in combined

    def test_hydration_tip_present(self):
        block = _build_support_block(13.5, 6, "su hijo/a")
        categories = {t["category"] for t in block["tips"]}
        assert "hidratacion" in categories

    def test_sleep_tip_present(self):
        block = _build_support_block(13.5, 6, "su hijo/a")
        categories = {t["category"] for t in block["tips"]}
        assert "sueno" in categories


# ---------------------------------------------------------------------------
# _build_charts_context
# ---------------------------------------------------------------------------


class TestBuildChartsContext:
    def test_empty_race_block_returns_no_data(self):
        ctx = _build_charts_context({"has_races": False, "results": []})
        assert ctx["has_data"] is False
        assert ctx["positions"] == []

    def test_with_progression_history(self):
        race_block = {
            "has_races": True,
            "progression_history": [
                {"valida_num": 1, "position": 5, "gap_to_winner_pct": 4.2, "points_awarded": 10},
                {"valida_num": 2, "position": 3, "gap_to_winner_pct": 2.1, "points_awarded": 15},
                {"valida_num": 3, "position": 7, "gap_to_winner_pct": 6.0, "points_awarded": 8},
            ],
        }
        ctx = _build_charts_context(race_block)
        assert ctx["has_data"] is True
        assert len(ctx["positions"]) == 3
        assert len(ctx["gap_pcts"]) == 3
        assert len(ctx["points_accumulated"]) == 3

    def test_points_accumulated_is_cumulative(self):
        race_block = {
            "has_races": True,
            "progression_history": [
                {"valida_num": 1, "position": 5, "gap_to_winner_pct": 4.0, "points_awarded": 10},
                {"valida_num": 2, "position": 3, "gap_to_winner_pct": 2.0, "points_awarded": 15},
            ],
        }
        ctx = _build_charts_context(race_block)
        acc_values = [p["y"] for p in ctx["points_accumulated"]]
        assert acc_values[0] == 10
        assert acc_values[1] == 25  # 10 + 15

    def test_low_confidence_if_few_samples(self):
        race_block = {
            "has_races": True,
            "progression_history": [
                {"valida_num": 1, "position": 5, "gap_to_winner_pct": 4.0, "points_awarded": 10},
                {"valida_num": 2, "position": None, "gap_to_winner_pct": None, "points_awarded": 0},
            ],
        }
        ctx = _build_charts_context(race_block)
        # n_samples es el conteo de posiciones no nulas
        assert ctx["n_samples"] < 5
        assert ctx["low_confidence"] is True

    def test_high_confidence_if_many_samples(self):
        race_block = {
            "has_races": True,
            "progression_history": [
                {"valida_num": i, "position": i + 1, "gap_to_winner_pct": float(i), "points_awarded": 10}
                for i in range(1, 7)
            ],
        }
        ctx = _build_charts_context(race_block)
        assert ctx["n_samples"] >= 5
        assert ctx["low_confidence"] is False


# ---------------------------------------------------------------------------
# Fix boletín: campeonato (departamental/nacional) fuera de la secuencia de
# válidas. sequence_number=1 (spec 014) NO debe colisionar con la Válida I ni
# desordenar el eje X del gráfico. El eje usa índice ordinal cronológico y la
# etiqueta viene de series_kind/level.
# ---------------------------------------------------------------------------


class TestChampionshipChartLabels:
    def test_championship_no_colisiona_con_valida_1(self):
        """CD (sequence_number=1) intercalado entre válidas se dibuja en su
        posición cronológica (x ordinal), no en x=1 sobre la Válida I."""
        race_block = {
            "has_races": True,
            "progression_history": [
                {"valida_num": 3, "position": 5, "gap_to_winner_pct": 4.0,
                 "points_awarded": 10, "series_kind": "cup",
                 "series_level": "departmental", "label": "V3"},
                {"valida_num": 4, "position": 4, "gap_to_winner_pct": 3.0,
                 "points_awarded": 12, "series_kind": "cup",
                 "series_level": "departmental", "label": "V4"},
                # Campeonato departamental: sequence_number=1 pero va DESPUÉS.
                {"valida_num": 1, "position": 3, "gap_to_winner_pct": 2.0,
                 "points_awarded": 0, "series_kind": "championship",
                 "series_level": "departmental", "label": "CD"},
            ],
        }
        ctx = _build_charts_context(race_block)
        xs = [p["x"] for p in ctx["positions"]]
        labels = [p["label"] for p in ctx["positions"]]
        # X ordinal estrictamente creciente y único (sin colisión en x=1).
        assert xs == [1, 2, 3]
        assert labels == ["V3", "V4", "CD"]

    def test_campeonato_nacional_label_cn(self):
        race_block = {
            "has_races": True,
            "progression_history": [
                {"valida_num": 1, "position": 2, "gap_to_winner_pct": 1.0,
                 "points_awarded": 0, "series_kind": "championship",
                 "series_level": "national"},
            ],
        }
        ctx = _build_charts_context(race_block)
        # Sin 'label' precomputado, se deriva de series_kind/level → "CN".
        assert ctx["positions"][0]["label"] == "CN"

    def test_short_labels(self):
        assert _race_short_label("championship", "departmental", 1) == "CD"
        assert _race_short_label("championship", "national", 1) == "CN"
        assert _race_short_label("cup", "departmental", 5) == "V5"

    def test_readable_labels(self):
        assert _race_readable_label("championship", "departmental", 1) == "Campeonato Departamental"
        assert _race_readable_label("championship", "national", 1) == "Campeonato Nacional"
        assert _race_readable_label("cup", "departmental", 5) == "Válida 5"


# ---------------------------------------------------------------------------
# Feature 039 (T008/T009) — grupos de comparación: _build_race_block emite
# cups[] / championships[] separados en vez de un único histórico mezclado
# (contracts/newsletter-context.md); _build_charts_context agrupa las tres
# curvas SVG por copa.
#
# Estas fixtures/tests corren contra una sesión aiosqlite real (mismo
# harness que tests/fixtures/race_groups.py, registrado como plugin en
# tests/conftest.py) porque necesitan series `championship` reales además de
# la copa — algo que el FakeAsyncSession de este archivo (make_session) no
# modela. Las dos fixtures locales de abajo cubren las combinaciones que las
# fixtures compartidas (race_groups_base_season/_two_cups/_dnf_championship)
# no ofrecen: solo copa (sin campeonato) y solo campeonatos (sin copa).
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def race_groups_cup_only(race_groups_session_factory):
    """Variante local (039): solo la copa de 5 válidas, sin ningún campeonato."""
    from tests.fixtures.race_groups import (
        ATHLETE_COMPETITOR_ID,
        ATHLETE_ID,
        CATEGORY_ID,
        CUP_LOCATION,
        CUP_SERIES_ID,
        CUP_SERIES_NAME,
        SEASON,
        _seed_actors,
        _seed_cup_series,
    )

    async with race_groups_session_factory() as session:
        await _seed_actors(session)
        cup_event_ids = await _seed_cup_series(
            session,
            series_id=CUP_SERIES_ID,
            name=CUP_SERIES_NAME,
            num_rounds=5,
            round_dates=[date(SEASON, m, 15) for m in range(1, 6)],
            location=CUP_LOCATION,
        )
        await session.commit()
        yield SimpleNamespace(
            session=session,
            athlete_id=ATHLETE_ID,
            competitor_id=ATHLETE_COMPETITOR_ID,
            category_id=CATEGORY_ID,
            season=SEASON,
            cup_series_id=CUP_SERIES_ID,
            cup_event_ids=cup_event_ids,
        )


@pytest_asyncio.fixture
async def race_groups_championship_only(race_groups_session_factory):
    """Variante local (039): Cto. Departamental + Cto. Nacional, sin copa."""
    from app.models.race_series import RaceSeriesLevel
    from tests.fixtures.race_groups import (
        ATHLETE_COMPETITOR_ID,
        ATHLETE_ID,
        CATEGORY_ID,
        DEPARTMENTAL_LOCATION,
        DEPARTMENTAL_SERIES_ID,
        DEPARTMENTAL_SERIES_NAME,
        NATIONAL_LOCATION,
        NATIONAL_SERIES_ID,
        NATIONAL_SERIES_NAME,
        SEASON,
        _seed_actors,
        _seed_championship_series,
    )

    async with race_groups_session_factory() as session:
        await _seed_actors(session)
        departmental_event_id = await _seed_championship_series(
            session,
            series_id=DEPARTMENTAL_SERIES_ID,
            name=DEPARTMENTAL_SERIES_NAME,
            level=RaceSeriesLevel.departmental,
            event_date=date(SEASON, 6, 20),
            location=DEPARTMENTAL_LOCATION,
        )
        national_event_id = await _seed_championship_series(
            session,
            series_id=NATIONAL_SERIES_ID,
            name=NATIONAL_SERIES_NAME,
            level=RaceSeriesLevel.national,
            event_date=date(SEASON, 8, 22),
            location=NATIONAL_LOCATION,
        )
        await session.commit()
        yield SimpleNamespace(
            session=session,
            athlete_id=ATHLETE_ID,
            competitor_id=ATHLETE_COMPETITOR_ID,
            category_id=CATEGORY_ID,
            season=SEASON,
            departmental_event_id=departmental_event_id,
            national_event_id=national_event_id,
        )


class TestBuildRaceBlockComparisonGroups:
    """T008 (039): ``_build_race_block`` separa ``cups[]``/``championships[]``.

    Contrato: ``specs/039-season-comparison-groups/contracts/newsletter-context.md``.
    """

    @pytest.mark.asyncio
    async def test_cups_and_championships_shape(self, race_groups_base_season):
        from tests.fixtures.race_groups import CATEGORY_LABEL, DEPARTMENTAL_LOCATION, NATIONAL_LOCATION
        from app.services.training.newsletter_builder import _build_race_block

        scenario = race_groups_base_season
        block = await _build_race_block(scenario.session, scenario.athlete_id, scenario.season, 8)

        # progression_history (plano) se conserva un release por compatibilidad.
        assert "progression_history" in block
        assert len(block["progression_history"]) == 7  # 5 válidas + CD + CN

        cups = block["cups"]
        assert len(cups) == 1
        cup = cups[0]
        assert cup["series_id"] == scenario.cup_series_id
        assert cup["label"] == f"{scenario.cup_series_name} {scenario.season}"
        assert [row["event_id"] for row in cup["history"]] == scenario.cup_event_ids

        championships = block["championships"]
        assert len(championships) == 2
        by_event = {c["event_id"]: c for c in championships}

        cd = by_event[scenario.departmental_event_id]
        assert cd["level"] == "departmental"
        assert cd["label"] == "Campeonato Departamental"
        assert cd["short_label"] == f"Cto. Dep. — {DEPARTMENTAL_LOCATION}"
        assert cd["category_label"] == CATEGORY_LABEL
        assert cd["finished"] is True
        assert cd["position"] is not None
        assert cd["gap_pct"] is not None
        assert cd["percentile"] is not None

        cn = by_event[scenario.national_event_id]
        assert cn["level"] == "national"
        assert cn["label"] == "Campeonato Nacional"
        assert cn["short_label"] == f"Cto. Nal. — {NATIONAL_LOCATION}"
        assert cn["finished"] is True
        assert cn["position"] is not None

    @pytest.mark.asyncio
    async def test_dnf_championship_finished_false_and_nulls(self, race_groups_dnf_championship):
        from app.services.training.newsletter_builder import _build_race_block

        scenario = race_groups_dnf_championship
        block = await _build_race_block(scenario.session, scenario.athlete_id, scenario.season, 8)

        national = next(c for c in block["championships"] if c["event_id"] == scenario.national_event_id)
        assert national["finished"] is False
        assert national["position"] is None
        assert national["gap_pct"] is None
        assert national["percentile"] is None

        # El departamental de esta variante no es DNF — sigue completo.
        departmental = next(
            c for c in block["championships"] if c["event_id"] == scenario.departmental_event_id
        )
        assert departmental["finished"] is True
        assert departmental["position"] is not None

    @pytest.mark.asyncio
    async def test_no_championship_yields_empty_championships_list(self, race_groups_cup_only):
        from app.services.training.newsletter_builder import _build_race_block

        scenario = race_groups_cup_only
        block = await _build_race_block(scenario.session, scenario.athlete_id, scenario.season, 1)

        assert block["championships"] == []
        assert len(block["cups"]) == 1
        assert block["cups"][0]["series_id"] == scenario.cup_series_id
        assert "progression_history" in block

    @pytest.mark.asyncio
    async def test_only_championships_yields_empty_cups_list(self, race_groups_championship_only):
        from app.services.training.newsletter_builder import _build_race_block

        scenario = race_groups_championship_only
        block = await _build_race_block(scenario.session, scenario.athlete_id, scenario.season, 8)

        assert block["cups"] == []
        assert len(block["championships"]) == 2
        assert "progression_history" in block

    @pytest.mark.asyncio
    async def test_dedupe_by_event_id_across_linked_competitors(self, race_groups_base_season):
        """Dos ``RaceCompetitor`` distintos vinculados al mismo atleta que
        corrieron el MISMO evento (dos matches de identidad del mismo
        corredor) no deben duplicar esa fila del campeonato — dedupe por
        ``event_id`` (D8), no por ``event_date`` como antes de esta feature."""
        from app.models.race_competitor import RaceCompetitor
        from app.models.race_result import RaceResult, ResultStatus
        from app.services.training.newsletter_builder import _build_race_block

        scenario = race_groups_base_season
        session = scenario.session

        duplicate_competitor = RaceCompetitor(
            id=9999,
            normalized_name="camila ficticia salazar duplicado",
            display_name="Camila Ficticia Salazar",
            athlete_id=scenario.athlete_id,
        )
        session.add(duplicate_competitor)
        await session.flush()
        session.add(
            RaceResult(
                event_id=scenario.national_event_id,
                category_id=scenario.category_id,
                competitor_id=duplicate_competitor.id,
                athlete_id=scenario.athlete_id,
                position=4,
                status=ResultStatus.FINISHED,
                race_time_ms=1_980_000,
                bib_number=77,
                points_awarded=0,
                created_by_user_id=910,
            )
        )
        await session.commit()

        block = await _build_race_block(session, scenario.athlete_id, scenario.season, 8)

        national_rows = [c for c in block["championships"] if c["event_id"] == scenario.national_event_id]
        assert len(national_rows) == 1


class TestBuildChartsContextComparisonGroups:
    """T009 (039): ``_build_charts_context`` agrupa las tres curvas por copa
    en ``cups[]``; ``has_data`` solo es ``True`` cuando alguna copa tiene
    filas. Contrato: ``contracts/newsletter-context.md``."""

    @pytest.mark.asyncio
    async def test_cups_shape_and_ordinal_x(self, race_groups_base_season):
        from app.services.training.newsletter_builder import _build_charts_context, _build_race_block

        scenario = race_groups_base_season
        race_block = await _build_race_block(scenario.session, scenario.athlete_id, scenario.season, 8)
        ctx = _build_charts_context(race_block)

        assert ctx["has_data"] is True
        assert ctx["has_championship"] is True
        assert len(ctx["cups"]) == 1

        cup_ctx = ctx["cups"][0]
        assert cup_ctx["series_id"] == scenario.cup_series_id
        assert cup_ctx["n_samples"] == 5
        assert cup_ctx["low_confidence"] is False

        for key in ("positions", "gap_pcts", "points_accumulated"):
            points = cup_ctx[key]
            assert [p["x"] for p in points] == [1, 2, 3, 4, 5]
            assert [p["label"] for p in points] == [f"V{i}" for i in range(1, 6)]
            for p in points:
                assert set(p) == {"x", "label", "y"}

    @pytest.mark.asyncio
    async def test_has_data_false_when_only_championships(self, race_groups_championship_only):
        from app.services.training.newsletter_builder import _build_charts_context, _build_race_block

        scenario = race_groups_championship_only
        race_block = await _build_race_block(scenario.session, scenario.athlete_id, scenario.season, 8)
        ctx = _build_charts_context(race_block)

        assert ctx["cups"] == []
        assert ctx["has_data"] is False
        assert ctx["has_championship"] is True

    @pytest.mark.asyncio
    async def test_low_confidence_is_computed_per_cup(self, race_groups_two_cups):
        """La copa principal tiene 5 válidas (>=5, alta confianza); "Liga
        Departamental" (fixture (b)) tiene solo 3 (<5, baja confianza) — el
        umbral se evalúa por copa, no de forma global."""
        from app.services.training.newsletter_builder import _build_charts_context, _build_race_block

        scenario = race_groups_two_cups
        race_block = await _build_race_block(scenario.session, scenario.athlete_id, scenario.season, 8)
        ctx = _build_charts_context(race_block)

        assert len(ctx["cups"]) == 2
        by_series = {c["series_id"]: c for c in ctx["cups"]}
        assert by_series[scenario.cup_series_id]["low_confidence"] is False
        assert by_series[scenario.second_cup_series_id]["low_confidence"] is True

    @pytest.mark.asyncio
    async def test_points_accumulated_matches_standings_total(self, race_groups_base_season):
        """El último punto de ``points_accumulated`` de una copa DEBE
        coincidir con el total de puntos del atleta en esa copa según
        ``services/race/standings.get_event_standings`` (contrato: "MUST
        equal the athlete's cup total in standings"). Se verifica también
        contra la suma independiente de ``points_awarded`` del fixture, para
        que un bug compartido entre ambos caminos no quede oculto detrás de
        "coinciden entre sí"."""
        from app.services.race.standings import get_event_standings
        from app.services.training.newsletter_builder import _build_charts_context, _build_race_block

        scenario = race_groups_base_season
        race_block = await _build_race_block(scenario.session, scenario.athlete_id, scenario.season, 8)
        ctx = _build_charts_context(race_block)

        cup_ctx = next(c for c in ctx["cups"] if c["series_id"] == scenario.cup_series_id)
        points_from_chart = cup_ctx["points_accumulated"][-1]["y"]

        standings = await get_event_standings(
            scenario.session, scenario.cup_event_ids[-1], category_id=scenario.category_id
        )
        standing_row = next(
            row
            for cat in standings.categories
            for row in cat.rows
            if row.competitor_id == scenario.competitor_id
        )

        # tests/fixtures/race_groups.py::_seed_cup_series otorga
        # max(40 - 4*(athlete_position - 1), 4) puntos por válida; el
        # atleta corre en athlete_position=2 (default) las 5 válidas de la
        # copa principal → 36 puntos x 5 = 180.
        expected_total = 5 * max(40 - 4 * (2 - 1), 4)

        assert points_from_chart == expected_total
        assert standing_row.total_points == expected_total


class TestTwoCupsOrderingAndIsolation:
    """T041 (039): con DOS copas en la temporada (fixture ``race_groups_two_cups``),
    ``_build_race_block``/``_build_charts_context`` deben mantenerlas
    ordenadas por válida más temprana y completamente aisladas entre sí.

    "Liga Departamental" corre desde 2026-01-05 (3 rondas); la copa
    principal desde 2026-01-15 (5 rondas) — Liga debe ir primero pese a
    tener ``series_id`` mayor (6002 > 6001) y a sembrarse DESPUÉS en
    ``seed_two_cups_season`` (ver docstring de ``tests/fixtures/race_groups.py``).
    """

    @pytest.mark.asyncio
    async def test_race_block_cups_ordered_and_histories_isolated(
        self, race_groups_two_cups
    ):
        from app.services.training.newsletter_builder import _build_race_block

        scenario = race_groups_two_cups
        block = await _build_race_block(
            scenario.session, scenario.athlete_id, scenario.season, 8
        )

        cups = block["cups"]
        assert len(cups) == 2
        assert [c["series_id"] for c in cups] == [
            scenario.second_cup_series_id,
            scenario.cup_series_id,
        ], f"Orden de cups inesperado: {[c['series_id'] for c in cups]}"

        liga_cup, main_cup = cups
        assert [row["event_id"] for row in liga_cup["history"]] == scenario.second_cup_event_ids
        assert [row["event_id"] for row in main_cup["history"]] == scenario.cup_event_ids

        # Cada historial trae EXCLUSIVAMENTE sus propias rondas — ninguna
        # fila de la otra copa se cuela en el histórico equivocado.
        liga_ids = {row["event_id"] for row in liga_cup["history"]}
        main_ids = {row["event_id"] for row in main_cup["history"]}
        assert liga_ids.isdisjoint(main_ids)
        assert len(liga_cup["history"]) == 3
        assert len(main_cup["history"]) == 5

    @pytest.mark.asyncio
    async def test_charts_context_per_cup_points_accumulated_isolated(
        self, race_groups_two_cups
    ):
        """El acumulado de puntos de cada copa en ``_build_charts_context``
        es SOLO la suma de sus propios puntos (contrato
        ``newsletter-context.md``). Los totales esperados se calculan de
        forma independiente a partir de la fórmula de puntos del fixture
        (no leyendo los propios números del chart), para que un bug
        compartido entre ``_build_race_block`` y ``_build_charts_context``
        no quede oculto detrás de "coinciden entre sí"."""
        from app.services.training.newsletter_builder import (
            _build_charts_context,
            _build_race_block,
        )

        scenario = race_groups_two_cups
        race_block = await _build_race_block(
            scenario.session, scenario.athlete_id, scenario.season, 8
        )
        ctx = _build_charts_context(race_block)

        assert len(ctx["cups"]) == 2
        by_series = {c["series_id"]: c for c in ctx["cups"]}

        # tests/fixtures/race_groups.py::_seed_cup_series otorga
        # max(40 - 4*(athlete_position - 1), 4) puntos por válida;
        # athlete_position=2 (default) en ambas copas de este fixture.
        per_round_points = max(40 - 4 * (2 - 1), 4)
        expected_main_total = per_round_points * len(scenario.cup_event_ids)
        expected_liga_total = per_round_points * len(scenario.second_cup_event_ids)

        main_ctx = by_series[scenario.cup_series_id]
        liga_ctx = by_series[scenario.second_cup_series_id]

        assert main_ctx["points_accumulated"][-1]["y"] == expected_main_total
        assert liga_ctx["points_accumulated"][-1]["y"] == expected_liga_total
