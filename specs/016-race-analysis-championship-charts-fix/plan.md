# Implementation Plan: Race-analysis Distribution & Evolution charts handle the Departmental Championship correctly

**Branch**: `016-race-analysis-championship-charts-fix` | **Date**: 2026-06-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/016-race-analysis-championship-charts-fix/spec.md`

## Summary

The athlete AI-analysis **Distribution** and **Evolution** charts identify races by a round number (`valida_num` / `sequence_number`), with the Departmental Championship hard-coded as `99`. Feature 014 retired that convention: each championship is now its own `race_series` (`kind='championship'`) with `sequence_number=1`. The charts were never updated, producing two defects:

1. **Distribution returns HTTP 500 for the championship (and any no-data race).** `build_distribution` looks up the race `WHERE e.sequence_number = :valida_num`; the frontend sends `99`, which matches no event, so the service hits its empty-fallback branch — which builds a `DistributionResponse(category_id=0, category_code="")` that **violates its own schema** (`category_id: ge=1`, `category_code: min_length=1`) → `ResponseValidationError` → 500.
2. **Evolution collides the championship with cup round I.** The championship now has `sequence_number=1`, so `romanForValida(1)` renders `"I"` and the Recharts `dataKey="roman"` merges it with the real Válida I.

**Technical approach**: identify races by their stable `event_id` (the spec's "Race" / "Athlete race participation" entities), not by round number.

- **Backend**: add a read-only `GET …/race-analysis/races?season=` endpoint that returns exactly the races an athlete competed in (cup rounds + championship), each with a server-built label; switch `GET …/distribution` from `valida_num` to `event_id`; delete the schema-violating empty fallback (replace with a clean, schema-valid no-data payload + 404 for non-participated events); add `series_kind` + `label` to `EvolutionPoint`.
- **Frontend**: feed the Distribution race picker from the new endpoint (real labels, `event_id` values, prepended "Temporada (todas)" informational entry); query distribution by `event_id`; label the Evolution championship point as its own point via `series_kind`, keyed by `event_id`.

No database migration — `race_series.kind` and `event_id` already exist (migration `b1c2d3e4f5a6`, feature 014). The change is confined to the two charts and their read models; AI insight text, chat, imports, results, and ranking are untouched.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript 5.x / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Pydantic v2 (backend); React 19 + Vite, TanStack Query v5, Recharts, shadcn/ui + Tailwind v4 (frontend)

**Storage**: MySQL 8.4 — **no schema change**; reuses `race_results`, `race_events`, `race_series` (`.kind`), `race_categories`, `race_competitors` and index `ix_race_results_athlete_event`

**Testing**: pytest + `httpx.AsyncClient` + `aiosqlite` (backend); vitest + Testing Library + MSW + jest-axe (frontend); Playwright (e2e); StrykerJS 9.6.1 + `@stryker-mutator/vitest-runner` (mutation gate)

**Target Platform**: Render (backend, Linux container); Cloudflare Pages SPA on mid-tier Android / coach tablet over 3G/4G

**Project Type**: Web (FastAPI backend + React SPA frontend)

**Performance Goals**: races endpoint is one indexed query (`ix_race_results_athlete_event`), p95 ≤ 500 ms (Principle IV read budget); charts already lazy-loaded

**Constraints**: español neutro (Colombia) for all user-facing copy; WCAG 2.1 AA; minors-privacy (Ley 1581) — pseudonymized competitors for parents, no minor PII in logs/errors/responses; **no `sequence_number=99`** in new code (feature 014 retirement)

**Scale/Scope**: ~tens of race results per athlete-season; 2 endpoints changed + 1 added; ~2 backend files + ~6 frontend files touched; out of scope: AI insight/chat, imports, results, ranking, ComparatorPanel

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan satisfies it |
|---|---|
| **I. Code Quality & Maintainability** | Race identity collapses to one concept (`event_id`); the dead `sequence_number=99` mapping and the invalid empty fallback are removed. Label-building logic is extracted into one pure, named helper (server-side builder + a frontend mirror) — no comment needed to explain it. `ruff`+`mypy` (backend), `eslint`+`tsc --noEmit` (frontend) are pre-merge blockers. Public service `build_distribution`/`build_evolution` keep docstrings describing the new `event_id` contract. Human review required before merge to `main`. |
| **II. Testing Standards (NON-NEGOTIABLE)** | Each defect lands with a regression test that fails on unfixed code: (a) pytest — championship distribution by `event_id` returns 200 with its own category; (b) pytest — no-comparable-data returns a valid 200, never 500; (c) pytest — races endpoint lists exactly competed races incl. championship, with RBAC parent path; (d) vitest — picker from backend list, no collision, aggregate informational state, friendly no-data; (e) jest-axe on both charts (zero violations); (f) Playwright e2e extending `cup-vs-championship.spec.ts`. Privacy invariants asserted: no real competitor name in parent responses, no `competitor_id`/`athlete_id` in any payload. Mutation gate extended to the new TS modules. |
| **III. User Experience Consistency** | shadcn/ui components reused; defined loading / empty / error states on every async surface (no unbounded spinner, no raw exception text); "Temporada (todas)" resolves to a calm informational state (coach decision), never an error; copy in español neutro ("Válida IV — Cali", "Cto. Dep. — Ginebra", "La distribución se calcula por carrera…"); 48×48 px targets and focus rings preserved; status color semantics unchanged. WCAG AA verified via jest-axe. |
| **IV. Performance Requirements** | New races endpoint = single query over the existing composite index, no N+1; covered by a query-count/time assertion. Distribution/Evolution remain `React.lazy`-loaded; no new >50 KB import into shared layouts. Cold-start state already handled upstream. |

**Quality gates / compliance**: `data-privacy-guard` audit is mandatory (feature reads athlete-identifiable race data). Stack unchanged — no new runtime dependency. No new auth surface; RBAC for the new endpoint reuses the existing `verify_athlete_access` dependency. `AI_LOG_PROMPTS` untouched (no AI surface in scope).

**Result**: PASS — no violations; Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/016-race-analysis-championship-charts-fix/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions & rationale
├── data-model.md        # Phase 1 — entities & read-model changes
├── quickstart.md        # Phase 1 — validation guide
├── contracts/           # Phase 1 — endpoint contracts
│   ├── races.md
│   ├── distribution.md
│   └── evolution.md
└── checklists/
    └── requirements.md   # (existing) spec quality checklist
```

