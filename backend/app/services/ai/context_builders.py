"""Builders de contexto para los prompts.

Función pura: recibe instancias de SQLAlchemy y devuelve un dict con
**allowlist explícita** de claves seguras. Nada que pueda identificar al
menor sale de aquí: ni nombre, ni apellido, ni fecha de nacimiento exacta,
ni email, ni id.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from app.services.category import compute_age_decimal, get_category

if TYPE_CHECKING:
    from app.models.anthropometry import AnthropometricRecord
    from app.models.athlete import Athlete


# Umbrales para distinguir señal de ruido en deltas (Mirwald, error de medición).
# Por debajo de estos valores el cambio es indistinguible del error instrumental.
DELTA_HEIGHT_SIGNIFICANT_CM = 0.7
DELTA_WEIGHT_SIGNIFICANT_KG = 1.5
# Mínimo de semanas entre mediciones para calcular velocidad de crecimiento confiable.
MIN_WEEKS_FOR_VELOCITY = 8


# Claves permitidas en el contexto que se entrega al LLM.
# Cualquier clave fuera de esta lista es un bug de privacidad.
ATHLETE_CONTEXT_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "age_decimal",
        "age_group",          # "10-12" | "13-15" | "16+"
        "sex",                # "M" | "F"
        "category",           # categoría FCC
        "phv_offset",
        "age_at_phv",
        "maturation_status",  # "Pre-PHV" | "Circa-PHV" | "Post-PHV"
        "height_z_score",
        "weight_z_score",
        "nutritional_status",
        "evaluation_age_decimal",
        "trend",              # dict con deltas de últimas mediciones
        "training_implications",
        "arm_span_cm",
        # Análisis particular por medición:
        "delta_height_cm",
        "delta_weight_kg",
        "delta_height_significant",
        "delta_weight_significant",
        "growth_velocity_cm_per_year",
        "weeks_since_prev_measurement",
        "num_previous_measurements",
        "crossed_phv_phase",
        "prev_maturation_status",
    }
)


@dataclass(frozen=True)
class TrendPoint:
    """Delta entre dos mediciones consecutivas (sin fechas exactas)."""

    weeks_ago: int
    delta_height_cm: float
    delta_weight_kg: float


def _to_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _age_group(age_decimal: float) -> str:
    if age_decimal < 13:
        return "10-12"
    if age_decimal < 16:
        return "13-15"
    return "16+"


def _build_trend(records: list["AnthropometricRecord"]) -> list[dict] | None:
    """Tendencia derivada de las últimas 3 mediciones (más reciente primero).

    Devuelve solo deltas y semanas relativas; nunca fechas absolutas.
    """
    if len(records) < 2:
        return None
    sorted_records = sorted(records, key=lambda r: r.evaluation_date, reverse=True)
    selected = sorted_records[:3]
    out: list[dict] = []
    for current, previous in zip(selected, selected[1:]):
        weeks = max(
            int((current.evaluation_date - previous.evaluation_date).days / 7), 0
        )
        out.append(
            {
                "weeks_ago": weeks,
                "delta_height_cm": round(
                    float(current.standing_height_cm - previous.standing_height_cm), 1
                ),
                "delta_weight_kg": round(
                    float(current.weight_kg - previous.weight_kg), 1
                ),
            }
        )
    return out


def _maturation_value(record: "AnthropometricRecord") -> str:
    status = record.maturation_status
    return status.value if hasattr(status, "value") else str(status)


class AthleteAIContextBuilder:
    """Construye el contexto seguro para alimentar prompts.

    No depende de la sesión DB: recibe instancias ya cargadas. Es una función
    pura, fácil de testear, y la **única** vía aprobada por la que datos del
    atleta llegan a un LLM.
    """

    def build(
        self,
        athlete: "Athlete",
        latest_record: "AnthropometricRecord | None",
        history: list["AnthropometricRecord"] | None = None,
        *,
        reference_date: date | None = None,
    ) -> dict:
        ref = reference_date or date.today()
        age_decimal = compute_age_decimal(athlete.birth_date, ref)
        ctx: dict = {
            "age_decimal": round(age_decimal, 1),
            "age_group": _age_group(age_decimal),
            "sex": athlete.sex.value,
            "category": get_category(athlete.birth_date.year, athlete.sex.value),
        }

        if latest_record is not None:
            ctx.update(
                {
                    "phv_offset": _to_float(latest_record.maturity_offset),
                    "age_at_phv": _to_float(latest_record.age_at_phv),
                    "maturation_status": _maturation_value(latest_record),
                    "evaluation_age_decimal": round(
                        compute_age_decimal(
                            athlete.birth_date, latest_record.evaluation_date
                        ),
                        1,
                    ),
                    "training_implications": latest_record.training_implications,
                }
            )
            if latest_record.height_z_score is not None:
                ctx["height_z_score"] = _to_float(latest_record.height_z_score)
            if latest_record.weight_z_score is not None:
                ctx["weight_z_score"] = _to_float(latest_record.weight_z_score)
            if latest_record.nutritional_status is not None:
                ns = latest_record.nutritional_status
                ctx["nutritional_status"] = (
                    ns.value if hasattr(ns, "value") else str(ns)
                )

        if history:
            trend = _build_trend(history)
            if trend:
                ctx["trend"] = trend

        return self._sanitize(ctx)

    def build_record_delta(
        self,
        athlete: "Athlete",
        target_record: "AnthropometricRecord",
        prior_records: list["AnthropometricRecord"],
        *,
        reference_date: date | None = None,
    ) -> dict:
        """Contexto para análisis particular: target vs medición inmediata anterior.

        `prior_records` son las mediciones ESTRICTAMENTE previas a `target_record`,
        en cualquier orden. Si la lista está vacía, el contexto omite los campos
        delta y la plantilla debe tomar la rama "primera medición".
        """
        ctx = self.build(athlete, target_record, history=None, reference_date=reference_date)
        ctx.pop("trend", None)

        prior_sorted = sorted(
            [r for r in prior_records if r.evaluation_date < target_record.evaluation_date],
            key=lambda r: r.evaluation_date,
            reverse=True,
        )
        ctx["num_previous_measurements"] = len(prior_sorted)

        if not prior_sorted:
            return self._sanitize(ctx)

        previous = prior_sorted[0]
        weeks = max(
            int((target_record.evaluation_date - previous.evaluation_date).days / 7),
            0,
        )
        delta_h = round(
            float(target_record.standing_height_cm - previous.standing_height_cm), 1
        )
        delta_w = round(
            float(target_record.weight_kg - previous.weight_kg), 1
        )

        ctx["weeks_since_prev_measurement"] = weeks
        ctx["delta_height_cm"] = delta_h
        ctx["delta_weight_kg"] = delta_w
        ctx["delta_height_significant"] = abs(delta_h) >= DELTA_HEIGHT_SIGNIFICANT_CM
        ctx["delta_weight_significant"] = abs(delta_w) >= DELTA_WEIGHT_SIGNIFICANT_KG

        if weeks >= MIN_WEEKS_FOR_VELOCITY:
            years = weeks / 52.18
            if years > 0:
                ctx["growth_velocity_cm_per_year"] = round(delta_h / years, 1)

        prev_status = _maturation_value(previous)
        ctx["prev_maturation_status"] = prev_status
        ctx["crossed_phv_phase"] = prev_status != ctx.get("maturation_status", "")

        return self._sanitize(ctx)

    @staticmethod
    def _sanitize(ctx: dict) -> dict:
        # Defensa en profundidad: si alguna vez se cuela una clave fuera de la
        # allowlist, recortamos en silencio (mejor que filtrar PII).
        for key in list(ctx.keys() - ATHLETE_CONTEXT_ALLOWED_KEYS):
            ctx.pop(key, None)
        return ctx
