"""Tests del router para `/api/ai/athletes/{id}/measurements/{rid}/explanation`.

Cubre:
  - 451 cuando falta consentimiento third_party_sharing.
  - 403 padre intentando POST / pidiendo `audience=coach`.
  - 200 lectura del caché (coach y padre).
  - 200 generación happy path (coach), vía el pipeline (T055, ver abajo).
  - 404 cuando la medición no pertenece al atleta.
  - `?audience=family|coach` (NUEVO en esta feature, `contracts/measurement-
    analysis-api.md` §0.1) con caché separado por audiencia.
  - La compuerta familiar por rol (FR-016) y la respuesta discriminada v1|v2
    (`contracts/measurement-analysis-api.md` §§2-4).

Feature 042 (T055) — actualización sustancial
==============================================
Igual que `test_ai_router.py`: el POST ya NO consume `get_llm_provider` —
delega a `app.services.ai.anthro.pipeline.run_analysis` (T043), monkeypatcheado
aquí como `app.routers.ai.run_analysis`. La lógica interna del pipeline vive
en `tests/anthro/test_pipeline.py` (T053, fuera de este ownership); este
archivo solo verifica el cableado del router.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
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


def _coach_user():
    return SimpleNamespace(
        id=2, first_name="Coach", last_name="Test", email="coach@test",
        role=UserRole.coach, can_login=True, is_active=True, club_memberships=[],
    )


def _admin_user():
    return SimpleNamespace(
        id=1, first_name="Admin", last_name="Test", email="admin@test",
        role=UserRole.admin, can_login=True, is_active=True, club_memberships=[],
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


def _structured_payload(
    *,
    summary_line: str = "Resumen de ejemplo listo para la prueba automatizada.",
    confidence_level: str = "high",
) -> dict:
    """`structured_json` válido — ver el mismo helper en `test_ai_router.py`
    para la explicación de los tres campos extra deliberadamente ignorados
    por `AnthropometryInsightOut.from_stored`."""
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


def _cached(
    record_id: int,
    text: str = "texto cacheado",
    *,
    use_case: str = "anthropometric_record_analysis",
    schema_version: str | None = None,
    structured_json: dict | None = None,
    critic_verdict: str | None = None,
    prompt_version: str | None = None,
    langfuse_trace_id: str | None = None,
):
    """Fila simulada de `athlete_ai_explanations`.

    Feature 042 (T055): incluye las cinco columnas nuevas que
    `_map_structured_fields` lee. Por defecto reproduce una fila "v1"
    heredada (`None` en las cinco), igual que antes de esta feature.
    """
    return SimpleNamespace(
        id=99, athlete_id=42, anthropometric_record_id=record_id,
        use_case=use_case,
        text=text, model="cached-model", provider="anthropic",
        generated_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        age_group="10-12", maturation_status="Pre-PHV",
        generated_by_user_id=2,
        schema_version=schema_version,
        structured_json=structured_json,
        critic_verdict=critic_verdict,
        prompt_version=prompt_version,
        langfuse_trace_id=langfuse_trace_id,
    )


class _ScalarResult:
    """Result que responde a `.scalar_one_or_none()`, `.scalar_one()` y a
    `.scalars().all()`. `.scalar_one()` (T055) es lo que
    `_explanation_row_or_404` usa para releer la fila que el pipeline
    (mockeado en este archivo) dice haber persistido."""

    def __init__(self, *, scalar=None, items=None):
        self._scalar = scalar
        self._items = items if items is not None else []

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        if self._scalar is None:
            raise LookupError(
                "scalar_one() sin fila — fixture de test mal armado "
                "(ver _ScalarResult, tests/test_ai_record_router.py)"
            )
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._items


class _QueueSession:
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
    async def _stub(state: dict, config: dict | None = None) -> dict:
        return {"persisted_explanation_id": persisted_explanation_id}

    return _stub


def _capturing_run_analysis(result: dict) -> Callable[..., Any]:
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
        monkeypatch.setattr(ai_router, "run_analysis", _run_analysis_stub())
        target = _record(rid=10, eval_date=date(2026, 4, 1))
        cached = _cached(10, text="Esta es la primera medición de su hijo.")
        # 1: get_record_or_404 devuelve target
        # 2: priors query devuelve [] (sin historial)
        # 3: _explanation_row_or_404 relee la fila que el pipeline persistió
        # 4: _delta_summary (mismo criterio que el GET) — sin previos
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(items=[]),
            _ScalarResult(scalar=cached),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
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
        assert body["text"] == "Esta es la primera medición de su hijo."
        assert body["schema_version"] == "v1"

    async def test_happy_path_with_history(
        self, http_client, monkeypatch, allow_consent
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        monkeypatch.setattr(ai_router, "run_analysis", _run_analysis_stub())
        target = _record(rid=20, eval_date=date(2026, 4, 1), height="153.0", weight="42.5")
        prior = _record(rid=10, eval_date=date(2026, 1, 1), height="150.0", weight="40.0")
        cached = _cached(20, text="Su hijo creció en este periodo.")
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(items=[prior]),          # priors para el pipeline
            _ScalarResult(scalar=cached),          # _explanation_row_or_404
            _ScalarResult(items=[prior]),          # _delta_summary
        ])
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
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
        monkeypatch.setattr(
            ai_router,
            "run_analysis",
            _raising_run_analysis(LLMSchemaError("Respuesta rechazada por guardrails")),
        )
        target = _record(rid=10)
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 502
        assert len(session.executed) == 2  # nada se releyó tras el rechazo

    async def test_config_error_returns_500(
        self, http_client, monkeypatch, allow_consent
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        monkeypatch.setattr(
            ai_router,
            "run_analysis",
            _raising_run_analysis(LLMConfigError("proveedor no soportado")),
        )
        target = _record(rid=10)
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 500

    async def test_timeout_resolves_to_200_fallback_not_503(
        self, http_client, monkeypatch, allow_consent
    ):
        """`contracts/measurement-analysis-api.md` §5, "Behaviour change to
        flag explicitly": un timeout del analista/crítico ya NO surge como
        503 — el pipeline resuelve al fallback determinista, `200` con
        `critic_verdict="fallback"`. Test con el nombre exacto pedido por el
        contrato §7 (`test_timeout_resolves_to_200_fallback_not_503`)."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        monkeypatch.setattr(ai_router, "run_analysis", _run_analysis_stub())
        target = _record(rid=10)
        cached = _cached(
            10,
            text="Análisis no disponible para esta medición; ver la próxima.",
            schema_version="v2",
            critic_verdict="fallback",
            structured_json=_structured_payload(confidence_level="low"),
        )
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(items=[]),
            _ScalarResult(scalar=cached),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["critic_verdict"] == "fallback"
        assert body["is_fallback"] is True
        assert body["structured"]["confidence"]["level"] == "low"


