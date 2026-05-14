from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import ParentAthlete
from app.models.club import ClubMember, ClubRole
from app.models.training_session import SessionAttendance, TrainingSession
from app.models.user import User, UserRole


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
    """Retorna los IDs de atletas vinculados a un usuario padre."""
    result = await db.execute(
        select(ParentAthlete.athlete_id).where(ParentAthlete.parent_id == user_id)
    )
    return list(result.scalars().all())


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
            result = await db.execute(
                select(Athlete.id).where(
                    Athlete.id.in_(athlete_ids),
                    Athlete.club_id == event.club_id,  # type: ignore[attr-defined]
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
