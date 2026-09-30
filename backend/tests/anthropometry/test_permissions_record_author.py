"""Feature 048 (T010, research R2, clarificación 3): solo el evaluador de la
medición o un admin pueden editarla o eliminarla.

Pruebas unitarias puras sobre instancias ORM transitorias (sin BD): el helper
es síncrono y solo compara rol e ids.
"""

from __future__ import annotations

import pytest

from app.models.anthropometry import AnthropometricRecord
from app.models.user import User, UserRole
from app.services.permissions import can_modify_anthropometric_record

EVALUATOR_ID = 10
OTHER_COACH_ID = 11
ADMIN_ID = 1
PARENT_ID = 20


def _user(user_id: int, role: UserRole) -> User:
    return User(id=user_id, role=role, first_name="Usuario", last_name="Prueba")


def _record(evaluated_by: int = EVALUATOR_ID) -> AnthropometricRecord:
    return AnthropometricRecord(id=100, athlete_id=5, evaluated_by=evaluated_by)


def test_evaluator_coach_can_modify() -> None:
    assert can_modify_anthropometric_record(_user(EVALUATOR_ID, UserRole.coach), _record()) is True


def test_admin_can_modify_record_taken_by_someone_else() -> None:
    assert can_modify_anthropometric_record(_user(ADMIN_ID, UserRole.admin), _record()) is True


def test_admin_who_is_also_evaluator_can_modify() -> None:
    record = _record(evaluated_by=ADMIN_ID)
    assert can_modify_anthropometric_record(_user(ADMIN_ID, UserRole.admin), record) is True


def test_other_coach_cannot_modify() -> None:
    """Otro coach del mismo club ve la medición pero no puede cambiarla."""
    assert (
        can_modify_anthropometric_record(_user(OTHER_COACH_ID, UserRole.coach), _record())
        is False
    )


@pytest.mark.parametrize("role", [UserRole.parent, UserRole.athlete])
def test_parent_and_athlete_cannot_modify(role: UserRole) -> None:
    assert can_modify_anthropometric_record(_user(PARENT_ID, role), _record()) is False
