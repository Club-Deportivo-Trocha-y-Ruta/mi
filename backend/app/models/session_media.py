from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.training_session import TrainingSession
    from app.models.user import User


class MediaType(str, enum.Enum):
    PHOTO = "photo"
    VIDEO = "video"


class SessionMedia(Base):
    """Fotos y videos asociados a una sesión de entrenamiento.

    Storage externo (Hostinger via SFTP). `storage_url` apunta al asset
    público; `storage_path` se conserva para el borrado SFTP posterior.
    """

    __tablename__ = "session_media"
    __table_args__ = (
        Index("idx_session_media_session", "session_id"),
        Index("idx_session_media_uploaded_at", "uploaded_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False
    )
    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    storage_url: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    filename_original: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    caption: Mapped[str | None] = mapped_column(String(280), nullable=True)
    consent_ack: Mapped[bool] = mapped_column(default=False, nullable=False)
    uploaded_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    session: Mapped["TrainingSession"] = relationship(
        "TrainingSession",
        back_populates="media",
        foreign_keys="[SessionMedia.session_id]",
    )
    uploaded_by: Mapped["User"] = relationship(
        "User",
        foreign_keys="[SessionMedia.uploaded_by_user_id]",
    )
    athletes: Mapped[list["Athlete"]] = relationship(
        "Athlete",
        secondary="session_media_athlete",
        lazy="selectin",
    )


class SessionMediaAthlete(Base):
    """Tabla puente media↔atleta. Sirve para filtrar la visibilidad de padres.

    Cada media puede etiquetar a varios atletas; cada atleta puede aparecer
    en varias media. Un padre verá una media sólo si la intersección con sus
    propios hijos es no vacía.
    """

    __tablename__ = "session_media_athlete"
    __table_args__ = (
        # Búsquedas "todas las media de un atleta" (filtros de privacidad
        # para padres). El PK compuesto empieza por media_id, así que un
        # índice secundario solo por athlete_id acelera la query inversa.
        Index("ix_session_media_athlete_athlete", "athlete_id"),
    )

    media_id: Mapped[int] = mapped_column(
        ForeignKey("session_media.id", ondelete="CASCADE"),
        primary_key=True,
    )
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tagged_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
