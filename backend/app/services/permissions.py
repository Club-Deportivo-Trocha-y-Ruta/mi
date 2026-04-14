from fastapi import HTTPException, status

from app.models.user import UserRole


def require_role(user_role: UserRole, allowed_roles: list[UserRole]) -> None:
    """Verifica que el rol del usuario este en la lista de roles permitidos."""
    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para esta accion",
        )
