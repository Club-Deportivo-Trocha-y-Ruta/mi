"""Tests del router de bitácora para el portal de padres (feature 038, T202).

Cubre:
- Parent ve solo bitácoras de sus atletas vinculados (404 en atletas ajenos).
- Solo ``status == sent`` aparece en la lista/detalle.
- Coach/admin -> 403 en todas las rutas (exclusivas de rol parent).
- ``POST /{id}/read`` es idempotente y crea un ``newsletter_delivery_events``
  tipo ``web_read`` solo la primera vez.
- El DTO de padre (``ParentNewsletterOut.stage_log``) nunca contiene
  ``source_insight_id`` ni claves de antropometría/field-metrics — key-set
  explícito, a nivel HTTP.
- ``GET /api/parent-athletes/my-athletes`` cuenta ``unread_newsletters``
  correctamente.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, AsyncGenerator

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
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus
from app.models.newsletter_delivery_event import DeliveryEventType, NewsletterDeliveryEvent
from app.models.user import UserRole

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_user,
    link_parent_to_athlete,
    link_user_to_club,
)


# ---------------------------------------------------------------------------
# StageLog fixture mínimo (mismo patrón que test_stage_log.py)
# ---------------------------------------------------------------------------


def _stage_log_json(**overrides: Any) -> dict[str, Any]:
    from app.services.training.stage_log import (
        AnalystReading,
        BlockState,
        FamilyCompass,
        NextRace,
        NextSegment,
        Observation,
        StageLog,
        Summit,
        SummitKind,
        Waypoint,
        WaypointKind,
    )

    defaults: dict[str, Any] = {
        "stage_number": 3,
        "period_label": "Junio 2026",
        "is_current_month": False,
        "athlete_first_name": "Atleta",
        "athlete_reference": "su hijo",
        "stage_title": "Una etapa de constancia y aprendizaje sobre la bici",
        "trail": [
            Waypoint(
                kind=WaypointKind.RACE,
                date=date(2026, 6, 12),
                label="Válida 3 · P2",
                sublabel="+4,1 % al P1",
                icon="map-pin",
            ),
        ],
        "summit": Summit(
            kind=SummitKind.RACE,
            title="P2 en la Válida 3",
            detail="Copa Valle · Prejuvenil A Femenino",
            caption="Un gran resultado que refleja el trabajo del mes.",
            date=date(2026, 6, 12),
        ),
        "observations": [
            Observation(
                claim="Mantuvo un ritmo de entrenamiento constante.",
                evidence="Asistió a 12 de 14 sesiones (86 %).",
                block_ref="attendance",
            ),
        ],
        "analyst_reading": AnalystReading(
            headline_family="El trabajo en curvas está dando resultado.",
            action_family="Practicar frenado antes de las curvas cerradas.",
            valida_label="Válida 3 · Copa Valle",
            source_insight_id=42,
        ),
        "effort_profile": [],
        "next_segment": NextSegment(
            focus_groups=["Frenado modulado"],
            next_race=NextRace(label="Válida 4", date=date(2026, 7, 10), venue="Cali", priority_label="Prioridad A"),
            text="Las próximas semanas se enfocan en frenado.",
        ),
        "family_compass": FamilyCompass(
            conversation_question="¿Qué fue lo que más disfrutó en la bici este mes?",
            monthly_challenge="Proponle preparar la bici antes de cada sesión.",
            what_to_watch="Observen cómo mejora el frenado en curvas.",
        ),
        "badges": [],
        "photos": [],
        "coach_note": "Muy buen mes, sigue así.",
        "block_states": {"stage_title": BlockState.AI},
        "grounding_violations": [],
    }
    defaults.update(overrides)
    return StageLog(**defaults).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Engine + seeded factory + client
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
            "parent_athlete",
            "anthropometric_records",
            "athlete_monthly_newsletters",
            "newsletter_delivery_events",
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
async def seeded_factory(session_factory):
    """1 club, 1 coach, 1 admin, 1 padre, 2 atletas (uno vinculado, uno no).

    - athlete_id=144: vinculado al padre (user_id=200).
    - athlete_id=145: NO vinculado al padre (control de aislamiento).
    - newsletter_id=1: sent, con stage_log_json (bitácora visible).
    - newsletter_id=2: draft (no debe verse).
    - newsletter_id=3: sent, sin stage_log_json (bitácora aún no derivada,
      no debe verse).
    """
    async with session_factory() as s:
        await create_club(s, club_id=1, code="club1")
        await create_user(s, user_id=10, role=UserRole.coach)
        await link_user_to_club(s, user_id=10, club_id=1)
        await create_user(s, user_id=11, role=UserRole.admin)
        await create_user(s, user_id=200, role=UserRole.parent, email="padre@test.com")

        await create_user(s, user_id=144, role=UserRole.athlete, can_login=False)
        await create_athlete(s, athlete_id=144, club_id=1, user_id=144)
        await create_user(s, user_id=145, role=UserRole.athlete, can_login=False)
        await create_athlete(s, athlete_id=145, club_id=1, user_id=145, first_name="Otro")

        await link_parent_to_athlete(s, parent_user_id=200, athlete_id=144)

        now = datetime.now(timezone.utc)

        nl_sent = AthleteMonthlyNewsletter(
            id=1,
            athlete_id=144,
            year=2026,
            month=6,
            status=NewsletterStatus.sent,
            stage_log_json=_stage_log_json(),
            hidden_blocks=None,
            metrics_snapshot={"email_blocks": {}, "pdf_only_blocks": {}},
            sent_at=now,
            generated_by_user_id=10,
        )
        s.add(nl_sent)

        nl_draft = AthleteMonthlyNewsletter(
            id=2,
            athlete_id=144,
            year=2026,
            month=7,
            status=NewsletterStatus.draft,
            stage_log_json=_stage_log_json(stage_title="Etapa en progreso, aún no enviada"),
            generated_by_user_id=10,
        )
        s.add(nl_draft)

        nl_sent_without_stage_log = AthleteMonthlyNewsletter(
            id=3,
            athlete_id=144,
            year=2026,
            month=5,
            status=NewsletterStatus.sent,
            stage_log_json=None,
            metrics_snapshot={"email_blocks": {}, "pdf_only_blocks": {}},
            sent_at=now,
            generated_by_user_id=10,
        )
        s.add(nl_sent_without_stage_log)

        # Boletín sent de un atleta NO vinculado al padre — control de 404.
        nl_other_athlete = AthleteMonthlyNewsletter(
            id=4,
            athlete_id=145,
            year=2026,
            month=6,
            status=NewsletterStatus.sent,
            stage_log_json=_stage_log_json(),
            metrics_snapshot={"email_blocks": {}, "pdf_only_blocks": {}},
            sent_at=now,
            generated_by_user_id=10,
        )
        s.add(nl_other_athlete)

        await s.commit()
    return session_factory


def _parent_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=200,
        first_name="Padre",
        last_name="Test",
        email="padre@test.com",
        role=UserRole.parent,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


def _coach_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=10,
        first_name="Coach",
        last_name="Test",
        email="coach@test.com",
        role=UserRole.coach,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


def _admin_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=11,
        first_name="Admin",
        last_name="Test",
        email="admin@test.com",
        role=UserRole.admin,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


@pytest_asyncio.fixture
async def _client_factory(seeded_factory):
    async def _override_db():
        async with seeded_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async def _make(user: SimpleNamespace) -> AsyncClient:
        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: user
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    yield _make
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def parent_client(_client_factory):
    async with await _client_factory(_parent_user()) as c:
        yield c


@pytest_asyncio.fixture
async def coach_client(_client_factory):
    async with await _client_factory(_coach_user()) as c:
        yield c


@pytest_asyncio.fixture
async def admin_client(_client_factory):
    async with await _client_factory(_admin_user()) as c:
        yield c


# ---------------------------------------------------------------------------
# GET / — lista
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_only_shows_sent_bitacora(parent_client):
    resp = await parent_client.get("/api/parents/me/athletes/144/newsletters")
    assert resp.status_code == 200
    body = resp.json()
    ids = {item["id"] for item in body}
    # Solo id=1 (sent + stage_log_json). id=2 (draft) e id=3 (sent sin
    # stage_log_json) quedan fuera.
    assert ids == {1}
    assert body[0]["period_label"] == "Junio 2026"
    assert body[0]["stage_title"] == "Una etapa de constancia y aprendizaje sobre la bici"


@pytest.mark.asyncio
async def test_list_unlinked_athlete_returns_404(parent_client):
    resp = await parent_client.get("/api/parents/me/athletes/145/newsletters")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_coach_forbidden(coach_client):
    resp = await coach_client.get("/api/parents/me/athletes/144/newsletters")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_admin_forbidden(admin_client):
    resp = await admin_client.get("/api/parents/me/athletes/144/newsletters")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /{id} — detalle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detail_sent_bitacora_ok(parent_client):
    resp = await parent_client.get("/api/parents/me/athletes/144/newsletters/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 1
    assert body["athlete_id"] == 144
    assert body["has_pdf"] is False
    assert body["stage_log"]["stage_title"]


@pytest.mark.asyncio
async def test_detail_draft_returns_404(parent_client):
    resp = await parent_client.get("/api/parents/me/athletes/144/newsletters/2")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_detail_without_stage_log_returns_404(parent_client):
    """Un boletín sent sin stage_log_json aún no es una bitácora visible."""
    resp = await parent_client.get("/api/parents/me/athletes/144/newsletters/3")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_detail_other_athlete_returns_404(parent_client):
    """Boletín existe (sent) pero pertenece a un atleta no vinculado → 404."""
    resp = await parent_client.get("/api/parents/me/athletes/145/newsletters/4")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_detail_coach_forbidden(coach_client):
    resp = await coach_client.get("/api/parents/me/athletes/144/newsletters/1")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_detail_stage_log_key_set_never_leaks_coach_only_fields(parent_client):
    """stage_log del padre NUNCA trae source_insight_id / block_states /
    grounding_violations / claves de antropometría o field-metrics."""
    resp = await parent_client.get("/api/parents/me/athletes/144/newsletters/1")
    assert resp.status_code == 200
    stage_log = resp.json()["stage_log"]

    expected_keys = {
        "schema_version",
        "stage_number",
        "period_label",
        "is_current_month",
        "athlete_first_name",
        "athlete_reference",
        "stage_title",
        "trail",
        "summit",
        "observations",
        "analyst_reading",
        "effort_profile",
        "next_segment",
        "family_compass",
        "badges",
        "photos",
        "coach_note",
    }
    assert set(stage_log.keys()) == expected_keys
    assert "block_states" not in stage_log
    assert "grounding_violations" not in stage_log

    analyst_reading = stage_log["analyst_reading"]
    assert set(analyst_reading.keys()) == {
        "headline_family",
        "action_family",
        "valida_label",
    }
    assert "source_insight_id" not in analyst_reading

    forbidden_substrings = (
        "source_insight_id",
        "standing_height_cm",
        "weight_kg",
        "maturation_status",
        "anthropometry",
        "field_metrics",
    )
    payload_str = str(stage_log)
    for token in forbidden_substrings:
        assert token not in payload_str


# ---------------------------------------------------------------------------
# POST /{id}/read — idempotente
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_idempotent_and_creates_web_read_event(seeded_factory, _client_factory):
    async with await _client_factory(_parent_user()) as client:
        resp1 = await client.post("/api/parents/me/athletes/144/newsletters/1/read")
        assert resp1.status_code == 204

        resp2 = await client.post("/api/parents/me/athletes/144/newsletters/1/read")
        assert resp2.status_code == 204

    async with seeded_factory() as s:
        result = await s.execute(
            select(AthleteMonthlyNewsletter).where(AthleteMonthlyNewsletter.id == 1)
        )
        nl = result.scalar_one()
        assert nl.read_at is not None
        assert nl.read_by_user_id == 200
        first_read_at = nl.read_at

        events_result = await s.execute(
            select(NewsletterDeliveryEvent).where(
                NewsletterDeliveryEvent.newsletter_id == 1,
                NewsletterDeliveryEvent.event_type == DeliveryEventType.web_read,
            )
        )
        events = events_result.scalars().all()
        assert len(events) == 1
        assert events[0].parent_user_id == 200

    # Segunda llamada no debe mover read_at ni duplicar el evento.
    async with await _client_factory(_parent_user()) as client:
        resp3 = await client.post("/api/parents/me/athletes/144/newsletters/1/read")
        assert resp3.status_code == 204

    async with seeded_factory() as s:
        result = await s.execute(
            select(AthleteMonthlyNewsletter).where(AthleteMonthlyNewsletter.id == 1)
        )
        nl = result.scalar_one()
        assert nl.read_at == first_read_at

        events_result = await s.execute(
            select(NewsletterDeliveryEvent).where(
                NewsletterDeliveryEvent.newsletter_id == 1,
                NewsletterDeliveryEvent.event_type == DeliveryEventType.web_read,
            )
        )
        assert len(events_result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_read_coach_forbidden(coach_client):
    resp = await coach_client.post("/api/parents/me/athletes/144/newsletters/1/read")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_read_unlinked_athlete_404(parent_client):
    resp = await parent_client.post("/api/parents/me/athletes/145/newsletters/4/read")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/parent-athletes/my-athletes — unread_newsletters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_my_athletes_unread_count(seeded_factory, _client_factory):
    async with await _client_factory(_parent_user()) as client:
        resp = await client.get("/api/parent-athletes/my-athletes")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        # id=1 (sent, sin leer) e id=3 (sent sin stage_log_json, sin leer)
        # cuentan ambas — el contrato de unread_newsletters (data-model.md
        # §5) es "sent and read_at is null", sin filtrar por stage_log_json.
        assert body[0]["unread_newsletters"] == 2

        read_resp = await client.post("/api/parents/me/athletes/144/newsletters/1/read")
        assert read_resp.status_code == 204

    async with await _client_factory(_parent_user()) as client:
        resp2 = await client.get("/api/parent-athletes/my-athletes")
        assert resp2.json()[0]["unread_newsletters"] == 1
