"""Tests del router para `/api/ai/athletes/{id}/measurements/{rid}/explanation`.

Cubre:
  - 451 cuando falta consentimiento third_party_sharing.
  - 403 padre intentando POST.
  - 200 lectura del caché (coach y padre).
  - 200 generación happy path (coach).
  - 422 cuando la medición no pertenece al atleta (404 técnicamente).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.dependencies import (
    get_current_user,
    get_db,
    get_llm_provider,
    verify_athlete_access,
)
from app.main import app
from app.models.anthropometry import MaturationStatus
from app.models.athlete import Sex
from app.models.user import UserRole
from app.services.ai.providers.fake import FakeLLMProvider


def _coach_user():
    return SimpleNamespace(
        id=2, first_name="Coach", last_name="Test", email="coach@test",
        role=UserRole.coach, can_login=True, is_active=True, club_memberships=[],
    )


def _parent_user():
    return SimpleNamespace(
        id=3, first_name="Padre", last_name="Test", email="parent@test",
        role=UserRole.parent, can_login=True, is_active=True, club_memberships=[],
    )


def _athlete():
    return SimpleNamespace(
        id=42, first_name="Atleta", last_name="Demo",
        birth_date=date(2014, 6, 15), sex=Sex.M, user_id=99, club_id=1,
    )


def _record(rid: int = 10, eval_date: date = date(2026, 4, 1), height="150.0", weight="40.0"):
    return SimpleNamespace(
        id=rid, athlete_id=42,
        evaluation_date=eval_date,
        weight_kg=Decimal(weight),
        standing_height_cm=Decimal(height),
        arm_span_cm=Decimal("152.0"),
        sitting_height_cm=Decimal("75.0"),
        leg_length_cm=Decimal("75.0"),
        leg_sitting_ratio=Decimal("1.0"),
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


def _cached(record_id: int, text="texto cacheado"):
    return SimpleNamespace(
        id=99, athlete_id=42, anthropometric_record_id=record_id,
        use_case="anthropometric_record_analysis",
        text=text, model="cached-model", provider="anthropic",
        generated_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        age_group="10-12", maturation_status="Pre-PHV",
        generated_by_user_id=2,
    )


class _ScalarResult:
    def __init__(self, *, scalar=None, items=None):
        self._scalar = scalar
        self._items = items if items is not None else []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._items


class _QueueSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.executed: list = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        if not self._responses:
            return _ScalarResult()
        return self._responses.pop(0)


@pytest.fixture
def fastapi_app():
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def http_client(fastapi_app):
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def allow_consent(monkeypatch):
    async def _allow(_athlete_id, _db):
        return True
    monkeypatch.setattr("app.routers.ai.athlete_has_ai_processing_consent", _allow)


@pytest.fixture
def deny_consent(monkeypatch):
    async def _deny(_athlete_id, _db):
        return False
    monkeypatch.setattr("app.routers.ai.athlete_has_ai_processing_consent", _deny)


# ---------------------------------------------------------------------------
# POST measurement explanation
# ---------------------------------------------------------------------------


class TestPostMeasurementExplanation:
    async def test_consent_missing_returns_451(
        self, http_client, monkeypatch, deny_consent
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(canned="x")
        app.dependency_overrides[get_db] = lambda: _QueueSession([])

        resp = await http_client.post(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 451
        assert "consentimiento" in resp.json()["detail"].lower()

    async def test_parent_forbidden(self, http_client, monkeypatch, allow_consent):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _QueueSession([])

        resp = await http_client.post(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 403

    async def test_disabled_returns_503(
        self, http_client, monkeypatch, allow_consent
    ):
        monkeypatch.setattr(settings, "ai_enabled", False)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _QueueSession([])

        resp = await http_client.post(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 503

    async def test_record_not_found_returns_404(
        self, http_client, monkeypatch, allow_consent
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(canned="x")
        # 1. get_record_or_404 → scalar=None → 404
        session = _QueueSession([_ScalarResult(scalar=None)])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post(
            "/api/ai/athletes/42/measurements/999/explanation"
        )
        assert resp.status_code == 404

    async def test_happy_path_first_measurement(
        self, http_client, monkeypatch, allow_consent
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        monkeypatch.setattr(settings, "ai_provider", "fake")
        monkeypatch.setattr(settings, "ai_model", "fake-model")
        target = _record(rid=10, eval_date=date(2026, 4, 1))
        fake = FakeLLMProvider(
            canned="Esta es la primera medición de su hijo.", model="fake-model"
        )
        app.dependency_overrides[get_llm_provider] = lambda: fake
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        # 1: get_record_or_404 returns target
        # 2: priors query returns []
        # 3: upsert (no result needed)
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(items=[]),
            _ScalarResult(),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["record_id"] == 10
        assert body["num_previous_measurements"] == 0
        assert body["delta_height_cm"] is None
        assert body["delta_weight_kg"] is None
        assert body["age_group"] == "10-12"

    async def test_happy_path_with_history(
        self, http_client, monkeypatch, allow_consent
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        target = _record(rid=20, eval_date=date(2026, 4, 1), height="153.0", weight="42.5")
        prior = _record(rid=10, eval_date=date(2026, 1, 1), height="150.0", weight="40.0")
        fake = FakeLLMProvider(canned="Su hijo creció en este periodo.")
        app.dependency_overrides[get_llm_provider] = lambda: fake
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(items=[prior]),
            _ScalarResult(),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post(
            "/api/ai/athletes/42/measurements/20/explanation"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["record_id"] == 20
        assert body["num_previous_measurements"] == 1
        assert body["delta_height_cm"] == 3.0
        assert body["delta_weight_kg"] == 2.5

    async def test_guardrail_violation_returns_502(
        self, http_client, monkeypatch, allow_consent
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        target = _record(rid=10)
        canned = (
            "Su hijo tiene patología, diagnóstico de retraso puberal, "
            "déficit energético y RED-S, lo cual es anormal."
        )
        fake = FakeLLMProvider(canned=canned)
        app.dependency_overrides[get_llm_provider] = lambda: fake
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# GET measurement explanation (cache)
# ---------------------------------------------------------------------------


class TestGetMeasurementExplanationCached:
    async def test_record_not_found_returns_404(self, http_client, monkeypatch):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        session = _QueueSession([_ScalarResult(scalar=None)])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/999/explanation"
        )
        assert resp.status_code == 404

    async def test_cache_miss_returns_204(self, http_client, monkeypatch):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        session = _QueueSession([
            _ScalarResult(scalar=_record(rid=10)),  # record exists
            _ScalarResult(scalar=None),             # no cache
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 204
        assert resp.content == b""

    async def test_cache_hit_returns_payload(self, http_client, monkeypatch):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10, eval_date=date(2026, 4, 1), height="153.0", weight="42.5")
        prior = _record(rid=5, eval_date=date(2026, 1, 1), height="150.0", weight="40.0")
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(scalar=_cached(record_id=10, text="hola padres")),
            _ScalarResult(items=[prior]),  # _delta_summary query
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["text"] == "hola padres"
        assert body["record_id"] == 10
        assert body["num_previous_measurements"] == 1
        assert body["delta_height_cm"] == 3.0
        assert body["delta_weight_kg"] == 2.5

    async def test_parent_can_read_cache(self, http_client, monkeypatch):
        """Padres con ownership ven el caché (sin botón generar en el front)."""
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(scalar=_cached(record_id=10)),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 200
        body = resp.json()
        # El padre no ve quién lo generó
        assert "generated_by_user_id" not in body


# ---------------------------------------------------------------------------
# Gate de consentimiento sobre el endpoint PHV existente
# ---------------------------------------------------------------------------


class TestPHVConsentGate:
    """El POST PHV existente ahora también verifica consentimiento."""

    async def test_phv_consent_missing_returns_451(
        self, http_client, monkeypatch, deny_consent
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(canned="x")
        app.dependency_overrides[get_db] = lambda: _QueueSession([])

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 451
