# Implementation Plan: AI Race Analysis in the Competitions Module — Restore Access and Enhance Insights

**Branch**: `010-competitions-ai-insights` | **Date**: 2026-06-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/010-competitions-ai-insights/spec.md`

## Summary

Restore coach access to the already-built AI race-analysis capability from inside the competitions module and enrich insights with season context. Backend: a new coach-only group-launch endpoint (`POST /api/race-analysis/race-events/{id}/runs`) that fans out one standard run per club athlete with results (reusing `submit_run()`, budget guard, backpressure, HITL), a companion `GET .../runs` for refresh recovery, an additive `race_event_id` scope on `ChatRequest`, and a `season_comparative` + `progression_assessment` enrichment computed in `compute_metrics` and injected into the `race_analyst_v2` prompt and `AnalysisOutput`. Frontend: a `GroupAnalysisPanel` in the competition InsightsTab (launch, per-athlete progress, HITL approvals, retry-failed), a post-import "Analizar con IA ahora" offer in `ImportWizard`, a per-athlete row action in `ResultsTable`, and a new `CompetitionChatPanel` over the existing unused `chatTurn()` client. AI provider/model unchanged (Gemini); no DB migration.

## Technical Context

**Language/Version**: Python 3.12+ (backend), TypeScript 5 / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 (async, aiomysql), LangChain + LangGraph (existing race agent graph, Gemini provider — unchanged), Pydantic v2; Vite, TanStack Query, Zustand, React Hook Form + Zod, shadcn/ui + Tailwind

**Storage**: MySQL 8.4 — existing tables only (`agent_runs`, `agent_run_events`, `athlete_ai_insights`, `race_results`, `race_events`, `race_series`). **No Alembic migration.**

**Testing**: pytest + httpx.AsyncClient + aiosqlite (backend), vitest + Testing Library (frontend)

**Target Platform**: Render (Docker, free tier, cold start ~50s) + browser SPA (coach on desktop)

**Project Type**: Web application (backend + frontend)

**Performance Goals**: Group launch endpoint responds < 2s for a 15-athlete squad (run creation only; analysis is async). Status polling stays on the existing 2s/ETag-304 protocol. No added per-request LLM calls outside runs/chat.

**Constraints**: `MAX_CONCURRENT_RUNS = 10` semaphore (overflow surfaced, not queued); `RACE_AI_BUDGET_USD_30D` guard enforced before any run starts; `AI_LOG_PROMPTS=false` and anonymizer node untouched (minors privacy); all coach-facing copy es-CO.

**Scale/Scope**: 1 club, ~15 athletes/válida, 8 válidas/season; 2 new endpoints + 1 extended; ~4 new frontend components; ~6 touched backend modules.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Code Quality & Maintainability | `ruff` + `mypy` (backend), `eslint` + `tsc --noEmit` (frontend) must pass; no new abstractions beyond need (no new tables, no provider refactor) | PASS — design reuses `submit_run()`, existing hooks; composition over new machinery |
| II. Testing (NON-NEGOTIABLE) | Every new endpoint/component ships with tests in the same PR | PASS — test plan in research.md R9; tasks will pair implementation+tests |
| III. UX Consistency | Product copy es neutro (Colombia); spec/docs English; coach-only controls follow existing role-gating pattern | PASS — copy inventory in quickstart.md; `isCoach` gating per existing pattern |
| IV. Performance | No N+1 on group resolution (single query for athletes-with-results); polling reuses ETag/304; cold-start feedback in UI | PASS — group resolution is one JOIN query; no new polling protocol |

**Post-design re-check (Phase 1)**: PASS — no violations introduced; Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/010-competitions-ai-insights/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── race-event-runs.md   # Group launch + list endpoints
│   └── chat-event-scope.md  # ChatRequest extension
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── routers/
│   │   ├── race_analysis.py          # MODIFIED: +group launch, +event runs list, chat schema accepts race_event_id
│   │   └── race_imports.py           # UNCHANGED (commit already returns race_event_id)
│   ├── schemas/
│   │   └── race_ai.py                # MODIFIED: GroupRun* schemas, ChatRequest.race_event_id, ProgressionAssessment
│   ├── services/race/
│   │   ├── ai/nodes/compute_metrics.py   # MODIFIED: season_comparative + progression_assessment
│   │   ├── ai/nodes/load_race_data.py    # MODIFIED (if needed): ensure prior-válida rows loaded
│   │   ├── agents/analyst.py             # MODIFIED: AnalysisInput + prompt vars
│   │   ├── prompts/race_analyst_v2.md    # MODIFIED: season-context section + no-fabrication rule
│   │   ├── group_launch.py               # NEW: resolve athletes-with-results, fan-out via submit_run
│   │   └── agents/chat.py                # MODIFIED: event-scoped tool filtering
│   └── models/                            # UNCHANGED (no migration)
└── tests/
    ├── routers/test_race_event_runs.py    # NEW
    ├── routers/test_race_analysis.py      # MODIFIED: chat event-scope cases
    └── services/test_compute_metrics_season.py  # NEW

frontend/
├── src/
│   ├── api/
│   │   ├── raceAnalysis.ts               # MODIFIED: launchGroupAnalysis, getRaceEventRuns, chatTurn race_event_id
│   │   └── athleteRaceAnalysis.ts        # UNCHANGED (startAthleteRun reused)
│   ├── hooks/ai/
│   │   ├── useRaceRun.ts                 # UNCHANGED (reused)
│   │   └── useGroupAnalysis.ts           # NEW: launch/list/retry + multi-run polling aggregation
│   ├── components/competitions/
│   │   ├── tabs/InsightsTab.tsx          # MODIFIED: mounts GroupAnalysisPanel
│   │   ├── insights/GroupAnalysisPanel.tsx   # NEW
│   │   ├── insights/GroupRunRow.tsx          # NEW (per-athlete state chip + HITL surface)
│   │   ├── results/ResultsTable.tsx      # MODIFIED: per-athlete launch row action
│   │   ├── import/ImportWizard.tsx       # MODIFIED: post-commit launch offer
│   │   └── chat/CompetitionChatPanel.tsx # NEW
│   └── types/raceAnalysis.types.ts       # MODIFIED: group types, chat body
└── src/components/competitions/**/__tests__/   # NEW/MODIFIED vitest suites
```

