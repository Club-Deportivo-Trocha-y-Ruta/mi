"""Rule-based interpretation fallback (FR-016).

Produces the same JSON schema as the LLM use case when the model is
unavailable or returns invalid output. All athlete-/coach-facing text is in
español neutro (Colombia). Constitution Principle V: no diagnosis, mastery
climate, baseline-anchored, referral flag on sustained high-anxiety +
low-confidence. This module never calls an LLM.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.anxiety.instrument_keys import load_key

# Coarse bands as fractions of each subscale's range (guidance only, not cutoffs).
_LOW = 0.33
_HIGH = 0.66


@dataclass(frozen=True)
class Band:
    label: str  # "bajo" | "moderado" | "alto"
    position: float | None  # 0..1 within range, None if no score


def _band(value: float | None, rng: tuple[int, int]) -> Band:
    if value is None:
        return Band(label="sin dato", position=None)
    lo, hi = rng
    pos = 0.0 if hi == lo else (value - lo) / (hi - lo)
    pos = max(0.0, min(1.0, pos))
    if pos < _LOW:
        label = "bajo"
    elif pos >= _HIGH:
        label = "alto"
    else:
        label = "moderado"
    return Band(label=label, position=pos)


_SOMATIC_STRATEGIES = [
    "Respiración diafragmática 4-7-8 durante el calentamiento.",
    "Rutina pre-salida estructurada y constante (mismos pasos cada carrera).",
    "Relajación progresiva breve y música personal antes de la línea de salida.",
]
_COGNITIVE_STRATEGIES = [
    "Fijar 2-3 metas de proceso (no de resultado) para la primera vuelta.",
    "Visualizar el recorrido por secciones; clave 'tu bici sigue tus ojos'.",
    "Técnica de parar-el-pensamiento ante dudas; debrief con la regla de las 24 h.",
]
_CONFIDENCE_STRATEGIES = [
    "Recordar 2-3 logros recientes concretos antes de salir.",
    "Fragmentar el circuito en secciones alcanzables y celebrar cada una.",
    "Huddle pre-carrera con metas de proceso y apoyo del compañero.",
]
_FAVORABLE_STRATEGIES = [
    "Mantener la rutina habitual y una activación ligera.",
    "Reforzar el disfrute y el enfoque en el proceso; no sobre-intervenir.",
]


def _dimension_text(name: str, band: Band, baseline: float | None) -> str:
    if band.position is None:
        return f"{name}: sin dato suficiente en esta evaluación."
    base = f"{name}: nivel {band.label}"
    if baseline is None:
        return base + " (sin línea base aún; esta evaluación servirá de referencia)."
    return base + " respecto a su propia línea base."


def interpret(
    *,
    instrument_type: str,
    scores: dict[str, float | None],
    baseline: dict[str, float | None] | None = None,
    event: str | None = None,
    priority: str | None = None,
) -> dict:
    """Return the fixed interpretation schema from rules alone.

    ``scores`` / ``baseline`` map subscale → value (``cognitive``, ``somatic``,
    ``selfconfidence``). Output keys are in Spanish to match the runtime
    prompt contract.
    """
    key = load_key(instrument_type)
    baseline = baseline or {}

    def rng(name: str) -> tuple[int, int]:
        sub = key.subscale(name)
        return sub.range if sub else (0, 1)

    cog = _band(scores.get("cognitive"), rng("cognitive"))
    som = _band(scores.get("somatic"), rng("somatic"))
    conf = _band(scores.get("selfconfidence"), rng("selfconfidence"))

    anxiety_high = cog.label == "alto" or som.label == "alto"
    confidence_low = conf.position is not None and conf.label == "bajo"

    # Dominant pattern → strategy family.
    if confidence_low and anxiety_high:
        resumen = (
            "Llega con activación/preocupación elevada y confianza baja. "
            "Prioricemos construir confianza y bajar expectativas de resultado, "
            "enfocándonos en el proceso."
        )
        estrategias = _CONFIDENCE_STRATEGIES[:2] + _SOMATIC_STRATEGIES[:1]
    elif som.label == "alto" and som.position and som.position >= (cog.position or 0):
        resumen = "Patrón dominante: activación corporal (somática) elevada. Trabajemos regulación de la activación."
        estrategias = _SOMATIC_STRATEGIES[:3]
    elif cog.label == "alto":
        resumen = "Patrón dominante: preocupación (cognitiva) elevada. Trabajemos reencuadre y foco en el proceso."
        estrategias = _COGNITIVE_STRATEGIES[:3]
    elif confidence_low:
        resumen = "Confianza baja sin ansiedad marcada. Trabajemos experiencias de maestría."
        estrategias = _CONFIDENCE_STRATEGIES[:3]
    else:
        resumen = "Perfil favorable: activación y confianza en buen rango. Mantengamos la rutina."
        estrategias = _FAVORABLE_STRATEGIES[:2]

    banderas: list[str] = []
    if confidence_low and anxiety_high:
        banderas.append(
            "Ansiedad alta junto con confianza baja: sugiere conversación individual. "
            "Si se sostiene en varias evaluaciones, considerar derivación a un profesional de salud."
        )

    mensaje = (
        "Estar nervioso antes de competir es normal y se puede trabajar. "
        "Hoy enfócate en disfrutar y en hacer bien tu primera sección; el resto se acomoda."
    )

    return {
        "resumen": resumen,
        "por_dimension": {
            "cognitiva": _dimension_text("Cognitiva", cog, baseline.get("cognitive")),
            "somatica": _dimension_text("Somática", som, baseline.get("somatic")),
            "autoconfianza": _dimension_text("Autoconfianza", conf, baseline.get("selfconfidence")),
        },
        "estrategias": estrategias,
        "mensaje_para_el_atleta": mensaje,
        "banderas": banderas,
    }
