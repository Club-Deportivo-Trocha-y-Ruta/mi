"""T040 (specs/047-imderty-attendance-sheet/tasks.md, US3):
``backend/tests/imderty/test_readiness.py``.

Two layers:

- **Service** (``build_readiness``, T042): one case per gap code of
  ``data-model.md``'s "Readiness gap" block, the ``month_in_progress`` /
  ``months_without_activity`` flags, and the 480-athlete size limit
  (``ReadinessTooLarge``). Uses a self-contained aiosqlite engine with the
  full schema (same idiom as ``test_attendance_grid.py``) because these
  scenarios need calendar/training tables the shared ``imderty_scenario``
  fixture does not create.
- **Route** (``GET /api/clubs/{club_id}/imderty-sheet/readiness``): 403 for
  parent/foreign-coach/athlete-account, and the ``POST`` header-override
  contract of T043 (an override without ``save_header_as_default`` never
  touches the stored settings; ``save_header_as_default=true`` persists it).

Every name here is fictitious (CLAUDE.md, Ley 1581); nothing asserted here
depends on a real minor's data.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.athlete import Athlete, Sex
from app.models.calendar_event import (
    AudienceType,
    CalendarEvent,
    EventAudience,
    EventStatus,
    EventType,
)
from app.models.imderty import AthleteImdertyProfile, ImdertyBarrio, ImdertyDocumentType
from app.models.training_session import (
    AttendanceStatus,
    SessionAttendance,
    SessionStatus,
    TrainingSession,
)
from app.models.user import User, UserRole
from app.services.imderty.readiness import ReadinessTooLarge, build_readiness
from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_user,
    link_parent_to_athlete,
)
from tests.imderty.conftest import ImdertyScenario

# ---------------------------------------------------------------------------
# Service-level fixtures (self-contained engine, full schema)
# ---------------------------------------------------------------------------

CLUB_ID = 4901
COACH_ID = 4910
FIRST_GUARDIAN_ID = 4911
SECOND_GUARDIAN_ID = 4912

AUG = date(2026, 8, 1)
SEP = date(2026, 9, 1)
TODAY = date(2026, 9, 28)  # well into September, no August day is "future"

_next_id = 4950
_next_user_id = 14950


def _athlete_id() -> int:
    global _next_id
    _next_id += 1
    return _next_id


def _user_id() -> int:
    global _next_user_id
    _next_user_id += 1
    return _next_user_id


@pytest_asyncio.fixture
async def readiness_engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(readiness_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(readiness_engine, expire_on_commit=False)
    async with factory() as session:
        await create_club(session, club_id=CLUB_ID, name="Club Ficticio 049", code="cf-049")
        await create_user(session, user_id=COACH_ID, role=UserRole.coach)
        await create_user(
            session, user_id=FIRST_GUARDIAN_ID, role=UserRole.parent,
            first_name="Acudiente", last_name="Uno",
        )
        await create_user(
            session, user_id=SECOND_GUARDIAN_ID, role=UserRole.parent,
            first_name="Acudiente", last_name="Dos",
        )
        await session.commit()
        yield session


async def _new_athlete(
    db: AsyncSession,
    *,
    first_name: str = "Deportista Ficticio",
    last_name_suffix: str | None = None,
) -> Athlete:
    athlete_id = _athlete_id()
    last_name_suffix = last_name_suffix or str(athlete_id)
    return await create_athlete(
        db,
        athlete_id=athlete_id,
        first_name=first_name,
        last_name=f"Prueba {last_name_suffix}",
        birth_date=date(2014, 5, 2),
        sex=Sex.M,
        club_id=CLUB_ID,
        user_id=_user_id(),
        created_by=COACH_ID,
    )


async def _barrio(db: AsyncSession, *, name: str = "Barrio Ficticio Uno") -> ImdertyBarrio:
    barrio = ImdertyBarrio(name=name, zone="1", is_active=True)
    db.add(barrio)
    await db.flush()
    return barrio


async def _complete_profile(
    db: AsyncSession,
    athlete: Athlete,
    barrio: ImdertyBarrio,
    *,
    phone: str | None = "3000000001",
    confirmed: bool = True,
) -> AthleteImdertyProfile:
    """A profile with every gap-checked field filled, split confirmed."""
    first, second = athlete.last_name.rsplit(" ", 1) if " " in athlete.last_name else (
        athlete.last_name,
        None,
    )
    profile = AthleteImdertyProfile(
        athlete_id=athlete.id,
        first_surname=first,
        second_surname=second,
        surname_split_confirmed_at=datetime(2026, 8, 1, 12, 0) if confirmed else None,
        document_type=ImdertyDocumentType.ti,
        document_number="1000000001",
        barrio_id=barrio.id,
        other_municipality=False,
        eps="EPS Ficticia",
        phone=phone,
    )
    db.add(profile)
    await db.flush()
    return profile


async def _event(
    db: AsyncSession,
    start_at: datetime,
    *,
    athlete_ids: list[int],
    club_id: int = CLUB_ID,
) -> CalendarEvent:
    """A club-outing event whose audience is ``athlete_ids``, with no
    ``EventAttendance`` rows at all — the source of ``activity_without_record``."""
    event = CalendarEvent(
        club_id=club_id,
        event_type=EventType.CLUB_EVENT,
        status=EventStatus.COMPLETED,
        title="Salida ficticia",
        start_at=start_at,
        end_at=start_at.replace(hour=min(start_at.hour + 1, 23)),
        all_day=False,
        timezone="America/Bogota",
        created_by_user_id=COACH_ID,
    )
    db.add(event)
    await db.flush()
    db.add(
        EventAudience(
            event_id=event.id,
            audience_type=AudienceType.ATHLETE_LIST,
            audience_value={"athlete_ids": athlete_ids},
        )
    )
    await db.flush()
    return event


async def _session_mark(
    db: AsyncSession, day: date, marks: dict[int, AttendanceStatus]
) -> TrainingSession:
    session = TrainingSession(
        club_id=CLUB_ID,
        created_by_user_id=COACH_ID,
        status=SessionStatus.EXECUTED,
        scheduled_date=day,
        scheduled_start_time=time(15, 0),
        duration_min=90,
        location="Parque ficticio",
        technical_focus="Técnica",
    )
    db.add(session)
    await db.flush()
    for athlete_id, mark in marks.items():
        db.add(SessionAttendance(session_id=session.id, athlete_id=athlete_id, status=mark))
    await db.flush()
    return session


async def _readiness(db: AsyncSession, months: list[date], **kwargs):
    await db.commit()
    return await build_readiness(db, CLUB_ID, months, today=TODAY, **kwargs)


def _codes_for(report, athlete_id: int) -> list[str] | None:
    for gap in report.gaps:
        if gap.athlete_id == athlete_id:
            return gap.codes
    return None


# ---------------------------------------------------------------------------
# Gap codes — one athlete per case, isolated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_profile_has_no_gaps(db: AsyncSession) -> None:
    athlete = await _new_athlete(db)
    barrio = await _barrio(db)
    await _complete_profile(db, athlete, barrio)
    await link_parent_to_athlete(db, parent_user_id=FIRST_GUARDIAN_ID, athlete_id=athlete.id)

    report = await _readiness(db, [AUG])

    assert _codes_for(report, athlete.id) is None
    assert athlete.id not in [g.athlete_id for g in report.gaps]


@pytest.mark.asyncio
async def test_missing_document_gap(db: AsyncSession) -> None:
    athlete = await _new_athlete(db)
    barrio = await _barrio(db)
    profile = await _complete_profile(db, athlete, barrio)
    profile.document_type = None
    profile.document_number = None
    await link_parent_to_athlete(db, parent_user_id=FIRST_GUARDIAN_ID, athlete_id=athlete.id)

    report = await _readiness(db, [AUG])

    assert "missing_document" in _codes_for(report, athlete.id)


@pytest.mark.asyncio
async def test_missing_barrio_gap(db: AsyncSession) -> None:
    athlete = await _new_athlete(db)
    barrio = await _barrio(db)
    profile = await _complete_profile(db, athlete, barrio)
    profile.barrio_id = None
    profile.other_municipality = False
    await link_parent_to_athlete(db, parent_user_id=FIRST_GUARDIAN_ID, athlete_id=athlete.id)

    report = await _readiness(db, [AUG])

    assert "missing_barrio" in _codes_for(report, athlete.id)


@pytest.mark.asyncio
async def test_other_municipality_clears_missing_barrio_gap(db: AsyncSession) -> None:
    athlete = await _new_athlete(db)
    barrio = await _barrio(db)
    profile = await _complete_profile(db, athlete, barrio)
    profile.barrio_id = None
    profile.other_municipality = True
    await link_parent_to_athlete(db, parent_user_id=FIRST_GUARDIAN_ID, athlete_id=athlete.id)

    report = await _readiness(db, [AUG])

    codes = _codes_for(report, athlete.id) or []
    assert "missing_barrio" not in codes


@pytest.mark.asyncio
async def test_missing_eps_gap(db: AsyncSession) -> None:
    athlete = await _new_athlete(db)
    barrio = await _barrio(db)
    profile = await _complete_profile(db, athlete, barrio)
    profile.eps = None
    await link_parent_to_athlete(db, parent_user_id=FIRST_GUARDIAN_ID, athlete_id=athlete.id)

    report = await _readiness(db, [AUG])

    assert "missing_eps" in _codes_for(report, athlete.id)


@pytest.mark.asyncio
async def test_missing_phone_gap_when_no_source_resolves(db: AsyncSession) -> None:
    athlete = await _new_athlete(db)
    barrio = await _barrio(db)
    await _complete_profile(db, athlete, barrio, phone=None)
    # Guardian without a phone either (default create_user leaves phone NULL).
    await link_parent_to_athlete(db, parent_user_id=FIRST_GUARDIAN_ID, athlete_id=athlete.id)

    report = await _readiness(db, [AUG])

    assert "missing_phone" in _codes_for(report, athlete.id)


@pytest.mark.asyncio
async def test_guardian_phone_resolves_missing_phone_gap(db: AsyncSession) -> None:
    athlete = await _new_athlete(db)
    barrio = await _barrio(db)
    await _complete_profile(db, athlete, barrio, phone=None)
    guardian = await db.get(User, FIRST_GUARDIAN_ID)
    guardian.phone = "3000000099"
    await link_parent_to_athlete(db, parent_user_id=FIRST_GUARDIAN_ID, athlete_id=athlete.id)

    report = await _readiness(db, [AUG])

    codes = _codes_for(report, athlete.id) or []
    assert "missing_phone" not in codes


@pytest.mark.asyncio
async def test_no_guardian_gap(db: AsyncSession) -> None:
    athlete = await _new_athlete(db)
    barrio = await _barrio(db)
    await _complete_profile(db, athlete, barrio)
    # No link_parent_to_athlete call at all.

    report = await _readiness(db, [AUG])

    assert "no_guardian" in _codes_for(report, athlete.id)
    assert "multiple_guardians_no_primary" not in _codes_for(report, athlete.id)


@pytest.mark.asyncio
async def test_multiple_guardians_no_primary_gap(db: AsyncSession) -> None:
    athlete = await _new_athlete(db)
    barrio = await _barrio(db)
    await _complete_profile(db, athlete, barrio)
    await link_parent_to_athlete(db, parent_user_id=FIRST_GUARDIAN_ID, athlete_id=athlete.id)
    await link_parent_to_athlete(db, parent_user_id=SECOND_GUARDIAN_ID, athlete_id=athlete.id)

    report = await _readiness(db, [AUG])

    assert "multiple_guardians_no_primary" in _codes_for(report, athlete.id)


@pytest.mark.asyncio
async def test_multiple_guardians_with_primary_has_no_gap(db: AsyncSession) -> None:
    athlete = await _new_athlete(db)
    barrio = await _barrio(db)
    await _complete_profile(db, athlete, barrio)
    from app.models.athlete import ParentAthlete

    await link_parent_to_athlete(db, parent_user_id=FIRST_GUARDIAN_ID, athlete_id=athlete.id)
    await link_parent_to_athlete(db, parent_user_id=SECOND_GUARDIAN_ID, athlete_id=athlete.id)
    result = await db.execute(
        ParentAthlete.__table__.select().where(
            ParentAthlete.athlete_id == athlete.id,
            ParentAthlete.parent_id == FIRST_GUARDIAN_ID,
        )
    )
    link = result.first()
    await db.execute(
        ParentAthlete.__table__.update()
        .where(ParentAthlete.id == link.id)
        .values(primary_contact_key=athlete.id)
    )
    await db.flush()

    report = await _readiness(db, [AUG])

    codes = _codes_for(report, athlete.id) or []
    assert "multiple_guardians_no_primary" not in codes


@pytest.mark.asyncio
async def test_surname_split_unconfirmed_gap(db: AsyncSession) -> None:
    athlete = await _new_athlete(db)
    barrio = await _barrio(db)
    await _complete_profile(db, athlete, barrio, confirmed=False)
    await link_parent_to_athlete(db, parent_user_id=FIRST_GUARDIAN_ID, athlete_id=athlete.id)

    report = await _readiness(db, [AUG])

    assert "surname_split_unconfirmed" in _codes_for(report, athlete.id)


@pytest.mark.asyncio
async def test_activity_without_record_gap_carries_dates(db: AsyncSession) -> None:
    athlete = await _new_athlete(db)
    barrio = await _barrio(db)
    await _complete_profile(db, athlete, barrio)
    await link_parent_to_athlete(db, parent_user_id=FIRST_GUARDIAN_ID, athlete_id=athlete.id)
    await _event(db, datetime(2026, 8, 15, 8, 0), athlete_ids=[athlete.id])

    report = await _readiness(db, [AUG])

    codes = _codes_for(report, athlete.id)
    assert "activity_without_record" in codes
    gap = next(g for g in report.gaps if g.athlete_id == athlete.id)
    assert gap.activity_dates == [date(2026, 8, 15)]


@pytest.mark.asyncio
async def test_no_profile_at_all_reports_every_static_gap(db: AsyncSession) -> None:
    """An athlete with no ``athlete_imderty_profiles`` row at all (never
    saved) reports every gap the schema-level fields cover — never a 404 or
    a crash on a NULL profile."""
    athlete = await _new_athlete(db)
    await link_parent_to_athlete(db, parent_user_id=FIRST_GUARDIAN_ID, athlete_id=athlete.id)

    report = await _readiness(db, [AUG])

    codes = _codes_for(report, athlete.id)
    assert set(codes) == {
        "missing_document",
        "missing_barrio",
        "missing_eps",
        "missing_phone",
        "surname_split_unconfirmed",
    }


# ---------------------------------------------------------------------------
# Month flags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_month_in_progress_true_for_current_month(db: AsyncSession) -> None:
    athlete = await _new_athlete(db)
    barrio = await _barrio(db)
    await _complete_profile(db, athlete, barrio)
    await link_parent_to_athlete(db, parent_user_id=FIRST_GUARDIAN_ID, athlete_id=athlete.id)

    report = await _readiness(db, [SEP])  # TODAY = 2026-09-28

    assert report.month_in_progress is True


@pytest.mark.asyncio
async def test_month_in_progress_false_for_a_past_month(db: AsyncSession) -> None:
    athlete = await _new_athlete(db)
    barrio = await _barrio(db)
    await _complete_profile(db, athlete, barrio)
    await link_parent_to_athlete(db, parent_user_id=FIRST_GUARDIAN_ID, athlete_id=athlete.id)

    report = await _readiness(db, [AUG])

    assert report.month_in_progress is False


@pytest.mark.asyncio
async def test_months_without_activity(db: AsyncSession) -> None:
    athlete = await _new_athlete(db)
    barrio = await _barrio(db)
    await _complete_profile(db, athlete, barrio)
    await link_parent_to_athlete(db, parent_user_id=FIRST_GUARDIAN_ID, athlete_id=athlete.id)
    # A real mark in August (not just a pending gap) …
    await _session_mark(db, date(2026, 8, 10), {athlete.id: AttendanceStatus.PRESENTE})
    # … and nothing at all in September.

    report = await _readiness(db, [AUG, SEP])

    assert report.months_without_activity == ["2026-09"]


# ---------------------------------------------------------------------------
# Size limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_size_limit_raises_over_480_athletes(db: AsyncSession) -> None:
    users = [
        User(
            id=_user_id(),
            email=f"masivo{i}@test.com",
            hashed_password="x",
            first_name="Masivo",
            last_name=f"Ficticio {i}",
            role=UserRole.athlete,
            is_active=True,
            can_login=False,
        )
        for i in range(481)
    ]
    db.add_all(users)
    await db.flush()
    athletes = [
        Athlete(
            id=_athlete_id(),
            user_id=user.id,
            first_name="Masivo",
            last_name=f"Ficticio {i}",
            birth_date=date(2014, 5, 2),
            sex=Sex.M,
            club_id=CLUB_ID,
            created_by=COACH_ID,
        )
        for i, user in enumerate(users)
    ]
    db.add_all(athletes)
    await db.flush()

    with pytest.raises(ReadinessTooLarge):
        await _readiness(db, [AUG])


# ---------------------------------------------------------------------------
# Route — access (403) and header override
# ---------------------------------------------------------------------------

_ROUTE_TABLES = (
    "imderty_barrios",
    "athlete_imderty_profiles",
    "club_imderty_settings",
    "training_sessions",
    "session_attendance",
    "calendar_events",
    "event_audiences",
    "event_attendances",
    "race_events",
    "race_results",
    # The sheet POST loads the authorized sensitive block per month.
    "athlete_sensitive_authorizations",
    "athlete_sensitive_data",
)


@pytest_asyncio.fixture(autouse=True)
async def _ensure_route_tables(imderty_engine):
    """Same idiom as ``test_sheet_api.py``: these tables are not in
    ``conftest.py``'s shared ``_TABLES`` and this file must not edit it."""
    async with imderty_engine.begin() as conn:
        for name in _ROUTE_TABLES:
            await conn.run_sync(
                lambda c, name=name: Base.metadata.tables[name].create(
                    c, checkfirst=True
                )
            )
    yield


