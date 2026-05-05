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


class _ScalarResult:
    """Result que responde a `.scalar_one_or_none()` y a `.scalars().all()`.

    Se usa para tests que necesitan distinguir entre la query de "última
    medición" (scalar) y "history" (list) sobre la misma sesión.
    """

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
    """Sesión que devuelve respuestas en orden de llamada y captura stmts.

    Atributo `executed` guarda en orden cada `stmt` recibido para que un test
    pueda verificar (por ejemplo) que tras la generación se ejecutó un upsert.
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.executed: list = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        if not self._responses:
            # default no-op: devuelve resultado vacío
            return _ScalarResult()
        return self._responses.pop(0)


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


# ---------------------------------------------------------------------------
# Caché backend: GET + POST upsert + invalidación implícita + guard parent
# ---------------------------------------------------------------------------


def _parent_user():
    return SimpleNamespace(
        id=3,
        first_name="Padre",
        last_name="Test",
        email="parent@test",
        role=UserRole.parent,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


def _cached_explanation(record_id: int = 1, *, text: str = "cache hit"):
    """Fila simulada de `athlete_ai_explanations`."""
    from datetime import datetime, timezone

    return SimpleNamespace(
        id=10,
        athlete_id=42,
        anthropometric_record_id=record_id,
        use_case="phv_explainer",
        text=text,
        model="cached-model",
        provider="anthropic",
        generated_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        age_group="10-12",
        maturation_status="Pre-PHV",
        generated_by_user_id=2,
    )


class TestGetPHVExplanationCached:
    """GET /api/ai/athletes/{id}/phv-explanation — solo lectura del caché.

    Diseñado para sobrevivir al apagado del LLM: NO chequea `ai_enabled`.
    """

    async def test_no_records_returns_204(self, http_client, monkeypatch):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        # Una sola query (latest_record) devuelve None.
        session = _QueueSession([_ScalarResult(scalar=None)])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 204
        assert resp.content == b""

    async def test_cache_miss_returns_204(self, http_client, monkeypatch):
        """Hay medición pero no hay caché para ella."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        session = _QueueSession([
            _ScalarResult(scalar=_record()),     # latest_record
            _ScalarResult(scalar=None),          # cache lookup
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 204

    async def test_cache_hit_returns_payload(self, http_client, monkeypatch):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(scalar=_cached_explanation(text="hola padres")),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200
        body = resp.json()
        assert body["text"] == "hola padres"
        assert body["provider"] == "anthropic"
        assert body["model"] == "cached-model"
        assert body["age_group"] == "10-12"
        assert body["maturation_status"] == "Pre-PHV"

    async def test_cached_generated_at_is_utc_serialized(
        self, http_client, monkeypatch
    ):
        """MySQL devuelve datetime naive; el endpoint debe reaplicar UTC al
        serializar para que el navegador no interprete el ISO como hora local.
        """
        from datetime import datetime

        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete

        # Simulamos el round-trip MySQL: la fila vuelve con datetime naive.
        cached = _cached_explanation()
        cached.generated_at = datetime(2026, 5, 5, 20, 10, 0)  # sin tzinfo
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(scalar=cached),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200
        body = resp.json()
        # Pydantic serializa con tzinfo UTC → ISO termina en Z o +00:00.
        assert (
            body["generated_at"].endswith("Z")
            or body["generated_at"].endswith("+00:00")
        ), f"generated_at debe tener tzinfo UTC, recibido: {body['generated_at']}"

    async def test_serves_cache_when_ai_disabled(
        self, http_client, monkeypatch
    ):
        """Lectura del caché sobrevive a outage del LLM (AI_ENABLED=false)."""
        monkeypatch.setattr(settings, "ai_enabled", False)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(scalar=_cached_explanation()),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200, (
            "GET cache debe servir aunque AI_ENABLED=false"
        )

    async def test_parent_forbidden(self, http_client, monkeypatch):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        # No debería llegar a tocar la DB, pero proveemos session por si acaso.
        app.dependency_overrides[get_db] = lambda: _QueueSession([])

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 403


class TestPostPHVExplanationCacheUpsert:
    """POST genera y persiste vía upsert idempotente."""

    async def test_executes_upsert_after_generation(
        self, http_client, monkeypatch
    ):
        from sqlalchemy.dialects.mysql.dml import Insert as MySQLInsert

        from app.models.ai_explanation import AthleteAIExplanation

        monkeypatch.setattr(settings, "ai_enabled", True)
        fake = FakeLLMProvider(canned="Hola padres en Pre-PHV.")
        app.dependency_overrides[get_llm_provider] = lambda: fake
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete

        # 1ra execute: history (4 records). 2da: upsert.
        history_result = _ScalarResult(items=[_record()])
        upsert_result = _ScalarResult()
        session = _QueueSession([history_result, upsert_result])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200, resp.text

        # Verifica que se ejecutaron exactamente 2 statements y el segundo
        # fue un INSERT MySQL sobre la tabla del caché.
        assert len(session.executed) == 2
        upsert_stmt = session.executed[1]
        assert isinstance(upsert_stmt, MySQLInsert), (
            "el segundo execute debe ser un INSERT MySQL (upsert)"
        )
        assert upsert_stmt.table.name == AthleteAIExplanation.__tablename__

    async def test_parent_forbidden(self, http_client, monkeypatch):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _QueueSession([])

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 403

    async def test_no_upsert_when_llm_fails(self, http_client, monkeypatch):
        """Si el LLM falla devolvemos 503 y NO escribimos al caché."""
        from app.services.ai.errors import LLMUnavailableError

        class BoomProvider(FakeLLMProvider):
            async def complete(self, req):
                raise LLMUnavailableError("backend caído")

        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_llm_provider] = lambda: BoomProvider()
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        session = _QueueSession([_ScalarResult(items=[_record()])])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 503
        # Solo se ejecutó la query de history; el upsert no se intentó.
        assert len(session.executed) == 1
