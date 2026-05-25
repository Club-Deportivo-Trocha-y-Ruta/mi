"""Tests P0 — persistencia de eventos en cierre de run agéntico.

Cubren el bug detectado en producción local 2026-05-22:
- Runs terminales (`failed`/`completed`/`cancelled`) en `agent_runs` no
  emitían filas a `agent_run_events`, dejando `last_seq=0` y UI vacía.

Tests:

1. ``test_finalize_persists_state_events`` — happy path: el grafo termina
   con éxito, los eventos en memoria se persisten a la tabla.
2. ``test_finalize_synthesizes_error_event_when_exc`` — el grafo lanza
   excepción antes de emitir cualquier evento (bootstrap fail); el
   finalize sintetiza un evento ``error`` para que la UI tenga ≥1 dato.
3. ``test_finalize_run_terminal_invariant`` — invariante: cualquier run
   que termina en estado terminal tiene al menos un evento persistido.
4. ``test_finalize_is_idempotent`` — re-invocar no duplica eventos.
5. ``test_finalize_maps_node_error_to_db_error_enum`` — eventos in-memory
   con type=``node_error`` se persisten como ENUM=``error`` (compat DB).
"""

from __future__ import annotations

import pytest

from app.routers.race_analysis import _finalize_run


@pytest.mark.asyncio
async def test_finalize_persists_state_events(fake_db) -> None:
    """Eventos in-memory del grafo se persisten a agent_run_events."""
    rid = "run-happy-001"
    await fake_db.seed_run(rid, status_="running")

    result_state = {
        "events": [
            {"seq": 1, "ts": "2026-05-22T15:12:44Z", "type": "node_start",
             "node": "validate_input", "payload": {}},
            {"seq": 2, "ts": "2026-05-22T15:12:45Z", "type": "node_end",
             "node": "validate_input", "payload": {"ok": True}},
            {"seq": 3, "ts": "2026-05-22T15:12:46Z", "type": "node_start",
             "node": "load_race_data", "payload": {}},
            {"seq": 4, "ts": "2026-05-22T15:12:47Z", "type": "node_end",
             "node": "load_race_data", "payload": {}},
        ],
        "final_analysis": {"raw_markdown": "# Análisis\nContenido"},
        "rendered_markdown": "# Análisis\nContenido",
        "status": "ok",
    }

    await _finalize_run(fake_db, rid, exc=None, result_state=result_state)

    run_snap = await fake_db.get_run_dict(rid)
    persisted = await fake_db.get_events(run_snap["id"])
    assert len(persisted) == 4
    assert [e["seq"] for e in persisted] == [1, 2, 3, 4]
    assert persisted[0]["event_type"] == "node_start"
    assert persisted[0]["node_name"] == "validate_input"
    assert run_snap["status"] == "completed"


@pytest.mark.asyncio
async def test_finalize_synthesizes_error_event_when_exc(fake_db) -> None:
    """Bug bootstrap: grafo falla antes del primer evento. Sintetizar uno."""
    rid = "run-bootstrap-fail-002"
    await fake_db.seed_run(rid, status_="running")

    boom = RuntimeError("race AI db_factory no configurado")

    await _finalize_run(fake_db, rid, exc=boom, result_state=None)

    run_snap = await fake_db.get_run_dict(rid)
    persisted = await fake_db.get_events(run_snap["id"])
    assert len(persisted) == 1, "debe sintetizar 1 evento error"
    ev = persisted[0]
    assert ev["event_type"] == "error"
    assert ev["seq"] == 1
    assert ev["node_name"] is None
    import json
    payload = json.loads(ev["payload_json"]) if isinstance(ev["payload_json"], str) else ev["payload_json"]
    assert payload["exc"] == "RuntimeError"
    assert "db_factory" in payload["msg"]
    assert run_snap["status"] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param(
            {"exc": RuntimeError("boom"), "result_state": None, "expected": "failed"},
            id="exc_no_state",
        ),
        pytest.param(
            {
                "exc": None,
                "result_state": {"events": [], "status": "failed",
                                 "errors": [{"node": "x", "message": "fail"}]},
                "expected": "failed",
            },
            id="graph_status_failed",
        ),
        pytest.param(
            {
                "exc": None,
                "result_state": {"events": [], "status": "ok"},
                "expected": "failed",  # sin final_payload
            },
            id="completed_without_output",
        ),
        pytest.param(
            {
                "exc": None,
                "result_state": {
                    "events": [
                        {"seq": 1, "type": "node_start", "node": "validate_input",
                         "payload": {}, "ts": "2026-05-22T15:12:44Z"},
                    ],
                    "final_analysis": {"raw_markdown": "ok"},
                },
                "expected": "completed",
            },
            id="happy",
        ),
    ],
)
async def test_finalize_run_terminal_invariant(fake_db, scenario) -> None:
    """INV-3: status terminal ⇒ ≥1 evento persistido en agent_run_events."""
    rid = f"run-inv-{scenario['expected']}"
    await fake_db.seed_run(rid, status_="running")

    await _finalize_run(
        fake_db, rid,
        exc=scenario["exc"],
        result_state=scenario["result_state"],
    )

    run_snap = await fake_db.get_run_dict(rid)
    persisted = await fake_db.get_events(run_snap["id"])
    assert run_snap["status"] == scenario["expected"]
    assert len(persisted) >= 1, (
        f"INV-3 violado: run status={scenario['expected']} sin eventos "
        f"persistidos (escenario {scenario})"
    )


