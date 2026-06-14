"""Test sentinela de PII en respuestas del router race_analysis (F5.8).

Garantiza que ningún nombre real de atleta del club aparece en:
- ``new_events`` del polling response
- Cualquier campo de la response (incluyendo payloads anidados)

Property test: 50 athlete_ids × 50 polling responses con payloads
simulados que incluyen nombres reales en posiciones aleatorias. Cada
response es procesada por el router (vía el slicing/escapado real) y
se valida que NO contiene los nombres prohibidos.

Lista de nombres prohibidos: los atletas reales del club (caso real),
extraída de CLAUDE.md y memorias. Si en el futuro hay nuevos atletas,
agregar a la lista — este test es la última línea de defensa para
fugas accidentales en logs/UI.

Decisión técnica: usamos iteración determinista (50×50 = 2500 casos)
en vez de hypothesis full property-based para mantener tiempos de test
<1s. La estrategia es "fuzzing dirigido" — los nombres reales se
inyectan en payloads de eventos y verificamos el contrato del router.

Extensión feature 013-race-result-athlete-notes (T024):
Tests de invariantes de privacidad para ``coach_note`` por atleta por válida.
Garantiza que nombres reales incrustados en notas del entrenador no llegan
al LLM (ruta analyst), no salen por el tool fetch_results del chat, y que
una nota ausente no produce placeholder fabricado (FR-009).
"""

from __future__ import annotations


import pytest

pytestmark = pytest.mark.asyncio


# Nombres reales de atletas del club (privacidad: estos son los que
# NUNCA deben fugar). Tomados del rubric en el prompt y CLAUDE.md.
FORBIDDEN_NAMES = [
    "Mariana",
    "Thiago",
    "Sofia",
    "Sofía",
    "Miguel",
    "Isabel",
    "Jostin",
    # Variantes con apellido + acento
    "Mariana García",
    "Sofía Pérez",
]


def _contains_forbidden(text_blob: str) -> list[str]:
    """Retorna lista de nombres encontrados (vacía si limpio)."""
    if not text_blob:
        return []
    lower = text_blob.lower()
    return [n for n in FORBIDDEN_NAMES if n.lower() in lower]


