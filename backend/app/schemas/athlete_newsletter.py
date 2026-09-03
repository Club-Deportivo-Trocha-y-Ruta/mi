"""Schemas Pydantic para el módulo Boletín Mensual Individual por Atleta —
bitácora de etapa (feature 038, StageLog v2; el formato legacy v1 fue
retirado, ver docs/technical-notes.md).

Contrato de API:
  - AthleteNewsletterCreate: body del POST al crear/regenerar un draft.
  - AthleteNewsletterRead: respuesta estándar (sin pdf_only_blocks — va solo en PDF).
  - AthleteNewsletterPatch: edición de la bitácora (solo coach, solo si status
    es draft o approved).
  - AthleteNewsletterBatchCreate: body del POST /clubs/{id}/monthly-newsletters/batch.
  - AthleteNewsletterBatchResult: resultado del batch.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.models.athlete_newsletter import NewsletterStatus


# Bloques opcionales que el coach puede ocultar en la bitácora v2 (feature
# 038, data-model.md §3 — `hidden_blocks`). Duplicado deliberado del literal
# usado por StageLog (app/services/training/stage_log.py, T101): esta es la
# validación de forma del PATCH, no depende de ese módulo estar disponible.
_HIDEABLE_BLOCKS: frozenset[str] = frozenset(
    {"analyst_reading", "photos", "badges", "coach_note"}
)

# Bloques narrativos v2 regenerables individualmente (feature 038, T201,
# contracts/api.md §Coach POST .../regenerate-block). Duplicado deliberado
# del mismo literal en app/services/ai/use_cases/athlete_monthly_newsletter_v2.py
# — validación de forma del request, no depende de ese módulo.
_REGENERABLE_BLOCKS: frozenset[str] = frozenset(
    {
        "stage_title",
        "summit_caption",
        "observations",
        "next_segment_text",
        "family_compass",
        "analyst_reading",
    }
)


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
    """Edición del coach sobre la bitácora (feature 038, StageLog v2).

    ``stage_overrides`` (edición por bloque de la bitácora), ``hidden_blocks``
    (bloques opcionales ocultos), ``coach_note`` (nota del entrenador,
    ≤ 60 palabras) y ``selected_race_insight_ids`` (solo reordenar — el
    router valida que sea una permutación exacta del valor ya guardado; no se
    puede usar este campo para agregar/quitar insights, eso sigue siendo
    ``attach-insights``).

    Todos los campos son opcionales — un PATCH parcial solo persiste lo
    enviado.
    """

    stage_overrides: dict[str, Any] | None = Field(
        default=None,
        description=(
            "(v2) Overrides por bloque de la bitácora: stage_title, "
            "summit_caption, observations, analyst_reading, "
            "next_segment_text, family_compass. Tipado laxo (dict) porque "
            "la forma exacta la define StageLog (app/services/training/"
            "stage_log.py, feature 038 T101)."
        ),
    )
    hidden_blocks: list[str] | None = Field(
        default=None,
        description=(
            "(v2) Subconjunto de bloques opcionales a ocultar: "
            "analyst_reading, photos, badges, coach_note."
        ),
    )
    coach_note: str | None = Field(
        default=None,
        max_length=600,
        description="(v2) Nota del entrenador, primera persona, ≤ 60 palabras.",
    )
    selected_race_insight_ids: list[int] | None = Field(
        default=None,
        description=(
            "(v2) Reordena los insights ya adjuntados al boletín. Debe ser "
            "una permutación exacta de los ids actualmente guardados — el "
            "router responde 422 si no lo es. Para agregar/quitar insights "
            "usa POST .../attach-insights."
        ),
    )

    @model_validator(mode="after")
    def _validate_coach_note_word_limit(self) -> "AthleteNewsletterPatch":
        if self.coach_note is not None:
            word_count = len(self.coach_note.split())
            if word_count > 60:
                raise ValueError(
                    f"coach_note no puede exceder 60 palabras (tiene {word_count})."
                )
        return self

    @model_validator(mode="after")
    def _validate_hidden_blocks_allowlist(self) -> "AthleteNewsletterPatch":
        if self.hidden_blocks is not None:
            invalid = sorted(set(self.hidden_blocks) - _HIDEABLE_BLOCKS)
            if invalid:
                raise ValueError(
                    f"hidden_blocks contiene bloques no ocultables: {invalid}. "
                    f"Solo se permite: {sorted(_HIDEABLE_BLOCKS)}."
                )
        return self


class RegenerateBlockRequest(BaseModel):
    """Body de ``POST .../monthly-newsletters/{id}/regenerate-block`` (v2).

    ``block`` debe ser uno de los bloques narrativos regenerables de la
    bitácora (contracts/api.md §Coach). ``instruction`` es una indicación
    libre opcional del entrenador (ej. "más corto y menciona la lluvia") que
    se agrega al prompt como contexto adicional para ese bloque.
    """

    block: Literal[
        "stage_title",
        "summit_caption",
        "observations",
        "next_segment_text",
        "family_compass",
        "analyst_reading",
    ]
    instruction: str | None = Field(default=None, max_length=300)


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


class DeliveryRow(BaseModel):
    """Estado de entrega/lectura de un boletín para una familia (feature 038).

    Poblado a partir de ``newsletter_delivery_events`` + ``parent_athletes``
    por el router (requiere sesión de DB — fuera del alcance de T102; ver
    T202/T203/T401). ``email_masked`` NUNCA expone el email completo
    (``j***@gmail.com``) — igual criterio que ``sent_to`` en el modelo, que
    tampoco se serializa nunca en esta respuesta.
    """

    parent_user_id: int | None = None
    email_masked: str
    has_account: bool
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    opened_at: datetime | None = None
    web_read_at: datetime | None = None
    bounced: bool = False

    model_config = {"from_attributes": True}


class AthleteNewsletterRead(BaseModel):
    """Respuesta de lectura de un boletín (bitácora de etapa, StageLog v2).

    NUNCA incluye pdf_only_blocks (antropometría) — esos datos van solo en el PDF.
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

    badges_earned: list[dict[str, Any]] | None = Field(
        default=None,
        description="Snapshot de insignias ganadas en el periodo.",
    )

    # ── Feature 038 (Bitácora de etapa) ──────────────────────────────────
    stage_log: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Vista coach del StageLog v2 (incluye block_states y "
            "grounding_violations). Tipado laxo (dict) — el schema "
            "estructurado vive en app/services/training/stage_log.py "
            "(feature 038 T101). NULL solo si la generación falló antes de "
            "derivar la bitácora."
        ),
    )
    stage_overrides: dict[str, Any] | None = Field(
        default=None,
        description="(v2) Overrides por bloque de la bitácora.",
    )
    hidden_blocks: list[str] = Field(
        default_factory=list,
        description="(v2) Bloques opcionales ocultos por el coach.",
    )
    coach_note: str | None = Field(
        default=None,
        description="(v2) Nota del entrenador, ya redactada (sin nombres).",
    )
    read_at: datetime | None = Field(
        default=None,
        description="(v2) Primera lectura web por un padre.",
    )
    delivery: list[DeliveryRow] = Field(
        default_factory=list,
        description=(
            "(v2) Estado de entrega/lectura por familia. Poblado por el "
            "router a partir de newsletter_delivery_events — ver DeliveryRow."
        ),
    )
    selected_race_insight_ids: list[int] = Field(
        default_factory=list,
        description=(
            "(v2) Insights de carrera adjuntados, en el orden elegido por "
            "el coach (el primero elegible es el usado en analyst_reading). "
            "Solo IDs — el estudio (AnalystPicker, T302) los usa para "
            "reordenar vía PATCH; nunca expone structured_json aquí."
        ),
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
    def from_orm_model(
        cls,
        obj: Any,
        *,
        delivery: list[DeliveryRow] | None = None,
    ) -> "AthleteNewsletterRead":
        """Construye el schema extrayendo solo email_blocks del metrics_snapshot.

        ``delivery`` es opcional: T102 solo agrega la columna de datos; su
        población real (JOIN a newsletter_delivery_events + parent_athletes,
        masking de email) requiere una sesión de DB y queda para el router
        que la consuma en el studio (T202/T203/T401).
        """
        snapshot = obj.metrics_snapshot or {}
        email_blocks = snapshot.get("email_blocks") if snapshot else None

        return cls(
            id=obj.id,
            athlete_id=obj.athlete_id,
            year=obj.year,
            month=obj.month,
            status=obj.status,
            email_blocks=email_blocks,
            badges_earned=obj.badges_earned,
            stage_log=getattr(obj, "stage_log_json", None),
            stage_overrides=getattr(obj, "stage_overrides", None),
            hidden_blocks=getattr(obj, "hidden_blocks", None) or [],
            coach_note=getattr(obj, "coach_note", None),
            read_at=getattr(obj, "read_at", None),
            delivery=delivery or [],
            selected_race_insight_ids=getattr(obj, "selected_race_insight_ids", None) or [],
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


class AttachInsightsRequest(BaseModel):
    """Body para adjuntar insights de race-analysis aprobados a un boletín.

    El coach selecciona N insights desde el tab Análisis IA y los envía aquí.
    El endpoint hace upsert: si ya existe un newsletter para (athlete_id, year, month)
    se hace append+dedupe; si no existe, se crea con status=pending (draft).

    Privacy: solo accesible a coach/admin del club. Parent → 403 en el endpoint.
    """

    insight_ids: list[int] = Field(
        min_length=1,
        max_length=20,
        description="IDs de AthleteAIInsight a adjuntar (activos y del atleta).",
    )
    year: int | None = Field(
        default=None,
        ge=2020,
        le=2100,
        description="Año del boletín. Default: año actual en zona Colombia.",
    )
    month: int | None = Field(
        default=None,
        ge=1,
        le=12,
        description="Mes del boletín (1=enero). Default: mes actual en zona Colombia.",
    )


class AttachInsightsResponse(BaseModel):
    """Respuesta del endpoint attach-insights.

    Privacy: no expone datos del atleta ni de los insights más allá de sus IDs.
    """

    newsletter_id: int
    athlete_id: int
    year: int
    month: int
    status: NewsletterStatus
    selected_race_insight_ids: list[int]
    created: bool = Field(
        description="True si el newsletter se creó en esta operación; False si ya existía.",
    )

    model_config = {"from_attributes": True}


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


class NewsletterStatusSummaryItem(BaseModel):
    """Estado del boletín mensual de un atleta para un periodo dado.

    Una fila por atleta en el resumen de estado a nivel de club/roster.
    status='none' si aún no existe newsletter para (athlete_id, year, month).
    """

    athlete_id: int
    newsletter_id: int | None = None
    status: Literal["none", "draft", "sent"]
    generated_at: datetime | None = None
    sent_at: datetime | None = None


class NewsletterStatusSummary(BaseModel):
    """Resumen de estado de boletines mensuales de todos los atletas de un club."""

    year: int
    month: int
    items: list[NewsletterStatusSummaryItem]
