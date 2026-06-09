# Phase 0 Research: Faithful, Grounded AI Insights for Competitions

**Feature**: 011-ai-insights-grounding · **Date**: 2026-06-09

No `NEEDS CLARIFICATION` markers remained in the Technical Context; the open design
questions below were resolved by direct codebase investigation (the root-cause analysis
that motivated this feature) plus the coach's scope decisions recorded in the spec.

## R1. Where to load race conditions into the pipeline

- **Decision**: Extend the `load_race_data` node to emit `state["event_conditions"]`, a
  dict keyed by `valida_num` with the five recorded condition fields of each launched
  event, built from the events list the node already loads via `load_events(db)`.
- **Rationale**: A v2 run analyzes up to 4 válidas, each a different `RaceEvent` with
  its own conditions — a single "focus event" value (like today's `podium_context`)
  cannot represent the batch. `load_race_data` already resolves events per válida for
  the chronological cut, so the data is in hand with zero extra queries.
- **Alternatives considered**:
  - *Load in the router and pass via `initial_state`* — rejected: the router doesn't
    resolve valida→event mapping; duplicating that logic invites drift.
  - *Extend `fetch_podium_context()` to return `race_meta`* (matching the dead read at
    `analyst.py:729`) — rejected: keeps conditions coupled to the podium query and only
    covers the focus event, not every válida in the batch.

## R2. How conditions reach the analyst prompt

- **Decision**: Add explicit `race_meta: str | None` (formatted, per válida) and
  `maturation_status: str | None` fields to `AnalysisInput`; `_build_v2_context` reads
  them directly and stops reading `podium_context.get("race_meta")` /
  `.get("maturation_status")` (dead keys). The Jinja2 `{% if race_meta %}` block stays;
  a new hard rule is added: when no conditions are provided, mentioning climate or
  track is **PROHIBIDO** (and line 43's "SÍ incluir … condiciones de clima, tipo de
  pista" becomes conditional on data being present).
- **Rationale**: The bug is "instruction to include + no data = fabrication". Both
  halves must be fixed: provide the data when it exists, and remove the instruction
  (replace it with a veto) when it doesn't. Explicit typed fields make the contract
  testable and kill the silent-empty-string failure mode.
- **Alternatives considered**: keep piggybacking on `podium_context` dict — rejected:
  untyped, untested, and exactly how the bug shipped unnoticed.

## R3. Source of maturation status and LTAD group

- **Decision**: Routers (`athlete_race_analysis.py`, `race_analysis.py`) inject
  `ltad_group` (derived from `age_decimal`, reusing the existing mapping at
  `athlete_race_analysis.py:776-794`) and `maturation_status` (latest
  `anthropometric_records` row for the athlete, `None` if no records) into
  `initial_state`. `_resolve_ltad`'s BAMBINO fallback stays only as a guarded
  last-resort with a warning log.
- **Rationale**: The correct computation already exists in the codebase for the
  chat/season path; the graph path simply never received it. One extra indexed query
  per run (single athlete) is negligible. Putting it in the router matches how
  `athlete_age` is already injected (Fix 1 precedent in `_resolve_age`).
- **Alternatives considered**: compute inside `load_race_data` — viable, but the
  routers already load the `Athlete` row for authorization, so the router avoids a
  second fetch and keeps graph nodes athlete-agnostic.
- **No-data behavior** (spec FR-007): `maturation_status=None` → the prompt makes no
  maturation claim; LTAD group falls back to chronological age. A default value is
  never presented as fact.

## R4. Critic v2: structure, coverage, ground truth

- **Decision**: New prompt `race_critic_v2.md` that (a) validates the v2 headings
  ("Qué pasó en esta válida", "Recorrido hasta acá", "Hacia dónde va"), (b) receives a
  per-draft ground-truth block (recorded conditions + the athlete's result rows +
  podium times for that válida) and flags any draft statement contradicting it as a
  quality issue (severity high), and (c) keeps the existing inviolable-rules JSON
  verdict format unchanged. The `critic_agent` node iterates `per_valida_drafts`
  (sequential or bounded gather, cap=4) and emits `state["per_valida_verdicts"]:
  dict[int, CriticFeedback]`; `draft_analysis`/`critic_feedback` singular keys remain
  for v1 compatibility.
- **Rationale**: Coverage and contradiction detection are spec FR-008/FR-010; the JSON
  verdict schema (`approved/severity/issues/must_block`) already has parsing, retry,
  and HITL plumbing — only the prompt content and the iteration change. Reusing the
  schema keeps `hitl_gate_review` and persistence compatible.
- **Alternatives considered**:
  - *Deterministic Python fact-checker instead of LLM critic* — partially adopted: the
    veto on unprovided conditions is enforceable in guardrails (string scan for climate
    terms when `race_meta is None`), but paraphrased contradictions ("la pista estaba
    seca" vs surface=Húmeda) need the LLM check. Both layers are specified.
  - *One critic call covering all drafts* — rejected: a 4-draft mega-prompt degrades
    JSON reliability and loses per-draft verdicts needed for per-row confidence.

## R5. Confidence computation

- **Decision**: New pure function in `app/services/race/ai/confidence.py`:
  `compute_confidence(verdict, data_completeness) -> InsightConfidence`, deterministic
  rules — start at `high`; any critic issue of severity `med` → `medium`; severity
  `high` or `must_block` or analysis from fallback → `low`; missing key inputs
  (no conditions recorded, no maturation data, or N=1 season context) cap at `medium`.
  Computed per draft in the graph (after critic), stored per row by `persist_insight`.
- **Rationale**: Spec assumption explicitly accepts a simple deterministic scheme;
  it's testable (Constitution II), explainable to the coach, and reuses signals the
  pipeline already produces. The `InsightConfidence` enum and DB column already exist.
- **Alternatives considered**: LLM self-reported confidence — rejected (uncalibrated,
  fabrication-prone — the very failure mode this feature removes).

## R6. Chat grounding

- **Decision**: Add a third chat tool `obtener_condiciones_evento(event_id |
  valida_num, season)` (factory pattern identical to the two existing tools in
  `agents/chat.py`), returning the recorded conditions or an explicit
  `"sin registro"` payload. Extend `race_chat_v1.md` with the grounding rule: answers
  about event facts must come from tool results; if the tool reports no record, say
  "no quedó registrado" — never invent.
- **Rationale**: The chat is already tool-calling (`_build_*_tool` factories +
  bounded loop); a tool is the idiomatic, testable extension point and avoids
  stuffing every event's conditions into the system prompt.
- **Alternatives considered**: inject conditions into the chat system prompt at
  session start — rejected: the chat may span events not known at session start, and
  prompt-stuffing grows tokens for every turn.

## R7. Re-generation of stored insights

- **Decision**: Reuse the existing replacement mechanics: persisting an approved run
  already calls `deprecate_previous_active()` per (athlete, season, valida_num),
  deactivating the prior active insight. The feature adds (a) a "Regenerar" action on
  the insight row in `InsightsTimeline.tsx` that re-launches the existing per-válida
  analysis endpoint scoped to that válida, and (b) verified failure behavior: a failed
  run never deactivates the existing insight (already true — deprecation happens only
  inside approved persists; covered by a regression test).
- **Rationale**: Spec US6 needs a single coach action and failure safety; both are
  achievable with the existing endpoint + persistence path. No new endpoint, no
  migration.
- **Alternatives considered**: dedicated `POST /insights/{id}/regenerate` endpoint —
  rejected for now: it would duplicate the launch flow's HITL/eventing; the timeline
  action can pass the same parameters. Revisit only if UX testing shows confusion.

## R8. Anonymization of condition notes

- **Decision**: `weather_notes` free text passes through the existing guardrails
  name-scrubbing (forbidden-names list) before being included in `race_meta`; the
  structured fields (enum/numeric) carry no PII by construction. Property test asserts
  no forbidden name survives into the assembled prompt context.
- **Rationale**: Constitution privacy gate; notes are coach-typed free text and the
  only PII-capable field among the five.
- **Alternatives considered**: exclude `weather_notes` from the LLM entirely —
  rejected: notes often hold the most coaching-relevant detail (e.g., "barro en el
  sector técnico"); scrubbing preserves value at equal risk to other scrubbed inputs.
