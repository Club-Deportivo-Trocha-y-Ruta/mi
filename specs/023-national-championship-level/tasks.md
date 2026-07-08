# Tasks: National Championship Support (Series Level)

**Input**: Design documents from `/specs/023-national-championship-level/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-delta.md, quickstart.md

**Tests**: INCLUDED — constitution Principle II (Testing) is NON-NEGOTIABLE for this project; every router/service/UI change ships with tests.

**Organization**: Tasks grouped by user story. Each task carries an **agent assignment** (`Agente:`) with the recommended specialized agent and model tier, per user request.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 / US2 / US3 traceability
- `Agente: <agent> (<model>)` — recommended executor. Model tiers: **haiku** = mechanical/low-risk edits; **sonnet** = standard implementation & tests (project agents' default). No task here warrants opus — blast radius is small and design is fully resolved.

## Agent/model assignment rationale

| Agent | Model | Used for |
|---|---|---|
| `database-architect` | sonnet | Alembic migration (enum column, server_default) |
| `fastapi-architect` | sonnet | Model/schema/router/service changes |
| `react-ui-engineer` | sonnet | Forms, wizard, labels, TS types |
| `qa-engineer` | sonnet | Test suites backend + frontend, regression invariants |
| `technical-writer` | haiku | Docs/status updates (mechanical, template-following) |
| general-purpose | haiku | Pure-mechanical single-string edits (filter copy) |

---

## Phase 1: Setup

**Purpose**: No project initialization needed — existing web app. Single pre-flight check.

- [x] T001 Verify Alembic head is `a7b8c9d0e1f2` and working tree separates 022 changes before starting (`cd backend && alembic heads`; `git status`). Agente: `devops-engineer` (haiku)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema + types every story depends on. **BLOCKS all user stories.**

- [x] T002 [P] Add `RaceSeriesLevel` enum (`departmental|national`) and `level` column (`values_callable`, `nullable=False`, `default=departmental`) to `backend/app/models/race_series.py`, updating module docstring per data-model.md. Agente: `fastapi-architect` (sonnet)
- [x] T003 [P] Create Alembic migration `backend/alembic/versions/d3e4f5a6b7c8_add_race_series_level.py` — revision `d3e4f5a6b7c8`, down_revision `a7b8c9d0e1f2`, additive enum column with `server_default='departmental'`, symmetric downgrade (see data-model.md Migration contract). Agente: `database-architect` (sonnet)
- [x] T004 [P] Add `level` to `RaceSeriesCreate` (optional, default departmental) and `RaceSeriesRead` (required) in `backend/app/schemas/race_series.py`. Agente: `fastapi-architect` (sonnet)
- [x] T005 [P] Add `RaceSeriesLevel` type and `level` fields to `frontend/src/types/raceSeries.types.ts` (`RaceSeriesCreate.level?`, `RaceSeriesRead.level`) mirroring contracts/api-delta.md §1–2. Agente: `react-ui-engineer` (sonnet)

**Checkpoint**: Column + schemas + types exist; migration applies cleanly (`alembic upgrade head` on local MySQL) — user stories can start.

---

## Phase 3: User Story 1 — Register the National Championship before race day (Priority: P1) 🎯 MVP

**Goal**: Coach creates a national-level championship series + its Pereira event through the UI, correctly labeled, before results exist.

**Independent Test**: Create the series with level Nacional via UI/API, verify list shows "Campeonato Nacional", second event on same series → 409, organizer not overridden (quickstart Scenario 1).

### Tests for User Story 1 (write first, must fail pre-implementation)

- [x] T006 [P] [US1] Backend router tests in `backend/tests/test_race_series_router.py` (extend or create): create championship with `level=national` → 201 echoing level; omit level → 201 `departmental`; invalid level → 422; organizer persisted verbatim (never "Liga Vallecaucana"); GET list includes `level`. Agente: `qa-engineer` (sonnet)
- [x] T007 [P] [US1] INV-2 regression for national series in `backend/tests/test_race_events_championship_guard.py` (extend existing guard tests): second event on a `national` championship series → 409. Agente: `qa-engineer` (sonnet)
- [x] T008 [P] [US1] Frontend tests `frontend/src/routes/competitions/CompetitionFormPage.test.tsx` (extend): level select visible only when kind=championship, defaults Departamental, submit payload carries `level`; jest-axe on the form. Agente: `qa-engineer` (sonnet)

### Implementation for User Story 1

- [x] T009 [US1] Persist `body.level` in POST handler and include `level` in all `RaceSeriesRead` constructions in `backend/app/routers/race_series.py` (create + list). Agente: `fastapi-architect` (sonnet)
- [x] T010 [P] [US1] Create shared label helper `frontend/src/lib/raceSeriesLabels.ts` — `championshipLabel(level)` → "Campeonato Nacional"/"Campeonato Departamental" (+ short forms "Cto. Nal."/"Cto. Dep." for reuse), with unit test `raceSeriesLabels.test.ts`. Agente: `react-ui-engineer` (sonnet)
- [x] T011 [US1] Add level `<select>` (Departamental | Nacional, shadcn pattern, español neutro, 48px target) to `CreateChampionshipSeriesForm` in `frontend/src/routes/competitions/CompetitionFormPage.tsx`; send `level` in `useCreateRaceSeries` payload (depends on T005, T010). Agente: `react-ui-engineer` (sonnet)
- [x] T012 [US1] Render level-aware championship label in `frontend/src/components/competitions/tabs/InfoTab.tsx` via `championshipLabel` (needs `level` from series data; verify series fields reach the tab — extend the event/series query mapping if absent) + extend `InfoTab` tests. Agente: `react-ui-engineer` (sonnet)
- [x] T013 [P] [US1] Update filter option copy in `frontend/src/components/competitions/CompetitionFiltersBar.tsx`: "Campeonatos (CD)" → "Campeonatos" (predicate `kind==championship` untouched, matches both levels — FR-012); adjust its test snapshot. Agente: general-purpose (haiku)

**Checkpoint**: US1 fully functional — coach can register the Pereira national championship today. Deployable MVP (migration + this phase).

---

## Phase 4: User Story 2 — Ingest and analyze national championship results (Priority: P2)

**Goal**: Results import linked to the national championship works unchanged; analytics label it "Cto. Nal. — Pereira"; standings unaffected.

**Independent Test**: With US1 data, run import → commit, check evolution/races labels and standings diff empty (quickstart Scenarios 2–3).

### Tests for User Story 2 (write first, must fail pre-implementation)

- [x] T014 [P] [US2] Extend `backend/tests/test_race_labels.py`: matrix {championship×national → "Cto. Nal. — Pereira", championship×departmental → "Cto. Dep. — Ginebra" (regression), cup unchanged, no-location variants, default-param backward compat}. Agente: `qa-engineer` (sonnet)
- [x] T015 [P] [US2] Import tests in `backend/tests/test_race_imports_series_level.py` (new): upload with `series_level=national` creating championship series → organizer NULL (no Valle default), level persisted; cup path keeps Valle organizer default byte-identical; invalid `series_level` → 422. Agente: `qa-engineer` (sonnet)
- [x] T016 [P] [US2] Standings/panorama regression in `backend/tests/test_standings_championship_exclusion.py` (extend existing): national championship results present → cumulative standings and season panorama identical to baseline (SC-004). Agente: `qa-engineer` (sonnet)
- [x] T017 [P] [US2] Frontend `frontend/src/components/competitions/import/ImportWizard.test.tsx` (extend): level select appears only in new-championship-series branch; zod accepts level; submit forwards `series_level`; prefill (feature 015) path untouched. Agente: `qa-engineer` (sonnet)

### Implementation for User Story 2

- [x] T018 [US2] Add `level` keyword param (default `RaceSeriesLevel.departmental`) to `build_race_label` in `backend/app/services/race/race_labels.py`; national championship → "Cto. Nal.{ — city}"; update module docstring contract. Agente: `fastapi-architect` (sonnet)
- [x] T019 [US2] Thread `series.level` into both label call sites: evolution serializer in `backend/app/services/race/analytics_charts.py` and the `GET /races` participation-list serializer (feature 016) — both already join `RaceSeries`, add `level` to the selected columns, zero new queries (depends on T018). Agente: `fastapi-architect` (sonnet)
- [x] T020 [US2] In `backend/app/routers/race_imports.py`: accept optional `series_level` Form field (validated to `RaceSeriesLevel`, default departmental); in `_get_or_create_series` persist level and apply organizer default "Liga Vallecaucana de Ciclismo" **only when kind==cup** (research R5). Agente: `fastapi-architect` (sonnet)
- [x] T021 [US2] Add level select to the new-championship-series branch of `frontend/src/components/competitions/import/ImportWizard.tsx`: extend zod schema with `series_level`, default departmental, hidden for cups; forward as form field (depends on T005). Agente: `react-ui-engineer` (sonnet)

**Checkpoint**: US1 + US2 — ready for race week: register now, ingest when results publish, charts correct.

---

## Phase 5: User Story 3 — Correct level in family communications (Priority: P3)

**Goal**: Parent notifications say "Campeonato Nacional" for Pereira, "Campeonato Departamental" for Ginebra.

**Independent Test**: Generate insight notifications for both championships, inspect bodies (quickstart Scenario 4).

### Tests for User Story 3 (write first, must fail pre-implementation)

- [x] T022 [P] [US3] Dispatcher tests in `backend/tests/test_race_insight_dispatcher.py` (extend): national championship event → body/labels contain "Campeonato Nacional" and never "Departamental"; departmental event → "Campeonato Departamental" (regression); tier remains `RaceTier.CD` for both (research R4). Agente: `qa-engineer` (sonnet)

### Implementation for User Story 3

- [x] T023 [US3] In `backend/app/services/notification/race_insight_dispatcher.py`: make `_build_valida_label` and `_tier_label_es` level-aware for `RaceTier.CD` (resolve `event.series.level` — extend the dispatcher's event query to eager-load series or pass level explicitly; avoid N+1 per constitution IV); tier derivation in `race_event_tier.py` stays untouched. Agente: `fastapi-architect` (sonnet)

**Checkpoint**: All three stories functional independently.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T024 [P] Run full gates: `cd backend && pytest && ruff check . && mypy app`; `cd frontend && npx vitest run && npx eslint src && npx tsc --noEmit` — zero regressions, zero pre-023 tests modified except deliberate label assertions. Agente: `qa-engineer` (sonnet)
- [x] T025 [P] Execute quickstart.md Scenarios 1–5 against local stack (docker compose or venv+MySQL); record outcomes in `specs/023-national-championship-level/quickstart.md` checkboxes or a short results note. Agente: `qa-engineer` (sonnet)
- [x] T026 [P] Update `CLAUDE.md` implementation-status row (feature 023, migration `d3e4f5a6b7c8`, deploy pending) and `docs/implementation-status.md`; note R5 cosmetic debt (`points_scheme_code` on championships) where feature docs live. Agente: `technical-writer` (haiku)
- [x] T027 Final review pass: verify no remaining hardcoded "Cto. Dep."/"Campeonato Departamental" reachable for national series (`grep -rn "Cto. Dep\|Campeonato Departamental" backend/app frontend/src` — each hit must be level-branched or departmental-only). Agente: `qa-engineer` (sonnet)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (T001)**: none — immediate.
- **Phase 2 (T002–T005)**: after T001. T002/T003/T004/T005 all [P] (different files; migration is hand-written, not autogenerated, so it does not wait on the model edit — but review consistency at checkpoint).
- **Phase 3–5**: all require Phase 2 complete. Stories independent of each other; sequential P1→P2→P3 recommended (solo dev), parallel possible.
- **Phase 6**: after desired stories complete.

### Within stories

- Tests (T006–T008, T014–T017, T022) written FIRST and failing before their implementation tasks.
- US1: T009 ⟂ T010 [P]; T011 depends on T005+T010; T012 depends on T010; T013 independent [P].
- US2: T018 → T019; T020 independent of T018/T019; T021 depends on T005.
- US3: T023 after T022.

### Parallel opportunities

```text
Phase 2: T002 ∥ T003 ∥ T004 ∥ T005          (4 agents)
US1 tests: T006 ∥ T007 ∥ T008               (qa-engineer ×3)
US1 impl:  T009 ∥ T010 ∥ T013, then T011 ∥ T012
US2 tests: T014 ∥ T015 ∥ T016 ∥ T017
US2 impl:  (T018→T019) ∥ T020 ∥ T021
Polish:    T024 ∥ T025 ∥ T026
```

### Parallel Example: Phase 2 kickoff

```text
Agent: fastapi-architect  → "T002: RaceSeriesLevel enum + level column in backend/app/models/race_series.py"
Agent: database-architect → "T003: migration d3e4f5a6b7c8_add_race_series_level.py"
Agent: fastapi-architect  → "T004: level in backend/app/schemas/race_series.py"
Agent: react-ui-engineer  → "T005: RaceSeriesLevel in frontend/src/types/raceSeries.types.ts"
```

---

## Implementation Strategy

### MVP First (URGENT — race is 14–20 July 2026, days away)

1. Phase 1 + Phase 2 (foundation, ~4 parallel tasks).
2. Phase 3 (US1) → coach registers the Pereira championship **now**, before results exist.
3. **STOP and VALIDATE**: quickstart Scenario 1. Deploy MVP (migration is additive/zero-risk).
4. Phase 4 (US2) before results publish (~race weekend) → ingestion + charts ready.
5. Phase 5 (US3) any time before the first national insight email.
6. Phase 6 gates before each deploy.

### Incremental delivery

Each story checkpoint is deployable: US1 alone lets the coach prepare; US2 unlocks results week; US3 completes family comms. No story breaks prior behavior — departmental regressions guarded at every phase.