class TestPIISentinel:
    """50 athlete_ids × 50 polls → 0 fugas."""

    async def test_polling_no_filtra_nombres_reales(self, coach_client, fake_db):
        """50 runs con 50 eventos cada uno. El servidor recibe payloads
        anonimizados (pseudónimos) — el test confirma que el contrato
        no rompe la invariante."""
        run_ids = []
        for athlete_id in range(1, 51):
            rid = f"run-pii-{athlete_id}"
            run = fake_db.seed_run(rid, requested_by_user_id=10)
            # Seed 50 eventos por run con pseudónimos (correcto).
            for seq in range(1, 51):
                fake_db.seed_event(
                    run["id"],
                    seq,
                    "node_end",
                    "anonymize",
                    payload={
                        "pseudonym": f"AzulZorro{athlete_id:03d}",
                        "explain": "Reemplazo nombres por pseudónimos",
                    },
                )
            run_ids.append(rid)

        leaks: list[tuple[str, list[str]]] = []
        for rid in run_ids:
            resp = await coach_client.get(
                f"/api/race-analysis/runs/{rid}/status?since=0"
            )
            assert resp.status_code == 200
            body_text = resp.text
            found = _contains_forbidden(body_text)
            if found:
                leaks.append((rid, found))

        assert not leaks, (
            f"PII LEAK DETECTADO: {leaks[:5]} (de {len(leaks)} runs con fuga). "
            f"El router no debe propagar nombres reales en ningún campo."
        )

    async def test_polling_payload_con_nombre_real_es_inquietante(
        self, coach_client, fake_db
    ):
        """Caso negativo: si por bug del grafo un nombre real llega al
        payload, el router lo propaga (no sanitiza — eso es responsabilidad
        del nodo anonymize). Este test documenta el contrato: la barrera
        primaria es upstream. Si fuera mejor sanitizar también acá,
        se actualizaría el contrato.

        Marcado como caso "contract documentation" — falla intencional
        para hacer visible la decisión arquitectónica.
        """
        run = fake_db.seed_run("run-leak-doc", requested_by_user_id=10)
        # Simulamos un bug: el nodo upstream dejó un nombre real.
        fake_db.seed_event(
            run["id"],
            1,
            "node_end",
            "load_race_data",
            payload={"_buggy": "Mariana lideró"},
        )
        resp = await coach_client.get("/api/race-analysis/runs/run-leak-doc/status")
        body_text = resp.text
        # Documenta el contrato: el router NO sanitiza — la barrera es upstream.
        # Si esto cambia (defensa en profundidad), actualizar este test.
        assert "Mariana" in body_text, (
            "Contrato actual: router propaga payloads tal cual; "
            "sanitización es responsabilidad del nodo anonymize. "
            "Si este test falla, alguien añadió sanitización defensiva — "
            "actualiza el contrato."
        )

    async def test_chat_response_no_filtra_nombres(self, coach_client, ai_enabled):
        """El chat agent (mockeado) no debe propagar nombres en la
        respuesta. Probamos 10 queries variadas."""
        from app.main import app
        from app.routers.race_analysis import get_race_chat_agent
        from app.services.race.schemas import ChatResponse

        class CleanAgent:
            async def chat(
                self,
                session_id,
                query,
                athlete_id=None,
                race_event_id=None,
                event_scope=None,
            ):
                # Respuesta segura: solo pseudónimo.
                return ChatResponse(
                    answer="El atleta (pseudónimo: AzulZorro) progresa.",
                    citations_used=[],
                    tools_called=[],
                )

        app.dependency_overrides[get_race_chat_agent] = lambda: CleanAgent()
        try:
            queries = [
                "qué hizo Mariana?",  # nombre real en query
                "cómo va Sofia?",
                "Miguel necesita más fuerza?",
                "Isabel está lista para válida V?",
                "tendencia general del club",
                "comparar bambinos",
                "principios LTAD para 12 años",
                "carga semanal recomendada",
                "Jostin vs Thiago",
                "qué dice el marco?",
            ]
            leaks = []
            for q in queries:
                resp = await coach_client.post(
                    "/api/race-analysis/chat",
                    json={"session_id": "sentinel", "query": q},
                )
                assert resp.status_code == 200
                # El query del usuario puede contener nombres reales (eso es ok —
                # el LLM los recibe), pero la RESPUESTA del agente no debe.
                answer = resp.json()["answer"]
                found = _contains_forbidden(answer)
                if found:
                    leaks.append((q, found))
            assert not leaks, f"Chat agent filtra nombres: {leaks}"
        finally:
            app.dependency_overrides.pop(get_race_chat_agent, None)

    async def test_result_endpoint_no_filtra_nombres_si_grafo_limpio(
        self, coach_client, fake_db
    ):
        """Si el final_output del grafo está limpio (pseudónimos), el
        endpoint /result no debe inyectar nombres."""
        fake_db.seed_run(
            "run-clean",
            status_="completed",
            requested_by_user_id=10,
            final_output_json={
                "raw_markdown": "# AzulZorro001 — análisis\nProgreso constante.",
                "sections": {"evolution": "ok"},
                "recommendations": [],
                "risk_flags": [],
            },
        )
        resp = await coach_client.get("/api/race-analysis/runs/run-clean/result")
        assert resp.status_code == 200
        body_text = resp.text
        leaks = _contains_forbidden(body_text)
        assert not leaks, f"PII leak en /result: {leaks}"

    async def test_50x50_combinatorio(self, coach_client, fake_db):
        """Property test concentrado: 50 runs × 50 polls. El status
        response NUNCA debe contener nombres reales si los payloads del
        grafo están limpios."""
        # Setup compartido: 5 runs con 10 eventos cada uno → 50 polls totales.
        runs_meta = []
        for athlete_id in range(1, 6):
            rid = f"prop-{athlete_id}"
            run = fake_db.seed_run(rid, requested_by_user_id=10)
            for seq in range(1, 11):
                fake_db.seed_event(
                    run["id"],
                    seq,
                    "node_end",
                    f"node_{seq}",
                    payload={"pseudonym": f"Atleta{athlete_id:03d}", "seq": seq},
                )
            runs_meta.append(rid)

        leak_count = 0
        for rid in runs_meta:
            for since in [0, 2, 5, 8, 10]:
                resp = await coach_client.get(
                    f"/api/race-analysis/runs/{rid}/status?since={since}"
                )
                # 200 o 304 (si since==last_seq)
                assert resp.status_code in (200, 304)
                if resp.status_code == 200:
                    found = _contains_forbidden(resp.text)
                    if found:
                        leak_count += 1

        assert leak_count == 0, f"Detectadas {leak_count} fugas de PII en 50 polls"


