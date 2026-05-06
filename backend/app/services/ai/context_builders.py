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
        "bmi",
        "bmi_z_score",
        "weight_z_score",
        "nutritional_status",
        "evaluation_age_decimal",
        "trend",              # dict con deltas de últimas mediciones
        "training_implications",
        "mesocycle",
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
            "age_decimal": age_decimal,
            "age_group": _age_group(age_decimal),
            "sex": athlete.sex.value,
            "category": get_category(athlete.birth_date.year, athlete.sex.value),
        }

        if latest_record is not None:
            status = latest_record.maturation_status
            ctx.update(
                {
                    "phv_offset": _to_float(latest_record.maturity_offset),
                    "age_at_phv": _to_float(latest_record.age_at_phv),
                    "maturation_status": (
                        status.value if hasattr(status, "value") else str(status)
                    ),
                    "evaluation_age_decimal": compute_age_decimal(
                        athlete.birth_date, latest_record.evaluation_date
                    ),
                    "mesocycle": latest_record.mesocycle,
                    "training_implications": latest_record.training_implications,
                }
            )
            if latest_record.height_z_score is not None:
                ctx["height_z_score"] = _to_float(latest_record.height_z_score)
            if latest_record.bmi is not None:
                ctx["bmi"] = _to_float(latest_record.bmi)
            if latest_record.bmi_z_score is not None:
                ctx["bmi_z_score"] = _to_float(latest_record.bmi_z_score)
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

        # Defensa en profundidad: si alguna vez se cuela una clave fuera de la
        # allowlist, recortamos en silencio (mejor que filtrar PII).
        leaked = set(ctx) - ATHLETE_CONTEXT_ALLOWED_KEYS
        for key in leaked:
            ctx.pop(key, None)
        return ctx
