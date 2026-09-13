"""Tests del router `/api/ai/*` sin tocar MySQL.

Sobrescribimos las dependencias (`get_current_user`, `verify_athlete_access`,
`get_db`) para validar el comportamiento del router en forma aislada. Los
tests de integración real siguen el patrón del resto del proyecto y
requieren Docker compose con MySQL (no se incluyen aquí).

Feature 042 (T055) — actualización sustancial
==============================================
Desde esta feature, `phv_explanation`/`measurement_explanation` (POST) ya NO
consumen `get_llm_provider` — delegan la generación completa a
`app.services.ai.anthro.pipeline.run_analysis` (T043), que hace su propia
persistencia. Este archivo por tanto:

  - Monkeypatchea `app.routers.ai.run_analysis` (el nombre importado en el
    módulo del router, no el símbolo original) para controlar el resultado
    del pipeline sin invocar un LLM real — la lógica INTERNA del pipeline
    (máquina de estados de `data-model.md` §3) ya está cubierta por
    `tests/anthro/test_pipeline.py` (T053), fuera de este ownership; este
    archivo solo verifica el CABLEADO del router (qué le pasa al pipeline,
    qué hace con lo que el pipeline devuelve, qué códigos de estado mapea).
  - Ya NO inspecciona sentencias SQL de upsert tras un POST (ese INSERT
    ahora vive exclusivamente en `anthro/persist.py`, invariante 5 de
    `data-model.md` §6) — en su lugar verifica que el router relee la fila
    ya persistida (`_explanation_row_or_404`, `scalar_one()`) y construye la
    respuesta v1|v2 correctamente.
  - Añade la compuerta familiar por rol (FR-016), la respuesta discriminada
    v1|v2 (incluida degradación ante `structured_json` corrupto) y los
    campos técnicos exclusivos de coach/admin (`contracts/measurement-
    analysis-api.md` §§2-4).

Fixtures de fila cacheada (`_cached_explanation`) ahora incluyen las cinco
columnas nuevas que `_map_structured_fields` (`app/routers/ai.py`) lee:
`schema_version`, `structured_json`, `critic_verdict`, `prompt_version`,
`langfuse_trace_id`. Los tests que no las mencionan reciben los valores
legado (`None`), es decir una fila "v1" — el comportamiento pre-042 sigue
siendo el default de este archivo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Callable

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.dependencies import (
    get_current_user,
    get_db,
    verify_athlete_access,
)
from app.main import app
from app.models.anthropometry import MaturationStatus
from app.models.athlete import Sex
from app.models.user import UserRole
from app.routers import ai as ai_router
from app.services.ai.errors import LLMConfigError, LLMSchemaError


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


def _structured_payload(
    *,
    summary_line: str = "Resumen de ejemplo listo para la prueba automatizada.",
    confidence_level: str = "high",
) -> dict:
    """`structured_json` válido — proyectable por `AnthropometryInsightOut.from_stored`.

    Incluye tres campos extra (`schema_version`, `audience`, `word_count`) que
    `from_stored` filtra a propósito (data-model.md §0 / `schemas/ai.py`
    docstring) — se dejan aquí para que el fixture sea un `structured_json`
    real, byte a byte lo que `persist.py` escribiría, no un atajo.
    """
    return {
        "schema_version": "v1",
        "audience": "family",
        "summary_line": summary_line,
        "changes": ["El cambio de talla se mantiene dentro de lo esperado."],
        "meaning": ["Este ritmo corresponde a un desarrollo típico para esta etapa."],
        "next_weeks": ["Continuar con la rutina habitual de entrenamiento."],
        "warning_signs": [],
        "confidence": {
            "level": confidence_level,
            "reason": "Hay suficientes datos recientes para esta lectura.",
        },
        "data_gaps": [],
        "word_count": 24,
    }


class _ScalarResult:
    """Result que responde a `.scalar_one_or_none()`, `.scalar_one()` y a
    `.scalars().all()`.

    `.scalar_one()` (nuevo en T055) es lo que `_explanation_row_or_404`
    (`app/routers/ai.py`) usa para releer la fila que el pipeline (mockeado
    en este archivo) dice haber persistido — antes de esta feature el router
    nunca llamaba a `scalar_one()` directamente.
    """

    def __init__(self, *, scalar=None, items=None):
        self._scalar = scalar
        self._items = items if items is not None else []

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        if self._scalar is None:
            raise LookupError(
                "scalar_one() sin fila — fixture de test mal armado "
                "(ver _ScalarResult, tests/test_ai_router.py)"
            )
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._items


class _QueueSession:
    """Sesión que devuelve respuestas en orden de llamada y captura stmts."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.executed: list = []
        self.added: list = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        if not self._responses:
            return _ScalarResult()
        return self._responses.pop(0)

    def add(self, obj) -> None:
        self.added.append(obj)


