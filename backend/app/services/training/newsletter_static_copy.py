"""Copia estática determinista para el boletín mensual individual (US3 / FR-009/FR-010).

Cuando falta consentimiento Ley 1581 para procesamiento con IA, o cuando el LLM
falla/agota tiempo, el boletín DEBE renderizarse igual. Este módulo produce, de
forma 100% determinista y sin red:

  - block_captions: un subtítulo en español neutro por bloque
    (attendance, technical, race_results, anthropometry), seleccionado de una
    biblioteca vetada según señales simples del snapshot de métricas.
  - month_highlights: una línea de resumen del mes.
  - support_at_home: selección de consejos desde la biblioteca fija del builder.

Garantías de privacidad / pedagogía:
  - NUNCA contiene nombres reales (texto fijo, sin interpolar datos personales).
  - Sin términos médicos/diagnósticos ni comparaciones negativas.
  - Sin etiquetas clasificatorias de antropometría (peso/talla baja, etc.).
  - español neutro (Colombia), tono positivo y respetuoso de la edad biológica.

NO sustituye la narrativa del entrenador (strengths/area/milestone): esa sigue
detrás del gate de consentimiento y, sin IA, muestra un placeholder neutro.
"""

from __future__ import annotations

from typing import Any

# Placeholder neutro para la narrativa del entrenador cuando no hay IA/consentimiento.
# (research.md Open Item — default acordado para la valoración legada).
COACH_NARRATIVE_UNAVAILABLE = "Valoración del entrenador no disponible este mes."

# ---------------------------------------------------------------------------
# Biblioteca vetada de subtítulos por bloque (español neutro).
# Cada entrada es una frase completa (>=10 palabras) para pasar el mismo umbral
# de longitud que aplica el guardrail de IA, manteniendo consistencia.
# ---------------------------------------------------------------------------

_ATTENDANCE_HIGH = (
    "La asistencia constante de este mes ayuda a consolidar el aprendizaje y a "
    "construir buenos hábitos de entrenamiento."
)
_ATTENDANCE_MID = (
    "La asistencia es la base del progreso: cada sesión suma para afianzar la "
    "técnica y disfrutar más sobre la bici."
)
_ATTENDANCE_LOW = (
    "Acompañar la constancia en las sesiones, sin presionar, ayuda a que el "
    "aprendizaje y la confianza crezcan con el tiempo."
)

_TECHNICAL_WITH_FOCI = (
    "El trabajo técnico del mes se enfocó en habilidades concretas que se "
    "construyen con repetición paciente y mucho juego."
)
_TECHNICAL_GENERIC = (
    "El desarrollo técnico prioriza el dominio de la bici antes que la "
    "intensidad, tal como corresponde a esta etapa de crecimiento."
)

_RACE_WITH_RESULTS = (
    "Participar en competencia es una experiencia de aprendizaje: lo importante "
    "es el esfuerzo, la actitud y lo que se gana de cada salida."
)

_ANTHRO_CAPTION = (
    "Este seguimiento acompaña el crecimiento y la maduración de manera "
    "pedagógica, para planificar el entrenamiento según la edad biológica."
)

# ---------------------------------------------------------------------------
# Resumen del mes (highlights) — biblioteca vetada.
# ---------------------------------------------------------------------------

_HIGHLIGHTS_RACES = (
    "Este mes combinó entrenamiento y competencia: una gran oportunidad para "
    "aprender, disfrutar y seguir creciendo sobre la bici."
)
_HIGHLIGHTS_STRONG_ATTENDANCE = (
    "Un mes de buena constancia en los entrenamientos, base sólida para seguir "
    "afianzando la técnica y disfrutar del proceso."
)
_HIGHLIGHTS_DEFAULT = (
    "Un mes más de proceso y aprendizaje sobre la bici, con foco en disfrutar y "
    "construir buenos hábitos paso a paso."
)


def _attendance_pct(email_blocks: dict[str, Any]) -> float | None:
    attendance = email_blocks.get("attendance") or {}
    pct = attendance.get("attendance_pct")
    return pct if isinstance(pct, (int, float)) else None


def _has_races(email_blocks: dict[str, Any]) -> bool:
    race = email_blocks.get("race_results") or {}
    return bool(race.get("has_races"))


def build_static_captions(email_blocks: dict[str, Any]) -> dict[str, str]:
    """Subtítulos deterministas por bloque a partir de señales del snapshot.

    `race_results` se omite si no hubo carreras en el mes (igual que la IA).
    """
    captions: dict[str, str] = {}

    pct = _attendance_pct(email_blocks)
    if pct is None:
        captions["attendance"] = _ATTENDANCE_MID
    elif pct >= 90:
        captions["attendance"] = _ATTENDANCE_HIGH
    elif pct < 60:
        captions["attendance"] = _ATTENDANCE_LOW
    else:
        captions["attendance"] = _ATTENDANCE_MID

    technical = email_blocks.get("technical") or {}
    if technical.get("focos_tecnicos"):
        captions["technical"] = _TECHNICAL_WITH_FOCI
    else:
        captions["technical"] = _TECHNICAL_GENERIC

    if _has_races(email_blocks):
        captions["race_results"] = _RACE_WITH_RESULTS

    # La antropometría es SOLO PDF; este caption se consume únicamente en el
    # template PDF (nunca en email).
    captions["anthropometry"] = _ANTHRO_CAPTION

    return captions


def build_static_highlights(email_blocks: dict[str, Any]) -> str:
    """Línea de resumen del mes, determinista y vetada."""
    if _has_races(email_blocks):
        return _HIGHLIGHTS_RACES
    pct = _attendance_pct(email_blocks)
    if pct is not None and pct >= 90:
        return _HIGHLIGHTS_STRONG_ATTENDANCE
    return _HIGHLIGHTS_DEFAULT


def build_static_narrative(email_blocks: dict[str, Any]) -> dict[str, Any]:
    """Construye el dict de narrativa estática usado como fallback.

    Forma compatible con `ai_narrative` para que las plantillas lean los mismos
    campos. Incluye `block_captions`, `month_highlights` y marca el origen.
    NO incluye strengths/area/milestone (esos quedan al placeholder del coach).
    """
    return {
        "block_captions": build_static_captions(email_blocks),
        "month_highlights": build_static_highlights(email_blocks),
        "confidence": "low",
        "source": "static_fallback",
    }