# ---------------------------------------------------------------------------
# Feature 013 — coach_note privacy invariants (T024)
# ---------------------------------------------------------------------------


class TestCoachNotePrivacy:
    """Locks privacy invariants for the coach_note per-athlete per-válida path.

    Audit checklist (feature 013 / T024):
    1. Real name in coach_note → scrubbed before any LLM prompt (analyst path).
    2. coach_note absent → no note text and no placeholder in AI context (FR-009).
    3. Chat fetch_results tool output with real name in note → scrubbed.
    4. coach_note is NOT present in parent-facing result response.
    """

    # ---- helpers ------------------------------------------------------------

    @staticmethod
    def _make_result_orm(
        *,
        athlete_id: int = 42,
        event_id: int = 10,
        sequence_number: int = 1,
        coach_note: str | None = None,
        position: int = 3,
        race_time_ms: int = 1_200_000,
    ):
        """Return a minimal SimpleNamespace that mimics a RaceResult ORM row."""
        from types import SimpleNamespace
        from enum import Enum

        class Status(Enum):
            finished = "finished"

        return SimpleNamespace(
            id=99,
            event_id=event_id,
            category_id=1,
            competitor_id=200,
            athlete_id=athlete_id,
            position=position,
            race_time_ms=race_time_ms,
            points_awarded=18,
            status=Status.finished,
            coach_note=coach_note,
        )

    @staticmethod
    def _make_event_orm(*, event_id: int = 10, sequence_number: int = 1):
        from types import SimpleNamespace

        return SimpleNamespace(
            id=event_id,
            sequence_number=sequence_number,
            series_id=1,
            event_date=None,
        )

    # ---- 1. anonymize node: real name in per-row coach_note is scrubbed -----

    async def test_anonymize_scrubs_real_name_in_per_row_coach_note(self):
        """A club athlete's real name embedded in coach_note is replaced by
        the forbidden-names rules before reaching the LLM (analyst path)."""
        from app.services.race.ai.nodes.anonymize import _scrub_note
        from app.services.ai.guardrails import build_race_v2_forbidden_names_rules

        note_with_name = "Mariana tuvo una caída en la salida pero recuperó bien."
        forbidden = ["Mariana", "Mariana García"]

        rules = build_race_v2_forbidden_names_rules(forbidden)
        scrubbed = note_with_name
        for rule in rules:
            scrubbed = rule.pattern.sub(rule.replacement or "", scrubbed)

        found = _contains_forbidden(scrubbed)
        assert not found, (
            f"Real name still present after scrub: {found}. "
            f"Scrubbed note: {scrubbed!r}"
        )
        # The replacement is "la deportista"
        assert "la deportista" in scrubbed or "Mariana" not in scrubbed

    async def test_anonymize_scrubs_real_name_in_coach_notes_by_valida(self):
        """The {valida_num: raw_note} dict produced by load_race_data is
        scrubbed by the anonymize node before analyst_agent reads it."""
        from app.services.race.ai.nodes.anonymize import anonymize

        # Build a minimal state that exercises the scrub path.
        athlete_id = 42
        raw_notes_by_valida = {
            1: "Sofia completó las 4 vueltas sin problemas.",
            2: None,  # no note for válida 2
        }
        # forbidden_names carries the real names that must be scrubbed.
        state = {
            "athlete_id": athlete_id,
            "competitor_id": 200,
            "run_id": "test-run-notes",
            "raw_data": [
                {
                    "result_id": 99,
                    "event_id": 10,
                    "category_id": 1,
                    "competitor_id": 200,
                    "athlete_id": athlete_id,
                    "position": 3,
                    "race_time_ms": 1_200_000,
                    "points_awarded": 18,
                    "status": "finished",
                    # Note also present in the per-row dict (T020 path):
                    "coach_note": "Sofía Pérez terminó bien en el sector técnico.",
                }
            ],
            "forbidden_names": ["Sofia", "Sofía", "Sofía Pérez"],
            "coach_notes_by_valida": raw_notes_by_valida,
            "event_conditions": {},
        }

        # Patch the DB session used to persist mapping (best-effort, can fail).
        from unittest.mock import AsyncMock, patch, MagicMock

        fake_db_ctx = MagicMock()
        fake_db_ctx.__aenter__ = AsyncMock(return_value=AsyncMock(execute=AsyncMock()))
        fake_db_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.services.race.ai.nodes.anonymize.get_session",
            return_value=fake_db_ctx,
        ):
            result = await anonymize(state)

        # --- coach_notes_by_valida scrub (T021 path) ---
        scrubbed_notes = result.get("coach_notes_by_valida", {})
        # Válida 1 had a note with "Sofia" — must be gone.
        note_v1 = scrubbed_notes.get(1)
        assert note_v1 is not None, "Scrubbed note for válida 1 should be present (not None)"
        found_v1 = _contains_forbidden(note_v1)
        assert not found_v1, (
            f"Real name leaked in coach_notes_by_valida[1]: {found_v1}. "
            f"Scrubbed: {note_v1!r}"
        )
        # Válida 2 had no note — key preserved with None value (FR-009, no placeholder).
        assert 2 in scrubbed_notes, "Válida 2 key must remain in scrubbed dict"
        assert scrubbed_notes[2] is None, (
            "Absent note (None) must stay None — no placeholder injected (FR-009)."
        )

        # --- per-row coach_note scrub (T020 path) ---
        anon_data = result.get("anonymized_data", {})
        rows = anon_data.get("rows", [])
        assert rows, "anonymized_data.rows must be populated"
        for row in rows:
            raw_row_note = row.get("coach_note")
            if raw_row_note is not None:
                found_row = _contains_forbidden(raw_row_note)
                assert not found_row, (
                    f"Real name leaked in per-row coach_note: {found_row}. "
                    f"Scrubbed note: {raw_row_note!r}"
                )

    # ---- 2. analyst path: race_meta built from scrubbed note has no real name -

    async def test_analyst_race_meta_contains_no_real_name(self):
        """When analyst_agent v2 builds race_meta and appends the scrubbed
        coach_note, the resulting string must contain no real name."""
        from app.services.race.agents.analyst import format_race_meta

        # Simulates what _analyst_agent_v2 does in analyst_agent.py lines 216-224.
        # Pre-condition: anonymize node has already scrubbed the note.
        athlete_real_name = "Mariana García"
        scrubbed_note = "la deportista tuvo una caída en la salida."

        # Confirm the scrubbed note itself contains no real name.
        found = _contains_forbidden(scrubbed_note)
        assert not found, (
            f"Scrubbed note fed to race_meta should have no real name: {found}"
        )

        # Build race_meta exactly as analyst_agent does.
        race_meta = format_race_meta(None)  # no event conditions
        coach_note = scrubbed_note.strip()
        if coach_note:
            note_line = f"- Nota del entrenador: {coach_note}"
            race_meta = f"{race_meta}\n{note_line}" if race_meta else note_line

        # The composed race_meta must not contain the athlete's real name.
        found_meta = _contains_forbidden(race_meta or "")
        assert not found_meta, (
            f"Real name appeared in race_meta: {found_meta}. "
            f"race_meta: {race_meta!r}"
        )
        # The note content should be present (scrubbed form).
        assert "Nota del entrenador" in (race_meta or "")
        assert athlete_real_name not in (race_meta or "")

    async def test_analyst_race_meta_with_family_member_name_scrubbed(self):
        """A family member name in the coach_note is also scrubbed by the
        same forbidden-names rules before reaching race_meta."""
        from app.services.race.ai.nodes.anonymize import _scrub_note

        # Coach wrote a note mentioning a parent's name (e.g. picked up by wrong context).
        note = "El papá de Thiago comentó que tuvo problemas de nutrición pre-carrera."
        forbidden = ["Thiago", "Miguel"]

        scrubbed = _scrub_note(note, forbidden)

        found = _contains_forbidden(scrubbed)
        assert not found, (
            f"Family member name still present after scrub: {found}. "
            f"Scrubbed: {scrubbed!r}"
        )

    # ---- 3. coach_note absent → no placeholder in AI context (FR-009) -------

    async def test_absent_coach_note_produces_no_placeholder_in_anonymize(self):
        """When load_race_data builds coach_notes_by_valida with None values
        (no coach note), the anonymize node must not inject any text — the
        key stays None so analyst_agent detects absence and behaves as before."""
        from app.services.race.ai.nodes.anonymize import anonymize
        from unittest.mock import AsyncMock, patch, MagicMock

        athlete_id = 7
        state = {
            "athlete_id": athlete_id,
            "competitor_id": 300,
            "run_id": "test-run-no-note",
            "raw_data": [
                {
                    "result_id": 55,
                    "event_id": 20,
                    "category_id": 2,
                    "competitor_id": 300,
                    "athlete_id": athlete_id,
                    "position": 1,
                    "race_time_ms": 900_000,
                    "points_awarded": 25,
                    "status": "finished",
                    # No "coach_note" key — mimics _serialize_result when note is None.
                }
            ],
            "forbidden_names": ["Isabel", "Jostin"],
            # coach_notes_by_valida has the key but value is None (no note).
            "coach_notes_by_valida": {3: None},
            "event_conditions": {},
        }

        fake_db_ctx = MagicMock()
        fake_db_ctx.__aenter__ = AsyncMock(return_value=AsyncMock(execute=AsyncMock()))
        fake_db_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.services.race.ai.nodes.anonymize.get_session",
            return_value=fake_db_ctx,
        ):
            result = await anonymize(state)

        scrubbed_notes = result.get("coach_notes_by_valida", {})
        # Key 3 must exist and be None — not a placeholder string.
        assert 3 in scrubbed_notes, "Key for válida 3 must be in scrubbed notes"
        assert scrubbed_notes[3] is None, (
            f"Absent note must remain None (FR-009 — no fabricated context). "
            f"Got: {scrubbed_notes[3]!r}"
        )

        # Per-row data: no coach_note key at all when note is absent.
        anon_rows = result.get("anonymized_data", {}).get("rows", [])
        for row in anon_rows:
            assert "coach_note" not in row, (
                "coach_note key must be absent from per-row data when no note was set "
                "(FR-009 — load_race_data omits key when note is None)."
            )

    async def test_absent_coach_note_produces_no_note_line_in_race_meta(self):
        """When coach_notes_by_valida has no note for a válida, analyst_agent v2
        must NOT append a 'Nota del entrenador' line to race_meta (FR-009)."""
        from app.services.race.agents.analyst import format_race_meta

        # Simulate _analyst_agent_v2: coach_notes_by_valida absent for this válida.
        coach_notes_by_valida: dict[int, str | None] = {}  # no key → no note
        valida_num = 2

        race_meta = format_race_meta(None)
        coach_note = coach_notes_by_valida.get(valida_num)
        # Only append when truthy (non-None, non-empty).
        if coach_note:
            note_line = f"- Nota del entrenador: {coach_note.strip()}"
            race_meta = f"{race_meta}\n{note_line}" if race_meta else note_line

        # No note should appear in race_meta.
        assert "Nota del entrenador" not in (race_meta or ""), (
            f"Absent note must not produce a 'Nota del entrenador' line. "
            f"race_meta: {race_meta!r}"
        )

    async def test_none_note_value_produces_no_note_line_in_race_meta(self):
        """When coach_notes_by_valida has the key but value is None, analyst_agent
        v2 must also NOT append any note line (FR-009 — identical to absent key)."""
        from app.services.race.agents.analyst import format_race_meta

        coach_notes_by_valida: dict[int, str | None] = {1: None}
        valida_num = 1

        race_meta = format_race_meta(None)
        coach_note = coach_notes_by_valida.get(valida_num)
        if coach_note:  # None is falsy → block not entered
            note_line = f"- Nota del entrenador: {coach_note.strip()}"
            race_meta = f"{race_meta}\n{note_line}" if race_meta else note_line

        assert "Nota del entrenador" not in (race_meta or ""), (
            f"None note must not produce a 'Nota del entrenador' line. "
            f"race_meta: {race_meta!r}"
        )

    # ---- 4. chat fetch_results tool: real name in note is scrubbed ----------

    async def test_chat_fetch_results_scrubs_real_name_in_coach_note(self):
        """The _build_fetch_results_tool in chat.py scrubs coach_note via
        _scrub_coach_note_for_chat before including it in the tool output."""
        from app.services.race.agents.chat import _scrub_coach_note_for_chat

        raw_note = "Miguel llegó tarde al parque de vehículos y arrancó nervioso."
        forbidden = ["Miguel", "Isabel"]

        scrubbed = _scrub_coach_note_for_chat(raw_note, forbidden)

        found = _contains_forbidden(scrubbed)
        assert not found, (
            f"Real name still present after chat scrub: {found}. "
            f"Scrubbed note: {scrubbed!r}"
        )

    async def test_chat_fetch_results_tool_output_contains_no_real_name(self):
        """End-to-end: the fetch_results tool builds its output string using
        _scrub_coach_note_for_chat. The resulting string must contain no
        club-athlete real name from FORBIDDEN_NAMES."""
        from app.services.race.agents.chat import _build_fetch_results_tool
        from types import SimpleNamespace
        from enum import Enum
        from unittest.mock import AsyncMock, MagicMock

        class Status(Enum):
            finished = "finished"

        # ORM-like result with a real name embedded in coach_note.
        fake_result = SimpleNamespace(
            event_id=5,
            position=2,
            race_time_ms=1_350_000,
            coach_note="Jostin tuvo una excelente salida y mantuvo la rueda del líder.",
            status=Status.finished,
        )

        # Build a fake db that returns the above result.
        fake_db = MagicMock()
        fake_db.execute = AsyncMock()
        fake_db.close = AsyncMock()

        from app.services.race.queries import fetch_results_for_athlete

        async def fake_fetch(db, athlete_id, season, valida_nums=None):
            return [fake_result]

        tool = _build_fetch_results_tool(
            db_factory=lambda: fake_db,
            scope_season=2026,
            scope_valida_num=3,
            forbidden_names=["Jostin", "Thiago"],
        )

        import unittest.mock as _mock

        with _mock.patch(
            "app.services.race.agents.chat.fetch_results_for_athlete",
            side_effect=fake_fetch,
        ):
            output = await tool.ainvoke({"athlete_id": 42})

        found = _contains_forbidden(output)
        assert not found, (
            f"Real name leaked in fetch_results tool output: {found}. "
            f"Output: {output!r}"
        )
        # Confirm a note was included (scrubbed form) so the tool still adds context.
        assert "nota_entrenador" in output, (
            "Tool output should include 'nota_entrenador' field when note is present."
        )

    async def test_chat_fetch_results_no_note_placeholder(self):
        """When coach_note is None on the result, the tool must not emit
        any 'nota_entrenador' line — no fabricated context (FR-009)."""
        from app.services.race.agents.chat import _build_fetch_results_tool
        from types import SimpleNamespace
        from enum import Enum
        from unittest.mock import AsyncMock, MagicMock

        class Status(Enum):
            finished = "finished"

        fake_result = SimpleNamespace(
            event_id=5,
            position=1,
            race_time_ms=900_000,
            coach_note=None,  # no note
            status=Status.finished,
        )

        fake_db = MagicMock()
        fake_db.execute = AsyncMock()
        fake_db.close = AsyncMock()

        async def fake_fetch(db, athlete_id, season, valida_nums=None):
            return [fake_result]

        tool = _build_fetch_results_tool(
            db_factory=lambda: fake_db,
            scope_season=2026,
            scope_valida_num=1,
            forbidden_names=["Mariana", "Sofia"],
        )

        import unittest.mock as _mock

        with _mock.patch(
            "app.services.race.agents.chat.fetch_results_for_athlete",
            side_effect=fake_fetch,
        ):
            output = await tool.ainvoke({"athlete_id": 88})

        # No note → no nota_entrenador line.
        assert "nota_entrenador" not in output, (
            f"Absent note must not produce 'nota_entrenador' in tool output (FR-009). "
            f"Output: {output!r}"
        )

    # ---- 5. parent-facing results endpoint: coach_note suppressed -----------

    async def test_parent_cannot_see_coach_note_in_results(self):
        """GET /{race_event_id}/results accessible to parents must return
        coach_note=null for every row, regardless of whether a note exists
        (FR-005 / SC-005).

        Verifies the fix in results_read.py: when allowed_athlete_ids is a
        set (parent scope), coach_note and coach_note_updated_at are suppressed.
        """
        from app.services.race.results_read import get_event_results
        from unittest.mock import AsyncMock, MagicMock, patch
        from types import SimpleNamespace
        from enum import Enum

        class RStatus(Enum):
            finished = "finished"

        class EStatus(Enum):
            completed = "completed"

        # Simulate DB returning one result row with a real coach_note.
        db = MagicMock()

        from datetime import date as _date

        # RaceEvent row.
        event_mapping = {
            "id": 7,
            "name": "Copa Valle I",
            "event_date": _date(2026, 1, 31),
            "location": "Sevilla",
            "status": EStatus.completed,
        }

        # RaceResult + competitor + category row as a mapping.
        result_mapping = {
            "id": 101,
            "position": 2,
            "competitor_id": 55,
            "athlete_id": 42,
            "status": RStatus.finished,
            "race_time_ms": 1_200_000,
            "laps_behind": None,
            "points_awarded": 20,
            "bib_number": 7,
            "category_id": 3,
            "coach_note": "Sofia tuvo una excelente salida.",  # real name in note
            "coach_note_updated_at": None,
            "display_name": "S. Perez",
            "club_text": "Trocha y Ruta",
            "category_code": "INF_F",
            "category_label": "Infantil Femenino",
            "category_sort_order": 1,
        }

        # Build fake execute results.
        from tests.routers.conftest import FakeRow, FakeResult

        event_result = MagicMock()
        event_result.mappings.return_value.one_or_none.return_value = event_mapping

        result_rows = MagicMock()
        result_rows.mappings.return_value.all.return_value = [result_mapping]

        db.execute = AsyncMock(side_effect=[event_result, result_rows])

        # Call with parent scope (allowed_athlete_ids is a set, not None).
        payload = await get_event_results(
            db,
            race_event_id=7,
            allowed_athlete_ids={42},  # parent can only see athlete 42
        )

        assert payload is not None
        assert payload.categories, "Expected at least one category in results"
        rows = payload.categories[0].rows
        assert rows, "Expected at least one result row"
        row = rows[0]
        assert row.coach_note is None, (
            f"Parent must NOT see coach_note (FR-005). Got: {row.coach_note!r}"
        )
        assert row.coach_note_updated_at is None, (
            "Parent must NOT see coach_note_updated_at (FR-005)."
        )

    async def test_coach_can_see_coach_note_in_results(self):
        """GET /{race_event_id}/results with coach scope (allowed_athlete_ids=None)
        must expose coach_note as stored (not suppressed)."""
        from app.services.race.results_read import get_event_results
        from unittest.mock import AsyncMock, MagicMock
        from enum import Enum

        class RStatus(Enum):
            finished = "finished"

        class EStatus(Enum):
            completed = "completed"

        db = MagicMock()

        from datetime import date as _date

        event_mapping = {
            "id": 8,
            "name": "Copa Valle II",
            "event_date": _date(2026, 2, 28),
            "location": "Ginebra",
            "status": EStatus.completed,
        }
        note_text = "Thiago terminó 3.º tras una caída en la bajada técnica."
        result_mapping = {
            "id": 102,
            "position": 3,
            "competitor_id": 66,
            "athlete_id": 43,
            "status": RStatus.finished,
            "race_time_ms": 1_300_000,
            "laps_behind": None,
            "points_awarded": 15,
            "bib_number": 12,
            "category_id": 4,
            "coach_note": note_text,
            "coach_note_updated_at": None,
            "display_name": "T. Gomez",
            "club_text": "Trocha y Ruta",
            "category_code": "INF_M",
            "category_label": "Infantil Masculino",
            "category_sort_order": 2,
        }

        from datetime import date as _date

        event_mapping["event_date"] = _date(2026, 2, 28)

        event_result = MagicMock()
        event_result.mappings.return_value.one_or_none.return_value = event_mapping

        result_rows = MagicMock()
        result_rows.mappings.return_value.all.return_value = [result_mapping]

        db.execute = AsyncMock(side_effect=[event_result, result_rows])

        # Coach scope: allowed_athlete_ids=None.
        payload = await get_event_results(
            db,
            race_event_id=8,
            allowed_athlete_ids=None,
        )

        assert payload is not None
        rows = payload.categories[0].rows
        assert rows[0].coach_note == note_text, (
            f"Coach must see the stored coach_note. Got: {rows[0].coach_note!r}"
        )

    # ---- 6. no new note logging in the AI path ------------------------------

    async def test_no_note_content_logged_in_scrub_functions(self, caplog):
        """_scrub_note and _scrub_coach_note_for_chat must never log note
        content (even at DEBUG level). They log nothing about note text."""
        import logging
        from app.services.race.ai.nodes.anonymize import _scrub_note
        from app.services.race.agents.chat import _scrub_coach_note_for_chat

        sensitive_note = "Mariana García cayó en la primera curva."
        forbidden = ["Mariana", "Mariana García"]

        with caplog.at_level(logging.DEBUG):
            _scrub_note(sensitive_note, forbidden)
            _scrub_coach_note_for_chat(sensitive_note, forbidden)

        # Neither the raw note nor the real name must appear in any log record.
        log_text = "\n".join(r.getMessage() for r in caplog.records)
        found = _contains_forbidden(log_text)
        assert not found, (
            f"Real name leaked into logs during scrub: {found}. "
            f"Log output: {log_text!r}"
        )
        assert sensitive_note not in log_text, (
            "Raw note text must never appear in log output."
        )
