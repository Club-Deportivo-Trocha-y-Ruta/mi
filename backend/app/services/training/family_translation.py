"""Traducción del análisis IA v3 (feature 037) a lenguaje de familia.

Implementa ``specs/038-newsletter-bitacora-redesign/spec.md`` §AC-3.1/AC-3.2
y ``data-model.md`` §2 (``FamilyInsightInput``).

Por qué un filtro determinista antes de cualquier LLM
=======================================================
``InsightV3`` (``app.services.race.insight_v3``) es el análisis completo que
lee el coach: incluye la lectura relativa al pelotón (``field_reading``),
observaciones de dominio ``field``, la pregunta abierta para el coach,
señales a vigilar y vacíos de datos. Nada de eso es apto para una familia —
compara al deportista contra sus compañeros de club, algo que el club NUNCA
expone fuera del panel del coach (spec.md §problem 5).

``filter_for_family`` aplica ese recorte con reglas fijas, sin LLM de por
medio, antes de que el hallazgo llegue al paso de paráfrasis (T201). Sólo
sobrevive el titular (``headline``) y la acción elegible de mayor
prioridad — nunca las observaciones descartadas ni ``coach_question`` /
``watch_signals`` / ``data_gaps`` / ``derived_from``.

``select_insight`` resuelve, para un boletín dado, cuál ``AthleteAiInsight``
(de los adjuntados manualmente por el coach vía
``selected_race_insight_ids``) es apto como fuente de esa traducción: debe
pertenecer al atleta del boletín, seguir activo (no reemplazado por una
versión más nueva), tener ``structured_json`` (ser v3) y su evento debe
caer en el mes del boletín. Si el atleta no tiene consentimiento IA, la
función retorna ``None`` sin tocar la base de datos — nunca se llama a un
proveedor de IA desde este módulo.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.athlete_newsletter import AthleteMonthlyNewsletter
from app.services.race.insight_v3 import ActionV3, EvidenceDomain, InsightV3, Observation, Priority

__all__ = ["FamilyInsightInput", "filter_for_family", "select_insight"]

logger = logging.getLogger(__name__)


class FamilyInsightInput(BaseModel):
    """Lo único que puede salir de un ``InsightV3`` hacia la familia.

    ``data-model.md`` §2: "nothing else leaves the InsightV3". ``valida_label``
    no es un campo de ``InsightV3`` (no hay nombre de carrera ni número de
    válida ahí) — el llamador que sí conoce el evento (``select_insight`` /
    T201, con acceso a ``race_events``) lo provee explícitamente; por eso
    tiene un valor por defecto vacío en vez de resolverse aquí.
    """

    model_config = ConfigDict(extra="forbid")

    headline: str
    action_text: str
    action_category: str
    valida_label: str = ""


# Prioridad → rango numérico para elegir la acción "más alta". ``low`` no
# aparece: se descarta antes de llegar a este punto (AC-3.2).
_PRIORITY_RANK: dict[Priority, int] = {
    Priority.HIGH: 2,
    Priority.MED: 1,
}


def _eligible_observations(insight: InsightV3) -> list[Observation]:
    """Observaciones que podrían llegar a la familia: descarta dominio ``field``.

    AC-3.2 lista esta regla junto a las demás del recorte determinista.
    Ninguna observación —elegible o no— viaja hoy en ``FamilyInsightInput``
    (T201 sólo usa el titular + la acción), pero la regla se deja como
    función pura y testeable en caso de que un consumidor futuro necesite
    la lista filtrada (p. ej. grounding del bloque de paráfrasis).
    """
    return [obs for obs in insight.observations if obs.domain != EvidenceDomain.FIELD]


def _eligible_actions(insight: InsightV3) -> list[ActionV3]:
    """Acciones que podrían llegar a la familia: descarta prioridad ``low``."""
    return [action for action in insight.actions if action.priority != Priority.LOW]


def _best_action(actions: list[ActionV3]) -> ActionV3 | None:
    """Acción de mayor prioridad; en empate, la primera en orden de aparición.

    ``max()`` sólo reemplaza el máximo actual cuando encuentra un rango
    estrictamente mayor, así que en un empate conserva la primera ocurrencia
    — exactamente la regla pedida ("si hay empate toma la primera en orden
    de aparición").
    """
    if not actions:
        return None
    best = actions[0]
    best_rank = _PRIORITY_RANK.get(best.priority, 0)
    for action in actions[1:]:
        rank = _PRIORITY_RANK.get(action.priority, 0)
        if rank > best_rank:
            best = action
            best_rank = rank
    return best


def filter_for_family(insight: InsightV3, valida_label: str = "") -> FamilyInsightInput | None:
    """Recorte determinista pre-LLM (AC-3.2).

    Descarta ``field_reading``, ``coach_question``, ``watch_signals``,
    ``data_gaps`` y ``derived_from`` de forma implícita (nunca se leen);
    descarta explícitamente toda observación de dominio ``field`` y toda
    acción de prioridad ``low``. Si no queda ninguna acción elegible,
    retorna ``None`` — no hay lectura de analista publicable para la
    familia ese mes.

    Args:
        insight: análisis v3 ya aprobado por el coach.
        valida_label: etiqueta legible de la carrera (p. ej. "Válida IV —
            Cali", ver ``app.services.race.race_labels.build_race_label``);
            no se deriva de ``insight`` porque no vive ahí. Por defecto
            vacía cuando el llamador no la provee.

    Returns:
        ``FamilyInsightInput`` con el titular y la acción elegida, o
        ``None`` si no hay acción apta para familia.
    """
    action = _best_action(_eligible_actions(insight))
    if action is None:
        return None
    return FamilyInsightInput(
        headline=insight.headline,
        action_text=action.text,
        action_category=getattr(action.category, "value", action.category),
        valida_label=valida_label,
    )


def _is_eligible_row(insight: AthleteAiInsight, year: int, month: int) -> bool:
    """Elegibilidad de una fila ``athlete_ai_insights`` como fuente familiar.

    - ``is_active == 1``: sentinel de "activo/publicable" (ver docstring
      del modelo). Un insight reemplazado queda con ``is_active=NULL``.
    - ``superseded_by_insight_id is None``: chequeo defensivo redundante
      con lo anterior (el versionado BE-1 garantiza que un reemplazado
      pierde ``is_active``, pero no cuesta nada verificarlo también aquí).
    - ``structured_json is not None``: sólo insights v3 tienen traducción
      familiar — v1/v2 no tienen esta estructura.
    - El evento asociado (``event_id``) debe caer en el año/mes del
      boletín; sin evento no hay forma de anclar el insight a ese mes.
    """
    if insight.is_active != 1:
        return False
    if insight.superseded_by_insight_id is not None:
        return False
    if insight.structured_json is None:
        return False
    event = insight.event
    if event is None or event.event_date is None:
        return False
    return event.event_date.year == year and event.event_date.month == month


async def select_insight(
    db: AsyncSession,
    newsletter: AthleteMonthlyNewsletter,
    athlete_has_ai_consent: bool,
) -> tuple[int, InsightV3] | None:
    """Primer ``AthleteAiInsight`` apto de ``newsletter.selected_race_insight_ids``.

    Recorre la lista en el orden guardado por el coach (el estudio permite
    reordenarla — ``AthleteNewsletterPatch``) y retorna el primero que
    cumpla ``_is_eligible_row``. Sin consentimiento IA del atleta, retorna
    ``None`` de inmediato sin ejecutar ninguna consulta — este módulo nunca
    llama a un proveedor de IA ni necesita tocar la base de datos si no hay
    consentimiento.

    Returns:
        ``(insight_id, InsightV3)`` del primer insight elegible, o ``None``
        si ninguno califica (incluida la lista vacía).
    """
    if not athlete_has_ai_consent:
        return None

    ids = list(newsletter.selected_race_insight_ids or [])
    if not ids:
        return None

    result = await db.execute(
        select(AthleteAiInsight)
        .where(
            AthleteAiInsight.id.in_(ids),
            AthleteAiInsight.athlete_id == newsletter.athlete_id,
        )
        .options(selectinload(AthleteAiInsight.event))
    )
    rows_by_id = {row.id: row for row in result.scalars().all()}

    for insight_id in ids:
        row = rows_by_id.get(insight_id)
        if row is None:
            continue
        if not _is_eligible_row(row, newsletter.year, newsletter.month):
            continue
        try:
            return insight_id, InsightV3.model_validate(row.structured_json)
        except ValidationError:
            # structured_json corrupto o de un contrato anterior — se salta
            # al siguiente id en vez de romper la generación del boletín.
            logger.warning(
                "family_translation.select_insight: structured_json inválido "
                "para insight_id=%s — se descarta",
                insight_id,
            )
            continue

    return None
