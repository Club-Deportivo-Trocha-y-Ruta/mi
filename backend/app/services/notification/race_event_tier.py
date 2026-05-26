"""Mapeo de tier de prioridad de carrera (A/B/C/CD) por temporada.

Contexto
========
El equipo decidió (cierre Family Relations Track) que NO toda válida aprobada
genera email a padres. Solo las válidas de máxima prioridad (tier ``A`` y
``CD``) disparan email. Las tier ``B`` y ``C`` quedan en notificación in-app
+ inclusión en el boletín mensual existente (Fase 1.8).

Fuente de verdad
================
El calendario competitivo vive en ``CLAUDE.md`` (raíz del proyecto). El modelo
``RaceEvent`` NO tiene un campo ``tier`` persistido — el único proxy parcial
es ``is_championship`` (True ⇒ CD). Para el resto debemos derivarlo desde
``(season, sequence_number)``.

Cuando se agreguen temporadas nuevas, basta con añadir una entrada al dict
``_CALENDAR_TIERS`` con el mismo formato. Si una válida no está mapeada se
retorna ``RaceTier.UNKNOWN`` y el dispatcher hace fallback conservador (no
envía email).

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


# ---------------------------------------------------------------------------
# Calendario por (season_year, sequence_number) → tier
# ---------------------------------------------------------------------------
# Fuente: CLAUDE.md sección "Calendario Copa Valle 2026".
# La convención `sequence_number=99` se reserva para Campeonato Departamental
# en `race_event.py` (design §3.2). Aquí lo mapeamos a `CD` adicionalmente
# por explicitud — el dict no es la única señal: `is_championship=True` también
# lo fuerza (ver `_tier_from_event`).
_CALENDAR_TIERS: dict[tuple[int, int], RaceTier] = {
    # Temporada 2026 — Copa Valle
    (2026, 1): RaceTier.UNKNOWN,  # I  31-ene Sevilla — ya completada, sin clasif
    (2026, 2): RaceTier.UNKNOWN,  # II 28-feb Ginebra — ya completada, sin clasif
    (2026, 3): RaceTier.C,        # III 19-abr La Cumbre (diagnóstica)
    (2026, 4): RaceTier.A,        # IV  17-may Cali (A)
    (2026, 99): RaceTier.CD,      # CD  26-jun Ginebra (Cto. Departamental)
    (2026, 5): RaceTier.B,        # V   01-ago Palmira (B)
    (2026, 6): RaceTier.A,        # VI  12-sep Roldanillo (A)
    (2026, 7): RaceTier.B,        # VII 18-oct Yumbo (B)
}


def _tier_from_event(event: "RaceEvent", series: "RaceSeries | None" = None) -> RaceTier:
    """Deriva el tier desde un ``RaceEvent``.

    Reglas (en orden de prioridad):

    1. ``is_championship=True`` ⇒ ``CD`` (señal explícita en DB).
    2. ``sequence_number == 99`` ⇒ ``CD`` (convención design §3.2).
    3. Lookup en ``_CALENDAR_TIERS`` por ``(season_year, sequence_number)``.
    4. Fallback ``UNKNOWN`` con log warning.
    """
    # Señal explícita: CD siempre tiene prioridad sobre el lookup numérico.
    if getattr(event, "is_championship", False):
        return RaceTier.CD
    if event.sequence_number == 99:
        return RaceTier.CD

    season_year: int | None = None
    if series is not None:
        season_year = getattr(series, "season_year", None)
    elif getattr(event, "series", None) is not None:
        season_year = getattr(event.series, "season_year", None)

    if season_year is None:
        logger.warning(
            "race_event_tier: season_year no disponible para event_id=%s — "
            "fallback UNKNOWN. ¿La relación 'series' fue cargada con selectinload?",
            event.id,
        )
        return RaceTier.UNKNOWN

    tier = _CALENDAR_TIERS.get((int(season_year), int(event.sequence_number)))
    if tier is None:
        logger.warning(
            "race_event_tier: combinación (season=%s, valida=%s) no mapeada en "
            "_CALENDAR_TIERS — fallback UNKNOWN. Añadir entrada al calendario "
            "si es una temporada nueva.",
            season_year,
            event.sequence_number,
        )
        return RaceTier.UNKNOWN

    return tier


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
