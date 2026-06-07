"""Servicio de restablecimiento de contraseña (specs/003-password-reset-login).

Diseño alineado con OWASP (Forgot Password Cheat Sheet):
  - Token de 256 bits (`secrets.token_urlsafe(32)`), almacenado **hasheado**
    (SHA-256) — el token en claro solo viaja en el enlace por correo.
  - Vigencia corta (default 60 min), un solo uso.
  - Crear un token o consumir uno invalida los demás tokens vigentes del usuario.
  - A prueba de enumeración: el router responde siempre neutral; aquí no se
    revela si la cuenta existe (las funciones devuelven None silenciosamente).
  - Rate-limit por correo dentro de una ventana móvil (anti-flooding).
  - Logs solo con ids (nunca correo ni token) — privacidad de menores (Ley 1581).
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
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services.auth import hash_password

logger = logging.getLogger(__name__)


def _hash_token(raw_token: str) -> str:
    """SHA-256 hex del token en claro. Apropiado para un secreto de alta entropía."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Normaliza a aware-UTC (las fechas guardadas en MySQL/SQLite son naive)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def _invalidate_user_tokens(user_id: int, db: AsyncSession) -> None:
    """Marca como usados todos los tokens vigentes del usuario."""
    stmt = select(PasswordResetToken).where(
        PasswordResetToken.user_id == user_id,
        PasswordResetToken.used_at.is_(None),
    )
    for tok in (await db.execute(stmt)).scalars().all():
        tok.used_at = _now()


async def request_reset(
    email: str,
    db: AsyncSession,
    ip_address: str | None = None,
) -> tuple[User, str] | None:
    """Crea un token de restablecimiento si la cuenta es elegible.

    Devuelve ``(user, reset_url)`` cuando se debe enviar correo, o ``None`` en
    cualquier otro caso (cuenta inexistente, inactiva, sin login, o rate-limit
    excedido). El llamador (router) responde siempre con el mismo mensaje
    neutral, sin importar el resultado, para evitar enumeración de cuentas.
    """
    normalized = email.strip()

    user = (
        await db.execute(select(User).where(User.email == normalized))
    ).scalar_one_or_none()

    # Cuenta inexistente o que no puede iniciar sesión: no se genera nada.
    if (
        user is None
        or not user.is_active
        or not user.can_login
        or not user.hashed_password
    ):
        logger.info("password_reset: solicitud sin cuenta elegible")
        return None

    # Rate-limit por correo dentro de la ventana móvil.
    window_start = _now() - timedelta(minutes=settings.password_reset_window_minutes)
    recent_count = (
        await db.execute(
            select(func.count(PasswordResetToken.id)).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.created_at >= window_start,
            )
        )
    ).scalar_one()
    if recent_count >= settings.password_reset_max_per_window:
        logger.warning(
            "password_reset: rate-limit alcanzado | user_id=%s", user.id
        )
        return None

    # Invalidar tokens previos antes de emitir uno nuevo.
    await _invalidate_user_tokens(user.id, db)

    raw_token = secrets.token_urlsafe(32)
    token = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=_now()
        + timedelta(minutes=settings.password_reset_token_ttl_minutes),
        requested_ip=ip_address,
    )
    db.add(token)
    await db.flush()

    reset_url = f"{settings.frontend_base_url}/restablecer-contrasena?token={raw_token}"
    logger.info("password_reset: token emitido | user_id=%s", user.id)
    return user, reset_url


async def _get_token_row(raw_token: str, db: AsyncSession) -> PasswordResetToken | None:
    return (
        await db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == _hash_token(raw_token)
            )
        )
    ).scalar_one_or_none()


async def validate_token(raw_token: str, db: AsyncSession) -> PasswordResetToken:
    """Devuelve la fila del token si es válido; lanza 404/410 en caso contrario.

    Mensajes genéricos: el token es secreto, por lo que informar al portador del
    enlace sobre su validez no es una fuga de enumeración.
    """
    row = await _get_token_row(raw_token, db)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enlace no válido.",
        )
    if row.used_at is not None or _as_utc(row.expires_at) < _now():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="El enlace ha expirado o ya fue utilizado. Solicita uno nuevo.",
        )
    return row


async def consume_token(
    raw_token: str,
    new_password: str,
    db: AsyncSession,
) -> User:
    """Aplica la nueva contraseña y consume el token (un solo uso).

    Actualiza ``hashed_password``, marca ``used_at`` e invalida los tokens
    hermanos. No emite JWT (sin auto-login, por recomendación de OWASP).
    """
    row = await validate_token(raw_token, db)

    user = await db.get(User, row.user_id)
    if user is None:
        # Defensa: la cuenta desapareció entre la emisión y el consumo.
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="El enlace ha expirado o ya fue utilizado. Solicita uno nuevo.",
        )

    user.hashed_password = hash_password(new_password)
    row.used_at = _now()
    await _invalidate_user_tokens(user.id, db)
    await db.flush()
    logger.info("password_reset: contraseña actualizada | user_id=%s", user.id)
    return user
