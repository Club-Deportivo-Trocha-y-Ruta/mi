"""Router for Structured Interval Training with Strava Correlation (feature 026).

Registered in ``app/main.py`` with prefix ``/api/intervals``.

RBAC: every route requires coach or admin (``_require_coach_or_admin``
dependency, same pattern as ``routers/strength.py``), plus club-scope
verification performed inline — a structure/template/session/activity that
belongs to another club is treated as **not found** (404), never as a 403
that would leak its existence (data-model.md "Access control invariants").
Parents and the athlete role always receive 403 from
``_require_coach_or_admin`` itself (FR-018).

Route inventory (contract: specs/026-structured-interval-training/contracts/api.md):

  POST   /api/intervals/structures                         — create (US1)
  GET    /api/intervals/sessions/{id}/structure             — read by session (US1)
  PUT    /api/intervals/structures/{id}                     — full replace (US1)
  DELETE /api/intervals/structures/{id}                     — delete (US1)
  POST   /api/intervals/templates                           — create (US4)
  GET    /api/intervals/templates                           — list/filter (US4)
  PUT    /api/intervals/templates/{id}                      — full replace (US4)
  PATCH  /api/intervals/templates/{id}/archive              — archive/unarchive (US4)
  POST   /api/intervals/templates/{id}/attach                — copy-on-attach (US4)
  GET    /api/intervals/sessions/{id}/match                  — plan-vs-actual detail (US2)
  POST   /api/intervals/structures/{id}/recalculate          — manual recompute (US2)
  GET    /api/intervals/sessions/{id}/instructivo             — brand PDF (US3)

Deferred matching (research.md D6): structure create/update/attach dispatch a
background recompute (``triggered_by=structure_change``) for every activity
already linked to the session — the request stays fast (no outbound Strava
call on the write path); ``recalculate`` dispatches the same job with
``triggered_by=manual``. The link-triggered dispatch (``triggered_by=link``)
lives in ``routers/activities.py::link_activity`` (edited by a different
task in this feature, not this file).

Privacidad (Ley 1581, menores): laps only ever appear embedded inside the
match-detail response (``MatchDetailOut.blocks``/``extra_laps``), never as a
standalone listing — see ``schemas/intervals.py`` module docstring.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_document_generator, get_task_dispatcher, require_role
from app.models.club import Club, ClubMember
from app.models.interval_structure import IntervalStructure, IntervalTemplate
from app.models.strava_activity import StravaActivity
from app.models.strava_activity_lap import IntervalMatchResult, MatchTrigger
from app.models.technique_exercise import AgeBand
from app.models.training_session import TrainingSession
from app.models.user import User, UserRole
from app.schemas.intervals import (
    BlockOut,
    ExtraLapOut,
    MatchActivityOut,
    MatchBlockOut,
    MatchDetailOut,
    MatchSummary,
    RecalculateIn,
    RecalculateOut,
    StructureCreate,
    StructureOut,
    StructureUpdate,
    TemplateAttachIn,
    TemplateCreate,
    TemplateListOut,
    TemplateOut,
    TemplateUpdate,
)
from app.services.intervals import match_runner
from app.services.intervals import structures as structures_svc
from app.services.intervals import templates as templates_svc
from app.services.notification.document_generator import DocumentGenerator
from app.services.notification.task_dispatcher import TaskDispatcher
from app.services.intervals.instructivo_pdf import generate_instructivo_pdf

router = APIRouter()

BrandLiteral = Literal["garmin", "magene", "igpsport"]

# ---------------------------------------------------------------------------
# RBAC dependency: coach or admin only (mirrors routers/strength.py)
# ---------------------------------------------------------------------------

_coach_or_admin = require_role([UserRole.admin, UserRole.coach])


async def _require_coach_or_admin(
    current_user: User = Depends(_coach_or_admin),
) -> User:
    """Gate that limits access to coach and admin roles.

    Raises:
        HTTPException 403: when the authenticated user is a parent, athlete,
            or any unrecognized role (FR-018).

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
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_block_out(block) -> BlockOut:
    """Map an ``IntervalStructureBlock``/``IntervalTemplateBlock`` ORM row to
    ``BlockOut``. Reads only scalar columns — no I/O, no lazy load risk."""
    return BlockOut(
        id=block.id,
        position=block.position,
        block_type=block.block_type.value,
        duration_s=block.duration_s,
        target_zone=block.target_zone.value,
        target_cadence_rpm=block.target_cadence_rpm,
        repeat_group=block.repeat_group,
        repeat_count=block.repeat_count,
    )


