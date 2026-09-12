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
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.ai_explanation import AthleteAIExplanation
from app.services.ai.context_builders import (
    DELTA_HEIGHT_SIGNIFICANT_CM,
    DELTA_WEIGHT_SIGNIFICANT_KG,
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

__all__ = ["AnalysisContext", "build_context"]


@dataclass(frozen=True)
class AnalysisContext:
    """Entrada determinística y saneada que el prompt del analista renderiza.

    Verbatim de ``data-model.md`` §2.2 — no le agregues campos aquí; el
    texto pre-formateado para el prompt viaja aparte, en ``context_blocks``
    (ver el docstring del módulo), precisamente para no ensanchar esta forma
    ya fijada por el contrato.
    """

    identity: dict
    measurement_deltas: dict | None
    longitudinal_series: list[dict]
    growth_summary: dict
    training_load_window: dict | None
    previous_analysis: dict | None


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


def _build_previous_analysis_dict(
    row: AthleteAIExplanation, reference_date: date
) -> dict | None:
    """``None`` si la fila no trae un ``structured_json`` legible (FR-009:
    nunca inventar contenido — mejor sin continuidad previa que corrupta)."""
    structured = row.structured_json or {}
    summary_line = structured.get("summary_line")
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
            raw_previous = _build_previous_analysis_dict(previous_row, reference_date)
            if raw_previous is not None:
                previous_analysis = sanitize_insight_context(raw_previous)

    context = AnalysisContext(
        identity=identity,
        measurement_deltas=measurement_deltas,
        longitudinal_series=longitudinal_series,
        growth_summary=growth_summary,
        training_load_window=training_load_window,
        previous_analysis=previous_analysis,
    )

    context_blocks = {
        "identity_block": _render_identity_block(identity),
        "measurement_deltas_block": _render_measurement_deltas_block(measurement_deltas),
        "longitudinal_series_block": _render_longitudinal_series_block(longitudinal_series),
        "growth_summary_block": _render_growth_summary_block(growth_summary),
        "training_load_block": _render_training_load_block(training_load_window),
        "previous_analysis_block": _render_previous_analysis_block(previous_analysis),
    }

    return {"analysis_context": context, "context_blocks": context_blocks}
