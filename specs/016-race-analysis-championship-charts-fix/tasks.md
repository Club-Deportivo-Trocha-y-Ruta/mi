---

description: "Task list — Race-analysis Distribution & Evolution championship fix"
---

# Tasks: Race-analysis Distribution & Evolution charts handle the Departmental Championship correctly

**Input**: Design documents from `/specs/016-race-analysis-championship-charts-fix/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: INCLUDED — Constitution II (Testing NON-NEGOTIABLE) requires a regression test that fails on the unfixed code for every bug fix. Test tasks are therefore mandatory here, not optional.

**Organization**: Tasks grouped by user story (P1→P2→P3) for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description (→ agent)`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks).
- **[Story]**: US1 / US2 / US3 (maps to spec.md user stories). Setup/Foundational/Polish have no story label.
- Each task ends with `(→ agent: <name>)` — the specialized agent assigned to execute it.

## Agent assignment legend

| Agent | Scope in this feature |
|---|---|
| `fastapi-architect` | FastAPI routes, Pydantic schemas, RBAC wiring |
| `data-analyst` | `analytics_charts.py` SQL/read-model logic (distribution, evolution, participation) |
| `react-ui-engineer` | React components, hooks, api client, TS types |
| `qa-engineer` | pytest, vitest, jest-axe, Playwright e2e, Stryker mutation gate |
| `data-privacy-guard` | Minors-privacy audit (Ley 1581) |
| `technical-writer` | docs/ + CLAUDE.md status updates |
| `devops-engineer` | local data/env preconditions for validation |

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm preconditions; no scaffolding needed (code exists).

- [X] T001 [P] Verify `/api/.../race-analysis/distribution` has only one consumer (grep `getAthleteDistribution` / `useAthleteDistribution`; confirm the agentic `valida_num` contract is untouched) and record it as a regression guard note in `specs/016-race-analysis-championship-charts-fix/research.md` (→ agent: qa-engineer)
- [X] T002 [P] Confirm the local/dev DB has feature-014 data (migration `b1c2d3e4f5a6` applied) and at least one athlete who competed in cup rounds **and** the Departmental Championship in season 2026, per `quickstart.md` prerequisites (→ agent: devops-engineer)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared, pure label/identity helpers used by the races endpoint (US2) and the Evolution serializer (US3).

**⚠️ CRITICAL**: Complete before US2/US3 implementation.

- [X] T003 [P] Add pure label builder `build_race_label(kind, sequence_number, location)` (cup → `"Válida {roman} — {city}"`, championship → `"Cto. Dep. — {city}"`) in `backend/app/services/race/race_labels.py`, importing `RaceSeriesKind` from `app.models.race_series` (→ agent: fastapi-architect)
- [X] T004 [P] Add frontend pure helpers in `frontend/src/lib/raceOptionLabel.ts`: `SEASON_AGGREGATE` sentinel, `isAggregateOption()`, `aggregateLabel()` ("Temporada (todas)"), and `raceOptionValue()` keyed by `event_id` (→ agent: react-ui-engineer)
- [X] T005 [P] Unit tests: pytest for `build_race_label` (cup roman + championship + null city) in `backend/tests/services/test_race_labels.py`; vitest for `raceOptionLabel.ts` branches in `frontend/src/lib/raceOptionLabel.test.ts` (→ agent: qa-engineer)

**Checkpoint**: Shared helpers ready — user stories can proceed.

---

## Phase 3: User Story 1 - Selecting any race in Distribution never breaks (Priority: P1) 🎯 MVP

**Goal**: The Distribution chart never errors/blanks; the championship and any no-data race return a distribution or a friendly "no data" state.

**Independent Test**: `GET /distribution?event_id=<championship>` → 200; UI selecting that race (via default selection) shows a curve or friendly empty, no error. No-data race → friendly state; non-participated event → clean 404.

### Tests for User Story 1 ⚠️ (write first, must FAIL on unfixed code)

