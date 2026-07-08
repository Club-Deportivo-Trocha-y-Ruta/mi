"""Router ``/api/race-analysis/race-series`` — gestión de series de competencias.

Endpoints:

- ``GET  /``  — lista series con filtros opcionales (season, kind) y event_count
               calculado sin N+1 (subquery COUNT).
- ``POST /``  — crea serie; solo coach + admin; 409 si (name, season_year) duplicado;
               ``points_scheme_code`` se fija a ``copa_valle_2026`` en el servidor.

Convenciones:
- RBAC: coach + admin en escritura. Lectura también coach + admin (misma restricción
  que el resto del módulo race-analysis).
- Privacidad: series y eventos son datos públicos de la federación — no exponen PII
  de menores (Ley 1581). Logs usan solo IDs y conteos.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.race_event import RaceEvent
from app.models.race_series import RaceSeries, RaceSeriesKind
from app.models.user import User, UserRole
from app.schemas.race_series import RaceSeriesCreate, RaceSeriesListResponse, RaceSeriesRead

logger = logging.getLogger(__name__)

router = APIRouter()

_DEFAULT_POINTS_SCHEME_CODE = "copa_valle_2026"


# ---------------------------------------------------------------------------
# GET / — Listar series con event_count
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=RaceSeriesListResponse,
    summary="Listar series de competencias",
)
async def list_race_series(
    season: Optional[int] = Query(
        default=None,
        ge=2020,
        le=2100,
        description="Filtrar por año de temporada.",
    ),
    kind: Optional[RaceSeriesKind] = Query(
        default=None,
        description="Filtrar por tipo: 'cup' o 'championship'.",
    ),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(
        require_role([UserRole.admin, UserRole.coach])
    ),
) -> RaceSeriesListResponse:
    """Lista todas las series de competencias con el conteo de eventos de cada una.

    El ``event_count`` se calcula con una subquery COUNT para evitar N+1.

    Filtros opcionales:
    - ``season``: restringe a una temporada específica.
    - ``kind``: filtra por tipo de serie (cup | championship).

    Códigos de respuesta:
    - 200: lista (puede estar vacía si no hay series o no coincide el filtro).
    - 403: usuario sin rol coach o admin.
    """
    # Subquery: COUNT de eventos por serie — un único JOIN en lugar de N+1
    event_count_subq = (
        select(func.count(RaceEvent.id))
        .where(RaceEvent.series_id == RaceSeries.id)
        .correlate(RaceSeries)
        .scalar_subquery()
    )

    stmt = select(
        RaceSeries,
        event_count_subq.label("event_count"),
    )

    if season is not None:
        stmt = stmt.where(RaceSeries.season_year == season)
    if kind is not None:
        stmt = stmt.where(RaceSeries.kind == kind)

    stmt = stmt.order_by(RaceSeries.season_year.desc(), RaceSeries.name.asc())

    rows = (await db.execute(stmt)).all()

    items = [
        RaceSeriesRead(
            id=series.id,
            name=series.name,
            season_year=series.season_year,
            organizer=series.organizer,
            kind=series.kind,
            level=series.level,
            event_count=int(event_count or 0),
        )
        for series, event_count in rows
    ]

    logger.info(
        "race_series_list season=%s kind=%s total=%s",
        season,
        kind.value if kind else None,
        len(items),
    )

    return RaceSeriesListResponse(items=items, total=len(items))


# ---------------------------------------------------------------------------
# POST / — Crear serie
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=RaceSeriesRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear serie de competencias",
)
async def create_race_series(
    body: RaceSeriesCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role([UserRole.admin, UserRole.coach])
    ),
) -> RaceSeriesRead:
    """Crea una nueva serie de competencias.

    El campo ``points_scheme_code`` NO se acepta del cliente — el servidor
    lo fija en ``copa_valle_2026`` (decisión D5 del spec 014). La exclusión
    del ranking acumulado para campeonatos se controla por ``kind``, no por
    el scheme code.

    Códigos de respuesta:
    - 201: serie creada correctamente.
    - 409: ya existe una serie con el mismo nombre para la misma temporada.
    - 422: campo fuera de rango o tipo inválido.
    - 403: usuario sin rol coach o admin.
    """
    # Guard: UNIQUE(name, season_year)
    existing = await db.execute(
        select(RaceSeries).where(
            RaceSeries.name == body.name,
            RaceSeries.season_year == body.season_year,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una serie con ese nombre para la temporada.",
        )

    series = RaceSeries(
        name=body.name,
        season_year=body.season_year,
        organizer=body.organizer,
        points_scheme_code=_DEFAULT_POINTS_SCHEME_CODE,
        kind=body.kind,
        level=body.level,
    )
    db.add(series)
    await db.flush()

    logger.info(
        "race_series_create series_id=%s kind=%s user_id=%s",
        series.id,
        series.kind.value,
        current_user.id,
    )

    return RaceSeriesRead(
        id=series.id,
        name=series.name,
        season_year=series.season_year,
        organizer=series.organizer,
        kind=series.kind,
        level=series.level,
        event_count=0,
    )
