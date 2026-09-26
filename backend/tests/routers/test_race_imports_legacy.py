"""Tests del router — un import legado (staged por el flujo de subida
anterior a esta amendment, sin fila en ``race_import_staged_documents``)
responde ``409 restage_required`` en cada ruta de revisión (feature 044,
amendment 2026-09-26, T134 — contracts/staged-import.md § "API deltas").

No usa ``stage_for_test``/``stage_extracted_results`` a propósito para el
caso legado: inserta el ``RaceImport`` directamente, exactamente como
quedó cualquier carga hecha antes de esta amendment — la fila nunca tuvo
documento y nunca lo tendrá salvo que se re-suba.

Privacidad: nombres/ciudades/clubes sintéticos; ningún archivo real.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

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

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.race_category import RaceCategory
from app.models.race_competitor import CompetitorSex
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.query_counting import count_selects
from tests.helpers.staging import stage_for_test

_IMPORTS_URL = "/api/race-analysis/imports"


def _make_user(role: UserRole, user_id: int, club_ids: tuple[int, ...] = (1,)) -> SimpleNamespace:
    from app.models.club import ClubRole as _ClubRole

    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}{user_id}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[
            SimpleNamespace(club_id=cid, role_in_club=_ClubRole.coach) for cid in club_ids
        ],
    )


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
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
            "race_imports",
            "race_import_staged_documents",
            "race_categories",
            "race_competitors",
            "race_results",
            "race_competitor_signatures",
            "race_identity_candidates",
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
async def actor_user(db_session_factory) -> User:
    async with db_session_factory() as session:
        user = User(
            id=10, email="coach10@test.com", hashed_password="x",
            first_name="Coach", last_name="Ten",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        series = RaceSeries(
            id=1, name="Copa Valle de Ciclomontañismo", season_year=2026,
            organizer="Liga Vallecaucana", points_scheme_code="copa_valle_2026",
        )
        session.add_all([user, series])
        session.add(
            RaceCategory(
                code="INF_A", label="Infantil A", sex=CompetitorSex.M,
                age_min=10, age_max=11, tier="menores", sort_order=1, is_active=True,
            )
        )
        await session.commit()
    return user


@pytest.fixture
def override_storage(monkeypatch, tmp_path):
    from app.services.training import storage_sftp

    fake_base = tmp_path / "uploads-test"
    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_BASE", fake_base)
    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_URL_PREFIX", "/static/uploads/test")
    monkeypatch.setattr(settings, "hostinger_sftp_host", "")
    monkeypatch.setattr(settings, "hostinger_sftp_user", "")
    monkeypatch.setattr(settings, "hostinger_sftp_pass", "")
    monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "")
    monkeypatch.setattr(settings, "hostinger_public_base_url", "")
    yield fake_base


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_session_factory, actor_user, override_storage):
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach, 10, (1,))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _seed_legacy_pending(db_session_factory, *, sha: str = "a" * 64) -> int:
    """Import ``pending`` sin fila de documento — el caso exacto de una
    carga hecha antes de esta amendment."""
    async with db_session_factory() as db:
        imp = RaceImport(
            filename="legacy.pdf",
            sha256=sha,
            series_id=1,
            status=RaceImportStatus.pending,
            stats_json={},
            imported_by_user_id=10,
            imported_at=datetime.now(timezone.utc),
            kind=RaceImportKind.resultados,
            parse_meta_json={
                "header": {
                    "season": 2026, "valida_num": 4, "event_name": "VALIDA IV",
                    "event_date": "2026-05-17", "location": "Cali",
                },
                "results_ext": "pdf",
            },
            storage_path="/legacy/storage/path.pdf",
        )
        db.add(imp)
        await db.commit()
        return imp.id


async def _seed_legacy_committed_with_pending(db_session_factory, *, sha: str = "b" * 64) -> int:
    """Import ``committed`` con ``pending_categories`` y sin documento — un
    commit parcial hecho antes de esta amendment."""
    async with db_session_factory() as db:
        imp = RaceImport(
            filename="legacy_partial.pdf",
            sha256=sha,
            series_id=1,
            status=RaceImportStatus.committed,
            stats_json={"results_inserted": 1},
            imported_by_user_id=10,
            imported_at=datetime.now(timezone.utc),
            kind=RaceImportKind.resultados,
            parse_meta_json={
                "header": {
                    "season": 2026, "valida_num": 5, "event_name": "VALIDA V",
                    "event_date": "2026-06-01", "location": "Buga",
                },
                "results_ext": "pdf",
                "pending_categories": ["CATEGORIA SIN MAPEO"],
            },
            storage_path="/legacy/storage/partial.pdf",
        )
        db.add(imp)
        await db.commit()
        return imp.id


def _assert_restage_required_body(response, import_id: int) -> None:
    assert response.status_code == 409, response.text
    assert response.json() == {"detail": "restage_required", "import_id": import_id}


# ---------------------------------------------------------------------------
# 409 restage_required en cada ruta de revisión
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_on_legacy_import_returns_restage_required(coach_client, db_session_factory):
    import_id = await _seed_legacy_pending(db_session_factory)
    r = await coach_client.post(f"{_IMPORTS_URL}/{import_id}/dry-run")
    _assert_restage_required_body(r, import_id)


@pytest.mark.asyncio
async def test_commit_on_legacy_import_returns_restage_required(coach_client, db_session_factory):
    import_id = await _seed_legacy_pending(db_session_factory)
    r = await coach_client.post(
        f"{_IMPORTS_URL}/{import_id}/commit", json={"resolved_matches": []}
    )
    _assert_restage_required_body(r, import_id)


@pytest.mark.asyncio
async def test_corrections_on_legacy_import_returns_restage_required(coach_client, db_session_factory):
    import_id = await _seed_legacy_pending(db_session_factory)
    r = await coach_client.post(
        f"{_IMPORTS_URL}/{import_id}/corrections",
        json={"op": "remove", "category_header": "INFANTIL A", "ordinal": 1},
    )
    _assert_restage_required_body(r, import_id)


@pytest.mark.asyncio
async def test_acknowledge_on_legacy_import_returns_restage_required(coach_client, db_session_factory):
    import_id = await _seed_legacy_pending(db_session_factory)
    r = await coach_client.post(
        f"{_IMPORTS_URL}/{import_id}/acknowledge",
        json={"category_header": "INFANTIL A", "reason": "source_missing_ordinal"},
    )
    _assert_restage_required_body(r, import_id)


@pytest.mark.asyncio
async def test_commit_pending_on_legacy_partial_commit_returns_restage_required(
    coach_client, db_session_factory
):
    """Un commit parcial legado (``committed`` con ``pending_categories``,
    sin documento) también responde 409 — R-27."""
    import_id = await _seed_legacy_committed_with_pending(db_session_factory)
    r = await coach_client.post(
        f"{_IMPORTS_URL}/{import_id}/commit-pending", json={"resolved_matches": []}
    )
    _assert_restage_required_body(r, import_id)


# ---------------------------------------------------------------------------
# GET detail y discard siguen funcionando sobre un import legado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_detail_still_works_on_a_legacy_import(coach_client, db_session_factory):
    import_id = await _seed_legacy_pending(db_session_factory)
    r = await coach_client.get(f"{_IMPORTS_URL}/{import_id}")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == import_id
    assert r.json()["restage_required"] is True


@pytest.mark.asyncio
async def test_discard_still_works_on_a_legacy_import(coach_client, db_session_factory):
    import_id = await _seed_legacy_pending(db_session_factory)
    r = await coach_client.post(f"{_IMPORTS_URL}/{import_id}/discard")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "discarded"


# ---------------------------------------------------------------------------
# restage_required en detail/list: true para legado, false para stageado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restage_required_true_on_detail_for_legacy_pending(coach_client, db_session_factory):
    import_id = await _seed_legacy_pending(db_session_factory)
    r = await coach_client.get(f"{_IMPORTS_URL}/{import_id}")
    assert r.status_code == 200
    assert r.json()["restage_required"] is True


@pytest.mark.asyncio
async def test_restage_required_true_on_detail_for_legacy_committed_with_pending(
    coach_client, db_session_factory
):
    import_id = await _seed_legacy_committed_with_pending(db_session_factory)
    r = await coach_client.get(f"{_IMPORTS_URL}/{import_id}")
    assert r.status_code == 200
    assert r.json()["restage_required"] is True


@pytest.mark.asyncio
async def test_restage_required_false_on_detail_for_a_staged_import(
    coach_client, db_session_factory, actor_user
):
    async with db_session_factory() as db:
        staged = await stage_for_test(db, actor=actor_user)
        await db.commit()
    r = await coach_client.get(f"{_IMPORTS_URL}/{staged.import_id}")
    assert r.status_code == 200
    assert r.json()["restage_required"] is False


@pytest.mark.asyncio
async def test_restage_required_on_list_no_n_plus_one(
    coach_client, db_session_factory, actor_user, sqlite_engine
):
    """El listado calcula ``restage_required`` con un único ``SELECT``
    batched (T140) — no uno por fila, sin importar cuántos imports haya en
    la página."""
    legacy_ids = {
        await _seed_legacy_pending(db_session_factory, sha=f"{i:064d}") for i in range(3)
    }
    async with db_session_factory() as db:
        staged = await stage_for_test(db, actor=actor_user)
        await db.commit()

    async with count_selects(sqlite_engine) as counter:
        r = await coach_client.get(f"{_IMPORTS_URL}/")
    assert r.status_code == 200, r.text
    baseline_selects = counter[0]

    legacy_ids.add(
        await _seed_legacy_committed_with_pending(db_session_factory, sha="c" * 64)
    )

    async with count_selects(sqlite_engine) as counter:
        r2 = await coach_client.get(f"{_IMPORTS_URL}/")
    assert r2.status_code == 200, r2.text
    # Un import legado más en la página no debe sumar una consulta más: el
    # SELECT de restage_required sigue siendo uno solo, con un `IN` más grande.
    assert counter[0] == baseline_selects, (
        f"el listado hizo {counter[0]} SELECTs con un import legado más "
        f"(antes {baseline_selects}) — sugiere N+1 en restage_required"
    )

    by_id = {item["id"]: item for item in r2.json()["items"]}
    for legacy_id in legacy_ids:
        assert by_id[legacy_id]["restage_required"] is True, legacy_id
    assert by_id[staged.import_id]["restage_required"] is False


# ---------------------------------------------------------------------------
# El rebuild de identidad reporta el import legado como ilegible
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_identity_rebuild_reports_legacy_import_as_unreadable(
    coach_client, db_session_factory
):
    import_id = await _seed_legacy_pending(db_session_factory)
    r = await coach_client.post("/api/race-identity/rebuild")
    assert r.status_code == 200, r.text
    assert import_id in r.json()["imports_unreadable"]
