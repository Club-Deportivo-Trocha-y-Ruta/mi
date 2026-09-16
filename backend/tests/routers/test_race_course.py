"""Tests for the course-profile router endpoints (feature 043, User Story 1).

Contract: `specs/043-race-course-profile/contracts/course-api.md` (read it —
this file covers its §7 COACH-ONLY cases: uploads, setups, rename, delete,
and the negative/privacy/query-count assertions) PLUS, in `TestParentRead`
(T053, User Story 5), the parent-scoped reads (`my_categories`,
`suggested_setups`, the 404 `course_not_available` case) per §1 and §7's
"parent" bullets.

Pattern: same in-memory aiosqlite harness as
`tests/routers/test_race_event_conditions.py` — an explicit
`Base.metadata.create_all(conn, tables=[...])` subset, a `get_current_user`
override with a stub `SimpleNamespace` user (no JWT), and the shared
`AUDIT_TABLES` so `record_audit` calls do not error. `TestParentRead`'s
seeding (User(role=parent) + Athlete + ParentAthlete + RaceCompetitor +
RaceResult) mirrors `tests/routers/test_race_results_privacy.py`.

TDD note (`TestParentRead` only): the router's `GET /course` dependency is
still `require_role([UserRole.admin, UserRole.coach])` (T055 is the sibling
task that adds `UserRole.parent` there and wires the parent branch of
`app/services/race/course/service.py::get_course`, which today raises
`NotImplementedError` for that branch). Every parent-role request below
therefore 403s today instead of asserting its real expectation — that is the
expected red state; do not skip, xfail, or mock the missing service/router
change.
"""
from __future__ import annotations

import json
import logging
import math
import re
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
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

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.athlete import Athlete, ParentAthlete
from app.models.audit_log import AuditLog
from app.models.club import Club
from app.models.race_category import CategoryGender, RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_course_category_setup import RaceCourseCategorySetup
from app.models.race_course_variant import RaceCourseVariant
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from app.services.audit import AuditEntityType
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.gpx_builder import circle_gpx
from tests.helpers.query_counting import count_selects

_BASE = "/api/race-analysis/race-events"


def _course_url(event_id: int, suffix: str = "") -> str:
    return f"{_BASE}/{event_id}/course{suffix}"


def _gpx_files(
    content: bytes,
    filename: str = "recorrido.gpx",
    content_type: str = "application/gpx+xml",
) -> dict:
    return {"file": (filename, content, content_type)}


# ---------------------------------------------------------------------------
# Fixtures (pattern of test_race_event_conditions.py)
# ---------------------------------------------------------------------------