def _readiness_url(club_id: int) -> str:
    return f"/api/clubs/{club_id}/imderty-sheet/readiness?from=2026-08&to=2026-08"


@pytest.mark.asyncio
async def test_readiness_route_admin_ok(imderty_scenario: ImdertyScenario, admin_client):
    response = await admin_client.get(_readiness_url(imderty_scenario.club_id))
    assert response.status_code == 200
    body = response.json()
    assert body["months"] == ["2026-08"]
    assert isinstance(body["gaps"], list)


@pytest.mark.asyncio
async def test_readiness_route_coach_of_the_club_ok(
    imderty_scenario: ImdertyScenario, coach_client
):
    response = await coach_client.get(_readiness_url(imderty_scenario.club_id))
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_readiness_route_parent_forbidden(
    imderty_scenario: ImdertyScenario, parent_client
):
    response = await parent_client.get(_readiness_url(imderty_scenario.club_id))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_readiness_route_foreign_coach_forbidden(
    imderty_scenario: ImdertyScenario, foreign_coach_client
):
    response = await foreign_coach_client.get(_readiness_url(imderty_scenario.club_id))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_readiness_route_athlete_account_forbidden(
    imderty_scenario: ImdertyScenario, imderty_client_factory
):
    athlete_user_id = 9753
    await create_user(
        imderty_scenario.session,
        user_id=athlete_user_id,
        role=UserRole.athlete,
        first_name="Atleta Ficticio",
        last_name="Cuenta",
        can_login=False,
    )
    await imderty_scenario.session.commit()
    async with imderty_client_factory(athlete_user_id) as client:
        response = await client.get(_readiness_url(imderty_scenario.club_id))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_readiness_route_invalid_range_is_422(
    imderty_scenario: ImdertyScenario, admin_client
):
    url = f"/api/clubs/{imderty_scenario.club_id}/imderty-sheet/readiness?from=2026-08&to=2026-07"
    response = await admin_client.get(url)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_sheet_header_override_does_not_change_stored_settings(
    imderty_scenario: ImdertyScenario, admin_client
):
    settings_url = f"/api/clubs/{imderty_scenario.club_id}/imderty-settings"
    sheet_url = f"/api/clubs/{imderty_scenario.club_id}/imderty-sheet"

    before = await admin_client.get(settings_url)
    assert before.status_code == 200

    response = await admin_client.post(
        sheet_url,
        json={
            "from": "2026-08",
            "to": "2026-08",
            "header": {
                "contractor_name": "Contratista Override",
                "venue": None,
                "training_days": None,
                "schedule": None,
                "programs": ["individual"],
            },
            "save_header_as_default": False,
        },
    )
    assert response.status_code == 200

    after = await admin_client.get(settings_url)
    assert after.status_code == 200
    assert after.json() == before.json()


@pytest.mark.asyncio
async def test_sheet_header_override_saved_as_default_when_requested(
    imderty_scenario: ImdertyScenario, admin_client
):
    settings_url = f"/api/clubs/{imderty_scenario.club_id}/imderty-settings"
    sheet_url = f"/api/clubs/{imderty_scenario.club_id}/imderty-sheet"

    response = await admin_client.post(
        sheet_url,
        json={
            "from": "2026-08",
            "to": "2026-08",
            "header": {
                "contractor_name": "Contratista Override",
                "venue": None,
                "training_days": None,
                "schedule": None,
                "programs": ["individual"],
            },
            "save_header_as_default": True,
        },
    )
    assert response.status_code == 200

    after = await admin_client.get(settings_url)
    assert after.status_code == 200
    assert after.json()["contractor_name"] == "Contratista Override"