def _serialize_structure_out(structure: IntervalStructure) -> StructureOut:
    """Map an ``IntervalStructure`` ORM row (``blocks`` and
    ``age_gate_confirmed_by`` already eager-loaded by the service layer) to
    ``StructureOut``."""
    confirmed_by_name: str | None = None
    if structure.age_gate_confirmed_by is not None:
        confirmed_by_name = (
            f"{structure.age_gate_confirmed_by.first_name} "
            f"{structure.age_gate_confirmed_by.last_name}"
        )
    return StructureOut(
        id=structure.id,
        training_session_id=structure.training_session_id,
        target_age_band=structure.target_age_band.value,
        age_gate_confirmed=structure.age_gate_confirmed,
        age_gate_confirmed_by=confirmed_by_name,
        age_gate_confirmed_at=structure.age_gate_confirmed_at,
        blocks=[_serialize_block_out(b) for b in structure.blocks],
        total_planned_duration_s=structures_svc.total_planned_duration_s(structure.blocks),
        created_at=structure.created_at,
        updated_at=structure.updated_at,
    )


def _serialize_template_out(template: IntervalTemplate) -> TemplateOut:
    """Map an ``IntervalTemplate`` ORM row (``blocks`` eager-loaded) to
    ``TemplateOut``."""
    return TemplateOut(
        id=template.id,
        name=template.name,
        target_age_band=template.target_age_band.value,
        mesocycle_phase=template.mesocycle_phase,
        competition_proximity=template.competition_proximity,
        is_archived=template.is_archived,
        blocks=[_serialize_block_out(b) for b in template.blocks],
        total_planned_duration_s=structures_svc.total_planned_duration_s(template.blocks),
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


# ---------------------------------------------------------------------------
# Deferred-match dispatch helper (research.md D6, trigger 2)
# ---------------------------------------------------------------------------


async def _dispatch_match_for_linked_activities(
    db: AsyncSession,
    dispatcher: TaskDispatcher,
    *,
    training_session_id: int,
    structure_id: int,
    triggered_by: MatchTrigger,
) -> None:
    """Dispatch a deferred match recompute for every activity already linked
    to ``training_session_id`` (research.md D6, trigger 2: "structure
    create/update on a session that already has a linked activity"). Called
    after structure create, update, and template attach — a no-op (dispatches
    nothing) when the session has no linked activity yet, which is the common
    case.

    Side-effects: one SELECT; queues zero or more background jobs via
    ``dispatcher`` (does not await them — ``TaskDispatcher`` owns that).
    """
    result = await db.execute(
        select(StravaActivity.id).where(
            StravaActivity.training_session_id == training_session_id
        )
    )
    for activity_id in result.scalars().all():
        dispatcher.dispatch(
            match_runner.run_match_deferred,
            structure_id=structure_id,
            strava_activity_id=activity_id,
            triggered_by=triggered_by,
        )


# ---------------------------------------------------------------------------
# POST /api/intervals/structures — create (US1)
# ---------------------------------------------------------------------------


@router.post(
    "/structures",
    response_model=StructureOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear la estructura de intervalos de una sesión",
    description=(
        "Crea la estructura 1:1 de una sesión de entrenamiento. 404 si la "
        "sesión no existe o es de otro club. 409 si la sesión ya tiene una "
        "estructura (usar PUT). 422 con detail.code cadence_below_minimum / "
        "invalid_repeat_group / age_gate_z3_blocked / "
        "age_gate_confirmation_required según el guardarraíl violado."
    ),
)
async def create_structure(
    payload: StructureCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
) -> StructureOut:
    """Create a session's interval structure; dispatches a deferred match
    recompute when the session already has a linked activity (D6)."""
    club_id = await _coach_club_id(db, current_user)
    structure = await structures_svc.create_structure(
        db,
        training_session_id=payload.training_session_id,
        target_age_band=AgeBand(payload.target_age_band),
        age_gate_confirmed=payload.age_gate_confirmed,
        blocks=payload.blocks,
        club_id=club_id,
        created_by_user_id=current_user.id,
    )
    await _dispatch_match_for_linked_activities(
        db,
        dispatcher,
        training_session_id=structure.training_session_id,
        structure_id=structure.id,
        triggered_by=MatchTrigger.structure_change,
    )
    return _serialize_structure_out(structure)


# ---------------------------------------------------------------------------
# GET /api/intervals/sessions/{id}/structure — read by session (US1)
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{training_session_id}/structure",
    response_model=StructureOut,
    summary="Leer la estructura de intervalos de una sesión",
    description=(
        "404 si la sesión no tiene estructura, no existe, o pertenece a "
        "otro club (el frontend renderiza el estado vacío/create)."
    ),
)
async def get_session_structure(
    training_session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> StructureOut:
    """Return the session's structure, or 404 when it has none."""
    club_id = await _coach_club_id(db, current_user)
    structure = await structures_svc.get_structure_by_session(
        db, training_session_id=training_session_id, club_id=club_id
    )
    if structure is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La sesión {training_session_id} no tiene estructura de intervalos.",
        )
    return _serialize_structure_out(structure)


