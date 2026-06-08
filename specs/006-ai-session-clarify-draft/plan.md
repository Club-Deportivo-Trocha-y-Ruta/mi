# Implementation Plan: AI Session Clarify & Draft

**Branch**: `claude/session-creation-ai-ideas-MMOM7` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/006-ai-session-clarify-draft/spec.md`

## Summary

Add a pre-wizard "Asistente IA" that (1) asks the coach a single batch of 2–4 clarifying
questions rendered as selectable chips (single/multi-select + free-text "Otro"), then
(2) returns a fully editable session draft that pre-fills the existing session wizard via
React Hook Form `reset(..., { keepDirtyValues: true })`. Two stateless backend endpoints
reuse the established `BaseUseCase` + Jinja prompt + `PromptRegistry` + `Guardrails`
infrastructure and the robust prompt-instructed-JSON parsing pattern already proven by
`AthleteNewsletterUseCase`. The assistant conditions on **aggregate, non-identifying**
context only (age-mix counts, macrocycle phase, Copa Valle race proximity) — no minor's
name ever reaches or leaves the model. Athlete call-up is proposed as a non-identifying
**criterion** that the frontend resolves to specific athletes locally.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript 5 / React 19 (frontend)

**Primary Dependencies**: FastAPI, Pydantic v2, async SQLAlchemy 2 (read-only for context);
existing `app.services.ai` stack (factory, providers, registry, guardrails); frontend
React Hook Form + Zod, TanStack Query, shadcn/ui `ToggleGroup`, Tailwind v4.

**Storage**: None new. Feature is stateless — no migration, no new tables. Reads existing
`athletes` (birth_date, sex) to compute aggregate age-mix; Copa Valle calendar is a
module-level constant.

**Testing**: pytest + httpx.AsyncClient + aiosqlite (backend); vitest + Testing Library +
jest-axe + MSW (frontend). `FakeLLMProvider` for deterministic AI tests.

**Target Platform**: Render (FastAPI) + Cloudflare Pages (SPA); coach on tablet, español
neutro UI.

**Project Type**: Web application (backend + frontend).

**Performance Goals**: Clarify/draft are AI endpoints — documented budget exception to the
constitution's p95 ≤ 1500 ms write rule. Each call bounded by `ai_timeout_seconds` (~30 s)
with explicit waiting + cold-start UI. Assistant panel lazy-loaded (`React.lazy`).

**Constraints**: No minor PII to the AI provider; `ai_log_prompts` stays false; coach/admin
RBAC; output length capped (≤4 questions, bounded draft fields) per structured-output
hallucination-reduction guidance.

**Scale/Scope**: ~1 club, dozens of athletes; low request volume. 2 endpoints, 1 use case
class (with two `run_*` methods or two small use cases), 1 prompt template (two render
modes) or two templates, ~1 new frontend route + assistant panel + multi-select chip
wrapper.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Code Quality**: PASS — reuses existing patterns (BaseUseCase, registry, DI via
  `get_llm_provider`/`get_prompt_registry`, RHF+Zod). New public service modules get
  docstrings. `ruff` + `mypy` + `eslint` + `tsc` must stay green.
- **II. Testing (NON-NEGOTIABLE)**: PASS (planned) — backend: use-case JSON parse/validate,
  guardrail scrub, both endpoints (happy + auth-denied + AI-disabled + malformed-JSON +
  timeout), **privacy invariants** (no name in context/output/logs). Frontend: clarify
  panel render (single/multi/other), draft→wizard prefill, fallback states, a11y (axe = 0).
- **III. UX Consistency**: PASS — shadcn `ToggleGroup` (`type="single"`/`"multiple"`),
  RHF+Zod with `noValidate`, ≥48px targets, español neutro output (FR-017), loading/empty/
  error states for every async surface (FR-018), per-field AI-seeded markers (FR-019)
  using existing badge/neutral tokens.
- **IV. Performance**: PASS with documented exception — AI latency exception recorded here
  and in route docstrings; assistant panel lazy-loaded; context queries are bounded
  (selected athletes by id) and eager-loaded to avoid N+1.

**Privacy/Compliance gate (Ley 1581 — minors)**: PASS by design — only aggregate age-mix
counts + season/race timing are sent to the AI; athlete proposal is a criterion, resolved
to ids client-side; guardrails scrub all output; `ai_log_prompts=false`. A
`data-privacy-guard` audit is a planned task.

No violations → **Complexity Tracking is empty.**

## Project Structure

### Documentation (this feature)

```text
specs/006-ai-session-clarify-draft/
├── plan.md              # This file
├── research.md          # Phase 0 — design decisions (D1–D8)
├── data-model.md        # Phase 1 — transient schemas (no DB)
├── quickstart.md        # Phase 1 — run/test/smoke
├── contracts/
│   └── session-assistant.md   # Phase 1 — 2 endpoint contracts
└── tasks.md             # Phase 2 — /speckit-tasks (not created here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── schemas/
│   │   └── session_assistant.py        # NEW: ClarifyRequest/Response, DraftRequest/Response, enums
│   ├── services/
│   │   ├── ai/
│   │   │   ├── use_cases/
│   │   │   │   └── session_assistant.py # NEW: SessionClarifyUseCase + SessionDraftUseCase
│   │   │   ├── prompts/
│   │   │   │   ├── session_clarify.j2   # NEW
│   │   │   │   ├── session_draft.j2     # NEW
│   │   │   │   └── registry.py          # EDIT: register 2 PromptSpecs
│   │   │   └── guardrails.py            # (reuse; extend only if needed)
│   │   └── training/
│   │       └── session_assistant_context.py # NEW: aggregate age-mix + race-proximity builder
│   ├── routers/
│   │   └── session_assistant.py        # NEW: 2 endpoints under /api/clubs/{club_id}/session-assistant
│   ├── dependencies.py                 # EDIT: get_session_clarify/draft_use_case providers
│   └── main.py                         # EDIT: include new router
└── tests/
    ├── services/ai/test_session_assistant_use_case.py   # NEW
    ├── routers/test_session_assistant.py                # NEW
    └── privacy/test_session_assistant_privacy.py        # NEW