- [X] T006 [P] [US1] pytest: `/distribution?event_id=<championship event>` returns 200 with the championship's own category (pre-fix `valida_num=99` → 500) in `backend/tests/routers/test_athlete_race_analysis_distribution.py` (→ agent: qa-engineer)
- [X] T007 [P] [US1] pytest: no-comparable-data (DNF / field < min) returns a valid 200 (`category_id ≥ 1`, `athlete_time_ms` may be null, `curve=[]`, `confidence="low"`) — never 500/`category_id=0`, same file (→ agent: qa-engineer)
- [X] T008 [P] [US1] pytest: non-participated `event_id` → 404 with no `athlete_id`/`competitor_id` in body, same file (→ agent: qa-engineer)
- [X] T009 [P] [US1] vitest + jest-axe: `DistributionChart` renders friendly "no data" + error states (no raw exception text), zero a11y violations in `frontend/src/components/athletes/ai/__tests__/DistributionChart.test.tsx` (→ agent: qa-engineer)

### Implementation for User Story 1

- [X] T010 [US1] Change `DistributionResponse` race identity `valida_num` → `event_id (ge=1)` in `backend/app/schemas/athlete_race_analysis.py` (→ agent: fastapi-architect)
- [X] T011 [US1] Rewrite `build_distribution` to look up the target `WHERE rr.event_id = :event_id AND rr.athlete_id = :athlete_id`; **delete** the `category_id=0/category_code=""` fallback; return a schema-valid no-data payload when the field is too small/DNF; signal non-participated event so the router can 404, in `backend/app/services/race/analytics_charts.py` (→ agent: data-analyst)
- [X] T012 [US1] Update `GET /distribution` route param `valida_num` → `event_id` (`Query(..., ge=1)`) and map the non-participated signal to `HTTPException(404)` in `backend/app/routers/athlete_race_analysis.py` (→ agent: fastapi-architect)
- [X] T013 [US1] Flip `getAthleteDistribution(athleteId, eventId)` in `frontend/src/api/athleteRaceAnalysis.ts` and `useAthleteDistribution` key/param in `frontend/src/hooks/athletes/useAthleteDistribution.ts` (→ agent: react-ui-engineer)
- [X] T014 [US1] Wire `DistributionChart` data path to `event_id` (replace `validaNum` state; accept `defaultEventId`), and harden the no-data/empty/error states in español neutro in `frontend/src/components/athletes/ai/DistributionChart.tsx` + mirror the type change in `frontend/src/types/athleteRaceAnalysis.types.ts` (→ agent: react-ui-engineer)

**Checkpoint**: Championship and no-data races open with no error (SC-001, SC-002). MVP demoable.

---

## Phase 4: User Story 2 - Distribution lists the athlete's real races, identified correctly (Priority: P2)

**Goal**: The picker offers exactly the races the athlete competed in (cup rounds + championship), each labeled with real name + round marker and tied to its own `event_id`, plus a "Temporada (todas)" entry.

**Independent Test**: Open the picker for an athlete with several rounds + the championship → each competed race listed once with correct label, no collision, aggregate present; non-competed races absent.

### Tests for User Story 2 ⚠️

- [X] T015 [P] [US2] pytest: `GET /races?season=2026` lists exactly competed races (cup + championship), ordered by `event_date`, correct labels, excludes non-competed; a cup round and championship that shared a round number resolve to two distinct `event_id` (SC-004) in `backend/tests/routers/test_athlete_race_analysis_races.py` (→ agent: qa-engineer)
- [X] T016 [P] [US2] pytest: races endpoint RBAC (parent of own child → 200; other-athlete parent → 403) and privacy (no `athlete_id`/`competitor_id` in body), same file (→ agent: qa-engineer)
- [X] T017 [P] [US2] vitest + jest-axe: picker lists backend races with labels, "Temporada (todas)" present and selecting it shows the informational state with **no** `/distribution` request, zero-races shows only the aggregate + friendly empty, in `frontend/src/components/athletes/ai/__tests__/DistributionChart.test.tsx` (→ agent: qa-engineer)

### Implementation for User Story 2

