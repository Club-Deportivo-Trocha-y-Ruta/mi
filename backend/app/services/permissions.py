from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import Athlete, ParentAthlete
from app.models.club import ClubMember, ClubRole
from app.models.session_media import SessionMedia
from app.models.training_session import SessionAttendance, TrainingSession
from app.models.user import User, UserRole

if TYPE_CHECKING:
    # Modulo creado en la tarea T006 (feature 025); import solo para tipado
    # estatico — evita el import en tiempo de ejecucion mientras el modulo
    # aun no existe (`from __future__ import annotations` difiere la
    # evaluacion de anotaciones).
    from app.models.race_import import RaceImport
    from app.models.strava_activity import StravaActivity


async def allowed_athlete_ids_for(
    user: User,
    db: AsyncSession,
) -> set[int] | None:
    """Return the set of athlete IDs the *user* is permitted to see in race results.

    Semantics:
    - ``None``  → no restriction (coach / admin may see every competitor row).
    - ``set``   → parent scope; only rows whose ``athlete_id`` is in this set
                  should be returned.  An empty set means the parent has no linked
                  children and therefore sees zero rows.

    This helper is the single authoritative gate for the parent-scoping rule
    (FR-030 / Ley 1581) in the results and standings read paths.
    """
    if user.role in {UserRole.admin, UserRole.coach}:
        return None

    if user.role == UserRole.parent:
        ids = await parent_athlete_ids(db, user.id)
        return set(ids)

    # Any other role gets an empty set (no access to any athlete row).
    return set()


def require_role(user_role: UserRole, allowed_roles: list[UserRole]) -> None:
    """Verifica que el rol del usuario este en la lista de roles permitidos."""
    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para esta accion",
        )


# ---------------------------------------------------------------------------
# Helpers de consulta
# ---------------------------------------------------------------------------


async def parent_athlete_ids(db: AsyncSession, user_id: int) -> list[int]:
    """Retorna los IDs de atletas vinculados a un usuario padre.

    Un atleta archivado desaparece de toda superficie de padre (FR-014):
    se excluye aquí para que los ~20 sitios que consumen este helper hereden
    el filtro sin duplicar la condición.
    """
    result = await db.execute(
        select(ParentAthlete.athlete_id)
        .join(Athlete, Athlete.id == ParentAthlete.athlete_id)
        .where(
            ParentAthlete.parent_id == user_id,
            Athlete.deleted_at.is_(None),
        )
    )
    return list(result.scalars().all())


def coach_club_ids(user: User) -> set[int]:
    """Retorna los IDs de clubes donde el usuario tiene rol de coach."""
    return {m.club_id for m in user.club_memberships if m.role_in_club == ClubRole.coach}


