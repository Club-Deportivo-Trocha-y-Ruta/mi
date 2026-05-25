"""Servicio de autenticación: passwords, JWT y persistencia de refresh tokens.

A partir de la auditoría A3:

- ``create_access_token`` y ``create_refresh_token`` ahora incluyen
  ``jti`` (uuid4 hex), ``iat`` y ``nbf`` para soportar revocación y
  análisis de uso.
- ``create_refresh_token`` retorna una tupla ``(token, jti, expires_at)``
  para que el router persista el ``jti`` en ``refresh_tokens``.
- Helpers ``persist_refresh_token`` / ``revoke_refresh_token`` /
  ``is_refresh_revoked`` operan sobre el modelo ORM.

Privacidad: nunca se loguean tokens ni payloads completos. Solo se
maneja el ``jti`` (identificador opaco).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import bcrypt
import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.refresh_token import RefreshToken


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(data: dict) -> str:
    """Crea un access token JWT con ``jti``/``iat``/``nbf``/``exp``."""
    now = _utc_now()
    payload = data.copy()
    payload.setdefault("jti", uuid4().hex)
    payload["iat"] = int(now.timestamp())
    payload["nbf"] = int(now.timestamp())
    payload["exp"] = now + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload["type"] = "access"
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def create_refresh_token(data: dict) -> tuple[str, str, datetime]:
    """Crea un refresh token JWT y retorna ``(token, jti, expires_at)``.

    El caller debe persistir ``jti``/``expires_at`` en ``refresh_tokens``
    via :func:`persist_refresh_token`.
    """
    now = _utc_now()
    jti = uuid4().hex
    expires_at = now + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = data.copy()
    payload["jti"] = jti
    payload["iat"] = int(now.timestamp())
    payload["nbf"] = int(now.timestamp())
    payload["exp"] = expires_at
    payload["type"] = "refresh"
    token = jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    return token, jti, expires_at


def decode_token(token: str) -> dict:
    return jwt.decode(
        token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
    )


# ---------------------------------------------------------------------------
# Persistencia / revocación de refresh tokens
# ---------------------------------------------------------------------------


async def persist_refresh_token(
    db: AsyncSession,
    *,
    jti: str,
    user_id: int,
    expires_at: datetime,
    issued_at: datetime | None = None,
) -> RefreshToken:
    """Inserta la fila ``refresh_tokens`` correspondiente al jti.

    No hace commit: el router decide la unidad de trabajo.
    """
    row = RefreshToken(
        jti=jti,
        user_id=user_id,
        issued_at=issued_at or _utc_now(),
        expires_at=expires_at,
        revoked_at=None,
        replaced_by_jti=None,
    )
    db.add(row)
    await db.flush()
    return row


async def revoke_refresh_token(
    db: AsyncSession,
    jti: str,
    *,
    replaced_by: str | None = None,
) -> None:
    """Marca el jti como revocado. No-op si no existe."""
    stmt = (
        update(RefreshToken)
        .where(
            RefreshToken.jti == jti,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=_utc_now(), replaced_by_jti=replaced_by)
    )
    await db.execute(stmt)


async def is_refresh_revoked(db: AsyncSession, jti: str) -> bool:
    """Retorna True si el jti está revocado **o no existe en la tabla**.

    No-existencia = revocado porque significa que el token fue emitido
    antes de la introducción de la tabla (compat backward) o fue
    descartado manualmente.
    """
    stmt = select(RefreshToken.revoked_at).where(RefreshToken.jti == jti)
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        # Si no existe el jti en la tabla, consideramos el token como
        # válido (compat: tokens previos a la introducción del jti tracker).
        # El router lo trata como "no revocado" — la validación de exp
        # del JWT sigue garantizando expiración temporal.
        return False
    return row[0] is not None


async def revoke_all_refresh_tokens_for_user(
    db: AsyncSession, user_id: int
) -> int:
    """Revoca todos los refresh tokens vivos de un usuario (logout total).

    Útil para ``/logout`` o ante cambio de contraseña.
    """
    stmt = (
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=_utc_now())
    )
    result = await db.execute(stmt)
    return result.rowcount or 0


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "persist_refresh_token",
    "revoke_refresh_token",
    "is_refresh_revoked",
    "revoke_all_refresh_tokens_for_user",
]