def _run_analysis_stub(*, persisted_explanation_id: int = 7) -> Callable[..., Any]:
    """Doble simple de `run_analysis` — éxito, sin capturar el `state`."""

    async def _stub(state: dict, config: dict | None = None) -> dict:
        return {"persisted_explanation_id": persisted_explanation_id}

    return _stub


def _capturing_run_analysis(result: dict) -> Callable[..., Any]:
    """Doble de `run_analysis` que además guarda cada `state` recibido en
    `.captured`, para que un test pueda verificar qué le pasó el router
    (`use_case`, `audience`, `actor`, etc.) sin inspeccionar SQL."""
    captured: list[dict] = []

    async def _stub(state: dict, config: dict | None = None) -> dict:
        captured.append(state)
        return result

    _stub.captured = captured  # type: ignore[attr-defined]
    return _stub


def _raising_run_analysis(exc: Exception) -> Callable[..., Any]:
    async def _stub(state: dict, config: dict | None = None) -> dict:
        raise exc

    return _stub


@pytest.fixture
def fastapi_app():
    """Aplica overrides genéricos y limpia al final."""
    yield app
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _grant_ai_consent_by_default(monkeypatch):
    """Por defecto los tests no testean el gate de consentimiento.

    Sobrescribimos `athlete_has_ai_processing_consent` en el módulo del router
    para que devuelva True. Los tests que valida el gate explícitamente lo
    re-sobrescriben con False.
    """

    async def _allow(_athlete_id, _db):  # type: ignore[unused-argument]
        return True

    monkeypatch.setattr(
        "app.routers.ai.athlete_has_ai_processing_consent", _allow
    )


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
# /api/ai/athletes/{id}/phv-explanation — POST (generación vía pipeline)
# ---------------------------------------------------------------------------


