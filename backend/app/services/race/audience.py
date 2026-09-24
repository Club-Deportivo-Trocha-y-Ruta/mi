"""Política única de audiencia para métricas de carrera (feature 045).

Contrato: ``specs/045-competitions-one-place/data-model.md`` §1/§2/§3 y
``contracts/api.md``. La brecha vs. 1.ª posición y la brecha vs. podio son
**solo del coach**: a la familia nunca le llegan, ni como valor ni como
``null`` — las claves se **omiten** del payload (no basta con ocultarlas en
la UI, el dato de un menor comparado contra el ganador no debe viajar).

Diseño (Strategy)
------------------
Una :class:`Audience` se resuelve una sola vez por request
(:func:`audience_for_role`) y cada audiencia tiene su :class:`AudiencePolicy`
declarativa: qué campos se omiten y qué métricas de ``/evolution`` se
rechazan. La política del coach es vacía, así que **no existe ningún**
``if role == parent`` en los consumidores: aplican la política y punto.
Agregar una audiencia nueva (p. ej. «club público») es agregar una entrada a
``_POLICIES`` — ningún consumidor cambia (abierto/cerrado).

API pública
-----------
- :class:`Audience` — ``COACH`` (coach + admin) y ``FAMILY`` (todo lo demás).
- :func:`audience_for_role` — ``UserRole`` → ``Audience`` (fail-closed).
- :data:`FAMILY_EXCLUDED_METRIC_FIELDS` — fuente única de los nombres de
  campo que la familia nunca recibe (canónicos del ``MetricSet`` + nombres
  heredados de 037/039).
- :data:`FAMILY_FORBIDDEN_EVOLUTION_METRICS` — métricas de ``/evolution`` que
  la familia no puede pedir (403).
- :func:`is_evolution_metric_allowed` — ¿puede esta audiencia pedir la métrica?
- :func:`redact_for_audience` — quita las claves excluidas de cualquier
  estructura JSON (dict/lista anidados); sirve para un ``MetricSet`` suelto.
- :func:`serialize_for_audience` — ``BaseModel`` → dict JSON ya filtrado.

Los ids de terceros no forman parte de esta política (los cubre
``third_party_guard.py``); aquí solo se decide **qué métricas** ve cada rol.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel

from app.models.user import UserRole
from app.schemas.athlete_race_analysis import EvolutionMetric

__all__ = [
    "Audience",
    "AudiencePolicy",
    "FAMILY_EXCLUDED_METRIC_FIELDS",
    "FAMILY_FORBIDDEN_EVOLUTION_METRICS",
    "audience_for_role",
    "is_evolution_metric_allowed",
    "policy_for",
    "redact_for_audience",
    "serialize_for_audience",
]


class Audience(str, Enum):
    """Quién lee la respuesta. Decide qué métricas se incluyen."""

    COACH = "coach"
    FAMILY = "family"


#: Roles con la vista completa. Cualquier otro rol (padre, atleta…) es
#: ``FAMILY`` — fail-closed: un rol nuevo nunca hereda la vista del coach.
_STAFF_ROLES: frozenset[UserRole] = frozenset({UserRole.coach, UserRole.admin})


def audience_for_role(role: UserRole) -> Audience:
    """Audiencia de un rol autenticado (el RBAC de acceso vive en
    ``services/permissions.py`` y ``dependencies.verify_athlete_access``;
    esto solo decide qué *métricas* se sirven a quien ya tiene acceso)."""
    return Audience.COACH if role in _STAFF_ROLES else Audience.FAMILY


#: ÚNICA fuente de verdad de los campos de métrica que la familia nunca
#: recibe (data-model §1, columna «Family» = never); ningún otro módulo
#: repite esta lista. Incluye los nombres canónicos del ``MetricSet``
#: (``gap_to_winner_pct``, ``gap_to_winner_ms``, ``gap_to_podium_pct``,
#: ``gap_to_podium_ms``) y los heredados que aún circulan: ``gap_pct``
#: (``EvolutionPoint`` y ``compute_field_metrics``), ``gap_to_p1_ms`` y
#: ``gap_to_p3_ms``, más ``gap_pcts`` — la serie de gap al ganador que los
#: ``charts_context`` de boletines anteriores a la 045 aún traen en la base de
#: datos (el motor actual escribe ``median_gap_pcts``, la brecha vs. mediana).
FAMILY_EXCLUDED_METRIC_FIELDS: frozenset[str] = frozenset(
    {
        "gap_to_winner_pct",
        "gap_to_winner_ms",
        "gap_to_podium_pct",
        "gap_to_podium_ms",
        "gap_pct",
        "gap_pcts",
        "gap_to_p1_ms",
        "gap_to_p3_ms",
    }
)

#: Métricas de ``GET /evolution`` que la familia no puede pedir: responden
#: 403 y ni siquiera se calculan.
FAMILY_FORBIDDEN_EVOLUTION_METRICS: frozenset[EvolutionMetric] = frozenset(
    {EvolutionMetric.PODIUM_GAP_MS}
)


@dataclass(frozen=True)
class AudiencePolicy:
    """Qué se le quita a una audiencia. Inmutable y declarativa."""

    excluded_fields: frozenset[str] = frozenset()
    forbidden_evolution_metrics: frozenset[EvolutionMetric] = frozenset()


_POLICIES: dict[Audience, AudiencePolicy] = {
    Audience.COACH: AudiencePolicy(),
    Audience.FAMILY: AudiencePolicy(
        excluded_fields=FAMILY_EXCLUDED_METRIC_FIELDS,
        forbidden_evolution_metrics=FAMILY_FORBIDDEN_EVOLUTION_METRICS,
    ),
}


def policy_for(audience: Audience) -> AudiencePolicy:
    return _POLICIES[audience]


def is_evolution_metric_allowed(metric: EvolutionMetric, audience: Audience) -> bool:
    return metric not in policy_for(audience).forbidden_evolution_metrics


def redact_for_audience(data: Any, audience: Audience) -> Any:
    """Copia de ``data`` sin las claves que la política de ``audience`` excluye.

    Recorre dicts y listas a cualquier profundidad (fail-closed: si un
    ``MetricSet`` se anida en una respuesta nueva, igual se filtra). Las
    claves se **eliminan**, no se ponen en ``None``. No muta la entrada;
    con la política vacía del coach devuelve una copia equivalente.
    """
    excluded = policy_for(audience).excluded_fields
    return _strip_keys(data, excluded)


def _strip_keys(node: Any, excluded: frozenset[str]) -> Any:
    if isinstance(node, dict):
        return {
            key: _strip_keys(value, excluded)
            for key, value in node.items()
            if key not in excluded
        }
    if isinstance(node, list):
        return [_strip_keys(item, excluded) for item in node]
    return node


def serialize_for_audience(model: BaseModel, audience: Audience) -> dict[str, Any]:
    """``model`` → dict JSON-ready ya filtrado para ``audience``.

    Pensado para devolverse en una ``JSONResponse`` desde el router:
    ``response_model`` rellenaría con ``None`` las claves ausentes, así que
    los endpoints con variante de familia serializan aquí y responden
    directamente (el ``response_model`` del decorador se conserva solo para
    OpenAPI). ``by_alias=True`` replica el comportamiento de FastAPI.
    """
    return redact_for_audience(model.model_dump(mode="json", by_alias=True), audience)