frontend/
├── src/
│   ├── components/training/session-wizard/
│   │   ├── ai-assistant/
│   │   │   ├── SessionAssistantPanel.tsx   # NEW: chat-like clarify→draft flow (lazy)
│   │   │   ├── ClarifyQuestionCard.tsx     # NEW: single/multi chips + "Otro"
│   │   │   └── aiSeededFields.ts           # NEW: helper to track/clear AI-seeded markers
│   │   ├── SessionWizard.tsx               # EDIT: accept applied draft + AI-seeded markers
│   │   └── StepGeneral.tsx                 # EDIT: render per-field AI-seeded marker
│   ├── components/ui/
│   │   └── toggle-group.tsx                # (reuse; type="multiple")
│   ├── routes/training/
│   │   ├── SessionAssistantPage.tsx        # NEW: pre-wizard launch route
│   │   └── SessionFormPage.tsx             # EDIT: accept ?fromAssistant draft handoff
│   ├── api/
│   │   └── sessionAssistant.ts             # NEW: clarify() + draft() clients + types
│   ├── hooks/training/
│   │   └── useSessionAssistant.ts          # NEW: useClarify/useDraft mutations
│   ├── schemas/
│   │   └── sessionAssistant.schema.ts      # NEW: Zod for answers + draft mapping
│   └── App.tsx                             # EDIT: add /training/sessions/assistant route
└── test/msw/
    └── sessionAssistantHandlers.ts         # NEW
```

**Structure Decision**: Web-application layout. Backend lives entirely inside the existing
`app.services.ai` use-case framework + a new thin router scoped by `club_id` for RBAC
(mirroring `monthly_reports.py`). Frontend adds a lazy pre-wizard assistant under the
existing `session-wizard/` feature folder and hands the resulting draft to the wizard via
the established `reset()` mechanism. No database changes.

## Complexity Tracking

> No constitution violations. Section intentionally empty.
