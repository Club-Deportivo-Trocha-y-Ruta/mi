# Implementation Plan: Prefill results import from an existing competition

**Branch**: `015-prefill-import-from-competition` | **Date**: 2026-06-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/015-prefill-import-from-competition/spec.md`

## Summary

When the coach opens the results-import wizard **from an existing competition** (`/competitions/{id}/import`), it must open already populated with everything the system knows about that competition (name, date, city, series, type, round) — instead of starting blank and defaulting "Tipo de competencia" to *Copa*, which is wrong for a championship. Prefilled metadata is shown **locked/read-only**, type and series are **derived** (not editable inside import), the round (`válida #`) is **hidden for championships**, and the standalone `/competitions/import` flow is left untouched.

**Technical approach — frontend-only.** The container page already knows the event id (`useParams`) but never passes it to the wizard (`<ImportWizard onCompleted=… />`). The fix: pass `raceEventId` into `ImportWizard`; when present, the wizard fetches the event (`useRaceEvent`, already exposes `series_id`, `sequence_number`, `name`, `event_date`, `location`, `is_championship`) and its series (`useRaceSeries` → `kind` + `name` by `series_id`), `reset()`s the React Hook Form with those values, renders the identity fields as a locked read-only summary, derives `series_kind` from `series.kind`, and hides `válida #` for championships. The existing `/parse` → `/dry-run` → `/commit` pipeline is unchanged: prefilling the exact stored values makes the backend's header-matching resolve to the same `(series_id, sequence_number)` and link results to the exact competition via its revision/parent path. No migration, no new endpoint, no schema change (satisfies FR-011/FR-012).

## Technical Context

**Language/Version**: TypeScript ~6.0 (frontend); Python 3.14 / FastAPI (backend — **no backend changes in this feature**)

**Primary Dependencies**: React 19, Vite 8, React Hook Form + Zod, TanStack Query, shadcn/ui + Tailwind v4. Existing hooks `useRaceEvent` (`hooks/race/useRaceEvents.ts`), `useRaceSeries` (`hooks/race/useRaceSeries.ts`); API clients `api/raceSeries.ts`, `api/raceImports*`. Reused component: `components/competitions/import/ImportWizard.tsx`.

**Storage**: N/A for this feature (read-only consumption of existing `race_events` + `race_series`). No new tables/columns.

**Testing**: Vitest 4 + Testing Library + MSW (unit/integration), jest-axe (a11y), `@playwright/test` 1.50 (e2e — config + `e2e/` suite already present, e.g. `cup-vs-championship.spec.ts`), `@stryker-mutator/core` + `@stryker-mutator/vitest-runner` 9.6 for **mutation testing** (deps installed; `stryker.config.json` to be added, scoped to the new prefill logic).

**Target Platform**: Web SPA — coach on desktop (primary) and tablet in the field; intermittent 3G/4G.

**Project Type**: Web application (frontend `frontend/`, backend `backend/`). This feature touches **frontend only**.

**Performance Goals**: No regression to import route bundle. Prefill = 2 cached GETs (`race-event/{id}`, `race-series` list) via TanStack Query, no N+1. Initial route ≤250 KB gz / lazy route ≤150 KB gz (wizard already lazy-loaded). LCP budgets per constitution unchanged.

**Constraints**: Render free-tier cold start (~50 s) must surface a clear "starting" state during prefill fetch (reuse existing wizard/skeleton loading pattern). Minors-privacy: prefill carries only competition-level metadata already visible on the detail view; no minor PII introduced or logged.

**Scale/Scope**: One reused component (`ImportWizard.tsx`), one container page (`CompetitionImportPage.tsx`), one small prefill hook/helper, plus tests. ~1 club, dozens of competitions/season.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan satisfies it |
|---|---|
| **I. Code Quality & Maintainability** | Reuses the existing wizard and hooks; no new component pattern. New prefill logic extracted into a small, named, documented hook/helper (`useImportPrefill`) with explicit inputs/outputs. `eslint` + `tsc --noEmit` are blockers. No duplication (rule of three respected — single prefill source). |
| **II. Testing (NON-NEGOTIABLE)** | Vitest+RTL+MSW unit/integration for every branch (prefilled lock, derived type, championship hides round, block-on-unresolvable-series, standalone unchanged); jest-axe on the wizard (zero violations); Playwright e2e for both flows + championship + block path; **mutation testing** (Stryker) scoped to the new prefill logic. Regression test asserts the standalone path is unaffected. Privacy invariant test: prefilled flow exposes no minor PII. |
| **III. UX Consistency** | español neutro (Colombia) copy with diacritics; shadcn/ui + Tailwind tokens; locked fields rendered as a read-only summary (matches the detail "Información" card), not greyed inputs; RHF+Zod retained; loading/empty/error/blocked states designed; touch targets ≥48px; focus-trap and Escape unaffected; status/badge semantics (amber championship `CD`) reused. WCAG 2.1 AA: read-only via `readOnly`/static text + `aria-disabled`, never `disabled` that drops focus or omits the value. |
| **IV. Performance** | No new endpoint; 2 cached GETs through TanStack Query (no N+1). Wizard stays lazy-loaded. No bundle regression ≥10% expected (logic-only addition). Cold-start "starting server" state surfaced during prefill fetch. |

**Privacy / Security gate**: `data-privacy-guard` audit applies (feature reads competition metadata only; assert no minor name/DOB/medical/PII in prefill payloads, logs, or test fixtures). RBAC unchanged — import remains coach/admin only; prefilled entry point grants no new access (FR-010).

**Result**: ✅ PASS — no violations. Complexity Tracking table not required.

## Project Structure

### Documentation (this feature)

```text
specs/015-prefill-import-from-competition/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (read-model / view-model — no DB change)
├── quickstart.md        # Phase 1 output (manual verification script)
├── contracts/           # Phase 1 output (frontend component + data contracts; no new API)
│   ├── import-wizard-props.md
│   └── prefill-data-contract.md
├── checklists/
│   └── requirements.md  # from /speckit-specify + /speckit-clarify
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
frontend/
├── src/
│   ├── routes/competitions/
│   │   └── CompetitionImportPage.tsx        # MODIFY: pass raceEventId into <ImportWizard>
│   ├── components/competitions/import/
│   │   ├── ImportWizard.tsx                 # MODIFY: accept raceEventId; prefill+lock; derive type; hide válida; block path
│   │   └── __tests__/                       # ADD: prefill/lock/block/standalone unit + a11y tests
│   ├── hooks/race/
│   │   ├── useRaceEvents.ts                 # REUSE (useRaceEvent)
│   │   ├── useRaceSeries.ts                 # REUSE (resolve series by series_id)
│   │   └── useImportPrefill.ts             # ADD: composes event+series → prefill view-model + status
│   └── test/msw/
│       └── raceSeriesHandlers.ts            # REUSE/EXTEND for prefill tests
├── e2e/
│   └── prefill-import-from-competition.spec.ts  # ADD: Playwright e2e
├── stryker.config.json                      # ADD: mutation testing config (scoped)
└── package.json                             # MODIFY: add "test:mutation" script

backend/   # NO CHANGES in this feature
```

**Structure Decision**: Web application; **frontend-only** change. Backend `race_events`/`race_series`/import endpoints already expose everything needed (`series_id`, `sequence_number`, `kind`, `name`, `event_date`, `location`, `is_championship`). The feature is a wiring + view-model + lock/derive/hide concern in `ImportWizard.tsx` and its container, plus a new `useImportPrefill` hook and the test surface.

## Complexity Tracking

> No Constitution Check violations — table intentionally empty.
