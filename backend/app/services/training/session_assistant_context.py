"""Constructor de contexto agregado para el Asistente IA de sesiones (feature 006).

PRIVACIDAD: Esta función es la única fuente de contexto que se envía al LLM.
Carga los atletas seleccionados del club, calcula conteos de grupos de edad,
y descarta IDs y nombres ANTES de retornar el dict. El dict retornado
nunca contiene ningún dato identificante de menores.

Constante COPA_VALLE_2026: calendario oficial de la Copa Valle XCO 2026,
tal como se documenta en CLAUDE.md. Cada válida tiene fecha y prioridad
(A = tapering completo 5-7 días, B = mini-tapering 3-4 días, C = diagnóstico
sin tapering).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import Athlete
from app.services.category import compute_age_decimal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Calendario Copa Valle 2026
# ---------------------------------------------------------------------------

# Cada entrada: (fecha, prioridad)
# Prioridades: "A" (tapering completo 5-7 días), "B" (mini-tapering 3-4 días),
# "C" (diagnóstico — sin tapering).
COPA_VALLE_2026: list[tuple[date, str]] = [
    (date(2026, 1, 31), "A"),   # I   Sevilla
    (date(2026, 2, 28), "A"),   # II  Ginebra
    (date(2026, 4, 19), "C"),   # III La Cumbre  (diagnóstico, sin tapering)
    (date(2026, 5, 17), "A"),   # IV  Cali       (tapering completo 5-7 días)
    (date(2026, 6, 12), "A"),   # CD  Ginebra    (Campeonato Departamental, tapering 7 días)
    (date(2026, 8, 1),  "B"),   # V   Palmira    (mini-tapering 3-4 días)
    (date(2026, 9, 12), "A"),   # VI  Roldanillo (tapering completo 5-7 días)
    (date(2026, 10, 18), "B"),  # VII Yumbo      (mini-tapering 3-4 días)
]


# ---------------------------------------------------------------------------
# Age-group helpers (coincide con context_builders._age_group)
# ---------------------------------------------------------------------------


def _age_group(age_decimal: float) -> str:
    """Clasifica un atleta en el grupo de edad correcto.

    Umbrales: <13 → 10-12, <16 → 13-15, ≥16 → 16+.
    Coincide con ``app.services.ai.context_builders._age_group``.
    """
    if age_decimal < 13:
        return "10-12"
    if age_decimal < 16:
        return "13-15"
    return "16+"


# ---------------------------------------------------------------------------
# Race proximity
# ---------------------------------------------------------------------------


def _race_proximity(today: date) -> tuple[int | None, str | None]:
    """Calcula días hasta la próxima válida Copa Valle y su prioridad.

    Devuelve ``(days, priority)`` para la primera válida futura, o
    ``(None, None)`` si ya no quedan válidas en la temporada.
    """
    for race_date, priority in COPA_VALLE_2026:
        delta = (race_date - today).days
        if delta >= 0:
            return delta, priority
    return None, None


# ---------------------------------------------------------------------------
# Season phase
# ---------------------------------------------------------------------------

def _season_phase(today: date) -> str:
    """Determina la fase de temporada basada en la fecha actual.

    Lógica simplificada orientada por el calendario Copa Valle 2026:
    - Antes de Válida I (ene): pre-temporada / base general
    - Entre válidas: mesociclo en curso
    - Cerca de CD (jun) o fin de temporada: pico de forma
    - Después de la última válida: post-temporada / transición
    """
    days_to_next, priority = _race_proximity(today)

    if today < date(2026, 1, 1):
        return "pre-temporada (base general)"

    if today > date(2026, 10, 18):
        return "post-temporada (transición / descanso activo)"

    if days_to_next is None:
        return "post-temporada (transición)"

    if days_to_next <= 7 and priority == "A":
        return "semana de tapering (válida A)"
    if days_to_next <= 14 and priority == "A":
        return "pre-competencia (reducción de carga)"
    if days_to_next <= 4 and priority == "B":
        return "pre-competencia (mini-tapering B)"

    # Entre válidas — mesociclo de desarrollo
    if today <= date(2026, 3, 31):
        return "mesociclo de base (primer trimestre)"
    if today <= date(2026, 6, 30):
        return "mesociclo de construcción (segundo trimestre)"
    if today <= date(2026, 9, 30):
        return "mesociclo de desarrollo (tercer trimestre)"
    return "mesociclo de mantenimiento (cuarto trimestre)"


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


async def build_aggregate_context(
    db: AsyncSession,
    club_id: int,
    selected_athlete_ids: list[int],
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Construye el contexto agregado para los prompts del asistente.

    PRIVACIDAD (Ley 1581 — menores):
    - Carga `birth_date` únicamente para calcular age_decimal.
    - Descarta IDs y nombre tras calcular los conteos.
    - El dict retornado NUNCA contiene ningún dato identificante.

    Args:
        db: Sesión async de la BD.
        club_id: ID del club para verificar membership.
        selected_athlete_ids: Lista de IDs preseleccionados por el coach.
            Si está vacía, age_mix se omite (dict vacío).
        today: Fecha de referencia (por defecto: date.today()).

    Returns:
        Dict con claves: today, age_mix, total_athletes, season_phase,
        days_to_next_race, next_race_priority.
        Seguro para pasar directamente al PromptRegistry.render().
    """
    ref_date = today or date.today()

    age_mix: dict[str, int] = {}
    total_athletes = 0

    if selected_athlete_ids:
        # Cargar solo birth_date de atletas que pertenezcan al club
        # (defensa: el coach no puede pedir atletas de otro club)
        result = await db.execute(
            select(Athlete.birth_date).where(
                Athlete.id.in_(selected_athlete_ids),
                Athlete.club_id == club_id,
            )
        )
        birth_dates = list(result.scalars().all())

        # Calcular conteos — IDs y nombres descartados aquí
        for bd in birth_dates:
            age = compute_age_decimal(bd, ref_date)
            group = _age_group(age)
            age_mix[group] = age_mix.get(group, 0) + 1
            total_athletes += 1

    days_to_next, next_priority = _race_proximity(ref_date)
    phase = _season_phase(ref_date)

    context: dict[str, Any] = {
        "today": ref_date.isoformat(),
        "age_mix": age_mix,
        "total_athletes": total_athletes,
        "season_phase": phase,
        "days_to_next_race": days_to_next,
        "next_race_priority": next_priority,
    }

    # Log counts only — never ids/names (Ley 1581 + ai_log_prompts=false)
    logger.debug(
        "session_assistant.context built club_id=%d total_athletes=%d age_mix=%s "
        "days_to_next_race=%s next_race_priority=%s",
        club_id,
        total_athletes,
        age_mix,
        days_to_next,
        next_priority,
    )

    return context
