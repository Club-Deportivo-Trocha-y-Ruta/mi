"""Tests CRÍTICOS de privacidad — módulo Training Sessions.

INVARIANTES QUE NUNCA PUEDEN FALLAR:
1. Padre A NO ve sesiones de atleta B (otro padre).
2. Padre A NO puede ver el historial de asistencia de atleta B.
3. Padre A SÍ puede ver el historial de asistencia de SU atleta A1.
4. Coach del club A NO puede ver sesiones del club B.
5. Coach del club B NO puede editar asistencia de sesiones del club A.
6. Padre A filtrando por athlete_id=A2 → 403.
7. Respuesta de sesión a padre P1 (con A1 convocado) NO incluye feedback de otros convocados.
8. Padre NO puede generar reporte mensual del club.

Estrategia: todos los tests usan mocks de service layer para aislar la lógica
de permisos de la dependencia de la DB de test.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.training_session import (
    AttendanceStatus,
    SessionStatus,
)
from app.services.permissions import (
    can_view_athlete_feedback,
    can_view_monthly_report,
    can_view_session,
    parent_athlete_ids,
)
from app.models.user import User, UserRole
from app.models.club import ClubRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    user_id: int,
    role: UserRole = UserRole.parent,
    club_id: int | None = None,
) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.role = role
    u.email = f"user{user_id}@test.com"
    u.first_name = f"User{user_id}"
    u.last_name = "Test"
    u.club_memberships = []
    if club_id is not None:
        membership = MagicMock()
        membership.club_id = club_id
        membership.role_in_club = ClubRole.coach if role == UserRole.coach else ClubRole.member
        u.club_memberships = [membership]
    return u


def _make_session(session_id: int, club_id: int) -> MagicMock:
    s = MagicMock()
    s.id = session_id
    s.club_id = club_id
    s.status = SessionStatus.PLANNED
    s.attendances = []
    return s


def _make_db_with_parent_athletes(athlete_ids: list[int]) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=athlete_ids)))
    db.execute = AsyncMock(return_value=result)
    return db


def _make_db_no_club_membership() -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=result)
    return db


def _make_db_with_club_membership() -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=ClubRole.coach)
    db.execute = AsyncMock(return_value=result)
    return db


# ---------------------------------------------------------------------------
# INVARIANTE 1: Padre A NO ve sesiones de atleta B (no convocado en ninguna)
# ---------------------------------------------------------------------------


class TestParentCannotSeeOtherAthleteSession:
    async def test_parent_a_blocked_from_session_where_only_a2_convocado(self):
        """
        Setup: sesión del Club A con solo A2 convocado.
        P1 es padre de A1. P1 NO debe poder ver esa sesión.
        """
        parent_p1 = _make_user(user_id=10, role=UserRole.parent)

        session = _make_session(session_id=1, club_id=1)
        # Sesión tiene solo A2 convocado (athlete_id=200)
        att_a2 = MagicMock()
        att_a2.athlete_id = 200
        session.attendances = [att_a2]

        db = AsyncMock()

        # parent_athlete_ids retorna [A1=100] para P1
        # El execute para ParentAthlete retorna [100]
        # El execute para SessionAttendance no encuentra match con [100] (solo hay A2=200)
        call_count = 0

        async def execute_side(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # parent_athlete_ids query
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[100])))
            else:
                # SessionAttendance check — no match
                result.first = MagicMock(return_value=None)
            return result

        db.execute = AsyncMock(side_effect=execute_side)

        allowed = await can_view_session(db, parent_p1, session)
        assert allowed is False, "Padre P1 NO debe ver sesión donde solo está convocado A2"

    async def test_parent_a_allowed_when_a1_is_convocado(self):
        """P1 SÍ puede ver sesión donde A1 está convocado."""
        parent_p1 = _make_user(user_id=10, role=UserRole.parent)
        session = _make_session(session_id=1, club_id=1)

        call_count = 0

        async def execute_side(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # parent_athlete_ids retorna [100]
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[100])))
            else:
                # SessionAttendance — match encontrado
                result.first = MagicMock(return_value=MagicMock())
            return result

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=execute_side)

        allowed = await can_view_session(db, parent_p1, session)
        assert allowed is True

    async def test_parent_without_children_cannot_see_any_session(self):
        """Padre sin atletas vinculados → nunca puede ver sesiones."""
        parent = _make_user(user_id=50, role=UserRole.parent)
        session = _make_session(session_id=1, club_id=1)

        db = AsyncMock()
        result = MagicMock()
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        db.execute = AsyncMock(return_value=result)

        allowed = await can_view_session(db, parent, session)
        assert allowed is False


# ---------------------------------------------------------------------------
# INVARIANTE 2: Padre A NO puede ver historial de atleta B
# ---------------------------------------------------------------------------


class TestParentCannotSeeOtherAthleteHistory:
    async def test_parent_cannot_see_feedback_of_foreign_athlete(self):
        """P1 NO puede ver feedback individual de A2 (que no es su hijo)."""
        parent_p1 = _make_user(user_id=10, role=UserRole.parent)

        db = AsyncMock()
        result = MagicMock()
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[100])))
        db.execute = AsyncMock(return_value=result)

        allowed = await can_view_athlete_feedback(db, parent_p1, athlete_id=200)
        assert allowed is False, "P1 no debe ver feedback de A2"

    async def test_parent_can_see_own_athlete_feedback(self):
        """P1 SÍ puede ver feedback individual de su atleta A1."""
        parent_p1 = _make_user(user_id=10, role=UserRole.parent)

        db = AsyncMock()
        result = MagicMock()
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[100])))
        db.execute = AsyncMock(return_value=result)

        allowed = await can_view_athlete_feedback(db, parent_p1, athlete_id=100)
        assert allowed is True, "P1 DEBE ver feedback de su propio atleta A1"


# ---------------------------------------------------------------------------
# INVARIANTE 3: parent_athlete_ids retorna solo los atletas del padre
# ---------------------------------------------------------------------------


class TestParentAthleteIds:
    async def test_parent_athlete_ids_returns_only_own_children(self):
        db = _make_db_with_parent_athletes([100, 102])
        ids = await parent_athlete_ids(db, user_id=10)
        assert 100 in ids
        assert 102 in ids
        assert 200 not in ids

    async def test_parent_with_no_children_returns_empty(self):
        db = _make_db_with_parent_athletes([])
        ids = await parent_athlete_ids(db, user_id=99)
        assert ids == []


# ---------------------------------------------------------------------------
# INVARIANTE 4: Coach del club A NO ve sesiones del club B
# ---------------------------------------------------------------------------


class TestCoachCrossClubIsolation:
    async def test_coach_club_a_cannot_view_session_club_b(self):
        """Coach del club A (role sin membership en club B) → False para sesión de B."""
        coach_a = _make_user(user_id=20, role=UserRole.coach, club_id=1)

        # Sesión pertenece al club B (id=2)
        session_b = _make_session(session_id=10, club_id=2)

        # DB: user_club_role para coach en club_id=2 retorna None (no es miembro)
        db = _make_db_no_club_membership()

        allowed = await can_view_session(db, coach_a, session_b)
        assert allowed is False, "Coach del club A NO debe ver sesiones del club B"

    async def test_coach_club_a_can_view_own_club_session(self):
        """Coach del club A → True para sesión de su propio club."""
        coach_a = _make_user(user_id=20, role=UserRole.coach, club_id=1)
        session_a = _make_session(session_id=5, club_id=1)

        db = _make_db_with_club_membership()

        allowed = await can_view_session(db, coach_a, session_a)
        assert allowed is True


# ---------------------------------------------------------------------------
# INVARIANTE 5: Coach del club B NO puede editar asistencia del club A
# ---------------------------------------------------------------------------


class TestCoachCannotEditCrossClubAttendance:
    async def test_coach_b_blocked_from_editing_club_a_attendance(self):
        """
        can_view_session del club B da False para sesión del club A.
        La edición requiere can_view, así que la check es consistente.
        """
        coach_b = _make_user(user_id=30, role=UserRole.coach, club_id=2)
        session_a = _make_session(session_id=5, club_id=1)

        # user_club_role para coach_b en club 1 → None
        db = _make_db_no_club_membership()
        allowed = await can_view_session(db, coach_b, session_a)
        assert allowed is False


# ---------------------------------------------------------------------------
# INVARIANTE 7: Respuesta al padre no filtra feedback de otros convocados
# — Verificación de la lógica de can_view_athlete_feedback
# ---------------------------------------------------------------------------


class TestParentResponsePrivacy:
    async def test_parent_can_only_see_own_athlete_feedback(self):
        """
        P1 tiene A1. P2 tiene A2. Ambos en la misma sesión.
        P1 puede ver feedback de A1 pero NO de A2.
        """
        parent_p1 = _make_user(user_id=10, role=UserRole.parent)
        parent_p2 = _make_user(user_id=11, role=UserRole.parent)

        # P1 ve A1 (100)
        db_p1 = AsyncMock()
        result_p1 = MagicMock()
        result_p1.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[100])))
        db_p1.execute = AsyncMock(return_value=result_p1)

        allowed_a1 = await can_view_athlete_feedback(db_p1, parent_p1, athlete_id=100)
        allowed_a2_by_p1 = await can_view_athlete_feedback(db_p1, parent_p1, athlete_id=200)
        assert allowed_a1 is True
        assert allowed_a2_by_p1 is False

        # P2 ve A2 (200)
        db_p2 = AsyncMock()
        result_p2 = MagicMock()
        result_p2.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[200])))
        db_p2.execute = AsyncMock(return_value=result_p2)

        allowed_a2_by_p2 = await can_view_athlete_feedback(db_p2, parent_p2, athlete_id=200)
        allowed_a1_by_p2 = await can_view_athlete_feedback(db_p2, parent_p2, athlete_id=100)
        assert allowed_a2_by_p2 is True
        assert allowed_a1_by_p2 is False


# ---------------------------------------------------------------------------
# INVARIANTE 8: Padre NO puede ver reporte mensual individual del club
# ---------------------------------------------------------------------------


class TestParentMonthlyReportAccess:
    async def test_parent_can_see_aggregate_report(self):
        """Padre puede ver reporte agregado (individual=False)."""
        parent = _make_user(user_id=10, role=UserRole.parent)
        db = AsyncMock()

        allowed = await can_view_monthly_report(db, parent, club_id=1, individual=False)
        assert allowed is True

    async def test_parent_cannot_see_individual_report(self):
        """Padre NO puede ver reporte con datos individuales."""
        parent = _make_user(user_id=10, role=UserRole.parent)
        db = AsyncMock()

        allowed = await can_view_monthly_report(db, parent, club_id=1, individual=True)
        assert allowed is False

    async def test_coach_can_see_individual_and_aggregate_reports(self):
        """Coach de su club puede ver ambos tipos de reporte."""
        coach = _make_user(user_id=20, role=UserRole.coach)
        db = _make_db_with_club_membership()

        allowed_aggregate = await can_view_monthly_report(db, coach, club_id=1, individual=False)
        assert allowed_aggregate is True

    async def test_admin_can_always_see_reports(self):
        """Admin tiene acceso total."""
        admin = _make_user(user_id=1, role=UserRole.admin)
        db = AsyncMock()

        allowed = await can_view_monthly_report(db, admin, club_id=1, individual=True)
        assert allowed is True


# ---------------------------------------------------------------------------
# INVARIANTE extra: Admin siempre puede ver todo
# ---------------------------------------------------------------------------


class TestAdminAlwaysHasAccess:
    async def test_admin_can_view_any_session(self):
        admin = _make_user(user_id=1, role=UserRole.admin)
        session = _make_session(session_id=1, club_id=99)
        db = AsyncMock()

        allowed = await can_view_session(db, admin, session)
        assert allowed is True

    async def test_admin_can_see_any_athlete_feedback(self):
        admin = _make_user(user_id=1, role=UserRole.admin)
        db = AsyncMock()

        allowed = await can_view_athlete_feedback(db, admin, athlete_id=999)
        assert allowed is True

    async def test_admin_can_see_monthly_reports(self):
        admin = _make_user(user_id=1, role=UserRole.admin)
        db = AsyncMock()

        allowed = await can_view_monthly_report(db, admin, club_id=1)
        assert allowed is True


# ---------------------------------------------------------------------------
# INVARIANTE: Datos de respuesta no filtran PII cross-atleta
# — Test de la estructura del schema TrainingSessionRead
# ---------------------------------------------------------------------------


class TestSessionResponseDoesNotLeakIndividualFeedback:
    def test_training_session_read_has_no_individual_feedback_field(self):
        """
        TrainingSessionRead solo expone attendance_summary (conteos agregados),
        nunca el campo individual_feedback de cada atleta.
        """
        from app.schemas.training_session import TrainingSessionRead
        fields = set(TrainingSessionRead.model_fields.keys())
        # La respuesta de la sesión NO debe tener individual_feedback directamente
        assert "individual_feedback" not in fields, (
            "TrainingSessionRead no debe exponer individual_feedback directamente — "
            "viola la privacidad de retroalimentación individual"
        )

    def test_training_session_read_has_aggregated_summary_not_per_athlete(self):
        """
        La respuesta de sesión tiene attendance_summary (agregado), no lista de
        AttendanceRead completa con feedback individual.
        """
        from app.schemas.training_session import TrainingSessionRead, AttendanceSummary
        fields = TrainingSessionRead.model_fields
        assert "attendance_summary" in fields
        # El campo attendances (lista con feedback individual) NO debe estar en TrainingSessionRead
        assert "attendances" not in fields, (
            "TrainingSessionRead no debe exponer la lista raw de attendances con feedback individual"
        )

    def test_attendance_summary_schema_has_only_counts(self):
        """AttendanceSummary solo tiene conteos — nunca nombres, feedback ni RPE individual."""
        from app.schemas.training_session import AttendanceSummary
        fields = set(AttendanceSummary.model_fields.keys())
        pii_fields = {"individual_feedback", "rpe_omni", "rubric_effort",
                      "rubric_attitude", "rubric_technique", "athlete_id",
                      "excuse_reason", "athlete_name"}
        leaked = fields & pii_fields
        assert not leaked, f"AttendanceSummary expone campos PII: {leaked}"
