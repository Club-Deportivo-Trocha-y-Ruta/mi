# Tasks: Distinguish Cups (with rounds) from single annual Championships

**Feature**: 014-cup-vs-championship-series
**Input**: Design documents from `/specs/014-cup-vs-championship-series/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/race-series-api.md, quickstart.md
**Branch**: `main` (no feature branch, per user instruction)

Tests are REQUIRED here — the project constitution makes testing NON-NEGOTIABLE
(happy + negative path per router/service; vitest + jest-axe for frontend; privacy
invariants). Each task names the agent best suited to execute it.

**Agent legend**: `database-architect`, `fastapi-architect`, `react-ui-engineer`,
`qa-engineer`, `technical-writer`, `data-privacy-guard`.

---

## Phase 1: Setup

- [X] T001 Verify single Alembic head is `a3b4c5d6e7f8` (`cd backend && source .venv/bin/activate && alembic heads`) and confirm work proceeds on `main`; record the head in the migration to be created. — **Agent: database-architect**

---

## Phase 2: Foundational (BLOCKING — must complete before any user story)

- [X] T002 Add `RaceSeriesKind(str, enum.Enum)` (`cup`, `championship`) and the `kind` mapped column (NOT NULL, default `cup`, `values_callable`, MySQL type `raceserieskind`) to `backend/app/models/race_series.py`. — **Agent: database-architect**
- [X] T003 Create Alembic revision `backend/alembic/versions/<rev>_add_race_series_kind.py` with `down_revision = "a3b4c5d6e7f8"`: `op.add_column` `kind` ENUM NOT NULL server_default `'cup'`; backfill assert; downgrade drops the column (MySQL `alter_column` passes `existing_type`/`existing_nullable`). Data reclassification is added later in T026 to the SAME file. — **Agent: database-architect**
- [X] T004 [P] Create `backend/app/schemas/race_series.py`: `RaceSeriesCreate` (name, season_year, kind, organizer; `extra="forbid"`; no client `points_scheme_code`), `RaceSeriesRead`, `RaceSeriesListResponse` (with `event_count`). — **Agent: fastapi-architect**
- [X] T005 Create `backend/app/routers/race_series.py` with `GET /api/race-analysis/race-series?season=&kind=` and `POST /api/race-analysis/race-series` (defaults `points_scheme_code='copa_valle_2026'`, 409 on duplicate `(name, season_year)`), and register the router in `backend/app/main.py`. — **Agent: fastapi-architect**
- [X] T006 [P] Add service helpers in `backend/app/services/race/` (e.g. `series_rules.py`): `derive_event_fields_for_series(kind, requested_seq)` → forces `sequence_number=1`, `is_championship=True` for championships; and `assert_championship_single_event(db, series)` raising a 409-style error if a championship series already has an event. — **Agent: fastapi-architect**
- [X] T007 [P] Pytest for foundation in `backend/tests/`: enum persists round-trip; `GET/POST /race-series` happy + 409 duplicate + 422; response exposes no minor PII. — **Agent: qa-engineer**

**Checkpoint**: column + series API + guard helpers exist and are tested. User stories can begin.

---

## Phase 3: User Story 1 — Register a championship as a single annual event (P1)

**Goal**: Coach can create a championship series and register its single event with no round number and no Copa Valle coupling; a second event is rejected.

**Independent test**: Create a championship series via API/UI, add its one event (no round number, `is_championship=true`, not under Copa Valle), then attempt a second event → 409.

- [X] T008 [US1] Make `sequence_number` optional in `RaceEventCreate` (`backend/app/schemas/race_event.py`); in `create_race_event` (`backend/app/routers/race_events.py`) load the series, call `derive_event_fields_for_series` + `assert_championship_single_event`, and ignore client `is_championship` (derive from `series.kind`). Update the legacy `sequence_number=99` docstrings. — **Agent: fastapi-architect**
- [X] T009 [US1] Update `backend/app/services/race/ingestor.py` to honor the target series' kind when creating events (championship → seq 1 / is_championship true; reuse the helper). — **Agent: fastapi-architect**
- [X] T010 [P] [US1] Pytest `backend/tests/`: championship series rejects 2nd event (409 with es-CO message); championship event derives seq=1/is_championship; cup event creation unchanged (regression). — **Agent: qa-engineer**
- [X] T011 [US1] In `frontend/src/routes/competitions/CompetitionFormPage.tsx` add a "Tipo de competencia" selector (Copa / Campeonato); for Campeonato hide the **Válida #** field and create/select a championship series; submit derives correct payload. — **Agent: react-ui-engineer**
- [X] T012 [P] [US1] Vitest + jest-axe for the championship create path in `frontend/src/routes/competitions/__tests__/`. — **Agent: qa-engineer**

**Checkpoint**: US1 independently testable and demoable.

---

## Phase 4: User Story 2 — Choose the right series on create/edit (P1)

**Goal**: Create/edit form requires explicit series choice (no Copa Valle default); round field shown only for cups, hidden for championships; works in edit mode.

**Independent test**: Open create form → no series pre-selected; pick cup → round required; pick championship → round absent; repeat in edit.

- [X] T013 [P] [US2] Add `frontend/src/api/raceSeries.ts` (GET/POST client) and `frontend/src/hooks/race/useRaceSeries.ts` (TanStack Query) for the series list/create endpoints. — **Agent: react-ui-engineer**
- [X] T014 [P] [US2] Refactor `frontend/src/schemas/competitionEvent.schema.ts`: remove `COPA_VALLE_SERIES` hardcode and the `99=CD` option; make the schema type-aware (round required for cup, omitted for championship). — **Agent: react-ui-engineer**
- [X] T015 [US2] Update `frontend/src/routes/competitions/CompetitionFormPage.tsx`: dynamic series picker fed by `useRaceSeries` with loading/empty/error states (Principle III), no default series, conditional round field, correct edit-mode prefill for both kinds. — **Agent: react-ui-engineer**
- [X] T016 [P] [US2] Vitest + jest-axe: no default series; round field conditional on kind; edit mode for a championship never reverts to a cup round. — **Agent: qa-engineer**

**Checkpoint**: US2 independently testable; entry form is series-agnostic.

---

## Phase 5: User Story 3 — Import results with the correct series type (P1)

**Goal**: Import flow asks for a round only for cups, omits it for championships, never defaults to Copa Valle; backend honors series_name + kind.

**Independent test**: Import targeting a cup → round requested; targeting a championship → no round; neither pre-fills Copa Valle.

- [X] T017 [US3] In `backend/app/routers/race_imports.py`: fix `_get_or_create_series` to resolve/create by `(series_name, season, kind)` (honor the client `series_name`; remove the hardcoded `_SERIES_NAME` dependency); add a `series_kind` Form field (default `cup`); thread the real `series_name` into `detect_revision`; apply the championship single-event guard on commit. — **Agent: fastapi-architect**
- [X] T018 [P] [US3] Pytest `backend/tests/`: import into a championship omits válida and sets seq=1; import into a cup unchanged (regression); `_get_or_create_series` honors a non-Copa `series_name` (bug regression); `detect_revision` receives the real series name; championship 2nd-import → 409. — **Agent: qa-engineer**
- [X] T019 [US3] In `frontend/src/components/competitions/import/ImportWizard.tsx`: add the competition-type selector, hide the **Válida #** input + validation for championships, use the dynamic series picker (no Copa Valle default), send `series_kind`. — **Agent: react-ui-engineer**
- [X] T020 [P] [US3] Vitest + jest-axe for the type-aware ImportWizard. — **Agent: qa-engineer**

**Checkpoint**: all three entry paths (create, edit, import) are series-type-aware. P1 MVP complete.

---

## Phase 6: User Story 4 — See cup rounds vs championships clearly (P2)

**Goal**: Preserve the V3 vs CD distinction in lists/details; do not offer a season-standings tab for a championship.

**Independent test**: View list + detail for a cup round (shows "V3") and a championship (shows "CD", no round, no standings tab).

- [X] T021 [US4] In `frontend/src/routes/competitions/CompetitionDetailPage.tsx` hide the standings/ranking tab when the competition is a championship; verify badge logic in `CompetitionsListPage.tsx`, `components/competitions/tabs/InfoTab.tsx`, and `CompetitionDetailPage.tsx` still keys on `is_championship` (no regression). — **Agent: react-ui-engineer**
- [X] T022 [P] [US4] Vitest: cup shows "V{n}", championship shows "CD" with no round and no standings tab; jest-axe on the detail page. — **Agent: qa-engineer**

**Checkpoint**: US4 independently verifiable; visual distinction intact.

---

## Phase 7: User Story 5 — Keep championships out of the season ranking (P2)

**Goal**: Season cumulative ranking includes only cup-series results; championships contribute zero.

**Independent test**: One cup (several rounds) + one championship same season → season ranking unaffected by the championship.

- [X] T023 [US5] Add `AND rs.kind = 'cup'` to the aggregate in `backend/app/services/race/season_panorama.py`. — **Agent: database-architect**
- [X] T024 [US5] Guard `backend/app/services/race/standings.py::get_event_standings` to return `None` when the resolved series is not `kind=cup`, and update the standings router (`backend/app/routers/race_events.py` `GET /{id}/standings`) to return an empty/not-applicable payload for championships. — **Agent: fastapi-architect**
- [X] T025 [P] [US5] Pytest `backend/tests/`: panorama excludes championship results (points/wins/podiums); cup totals unchanged when a championship is added (SC-002); standings return None/empty for a championship event. — **Agent: qa-engineer**

**Checkpoint**: US5 independently verifiable; ranking integrity guaranteed.

---

## Phase 8: User Story 6 — Reclassify the existing Departmental Championship 2026 (P2)

**Goal**: Move the misfiled Departmental event into its own championship series, preserving all results and removing its Copa Valle points contribution.

**Independent test**: After `alembic upgrade head`, the Departmental event belongs to "Campeonato Departamental 2026" (championship, Liga Vallecaucana), has no round number, keeps all results, and no longer adds to the Copa Valle ranking.

- [X] T026 [US6] Extend the T003 migration file with an idempotent data step: upsert series `('Campeonato Departamental 2026', 2026, 'Liga Vallecaucana de Ciclismo', 'copa_valle_2026', 'championship')` (no-op via `UNIQUE(name, season_year)`); guarded `UPDATE` repointing the legacy `is_championship=1` / seq-99 Copa-Valle-2026 event to the new series with `sequence_number=1`; downgrade repoints back to Copa Valle (seq 99) and removes the empty championship series. — **Agent: database-architect**
- [X] T027 [P] [US6] Pytest `backend/tests/`: migration is idempotent (re-run safe), reclassification preserves every result row (FR-012), and the reclassified event no longer contributes to the Copa Valle cumulative ranking (SC-003); safe no-op when the legacy event is absent. — **Agent: qa-engineer**

**Checkpoint**: live data corrected; production deploy will auto-apply.

---

## Phase 9: Polish & Cross-Cutting

- [X] T028 [P] Run and fix gates: `cd backend && ruff check . && mypy app` and `cd frontend && npm run lint && npx tsc --noEmit`. — **Agent: qa-engineer**
- [X] T029 [P] Privacy audit: confirm new `/race-series` endpoints and the type-aware flows expose no minor PII and logs carry ids/counts only (Ley 1581). — **Agent: data-privacy-guard**
- [X] T030 [P] Update `docs/implementation-status.md` and the status table + technical-notes in `CLAUDE.md` with the spec 014 row (and the retirement of the `sequence_number=99` convention). — **Agent: technical-writer**
- [~] T031 Execute the five quickstart scenarios (A–E) — behavior covered by automated suites (backend 35/35 + frontend 34 new, all green); manual browser walkthrough deferred to pre-deploy smoke. — **Agent: qa-engineer**

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T007)** block everything.
- **US1 (T008–T012)**, **US2 (T013–T016)**, **US3 (T017–T020)** are all P1 and depend only on Foundational. They are largely independent but touch shared frontend files (`CompetitionFormPage.tsx`, `competitionEvent.schema.ts`): sequence US1→US2 on those files, run US3 backend (T017–T018) in parallel with US1/US2.
- **US4 (T021–T022)**, **US5 (T023–T025)**, **US6 (T026–T027)** are P2 and depend on Foundational; US6 depends on T003 (same migration file). US5 and US6 together fully satisfy ranking integrity for the live data.
- **Polish (T028–T031)** runs last.

### Parallel opportunities

- Foundational: T004, T006, T007 in parallel after T002/T003.
- All `[P]` test tasks (T010, T012, T016, T018, T020, T022, T025, T027) run alongside their sibling implementation once its files exist.
- Backend US3 (T017) can run in parallel with frontend US1/US2.
- Polish T028/T029/T030 in parallel.

## Implementation Strategy

- **MVP = Foundational + US1 + US2 + US3** (all P1): the coach can model, create, edit, and import championships vs cups with no Copa Valle assumption.
- **Increment 2 = US4 + US5 + US6** (P2): visual polish, ranking integrity, and the live-data reclassification that closes the production bug.
- Keep a single Alembic head; do not commit (user controls commits); human review required before any merge (Principle I).
