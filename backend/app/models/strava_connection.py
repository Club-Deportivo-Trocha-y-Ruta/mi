"""Modelo SQLAlchemy para ``strava_connections`` (feature 025).

Una fila por autorización atleta↔cuenta-Strava. Relación 1:1 con ``athletes``
(reconectar actualiza la misma fila, no inserta una nueva) y 1:1 con la cuenta
de Strava (``strava_athlete_id`` único — enlazar la misma cuenta a dos
atletas queda bloqueado por la constraint, ver data-model.md §1).

Los tokens (``access_token_enc``/``refresh_token_enc``) se guardan cifrados
con Fernet (``services/strava/token_store.py``, feature 025 T004) — nunca en
texto plano, nunca en logs.
"""
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
)
from sqlalchemy.dialects.mysql import VARBINARY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.parental_consent import ParentalConsent
    from app.models.strava_activity import StravaActivity
    from app.models.user import User


class StravaConnectionStatus(str, enum.Enum):
    """Estado del vínculo con Strava (data-model.md §1 — transiciones)."""

    active = "active"
    disconnected = "disconnected"
    broken = "broken"


class StravaConnection(Base):
    """Autorización OAuth de un atleta con su cuenta de Strava."""

    __tablename__ = "strava_connections"
    __table_args__ = (
        Index("ix_strava_connections_athlete_id", "athlete_id", unique=True),
        Index(
            "ix_strava_connections_strava_athlete_id",
            "strava_athlete_id",
            unique=True,
        ),
        Index("ix_strava_connections_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 1:1 con el atleta — reconectar actualiza esta misma fila.
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False
    )

    # Identificador de Strava (``owner_id`` del webhook). Único: bloquea
    # enlazar la misma cuenta de Strava a dos atletas (primer bind gana).
    strava_athlete_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    status: Mapped[StravaConnectionStatus] = mapped_column(
        Enum(
            StravaConnectionStatus,
            name="stravaconnectionstatus",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=StravaConnectionStatus.active,
    )

    # Tokens cifrados con Fernet (nunca texto plano — ver token_store.py).
    access_token_enc: Mapped[bytes] = mapped_column(VARBINARY(512), nullable=False)
    refresh_token_enc: Mapped[bytes] = mapped_column(VARBINARY(512), nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Scope efectivo otorgado (p. ej. "activity:read_all"); detecta downgrades.
    scope_granted: Mapped[str] = mapped_column(String(100), nullable=False)

    # Quién ejecutó el flujo de conexión — junto con ``connected_at`` es el
    # rastro de auditoría del consentimiento-por-acción: autorizar el OAuth de
    # Strava ES el consentimiento afirmativo (FR-001).
    authorized_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Legado: FK opcional a una fila de ``parental_consents``. Ya NO se exige
    # ni se puebla en el flujo de conexión (el consentimiento es la propia
    # autorización OAuth). Nullable para conexiones sin fila de consentimiento.
    consent_id: Mapped[int | None] = mapped_column(
        ForeignKey("parental_consents.id", ondelete="RESTRICT"), nullable=True
    )

    connected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    disconnected_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    # Watermark de reconciliación (parámetro ``after=`` menos margen de seguridad).
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Última falla legible por máquina (sin PII) — p. ej. "refresh_401".
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # --- Relaciones --------------------------------------------------------
    athlete: Mapped["Athlete"] = relationship(
        "Athlete", foreign_keys="[StravaConnection.athlete_id]"
    )
    authorized_by: Mapped["User"] = relationship(
        "User", foreign_keys="[StravaConnection.authorized_by_user_id]"
    )
    consent: Mapped["ParentalConsent | None"] = relationship(
        "ParentalConsent", foreign_keys="[StravaConnection.consent_id]"
    )
    activities: Mapped[list["StravaActivity"]] = relationship(
        "StravaActivity",
        back_populates="connection",
        foreign_keys="[StravaActivity.connection_id]",
    )
