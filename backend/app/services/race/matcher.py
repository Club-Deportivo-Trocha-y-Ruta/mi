"""Matching fuzzy de competidores observados en PDFs vs atletas registrados.

Convención (workflow.md §4.1, design.md §4.3):
- Solo se invoca por el ingestor cuando ``is_trocha_y_ruta(competitor.club)`` —
  para corredores externos no tiene sentido buscar en el roster del club.
- Devuelve top-3 candidatos con score >= threshold; **el coach confirma
  siempre** la asignación. El matcher nunca auto-asigna ``athlete_id`` en DB
  (eso queda en manos del flujo interactivo del CLI Paso 6).
- Score base: ``rapidfuzz.fuzz.token_set_ratio`` sobre los nombres normalizados.
  Boost configurable cuando la edad calculada del atleta cabe en el rango de
  la categoría observada.

El matcher es puro: no toca DB, no muta entrada. Acepta una lista pre-cargada
de ``Athlete`` (el caller hace el ``select(Athlete).where(club_id=...)``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Iterable, Optional

from rapidfuzz import fuzz

from app.services.race.normalizer import normalize_name

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.race_category import RaceCategory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclass de salida
# ---------------------------------------------------------------------------


@dataclass
class MatchCandidate:
    """Un candidato a match entre competidor PDF y atleta registrado.

    - ``score`` está acotado a ``[0, 100]`` post-boost (los boosts no
      empujan por encima del cap, ej. 98 + 5 = 100).
    - ``reason`` describe brevemente por qué entró al top-3, útil para que el
      coach decida en el flujo interactivo. Valores observables:
        - ``"name_only"``         — sin info para boost (sin birth_date o sin categoría).
        - ``"name+age_compat"``   — boost aplicado porque la edad cabe en el rango.
        - ``"name+age_incompat"`` — edad calculada NO cabe en rango (penalización suave: sin boost).
    """

    athlete_id: int
    full_name: str
    score: float
    age_decimal: Optional[float]
    reason: str


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Score máximo posible (rapidfuzz devuelve 0..100). Los boosts se clipean aquí.
_SCORE_CAP: float = 100.0

#: Tolerancia al rango etario de la categoría: la edad calculada del atleta
#: debe estar en ``[age_min, age_max + AGE_TOLERANCE]``. Razón: las categorías
#: se asignan por edad cumplida al **inicio** de temporada, pero los atletas
#: van envejeciendo durante el año (un INF_A puede tener 12.4 años en
#: diciembre aunque la categoría sea "9-12"). 0.5 años cubre ese drift.
AGE_TOLERANCE: float = 0.5


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _calc_age_decimal(birth_date: Optional[date], reference: date) -> Optional[float]:
    """Edad decimal del atleta a la ``reference`` (años con 1 decimal).

    Si ``birth_date`` es None retorna None (atleta sin fecha registrada).
    Usa el delta exacto en días dividido por 365.25 para promediar bisiestos.
    """
    if birth_date is None:
        return None
    days = (reference - birth_date).days
    if days < 0:
        return None
    return round(days / 365.25, 2)


def _age_compatible_with_category(
    age_decimal: Optional[float],
    category: Optional["RaceCategory"],
    tolerance: float = AGE_TOLERANCE,
) -> Optional[bool]:
    """¿La edad cabe en el rango de la categoría?

    Retorna:
    - ``None`` si falta información (sin age_decimal o sin categoría).
    - ``True`` si ``age_min - tolerance <= age <= age_max + tolerance``.
    - ``False`` si está fuera del rango.

    Categorías abiertas (``age_min=None`` o ``age_max=None``) se tratan como
    ``-inf`` / ``+inf`` respectivamente — ``PROMO`` y ``ELITE_M`` sin tope
    superior compatibilizan con cualquier adulto.
    """
    if age_decimal is None or category is None:
        return None
    age_min = category.age_min if category.age_min is not None else -1e9
    age_max = category.age_max if category.age_max is not None else 1e9
    return (age_min - tolerance) <= age_decimal <= (age_max + tolerance)


def _full_name_of(athlete: "Athlete") -> str:
    """Concatena ``first_name`` + ``last_name`` del athlete con un espacio."""
    parts = []
    if getattr(athlete, "first_name", None):
        parts.append(athlete.first_name)
    if getattr(athlete, "last_name", None):
        parts.append(athlete.last_name)
    return " ".join(parts).strip()


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def match_athletes(
    competitor_name: str,
    competitor_club: str,
    competitor_category: Optional["RaceCategory"] = None,
    athletes: Iterable["Athlete"] = (),
    *,
    threshold: float = 90.0,
    boost_age_match: float = 5.0,
    reference_date: Optional[date] = None,
) -> list[MatchCandidate]:
    """Calcula top-3 candidatos de match para un competidor TyR del PDF.

    Args:
        competitor_name: Nombre completo del competidor tal como aparece en
            el PDF (se normaliza internamente).
        competitor_club: Club tal como aparece en el PDF. **No** se valida
            como TyR aquí — esa decisión la toma el ingestor antes de invocar
            este matcher (regla del proyecto: nombres con ``is_trocha_y_ruta``
            no se persisten automáticamente, el coach confirma).
        competitor_category: ``RaceCategory`` opcional inferida del header
            del PDF. Si se pasa junto con ``athletes`` con ``birth_date``,
            aplica boost a candidatos cuya edad calza con ``[age_min, age_max+0.5]``.
        athletes: Lista (o cualquier iterable) de ``Athlete`` candidatos.
            El caller filtra previamente por ``club_id`` (no lo hace el matcher).
        threshold: Score mínimo (0..100) para incluir candidato. Default 90.
        boost_age_match: Bonus al score cuando la edad calza. Default +5.
            Capa al ``_SCORE_CAP`` (100).
        reference_date: Fecha a la cual calcular la edad del atleta. Si None,
            usa ``date.today()``. En producción debería pasarse la fecha del
            evento para evitar dependencia del wall clock en backfill.

    Returns:
        Lista ordenada descendente por score, con máximo 3 elementos. Vacía
        si ningún candidato alcanza ``threshold`` o ``athletes`` es vacío.

    Notas:
    - **No** logguea nombres completos: solo cardinalidad y score.
    - **No** muta los ``Athlete`` recibidos.
    - El `competitor_club` se acepta como parámetro para coherencia futura
      (ej. desempatar homónimos por club textual), pero la implementación
      actual no lo usa para el score — el nombre es la señal principal.
    """
    del competitor_club  # reservado para futuro desempate por club; no usado hoy
    ref = reference_date or date.today()
    normalized_query = normalize_name(competitor_name)
    if not normalized_query:
        return []

    candidates: list[MatchCandidate] = []
    for athlete in athletes:
        full_name = _full_name_of(athlete)
        if not full_name:
            continue
        normalized_athlete = normalize_name(full_name)
        if not normalized_athlete:
            continue

        base_score = float(fuzz.token_set_ratio(normalized_query, normalized_athlete))
        age_decimal = _calc_age_decimal(
            getattr(athlete, "birth_date", None), ref
        )
        compat = _age_compatible_with_category(age_decimal, competitor_category)

        if compat is True:
            score = min(base_score + boost_age_match, _SCORE_CAP)
            reason = "name+age_compat"
        elif compat is False:
            score = base_score
            reason = "name+age_incompat"
        else:
            score = base_score
            reason = "name_only"

        if score < threshold:
            continue

        candidates.append(
            MatchCandidate(
                athlete_id=athlete.id,
                full_name=full_name,
                score=score,
                age_decimal=age_decimal,
                reason=reason,
            )
        )

    # Orden descendente estable: score primero, después athlete_id para
    # determinismo en empates (importante para tests).
    candidates.sort(key=lambda c: (-c.score, c.athlete_id))
    top = candidates[:3]
    logger.debug(
        "match_athletes | candidates_total=%d top=%d threshold=%.1f",
        len(candidates),
        len(top),
        threshold,
    )
    return top
