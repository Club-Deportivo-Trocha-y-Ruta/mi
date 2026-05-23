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
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.training.newsletter_builder import (
    _build_charts_context,
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
    from app.models.training_session import AttendanceStatus

    db = make_session()
    athlete = make_athlete()

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
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

    async def mock_execute(stmt):
        return make_scalars_result([athlete] if "Athlete" in str(stmt) else [])

    db.execute = AsyncMock(side_effect=lambda stmt: make_scalars_result(
        [athlete] if call_count_holder[0] == 1 else []
    ))

    call_count = 0

    async def mock_execute2(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([athlete])
        return make_scalars_result([])

    db.execute = mock_execute2
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
        block = _build_support_block()
        assert "tips" in block
        assert isinstance(block["tips"], list)
        assert len(block["tips"]) > 0

    def test_tips_have_required_fields(self):
        block = _build_support_block()
        for tip in block["tips"]:
            assert "category" in tip
            assert "title" in tip
            assert "text" in tip

    def test_no_calorie_counting_language(self):
        """El bloque de apoyo no debe incluir conteo calórico."""
        block = _build_support_block()
        combined = " ".join(t["text"] for t in block["tips"]).lower()
        # No debe mencionar contar calorías como instrucción
        assert "contar calorías" not in combined
        assert "cuenta las calorías" not in combined

    def test_no_supplements_recommendation(self):
        """El bloque no debe recomendar suplementos."""
        block = _build_support_block()
        combined = " ".join(t["text"] for t in block["tips"]).lower()
        # No debe recomendar suplementos
        assert "tomar suplemento" not in combined
        assert "proteína en polvo" not in combined
        assert "creatina" not in combined

    def test_hydration_tip_present(self):
        block = _build_support_block()
        categories = {t["category"] for t in block["tips"]}
        assert "hidratacion" in categories

    def test_sleep_tip_present(self):
        block = _build_support_block()
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
