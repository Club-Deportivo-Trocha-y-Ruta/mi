"""T023 — AI node tests for coach_note feature (013-race-result-athlete-notes).

Covers:
1. _serialize_result includes coach_note when present, omits key when None.
2. After anonymize node, coach_notes_by_valida values are scrubbed of forbidden names.
3. analyst_agent (v2) injects scrubbed coach note into race_meta when note exists.
4. When note is None, race_meta is unchanged / not extended (FR-009 regression).

NOT covered here (owned by data-privacy-guard in test_race_analysis_privacy.py):
- Real-name-leakage property tests on prompts/logs.
- Parent/athlete-facing response leakage.

Patterns mirror existing test_load_race_data.py and test_anonymize.py in this package:
- Uses configure_db_factory / fake_session fixtures from conftest.py.
- No real DB, no real Gemini, no network.
- FakeResult / monkeypatch style.
"""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes import load_race_data as lrd_mod
from app.services.race.ai.nodes.anonymize import anonymize, _scrub_note
from app.services.race.ai.nodes.analyst_agent import analyst_agent
from tests.services.race.ai.conftest import FakeAnalystAgent, make_analysis_output


# ---------------------------------------------------------------------------
# Minimal fake ORM objects
# ---------------------------------------------------------------------------


class _FakeStatus:
    def __init__(self, value: str):
        self.value = value


class _FakeResult:
    """Minimal ORM-like object with coach_note attribute."""

    def __init__(
        self,
        *,
        id: int,
        event_id: int,
        category_id: int,
        competitor_id: int,
        athlete_id: int | None,
        position: int | None = 1,
        race_time_ms: int | None = 200_000,
        points_awarded: int = 40,
        coach_note: str | None = None,
    ):
        self.id = id
        self.event_id = event_id
        self.category_id = category_id
        self.competitor_id = competitor_id
        self.athlete_id = athlete_id
        self.position = position
        self.race_time_ms = race_time_ms
        self.points_awarded = points_awarded
        self.status = _FakeStatus("finished")
        self.coach_note = coach_note


# ---------------------------------------------------------------------------
# 1. _serialize_result — coach_note present / absent
# ---------------------------------------------------------------------------


class TestSerializeResultCoachNote:
    """Unit tests for _serialize_result helper in load_race_data."""

    def test_serialize_includes_coach_note_when_present(self):
        """When coach_note is set, the serialized dict must include the key."""
        r = _FakeResult(
            id=1, event_id=11, category_id=7, competitor_id=22,
            athlete_id=1,
            coach_note="Corredor ficticio gestionó bien el primer sector.",
        )
        row = lrd_mod._serialize_result(r)
        assert "coach_note" in row
        assert row["coach_note"] == "Corredor ficticio gestionó bien el primer sector."

    def test_serialize_omits_coach_note_key_when_none(self):
        """When coach_note is None, the key must be absent (not present as None).

        This is the FR-009 contract: downstream code detects absence with
        `.get("coach_note")` — an absent key and a None value have the same
        semantics but absence is the canonical encoding.
        """
        r = _FakeResult(
            id=2, event_id=11, category_id=7, competitor_id=22,
            athlete_id=1,
            coach_note=None,
        )
        row = lrd_mod._serialize_result(r)
        assert "coach_note" not in row

    def test_serialize_result_id_always_present(self):
        """result_id is always included regardless of note."""
        r = _FakeResult(id=99, event_id=11, category_id=7, competitor_id=5, athlete_id=None)
        row = lrd_mod._serialize_result(r)
        assert row["result_id"] == 99

    def test_serialize_includes_standard_fields(self):
        """Standard result fields are always present."""
        r = _FakeResult(
            id=3, event_id=11, category_id=7, competitor_id=22,
            athlete_id=1, position=2, race_time_ms=205_000, points_awarded=35,
        )
        row = lrd_mod._serialize_result(r)
        for field in ("result_id", "event_id", "category_id", "competitor_id",
                      "athlete_id", "position", "race_time_ms", "points_awarded", "status"):
            assert field in row, f"Field '{field}' missing from serialized result"


