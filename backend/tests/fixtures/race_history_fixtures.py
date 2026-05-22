"""Factories de fixtures para tests del módulo histórico IA (BE-3).

Funciones helper para construir filas de ``athlete_ai_insights``,
``race_events``, ``race_results``, ``calendar_events`` y otros modelos
en una sesión SQLite async in-memory.

Convención de IDs por defecto:
- club_id = 1
- athlete_id principal = 144
- coach user_id = 10
- season default = 2026

Cada factory devuelve la instancia ORM ya flusheada (con .id asignado).
El caller debe hacer ``await session.commit()`` cuando termine de
sembrar el escenario.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import Athlete, ParentAthlete, Sex, FamilyRelationship
from app.models.athlete_ai_insight import AthleteAiInsight, InsightConfidence
from app.models.calendar_event import (
    CalendarEvent,
    EventStatus,
    EventType,
)
from app.models.club import Club, ClubMember, ClubRole
from app.models.race_category import (
    CategoryGender,
    CategoryTier,
    RaceCategory,
)
from app.models.race_competitor import CompetitorSex, RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Users / clubs / athletes
# ---------------------------------------------------------------------------


def _utc() -> datetime:
    return datetime.now(timezone.utc)


async def create_club(
    session: AsyncSession,
    *,
    club_id: int = 1,
    name: str = "Trocha y Ruta",
    code: str = "tyr",
) -> Club:
    club = Club(id=club_id, name=name, code=code, is_active=True)
    session.add(club)
    await session.flush()
    return club


async def create_user(
    session: AsyncSession,
    *,
    user_id: int,
    role: UserRole,
    email: Optional[str] = None,
    first_name: str = "Test",
    last_name: str = "User",
    can_login: bool = True,
) -> User:
    u = User(
        id=user_id,
        email=email or f"{role.value}{user_id}@test.com",
        hashed_password="x",
        first_name=first_name,
        last_name=last_name,
        role=role,
        is_active=True,
        can_login=can_login,
        created_at=_utc(),
    )
    session.add(u)
    await session.flush()
    return u


async def link_user_to_club(
    session: AsyncSession,
    *,
    user_id: int,
    club_id: int = 1,
    role_in_club: ClubRole = ClubRole.coach,
) -> ClubMember:
    """Crea ClubMember para que el RBAC del backend lo reconozca."""
    cm = ClubMember(
        user_id=user_id,
        club_id=club_id,
        role_in_club=role_in_club,
        joined_at=_utc(),
    )
    session.add(cm)
    await session.flush()
    return cm


async def create_athlete(
    session: AsyncSession,
    *,
    athlete_id: int = 144,
    first_name: str = "Juan Diego",
    last_name: str = "Garcia",
    birth_date: date = date(2014, 3, 15),
    sex: Sex = Sex.M,
    club_id: int = 1,
    user_id: int = 10,
    created_by: int = 10,
) -> Athlete:
    a = Athlete(
        id=athlete_id,
        user_id=user_id,
        first_name=first_name,
        last_name=last_name,
        birth_date=birth_date,
        sex=sex,
        club_id=club_id,
        created_by=created_by,
    )
    session.add(a)
    await session.flush()
    return a


async def link_parent_to_athlete(
    session: AsyncSession,
    *,
    parent_user_id: int,
    athlete_id: int,
    relationship_type: FamilyRelationship = FamilyRelationship.padre,
) -> ParentAthlete:
    pa = ParentAthlete(
        parent_id=parent_user_id,
        athlete_id=athlete_id,
        relationship_type=relationship_type,
    )
    session.add(pa)
    await session.flush()
    return pa


# ---------------------------------------------------------------------------
# Race domain
# ---------------------------------------------------------------------------


async def create_race_series(
    session: AsyncSession,
    *,
    series_id: int = 1,
    season_year: int = 2026,
    name: str = "Copa Valle de Ciclomontanismo",
) -> RaceSeries:
    s = RaceSeries(
        id=series_id,
        name=name,
        season_year=season_year,
        organizer="Liga",
        points_scheme_code=f"copa_valle_{season_year}",
    )
    session.add(s)
    await session.flush()
    return s


async def create_race_event(
    session: AsyncSession,
    *,
    event_id: int,
    series_id: int = 1,
    sequence_number: int = 1,
    name: str = "Valida",
    event_date: date = date(2026, 1, 31),
    location: str = "Sevilla",
    created_by_user_id: int = 10,
    status: RaceEventStatus = RaceEventStatus.COMPLETED,
) -> RaceEvent:
    e = RaceEvent(
        id=event_id,
        series_id=series_id,
        sequence_number=sequence_number,
        name=name,
        event_date=event_date,
        location=location,
        is_championship=False,
        status=status,
        created_by_user_id=created_by_user_id,
    )
    session.add(e)
    await session.flush()
    return e


async def create_race_category(
    session: AsyncSession,
    *,
    category_id: int = 100,
    code: str = "INF_B",
    label: str = "Infantil B",
    sex: CategoryGender = CategoryGender.M,
    age_min: int = 11,
    age_max: int = 12,
    tier: CategoryTier = CategoryTier.menores,
    sort_order: int = 31,
) -> RaceCategory:
    c = RaceCategory(
        id=category_id,
        code=code,
        label=label,
        sex=sex,
        age_min=age_min,
        age_max=age_max,
        tier=tier,
        sort_order=sort_order,
        is_active=True,
    )
    session.add(c)
    await session.flush()
    return c


async def create_race_competitor(
    session: AsyncSession,
    *,
    competitor_id: int,
    normalized_name: str = "test runner",
    display_name: str = "Test Runner",
    club_text: str = "Club Trocha y Ruta",
    sex: CompetitorSex = CompetitorSex.M,
    athlete_id: Optional[int] = None,
) -> RaceCompetitor:
    rc = RaceCompetitor(
        id=competitor_id,
        normalized_name=normalized_name,
        display_name=display_name,
        club_text=club_text,
        sex=sex,
        athlete_id=athlete_id,
    )
    session.add(rc)
    await session.flush()
    return rc


async def create_race_result(
    session: AsyncSession,
    *,
    event_id: int,
    category_id: int,
    competitor_id: int,
    athlete_id: Optional[int] = None,
    position: int = 1,
    status: ResultStatus = ResultStatus.FINISHED,
    race_time_ms: Optional[int] = 1_800_000,
    bib_number: Optional[int] = 100,
    points_awarded: int = 40,
    created_by_user_id: int = 10,
    deleted_at: Optional[datetime] = None,
) -> RaceResult:
    r = RaceResult(
        event_id=event_id,
        category_id=category_id,
        competitor_id=competitor_id,
        athlete_id=athlete_id,
        bib_number=bib_number,
        position=position,
        status=status,
        race_time_ms=race_time_ms,
        points_awarded=points_awarded,
        created_by_user_id=created_by_user_id,
        deleted_at=deleted_at,
    )
    session.add(r)
    await session.flush()
    return r


async def create_race_event_with_results(
    session: AsyncSession,
    *,
    event_id: int,
    series_id: int,
    sequence_number: int,
    event_date: date,
    name: str,
    category_id: int = 100,
    athlete_id: int = 144,
    athlete_competitor_id: int = 217,
    athlete_position: int = 3,
    athlete_time_ms: int = 1_802_000,
    other_runners: int = 4,
    winner_time_ms: int = 1_800_000,
    coach_user_id: int = 10,
) -> RaceEvent:
    """Crea un RaceEvent con results: 1 ganador + N runners + el atleta.

    Devuelve el RaceEvent. Los times son lineales (gap de 1_000 ms entre
    runners). Útil para tests de evolution / distribution.
    """
    event = await create_race_event(
        session,
        event_id=event_id,
        series_id=series_id,
        sequence_number=sequence_number,
        name=name,
        event_date=event_date,
        created_by_user_id=coach_user_id,
    )
    # Ganador
    winner_comp_id = competitor_id_base = event_id * 100 + 1
    await create_race_competitor(
        session,
        competitor_id=winner_comp_id,
        normalized_name=f"winner ev{event_id}",
        display_name=f"Winner Ev{event_id}",
    )
    await create_race_result(
        session,
        event_id=event_id,
        category_id=category_id,
        competitor_id=winner_comp_id,
        position=1,
        race_time_ms=winner_time_ms,
        bib_number=1,
        points_awarded=40,
        created_by_user_id=coach_user_id,
    )
    # Otros runners
    for i in range(2, 2 + other_runners):
        cid = competitor_id_base + i
        await create_race_competitor(
            session,
            competitor_id=cid,
            normalized_name=f"runner{i} ev{event_id}",
            display_name=f"Runner {i} Ev{event_id}",
        )
        await create_race_result(
            session,
            event_id=event_id,
            category_id=category_id,
            competitor_id=cid,
            position=i,
            race_time_ms=winner_time_ms + 1_000 * (i - 1),
            bib_number=i,
            points_awarded=40 - 4 * (i - 1),
            created_by_user_id=coach_user_id,
        )
    # El atleta como un competidor más
    await create_race_competitor(
        session,
        competitor_id=athlete_competitor_id + event_id,
        normalized_name=f"athlete ev{event_id}",
        display_name=f"Athlete Ev{event_id}",
        athlete_id=athlete_id,
    )
    await create_race_result(
        session,
        event_id=event_id,
        category_id=category_id,
        competitor_id=athlete_competitor_id + event_id,
        athlete_id=athlete_id,
        position=athlete_position,
        race_time_ms=athlete_time_ms,
        bib_number=athlete_position,
        points_awarded=40 - (athlete_position - 1) * 4,
        created_by_user_id=coach_user_id,
    )
    return event


# ---------------------------------------------------------------------------
# AthleteAiInsight
# ---------------------------------------------------------------------------


async def create_insight(
    session: AsyncSession,
    *,
    athlete_id: int = 144,
    season: int = 2026,
    valida_num: Optional[int] = 1,
    use_case: str = "race_progression",
    coach_approved: bool = True,
    is_active: Optional[int] = 1,
    deprecated_at: Optional[datetime] = None,
    superseded_by_insight_id: Optional[int] = None,
    archived_at: Optional[datetime] = None,
    summary_text: str = "Resumen de muestra para test.",
    confidence: InsightConfidence = InsightConfidence.medium,
    model: str = "gemini-2.5-flash-lite",
    prompt_version: str = "race_analyst_v1",
    generated_at: Optional[datetime] = None,
    generated_by_user_id: int = 10,
    event_id: Optional[int] = None,
    competitor_id: Optional[int] = None,
    agent_run_id: Optional[int] = None,
    metrics_snapshot_json: Optional[dict[str, Any]] = None,
    recommendations_json: Optional[list[dict[str, Any]]] = None,
    principles_cited_json: Optional[list[dict[str, Any]]] = None,
    **overrides: Any,
) -> AthleteAiInsight:
    """Crea + flushea (NO commit) un insight, devolviendo la fila con ``.id``.

    ``is_active`` admite el sentinel 1 (activo publicable) o None.
    """
    now = generated_at or _utc()
    insight = AthleteAiInsight(
        athlete_id=athlete_id,
        season=season,
        valida_num=valida_num,
        use_case=use_case,
        summary_text=summary_text,
        recommendations_json=recommendations_json or [],
        metrics_snapshot_json=metrics_snapshot_json or {"aggregate": {}},
        principles_cited_json=principles_cited_json or [],
        confidence=confidence,
        model=model,
        prompt_version=prompt_version,
        coach_approved=coach_approved,
        coach_edits_count=0,
        generated_at=now,
        approved_at=now if coach_approved else None,
        archived_at=archived_at,
        deprecated_at=deprecated_at,
        is_active=is_active,
        superseded_by_insight_id=superseded_by_insight_id,
        generated_by_user_id=generated_by_user_id,
        event_id=event_id,
        competitor_id=competitor_id,
        agent_run_id=agent_run_id,
        created_at=now,
        updated_at=now,
        **overrides,
    )
    session.add(insight)
    await session.flush()
    return insight


# ---------------------------------------------------------------------------
# Calendar event
# ---------------------------------------------------------------------------


async def create_calendar_event(
    session: AsyncSession,
    *,
    event_id: Optional[int] = None,
    club_id: int = 1,
    event_type: EventType = EventType.COMPETITION,
    title: str = "Test event",
    start_at: Optional[datetime] = None,
    end_at: Optional[datetime] = None,
    location: Optional[str] = "Test location",
    description: Optional[str] = None,
    race_event_id: Optional[int] = None,
    event_data: Optional[dict[str, Any]] = None,
    created_by_user_id: int = 10,
    status: EventStatus = EventStatus.SCHEDULED,
) -> CalendarEvent:
    """Crea un CalendarEvent.

    NOTA: la PK es BigInteger en el modelo. SQLite no soporta autoincrement
    en BigInteger — los tests deben pasar ``event_id`` explícito.
    """
    start = start_at or datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    end = end_at or datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    ev = CalendarEvent(
        id=event_id,
        club_id=club_id,
        event_type=event_type,
        title=title,
        start_at=start,
        end_at=end,
        all_day=False,
        timezone="America/Bogota",
        location=location,
        description=description,
        race_event_id=race_event_id,
        event_data=event_data or {},
        color_hex=None,
        created_by_user_id=created_by_user_id,
        status=status,
    )
    session.add(ev)
    await session.flush()
    return ev


__all__ = [
    "create_athlete",
    "create_calendar_event",
    "create_club",
    "create_insight",
    "create_race_category",
    "create_race_competitor",
    "create_race_event",
    "create_race_event_with_results",
    "create_race_result",
    "create_race_series",
    "create_user",
    "link_parent_to_athlete",
    "link_user_to_club",
]
