"""Tests de habilitación del consentimiento de procesamiento con IA.

Verifica que el flag `accept_third_party_sharing` en `ConsentRenewIn` y en
`ParentalConsentData` se propague correctamente hasta `parental_consents.third_party_sharing`,
desbloqueando (o manteniendo bloqueado) el endpoint POST /api/ai/athletes/{id}/phv-explanation.

Estrategia:
  - Tests de renovación de consentimiento (renew) usan `conftest.client` (integración real
    contra aiosqlite, siguiendo el patrón de test_consent_endpoints.py).
  - Tests del endpoint IA usan overrides de dependencias sobre la app FastAPI (patrón
    de test_ai_router.py) para evitar dependencia de MySQL/LLM real.

Cambio de seam (feature 042, T039/T043) — LEER ANTES DE TOCAR ESTE ARCHIVO
===========================================================================
`test_renew_with_third_party_sharing_true_enables_ai` overrideaba la
dependencia FastAPI `get_llm_provider` con un `FakeLLMProvider` de texto
canned y afirmaba `body["text"] == canned`. Eso probaba el stack VIEJO
(`app/services/ai/factory.py::PHVExplainerUseCase`, feature 033). Desde esta
feature, `phv_explanation` (`app/routers/ai.py`) genera exclusivamente vía
`app.services.ai.anthro.pipeline.run_analysis`, que NUNCA consulta
`get_llm_provider` — construye su propio chat model LangChain llamando
`app.services.llm.factory.build_chat_llm(role=..., stack="app")` desde
DENTRO de `anthro/analyst.py` y `anthro/critic.py` (cada módulo importó el
símbolo a su propio namespace con `from ... import build_chat_llm`). El
seam real a parchear es, por lo tanto, `app.services.ai.anthro.analyst.
build_chat_llm` / `app.services.ai.anthro.critic.build_chat_llm` — nunca
`get_llm_provider`, que ese pipeline ni siquiera importa.

Este test se reescribió para:
  1. Reemplazar esos dos símbolos por un doble mínimo (`.ainvoke(messages,
     config=None) -> objeto con .content`) que devuelve JSON válido para
     `AnthropometryInsightV1` (analista) y `AnthropometryCriticVerdict`
     (crítico) — nunca `GenericFakeChatModel` de `langchain-core`, reservado
     por las reglas de esta tarea a las pruebas de adaptador/pipeline.
  2. Reemplazar `_QueueSession` (una cola posicional de resultados —fue
     diseñada para el viejo caso de uso de una sola consulta de historial +
     upsert legado, y ya no alcanza: el pipeline nuevo agrega dos lecturas
     auxiliares en `context.py` —ventana de entrenamiento, análisis
     estructurado previo— antes de llegar al upsert) por una sesión sqlite
     REAL en memoria. La única sentencia que sigue sin compilar sobre
     aiosqlite es el upsert MySQL de `persist.py`
     (`mysql_insert(...).on_duplicate_key_update(...)`,
     `UnsupportedCompilationError` verificado) — se sustituye ÚNICAMENTE esa
     fábrica por `_SqliteUpsertShim` (mismo doble que
     `test_ai_explanation_audit.py`), nunca el resto de la sesión.

La compuerta de consentimiento (451 sin consentimiento, 200 tras renovarlo)
sigue siendo la aserción central de esta clase — es el motivo de ser del
archivo — así que se preserva exactamente.

Bug real descubierto por esta reescritura (fuera del ownership de este
archivo — NO corregido aquí, ver `needs_orchestrator`): con el mock en el
seam correcto, `test_renew_with_third_party_sharing_true_enables_ai` sigue
en rojo, pero ya no por un mock desactualizado — `app/routers/ai.py::
_map_structured_fields` hace `AnthropometryInsightOut.model_validate(cached.
structured_json)` contra un modelo `extra="forbid"` de 7 campos, mientras
que `persist.py` guarda en `structured_json` el `model_dump(mode="json")`
COMPLETO de `AnthropometryInsightV1` (10 campos: además de los 7 que
`AnthropometryInsightOut` sí declara, trae siempre `schema_version`,
`audience` y `word_count`). Esto revienta con
`pydantic.ValidationError: 3 validation errors ... Extra inputs are not
permitted` en TODA generación v2 exitosa — reproducido también con un
`model_dump()` aislado, sin HTTP ni pipeline de por medio. No se debilitó
la aserción `resp.status_code == 200`: el test se deja en rojo a propósito
para que este bug no quede enmascarado.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import app.services.ai.anthro.analyst as anthro_analyst
import app.services.ai.anthro.critic as anthro_critic
import app.services.ai.anthro.persist as anthro_persist
from app.config import settings
from app.dependencies import (
    get_current_user,
    get_db,
    get_llm_provider,
    verify_athlete_access,
)
from app.main import app
from app.models import Base
from app.models.anthropometry import MaturationStatus
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
    """Cola posicional de resultados — sigue siendo válida SOLO para el
    camino de consentimiento denegado (451), que corta antes de tocar la
    DB. Ver el docstring del módulo: para el camino de éxito (200) el
    pipeline nuevo hace demasiadas lecturas propias para una cola
    posicional; ese test usa una sesión sqlite real (`ai_pipeline_session`)."""

    def __init__(self, responses):
        self._responses = list(responses)
        #: Filas encoladas con `db.add(...)` — hoy solo la de `audit_log`
        #: que escribe `record_audit` tras el upsert (T030).
        self.added: list = []

    async def execute(self, _stmt):
        if not self._responses:
            return _ScalarResult()
        return self._responses.pop(0)

    def add(self, obj) -> None:
        self.added.append(obj)


# ---------------------------------------------------------------------------
# Doble de la fábrica mysql_insert de `persist.py` — mismo doble que
# `test_ai_explanation_audit.py` (ver el docstring del módulo). `persist.py`
# usa `.values()` / `.inserted.<col>` / `.on_duplicate_key_update()`, la
# superficie exacta que ``sqlalchemy.dialects.mysql.dml.Insert`` expone —
# este doble la traduce a la variante sqlite (``on_conflict_do_update``,
# ``excluded``) para que el upsert real corra sobre un motor en memoria.
# ---------------------------------------------------------------------------


class _SqliteUpsertShim:
    def __init__(self, table):
        self._stmt = sqlite_insert(table)

    def values(self, **kwargs):
        self._stmt = self._stmt.values(**kwargs)
        return self

    @property
    def inserted(self):
        return self._stmt.excluded

    def on_duplicate_key_update(self, **kwargs):
        return self._stmt.on_conflict_do_update(
            index_elements=["athlete_id", "anthropometric_record_id", "use_case"],
            set_=kwargs,
        )


# ---------------------------------------------------------------------------
# Dobles mínimos de chat model LangChain — ver el docstring del módulo
# ("cambio de seam"). Nunca `GenericFakeChatModel` aquí (reservado a
# pruebas de adaptador/pipeline por las reglas de esta tarea): basta un
# `.ainvoke(...)` que devuelva un objeto con `.content`, que es todo lo que
# `app.services.llm.calls.call_llm` necesita.
# ---------------------------------------------------------------------------


_ANALYST_INSIGHT_JSON = """{
  "audience": "family",
  "summary_line": "Crecimiento estable dentro de lo esperado para esta fase.",
  "changes": ["La talla y el peso avanzaron de forma gradual."],
  "meaning": ["Este ritmo es compatible con un desarrollo saludable."],
  "next_weeks": ["Mantener la rutina de entrenamiento habitual."],
  "warning_signs": [],
  "confidence": {"level": "medium", "reason": "Datos suficientes para esta lectura, sin senales de alerta."},
  "data_gaps": [],
  "word_count": 30
}"""

_CRITIC_APPROVE_JSON = '{"verdict": "approve", "violations": []}'


class _FakeChatResponse:
    def __init__(self, text: str) -> None:
        self.content = text


class _FakeChatModel:
    def __init__(self, text: str) -> None:
        self._text = text

    async def ainvoke(self, _messages, config=None):
        del config
        return _FakeChatResponse(self._text)


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
# Sesión sqlite real para el camino de éxito (200) del gate de consentimiento
# — ver el docstring del módulo. Solo las tablas que `anthro.pipeline.
# run_analysis` toca de verdad: la medición objetivo (leída por el propio
# router), la ventana de entrenamiento (`context.py`, vacía aquí — atleta
# sin sesiones registradas es un estado válido, degrada a `None`) y la
# caché/auditoría de explicaciones que escribe `persist.py`.
# ---------------------------------------------------------------------------

_PIPELINE_TABLES = (
    "anthropometric_records",
    "athlete_ai_explanations",
    "session_attendance",
    "training_sessions",
    "audit_log",
    "training_session_coaches",
    "privacy_policies",
    "parent_invites",
)


@pytest_asyncio.fixture
async def ai_pipeline_engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[name] for name in _PIPELINE_TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def ai_pipeline_session(
    ai_pipeline_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """Sesión real con la medición objetivo del atleta stub (`_athlete_stub`,
    `id=42`) ya sembrada — el router hace su propia lectura de historial
    (`select(AnthropometricRecord).where(athlete_id==42)`) antes de invocar
    el pipeline, así que esta fila debe existir de verdad, no solo como
    objeto Python en memoria. Los z-scores/percentiles no son `None`
    (salvo donde el modelo los admite) porque `build_growth_summary` (paso 1
    del pipeline) es una función pura sobre estos campos, sin fallback
    "inventa si falta" — un `None` donde no lo espera revienta con
    `TypeError`, no con un dato faltante degradado con gracia.
    """
    factory = async_sessionmaker(ai_pipeline_engine, expire_on_commit=False)
    async with factory() as session:
        from app.models.anthropometry import AnthropometricRecord

        session.add(
            AnthropometricRecord(
                id=1,
                athlete_id=42,
                evaluation_date=date(2026, 4, 1),
                weight_kg=Decimal("40.0"),
                standing_height_cm=Decimal("150.0"),
                arm_span_cm=Decimal("152.0"),
                sitting_height_cm=Decimal("75.0"),
                leg_length_cm=Decimal("75.0"),
                leg_sitting_ratio=Decimal("1.0000"),
                maturity_offset=Decimal("-1.5"),
                age_at_phv=Decimal("13.5"),
                maturation_status=MaturationStatus.pre_phv,
                height_z_score=Decimal("0.4"),
                bmi=Decimal("17.8"),
                bmi_z_score=Decimal("0.1"),
                weight_z_score=Decimal("0.2"),
                height_percentile=Decimal("65.0"),
                bmi_percentile=Decimal("55.0"),
                weight_percentile=Decimal("60.0"),
                evaluated_by=2,
            )
        )
        await session.commit()
        yield session


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
        self, http_client_ai, monkeypatch, ai_pipeline_session
    ):
        """Consentimiento con third_party_sharing=True → POST no devuelve 451.

        Ver el docstring del módulo ("cambio de seam"): el LLM real se
        sustituye parcheando `build_chat_llm` en los namespaces de
        `anthro.analyst`/`anthro.critic` (el seam que el pipeline nuevo
        consulta de verdad), nunca `get_llm_provider` (dependencia FastAPI
        del stack viejo, que este pipeline no usa). El upsert MySQL de
        `persist.py` se sustituye por `_SqliteUpsertShim` para poder correr
        sobre la sesión sqlite real de `ai_pipeline_session`.
        """
        monkeypatch.setattr(settings, "ai_enabled", True)
        monkeypatch.setattr(anthro_persist, "mysql_insert", _SqliteUpsertShim)
        monkeypatch.setattr(
            anthro_analyst, "build_chat_llm", lambda *a, **k: _FakeChatModel(_ANALYST_INSIGHT_JSON)
        )
        monkeypatch.setattr(
            anthro_critic, "build_chat_llm", lambda *a, **k: _FakeChatModel(_CRITIC_APPROVE_JSON)
        )

        # Simular que el atleta tiene consentimiento IA vigente
        async def _allow(_athlete_id, _db):
            return True

        monkeypatch.setattr(
            "app.routers.ai.athlete_has_ai_processing_consent", _allow
        )

        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete_stub
        app.dependency_overrides[get_db] = lambda: ai_pipeline_session

        resp = await http_client_ai.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200, (
            f"Se esperaba 200 con consentimiento IA habilitado, recibido: {resp.status_code} — {resp.text}"
        )
        body = resp.json()
        assert "text" in body
        assert body["text"]

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