**Structure Decision**: Existing web-application split (`backend/` + `frontend/`) is retained; all changes land inside the already-established race-analysis and competitions module boundaries listed above.

## Design decisions (from research.md)

| # | Decision | Ref |
|---|---|---|
| 1 | Group launch = server-side fan-out of standard athlete runs; per-athlete typed outcomes; optional `athlete_ids` subset for retries | R1, R2 |
| 2 | Refresh recovery via `GET /api/race-analysis/race-events/{id}/runs` derived from `agent_runs` (no new table) | R1, R7 |
| 3 | Season comparatives computed in Python (`compute_metrics`), never by the LLM; `progression_assessment ∈ {improving, stable, declining, mixed, first_reference}` | R3 |
| 4 | `ChatRequest` gains optional `race_event_id`; chat tools filter by event; new `CompetitionChatPanel` UI | R4 |
| 5 | Per-athlete row launch reuses `startAthleteRun` with `(season, valida)` derived from the event; `ConfirmModal` on fresh insight | R5 |
| 6 | Post-import offer in ImportWizard success panel → group endpoint → navigate to Insights tab | R6 |
| 7 | Guards unchanged; error mapping 503 budget / backpressure entries / disabled AI with specific es-CO copy | R8 |

## Implementation execution model (requested by the coach)

Implementation (Phase 3, `/speckit-implement`) runs with an **agent team led by the Fable 5 model** (this session's main loop acts as engineering lead — decomposition, integration, review): `fastapi-architect` for backend endpoints/graph enrichment, `react-ui-engineer` for the four frontend surfaces, `qa-engineer` for pytest/vitest suites, with `data-privacy-guard` reviewing the prompt/anonymization changes before completion.

## Complexity Tracking

*No constitution violations — table intentionally empty.*