class TestPHVExplanation:
    async def test_disabled_returns_503(self, http_client, monkeypatch):
        monkeypatch.setattr(settings, "ai_enabled", False)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _QueueSession([])
        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 503

    async def test_no_records_returns_422(self, http_client, monkeypatch):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _QueueSession(
            [_ScalarResult(items=[])]
        )
        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 422

    async def test_happy_path(self, http_client, monkeypatch):
        """El router pasa por el pipeline (mockeado) y relee la fila persistida."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        monkeypatch.setattr(ai_router, "run_analysis", _run_analysis_stub())
        cached = _cached_explanation(text="Su hijo está en Pre-PHV.")
        session = _QueueSession([
            _ScalarResult(items=[_record()]),   # history
            _ScalarResult(scalar=cached),        # _explanation_row_or_404
        ])
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["text"] == "Su hijo está en Pre-PHV."
        assert body["provider"] == "anthropic"
        assert body["model"] == "cached-model"
        assert body["age_group"] == "10-12"
        assert body["maturation_status"] == "Pre-PHV"
        # Fila "v1" (legado) por defecto — sin campos estructurados.
        assert body["schema_version"] == "v1"
        assert body["structured"] is None
        assert body["critic_verdict"] is None

    async def test_guardrail_violation_returns_502(self, http_client, monkeypatch):
        """`guardrails_step.py` rechaza (`LLMSchemaError`) — 502, sin releer caché."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        monkeypatch.setattr(
            ai_router,
            "run_analysis",
            _raising_run_analysis(LLMSchemaError("Respuesta rechazada por guardrails")),
        )
        session = _QueueSession([_ScalarResult(items=[_record()])])
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 502
        # Nunca se intentó releer una fila persistida — el rechazo aborta
        # la corrida completa (data-model.md §3, invariante de guardrails_step).
        assert len(session.executed) == 1

    async def test_config_error_returns_500(self, http_client, monkeypatch):
        monkeypatch.setattr(settings, "ai_enabled", True)
        monkeypatch.setattr(
            ai_router,
            "run_analysis",
            _raising_run_analysis(LLMConfigError("proveedor no soportado")),
        )
        session = _QueueSession([_ScalarResult(items=[_record()])])
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 500

    async def test_pipeline_fallback_resolves_to_200_not_503(
        self, http_client, monkeypatch
    ):
        """Cambio de comportamiento deliberado (`contracts/measurement-
        analysis-api.md` §5): un timeout del analista/crítico ya NO propaga
        como 503 — el pipeline resuelve internamente al fallback determinista
        y persiste con `critic_verdict="fallback"`. Desde la perspectiva del
        router (que solo relee lo persistido) esto es indistinguible de
        cualquier otro éxito de `run_analysis`."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        monkeypatch.setattr(ai_router, "run_analysis", _run_analysis_stub())
        cached = _cached_explanation(
            schema_version="v2",
            critic_verdict="fallback",
            structured_json=_structured_payload(confidence_level="low"),
        )
        session = _QueueSession([
            _ScalarResult(items=[_record()]),
            _ScalarResult(scalar=cached),
        ])
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["critic_verdict"] == "fallback"
        assert body["is_fallback"] is True


# ---------------------------------------------------------------------------
# Caché backend: GET + guard parent
# ---------------------------------------------------------------------------


def _cached_explanation(
    record_id: int = 1,
    *,
    text: str = "cache hit",
    use_case: str = "phv_explainer",
    schema_version: str | None = None,
    structured_json: dict | None = None,
    critic_verdict: str | None = None,
    prompt_version: str | None = None,
    langfuse_trace_id: str | None = None,
):
    """Fila simulada de `athlete_ai_explanations`.

    Feature 042 (T055): incluye ahora las cinco columnas que
    `_map_structured_fields` lee (`schema_version`, `structured_json`,
    `critic_verdict`, `prompt_version`, `langfuse_trace_id`). Los defaults
    (`None`) reproducen una fila "v1" heredada — el comportamiento pre-042
    de este helper sigue siendo el default para no romper los tests que no
    les interesa el eje v1|v2.
    """
    from datetime import datetime, timezone

    return SimpleNamespace(
        id=10,
        athlete_id=42,
        anthropometric_record_id=record_id,
        use_case=use_case,
        text=text,
        model="cached-model",
        provider="anthropic",
        generated_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        age_group="10-12",
        maturation_status="Pre-PHV",
        generated_by_user_id=2,
        schema_version=schema_version,
        structured_json=structured_json,
        critic_verdict=critic_verdict,
        prompt_version=prompt_version,
        langfuse_trace_id=langfuse_trace_id,
    )


class TestGetPHVExplanationCached:
    """GET /api/ai/athletes/{id}/phv-explanation — solo lectura del caché.

    Diseñado para sobrevivir al apagado del LLM: NO chequea `ai_enabled`.
    """

    async def test_no_records_returns_204(self, http_client, monkeypatch):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
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

    async def test_parent_cache_hit_returns_200(self, http_client, monkeypatch):
        """Padre con ownership válido + caché existente (approved) → 200 con payload."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(
                scalar=_cached_explanation(text="texto para padres")
            ),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["text"] == "texto para padres"
        assert body["provider"] == "anthropic"
        assert body["model"] == "cached-model"
        assert body["age_group"] == "10-12"
        assert body["maturation_status"] == "Pre-PHV"
        # El schema no expone generated_by_user_id — no debe filtrarse.
        assert "generated_by_user_id" not in body

    async def test_parent_no_cache_returns_204(self, http_client, monkeypatch):
        """Padre con ownership válido + sin caché → 204 (sin contenido)."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        session = _QueueSession([
            _ScalarResult(scalar=_record()),   # latest_record existe
            _ScalarResult(scalar=None),        # pero no hay caché
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 204
        assert resp.content == b""

    async def test_parent_without_ownership_returns_403(
        self, http_client, monkeypatch
    ):
        """Padre sin ownership (atleta de otra familia) → 403.

        El guard lo aplica `verify_athlete_access` — este test es regresión
        para asegurar que remover `_forbid_parents` del GET no eliminó la
        barrera real de ownership.
        """
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _parent_user

        def _deny_access():
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene acceso a este atleta.",
            )

        app.dependency_overrides[verify_athlete_access] = _deny_access
        app.dependency_overrides[get_db] = lambda: _QueueSession([])

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Compuerta familiar por rol (FR-016, data-model.md §3) — T055
# ---------------------------------------------------------------------------


class TestFamilyGate:
    """`contracts/measurement-analysis-api.md` §3 — la compuerta se aplica
    SOLO a un padre, keyed en `critic_verdict`, nunca en `?audience=`."""

    @pytest.mark.parametrize(
        "verdict,expected_status",
        [
            ("approved", 200),
            ("revised", 200),
            ("flagged", 204),
            ("fallback", 204),
            ("skipped", 204),
        ],
    )
    async def test_parent_gate_by_critic_verdict(
        self, http_client, monkeypatch, verdict, expected_status
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        cached = _cached_explanation(
            schema_version="v2",
            critic_verdict=verdict,
            structured_json=_structured_payload(),
        )
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(scalar=cached),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == expected_status, resp.text
        if expected_status == 204:
            assert resp.content == b""

    async def test_parent_gate_treats_legacy_null_verdict_as_deliverable(
        self, http_client, monkeypatch
    ):
        """data-model.md §6, invariante 3: `critic_verdict IS NULL` (fila
        "v1" heredada) siempre se trata como entregable — esta feature no
        censura retroactivamente contenido anterior al crítico."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(scalar=_cached_explanation(critic_verdict=None)),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200

    async def test_coach_sees_flagged_content_unfiltered(
        self, http_client, monkeypatch
    ):
        """El coach es el humano en el bucle — nunca queda ciego a un
        `flagged`/`fallback`/`skipped` (FR-016)."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        cached = _cached_explanation(
            schema_version="v2",
            critic_verdict="flagged",
            structured_json=_structured_payload(),
        )
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(scalar=cached),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["critic_verdict"] == "flagged"
        assert body["structured"] is not None

    async def test_coach_previewing_family_audience_still_sees_flagged(
        self, http_client, monkeypatch
    ):
        """`?audience=family` pedido por un coach para previsualizar SIGUE
        mostrando el contenido real — la compuerta está keyed en el ROL del
        solicitante, no en `audience` (§3 del contrato)."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        cached = _cached_explanation(
            use_case="phv_explainer",
            schema_version="v2",
            critic_verdict="fallback",
            structured_json=_structured_payload(confidence_level="low"),
        )
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(scalar=cached),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/phv-explanation", params={"audience": "family"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["critic_verdict"] == "fallback"


