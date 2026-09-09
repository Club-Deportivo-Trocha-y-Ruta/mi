"""Cobertura de auditoría (feature 041, T022 / T027 parte-atletas).

`contracts/audit-recording.md` §4.3, §4.4 y §4.9. Cubre, sobre SQLite
in-memory (mismo patrón que ``tests/routers/test_athlete_race_analysis_answer.py``):

- `POST /api/athletes` → `athlete`·`create`.
- `PATCH /api/athletes/{id}` → `athlete`·`update` con `changed_fields`.
- `DELETE /api/athletes/{id}` → `athlete`·`delete` (admin-only hoy; ver
  blockers del reporte de T022 sobre el rediseño a `archive`).
- `POST /api/athletes/{id}/anthropometry` → `anthropometric_record`·`create`.
- `POST /api/me/consent/renew` → `parental_consent`·`create` (+ `update` de
  la fila supersedida cuando existe una previa).
- `POST /api/me/consent/withdraw` → `parental_consent`·`update`.
- `POST /api/athletes/{id}/race-analysis/insights/{insight_id}/answer` →
  `athlete_ai_insight`·`update` con `changed_fields` que incluye
  `coach_answer_by_user_id`.

Ningún nombre corresponde a una persona real (CLAUDE.md, Ley 1581).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool


# ``ParentalConsent.policy`` es ``lazy="joined"`` — crear ``parental_consents``
# arrastra ``privacy_policies``, cuya ``content_html`` es MySQL ``LONGTEXT``
# (SQLite no tiene compilador). Shim estándar de SQLAlchemy, igual que
# ``tests/routers/test_strava_integration.py``; solo afecta el DDL de este
# engine in-memory, no cambia código de producto.
@compiles(LONGTEXT, "sqlite")
def _compile_longtext_as_text_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "TEXT"

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.audit_log import AuditLog
from app.models.club import ClubRole
from app.models.privacy_policy import PrivacyPolicy
from app.models.user import UserRole

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
    create_user,
    link_parent_to_athlete,
    link_user_to_club,
)
from tests.helpers.audit_tables import AUDIT_TABLES

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "anthropometric_records",
    "privacy_policies",
    "parental_consents",
    "athlete_ai_insights",
    "athlete_ai_explanations",
    "parent_invites",
    *AUDIT_TABLES,
)


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded_factory(session_factory) -> async_sessionmaker[AsyncSession]:
    """club1 + admin + coach(club1) + parent + atleta 144, más una política
    de privacidad vigente y un insight de IA aprobado para el atleta 144."""
    async with session_factory() as s:
        await create_club(s, club_id=1, code="club1")
        await create_user(s, user_id=900, role=UserRole.admin, email="admin@test.com")
        await link_user_to_club(s, user_id=900, club_id=1, role_in_club=ClubRole.admin)
        await create_user(s, user_id=10, role=UserRole.coach, email="coach1@test.com")
        await link_user_to_club(s, user_id=10, club_id=1, role_in_club=ClubRole.coach)
        await create_user(s, user_id=20, role=UserRole.parent, email="parent@test.com")

        await create_user(
            s,
            user_id=144,
            role=UserRole.athlete,
            can_login=False,
            first_name="Deportista",
            last_name="Ficticio",
        )
        await create_athlete(
            s,
            athlete_id=144,
            club_id=1,
            user_id=144,
            first_name="Deportista",
            last_name="Ficticio",
        )
        await link_parent_to_athlete(s, parent_user_id=20, athlete_id=144)

        s.add(
            PrivacyPolicy(
                id=1,
                version="v1.0",
                effective_date=date(2026, 1, 1),
                title="Política de prueba",
                content_html="<p>contenido</p>",
                content_hash="0" * 64,
            )
        )

        now = datetime.now(timezone.utc)
        insight = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=1,
            coach_approved=True,
            is_active=1,
            generated_at=now,
        )
        await s.commit()
        s._test_insight_id = insight.id  # type: ignore[attr-defined]
    return session_factory


def _make_user(user_id: int, role: UserRole, club_id: int | None = 1) -> SimpleNamespace:
    cm = (
        SimpleNamespace(
            club_id=club_id,
            role_in_club=(
                ClubRole.coach
                if role == UserRole.coach
                else ClubRole.admin
                if role == UserRole.admin
                else ClubRole.parent
            ),
        )
        if club_id is not None
        else None
    )
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"u{user_id}@test.com",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[cm] if cm else [],
    )


@pytest_asyncio.fixture
async def client_factory(seeded_factory):
    def _build(user: SimpleNamespace):
        async def _override_db():
            async with seeded_factory() as s:
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: user
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    yield _build
    app.dependency_overrides.clear()


async def _last_audit_row(
    session_factory, *, entity_type: str, action: str
) -> AuditLog | None:
    async with session_factory() as s:
        result = await s.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type, AuditLog.action == action)
            .order_by(AuditLog.id.desc())
        )
        return result.scalars().first()


async def _get_insight_id(session_factory, athlete_id: int) -> int:
    async with session_factory() as s:
        from app.models.athlete_ai_insight import AthleteAiInsight

        result = await s.execute(
            select(AthleteAiInsight.id).where(AthleteAiInsight.athlete_id == athlete_id)
        )
        return int(result.scalars().first())


# ---------------------------------------------------------------------------
# T022 — atleta: crear / actualizar / borrar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_athlete_records_audit_row(client_factory, seeded_factory):
    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            "/api/athletes",
            json={
                "first_name": "Nuevo",
                "last_name": "Deportista",
                "birth_date": "2013-05-10",
                "sex": "M",
                "club_id": 1,
            },
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 201
    new_athlete_id = resp.json()["id"]

    row = await _last_audit_row(seeded_factory, entity_type="athlete", action="create")
    assert row is not None
    assert row.entity_id == new_athlete_id
    assert row.athlete_id == new_athlete_id
    assert row.club_id == 1
    assert row.actor_user_id == 10


@pytest.mark.asyncio
async def test_update_athlete_records_changed_fields_names_only(
    client_factory, seeded_factory
):
    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.patch(
            "/api/athletes/144",
            json={"first_name": "Actualizado"},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200

    row = await _last_audit_row(seeded_factory, entity_type="athlete", action="update")
    assert row is not None
    assert row.entity_id == 144
    assert row.athlete_id == 144
    assert row.changed_fields == ["first_name"]
    # first_name no está en VALUE_ALLOWLIST[athlete] — nunca debe viajar el valor.
    assert row.diff_json is None


@pytest.mark.asyncio
async def test_delete_athlete_as_admin_records_audit_row(client_factory, seeded_factory):
    admin = _make_user(900, UserRole.admin, club_id=1)
    async with client_factory(user=admin) as ac:
        resp = await ac.delete(
            "/api/athletes/144",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 204

    row = await _last_audit_row(seeded_factory, entity_type="athlete", action="delete")
    assert row is not None
    assert row.entity_id == 144
    assert row.athlete_id == 144
    assert row.actor_user_id == 900


@pytest.mark.asyncio
async def test_delete_athlete_as_coach_is_forbidden_no_audit_row(
    client_factory, seeded_factory
):
    """Guard interino (T002): coach no puede borrar — no debe quedar fila."""
    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.delete(
            "/api/athletes/144",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 403

    row = await _last_audit_row(seeded_factory, entity_type="athlete", action="delete")
    assert row is None


# ---------------------------------------------------------------------------
# T022 — antropometría (§4.3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_anthropometry_records_audit_row(client_factory, seeded_factory):
    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            "/api/athletes/144/anthropometry",
            json={
                "evaluation_date": "2026-06-01",
                "weight_kg": "45.5",
                "standing_height_cm": "150.0",
                "sitting_height_cm": "78.0",
            },
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 201
    record_id = resp.json()["id"]

    row = await _last_audit_row(
        seeded_factory, entity_type="anthropometric_record", action="create"
    )
    assert row is not None
    assert row.entity_id == record_id
    assert row.athlete_id == 144
    assert row.club_id == 1


# ---------------------------------------------------------------------------
# T022 — consentimiento (§4.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consent_renew_records_create_row(client_factory, seeded_factory):
    parent = _make_user(20, UserRole.parent, club_id=None)
    async with client_factory(user=parent) as ac:
        resp = await ac.post(
            "/api/me/consent/renew",
            json={
                "athlete_id": 144,
                "policy_version": "v1.0",
                "accept_data_collection": True,
                "accept_anthropometry": True,
            },
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 201
    consent_id = resp.json()["id"]

    row = await _last_audit_row(
        seeded_factory, entity_type="parental_consent", action="create"
    )
    assert row is not None
    assert row.entity_id == consent_id
    assert row.athlete_id == 144
    assert row.actor_user_id == 20
    assert row.actor_role == UserRole.parent.value


@pytest.mark.asyncio
async def test_consent_renew_supersedes_previous_records_update_row(
    client_factory, seeded_factory
):
    parent = _make_user(20, UserRole.parent, club_id=None)
    body = {
        "athlete_id": 144,
        "policy_version": "v1.0",
        "accept_data_collection": True,
        "accept_anthropometry": True,
    }
    async with client_factory(user=parent) as ac:
        first = await ac.post(
            "/api/me/consent/renew", json=body, headers={"Authorization": "Bearer fake"}
        )
        assert first.status_code == 201
        previous_id = first.json()["id"]

        second = await ac.post(
            "/api/me/consent/renew", json=body, headers={"Authorization": "Bearer fake"}
        )
        assert second.status_code == 201

    row = await _last_audit_row(
        seeded_factory, entity_type="parental_consent", action="update"
    )
    assert row is not None
    assert row.entity_id == previous_id
    assert row.changed_fields == ["withdrawal_reason", "withdrawn_at"]


@pytest.mark.asyncio
async def test_consent_withdraw_records_update_row(client_factory, seeded_factory):
    parent = _make_user(20, UserRole.parent, club_id=None)
    async with client_factory(user=parent) as ac:
        renew_resp = await ac.post(
            "/api/me/consent/renew",
            json={
                "athlete_id": 144,
                "policy_version": "v1.0",
                "accept_data_collection": True,
                "accept_anthropometry": True,
            },
            headers={"Authorization": "Bearer fake"},
        )
        consent_id = renew_resp.json()["id"]

        resp = await ac.post(
            "/api/me/consent/withdraw",
            json={"athlete_id": 144, "reason": "ya no participa"},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200

    row = await _last_audit_row(
        seeded_factory, entity_type="parental_consent", action="update"
    )
    assert row is not None
    assert row.entity_id == consent_id
    assert row.changed_fields == ["withdrawal_reason", "withdrawn_at"]
    assert row.diff_json is None


# ---------------------------------------------------------------------------
# T027 (parte atletas) — responder un insight de IA (§4.9)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_answer_insight_records_audit_row_with_actor_column(
    client_factory, seeded_factory
):
    insight_id = await _get_insight_id(seeded_factory, 144)
    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            f"/api/athletes/144/race-analysis/insights/{insight_id}/answer",
            json={"answer_text": "Respuesta del coach.", "rating": 1},
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200

    row = await _last_audit_row(
        seeded_factory, entity_type="athlete_ai_insight", action="update"
    )
    assert row is not None
    assert row.entity_id == insight_id
    assert row.athlete_id == 144
    assert row.club_id == 1
    assert set(row.changed_fields) == {
        "coach_answer_text",
        "coach_answer_at",
        "coach_answer_by_user_id",
        "coach_rating",
    }
    # coach_answer_text no está en VALUE_ALLOWLIST[athlete_ai_insight] —
    # nunca debe viajar el valor (Ley 1581).
    assert row.diff_json is None
