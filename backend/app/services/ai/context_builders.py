"""Builders de contexto para los prompts.

Función pura: recibe instancias de SQLAlchemy y devuelve un dict con
**allowlist explícita** de claves seguras. Nada que pueda identificar al
menor sale de aquí: ni nombre, ni apellido, ni fecha de nacimiento exacta,
ni email, ni id.
"""

from __future__ import annotations

import re
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

# Máximo permitido para `training_implications` antes de inyectarlo al ctx.
# Si excede, truncamos con elipsis para limitar superficie de PII libre escrita
# por el coach.
TRAINING_IMPLICATIONS_MAX_CHARS = 300


# Patrones anti-diagnóstico para sanitizar `training_implications` antes de
# pasarlo al LLM. Replican (con replacement vacío para simplificar) las reglas
# `_RECORD_ANALYSIS_RULES` de `guardrails.py`. Se duplican aquí porque el
# guardrail opera sobre el OUTPUT del LLM, mientras que aquí hay que sanitizar
# el INPUT (texto libre escrito por el coach en la BD). Si los patrones de
# `guardrails.py` cambian, actualizar también esta lista.
_TRAINING_IMPLICATIONS_DIAGNOSTIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bdiagn[óo]stic[oa]s?\b", re.IGNORECASE),
    re.compile(r"\bpatolog[ií]a(s|o|os|cas?)?\b", re.IGNORECASE),
    re.compile(r"\banormal(idad(es)?)?\b", re.IGNORECASE),
    re.compile(
        r"\b(RED-?S|s[íi]ndrome de deficiencia energ[ée]tica( relativa)?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(d[ée]ficit energ[ée]tico|desnutrici[óo]n|anemia)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bretraso pub(eral|ertal)\b", re.IGNORECASE),
)

# Patrón conservador para detectar nombres propios en español: dos palabras
# consecutivas que empiezan con mayúscula y tienen al menos 3 letras. Usa
# letras latinas con acentos (À-ſ). Conscientemente conservador:
# prefiere falsos positivos a fugas de nombres ("Recordar Trabajar" se
# eliminaría, pero el operador no escribe así en notas clínicas).
_NAME_LIKE_PATTERN = re.compile(
    r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñÀ-ſ]{2,}"
    r"\s+"
    r"[A-ZÁÉÍÓÚÑ][a-záéíóúñÀ-ſ]{2,}\b"
)


def _sanitize_training_implications(text: str | None) -> str | None:
    """Sanea texto libre del coach antes de inyectarlo al LLM.

    Pasos (en orden):
      1. Si es ``None`` o queda vacío tras strip, devuelve ``None``.
      2. Elimina secuencias que parezcan nombres propios (regex conservadora).
      3. Aplica patrones anti-diagnóstico (replacement vacío).
      4. Trunca a ``TRAINING_IMPLICATIONS_MAX_CHARS`` caracteres con elipsis.
      5. Si tras todo lo anterior queda vacío o solo whitespace, devuelve
         ``None`` para que el caller pueda omitir la clave del contexto.
    """
    if text is None:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None

    # Eliminar nombres propios antes que los patrones diagnósticos para no
    # dejar restos parciales si un nombre aparecía junto a un término clínico.
    cleaned = _NAME_LIKE_PATTERN.sub("", cleaned)

    for pattern in _TRAINING_IMPLICATIONS_DIAGNOSTIC_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    # Normalizar whitespace que pueda haber quedado tras las sustituciones.
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    # Si solo quedó puntuación residual (".", ",", "—", etc.) tras eliminar
    # nombres y términos clínicos, consideramos el contenido vacío. Sin esto
    # quedarían restos sin significado como "." que solo confunden al LLM.
    if not cleaned or not re.search(r"\w", cleaned):
        return None

    if len(cleaned) > TRAINING_IMPLICATIONS_MAX_CHARS:
        cleaned = cleaned[:TRAINING_IMPLICATIONS_MAX_CHARS].rstrip() + "…"

    return cleaned


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
        # Privacidad: z-scores eliminados a propósito de la allowlist. En bases
        # pequeñas un par (z-altura, z-peso, edad, sexo) puede re-identificar al
        # menor. La plantilla `phv_explainer.j2` v2 ya no los renderiza; al
        # excluirlos también de la allowlist y de `build()` garantizamos que
        # nunca lleguen al LLM aunque un template futuro intente referenciarlos.
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
            # Privacidad: phv_offset y age_at_phv se redondean a 1 decimal
            # antes de inyectarse. La precisión a 2-3 decimales combinada con
            # (sexo, age_group) en clubes pequeños (n<10) facilita
            # re-identificación. Un decimal preserva la utilidad clínica
            # (Mirwald reporta ±1 año de error) sin entregar firmas únicas.
            phv_offset_raw = _to_float(latest_record.maturity_offset)
            age_at_phv_raw = _to_float(latest_record.age_at_phv)
            ctx.update(
                {
                    "phv_offset": (
                        round(phv_offset_raw, 1)
                        if phv_offset_raw is not None
                        else None
                    ),
                    "age_at_phv": (
                        round(age_at_phv_raw, 1)
                        if age_at_phv_raw is not None
                        else None
                    ),
                    "maturation_status": _maturation_value(latest_record),
                    "evaluation_age_decimal": round(
                        compute_age_decimal(
                            athlete.birth_date, latest_record.evaluation_date
                        ),
                        1,
                    ),
                }
            )
            # `training_implications` es texto libre escrito por el coach.
            # Se sanea (truncado + anti-diagnóstico + anti-nombre propio)
            # antes de inyectarlo. Si tras saneo queda vacío, omitimos la
            # clave para no contaminar el prompt con un string nulo.
            sanitized_implications = _sanitize_training_implications(
                latest_record.training_implications
            )
            if sanitized_implications is not None:
                ctx["training_implications"] = sanitized_implications
            # NOTA privacidad: NO se inyectan height_z_score ni weight_z_score
            # al contexto del LLM. Quedan disponibles en el modelo SQL para uso
            # interno (clasificación, reporting), pero la capa IA solo recibe
            # la categoría cualitativa `nutritional_status`.
            if latest_record.nutritional_status is not None:
                ns = latest_record.nutritional_status
                ctx["nutritional_status"] = (
                    ns.value if hasattr(ns, "value") else str(ns)
                )
            # Envergadura: dato del PROPIO atleta, útil como referencia
            # interna (relación talla/envergadura). Se inyecta solo si está
            # disponible y se redondea a 1 decimal para mantener la
            # consistencia con phv_offset/age_at_phv. Sigue dentro de la
            # allowlist (ATHLETE_CONTEXT_ALLOWED_KEYS).
            if latest_record.arm_span_cm is not None:
                arm_span_raw = _to_float(latest_record.arm_span_cm)
                if arm_span_raw is not None:
                    ctx["arm_span_cm"] = round(arm_span_raw, 1)

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
