"""Mapeo de tier de prioridad de carrera (A/B/C/CD) por temporada.

Contexto
========
El equipo decidió (cierre Family Relations Track) que NO toda válida aprobada
genera email a padres. Solo las válidas de máxima prioridad (tier ``A`` y
``CD``) disparan email. Las tier ``B`` y ``C`` quedan en notificación in-app
+ inclusión en el boletín mensual existente (Fase 1.8).

Fuente de verdad
================
Hotfix "identidad de válida" (2026-09-16, ver
``~/.claude/plans/multicopa-identidad-valida.md``): el tier ya NO se deriva
de un dict hardcodeado por ``(season, sequence_number)`` — ese calendario
solo conocía Copa Valle 2026 y colisionaba en cuanto otra copa (ej. Copa
Let's Go) reutilizaba el mismo ``sequence_number`` en la misma temporada
(exactamente el bug: una válida de Let's Go terminó heredando el tier ``A``
de la Válida IV de Copa Valle y disparó email a padres indebidamente).

``RaceEvent.priority`` (``app.models.race_event.RaceEventPriority``, columna
nullable) es ahora el dato por evento. ``NULL`` significa "sin prioridad
asignada" → ``RaceTier.UNKNOWN`` → sin email (fallback conservador) hasta
que el coach la asigne explícitamente vía ``PATCH /race-events/{id}``. Solo
las válidas de Copa Valle 2026 vienen backfilleadas por la migración
``c2314ccd7927``; el resto (incluida cualquier copa nueva) parte en NULL.

Privacidad
==========
Este módulo NO toca PII. Solo lee atributos públicos de ``RaceEvent``
(``sequence_number``, ``series_id``, ``is_championship``) y constantes.
Nada que loggear con cuidado.
"""
from __future__ import annotations

import enum
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.race_event import RaceEvent
    from app.models.race_series import RaceSeries

logger = logging.getLogger(__name__)


class RaceTier(str, enum.Enum):
    """Prioridad/tier de una válida según planificación anual del club.

    - ``A``  → válida tipo A (tapering completo 5-7 días). Email a padres.
    - ``CD`` → Campeonato Departamental. Email a padres.
    - ``B``  → válida tipo B (mini-tapering 3-4 días). Solo in-app.
    - ``C``  → válida tipo C (diagnóstica, sin tapering). Solo in-app.
    - ``UNKNOWN`` → no mapeada en calendario. Sin email (fallback conservador).
    """

    A = "A"
    CD = "CD"
    B = "B"
    C = "C"
    UNKNOWN = "unknown"


#: Tiers que SI disparan email a padres tras aprobación de insight.
TIERS_WITH_PARENT_EMAIL: frozenset[RaceTier] = frozenset({RaceTier.A, RaceTier.CD})


def _tier_from_event(event: "RaceEvent", series: "RaceSeries | None" = None) -> RaceTier:
    """Deriva el tier desde un ``RaceEvent``.

    Reglas (en orden de prioridad — hotfix identidad de válida, 2026-09-16):

    1. ``is_championship=True`` ⇒ ``CD`` (señal explícita en DB).
    2. ``sequence_number == 99`` ⇒ ``CD`` (convención design §3.2).
    3. ``event.priority`` (``RaceEventPriority``) cuando está asignado.
    4. Fallback ``UNKNOWN`` con log warning — sin prioridad asignada.

    ``series`` se acepta por compatibilidad de firma con callers existentes
    (evita un lazy-load si ya lo tienen a mano) pero ya no participa en la
    derivación del tier — el antiguo lookup por ``(season_year,
    sequence_number)`` colisionaba entre copas distintas con el mismo
    ``sequence_number`` en la misma temporada.
    """
    # Señal explícita: CD siempre tiene prioridad sobre `priority`.
    if getattr(event, "is_championship", False):
        return RaceTier.CD
    if event.sequence_number == 99:
        return RaceTier.CD

    priority = getattr(event, "priority", None)
    if priority is None:
        logger.warning(
            "race_event_tier: event_id=%s sin priority asignada — fallback "
            "UNKNOWN (sin email a padres). Asignar vía PATCH /race-events/{id} "
            "si esta válida debe notificar.",
            event.id,
        )
        return RaceTier.UNKNOWN

    return RaceTier(priority.value)


def get_race_tier(event: "RaceEvent", series: "RaceSeries | None" = None) -> RaceTier:
    """API pública del módulo. Retorna el ``RaceTier`` de un evento.

    Args:
        event: instancia de ``RaceEvent`` (debe tener ``series`` cargada via
            ``selectinload`` si ``series`` se pasa como ``None``).
        series: opcional, evita un lazy-load adicional cuando el caller ya tiene
            la serie a mano. Si se omite, se usa ``event.series``.

    Returns:
        ``RaceTier`` (nunca ``None`` — siempre cae a ``UNKNOWN``).
    """
    return _tier_from_event(event, series=series)


def should_email_parents(tier: RaceTier) -> bool:
    """Helper de decisión: ¿este tier dispara email a padres tras aprobación?"""
    return tier in TIERS_WITH_PARENT_EMAIL


__all__ = [
    "RaceTier",
    "TIERS_WITH_PARENT_EMAIL",
    "get_race_tier",
    "should_email_parents",
]