# ---------------------------------------------------------------------------
# PUT /api/intervals/structures/{id} — full replace (US1)
# ---------------------------------------------------------------------------


@router.put(
    "/structures/{structure_id}",
    response_model=StructureOut,
    summary="Reemplazar la estructura de intervalos",
    description=(
        "Reemplazo completo de banda + bloques (mismo shape que POST, sin "
        "training_session_id). Mismos códigos 422 que la creación. Si la "
        "sesión tiene actividad vinculada, despacha un recálculo diferido "
        "(triggered_by=structure_change). 404 si no existe / es de otro club."
    ),
)
async def update_structure(
    structure_id: int,
    payload: StructureUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
) -> StructureOut:
    """Full replace of a structure's band + blocks."""
    club_id = await _coach_club_id(db, current_user)
    structure = await structures_svc.update_structure(
        db,
        structure_id=structure_id,
        club_id=club_id,
        target_age_band=AgeBand(payload.target_age_band),
        age_gate_confirmed=payload.age_gate_confirmed,
        blocks=payload.blocks,
    )
    if structure is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Estructura de intervalos {structure_id} no encontrada.",
        )
    await _dispatch_match_for_linked_activities(
        db,
        dispatcher,
        training_session_id=structure.training_session_id,
        structure_id=structure.id,
        triggered_by=MatchTrigger.structure_change,
    )
    return _serialize_structure_out(structure)


# ---------------------------------------------------------------------------
# DELETE /api/intervals/structures/{id} — delete (US1)
# ---------------------------------------------------------------------------


