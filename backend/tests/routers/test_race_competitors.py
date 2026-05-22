"""Tests del router ``/api/race-competitors/*``.

Estrategia: SQLite async in-memory (StaticPool), seed compartido, overrides
de ``get_db`` + ``get_current_user`` para cada rol (coach/admin/parent/anon).

Cobertura del contrato HTTP:

| Caso                                         | Status |
|----------------------------------------------|--------|
| GET /  unlinked=true happy                   |  200   |
| GET /?unlinked=false                         |  400   |
| GET / como parent                            |  403   |
| GET / sin auth                               |  401   |
| GET /{id}/suggestions happy                  |  200   |
| GET /{id}/suggestions competitor inexistente |  404   |
| POST /{id}/link happy (4 results propagados) |  200   |
| POST /{id}/link mismo athlete (idempotente)  |  200, already_linked=true |
| POST /{id}/link athlete distinto             |  409   |
| POST /{id}/link athlete inexistente          |  404   |
| POST /{id}/link competitor inexistente       |  404   |
| POST /{id}/link coach a athlete de otro club |  403   |
| POST /{id}/link como parent                  |  403   |
| DELETE /{id}/link happy                      |  200, results NULL |
| DELETE /{id}/link competitor unlinked        |  200, was_linked=false |
| DELETE /{id}/link competitor inexistente     |  404   |
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
from app.models.club import Club, ClubMember, ClubRole
from app.models.race_category import CategoryGender, CategoryTier, RaceCategory
from app.models.race_competitor import CompetitorSex, RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    role: UserRole, user_id: int = 10, coach_club_ids: list[int] = None
) -> SimpleNamespace:
    memberships = []
    if coach_club_ids:
        for cid in coach_club_ids:
            memberships.append(
                SimpleNamespace(club_id=cid, role_in_club=ClubRole.coach)
            )
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
    # Asegurar registro de modelos
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.race_category import RaceCategory as _Cat  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_competitor_link_audit import (  # noqa: F401
        RaceCompetitorLinkAudit as _LA,
    )
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.user import User as _U  # noqa: F401

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
            "race_results",
            "race_competitor_link_audit",
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
        club_other = Club(id=2, name="Otro Club", code="otro", is_active=True)
        admin = User(
            id=1,
            email="admin@test.com",
            hashed_password="x",
            first_name="Admin",
            last_name="User",
            role=UserRole.admin,
            is_active=True,
            can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        coach = User(
            id=10,
            email="coach@test.com",
            hashed_password="x",
            first_name="Coach",
            last_name="Test",
            role=UserRole.coach,
            is_active=True,
            can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        parent = User(
            id=20,
            email="parent@test.com",
            hashed_password="x",
            first_name="Parent",
            last_name="Test",
            role=UserRole.parent,
            is_active=True,
            can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        coach_membership = ClubMember(
            id=1, club_id=1, user_id=10, role_in_club=ClubRole.coach
        )
        # Athletes: 144 en club TyR, 145 en club Otro
        athlete = Athlete(
            id=144,
            user_id=10,
            first_name="Juan Diego",
            last_name="Garcia Bohorquez",
            birth_date=date(2014, 3, 15),
            sex=Sex.M,
            club_id=1,
            created_by=10,
        )
        athlete_other_club = Athlete(
            id=145,
            user_id=1,
            first_name="Otro",
            last_name="Atleta",
            birth_date=date(2013, 6, 20),
            sex=Sex.M,
            club_id=2,
            created_by=1,
        )
        series_2026 = RaceSeries(
            id=1,
            name="Copa Valle de Ciclomontañismo",
            season_year=2026,
            organizer="Liga",
            points_scheme_code="copa_valle_2026",
        )
        event = RaceEvent(
            id=10,
            series_id=1,
            sequence_number=1,
            name="Sevilla",
            event_date=date(2026, 1, 31),
            location="Sevilla",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        event2 = RaceEvent(
            id=11,
            series_id=1,
            sequence_number=2,
            name="Ginebra",
            event_date=date(2026, 2, 28),
            location="Ginebra",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        cat = RaceCategory(
            id=100,
            code="INF_B",
            label="Infantil B",
            sex=CategoryGender.M,
            age_min=11,
            age_max=12,
            tier=CategoryTier.menores,
            sort_order=31,
            is_active=True,
        )
        comp_jd = RaceCompetitor(
            id=217,
            normalized_name="juan diego garcia bohorquez",
            display_name="Juan Diego Garcia Bohorquez",
            club_text="Club Trocha y Ruta",
            sex=CompetitorSex.M,
            athlete_id=None,
        )

        session.add_all(
            [
                club_tyr,
                club_other,
                admin,
                coach,
                parent,
                coach_membership,
                athlete,
                athlete_other_club,
                series_2026,
                event,
                event2,
                cat,
                comp_jd,
            ]
        )
        await session.commit()

        # 2 race_results activos para comp_jd
        results = [
            RaceResult(
                event_id=10,
                category_id=100,
                competitor_id=217,
                athlete_id=None,
                bib_number=100,
                position=1,
                status=ResultStatus.FINISHED,
                race_time_ms=1800000,
                points_awarded=40,
                created_by_user_id=10,
            ),
            RaceResult(
                event_id=11,
                category_id=100,
                competitor_id=217,
                athlete_id=None,
                bib_number=101,
                position=2,
                status=ResultStatus.FINISHED,
                race_time_ms=1810000,
                points_awarded=35,
                created_by_user_id=10,
            ),
        ]
        session.add_all(results)
        await session.commit()

    return {
        "athlete_id": 144,
        "athlete_other_club_id": 145,
        "coach_id": 10,
        "admin_id": 1,
        "parent_id": 20,
        "comp_jd_id": 217,
        "comp_nonexistent_id": 99_999,
        "athlete_nonexistent_id": 99_999,
        "tyr_club_id": 1,
        "other_club_id": 2,
    }


# ---------------------------------------------------------------------------
# Client fixtures por rol
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def coach_client(session_factory, seed_data):
    async def _override_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=10, coach_club_ids=[1]
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(session_factory, seed_data):
    async def _override_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.admin, user_id=1
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def parent_client(session_factory, seed_data):
    async def _override_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.parent, user_id=20
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client(session_factory):
    async def _override_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/race-competitors/  — listado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_unlinked_happy_coach(coach_client, seed_data):
    response = await coach_client.get("/api/race-competitors/?unlinked=true")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    ids = [item["id"] for item in body["items"]]
    assert seed_data["comp_jd_id"] in ids
    jd = next(item for item in body["items"] if item["id"] == seed_data["comp_jd_id"])
    assert jd["results_count"] == 2
    assert jd["seasons"] == [2026]
    assert jd["club_text"] == "Club Trocha y Ruta"
    # Sugerencias incluyen al athlete 144
    suggestion_ids = [s["athlete_id"] for s in jd["suggestions"]]
    assert seed_data["athlete_id"] in suggestion_ids


@pytest.mark.asyncio
async def test_list_unlinked_false_returns_400(coach_client):
    response = await coach_client.get("/api/race-competitors/?unlinked=false")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_unlinked_admin_ok(admin_client, seed_data):
    response = await admin_client.get("/api/race-competitors/?unlinked=true")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_unlinked_parent_forbidden(parent_client):
    response = await parent_client.get("/api/race-competitors/?unlinked=true")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_unlinked_anon_unauthorized(anon_client):
    response = await anon_client.get("/api/race-competitors/?unlinked=true")
    # FastAPI HTTPBearer devuelve 403 si no se manda Authorization;
    # algunas configuraciones devuelven 401. Aceptamos ambos.
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_unlinked_with_club_filter_trocha(coach_client, seed_data):
    response = await coach_client.get(
        "/api/race-competitors/?unlinked=true&club_filter=trocha"
    )
    assert response.status_code == 200
    body = response.json()
    # El único competitor (JD) ES de TyR → debe aparecer
    ids = [item["id"] for item in body["items"]]
    assert seed_data["comp_jd_id"] in ids


@pytest.mark.asyncio
async def test_list_unlinked_with_season_filter(coach_client, seed_data):
    response = await coach_client.get(
        "/api/race-competitors/?unlinked=true&season=2026"
    )
    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["items"]]
    assert seed_data["comp_jd_id"] in ids

    response2 = await coach_client.get(
        "/api/race-competitors/?unlinked=true&season=2025"
    )
    body2 = response2.json()
    # comp_jd no tiene results en 2025
    ids2 = [item["id"] for item in body2["items"]]
    assert seed_data["comp_jd_id"] not in ids2


@pytest.mark.asyncio
async def test_list_unlinked_include_suggestions_false(coach_client, seed_data):
    response = await coach_client.get(
        "/api/race-competitors/?unlinked=true&include_suggestions=false"
    )
    assert response.status_code == 200
    body = response.json()
    for item in body["items"]:
        assert item["suggestions"] == []


# ---------------------------------------------------------------------------
# GET /{id}/suggestions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggestions_happy(coach_client, seed_data):
    response = await coach_client.get(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/suggestions"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["competitor_id"] == seed_data["comp_jd_id"]
    assert len(body["suggestions"]) >= 1
    top = body["suggestions"][0]
    assert top["athlete_id"] == seed_data["athlete_id"]
    assert 0.0 <= top["score"] <= 1.0


@pytest.mark.asyncio
async def test_suggestions_nonexistent_returns_404(coach_client, seed_data):
    response = await coach_client.get(
        f"/api/race-competitors/{seed_data['comp_nonexistent_id']}/suggestions"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_suggestions_parent_forbidden(parent_client, seed_data):
    response = await parent_client.get(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/suggestions"
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /{id}/link
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_happy_propagates_results(
    coach_client, session_factory, seed_data
):
    response = await coach_client.post(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link",
        json={"athlete_id": seed_data["athlete_id"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["competitor_id"] == seed_data["comp_jd_id"]
    assert body["athlete_id"] == seed_data["athlete_id"]
    assert body["results_propagated"] == 2
    assert body["already_linked"] is False
    assert body["linked_by_user_id"] == seed_data["coach_id"]

    # Verifica en DB que los 2 race_results activos están propagados
    async with session_factory() as s:
        results = (
            await s.execute(
                select(RaceResult).where(
                    RaceResult.competitor_id == seed_data["comp_jd_id"],
                    RaceResult.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        assert all(r.athlete_id == seed_data["athlete_id"] for r in results)


@pytest.mark.asyncio
async def test_link_idempotent_same_athlete(coach_client, seed_data):
    # Primer link
    r1 = await coach_client.post(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link",
        json={"athlete_id": seed_data["athlete_id"]},
    )
    assert r1.status_code == 200
    # Re-link
    r2 = await coach_client.post(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link",
        json={"athlete_id": seed_data["athlete_id"]},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["already_linked"] is True
    assert body["results_propagated"] == 0


@pytest.mark.asyncio
async def test_link_to_different_athlete_returns_409(
    admin_client, seed_data
):
    """Admin: linkar a athlete 144, después intentar 145 → 409."""
    # Primer link a athlete_id=144
    r1 = await admin_client.post(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link",
        json={"athlete_id": seed_data["athlete_id"]},
    )
    assert r1.status_code == 200
    # Intentar a athlete_id=145 (otro club) → 409 (no 403, porque admin sí pasa RBAC)
    r2 = await admin_client.post(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link",
        json={"athlete_id": seed_data["athlete_other_club_id"]},
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_link_to_nonexistent_athlete_returns_404(
    admin_client, seed_data
):
    response = await admin_client.post(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link",
        json={"athlete_id": seed_data["athlete_nonexistent_id"]},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_link_competitor_nonexistent_returns_404(
    admin_client, seed_data
):
    response = await admin_client.post(
        f"/api/race-competitors/{seed_data['comp_nonexistent_id']}/link",
        json={"athlete_id": seed_data["athlete_id"]},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_link_coach_other_club_forbidden(coach_client, seed_data):
    """Coach del club 1 intenta linkar a athlete del club 2 → 403."""
    response = await coach_client.post(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link",
        json={"athlete_id": seed_data["athlete_other_club_id"]},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_link_parent_forbidden(parent_client, seed_data):
    response = await parent_client.post(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link",
        json={"athlete_id": seed_data["athlete_id"]},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_link_anon_unauthorized(anon_client, seed_data):
    response = await anon_client.post(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link",
        json={"athlete_id": seed_data["athlete_id"]},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_link_invalid_payload_returns_422(coach_client, seed_data):
    """Body sin athlete_id o con athlete_id <= 0 → 422 (validation)."""
    response = await coach_client.post(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link",
        json={"athlete_id": -1},
    )
    assert response.status_code == 422

    response2 = await coach_client.post(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link",
        json={},
    )
    assert response2.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /{id}/link
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unlink_happy_reverts_results(
    coach_client, session_factory, seed_data
):
    # Setup: linkar primero
    await coach_client.post(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link",
        json={"athlete_id": seed_data["athlete_id"]},
    )
    # Unlink
    response = await coach_client.delete(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["was_linked"] is True
    assert body["results_propagated"] == 2

    # Verifica en DB
    async with session_factory() as s:
        results = (
            await s.execute(
                select(RaceResult).where(
                    RaceResult.competitor_id == seed_data["comp_jd_id"],
                    RaceResult.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        assert all(r.athlete_id is None for r in results)


@pytest.mark.asyncio
async def test_unlink_already_unlinked_idempotent(coach_client, seed_data):
    """Unlink un competitor en NULL → 200 + was_linked=false."""
    response = await coach_client.delete(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["was_linked"] is False
    assert body["results_propagated"] == 0


@pytest.mark.asyncio
async def test_unlink_nonexistent_returns_404(coach_client, seed_data):
    response = await coach_client.delete(
        f"/api/race-competitors/{seed_data['comp_nonexistent_id']}/link"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unlink_parent_forbidden(parent_client, seed_data):
    response = await parent_client.delete(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link"
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unlink_coach_other_club_forbidden(
    coach_client, session_factory, seed_data
):
    """Coach del club 1 intenta unlink un competitor linkado a athlete del club 2 → 403.

    Seteamos el linkage directo en DB (bypaseando router) para no tener
    que combinar dos clientes con dependency-overrides en conflicto.
    """
    async with session_factory() as s:
        comp = (
            await s.execute(
                select(RaceCompetitor).where(
                    RaceCompetitor.id == seed_data["comp_jd_id"]
                )
            )
        ).scalar_one()
        comp.athlete_id = seed_data["athlete_other_club_id"]
        comp.linked_at = datetime.now(timezone.utc)
        comp.linked_by_user_id = seed_data["admin_id"]
        await s.commit()

    # Coach del club 1 intenta unlink → athlete actual está en club 2 → 403
    response = await coach_client.delete(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link"
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Listado: cuando el competitor ya fue linkeado, desaparece
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_excludes_competitor_after_link(coach_client, seed_data):
    # Pre-condición: aparece
    r0 = await coach_client.get("/api/race-competitors/?unlinked=true")
    ids0 = [item["id"] for item in r0.json()["items"]]
    assert seed_data["comp_jd_id"] in ids0

    # Linkar
    await coach_client.post(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link",
        json={"athlete_id": seed_data["athlete_id"]},
    )

    # Ya no debe aparecer en unlinked=true
    r1 = await coach_client.get("/api/race-competitors/?unlinked=true")
    ids1 = [item["id"] for item in r1.json()["items"]]
    assert seed_data["comp_jd_id"] not in ids1


# ---------------------------------------------------------------------------
# GET /api/race-competitors/suggestions-by-name  — Option B sugerencias INVERSAS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggestions_by_name_happy_coach(coach_client, seed_data):
    """Coach query: 'Juan Diego' + 'Garcia Bohorquez' → top match comp_jd."""
    response = await coach_client.get(
        "/api/race-competitors/suggestions-by-name",
        params={"first_name": "Juan Diego", "last_name": "Garcia Bohorquez"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "suggestions" in body
    assert len(body["suggestions"]) >= 1
    top = body["suggestions"][0]
    assert top["competitor_id"] == seed_data["comp_jd_id"]
    assert 0.0 <= top["score"] <= 1.0
    assert top["score"] >= 0.9
    assert top["results_count"] == 2  # seed router: 2 active results
    assert top["seasons"] == [2026]
    # club_text del seed
    assert top["club_text"] == "Club Trocha y Ruta"
    # reason no vacío
    assert top["reason"]


@pytest.mark.asyncio
async def test_suggestions_by_name_admin_ok(admin_client, seed_data):
    response = await admin_client.get(
        "/api/race-competitors/suggestions-by-name",
        params={"first_name": "Juan Diego", "last_name": "Garcia Bohorquez"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["suggestions"]) >= 1


@pytest.mark.asyncio
async def test_suggestions_by_name_parent_forbidden(parent_client):
    response = await parent_client.get(
        "/api/race-competitors/suggestions-by-name",
        params={"first_name": "Juan Diego", "last_name": "Garcia Bohorquez"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_suggestions_by_name_anon_unauthorized(anon_client):
    response = await anon_client.get(
        "/api/race-competitors/suggestions-by-name",
        params={"first_name": "Juan", "last_name": "Garcia"},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_suggestions_by_name_respects_limit(coach_client, seed_data):
    """``limit=1`` recorta al top-1."""
    response = await coach_client.get(
        "/api/race-competitors/suggestions-by-name",
        params={
            "first_name": "Juan Diego",
            "last_name": "Garcia Bohorquez",
            "limit": 1,
            "threshold": 0.0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["suggestions"]) <= 1


@pytest.mark.asyncio
async def test_suggestions_by_name_high_threshold_excludes_weak(
    coach_client, seed_data
):
    """``threshold=95`` excluye matches débiles (nombre que no existe)."""
    response = await coach_client.get(
        "/api/race-competitors/suggestions-by-name",
        params={
            "first_name": "Pedro",
            "last_name": "Perez",
            "threshold": 95.0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["suggestions"] == []


@pytest.mark.asyncio
async def test_suggestions_by_name_with_club_filter(coach_client, seed_data):
    """Pasar ``club=Trocha y Ruta`` no debe romper y mantiene el match top."""
    response = await coach_client.get(
        "/api/race-competitors/suggestions-by-name",
        params={
            "first_name": "Juan Diego",
            "last_name": "Garcia Bohorquez",
            "club": "Trocha y Ruta",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["suggestions"]) >= 1
    top = body["suggestions"][0]
    assert top["competitor_id"] == seed_data["comp_jd_id"]
    # Reason debe indicar boost por club
    assert "same club" in top["reason"]


@pytest.mark.asyncio
async def test_suggestions_by_name_missing_first_name_returns_422(coach_client):
    """``first_name`` ausente → 422."""
    response = await coach_client.get(
        "/api/race-competitors/suggestions-by-name",
        params={"last_name": "Garcia"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_suggestions_by_name_missing_last_name_returns_422(coach_client):
    """``last_name`` ausente → 422."""
    response = await coach_client.get(
        "/api/race-competitors/suggestions-by-name",
        params={"first_name": "Juan"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_suggestions_by_name_empty_first_name_returns_422(coach_client):
    """``first_name`` vacío (min_length=1) → 422."""
    response = await coach_client.get(
        "/api/race-competitors/suggestions-by-name",
        params={"first_name": "", "last_name": "Garcia"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_suggestions_by_name_threshold_out_of_range_returns_422(
    coach_client,
):
    """``threshold > 100`` → 422."""
    response = await coach_client.get(
        "/api/race-competitors/suggestions-by-name",
        params={
            "first_name": "Juan",
            "last_name": "Garcia",
            "threshold": 150.0,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_suggestions_by_name_excludes_linked_competitor(
    coach_client, seed_data
):
    """Tras linkar comp_jd, ya NO debe aparecer en suggestions-by-name."""
    # Linkar primero
    await coach_client.post(
        f"/api/race-competitors/{seed_data['comp_jd_id']}/link",
        json={"athlete_id": seed_data["athlete_id"]},
    )
    # Query inversa con el mismo nombre — no debe aparecer
    response = await coach_client.get(
        "/api/race-competitors/suggestions-by-name",
        params={"first_name": "Juan Diego", "last_name": "Garcia Bohorquez"},
    )
    assert response.status_code == 200
    body = response.json()
    ids = [s["competitor_id"] for s in body["suggestions"]]
    assert seed_data["comp_jd_id"] not in ids
