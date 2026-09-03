from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    CHAR,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.user import User


class NewsletterStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    sent = "sent"
    failed = "failed"
    # PR5 (D3): boletín ya enviado que quedó desactualizado por una corrección
    # de resultados (re-ingesta). NO se reenvía automáticamente — solo se marca.
    outdated = "outdated"


class AthleteMonthlyNewsletter(Base):
    """Boletín mensual individual por atleta.

    Workflow: draft → approved → sent (o failed en cualquier punto).
    El coach genera el draft (builder + IA), revisa y opcionalmente edita
    la narrativa, aprueba, y finalmente dispara el envío a los padres.

    Privacidad:
      - metrics_snapshot separa email_blocks y pdf_only_blocks.
        Antropometría SOLO en pdf_only_blocks — el builder garantiza esto.
      - sent_to almacena emails de padres; NUNCA se loguea.
      - ai_narrative pasa guardrails _redact_names antes de persistir.
    """

    __tablename__ = "athlete_monthly_newsletters"
    __table_args__ = (
        UniqueConstraint(
            "athlete_id",
            "year",
            "month",
            name="uq_athlete_newsletter_period",
        ),
        Index("idx_newsletter_status_period", "status", "year", "month"),
        Index("idx_newsletter_athlete_period", "athlete_id", "year", "month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    month: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    status: Mapped[NewsletterStatus] = mapped_column(
        Enum(NewsletterStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=NewsletterStatus.draft,
        server_default="draft",
    )

    # Snapshot de métricas separada en email_blocks y pdf_only_blocks.
    # email_blocks: asistencia, carga técnica, resultados carreras, narrativa IA,
    #               calendario, apoyo desde casa, fotos (links), badges.
    # pdf_only_blocks: todo lo anterior + antropometría completa + gráficos SVG.
    metrics_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Narrativa IA estructurada (StageNarrative — ver
    # app/services/ai/use_cases/athlete_monthly_newsletter_v2.py): stage_title,
    # summit_caption, observations, next_segment_text, family_compass,
    # analyst_reading, model, prompt_version, confidence.
    ai_narrative: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Snapshot inmutable de las insignias ganadas en el periodo
    badges_earned: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Storage PDF
    pdf_storage_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pdf_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pdf_sha256: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)

    # Audit trail (sin FK estricta a nivel DB para no bloquear si se desactiva un usuario)
    generated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Lista de emails enviados — PII, NUNCA loguear. Solo almacenar.
    sent_to: Mapped[list | None] = mapped_column(JSON, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # IDs ordenados de AthleteAIInsight seleccionados manualmente por el coach
    # para incluir en el boletín. La posición en la lista define el orden de
    # renderizado. Dedupe garantizado por el endpoint attach-insights.
    # RBAC: solo accesible a coach/admin del club — nunca a padres.
    selected_race_insight_ids: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        default=None,
        comment="IDs ordenados de AthleteAIInsight seleccionados manualmente por el coach",
    )

    # ── Feature 038 (Bitácora de etapa) ──────────────────────────────────
    # StageLog.model_dump() (vista coach: incluye block_states y
    # grounding_violations). NULL solo si la generación falló antes de
    # derivar la bitácora. Se re-deriva en cada PATCH que toque
    # stage_overrides/hidden_blocks/coach_note.
    stage_log_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Edición manual del coach por bloque narrativo v2: {block: value} para
    # stage_title, summit_caption, observations, analyst_reading,
    # next_segment_text, family_compass.
    stage_overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Subconjunto de bloques opcionales ocultos por el coach: analyst_reading,
    # photos, badges, coach_note.
    hidden_blocks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # "Nota del entrenador" — texto libre en primera persona, ≤ 60 palabras.
    # Pasa por _redact_names (nombres prohibidos del club) antes de persistir
    # — mismo guard que el resto del texto libre del coach en este módulo.
    coach_note: Mapped[str | None] = mapped_column(String(600), nullable=True)
    # Primera lectura web de un padre (POST .../newsletters/{id}/read,
    # idempotente — solo la primera llamada la puebla).
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    read_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relaciones
    athlete: Mapped["Athlete"] = relationship(
        "Athlete",
        back_populates="monthly_newsletters",
        foreign_keys="[AthleteMonthlyNewsletter.athlete_id]",
    )
    generated_by: Mapped["User | None"] = relationship(
        "User",
        foreign_keys="[AthleteMonthlyNewsletter.generated_by_user_id]",
    )
    approved_by: Mapped["User | None"] = relationship(
        "User",
        foreign_keys="[AthleteMonthlyNewsletter.approved_by_user_id]",
    )
    read_by: Mapped["User | None"] = relationship(
        "User",
        foreign_keys="[AthleteMonthlyNewsletter.read_by_user_id]",
    )