@router.delete(
    "/structures/{structure_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Borrar la estructura de intervalos",
    description=(
        "Cascada: borra bloques y resultados de emparejamiento. Las vueltas "
        "(laps) de la actividad se preservan (D7). 404 si no existe / es de "
        "otro club."
    ),
)
async def delete_structure(
    structure_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> None:
    """Delete a structure (cascades blocks + match results; laps preserved)."""
    club_id = await _coach_club_id(db, current_user)
    deleted = await structures_svc.delete_structure(
        db, structure_id=structure_id, club_id=club_id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Estructura de intervalos {structure_id} no encontrada.",
        )


# ---------------------------------------------------------------------------
# POST /api/intervals/templates — create (US4)
# ---------------------------------------------------------------------------


@router.post(
    "/templates",
    response_model=TemplateOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una plantilla de intervalos",
    description=(
        "Crea una plantilla reutilizable, club-scoped. Mismos códigos 422 "
        "que una estructura — Z3+ en banda 10-12 se rechaza al guardar "
        "(la confirmación real ocurre al adjuntar)."
    ),
)
async def create_template(
    payload: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> TemplateOut:
    """Create a reusable interval template owned by the coach's club."""
    club_id = await _coach_club_id(db, current_user)
    template = await templates_svc.create_template(
        db,
        name=payload.name,
        target_age_band=AgeBand(payload.target_age_band),
        mesocycle_phase=payload.mesocycle_phase,
        competition_proximity=payload.competition_proximity,
        blocks=payload.blocks,
        club_id=club_id,
        created_by_user_id=current_user.id,
    )
    return _serialize_template_out(template)


# ---------------------------------------------------------------------------
# GET /api/intervals/templates — list/filter (US4)
# ---------------------------------------------------------------------------


@router.get(
    "/templates",
    response_model=TemplateListOut,
    summary="Listar y filtrar plantillas de intervalos",
    description=(
        "Lista las plantillas del club del coach, filtrables por "
        "age_band/mesocycle_phase/competition_proximity (US4-AC2). Excluye "
        "archivadas por defecto — ?include_archived=true las incluye."
    ),
)
async def list_templates(
    age_band: Literal["10-12", "13-15"] | None = Query(default=None),
    mesocycle_phase: str | None = Query(default=None),
    competition_proximity: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> TemplateListOut:
    """Return the coach's club templates, filtered by the three tags."""
    club_id = await _coach_club_id(db, current_user)
    templates, total = await templates_svc.list_templates(
        db,
        club_id=club_id,
        age_band=AgeBand(age_band) if age_band is not None else None,
        mesocycle_phase=mesocycle_phase,
        competition_proximity=competition_proximity,
        include_archived=include_archived,
    )
    return TemplateListOut(
        items=[_serialize_template_out(t) for t in templates], total=total
    )


# ---------------------------------------------------------------------------
# PUT /api/intervals/templates/{id} — full replace (US4)
# ---------------------------------------------------------------------------


@router.put(
    "/templates/{template_id}",
    response_model=TemplateOut,
    summary="Reemplazar una plantilla de intervalos",
    description=(
        "Reemplazo completo (mismo shape que POST). Editar una plantilla "
        "nunca muta las sesiones que ya la adjuntaron (copy-on-attach). "
        "404 si no existe / es de otro club."
    ),
)
async def update_template(
    template_id: int,
    payload: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> TemplateOut:
    """Full replace of a template's fields and blocks."""
    club_id = await _coach_club_id(db, current_user)
    template = await templates_svc.update_template(
        db,
        template_id=template_id,
        club_id=club_id,
        name=payload.name,
        target_age_band=AgeBand(payload.target_age_band),
        mesocycle_phase=payload.mesocycle_phase,
        competition_proximity=payload.competition_proximity,
        blocks=payload.blocks,
    )
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plantilla de intervalos {template_id} no encontrada.",
        )
    return _serialize_template_out(template)


# ---------------------------------------------------------------------------
# PATCH /api/intervals/templates/{id}/archive — archive/unarchive (US4)
# ---------------------------------------------------------------------------


class ArchiveTemplateIn(BaseModel):
    """Body para PATCH /api/intervals/templates/{id}/archive."""

    is_archived: bool


@router.patch(
    "/templates/{template_id}/archive",
    response_model=TemplateOut,
    summary="Archivar o desarchivar una plantilla de intervalos",
    description=(
        "Marca is_archived. Plantillas archivadas se excluyen de "
        "GET /templates por defecto pero nunca se borran físicamente. "
        "404 si no existe / es de otro club."
    ),
)
async def archive_template(
    template_id: int,
    payload: ArchiveTemplateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> TemplateOut:
    """Toggle a template's archived state."""
    club_id = await _coach_club_id(db, current_user)
    template = await templates_svc.archive_template(
        db, template_id=template_id, club_id=club_id, is_archived=payload.is_archived
    )
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plantilla de intervalos {template_id} no encontrada.",
        )
    return _serialize_template_out(template)


# ---------------------------------------------------------------------------
# POST /api/intervals/templates/{id}/attach — copy-on-attach (US4)
# ---------------------------------------------------------------------------


@router.post(
    "/templates/{template_id}/attach",
    response_model=StructureOut,
    status_code=status.HTTP_201_CREATED,
    summary="Adjuntar una plantilla a una sesión",
    description=(
        "Clona los bloques de la plantilla en una estructura nueva para la "
        "sesión (copy-on-attach, FR-009). Corre el guardarraíl completo "
        "contra la banda/bloques de la plantilla en este momento. 404 si la "
        "plantilla o la sesión no existen / son de otro club. 409 si la "
        "sesión ya tiene estructura. 422 con los mismos códigos que crear "
        "una estructura."
    ),
)
async def attach_template(
    template_id: int,
    payload: TemplateAttachIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
) -> StructureOut:
    """Clone a template's blocks into a new structure for the session."""
    club_id = await _coach_club_id(db, current_user)
    structure = await templates_svc.attach_template(
        db,
        template_id=template_id,
        training_session_id=payload.training_session_id,
        club_id=club_id,
        age_gate_confirmed=payload.age_gate_confirmed,
        attached_by_user_id=current_user.id,
    )
    await _dispatch_match_for_linked_activities(
        db,
        dispatcher,
        training_session_id=structure.training_session_id,
        structure_id=structure.id,
        triggered_by=MatchTrigger.structure_change,
    )
    return _serialize_structure_out(structure)


# ---------------------------------------------------------------------------
# Shared: resolve the activity to compare against a structure (US2)
# ---------------------------------------------------------------------------


async def _resolve_linked_activity(
    db: AsyncSession, *, training_session_id: int, activity_id: int | None
) -> StravaActivity | None:
    """Resolve the activity to compare against a session's structure.

    ``activity_id`` given: must be linked to ``training_session_id`` (else
    ``None``). Omitted: resolves the session's linked activity — when more
    than one is linked (contract only specifies the "exactly one" case),
    the most recent by ``start_date_utc`` is used, a safe degrade at this
    club's scale. Returns ``None`` when the session has no linked activity.

    Side-effects: one SELECT. No writes.
    """
    stmt = select(StravaActivity).where(
        StravaActivity.training_session_id == training_session_id
    )
    if activity_id is not None:
        stmt = stmt.where(StravaActivity.id == activity_id)
    stmt = stmt.order_by(StravaActivity.start_date_utc.desc())
    result = await db.execute(stmt)
    return result.scalars().first()


def _build_computed_match_detail(
    structure_id: int,
    activity: StravaActivity,
    match_result: IntervalMatchResult,
) -> MatchDetailOut:
    """Build ``MatchDetailOut`` (status=computed) from the persisted
    ``result_json`` (already validated by ``MatchResultPayload`` before
    being written — see ``services/intervals/matching.py``).

    ``lap_moving_time_s``/``lap_average_speed_m_s`` on ``MatchBlockOut`` stay
    ``None`` here: the persisted ``result_json`` block shape
    (``MatchResultBlock``, data-model.md §6) only carries
    ``lap_elapsed_time_s``/``lap_average_heartrate`` — both remain optional
    on the schema for exactly this reason.
    """
    payload = match_result.result_json
    blocks = [
        MatchBlockOut(
            flat_index=b["flat_index"],
            block_type=b["block_type"],
            repeat_iteration=b.get("repeat_iteration"),
            planned_duration_s=b["planned_duration_s"],
            target_zone=b["target_zone"],
            target_cadence_rpm=b["target_cadence_rpm"],
            lap_index=b.get("lap_index"),
            lap_elapsed_time_s=b.get("lap_elapsed_time_s"),
            lap_average_heartrate=b.get("lap_average_heartrate"),
            status=b["status"],
        )
        for b in payload.get("blocks", [])
    ]
    extra_laps = [
        ExtraLapOut(
            lap_index=e["lap_index"],
            elapsed_time_s=e["elapsed_time_s"],
            average_heartrate=e.get("average_heartrate"),
        )
        for e in payload.get("extra_laps", [])
    ]
    summary_dict = payload.get("summary") or {}

    return MatchDetailOut(
        structure_id=structure_id,
        status="computed",
        activity=MatchActivityOut(
            id=activity.id,
            start_date_local=activity.start_date_local,
            elapsed_time_s=activity.elapsed_time_s,
            sport_type=activity.sport_type,
        ),
        computed_at=match_result.computed_at,
        engine_version=match_result.engine_version,
        tolerance_pct=payload.get("tolerance_pct"),
        blocks=blocks,
        extra_laps=extra_laps,
        summary=MatchSummary(**summary_dict),
    )


# ---------------------------------------------------------------------------
# GET /api/intervals/sessions/{id}/match — plan-vs-actual detail (US2)
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{training_session_id}/match",
    response_model=MatchDetailOut,
    summary="Detalle de comparación plan-vs-real de una sesión",
    description=(
        "FR-017. activity_id opcional cuando la sesión tiene exactamente "
        "una actividad vinculada. status: computed | no_activity | "
        "computing | failed (siempre 200 — nunca un error crudo). 404 si la "
        "sesión no tiene estructura, o si activity_id no corresponde a una "
        "actividad vinculada a la sesión."
    ),
)
async def get_session_match(
    training_session_id: int,
    activity_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
) -> MatchDetailOut:
    """Return the plan-vs-actual comparison detail view for a session."""
    club_id = await _coach_club_id(db, current_user)
    structure = await structures_svc.get_structure_by_session(
        db, training_session_id=training_session_id, club_id=club_id
    )
    if structure is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La sesión {training_session_id} no tiene estructura de intervalos.",
        )

    activity = await _resolve_linked_activity(
        db, training_session_id=training_session_id, activity_id=activity_id
    )
    if activity is None:
        if activity_id is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"La actividad {activity_id} no está vinculada a la "
                    f"sesión {training_session_id}."
                ),
            )
        return MatchDetailOut(structure_id=structure.id, status="no_activity")

    result = await db.execute(
        select(IntervalMatchResult).where(
            IntervalMatchResult.structure_id == structure.id,
            IntervalMatchResult.strava_activity_id == activity.id,
        )
    )
    match_result = result.scalar_one_or_none()
    if match_result is not None:
        return _build_computed_match_detail(structure.id, activity, match_result)

    if match_runner.has_failed(structure.id, activity.id):
        return MatchDetailOut(
            structure_id=structure.id,
            status="failed",
            activity=MatchActivityOut(
                id=activity.id,
                start_date_local=activity.start_date_local,
                elapsed_time_s=activity.elapsed_time_s,
                sport_type=activity.sport_type,
            ),
            retry_available=True,
        )

    return MatchDetailOut(
        structure_id=structure.id,
        status="computing",
        activity=MatchActivityOut(
            id=activity.id,
            start_date_local=activity.start_date_local,
            elapsed_time_s=activity.elapsed_time_s,
            sport_type=activity.sport_type,
        ),
    )


