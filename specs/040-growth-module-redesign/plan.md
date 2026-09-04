# Implementation Plan: Growth module redesign — one reference standard, decision-first tab, family view

**Branch**: `feat/040-growth-module-redesign` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/040-growth-module-redesign/spec.md`, audit in `docs/18-growth-module-redesign/proposal.md`

## Summary

The `Crecimiento` tab shows growth classifications computed against two population references (CDC on the server, WHO 2007 on the client), opens on unreadable longitudinal charts, hides the coach's decision inputs (velocity, months from PHV, next measurement) that the backend already derives for the dashboard and the AI, and reuses coach-grade components for families — with a defect that classifies the oldest measurement for parents. The plan: (1) make **WHO 2007** the single reference on the server (vendored from the reviewed client dataset, additive `growth_source` column, idempotent recompute with a band-change report), (2) expose a small **growth summary** endpoint reusing the existing alert helpers, (3) rebuild the tab as a **lazy-loaded** `GrowthTab` with a decision-first status row, a compact rule block, one windowed percentile chart with a visible table view, a maturation timeline and shared components/tokens, (4) add a **family mode** without numerals or clinical labels, and (5) remove the automatic jump to the tab while lifting the glance summary into the page tiles. No PHV/Mirwald change, no capture-form change, no new runtime dependency.

## Technical Context

**Language/Version**: Python 3.13 (backend), TypeScript 5 / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async (aiomysql / aiosqlite), Alembic, Pydantic v2; Vite 8, TanStack Query 5, recharts ^3.8.1 (existing), shadcn/ui + Tailwind v4, React Hook Form + Zod 4, html-to-image (existing); Jinja2 + WeasyPrint for the family PDF

**Storage**: MySQL 8.4 (prod, Hostinger). One additive migration (`anthropometric_records.growth_source`, nullable enum). New WHO rows in `growth_reference_lms` via the existing idempotent seed. Recompute of derived columns via the existing backfill script (never raw columns).

**Testing**: pytest (offline aiosqlite default lane; `-m mysql` once for the migration/backfill on a `_test` DB), vitest + Testing Library + MSW, jest-axe, Playwright (`growth.spec.ts`, `growth-parent.spec.ts`, updated `history.spec.ts`), build-size gate script

**Target Platform**: Render free tier (backend, cold start ~50 s), Cloudflare Pages SPA; coach on tablet outdoors, parents on mid-tier Android over 3G/4G

**Project Type**: Web application (backend + frontend monorepo)

**Performance Goals**: `growth-summary` p95 ≤ 500 ms (one query, two rows); growth tab summary visible < 1 s from cached data, chart < 2 s on simulated 3G; entry bundle stops statically importing the recharts chunk (measured baseline: entry 336.68 kB gzip + statically imported 107.39 kB gzip recharts chunk + WHO JSON inside entry — see `research.md` R-08); growth chunk ≤ 150 kB gzip (Constitution IV lazy-route budget)

**Constraints**: minors' privacy (no names/birth dates in growth components, logs, reports, export file names); español neutro with diacritics for all product copy; Res. 2465/2016 cut-offs unchanged; PHV values unchanged for every athlete; no new runtime dependency; AI guardrails and consent gate unchanged; the recompute must be idempotent and safe at Render startup

**Scale/Scope**: ~30 athletes × ≤ 10 measurements; 1 migration, 1 seed extension, 1 script extension, 1 new endpoint, 1 new service; ~10 new/refactored frontend components in one folder, 2 route pages touched, 1 PDF builder switch, 1 new AI prompt variant; ~73 existing unit tests re-homed plus new ones

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan satisfies it | Status |
|---|---|---|
| I. Code Quality | Removes three duplicated helpers/colour maps and a page-local `StatCard` (rule of three met); splits an 875-LOC component into chart/toolbar/table; one rule table, one band vocabulary; docstrings on `growth_summary.py`; `ruff` + `tsc --noEmit` gates. | PASS |
| II. Testing (NON-NEGOTIABLE) | Router tests incl. parent-denied path (403) and privacy invariant; seed parity + idempotency tests; recompute tests (raw untouched, no-op re-run, report shape, no PII in logs); regression test for the parent oldest-record bug (fails on old code); characterization tests before the chart split; vitest + MSW for every new component with branching; jest-axe on `GrowthTab` (both modes); Playwright coach + parent; build gate script. | PASS |
| III. UX Consistency | Only shared components (`StatCard`, `StatusBadge`, `EmptyState`, `ErrorState`, shadcn `Tabs`/`ToggleGroup`/`Collapsible`/`Table`/`Alert`); status vocabulary respected (bands → success/warning/danger/neutral, never colour-alone); 48 px targets; loading/empty/error/retry states specified per surface (`contracts/growth-tab-ui.md`); español neutro with diacritics, judgment-free family copy (`contracts/band-vocabulary.md`). | PASS |
| IV. Performance | New endpoint is one query; growth tab and WHO JSON become a lazy chunk, removing a ~107 kB gzip static import from the first paint (measured); sparklines are inline SVG; recompute runs once at startup and is a no-op afterwards. Pre-existing violation: the entry chunk is already 336.68 kB gzip (> 250 kB) — not introduced here and reduced by this feature; tracked below. | PASS (pre-existing debt noted) |
| V. Youth Psych. Safeguards | Not a psychological instrument. Adjacent safeguards honoured: no diagnostic labels for families, referral hints coach-only and phrased as "consulta", velocity ranges labeled orientative, AI explanation still consent-gated with guardrails. | N/A / respected |
| Quality gate — Privacy | `data-privacy-guard` audit task with checklist; growth summary exposes ids and numbers only; recompute report by athlete id; no name inside growth components; export file name unchanged. | PASS |
| Quality gate — Stack discipline | No new runtime dependency (recharts, html-to-image already present; shadcn `chart` explicitly not added). | PASS |
| Workflow — Branching | Work on `feat/040-growth-module-redesign` (created by the Spec Kit hook, project naming convention). | PASS |

**Post-design re-check (after Phase 1)**: unchanged. The contracts introduce no new dependency, no PII field, no colour-only status; the only budget item is the pre-existing entry-chunk size, recorded in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/040-growth-module-redesign/
├── plan.md              # This file
├── spec.md
├── research.md          # Phase 0 — R-01…R-17
├── data-model.md        # Phase 1 — column, seed rows, GrowthSummary, band vocabulary, rules, view-model
├── quickstart.md        # Phase 1 — validation runbook per user story
├── contracts/
│   ├── growth-summary-api.md
│   ├── anthropometry-source.md
│   ├── band-vocabulary.md
│   ├── growth-tab-ui.md
│   └── who-lms-seed.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 — /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/<id>_growth_source_on_anthropometry.py      # new (additive column)
├── app/
│   ├── data/who_lms/{README.md, who_height_for_age.csv, who_bmi_for_age.csv, who_weight_for_age.csv}   # new
│   ├── models/anthropometry.py                                  # + growth_source
│   ├── schemas/anthropometry.py                                 # + growth_source
│   ├── schemas/growth.py                                        # new: GrowthSummaryOut & parts
│   ├── seed_growth_data.py                                      # + WHO sources
│   ├── scripts/backfill_anthropometry.py                        # + recompute_to_source
│   ├── routers/anthropometry.py                                 # POST uses WHO; weight gate
│   ├── routers/growth.py                                        # + GET /athletes/{id}/growth-summary
│   ├── services/growth_summary.py                               # new (pure derivation + constants)
│   ├── services/training/growth_chart_builder.py                # WHO source, weight omitted > 10 y
│   ├── services/ai/use_cases/phv_explainer.py                   # audience param
│   └── services/ai/prompts/{registry.py, phv_explanation_coach_v1.md}   # new prompt
├── scripts/export_who_lms_csv.py                                # new (one-off, committed output)
└── tests/
    ├── routers/test_growth_summary.py                           # new
    ├── services/test_growth_seed.py                             # + WHO + parity
    ├── services/test_growth_summary.py                          # new
    ├── scripts/test_backfill_anthropometry.py                   # + recompute
    └── (existing anthropometry/newsletter tests updated)

frontend/
├── scripts/check-chart-chunk.sh                                 # new build gate
├── src/
│   ├── api/growth.ts                                            # new
│   ├── schemas/growth.schemas.ts · types/growth.types.ts         # new
│   ├── hooks/athletes/useGrowthSummary.ts                       # new
│   ├── lib/growth/{bands.ts (extended), rules.ts (new), window.ts (new: axis window + nice ticks), lms.ts}
│   ├── lib/measurementStatus.ts                                 # new: STATUS_META shared with dashboard
│   ├── components/athletes/growth/                              # new folder (see contracts/growth-tab-ui.md)
│   │   ├── GrowthTab.tsx · GrowthAlerts.tsx · GrowthStatusRow.tsx · Sparkline.tsx
│   │   ├── NextMeasurementCard.tsx · MaturationTimeline.tsx
│   │   ├── FamilyStageCard.tsx · FamilyBandCards.tsx
│   │   ├── PercentileChart.tsx · PercentileToolbar.tsx · PercentileTable.tsx · GrowthCurveSection.tsx
│   │   └── __tests__/ (unit, a11y, parent)
│   ├── components/athletes/{TrainingReadiness.tsx, MorphologyCard.tsx, PHVBadge.tsx, PercentileInterpretationBlock.tsx}   # refactored
│   ├── components/athletes/{GrowthCharts.tsx, PercentileCurves.tsx}   # deleted after re-homing tests
│   ├── components/ai/PHVExplanationCard.tsx                     # title + audience
│   ├── components/dashboard/MeasurementAlerts.tsx               # imports STATUS_META from lib
│   ├── routes/athletes/AthleteDetailPage.tsx · routes/parents/MyAthleteDetailPage.tsx   # lazy GrowthTab, tiles, no auto-select
│   └── test/msw/growthSummaryHandlers.ts                        # new
└── e2e/{growth.spec.ts, growth-parent.spec.ts (new), history.spec.ts (updated)}
```

