"""Grounding helpers para el lanzamiento de análisis (feature 011).

Resuelven los dos valores que los routers inyectan en ``initial_state`` para
que el grafo analice con datos reales (no defaults):

- ``ltad_group_from_age``: mapeo edad cronológica → grupo LTAD. Reutiliza la
  misma regla que el resto del backend (≤12 bambino, 13-15 juvenil, else junior).
- ``latest_maturation_status``: fase madurativa del último registro
  antropométrico del atleta (por ``evaluation_date``). ``None`` cuando no hay
  registros → el prompt no afirma fase madurativa (FR-007).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.models.anthropometry import AnthropometricRecord
from app.services.race.schemas import LTADGroup

logger = logging.getLogger(__name__)


def ltad_group_from_age(age_decimal: float) -> LTADGroup:
    """Mapea edad cronológica decimal → :class:`LTADGroup`.

    Regla idéntica a la del path season_summary (athlete_race_analysis.py):
    se compara sobre la edad en años enteros (floor), ≤12 → bambino,
    13-15 → juvenil, else → junior. Una niña de 12.7 años es bambino.
    """
    age = int(age_decimal)
    if age <= 12:
        return LTADGroup.BAMBINO
    if age <= 15:
        return LTADGroup.JUVENIL
    return LTADGroup.JUNIOR


async def latest_maturation_status(db: Any, athlete_id: int) -> str | None:
    """Devuelve la fase madurativa del último registro antropométrico.

    Returns:
        El valor string del enum ``MaturationStatus`` (``Pre-PHV`` /
        ``Circa-PHV`` / ``Post-PHV``) del registro más reciente por
        ``evaluation_date``, o ``None`` si el atleta no tiene registros (o si
        la consulta falla — la ausencia nunca se presenta como un default).
    """
    try:
        result = await db.execute(
            select(AnthropometricRecord)
            .where(AnthropometricRecord.athlete_id == athlete_id)
            .order_by(AnthropometricRecord.evaluation_date.desc())
            .limit(1)
        )
        record = result.scalar_one_or_none()
    except Exception:  # noqa: BLE001
        logger.warning(
            "latest_maturation_status: consulta falló para atleta %d; "
            "se asume sin registro (None).",
            athlete_id,
            exc_info=True,
        )
        return None

    if record is None:
        return None
    status = record.maturation_status
    return status.value if hasattr(status, "value") else status


async def load_forbidden_names(
    db: Any, athlete_id: int, *, nickname: str | None = None
) -> list[str]:
    """Carga los nombres reales a prohibir en los guardrails/scrubbing.

    Reúne: el ``full_name`` del usuario-atleta, su ``nickname`` (si se provee) y
    los ``full_name`` de los padres/acudientes vinculados. Estos NUNCA van al
    prompt — solo a los guardrails post-generación y al scrub de
    ``weather_notes`` (feature 011). Best-effort: si la consulta falla devuelve
    lo acumulado (o lista vacía), nunca rompe el lanzamiento.
    """
    names: list[str] = []
    try:
        from sqlalchemy import select as sa_select

        from app.models.athlete import Athlete as AthleteModel, ParentAthlete
        from app.models.user import User as UserModel

        fn_rows = await db.execute(
            sa_select(UserModel.full_name).where(
                UserModel.id
                == (
                    sa_select(AthleteModel.user_id)
                    .where(AthleteModel.id == athlete_id)
                    .scalar_subquery()
                )
            )
        )
        fn_row = fn_rows.scalar_one_or_none()
        if fn_row:
            names.append(str(fn_row))

        if nickname:
            names.append(str(nickname))

        parent_rows = await db.execute(
            sa_select(UserModel.full_name)
            .join(ParentAthlete, UserModel.id == ParentAthlete.parent_id)
            .where(ParentAthlete.athlete_id == athlete_id)
        )
        for prow in parent_rows.scalars().all():
            if prow:
                names.append(str(prow))
    except Exception:  # noqa: BLE001
        logger.warning(
            "load_forbidden_names: no se pudieron cargar nombres para atleta %d; "
            "el scrubbing usará la lista parcial acumulada.",
            athlete_id,
            exc_info=True,
        )
    return names


__all__ = [
    "ltad_group_from_age",
    "latest_maturation_status",
    "load_forbidden_names",
]