# ---------------------------------------------------------------------------
# POST /api/intervals/structures/{id}/recalculate — manual recompute (US2)
# ---------------------------------------------------------------------------


@router.post(
    "/structures/{structure_id}/recalculate",
    response_model=RecalculateOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Recalcular manualmente la comparación plan-vs-real",
    description=(
        "Vuelve a traer las vueltas de Strava y recalcula (FR-015, "
        "triggered_by=manual). activity_id opcional bajo la misma regla de "
        "actividad única. 404 si la estructura no existe / es de otro club, "
        "o si activity_id no corresponde a una actividad vinculada. 409 si "
        "la sesión no tiene ninguna actividad vinculada."
    ),
)
async def recalculate_match(
    structure_id: int,
    payload: RecalculateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
) -> RecalculateOut:
    """Dispatch a manual deferred recompute for a structure↔activity pair."""
    club_id = await _coach_club_id(db, current_user)
    structure = await structures_svc.get_structure(
        db, structure_id=structure_id, club_id=club_id
    )
    if structure is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Estructura de intervalos {structure_id} no encontrada.",
        )

    activity = await _resolve_linked_activity(
        db,
        training_session_id=structure.training_session_id,
        activity_id=payload.activity_id,
    )
    if activity is None:
        if payload.activity_id is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"La actividad {payload.activity_id} no está vinculada a "
                    "la sesión de esta estructura."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La sesión no tiene ninguna actividad de Strava vinculada.",
        )

    dispatcher.dispatch(
        match_runner.run_match_deferred,
        structure_id=structure.id,
        strava_activity_id=activity.id,
        triggered_by=MatchTrigger.manual,
    )
    return RecalculateOut(status="computing")


