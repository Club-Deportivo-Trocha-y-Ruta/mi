"""Tests del router ``/api/race-identity/*`` (feature 044, US4, T040).

Estrategia: SQLite async in-memory (StaticPool), seed compartido, overrides
de ``get_db`` + ``get_current_user`` por rol (coach/admin/parent/athlete).
Los candidatos se siembran directamente en ``race_identity_candidates`` —
la lógica pura de ``build_candidates`` ya está cubierta por
``tests/services/race/test_identity_review.py``; aquí se prueba la cáscara
HTTP: status codes, forma de la respuesta, RBAC y que la auditoría llegue.

Nombres sintéticos, evidentemente ficticios ("Ana Prueba Uno" / "Ana Prueba
Uno Dos" / "Carlos Prueba Cuatro"); ninguno corresponde a un menor real.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import AsyncGenerator

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
from app.models.athlete import Athlete, Sex
from app.models.audit_log import AuditLog
from app.models.club import Club, ClubMember, ClubRole
from app.models.race_category import CategoryGender, CategoryTier, RaceCategory
from app.models.race_competitor import CompetitorSex, RaceCompetitor
from app.models.race_competitor_link_audit import RaceCompetitorLinkAudit
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_identity_candidate import (
    IdentityCandidateKind,
    IdentityCandidateState,
    RaceIdentityCandidate,
)
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from app.services.race.identity_resolver import signature_triple
from app.services.race.identity_review import pair_hash, record_key
from tests.helpers.audit_tables import AUDIT_TABLES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(role: UserRole, user_id: int, coach_club_ids: list[int] | None = None) -> SimpleNamespace:
    memberships = []
    if coach_club_ids:
        for cid in coach_club_ids:
            memberships.append(SimpleNamespace(club_id=cid, role_in_club=ClubRole.coach))
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


def _record_snapshot(
    *,
    name: str,
    club: str,
    city: str,
    seasons: list[int],
    category_labels: list[str],
    sex: str | None,
    competitor_id: int | None,
    athlete_linked: bool,
) -> dict:
    triple = signature_triple(name, club, city)
    return {
        "key": record_key(triple),
        "name_printed": name,
        "normalized_name": triple[0],
        "club": club,
        "club_norm": triple[1],
        "city": city,
        "city_norm": triple[2],
        "seasons": seasons,
        "category_codes": [],
        "category_labels": category_labels,
        "sex": sex,
        "competitor_id": competitor_id,
        "athlete_linked": athlete_linked,
    }


# ---------------------------------------------------------------------------
# Fixtures: engine + seed
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
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
            "race_categories",
            "race_competitors",
            "race_competitor_signatures",
            "race_results",
            "race_imports",
            "race_identity_candidates",
            "race_competitor_link_audit",
            *AUDIT_TABLES,
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seed_data(session_factory) -> dict:
    async with session_factory() as session:
        club_tyr = Club(id=1, name="Trocha y Ruta", code="tyr", is_active=True)
        admin = User(
            id=1, email="admin@test.com", hashed_password="x",
            first_name="Admin", last_name="User", role=UserRole.admin,
            is_active=True, can_login=True, created_at=datetime.now(timezone.utc),
        )
        coach = User(
            id=10, email="coach@test.com", hashed_password="x",
            first_name="Coach", last_name="Test", role=UserRole.coach,
            is_active=True, can_login=True, created_at=datetime.now(timezone.utc),
        )
        parent = User(
            id=20, email="parent@test.com", hashed_password="x",
            first_name="Parent", last_name="Test", role=UserRole.parent,
            is_active=True, can_login=True, created_at=datetime.now(timezone.utc),
        )
        athlete_user = User(
            id=30, email="athlete@test.com", hashed_password="x",
            first_name="Athlete", last_name="Test", role=UserRole.athlete,
            is_active=True, can_login=False, created_at=datetime.now(timezone.utc),
        )
        coach_membership = ClubMember(id=1, club_id=1, user_id=10, role_in_club=ClubRole.coach)
        athlete = Athlete(
            id=144, user_id=30, first_name="Ana", last_name="PruebaLink",
            birth_date=date(2013, 3, 15), sex=Sex.F, club_id=1, created_by=10,
        )
        series = RaceSeries(
            id=1, name="Copa Valle de Ciclomontañismo", season_year=2025,
            organizer="Liga", points_scheme_code="copa_valle_2026",
        )
        event_a = RaceEvent(
            id=10, series_id=1, sequence_number=1, name="Sevilla",
            event_date=date(2025, 1, 31), location="Sevilla",
            is_championship=False, status=RaceEventStatus.COMPLETED, created_by_user_id=10,
        )
        event_b = RaceEvent(
            id=11, series_id=1, sequence_number=2, name="Ginebra",
            event_date=date(2025, 2, 28), location="Ginebra",
            is_championship=False, status=RaceEventStatus.COMPLETED, created_by_user_id=10,
        )
        cat = RaceCategory(
            id=100, code="INF_A_F", label="Infantil A Femenino", sex=CategoryGender.F,
            age_min=9, age_max=10, tier=CategoryTier.menores, sort_order=10, is_active=True,
        )

        # Par "same_person_suspect" ya confirmado (dos competitors, dos
        # resultados en válidas distintas) — para decide()/merge/reverse().
        comp_left = RaceCompetitor(
            id=301, normalized_name="ana prueba uno", display_name="Ana Prueba Uno",
            club_text="Club Sintetico Norte", city_text="Ciudad Uno",
            sex=CompetitorSex.F, athlete_id=None,
        )
        comp_right = RaceCompetitor(
            id=302, normalized_name="ana prueba uno dos", display_name="Ana Prueba Uno Dos",
            club_text="Club Sintetico Norte", city_text="Ciudad Uno",
            sex=CompetitorSex.F, athlete_id=144,
            linked_at=datetime.now(timezone.utc), linked_by_user_id=10,
        )
        # Par homónimo pendiente, aislado — solo para 409 not-decided.
        comp_c = RaceCompetitor(
            id=303, normalized_name="carlos prueba cuatro", display_name="Carlos Prueba Cuatro",
            club_text="Club Sintetico Sur", city_text="Ciudad Dos", sex=CompetitorSex.M,
        )
        comp_d = RaceCompetitor(
            id=304, normalized_name="carlos prueba cuatro", display_name="Carlos Prueba Cuatro",
            club_text="Club Sintetico Sur", city_text="Ciudad Tres", sex=CompetitorSex.F,
        )

        session.add_all([
            club_tyr, admin, coach, parent, athlete_user, coach_membership, athlete,
            series, event_a, event_b, cat, comp_left, comp_right, comp_c, comp_d,
        ])
        await session.commit()

        result_left = RaceResult(
            id=9001, event_id=10, category_id=100, competitor_id=301, athlete_id=None,
            bib_number=100, position=1, status=ResultStatus.FINISHED,
            race_time_ms=1800000, points_awarded=40, created_by_user_id=10,
        )
        result_right = RaceResult(
            id=9002, event_id=11, category_id=100, competitor_id=302, athlete_id=144,
            bib_number=101, position=2, status=ResultStatus.FINISHED,
            race_time_ms=1810000, points_awarded=35, created_by_user_id=10,
        )
        session.add_all([result_left, result_right])
        await session.commit()

        left_snap = _record_snapshot(
            name="Ana Prueba Uno", club="Club Sintetico Norte", city="Ciudad Uno",
            seasons=[2025], category_labels=["Infantil A Femenino"], sex="F",
            competitor_id=301, athlete_linked=False,
        )
        right_snap = _record_snapshot(
            name="Ana Prueba Uno Dos", club="Club Sintetico Norte", city="Ciudad Uno",
            seasons=[2025], category_labels=["Infantil A Femenino"], sex="F",
            competitor_id=302, athlete_linked=True,
        )
        merge_candidate = RaceIdentityCandidate(
            id=501, kind=IdentityCandidateKind.same_person_suspect,
            pair_hash=pair_hash(left_snap["key"], right_snap["key"]),
            left_record=left_snap, right_record=right_snap,
            score=91, signals=["extra_or_missing_surname"],
            state=IdentityCandidateState.pending, linked_athlete_involved=True,
        )

        c_snap = _record_snapshot(
            name="Carlos Prueba Cuatro", club="Club Sintetico Sur", city="Ciudad Dos",
            seasons=[2025], category_labels=[], sex="M", competitor_id=303, athlete_linked=False,
        )
        d_snap = _record_snapshot(
            name="Carlos Prueba Cuatro", club="Club Sintetico Sur", city="Ciudad Tres",
            seasons=[2025], category_labels=[], sex="F", competitor_id=304, athlete_linked=False,
        )
        homonym_candidate = RaceIdentityCandidate(
            id=502, kind=IdentityCandidateKind.homonym_suspect,
            pair_hash=pair_hash(c_snap["key"], d_snap["key"]),
            left_record=c_snap, right_record=d_snap,
            score=100, signals=["sex_conflict"],
            state=IdentityCandidateState.pending, linked_athlete_involved=False,
        )
        session.add_all([merge_candidate, homonym_candidate])
        await session.commit()

    return {
        "merge_candidate_id": 501,
        "homonym_candidate_id": 502,
        "comp_left_id": 301,
        "comp_right_id": 302,
        "athlete_id": 144,
        "event_a_id": 10,
        "event_b_id": 11,
        "result_left_id": 9001,
        "result_right_id": 9002,
    }


# ---------------------------------------------------------------------------
# Client fixtures por rol
# ---------------------------------------------------------------------------


def _client_for(session_factory, role: UserRole, user_id: int, **kwargs):
    async def _override_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _make_user(role, user_id, **kwargs)
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest_asyncio.fixture
async def coach_client(session_factory, seed_data):
    async with _client_for(session_factory, UserRole.coach, 10, coach_club_ids=[1]) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(session_factory, seed_data):
    async with _client_for(session_factory, UserRole.admin, 1) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def parent_client(session_factory, seed_data):
    async with _client_for(session_factory, UserRole.parent, 20) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def athlete_client(session_factory, seed_data):
    async with _client_for(session_factory, UserRole.athlete, 30) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# RBAC — denied paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_candidates_parent_403(parent_client):
    response = await parent_client.get("/api/race-identity/candidates")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_candidates_athlete_403(athlete_client):
    response = await athlete_client.get("/api/race-identity/candidates")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_decide_parent_403(parent_client, seed_data):
    response = await parent_client.post(
        f"/api/race-identity/candidates/{seed_data['homonym_candidate_id']}/decide",
        json={"answer": "different_people"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_rebuild_athlete_403(athlete_client):
    response = await athlete_client.post("/api/race-identity/rebuild")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /candidates + GET /summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_candidates_happy_coach(coach_client, seed_data):
    response = await coach_client.get("/api/race-identity/candidates")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 20
    ids = {item["id"] for item in body["items"]}
    assert ids == {seed_data["merge_candidate_id"], seed_data["homonym_candidate_id"]}
    merge_item = next(i for i in body["items"] if i["id"] == seed_data["merge_candidate_id"])
    assert merge_item["state"] == "pending"
    assert merge_item["linked_athlete_involved"] is True
    assert merge_item["left"]["city"] == "Ciudad Uno"
    assert merge_item["right"]["athlete_linked"] is True
    assert set(merge_item.keys()) == {
        "id", "kind", "score", "signals", "left", "right", "state",
        "linked_athlete_involved", "decided_at", "reversed_at",
    }
    assert set(merge_item["left"].keys()) == {
        "name_printed", "club", "city", "seasons", "category_labels",
        "competitor_id", "athlete_linked",
    }


@pytest.mark.asyncio
async def test_list_candidates_filters_by_state_and_kind(coach_client, seed_data):
    response = await coach_client.get(
        "/api/race-identity/candidates", params={"kind": "homonym_suspect"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == seed_data["homonym_candidate_id"]

    response = await coach_client.get(
        "/api/race-identity/candidates", params={"state": "same_person"}
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_list_candidates_invalid_state_422(coach_client):
    response = await coach_client.get(
        "/api/race-identity/candidates", params={"state": "no_existe"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_summary_happy(coach_client, seed_data):
    response = await coach_client.get("/api/race-identity/summary")
    assert response.status_code == 200
    assert response.json() == {"pending": 2, "same_person": 0, "different_people": 0}


# ---------------------------------------------------------------------------
# POST /candidates/{id}/decide — 404, 409, happy (merge)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decide_not_found_404(coach_client):
    response = await coach_client.post(
        "/api/race-identity/candidates/999999/decide",
        json={"answer": "same_person"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_decide_invalid_answer_422(coach_client, seed_data):
    response = await coach_client.post(
        f"/api/race-identity/candidates/{seed_data['homonym_candidate_id']}/decide",
        json={"answer": "not_a_real_answer"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_decide_same_person_merges_and_audits(admin_client, session_factory, seed_data):
    cid = seed_data["merge_candidate_id"]
    response = await admin_client.post(
        f"/api/race-identity/candidates/{cid}/decide",
        json={"answer": "same_person"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"id": cid, "state": "same_person", "merged": True, "results_moved": 1}

    async with session_factory() as session:
        # El competitor "drop" (302, mayor id) fue borrado; sus resultados y
        # su vínculo con el atleta pasaron al competitor "keep" (301).
        dropped = (
            await session.execute(select(RaceCompetitor).where(RaceCompetitor.id == 302))
        ).scalar_one_or_none()
        assert dropped is None
        kept = (
            await session.execute(select(RaceCompetitor).where(RaceCompetitor.id == 301))
        ).scalar_one()
        assert kept.athlete_id == seed_data["athlete_id"]

        moved_result = (
            await session.execute(
                select(RaceResult).where(RaceResult.id == seed_data["result_right_id"])
            )
        ).scalar_one()
        assert moved_result.competitor_id == 301
        assert moved_result.athlete_id == seed_data["athlete_id"]

        # Auditoría: la decisión + la baja del competitor fusionado, ninguna
        # con nombre/club/ciudad en meta_json.
        rows = (
            await session.execute(
                select(AuditLog).where(AuditLog.entity_type == "race_identity_candidate")
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].entity_id == cid
        assert rows[0].diff_json == {"state": {"before": "pending", "after": "same_person"}}
        link_rows = (
            await session.execute(
                select(RaceCompetitorLinkAudit).where(RaceCompetitorLinkAudit.competitor_id == 301)
            )
        ).scalars().all()
        assert len(link_rows) == 1


@pytest.mark.asyncio
async def test_decide_already_decided_409(coach_client, seed_data):
    cid = seed_data["merge_candidate_id"]
    first = await coach_client.post(
        f"/api/race-identity/candidates/{cid}/decide", json={"answer": "same_person"}
    )
    assert first.status_code == 200
    second = await coach_client.post(
        f"/api/race-identity/candidates/{cid}/decide", json={"answer": "same_person"}
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "candidate_not_pending"


# ---------------------------------------------------------------------------
# POST /candidates/{id}/reverse — 404, 409, happy (split después de merge)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reverse_not_found_404(coach_client):
    response = await coach_client.post("/api/race-identity/candidates/999999/reverse")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reverse_pending_candidate_409(coach_client, seed_data):
    response = await coach_client.post(
        f"/api/race-identity/candidates/{seed_data['homonym_candidate_id']}/reverse"
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "candidate_not_decided"


@pytest.mark.asyncio
async def test_reverse_after_commit_splits_and_clears_link(admin_client, session_factory, seed_data):
    cid = seed_data["merge_candidate_id"]
    decide_resp = await admin_client.post(
        f"/api/race-identity/candidates/{cid}/decide", json={"answer": "same_person"}
    )
    assert decide_resp.status_code == 200

    reverse_resp = await admin_client.post(f"/api/race-identity/candidates/{cid}/reverse")
    assert reverse_resp.status_code == 200
    body = reverse_resp.json()
    assert body["id"] == cid
    assert body["state"] == "pending"
    assert body["split"] is True
    assert body["results_moved"] == 1
    assert body["links_cleared"] == 1

    async with session_factory() as session:
        moved_result = (
            await session.execute(
                select(RaceResult).where(RaceResult.id == seed_data["result_right_id"])
            )
        ).scalar_one()
        # El resultado volvió a un competitor NUEVO (no 301, no el 302
        # original que fue borrado) y perdió su athlete_id heredado.
        assert moved_result.competitor_id not in (301, 302)
        assert moved_result.athlete_id is None

        cand = (
            await session.execute(
                select(RaceIdentityCandidate).where(RaceIdentityCandidate.id == cid)
            )
        ).scalar_one()
        assert cand.state == IdentityCandidateState.pending

        rows = (
            await session.execute(
                select(AuditLog).where(AuditLog.entity_type == "race_identity_candidate")
            )
        ).scalars().all()
        # decide() + reverse(): dos filas de auditoría sobre el candidato.
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# POST /rebuild
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rebuild_is_idempotent_over_existing_candidates(coach_client, seed_data):
    response = await coach_client.post("/api/race-identity/rebuild")
    assert response.status_code == 200
    body = response.json()
    # `merge_candidate` (comp_left/comp_right) se regenera con el mismo
    # `pair_hash` → unchanged. `homonym_candidate` (comp_c/comp_d) NO: ambos
    # lados ya son competitors confirmados y distintos, y `build_candidates`
    # no vuelve a preguntar por un par ya separado (docstring del servicio) —
    # sigue en la cola tal como se sembró, sin tocarse ni desaparecer.
    assert body["unchanged"] == 1
    assert body["created"] == 0
    assert body["pending"] == 2
    assert body["imports_unreadable"] == []

    summary = await coach_client.get("/api/race-identity/summary")
    assert summary.json()["pending"] == 2
