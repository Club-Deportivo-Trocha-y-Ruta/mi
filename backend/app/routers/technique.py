"""Router for the Technique & Gymkhana Library (feature 018).

Registered in ``app/main.py`` with prefix ``/api/technique`` and tag
``technique``.

RBAC: every route requires coach or admin (``_coach_or_admin`` dependency
defined below), plus club-scope verification performed inline where the resource
belongs to a specific club.  Parents and athletes receive 403 on all routes
(FR-021, data-model rule 8).

Route inventory (contract: specs/018-technique-gymkhana-library/contracts/rest-api.md):

  IMPLEMENTED (T007):
    GET  /api/technique/skills          — taxonomy list for filter controls
    GET  /api/technique/materials       — material list for filter controls

  TODO (filled by later tasks):
    GET  /api/technique/exercises                    — T008 catalog list/filter
    GET  /api/technique/exercises/{id}               — T008 exercise detail
    POST /api/technique/sessions                     — T009 session assembly
    GET  /api/technique/sessions/{training_session_id}/exercises — T009 session read
    GET  /api/technique/athletes/{athlete_id}/progress   — T010 progress read
    POST /api/technique/athletes/{athlete_id}/progress   — T010 progress append
    POST /api/technique/exercises                    — T011 curation create
    PUT  /api/technique/exercises/{id}               — T011 curation update
    PATCH /api/technique/exercises/{id}/visibility   — T011 curation hide/unhide
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.technique_exercise import AgeBand, ExerciseDifficulty
from app.models.user import User, UserRole
from app.schemas.technique import (
    ExerciseDetail,
    ExerciseListItem,
    MaterialRead,
    SkillRead,
)
from app.services.technique import catalog as catalog_svc
from app.services.permissions import user_club_role

router = APIRouter()

# ---------------------------------------------------------------------------
# RBAC dependency: coach or admin only (FR-021)
# ---------------------------------------------------------------------------

# Mirrors the pattern in anxiety.py — a module-level callable that is reused
# as a Depends() argument across every route in this router.
_coach_or_admin = require_role([UserRole.admin, UserRole.coach])


async def _require_coach_or_admin(
    current_user: User = Depends(_coach_or_admin),
) -> User:
    """Gate that limits access to coach and admin roles.

    Raises:
        HTTPException 403: when the authenticated user is a parent, athlete,
            or any unrecognized role.

    Returns:
        The authenticated ``User`` object, guaranteed to be coach or admin.

    Note:
        Club-scope checks (``user_club_role``) are performed per-endpoint
        where the targeted resource carries a ``club_id`` (e.g. session
        assembly, curation of custom exercises).  The taxonomy endpoints
        (skills, materials) are club-agnostic by design.
    """
    return current_user


# ---------------------------------------------------------------------------
# GET /api/technique/skills — taxonomy list (US1, filter controls)
# ---------------------------------------------------------------------------


class SkillListResponse(SkillRead):
    """Extended skill read that adds sort_order and focus for the filter UI."""

    sort_order: int
    focus: str

    model_config = {"from_attributes": True}


@router.get(
    "/skills",
    response_model=list[SkillListResponse],
    summary="Listar habilidades técnicas A–H",
    description=(
        "Devuelve la taxonomía completa de habilidades técnicas (A–H) ordenada "
        "por ``sort_order``. Usada para construir los controles de filtro del "
        "catálogo (US1)."
    ),
)
async def list_skills(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> list[SkillListResponse]:
    """Return all technique skills ordered by progression (sort_order).

    Returns an empty list when the table has not been seeded yet; never
    returns 404 or 500 for an empty taxonomy (FR-004 analogue).
    """
    skills = await catalog_svc.list_skills(db)
    return [SkillListResponse.model_validate(s) for s in skills]


# ---------------------------------------------------------------------------
# GET /api/technique/materials — material list (US1, filter controls)
# ---------------------------------------------------------------------------


@router.get(
    "/materials",
    response_model=list[MaterialRead],
    summary="Listar materiales físicos",
    description=(
        "Devuelve todos los materiales del catálogo (conos, llantas, estacas, "
        "topes, sin_material…) ordenados por slug. Usada para el selector de "
        "'materiales disponibles hoy' en el catálogo (US1, FR-009)."
    ),
)
async def list_materials(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> list[MaterialRead]:
    """Return all technique materials including the is_none sentinel row.

    Returns an empty list when the table has not been seeded yet; never
    returns 404 or 500 for an empty material list.
    """
    materials = await catalog_svc.list_materials(db)
    return [MaterialRead.model_validate(m) for m in materials]


# ---------------------------------------------------------------------------
# TODO (T008): GET /api/technique/exercises — catalog list / filter
# ---------------------------------------------------------------------------


@router.get(
    "/exercises",
    response_model=dict,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="[TODO T008] Listar y filtrar ejercicios del catálogo",
    description=(
        "Implementado por T008. Soporta filtros: skill (slug), age_band, "
        "difficulty, materials (csv), include_hidden, is_game. "
        "Respuesta: { items: [ExerciseListItem], total: int }."
    ),
    include_in_schema=True,
)
async def list_exercises(
    skill: str | None = Query(default=None, description="Slug de habilidad."),
    age_band: AgeBand | None = Query(default=None, description="Banda de edad."),
    difficulty: ExerciseDifficulty | None = Query(default=None),
    materials: str | None = Query(default=None, description="CSV de slugs de materiales disponibles."),
    include_hidden: bool = Query(default=False),
    is_game: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> dict:
    # TODO (T008): replace with full implementation.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="GET /exercises — pendiente T008",
    )


# ---------------------------------------------------------------------------
# TODO (T008): GET /api/technique/exercises/{id} — exercise detail
# ---------------------------------------------------------------------------


@router.get(
    "/exercises/{exercise_id}",
    response_model=ExerciseDetail,
    status_code=status.HTTP_200_OK,
    summary="[TODO T008] Detalle de un ejercicio",
    description=(
        "Implementado por T008. Devuelve ExerciseDetail con how_to, "
        "layout_ascii, layout_alt, confidence (US2). 404 cuando id desconocido."
    ),
    include_in_schema=True,
)
async def get_exercise(
    exercise_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> ExerciseDetail:
    # TODO (T008): replace with full implementation using catalog_svc.get_exercise.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="GET /exercises/{id} — pendiente T008",
    )


# ---------------------------------------------------------------------------
# TODO (T009): POST /api/technique/sessions — assemble technique session
# ---------------------------------------------------------------------------


@router.post(
    "/sessions",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="[TODO T009] Ensamblar sesión de técnica",
    description=(
        "Implementado por T009. Crea un TrainingSession ordinario via "
        "training_svc.create_session y guarda technique_session_exercises (US3, "
        "FR-011). Respuesta 201: AssembleSessionResponse con mixes_age_bands."
    ),
    include_in_schema=True,
)
async def assemble_session(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> None:
    # TODO (T009): accept AssembleSessionRequest body, delegate to assembler service.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="POST /sessions — pendiente T009",
    )


# ---------------------------------------------------------------------------
# TODO (T009): GET /api/technique/sessions/{training_session_id}/exercises
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{training_session_id}/exercises",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="[TODO T009] Leer ejercicios ensamblados de una sesión",
    description=(
        "Implementado por T009. Devuelve la lista ordenada de TechniqueSessionItem "
        "de la sesión, agrupados por segmento (FR-013, FR-020)."
    ),
    include_in_schema=True,
)
async def get_session_exercises(
    training_session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> None:
    # TODO (T009): query technique_session_exercises for the given session.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="GET /sessions/{training_session_id}/exercises — pendiente T009",
    )


# ---------------------------------------------------------------------------
# TODO (T010): GET /api/technique/athletes/{athlete_id}/progress
# ---------------------------------------------------------------------------


@router.get(
    "/athletes/{athlete_id}/progress",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="[TODO T010] Leer progreso de habilidades de un atleta",
    description=(
        "Implementado por T010. Devuelve AthleteProgressRead con current "
        "(último evento por habilidad) e history (eventos de la temporada). "
        "Coach/admin únicamente — sin PII de menores (FR-017, SC-005)."
    ),
    include_in_schema=True,
)
async def get_athlete_progress(
    athlete_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> None:
    # TODO (T010): verify club scope, then delegate to progress service.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="GET /athletes/{athlete_id}/progress — pendiente T010",
    )


# ---------------------------------------------------------------------------
# TODO (T010): POST /api/technique/athletes/{athlete_id}/progress
# ---------------------------------------------------------------------------


@router.post(
    "/athletes/{athlete_id}/progress",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="[TODO T010] Registrar evento de progreso de habilidad",
    description=(
        "Implementado por T010. Añade un evento append-only de SkillProgressStatus "
        "para el atleta (US4, FR-015). Body: ProgressCreate. Respuesta 201: "
        "SkillProgressEvent."
    ),
    include_in_schema=True,
)
async def create_athlete_progress(
    athlete_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> None:
    # TODO (T010): accept ProgressCreate body, verify club scope, insert row.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="POST /athletes/{athlete_id}/progress — pendiente T010",
    )


# ---------------------------------------------------------------------------
# TODO (T011): POST /api/technique/exercises — curation create
# ---------------------------------------------------------------------------


@router.post(
    "/exercises",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="[TODO T011] Crear ejercicio personalizado",
    description=(
        "Implementado por T011. Crea un ejercicio con club_id del coach "
        "(is_seeded=false). Body: ExerciseCreate. Respuesta 201: ExerciseDetail. "
        "Validaciones: gymkhana ⇒ layout_ascii; ≥1 age_band; ≥1 skill (FR-019)."
    ),
    include_in_schema=True,
)
async def create_exercise(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> None:
    # TODO (T011): accept ExerciseCreate, verify club scope, insert with club_id.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="POST /exercises — pendiente T011",
    )


# ---------------------------------------------------------------------------
# TODO (T011): PUT /api/technique/exercises/{id} — curation update
# ---------------------------------------------------------------------------


@router.put(
    "/exercises/{exercise_id}",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="[TODO T011] Editar ejercicio (incluso seeded)",
    description=(
        "Implementado por T011. Edición parcial. Body: ExerciseUpdate. "
        "Respuesta 200: ExerciseDetail. Edits no alteran sesiones ya guardadas "
        "(FR-020)."
    ),
    include_in_schema=True,
)
async def update_exercise(
    exercise_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> None:
    # TODO (T011): accept ExerciseUpdate, apply partial update, return ExerciseDetail.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="PUT /exercises/{exercise_id} — pendiente T011",
    )


# ---------------------------------------------------------------------------
# TODO (T011): PATCH /api/technique/exercises/{id}/visibility — hide/unhide
# ---------------------------------------------------------------------------


@router.patch(
    "/exercises/{exercise_id}/visibility",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="[TODO T011] Ocultar/mostrar ejercicio",
    description=(
        "Implementado por T011. Body: ExerciseVisibilityPatch { is_hidden: bool }. "
        "Respuesta 200: ExerciseVisibilityRead { id, is_hidden }. "
        "Soft-hide only — RESTRICT FKs previenen borrado real (FR-019/020)."
    ),
    include_in_schema=True,
)
async def set_exercise_visibility(
    exercise_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> None:
    # TODO (T011): accept ExerciseVisibilityPatch, update is_hidden, return read.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="PATCH /exercises/{exercise_id}/visibility — pendiente T011",
    )