# ---------------------------------------------------------------------------
# GET /api/intervals/sessions/{id}/instructivo — brand PDF (US3)
# ---------------------------------------------------------------------------


async def _get_session_or_404(
    db: AsyncSession, *, training_session_id: int, club_id: int
) -> TrainingSession:
    result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.id == training_session_id,
            TrainingSession.club_id == club_id,
        )
    )
    session_obj = result.scalar_one_or_none()
    if session_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sesión de entrenamiento {training_session_id} no encontrada.",
        )
    return session_obj


@router.get(
    "/sessions/{training_session_id}/instructivo",
    response_class=Response,
    summary="Descargar el instructivo PDF de una estructura de intervalos",
    responses={
        200: {"content": {"application/pdf": {}}, "description": "Archivo PDF"},
        404: {"description": "La sesión no tiene estructura, no existe, o es de otro club"},
        422: {"description": "Marca de ciclocomputador no soportada"},
    },
    description=(
        "FR-010/FR-011. brand=garmin|magene|igpsport. 404 si la sesión no "
        "tiene estructura de intervalos (el frontend deshabilita el botón "
        "en ese estado; el servidor igual lo garantiza)."
    ),
)
async def download_instructivo_pdf(
    training_session_id: int,
    brand: BrandLiteral = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_coach_or_admin),
    generator: DocumentGenerator = Depends(get_document_generator),
) -> Response:
    """Generate and return the brand-specific instructivo PDF."""
    club_id = await _coach_club_id(db, current_user)

    structure = await structures_svc.get_structure_by_session(
        db, training_session_id=training_session_id, club_id=club_id
    )
    if structure is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La sesión {training_session_id} no tiene estructura de intervalos.",
        )

    session_obj = await _get_session_or_404(
        db, training_session_id=training_session_id, club_id=club_id
    )

    club_result = await db.execute(select(Club).where(Club.id == club_id))
    club = club_result.scalar_one()

    doc = await generate_instructivo_pdf(
        generator,
        structure=structure,
        training_session=session_obj,
        brand=brand,
        club_name=club.name,
    )

    return Response(
        content=doc.data,
        media_type=doc.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{doc.filename}"',
            "Content-Length": str(len(doc.data)),
        },
    )
