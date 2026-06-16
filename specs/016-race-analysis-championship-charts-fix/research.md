# Phase 0 Research — Race-analysis Championship Charts Fix

All Technical Context unknowns are resolved; **no `NEEDS CLARIFICATION` remains**. The one product
ambiguity (season-aggregate semantics in Distribution) was resolved with the coach via a clarifying
question — see Decision 5.

## Root-cause findings (codebase evidence)

| # | Evidence | Consequence |
|---|---|---|
| RC1 | `services/race/analytics_charts.py:319` — distribution target lookup `AND e.sequence_number = :valida_num` | Championship (stored `sequence_number=1` since feature 014) never matches the frontend's `valida_num=99`. |
| RC2 | `analytics_charts.py:334-350` — empty fallback returns `DistributionResponse(category_id=0, category_code="")` | Violates the schema `category_id: ge=1` / `category_code: min_length=1` (`schemas/athlete_race_analysis.py:330-331`) → `ResponseValidationError` → HTTP 500 on **any** no-data race, not only the championship. |
| RC3 | `components/athletes/ai/DistributionChart.tsx:33-42` — `VALIDA_OPTIONS` hard-codes `{ value: 99, label: "Cto. Dep." }` | Frontend sends a round number that no longer maps to the championship event. |
| RC4 | `components/athletes/ai/EvolutionChart.tsx:42-46` — `romanForValida(99)→"CD"`, but championship now arrives as `valida_num=1`; `XAxis dataKey="roman"` (line 221) | `romanForValida(1)="I"` merges the championship with cup Válida I → mislabeled/merged point (violates FR-009/011). |
| RC5 | `api/athleteRaceAnalysis.ts:130-140` is the **only** caller of `/distribution`; the agentic pipeline uses its own `valida_num` contract (`LaunchAnalysisForm.tsx`, `services/race/schemas`) | Flipping `/distribution` to `event_id` is safe and in scope; the AI/chat/import contracts are untouched. |

## Decisions

### Decision 1 — Identify races by `event_id`, not round number
- **Decision**: The Distribution chart selects a race by its stable `event_id`; the backend looks up `WHERE rr.event_id = :event_id AND rr.athlete_id = :athlete_id`. Round number is no longer part of race identity.
- **Rationale**: `event_id` is unique per competition and already present on `race_results`/`race_events`/`EvolutionPoint`. It is the spec's "Race"/"Athlete race participation" entity. It eliminates the cup↔championship collision at the root (SC-004, FR-004) and fixes the championship lookup (FR-006). Feature 014 explicitly retired `sequence_number=99`.
- **Alternatives rejected**:
  - *Accept both `99` and `1` for championship*: perpetuates the retired convention, still collides cup I with championship (both `sequence_number=1`), brittle.
  - *Look up by `(season, series_kind, sequence_number)`*: more join surface, still ambiguous if a season ever has >1 championship; `event_id` is simpler and exact.

### Decision 2 — Add a dedicated `GET …/race-analysis/races` participation endpoint
- **Decision**: New read-only endpoint returns one entry per race the athlete actually competed in for a season — `{ event_id, sequence_number, series_kind, event_date, event_name, location, label }` — ordered by `event_date`. It is the single source of truth for the Distribution picker (FR-003/004/005).
- **Rationale**: The frontend currently hard-codes the option list; there is no endpoint exposing real participation. A dedicated read model keeps labels and identity server-authored (consistent, one place to localize) and lets the picker list exactly the competed races and nothing else (FR-003, US2-AC4). Event name/city come from the public federation PDF — not minor PII.
- **Alternatives rejected**:
  - *Derive the list client-side from the `/evolution` series*: evolution is metric-scoped and lacks `series_kind`/`location`/label; coupling the picker to a metric query is fragile.
  - *Reuse `/race-events/available-for-calendar`*: that endpoint is season-wide (all events), not athlete-scoped participation — would list races the athlete did not run (violates FR-003 / US2-AC4).

### Decision 3 — Replace the invalid empty fallback with schema-valid no-data + 404
- **Decision**: Delete the `category_id=0/category_code=""` branch. With a valid `event_id` the athlete's own result row is always found, so `category_id`/`category_code` are real. The "no comparable data" case (DNF, or field too small for a curve) returns a **valid** `DistributionResponse` with `athlete_time_ms` possibly `null`, `curve=[]`, `confidence=low` → frontend renders the friendly "no data for this race" state (FR-001/FR-002). An `event_id` the athlete did not compete in returns a clean **404** (not a 500, no identifying data echoed).
- **Rationale**: Removes the only path that could 500 and satisfies "never an error or blank screen". Keeps `extra="forbid"` + `ge=1`/`min_length=1` invariants intact (no schema loosening that could hide bugs).
- **Alternatives rejected**: *Loosen `category_id` to allow 0* — weakens the contract and leaves a meaningless category on the wire.