# ---------------------------------------------------------------------------
# Respuesta discriminada v1|v2 (contracts/measurement-analysis-api.md §2)
# ---------------------------------------------------------------------------


class TestDiscriminatedResponse:
    async def test_legacy_v1_row_renders_without_structured_fields(
        self, http_client, monkeypatch
    ):
        """FR-026, Edge Case spec.md:129: una fila heredada (`schema_version
        IS NULL`) SIEMPRE se expone como API `"v1"`, con los campos nuevos
        en su valor por defecto, texto byte a byte igual al almacenado."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        cached = _cached_explanation(text="Texto libre heredado, sin estructura.")
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(scalar=cached),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200
        body = resp.json()
        assert body["text"] == "Texto libre heredado, sin estructura."
        assert body["schema_version"] == "v1"
        assert body["structured"] is None
        assert body["critic_verdict"] is None
        assert body["is_fallback"] is False
        assert body["prompt_version"] is None
        assert body["trace_id"] is None

    async def test_v2_row_returns_structured_payload(
        self, http_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        cached = _cached_explanation(
            schema_version="v2",
            critic_verdict="approved",
            prompt_version="anthropometry_analyst_v1",
            structured_json=_structured_payload(summary_line="Talla dentro de lo esperado."),
        )
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(scalar=cached),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["schema_version"] == "v2"
        assert body["critic_verdict"] == "approved"
        assert body["prompt_version"] == "anthropometry_analyst_v1"
        assert body["structured"]["summary_line"] == "Talla dentro de lo esperado."
        assert body["structured"]["confidence"]["level"] == "high"
        assert body["structured"]["data_gaps"] == []

    async def test_corrupt_structured_json_degrades_gracefully(
        self, http_client, monkeypatch
    ):
        """`quickstart.md` §Scenario 11 / `plan.md` W2 exit gate: "a v2 row
        with corrupt structured_json falls back to prose rather than
        raising." `text` (columna `NOT NULL`, siempre saneada por
        guardrails_step antes de persistir) debe seguir sirviéndose con
        `200`, nunca un `500` sin manejar."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        cached = _cached_explanation(
            text="Prosa igualmente válida ya persistida en la columna NOT NULL.",
            schema_version="v2",
            critic_verdict="approved",
            # JSON corrupto: falta "confidence" (requerido) — simula un
            # payload de una versión de esquema futura/rota.
            structured_json={"summary_line": "Incompleto a propósito."},
        )
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(scalar=cached),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200, (
            "un structured_json corrupto debe degradar a prosa, no producir "
            f"un 500 sin manejar (recibido {resp.status_code}): {resp.text}"
        )
        body = resp.json()
        assert body["text"] == (
            "Prosa igualmente válida ya persistida en la columna NOT NULL."
        )
        assert body["structured"] is None


