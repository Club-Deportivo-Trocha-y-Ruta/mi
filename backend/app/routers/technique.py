"""Router for the Technique & Gymkhana Library (feature 018).

Registered in ``app/main.py`` with prefix ``/api/technique`` and tag
``technique``.

RBAC: every route requires coach or admin (``_coach_or_admin`` dependency
defined below), plus club-scope verification performed inline where the resource
belongs to a specific club.  Parents and athletes receive 403 on all routes
(FR-021, data-model rule 8).

Route inventory (contract: specs/018-technique-gymkhana-library/contracts/rest-api.md):

  GET  /api/technique/skills                              — taxonomy list
  GET  /api/technique/materials                           — material list
  GET  /api/technique/exercises                           — catalog list/filter (T011)
  GET  /api/technique/exercises/{id}                      — exercise detail (T019)
  POST /api/technique/exercises                           — curation create (T044)
  PUT  /api/technique/exercises/{id}                      — curation update (T044)
  PATCH /api/technique/exercises/{id}/visibility          — hide/unhide (T044)
  POST /api/technique/sessions                            — session assembly (T028)
  GET  /api/technique/sessions/{training_session_id}/exercises — session read (T028)
  POST /api/technique/sessions/{training_session_id}/exercises — attach to existing session (feature 032, T003/T006)
  GET  /api/technique/athletes/{athlete_id}/progress      — progress read (T037)
  POST /api/technique/athletes/{athlete_id}/progress      — progress append (T037)
"""
from __future__ import annotations

import logging
import re as _re
import time as _time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.athlete import Athlete
from app.models.club import ClubMember
from app.models.technique_exercise import (
    AgeBand,
    ExerciseDifficulty,
    TechniqueExercise,
    TechniqueExerciseAgeBand,
)
from app.models.technique_material import TechniqueMaterial
from app.models.technique_skill import TechniqueSkill
from app.models.user import User, UserRole
from app.schemas.technique import (
    AssembleSessionRequest,
    AssembleSessionResponse,
    AthleteProgressRead,
    AttachExercisesRequest,
    AttachExercisesResponse,
    ExerciseCreate,
    ExerciseDetail,
    ExerciseListItem,
    ExerciseUpdate,
    ExerciseVisibilityPatch,
    ExerciseVisibilityRead,
    MaterialRead,
    ProgressCreate,
    SkillProgressEvent,
    SkillRead,
    TechniqueSessionItem,
)
from app.services.permissions import user_club_role
from app.services.technique import assembler as assembler_svc
from app.services.technique import catalog as catalog_svc
from app.services.technique import progress as progress_svc

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# RBAC dependency: coach or admin only (FR-021)
# ---------------------------------------------------------------------------

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
# Internal serialization helpers
# ---------------------------------------------------------------------------


def _serialize_exercise_list_item(ex: TechniqueExercise) -> ExerciseListItem:
    """Map an ORM TechniqueExercise to ExerciseListItem.

    The three relationship collections (skills, materials, age_bands) must
    already be eagerly loaded by the caller (selectinload).
    """
    return ExerciseListItem(
        id=ex.id,
        slug=ex.slug,
        name=ex.name,
        summary=ex.summary,
        difficulty=ex.difficulty,
        is_game=ex.is_game,
        is_gymkhana=ex.is_gymkhana,
        age_bands=[ab.age_band for ab in ex.age_bands],
        skills=[SkillRead.model_validate(s) for s in ex.skills],
        materials=[MaterialRead.model_validate(m) for m in ex.materials],
        is_seeded=ex.is_seeded,
        is_hidden=ex.is_hidden,
    )


def _serialize_exercise_detail(ex: TechniqueExercise) -> ExerciseDetail:
    """Map an ORM TechniqueExercise to ExerciseDetail.

    layout_json is stored as a raw dict in the JSON column; Pydantic coerces it
    to GymkhanaLayout on construction (validated on read — feature 019 Phase A).
    """
    return ExerciseDetail(
        id=ex.id,
        slug=ex.slug,
        name=ex.name,
        summary=ex.summary,
        difficulty=ex.difficulty,
        is_game=ex.is_game,
        is_gymkhana=ex.is_gymkhana,
        age_bands=[ab.age_band for ab in ex.age_bands],
        skills=[SkillRead.model_validate(s) for s in ex.skills],
        materials=[MaterialRead.model_validate(m) for m in ex.materials],
        is_seeded=ex.is_seeded,
        is_hidden=ex.is_hidden,
        how_to=ex.how_to,
        layout_ascii=ex.layout_ascii,
        layout_alt=ex.layout_alt,
        layout_json=ex.layout_json,
        confidence=ex.confidence,
        created_at=ex.created_at,
        updated_at=ex.updated_at,
    )


