"""Tests del router `/api/ai/*` sin tocar MySQL.

Sobrescribimos las dependencias (`get_current_user`, `verify_athlete_access`,
`get_db`, `get_llm_provider`) para validar el comportamiento del router en
forma aislada. Los tests de integración real siguen el patrón del resto del
proyecto y requieren Docker compose con MySQL (no se incluyen aquí).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.dependencies import (
    get_current_user,
    get_db,
    get_llm_provider,
    require_role,
    verify_athlete_access,
)
from app.main import app
from app.models.anthropometry import MaturationStatus
from app.models.athlete import Sex
from app.models.user import UserRole
from app.services.ai.providers.fake import FakeLLMProvider


def _admin_user():
    return SimpleNamespace(
        id=1,
        first_name="Admin",
        last_name="Test",
        email="admin@test",
        role=UserRole.admin,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


def _coach_user():
    return SimpleNamespace(
        id=2,
        first_name="Coach",
        last_name="Test",
        email="coach@test",
        role=UserRole.coach,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


def _athlete():
    return SimpleNamespace(
        id=42,
        first_name="Atleta",
        last_name="Demo",
        birth_date=date(2014, 6, 15),
        sex=Sex.M,
        user_id=99,
        club_id=1,
    )


def _record():
    return SimpleNamespace(
        id=1,
        athlete_id=42,
        evaluation_date=date(2026, 4, 1),
        mesocycle=2,
        weight_kg=Decimal("40.0"),
        standing_height_cm=Decimal("150.0"),
        sitting_height_cm=Decimal("75.0"),
        leg_length_cm=Decimal("75.0"),
        maturity_offset=Decimal("-1.5"),
        age_at_phv=Decimal("13.5"),
        maturation_status=MaturationStatus.pre_phv,
        training_implications="Habilidades, juego.",
        height_z_score=Decimal("0.4"),
        bmi=Decimal("17.8"),
        bmi_z_score=Decimal("0.1"),
        weight_z_score=Decimal("0.2"),
        height_percentile=None,
        bmi_percentile=None,
        weight_percentile=None,
        nutritional_status=None,
    )


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _FakeSession:
    """Stub mínimo de AsyncSession — solo soporta `.execute(...)`."""

    def __init__(self, records):
        self._records = records

    async def execute(self, _stmt):
        return _FakeResult(self._records)


@pytest.fixture
def fastapi_app():
    """Aplica overrides genéricos y limpia al final."""
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def http_client(fastapi_app):
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# /api/ai/health
# ---------------------------------------------------------------------------


class TestAIHealth:
    async def test_admin_returns_state(self, http_client, monkeypatch):
        monkeypatch.setattr(settings, "ai_enabled", True)
        monkeypatch.setattr(settings, "ai_provider", "fake")
        monkeypatch.setattr(settings, "ai_model", "test-model")
        app.dependency_overrides[get_current_user] = _admin_user
        # require_role([admin]) construye su propio dependency interno.
        # Lo más simple: override require_role no aplica directo; el flow real
        # llama get_current_user → require_role chequea role. Como admin,
        # pasa.
        resp = await http_client.get("/api/ai/health")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["enabled"] is True
        assert body["provider"] == "fake"
        assert body["model"] == "test-model"

    async def test_coach_forbidden(self, http_client):
        app.dependency_overrides[get_current_user] = _coach_user
        resp = await http_client.get("/api/ai/health")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# /api/ai/athletes/{id}/phv-explanation
# ---------------------------------------------------------------------------


class TestPHVExplanation:
    async def test_disabled_returns_503(self, http_client, monkeypatch):
        monkeypatch.setattr(settings, "ai_enabled", False)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _FakeSession([_record()])
        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 503

    async def test_no_records_returns_422(self, http_client, monkeypatch):
        monkeypatch.setattr(settings, "ai_enabled", True)
        fake = FakeLLMProvider(canned="ok")
        app.dependency_overrides[get_llm_provider] = lambda: fake
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _FakeSession([])
        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 422

    async def test_happy_path(self, http_client, monkeypatch):
        monkeypatch.setattr(settings, "ai_enabled", True)
        monkeypatch.setattr(settings, "ai_provider", "fake")
        monkeypatch.setattr(settings, "ai_model", "fake-model")
        canned = (
            "Su hijo está en Pre-PHV. Priorizamos juego, técnica y descanso."
        )
        fake = FakeLLMProvider(canned=canned, model="fake-model")
        app.dependency_overrides[get_llm_provider] = lambda: fake
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _FakeSession([_record()])

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["text"] == canned
        assert body["provider"] == "fake"
        assert body["age_group"] == "10-12"
        assert body["maturation_status"] == "Pre-PHV"

    async def test_provider_unavailable_returns_503(
        self, http_client, monkeypatch
    ):
        from app.services.ai.errors import LLMUnavailableError

        class BoomProvider(FakeLLMProvider):
            async def complete(self, req):
                raise LLMUnavailableError("backend caído")

        monkeypatch.setattr(settings, "ai_enabled", True)
        provider = BoomProvider()
        app.dependency_overrides[get_llm_provider] = lambda: provider
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _FakeSession([_record()])

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 503

    async def test_guardrail_violation_returns_502(
        self, http_client, monkeypatch
    ):
        canned = (
            "Tome creatina, entrene 6 días por semana, "
            "pedalee a 50 rpm para fortalecerse."
        )
        monkeypatch.setattr(settings, "ai_enabled", True)
        fake = FakeLLMProvider(canned=canned)
        app.dependency_overrides[get_llm_provider] = lambda: fake
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _FakeSession([_record()])

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 502
