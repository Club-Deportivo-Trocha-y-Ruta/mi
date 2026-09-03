"""Modelo SQLAlchemy para ``newsletter_delivery_events`` (feature 038, T102).

Una fila por evento de entrega/lectura de un boletín mensual (bitácora):

- ``sent``      — el coach disparó el envío (``newsletter_dispatcher``); una
                  fila por destinatario, con ``provider_message_id`` cuando el
                  proveedor lo devuelve (Resend; NULL en SMTP/MailHog).
- ``delivered`` / ``opened`` / ``clicked`` / ``bounced`` — eventos del webhook
  de Resend (feature 038 P3, T401), keyed por ``provider_message_id``.
- ``web_read``  — el padre abrió la bitácora en el portal
  (``POST /api/parents/.../newsletters/{id}/read``, idempotente).

Privacidad (Ley 1581, CLAUDE.md): esta tabla es append-only y **nunca**
almacena emails, nombres, IPs ni user-agents — solo ids (newsletter, padre),
timestamp y tipo de evento. El panel de entrega del studio resuelve el email
enmascarado por JOIN a ``users`` en tiempo de lectura, no lo persiste aquí.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete_newsletter import AthleteMonthlyNewsletter
    from app.models.user import User


class DeliveryEventType(str, enum.Enum):
    sent = "sent"
    delivered = "delivered"
    opened = "opened"
    clicked = "clicked"
    bounced = "bounced"
    web_read = "web_read"


class NewsletterDeliveryEvent(Base):
    """Evento append-only de entrega/lectura de un boletín mensual."""

    __tablename__ = "newsletter_delivery_events"
    __table_args__ = (
        Index(
            "ix_newsletter_delivery_events_newsletter_event_type",
            "newsletter_id",
            "event_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    newsletter_id: Mapped[int] = mapped_column(
        ForeignKey("athlete_monthly_newsletters.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[DeliveryEventType] = mapped_column(
        Enum(
            DeliveryEventType,
            name="newsletterdeliveryeventtype",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    # svix/Resend id del mensaje entregado — llave para correlacionar eventos
    # del webhook (delivered/opened/clicked/bounced) con el envío original.
    # NULL en filas 'sent' vía SMTP (MailHog no lo provee).
    provider_message_id: Mapped[str | None] = mapped_column(
        String(length=128), nullable=True, index=True
    )
    # svix-id del evento del webhook — UNIQUE, llave de idempotencia para que
    # un replay del webhook nunca duplique la fila (T401).
    provider_event_id: Mapped[str | None] = mapped_column(
        String(length=128), nullable=True, unique=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relaciones (solo lectura — la tabla es append-only)
    newsletter: Mapped["AthleteMonthlyNewsletter"] = relationship(
        "AthleteMonthlyNewsletter",
        foreign_keys="[NewsletterDeliveryEvent.newsletter_id]",
    )
    parent_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys="[NewsletterDeliveryEvent.parent_user_id]",
    )
