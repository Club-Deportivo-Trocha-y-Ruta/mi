"""Tests del nodo compute_metrics.

Feature 044 (candado de terceros, FR-012…FR-015): ``compute_metrics`` llama
``require_club_competitor(db, competitor_id)`` como primera operación del
nodo, así que todo test del camino feliz declara su competidor como
vinculado con ``fake_session.link_competitor(...)``. El rechazo del
competidor ajeno se prueba acá mismo (``test_compute_metrics_refuses_*``) y,
a nivel de servicio, en ``tests/privacy/test_third_party_lock.py``.
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.services.race.ai.nodes import compute_metrics as mod
from app.services.race.third_party_guard import ThirdPartyProgressionForbidden


@pytest.mark.asyncio
async def test_compute_metrics_serializes_dataframes(monkeypatch, configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    fake_session.link_competitor(22)
    prog = pd.DataFrame([{"valida_num": 1, "position": 2}])
    podium = pd.DataFrame([{"competitor_id": 22, "gap_to_p1_ms": 1500}])

    async def _ap(db, cid):
        return prog

    async def _pg(db, cat, season):
        return podium

    monkeypatch.setattr(mod, "athlete_progression", _ap)
    monkeypatch.setattr(mod, "podium_gap", _pg)

    state = {"competitor_id": 22, "category_id": 7, "season": 2026}
    update = await mod.compute_metrics(state)
    assert update["metrics"]["progression"][0]["valida_num"] == 1
    assert update["metrics"]["podium_gap"][0]["gap_to_p1_ms"] == 1500


@pytest.mark.asyncio
async def test_compute_metrics_no_competitor(configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    update = await mod.compute_metrics({"competitor_id": None, "category_id": None, "season": 2026})
    assert update["metrics"] == {}


# ---------------------------------------------------------------------------
# Candado de terceros (feature 044, FR-012…FR-015)
#
# El candado se aplica DENTRO del nodo, explícito y antes de cualquier carga.
# El barrido estructural de tests/privacy/test_third_party_lock.py no puede
# vigilar este punto: ``compute_metrics`` recibe ``state``, no un parámetro
# ``competitor_id``. Estos dos tests son, por tanto, la única red que impide
# que un reordenamiento del nodo (o mover la llamada guardada dentro de un
# condicional) deje pasar a un tercero sin que nadie se entere.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_metrics_refuses_unlinked_competitor(
    monkeypatch, configure_db_factory, fake_session
):
    """Competidor que existe pero no está vinculado → el nodo aborta.

    ``athlete_progression`` / ``podium_gap`` se patchean con funciones que
    registrarían su llamada: la prueba es que NO se llaman, es decir que el
    candado corta antes de cargar dato alguno del tercero.
    """
    configure_db_factory(fake_session)
    fake_session.seed_competitor(22, athlete_id=None)

    calls: list[str] = []

    async def _ap(db, cid):
        calls.append("athlete_progression")
        return pd.DataFrame()

    async def _pg(db, cat, season):
        calls.append("podium_gap")
        return pd.DataFrame()

    monkeypatch.setattr(mod, "athlete_progression", _ap)
    monkeypatch.setattr(mod, "podium_gap", _pg)

    with pytest.raises(ThirdPartyProgressionForbidden) as exc_info:
        await mod.compute_metrics({"competitor_id": 22, "category_id": 7, "season": 2026})

    assert exc_info.value.reason == "not_linked"
    assert calls == []


@pytest.mark.asyncio
async def test_compute_metrics_refuses_unknown_competitor(
    configure_db_factory, fake_session
):
    """``competitor_id`` inexistente → mismo rechazo, distinto ``reason``."""
    configure_db_factory(fake_session)

    with pytest.raises(ThirdPartyProgressionForbidden) as exc_info:
        await mod.compute_metrics({"competitor_id": 99999, "category_id": 7, "season": 2026})

    assert exc_info.value.reason == "unknown_competitor"


@pytest.mark.asyncio
async def test_compute_metrics_refusal_is_not_retried(
    configure_db_factory, fake_session, caplog
):
    """El rechazo NO se reintenta pese al ``@with_retry`` del nodo.

    ``ThirdPartyProgressionForbidden`` hereda de ``PermissionError`` →
    ``OSError``, que sí está en ``retry.RETRYABLE_EXCEPTIONS``; sin la
    exclusión ``non_retryable`` del nodo, un solo intento de acceso a un
    tercero produciría 3 consultas y 3 líneas de rechazo en el log.
    """
    import logging

    configure_db_factory(fake_session)
    fake_session.seed_competitor(22, athlete_id=None)

    caplog.set_level(logging.WARNING)
    with pytest.raises(ThirdPartyProgressionForbidden):
        await mod.compute_metrics({"competitor_id": 22, "category_id": 7, "season": 2026})

    assert caplog.text.count("third_party_progression_refused") == 1


@pytest.mark.asyncio
async def test_refusal_event_does_not_carry_the_competitor_id(
    configure_db_factory, fake_session
):
    """El evento ``node_error`` persistido no lleva el ``competitor_id``.

    Condición de cierre de la auditoría de privacidad (T036): ``with_events``
    guarda el mensaje de la excepción en ``state["errors"]`` y en el payload
    del evento, que termina en ``agent_run_events`` y se sirve por
    ``GET /race-analysis/runs/{run_id}/status``. El ``str()`` de
    ``ThirdPartyProgressionForbidden`` lleva el id —útil en el log del
    servidor— así que la excepción declara un ``event_safe_message`` que es
    lo único que se publica.
    """
    configure_db_factory(fake_session)
    fake_session.seed_competitor(31337, athlete_id=None)

    state: dict = {"competitor_id": 31337, "category_id": 7, "season": 2026}
    with pytest.raises(ThirdPartyProgressionForbidden):
        await mod.compute_metrics(state)

    error_event = state["events"][-1]
    assert error_event["type"] == "node_error"
    assert error_event["payload"]["exc"] == "ThirdPartyProgressionForbidden"
    assert "31337" not in error_event["payload"]["msg"]
    assert "31337" not in state["errors"][0]["message"]
    # El código sí queda, para que el operador sepa qué pasó sin el id.
    assert "third_party_progression_forbidden" in error_event["payload"]["msg"]


# ---------------------------------------------------------------------------
# progression_groups (feature 039 — season comparison groups, T030)
#
# contracts/ai-context.md: "metrics.progression_groups | compute_metrics |
# NEW {'cups': {'<series_id>': [rows]}, 'championships': [rows]}" — built
# from metrics.progression via comparison_groups.split_progression.
# metrics.progression itself stays flat and unchanged.
# ---------------------------------------------------------------------------

_PROGRESSION_ROWS_039 = [
    {
        "event_id": 11,
        "series_id": 1,
        "series_kind": "cup",
        "series_level": "departmental",
        "series_name": "Copa Valle",
        "season_year": 2026,
        "event_date": "2026-03-01",
        "valida_num": 1,
        "position": 5,
    },
    {
        "event_id": 12,
        "series_id": 1,
        "series_kind": "cup",
        "series_level": "departmental",
        "series_name": "Copa Valle",
        "season_year": 2026,
        "event_date": "2026-04-01",
        "valida_num": 2,
        "position": 3,
    },
    {
        "event_id": 90,
        "series_id": 2,
        "series_kind": "championship",
        "series_level": "departmental",
        "series_name": "Cto. Departamental Valle",
        "season_year": 2026,
        "event_date": "2026-05-01",
        "valida_num": 1,
        "position": 1,
    },
]


@pytest.mark.asyncio
async def test_compute_metrics_emits_progression_groups(
    monkeypatch, configure_db_factory, fake_session
):
    """metrics.progression stays flat (compat) and metrics.progression_groups
    splits it into cups (by series_id) / championships (research.md D9)."""
    configure_db_factory(fake_session)
    fake_session.link_competitor(22)
    prog = pd.DataFrame(_PROGRESSION_ROWS_039)

    async def _ap(db, cid):
        return prog

    async def _pg(db, cat, season):
        return pd.DataFrame()

    monkeypatch.setattr(mod, "athlete_progression", _ap)
    monkeypatch.setattr(mod, "podium_gap", _pg)

    update = await mod.compute_metrics({"competitor_id": 22, "category_id": 7, "season": 2026})

    # metrics.progression: flat, unchanged, same row order.
    assert [r["event_id"] for r in update["metrics"]["progression"]] == [11, 12, 90]

    progression_groups = update["metrics"].get("progression_groups")
    assert progression_groups is not None, (
        "compute_metrics no emite metrics.progression_groups todavía "
        "(pendiente T033: split_progression sobre metrics.progression)"
    )
    # F-7: las claves de "cups" son str (contracts/ai-context.md: "<series_id>").
    assert set(progression_groups["cups"].keys()) == {"1"}
    assert [r["event_id"] for r in progression_groups["cups"]["1"]] == [11, 12]
    assert [r["event_id"] for r in progression_groups["championships"]] == [90]


@pytest.mark.asyncio
async def test_season_comparative_receives_anchored_event_id(
    monkeypatch, configure_db_factory, fake_session
):
    """El event_id del lanzamiento anclado debe llegar a
    _compute_season_comparative como anchored_event_id (contracts/ai-context.md
    regla 1 — nunca resolver la carrera analizada solo por valida_num)."""
    configure_db_factory(fake_session)
    fake_session.link_competitor(22)
    captured: dict = {}

    def _fake_compute_season_comparative(full_season_results, analyzed_valida_nums, **kwargs):
        captured["args"] = (full_season_results, analyzed_valida_nums)
        captured["kwargs"] = kwargs
        return [], "first_reference"

    async def _ap(db, cid):
        return pd.DataFrame(_PROGRESSION_ROWS_039)

    async def _pg(db, cat, season):
        return pd.DataFrame()

    monkeypatch.setattr(mod, "athlete_progression", _ap)
    monkeypatch.setattr(mod, "podium_gap", _pg)
    monkeypatch.setattr(mod, "_compute_season_comparative", _fake_compute_season_comparative)

    state = {
        "competitor_id": 22,
        "category_id": 7,
        "season": 2026,
        "event_id": 90,
        "valida_nums": [1],
        "full_season_results": [
            {
                "result_id": 1,
                "event_id": 90,
                "valida_num": 1,
                "series_id": 2,
                "series_kind": "championship",
                "series_level": "departmental",
                "event_date": "2026-05-01",
                "position": 1,
                "race_time_ms": 3_000_000,
                "gap_to_winner_ms": 0,
                "gap_pct": 0.0,
                "status": "finished",
            },
        ],
    }
    await mod.compute_metrics(state)

    assert captured.get("kwargs", {}).get("anchored_event_id") == 90
