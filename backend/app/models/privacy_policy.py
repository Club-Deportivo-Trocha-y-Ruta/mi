from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class PrivacyPolicy(Base):
    """Versiones inmutables de la política de privacidad (Ley 1581, Art. 26).

    Cada fila es append-only: no se modifican filas existentes. Cuando la
    política cambia, se inserta una nueva fila y se depreca la anterior.
    """

    __tablename__ = "privacy_policies"
    __table_args__ = (
        Index("ix_privacy_policies_version", "version", unique=True),
        Index("ix_privacy_policies_effective_date", "effective_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(20), unique=True)
    effective_date: Mapped[date] = mapped_column(Date)
    deprecated_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    # Texto completo entregable al titular (conservado según Ley 1581 Art. 26)
    content_html: Mapped[str] = mapped_column(LONGTEXT)
    # SHA-256 hex del content_html para verificar integridad
    content_hash: Mapped[str] = mapped_column(String(64))
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Quién creó la versión (NULL para versiones migradas)
    creator: Mapped[User | None] = relationship(
        "User",
        foreign_keys="[PrivacyPolicy.created_by]",
    )
