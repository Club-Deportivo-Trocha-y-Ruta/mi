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


# ---------------------------------------------------------------------------
# "Cómo apoyar desde casa" — variantes por banda etaria y rotación mensual
# (R14/B14). Cada texto usa el placeholder ``{ref}`` para el pronombre de
# referencia del atleta ("su hijo"/"su hija"/"su hijo/a"), sustituido por el
# builder. Todas las variantes preservan los no-negociables del club: cero
# suplementos, sin conteo calórico, alimentación real como base.
# ---------------------------------------------------------------------------

SUPPORT_TIP_TITLES: dict[str, str] = {
    "hidratacion": "Hidratación",
    "sueno": "Sueño",
    "descanso": "Descanso activo",
    "nutricion": "Alimentación",
}

SUPPORT_TIP_VARIANTS: dict[str, dict[str, list[str]]] = {
    "10-12": {
        "hidratacion": [
            (
                "Asegúrate de que {ref} llegue al entrenamiento bien hidratado/a. "
                "Durante el día: agua o bebida de fruta natural. "
                "Antes del entreno: 500ml en la hora previa. "
                "Durante: sorbos cada 15-20 min según la sed."
            ),
            (
                "A esta edad la sed llega tarde: ofrece agua a {ref} de forma regular "
                "durante el día, sin esperar a que la pida. "
                "Un vaso al despertar y otro antes de salir de casa ayudan a llegar "
                "bien hidratado/a al entrenamiento."
            ),
            (
                "Después de entrenar, lo mejor para {ref} es agua o una fruta jugosa. "
                "Evita bebidas con mucha azúcar o cafeína; el cuerpo en esta etapa "
                "se hidrata mejor con líquidos simples."
            ),
        ],
        "sueno": [
            (
                "Los atletas de 10-12 años necesitan 9-11 horas de sueño por noche. "
                "El sueño es cuando el cuerpo crece y se recupera. "
                "Mantén horarios regulares para {ref}, especialmente antes de competencia."
            ),
            (
                "A los 10-12 años el cuerpo de {ref} crece mientras duerme: prioriza "
                "9-11 horas por noche. Apagar pantallas una hora antes de dormir "
                "ayuda a conciliar el sueño más rápido."
            ),
            (
                "Una rutina estable de sueño (misma hora de acostarse) es tan "
                "importante para {ref} como el entrenamiento mismo. "
                "Apunta a 9-11 horas por noche en esta etapa de crecimiento."
            ),
        ],
        "descanso": [
            (
                "Los días sin entrenamiento son parte del plan de {ref}. "
                "Un paseo en familia, nadar o jugar libremente es ideal. "
                "Evitar actividades extenuantes el día antes de competencia."
            ),
            (
                "El descanso activo de {ref} puede ser tan simple como jugar en el "
                "parque o andar en bici por diversión, sin cronómetro ni exigencia. "
                "El objetivo es moverse con disfrute, no entrenar dos veces."
            ),
            (
                "Respeta los días de descanso de {ref}: el cuerpo necesita esas "
                "pausas para asimilar el entrenamiento. "
                "Actividades multideporte libres (nadar, correr, jugar) son bienvenidas."
            ),
        ],
        "nutricion": [
            (
                "Tres comidas principales más un snack post-entreno balanceado para {ref}. "
                "Fruta, lácteos, proteína de alimentos naturales. "
                "Sin suplementos: a esta edad, la comida real es suficiente. "
                "El entrenador no realiza seguimiento calórico — la familia es la guía."
            ),
            (
                "La alimentación de {ref} debe apoyarse en comida real: frutas, "
                "verduras, cereales y proteína natural en cada comida principal. "
                "Cero suplementos y cero conteo de calorías — el apetito de un niño "
                "en crecimiento es la mejor guía."
            ),
            (
                "Después de entrenar, un snack sencillo (fruta con yogur, por ejemplo) "
                "ayuda a {ref} a recuperarse. "
                "No se recomiendan suplementos ni seguimiento calórico a esta edad; "
                "la comida real y variada es la base."
            ),
        ],
    },
    "13-15": {
        "hidratacion": [
            (
                "Asegúrate de que {ref} llegue al entrenamiento bien hidratado/a. "
                "Durante el día: agua como bebida principal. "
                "Antes del entreno: 500ml en la hora previa. "
                "Durante sesiones largas o de calor: sorbos frecuentes cada 15-20 min."
            ),
            (
                "En esta etapa el volumen de entrenamiento de {ref} aumenta: "
                "reforzar la hidratación durante todo el día (no solo en el entreno) "
                "hace la diferencia en el rendimiento y la recuperación."
            ),
            (
                "Antes de una competencia, ayuda a {ref} a hidratarse bien desde el "
                "día anterior, no solo esa mañana. "
                "Agua como base; evita bebidas energizantes o con cafeína."
            ),
        ],
        "sueno": [
            (
                "Los atletas de 13-15 años necesitan 8-10 horas de sueño por noche. "
                "El sueño es cuando el cuerpo se recupera del entrenamiento. "
                "Mantén horarios regulares para {ref}, especialmente antes de competencia."
            ),
            (
                "Con la carga de estudio y entrenamiento, el sueño de {ref} es la "
                "recuperación más importante y muchas veces la más descuidada. "
                "Apunta a 8-10 horas por noche, con horarios consistentes."
            ),
            (
                "Las pantallas antes de dormir afectan la calidad del sueño de {ref}. "
                "En esta etapa de mayor exigencia física, 8-10 horas de sueño "
                "reparador son clave para el progreso y para evitar lesiones."
            ),
        ],
        "descanso": [
            (
                "Los días sin entrenamiento son parte del plan de {ref}. "
                "Actividad ligera y recreativa está bien; evitar sobrecarga física extra. "
                "Evitar actividades extenuantes el día antes de competencia."
            ),
            (
                "A los 13-15 años, con más sesiones de intensidad por semana, el "
                "descanso de {ref} entre entrenamientos duros no es opcional. "
                "Un día completamente libre de esfuerzo físico ayuda a prevenir lesiones."
            ),
            (
                "Antes de una válida importante, prioriza que {ref} reduzca la "
                "actividad física extra (no solo el entrenamiento) los días previos. "
                "Llegar descansado/a rinde más que llegar cansado/a pero \"en forma\"."
            ),
        ],
        "nutricion": [
            (
                "Tres comidas principales más snacks balanceados para {ref}, ajustados "
                "al mayor gasto energético de esta etapa. "
                "Fruta, lácteos, proteína de alimentos naturales. "
                "Sin suplementos: la comida real cubre las necesidades. "
                "El entrenador no realiza seguimiento calórico — la familia es la guía."
            ),
            (
                "Con más horas de entrenamiento, {ref} necesita comidas completas y "
                "snacks de recuperación (ej. fruta con proteína) tras las sesiones. "
                "Cero suplementos y cero conteo de calorías: comida real y variada "
                "en cantidad suficiente."
            ),
            (
                "Evita restringir la alimentación de {ref} pensando en el peso: en "
                "esta etapa de crecimiento y mayor carga física la prioridad es comer "
                "suficiente y variado, sin suplementos ni conteo calórico."
            ),
        ],
    },
}


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
