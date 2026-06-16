"""Reglas de negocio relacionadas con el tipo de serie (cup vs championship).

Spec 014 — cup-vs-championship-series / T006.

Exports
-------
derive_event_fields_for_series(kind, requested_sequence) -> tuple[int, bool]
    Calcula (sequence_number, is_championship) según el kind de la serie.
    Para campeonatos: fuerza seq=1 e is_championship=True.
    Para copas: pasa el sequence solicitado e is_championship=False.

assert_championship_single_event(db, series) -> None
    Lanza HTTPException 409 si la serie es de tipo championship y ya tiene ≥1
    evento. Garantiza la invariante INV-2 del data-model.

Privacidad: estas funciones trabajan solo con IDs de series y conteos —
ningún campo de menores pasa por aquí.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_event import RaceEvent
from app.models.race_series import RaceSeries, RaceSeriesKind

logger = logging.getLogger(__name__)


def derive_event_fields_for_series(
    kind: RaceSeriesKind,
    requested_sequence: int | None,
) -> tuple[int, bool]:
    """Deriva ``(sequence_number, is_championship)`` según el tipo de serie.

    Rules (spec 014 / D2):
    - championship → sequence_number forced to 1, is_championship=True.
      The client-supplied sequence is ignored.
    - cup          → sequence_number=requested_sequence (caller must validate
      that it is ≥1), is_championship=False.

    Parameters
    ----------
    kind:
        Series kind (cup | championship).
    requested_sequence:
        The sequence_number the client sent. May be None for championship
        (field is optional on create). Must be a positive int for cups —
        the caller is responsible for this validation.

    Returns
    -------
    tuple[sequence_number: int, is_championship: bool]
    """
    if kind == RaceSeriesKind.championship:
        return (1, True)
    # cup
    seq = requested_sequence if requested_sequence is not None else 1
    return (seq, False)


async def assert_championship_single_event(
    db: AsyncSession,
    series: RaceSeries,
) -> None:
    """Garantiza que una serie de tipo campeonato no tenga más de un evento.

    Lanza HTTPException 409 con mensaje en es-CO si la serie ya tiene ≥1 evento.
    Para series de tipo 'cup' esta función es un no-op.

    Parameters
    ----------
    db:
        Sesión async de SQLAlchemy.
    series:
        Instancia ORM de ``RaceSeries`` ya cargada.

    Raises
    ------
    HTTPException(409) si la serie es championship y ya tiene ≥1 evento.
    """
    if series.kind != RaceSeriesKind.championship:
        return

    result = await db.execute(
        select(func.count()).where(RaceEvent.series_id == series.id)
    )
    count: int = result.scalar_one() or 0

    if count >= 1:
        logger.info(
            "series_rules_championship_guard series_id=%s existing_events=%s",
            series.id,
            count,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Un campeonato representa un único evento anual; "
                "esta serie ya tiene su evento."
            ),
        )