# ---------------------------------------------------------------------------
# Campos técnicos exclusivos de coach/admin (contracts/measurement-
# analysis-api.md §4) — T055
# ---------------------------------------------------------------------------


class TestCoachOnlyTechnicalFields:
    async def test_trace_id_null_for_parent_even_when_set(
        self, http_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        cached = _cached_explanation(
            schema_version="v2",
            critic_verdict="approved",
            structured_json=_structured_payload(),
            langfuse_trace_id="a1b2c3d4e5f60718",
        )
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(scalar=cached),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200
        assert resp.json()["trace_id"] is None

    async def test_trace_id_visible_for_coach_when_set(
        self, http_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        cached = _cached_explanation(
            schema_version="v2",
            critic_verdict="approved",
            structured_json=_structured_payload(),
            langfuse_trace_id="a1b2c3d4e5f60718",
        )
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(scalar=cached),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200
        assert resp.json()["trace_id"] == "a1b2c3d4e5f60718"

    async def test_trace_id_null_for_coach_when_tracing_disabled(
        self, http_client, monkeypatch
    ):
        """Producción (`LANGFUSE_ENABLED=false`, siempre cierto ahí) ya deja
        `langfuse_trace_id=None` en la fila persistida — el router no vuelve
        a chequear ese flag, solo el rol; para un coach esto sigue
        resultando en `trace_id=null` porque no hay nada que exponer."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        cached = _cached_explanation(
            schema_version="v2",
            critic_verdict="approved",
            structured_json=_structured_payload(),
            langfuse_trace_id=None,
        )
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(scalar=cached),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200
        assert resp.json()["trace_id"] is None


# ---------------------------------------------------------------------------
# Cableado del router hacia el pipeline (reemplaza a las viejas aserciones
# de upsert SQL — esa persistencia ahora vive en anthro/persist.py)
# ---------------------------------------------------------------------------


class TestPostPHVExplanationPipelineWiring:
    async def test_post_passes_expected_state_to_pipeline(
        self, http_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        stub = _capturing_run_analysis({"persisted_explanation_id": 7})
        monkeypatch.setattr(ai_router, "run_analysis", stub)
        record = _record()
        session = _QueueSession([
            _ScalarResult(items=[record]),
            _ScalarResult(scalar=_cached_explanation()),
        ])
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200, resp.text

        assert len(stub.captured) == 1
        state = stub.captured[0]
        assert state["athlete"].id == 42
        assert state["target_record"] is record
        assert state["audience"] == "family"
        assert state["use_case"] == "phv_explainer"
        assert state["club_id"] == 1
        assert state["actor"].role == UserRole.coach

    async def test_parent_forbidden(self, http_client, monkeypatch):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _QueueSession([])

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 403

    async def test_no_explanation_lookup_when_pipeline_config_error(
        self, http_client, monkeypatch
    ):
        """Si el pipeline falla con `LLMConfigError`, el router nunca llega
        a `_explanation_row_or_404` — solo se ejecutó la query de history."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        monkeypatch.setattr(
            ai_router,
            "run_analysis",
            _raising_run_analysis(LLMConfigError("configuración inválida")),
        )
        session = _QueueSession([_ScalarResult(items=[_record()])])
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 500
        assert len(session.executed) == 1


# ---------------------------------------------------------------------------
# Audiencia (feature 040/042): `?audience=family|coach`
# ---------------------------------------------------------------------------


class TestPHVExplanationAudience:
    """`audience=coach` agrega números (velocidad, meses) vedados a padres;
    cachea aparte de la variante familiar vía `use_case`."""

    async def test_get_coach_audience_forbidden_for_parent(
        self, http_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _QueueSession([])

        resp = await http_client.get(
            "/api/ai/athletes/42/phv-explanation", params={"audience": "coach"}
        )
        assert resp.status_code == 403

    async def test_get_family_audience_still_allowed_for_parent(
        self, http_client, monkeypatch
    ):
        """Regresión: el nuevo query param no rompe el flujo de padres
        (default `family`, sin cambios de comportamiento)."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(scalar=_cached_explanation(text="texto para padres")),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/phv-explanation", params={"audience": "family"}
        )
        assert resp.status_code == 200
        assert resp.json()["text"] == "texto para padres"

    async def test_get_coach_audience_allowed_for_admin_no_records(
        self, http_client, monkeypatch
    ):
        """Sin mediciones el resultado es 204 (no 403): admin sí puede pedir
        `audience=coach`, la barrera de rol no debe interferir con el flujo
        normal de "sin datos"."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _admin_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _QueueSession(
            [_ScalarResult(scalar=None)]
        )

        resp = await http_client.get(
            "/api/ai/athletes/42/phv-explanation", params={"audience": "coach"}
        )
        assert resp.status_code == 204

    async def test_get_coach_audience_reads_coach_cache_row(
        self, http_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        session = _QueueSession([
            _ScalarResult(scalar=_record()),
            _ScalarResult(
                scalar=_cached_explanation(
                    text="texto para entrenador",
                    use_case="phv_explanation_coach",
                )
            ),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/phv-explanation", params={"audience": "coach"}
        )
        assert resp.status_code == 200
        assert resp.json()["text"] == "texto para entrenador"

    async def test_get_cache_filter_use_case_differs_per_audience(
        self, http_client, monkeypatch
    ):
        """Garantía real de que family/coach cachean aparte: el SELECT de
        caché filtra por un `use_case` distinto según `audience` (no solo
        un mock que "adivina" la respuesta esperada)."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete

        for audience, expected_use_case in (
            ("family", "phv_explainer"),
            ("coach", "phv_explanation_coach"),
        ):
            session = _QueueSession([
                _ScalarResult(scalar=_record()),
                _ScalarResult(scalar=None),
            ])
            app.dependency_overrides[get_db] = lambda: session

            resp = await http_client.get(
                "/api/ai/athletes/42/phv-explanation",
                params={"audience": audience},
            )
            assert resp.status_code == 204

            cache_select = session.executed[1]
            compiled = cache_select.compile()
            assert compiled.params["use_case_1"] == expected_use_case

    async def test_post_coach_audience_passes_coach_use_case_to_pipeline(
        self, http_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        stub = _capturing_run_analysis({"persisted_explanation_id": 7})
        monkeypatch.setattr(ai_router, "run_analysis", stub)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        session = _QueueSession([
            _ScalarResult(items=[_record()]),
            _ScalarResult(
                scalar=_cached_explanation(use_case="phv_explanation_coach")
            ),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post(
            "/api/ai/athletes/42/phv-explanation", params={"audience": "coach"}
        )
        assert resp.status_code == 200, resp.text
        assert stub.captured[0]["use_case"] == "phv_explanation_coach"
        assert stub.captured[0]["audience"] == "coach"

    async def test_post_family_default_still_passes_family_use_case(
        self, http_client, monkeypatch
    ):
        """Regresión: sin `audience` explícito el use_case sigue siendo el
        histórico `phv_explainer` — no invalida caché ya existente."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        stub = _capturing_run_analysis({"persisted_explanation_id": 7})
        monkeypatch.setattr(ai_router, "run_analysis", stub)
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        session = _QueueSession([
            _ScalarResult(items=[_record()]),
            _ScalarResult(scalar=_cached_explanation()),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 200, resp.text
        assert stub.captured[0]["use_case"] == "phv_explainer"
        assert stub.captured[0]["audience"] == "family"

    async def test_post_coach_audience_still_forbidden_for_parent(
        self, http_client, monkeypatch
    ):
        """`_forbid_parents` ya bloqueaba todo POST de padres; confirma que
        agregar `audience` no abre una rendija."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _QueueSession([])

        resp = await http_client.post(
            "/api/ai/athletes/42/phv-explanation", params={"audience": "coach"}
        )
        assert resp.status_code == 403