def _serialize_session_item(link) -> TechniqueSessionItem:
    """Map a TechniqueSessionExercise (with eager .exercise) to TechniqueSessionItem."""
    ex = link.exercise
    return TechniqueSessionItem(
        exercise_id=ex.id,
        name=ex.name,
        segment=link.segment,
        position=link.position,
        age_bands=[ab.age_band for ab in ex.age_bands],
        skills=[SkillRead.model_validate(s) for s in ex.skills],
        # Feature 019 Phase B (O-6): flag the synthetic combined-circuit exercise
        # so the frontend can identify/skip it among the catalog exercises.
        is_hidden=ex.is_hidden,
        is_gymkhana=ex.is_gymkhana,
    )


def _serialize_progress_event(event) -> SkillProgressEvent:
    """Map an AthleteSkillProgress ORM row to SkillProgressEvent."""
    return SkillProgressEvent(
        id=event.id,
        skill=SkillRead.model_validate(event.skill),
        status=event.status,
        coach_note=event.coach_note,
        season=event.season,
        recorded_at=event.recorded_at,
    )


async def _coach_club_id(db: AsyncSession, user: User) -> int:
    """Return the coach's primary club_id.

    For admin users, returns the first club_id in their memberships.
    Raises HTTPException 403 when the user has no club membership.
    """
    result = await db.execute(
        select(ClubMember.club_id).where(ClubMember.user_id == user.id).limit(1)
    )
    club_id = result.scalar_one_or_none()
    if club_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no pertenece a ningún club.",
        )
    return club_id


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
    """Return all technique skills ordered by progression (sort_order)."""
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
    """Return all technique materials including the is_none sentinel row."""
    materials = await catalog_svc.list_materials(db)
    return [MaterialRead.model_validate(m) for m in materials]


# ---------------------------------------------------------------------------
# GET /api/technique/exercises — catalog list / filter (T011)
# ---------------------------------------------------------------------------


