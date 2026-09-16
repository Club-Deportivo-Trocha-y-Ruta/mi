"""US3 (feature 011): the critic reviews ALL drafts of a batch, not just one.

Regression: the critic node only read singular ``draft_analysis`` → in a
group run of N válidas, N-1 drafts went unreviewed.
"""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes import critic_agent as mod
from tests.helpers.ai_stubs import StubCriticAgentV2, contradiction_verdict, make_v2_output


@pytest.mark.asyncio
async def test_critic_reviews_all_drafts():
    stub = StubCriticAgentV2()
    state = {
        "_critic_agent": stub,
        "per_valida_drafts": {
            3: make_v2_output(),
            4: make_v2_output(),
            5: make_v2_output(),
        },
        "event_conditions": {3: {}, 4: {}, 5: {}},
        "full_season_results": [],
        "podium_context": {},
    }
    update = await mod.critic_agent(state)
    verdicts = update["per_valida_verdicts"]
    assert set(verdicts.keys()) == {3, 4, 5}
    assert stub.invoke_v2_calls == 3
    # Compat: singular critic_feedback kept (first válida).
    assert "critic_feedback" in update


@pytest.mark.asyncio
async def test_critic_flags_contradiction_with_ground_truth():
    stub = StubCriticAgentV2(verdicts=[contradiction_verdict()])
    state = {
        "_critic_agent": stub,
        "per_valida_drafts": {4: make_v2_output()},
        "event_conditions": {
            4: {
                "climate": "Nublado",
                "temperature_c": 25.0,
                "surface_condition": "humeda",
                "altitude_msnm": 1000,
                "weather_notes": None,
            }
        },
        "full_season_results": [
            {"valida_num": 4, "position": 2, "race_time_ms": 2_050_000,
             "gap_to_winner_ms": 30_000}
        ],
        "podium_context": {"podium": [{"position": 1, "race_time_ms": 2_020_000}]},
    }
    update = await mod.critic_agent(state)
    verdict = update["per_valida_verdicts"][4]
    assert verdict.approved is False
    # The ground truth threaded to the critic includes the recorded surface.
    gt = stub.captured_ground_truth[0]
    assert "Húmeda" in gt
    assert "Posición: 2" in gt


@pytest.mark.asyncio
async def test_critic_caps_at_four_drafts():
    stub = StubCriticAgentV2()
    state = {
        "_critic_agent": stub,
        "per_valida_drafts": {1: make_v2_output(), 2: make_v2_output(),
                              3: make_v2_output(), 4: make_v2_output(),
                              5: make_v2_output()},
        "event_conditions": {},
        "full_season_results": [],
        "podium_context": {},
    }
    await mod.critic_agent(state)
    assert stub.invoke_v2_calls == 4


@pytest.mark.asyncio
async def test_critic_ground_truth_finds_row_from_load_race_data_output(
    monkeypatch, configure_db_factory, fake_session
):
    """Regresión end-to-end (feature 037, T101): el ``full_season_results``
    que produce ``load_race_data`` (con el fix de ``valida_num``) debe ser
    encontrable por ``critic_agent._build_ground_truth``. Antes del fix,
    ``valida_num`` era siempre ``None`` en ``load_race_data`` → el critic
    nunca encontraba la fila del atleta y siempre reportaba "sin fila de
    resultado registrada".
    """
    from datetime import date

    from app.services.race.ai.nodes import load_race_data as load_mod

    class _FakeResult:
        def __init__(self, *, id, event_id, category_id, competitor_id,
                     athlete_id, position, race_time_ms, status=None):
            self.id = id
            self.event_id = event_id
            self.category_id = category_id
            self.competitor_id = competitor_id
            self.athlete_id = athlete_id
            self.position = position
            self.race_time_ms = race_time_ms
            self.points_awarded = 20
            self.status = status

    class _FakeEvent:
        def __init__(self, *, id, series_id, sequence_number, event_date):
            self.id = id
            self.series_id = series_id
            self.sequence_number = sequence_number
            self.event_date = event_date

    configure_db_factory(fake_session)

    rs = [
        _FakeResult(id=1, event_id=14, category_id=7, competitor_id=22,
                    athlete_id=1, position=2, race_time_ms=2_050_000),
    ]
    events = [_FakeEvent(id=14, series_id=1, sequence_number=4, event_date=date(2026, 5, 17))]

    async def _fake_fetch_results(db, aid, season, valida_nums=None, series_id=None):
        return rs

    async def _fake_fetch_podium(db, cat, evt):
        return {"category_id": cat, "event_id": evt, "podium": [], "finishers_count": 0}

    async def _fake_fetch_all_season(db, cat, season):
        return rs

    async def _fake_load_events(db):
        return events

    monkeypatch.setattr(load_mod, "fetch_results_for_athlete", _fake_fetch_results)
    monkeypatch.setattr(load_mod, "fetch_podium_context", _fake_fetch_podium)
    monkeypatch.setattr(load_mod, "fetch_all_results_for_season", _fake_fetch_all_season)
    monkeypatch.setattr(load_mod, "load_events", _fake_load_events)

    load_update = await load_mod.load_race_data({"athlete_id": 1, "season": 2026})
    assert load_update["full_season_results"][0]["valida_num"] == 4

    stub = StubCriticAgentV2()
    critic_state = {
        "_critic_agent": stub,
        "per_valida_drafts": {4: make_v2_output()},
        "event_conditions": {4: {}},
        "full_season_results": load_update["full_season_results"],
        "podium_context": {},
    }
    await mod.critic_agent(critic_state)
    gt = stub.captured_ground_truth[0]
    assert "sin fila de resultado registrada" not in gt
    assert "Posición: 2" in gt


