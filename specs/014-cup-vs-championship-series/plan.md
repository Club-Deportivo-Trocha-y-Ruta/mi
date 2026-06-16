# Implementation Plan: Distinguish Cups (with rounds) from single annual Championships

**Branch**: `main` (no feature branch — work proceeds on `main` per user instruction) | **Date**: 2026-06-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/014-cup-vs-championship-series/spec.md`

## Summary

Today every results event is modeled as a numbered round of a cup, forcing the
annual Departmental Championship to masquerade as "Válida #1" of the Copa Valle.
This corrupts the season ranking and forces fake round numbers. The fix adds a
single `kind` discriminator (`cup` | `championship`) to `race_series`, makes each
championship its own one-event series, removes every hardcoded "Copa Valle"
assumption from the create / edit / import flows, excludes championships from the
season cumulative ranking, and reclassifies the one existing misfiled event — all
while reusing the existing results/imports/analytics pipeline with **one** new DB
column and **no** change to `race_events`.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript 5 / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 (async, aiomysql), Alembic, Pydantic
v2 (backend); React 19 + Vite, shadcn/ui + Tailwind v4, TanStack Query, React Hook
Form + Zod (frontend)

**Storage**: MySQL 8.4 (prod, Hostinger) / SQLite via aiosqlite (tests)

**Testing**: pytest + httpx.AsyncClient + aiosqlite (backend); vitest + Testing
Library + jest-axe (frontend)

**Target Platform**: Linux server (Render, Docker); coach desktop/tablet, parent
Android mobile

**Project Type**: Web application (FastAPI backend + React SPA)

**Performance Goals**: No new N+1; ranking aggregates remain single-query. No new
per-request latency budget beyond existing endpoints.

**Constraints**: Single Alembic head (current: `a3b4c5d6e7f8`); data migration must
be idempotent and prod-safe (auto-runs on deploy); backward-compatible API
(`series_kind` defaults to `cup`); minors-privacy invariant preserved.

**Scale/Scope**: Small dataset (one club, ~tens of events/season). 1 new DB column,
2 new endpoints, 3 changed endpoints, 2 read-path filters, 1 data migration, ~4
frontend surfaces.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Code Quality & Maintainability | PASS | Reuses existing patterns (enum `values_callable`, service guards). Removes a latent bug (`_get_or_create_series` ignoring `series_name`). `ruff`/`mypy`/`eslint`/`tsc` gates apply; human review required before any merge. |
| II. Testing (NON-NEGOTIABLE) | PASS (planned) | Each new/changed router+service gets happy+negative pytest; migration idempotency test; frontend vitest + jest-axe; privacy invariant tests assert no minor PII in series/competition responses. |
| III. UX Consistency | PASS | New "competition type" selector reuses shadcn/ui + RHF+Zod; round field hidden for championships; badge semantics (`is_championship`) preserved; es-CO copy; 48px targets; loading/empty/error states for the new series picker. |
| IV. Performance | PASS | Ranking stays single-query; `kind` filter is indexed-eligible; series picker is one small `GET`. No N+1 introduced. |

No violations → Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/014-cup-vs-championship-series/
├── plan.md              # This file
├── spec.md              # Feature spec
├── research.md          # Phase 0 — technical decisions D1..D7
├── data-model.md        # Phase 1 — race_series.kind, behavioral rules, migration
├── quickstart.md        # Phase 1 — end-to-end manual + automated checks
├── contracts/
│   └── race-series-api.md   # Phase 1 — series + event/import contracts
├── checklists/
│   └── requirements.md  # spec quality checklist (16/16)
└── tasks.md             # Phase 2 — created by /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── models/
│   │   └── race_series.py            # + RaceSeriesKind enum, kind column
│   ├── schemas/
│   │   ├── race_series.py            # NEW — RaceSeriesCreate/Read/ListResponse
│   │   └── race_event.py             # sequence_number optional; is_championship derived
│   ├── routers/
│   │   ├── race_series.py            # NEW — GET/POST /race-series
│   │   ├── race_events.py            # POST guard: championship single-event + derive
│   │   └── race_imports.py           # fix _get_or_create_series; series_kind Form; detect_revision
│   └── services/
│       └── race/
│           ├── season_panorama.py    # + AND rs.kind='cup'
│           ├── standings.py          # guard: non-cup series → None
│           └── ingestor.py           # honor series kind on event creation
├── alembic/versions/
│   └── <new>_add_race_series_kind_and_reclassify_championship.py   # down_revision=a3b4c5d6e7f8
└── tests/                            # pytest for all of the above

frontend/
├── src/
│   ├── api/
│   │   └── raceSeries.ts             # NEW — GET/POST /race-series client
│   ├── hooks/race/
│   │   └── useRaceSeries.ts          # NEW — TanStack Query hooks
│   ├── schemas/
│   │   └── competitionEvent.schema.ts # drop COPA_VALLE_SERIES hardcode; type-aware
│   ├── components/competitions/import/
│   │   └── ImportWizard.tsx          # competition-type selector; hide válida for champ
│   ├── routes/competitions/
│   │   ├── CompetitionFormPage.tsx   # type selector; conditional round field; dynamic series
│   │   ├── CompetitionsListPage.tsx  # preserve badge (no change expected)
│   │   └── CompetitionDetailPage.tsx # preserve badge; hide standings tab for champ
│   └── types/raceEvents.types.ts     # series kind types
└── src/**/__tests__/                 # vitest + jest-axe
```

**Structure Decision**: Existing web-app layout (FastAPI `backend/app` + React
`frontend/src`). Changes are additive and localized to the race/competition slice;
no new top-level modules.

## Complexity Tracking

No constitution violations — section intentionally empty.

## Phase 0 — Research

Complete. See [research.md](./research.md). Decisions D1–D7 resolve all technical
unknowns; zero `[NEEDS CLARIFICATION]` remain (the four product questions were
resolved with the coach before planning).

## Phase 1 — Design & Contracts

Complete:
- [data-model.md](./data-model.md) — `race_series.kind` enum, unchanged
  `race_events`, read-time ranking rules, idempotent data migration.
- [contracts/race-series-api.md](./contracts/race-series-api.md) — new
  `GET`/`POST /race-series`; changed `POST /race-events`, import parse, and
  standings; season-panorama filter.
- [quickstart.md](./quickstart.md) — five scenarios + automated checks + rollback.

Agent context (`CLAUDE.md`) updated to point at this plan.

## Key risks & mitigations

| Risk | Mitigation |
|---|---|
| Two-heads Alembic regression | New revision chains from the single head `a3b4c5d6e7f8`; verify `alembic heads` returns one head pre-merge. |
| Data migration runs in prod on deploy | Idempotent, guarded `UPDATE`/upsert; safe no-op on fresh DBs and re-runs; downgrade restores legacy state. |
| Frontend hardcoded `series id=2` removed | Series now loaded via `GET /race-series`; loading/empty/error states required (Principle III). |
| Championship leaking into ranking | Two filters keyed on `series.kind` (panorama SQL + standings guard) with explicit tests (SC-002). |
| Backward compatibility of import | `series_kind` Form defaults to `cup`; existing Copa Valle flow unchanged + regression test. |

## Next phase

Run `/speckit-tasks` to generate `tasks.md` (dependency-ordered, agent-assigned).
The `before_tasks` git hook is optional and will be skipped to stay uncommitted on
`main`.
