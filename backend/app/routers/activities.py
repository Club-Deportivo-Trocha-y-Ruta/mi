"""Router for Strava activity review & coach-gated session linking (feature 025).

Registered in ``app/main.py`` with prefix ``/api`` and tag ``activities``,
guarded so it is only included when ``settings.strava_enabled`` is true.

RBAC: coach/admin review the full club list and link/unlink activities to
training sessions; parents may only read their own children's activities
(``services/permissions.py`` helpers ``can_view_activity`` /
``can_link_activity``).

Route inventory (contract: specs/025-strava-activity-sync/contracts/api.md
§C):

  GET   /api/activities                                    — coach/admin review list
  GET   /api/athletes/{athlete_id}/activities               — athlete-scoped list (T020, parent scope T035)
  GET   /api/activities/{id}/session-suggestions             — link candidates (T029)
  PATCH /api/activities/{id}/link                            — link/unlink (coach/admin only) (T029)
  GET   /api/training-sessions/{session_id}/activities        — session-scoped list (T029, parent scope T035)

Privacidad (Ley 1581, menores de edad): ``ActivityOut`` nunca incluye
coordenadas, polylines, mapas ni texto de ubicación libre — ver
``schemas/strava.py`` y ``models/strava_activity.py`` (esas columnas no
existen en el modelo). Los logs de este router deben usar solo IDs
numéricos, nunca nombres.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_current_user, get_db, get_task_dispatcher
from app.models.athlete import Athlete
from app.models.club import ClubRole
from app.models.interval_structure import IntervalStructure
from app.models.strava_activity import StravaActivity
from app.models.strava_activity_lap import IntervalMatchResult, MatchTrigger
from app.models.training_session import SessionAttendance, TrainingSession
from app.models.user import User, UserRole
from app.schemas.strava import (
    ActivityLinkOut,
    ActivityListOut,
    ActivityOut,
    LinkUpdateIn,
    SessionActivitiesOut,
    SessionSuggestionListOut,
    SessionSuggestionOut,
)
from app.services.intervals.match_runner import run_match_deferred
from app.services.notification.task_dispatcher import TaskDispatcher
from app.services.permissions import (
    can_link_activity,
    can_view_activity,
    can_view_session,
    filter_activities_for_parent,
    parent_athlete_ids,
)
from app.services.utils.dates_es import format_date_es

router = APIRouter(tags=["activities"])

_ACTIVITY_EAGER_OPTIONS = (
    selectinload(StravaActivity.athlete),
    selectinload(StravaActivity.training_session),
    selectinload(StravaActivity.linked_by),
)


def _session_label(session: TrainingSession) -> str:
    """Etiqueta legible de una sesión de entrenamiento para ActivityLinkOut."""
    return f"{format_date_es(session.scheduled_date)} · {session.location}"


def _serialize_activity_out(activity: StravaActivity) -> ActivityOut:
    """Map a StravaActivity ORM row to ActivityOut.

    The ``athlete``, ``training_session`` and ``linked_by`` relationships
    must already be eagerly loaded by the caller (selectinload) to avoid
    N+1 queries and async lazy-load errors.
    """
    link: ActivityLinkOut | None = None
    if activity.training_session_id is not None and activity.training_session is not None:
        linked_by_name = (
            f"{activity.linked_by.first_name} {activity.linked_by.last_name}"
            if activity.linked_by is not None
            else ""
        )
        link = ActivityLinkOut(
            training_session_id=activity.training_session_id,
            session_label=_session_label(activity.training_session),
            linked_by=linked_by_name,
            linked_at=activity.linked_at,
        )

    return ActivityOut(
        id=activity.id,
        athlete_id=activity.athlete_id,
        athlete_name=f"{activity.athlete.first_name} {activity.athlete.last_name}",
        name=activity.name,
        sport_type=activity.sport_type,
        start_date_local=activity.start_date_local,
        elapsed_time_s=activity.elapsed_time_s,
        moving_time_s=activity.moving_time_s,
        distance_m=activity.distance_m,
        total_elevation_gain_m=activity.total_elevation_gain_m,
        average_heartrate=activity.average_heartrate,
        max_heartrate=activity.max_heartrate,
        is_trainer=activity.is_trainer,
        upstream_state=activity.upstream_state.value,
        summary_complete=activity.summary_complete,
        link=link,
    )


@router.get("/athletes/{athlete_id}/activities", response_model=ActivityListOut)
async def list_athlete_activities(
    athlete_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActivityListOut:
    """Paginated Strava activities for one athlete.

    Roles: admin, coach (athlete's club), parent (own child) — via
    ``can_view_activity``. Ordered ``start_date_utc DESC`` (most recent
    first).
    """
    athlete_result = await db.execute(select(Athlete).where(Athlete.id == athlete_id))
    athlete = athlete_result.scalar_one_or_none()
    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Atleta no encontrado"
        )

    if not await can_view_activity(current_user, athlete_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permiso para ver las actividades de este atleta",
        )

    count_result = await db.execute(
        select(func.count())
        .select_from(StravaActivity)
        .where(StravaActivity.athlete_id == athlete_id)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(StravaActivity)
        .where(StravaActivity.athlete_id == athlete_id)
        .options(*_ACTIVITY_EAGER_OPTIONS)
        .order_by(StravaActivity.start_date_utc.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    activities = result.scalars().all()

    return ActivityListOut(
        items=[_serialize_activity_out(a) for a in activities],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# GET /activities — lista de revisión para coach/admin (T029, FR-010)
# ---------------------------------------------------------------------------


@router.get("/activities", response_model=ActivityListOut)
async def list_activities(
    linked: str = Query(default="all", pattern="^(true|false|all)$"),
    athlete_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActivityListOut:
    """Lista paginada de actividades de Strava para revisión (FR-010).

    Roles: admin (todos los clubes), coach (solo atletas de los clubes en
    los que tiene rol ``coach`` — mismo criterio que
    ``dependencies.verify_athlete_access``). Parents reciben 403: su vista
    de solo lectura vive en ``GET /athletes/{athlete_id}/activities``.

    Filtros: ``linked`` (``true``/``false``/``all``, default ``all``),
    ``athlete_id``, ``date_from``/``date_to`` (sobre la fecha local
    ``start_date_local``, coherente con el agrupamiento por día de la UI de
    revisión). Orden: ``start_date_utc DESC``; con ``linked=all`` las
    actividades sin vincular aparecen primero (badge ámbar).
    """
    if current_user.role not in {UserRole.admin, UserRole.coach}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permiso para revisar actividades",
        )

    filters = []

    if current_user.role == UserRole.coach:
        coach_club_ids = {
            m.club_id
            for m in current_user.club_memberships
            if m.role_in_club == ClubRole.coach
        }
        if not coach_club_ids:
            return ActivityListOut(items=[], total=0, page=page, page_size=page_size)
        filters.append(Athlete.club_id.in_(coach_club_ids))

    if athlete_id is not None:
        filters.append(StravaActivity.athlete_id == athlete_id)

    if linked == "true":
        filters.append(StravaActivity.training_session_id.is_not(None))
    elif linked == "false":
        filters.append(StravaActivity.training_session_id.is_(None))

    if date_from is not None:
        filters.append(func.date(StravaActivity.start_date_local) >= date_from)
    if date_to is not None:
        filters.append(func.date(StravaActivity.start_date_local) <= date_to)

    count_result = await db.execute(
        select(func.count())
        .select_from(StravaActivity)
        .join(Athlete, StravaActivity.athlete_id == Athlete.id)
        .where(*filters)
    )
    total = count_result.scalar_one()

    stmt = (
        select(StravaActivity)
        .join(Athlete, StravaActivity.athlete_id == Athlete.id)
        .where(*filters)
        .options(*_ACTIVITY_EAGER_OPTIONS)
    )
    if linked == "all":
        # Unlinked-first: NULL == True ordena antes que False en DESC.
        stmt = stmt.order_by(
            StravaActivity.training_session_id.is_(None).desc(),
            StravaActivity.start_date_utc.desc(),
        )
    else:
        stmt = stmt.order_by(StravaActivity.start_date_utc.desc())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    activities = result.scalars().all()

    return ActivityListOut(
        items=[_serialize_activity_out(a) for a in activities],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# GET /activities/{id}/session-suggestions — candidatas de vínculo (T029, FR-008)
# ---------------------------------------------------------------------------


async def _get_activity_or_404(db: AsyncSession, activity_id: int) -> StravaActivity:
    result = await db.execute(
        select(StravaActivity)
        .where(StravaActivity.id == activity_id)
        .options(*_ACTIVITY_EAGER_OPTIONS)
    )
    activity = result.scalar_one_or_none()
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Actividad no encontrada"
        )
    return activity


@router.get(
    "/activities/{activity_id}/session-suggestions",
    response_model=SessionSuggestionListOut,
)
async def get_session_suggestions(
    activity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionSuggestionListOut:
    """Sesiones candidatas para vincular una actividad (FR-008).

    Roles: admin, coach (club del atleta dueño de la actividad) — vía
    ``can_link_activity``. Candidatas: sesiones del mismo club con
    ``scheduled_date`` dentro de ±1 día de ``start_date_local``. Orden:
    mismo día + asistencia del atleta primero.
    """
    activity = await _get_activity_or_404(db, activity_id)

    if not await can_link_activity(current_user, activity, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permiso para vincular esta actividad",
        )

    activity_date = activity.start_date_local.date()
    lower = activity_date - timedelta(days=1)
    upper = activity_date + timedelta(days=1)

    sessions_result = await db.execute(
        select(TrainingSession)
        .where(
            TrainingSession.club_id == activity.athlete.club_id,
            TrainingSession.scheduled_date >= lower,
            TrainingSession.scheduled_date <= upper,
        )
        .order_by(TrainingSession.scheduled_date)
    )
    sessions = sessions_result.scalars().all()

    attended_session_ids: set[int] = set()
    if sessions:
        session_ids = [s.id for s in sessions]
        attendance_result = await db.execute(
            select(SessionAttendance.session_id).where(
                SessionAttendance.session_id.in_(session_ids),
                SessionAttendance.athlete_id == activity.athlete_id,
            )
        )
        attended_session_ids = set(attendance_result.scalars().all())

    suggestions = [
        SessionSuggestionOut(
            training_session_id=s.id,
            scheduled_date=datetime.combine(s.scheduled_date, s.scheduled_start_time),
            session_kind=s.session_kind.value if s.session_kind else None,
            location=s.location,
            technical_focus=s.technical_focus,
            same_day=s.scheduled_date == activity_date,
            athlete_in_attendance=s.id in attended_session_ids,
        )
        for s in sessions
    ]

    # Mismo día + asistencia primero; luego mismo día; luego asistencia;
    # empates por cercanía a la fecha de la actividad.
    suggestions.sort(
        key=lambda s: (
            not (s.same_day and s.athlete_in_attendance),
            not s.same_day,
            not s.athlete_in_attendance,
            abs((s.scheduled_date.date() - activity_date).days),
        )
    )

    return SessionSuggestionListOut(suggestions=suggestions)


# ---------------------------------------------------------------------------
# PATCH /activities/{id}/link — vincular/desvincular (T029, FR-007)
# ---------------------------------------------------------------------------


@router.patch("/activities/{activity_id}/link", response_model=ActivityOut)
async def link_activity(
    activity_id: int,
    body: LinkUpdateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
) -> ActivityOut:
    """Vincula, re-vincula o desvincula una actividad a una sesión (FR-007).

    Roles: admin, coach (club del atleta) ÚNICAMENTE — vía
    ``can_link_activity`` (parents y el propio athlete-role reciben 403).
    ``training_session_id=None`` desvincula. La sesión debe pertenecer al
    mismo club del atleta o se rechaza con 422 (mensaje en español).

    Feature 026 (structured interval training): si la sesión previamente
    vinculada tenía un ``IntervalStructure`` con un ``IntervalMatchResult``
    persistido para este par estructura↔actividad, el desvínculo borra esa
    fila de comparación (el par ya no existe) pero preserva las
    ``StravaActivityLap`` — son propiedad de la actividad, no del match
    (data-model.md §5/§7). Si el vínculo nuevo apunta a una sesión que sí
    tiene ``IntervalStructure``, se despacha el job diferido de
    emparejamiento (``services/intervals/match_runner.py``,
    ``triggered_by=link``) vía el ``TaskDispatcher`` existente — el fetch de
    laps a Strava y el cómputo nunca corren en el hilo de este endpoint
    (contracts/api.md "Side-contract on existing endpoint"). El shape de la
    respuesta no cambia.
    """
    activity = await _get_activity_or_404(db, activity_id)

    if not await can_link_activity(current_user, activity, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permiso para vincular esta actividad",
        )

    if body.training_session_id is None:
        previous_session_id = activity.training_session_id

        activity.training_session = None
        activity.training_session_id = None
        activity.linked_by = None
        activity.linked_by_user_id = None
        activity.linked_at = None

        if previous_session_id is not None:
            previous_structure_result = await db.execute(
                select(IntervalStructure.id).where(
                    IntervalStructure.training_session_id == previous_session_id
                )
            )
            previous_structure_id = previous_structure_result.scalar_one_or_none()
            if previous_structure_id is not None:
                # Borra solo la fila de comparación de este par
                # estructura↔actividad — las StravaActivityLap NO se tocan
                # (son propiedad de la actividad, D7).
                await db.execute(
                    sa_delete(IntervalMatchResult).where(
                        IntervalMatchResult.structure_id == previous_structure_id,
                        IntervalMatchResult.strava_activity_id == activity.id,
                    )
                )
    else:
        session_result = await db.execute(
            select(TrainingSession).where(
                TrainingSession.id == body.training_session_id
            )
        )
        session_obj = session_result.scalar_one_or_none()
        if session_obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sesión de entrenamiento no encontrada",
            )
        if session_obj.club_id != activity.athlete.club_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="La sesión no pertenece al club del atleta.",
            )
        activity.training_session = session_obj
        activity.training_session_id = session_obj.id
        activity.linked_by = current_user
        activity.linked_by_user_id = current_user.id
        activity.linked_at = datetime.now(timezone.utc)

        target_structure_result = await db.execute(
            select(IntervalStructure.id).where(
                IntervalStructure.training_session_id == session_obj.id
            )
        )
        target_structure_id = target_structure_result.scalar_one_or_none()
        if target_structure_id is not None:
            dispatcher.dispatch(
                run_match_deferred,
                target_structure_id,
                activity.id,
                MatchTrigger.link,
            )

    await db.flush()

    return _serialize_activity_out(activity)


# ---------------------------------------------------------------------------
# GET /training-sessions/{session_id}/activities — vista por sesión (T029, FR-009)
# ---------------------------------------------------------------------------


@router.get(
    "/training-sessions/{session_id}/activities",
    response_model=SessionActivitiesOut,
)
async def list_session_activities(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionActivitiesOut:
    """Actividades de Strava vinculadas a una sesión de entrenamiento (FR-009).

    Roles: reutiliza ``can_view_session`` (admin siempre; coach del club de
    la sesión; parent solo si alguno de sus atletas fue convocado). Para
    parent, las filas se acotan además a sus propios hijos vía
    ``filter_activities_for_parent`` — mismo patrón que
    ``filter_media_for_parent`` para session media — un padre no debe ver
    la actividad de otra familia solo porque comparten sesión (FR-011).
    """
    session_result = await db.execute(
        select(TrainingSession).where(TrainingSession.id == session_id)
    )
    session_obj = session_result.scalar_one_or_none()
    if session_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión de entrenamiento no encontrada",
        )

    if not await can_view_session(db, current_user, session_obj):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permiso para ver las actividades de esta sesión",
        )

    result = await db.execute(
        select(StravaActivity)
        .where(StravaActivity.training_session_id == session_id)
        .options(*_ACTIVITY_EAGER_OPTIONS)
        .order_by(StravaActivity.start_date_utc.desc())
    )
    activities = result.scalars().all()

    if current_user.role == UserRole.parent:
        child_ids = set(await parent_athlete_ids(db, current_user.id))
        activities = filter_activities_for_parent(list(activities), child_ids)

    return SessionActivitiesOut(items=[_serialize_activity_out(a) for a in activities])