def _make_user(role: UserRole, user_id: int) -> SimpleNamespace:
    """Stub User for the `get_current_user` override — no JWT involved."""
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}{user_id}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    """SQLite in-memory with only the tables this router's domain touches."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Import so metadata registers them (defensive — `app.models.Base`
    # already imports every model, but this documents the dependency).
    from app.models.user import User as _U  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_category import RaceCategory as _C  # noqa: F401
    from app.models.race_course_variant import RaceCourseVariant as _V  # noqa: F401
    from app.models.race_course_category_setup import (  # noqa: F401
        RaceCourseCategorySetup as _CS,
    )
    # Parent-read domain (TestParentRead, T053) — mirrors the table subset of
    # `tests/routers/test_race_results_privacy.py`.
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.athlete import Athlete as _A, ParentAthlete as _PA  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401

    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "club_members",
            "athletes",
            "parent_athlete",
            "race_series",
            "race_events",
            "race_categories",
            "race_competitors",
            "race_results",
            "race_course_variants",
            "race_course_category_setups",
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
async def seed_course_event(db_session_factory):
    """One coach, one admin, one athlete, one series, two válidas (100 and a
    second, unrelated 101 used for the cross-event `variant_not_in_event`
    case), and two race categories to attach setups to."""
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
        athlete_user = User(
            id=20, email="athlete@test.com", hashed_password="x",
            first_name="Athlete", last_name="User",
            role=UserRole.athlete, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        series = RaceSeries(
            id=1, name="Copa Valle de Ciclomontañismo", season_year=2026,
            organizer="Liga Vallecaucana", points_scheme_code="copa_valle_2026",
        )
        event = RaceEvent(
            id=100, series_id=1, sequence_number=4, name="VALIDA IV CALI",
            event_date=date(2026, 5, 17), location="CALI",
            is_championship=False, status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        other_event = RaceEvent(
            id=101, series_id=1, sequence_number=5, name="VALIDA V CALI",
            event_date=date(2026, 6, 14), location="CALI",
            is_championship=False, status=RaceEventStatus.SCHEDULED,
            created_by_user_id=10,
        )
        cat_m = RaceCategory(
            id=12, code="INF_M", label="Infantil masculino", sex=CategoryGender.M
        )
        cat_f = RaceCategory(
            id=13, code="INF_F", label="Infantil femenino", sex=CategoryGender.F
        )
        session.add_all(
            [coach, admin, athlete_user, series, event, other_event, cat_m, cat_f]
        )
        await session.commit()
    yield


def _override_db_factory(factory: async_sessionmaker[AsyncSession]):
    async def _override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return _override_db


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_session_factory, seed_course_event):
    """HTTP client authenticated as coach id=10."""
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach, 10)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def athlete_client(sqlite_engine, db_session_factory, seed_course_event):
    """HTTP client authenticated as an athlete — must be blocked everywhere."""
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.athlete, 20
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client(sqlite_engine, db_session_factory, seed_course_event):
    """HTTP client with no auth override at all."""
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@asynccontextmanager
async def _course_client_as(
    db_session_factory: async_sessionmaker[AsyncSession],
    role: UserRole,
    user_id: int,
):
    """Ad-hoc client builder for `TestParentRead`, which needs many distinct
    parent identities against the same seeded DB — one dedicated fixture per
    identity (the `coach_client`/`athlete_client`/`anon_client` pattern above)
    would not scale here. Same override wiring as those fixtures."""
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(role, user_id)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


# ===========================================================================
# RBAC
# ===========================================================================


class TestRbac:
    @pytest.mark.asyncio
    async def test_athlete_forbidden_on_upload(self, athlete_client):
        content = circle_gpx(radius_m=640, points=300, laps=1)
        r = await athlete_client.post(
            _course_url(100, "/variants"),
            data={"label": "Circuito completo"},
            files=_gpx_files(content),
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_anon_unauthorized_on_upload(self, anon_client):
        content = circle_gpx(radius_m=640, points=300, laps=1)
        r = await anon_client.post(
            _course_url(100, "/variants"),
            data={"label": "Circuito completo"},
            files=_gpx_files(content),
        )
        assert r.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_athlete_forbidden_on_get_course(self, athlete_client):
        """GET /course is coach/admin/parent (T053) — athlete stays rejected."""
        r = await athlete_client.get(_course_url(100))
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_anon_unauthorized_on_get_course(self, anon_client):
        r = await anon_client.get(_course_url(100))
        assert r.status_code in (401, 403)


# ===========================================================================
# Happy paths
# ===========================================================================


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_upload_single_lap_creates_variant_with_figures(
        self, coach_client
    ):
        content = circle_gpx(radius_m=640, points=1200, laps=1)
        r = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Circuito completo"},
            files=_gpx_files(content),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["race_event_id"] == 100
        assert body["has_course_data"] is True
        assert len(body["variants"]) == 1

        variant = body["variants"][0]
        assert variant["label"] == "Circuito completo"
        assert variant["detection"]["method"] == "single"
        circumference = 2 * math.pi * 640
        assert (
            abs(variant["lap_distance_m"] - circumference) / circumference <= 0.01
        )
        assert variant["point_count"] <= 800

    @pytest.mark.asyncio
    async def test_upload_three_laps_detects_closed_loop(self, coach_client):
        content = circle_gpx(radius_m=640, points=120, laps=3, jitter_m=3)
        r = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Vuelta triple"},
            files=_gpx_files(content),
        )
        assert r.status_code == 201, r.text
        variant = r.json()["variants"][0]
        assert variant["detection"]["method"] == "closed_loop"
        assert variant["detection"]["laps_detected"] == 3

    @pytest.mark.asyncio
    async def test_upload_with_recorded_laps_forces_manual(self, coach_client):
        content = circle_gpx(radius_m=640, points=400, laps=2, jitter_m=0)
        r = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Manual dos vueltas", "recorded_laps": "2"},
            files=_gpx_files(content),
        )
        assert r.status_code == 201, r.text
        variant = r.json()["variants"][0]
        assert variant["detection"]["method"] == "manual"

    @pytest.mark.asyncio
    async def test_setups_put_then_get_persists(self, coach_client):
        content = circle_gpx(radius_m=640, points=800, laps=1)
        upload = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Circuito completo"},
            files=_gpx_files(content),
        )
        assert upload.status_code == 201, upload.text
        variant_id = upload.json()["variants"][0]["id"]

        put_resp = await coach_client.put(
            _course_url(100, "/setups"),
            json={
                "setups": [
                    {"category_id": 12, "laps": 3, "variant_id": variant_id}
                ]
            },
        )
        assert put_resp.status_code == 200, put_resp.text
        assert len(put_resp.json()["setups"]) == 1

        get_resp = await coach_client.get(_course_url(100))
        assert get_resp.status_code == 200, get_resp.text
        setups = get_resp.json()["setups"]
        assert len(setups) == 1
        assert setups[0]["category_id"] == 12
        assert setups[0]["laps"] == 3
        assert setups[0]["variant_id"] == variant_id

    @pytest.mark.asyncio
    async def test_patch_variant_renames(self, coach_client):
        content = circle_gpx(radius_m=640, points=800, laps=1)
        upload = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Nombre original"},
            files=_gpx_files(content),
        )
        assert upload.status_code == 201, upload.text
        variant_id = upload.json()["variants"][0]["id"]

        r = await coach_client.patch(
            _course_url(100, f"/variants/{variant_id}"),
            json={"label": "Nombre renombrado"},
        )
        assert r.status_code == 200, r.text
        renamed = next(v for v in r.json()["variants"] if v["id"] == variant_id)
        assert renamed["label"] == "Nombre renombrado"

    @pytest.mark.asyncio
    async def test_delete_unreferenced_variant_succeeds(self, coach_client):
        content = circle_gpx(radius_m=640, points=800, laps=1)
        upload = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Para borrar"},
            files=_gpx_files(content),
        )
        assert upload.status_code == 201, upload.text
        variant_id = upload.json()["variants"][0]["id"]

        r = await coach_client.delete(_course_url(100, f"/variants/{variant_id}"))
        assert r.status_code == 200, r.text
        assert all(v["id"] != variant_id for v in r.json()["variants"])


# ===========================================================================
# Negative paths
# ===========================================================================


class TestNegativePaths:
    @pytest.mark.asyncio
    async def test_fit_named_file_rejected_as_not_gpx(self, coach_client):
        # A valid content-type (octet-stream is in the accepted set for
        # browsers that mislabel .gpx) but a `.fit` filename must fail the
        # extension gate specifically, not the content-type gate.
        content = circle_gpx(radius_m=640, points=200, laps=1)
        r = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Archivo fit"},
            files=_gpx_files(
                content,
                filename="recorrido.fit",
                content_type="application/octet-stream",
            ),
        )
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "not_gpx"

    @pytest.mark.asyncio
    async def test_gzip_magic_bytes_rejected(self, coach_client):
        r = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Comprimido"},
            files=_gpx_files(b"\x1f\x8bjunkjunkjunk", filename="recorrido.gpx"),
        )
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "compressed_not_allowed"

    @pytest.mark.asyncio
    async def test_file_too_large_rejected(self, coach_client):
        oversized = b"x" * (5 * 1024 * 1024 + 1024)  # > 5 MB cap
        r = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Muy grande"},
            files=_gpx_files(oversized, filename="recorrido.gpx"),
        )
        assert r.status_code == 413
        assert r.json()["detail"]["code"] == "file_too_large"

    @pytest.mark.asyncio
    async def test_xxe_payload_rejected(self, coach_client):
        xxe = (
            b'<?xml version="1.0"?>'
            b'<!DOCTYPE gpx [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            b'<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
            b"<trk><trkseg>"
            b'<trkpt lat="3.45" lon="-76.53"><name>&xxe;</name></trkpt>'
            b"</trkseg></trk></gpx>"
        )
        r = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "XXE"},
            files=_gpx_files(xxe, filename="recorrido.gpx"),
        )
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "xml_unsafe"

    @pytest.mark.asyncio
    async def test_duplicate_label_in_same_event_conflicts(self, coach_client):
        content_a = circle_gpx(radius_m=640, points=200, laps=1)
        r1 = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Duplicado"},
            files=_gpx_files(content_a),
        )
        assert r1.status_code == 201, r1.text

        # Different bytes, same label, same event.
        content_b = circle_gpx(radius_m=700, points=200, laps=1)
        r2 = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Duplicado"},
            files=_gpx_files(content_b),
        )
        assert r2.status_code == 409
        assert r2.json()["detail"]["code"] == "variant_label_taken"

    @pytest.mark.asyncio
    async def test_delete_variant_in_use_conflicts_with_category_named(
        self, coach_client
    ):
        content = circle_gpx(radius_m=640, points=800, laps=1)
        upload = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "En uso"},
            files=_gpx_files(content),
        )
        assert upload.status_code == 201, upload.text
        variant_id = upload.json()["variants"][0]["id"]

        put_resp = await coach_client.put(
            _course_url(100, "/setups"),
            json={
                "setups": [
                    {"category_id": 12, "laps": 3, "variant_id": variant_id}
                ]
            },
        )
        assert put_resp.status_code == 200, put_resp.text

        r = await coach_client.delete(_course_url(100, f"/variants/{variant_id}"))
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail["code"] == "variant_in_use"
        assert "Infantil masculino" in json.dumps(detail)

    @pytest.mark.asyncio
    async def test_setups_with_variant_from_another_event_rejected(
        self, coach_client
    ):
        content = circle_gpx(radius_m=640, points=800, laps=1)
        upload = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Del otro evento"},
            files=_gpx_files(content),
        )
        assert upload.status_code == 201, upload.text
        variant_id = upload.json()["variants"][0]["id"]

        # variant_id belongs to event 100 — referencing it from event 101
        # must be rejected.
        r = await coach_client.put(
            _course_url(101, "/setups"),
            json={
                "setups": [
                    {"category_id": 12, "laps": 3, "variant_id": variant_id}
                ]
            },
        )
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "variant_not_in_event"

    @pytest.mark.asyncio
    async def test_same_bytes_twice_is_duplicate_recording(self, coach_client):
        content = circle_gpx(radius_m=640, points=200, laps=1)
        r1 = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Primera subida"},
            files=_gpx_files(content),
        )
        assert r1.status_code == 201, r1.text

        # Exact same bytes, different label, same event.
        r2 = await coach_client.post(
            _course_url(100, "/variants"),
            data={"label": "Segunda subida"},
            files=_gpx_files(content),
        )
        assert r2.status_code == 409
        assert r2.json()["detail"]["code"] == "duplicate_recording"


# ===========================================================================
# Privacy (non-negotiable — Ley 1581)
# ===========================================================================


class TestPrivacy:
    @pytest.mark.asyncio
    async def test_upload_strips_extensions_time_and_author_everywhere(
        self, coach_client, db_session_factory, caplog
    ):
        content = circle_gpx(
            radius_m=640,
            points=300,
            laps=1,
            extensions=True,
            with_time=True,
            metadata=True,
        )
        filename = "grabacion_privada_coach.gpx"

        with caplog.at_level(logging.INFO):
            r = await coach_client.post(
                _course_url(100, "/variants"),
                data={"label": "Con extensiones"},
                files=_gpx_files(content, filename=filename),
            )
        assert r.status_code == 201, r.text

        response_dump = json.dumps(r.json())

        async with db_session_factory() as session:
            row = (
                await session.execute(
                    select(RaceCourseVariant).where(
                        RaceCourseVariant.race_event_id == 100,
                        RaceCourseVariant.label == "Con extensiones",
                    )
                )
            ).scalar_one()
            row_dump = json.dumps(
                {
                    "id": row.id,
                    "label": row.label,
                    "lap_distance_m": row.lap_distance_m,
                    "elevation_gain_m": row.elevation_gain_m,
                    "has_elevation": row.has_elevation,
                    "point_count": row.point_count,
                    "geometry": row.geometry,
                    "detection_method": row.detection_method,
                    "recorded_laps": row.recorded_laps,
                    "source_sha256": row.source_sha256,
                },
                default=str,
            )

        for forbidden in (
            "gpxtpx",
            "TrackPointExtension",
            "Coach Test",
            "2026-01-15",
            '"hr"',
            '"cad"',
            '"atemp"',
        ):
            assert forbidden not in response_dump, forbidden
            assert forbidden not in row_dump, forbidden

        # No filename, no raw high-precision coordinate floats in the logs —
        # only ids/counts/codes belong there (Ley 1581).
        assert filename not in caplog.text
        assert re.search(r"\d+\.\d{5,}", caplog.text) is None


# ===========================================================================
# Query count (N+1 guard)
# ===========================================================================


class TestQueryCount:
    @pytest.mark.asyncio
    async def test_get_course_executes_at_most_three_selects(
        self, coach_client, sqlite_engine
    ):
        async with count_selects(sqlite_engine) as counter:
            r = await coach_client.get(_course_url(100))
        assert r.status_code == 200, r.text
        assert counter[0] <= 3, f"GET /course issued {counter[0]} SELECTs"


# ===========================================================================
# PATCH /course/description (feature 043, User Story 3, T040)
#
# Contract: course-api.md §5b. Body is all four description fields, each
# optional, `extra="forbid"`; `exclude_unset` semantics — a field absent from
# the body is untouched, an explicit `null` clears it.
#
# TDD note: `PATCH .../course/description` does not exist on the router yet
# (T041 lands it — see the "PATCH /course/description es T041 y no se toca
# aquí" comment above `get_race_event_course` in `app/routers/race_events.py`).
# Every case below either 404s (no matching route registered) or fails its
# assertion until then. That is the expected state — do not skip, xfail, or
# mock the missing route/service function.
# ===========================================================================


class TestDescriptionPatch:
    @pytest.mark.asyncio
    async def test_partial_update_leaves_other_fields_untouched(self, coach_client):
        seed = await coach_client.patch(
            _course_url(100, "/description"),
            json={
                "terrain_type": "trocha",
                "technical_difficulty": 3,
                "key_sectors": ["rock_garden"],
                "course_notes": "Sube técnica al inicio.",
            },
        )
        assert seed.status_code == 200, seed.text

        r = await coach_client.patch(
            _course_url(100, "/description"),
            json={"terrain_type": "mixto"},
        )
        assert r.status_code == 200, r.text
        description = r.json()["description"]
        assert description["terrain_type"] == "mixto"
        # exclude_unset semantics — fields absent from this second body must
        # keep the value the first PATCH set, not revert to null.
        assert description["technical_difficulty"] == 3
        assert description["key_sectors"] == ["rock_garden"]
        assert description["course_notes"] == "Sube técnica al inicio."

        # A follow-up GET confirms the persisted state, not just the response.
        get_resp = await coach_client.get(_course_url(100))
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["description"] == description

    @pytest.mark.asyncio
    async def test_explicit_null_clears_field(self, coach_client):
        seed = await coach_client.patch(
            _course_url(100, "/description"),
            json={"technical_difficulty": 4},
        )
        assert seed.status_code == 200, seed.text
        assert seed.json()["description"]["technical_difficulty"] == 4

        r = await coach_client.patch(
            _course_url(100, "/description"),
            json={"technical_difficulty": None},
        )
        assert r.status_code == 200, r.text
        assert r.json()["description"]["technical_difficulty"] is None

    @pytest.mark.asyncio
    async def test_course_notes_over_limit_rejected(self, coach_client):
        r = await coach_client.patch(
            _course_url(100, "/description"),
            json={"course_notes": "x" * 1001},
        )
        assert r.status_code == 422, r.text
        body_text = json.dumps(r.json())
        assert "1000" in body_text or "1 000" in body_text, body_text

    @pytest.mark.asyncio
    async def test_technical_difficulty_out_of_range_rejected(self, coach_client):
        r = await coach_client.patch(
            _course_url(100, "/description"),
            json={"technical_difficulty": 6},
        )
        assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_unknown_key_sector_code_rejected(self, coach_client):
        r = await coach_client.patch(
            _course_url(100, "/description"),
            json={"key_sectors": ["volcano"]},
        )
        assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_more_than_eight_key_sectors_rejected(self, coach_client):
        # Only 8 codes exist in the KeySector catalogue, so a 9th entry must
        # repeat one — the >8 count check fires before the duplicate check
        # either way (schema validator order), so this still isolates the
        # "too many sectors" case rather than the "duplicate sector" one.
        r = await coach_client.patch(
            _course_url(100, "/description"),
            json={
                "key_sectors": [
                    "subida_larga",
                    "bajada_tecnica",
                    "rock_garden",
                    "singletrack",
                    "plano_rapido",
                    "paso_quebrada",
                    "raices",
                    "escalones",
                    "subida_larga",
                ]
            },
        )
        assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_description_alone_sets_has_course_data_with_zero_variants(
        self, coach_client
    ):
        r = await coach_client.patch(
            _course_url(100, "/description"),
            json={
                "terrain_type": "sendero",
                "technical_difficulty": 2,
                "key_sectors": ["singletrack"],
                "course_notes": "Circuito de bosque, sin variantes subidas aún.",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["variants"] == []
        assert body["has_course_data"] is True

    @pytest.mark.asyncio
    async def test_mutation_writes_audit_row(self, coach_client, db_session_factory):
        r = await coach_client.patch(
            _course_url(100, "/description"),
            json={"terrain_type": "pista", "course_notes": "Superficie compactada."},
        )
        assert r.status_code == 200, r.text

        async with db_session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.entity_type == AuditEntityType.race_event.value,
                            AuditLog.entity_id == 100,
                        )
                    )
                )
                .scalars()
                .all()
            )

        assert rows, "expected at least one audit_log row for the PATCH"
        # The exact `changed_fields` shape ("course_description:<field,…>" per
        # course-api.md §22) is left to T041's implementation — asserted
        # loosely here on the touched field names being named somewhere in
        # the row(s) rather than pinned to one exact string.
        changed = ",".join(
            field for row in rows for field in (row.changed_fields or [])
        )
        assert "course_description" in changed
        assert "terrain_type" in changed
        assert "course_notes" in changed

    @pytest.mark.asyncio
    async def test_non_coach_forbidden(self, athlete_client):
        r = await athlete_client.patch(
            _course_url(100, "/description"),
            json={"terrain_type": "mixto"},
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_anon_unauthorized(self, anon_client):
        r = await anon_client.patch(
            _course_url(100, "/description"),
            json={"terrain_type": "mixto"},
        )
        assert r.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_unknown_race_event_404(self, coach_client):
        r = await coach_client.patch(
            _course_url(999999, "/description"),
            json={"terrain_type": "mixto"},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "race_event_not_found"


# ===========================================================================
# Parent read (feature 043, User Story 5, T053)
#
# Contract: course-api.md §1 (`CourseRead.my_categories`, the "parent" bullets
# right below the JSON block) and §7. `my_categories` is derived from
# `RaceResult` rows of the caller's own athletes for this `race_event_id`
# (soft-deleted results excluded). The 200-vs-404 *visibility* gate matches
# `my_categories` exactly: a parent gets 200 only when at least one of their
# own athletes has a result in this event.
#
# TDD note: `GET /course`'s dependency is still
# `require_role([UserRole.admin, UserRole.coach])`, so every parent-role
# request below gets a 403 today (T055 wires `UserRole.parent` in and
# implements the parent branch of `course_svc.get_course`, which currently
# raises `NotImplementedError`). That 403 is the expected red state.
# ===========================================================================


@pytest_asyncio.fixture
async def seed_parent_course(db_session_factory):
    """Seeds the parent-read domain for this event, mirroring the seeding
    style of `tests/routers/test_race_results_privacy.py` (User(role=parent)
    + Athlete + ParentAthlete + RaceCompetitor + RaceResult), not a new one.

    Events (own series, id=2, distinct from `seed_course_event`'s series 1
    used by the coach-only classes above — this fixture is independent and
    never combined with `seed_course_event` in the same test):

    - ``event_prev`` (id=199, sequence_number=4): an earlier válida of the
      series that already has its own category setup + variant — this is
      the "previous válida" R-14 looks at for `suggested_setups` prefill.
    - ``event_main`` (id=200, sequence_number=5): the válida under test.
      Deliberately has NO own setups/variants/description, so
      `has_course_data=False` for it and a coach/admin GET would still show
      a *non-empty* `suggested_setups` sourced from ``event_prev`` (R-14) —
      the parent must never see that prefill (course-api.md §1: "For
      parents: `suggested_setups` is always `[]`").
    - ``event_unrelated`` (id=300, its own series id=3): exists, but no
      result row, nothing ties any seeded athlete to it — the "truly
      unrelated válida" 404 case.

    Athletes / parents (athlete ids use an unusual 94xx range to make a
    cross-parent leakage assertion via plain substring search on the
    serialized JSON reliable — collision with category/event/variant ids is
    not plausible):

    - parent 201 → athlete 9401: linked to the club but with no
      `RaceResult` row anywhere → a second "no relation at all" 404 case.
    - parent 202 → athlete 9402: has a `RaceResult` row on ``event_main`` in
      category 12 (INF_M) → the "one category resolved" case.
    - parent 203 → athletes 9403 (category 12/INF_M) and 9404 (category
      13/INF_F): both via `RaceResult` rows on ``event_main`` → the
      "two children, two categories" case.
    - parent 204 → athlete 9405: linked to the club but with no result row
      on ``event_main`` (nor on ``event_unrelated``) → the "no relation at
      all" 404 case.
    """
    async with db_session_factory() as session:
        coach = User(
            id=10, email="coach_parent_read@test.com", hashed_password="x",
            first_name="Coach", last_name="Ten",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        parent_roster = User(
            id=201, email="parent_roster@test.com", hashed_password="x",
            first_name="Padre", last_name="Roster",
            role=UserRole.parent, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        parent_result = User(
            id=202, email="parent_result@test.com", hashed_password="x",
            first_name="Padre", last_name="Result",
            role=UserRole.parent, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        parent_two = User(
            id=203, email="parent_two@test.com", hashed_password="x",
            first_name="Padre", last_name="Two",
            role=UserRole.parent, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        parent_unrelated = User(
            id=204, email="parent_unrelated@test.com", hashed_password="x",
            first_name="Padre", last_name="Unrelated",
            role=UserRole.parent, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        athlete_users = [
            User(
                id=uid, email=f"athlete{uid}@test.com", hashed_password="x",
                first_name="Atleta", last_name=str(uid),
                role=UserRole.parent, is_active=True, can_login=False,
                created_at=datetime.now(timezone.utc),
            )
            for uid in (9401, 9402, 9403, 9404, 9405)
        ]

        club = Club(id=1, name="Club TyR", code="TYR-PARENT-READ")

        athlete_roster = Athlete(
            id=9401, user_id=9401, first_name="Atleta", last_name="Roster",
            birth_date=date(2013, 1, 1), sex="M", club_id=1, created_by=10,
        )
        athlete_result = Athlete(
            id=9402, user_id=9402, first_name="Atleta", last_name="Result",
            birth_date=date(2013, 2, 2), sex="M", club_id=1, created_by=10,
        )
        athlete_two_a = Athlete(
            id=9403, user_id=9403, first_name="Atleta", last_name="TwoA",
            birth_date=date(2013, 3, 3), sex="M", club_id=1, created_by=10,
        )
        athlete_two_b = Athlete(
            id=9404, user_id=9404, first_name="Atleta", last_name="TwoB",
            birth_date=date(2013, 4, 4), sex="F", club_id=1, created_by=10,
        )
        athlete_unrelated = Athlete(
            id=9405, user_id=9405, first_name="Atleta", last_name="Unrelated",
            birth_date=date(2013, 5, 5), sex="M", club_id=1, created_by=10,
        )

        links = [
            ParentAthlete(parent_id=201, athlete_id=9401, relationship_type="madre"),
            ParentAthlete(parent_id=202, athlete_id=9402, relationship_type="padre"),
            ParentAthlete(parent_id=203, athlete_id=9403, relationship_type="madre"),
            ParentAthlete(parent_id=203, athlete_id=9404, relationship_type="madre"),
            ParentAthlete(parent_id=204, athlete_id=9405, relationship_type="padre"),
        ]

        series = RaceSeries(
            id=2, name="Copa Valle Parent Read", season_year=2026,
            organizer="Liga Vallecaucana", points_scheme_code="copa_valle_2026",
        )
        other_series = RaceSeries(
            id=3, name="Serie sin relacion", season_year=2026,
            organizer="Liga Vallecaucana", points_scheme_code="copa_valle_2026",
        )
        event_prev = RaceEvent(
            id=199, series_id=2, sequence_number=4, name="VALIDA III PARENT",
            event_date=date(2026, 4, 12), location="CALI",
            is_championship=False, status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        event_main = RaceEvent(
            id=200, series_id=2, sequence_number=5, name="VALIDA IV PARENT",
            event_date=date(2026, 5, 17), location="CALI",
            is_championship=False, status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        event_unrelated = RaceEvent(
            id=300, series_id=3, sequence_number=1, name="VALIDA SIN RELACION",
            event_date=date(2026, 6, 1), location="CALI",
            is_championship=False, status=RaceEventStatus.SCHEDULED,
            created_by_user_id=10,
        )

        cat_m = RaceCategory(
            id=12, code="INF_M", label="Infantil masculino", sex=CategoryGender.M
        )
        cat_f = RaceCategory(
            id=13, code="INF_F", label="Infantil femenino", sex=CategoryGender.F
        )

        # `event_prev` has its own setup + variant so R-14's `suggested_setups`
        # has something to prefill onto `event_main` (which has none of its
        # own) — this is what a coach/admin GET on `event_main` would surface,
        # and what a parent's GET on the same event must NOT surface.
        prev_variant = RaceCourseVariant(
            id=50, race_event_id=199, label="Circuito válida anterior",
            lap_distance_m=4200, elevation_gain_m=90, has_elevation=True,
            point_count=400, geometry=[[3.45, -76.53, 1000.0]],
            detection_method="single", recorded_laps=1,
            source_sha256="a" * 64, created_by_user_id=10,
        )
        # Results: athlete 9402 (event_main/cat 12), 9403 (event_main/cat 12),
        # 9404 (event_main/cat 13) — one RaceCompetitor per result row.
        comp_9402 = RaceCompetitor(
            id=9402, normalized_name="atleta result", display_name="Atleta Result",
            club_text="Club TyR", athlete_id=9402,
        )
        comp_9403 = RaceCompetitor(
            id=9403, normalized_name="atleta twoa", display_name="Atleta TwoA",
            club_text="Club TyR", athlete_id=9403,
        )
        comp_9404 = RaceCompetitor(
            id=9404, normalized_name="atleta twob", display_name="Atleta TwoB",
            club_text="Club TyR", athlete_id=9404,
        )
        result_9402 = RaceResult(
            event_id=200, category_id=12, competitor_id=9402, athlete_id=9402,
            position=1, status=ResultStatus.FINISHED,
            race_time_ms=200_000, points_awarded=40, created_by_user_id=10,
        )
        result_9403 = RaceResult(
            event_id=200, category_id=12, competitor_id=9403, athlete_id=9403,
            position=2, status=ResultStatus.FINISHED,
            race_time_ms=205_000, points_awarded=35, created_by_user_id=10,
        )
        result_9404 = RaceResult(
            event_id=200, category_id=13, competitor_id=9404, athlete_id=9404,
            position=1, status=ResultStatus.FINISHED,
            race_time_ms=210_000, points_awarded=40, created_by_user_id=10,
        )

        session.add_all(
            [
                coach, parent_roster, parent_result, parent_two, parent_unrelated,
                *athlete_users, club,
                athlete_roster, athlete_result, athlete_two_a, athlete_two_b,
                athlete_unrelated,
                *links,
                series, other_series, event_prev, event_main, event_unrelated,
                cat_m, cat_f,
                prev_variant,
                comp_9402, comp_9403, comp_9404,
                result_9402, result_9403, result_9404,
            ]
        )
        await session.flush()

        # `RaceCourseCategorySetup` needs `prev_variant`'s id — it's set
        # explicitly above (id=50), but flushing first keeps this symmetric
        # with how the other fixtures order inserts and guarantees the FK
        # target row exists before this insert.
        session.add(
            RaceCourseCategorySetup(
                race_event_id=199, category_id=12, variant_id=50, laps=3,
                updated_by_user_id=10,
            )
        )
        await session.commit()
    yield


class TestParentRead:
    """T053 — parent-scoped `GET /course`."""

    @pytest.mark.asyncio
    async def test_child_with_no_result_is_404_course_not_available(
        self, sqlite_engine, db_session_factory, seed_parent_course
    ):
        """A child with no `RaceResult` row on this event gets 404 —
        visibility is derived solely from results, not from any separate
        call-up concept."""
        async with _course_client_as(db_session_factory, UserRole.parent, 201) as ac:
            r = await ac.get(_course_url(200))
        assert r.status_code == 404, r.text
        assert r.json()["detail"]["code"] == "course_not_available"

    @pytest.mark.asyncio
    async def test_child_with_result_resolves_one_category(
        self, sqlite_engine, db_session_factory, seed_parent_course
    ):
        async with _course_client_as(db_session_factory, UserRole.parent, 202) as ac:
            r = await ac.get(_course_url(200))
        assert r.status_code == 200, r.text
        assert r.json()["my_categories"] == [
            {"athlete_id": 9402, "category_id": 12}
        ]

    @pytest.mark.asyncio
    async def test_two_children_two_categories_both_resolved(
        self, sqlite_engine, db_session_factory, seed_parent_course
    ):
        async with _course_client_as(db_session_factory, UserRole.parent, 203) as ac:
            r = await ac.get(_course_url(200))
        assert r.status_code == 200, r.text
        my_categories = r.json()["my_categories"]
        assert len(my_categories) == 2
        assert {(c["athlete_id"], c["category_id"]) for c in my_categories} == {
            (9403, 12),
            (9404, 13),
        }

    @pytest.mark.asyncio
    async def test_no_related_athlete_on_event_is_404_course_not_available(
        self, sqlite_engine, db_session_factory, seed_parent_course
    ):
        """Parent 204's only athlete (9405) has no result on `event_main` —
        the event itself exists, so this must be `course_not_available`,
        never `race_event_not_found`."""
        async with _course_client_as(db_session_factory, UserRole.parent, 204) as ac:
            r = await ac.get(_course_url(200))
        assert r.status_code == 404, r.text
        assert r.json()["detail"]["code"] == "course_not_available"

    @pytest.mark.asyncio
    async def test_truly_unrelated_valida_is_also_404_course_not_available(
        self, sqlite_engine, db_session_factory, seed_parent_course
    ):
        """Parent 202 *does* have visibility on `event_main` (200) via a
        result, but `event_unrelated` (300) has no result tying any seeded
        athlete to it — scoping is per-event, so this must still 404, not
        leak visibility from the other event."""
        async with _course_client_as(db_session_factory, UserRole.parent, 202) as ac:
            r = await ac.get(_course_url(300))
        assert r.status_code == 404, r.text
        assert r.json()["detail"]["code"] == "course_not_available"

    @pytest.mark.asyncio
    async def test_response_never_leaks_other_athletes_or_results_key(
        self, sqlite_engine, db_session_factory, seed_parent_course
    ):
        """Parent 203 (two own children, 9403/9404) must never see athlete
        9401 (parent 201's child, no relation), 9402 (parent 202's child) or
        9405 (parent 204's child, unrelated) anywhere in the payload. The
        response is also confirmed to keep the plain `CourseRead` shape —
        no separate `results` key ever appears here (results are a
        completely different endpoint)."""
        async with _course_client_as(db_session_factory, UserRole.parent, 203) as ac:
            r = await ac.get(_course_url(200))
        assert r.status_code == 200, r.text
        body = r.json()
        raw = json.dumps(body)

        assert "results" not in body
        assert set(body.keys()) <= {
            "race_event_id", "has_course_data", "variants", "setups",
            "suggested_setups", "description", "my_categories",
        }

        for foreign_athlete_id in (9401, 9402, 9405):
            assert str(foreign_athlete_id) not in raw, (
                f"athlete_id={foreign_athlete_id} (another family's child) "
                "must never appear in a parent-scoped course response."
            )

    @pytest.mark.asyncio
    async def test_suggested_setups_always_empty_for_parent_even_when_coach_sees_entries(
        self, sqlite_engine, db_session_factory, seed_parent_course
    ):
        """`event_main` (200) has no setups of its own, so R-14 prefill from
        `event_prev` (199) applies — course-api.md §1 confirms a coach/admin
        GET surfaces that as `suggested_setups`. §1 also states parents
        always get `suggested_setups: []`, regardless. Proven on the exact
        same event so the only variable is the caller's role."""
        async with _course_client_as(db_session_factory, UserRole.coach, 10) as ac:
            coach_resp = await ac.get(_course_url(200))
        assert coach_resp.status_code == 200, coach_resp.text
        coach_suggested = coach_resp.json()["suggested_setups"]
        assert coach_suggested != [], (
            "test setup error: expected the coach view of event_main to show "
            "the R-14 prefill from event_prev's setup — fixture drifted."
        )
        assert coach_suggested[0]["category_id"] == 12
        assert coach_suggested[0]["source_event_id"] == 199

        async with _course_client_as(db_session_factory, UserRole.parent, 202) as ac:
            parent_resp = await ac.get(_course_url(200))
        assert parent_resp.status_code == 200, parent_resp.text
        assert parent_resp.json()["suggested_setups"] == []
