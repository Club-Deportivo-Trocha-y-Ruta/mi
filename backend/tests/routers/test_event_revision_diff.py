"""Tests del endpoint read-only ``GET /api/race-analysis/imports/{id}/diff`` (PR4).

Cubre:
- Válida sin revisiones → has_revision=false.
- Última revisión con update de posición/tiempo/gap → grupos + conteos.
- create / delete → grupo added_removed.
- Solo se considera el batch más reciente (changed_at máximo).
- Parent → 403 (RBAC coach/admin).

Estrategia: SQLite async in-memory + override de get_db / get_current_user.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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
from app.models.race_result_revision import (
    RaceResultRevision,
    RaceResultRevisionAction,
)
from app.models.user import UserRole

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
)

_TABLES_NEEDED = [
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
    "race_result_revisions",
]


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES_NEEDED]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded_factory(session_factory):
    """Evento 5 con 3 resultados y un batch de revisión reciente."""
    async with session_factory() as s:
        await create_club(s, club_id=1, name="TyR", code="tyr")
        await create_user(s, user_id=10, role=UserRole.coach, email="coach@test.com")
        await create_race_series(s, series_id=1, season_year=2026)
        await create_race_category(s, category_id=100, code="INF_B")
        await create_race_event(
            s, event_id=5, series_id=1, sequence_number=4,
            name="Válida IV", event_date=date(2026, 5, 17), location="Cali",
        )
        await create_race_competitor(
            s, competitor_id=501, normalized_name="ana ruiz", display_name="Ana Ruiz",
        )
        await create_race_competitor(
            s, competitor_id=502, normalized_name="leo diaz", display_name="Leo Diaz",
        )
        await create_race_competitor(
            s, competitor_id=503, normalized_name="sara gil", display_name="Sara Gil",
        )
        # Resultados (r1 update, r2 delete, r3 sin cambios pero existe)
        r1 = await create_race_result(
            s, event_id=5, category_id=100, competitor_id=501,
            position=2, race_time_ms=1_800_000,
        )
        r2 = await create_race_result(
            s, event_id=5, category_id=100, competitor_id=502,
            position=3, race_time_ms=1_850_000,
            deleted_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
        )
        r3 = await create_race_result(
            s, event_id=5, category_id=100, competitor_id=503,
            position=4, race_time_ms=1_900_000,
        )
        await s.flush()

        latest = datetime(2026, 5, 26, 10, 0, 0)
        older = datetime(2026, 5, 20, 10, 0, 0)

        # Batch reciente (latest): update posición+tiempo de r1, delete r2.
        s.add(
            RaceResultRevision(
                id=1,
                result_id=r1.id,
                action=RaceResultRevisionAction.update,
                changed_by_user_id=10,
                changed_at=latest,
                diff_json={
                    "before": {"position": 3, "race_time_ms": 1_810_000},
                    "after": {"position": 2, "race_time_ms": 1_800_000},
                    "fields": ["position", "race_time_ms"],
                },
                reason="official_correction",
            )
        )
        s.add(
            RaceResultRevision(
                id=2,
                result_id=r2.id,
                action=RaceResultRevisionAction.delete,
                changed_by_user_id=10,
                changed_at=latest,
                diff_json={"removed": {"position": 3}},
                reason="official_correction",
            )
        )
        # Revisión antigua (older) — NO debe aparecer en el diff de la última.
        s.add(
            RaceResultRevision(
                id=3,
                result_id=r3.id,
                action=RaceResultRevisionAction.update,
                changed_by_user_id=10,
                changed_at=older,
                diff_json={
                    "before": {"laps_behind": 1},
                    "after": {"laps_behind": 2},
                    "fields": ["laps_behind"],
                },
                reason="timing_fix",
            )
        )
        await s.commit()

    return session_factory


def _make_user(user_id: int, role: UserRole, email: str):
    return SimpleNamespace(
        id=user_id, role=role, email=email,
        is_active=True, can_login=True, club_memberships=[],
    )


@pytest_asyncio.fixture
async def client_factory(seeded_factory):
    async def _make(user_id: int, role: UserRole, email: str):
        fake_user = _make_user(user_id, role, email)

        async def _override_db() -> AsyncGenerator[AsyncSession, None]:
            async with seeded_factory() as s:
                yield s

        async def _override_user():
            return fake_user

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = _override_user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield _make
    app.dependency_overrides.clear()


_URL = "/api/race-analysis/imports/{eid}/diff"


@pytest.mark.asyncio
async def test_ultima_revision_agrupa_position_time_y_delete(client_factory):
    async with await client_factory(10, UserRole.coach, "coach@test.com") as client:
        r = await client.get(_URL.format(eid=5))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["has_revision"] is True
    assert data["reason_code"] == "official_correction"

    # update de r1 emite 2 items (position + time); delete de r2 → added_removed.
    assert data["counts"]["position"] == 1
    assert data["counts"]["time"] == 1
    assert data["counts"]["added_removed"] == 1
    # gap_gc del batch viejo NO debe aparecer.
    assert data["counts"]["gap_gc"] == 0

    groups = {(it["action"], it["group"]) for it in data["items"]}
    assert ("update", "position") in groups
    assert ("update", "time") in groups
    assert ("delete", "added_removed") in groups


@pytest.mark.asyncio
async def test_time_formateado_en_field_after(client_factory):
    async with await client_factory(10, UserRole.coach, "coach@test.com") as client:
        r = await client.get(_URL.format(eid=5))
    items = r.json()["items"]
    time_item = next(i for i in items if i["group"] == "time")
    # 1_800_000 ms = 30:00
    assert time_item["field_after"] == "30:00"


@pytest.mark.asyncio
async def test_evento_sin_revisiones_has_revision_false(client_factory, session_factory):
    # Creamos un evento 6 sin revisiones.
    async with session_factory() as s:
        await create_race_event(
            s, event_id=6, series_id=1, sequence_number=5,
            name="Válida V", event_date=date(2026, 8, 1), location="Palmira",
        )
        await create_race_competitor(
            s, competitor_id=600, normalized_name="x y", display_name="X Y",
        )
        await create_race_result(
            s, event_id=6, category_id=100, competitor_id=600, position=1,
        )
        await s.commit()

    async with await client_factory(10, UserRole.coach, "coach@test.com") as client:
        r = await client.get(_URL.format(eid=6))
    data = r.json()
    assert data["has_revision"] is False
    assert data["items"] == []


@pytest.mark.asyncio
async def test_parent_403(client_factory):
    async with await client_factory(20, UserRole.parent, "parent@test.com") as client:
        r = await client.get(_URL.format(eid=5))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Catálogo cerrado de motivos de revisión (PR4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_catalogo_motivos_revision(client_factory):
    async with await client_factory(10, UserRole.coach, "coach@test.com") as client:
        r = await client.get("/api/race-analysis/imports/revision-reasons")
    assert r.status_code == 200
    options = r.json()["options"]
    codes = {o["code"] for o in options}
    # Algunos codes esperados del catálogo cerrado.
    assert "official_correction" in codes
    assert "category_reclassification" in codes
    # Todos tienen label legible.
    assert all(o["label"] for o in options)


@pytest.mark.asyncio
async def test_catalogo_motivos_parent_403(client_factory):
    async with await client_factory(20, UserRole.parent, "p@test.com") as client:
        r = await client.get("/api/race-analysis/imports/revision-reasons")
    assert r.status_code == 403
