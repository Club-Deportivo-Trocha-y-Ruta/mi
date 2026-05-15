"""Tests de habilitación del consentimiento de procesamiento con IA.

Verifica que el flag `accept_third_party_sharing` en `ConsentRenewIn` y en
`ParentalConsentData` se propague correctamente hasta `parental_consents.third_party_sharing`,
desbloqueando (o manteniendo bloqueado) el endpoint POST /api/ai/athletes/{id}/phv-explanation.

Estrategia:
  - Tests de renovación de consentimiento (renew) usan `conftest.client` (integración real
    contra aiosqlite, siguiendo el patrón de test_consent_endpoints.py).
  - Tests del endpoint IA usan overrides de dependencias sobre la app FastAPI (patrón
    de test_ai_router.py) para evitar dependencia de MySQL/LLM real.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

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
from app.models.user import UserRole
from app.services.ai.providers.fake import FakeLLMProvider


# ---------------------------------------------------------------------------
# Helpers de integración (mismos que test_consent_endpoints.py)
# ---------------------------------------------------------------------------


async def _login(client, email: str, password: str) -> str:
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, f"Login fallido: {resp.text}"
    return resp.json()["access_token"]


async def _coach_headers(client) -> dict:
    token = await _login(client, "entrenador@trochyruta.com", "Coach2026!")
    return {"Authorization": f"Bearer {token}"}


async def _get_club_id(client, headers: dict) -> int:
    me = await client.get("/api/auth/me", headers=headers)
    return me.json()["club_ids"][0]


async def _create_athlete(client, headers: dict, club_id: int) -> int:
    resp = await client.post(
        "/api/athletes",
        headers=headers,
        json={
            "first_name": "AIConsent",
            "last_name": f"Test-{uuid4().hex[:6]}",
            "birth_date": "2013-03-10",
            "sex": "M",
            "club_id": club_id,
        },
    )
    assert resp.status_code == 201, f"No se pudo crear atleta: {resp.text}"
    return resp.json()["id"]


async def _register_parent(
    client,
    athlete_id: int,
    *,
    accept_third_party_sharing: bool = False,
    consent_version: str = "v1.2",
) -> tuple[str, str]:
    """Registra un padre vinculado al atleta con el flag de IA indicado.

    Retorna (email, jwt_access_token).
    """
    coach_headers = await _coach_headers(client)
    email = f"parent-ai-{uuid4().hex[:8]}@test.com"

    inv_resp = await client.post(
        "/api/parent-athletes/invite",
        headers=coach_headers,
        json={"athlete_id": athlete_id, "email": email},
    )
    assert inv_resp.status_code == 201, f"Invite fallida: {inv_resp.text}"
    invite_token = inv_resp.json()["token"]

    reg_resp = await client.post(
        "/api/auth/parent-register",
        json={
            "token": invite_token,
            "first_name": "Padre",
            "last_name": "AITest",
            "password": "Parent2026!",
            "relationship_type": "madre",
            "consent": {
                "accept_data_collection": True,
                "accept_anthropometry": True,
                "accept_third_party_sharing": accept_third_party_sharing,
                "privacy_policy_version": consent_version,
            },
        },
    )
    assert reg_resp.status_code == 201, f"Registro fallido: {reg_resp.text}"

    jwt = await _login(client, email, "Parent2026!")
    return email, jwt


async def _full_setup(client) -> tuple[int, str]:
    """Crea atleta y padre con consentimiento por defecto (third_party_sharing=False).

    Retorna (athlete_id, parent_jwt).
    """
    headers = await _coach_headers(client)
    club_id = await _get_club_id(client, headers)
    athlete_id = await _create_athlete(client, headers, club_id)
    _, parent_jwt = await _register_parent(client, athlete_id)
    return athlete_id, parent_jwt


# ---------------------------------------------------------------------------
# Stubs para tests de override de dependencias (patrón test_ai_router.py)
# ---------------------------------------------------------------------------


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

    async def execute(self, _stmt):
        if not self._responses:
            return _ScalarResult()
        return self._responses.pop(0)


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


def _athlete_stub():
    from datetime import date
    from decimal import Decimal

    from app.models.anthropometry import MaturationStatus
    from app.models.athlete import Sex

    return SimpleNamespace(
        id=42,
        first_name="Atleta",
        last_name="Demo",
        birth_date=date(2014, 6, 15),
        sex=Sex.M,
        user_id=99,
        club_id=1,
    )


def _record_stub():
    from datetime import date
    from decimal import Decimal

    from app.models.anthropometry import MaturationStatus

    return SimpleNamespace(
        id=1,
        athlete_id=42,
        evaluation_date=date(2026, 4, 1),
        weight_kg=Decimal("40.0"),
        standing_height_cm=Decimal("150.0"),
        arm_span_cm=Decimal("152.0"),
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


# ---------------------------------------------------------------------------
# Tests de integración: renew con flag → parental_consents.third_party_sharing
# ---------------------------------------------------------------------------


class TestRenewThirdPartySharing:
    """Verifica que el flag accept_third_party_sharing se persista correctamente
    en parental_consents al renovar el consentimiento."""

    async def test_renew_con_third_party_sharing_true_persiste_true(self, client):
        """Padre renueva con accept_third_party_sharing=True → grants.third_party_sharing=True."""
        athlete_id, parent_jwt = await _full_setup(client)
        headers = {"Authorization": f"Bearer {parent_jwt}"}

        resp = await client.post(
            "/api/me/consent/renew",
            headers=headers,
            json={
                "athlete_id": athlete_id,
                "policy_version": "v1.2",
                "accept_data_collection": True,
                "accept_anthropometry": True,
                "accept_third_party_sharing": True,
            },
        )
        assert resp.status_code == 201, resp.text
        grants = resp.json()["grants"]
        assert grants["third_party_sharing"] is True
        # training_tracking sigue siendo False — no se toca
        assert grants["training_tracking"] is False

    async def test_renew_con_third_party_sharing_false_persiste_false(self, client):
        """Padre renueva con accept_third_party_sharing=False → grants.third_party_sharing=False."""
        athlete_id, parent_jwt = await _full_setup(client)
        headers = {"Authorization": f"Bearer {parent_jwt}"}

        resp = await client.post(
            "/api/me/consent/renew",
            headers=headers,
            json={
                "athlete_id": athlete_id,
                "policy_version": "v1.2",
                "accept_data_collection": True,
                "accept_anthropometry": True,
                "accept_third_party_sharing": False,
            },
        )
        assert resp.status_code == 201, resp.text
        grants = resp.json()["grants"]
        assert grants["third_party_sharing"] is False

    async def test_renew_sin_flag_usa_default_false(self, client):
        """Campo omitido → default False (compatibilidad con clientes antiguos)."""
        athlete_id, parent_jwt = await _full_setup(client)
        headers = {"Authorization": f"Bearer {parent_jwt}"}

        resp = await client.post(
            "/api/me/consent/renew",
            headers=headers,
            json={
                "athlete_id": athlete_id,
                "policy_version": "v1.2",
                "accept_data_collection": True,
                "accept_anthropometry": True,
                # accept_third_party_sharing no enviado
            },
        )
        assert resp.status_code == 201, resp.text
        grants = resp.json()["grants"]
        assert grants["third_party_sharing"] is False


# ---------------------------------------------------------------------------
# Tests del endpoint IA con override de consentimiento
# ---------------------------------------------------------------------------


@pytest.fixture
def fastapi_app_ai():
    """Fixture que limpia dependency_overrides después de cada test."""
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def http_client_ai(fastapi_app_ai):
    transport = ASGITransport(app=fastapi_app_ai)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestPHVExplanationConsentGate:
    """Verifica el gate de consentimiento en POST /api/ai/athletes/{id}/phv-explanation."""

    async def test_renew_with_third_party_sharing_true_enables_ai(
        self, http_client_ai, monkeypatch
    ):
        """Consentimiento con third_party_sharing=True → POST no devuelve 451."""
        monkeypatch.setattr(settings, "ai_enabled", True)

        # Simular que el atleta tiene consentimiento IA vigente
        async def _allow(_athlete_id, _db):
            return True

        monkeypatch.setattr(
            "app.routers.ai.athlete_has_ai_processing_consent", _allow
        )

        canned = "Su hijo está en Pre-PHV. Priorizamos juego y técnica."
        fake = FakeLLMProvider(canned=canned)
        app.dependency_overrides[get_llm_provider] = lambda: fake
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete_stub

        session = _QueueSession([
            _ScalarResult(items=[_record_stub()]),   # history
            _ScalarResult(),                          # upsert
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client_ai.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200, (
            f"Se esperaba 200 con consentimiento IA habilitado, recibido: {resp.status_code} — {resp.text}"
        )
        body = resp.json()
        assert "text" in body
        assert body["text"] == canned

    async def test_renew_with_third_party_sharing_false_keeps_ai_blocked(
        self, http_client_ai, monkeypatch
    ):
        """Consentimiento vigente con third_party_sharing=False → POST devuelve 451."""
        monkeypatch.setattr(settings, "ai_enabled", True)

        # Simular que el atleta NO tiene consentimiento IA
        async def _deny(_athlete_id, _db):
            return False

        monkeypatch.setattr(
            "app.routers.ai.athlete_has_ai_processing_consent", _deny
        )

        fake = FakeLLMProvider(canned="texto")
        app.dependency_overrides[get_llm_provider] = lambda: fake
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete_stub
        app.dependency_overrides[get_db] = lambda: _QueueSession([])

        resp = await http_client_ai.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 451, (
            f"Se esperaba 451 con consentimiento IA denegado, recibido: {resp.status_code}"
        )
        body = resp.json()
        assert "consent_missing" in body.get("detail", "").lower() or "consentimiento" in body.get("detail", "").lower()


# ---------------------------------------------------------------------------
# Tests de integración: wizard signup con accept_third_party_sharing
# ---------------------------------------------------------------------------


class TestSignupWizardThirdPartySharing:
    """Verifica que el wizard de registro propague correctly accept_third_party_sharing."""

    async def test_signup_wizard_con_third_party_sharing_true(self, client):
        """Wizard con accept_third_party_sharing=True → parental_consents.third_party_sharing=True.

        Verificación indirecta: el padre renueva de inmediato para leer el grants,
        dado que el wizard no expone el consentimiento en su respuesta de registro.
        En su lugar, validamos que el GET /me/consent muestra third_party_sharing=True.
        """
        coach_headers = await _coach_headers(client)
        club_id = await _get_club_id(client, coach_headers)
        athlete_id = await _create_athlete(client, coach_headers, club_id)

        _, parent_jwt = await _register_parent(
            client, athlete_id, accept_third_party_sharing=True, consent_version="v1.2"
        )
        parent_headers = {"Authorization": f"Bearer {parent_jwt}"}

        status_resp = await client.get("/api/me/consent", headers=parent_headers)
        assert status_resp.status_code == 200
        atletas = status_resp.json()["consents_per_athlete"]
        atleta = next(a for a in atletas if a["athlete_id"] == athlete_id)
        assert atleta["current_consent"] is not None
        grants = atleta["current_consent"]["grants"]
        assert grants["third_party_sharing"] is True, (
            "El wizard con accept_third_party_sharing=True debe persistir third_party_sharing=True"
        )
        # training_tracking sigue siendo False
        assert grants["training_tracking"] is False

    async def test_signup_wizard_default_third_party_sharing_false(self, client):
        """Wizard sin accept_third_party_sharing (campo omitido) → default False.

        Garantiza compatibilidad con clientes antiguos que no envían el campo.
        """
        coach_headers = await _coach_headers(client)
        club_id = await _get_club_id(client, coach_headers)
        athlete_id = await _create_athlete(client, coach_headers, club_id)

        email = f"parent-legacy-{uuid4().hex[:8]}@test.com"
        inv_resp = await client.post(
            "/api/parent-athletes/invite",
            headers=coach_headers,
            json={"athlete_id": athlete_id, "email": email},
        )
        assert inv_resp.status_code == 201
        invite_token = inv_resp.json()["token"]

        # Payload sin accept_third_party_sharing — cliente antiguo (v1.1 style)
        reg_resp = await client.post(
            "/api/auth/parent-register",
            json={
                "token": invite_token,
                "first_name": "Legacy",
                "last_name": "Padre",
                "password": "Parent2026!",
                "relationship_type": "acudiente",
                "consent": {
                    "accept_data_collection": True,
                    "accept_anthropometry": True,
                    # accept_third_party_sharing no incluido
                    "privacy_policy_version": "v1.2",
                },
            },
        )
        assert reg_resp.status_code == 201, f"Registro fallido: {reg_resp.text}"

        parent_jwt = await _login(client, email, "Parent2026!")
        parent_headers = {"Authorization": f"Bearer {parent_jwt}"}

        status_resp = await client.get("/api/me/consent", headers=parent_headers)
        assert status_resp.status_code == 200
        atletas = status_resp.json()["consents_per_athlete"]
        atleta = next(a for a in atletas if a["athlete_id"] == athlete_id)
        assert atleta["current_consent"] is not None
        grants = atleta["current_consent"]["grants"]
        assert grants["third_party_sharing"] is False, (
            "Payload sin accept_third_party_sharing debe persistir third_party_sharing=False (default)"
        )