- [X] T018 [P] [US2] Add `RaceParticipationOption` + `RaceParticipationResponse` schemas (`extra="forbid"`, no athlete/competitor ids) in `backend/app/schemas/athlete_race_analysis.py` (→ agent: fastapi-architect)
- [X] T019 [US2] Implement `list_athlete_races(db, *, athlete_id, season)` — single query over `ix_race_results_athlete_event` joining `race_events`/`race_series`, one row per competed event, label via `build_race_label`, ordered by `event_date` — in `backend/app/services/race/analytics_charts.py` (→ agent: data-analyst)
- [X] T020 [US2] Add `GET /{athlete_id}/race-analysis/races` route guarded by `verify_athlete_access`, returning `RaceParticipationResponse`, in `backend/app/routers/athlete_race_analysis.py` (→ agent: fastapi-architect)
- [X] T021 [P] [US2] Add `getAthleteRaces(athleteId, season)` to `frontend/src/api/athleteRaceAnalysis.ts`, `useAthleteRaces` hook in `frontend/src/hooks/athletes/useAthleteRaces.ts`, and `RaceParticipationOption` type in `frontend/src/types/athleteRaceAnalysis.types.ts` (→ agent: react-ui-engineer)
- [X] T022 [US2] Rewrite the `DistributionChart` race picker: source options from `useAthleteRaces`, `value = event_id`, render server `label`, prepend the `SEASON_AGGREGATE` "Temporada (todas)" informational entry (no fetch on select), handle zero-races, in `frontend/src/components/athletes/ai/DistributionChart.tsx` (depends on T014, T021) (→ agent: react-ui-engineer)

**Checkpoint**: Picker is unambiguous and complete (SC-004); US1 still passes.

---

## Phase 5: User Story 3 - Evolution shows the Departmental Championship as its own point (Priority: P3)

**Goal**: The championship appears as exactly one distinct, date-ordered point in Evolution, labeled as the championship — never merged with or mislabeled as a cup round.

**Independent Test**: Open Evolution for an athlete who ran the championship → one distinct point labeled "CD"/"Cto. Dep." between the May and August rounds, not merged with Válida I.

### Tests for User Story 3 ⚠️

- [X] T023 [P] [US3] pytest: each `EvolutionPoint` carries `series_kind` + `label`; the championship point is distinct from cup Válida I and ordered by `event_date`, in `backend/tests/routers/test_athlete_race_analysis_evolution.py` (→ agent: qa-engineer)
- [X] T024 [P] [US3] vitest + jest-axe: `EvolutionChart` renders the championship as its own point keyed by `event_id` (no merge with Válida I), labeled CD; DNF list uses `label`; zero a11y violations, in `frontend/src/components/athletes/ai/__tests__/EvolutionChart.test.tsx` (→ agent: qa-engineer)

### Implementation for User Story 3

- [X] T025 [US3] Add `series_kind` (`cup|championship`) + `label` (additive) to `EvolutionPoint` in `backend/app/schemas/athlete_race_analysis.py` (→ agent: fastapi-architect)
- [X] T026 [US3] In `build_evolution`, add `s.kind` to the `athlete_results` CTE select and emit `series_kind` + `label` (via `build_race_label`) per point, in `backend/app/services/race/analytics_charts.py` (→ agent: data-analyst)
- [X] T027 [US3] `EvolutionChart`: label points via `series_kind`/`label`, key dots and the categorical axis by `event_id` (remove the `romanForValida` collision at `sequence_number=1`), DNF list uses `label`, in `frontend/src/components/athletes/ai/EvolutionChart.tsx` + mirror `EvolutionPoint` type in `frontend/src/types/athleteRaceAnalysis.types.ts` (→ agent: react-ui-engineer)

