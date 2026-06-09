# Implementation Plan: Unified Competitions Module

**Branch**: `claude/race-competition-consolidation-dqRZv` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/007-competitions-consolidation/spec.md`

## Summary

Consolidate the two race areas (the `/competitions` CRUD module and the `/coach/race-analysis` AI module) into one coherent **Competitions** module, and build the capabilities that were designed but never shipped. Research (`research.md`) confirms the data layer largely exists — `race_results`, the `season_standings` view, ingestion/revision, athlete↔rider link, bidirectional calendar FKs, and `agent_runs.stale_since` are all present. The work is therefore: (1) **read endpoints + UI tables** for per-event results and season standings with club highlighting; (2) one **net-new roster** table + endpoints; (3) **calendar-sync propagation** logic over the existing FKs; (4) **finishing the consolidation** (single sidebar, redirect lifecycle, removal of legacy pages); and (5) surfacing existing **AI insights** inside the module. Delivered in independently shippable waves per the approved PRD (`docs/12-competitions-unification/workflow.md`).

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript / React 19 (frontend)
**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, MySQL 8.4 (backend); React 19 + Vite, shadcn/ui + Tailwind, TanStack Query v5, Zustand, RHF + Zod (frontend). **No new runtime dependency** (results table uses a local shadcn `ui/table` primitive + client-side sort/filter).
**Storage**: MySQL 8.4 (Hostinger prod); `aiosqlite` for tests. One new table `race_event_roster`; everything else reused. `season_standings` is an existing VIEW.
**Testing**: `pytest` + `httpx.AsyncClient` + `aiosqlite` (backend); `vitest` + Testing Library + `jest-axe` (frontend). Privacy invariants mandatory for minor data.
**Target Platform**: Render free-tier backend (Oregon); coach on field tablet, parent on mid-tier Android over 3G/4G.
**Project Type**: Web application (backend + frontend).
**Performance Goals**: API p95 ≤500 ms cached reads / ≤1500 ms writes; standings/results reads must be single aggregated queries (no N+1); results-tab lazy chunk ≤150 KB gzipped; data-dense route LCP ≤3.5 s on 3G.
**Constraints**: Ley 1581 — no minor PII in logs/commits/AI prompts/output; incremental & reversible waves; redirects live one release cycle before 410; reuse existing hooks/services (do not duplicate AI hooks).
**Scale/Scope**: ~7 rounds/season × 26 categories; a round's field is bounded (hundreds of rows) → client-side table sort/filter is sufficient.

## Constitution Check

*GATE: must pass before Phase 0; re-checked after Phase 1.*

| Principle | How this plan satisfies it |
|---|---|
| **I. Code Quality** | Reuses existing models/services; no premature abstraction; new roster service + read services get docstrings; centralized cross-invalidation helper removes the duplicate-invalidation smell (rule of three). `ruff`/`mypy`/`eslint`/`tsc` gating. |
| **II. Testing (NON-NEGOTIABLE)** | New endpoints (results, standings, roster, calendar-link) each get happy + negative (auth/404/409/422) tests; calendar-sync propagation gets a regression test; **privacy invariants**: parent-scoped results/standings return only own child, AI output name-free (property test). a11y axe on new tabs/pages. |
| **III. UX Consistency** | shadcn/ui + Tailwind only; RHF+Zod with `noValidate`; ≥48px targets; designed loading/empty/error states (the results empty-state CTA is explicit in FR-013); green/amber/red/gray semantics; español neutro copy; WCAG AA. |
| **IV. Performance** | Results/standings are single aggregated SQL queries (standings from the view) with query-count tests; results tab lazy-loaded; "our club" filter server-side; cold-start state surfaced. |
| **Privacy / AI guardrails** | Mandatory `data-privacy-guard` audit; `forbidden_names` retained, `[]` for global views; ids-only logs; `AI_LOG_PROMPTS=false`. |

**Gate result**: PASS. One justified deviation (new table) recorded in Complexity Tracking.

## Project Structure

### Documentation (this feature)
```text
specs/007-competitions-consolidation/
├── plan.md          # this file
├── spec.md
├── research.md      # Phase 0
├── data-model.md    # Phase 1
├── quickstart.md    # Phase 1
├── contracts/
│   └── api.md       # Phase 1
└── tasks.md         # /speckit-tasks (next)
```

### Source Code (repository root)
```text
backend/app/
├── models/
│   └── race_event_roster.py            # NEW (only new model)
├── schemas/
│   ├── race_results.py                 # NEW (results + standings read schemas)
│   └── race_roster.py                  # NEW
├── services/race/
│   ├── results_read.py                 # NEW (per-event finishing table)
│   ├── standings.py                    # NEW (season_standings view reader)
│   ├── roster.py                       # NEW (call-up + reconciliation)
│   └── calendar_sync.py                # NEW (1:1 propagation; or extend services/race_events.py)
├── routers/
│   ├── race_events.py                  # CHANGED (results/standings/roster/calendar-link; create checkbox)
│   └── (race_analysis.py et al.)       # reused; absorbed into module via frontend
└── alembic/versions/<new>_race_event_roster.py   # NEW migration (chained to head)

