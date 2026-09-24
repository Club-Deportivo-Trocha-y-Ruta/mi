"""Paso 1 del pipeline antropométrico (feature 042): ensamblar ``AnalysisContext``.

Implementa ``specs/042-traceable-growth-ai/contracts/analysis-context.md`` y
``data-model.md`` §2.2. Firma compatible con un nodo LangGraph
(``async def step(state, config) -> dict``, `research.md` R-03) aunque este
pipeline es un orquestador plano sin grafo, checkpointer ni HITL — la firma
se mantiene idéntica solo para que una futura promoción a ``StateGraph`` sea
un envoltorio mecánico, no una reescritura.

Contrato de entrada de ``state`` (documentado aquí porque no existe un
``TypedDict`` compartido — lo puebla ``pipeline.py``, T039, no este módulo):

- ``athlete``: instancia de ``Athlete`` ya cargada.
- ``target_record``: ``AnthropometricRecord`` que se está analizando.
- ``history_records``: TODAS las mediciones del atleta (incluya o no al
  target — se deduplica aquí por ``id``), en cualquier orden.
- ``audience``: ``"family" | "coach"``.
- ``use_case``: el mismo string que ``AthleteAIExplanation.use_case`` — se
  usa para buscar el análisis estructurado previo del atleta (§2.6).
- ``club_id``: ``int | None`` — club del atleta, para la ventana de
  entrenamiento. ``None`` degrada ``training_load_window`` a ``None``
  (nunca se inventa, FR-009).
- ``db``: sesión async de SQLAlchemy — solo para dos lecturas auxiliares
  (ventana de entrenamiento, análisis estructurado previo). Nunca se usa
  para releer atleta o mediciones, que ya llegan cargadas en ``state``.
- ``reference_date``: ``date | None``, opcional (tests) — default hoy.

Retorna una actualización de estado (mismo patrón que
``app/services/race/ai/nodes/*``):
``{"analysis_context": AnalysisContext(...), "context_blocks": {...}}``.

``context_blocks`` trae el texto YA formateado (español neutro) para las
seis variables Jinja que el prompt del analista espera
(``contracts/prompts/anthropometry_analyst_v1.md``). Se genera en esta misma
función, a partir de los MISMOS dicts ya saneados por la allowlist — nunca
releyendo datos crudos por separado — para que el límite de privacidad
(``sanitize_insight_context``) y el límite de renderizado no puedan divergir
con el tiempo (instrucción explícita de la feature).

CRÍTICO (FR-003): ningún z-score, percentil, valor crudo de banda o fecha
absoluta puede sobrevivir a ``sanitize_insight_context()``. Todo lo temporal
sale como semanas relativas (``weeks_*``), nunca una fecha.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import re
from typing import TYPE_CHECKING, Any, Sequence

from sqlalchemy import select

from app.models.ai_explanation import AthleteAIExplanation
from app.services.ai.context_builders import (
    DELTA_HEIGHT_SIGNIFICANT_CM,
    DELTA_WEIGHT_SIGNIFICANT_KG,
    _NAME_LIKE_PATTERN,
    age_group_for,
    build_longitudinal_series,
    phase_crossing_corroborated,
    sanitize_insight_context,
    velocity_confidence,
)
from app.services.category import compute_age_decimal, get_category
from app.services.growth_summary import build_growth_summary, get_expected_velocity_range
from app.services.race.ai.athlete_context import load_training_window

if TYPE_CHECKING:
    from app.models.anthropometry import AnthropometricRecord
    from app.models.athlete import Athlete
    from app.schemas.growth import GrowthSummaryOut

_TRAINING_WINDOW_DAYS = 28

__all__ = [
    "AnalysisContext",
    "build_context",
    "_build_body_composition_dict",
    "_render_body_composition_block",
]


@dataclass(frozen=True)
class AnalysisContext:
    """Entrada determinística y saneada que el prompt del analista renderiza.

    Verbatim de ``data-model.md`` §2.2 — no le agregues campos aquí sin
    actualizar ese contrato; ``body_composition`` es la única excepción
    documentada, agregada por la feature 046
    (``specs/046-body-composition-skinfolds/contracts/
    ai-body-composition-leaf.md`` §1). El texto pre-formateado para el
    prompt viaja aparte, en ``context_blocks`` (ver el docstring del
    módulo), precisamente para no ensanchar esta forma ya fijada por el
    contrato.
    """

    identity: dict
    measurement_deltas: dict | None
    longitudinal_series: list[dict]
    growth_summary: dict
    training_load_window: dict | None
    previous_analysis: dict | None
    body_composition: dict | None = None


def _status_value(record: "AnthropometricRecord") -> str:
    status = record.maturation_status
    return status.value if hasattr(status, "value") else str(status)


def _merge_history(
    history_records: list["AnthropometricRecord"], target_record: "AnthropometricRecord"
) -> list["AnthropometricRecord"]:
    """``history_records`` + ``target_record``, sin duplicar por ``id``."""
    if any(r.id == target_record.id for r in history_records):
        return list(history_records)
    return [*history_records, target_record]


def _prior_records_desc(
    history_records: list["AnthropometricRecord"], target_record: "AnthropometricRecord"
) -> list["AnthropometricRecord"]:
    """Mediciones estrictamente anteriores al target, de la más a la menos reciente."""
    return sorted(
        (r for r in history_records if r.evaluation_date < target_record.evaluation_date),
        key=lambda r: r.evaluation_date,
        reverse=True,
    )


def _build_identity(
    athlete: "Athlete",
    target_record: "AnthropometricRecord",
    audience: str,
    reference_date: date,
) -> dict:
    age_decimal = round(compute_age_decimal(athlete.birth_date, reference_date), 1)
    identity: dict[str, Any] = {
        "age_decimal": age_decimal,
        "age_group": age_group_for(age_decimal),
        "sex": athlete.sex.value,
        "category": get_category(athlete.birth_date.year, athlete.sex.value),
        "audience": audience,
    }
    if target_record.arm_span_cm is not None:
        identity["arm_span_cm"] = round(float(target_record.arm_span_cm), 1)
    return identity


def _build_measurement_deltas(
    target_record: "AnthropometricRecord",
    previous_record: "AnthropometricRecord | None",
    older_record: "AnthropometricRecord | None",
) -> dict | None:
    """``None`` en la primera medición (FR sin previa, data-model.md §2.2)."""
    if previous_record is None:
        return None

    weeks = max(
        int((target_record.evaluation_date - previous_record.evaluation_date).days / 7), 0
    )
    delta_h = round(
        float(target_record.standing_height_cm) - float(previous_record.standing_height_cm), 1
    )
    delta_w = round(float(target_record.weight_kg) - float(previous_record.weight_kg), 1)
    prev_status = _status_value(previous_record)

    deltas: dict[str, Any] = {
        "weeks_since_prev_measurement": weeks,
        "delta_height_cm": delta_h,
        "delta_weight_kg": delta_w,
        "delta_height_significant": abs(delta_h) >= DELTA_HEIGHT_SIGNIFICANT_CM,
        "delta_weight_significant": abs(delta_w) >= DELTA_WEIGHT_SIGNIFICANT_KG,
        "crossed_phv_phase": prev_status != _status_value(target_record),
        "prev_maturation_status": prev_status,
        "phase_crossing_corroborated": phase_crossing_corroborated(
            prev_status,
            previous_record.evaluation_date,
            _status_value(older_record) if older_record is not None else None,
            older_record.evaluation_date if older_record is not None else None,
        ),
    }

    conf = velocity_confidence(weeks)
    if conf is not None:
        years = weeks / 52.18
        deltas["growth_velocity_cm_per_year"] = round(delta_h / years, 1)
        deltas["velocity_confidence"] = conf

    return deltas


def _build_growth_summary_dict(summary: "GrowthSummaryOut", sex: str) -> dict:
    """Solo códigos cualitativos — nunca z-score/percentil/valor crudo (§2.4)."""
    out: dict[str, Any] = {}
    if summary.stage is not None:
        stage_value = summary.stage.value
        out["stage"] = stage_value
        # Única fuente permitida del ancla de velocidad (FR-007/FR-036): la
        # misma función que feature 040 ya usa para este propósito, nunca un
        # literal reinventado en este módulo.
        out["expected_velocity_range_cm_year"] = get_expected_velocity_range(stage_value, sex)
    if summary.maturity_offset is not None:
        out["maturity_offset"] = summary.maturity_offset
    if summary.age_at_phv is not None:
        out["age_at_phv"] = summary.age_at_phv
    if summary.months_from_phv is not None:
        out["months_from_phv"] = summary.months_from_phv
    if summary.latest is not None:
        if summary.latest.height is not None:
            out["height_band"] = summary.latest.height.band.value
        if summary.latest.weight is not None:
            out["weight_band"] = summary.latest.weight.band.value
        if summary.latest.bmi is not None:
            out["nutritional_status"] = summary.latest.bmi.band.value
    out["alerts"] = [alert.value for alert in summary.alerts]
    out["measurement_due_status"] = summary.measurement.status.value
    return out


async def _load_previous_structured_insight(
    db: Any, athlete_id: int, use_case: str
) -> AthleteAIExplanation | None:
    """El último insight estructurado (``schema_version="v2"``) del atleta.

    Filtra únicamente por ``athlete_id`` + ``use_case`` — nunca por
    ``anthropometric_record_id`` — porque el propósito es continuidad entre
    dos generaciones ESTRUCTURADAS cualesquiera del atleta, no de la misma
    medición (analysis-context.md §2.6, corrección a la nota de diseño).
    Las filas legadas (``schema_version IS NULL``) nunca se leen aquí.
    """
    stmt = (
        select(AthleteAIExplanation)
        .where(
            AthleteAIExplanation.athlete_id == athlete_id,
            AthleteAIExplanation.use_case == use_case,
            AthleteAIExplanation.schema_version == "v2",
        )
        .order_by(AthleteAIExplanation.generated_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _scrub_previous_summary(text: str, forbidden_names: Sequence[str]) -> str:
    """Tacha nombres del resumen previo antes de que vuelva al prompt.

    ``previous_analysis.summary_line`` es el ÚNICO texto libre que el
    allow-list admite en el prompt (``contracts/analysis-context.md`` §2.6), y
    §3 del mismo contrato prohíbe que viaje cualquier nombre. Las dos capas:

    1. Coincidencia exacta contra la lista prohibida del club, que es la única
       defensa que funciona con un nombre de forma arbitraria (una regex de
       "Nombre Apellido" no atrapa mayúsculas completas ni grafías raras).
    2. ``_NAME_LIKE_PATTERN``, el mismo saneador que ya se aplica al texto
       libre del coach, como defensa en profundidad para un nombre que todavía
       no esté en la lista.

    Por qué hace falta: R06 solo revisa el borrador NUEVO ya generado. Un
    nombre que quedó dentro de un insight persistido —o que pasó a ser
    prohibido después de generarlo— volvería a salir hacia el proveedor
    externo en el siguiente prompt sin que ningún guardrail lo viera. Hallazgo
    CRÍTICO de la auditoría data-privacy-guard (T057).
    """
    cleaned = text
    for name in sorted(forbidden_names, key=len, reverse=True):
        candidate = name.strip()
        if not candidate:
            continue
        cleaned = re.sub(rf"\b{re.escape(candidate)}\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = _NAME_LIKE_PATTERN.sub("", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _build_previous_analysis_dict(
    row: AthleteAIExplanation,
    reference_date: date,
    forbidden_names: Sequence[str] = (),
) -> dict | None:
    """``None`` si la fila no trae un ``structured_json`` legible (FR-009:
    nunca inventar contenido — mejor sin continuidad previa que corrupta).

    ``forbidden_names`` llega desde ``pipeline.py`` (lista del club cargada
    antes del contexto) y tacha el resumen previo — ver
    :func:`_scrub_previous_summary`.
    """
    structured = row.structured_json or {}
    summary_line = structured.get("summary_line")
    if summary_line:
        summary_line = _scrub_previous_summary(summary_line, forbidden_names)
    confidence_level = (structured.get("confidence") or {}).get("level")
    if not summary_line or not confidence_level:
        return None
    weeks_since = max(int((reference_date - row.generated_at.date()).days / 7), 0)
    return {
        # "v1" aquí es la versión del PAYLOAD del insight (data-model.md §0),
        # no el discriminador de fila que ya filtramos arriba (=="v2").
        "insight_schema_version": structured.get("schema_version", "v1"),
        "summary_line": summary_line,
        "confidence_level": confidence_level,
        "weeks_since": weeks_since,
    }


# ---------------------------------------------------------------------------
# Hoja de composición corporal (feature 046, contracts/ai-body-composition-
# leaf.md §1) — SIEMPRE códigos cualitativos, nunca un `*_mm`/`*_pct`/`*_kg`.
# ---------------------------------------------------------------------------

#: `band_reason_code` que también son válidos como `growth_explanation_code`
#: (contract §2 de ``body-composition-reading.md``, filas de la banda verde).
_GROWTH_EXPLANATION_REASON_CODES = frozenset(
    {"expected_pubertal_gain", "pre_spurt_accumulation", "post_phv_lean_gain"}
)

_REFERENCE_WORST_ORDER = ("low", "high", "normal")


def _collapse_reference_code(code: str | None) -> str:
    """`low_extreme`/`low` -> `low`; `high_extreme`/`high` -> `high` (contract §1)."""
    if code in ("low_extreme", "low"):
        return "low"
    if code in ("high_extreme", "high"):
        return "high"
    if code == "normal":
        return "normal"
    return "unavailable"


def _worst_reference_context_code(triceps_code: str | None, subscapular_code: str | None) -> str:
    """Peor de los dos sitios de referencia, extremos colapsados a low/high."""
    collapsed = {_collapse_reference_code(triceps_code), _collapse_reference_code(subscapular_code)}
    for candidate in _REFERENCE_WORST_ORDER:
        if candidate in collapsed:
            return candidate
    return "unavailable"


def _build_body_composition_dict(
    latest_record: "AnthropometricRecord | None",
    previous_record: "AnthropometricRecord | None",
    reading: Any | None,
) -> dict | None:
    """Las diez claves cualitativas de ``contracts/ai-body-composition-leaf.md`` §1.

    ``reading`` es el ``BodyCompositionReading`` (o ``None`` si el atleta no
    tiene ningún set contado) ya calculado por
    ``app/services/body_composition.py::build_reading`` — este builder NO
    recalcula la lógica de banda, solo proyecta el resultado a códigos
    cualitativos aptos para prompt. ``None`` cuando ``reading`` es ``None``
    (ningún set con datos), igual que el resto de hojas de este módulo.
    """
    if reading is None:
        return None

    weeks_since_prev_set: int | None = None
    if previous_record is not None and latest_record is not None:
        weeks_since_prev_set = max(
            int((latest_record.evaluation_date - previous_record.evaluation_date).days / 7), 0
        )

    growth_explanation_code = (
        reading.band_reason_code
        if reading.band_reason_code in _GROWTH_EXPLANATION_REASON_CODES
        else "none"
    )

    return {
        "sets_count": min(reading.sets_count, 9),
        "weeks_since_prev_set": weeks_since_prev_set,
        "sum_change_code": reading.sum_change_code,
        "growth_explanation_code": growth_explanation_code,
        "ffm_trend_code": reading.ffm_trend_code,
        # Coach-only en el prompt (ver `_render_body_composition_block`) —
        # viajan en el leaf igual para que el analista de la audiencia coach
        # los reciba; la audiencia familiar nunca los renderiza.
        "band": reading.band,
        "band_reason_code": reading.band_reason_code,
        "family_band": reading.family_band,
        "reference_context_code": _worst_reference_context_code(
            reading.reference_triceps.code, reading.reference_subscapular.code
        ),
        "sites_declined_count": reading.sites_declined_count,
    }


#: Español (Colombia) — significado de una línea por código, nunca un número.
_FAMILY_BAND_LINE = {
    "verde": "En su curva esperada: sigue acompañando el proceso con normalidad.",
    "ambar": "En observación: el entrenador está acompañando el proceso de cerca.",
}

_SUM_CHANGE_MEANING = {
    "none": "sin una medición anterior para comparar",
    "within_noise": "sin cambio real frente a la medición anterior",
    "up_real": "un aumento real frente a la medición anterior",
    "down_real": "una disminución real frente a la medición anterior",
}

_GROWTH_EXPLANATION_MEANING = {
    "expected_pubertal_gain": "una ganancia esperada asociada a la etapa puberal",
    "pre_spurt_accumulation": "una acumulación previa al estirón de crecimiento",
    "post_phv_lean_gain": "una ganancia de masa magra posterior al pico de velocidad",
    "none": "sin una explicación de crecimiento asociada todavía",
}

_FFM_TREND_MEANING = {
    "up": "en aumento",
    "flat": "estable",
    "down": "en descenso",
    "unavailable": "sin dato suficiente para establecer una tendencia",
}

_REFERENCE_CONTEXT_MEANING = {
    "low": "por debajo de lo habitual en la referencia poblacional",
    "high": "por encima de lo habitual en la referencia poblacional",
    "normal": "dentro de lo habitual en la referencia poblacional",
    "unavailable": "sin referencia poblacional disponible",
}

#: Coach-only (nunca se usa en la rama familiar del renderizador).
_BAND_REASON_MEANING = {
    "energy_availability_pattern": "un patrón de disponibilidad energética para conversar en persona",
    "sum_down_unexplained": "una disminución de pliegues sin explicación de talla o peso",
    "sum_up_unexplained": "un aumento de pliegues sin explicación de crecimiento",
    "sum_up_velocity_low": "un aumento de pliegues con velocidad de crecimiento baja",
    "reference_extreme": "un sitio de referencia en el extremo de la población",
    "bmi_z_drop": "una caída relevante del z-score de índice de masa corporal",
    "velocity_low_persistent": "una velocidad de crecimiento baja en dos ciclos seguidos",
    "expected_pubertal_gain": "una ganancia esperada asociada a la etapa puberal",
    "pre_spurt_accumulation": "una acumulación previa al estirón de crecimiento",
    "post_phv_lean_gain": "una ganancia de masa magra posterior al pico de velocidad",
    "first_set": "la primera medición registrada, sin comparación previa",
    "no_real_change": "un patrón estable respecto a la medición anterior",
    "stable": "una composición corporal estable",
}


def _render_body_composition_block(leaf: dict | None, audience: str) -> str | None:
    """Bloque "Composición corporal (códigos cualitativos)" del prompt.

    ``None`` cuando ``leaf`` es ``None`` (sin set con datos) — se agrega a
    ``context_blocks`` solo cuando existe (contract §2). La rama familiar
    SOLO usa ``family_band``; ``band``/``band_reason_code`` (contenido
    exclusivo del entrenador) se renderizan únicamente para ``audience ==
    "coach"``.
    """
    if leaf is None:
        return None

    is_coach = audience == "coach"
    lines = ["Composición corporal (códigos cualitativos):"]
    if is_coach:
        reason = _BAND_REASON_MEANING.get(leaf["band_reason_code"], leaf["band_reason_code"])
        lines.append(f"- Banda del entrenador: {leaf['band']}, por {reason}.")
        lines.append(f"- Sets de pliegues registrados: {leaf['sets_count']}.")
    else:
        # Defensa en profundidad: nunca una frase roja para familias, aunque
        # llegue un `family_band` inesperado (contract §3c).
        family_band = "verde" if leaf.get("family_band") == "verde" else "ambar"
        lines.append(f"- {_FAMILY_BAND_LINE[family_band]}")
    if leaf.get("weeks_since_prev_set") is not None:
        lines.append(f"- Semanas desde el set anterior: {leaf['weeks_since_prev_set']}.")
    lines.append(
        "- Cambio de la sumatoria de pliegues: "
        f"{_SUM_CHANGE_MEANING.get(leaf['sum_change_code'], leaf['sum_change_code'])}."
    )
    lines.append(
        "- Explicación de crecimiento asociada: "
        f"{_GROWTH_EXPLANATION_MEANING.get(leaf['growth_explanation_code'], leaf['growth_explanation_code'])}."
    )
    lines.append(
        "- Tendencia de masa libre de grasa: "
        f"{_FFM_TREND_MEANING.get(leaf['ffm_trend_code'], leaf['ffm_trend_code'])}."
    )
    # Coach-only (T069, hallazgo F3): la referencia poblacional es contexto
    # exclusivo del entrenador (spec, aclaración Q4 — un ámbar solo por
    # referencia se ve "En su curva esperada"), y el prompt familiar prohíbe
    # mencionar la referencia, los sitios no medidos o el número de tomas;
    # el proveedor no recibe esas líneas en la audiencia familiar.
    if is_coach:
        lines.append(
            "- Contexto frente a la referencia poblacional: "
            f"{_REFERENCE_CONTEXT_MEANING.get(leaf['reference_context_code'], leaf['reference_context_code'])}."
        )
        if leaf.get("sites_declined_count"):
            lines.append(f"- Sitios que el/la deportista prefirió no medir: {leaf['sites_declined_count']}.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Bloques pre-formateados para el prompt (español neutro, mismo dict saneado)
# ---------------------------------------------------------------------------


def _render_identity_block(identity: dict) -> str:
    parts = [
        f"Edad: {identity['age_decimal']} años ({identity['age_group']}).",
        f"Sexo: {identity['sex']}. Categoría: {identity['category']}.",
    ]
    if identity.get("arm_span_cm") is not None:
        parts.append(f"Envergadura más reciente: {identity['arm_span_cm']} cm.")
    return " ".join(parts)


def _render_measurement_deltas_block(deltas: dict | None) -> str | None:
    if deltas is None:
        return None
    lines = [
        f"Han pasado {deltas['weeks_since_prev_measurement']} semanas desde la medición anterior.",
        "Cambio de talla: {:+.1f} cm ({}).".format(
            deltas["delta_height_cm"],
            "significativo" if deltas["delta_height_significant"] else "dentro del ruido instrumental",
        ),
        "Cambio de peso: {:+.1f} kg ({}).".format(
            deltas["delta_weight_kg"],
            "significativo" if deltas["delta_weight_significant"] else "dentro del ruido instrumental",
        ),
    ]
    if deltas.get("growth_velocity_cm_per_year") is not None:
        etiqueta = {"reliable": "confiable", "early_signal": "señal temprana, aún no confiable"}.get(
            deltas.get("velocity_confidence"), "sin clasificar"
        )
        lines.append(
            f"Velocidad de crecimiento estimada: {deltas['growth_velocity_cm_per_year']} cm/año ({etiqueta})."
        )
    if deltas["crossed_phv_phase"]:
        estado = (
            "confirmado por una lectura previa consistente"
            if deltas["phase_crossing_corroborated"]
            else "aún sin confirmar con una lectura previa"
        )
        lines.append(f"Cambio de fase de maduración desde {deltas['prev_maturation_status']} ({estado}).")
    return " ".join(lines)


def _render_longitudinal_series_block(series: list[dict]) -> str | None:
    if not series:
        return None
    lines = []
    for point in series:
        delta_txt = ""
        if point.get("delta_height_cm_from_prior_point") is not None:
            delta_txt = f", cambio de {point['delta_height_cm_from_prior_point']:+.1f} cm respecto al punto anterior"
        lines.append(
            "- Hace {} semanas: talla {} cm, peso {} kg, fase {}{}.".format(
                point["weeks_offset_from_latest"],
                point["height_cm"],
                point["weight_kg"],
                point["maturation_status_at_point"],
                delta_txt,
            )
        )
    return "\n".join(lines)


def _render_growth_summary_block(summary: dict) -> str:
    lines = []
    if summary.get("stage"):
        lines.append(f"Fase de maduración actual: {summary['stage']}.")
    if summary.get("expected_velocity_range_cm_year"):
        lo, hi = summary["expected_velocity_range_cm_year"]
        lines.append(f"Rango esperado de velocidad de crecimiento para esta fase: {lo}-{hi} cm/año.")
    if summary.get("height_band"):
        lines.append(f"Banda de talla: {summary['height_band']}.")
    if summary.get("weight_band"):
        lines.append(f"Banda de peso: {summary['weight_band']}.")
    if summary.get("nutritional_status"):
        lines.append(f"Estado nutricional: {summary['nutritional_status']}.")
    if summary.get("alerts"):
        lines.append("Alertas activas: " + ", ".join(summary["alerts"]) + ".")
    if summary.get("measurement_due_status"):
        lines.append(f"Estado de próxima medición: {summary['measurement_due_status']}.")
    return " ".join(lines)


def _render_training_load_block(window: dict | None) -> str | None:
    if window is None:
        return None
    lines = [f"Sesiones registradas en los últimos {_TRAINING_WINDOW_DAYS} días: {window['sessions_count_28d']}."]
    if window.get("avg_rpe_28d") is not None:
        lines.append(f"RPE promedio: {window['avg_rpe_28d']}.")
    if window.get("hours_28d") is not None:
        lines.append(f"Horas de entrenamiento: {window['hours_28d']}.")
    return " ".join(lines)


def _render_previous_analysis_block(previous: dict | None) -> str | None:
    if previous is None:
        return None
    return (
        f"Hace {previous['weeks_since']} semanas el análisis anterior resumió: "
        f"“{previous['summary_line']}” (confianza {previous['confidence_level']}). "
        "Esta nueva lectura no debe repetir esa misma frase."
    )


async def build_context(state: dict, config: dict | None = None) -> dict[str, Any]:
    """Paso 1: ensambla ``AnalysisContext`` + los bloques de texto del prompt.

    Ver el docstring del módulo para el contrato completo de ``state``.
    ``config`` no se usa en este paso (no hace ninguna llamada al LLM) pero
    se acepta para mantener la firma uniforme entre los cinco pasos del
    pipeline (``research.md`` R-03) y para poder threadear `callbacks` de
    tracing sin cambiar la firma el día que este paso también necesite
    abrir su propio span.
    """
    del config  # no usado en este paso — ver docstring.

    athlete: Athlete = state["athlete"]
    target_record: AnthropometricRecord = state["target_record"]
    history_records: list[AnthropometricRecord] = state.get("history_records") or []
    audience: str = state["audience"]
    use_case: str = state["use_case"]
    club_id: int | None = state.get("club_id")
    db = state.get("db")
    reference_date: date = state.get("reference_date") or date.today()

    prior_records = _prior_records_desc(history_records, target_record)
    previous_record = prior_records[0] if prior_records else None
    older_record = prior_records[1] if len(prior_records) > 1 else None

    identity = sanitize_insight_context(
        _build_identity(athlete, target_record, audience, reference_date)
    )

    raw_deltas = _build_measurement_deltas(target_record, previous_record, older_record)
    measurement_deltas = sanitize_insight_context(raw_deltas) if raw_deltas is not None else None

    full_history = _merge_history(history_records, target_record)
    longitudinal_series = [
        sanitize_insight_context(point)
        for point in build_longitudinal_series(full_history, reference_date=target_record.evaluation_date)
    ]

    growth_summary_out = build_growth_summary(
        athlete, target_record, previous_record, today=reference_date
    )
    growth_summary = sanitize_insight_context(
        _build_growth_summary_dict(growth_summary_out, athlete.sex.value)
    )

    training_load_window: dict | None = None
    if db is not None and club_id is not None:
        window = await load_training_window(
            db,
            athlete.id,
            club_id,
            reference_date - timedelta(days=_TRAINING_WINDOW_DAYS),
            reference_date,
        )
        if window is not None:
            training_load_window = sanitize_insight_context(
                {
                    "sessions_count_28d": window["sessions_in_window"],
                    "avg_rpe_28d": window["rpe_mean"],
                    "hours_28d": window["training_hours"],
                }
            )

    previous_analysis: dict | None = None
    if db is not None:
        previous_row = await _load_previous_structured_insight(db, athlete.id, use_case)
        if previous_row is not None:
            raw_previous = _build_previous_analysis_dict(
                previous_row, reference_date, state.get("forbidden_names") or ()
            )
            if raw_previous is not None:
                previous_analysis = sanitize_insight_context(raw_previous)

    # Feature 046: hoja opcional de composición corporal. El llamador
    # (pipeline.py) pasa el `BodyCompositionReading` ya calculado bajo
    # `body_composition_reading`; sin esa clave (o sin ningún set contado)
    # la hoja es `None` y no aparece en el contexto ni en el prompt.
    # `weeks_since_prev_set` se mide entre SETS de pliegues, no entre
    # mediciones: pipeline.py (T080) pasa el registro del set contado
    # anterior (o `None` si es la primera toma). Sin esa clave (llamadores
    # previos a T080) se conserva el registro antropométrico anterior.
    body_composition_previous = (
        state["body_composition_previous_set_record"]
        if "body_composition_previous_set_record" in state
        else previous_record
    )
    raw_body_composition = _build_body_composition_dict(
        target_record, body_composition_previous, state.get("body_composition_reading")
    )
    body_composition = (
        sanitize_insight_context(raw_body_composition) if raw_body_composition is not None else None
    )

    context = AnalysisContext(
        identity=identity,
        measurement_deltas=measurement_deltas,
        longitudinal_series=longitudinal_series,
        growth_summary=growth_summary,
        training_load_window=training_load_window,
        previous_analysis=previous_analysis,
        body_composition=body_composition,
    )

    context_blocks = {
        "identity_block": _render_identity_block(identity),
        "measurement_deltas_block": _render_measurement_deltas_block(measurement_deltas),
        "longitudinal_series_block": _render_longitudinal_series_block(longitudinal_series),
        "growth_summary_block": _render_growth_summary_block(growth_summary),
        "training_load_block": _render_training_load_block(training_load_window),
        "previous_analysis_block": _render_previous_analysis_block(previous_analysis),
        "body_composition_block": _render_body_composition_block(body_composition, audience),
    }

    return {"analysis_context": context, "context_blocks": context_blocks}
