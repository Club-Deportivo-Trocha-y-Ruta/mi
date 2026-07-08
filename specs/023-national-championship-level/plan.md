# Implementation Plan: National Championship Support (Series Level)

**Branch**: `023-national-championship-level` | **Date**: 2026-07-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/023-national-championship-level/spec.md`

## Summary

Add a `level` attribute (`departmental` | `national`) to `race_series` so the upcoming **National XCO Championship in Pereira (14–20 July 2026, Fedeciclismo)** can be registered, ingested, analyzed, and reported with correct labels. Everything that keys off `kind == championship` (standings exclusion, single-event guard INV-2, monthly-report jornada grouping, event-anchored analytics) already generalizes and is **not touched**. The work is: one additive Alembic migration, a `level` parameter threaded through `build_race_label` and the notification label helpers, level selection in the two series-creation UIs, and removal of the Valle-specific organizer default for championship series created via import.

## Technical Context

**Language/Version**: Python 3.12+ (FastAPI backend), TypeScript 5 / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async + aiomysql, Alembic, Pydantic v2; React 19 + Vite, TanStack Query, React Hook Form + Zod, shadcn/ui + Tailwind

**Storage**: MySQL 8.4 (Hostinger prod); aiosqlite in backend tests

**Testing**: pytest + httpx.AsyncClient + aiosqlite (backend); vitest + Testing Library + jest-axe (frontend)

**Target Platform**: Render free tier (backend, Docker, Oregon); Cloudflare Pages (frontend pending)

**Project Type**: Web application (backend + frontend)

**Performance Goals**: No new endpoints with heavy queries; `level` rides along existing selects (zero extra queries). Constitution budgets apply unchanged (p95 ≤ 500 ms reads).

**Constraints**: Zero downtime additive migration (`server_default`), backward compatible with pre-023 data and pre-023 report snapshots; no change to ranking, INV-2, or monthly-report grouping logic.

**Scale/Scope**: 1 migration, ~6 backend files touched, ~6 frontend files touched, 2 label helpers, ~10 test files. Single new enum with 2 values.

## Constitution Check

*GATE: evaluated against constitution v1.2.0 — PASS (pre-design and post-design).*

| Principle | Status | Notes |
|---|---|---|
| I. Code Quality | ✅ | Pure-helper extension (`build_race_label` gains `level` param with default); shared frontend label helper avoids string triplication (rule of three: InfoTab, FiltersBar, form). ruff/mypy/eslint/tsc gates apply. |
| II. Testing (NON-NEGOTIABLE) | ✅ | Happy + negative paths planned per router/service change; regression tests: departmental label unchanged, standings byte-identical (SC-004). No minors-PII involved (series/event metadata only). |
| III. UX Consistency | ✅ | New copy in español neutro ("Campeonato Nacional", "Cto. Nal."); level select uses existing shadcn select pattern; RHF+Zod extended, no native validation added. |
| IV. Performance | ✅ | No new queries; `level` column added to existing selects. No bundle impact beyond a few strings. |
| V. Psych Assessment Safeguards | N/A | No psychological instruments involved. |

No violations → Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/023-national-championship-level/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── api-delta.md     # Phase 1 output — REST surface changes
├── checklists/
│   └── requirements.md  # Spec quality checklist (done)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/
│   └── d3e4f5a6b7c8_add_race_series_level.py        # NEW — additive enum column
├── app/
│   ├── models/race_series.py                        # + RaceSeriesLevel enum, level column
│   ├── schemas/race_series.py                       # + level in Create/Read
│   ├── routers/
│   │   ├── race_series.py                           # persist body.level
│   │   └── race_imports.py                          # accept series_level Form; organizer default only for cups
│   └── services/
│       ├── race/
│       │   ├── race_labels.py                       # build_race_label(+level) → "Cto. Nal." | "Cto. Dep."
│       │   ├── analytics_charts.py                  # pass series.level to label builder
│       │   └── (races list endpoint serializer)     # pass series.level to label builder
│       └── notification/
│           └── race_insight_dispatcher.py           # championship label by level
└── tests/
    ├── test_race_labels.py                          # extend: national variants
    ├── test_race_series_router.py                   # create with level, default, 422
    ├── test_race_imports*.py                        # championship import w/o Valle organizer
    └── test_race_insight_dispatcher*.py             # "Campeonato Nacional" label

frontend/src/
├── types/raceSeries.types.ts                        # + RaceSeriesLevel, level in Create/Read
├── lib/raceSeriesLabels.ts                          # NEW — shared championship label helper
├── routes/competitions/CompetitionFormPage.tsx      # level select in CreateChampionshipSeriesForm
├── components/competitions/
│   ├── import/ImportWizard.tsx                      # level select when creating championship series
│   ├── tabs/InfoTab.tsx                             # level-aware "Campeonato Nacional/Departamental"
│   └── CompetitionFiltersBar.tsx                    # filter copy "Campeonatos" (matches both levels)
└── (tests colocated: *.test.tsx)
```

**Structure Decision**: Existing web-application layout (backend/ + frontend/). No new modules; feature threads one attribute through established files. Only genuinely new files: the Alembic migration and `frontend/src/lib/raceSeriesLabels.ts`.

## Design decisions (from Phase 0 research — see research.md)

- **D1**: `level` is a column on `race_series` (not `race_event`), enum `raceserieslevel` (`departmental` | `national`), `server_default='departmental'`, NOT NULL. Cups carry `departmental` harmlessly; UI never asks level for cups.
- **D2**: `build_race_label(kind, sequence_number, location, level=departmental)` — default keeps every existing caller/test green; championship branches to "Cto. Nal." / "Cto. Dep.".
- **D3**: Notification **tier stays `RaceTier.CD`** for all championships (highest importance); only the human label branches by level ("Campeonato Nacional"/"Campeonato Departamental"). `_tier_from_event` unchanged.
- **D4**: `points_scheme_code` stays server-forced `copa_valle_2026` on all series (spec-014 D5). Harmless for championships: standings exclude by `kind`, the scheme is never read. Documented cosmetic debt, not fixed here.
- **D5**: Import path `_get_or_create_series` applies the Valle organizer default **only for cups**; championship series take the client-provided organizer (or NULL). Legacy `_upsert_series` (no series_id) path remains Copa-Valle-only — national imports must go through the competition-linked import (feature 015 prefill), which is the documented flow.

## Phase 1 artifacts

- [data-model.md](data-model.md) — entity delta, enum, migration contract
- [contracts/api-delta.md](contracts/api-delta.md) — REST surface changes
- [quickstart.md](quickstart.md) — end-to-end validation guide

## Complexity Tracking

No constitution violations — section not applicable.