async def user_club_role(
    db: AsyncSession, user_id: int, club_id: int
) -> ClubRole | None:
    """Retorna el rol del usuario en un club, o None si no es miembro."""
    result = await db.execute(
        select(ClubMember.role_in_club).where(
            ClubMember.user_id == user_id,
            ClubMember.club_id == club_id,
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Alcance por club para runs agénticos e importaciones de resultados
# (contracts/scope-ai-imports.md §1). Regla única que reemplaza el
# creator-lock: *cualquier cosa del club la puede operar cualquier coach del
# club; el admin siempre; el coach de otro club nunca.*
# ---------------------------------------------------------------------------


async def _coach_membership_club_ids(db: AsyncSession, user_id: int) -> set[int]:
    """Clubes donde ``user_id`` figura como coach en ``club_members``.

    Se consulta contra la tabla (no contra ``user.club_memberships``) porque
    el usuario en cuestión es el *autor* de la fila, no quien hace la
    petición: su relación no está cargada en esta sesión.
    """
    if user_id is None:
        return set()
    result = await db.execute(
        select(ClubMember.club_id).where(
            ClubMember.user_id == user_id,
            ClubMember.role_in_club == ClubRole.coach,
        )
    )
    return {int(cid) for cid in result.scalars().all() if cid is not None}


def _athlete_id_from_input_json(raw: Any) -> int | None:
    """``input_json['athlete_id']`` — respaldo permanente de §1.1 paso 2.

    Las filas históricas de ``agent_runs`` quedaron con ``athlete_id`` en
    NULL (§1.3): el backfill B7 sólo alcanza a las que traen el id dentro
    del JSON, así que la lectura del JSON se mantiene para siempre.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    if not isinstance(raw, dict):
        return None
    value = raw.get("athlete_id")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def run_club_ids(db: AsyncSession, run: dict[str, Any]) -> set[int]:
    """Clubes a los que pertenece un run agéntico (§1.1).

    Escalera: ``agent_runs.athlete_id`` → ``input_json['athlete_id']`` →
    ``athletes.club_id`` → clubes donde el solicitante es coach → ``set()``.

    ``deleted_at`` NO se filtra: un run sobre un deportista archivado sigue
    siendo abrible (data-model §8.1).
    """
    athlete_id = run.get("athlete_id")
    if athlete_id is None:
        athlete_id = _athlete_id_from_input_json(run.get("input_json"))

    if athlete_id is not None:
        result = await db.execute(
            select(Athlete.club_id).where(Athlete.id == int(athlete_id))
        )
        club_id = result.scalar_one_or_none()
        if club_id is not None:
            return {int(club_id)}

    # Paso 4 — sólo cuando los pasos 1-3 no resolvieron nada.
    return await _coach_membership_club_ids(db, run.get("requested_by_user_id"))


async def import_club_ids(db: AsyncSession, imp: "RaceImport") -> set[int]:
    """Clubes a los que pertenece un cargue de resultados (§1.2).

    ``race_imports`` / ``race_series`` / ``race_events`` no tienen
    ``club_id``: las carreras son competencias de terceros, no filas del
    club. El único vínculo veraz es la membresía de quien cargó el archivo.
    """
    return await _coach_membership_club_ids(db, getattr(imp, "imported_by_user_id", None))


def _has_club_access(
    club_ids: set[int], user: User, *, legacy_owner_id: int | None
) -> bool:
    """Matriz de decisión de §1.4 (el admin ya salió antes de llamar aquí).

    El respaldo por autoría sólo aplica cuando el club es irresoluble: nunca
    ensancha el acceso, sólo evita que una fila sin club quede inalcanzable
    para quien la creó.
    """
    if club_ids:
        return bool(coach_club_ids(user) & club_ids)
    return legacy_owner_id is not None and legacy_owner_id == user.id


async def ensure_run_club_access(
    db: AsyncSession, run: dict[str, Any], user: User
) -> None:
    """Lanza 403 si ``user`` no es coach de ningún club del run (§1.4, §2)."""
    if user.role == UserRole.admin:
        return
    club_ids = await run_club_ids(db, run)
    if _has_club_access(
        club_ids, user, legacy_owner_id=run.get("requested_by_user_id")
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes acceso a este run",
    )


async def ensure_import_club_access(
    db: AsyncSession, imp: "RaceImport", user: User
) -> None:
    """Lanza 403 si ``user`` no es coach de ningún club del cargue (§6.1)."""
    if user.role == UserRole.admin:
        return
    club_ids = await import_club_ids(db, imp)
    if _has_club_access(
        club_ids, user, legacy_owner_id=getattr(imp, "imported_by_user_id", None)
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes acceso a este cargue de resultados: pertenece a otro club.",
    )


# ---------------------------------------------------------------------------
# Permisos de sesiones de entrenamiento
# ---------------------------------------------------------------------------


async def can_view_session(
    db: AsyncSession,
    user: User,
    session: TrainingSession,
) -> bool:
    """
    Admin: siempre.
    Coach: si pertenece al mismo club.
    Parent: si alguno de sus atletas fue convocado a la sesión.
    """
    if user.role == UserRole.admin:
        return True

    if user.role == UserRole.coach:
        role = await user_club_role(db, user.id, session.club_id)
        return role is not None

    if user.role == UserRole.parent:
        athlete_ids = await parent_athlete_ids(db, user.id)
        if not athlete_ids:
            return False
        result = await db.execute(
            select(SessionAttendance.id).where(
                SessionAttendance.session_id == session.id,
                SessionAttendance.athlete_id.in_(athlete_ids),
            )
        )
        return result.first() is not None

    return False


async def can_edit_session(
    db: AsyncSession,
    user: User,
    session: TrainingSession,
) -> bool:
    """
    Admin: siempre.
    Coach: solo si pertenece al club de la sesión.
    Otros: False.
    """
    if user.role == UserRole.admin:
        return True
    if user.role == UserRole.coach:
        role = await user_club_role(db, user.id, session.club_id)
        return role is not None
    return False


async def can_view_session_media(
    db: AsyncSession,
    user: User,
    session: TrainingSession,
    media: SessionMedia,
) -> bool:
    """
    Admin: siempre.
    Coach: si pertenece al club de la sesión.
    Parent: sólo si la media etiqueta a alguno de sus hijos.
    """
    if user.role == UserRole.admin:
        return True
    if user.role == UserRole.coach:
        role = await user_club_role(db, user.id, session.club_id)
        return role is not None
    if user.role == UserRole.parent:
        athlete_ids = set(await parent_athlete_ids(db, user.id))
        if not athlete_ids:
            return False
        tagged = {a.id for a in (media.athletes or [])}
        return bool(athlete_ids & tagged)
    return False


def filter_media_for_parent(
    media_list: list[SessionMedia],
    children_ids: set[int],
) -> list[SessionMedia]:
    """Filtra la lista de media para una vista parent: sólo aquellas donde
    al menos un hijo aparece etiquetado y la media no fue soft-deleted."""
    result: list[SessionMedia] = []
    for m in media_list:
        if m.deleted_at is not None:
            continue
        tagged = {a.id for a in (m.athletes or [])}
        if children_ids & tagged:
            result.append(m)
    return result


async def can_view_athlete_feedback(
    db: AsyncSession,
    user: User,
    athlete_id: int,
) -> bool:
    """
    Admin: siempre.
    Coach: siempre (se asume mismo club — el router lo valida).
    Parent: solo si el atleta le pertenece.
    """
    if user.role in {UserRole.admin, UserRole.coach}:
        return True

    if user.role == UserRole.parent:
        ids = await parent_athlete_ids(db, user.id)
        return athlete_id in ids

    return False


async def can_view_monthly_report(
    db: AsyncSession,
    user: User,
    club_id: int,
    individual: bool = False,
) -> bool:
    """
    Admin/coach del club: acceso total.
    Parent: solo vista agregada (individual=False).
    """
    if user.role == UserRole.admin:
        return True

    if user.role == UserRole.coach:
        role = await user_club_role(db, user.id, club_id)
        return role is not None

    if user.role == UserRole.parent:
        return not individual

    return False


# ---------------------------------------------------------------------------
# Permisos del calendario de eventos
# ---------------------------------------------------------------------------


async def can_view_calendar_event(
    db: AsyncSession,
    user: User,
    event: object,
) -> bool:
    """
    Admin: siempre.
    Coach: si pertenece al club del evento.
    Parent: si alguno de sus atletas está en la audiencia del evento.
    """
    if user.role == UserRole.admin:
        return True

    if user.role == UserRole.coach:
        role = await user_club_role(db, user.id, event.club_id)  # type: ignore[attr-defined]
        return role is not None

    if user.role == UserRole.parent:
        from app.models.calendar_event import EventType  # late import evita circular
        from app.services.calendar.audiences import any_athlete_in_audience  # late import

        athlete_ids = await parent_athlete_ids(db, user.id)
        if not athlete_ids:
            return False
        # Cumpleaños: visibles a todos los miembros del club (decisión de producto).
        # El padre los ve si tiene al menos un atleta en el club del evento.
        if event.event_type == EventType.BIRTHDAY:  # type: ignore[attr-defined]
            from app.models.athlete import Athlete  # late import
            # FR-014: un atleta archivado no da visibilidad de eventos al padre.
            # ``parent_athlete_ids`` ya excluye archivados, pero el filtro se
            # repite aquí porque esta consulta es la que decide la visibilidad.
            result = await db.execute(
                select(Athlete.id).where(
                    Athlete.id.in_(athlete_ids),
                    Athlete.club_id == event.club_id,  # type: ignore[attr-defined]
                    Athlete.deleted_at.is_(None),
                )
            )
            return result.first() is not None
        return await any_athlete_in_audience(db, event, athlete_ids)  # type: ignore[arg-type]

    return False


async def can_edit_calendar_event(
    db: AsyncSession,
    user: User,
    event: object,
) -> bool:
    """
    Admin: siempre.
    Coach del club: siempre.
    Otros: False.
    """
    if user.role == UserRole.admin:
        return True

    if user.role == UserRole.coach:
        role = await user_club_role(db, user.id, event.club_id)  # type: ignore[attr-defined]
        return role is not None

    return False


async def can_rsvp_event(
    db: AsyncSession,
    user: User,
    event: object,
    athlete_id: int,
) -> bool:
    """
    Parent: el atleta debe ser hijo suyo + estar en audiencia + evento no es training_session.
    Coach del club: siempre.
    Admin: siempre.
    """
    from app.models.calendar_event import EventType  # late import evita circular

    if user.role == UserRole.admin:
        return True

    if user.role == UserRole.coach:
        role = await user_club_role(db, user.id, event.club_id)  # type: ignore[attr-defined]
        return role is not None

    if user.role == UserRole.parent:
        # No permitir RSVP en training_sessions
        if event.event_type == EventType.TRAINING_SESSION:  # type: ignore[attr-defined]
            return False

        my_ids = await parent_athlete_ids(db, user.id)
        if athlete_id not in my_ids:
            return False

        from app.services.calendar.audiences import event_visible_to_athlete  # late import
        return await event_visible_to_athlete(db, event, athlete_id)  # type: ignore[arg-type]

    return False


# ---------------------------------------------------------------------------
# Permisos de actividades de Strava (feature 025)
# ---------------------------------------------------------------------------


async def can_view_activity(
    user: User,
    athlete_id: int,
    db: AsyncSession,
) -> bool:
    """Autoriza la lectura de actividades de Strava de un atleta.

    Admin: siempre.
    Coach: si pertenece al mismo club que el atleta.
    Parent: solo si el atleta es uno de sus hijos vinculados (acceso de solo
        lectura — nunca puede vincular/desvincular, ver ``can_link_activity``).
    Otros roles (athlete, etc.): False.
    """
    if user.role == UserRole.admin:
        return True

    if user.role == UserRole.coach:
        # FR-014: para el coach, un atleta archivado no resuelve club y la
        # autorización cae a False (el admin sí conserva el acceso, arriba).
        result = await db.execute(
            select(Athlete.club_id).where(
                Athlete.id == athlete_id,
                Athlete.deleted_at.is_(None),
            )
        )
        club_id = result.scalar_one_or_none()
        if club_id is None:
            return False
        role = await user_club_role(db, user.id, club_id)
        return role is not None

    if user.role == UserRole.parent:
        ids = await parent_athlete_ids(db, user.id)
        return athlete_id in ids

    return False


async def can_link_activity(
    user: User,
    activity: "StravaActivity",
    db: AsyncSession,
) -> bool:
    """Autoriza vincular, re-vincular o desvincular una actividad de Strava
    a una sesion de entrenamiento (FR-007).

    Admin: siempre.
    Coach: solo si pertenece al club del atleta duenio de la actividad.
    Parent: nunca — la vinculacion es una accion exclusiva del cuerpo
        tecnico; las familias solo tienen visibilidad de solo lectura
        (ver ``can_view_activity``).
    Otros roles: False.
    """
    if user.role == UserRole.admin:
        return True

    if user.role == UserRole.coach:
        # FR-014: no se puede vincular ni desvincular actividad de un atleta
        # archivado — la consulta no lo resuelve y la autorización cae a False.
        result = await db.execute(
            select(Athlete.club_id).where(
                Athlete.id == activity.athlete_id,
                Athlete.deleted_at.is_(None),
            )
        )
        club_id = result.scalar_one_or_none()
        if club_id is None:
            return False
        role = await user_club_role(db, user.id, club_id)
        return role is not None

    # Parent (y cualquier otro rol) nunca puede vincular actividades.
    return False


def filter_activities_for_parent(
    activities: list["StravaActivity"],
    children_ids: set[int],
) -> list["StravaActivity"]:
    """Filtra una lista de actividades de Strava para una vista parent.

    Mismo patron que ``filter_media_for_parent`` (session media): un padre
    solo debe ver las filas cuyo ``athlete_id`` sea uno de sus propios hijos,
    incluso cuando la lista de entrada proviene de un query no acotado por
    atleta (p.ej. ``GET /training-sessions/{id}/activities``, donde la
    sesion puede convocar a atletas de otras familias — FR-011).
    """
    return [a for a in activities if a.athlete_id in children_ids]


async def athlete_activity_scope(
    user: User,
    db: AsyncSession,
) -> set[int] | None:
    """Retorna el alcance de athlete_id cuyas actividades de Strava el
    usuario puede consultar.

    Reutiliza la misma semantica que ``allowed_athlete_ids_for``:
    - ``None`` → sin restriccion por atleta (admin / coach); el router aun
      debe filtrar por club cuando corresponda (p.ej. ``GET /api/activities``
      solo debe listar atletas del club del coach).
    - ``set``  → alcance de padre; solo actividades cuyo ``athlete_id`` esta
      en este set. Un set vacio significa que el padre no tiene hijos
      vinculados y por tanto no ve ninguna actividad.

    Pensado para acotar las queries de listado
    (``GET /api/activities``, ``GET /api/athletes/{id}/activities``) antes
    de aplicar filtros adicionales de club/sesion.
    """
    return await allowed_athlete_ids_for(user, db)


# ---------------------------------------------------------------------------
# Permisos del historial de auditoría (feature 041)
# ---------------------------------------------------------------------------


def can_view_audit(user: User, club_id: int) -> bool:
    """FR-006/FR-007: solo admin y coaches del propio club leen el historial.

    Síncrona a propósito: ``get_current_user`` ya trae ``club_memberships``
    con ``selectinload`` (``app/dependencies.py``), así que resolver la
    membresía en memoria evita el SELECT extra que sí paga
    ``user_club_role`` y deja el endpoint del club en 2 queries
    (contracts/audit-log-api.md §4.2).

    No confundir con ``can_view_monthly_report``: esa función retorna
    ``True`` para cualquier padre en la vista agregada, comportamiento que
    FR-006 prohíbe explícitamente para el historial de auditoría.
    """
    if user.role == UserRole.admin:
        return True
    if user.role == UserRole.coach:
        return club_id in coach_club_ids(user)
    return False


# NOTA (contracts/audit-log-api.md §4.3): no existe un
# ``can_view_athlete_audit`` separado en este módulo. El endpoint
# ``GET /api/athletes/{athlete_id}/audit-log`` combina, en este orden,
# ``require_role([UserRole.admin, UserRole.coach])`` (rechaza parent/athlete
# antes de tocar la base de datos) y ``verify_athlete_access``
# (``app/dependencies.py``), que ya resuelve el 404 de atleta desconocido y
# el 403 de coach de otro club. Duplicar esa lógica aquí reintroduciría el
# error de copy-paste que el contrato señala explícitamente para
# ``can_view_monthly_report``.
