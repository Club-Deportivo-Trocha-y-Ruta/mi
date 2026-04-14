import pytest
from fastapi import HTTPException

from app.models.user import UserRole
from app.services.permissions import require_role


class TestRequireRole:
    def test_permite_rol_exactamente_en_lista(self):
        """No lanza excepción cuando el rol está en la lista."""
        require_role(UserRole.admin, [UserRole.admin])

    def test_permite_coach_en_lista_de_coach_y_admin(self):
        require_role(UserRole.coach, [UserRole.admin, UserRole.coach])

    def test_permite_admin_en_lista_de_admin_y_coach(self):
        require_role(UserRole.admin, [UserRole.admin, UserRole.coach])

    def test_rechaza_cuando_rol_no_esta_en_lista(self):
        with pytest.raises(HTTPException) as exc_info:
            require_role(UserRole.parent, [UserRole.admin, UserRole.coach])
        assert exc_info.value.status_code == 403

    def test_mensaje_de_error_es_correcto(self):
        with pytest.raises(HTTPException) as exc_info:
            require_role(UserRole.parent, [UserRole.admin])
        assert exc_info.value.detail == "No tienes permisos para esta accion"

    def test_rechaza_athlete_en_lista_solo_admin(self):
        with pytest.raises(HTTPException) as exc_info:
            require_role(UserRole.athlete, [UserRole.admin])
        assert exc_info.value.status_code == 403

    def test_lista_vacia_rechaza_cualquier_rol(self):
        with pytest.raises(HTTPException):
            require_role(UserRole.admin, [])

    def test_todos_los_roles_permitidos_acepta_admin(self):
        require_role(
            UserRole.admin,
            [UserRole.admin, UserRole.coach, UserRole.parent, UserRole.athlete],
        )