**Checkpoint**: Championship is one distinct, correctly-ordered, correctly-labeled point (SC-003).

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T028 [P] Playwright e2e `frontend/e2e/race-analysis-championship.spec.ts` (coach: select championship in Distribution → no error + curve/empty; Evolution shows CD as a distinct, date-ordered point), extending the `cup-vs-championship.spec.ts` pattern (→ agent: qa-engineer)
- [X] T029 [P] Extend `frontend/stryker.config.json` `mutate[]` with `src/lib/raceOptionLabel.ts` and `src/hooks/athletes/useAthleteRaces.ts`; keep thresholds `high:80/low:70/break:70`; require zero surviving mutants on the `event_id` identity, championship-label, and aggregate-sentinel branches (→ agent: qa-engineer)
- [X] T030 `data-privacy-guard` audit of the races endpoint, the distribution 404 path, and both charts: no minor PII in responses/logs/errors, parents see pseudonyms only (FR-013/014, SC-006) (→ agent: data-privacy-guard)
- [X] T031 Confirm `frontend/src/lib/raceCalendar.ts` is **unchanged** and the out-of-scope `ComparatorPanel` still renders (regression guard for FR-008/SC-005) (→ agent: react-ui-engineer)
- [X] T032 [P] Run `quickstart.md` validation end-to-end (API smoke + UI walkthrough + automated gates) and record results (→ agent: qa-engineer)
- [X] T033 [P] Update `docs/implementation-status.md` and the CLAUDE.md implementation-status table with the feature 016 row (→ agent: technical-writer)

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (P1)**: no dependencies — start immediately.
- **Foundational (P2)**: after Setup; blocks US2 + US3 (provides label/identity helpers). US1 does not depend on it.
- **US1 (P3 phase)**: after Setup. The MVP — backend distribution fix + frontend states.
- **US2**: after Foundational + US1 (reuses the event_id distribution data path: T013/T014).
- **US3**: after Foundational (independent of US1/US2; shares only `build_race_label`).
- **Polish (P6)**: after the targeted stories complete.

### User story dependencies

- **US1 (P1)**: independent — testable via API (`event_id`) and the chart's default selection.
- **US2 (P2)**: builds on US1's `event_id` data path; independently testable at the picker level.
- **US3 (P3)**: independent of US1/US2; depends only on the foundational label builder.

### Within each story

- Tests written first and FAIL before implementation.
- Backend schema → service → route → frontend api/hook → component.
- `analytics_charts.py` tasks within a story are sequential (same file): T011 (US1), T019 (US2), T026 (US3) do not run [P] against each other.

### Parallel opportunities

- Setup T001/T002 in parallel.
- Foundational T003/T004 in parallel (T005 after).
- All `[P]` test tasks within a story in parallel.
- US3 can be developed in parallel with US1/US2 by a different agent once Foundational is done.

---

## Parallel Example: User Story 1

```bash
# Tests first (parallel — different files / assertions):
Task: "T006 pytest championship distribution 200 (qa-engineer)"
Task: "T007 pytest no-data distribution valid 200 (qa-engineer)"
Task: "T008 pytest non-participated event 404 (qa-engineer)"
Task: "T009 vitest+jest-axe DistributionChart friendly states (qa-engineer)"

# Then implementation in dependency order:
Task: "T010 DistributionResponse event_id (fastapi-architect)"
Task: "T011 build_distribution by event_id, drop invalid fallback (data-analyst)"
Task: "T012 /distribution route event_id + 404 (fastapi-architect)"
Task: "T013 api client + hook event_id (react-ui-engineer)"
Task: "T014 DistributionChart event_id + states (react-ui-engineer)"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Setup (T001–T002) → Foundational (T003–T005).
2. US1 (T006–T014) → **STOP & VALIDATE**: championship + no-data races never error.
3. Deploy/demo the MVP (the live defect is gone).

### Incremental delivery

1. Foundation ready → US1 (MVP) → US2 (usable, unambiguous picker) → US3 (Evolution point).
2. Each story tested independently; no regression to working races or the out-of-scope ComparatorPanel.
3. Polish: e2e + mutation gate + privacy audit + quickstart + docs.

### Parallel agent strategy

- After Foundational: `data-analyst` + `fastapi-architect` drive backend per story; `react-ui-engineer` drives the matching frontend; `qa-engineer` writes the failing tests up front. `data-privacy-guard` runs the audit before merge; `technical-writer` closes docs.

---

## Notes

- `[P]` = different files, no incomplete dependency.
- No database migration — `race_series.kind`, `event_id`, and `event_date` already exist (feature 014, migration `b1c2d3e4f5a6`).
- Out of scope (do not touch): AI insight text/chat, imports, results, ranking, `ComparatorPanel`, `raceCalendar.ts`, and the agentic `valida_num` contract.
- Commit after each task or logical group (Conventional Commits, type in English, description in español latino).
