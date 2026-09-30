from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.models.anthropometry import MaturationStatus
from app.schemas.body_composition import SkinfoldSetOut

# Feature 048 (FR-016, data-model.md): rangos duros de captura, idénticos en el
# backend y en el Zod del frontend (`anthropometryCapture.schema.ts`).
WEIGHT_KG_RANGE: tuple[int, int] = (20, 150)
STANDING_HEIGHT_CM_RANGE: tuple[int, int] = (100, 220)
SITTING_HEIGHT_CM_RANGE: tuple[int, int] = (50, 120)
ARM_SPAN_CM_RANGE: tuple[int, int] = (100, 220)
# Talla sentado (neta) / talla de pie fuera de este rango es físicamente
# imposible → dato mal digitado o banco sin restar (research R5).
SITTING_RATIO_HARD_RANGE: tuple[float, float] = (0.40, 0.65)

#: Código estable del 422 por proporción imposible (aparece como `type` en el
#: cuerpo de error; el frontend es dueño del texto en español).
SITTING_RATIO_IMPOSSIBLE = "sitting_ratio_impossible"

PlausibilityCode = Literal[
    "height_decreased",
    "height_velocity_implausible",
    "weight_change_large",
    "sitting_ratio_atypical",
    "arm_span_ratio_atypical",
]
PlausibilityMeasure = Literal["weight", "standing_height", "sitting_height", "arm_span"]


class _AnthropometryMeasuresIn(BaseModel):
    """Campos editables de una medición + validación compartida (feature 048).

    Los mensajes nunca interpolan el valor recibido (privacidad de menores:
    el manejador global de 422 además descarta `input`/`ctx`).
    """

    evaluation_date: date
    weight_kg: Decimal = Field(ge=WEIGHT_KG_RANGE[0], le=WEIGHT_KG_RANGE[1])
    standing_height_cm: Decimal = Field(
        ge=STANDING_HEIGHT_CM_RANGE[0], le=STANDING_HEIGHT_CM_RANGE[1]
    )
    arm_span_cm: Decimal | None = Field(
        default=None, ge=ARM_SPAN_CM_RANGE[0], le=ARM_SPAN_CM_RANGE[1]
    )
    sitting_height_cm: Decimal = Field(
        ge=SITTING_HEIGHT_CM_RANGE[0], le=SITTING_HEIGHT_CM_RANGE[1]
    )
    notes: str | None = Field(default=None, max_length=2000)  # igual que el Zod del frontend (privacy-audit P-1)

    @field_validator("evaluation_date")
    @classmethod
    def evaluation_date_must_not_be_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("La fecha de evaluación no puede ser futura")
        return v

    @model_validator(mode="after")
    def sitting_ratio_must_be_possible(self) -> "_AnthropometryMeasuresIn":
        # Solo corre si los campos individuales ya pasaron sus rangos.
        ratio = self.sitting_height_cm / self.standing_height_cm
        low, high = SITTING_RATIO_HARD_RANGE
        if not (Decimal(str(low)) <= ratio <= Decimal(str(high))):
            raise PydanticCustomError(
                SITTING_RATIO_IMPOSSIBLE,
                "Sitting height to standing height ratio is physically impossible",
            )
        return self


class AnthropometryCreate(_AnthropometryMeasuresIn):
    """Cuerpo de `POST /api/athletes/{id}/anthropometry`."""


class AnthropometryUpdate(_AnthropometryMeasuresIn):
    """Cuerpo de `PUT /api/athletes/{id}/anthropometry/{record_id}` (feature 048).

    Reemplazo completo de los campos editables: mismos campos y validación
    que el POST; `arm_span_cm` y `notes` son opcionales.
    """


class PlausibilityCheckIn(_AnthropometryMeasuresIn):
    """Cuerpo del dry-run `POST .../anthropometry/plausibility` (feature 048).

    `record_id` se envía al editar para excluir ese registro del "anterior".
    """

    record_id: int | None = None


class PlausibilityWarningOut(BaseModel):
    code: PlausibilityCode
    measure: PlausibilityMeasure


class PlausibilityCheckOut(BaseModel):
    warnings: list[PlausibilityWarningOut]
    # None en la primera evaluación del deportista.
    previous_evaluation_date: date | None = None


class RosterRowOut(BaseModel):
    """Fila de `GET /api/anthropometry/roster` (feature 048, research R9).

    Solo para coach/admin (jornada de medición); nunca se registra en logs.
    """

    athlete_id: int
    full_name: str
    category: str | None = None
    sex: str
    birth_date: date
    last_evaluation_date: date | None = None
    has_record_on_date: bool
    skinfolds_eligible: bool


class GrowthPercentiles(BaseModel):
    bmi: float | None = None
    height_z_score: float | None = None
    height_percentile: float | None = None
    bmi_z_score: float | None = None
    bmi_percentile: float | None = None
    weight_z_score: float | None = None
    weight_percentile: float | None = None
    nutritional_status_height: str | None = None
    nutritional_status_bmi: str | None = None


class MorphologyMetrics(BaseModel):
    ape_index: float
    arm_span_height_delta_cm: float
    posture_screening_flag: bool
    posture_screening_message: str | None = None
    bike_fit_category: str
    bike_fit_guidance: str
    ape_index_advisory: str | None = None


class AnthropometryOut(BaseModel):
    id: int
    athlete_id: int
    evaluation_date: date
    weight_kg: float
    standing_height_cm: float
    arm_span_cm: float | None
    sitting_height_cm: float
    leg_length_cm: float
    leg_sitting_ratio: float
    maturity_offset: float
    age_at_phv: float
    maturation_status: MaturationStatus
    training_implications: str | None
    evaluated_by: int
    created_at: datetime
    notes: str | None
    # Campos individuales de percentiles (nullable — compatibilidad backward)
    height_z_score: float | None = None
    height_percentile: float | None = None
    bmi: float | None = None
    bmi_z_score: float | None = None
    bmi_percentile: float | None = None
    weight_z_score: float | None = None
    weight_percentile: float | None = None
    nutritional_status: str | None = None
    # Referencia poblacional usada para los campos anteriores (feature 040).
    # None = fila legacy aún no recalculada ("referencia anterior" en la UI).
    growth_source: str | None = None
    # Objeto compuesto (se construye desde el router; no proviene del ORM directamente)
    growth_percentiles: GrowthPercentiles | None = None
    morphology: MorphologyMetrics | None = None
    # Feature 046 — None for parents (projection nulls it like `notes`/`morphology`).
    skinfolds: SkinfoldSetOut | None = None
    # Feature 048 — solo coach/admin. Cuando quedan en None (padres) las claves
    # se OMITEN del JSON (no se envían como null); el resto de campos None se
    # siguen serializando como hoy. `exclude_if` requiere pydantic >= 2.11.
    can_modify: bool | None = Field(default=None, exclude_if=lambda v: v is None)
    plausibility_flags: list[str] | None = Field(
        default=None, exclude_if=lambda v: v is None
    )

    model_config = {"from_attributes": True}

    @field_validator("skinfolds", mode="before")
    @classmethod
    def _skip_orm_skinfolds(cls, v: Any) -> Any:
        """``model_validate(record, from_attributes=True)`` would otherwise try
        to coerce `record.skinfolds` (the flat-column ORM relationship) into
        the nested `SkinfoldSetOut` shape and fail — same reason
        `growth_percentiles`/`morphology` are never read straight off the ORM.
        The router always sets this field explicitly afterwards via
        `routers/body_composition.py::skinfold_set_out`.
        """
        if v is None or isinstance(v, SkinfoldSetOut) or isinstance(v, dict):
            return v
        return None
