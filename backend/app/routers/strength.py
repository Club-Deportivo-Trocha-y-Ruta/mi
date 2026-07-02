"""Router for the Strength Training Library (feature 021).

Registered in ``app/main.py`` with prefix ``/api/strength`` and tag
``strength``.

RBAC: every route requires coach or admin (``_require_coach_or_admin``
dependency defined below), plus club-scope verification performed inline
where the resource belongs to a specific club.

Route inventory (contract: specs/021-strength-training-library/contracts/strength-api.md):

  GET  /api/strength/exercises           — catalog list/filter (T014)
  GET  /api/strength/exercises/{id}      — exercise detail (T014)
  POST /api/strength/blocks              — block create (T022)
  GET  /api/strength/blocks              — block list (T022)
  GET  /api/strength/blocks/{id}         — block detail (T022)
  PUT  /api/strength/blocks/{id}         — block full replace (T022)
  PATCH /api/strength/blocks/{id}/archive — block archive/unarchive (T022)
  POST /api/strength/blocks/{id}/attach  — attach block to session (T022)
  DELETE /api/strength/blocks/{id}/attach/{session_id} — detach (T022)
  GET  /api/strength/sessions/{id}/blocks — blocks attached to session (T022)
  GET  /api/strength/athletes/{id}/progress  — progress read (T035)
  POST /api/strength/athletes/{id}/progress  — progress append (T035)
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.athlete import Athlete
from app.models.club import ClubMember
from app.models.strength import EquipmentKind, MovementCategory
from app.models.technique_exercise import AgeBand
from app.models.user import User, UserRole
from app.schemas.strength import (
    AttachIn,
    AttachOut,
    BlockCreate,
    BlockOut,
    BlockUpdate,
    EntryOut,
    ExerciseDetailOut,
    ExerciseOut,
    ProgressIn,
    ProgressOut,
)
from app.services.permissions import user_club_role
from app.services.strength import blocks as blocks_svc
from app.services.strength import catalog as catalog_svc
from app.services.strength import progress as progress_svc

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# RBAC dependency: coach or admin only
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
    """
    return current_user


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
# Internal serialization helpers
# ---------------------------------------------------------------------------


def _serialize_exercise_out(ex) -> ExerciseOut:
    """Map a StrengthExercise ORM row to ExerciseOut (card view — no how_to/etc.).

    The ``age_bands`` relationship must already be eagerly loaded by the
    caller (selectinload) to avoid N+1.
    """
    return ExerciseOut(
        id=ex.id,
        slug=ex.slug,
        name=ex.name,
        summary=ex.summary,
        equipment=ex.equipment,
        equipment_detail=ex.equipment_detail,
        movement_category=ex.movement_category,
        age_bands=[ab.age_band for ab in ex.age_bands],
        suggested_duration_min=ex.suggested_duration_min,
        suggested_reps=ex.suggested_reps,
        is_seeded=ex.is_seeded,
        is_hidden=ex.is_hidden,
    )


def _serialize_exercise_detail_out(ex) -> ExerciseDetailOut:
    """Map a StrengthExercise ORM row to ExerciseDetailOut (full record)."""
    return ExerciseDetailOut(
        id=ex.id,
        slug=ex.slug,
        name=ex.name,
        summary=ex.summary,
        equipment=ex.equipment,
        equipment_detail=ex.equipment_detail,
        movement_category=ex.movement_category,
        age_bands=[ab.age_band for ab in ex.age_bands],
        suggested_duration_min=ex.suggested_duration_min,
        suggested_reps=ex.suggested_reps,
        is_seeded=ex.is_seeded,
        is_hidden=ex.is_hidden,
        how_to=ex.how_to,
        common_errors=ex.common_errors,
        illustration_ascii=ex.illustration_ascii,
        illustration_alt=ex.illustration_alt,
    )


def _serialize_entry_out(entry) -> EntryOut:
    """Map a StrengthBlockEntry ORM row to EntryOut (embeds ExerciseOut).

    Built manually — rather than relying on ``EntryOut.model_validate``
    with ``from_attributes=True`` — because the nested exercise's
    ``age_bands`` relationship holds ``StrengthExerciseAgeBand`` rows, not
    bare ``AgeBand`` enum values; only ``_serialize_exercise_out`` knows how
    to unwrap that (mirrors ``routers/technique.py`` convention).
    """
    return EntryOut(
        id=entry.id,
        position=entry.position,
        duration_min=entry.duration_min,
        reps=entry.reps,
        is_age_override=entry.is_age_override,
        override_note=entry.override_note,
        exercise=_serialize_exercise_out(entry.exercise),
    )