@pytest.mark.asyncio
async def test_finalize_is_idempotent(fake_db) -> None:
    """Re-invocar finalize no duplica eventos (idempotencia por seq)."""
    rid = "run-idempotent-003"
    await fake_db.seed_run(rid, status_="running")

    state = {
        "events": [
            {"seq": 1, "type": "node_start", "node": "validate_input",
             "payload": {}, "ts": "2026-05-22T15:12:44Z"},
            {"seq": 2, "type": "node_end", "node": "validate_input",
             "payload": {}, "ts": "2026-05-22T15:12:45Z"},
        ],
        "final_analysis": {"raw_markdown": "ok"},
    }

    await _finalize_run(fake_db, rid, exc=None, result_state=state)
    await _finalize_run(fake_db, rid, exc=None, result_state=state)

    run_snap = await fake_db.get_run_dict(rid)
    persisted = await fake_db.get_events(run_snap["id"])
    assert len(persisted) == 2, "segunda invocación no debe duplicar"


@pytest.mark.asyncio
async def test_finalize_detects_hitl_interrupt_as_awaiting_hitl(fake_db) -> None:
    """ainvoke retorna con __interrupt__ (HITL pause) → awaiting_hitl, no failed.

    Bug E2E secundario: cuando hitl_gate_review llama interrupt(), LangGraph
    retorna sin error pero sin final_analysis. Sin esta detección, el run
    se marcaba 'failed' por 'Grafo completó sin output'.
    """
    rid = "run-hitl-pause-005"
    await fake_db.seed_run(rid, status_="running")

    result_state = {
        "events": [
            {"seq": 1, "type": "node_start", "node": "validate_input",
             "payload": {}, "ts": "2026-05-22T15:45:00Z"},
            {"seq": 2, "type": "node_end", "node": "validate_input",
             "payload": {}, "ts": "2026-05-22T15:45:01Z"},
            {"seq": 3, "type": "node_start", "node": "hitl_gate_review",
             "payload": {}, "ts": "2026-05-22T15:45:02Z"},
        ],
        "__interrupt__": [
            {"value": {"step": "review", "draft_markdown": "# Draft"},
             "resumable": True}
        ],
    }

    await _finalize_run(fake_db, rid, exc=None, result_state=result_state)

    run_snap = await fake_db.get_run_dict(rid)
    assert run_snap["status"] == "awaiting_hitl", (
        "HITL interrupt no debe terminar el run como failed"
    )
    assert run_snap["finished_at"] is None, (
        "awaiting_hitl no es terminal — finished_at debe quedar NULL"
    )
    persisted = await fake_db.get_events(run_snap["id"])
    assert len(persisted) == 3, "los eventos previos al interrupt sí se persisten"
    types = [e["event_type"] for e in persisted]
    assert "error" not in types, "no debe sintetizar evento error en HITL pause"


@pytest.mark.asyncio
async def test_finalize_maps_node_error_to_db_error_enum(fake_db) -> None:
    """Eventos in-memory con type=node_error → ENUM DB 'error' (DataError)."""
    rid = "run-node-error-004"
    await fake_db.seed_run(rid, status_="running")

    state = {
        "events": [
            {"seq": 1, "type": "node_start", "node": "load_race_data",
             "payload": {}, "ts": "2026-05-22T15:12:44Z"},
            {"seq": 2, "type": "node_error", "node": "load_race_data",
             "payload": {"exc": "ValueError", "msg": "no data"},
             "ts": "2026-05-22T15:12:45Z"},
        ],
        "status": "failed",
        "errors": [{"node": "load_race_data", "message": "no data"}],
    }

    await _finalize_run(fake_db, rid, exc=None, result_state=state)

    run_snap = await fake_db.get_run_dict(rid)
    persisted = await fake_db.get_events(run_snap["id"])
    types = [e["event_type"] for e in persisted]
    assert types == ["node_start", "error"], (
        f"node_error in-memory debe mapearse a ENUM 'error' en DB, fue {types}"
    )
    assert run_snap["status"] == "failed"