### Decision 4 — Evolution emits `series_kind` + `label`; frontend keys by `event_id`
- **Decision**: Add `series_kind: ("cup"|"championship")` and a display `label` to `EvolutionPoint` (derived in the existing CTE via `s.kind`). The chart keys points/dots by `event_id` and labels the championship as its own marker ("CD"/"Cto. Dep."), placed by `event_date` (FR-009/010/011).
- **Rationale**: Additive, no migration; `event_date` ordering already exists (`analytics_charts.py:175`). Keying by `event_id` prevents two `sequence_number=1` races from merging on a categorical axis.
- **Alternatives rejected**: *Cross-reference the races endpoint in the Evolution component* — adds a second dependent query for data the evolution serializer can supply directly.

### Decision 5 — "Temporada (todas)" = informational state (coach decision)
- **Decision**: The Distribution picker keeps a "Temporada (todas)" entry (FR-007); selecting it shows a calm informational message ("La distribución se calcula por carrera. Elige una válida o el campeonato…") and issues **no** `/distribution` request.
- **Rationale**: Coach-confirmed via clarifying question. A single normal curve across races of different distance/difficulty is statistically misleading — consistent with the existing coach override that removed cross-track absolute-time comparisons in `ComparatorPanel`. It satisfies "available and works" (a defined, non-error state) without inventing a meaningless aggregate curve. Edge case "athlete competed in zero races" → only this entry + friendly empty.
- **Alternatives rejected**: *Aggregate curve* (statistically misleading); *per-race mini-table* (more scope than the fix warrants, not requested); *drop the option* (deviates from FR-007 literal).

### Decision 6 — `raceCalendar.ts` left unchanged
- **Decision**: Do not touch `lib/raceCalendar.ts` (`getRaceMeta`, key `99`).
- **Rationale**: The out-of-scope `ComparatorPanel` still keys race metadata by `99`. The new Distribution/Evolution path takes labels from the backend, so it does not depend on `raceCalendar`. Decoupling avoids regressing an out-of-scope surface (FR-008, SC-005).

## Tooling research (requested: Context7 · web · sequential-thinking · Playwright · mutation)

- **Mutation testing (StrykerJS 9.6.1)** — verified via Context7 (`/stryker-mutator/stryker-js`): the repo's `frontend/stryker.config.json` already uses the current schema (`mutate[]` glob array, `thresholds.break`, `testRunner: "vitest"` via `vitest.stryker.config.ts`). Plan: extend `mutate[]` with the new pure modules (`src/lib/raceOptionLabel.ts`, `src/hooks/athletes/useAthleteRaces.ts`); keep thresholds `high:80 / low:70 / break:70`; require zero surviving mutants on the `event_id` identity branch, the championship-label branch, and the aggregate-sentinel branch — mirroring the feature 012/015 gate convention.
- **Playwright e2e** — reuse `frontend/playwright.config.ts` and the `cup-vs-championship.spec.ts` pattern (coach login, navigate to athlete AI-analysis). New spec asserts: selecting the championship in Distribution shows no error + a curve or friendly empty; Evolution shows the championship as exactly one distinctly-labeled point in date order.
- **Recharts categorical-axis collision** — confirmed by code reading: `dataKey="roman"` collapses duplicate category labels. Mitigation is keying by `event_id` and labeling via `series_kind`; no library change needed (Recharts already in use).
- **Sequential-thinking** drove the two-bug decomposition and the backward-compatibility check (only `DistributionChart` consumes `/distribution`).

## Open risks / verification carried into tasks

1. Add an explicit guard/test confirming **no other consumer** sends `valida_num` to `/distribution` after the flip (grep already shows only `DistributionChart`; lock it with a test).
2. `data-privacy-guard` audit on the new races endpoint and the 404 path (no minor PII in body/logs).
3. Confirm `RaceSeriesKind` import path (`app.models.race_series.RaceSeriesKind`) and that `s.kind` is selectable in the existing CTEs (feature 014 migration `b1c2d3e4f5a6` present).

## T001 regression guard (verified)

Consumidor único confirmado (código de producción, excluye tests y mocks):

- `frontend/src/api/athleteRaceAnalysis.ts:130` — `getAthleteDistribution()` define la llamada HTTP a `/distribution`.
- `frontend/src/hooks/athletes/useAthleteDistribution.ts:10,25` — único hook que importa `getAthleteDistribution`; invoca el hook en línea 25.
- `frontend/src/components/athletes/ai/DistributionChart.tsx:28,77` — único componente que importa `useAthleteDistribution`; lo consume en línea 77.

Invariante single-consumer: **sí se cumple**. Ningún otro archivo de producción llama a `getAthleteDistribution` ni a `useAthleteDistribution`.

Contrato agentico separado confirmado: `LaunchAnalysisForm.tsx` (líneas 54, 86, 91, 98-99, 104, 121, 128) y `backend/app/services/race/schemas.py:212` usan `valida_num`/`valida_nums` para lanzar el pipeline de IA, **no** para consultar `/distribution`. Son contratos distintos y quedan fuera del alcance de este fix.