def _serialize_block_out(block) -> BlockOut:
    """Map a StrengthBlock ORM row (with entries+exercise eager-loaded) to BlockOut."""
    return BlockOut(
        id=block.id,
        name=block.name,
        target_age_band=block.target_age_band,
        duration_target_min=block.duration_target_min,
        total_duration_min=blocks_svc.total_duration_min(block.entries),
        is_archived=block.is_archived,
        entries=[_serialize_entry_out(entry) for entry in block.entries],
        created_at=block.created_at,
    )


# ---------------------------------------------------------------------------
# GET /api/strength/exercises — catalog list / filter (T014)
# ---------------------------------------------------------------------------


@router.get(
    "/exercises",
    response_model=dict[str, Any],
    summary="Listar y filtrar ejercicios de fuerza",
    description=(
        "Lista y filtra el catálogo de fuerza. Parámetros opcionales y "
        "combinables: q (texto libre sobre nombre+resumen), equipment, "
        "age_band, movement_category, include_hidden. Respuesta: "
        "{ items: [ExerciseOut], total: int }. Vista de tarjeta — omite "
        "how_to/common_errors/illustration_* (el detalle se obtiene con "
        "GET /exercises/{id})."
    ),
)
async def list_exercises(
    q: str | None = Query(default=None, description="Texto libre sobre nombre+resumen."),
    equipment: EquipmentKind | None = Query(default=None, description="Facet de equipo."),
    age_band: AgeBand | None = Query(default=None, description="Banda de edad."),
    movement_category: MovementCategory | None = Query(
        default=None, description="Categoría de movimiento."
    ),
    include_hidden: bool = Query(default=False, description="Solo curación."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> dict[str, Any]:
    """Return filtered strength catalog (card view)."""
    exercises = await catalog_svc.list_exercises(
        db,
        equipment=equipment,
        age_band=age_band,
        movement_category=movement_category,
        q=q,
        include_hidden=include_hidden,
    )
    items = [_serialize_exercise_out(ex) for ex in exercises]
    return {"items": [item.model_dump() for item in items], "total": len(items)}


# ---------------------------------------------------------------------------
# GET /api/strength/exercises/{id} — exercise detail (T014)
# ---------------------------------------------------------------------------


@router.get(
    "/exercises/{exercise_id}",
    response_model=ExerciseDetailOut,
    summary="Detalle de un ejercicio de fuerza",
    description=(
        "Devuelve ExerciseDetailOut con how_to, common_errors, "
        "illustration_ascii e illustration_alt. 404 cuando el id es "
        "desconocido o el ejercicio está oculto."
    ),
)
async def get_exercise(
    exercise_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> ExerciseDetailOut:
    """Return exercise detail by id; 404 when not found or hidden."""
    ex = await catalog_svc.get_exercise(
        db, exercise_id, include_hidden=current_user.role == UserRole.admin
    )
    if ex is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ejercicio {exercise_id} no encontrado.",
        )
    return _serialize_exercise_detail_out(ex)


# ---------------------------------------------------------------------------
# POST /api/strength/blocks — block create (T022)
# ---------------------------------------------------------------------------


@router.post(
    "/blocks",
    response_model=BlockOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un bloque de fuerza",
    description=(
        "Crea un bloque de fuerza con sus entradas, club-scoped al coach "
        "autenticado. 404 cuando alguna entrada referencia un exercise_id "
        "desconocido u oculto. 422 AGE_BAND_GUARDRAIL cuando una entrada "
        "referencia un ejercicio no apropiado para target_age_band y no "
        "envía is_age_override=true (FR-011)."
    ),
)
async def create_block(
    payload: BlockCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> BlockOut:
    """Create a strength block owned by the coach's club."""
    club_id = await _coach_club_id(db, current_user)
    block = await blocks_svc.create_block(
        db,
        name=payload.name,
        target_age_band=payload.target_age_band,
        duration_target_min=payload.duration_target_min,
        entries=payload.entries,
        club_id=club_id,
        created_by_user_id=current_user.id,
    )
    return _serialize_block_out(block)


# ---------------------------------------------------------------------------
# GET /api/strength/blocks — block list (T022)
# ---------------------------------------------------------------------------


@router.get(
    "/blocks",
    response_model=dict[str, Any],
    summary="Listar bloques de fuerza",
    description=(
        "Lista los bloques de fuerza del club del coach autenticado. Por "
        "defecto excluye bloques archivados; ?include_archived=true los "
        "incluye. Respuesta: { items: [BlockOut], total: int }."
    ),
)
async def list_blocks(
    include_archived: bool = Query(default=False, description="Incluir bloques archivados."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> dict[str, Any]:
    """Return the coach's club blocks, most-recently-created first."""
    club_id = await _coach_club_id(db, current_user)
    blocks, total = await blocks_svc.list_blocks(
        db, club_id=club_id, include_archived=include_archived
    )
    items = [_serialize_block_out(block) for block in blocks]
    return {"items": [item.model_dump() for item in items], "total": total}


# ---------------------------------------------------------------------------
# GET /api/strength/blocks/{id} — block detail (T022)
# ---------------------------------------------------------------------------


@router.get(
    "/blocks/{block_id}",
    response_model=BlockOut,
    summary="Detalle de un bloque de fuerza",
    description="Devuelve BlockOut. 404 cuando el bloque no existe o pertenece a otro club.",
)
async def get_block(
    block_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> BlockOut:
    """Return a single club-scoped block by id; 404 when not found."""
    club_id = await _coach_club_id(db, current_user)
    block = await blocks_svc.get_block(db, block_id=block_id, club_id=club_id)
    if block is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bloque de fuerza {block_id} no encontrado.",
        )
    return _serialize_block_out(block)


# ---------------------------------------------------------------------------
# PUT /api/strength/blocks/{id} — block full replace (T022)
# ---------------------------------------------------------------------------


@router.put(
    "/blocks/{block_id}",
    response_model=BlockOut,
    summary="Reemplazar un bloque de fuerza",
    description=(
        "Reemplazo completo de un bloque (mismo shape que POST /blocks). "
        "404 cuando el bloque no existe/pertenece a otro club, o cuando "
        "alguna entrada referencia un exercise_id desconocido u oculto. "
        "422 AGE_BAND_GUARDRAIL cuando una entrada referencia un ejercicio "
        "no apropiado para target_age_band y no envía "
        "is_age_override=true (FR-011)."
    ),
)
async def update_block(
    block_id: int,
    payload: BlockUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> BlockOut:
    """Full replace of a block's fields and entries."""
    club_id = await _coach_club_id(db, current_user)
    block = await blocks_svc.update_block(
        db,
        block_id=block_id,
        club_id=club_id,
        name=payload.name,
        target_age_band=payload.target_age_band,
        duration_target_min=payload.duration_target_min,
        entries=payload.entries,
    )
    if block is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bloque de fuerza {block_id} no encontrado.",
        )
    return _serialize_block_out(block)


# ---------------------------------------------------------------------------
# PATCH /api/strength/blocks/{id}/archive — block archive/unarchive (T022)
# ---------------------------------------------------------------------------


class ArchiveBlockIn(BaseModel):
    """Body para PATCH /api/strength/blocks/{id}/archive."""

    is_archived: bool


@router.patch(
    "/blocks/{block_id}/archive",
    response_model=BlockOut,
    summary="Archivar o desarchivar un bloque de fuerza",
    description=(
        "Marca is_archived en el bloque. Bloques archivados permanecen "
        "adjuntos a sesiones (solo lectura ahí) y se excluyen de "
        "GET /blocks por defecto. 404 cuando el bloque no existe/pertenece "
        "a otro club."
    ),
)
async def archive_block(
    block_id: int,
    payload: ArchiveBlockIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> BlockOut:
    """Toggle a block's archived state."""
    club_id = await _coach_club_id(db, current_user)
    block = await blocks_svc.archive_block(
        db, block_id=block_id, club_id=club_id, is_archived=payload.is_archived
    )
    if block is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bloque de fuerza {block_id} no encontrado.",
        )
    return _serialize_block_out(block)


# ---------------------------------------------------------------------------
# POST /api/strength/blocks/{id}/attach — attach block to session (T022)
# ---------------------------------------------------------------------------


@router.post(
    "/blocks/{block_id}/attach",
    response_model=AttachOut,
    status_code=status.HTTP_201_CREATED,
    summary="Adjuntar un bloque de fuerza a una sesión",
    description=(
        "Adjunta un bloque reutilizable a una sesión de entrenamiento. "
        "409 si ya está adjunto (par único). 404 si el bloque o la sesión "
        "son desconocidos o pertenecen a otro club."
    ),
)
async def attach_block(
    block_id: int,
    payload: AttachIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> AttachOut:
    """Attach a block to a training session (club-scoped, unique pair)."""
    club_id = await _coach_club_id(db, current_user)
    link = await blocks_svc.attach_block_to_session(
        db,
        block_id=block_id,
        training_session_id=payload.training_session_id,
        club_id=club_id,
        attached_by_user_id=current_user.id,
    )
    return AttachOut(
        id=link.id,
        training_session_id=link.training_session_id,
        block_id=link.block_id,
        position=link.position,
        attached_at=link.attached_at,
    )


# ---------------------------------------------------------------------------
# DELETE /api/strength/blocks/{id}/attach/{session_id} — detach (T022)
# ---------------------------------------------------------------------------


@router.delete(
    "/blocks/{block_id}/attach/{training_session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desadjuntar un bloque de fuerza de una sesión",
    description=(
        "Elimina el vínculo bloque↔sesión. El bloque en sí no se elimina. "
        "404 cuando el bloque no existe o pertenece a otro club."
    ),
)
async def detach_block(
    block_id: int,
    training_session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> None:
    """Detach a block from a session (idempotent no-op when not attached)."""
    club_id = await _coach_club_id(db, current_user)
    await blocks_svc.detach_block_from_session(
        db,
        block_id=block_id,
        training_session_id=training_session_id,
        club_id=club_id,
    )


# ---------------------------------------------------------------------------
# GET /api/strength/sessions/{id}/blocks — blocks attached to session (T022)
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{training_session_id}/blocks",
    response_model=dict[str, Any],
    summary="Bloques de fuerza adjuntos a una sesión",
    description=(
        "Devuelve { items: [BlockOut] } — bloques adjuntos a una sesión, "
        "para renderizar el plan de la sesión (FR-012/FR-013)."
    ),
)
async def list_session_blocks(
    training_session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> dict[str, Any]:
    """Return the blocks attached to a session, club-scoped."""
    club_id = await _coach_club_id(db, current_user)
    blocks = await blocks_svc.list_session_blocks(
        db, training_session_id=training_session_id, club_id=club_id
    )
    items = [_serialize_block_out(block) for block in blocks]
    return {"items": [item.model_dump() for item in items]}


# ---------------------------------------------------------------------------
# Club-scope guard for progress endpoints (coach must belong to athlete's club)
# ---------------------------------------------------------------------------


async def _require_athlete_club_scope(
    db: AsyncSession,
    athlete_id: int,
    current_user: User,
) -> None:
    """Verify that a coach belongs to the same club as the target athlete.

    Mirrors ``app/routers/technique.py:_require_athlete_club_scope`` (feature
    018). Admin users pass unconditionally. Coach users receive 403 when the
    athlete does not belong to any of the coach's clubs. The athlete
    existence check is intentionally opaque: a non-existent athlete_id
    always raises 404 with no PII in the detail (FR-020).

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

    result = await db.execute(
        select(Athlete.club_id).where(Athlete.id == athlete_id)
    )
    athlete_club_id = result.scalar_one_or_none()
    if athlete_club_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Atleta {athlete_id} no encontrado.",
        )

    club_role = await user_club_role(db, current_user.id, athlete_club_id)
    if club_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso al progreso de este atleta.",
        )


# ---------------------------------------------------------------------------
# GET /api/strength/athletes/{id}/progress — progress read (T035)
# ---------------------------------------------------------------------------


@router.get(
    "/athletes/{athlete_id}/progress",
    response_model=dict[str, Any],
    summary="Leer progreso de fuerza de un atleta",
    description=(
        "Devuelve { items: [ProgressOut] } — el último registro por "
        "ejercicio para un único atleta (append-only, latest-wins). "
        "Coach/admin únicamente — sin PII de menores más allá del id de "
        "ruta (FR-020). 404 cuando el athlete_id no existe. 403 cuando el "
        "coach no pertenece al club del atleta."
    ),
)
async def get_athlete_progress(
    athlete_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> dict[str, Any]:
    """Return the latest strength progress note per exercise for one athlete."""
    await _require_athlete_club_scope(db, athlete_id, current_user)
    try:
        rows = await progress_svc.get_latest_progress(db, athlete_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    items = [ProgressOut(**row) for row in rows]
    return {"items": [item.model_dump() for item in items]}


# ---------------------------------------------------------------------------
# POST /api/strength/athletes/{id}/progress — progress append (T035)
# ---------------------------------------------------------------------------


@router.post(
    "/athletes/{athlete_id}/progress",
    response_model=ProgressOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nota de progreso de fuerza",
    description=(
        "Añade una nota de progreso append-only para el atleta (US4). "
        "Body: ProgressIn. Respuesta 201: ProgressOut. 404 cuando el "
        "atleta o el exercise_id no existen. 403 cuando el coach no "
        "pertenece al club del atleta."
    ),
)
async def create_athlete_progress(
    athlete_id: int,
    payload: ProgressIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> ProgressOut:
    """Append a new strength progress note for the athlete (append-only)."""
    await _require_athlete_club_scope(db, athlete_id, current_user)
    try:
        note = await progress_svc.add_progress_note(
            db,
            athlete_id,
            exercise_id=payload.exercise_id,
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

    # Capture the response fields BEFORE commit: ``add_progress_note`` already
    # eager-loaded ``note.exercise`` (selectinload), but ``db.commit()`` below
    # expires all attributes by default (expire_on_commit=True). Touching
    # ``note.exercise`` afterwards would trigger a synchronous lazy load,
    # which raises ``MissingGreenlet`` under AsyncSession.
    out = ProgressOut(
        exercise_id=note.exercise_id,
        exercise_name=note.exercise.name,
        status=note.status,
        coach_note=note.coach_note,
        season=note.season,
        recorded_at=note.recorded_at,
    )
    await db.commit()
    return out
