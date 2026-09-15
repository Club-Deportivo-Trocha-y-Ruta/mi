"""Tests for the course-profile router endpoints (feature 043, User Story 1).

Contract: `specs/043-race-course-profile/contracts/course-api.md` (read it —
this file covers exactly its §7 COACH-ONLY cases: uploads, setups, rename,
delete, and the negative/privacy/query-count assertions). Parent-scoped
reads (`my_categories`, `suggested_setups`, the 404 `course_not_available`
case) are a later task (T052/T053) and are deliberately NOT covered here.

Pattern: same in-memory aiosqlite harness as
`tests/routers/test_race_event_conditions.py` — an explicit
`Base.metadata.create_all(conn, tables=[...])` subset, a `get_current_user`
override with a stub `SimpleNamespace` user (no JWT), and the shared
`AUDIT_TABLES` so `record_audit` calls do not error.

TDD note: `POST/PUT/PATCH/DELETE .../course/*` and `GET .../course` do not
exist on the router yet (T018-T020 land later); every request below either
404s (no matching route) or fails its assertion until then. That is the
expected state — do not skip, xfail, or mock the missing service/router.
"""
from __future__ import annotations

import json
import logging
import math
import re
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
from app.models.race_category import CategoryGender, RaceCategory
from app.models.race_course_variant import RaceCourseVariant
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
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

    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "race_series",
            "race_events",
            "race_categories",
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
