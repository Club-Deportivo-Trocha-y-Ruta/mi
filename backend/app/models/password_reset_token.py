from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class PasswordResetToken(Base):
    """Token de restablecimiento de contraseña (enlace por correo, un solo uso).

    El token en claro nunca se persiste: solo se guarda su hash SHA-256
    (``token_hash``), siguiendo la recomendación de OWASP de almacenar los
    tokens de reset hasheados. El token en claro viaja únicamente dentro del
    enlace enviado por email. La búsqueda hashea el token entrante y compara
    contra el índice único.

    Un token es válido si ``used_at IS NULL`` y ``expires_at > now``. Tanto al
    crear un nuevo token como al consumir uno se invalidan (``used_at=now``) los
    demás tokens vigentes del mismo usuario.

    Privacidad (Ley 1581): la fila no contiene datos personales (ni correo, ni
    nombre, ni rol). Solo referencia al ``user_id``.
    """

    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("ix_password_reset_tokens_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # SHA-256 hex (64 chars) del token en claro. Único para lookup indexado.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    # IP de quien solicitó (forense de abuso). Nunca se loguea junto a PII.
    requested_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Usuario dueño de la cuenta a restablecer
    user: Mapped[User] = relationship("User", foreign_keys="[PasswordResetToken.user_id]")
