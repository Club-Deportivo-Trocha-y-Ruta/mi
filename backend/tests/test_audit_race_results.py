"""Tests de instrumentación de auditoría del dominio de resultados de carrera
(feature 041, T028 — contracts/audit-recording.md §4.10).

Cubre que cada endpoint mutador de
``routers/race_imports.py``, ``race_events.py``, ``race_series.py`` y
``race_competitors.py`` encola exactamente la fila de ``audit_log`` que
describe §4.10: mismo patrón SQLite in-memory + ``app.dependency_overrides``
que ``tests/routers/test_race_events_crud.py`` / ``test_race_imports.py`` —
sin MySQL, sin tocar ``tests/conftest.py``.

Los dos rastros de dominio (``race_result_revisions``,
``race_competitor_link_audit``) NO se duplican aquí — solo se verifica que la
fila-resumen del club-wide ``audit_log`` exista y apunte al mismo
``entity_id``.

Ningún nombre corresponde a una persona real (CLAUDE.md, Ley 1581).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.audit_log import AuditAction, AuditLog
from app.models.club import Club, ClubMember, ClubRole
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_import import RaceImport, RaceImportStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from tests.helpers.audit_tables import AUDIT_TABLES

_PDF_HEADER = b"%PDF-1.4\n"


def _make_user(role: UserRole, user_id: int = 10) -> SimpleNamespace:
    memberships = []
    if role == UserRole.coach:
        memberships = [
            SimpleNamespace(club_id=1, role_in_club=ClubRole.coach)
        ]
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=memberships,
    )


def _pdf_file(content_extra: bytes = b"") -> tuple[str, bytes, str]:
    return ("resultados.pdf", _PDF_HEADER + content_extra, "application/pdf")


def _parse_form(**overrides) -> dict:
    form = {
        "series_name": "Copa Valle",
        "season": "2026",
        "valida_num": "4",
        "event_name": "VALIDA IV CALI",
        "event_date": "2026-05-17",
        "location": "CALI",
    }
    form.update({k: str(v) for k, v in overrides.items()})
    return form


# ---------------------------------------------------------------------------
# Engine / sesión — subgrafo completo del dominio de carreras + audit_log
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.calendar_event import CalendarEvent as _CE  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.race_category import RaceCategory as _C  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_event_roster import RaceEventRoster as _RER  # noqa: F401
    from app.models.race_import import RaceImport as _I  # noqa: F401
    from app.models.race_competitor_link_audit import (  # noqa: F401
        RaceCompetitorLinkAudit as _RCLA,
    )
    from app.models.race_result import RaceResult as _R  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.training_session import TrainingSession as _TS  # noqa: F401
    from app.models.user import User as _U  # noqa: F401

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "club_members",
            "athletes",
            "race_series",
            "race_events",
            "calendar_events",
            "event_audiences",
            "event_attendances",
            "training_sessions",
            "race_imports",
            "race_categories",
            "race_competitors",
            "race_results",
            "race_event_roster",
            "race_competitor_link_audit",
            *AUDIT_TABLES,
        )
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seed(db_session_factory):
    """Coach id=10, admin id=1, club id=1, una serie base (id=1)."""
    async with db_session_factory() as session:
        coach = User(
            id=10, email="coach@test.com", hashed_password="x",
            first_name="Coach", last_name="Ten",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        admin = User(
            id=1, email="admin@test.com", hashed_password="x",
            first_name="Admin", last_name="User",
            role=UserRole.admin, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        club = Club(id=1, name="Club Ficticio", code="cft-t028")
        session.add_all([coach, admin, club])
        await session.flush()
        session.add(ClubMember(club_id=1, user_id=10, role_in_club=ClubRole.coach))
        series = RaceSeries(
            id=1, name="Copa Valle de Ciclomontañismo", season_year=2026,
            organizer="Liga Vallecaucana", points_scheme_code="copa_valle_2026",
        )
        session.add(series)
        await session.commit()
    yield


@pytest.fixture
def override_storage(monkeypatch, tmp_path):
    from app.services.training import storage_sftp

    fake_base = tmp_path / "uploads-test"
    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_BASE", fake_base)
    monkeypatch.setattr(
        storage_sftp, "_LOCAL_FALLBACK_URL_PREFIX", "/static/uploads/test"
    )
    monkeypatch.setattr(settings, "hostinger_sftp_host", "")
    monkeypatch.setattr(settings, "hostinger_sftp_user", "")
    monkeypatch.setattr(settings, "hostinger_sftp_pass", "")
    monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "")
    monkeypatch.setattr(settings, "hostinger_public_base_url", "")
    yield fake_base


@pytest.fixture
def stub_parsers(monkeypatch):
    from app.routers import race_imports as router_mod

    async def fake_parse_results(path, ext):  # noqa: ARG001
        from app.services.race.pdf_parser import ResultsRow
        return {
            "TET_CP": [
                ResultsRow(
                    position=1, bib="550", name="Sebastian Yule Mendoza",
                    city="Yumbo", club="Club Trocha y Ruta",
                    time_raw="0:03:38", points=40,
                ),
            ],
        }

    async def fake_parse_general(path):  # noqa: ARG001
        return {}

    monkeypatch.setattr(router_mod, "_parse_results_with_timeout", fake_parse_results)
    monkeypatch.setattr(router_mod, "_parse_general_with_timeout", fake_parse_general)


@pytest.fixture
def stub_ingestor(monkeypatch):
    """Promueve pending→committed como el ingestor real (evita queries que
    SQLite in-memory no soporta desde el ingestor completo)."""
    from app.schemas.race import IngestReport
    from app.services.race import ingestor as ingestor_mod

    async def fake_ingest(self, meta, results_by_category, **kwargs):  # noqa: ARG001
        dry_run = kwargs.get("dry_run", False)
        sha = kwargs.get("pdf_results_sha256")
        if not dry_run and sha:
            result = await self.db.execute(
                select(RaceImport).where(
                    RaceImport.sha256 == sha,
                    RaceImport.status == RaceImportStatus.pending,
                )
            )
            pending = result.scalar_one_or_none()
            if pending is not None:
                pending.status = RaceImportStatus.committed
                await self.db.flush()
        return IngestReport(
            event_id=100,
            series_id=1,
            competitors_created=1,
            competitors_updated=0,
            results_inserted=1,
            results_skipped=0,
            tyr_count=1,
            warnings=[],
        )

    monkeypatch.setattr(ingestor_mod.RaceIngestor, "ingest_event", fake_ingest)


def _override_db(factory):
    async def _inner():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return _inner


@pytest_asyncio.fixture
async def coach_client(db_session_factory, seed, override_storage):
    app.dependency_overrides[get_db] = _override_db(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=10
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(db_session_factory, seed, override_storage):
    app.dependency_overrides[get_db] = _override_db(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.admin, user_id=1
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _audit_rows(db_session_factory, entity_type: str) -> list[AuditLog]:
    async with db_session_factory() as session:
        rows = (
            await session.execute(
                select(AuditLog).where(AuditLog.entity_type == entity_type)
            )
        ).scalars().all()
        return list(rows)


# ---------------------------------------------------------------------------
# race_series — POST /
# ---------------------------------------------------------------------------


class TestRaceSeriesAudit:
    @pytest.mark.asyncio
    async def test_create_series_records_audit_row(self, coach_client, db_session_factory):
        r = await coach_client.post(
            "/api/race-analysis/race-series/",
            json={
                "name": "Copa Nueva",
                "season_year": 2027,
                "organizer": "Liga Vallecaucana",
                "kind": "cup",
                "level": "departmental",
            },
        )
        assert r.status_code == 201, r.text
        series_id = r.json()["id"]

        rows = await _audit_rows(db_session_factory, "race_series")
        assert len(rows) == 1
        assert rows[0].action == AuditAction.create
        assert rows[0].entity_id == series_id
        assert rows[0].actor_user_id == 10


# ---------------------------------------------------------------------------
# race_events — POST /, PATCH /{id}, DELETE /{id}, roster CRUD
# ---------------------------------------------------------------------------


class TestRaceEventAudit:
    @pytest.mark.asyncio
    async def test_create_event_records_audit_row(self, coach_client, db_session_factory):
        r = await coach_client.post(
            "/api/race-analysis/race-events/",
            json={
                "series_id": 1,
                "sequence_number": 1,
                "name": "V-I CALI",
                "event_date": "2026-05-17",
                "location": "CALI",
                "create_calendar_event": False,
            },
        )
        assert r.status_code == 201, r.text
        event_id = r.json()["id"]

        rows = await _audit_rows(db_session_factory, "race_event")
        assert len(rows) == 1
        assert rows[0].action == AuditAction.create
        assert rows[0].entity_id == event_id

    @pytest.mark.asyncio
    async def test_update_event_records_audit_row_with_changed_fields(
        self, coach_client, db_session_factory
    ):
        r = await coach_client.post(
            "/api/race-analysis/race-events/",
            json={
                "series_id": 1,
                "sequence_number": 1,
                "name": "V-I CALI",
                "event_date": "2026-05-17",
                "location": "CALI",
                "create_calendar_event": False,
            },
        )
        event_id = r.json()["id"]

        r = await coach_client.patch(
            f"/api/race-analysis/race-events/{event_id}",
            json={"name": "V-I CALI (editado)"},
        )
        assert r.status_code == 200, r.text

        rows = await _audit_rows(db_session_factory, "race_event")
        update_rows = [row for row in rows if row.action == AuditAction.update]
        assert len(update_rows) == 1
        assert update_rows[0].changed_fields == ["name"]

    @pytest.mark.asyncio
    async def test_update_event_empty_body_records_no_audit_row(
        self, coach_client, db_session_factory
    ):
        r = await coach_client.post(
            "/api/race-analysis/race-events/",
            json={
                "series_id": 1,
                "sequence_number": 1,
                "name": "V-I CALI",
                "event_date": "2026-05-17",
                "location": "CALI",
                "create_calendar_event": False,
            },
        )
        event_id = r.json()["id"]

        r = await coach_client.patch(
            f"/api/race-analysis/race-events/{event_id}", json={}
        )
        assert r.status_code == 200

        rows = await _audit_rows(db_session_factory, "race_event")
        update_rows = [row for row in rows if row.action == AuditAction.update]
        assert update_rows == []

    @pytest.mark.asyncio
    async def test_delete_event_records_audit_row(self, admin_client, db_session_factory):
        r = await admin_client.post(
            "/api/race-analysis/race-events/",
            json={
                "series_id": 1,
                "sequence_number": 1,
                "name": "V-I CALI",
                "event_date": "2026-05-17",
                "location": "CALI",
                "create_calendar_event": False,
            },
        )
        event_id = r.json()["id"]

        r = await admin_client.delete(f"/api/race-analysis/race-events/{event_id}")
        assert r.status_code == 204, r.text

        rows = await _audit_rows(db_session_factory, "race_event")
        delete_rows = [row for row in rows if row.action == AuditAction.delete]
        assert len(delete_rows) == 1
        assert delete_rows[0].entity_id == event_id

    @pytest.mark.asyncio
    async def test_conditions_patch_records_audit_row(
        self, coach_client, db_session_factory
    ):
        r = await coach_client.post(
            "/api/race-analysis/race-events/",
            json={
                "series_id": 1,
                "sequence_number": 1,
                "name": "V-I CALI",
                "event_date": "2026-05-17",
                "location": "CALI",
                "create_calendar_event": False,
            },
        )
        event_id = r.json()["id"]

        r = await coach_client.patch(
            f"/api/race-analysis/race-events/{event_id}/conditions",
            json={"climate": "soleado", "altitude_msnm": 1000},
        )
        assert r.status_code == 200, r.text

        rows = await _audit_rows(db_session_factory, "race_event")
        update_rows = [row for row in rows if row.action == AuditAction.update]
        assert len(update_rows) == 1
        assert update_rows[0].changed_fields == ["altitude_msnm", "climate"]


class TestRaceEventRosterAudit:
    @pytest_asyncio.fixture
    async def event_and_athlete(self, db_session_factory):
        from datetime import date

        from app.models.athlete import Athlete, Sex

        async with db_session_factory() as session:
            event = RaceEvent(
                series_id=1, sequence_number=2, name="V-II PALMIRA",
                event_date=date(2026, 6, 1), location="Palmira",
                status=RaceEventStatus.SCHEDULED, created_by_user_id=10,
            )
            session.add(event)
            athlete_user = User(
                id=600, email="atleta@test.com", hashed_password="x",
                first_name="Atleta", last_name="Ficticio",
                role=UserRole.parent, is_active=True, can_login=False,
                created_at=datetime.now(timezone.utc),
            )
            session.add(athlete_user)
            await session.flush()
            athlete = Athlete(
                id=600, user_id=600, first_name="Atleta", last_name="Ficticio",
                birth_date=date(2013, 1, 1), sex=Sex.M, club_id=1,
                created_by=10,
            )
            session.add(athlete)
            await session.commit()
            return event.id, athlete.id

    @pytest.mark.asyncio
    async def test_add_roster_entry_records_audit_row(
        self, coach_client, db_session_factory, event_and_athlete
    ):
        event_id, athlete_id = event_and_athlete
        r = await coach_client.post(
            f"/api/race-analysis/race-events/{event_id}/roster",
            json={"athlete_id": athlete_id, "status": "called_up"},
        )
        assert r.status_code == 201, r.text
        entry_id = r.json()["id"]

        rows = await _audit_rows(db_session_factory, "race_event_roster")
        assert len(rows) == 1
        assert rows[0].action == AuditAction.create
        assert rows[0].entity_id == entry_id
        assert rows[0].athlete_id == athlete_id

    @pytest.mark.asyncio
    async def test_update_roster_entry_records_audit_row(
        self, coach_client, db_session_factory, event_and_athlete
    ):
        event_id, athlete_id = event_and_athlete
        r = await coach_client.post(
            f"/api/race-analysis/race-events/{event_id}/roster",
            json={"athlete_id": athlete_id, "status": "called_up"},
        )
        entry_id = r.json()["id"]

        r = await coach_client.patch(
            f"/api/race-analysis/race-events/{event_id}/roster/{entry_id}",
            json={"status": "confirmed"},
        )
        assert r.status_code == 200, r.text

        rows = await _audit_rows(db_session_factory, "race_event_roster")
        update_rows = [row for row in rows if row.action == AuditAction.update]
        assert len(update_rows) == 1
        assert update_rows[0].changed_fields == ["status"]

    @pytest.mark.asyncio
    async def test_delete_roster_entry_records_audit_row(
        self, coach_client, db_session_factory, event_and_athlete
    ):
        event_id, athlete_id = event_and_athlete
        r = await coach_client.post(
            f"/api/race-analysis/race-events/{event_id}/roster",
            json={"athlete_id": athlete_id, "status": "called_up"},
        )
        entry_id = r.json()["id"]

        r = await coach_client.delete(
            f"/api/race-analysis/race-events/{event_id}/roster/{entry_id}"
        )
        assert r.status_code == 204, r.text

        rows = await _audit_rows(db_session_factory, "race_event_roster")
        delete_rows = [row for row in rows if row.action == AuditAction.delete]
        assert len(delete_rows) == 1
        assert delete_rows[0].entity_id == entry_id
        assert delete_rows[0].athlete_id == athlete_id


# ---------------------------------------------------------------------------
# race_import — parse (create) + commit (execute)
# ---------------------------------------------------------------------------


class TestRaceImportAudit:
    @pytest.mark.asyncio
    async def test_parse_records_create_audit_row(
        self, coach_client, db_session_factory, stub_parsers
    ):
        files = {"resultados_pdf": _pdf_file(b"contenido de prueba")}
        r = await coach_client.post(
            "/api/race-analysis/imports/parse", data=_parse_form(), files=files
        )
        assert r.status_code == 200, r.text
        parse_id = r.json()["parse_id"]

        rows = await _audit_rows(db_session_factory, "race_import")
        assert len(rows) == 1
        assert rows[0].action == AuditAction.create
        assert rows[0].entity_id == parse_id

    @pytest.mark.asyncio
    async def test_commit_records_execute_audit_row_with_meta(
        self, coach_client, db_session_factory, stub_parsers, stub_ingestor
    ):
        files = {"resultados_pdf": _pdf_file(b"contenido de flujo completo")}
        r = await coach_client.post(
            "/api/race-analysis/imports/parse", data=_parse_form(), files=files
        )
        parse_id = r.json()["parse_id"]

        r = await coach_client.post(f"/api/race-analysis/imports/{parse_id}/dry-run")
        assert r.status_code == 200, r.text

        from app.services.race.normalizer import normalize_name

        match_norm = normalize_name("Sebastian Yule Mendoza")
        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/commit",
            json={
                "resolved_matches": [
                    {"competitor_normalized_name": match_norm, "athlete_id": None}
                ]
            },
        )
        assert r.status_code == 200, r.text

        rows = await _audit_rows(db_session_factory, "race_import")
        execute_rows = [row for row in rows if row.action == AuditAction.execute]
        assert len(execute_rows) == 1
        row = execute_rows[0]
        assert row.entity_id == parse_id
        assert row.changed_fields == ["status"]
        assert row.meta_json["race_event_id"] == 100
        assert row.meta_json["is_revision"] is False
        assert row.meta_json["results_count"] == 1
        assert row.meta_json["competitors_count"] == 1


# ---------------------------------------------------------------------------
# race_competitors — POST /{id}/link, DELETE /{id}/link
# ---------------------------------------------------------------------------


class TestRaceCompetitorLinkAudit:
    @pytest_asyncio.fixture
    async def competitor_and_athlete(self, db_session_factory):
        from datetime import date

        from app.models.athlete import Athlete, Sex
        from app.models.race_competitor import RaceCompetitor

        async with db_session_factory() as session:
            athlete_user = User(
                id=700, email="atleta2@test.com", hashed_password="x",
                first_name="Atleta", last_name="Ficticio Dos",
                role=UserRole.parent, is_active=True, can_login=False,
                created_at=datetime.now(timezone.utc),
            )
            session.add(athlete_user)
            await session.flush()
            athlete = Athlete(
                id=700, user_id=700, first_name="Atleta", last_name="Ficticio Dos",
                birth_date=date(2012, 1, 1), sex=Sex.F, club_id=1,
                created_by=10,
            )
            session.add(athlete)
            competitor = RaceCompetitor(
                display_name="Competidor Sin Enlazar",
                normalized_name="competidor sin enlazar",
                club_text="Club Externo",
            )
            session.add(competitor)
            await session.commit()
            return competitor.id, athlete.id

    @pytest.mark.asyncio
    async def test_link_records_audit_row(
        self, coach_client, db_session_factory, competitor_and_athlete
    ):
        competitor_id, athlete_id = competitor_and_athlete
        r = await coach_client.post(
            f"/api/race-competitors/{competitor_id}/link",
            json={"athlete_id": athlete_id},
        )
        assert r.status_code == 200, r.text

        rows = await _audit_rows(db_session_factory, "race_competitor")
        link_rows = [row for row in rows if row.action == AuditAction.link]
        assert len(link_rows) == 1
        assert link_rows[0].entity_id == competitor_id
        assert link_rows[0].athlete_id == athlete_id

    @pytest.mark.asyncio
    async def test_link_idempotent_replay_records_no_extra_row(
        self, coach_client, db_session_factory, competitor_and_athlete
    ):
        competitor_id, athlete_id = competitor_and_athlete
        await coach_client.post(
            f"/api/race-competitors/{competitor_id}/link",
            json={"athlete_id": athlete_id},
        )
        r = await coach_client.post(
            f"/api/race-competitors/{competitor_id}/link",
            json={"athlete_id": athlete_id},
        )
        assert r.status_code == 200
        assert r.json()["already_linked"] is True

        rows = await _audit_rows(db_session_factory, "race_competitor")
        link_rows = [row for row in rows if row.action == AuditAction.link]
        assert len(link_rows) == 1

    @pytest.mark.asyncio
    async def test_unlink_records_audit_row(
        self, coach_client, db_session_factory, competitor_and_athlete
    ):
        competitor_id, athlete_id = competitor_and_athlete
        await coach_client.post(
            f"/api/race-competitors/{competitor_id}/link",
            json={"athlete_id": athlete_id},
        )

        r = await coach_client.delete(f"/api/race-competitors/{competitor_id}/link")
        assert r.status_code == 200, r.text
        assert r.json()["was_linked"] is True

        rows = await _audit_rows(db_session_factory, "race_competitor")
        unlink_rows = [row for row in rows if row.action == AuditAction.unlink]
        assert len(unlink_rows) == 1
        assert unlink_rows[0].entity_id == competitor_id
        assert unlink_rows[0].athlete_id == athlete_id
