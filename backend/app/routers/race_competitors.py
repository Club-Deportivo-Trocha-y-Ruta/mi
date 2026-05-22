"""Router ``/api/race-competitors/*`` — enlace retroactivo competidor↔atleta.

Endpoints:

| Método | Path                                          | Propósito                                  |
|--------|-----------------------------------------------|--------------------------------------------|
| GET    | ``/?unlinked=true&club_filter=trocha&season=N``| Lista competidores ``athlete_id IS NULL``  |
| GET    | ``/{competitor_id}/suggestions``              | Top-N atletas sugeridos (fuzzy)            |
| POST   | ``/{competitor_id}/link``                     | Enlazar + propagar a race_results          |
| DELETE | ``/{competitor_id}/link``                     | Deshacer enlace + propagar NULL            |

RBAC: ``coach`` + ``admin``. Padres bloqueados (403).

Audit:
- ``linked_by_user_id = current_user.id`` se persiste en cada link.
- Logs ``logger.info`` con ``competitor_id``, ``athlete_id``, ``user_id``,
  ``results_propagated``. **Nunca** loggear nombres (privacidad menores).

Idempotencia:
- ``POST /{id}/link`` con el MISMO athlete_id que ya tiene el competitor →
  200 + ``already_linked=true``.
- ``POST /{id}/link`` con athlete_id DISTINTO al actual → 409 Conflict.
- ``DELETE /{id}/link`` sobre un competitor no enlazado → 200 +
  ``was_linked=false`` (más útil que 404 para clientes naïve).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.club import ClubRole
from app.models.user import User, UserRole
from app.schemas.race_competitor import (
    AthleteSuggestion,
    CompetitorLinkRequest,
    CompetitorLinkResponse,
    CompetitorSuggestion,
    CompetitorSuggestionsByNameResponse,
    CompetitorSuggestionsResponse,
    CompetitorUnlinkResponse,
    UnlinkedCompetitorItem,
    UnlinkedCompetitorsResponse,
)
from app.services.race.competitor_linking import (
    AthleteNotFoundError,
    CompetitorAlreadyLinkedError,
    CompetitorNotFoundError,
    CompetitorSuggestionView,
    SuggestionView,
    link_competitor_to_athlete,
    list_unlinked_competitors,
    suggest_athletes_for_competitor,
    suggest_competitors_for_new_athlete,
    unlink_competitor,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coach_club_ids(user: User) -> set[int]:
    """Devuelve los club_ids donde el usuario es coach."""
    return {
        m.club_id
        for m in (user.club_memberships or [])
        if m.role_in_club == ClubRole.coach
    }


def _to_suggestion_schema(s: SuggestionView) -> AthleteSuggestion:
    return AthleteSuggestion(
        athlete_id=s.athlete_id,
        full_name=s.full_name,
        score=s.score,
        reason=s.reason,
    )


def _to_competitor_suggestion_schema(
    s: CompetitorSuggestionView,
) -> CompetitorSuggestion:
    return CompetitorSuggestion(
        competitor_id=s.competitor_id,
        display_name=s.display_name,
        club_text=s.club_text,
        score=s.score,
        reason=s.reason,
        results_count=s.results_count,
        seasons=s.seasons,
    )


async def _ensure_athlete_in_coach_clubs(
    db: AsyncSession, athlete_id: int, current_user: User
) -> None:
    """Coach solo puede linkar a athletes de SUS clubes; admin bypass.

    Si el athlete no existe lanza ``AthleteNotFoundError`` (lo maneja el caller).
    """
    if current_user.role == UserRole.admin:
        return
    from sqlalchemy import select

    from app.models.athlete import Athlete

    result = await db.execute(select(Athlete).where(Athlete.id == athlete_id))
    athlete = result.scalar_one_or_none()
    if athlete is None:
        raise AthleteNotFoundError(athlete_id)
    coach_clubs = _coach_club_ids(current_user)
    if athlete.club_id not in coach_clubs:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "No tienes acceso a este atleta (no pertenece a tus clubes)."
            ),
        )


# ---------------------------------------------------------------------------
# GET /api/race-competitors/  — listado
# ---------------------------------------------------------------------------


@router.get("/", response_model=UnlinkedCompetitorsResponse)
async def list_competitors(
    unlinked: bool = Query(
        default=True,
        description=(
            "Si True, lista solo competitors con athlete_id IS NULL. "
            "Otros valores (linked) no soportados en v1."
        ),
    ),
    club_filter: Optional[str] = Query(
        default=None,
        description=(
            "Filtro de club. 'trocha' aplica is_trocha_y_ruta() sobre club_text."
        ),
    ),
    season: Optional[int] = Query(
        default=None,
        ge=2020,
        le=2100,
        description="Filtra competitors que tienen race_results en esta temporada",
    ),
    include_suggestions: bool = Query(
        default=True,
        description="Incluir top-3 sugerencias del matcher fuzzy por competitor",
    ),
    suggestions_limit: int = Query(default=3, ge=1, le=10),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> UnlinkedCompetitorsResponse:
    """Lista competitors sin enlace a athlete + sugerencias top-N.

    Sólo soporta ``unlinked=True`` en esta versión (el caso ``unlinked=False``
    para listar TODOS los competitors no tiene caso de uso conocido).
    """
    if not unlinked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo unlinked=True está soportado en esta versión.",
        )

    # Para coaches, filtramos las sugerencias a sus clubes (admin = global).
    suggestions_club_id: Optional[int] = None
    if current_user.role == UserRole.coach:
        coach_clubs = _coach_club_ids(current_user)
        # Si el coach está asignado a un único club, restringimos. Si está en
        # varios, dejamos global y el matcher decide por score.
        if len(coach_clubs) == 1:
            suggestions_club_id = next(iter(coach_clubs))

    rows, total = await list_unlinked_competitors(
        db,
        club_filter=club_filter,
        season=season,
        include_suggestions=include_suggestions,
        suggestions_limit=suggestions_limit,
        suggestions_club_id=suggestions_club_id,
        limit=limit,
        offset=offset,
    )

    items = [
        UnlinkedCompetitorItem(
            id=r.id,
            display_name=r.display_name,
            normalized_name=r.normalized_name,
            club_text=r.club_text,
            sex=r.sex,
            results_count=r.results_count,
            seasons=r.seasons,
            suggestions=[_to_suggestion_schema(s) for s in r.suggestions],
        )
        for r in rows
    ]
    return UnlinkedCompetitorsResponse(items=items, total=total)


# ---------------------------------------------------------------------------
# GET /api/race-competitors/suggestions-by-name — sugerencias INVERSAS (Option B)
# ---------------------------------------------------------------------------
#
# IMPORTANTE: este endpoint debe declararse ANTES del endpoint dinámico
# ``/{competitor_id}/suggestions`` para que FastAPI lo resuelva como ruta
# literal y no como ``competitor_id="suggestions-by-name"`` (422).


@router.get(
    "/suggestions-by-name",
    response_model=CompetitorSuggestionsByNameResponse,
)
async def get_suggestions_by_name(
    first_name: str = Query(
        ...,
        min_length=1,
        max_length=80,
        description=(
            "Primer nombre del athlete a crear (se normaliza internamente)."
        ),
    ),
    last_name: str = Query(
        ...,
        min_length=1,
        max_length=80,
        description="Apellido(s) del athlete a crear.",
    ),
    club: Optional[str] = Query(
        default=None,
        max_length=150,
        description=(
            "Club textual opcional. Si se provee y matchea ``club_text`` del "
            "competitor por fuzzy → boost al score."
        ),
    ),
    limit: int = Query(default=5, ge=1, le=20),
    threshold: float = Query(
        default=70.0,
        ge=0.0,
        le=100.0,
        description="Score base mínimo (0..100). Default 70.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> CompetitorSuggestionsByNameResponse:
    """Devuelve competitors huérfanos sugeridos para un athlete a crear.

    Caso de uso (Option B):
    - El coach está creando un nuevo Athlete en el wizard.
    - Antes de hacer ``POST /athletes``, el frontend invoca este endpoint
      con ``first_name`` + ``last_name``.
    - Si hay competitors huérfanos con nombre similar, el frontend muestra
      un modal "¿Es este atleta? Hay N resultados pendientes".
    - El coach decide; si confirma, crea el athlete y luego invoca
      ``POST /api/race-competitors/{competitor_id}/link`` para enlazar.

    Este endpoint NO modifica nada en DB (solo lectura).

    RBAC: ``coach`` + ``admin``. Padres bloqueados (403).
    """
    # Nota privacidad: no logueamos los nombres. Solo cardinalidad y resultado.
    suggestions = await suggest_competitors_for_new_athlete(
        db,
        first_name=first_name,
        last_name=last_name,
        club=club,
        limit=limit,
        threshold=threshold,
    )
    logger.info(
        "suggestions_by_name user_id=%s suggestions_returned=%d has_club=%s",
        current_user.id,
        len(suggestions),
        bool(club),
    )
    return CompetitorSuggestionsByNameResponse(
        suggestions=[_to_competitor_suggestion_schema(s) for s in suggestions],
    )


# ---------------------------------------------------------------------------
# GET /api/race-competitors/{id}/suggestions  — top-N sugerencias
# ---------------------------------------------------------------------------


@router.get(
    "/{competitor_id}/suggestions",
    response_model=CompetitorSuggestionsResponse,
)
async def get_suggestions(
    competitor_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    threshold: float = Query(
        default=70.0,
        ge=0.0,
        le=100.0,
        description="Score mínimo del matcher (0..100). Default 70.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> CompetitorSuggestionsResponse:
    """Devuelve top-N atletas sugeridos por fuzzy match para el competitor."""
    # Coach con un solo club → restringe sugerencias; admin global.
    suggestions_club_id: Optional[int] = None
    if current_user.role == UserRole.coach:
        coach_clubs = _coach_club_ids(current_user)
        if len(coach_clubs) == 1:
            suggestions_club_id = next(iter(coach_clubs))

    try:
        suggestions = await suggest_athletes_for_competitor(
            db,
            competitor_id,
            limit=limit,
            threshold=threshold,
            club_id=suggestions_club_id,
        )
    except CompetitorNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    return CompetitorSuggestionsResponse(
        competitor_id=competitor_id,
        suggestions=[_to_suggestion_schema(s) for s in suggestions],
    )


# ---------------------------------------------------------------------------
# POST /api/race-competitors/{id}/link  — enlazar
# ---------------------------------------------------------------------------


@router.post(
    "/{competitor_id}/link",
    response_model=CompetitorLinkResponse,
)
async def link_competitor(
    competitor_id: int,
    body: CompetitorLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> CompetitorLinkResponse:
    """Enlaza un competitor a un athlete y propaga a sus race_results.

    Respuestas:
    - 200: link nuevo o idempotente (``already_linked=true``).
    - 404: competitor o athlete inexistente.
    - 409: competitor ya enlazado a un athlete DIFERENTE.
    - 403: rol parent, o coach intentando linkar athlete fuera de sus clubes.
    """
    # RBAC scope: el coach solo puede linkar a athletes de sus clubes.
    try:
        await _ensure_athlete_in_coach_clubs(db, body.athlete_id, current_user)
    except AthleteNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    try:
        result = await link_competitor_to_athlete(
            db,
            competitor_id=competitor_id,
            athlete_id=body.athlete_id,
            user_id=current_user.id,
        )
    except CompetitorNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except AthleteNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except CompetitorAlreadyLinkedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    return CompetitorLinkResponse(
        competitor_id=result.competitor_id,
        athlete_id=result.athlete_id,
        linked_at=result.linked_at,
        linked_by_user_id=result.linked_by_user_id,
        results_propagated=result.results_propagated,
        already_linked=result.already_linked,
    )


# ---------------------------------------------------------------------------
# DELETE /api/race-competitors/{id}/link  — desenlazar
# ---------------------------------------------------------------------------


@router.delete(
    "/{competitor_id}/link",
    response_model=CompetitorUnlinkResponse,
)
async def unlink_competitor_endpoint(
    competitor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> CompetitorUnlinkResponse:
    """Desvincula competitor del athlete y propaga NULL a race_results.

    Si el competitor ya estaba unlinked → 200 + ``was_linked=false``
    (idempotente). Si no existe → 404.

    RBAC: si el competitor estaba enlazado a un athlete fuera de los clubes
    del coach, se devuelve 403 (no puede deshacer linkage que no le pertenece).
    """
    # Pre-check: load competitor para validar RBAC sobre el athlete_id actual.
    from sqlalchemy import select

    from app.models.race_competitor import RaceCompetitor

    result = await db.execute(
        select(RaceCompetitor).where(RaceCompetitor.id == competitor_id)
    )
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"competitor_id={competitor_id} no existe",
        )

    # Coach: solo puede unlink si el athlete actual está en sus clubes.
    if (
        current_user.role == UserRole.coach
        and competitor.athlete_id is not None
    ):
        try:
            await _ensure_athlete_in_coach_clubs(
                db, competitor.athlete_id, current_user
            )
        except AthleteNotFoundError:
            # athlete_id huérfano (FK SET NULL no aplicó). Permitimos unlink
            # para limpiar el state inconsistente.
            pass

    try:
        result_obj = await unlink_competitor(
            db, competitor_id=competitor_id, user_id=current_user.id
        )
    except CompetitorNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    return CompetitorUnlinkResponse(
        competitor_id=result_obj.competitor_id,
        results_propagated=result_obj.results_propagated,
        was_linked=result_obj.was_linked,
    )
