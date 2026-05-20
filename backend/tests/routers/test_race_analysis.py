"""Tests integración del router ``/api/race-analysis/*`` (F5.9).

Cobertura:
- Auth: 401 sin token; 403 con rol incorrecto (parent).
- Happy path: POST /runs → seed completo → GET /status → GET /result.
- Polling: ?since funciona (slicing por seq).
- HITL: approve, reject, edit con edits obligatorios.
- PDF: si weasyprint falta o run incompleto → 404/501; happy path 200.
- Chat: respuesta JSON, 503 si AI deshabilitada.
- Backpressure: spawnea 10 runs, el 11 → 429.
- Admin metrics: agrega insights, calcula p50/p95, fail rate.

Convenciones:
- NO se llama Gemini real. Mock del chat agent vía dependency override.
- NO se llama LangGraph real. Stub via ``set_graph_factory``.
- Asserts sobre status code + estructura JSON.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.main import app
from app.routers.race_analysis import _admin_only, _coach_or_admin
from app.services.race.schemas import ChatResponse

pytestmark = pytest.mark.asyncio


# ===========================================================================
# Auth tests
# ===========================================================================


class TestAuth:
    async def test_401_sin_token(self, anon_client):
        # Sin override: HTTPBearer scheme exige header → 403 (FastAPI default)
        # o 401. Aceptamos cualquiera de los dos en el rango.
        resp = await anon_client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": 1, "season": 2026},
        )
        assert resp.status_code in (401, 403)

    async def test_403_parent_no_puede_iniciar_run(self, parent_client, ai_enabled):
        resp = await parent_client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": 1, "season": 2026},
        )
        assert resp.status_code == 403

    async def test_403_parent_no_puede_consultar_status(self, parent_client):
        resp = await parent_client.get("/api/race-analysis/runs/abc/status")
        assert resp.status_code == 403

    async def test_403_coach_no_puede_admin_metrics(self, coach_client):
        resp = await coach_client.get("/api/race-analysis/admin/ai-usage")
        # coach_client tiene override de _coach_or_admin pero NO de
        # _admin_only — el endpoint usa _admin_only así que rechaza.
        assert resp.status_code == 403


# ===========================================================================
# POST /runs
# ===========================================================================


class TestStartRun:
    async def test_503_si_ai_deshabilitada(self, coach_client, monkeypatch):
        # Forzamos ai_enabled=False (el .env del dev puede tenerlo en True).
        from app.config import settings

        monkeypatch.setattr(settings, "ai_enabled", False)
        resp = await coach_client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": 1, "season": 2026},
        )
        assert resp.status_code == 503

    async def test_happy_path_retorna_run_id(self, coach_client, ai_enabled, fake_db):
        resp = await coach_client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": 1, "season": 2026, "valida_nums": [1, 2, 3]},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "run_id" in body
        assert body["status"] == "running"
        assert body["status_url"] == f"/api/race-analysis/runs/{body['run_id']}/status"
        assert body["estimated_seconds"] == 15 + 5 * 3
        # Verificar insert en fake_db
        assert body["run_id"] in fake_db.runs

    async def test_valida_nums_vacio_es_400(self, coach_client, ai_enabled):
        resp = await coach_client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": 1, "season": 2026, "valida_nums": []},
        )
        # Pydantic validator rechaza lista vacía → 422 (FastAPI)
        assert resp.status_code == 422

    async def test_valida_nums_fuera_rango_es_422(self, coach_client, ai_enabled):
        resp = await coach_client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": 1, "season": 2026, "valida_nums": [15]},
        )
        assert resp.status_code == 422


# ===========================================================================
# GET /runs/{id}/status
# ===========================================================================


class TestStatus:
    async def test_404_run_no_existe(self, coach_client):
        resp = await coach_client.get("/api/race-analysis/runs/nonexistent/status")
        assert resp.status_code == 404

    async def test_403_si_no_eres_owner(self, coach_client, fake_db):
        # owner=99, coach_client.user.id=10 → forbidden
        fake_db.seed_run("run-otro", requested_by_user_id=99)
        resp = await coach_client.get("/api/race-analysis/runs/run-otro/status")
        assert resp.status_code == 403

    async def test_polling_devuelve_eventos_desde_since(self, coach_client, fake_db):
        run = fake_db.seed_run("run-poll", requested_by_user_id=10)
        fake_db.seed_event(run["id"], 1, "node_start", "validate_input")
        fake_db.seed_event(run["id"], 2, "node_end", "validate_input")
        fake_db.seed_event(run["id"], 3, "node_start", "load_race_data")

        # since=0 → todos
        resp = await coach_client.get("/api/race-analysis/runs/run-poll/status?since=0")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["new_events"]) == 3
        assert body["last_seq"] == 3
        assert body["state"] == "running"
        assert body["current_node"] == "load_race_data"

        # since=2 → sólo seq=3
        resp = await coach_client.get("/api/race-analysis/runs/run-poll/status?since=2")
        body = resp.json()
        assert len(body["new_events"]) == 1
        assert body["new_events"][0]["seq"] == 3

    async def test_etag_304_si_no_cambio(self, coach_client, fake_db):
        run = fake_db.seed_run("run-etag", requested_by_user_id=10)
        fake_db.seed_event(run["id"], 1, "node_start", "validate_input")

        r1 = await coach_client.get("/api/race-analysis/runs/run-etag/status")
        etag = r1.headers.get("etag")
        assert etag is not None

        r2 = await coach_client.get(
            "/api/race-analysis/runs/run-etag/status",
            headers={"If-None-Match": etag},
        )
        assert r2.status_code == 304

    async def test_state_done_cuando_status_completed(self, coach_client, fake_db):
        fake_db.seed_run(
            "run-done",
            status_="completed",
            requested_by_user_id=10,
            final_output_json={"raw_markdown": "ok"},
        )
        resp = await coach_client.get("/api/race-analysis/runs/run-done/status")
        body = resp.json()
        assert body["state"] == "done"
        assert body["progress_pct"] == 100

    async def test_state_hitl_waiting(self, coach_client, fake_db):
        fake_db.seed_run("run-hitl", status_="awaiting_hitl", requested_by_user_id=10)
        resp = await coach_client.get("/api/race-analysis/runs/run-hitl/status")
        body = resp.json()
        assert body["state"] == "hitl_waiting"


# ===========================================================================
# POST /runs/{id}/hitl/{step}
# ===========================================================================


class TestHITL:
    async def test_404_run_no_existe(self, coach_client):
        resp = await coach_client.post(
            "/api/race-analysis/runs/nope/hitl/review",
            json={"decision": "approve"},
        )
        assert resp.status_code == 404

    async def test_approve_happy_path(self, coach_client, fake_db):
        fake_db.seed_run("run-ok", status_="awaiting_hitl", requested_by_user_id=10)
        resp = await coach_client.post(
            "/api/race-analysis/runs/run-ok/hitl/review",
            json={"decision": "approve"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] is True
        assert body["run_id"] == "run-ok"

    async def test_reject_marca_evento(self, coach_client, fake_db):
        fake_db.seed_run("run-rej", status_="awaiting_hitl", requested_by_user_id=10)
        resp = await coach_client.post(
            "/api/race-analysis/runs/run-rej/hitl/review",
            json={"decision": "reject", "notes": "no aplicable"},
        )
        assert resp.status_code == 200
        # Evento persistido
        evs = fake_db.events_by_run_db_id[fake_db.runs["run-rej"]["id"]]
        assert any(e["event_type"] == "hitl_response" for e in evs)

    async def test_edit_sin_edits_es_422(self, coach_client, fake_db):
        fake_db.seed_run("run-edit", status_="awaiting_hitl", requested_by_user_id=10)
        resp = await coach_client.post(
            "/api/race-analysis/runs/run-edit/hitl/review",
            json={"decision": "edit"},
        )
        assert resp.status_code == 422

    async def test_edit_con_edits_ok(self, coach_client, fake_db):
        fake_db.seed_run("run-edit-ok", status_="awaiting_hitl", requested_by_user_id=10)
        resp = await coach_client.post(
            "/api/race-analysis/runs/run-edit-ok/hitl/review",
            json={"decision": "edit", "edits": "# Markdown editado"},
        )
        assert resp.status_code == 200

    async def test_409_si_run_terminal(self, coach_client, fake_db):
        fake_db.seed_run("run-comp", status_="completed", requested_by_user_id=10)
        resp = await coach_client.post(
            "/api/race-analysis/runs/run-comp/hitl/review",
            json={"decision": "approve"},
        )
        assert resp.status_code == 409


# ===========================================================================
# GET /runs/{id}/result
# ===========================================================================


class TestResult:
    async def test_404_si_run_no_existe(self, coach_client):
        resp = await coach_client.get("/api/race-analysis/runs/nope/result")
        assert resp.status_code == 404

    async def test_404_si_aun_running(self, coach_client, fake_db):
        fake_db.seed_run("run-running", status_="running", requested_by_user_id=10)
        resp = await coach_client.get("/api/race-analysis/runs/run-running/result")
        assert resp.status_code == 404

    async def test_409_si_failed(self, coach_client, fake_db):
        fake_db.seed_run("run-fail", status_="failed", requested_by_user_id=10)
        fake_db.runs["run-fail"]["error_message"] = "TimeoutError"
        resp = await coach_client.get("/api/race-analysis/runs/run-fail/result")
        assert resp.status_code == 409

    async def test_happy_path_devuelve_final(self, coach_client, fake_db):
        fake_db.seed_run(
            "run-result",
            status_="completed",
            requested_by_user_id=10,
            final_output_json={
                "raw_markdown": "# Análisis",
                "sections": {"evolution": "ok"},
                "recommendations": [],
                "risk_flags": [],
            },
        )
        resp = await coach_client.get("/api/race-analysis/runs/run-result/result")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["final"]["raw_markdown"] == "# Análisis"


# ===========================================================================
# GET /runs/{id}/pdf
# ===========================================================================


class TestPDF:
    async def test_404_run_no_existe(self, coach_client):
        resp = await coach_client.get("/api/race-analysis/runs/nope/pdf")
        assert resp.status_code == 404

    async def test_404_si_aun_running(self, coach_client, fake_db):
        fake_db.seed_run("run-r", status_="running", requested_by_user_id=10)
        resp = await coach_client.get("/api/race-analysis/runs/run-r/pdf")
        assert resp.status_code == 404

    async def test_pdf_completed_o_501(self, coach_client, fake_db):
        """PDF rendering puede fallar con 501 si weasyprint no tiene libs
        nativas (común en macOS sin brew). Aceptamos 200 (PDF binario)
        o 501 (TODO documentado)."""
        fake_db.seed_run(
            "run-pdf",
            status_="completed",
            requested_by_user_id=10,
            final_output_json={"raw_markdown": "# Hola\nTest content"},
        )
        resp = await coach_client.get("/api/race-analysis/runs/run-pdf/pdf")
        assert resp.status_code in (200, 501)
        if resp.status_code == 200:
            assert resp.headers["content-type"] == "application/pdf"
            assert "attachment" in resp.headers["content-disposition"]


# ===========================================================================
# POST /chat
# ===========================================================================


class TestChat:
    async def test_503_si_ai_deshabilitada(self, coach_client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ai_enabled", False)
        resp = await coach_client.post(
            "/api/race-analysis/chat",
            json={"session_id": "s1", "query": "hola"},
        )
        assert resp.status_code == 503

    async def test_happy_path(self, coach_client, ai_enabled):
        from app.routers.race_analysis import get_race_chat_agent

        class FakeChatAgent:
            async def chat(self, session_id, query, athlete_id=None):
                return ChatResponse(
                    answer=f"Respuesta a: {query}",
                    citations_used=["1"],
                    tools_called=["consultar_marco_teorico"],
                )

        app.dependency_overrides[get_race_chat_agent] = lambda: FakeChatAgent()
        try:
            resp = await coach_client.post(
                "/api/race-analysis/chat",
                json={"session_id": "s1", "query": "qué es PHV?"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "PHV" in body["answer"]
            assert body["citations_used"] == ["1"]
        finally:
            app.dependency_overrides.pop(get_race_chat_agent, None)

    async def test_agente_falla_502(self, coach_client, ai_enabled):
        from app.routers.race_analysis import get_race_chat_agent

        class FailAgent:
            async def chat(self, session_id, query, athlete_id=None):
                raise RuntimeError("Gemini caído")

        app.dependency_overrides[get_race_chat_agent] = lambda: FailAgent()
        try:
            resp = await coach_client.post(
                "/api/race-analysis/chat",
                json={"session_id": "s1", "query": "hi"},
            )
            assert resp.status_code == 502
        finally:
            app.dependency_overrides.pop(get_race_chat_agent, None)


# ===========================================================================
# Backpressure
# ===========================================================================


class TestBackpressure:
    async def test_max_concurrent_runs_429(self, coach_client, ai_enabled, fake_graph, monkeypatch):
        """Spawnea 10 runs lentos (mantienen slot) → el 11 retorna 429."""
        from app.services.race.ai import runner as runner_mod

        # Override del graph factory para que ainvoke "cuelgue" hasta sleep.
        class SlowGraph:
            async def ainvoke(self, value, config=None):
                await asyncio.sleep(5)  # mantiene el slot
                return {}

        async def _factory():
            return SlowGraph()

        runner_mod.set_graph_factory(_factory)

        ok_count = 0
        rejected_count = 0
        for _ in range(11):
            resp = await coach_client.post(
                "/api/race-analysis/runs",
                json={"athlete_id": 1, "season": 2026},
            )
            if resp.status_code == 201:
                ok_count += 1
            elif resp.status_code == 429:
                rejected_count += 1

        assert ok_count == 10
        assert rejected_count == 1


# ===========================================================================
# Admin metrics
# ===========================================================================


class TestAdminMetrics:
    async def test_403_si_no_admin(self, coach_client):
        resp = await coach_client.get("/api/race-analysis/admin/ai-usage")
        assert resp.status_code == 403

    async def test_admin_agrega_insights(self, admin_client, fake_db):
        # Seed 3 insights con costos variados.
        fake_db.seed_insight(cost_total=0.001, latency_total=1000)
        fake_db.seed_insight(cost_total=0.002, latency_total=2000)
        fake_db.seed_insight(cost_total=0.003, latency_total=3000)

        resp = await admin_client.get("/api/race-analysis/admin/ai-usage?days=30")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_count"] == 3
        assert abs(body["cost_usd_total"] - 0.006) < 1e-6
        assert body["latency_ms_p50"] == 2000
        assert body["window_days"] == 30
        # by_prompt_version
        assert len(body["by_prompt_version"]) >= 1

    async def test_admin_fail_rate(self, admin_client, fake_db):
        fake_db.seed_run("r-c", status_="completed")
        fake_db.seed_run("r-f", status_="failed")
        fake_db.seed_run("r-f2", status_="failed")
        resp = await admin_client.get("/api/race-analysis/admin/ai-usage")
        body = resp.json()
        # 2 failed de 3 terminales → 0.6667
        assert abs(body["fail_rate"] - 0.6667) < 0.01

    async def test_admin_shape_completo(self, admin_client, fake_db):
        """Verifica TODAS las keys del response shape (F8A regression guard)."""
        fake_db.seed_insight(cost_total=0.005, latency_total=1500)
        resp = await admin_client.get("/api/race-analysis/admin/ai-usage")
        assert resp.status_code == 200
        body = resp.json()
        expected_keys = {
            "window_days",
            "run_count",
            "cost_usd_total",
            "latency_ms_p50",
            "latency_ms_p95",
            "fail_rate",
            "by_prompt_version",
        }
        assert set(body.keys()) == expected_keys
        for entry in body["by_prompt_version"]:
            assert {"prompt_version", "run_count", "cost_usd_total"} == set(entry.keys())

    async def test_admin_zero_insights(self, admin_client):
        """Sin insights, los totales son 0 y fail_rate=0 (no division by zero)."""
        resp = await admin_client.get("/api/race-analysis/admin/ai-usage?days=7")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_count"] == 0
        assert body["cost_usd_total"] == 0.0
        assert body["fail_rate"] == 0.0
        assert body["window_days"] == 7


# ===========================================================================
# Budget guard (F8A)
# ===========================================================================


class TestBudgetGuard:
    """Integración del budget guard en POST /runs."""

    async def test_503_si_excede_presupuesto(
        self, coach_client, fake_db, ai_enabled, monkeypatch
    ):
        """Si el gasto últimos 30d >= settings.race_ai_budget_usd_30d → 503."""
        from app.config import settings
        from app.services.race.ai import budget_guard

        # Reset cooldown para que el log se emita limpio si hace falta debug.
        await budget_guard._reset_cooldown_for_tests()

        # Threshold bajo para forzar el bloqueo con seed mínimo.
        monkeypatch.setattr(settings, "race_ai_budget_usd_30d", 0.001)
        fake_db.seed_insight(cost_total=0.005, latency_total=1000)

        resp = await coach_client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": 1, "season": 2026},
        )
        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert "Presupuesto" in detail
        assert "0.005" in detail or "0.0050" in detail

    async def test_201_si_bajo_presupuesto(
        self, coach_client, fake_db, ai_enabled, monkeypatch
    ):
        """Bajo el límite, el run procede normalmente (201)."""
        from app.config import settings
        from app.services.race.ai import budget_guard

        await budget_guard._reset_cooldown_for_tests()

        monkeypatch.setattr(settings, "race_ai_budget_usd_30d", 100.0)
        fake_db.seed_insight(cost_total=0.005, latency_total=1000)

        resp = await coach_client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": 1, "season": 2026},
        )
        assert resp.status_code == 201