# ---------------------------------------------------------------------------
# 2. anonymize — coach_notes_by_valida scrubbing
# ---------------------------------------------------------------------------


class TestAnonymizeCoachNotesScrubbing:
    """Tests that anonymize scrubs forbidden names from coach_notes_by_valida."""

    @pytest.mark.asyncio
    async def test_scrub_forbidden_name_in_coach_note(self, configure_db_factory, fake_session):
        """A real name injected into a coach note must be scrubbed by anonymize."""
        configure_db_factory(fake_session)
        forbidden_name = "Mariana García Ficticia"
        note_with_name = f"Nota: {forbidden_name} tuvo una caída en curva 3."

        state = {
            "athlete_id": 42,
            "competitor_id": 100,
            "run_id": "test-run-scrub",
            "raw_data": [
                {"athlete_id": 42, "competitor_id": 100, "position": 1,
                 "coach_note": note_with_name},
            ],
            "coach_notes_by_valida": {4: note_with_name},
            "forbidden_names": [forbidden_name, "Mariana"],
        }

        update = await anonymize(state)

        assert "coach_notes_by_valida" in update
        scrubbed = update["coach_notes_by_valida"][4]
        assert scrubbed is not None
        # Forbidden name must not appear in the scrubbed note
        assert forbidden_name not in scrubbed
        assert "Mariana" not in scrubbed

    @pytest.mark.asyncio
    async def test_none_note_stays_none_in_coach_notes_by_valida(
        self, configure_db_factory, fake_session
    ):
        """None notes in coach_notes_by_valida remain None after anonymize (FR-009)."""
        configure_db_factory(fake_session)

        state = {
            "athlete_id": 7,
            "competitor_id": 22,
            "run_id": "test-run-none",
            "raw_data": [{"athlete_id": 7, "competitor_id": 22, "position": 1}],
            "coach_notes_by_valida": {1: None, 2: None},
            "forbidden_names": ["Sofia", "Thiago"],
        }

        update = await anonymize(state)

        assert "coach_notes_by_valida" in update
        assert update["coach_notes_by_valida"][1] is None
        assert update["coach_notes_by_valida"][2] is None

    @pytest.mark.asyncio
    async def test_note_passes_through_without_forbidden_names(
        self, configure_db_factory, fake_session
    ):
        """Note text without forbidden names passes through unchanged."""
        configure_db_factory(fake_session)
        note = "Corredor ficticio tuvo buen ritmo de pedaleo."

        state = {
            "athlete_id": 5,
            "competitor_id": 50,
            "run_id": "test-run-passthrough",
            "raw_data": [{"athlete_id": 5, "competitor_id": 50, "position": 3,
                          "coach_note": note}],
            "coach_notes_by_valida": {3: note},
            "forbidden_names": [],  # no forbidden names → passthrough
        }

        update = await anonymize(state)

        assert update["coach_notes_by_valida"][3] == note

    @pytest.mark.asyncio
    async def test_empty_coach_notes_by_valida_not_added_to_update(
        self, configure_db_factory, fake_session
    ):
        """When coach_notes_by_valida is empty/absent, anonymize does not inject it."""
        configure_db_factory(fake_session)

        state = {
            "athlete_id": 8,
            "competitor_id": 88,
            "run_id": "test-run-empty-notes",
            "raw_data": [{"athlete_id": 8, "competitor_id": 88, "position": 1}],
            # coach_notes_by_valida intentionally absent
        }

        update = await anonymize(state)

        # Key should not appear in update when there is nothing to scrub
        assert "coach_notes_by_valida" not in update

    @pytest.mark.asyncio
    async def test_scrub_note_helper_removes_name(self):
        """Direct unit test of _scrub_note helper: forbidden names are removed."""
        raw = "Atleta Juan Pérez Ficticio manejó bien la bajada."
        forbidden = ["Juan Pérez Ficticio", "Juan"]
        scrubbed = _scrub_note(raw, forbidden)
        assert "Juan Pérez Ficticio" not in scrubbed
        assert "Juan" not in scrubbed

    @pytest.mark.asyncio
    async def test_scrub_note_no_forbidden_names_passes_through(self):
        """_scrub_note returns original text unchanged when no forbidden names."""
        raw = "Buen desempeño en la pista ficticia."
        result = _scrub_note(raw, [])
        assert result == raw