class TestPostMeasurementExplanationPipelineWiring:
    async def test_post_passes_expected_state_to_pipeline(
        self, http_client, monkeypatch, allow_consent
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        stub = _capturing_run_analysis({"persisted_explanation_id": 7})
        monkeypatch.setattr(ai_router, "run_analysis", stub)
        target = _record(rid=10)
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(items=[]),
            _ScalarResult(scalar=_cached(10)),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 200, resp.text
        assert len(stub.captured) == 1
        state = stub.captured[0]
        assert state["athlete"].id == 42
        assert state["target_record"] is target
        assert state["audience"] == "family"
        assert state["use_case"] == "anthropometric_record_analysis"
        assert state["club_id"] == 1
        assert state["actor"].role == UserRole.coach

    async def test_no_explanation_lookup_when_pipeline_config_error(
        self, http_client, monkeypatch, allow_consent
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        monkeypatch.setattr(
            ai_router,
            "run_analysis",
            _raising_run_analysis(LLMConfigError("configuración inválida")),
        )
        target = _record(rid=10)
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 500
        assert len(session.executed) == 2


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
            _ScalarResult(scalar=_cached(10, text="hola padres")),
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
        assert body["schema_version"] == "v1"
        assert body["structured"] is None

    async def test_parent_can_read_cache(self, http_client, monkeypatch):
        """Padres con ownership ven el caché (sin botón generar en el front)."""
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(scalar=_cached(10)),
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
# Audiencia (feature 042, `contracts/measurement-analysis-api.md` §0.1) —
# NUEVA en este endpoint: antes de esta feature no existía `?audience=` aquí.
# ---------------------------------------------------------------------------


class TestMeasurementExplanationAudience:
    async def test_get_coach_audience_forbidden_for_parent(
        self, http_client, monkeypatch
    ):
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _QueueSession([])

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation",
            params={"audience": "coach"},
        )
        assert resp.status_code == 403

    async def test_get_family_audience_default_still_allowed_for_parent(
        self, http_client, monkeypatch
    ):
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(scalar=_cached(10, text="texto para padres")),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation",
            params={"audience": "family"},
        )
        assert resp.status_code == 200
        assert resp.json()["text"] == "texto para padres"

    async def test_get_coach_audience_reads_coach_cache_row(
        self, http_client, monkeypatch
    ):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(
                scalar=_cached(
                    10,
                    text="texto para entrenador",
                    use_case="anthropometric_record_explainer_coach",
                )
            ),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation",
            params={"audience": "coach"},
        )
        assert resp.status_code == 200
        assert resp.json()["text"] == "texto para entrenador"

    async def test_get_cache_filter_use_case_differs_per_audience(
        self, http_client, monkeypatch
    ):
        """El SELECT de caché filtra por un `use_case` distinto según
        `audience` — misma garantía que ya existía para el endpoint PHV,
        extendida aquí porque el parámetro es nuevo en este endpoint."""
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)

        for audience, expected_use_case in (
            ("family", "anthropometric_record_analysis"),
            ("coach", "anthropometric_record_explainer_coach"),
        ):
            session = _QueueSession([
                _ScalarResult(scalar=target),
                _ScalarResult(scalar=None),
            ])
            app.dependency_overrides[get_db] = lambda: session

            resp = await http_client.get(
                "/api/ai/athletes/42/measurements/10/explanation",
                params={"audience": audience},
            )
            assert resp.status_code == 204

            cache_select = session.executed[1]
            compiled = cache_select.compile()
            assert compiled.params["use_case_1"] == expected_use_case

    async def test_post_coach_audience_passes_coach_use_case_to_pipeline(
        self, http_client, monkeypatch, allow_consent
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        stub = _capturing_run_analysis({"persisted_explanation_id": 7})
        monkeypatch.setattr(ai_router, "run_analysis", stub)
        target = _record(rid=10)
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(items=[]),
            _ScalarResult(
                scalar=_cached(10, use_case="anthropometric_record_explainer_coach")
            ),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post(
            "/api/ai/athletes/42/measurements/10/explanation",
            params={"audience": "coach"},
        )
        assert resp.status_code == 200, resp.text
        assert stub.captured[0]["use_case"] == "anthropometric_record_explainer_coach"
        assert stub.captured[0]["audience"] == "coach"

    async def test_post_family_default_still_passes_family_use_case(
        self, http_client, monkeypatch, allow_consent
    ):
        """Regresión: la clave familiar histórica
        (`anthropometric_record_analysis`) no cambia — así una fila "v1"
        existente se upgradea en el mismo lugar (`contracts/measurement-
        analysis-api.md` §0.1)."""
        monkeypatch.setattr(settings, "ai_enabled", True)
        stub = _capturing_run_analysis({"persisted_explanation_id": 7})
        monkeypatch.setattr(ai_router, "run_analysis", stub)
        target = _record(rid=10)
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(items=[]),
            _ScalarResult(scalar=_cached(10)),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.post(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 200, resp.text
        assert stub.captured[0]["use_case"] == "anthropometric_record_analysis"
        assert stub.captured[0]["audience"] == "family"

    async def test_post_coach_audience_still_forbidden_for_parent(
        self, http_client, monkeypatch, allow_consent
    ):
        monkeypatch.setattr(settings, "ai_enabled", True)
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        app.dependency_overrides[get_db] = lambda: _QueueSession([])

        resp = await http_client.post(
            "/api/ai/athletes/42/measurements/10/explanation",
            params={"audience": "coach"},
        )
        assert resp.status_code == 403

    async def test_get_coach_audience_allowed_for_admin_no_cache(
        self, http_client, monkeypatch
    ):
        """La barrera de rol no debe interferir con el flujo normal de "sin
        datos" para un admin pidiendo `audience=coach`."""
        app.dependency_overrides[get_current_user] = _admin_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(scalar=None),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation",
            params={"audience": "coach"},
        )
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Compuerta familiar por rol (FR-016, data-model.md §3) — T055
# ---------------------------------------------------------------------------


class TestFamilyGate:
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
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)
        cached = _cached(
            10,
            schema_version="v2",
            critic_verdict=verdict,
            structured_json=_structured_payload(),
        )
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(scalar=cached),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == expected_status, resp.text
        if expected_status == 204:
            assert resp.content == b""

    async def test_parent_gate_treats_legacy_null_verdict_as_deliverable(
        self, http_client, monkeypatch
    ):
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(scalar=_cached(10, critic_verdict=None)),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 200

    async def test_parent_missing_row_and_only_flagged_analysis_both_look_like_no_analysis(
        self, http_client, monkeypatch
    ):
        """FR-016/SC-004: un padre cuyo hijo solo tiene análisis `flagged`
        ve exactamente el mismo estado (`204`, cuerpo vacío) que un padre sin
        ningún análisis todavía — el frontend renderiza ambos casos con el
        mismo mensaje pasivo compartido, sin distinguirlos."""
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)

        no_row_session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(scalar=None),
        ])
        app.dependency_overrides[get_db] = lambda: no_row_session
        resp_missing = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation"
        )

        flagged_session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(
                scalar=_cached(
                    10,
                    schema_version="v2",
                    critic_verdict="flagged",
                    structured_json=_structured_payload(),
                )
            ),
        ])
        app.dependency_overrides[get_db] = lambda: flagged_session
        resp_flagged = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation"
        )

        assert resp_missing.status_code == resp_flagged.status_code == 204
        assert resp_missing.content == resp_flagged.content == b""

    async def test_coach_sees_flagged_content_unfiltered(
        self, http_client, monkeypatch
    ):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)
        cached = _cached(
            10,
            schema_version="v2",
            critic_verdict="flagged",
            structured_json=_structured_payload(),
        )
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(scalar=cached),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["critic_verdict"] == "flagged"
        assert body["structured"] is not None

    async def test_coach_previewing_family_audience_still_sees_flagged(
        self, http_client, monkeypatch
    ):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)
        cached = _cached(
            10,
            use_case="anthropometric_record_analysis",
            schema_version="v2",
            critic_verdict="skipped",
            structured_json=_structured_payload(confidence_level="low"),
        )
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(scalar=cached),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation",
            params={"audience": "family"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["critic_verdict"] == "skipped"


# ---------------------------------------------------------------------------
# Respuesta discriminada v1|v2 (contracts/measurement-analysis-api.md §2)
# ---------------------------------------------------------------------------


class TestDiscriminatedResponse:
    async def test_legacy_v1_row_renders_without_structured_fields(
        self, http_client, monkeypatch
    ):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(scalar=_cached(10, text="Texto libre heredado.")),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["text"] == "Texto libre heredado."
        assert body["schema_version"] == "v1"
        assert body["structured"] is None
        assert body["critic_verdict"] is None
        assert body["is_fallback"] is False
        assert body["prompt_version"] is None
        assert body["trace_id"] is None

    async def test_v2_row_returns_structured_payload(
        self, http_client, monkeypatch
    ):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)
        cached = _cached(
            10,
            schema_version="v2",
            critic_verdict="revised",
            prompt_version="anthropometry_analyst_v1",
            structured_json=_structured_payload(summary_line="Talla dentro de lo esperado."),
        )
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(scalar=cached),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["schema_version"] == "v2"
        assert body["critic_verdict"] == "revised"
        assert body["prompt_version"] == "anthropometry_analyst_v1"
        assert body["structured"]["summary_line"] == "Talla dentro de lo esperado."

    async def test_corrupt_structured_json_degrades_gracefully(
        self, http_client, monkeypatch
    ):
        """`quickstart.md` §Scenario 11: "a v2 row with corrupt
        structured_json falls back to prose rather than raising." — mismo
        caso que `test_ai_router.py`, verificado también en este endpoint
        porque ambos pasan por la misma `_map_structured_fields`."""
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)
        cached = _cached(
            10,
            text="Prosa igualmente válida ya persistida en la columna NOT NULL.",
            schema_version="v2",
            critic_verdict="approved",
            structured_json={"summary_line": "Incompleto a propósito."},
        )
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(scalar=cached),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
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
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)
        cached = _cached(
            10,
            schema_version="v2",
            critic_verdict="approved",
            structured_json=_structured_payload(),
            langfuse_trace_id="9f8e7d6c5b4a3210",
        )
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(scalar=cached),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 200
        assert resp.json()["trace_id"] is None

    async def test_trace_id_visible_for_coach_when_set(
        self, http_client, monkeypatch
    ):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[verify_athlete_access] = _athlete
        target = _record(rid=10)
        cached = _cached(
            10,
            schema_version="v2",
            critic_verdict="approved",
            structured_json=_structured_payload(),
            langfuse_trace_id="9f8e7d6c5b4a3210",
        )
        session = _QueueSession([
            _ScalarResult(scalar=target),
            _ScalarResult(scalar=cached),
            _ScalarResult(items=[]),
        ])
        app.dependency_overrides[get_db] = lambda: session

        resp = await http_client.get(
            "/api/ai/athletes/42/measurements/10/explanation"
        )
        assert resp.status_code == 200
        assert resp.json()["trace_id"] == "9f8e7d6c5b4a3210"


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
        app.dependency_overrides[get_db] = lambda: _QueueSession([])

        resp = await http_client.post("/api/ai/athletes/42/phv-explanation")
        assert resp.status_code == 451
