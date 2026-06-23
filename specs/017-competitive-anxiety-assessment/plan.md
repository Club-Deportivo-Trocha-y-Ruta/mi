# Implementation Plan: Competitive Anxiety Assessment

**Branch**: `claude/spec-kit-agent-setup-poepvz` (session branch; feature dir `017-competitive-anxiety-assessment`) | **Date**: 2026-06-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/017-competitive-anxiety-assessment/spec.md`

## Summary

Build a coach-facing module to administer, score, and interpret **state** competitive-anxiety questionnaires (CSAI-2R default for 13–15, SAS-2 for 10–12, CSAI-2 import-only) for youth XCO athletes, anchored to each athlete's own baseline and framed in a mastery climate. Athletes answer via a coach-issued one-time token (no athlete login this version). Scoring is deterministic from a data-loaded official key (item answers always persisted). Interpretation is generated **on demand** by an LLM use case that mirrors the existing `app/services/ai` pattern, with a **rule-based fallback**, and cached. Guardian consent (reusing `parental_consents`) gates all assessment. Reuses the existing FastAPI + SQLAlchemy 2 async + Alembic + MySQL backend and the React 19 + Vite + shadcn/ui + TanStack Query frontend.

**Tooling for processes (per request)**: research and library/API lookups use **MCP** (Context7 for FastAPI/SQLAlchemy/React docs; GitHub MCP for repo operations) and **web search** (instrument validation literature). The licensed instrument scoring keys are loaded as **data**, never invented; web research only documents the public structure to verify the loaded key.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript 5 / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 (async, aiomysql), Alembic, PyJWT + bcrypt, Pydantic v2; React 19 + Vite, shadcn/ui + Tailwind v4, TanStack Query, Zustand, React Hook Form + Zod. AI via existing `app/services/ai` (provider-agnostic: google/anthropic/fake) + Jinja prompt registry + guardrails.

**Storage**: MySQL 8.4 (Hostinger prod). New tables via Alembic migration.

**Testing**: backend `pytest` + `httpx.AsyncClient` + `aiosqlite`; frontend `vitest` + Testing Library + `jest-axe`.

**Target Platform**: Linux server (Render free tier, Oregon) + mobile web (coach on tablet; athlete answers on phone via tokened link).

**Project Type**: Web application (existing `backend/` + `frontend/`).

**Performance Goals**: read endpoints p95 ≤ 500 ms; writes p95 ≤ 1500 ms; questionnaire answer screen LCP ≤ 2.5 s on mid-tier Android/3G; assume ~50 s Render cold start with explicit "starting" UI state.

**Constraints**: minors privacy (Ley 1581) — no PII in logs/commits/AI prompts; `AI_LOG_PROMPTS=false` in prod; español neutro for all product copy; WCAG 2.1 AA; no athlete login (token-only); on-demand LLM with cache (cost/latency control).

**Scale/Scope**: single club, dozens of athletes, ~7 Copa Valle events/season; tens of assessments per race; low write volume, read-heavy dashboards.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Code Quality & Maintainability** — PASS. Reuses existing service/model/router layering; new public services (`services/anxiety/*`, `services/ai/use_cases/anxiety_interpretation.py`) get docstrings. No premature abstraction (single instrument-key loader, no generic "survey engine").
- **II. Testing (NON-NEGOTIABLE)** — PASS (planned). Scoring has unit tests per instrument incl. partial/reverse-item cases; routers get happy + negative (auth denied, missing consent, age-inappropriate override) tests; interpretation has fallback + schema tests + a property test asserting no real athlete name leaks into AI output; frontend components/hooks get vitest + axe.
- **III. UX Consistency & Language** — PASS. All athlete/coach copy in español neutro; questionnaire one-item-at-a-time, 48×48 targets, loading/empty/error states; shadcn/ui components; RHF+Zod. This plan/spec/docs in English (dev corpus).
- **IV. Performance** — PASS. Dashboards eager-load (selectinload) to avoid N+1; interpretation cached (no per-view LLM call); heavy charts lazy-loaded; budgets above.
- **V. Youth Psychological Assessment Safeguards (NON-NEGOTIABLE)** — PASS. Age-driven selection + under-13 warning; wellbeing-not-diagnosis enforced in prompt + guardrails + rule fallback; baseline-anchored interpretation; mastery climate; human-in-the-loop (no auto-messaging); calendar-tied; item-level persistence; rule-based fallback; guardian consent gate; coach-only RBAC; minors privacy in AI prompts (pseudonyms only).

**Result**: No violations. Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/017-competitive-anxiety-assessment/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (REST contracts)
│   └── rest-api.md
├── checklists/
│   └── requirements.md  # from /speckit-specify
└── tasks.md             # /speckit-tasks output (not created here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── models/
│   │   ├── anxiety_instrument.py      # instrument definition + scoring key (data)
│   │   ├── anxiety_assessment.py      # one administration (answers, scores, flags)
│   │   ├── anxiety_response_token.py  # single-use athlete access token
│   │   └── anxiety_baseline.py        # per athlete+subscale April baseline
│   ├── schemas/
│   │   └── anxiety.py                 # Pydantic create/read/score/interpret schemas
│   ├── routers/
│   │   └── anxiety.py                 # coach CRUD + token answer + interpret + import/export
│   ├── services/
│   │   ├── anxiety/
│   │   │   ├── scoring.py             # deterministic subscale scoring per key
│   │   │   ├── instrument_keys.py     # loads CSAI-2R/SAS-2/CSAI-2 official keys (data)
│   │   │   ├── selection.py           # age-band → instrument + under-13 guard
│   │   │   ├── baseline.py            # baseline establish/compare + trend
│   │   │   ├── rule_interpreter.py    # rule-based fallback (same schema)
│   │   │   └── importer.py            # CSV item-by-item historical import
│   │   └── ai/
│   │       ├── use_cases/anxiety_interpretation.py
│   │       └── prompts/anxiety_interpretation_v1.j2
│   └── data/anxiety_keys/             # licensed scoring-key fixtures (no invented items)
├── alembic/versions/                  # new migration: anxiety_* tables
└── tests/                             # scoring, selection, interpretation, routers, import

frontend/
└── src/
    ├── components/anxiety/            # AssessmentWizard (config), Questionnaire (token),
    │                                   # IndividualPanel, GroupPanel, ImportDialog, AnalyzeButton
    ├── hooks/                         # useAnxietyAssessments, useInterpretation, useAnxietyImport
    ├── pages/                         # AnxietyDashboardPage, AnswerPage (token route)
    └── api/                           # anxiety client
```

**Structure Decision**: Web-application layout, extending the existing `backend/` and `frontend/` trees and their established conventions (models/schemas/routers/services; components/hooks/pages/api). The AI interpretation reuses `app/services/ai` (BaseUseCase + PromptRegistry + Guardrails + provider factory) rather than introducing a new AI path.

## Phase 0 — Research (→ research.md)

Resolved unknowns: instrument scoring keys (CSAI-2R/SAS-2/CSAI-2 structure, verified vs. literature, loaded as data), baseline/trend definition, on-demand+cache interpretation pattern (mirror `athlete_ai_insight`), consent reuse (`parental_consents` + new `psychological_assessment` scope), token-based athlete access, CSV import shape. See [research.md](./research.md).

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md): `anxiety_instruments`, `anxiety_assessments`, `anxiety_response_tokens`, `anxiety_baselines`; reuse `athletes`, `race_events`, `parental_consents`.
- [contracts/rest-api.md](./contracts/rest-api.md): coach CRUD, group create, token answer, scoring, on-demand interpret, import, CSV/JSON export.
- [quickstart.md](./quickstart.md): end-to-end validation scenarios.
- Agent context: CLAUDE.md SPECKIT marker updated to point at this plan.

## Phase 2 — Tasks (handled by `/speckit-tasks`)

`/speckit-tasks` will generate `tasks.md` and **assign each task to a specialized subagent** (see Appendix A mapping). Dependency-ordered, `[P]` for parallelizable.

## Phase 3 — Implementation (handled by `/speckit-implement`)

`/speckit-implement` will run a **dynamic workflow**: dispatch tasks to the assigned specialized agents, respecting dependencies, parallelizing independent `[P]` tasks, and re-checking the Constitution gates (esp. Principle V) before merge.

## Appendix A — Specialized-agent assignment (feeds /speckit-tasks & /speckit-implement)

| Work area | Specialized agent |
|---|---|
| Migration, table design, indexes, enums (`values_callable`) | `database-architect` |
| Models, schemas, routers, RBAC, scoring/selection/baseline services | `fastapi-architect` |
| LLM interpretation use case, prompt, guardrails, rule-based fallback, provider wiring | `integration-engineer` (with `mental-performance-coach` reviewing safeguard/clima copy) |
| Questionnaire UI, dashboards, import dialog, hooks | `react-ui-engineer` |
| Mobile/field usability, athlete token flow, WCAG AA | `ux-researcher` |
| Backend + frontend tests, axe, privacy/property tests | `qa-engineer` |
| Minors-privacy audit (no PII in logs/AI prompts), consent gate | `data-privacy-guard` |
| CSV historical import pipeline + normalization | `data-analyst` |
| Docs, runbook, CLAUDE.md status update | `technical-writer` |
| Deploy, env vars (AI_*), migration on Render | `devops-engineer` / `release-manager` |

Orchestration delegated by `engineering-lead` (full-stack) with `head-coach-lead` consulted for domain/safeguard correctness.

## Complexity Tracking

No constitution violations — table intentionally empty.