# ---------------------------------------------------------------------------
# 3. analyst_agent (v2) — coach note injected into race_meta
# ---------------------------------------------------------------------------


class TestAnalystAgentCoachNoteInjection:
    """Tests that analyst_agent v2 injects scrubbed coach note into race_meta."""

    @pytest.mark.asyncio
    async def test_v2_injects_coach_note_into_race_meta(self):
        """When a scrubbed note exists for a válida, race_meta includes note line."""
        from app.services.race.agents.analyst import PROMPT_VERSION_ANALYST_V2

        received_inputs: list = []

        class RecordingAgent:
            async def invoke(self, input_):
                received_inputs.append(input_)
                return make_analysis_output(), _make_zero_metrics()

            async def invoke_per_valida(self, pairs, **kwargs):
                results = {}
                for vn, inp in pairs:
                    received_inputs.append((vn, inp))
                    results[vn] = (make_analysis_output(), _make_zero_metrics())
                return results

        agent = RecordingAgent()
        state = {
            "athlete_id": 1,
            "season": 2026,
            "athlete_age": 13,
            "ltad_group": "junior_1",
            "anonymized_data": {"pseudonym": "AzulZorro", "rows": []},
            "metrics": {"progression": [{"valida_num": 4, "position": 2}]},
            "podium_context": {},
            "principles": [],
            "memory": [],
            "valida_nums": [4],
            "prompt_version": PROMPT_VERSION_ANALYST_V2,
            "is_first_in_season": False,
            "season_validas_count": 4,
            "full_season_results": [],
            "event_conditions": {},
            # Scrubbed coach note for válida 4
            "coach_notes_by_valida": {4: "Corredor ficticio gestionó bien el primer sector."},
            "_analyst_agent": agent,
        }

        update = await analyst_agent(state)

        assert len(received_inputs) == 1
        vn, inp = received_inputs[0]
        assert vn == 4
        # race_meta on the AnalysisInput must contain the note line
        assert inp.race_meta is not None
        assert "Nota del entrenador" in inp.race_meta
        assert "Corredor ficticio" in inp.race_meta

    @pytest.mark.asyncio
    async def test_v2_no_note_does_not_modify_race_meta(self):
        """When coach_notes_by_valida has None or is absent, race_meta is not extended (FR-009)."""
        from app.services.race.agents.analyst import PROMPT_VERSION_ANALYST_V2

        received_inputs: list = []

        class RecordingAgent:
            async def invoke_per_valida(self, pairs, **kwargs):
                results = {}
                for vn, inp in pairs:
                    received_inputs.append((vn, inp))
                    results[vn] = (make_analysis_output(), _make_zero_metrics())
                return results

        agent = RecordingAgent()
        state = {
            "athlete_id": 1,
            "season": 2026,
            "athlete_age": 13,
            "ltad_group": "junior_1",
            "anonymized_data": {"pseudonym": "VerdeJaguar", "rows": []},
            "metrics": {"progression": [{"valida_num": 4, "position": 3}]},
            "podium_context": {},
            "principles": [],
            "memory": [],
            "valida_nums": [4],
            "prompt_version": PROMPT_VERSION_ANALYST_V2,
            "is_first_in_season": False,
            "season_validas_count": 3,
            "full_season_results": [],
            "event_conditions": {},
            # Note is None — no qualitative context
            "coach_notes_by_valida": {4: None},
            "_analyst_agent": agent,
        }

        update = await analyst_agent(state)

        assert len(received_inputs) == 1
        _, inp = received_inputs[0]
        # race_meta must not contain fabricated note line (FR-009)
        if inp.race_meta:
            assert "Nota del entrenador" not in inp.race_meta

    @pytest.mark.asyncio
    async def test_v2_absent_notes_dict_does_not_modify_race_meta(self):
        """When coach_notes_by_valida is entirely absent from state, race_meta unchanged (FR-009)."""
        from app.services.race.agents.analyst import PROMPT_VERSION_ANALYST_V2

        received_inputs: list = []

        class RecordingAgent:
            async def invoke_per_valida(self, pairs, **kwargs):
                results = {}
                for vn, inp in pairs:
                    received_inputs.append((vn, inp))
                    results[vn] = (make_analysis_output(), _make_zero_metrics())
                return results

        agent = RecordingAgent()
        state = {
            "athlete_id": 2,
            "season": 2026,
            "athlete_age": 12,
            "ltad_group": "bambino",
            "anonymized_data": {"pseudonym": "RojoLeon", "rows": []},
            "metrics": {"progression": [{"valida_num": 2, "position": 4}]},
            "podium_context": {},
            "principles": [],
            "memory": [],
            "valida_nums": [2],
            "prompt_version": PROMPT_VERSION_ANALYST_V2,
            "is_first_in_season": True,
            "season_validas_count": 1,
            "full_season_results": [],
            "event_conditions": {},
            # coach_notes_by_valida intentionally absent from state
            "_analyst_agent": agent,
        }

        # Capture baseline race_meta by patching format_race_meta
        import app.services.race.ai.nodes.analyst_agent as aa_mod
        from app.services.race.agents.analyst import format_race_meta

        baseline_race_meta = format_race_meta(None)

        update = await analyst_agent(state)

        assert len(received_inputs) == 1
        _, inp = received_inputs[0]
        # race_meta must equal the no-conditions baseline, not extended with fabricated note
        assert inp.race_meta == baseline_race_meta, (
            f"race_meta should be baseline '{baseline_race_meta}' "
            f"when no notes in state, got: '{inp.race_meta}'"
        )

    @pytest.mark.asyncio
    async def test_v2_note_appended_after_conditions_block(self):
        """When conditions AND a note exist, note is appended after conditions block."""
        from app.services.race.agents.analyst import PROMPT_VERSION_ANALYST_V2, format_race_meta

        received_inputs: list = []

        class RecordingAgent:
            async def invoke_per_valida(self, pairs, **kwargs):
                results = {}
                for vn, inp in pairs:
                    received_inputs.append((vn, inp))
                    results[vn] = (make_analysis_output(), _make_zero_metrics())
                return results

        agent = RecordingAgent()

        conditions_for_valida_4 = {
            "climate": "Soleado",
            "temperature_c": "28",
            "surface_condition": "seca",
            "altitude_msnm": 1000,
            "weather_notes": None,
        }

        state = {
            "athlete_id": 3,
            "season": 2026,
            "athlete_age": 14,
            "ltad_group": "junior_1",
            "anonymized_data": {"pseudonym": "AmarilloAguila", "rows": []},
            "metrics": {"progression": [{"valida_num": 4, "position": 1}]},
            "podium_context": {},
            "principles": [],
            "memory": [],
            "valida_nums": [4],
            "prompt_version": PROMPT_VERSION_ANALYST_V2,
            "is_first_in_season": False,
            "season_validas_count": 2,
            "full_season_results": [],
            "event_conditions": {4: conditions_for_valida_4},
            "coach_notes_by_valida": {
                4: "Corredor ficticio realizó una salida explosiva y mantuvo ritmo."
            },
            "_analyst_agent": agent,
        }

        await analyst_agent(state)

        assert len(received_inputs) == 1
        _, inp = received_inputs[0]
        assert inp.race_meta is not None
        # Both conditions block and note line must be present
        assert "Nota del entrenador" in inp.race_meta
        assert "Corredor ficticio" in inp.race_meta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_zero_metrics():
    from app.services.race.schemas import RunMetrics
    return RunMetrics(
        tokens_in=10, tokens_out=20, latency_ms=5, cost_usd=0.0001,
        prompt_version="race_analyst_v2",
    )