**Structure Decision**: Web application layout already in place (`backend/app/*`, `frontend/src/*`). All new frontend UI lives under one folder `components/athletes/growth/` so the lazy boundary is a single import; backend additions follow the existing router → service → schema split.

## Phase 0 — Research (complete)

See `research.md`. All Technical Context unknowns resolved (R-01…R-17); the bundle claim in spec SC-005 was verified against a real build.

## Phase 1 — Design (complete)

- `data-model.md`: additive column, WHO rows, `GrowthSummary` derivation rules, band vocabulary, rule table, view-model.
- `contracts/`: endpoint, source/seed/recompute, band vocabulary, UI contract, WHO data invariants.
- `quickstart.md`: per-story validation commands and manual checks, bundle gate, post-deploy smoke.
- Agent context: `CLAUDE.md` active-feature block refreshed via `/speckit-agent-context-update`.

## Phase 2 — Task generation (next: `/speckit-tasks`)

Ordering constraints for the task generator (from spec priorities and research):

1. **Correctness first, no visual change** — parent latest-record regression test + fix; band alignment (D2) in `bands.ts`; FC-max removal; `history.spec.ts` decoupled from auto-select.
2. **Reference standard** — exporter + CSVs + README; seed; migration; POST source switch + weight gate; recompute pass + report; PDF builder switch; parity tests. Gate: `pytest` default lane + one `-m mysql` run of migration/backfill.
3. **Growth summary** — schema, service, router, tests; frontend api/schema/types/hook/MSW.
4. **Coach tab** — characterization tests → `lib/growth/{rules,window}` → `growth/` components (status row / alerts / next measurement / timeline in parallel with chart split) → `TrainingReadiness`, `MorphologyCard`, `PHVBadge` refactors → page wiring (lazy, tiles, no auto-select) → delete old components → build gate script → jest-axe → Playwright coach spec.
5. **Family mode** — family cards, simplified chart preset, `hideAdvanced`, AI audience, parent page wiring, parent Playwright spec, privacy audit.
6. **Close-out** — docs (`implementation-status.md`, `technical-notes.md`, `docs/04-percentiles/workflow.md` banner, `docs/06-parents/workflow.md:26`), CLAUDE.md block, smoke.

Agent tiering (per `.claude/agents/README.md`): leads = opus (`engineering-lead` for wave orchestration, `data-platform-lead` for the reference-standard wave), workers = sonnet (`fastapi-architect`, `database-architect`, `react-ui-engineer` ×2 in parallel, `qa-engineer`, `data-privacy-guard`, `parent-communicator` for family copy, `technical-writer`, `release-manager`).

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Entry bundle already 336.68 kB gzip (> 250 kB, Constitution IV) — **pre-existing**, not introduced by this feature | Recorded so the build gate has a baseline; this feature removes the static recharts import and the WHO JSON from the entry chunk (≈ 130 kB gzip) | Doing nothing keeps the violation; a full route-level code-splitting pass of `App.tsx` is a separate feature (out of scope) |
| Two mirrors of LMS math remain (backend `services/growth.py`, client `lib/growth/lms.ts`) | The client still needs LMS rows to draw reference *curves* offline; athlete Z/percentiles now come only from the server (FR-003) | Fetching curve points from `/growth-reference` per indicator/sex adds a request on a 3G surface for static data the client already ships; a parity test pins the two implementations together |
