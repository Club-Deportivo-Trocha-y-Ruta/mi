# Phase 0 Research: AI Session Clarify & Draft

Consolidated design decisions. Each resolves a Technical-Context unknown. Inputs:
existing codebase patterns (`AthleteNewsletterUseCase`, `monthly_reports.py`,
`SessionWizard.tsx`), Context7 (React Hook Form `reset`), and web research on
structured-output / clarifying-question design.

## D1 — Structured-output strategy: prompt-instructed JSON + safe parse + Pydantic

- **Decision**: Reuse the exact pattern proven by `AthleteNewsletterUseCase`: render a
  Jinja template that instructs the model to return **only** JSON, call
  `provider.complete(...)` via `BaseUseCase._ask()`, strip accidental ```` ```json ````
  fences, `json.loads`, then validate into Pydantic models. Cap output: clarify returns
  **2–4 questions, each 2–4 options**; draft fields are length-bounded (mirror
  `TrainingSessionCreate` limits).
- **Rationale**: Consistency with the one AI use case that already emits JSON in this
  codebase; fully testable with `FakeLLMProvider`; the provider's `complete_json()` is
  itself only a prompt-injection MVP today, so it offers no reliability gain yet. Web
  research confirms short, **length-capped structured outputs** materially reduce
  fabrication vs. long free-form text ([Future AGI], [arXiv 2404.08189]).
- **Alternatives considered**: (a) `provider.complete_json(req, schema)` — deferred; same
  MVP mechanism, less explicit control over fence-stripping/guardrails. (b) Provider-native
  structured output (Anthropic tool-use / Google `response_mime_type`) — **fast-follow**,
  noted in spec out-of-scope; swap behind the use case without touching the router.

## D2 — Two stateless endpoints scoped by club

- **Decision**:
  - `POST /api/clubs/{club_id}/session-assistant/clarify` → returns questions.
  - `POST /api/clubs/{club_id}/session-assistant/draft` → returns an editable draft.
  Both `require_role([admin, coach])` + `user_club_role(...)` check, mirroring
  `monthly_reports.py`. The client holds the conversation between calls (stateless server).
- **Rationale**: Club scoping gives a natural RBAC boundary and matches the newsletter/
  monthly-report routers. Statelessness matches every existing AI use case (no new tables),
  satisfying the spec's "frontend holds conversation" assumption.
- **Alternatives considered**: A single multi-turn endpoint with server-side session state
  (rejected — adds storage + single-round is in scope only); mounting under
  `/training-sessions/...` (rejected — no session exists yet at pre-wizard time).

## D3 — Privacy: aggregate-only context + criterion-based athlete proposal

- **Decision**: The only context sent to the model is non-identifying:
  `age_mix` counts (`{"10-12": n, "13-15": m, "16+": k}`), `total_athletes`,
  `season_phase`, `days_to_next_race`, `next_race_priority`, `today`. The draft's athlete
  proposal is an **enum criterion** (`todos_convocados` | `grupo_10_12` | `grupo_13_15` |
  `ninguno`), never ids/names. The frontend resolves the criterion against its already
  loaded roster to fill `convocados_athlete_ids`.
- **Rationale**: Directly satisfies FR-011/FR-016 and the Ley 1581 gate — no minor name or
  PII can reach the provider or logs. Honors the coach's "athlete suggestions" choice (Q2)
  without leaking identities.
- **Alternatives considered**: Sending masked athlete pseudonyms (rejected — unnecessary
  surface area; aggregate counts are sufficient for load decisions).

## D4 — Guardrails: reuse `Guardrails.scrub` on every free-text field + structural validation

- **Decision**: After JSON parse, run `Guardrails.scrub(...)` over every coach-visible free
  string (question text, option labels/descriptions, draft `technical_focus`,
  `objectives`, `description`). Structural compliance (counts, `duration_min` 15–240,
  valid `session_kind`, español) enforced by Pydantic validators; on violation raise
  `LLMSchemaError` → HTTP 422 with a neutral message.
- **Rationale**: The existing `Guardrails` already encodes the non-negotiables (no
  supplements, cadence ≥60, no power meters <13, no calorie counting, name redaction).
  Reusing it keeps a single source of truth (FR-009/FR-010).
- **Alternatives considered**: A bespoke session guardrail set (rejected — duplicates rule
  of three; extend `Guardrails` only if a session-specific rule is missing).

## D5 — Age-mix context built server-side from selected athletes (read-only)

- **Decision**: The request may carry optional `selected_athlete_ids` (empty at pure
  pre-wizard). When present, the backend loads those athletes **within the club**, computes
  `age_decimal` via `app.services.category.compute_age_decimal` + `_age_group`, and emits
  only **counts**. Names are never read into the prompt context. When absent, age-mix is
  omitted and the assistant asks a "target group" clarifying question.
- **Rationale**: Reuses existing `category.py` helpers and `context_builders._age_group`
  thresholds (`<13` = 10-12, `<16` = 13-15). Keeps PHV/biological-age principle (#3)
  reachable later without sending DOB.
- **Alternatives considered**: Trusting a free-text age group from the coach only (kept as
  fallback when no ids); computing PHV/Mirwald per athlete (deferred — not needed for an
  aggregate draft).

## D6 — Race-proximity from a module constant Copa Valle 2026 calendar

- **Decision**: Encode the documented 2026 calendar (date + priority A/B/C) as a
  module-level constant; compute `days_to_next_race` and `next_race_priority` from `today`.
- **Rationale**: Deterministic, unit-testable, zero DB coupling, and the calendar is fixed
  and already documented in `CLAUDE.md`. Drives the tapering implication (Race A = 5–7d).
- **Alternatives considered**: Querying `race_events`/`calendar_events` (rejected for v1 —
  adds coupling and N+1 risk for a value that is a known constant; can be swapped later).

## D7 — Frontend prefill via `reset(draft, { keepDirtyValues: true })` + AI-seeded markers

- **Decision**: The assistant hands its draft to the wizard, which calls
  `reset(mergedValues, { keepDirtyValues: true })` (Context7-confirmed) so fields the coach
  already edited are **not** clobbered (covers the "draft conflicts with chosen athletes"
  edge case). Track the set of fields the draft populated; render a subtle per-field marker
  (FR-019) that clears when the field becomes dirty (RHF `dirtyFields`).
- **Rationale**: Reuses the wizard's existing `reset()`-based draft-restore plumbing; no new
  form architecture. `keepDirtyValues` is purpose-built for "only update non-dirty fields".
- **Alternatives considered**: Single top-of-wizard banner (rejected per Q5 = per-field
  markers); `defaultValues` swap (rejected — needs remount; `reset` is the idiomatic path).

## D8 — Reliability: timeout, AI-disabled, and graceful fallback

- **Decision**: Wrap each provider call in `asyncio.wait_for(..., ai_timeout_seconds)` →
  custom `SessionAssistantLLMTimeout` → **HTTP 503**. If `settings.ai_enabled` is false (or
  provider is `Fake`), endpoints return **HTTP 503** with a neutral
  "asistente no disponible" message so the frontend shows the manual-wizard fallback.
  `LLMSchemaError`/malformed JSON → **HTTP 422** neutral message. Frontend always offers
  "continuar manualmente" and never loses entered data (FR-014).
- **Rationale**: Matches existing AI error mapping in `monthly_reports.py`/
  `athlete_monthly_newsletters.py` (timeout→503, schema→failed) and the spec's graceful-
  degrade requirement. Cold-start (~50 s Render) surfaced as "iniciando el servidor".
- **Alternatives considered**: 200-with-error-body (rejected — HTTP status should reflect
  failure for the query cache + retry UX).

## Open follow-ups (non-blocking, noted for later)

- Provider-native structured output (D1 fast-follow).
- Sourcing race proximity from `race_events` once the Competitions module is deployed (D6).
- Iterative multi-round clarification (explicitly out of scope this feature).

## Sources

- React Hook Form `reset` / `keepDirtyValues` — Context7 `/react-hook-form/documentation`.
- Structured-output length-capping reduces hallucination — Future AGI (2026);
  RAG-for-structured-output, arXiv:2404.08189; agentic clarification, arXiv:2501.13946.
- Clarify-then-act + chips/free-text UX — AI UX conversational patterns; ShapeofAI auto-fill.
