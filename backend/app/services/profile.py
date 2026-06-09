"""Servicio de perfil / ajustes de cuenta (specs/004-user-profile).

Cubre tres flujos autoservicio sobre el usuario autenticado:

1. Información básica (nombre, apellido, teléfono).
2. Cambio de contraseña en sesión (re-autenticación con la contraseña actual,
   OWASP Authentication Cheat Sheet).
3. Cambio de correo con verificación previa de la nueva dirección
   (verify-new-email-before-apply, OWASP "Changing a User's Registered Email
   Address"): se emite un token de un solo uso, hasheado (SHA-256) y de vigencia
   corta; el correo de la cuenta solo cambia cuando el titular confirma desde el
   nuevo buzón. A prueba de enumeración: un correo ya en uso produce la MISMA
   respuesta neutral que el camino exitoso, sin enviar nada.

Privacidad (Ley 1581): los logs usan solo ids (nunca correo, nombre ni token).
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.email_change_request import EmailChangeRequest
from app.models.user import User
from app.schemas.profile import ProfileBasicUpdate
from app.services.auth import hash_password, verify_password

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _hash_token(raw_token: str) -> str:
    """SHA-256 hex del token en claro (secreto de alta entropía)."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Normaliza a aware-UTC (las fechas en MySQL/SQLite son naive)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Información básica
# ---------------------------------------------------------------------------
async def update_basic_info(
    user: User, data: ProfileBasicUpdate, db: AsyncSession
) -> User:
    """Actualiza nombre/apellido/teléfono del usuario autenticado.

    Solo aplica los campos provistos (``exclude_unset``). No toca correo, rol,
    estado ni credenciales.
    """
    payload = data.model_dump(exclude_unset=True)
    for field, value in payload.items():
        setattr(user, field, value)
    await db.flush()
    logger.info("profile: información básica actualizada | user_id=%s", user.id)
    return user


# ---------------------------------------------------------------------------
# Cambio de contraseña
# ---------------------------------------------------------------------------
async def change_password(
    user: User, current_password: str, new_password: str, db: AsyncSession
) -> User:
    """Cambia la contraseña tras verificar la contraseña actual.

    Lanza 400 si la contraseña actual es incorrecta (sin modificar nada).
    """
    if not verify_password(current_password, user.hashed_password or ""):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual no es correcta.",
        )

    user.hashed_password = hash_password(new_password)
    await db.flush()
    logger.info("profile: contraseña actualizada | user_id=%s", user.id)
    return user


# ---------------------------------------------------------------------------
# Cambio de correo — solicitud
# ---------------------------------------------------------------------------
async def _invalidate_user_requests(user_id: int, db: AsyncSession) -> None:
    """Marca como usadas todas las solicitudes vigentes del usuario."""
    stmt = select(EmailChangeRequest).where(
        EmailChangeRequest.user_id == user_id,
        EmailChangeRequest.used_at.is_(None),
    )
    for row in (await db.execute(stmt)).scalars().all():
        row.used_at = _now()


async def request_email_change(
    user: User,
    current_password: str,
    new_email: str,
    db: AsyncSession,
    ip_address: str | None = None,
) -> tuple[str, str] | None:
    """Crea una solicitud de cambio de correo si procede.

    Devuelve ``(new_email, confirm_url)`` cuando se debe enviar el correo de
    verificación a la nueva dirección, o ``None`` cuando NO se debe enviar nada
    (correo igual al actual, ya en uso por otra cuenta, o rate-limit excedido).
    El router responde siempre con el mismo mensaje neutral, para evitar
    enumeración de cuentas.

    Lanza 400 si la contraseña actual es incorrecta (re-autenticación OWASP).
    """
    # Re-autenticación obligatoria antes de iniciar el cambio.
    if not verify_password(current_password, user.hashed_password or ""):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual no es correcta.",
        )

    normalized = new_email.strip().lower()

    # Igual al correo actual: no-op silencioso (no es conflicto).
    if user.email is not None and normalized == user.email.strip().lower():
        logger.info("profile: cambio de correo no-op | user_id=%s", user.id)
        return None

    # Ya en uso por otra cuenta: respuesta neutral, sin enviar nada.
    existing = (
        await db.execute(select(User.id).where(func.lower(User.email) == normalized))
    ).scalar_one_or_none()
    if existing is not None:
        logger.info("profile: cambio de correo a dirección en uso | user_id=%s", user.id)
        return None

    # Rate-limit por usuario dentro de la ventana móvil.
    window_start = _now() - timedelta(minutes=settings.email_change_window_minutes)
    recent_count = (
        await db.execute(
            select(func.count(EmailChangeRequest.id)).where(
                EmailChangeRequest.user_id == user.id,
                EmailChangeRequest.created_at >= window_start,
            )
        )
    ).scalar_one()
    if recent_count >= settings.email_change_max_per_window:
        logger.warning("profile: rate-limit cambio de correo | user_id=%s", user.id)
        return None

    # Invalidar solicitudes previas antes de emitir una nueva.
    await _invalidate_user_requests(user.id, db)

    raw_token = secrets.token_urlsafe(32)
    req = EmailChangeRequest(
        user_id=user.id,
        new_email=normalized,
        token_hash=_hash_token(raw_token),
        expires_at=_now()
        + timedelta(minutes=settings.email_change_token_ttl_minutes),
        requested_ip=ip_address,
    )
    db.add(req)
    await db.flush()

    confirm_url = f"{settings.frontend_base_url}/confirmar-correo?token={raw_token}"
    logger.info("profile: solicitud de cambio de correo emitida | user_id=%s", user.id)
    return normalized, confirm_url


# ---------------------------------------------------------------------------
# Cambio de correo — confirmación
# ---------------------------------------------------------------------------
async def _get_request_row(
    raw_token: str, db: AsyncSession
) -> EmailChangeRequest | None:
    return (
        await db.execute(
            select(EmailChangeRequest).where(
                EmailChangeRequest.token_hash == _hash_token(raw_token)
            )
        )
    ).scalar_one_or_none()


async def confirm_email_change(
    raw_token: str, db: AsyncSession
) -> tuple[User, str]:
    """Aplica el cambio de correo usando un token válido (un solo uso).

    Devuelve ``(user, old_email)`` para que el router avise a la dirección
    anterior. Lanza 404 (token desconocido), 410 (usado/expirado) o 409 (la
    dirección fue tomada por otra cuenta entre la solicitud y la confirmación).
    """
    row = await _get_request_row(raw_token, db)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enlace no válido.",
        )
    if row.used_at is not None or _as_utc(row.expires_at) < _now():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="El enlace ha expirado o ya fue utilizado. Solicita el cambio nuevamente.",
        )

    user = await db.get(User, row.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="El enlace ha expirado o ya fue utilizado. Solicita el cambio nuevamente.",
        )

    # Defensa: la dirección pudo ser tomada por otra cuenta tras la solicitud.
    taken = (
        await db.execute(
            select(User.id).where(
                func.lower(User.email) == row.new_email,
                User.id != user.id,
            )
        )
    ).scalar_one_or_none()
    if taken is not None:
        row.used_at = _now()
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se pudo aplicar el cambio. Solicita el cambio nuevamente.",
        )

    old_email = user.email or ""
    user.email = row.new_email
    row.used_at = _now()
    await _invalidate_user_requests(user.id, db)
    await db.flush()
    logger.info("profile: correo actualizado | user_id=%s", user.id)
    return user, old_email
