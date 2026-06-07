from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class EmailChangeRequest(Base):
    """Solicitud de cambio de correo del perfil (specs/004-user-profile).

    Sigue el patrón de ``PasswordResetToken`` (verify-new-email-before-apply,
    alineado con OWASP "Changing a User's Registered Email Address"):

    - El token en claro nunca se persiste: solo su hash SHA-256 (``token_hash``).
      El token viaja únicamente en el enlace enviado a la **nueva** dirección.
    - ``new_email`` es la dirección *propuesta*; el correo de la cuenta NO cambia
      hasta que la solicitud se confirma desde el nuevo buzón.
    - Válida si ``used_at IS NULL`` y ``expires_at > now``. Crear o consumir una
      solicitud invalida (``used_at=now``) las demás vigentes del mismo usuario.

    Privacidad (Ley 1581): la fila no contiene datos de menores; ``new_email`` es
    la propia dirección (adulta) del titular de la cuenta. Nunca se loguea con PII.
    """

    __tablename__ = "email_change_requests"
    __table_args__ = (
        Index("ix_email_change_requests_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Dirección propuesta (normalizada en minúsculas). No es la activa todavía.
    new_email: Mapped[str] = mapped_column(String(255))
    # SHA-256 hex (64 chars) del token en claro. Único para lookup indexado.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    # IP de quien solicitó (forense de abuso). Nunca se loguea junto a PII.
    requested_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Usuario dueño de la cuenta
    user: Mapped[User] = relationship(
        "User", foreign_keys="[EmailChangeRequest.user_id]"
    )