### Source Code (repository root)

```text
backend/app/
├── routers/
│   └── athlete_race_analysis.py        # CHANGE: /distribution param valida_num→event_id; ADD GET /races
├── services/race/
│   ├── analytics_charts.py             # CHANGE: build_distribution by event_id, drop invalid fallback;
│   │                                   #         build_evolution emits series_kind + label; ADD list_athlete_races
│   └── race_labels.py                  # ADD (or extend): pure label builder (cup → "Válida {roman} — {city}",
│                                       #                   championship → "Cto. Dep. — {city}")
├── schemas/
│   └── athlete_race_analysis.py        # CHANGE: DistributionResponse identity (event_id); EvolutionPoint +series_kind +label;
│                                       #         ADD RaceParticipationOption + RaceParticipationResponse
└── tests/ (pytest)                     # ADD regression + RBAC + privacy tests

frontend/src/
├── api/
│   └── athleteRaceAnalysis.ts          # CHANGE: getAthleteDistribution(event_id); ADD getAthleteRaces
├── hooks/athletes/
│   ├── useAthleteDistribution.ts       # CHANGE: key + param event_id
│   └── useAthleteRaces.ts              # ADD
├── lib/
│   └── raceOptionLabel.ts              # ADD: pure label/identity helpers (mutation-tested)
├── components/athletes/ai/
│   ├── DistributionChart.tsx           # CHANGE: picker from backend list, event_id, aggregate informational state
│   └── EvolutionChart.tsx              # CHANGE: label by series_kind, key by event_id (no collision)
├── types/
│   └── athleteRaceAnalysis.types.ts    # CHANGE/ADD: mirror schema changes
└── (vitest + jest-axe tests alongside; e2e/ Playwright spec)

frontend/
├── stryker.config.json                 # CHANGE: extend mutate[] with new TS modules
└── e2e/
    └── race-analysis-championship.spec.ts  # ADD Playwright e2e
```

**Structure Decision**: Web app (Option 2). The change is split across the existing `backend/app` (router + service + schema) and `frontend/src` (api + hooks + chart components + types), with no new top-level directories. `raceCalendar.ts` is intentionally **not** modified — the out-of-scope `ComparatorPanel` still keys it by `99`; the new path takes labels from the backend instead.

## Complexity Tracking

> No constitution violations. Table intentionally empty.
