"""Modelo SQLAlchemy de ``refresh_tokens``.

Persistencia de los ``jti`` (JWT ID) de cada refresh token emitido, para
permitir revocación explícita y romper la cadena cuando se rota uno.

Patrón
======
- Cada refresh token JWT incluye ``jti`` único (uuid4 hex).
- En ``/login`` se persiste una fila ``RefreshToken`` para ese jti.
- En ``/refresh`` el caller verifica que el ``jti`` actual no esté
  revocado (``revoked_at IS NULL``); rota emitiendo un nuevo refresh con
  nuevo ``jti`` y marca el viejo como ``revoked_at=now, replaced_by_jti=
  <nuevo>``.
- En ``/logout`` (cuando exista) se revoca el jti activo.

Diseño:
* ``jti`` es PK CHAR(32) (uuid4.hex → 32 chars).
* FK a ``users.id`` con ``CASCADE`` para limpiar tokens si se borra al
  usuario duro.
* Índice compuesto ``(user_id, revoked_at)`` para listar/contar tokens
  vivos por usuario.

Privacidad
==========
Las filas contienen únicamente identificadores opacos (jti, user_id,
timestamps). No se almacena el token serializado.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CHAR, DateTime, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(Base):
    """Refresh token JWT activo (o revocado) emitido a un usuario."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_user_revoked", "user_id", "revoked_at"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
    )

    jti: Mapped[str] = mapped_column(CHAR(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    replaced_by_jti: Mapped[str | None] = mapped_column(CHAR(32), nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])


__all__ = ["RefreshToken"]