# ---------------------------------------------------------------------------
# Hotfix identidad de válida (multicopa): ancla por event_id + etiqueta de
# copa + agrupación por evento en runs de temporada.
# ---------------------------------------------------------------------------


def test_ground_truth_picks_anchored_event_row_not_other_series_same_valida():
    """Copa A y Copa B comparten valida_num=4 (spec 014) — sin ancla, el
    lookup por valida_num tomaría la primera fila de la lista (Copa A) sin
    importar cuál se está analizando. Con ``state["event_id"]`` anclado al
    evento de Copa B, la fila resuelta debe ser la de Copa B."""
    full_season = [
        {
            "event_id": 101,
            "valida_num": 4,
            "series_id": 1,
            "series_name": "Copa A",
            "position": 2,
            "race_time_ms": 2_000_000,
            "gap_to_winner_ms": 30_000,
        },
        {
            "event_id": 202,
            "valida_num": 4,
            "series_id": 2,
            "series_name": "Copa B",
            "series_short_name": "Copa B corta",
            "position": 7,
            "race_time_ms": 2_300_000,
            "gap_to_winner_ms": 90_000,
        },
    ]
    state = {"event_id": 202, "full_season_results": full_season}
    text = mod._build_ground_truth(state, 4)
    assert "Posición: 7" in text
    assert "Posición: 2" not in text
    assert "- Copa: Copa B corta" in text


def test_ground_truth_falls_back_to_valida_num_without_anchor():
    full_season = [
        {
            "event_id": 101,
            "valida_num": 4,
            "series_name": "Copa A",
            "position": 2,
            "race_time_ms": 2_000_000,
            "gap_to_winner_ms": 30_000,
        }
    ]
    text = mod._build_ground_truth({"full_season_results": full_season}, 4)
    assert "Posición: 2" in text
    assert "- Copa: Copa A" in text


def test_season_ground_truth_groups_conditions_by_event_across_two_cups():
    full_season = [
        {"event_id": 101, "valida_num": 4, "series_name": "Copa A"},
        {"event_id": 202, "valida_num": 4, "series_name": "Copa B", "series_short_name": "Copa B corta"},
    ]
    state = {
        "analysis_kind": "season",
        "full_season_results": full_season,
        "event_conditions_by_event": {
            101: {
                "climate": "Soleado",
                "temperature_c": 28.0,
                "surface_condition": "seca",
                "altitude_msnm": 1200,
                "weather_notes": None,
            },
            202: {
                "climate": "Lluvia",
                "temperature_c": 18.0,
                "surface_condition": "humeda",
                "altitude_msnm": 900,
                "weather_notes": None,
            },
        },
    }
    text = mod._build_ground_truth(state, 0)
    assert "Válida 4 · Copa A:" in text
    assert "Válida 4 · Copa B corta:" in text
    assert "Soleado" in text
    assert "Lluvia" in text


def test_season_ground_truth_course_groups_by_event_and_omits_missing():
    course_entry = {
        "lap_distance_m": 4200,
        "elevation_gain_m": 110,
        "laps": 3,
        "terrain_type": "mixto",
        "technical_difficulty": 4,
        "key_sectors": ["subida_larga"],
    }
    full_season = [
        {"event_id": 101, "valida_num": 3, "series_name": "Copa A"},
        {"event_id": 202, "valida_num": 3, "series_name": "Copa B", "series_short_name": "Copa B corta"},
    ]
    state = {
        "analysis_kind": "season",
        "full_season_results": full_season,
        "course_context_by_event": {101: course_entry, 202: None},
    }
    text = mod._build_ground_truth(state, 0, include_course=True)
    assert "Válida 3 · Copa A:" in text
    assert "Distancia por vuelta" in text
    # Veto de ausencia (igual que el analista): sin dato de circuito, el
    # evento de Copa B no aparece con encabezado propio.
    assert "Válida 3 · Copa B corta:" not in text
