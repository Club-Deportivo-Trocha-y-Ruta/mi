"""Schemas Pydantic para el módulo Boletín Mensual Individual por Atleta (Fase 1.8).

Contrato de API:
  - AthleteNewsletterCreate: body del POST al crear/regenerar un draft.
  - AthleteNewsletterRead: respuesta estándar (sin pdf_only_blocks — va solo en PDF).
  - AthleteNewsletterPatch: edición de narrativa (solo coach, solo si status=draft).
  - AthleteNewsletterBatchCreate: body del POST /clubs/{id}/monthly-newsletters/batch.
  - AthleteNewsletterBatchResult: resultado del batch.
  - NarrativeOverride: estructura de overrides de narrativa IA.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.athlete_newsletter import NewsletterStatus


# ---------------------------------------------------------------------------
# Submodelos de narrativa
# ---------------------------------------------------------------------------


class NarrativeOverride(BaseModel):
    """Edición manual del coach sobre la narrativa IA.

    Solo se permiten campos de texto libre. El coach puede anular uno, dos
    o los tres campos. Los campos no enviados conservan el valor IA original.
    El override se aplica en capa de presentación (builder/PDF); el ai_narrative
    original persiste intacto para auditoría.
    """

    strengths: str | None = Field(
        default=None,
        max_length=500,
        description="Fortalezas observadas — override manual del coach.",
    )
    area_to_develop: str | None = Field(
        default=None,
        max_length=500,
        description="Área a desarrollar — override manual del coach.",
    )
    milestone: str | None = Field(
        default=None,
        max_length=500,
        description="Hito del mes — override manual del coach.",
    )


class AiNarrativeOut(BaseModel):
    """Narrativa IA tal como se persistió (post-guardrails, sin PII)."""

    strengths: str
    area_to_develop: str
    milestone: str
    model: str
    prompt_version: str
    confidence: str  # 'low' | 'medium' | 'high'


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class AthleteNewsletterCreate(BaseModel):
    """Body para crear o regenerar un boletín mensual de un atleta.

    - Si ya existe newsletter para (athlete_id, year, month) con status=draft,
      se regenera (sobrescribe métricas y narrativa IA).
    - Si existe con status=approved o sent, se rechaza con 409 a menos que
      force=true.
    """

    year: int = Field(..., ge=2020, le=2100, description="Año del periodo.")
    month: int = Field(..., ge=1, le=12, description="Mes del periodo (1=enero).")
    force: bool = Field(
        default=False,
        description=(
            "Permite generar para el mes actual (normalmente bloqueado) "
            "o regenerar uno ya aprobado/enviado."
        ),
    )

    @model_validator(mode="after")
    def month_must_be_valid(self) -> "AthleteNewsletterCreate":
        if not (1 <= self.month <= 12):
            raise ValueError("El mes debe estar entre 1 y 12.")
        return self


class AthleteNewsletterPatch(BaseModel):
    """Edición de narrativa del coach. Solo se acepta si status=draft."""

    coach_narrative_overrides: NarrativeOverride = Field(
        ...,
        description="Campos de narrativa a sobrescribir (parcial o total).",
    )


class AthleteNewsletterBatchCreate(BaseModel):
    """Body para crear drafts para todos los atletas activos del periodo.

    Idempotente: si ya existe newsletter para (athlete_id, year, month) con
    cualquier status, se omite ese atleta (no se sobrescribe). Para regenerar
    uno concreto, usar el endpoint individual con force=true.
    """

    year: int = Field(..., ge=2020, le=2100)
    month: int = Field(..., ge=1, le=12)
    force: bool = Field(
        default=False,
        description="Permite batch para el mes actual.",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class AthleteNewsletterRead(BaseModel):
    """Respuesta de lectura de un boletín.

    NUNCA incluye pdf_only_blocks (antropometría) — esos datos van solo en el PDF.
    ai_narrative se incluye completa (el coach la ve para revisar).
    sent_to NO se serializa: es PII y solo se almacena en DB.
    """

    id: int
    athlete_id: int
    year: int
    month: int
    status: NewsletterStatus

    # Solo email_blocks del snapshot (pdf_only_blocks se omite intencionalmente)
    email_blocks: dict[str, Any] | None = Field(
        default=None,
        description="Bloques de contenido para el email (sin antropometría).",
    )

    ai_narrative: AiNarrativeOut | None = Field(
        default=None,
        description="Narrativa IA post-guardrails.",
    )
    coach_narrative_overrides: NarrativeOverride | None = Field(
        default=None,
        description="Overrides manuales del coach.",
    )
    badges_earned: list[dict[str, Any]] | None = Field(
        default=None,
        description="Snapshot de insignias ganadas en el periodo.",
    )

    # pdf_storage_url se omite intencionalmente del contrato API: el PDF
    # se descarga exclusivamente vía el endpoint autenticado /pdf, nunca
    # exponiendo la ruta de storage que sería predecible y accesible
    # sin autenticación si el bucket fuese público.
    has_pdf: bool = Field(
        default=False,
        description="Indicador de existencia de PDF generado. Descargar vía endpoint /pdf.",
    )
    pdf_generated_at: datetime | None = None
    pdf_sha256: str | None = None

    generated_by_user_id: int | None = None
    approved_by_user_id: int | None = None
    approved_at: datetime | None = None
    sent_at: datetime | None = None

    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, obj: Any) -> "AthleteNewsletterRead":
        """Construye el schema extrayendo solo email_blocks del metrics_snapshot."""
        snapshot = obj.metrics_snapshot or {}
        email_blocks = snapshot.get("email_blocks") if snapshot else None

        ai_raw = obj.ai_narrative
        ai_out: AiNarrativeOut | None = None
        if ai_raw:
            try:
                ai_out = AiNarrativeOut(**ai_raw)
            except Exception:
                pass

        overrides_raw = obj.coach_narrative_overrides
        overrides_out: NarrativeOverride | None = None
        if overrides_raw:
            try:
                overrides_out = NarrativeOverride(**overrides_raw)
            except Exception:
                pass

        return cls(
            id=obj.id,
            athlete_id=obj.athlete_id,
            year=obj.year,
            month=obj.month,
            status=obj.status,
            email_blocks=email_blocks,
            ai_narrative=ai_out,
            coach_narrative_overrides=overrides_out,
            badges_earned=obj.badges_earned,
            has_pdf=bool(obj.pdf_storage_url or obj.pdf_sha256),
            pdf_generated_at=obj.pdf_generated_at,
            pdf_sha256=obj.pdf_sha256,
            generated_by_user_id=obj.generated_by_user_id,
            approved_by_user_id=obj.approved_by_user_id,
            approved_at=obj.approved_at,
            sent_at=obj.sent_at,
            error_message=obj.error_message,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class AthleteNewsletterBatchResult(BaseModel):
    """Resultado del batch de creación de boletines."""

    period_year: int
    period_month: int
    total_athletes: int
    created: int
    skipped: int
    failed: int
    newsletter_ids: list[int] = Field(
        default_factory=list,
        description="IDs de los boletines creados en esta operación.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Mensajes de error (sin PII) por atletas que fallaron.",
    )
