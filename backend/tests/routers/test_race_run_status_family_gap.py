"""``GET /api/race-analysis/runs/{run_id}/status`` — ``family_gap_mentions`` (feature 045, T031, FR-022).

El evento ``hitl_request`` (el que lleva el borrador a aprobar) recibe
``family_gap_mentions: list[str]`` calculado al leer, sólo con los campos del
borrador que ve la familia. Reglas:

- Coach/admin: la clave está SIEMPRE en el ``hitl_request`` (``[]`` si el texto
  está limpio).
- Padre: 403 en el endpoint — nunca recibe la clave (se excluye, no es ``null``).
- Los demás eventos no llevan la clave.
- No se persiste: el payload guardado en ``agent_run_events`` queda intacto.

Texto ficticio únicamente; nada del borrador se registra en logs.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

pytestmark = pytest.mark.asyncio

STATUS_URL = "/api/race-analysis/runs/{run_id}/status"


def _structured(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": "v3",
        "headline": "Avance sostenido en el descenso técnico.",
        "field_reading": {
            "percentile": 62.0,
            "expected_position": 5,
            "actual_position": 4,
            "delta_vs_expected": 1,
            "gap_to_p3_hhmmss": "0:01:12",
            "series_label": "Copa regional",
            "summary": "Mantuvo un ritmo estable dentro del pelotón.",
        },
        "trend": "improving",
        "observations": [
            {
                "claim": "Sostuvo la cadencia en la subida.",
                "evidence": ["percentil 62"],
                "domain": "race",
                "confidence": "medium",
            },
            {
                "claim": "Acumuló buena carga esta semana.",
                "evidence": ["4 sesiones"],
                "domain": "training",
                "confidence": "medium",
            },
        ],
        "actions": [
            {"text": "Practicar curvas cerradas dos veces por semana.", "category": "technique"},
            {"text": "Dormir bien antes de la próxima carrera.", "category": "recovery"},
        ],
        "watch_signals": [],
        "coach_question": "¿Cómo se sintió en la última subida?",
        "data_gaps": [],
        "principles_cited": [],
    }
    base.update(overrides)
    return base


def _hitl_payload(structured: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "step": "review",
        "draft_markdown": "## Hallazgo principal\nTexto del borrador.\n",
        "pseudonym": "Atleta-01",
        "structured_draft": structured,
        "structured_drafts": {"1": structured} if structured else {},
        "critic": {"approved": True, "must_block": False, "severity": None},
    }


def _seed_hitl_run(fake_db: Any, run_id: str, payload: dict[str, Any], *, user_id: int = 10) -> dict:
    run = fake_db.seed_run(run_id, status_="awaiting_hitl", requested_by_user_id=user_id)
    fake_db.seed_event(run["id"], 1, "node_start", "validate_input", {"note": "sin borrador"})
    fake_db.seed_event(run["id"], 2, "hitl_request", "hitl_gate_review", payload)
    return run


def _hitl_event(body: dict[str, Any]) -> dict[str, Any]:
    (event,) = [e for e in body["new_events"] if e["type"] == "hitl_request"]
    return event


class TestCoachSeesMentions:
    async def test_coach_recibe_menciones_del_texto_visible_para_la_familia(
        self, coach_client, fake_db
    ):
        draft = _structured(headline="Terminó con una brecha de 9.4% al líder de la categoría.")
        _seed_hitl_run(fake_db, "run-gap-1", _hitl_payload(draft))

        resp = await coach_client.get(STATUS_URL.format(run_id="run-gap-1"))

        assert resp.status_code == 200
        mentions = _hitl_event(resp.json())["payload"]["family_gap_mentions"]
        assert isinstance(mentions, list) and 1 <= len(mentions) <= 3
        assert all(isinstance(m, str) and len(m) <= 80 for m in mentions)
        assert any("líder" in m for m in mentions)

    async def test_texto_limpio_devuelve_lista_vacia_no_ausente(self, coach_client, fake_db):
        _seed_hitl_run(fake_db, "run-gap-clean", _hitl_payload(_structured()))

        resp = await coach_client.get(STATUS_URL.format(run_id="run-gap-clean"))

        payload = _hitl_event(resp.json())["payload"]
        assert "family_gap_mentions" in payload
        assert payload["family_gap_mentions"] == []

    async def test_admin_tambien_recibe_las_menciones(self, admin_client, fake_db):
        draft = _structured(actions=[
            {"text": "Buscar el podio en la próxima válida.", "category": "tactics"},
            {"text": "Dormir bien antes de la carrera.", "category": "recovery"},
        ])
        _seed_hitl_run(fake_db, "run-gap-admin", _hitl_payload(draft), user_id=1)

        resp = await admin_client.get(STATUS_URL.format(run_id="run-gap-admin"))

        assert resp.status_code == 200
        mentions = _hitl_event(resp.json())["payload"]["family_gap_mentions"]
        assert any("podio" in m for m in mentions)

    async def test_maximo_tres_menciones(self, coach_client, fake_db):
        draft = _structured(
            headline="Brecha al líder de 9%.",
            actions=[
                {"text": "Mirar el podio sin obsesionarse.", "category": "psychology"},
                {"text": "Acercarse al P3 con paciencia.", "category": "tactics"},
            ],
            watch_signals=["No compararse con la ganadora.", "Evitar pensar en el primer lugar."],
        )
        _seed_hitl_run(fake_db, "run-gap-cap", _hitl_payload(draft))

        resp = await coach_client.get(STATUS_URL.format(run_id="run-gap-cap"))

        assert len(_hitl_event(resp.json())["payload"]["family_gap_mentions"]) == 3

    async def test_borrador_sin_estructura_escanea_el_markdown(self, coach_client, fake_db):
        payload = _hitl_payload(None)
        payload["draft_markdown"] = "## Qué pasó\nLa brecha al líder fue de 9%.\n"
        _seed_hitl_run(fake_db, "run-gap-md", payload)

        resp = await coach_client.get(STATUS_URL.format(run_id="run-gap-md"))

        mentions = _hitl_event(resp.json())["payload"]["family_gap_mentions"]
        assert any("líder" in m for m in mentions)


class TestOnlyFamilyVisibleFields:
    async def test_campos_solo_coach_no_disparan_el_aviso(self, coach_client, fake_db):
        # coach_question y gap_to_p3 son coach-only (la API los omite al padre),
        # y el markdown v3 es la proyección de la vista del coach.
        draft = _structured(coach_question="¿Le preocupa el podio o el P3 esta temporada?")
        payload = _hitl_payload(draft)
        payload["draft_markdown"] = (
            "## Lectura del pelotón\ngap a P3 0:01:12\n## Pregunta para el coach\n¿Podio?\n"
        )
        _seed_hitl_run(fake_db, "run-gap-coach-only", payload)

        resp = await coach_client.get(STATUS_URL.format(run_id="run-gap-coach-only"))

        assert _hitl_event(resp.json())["payload"]["family_gap_mentions"] == []

    async def test_evidencia_de_observacion_training_no_dispara_el_aviso(
        self, coach_client, fake_db
    ):
        draft = _structured(observations=[
            {"claim": "Sostuvo la cadencia.", "evidence": ["percentil 62"], "domain": "race"},
            {"claim": "Buena carga semanal.", "evidence": ["a 2 min del líder"], "domain": "training"},
        ])
        _seed_hitl_run(fake_db, "run-gap-train-ev", _hitl_payload(draft))

        resp = await coach_client.get(STATUS_URL.format(run_id="run-gap-train-ev"))

        assert _hitl_event(resp.json())["payload"]["family_gap_mentions"] == []


class TestKeyScope:
    async def test_solo_el_evento_hitl_request_lleva_la_clave(self, coach_client, fake_db):
        _seed_hitl_run(fake_db, "run-gap-scope", _hitl_payload(_structured()))

        resp = await coach_client.get(STATUS_URL.format(run_id="run-gap-scope"))

        for event in resp.json()["new_events"]:
            if event["type"] == "hitl_request":
                assert "family_gap_mentions" in event["payload"]
            else:
                assert "family_gap_mentions" not in event["payload"]

    async def test_no_muta_ni_persiste_el_payload_almacenado(self, coach_client, fake_db):
        draft = _structured(headline="Brecha al líder de 9%.")
        payload = _hitl_payload(draft)
        run = _seed_hitl_run(fake_db, "run-gap-nopersist", payload)
        before = copy.deepcopy(fake_db.events_by_run_db_id[run["id"]])

        resp = await coach_client.get(STATUS_URL.format(run_id="run-gap-nopersist"))

        assert resp.status_code == 200
        assert "family_gap_mentions" in _hitl_event(resp.json())["payload"]
        assert fake_db.events_by_run_db_id[run["id"]] == before
        assert not any("INSERT INTO agent_run_events" in sql for sql, _ in fake_db.executed)

    async def test_payload_del_evento_conserva_el_resto_de_las_claves(self, coach_client, fake_db):
        _seed_hitl_run(fake_db, "run-gap-keys", _hitl_payload(_structured()))

        resp = await coach_client.get(STATUS_URL.format(run_id="run-gap-keys"))

        payload = _hitl_event(resp.json())["payload"]
        assert payload["step"] == "review"
        assert payload["critic"]["approved"] is True
        assert payload["structured_draft"]["headline"].startswith("Avance sostenido")


class TestParentNeverReceivesField:
    async def test_403_padre_y_la_clave_no_aparece_en_el_cuerpo(self, parent_client, fake_db):
        draft = _structured(headline="Brecha de 9.4% al líder.")
        _seed_hitl_run(fake_db, "run-gap-parent", _hitl_payload(draft))

        resp = await parent_client.get(STATUS_URL.format(run_id="run-gap-parent"))

        assert resp.status_code == 403
        assert "family_gap_mentions" not in resp.text
        assert "líder" not in resp.text

    async def test_403_padre_tampoco_con_since_ni_etag(self, parent_client, fake_db):
        _seed_hitl_run(fake_db, "run-gap-parent2", _hitl_payload(_structured()))

        resp = await parent_client.get(
            STATUS_URL.format(run_id="run-gap-parent2") + "?since=0",
            headers={"If-None-Match": 'W/"run-gap-parent2:2:awaiting_hitl"'},
        )

        assert resp.status_code == 403
        assert "family_gap_mentions" not in resp.text

    async def test_sin_token_no_hay_datos(self, anon_client):
        resp = await anon_client.get(STATUS_URL.format(run_id="run-gap-anon"))

        assert resp.status_code in (401, 403)
        assert "family_gap_mentions" not in resp.text