frontend/src/
├── components/competitions/
│   ├── tabs/ResultsTab.tsx             # CHANGED (real table, was a hub)
│   ├── tabs/StandingsTab.tsx           # NEW
│   ├── tabs/AthletesTab.tsx            # CHANGED (+ roster)
│   ├── results/ResultsTable.tsx        # NEW (shadcn table + sort/filter + club highlight)
│   ├── results/StandingsTable.tsx      # NEW
│   └── roster/RosterPanel.tsx          # NEW
├── components/ui/table.tsx             # NEW (shadcn primitive, local component)
├── routes/competitions/insights/*      # reused (absorb RaceAnalysisPage/ClubInsightsByRacePage)
├── api/{raceResults,raceStandings,raceRoster}.ts   # NEW
├── hooks/race/{useRaceResults,useRaceStandings,useRaceRoster,useCalendarSync}.ts  # NEW
└── (App.tsx, AppShell.tsx)             # CHANGED (single sidebar entry; redirect lifecycle)
```

**Structure Decision**: Existing web-app layout. Additions are localized: one model/migration, three read/roster/sync services, results/standings/roster schemas + routers on the existing `race_events` router, and the missing frontend tables/tabs. The AI-analysis pages are relocated under `/competitions/*` (no logic rewrite, no hook duplication).

## Phased delivery (waves, each shippable & reversible)

Mapped to spec user stories (US1–US6) and the PRD waves. Detailed tasks come from `/speckit-tasks`.

- **Wave A — Results & standings (US1, P1)**: read endpoints + schemas + services over existing data; `ResultsTab`/`StandingsTab` tables with club highlight + empty states; api/hooks; tests (incl. parent-scoping privacy, query-count). *Highest value; independent.*
- **Wave B — Consolidation (US2, P1)**: single "Competencias" sidebar; mount insights inside `/competitions/*`; 301 redirects for legacy routes; `MemoryRouter` test codemod. *No data changes.*
- **Wave C — Athlete association + roster (US3, P2)**: `race_event_roster` model + migration + roster service/endpoints + reconciliation; `RosterPanel` + match confirm/fix wiring; tests.
- **Wave D — Reload/fix (US4, P2)**: surface existing diff re-ingest in `/competitions/:id/import`; on apply, mark affected `agent_runs.stale_since` + newsletters outdated; "outdated" badge + manual re-execute. *Mostly wiring existing backend.*
- **Wave E — Calendar sync (US5, P3)**: `calendar_sync` propagation + create checkbox + associate endpoint; cross-invalidation helper; tests for date/venue/cancel propagation and 1:1 guard.
- **Wave F — Insights polish + cleanup (US6, P3 + PR7)**: season/club/athlete insight views final placement; redirects 301→410; remove `RaceAnalysisPage`/`ClubInsightsByRacePage`; bundle baseline check.

Each wave ends green (lint, type, pytest, vitest, axe) and is independently deployable.

## Complexity Tracking

| Violation | Why needed | Simpler alternative rejected because |
|---|---|---|
| New table `race_event_roster` | Roster/call-up must exist before results and independent of the (opt-out) calendar event; reconciliation needs queryable rows per `(event, athlete)`. | Reusing `EventAttendance` breaks when calendar creation is opted out and has wrong (RSVP) semantics; a JSON column on `race_events` is not queryable for reconciliation or per-athlete history. |

No other deviations. No new runtime dependency (results table uses a local shadcn primitive, not `@tanstack/react-table`).