@router.get(
    "/exercises",
    response_model=dict[str, Any],
    summary="Listar y filtrar ejercicios del catálogo",
    description=(
        "Lista y filtra el catálogo. Parámetros opcionales y combinables: "
        "skill (slug), age_band, difficulty, materials (csv), include_hidden, "
        "is_game. Respuesta: { items: [ExerciseListItem], total: int }. "
        "Resultado vacío devuelve 200 { items: [], total: 0 } (FR-004)."
    ),
)
async def list_exercises(
    skill: str | None = Query(default=None, description="Slug de habilidad."),
    age_band: AgeBand | None = Query(default=None, description="Banda de edad."),
    difficulty: ExerciseDifficulty | None = Query(default=None, description="Dificultad."),
    materials: str | None = Query(
        default=None,
        description="CSV de slugs de materiales disponibles hoy.",
    ),
    include_hidden: bool = Query(default=False, description="Incluye ejercicios ocultos."),
    is_game: bool | None = Query(default=None, description="Filtra por juego puro."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> dict[str, Any]:
    """Return filtered catalog. Empty result is a 200 with items=[] (FR-004)."""
    materials_list: list[str] | None = None
    if materials is not None:
        materials_list = [s.strip() for s in materials.split(",") if s.strip()]

    exercises = await catalog_svc.list_exercises(
        db,
        skill=skill,
        age_band=age_band,
        difficulty=difficulty,
        materials=materials_list,
        include_hidden=include_hidden,
        is_game=is_game,
    )
    items = [_serialize_exercise_list_item(ex) for ex in exercises]
    return {"items": [item.model_dump() for item in items], "total": len(items)}


# ---------------------------------------------------------------------------
# GET /api/technique/exercises/{id} — exercise detail (T019)
# ---------------------------------------------------------------------------


@router.get(
    "/exercises/{exercise_id}",
    response_model=ExerciseDetail,
    summary="Detalle de un ejercicio",
    description=(
        "Devuelve ExerciseDetail con how_to, layout_ascii, layout_alt, confidence "
        "(US2). Ejercicios ocultos también se devuelven (FR-019). "
        "404 cuando el id es desconocido."
    ),
)
async def get_exercise(
    exercise_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> ExerciseDetail:
    """Return exercise detail by id; 404 when not found."""
    ex = await catalog_svc.get_exercise(db, exercise_id)
    if ex is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ejercicio {exercise_id} no encontrado.",
        )
    return _serialize_exercise_detail(ex)


# ---------------------------------------------------------------------------
# POST /api/technique/sessions — assemble technique session (T028)
# ---------------------------------------------------------------------------


@router.post(
    "/sessions",
    response_model=AssembleSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ensamblar sesión de técnica",
    description=(
        "Crea una sesión de entrenamiento ordinaria vía training_svc.create_session "
        "y guarda los ejercicios de técnica (US3, FR-011). "
        "Respuesta 201: { training_session_id, mixes_age_bands, items }. "
        "422 cuando items está vacío o contiene exercise_id desconocido."
    ),
)
async def assemble_session(
    payload: AssembleSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> AssembleSessionResponse:
    """Assemble a technique session. Club scope resolved from coach's membership."""
    club_id = await _coach_club_id(db, current_user)

    (
        training_session,
        mixes,
        link_rows,
        combined_exercise_id,
    ) = await assembler_svc.assemble_technique_session(
        db,
        payload=payload,
        current_user=current_user,
        club_id=club_id,
    )

    items = [_serialize_session_item(link) for link in link_rows]
    return AssembleSessionResponse(
        training_session_id=training_session.id,
        mixes_age_bands=mixes,
        items=items,
        # Feature 019 Phase B (O-6): id of the hidden synthetic exercise that
        # persists the combined free-form circuit; null when no combined_layout
        # was sent in the request.
        combined_exercise_id=combined_exercise_id,
    )


# ---------------------------------------------------------------------------
# GET /api/technique/sessions/{training_session_id}/exercises — session read (T028)
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{training_session_id}/exercises",
    response_model=list[TechniqueSessionItem],
    summary="Leer ejercicios ensamblados de una sesión",
    description=(
        "Devuelve la lista ordenada de TechniqueSessionItem de la sesión, "
        "agrupados por segmento (FR-013, FR-020). Retorna lista vacía cuando la "
        "sesión existe pero no tiene ejercicios de técnica vinculados."
    ),
)
async def get_session_exercises(
    training_session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> list[TechniqueSessionItem]:
    """Return the ordered technique exercise list for a session."""
    link_rows = await assembler_svc.get_session_exercises(db, training_session_id)
    return [_serialize_session_item(link) for link in link_rows]


# ---------------------------------------------------------------------------
# POST /api/technique/sessions/{training_session_id}/exercises — attach to an
# existing session (feature 032, session content unification, T003/T006).
# Sibling of the GET above: same resource, same path prefix.
# ---------------------------------------------------------------------------


@router.post(
    "/sessions/{training_session_id}/exercises",
    response_model=AttachExercisesResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adjuntar ejercicios de técnica a una sesión existente",
    description=(
        "Adjunta uno o más ejercicios a una sesión de entrenamiento ya "
        "existente, sin crear una sesión nueva (FR-001/FR-002/FR-009). "
        "Idempotente: reenviar el mismo payload no duplica filas "
        "(deduplicado por (exercise_id, segment)). "
        "404 cuando la sesión no existe o pertenece a otro club. "
        "422 cuando items está vacío o contiene exercise_id desconocido."
    ),
)
async def attach_exercises(
    training_session_id: int,
    payload: AttachExercisesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> AttachExercisesResponse:
    """Attach technique exercises to an already-existing training session."""
    club_id = await _coach_club_id(db, current_user)

    mixes, link_rows = await assembler_svc.attach_exercises_to_session(
        db,
        training_session_id=training_session_id,
        items=payload.items,
        club_id=club_id,
    )

    return AttachExercisesResponse(
        mixes_age_bands=mixes,
        items=[_serialize_session_item(link) for link in link_rows],
    )


# ---------------------------------------------------------------------------
# Club-scope guard for progress endpoints (coach must belong to athlete's club)
# ---------------------------------------------------------------------------


async def _require_athlete_club_scope(
    db: AsyncSession,
    athlete_id: int,
    current_user: User,
) -> None:
    """Verify that a coach belongs to the same club as the target athlete.

    Admin users pass unconditionally.  Coach users receive 403 when the
    athlete does not belong to any of the coach's clubs.  The athlete
    existence check is intentionally opaque: a non-existent athlete_id
    always raises 404 with no PII in the detail, preserving the same
    behaviour as the service layer (FR-017, SC-005).

    Args:
        db:            Active async session.
        athlete_id:    Path parameter identifying the target athlete.
        current_user:  Authenticated user (coach or admin — parents are
                       already blocked upstream by ``_require_coach_or_admin``).

    Raises:
        HTTPException 404: athlete_id unknown.
        HTTPException 403: coach does not belong to the athlete's club.
    """
    if current_user.role == UserRole.admin:
        # Admin has unrestricted access to all clubs.
        return

    # Load athlete to obtain their club_id.
    result = await db.execute(
        select(Athlete.club_id).where(Athlete.id == athlete_id)
    )
    athlete_club_id = result.scalar_one_or_none()
    if athlete_club_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Atleta {athlete_id} no encontrado.",
        )

    # Verify the coach has membership in the athlete's club.
    club_role = await user_club_role(db, current_user.id, athlete_club_id)
    if club_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso al progreso de este atleta.",
        )


# ---------------------------------------------------------------------------
# GET /api/technique/athletes/{athlete_id}/progress — progress read (T037)
# ---------------------------------------------------------------------------


@router.get(
    "/athletes/{athlete_id}/progress",
    response_model=AthleteProgressRead,
    summary="Leer progreso de habilidades de un atleta",
    description=(
        "Devuelve AthleteProgressRead con current (último evento por habilidad) "
        "e history (todos los eventos del atleta, ordenados por fecha). "
        "Coach/admin únicamente — sin PII de menores (FR-017, SC-005). "
        "404 cuando el athlete_id no existe. "
        "403 cuando el coach no pertenece al club del atleta."
    ),
)
async def get_athlete_progress(
    athlete_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> AthleteProgressRead:
    """Return skill progress for a single athlete (SC-005: single-athlete scope)."""
    await _require_athlete_club_scope(db, athlete_id, current_user)
    try:
        result = await progress_svc.get_athlete_progress(db, athlete_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return AthleteProgressRead(
        athlete_id=athlete_id,
        current=[_serialize_progress_event(e) for e in result["current"]],
        history=[_serialize_progress_event(e) for e in result["history"]],
    )


# ---------------------------------------------------------------------------
# POST /api/technique/athletes/{athlete_id}/progress — progress append (T037)
# ---------------------------------------------------------------------------


@router.post(
    "/athletes/{athlete_id}/progress",
    response_model=SkillProgressEvent,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar evento de progreso de habilidad",
    description=(
        "Añade un evento append-only de SkillProgressStatus para el atleta "
        "(US4, FR-015). Body: ProgressCreate. Respuesta 201: SkillProgressEvent. "
        "404 cuando el atleta no existe. "
        "403 cuando el coach no pertenece al club del atleta."
    ),
)
async def create_athlete_progress(
    athlete_id: int,
    payload: ProgressCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> SkillProgressEvent:
    """Append a new skill-progress event for the athlete (append-only, FR-015)."""
    await _require_athlete_club_scope(db, athlete_id, current_user)
    try:
        event = await progress_svc.add_progress_event(
            db,
            athlete_id,
            skill_id=payload.skill_id,
            status=payload.status,
            coach_note=payload.coach_note,
            season=payload.season,
            recorded_by_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    await db.commit()
    await db.refresh(event)
    return _serialize_progress_event(event)


# ---------------------------------------------------------------------------
# POST /api/technique/exercises — curation create (T044)
# ---------------------------------------------------------------------------


async def _resolve_skills(
    db: AsyncSession, skill_slugs: list[str]
) -> list[TechniqueSkill]:
    """Resolve skill slugs to ORM rows; raises 422 for unknown slugs."""
    result = await db.execute(
        select(TechniqueSkill).where(TechniqueSkill.slug.in_(skill_slugs))
    )
    found = list(result.scalars().all())
    found_slugs = {s.slug for s in found}
    missing = [s for s in skill_slugs if s not in found_slugs]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Habilidades no encontradas: {missing}",
        )
    return found


async def _resolve_materials(
    db: AsyncSession, material_slugs: list[str]
) -> list[TechniqueMaterial]:
    """Resolve material slugs to ORM rows; raises 422 for unknown slugs."""
    if not material_slugs:
        return []
    result = await db.execute(
        select(TechniqueMaterial).where(TechniqueMaterial.slug.in_(material_slugs))
    )
    found = list(result.scalars().all())
    found_slugs = {m.slug for m in found}
    missing = [s for s in material_slugs if s not in found_slugs]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Materiales no encontrados: {missing}",
        )
    return found


def _slugify(name: str) -> str:
    """Derive a URL-safe slug from a display name."""
    slug = name.lower().strip()
    slug = _re.sub(r"[áàä]", "a", slug)
    slug = _re.sub(r"[éèë]", "e", slug)
    slug = _re.sub(r"[íìï]", "i", slug)
    slug = _re.sub(r"[óòö]", "o", slug)
    slug = _re.sub(r"[úùü]", "u", slug)
    slug = _re.sub(r"[ñ]", "n", slug)
    slug = _re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


@router.post(
    "/exercises",
    response_model=ExerciseDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Crear ejercicio personalizado",
    description=(
        "Crea un ejercicio con club_id del coach (is_seeded=false). "
        "Body: ExerciseCreate. Respuesta 201: ExerciseDetail. "
        "Validaciones: gymkhana ⇒ layout_ascii requerido; ≥1 age_band; ≥1 skill "
        "(FR-019). Aparece en browse/filtros de inmediato."
    ),
)
async def create_exercise(
    payload: ExerciseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> ExerciseDetail:
    """Create a coach-custom exercise scoped to the coach's club."""
    club_id = await _coach_club_id(db, current_user)

    skills = await _resolve_skills(db, payload.skill_slugs)
    materials = await _resolve_materials(db, payload.material_slugs)

    base_slug = _slugify(payload.name)
    # Ensure slug uniqueness by appending club_id when needed.
    candidate_slug = f"{base_slug}-club{club_id}"
    existing = await db.execute(
        select(TechniqueExercise.id).where(TechniqueExercise.slug == candidate_slug)
    )
    if existing.scalar_one_or_none() is not None:
        candidate_slug = f"{candidate_slug}-{int(_time.time())}"

    exercise = TechniqueExercise(
        slug=candidate_slug,
        name=payload.name,
        summary=payload.summary,
        how_to=payload.how_to,
        difficulty=payload.difficulty,
        is_game=payload.is_game,
        is_gymkhana=payload.is_gymkhana,
        layout_ascii=payload.layout_ascii,
        layout_alt=payload.layout_alt,
        # Feature 019 Phase A: persist validated GymkhanaLayout as a plain dict
        # (the JSON column stores raw dicts; Pydantic coerces on read).
        layout_json=(
            payload.layout_json.model_dump() if payload.layout_json is not None else None
        ),
        confidence=None,
        is_seeded=False,
        is_hidden=False,
        club_id=club_id,
        created_by_user_id=current_user.id,
    )
    exercise.skills = skills
    exercise.materials = materials
    db.add(exercise)
    await db.flush()

    # Insert age band rows.
    for band in set(payload.age_bands):
        db.add(TechniqueExerciseAgeBand(exercise_id=exercise.id, age_band=band))

    await db.commit()

    # Reload with all relationships for the response.
    reloaded = await catalog_svc.get_exercise(db, exercise.id)
    if reloaded is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al recuperar el ejercicio creado.",
        )
    return _serialize_exercise_detail(reloaded)


# ---------------------------------------------------------------------------
# PUT /api/technique/exercises/{id} — curation update (T044)
# ---------------------------------------------------------------------------


@router.put(
    "/exercises/{exercise_id}",
    response_model=ExerciseDetail,
    summary="Editar ejercicio (incluso seeded)",
    description=(
        "Edición parcial de cualquier ejercicio. Body: ExerciseUpdate. "
        "Respuesta 200: ExerciseDetail actualizado. Los edits no alteran sesiones "
        "ya guardadas (FR-020). 404 cuando el id es desconocido."
    ),
)
async def update_exercise(
    exercise_id: int,
    payload: ExerciseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> ExerciseDetail:
    """Apply a partial update to any exercise (seeded or custom)."""
    ex = await catalog_svc.get_exercise(db, exercise_id)
    if ex is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ejercicio {exercise_id} no encontrado.",
        )

    # Cross-field gymkhana/layout_ascii invariant when only one side supplied.
    effective_is_gymkhana = payload.is_gymkhana if payload.is_gymkhana is not None else ex.is_gymkhana
    effective_layout = payload.layout_ascii if payload.layout_ascii is not None else ex.layout_ascii
    if effective_is_gymkhana and not effective_layout:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="layout_ascii es requerido cuando is_gymkhana es True (FR-008).",
        )

    # Apply scalar fields.
    if payload.name is not None:
        ex.name = payload.name
    if payload.summary is not None:
        ex.summary = payload.summary
    if payload.how_to is not None:
        ex.how_to = payload.how_to
    if payload.difficulty is not None:
        ex.difficulty = payload.difficulty
    if payload.is_game is not None:
        ex.is_game = payload.is_game
    if payload.is_gymkhana is not None:
        ex.is_gymkhana = payload.is_gymkhana
    if payload.layout_ascii is not None:
        ex.layout_ascii = payload.layout_ascii
    if payload.layout_alt is not None:
        ex.layout_alt = payload.layout_alt
    # Feature 019 Phase A: persist GymkhanaLayout when included in the payload.
    # None means "not provided / leave unchanged" (consistent with other nullable
    # scalar fields on ExerciseUpdate — partial-update convention).
    if payload.layout_json is not None:
        ex.layout_json = payload.layout_json.model_dump()

    # Replace M2M relationships when supplied.
    if payload.skill_slugs is not None:
        ex.skills = await _resolve_skills(db, payload.skill_slugs)
    if payload.material_slugs is not None:
        ex.materials = await _resolve_materials(db, payload.material_slugs)

    # Replace age band rows when supplied (delete-orphan cascade handles removal).
    if payload.age_bands is not None:
        # Remove existing age band rows first.
        await db.execute(
            sa_delete(TechniqueExerciseAgeBand).where(
                TechniqueExerciseAgeBand.exercise_id == ex.id
            )
        )
        for band in set(payload.age_bands):
            db.add(TechniqueExerciseAgeBand(exercise_id=ex.id, age_band=band))

    await db.commit()

    reloaded = await catalog_svc.get_exercise(db, ex.id)
    if reloaded is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al recuperar el ejercicio actualizado.",
        )
    return _serialize_exercise_detail(reloaded)


# ---------------------------------------------------------------------------
# PATCH /api/technique/exercises/{id}/visibility — hide/unhide (T044)
# ---------------------------------------------------------------------------


@router.patch(
    "/exercises/{exercise_id}/visibility",
    response_model=ExerciseVisibilityRead,
    summary="Ocultar/mostrar ejercicio",
    description=(
        "Cambia el flag is_hidden de un ejercicio (soft-hide). "
        "Body: { is_hidden: bool }. Respuesta 200: { id, is_hidden }. "
        "Las filas ocultas no se destruyen (FR-019) y no corrompen sesiones "
        "guardadas (FR-020). 404 cuando el id es desconocido."
    ),
)
async def set_exercise_visibility(
    exercise_id: int,
    payload: ExerciseVisibilityPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> ExerciseVisibilityRead:
    """Set is_hidden on an exercise; never deletes the row."""
    result = await db.execute(
        select(TechniqueExercise).where(TechniqueExercise.id == exercise_id)
    )
    ex = result.scalar_one_or_none()
    if ex is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ejercicio {exercise_id} no encontrado.",
        )

    ex.is_hidden = payload.is_hidden
    await db.commit()
    await db.refresh(ex)

    return ExerciseVisibilityRead(id=ex.id, is_hidden=ex.is_hidden)
