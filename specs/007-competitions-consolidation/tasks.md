---
description: "Task list for 007-competitions-consolidation"
---

# Tasks: Unified Competitions Module

**Input**: Design documents from `/specs/007-competitions-consolidation/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md

**Tests**: INCLUDED — Constitution Principle II (NON-NEGOTIABLE) requires happy + negative paths, privacy invariants for minor data, and a11y axe on page/dialog components.

## Format: `[ID] [P?] [Story] Description — @owner`

- **[P]**: parallelizable (different files, no incomplete dependency)
- **[Story]**: US1..US6 (= Waves A..F in plan.md)
- **@owner**: recommended delegation agent
- Waves are independently shippable; each ends green (ruff/mypy/eslint/tsc + pytest + vitest + axe).

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 [P] Add shadcn `Table` primitive at `frontend/src/components/ui/table.tsx` (local component, no new dep) — @react-ui-engineer
- [X] T002 [P] Add `components/competitions/results/` and `components/competitions/roster/` folders with index barrels — @react-ui-engineer
- [X] T003 [P] Confirm `season_standings` view + `analytics.club_ranking` are queryable from `aiosqlite` test setup; add a view-or-fallback shim for SQLite tests in `backend/tests/conftest.py` — @qa-engineer

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ Must complete before US1/US3 work.**

- [X] T004 Add club/parent scoping helper `resolve_our_club_and_children(user)` in `backend/app/services/permissions.py` (coach/admin → club; parent → own children athlete_ids) with docstring — @fastapi-architect
- [X] T005 [P] Add shared read schema base in `backend/app/schemas/race_results.py` (`ResultRow`, `CategoryResults`, `StandingRow` with `is_our_club`) — @fastapi-architect
- [X] T006 [P] Add centralized cross-invalidation helper `invalidatePaired()` in `frontend/src/hooks/race/invalidation.ts` (raceEvents ↔ calendar ↔ results/standings/competitors/race-analysis keys) — @react-ui-engineer
- [X] T007 [P] Tests for T004 scoping helper (coach→club, parent→children, admin→all) in `backend/tests/services/test_permissions_scoping.py` — @qa-engineer

**Checkpoint**: Foundation ready.

---

## Phase 3: User Story 1 — View results & season standings (Wave A, P1) 🎯 MVP

**Goal**: Per-event finishing table + season standings, club highlighted, in-app.
**Independent Test**: Import a round with RESULTADOS + GENERAL, open it, see both tables with club rows highlighted and a working category filter + "solo mi club" toggle.

### Tests (write first, must fail)
- [X] T008 [P] [US1] Contract+integration test `GET /race-events/{id}/results` (happy: grouped by category; negative: 404; filter by category; soft-deleted excluded) in `backend/tests/routers/test_race_results_read.py` — @qa-engineer
- [X] T009 [P] [US1] Contract+integration test `GET /race-events/{id}/standings` (happy; 404 no series) in `backend/tests/routers/test_race_standings_read.py` — @qa-engineer
- [X] T010 [P] [US1] **Privacy invariant** test: parent gets only own child rows; another minor never present in results/standings payload — @data-privacy-guard
- [X] T011 [P] [US1] Query-count/N+1 test asserting results & standings reads are single aggregated queries — @qa-engineer
- [X] T012 [P] [US1] vitest + axe for `ResultsTable`/`StandingsTable` (sort, category filter, club highlight, empty state) **plus a full-field render check using a 26-category fixture to guard SC-007 mobile responsiveness** in `frontend/src/components/competitions/results/__tests__/` — @qa-engineer

### Implementation
- [X] T013 [US1] Implement `results_read.py` service (finishing order per `(category, position)`, exclude `deleted_at`, mark `is_our_club`) in `backend/app/services/race/results_read.py` — @fastapi-architect
- [X] T014 [US1] Implement `standings.py` service reading `season_standings` view scoped to the event's series/season in `backend/app/services/race/standings.py` — @fastapi-architect
- [X] T015 [US1] Add `GET /race-events/{id}/results` and `GET /race-events/{id}/standings` to `backend/app/routers/race_events.py` (RBAC + parent scoping via T004) — @fastapi-architect
- [X] T016 [P] [US1] TS types + api clients `frontend/src/api/raceResults.ts`, `raceStandings.ts` + `types/raceResults.types.ts` — @react-ui-engineer
- [X] T017 [P] [US1] Hooks `useRaceResults(id, filters)`, `useRaceStandings(id, filters)` in `frontend/src/hooks/race/` — @react-ui-engineer
- [X] T018 [US1] `ResultsTable.tsx` + `StandingsTable.tsx` (shadcn table, client sort/filter, club highlight, ≥48px targets) — @react-ui-engineer
- [X] T019 [US1] Replace placeholder `ResultsTab.tsx` with real table; add `StandingsTab.tsx`; wire into `CompetitionDetailPage` tabs (`?tab=results|standings`), lazy-loaded — @react-ui-engineer
- [X] T020 [US1] Empty/loading/error + cold-start states for both tabs (FR-013/032) — @react-ui-engineer

**Checkpoint**: US1 fully functional & shippable (MVP).

---

## Phase 4: User Story 2 — One Competitions module (Wave B, P1)

**Goal**: Single "Competencias" sidebar; AI analysis reached only inside `/competitions/*`; legacy routes 301-redirect.
**Independent Test**: One race entry in nav; old `/coach/race-analysis` + `/training/races/:id/club-insights` redirect into the module; no duplicate pages.

### Tests
- [X] T021 [P] [US2] vitest: single sidebar "Competencias" entry; legacy paths render `<Navigate>` to new locations (`MemoryRouter`) in `frontend/src/__tests__/competitions-routing.test.tsx` — @qa-engineer
- [X] T022 [P] [US2] vitest: parent role → 403 on `/competitions/insights/*` — @data-privacy-guard

### Implementation
- [X] T023 [US2] Unify sidebar in `frontend/src/components/layout/AppShell.tsx` to a single "Competencias" entry — @react-ui-engineer
- [X] T024 [US2] In `App.tsx`, mount insights pages under `/competitions/insights/*` and add 301-style redirects for `/coach/race-analysis` and `/training/races/:id/club-insights` (transition window) — @react-ui-engineer
- [X] T025 [US2] Mechanical `MemoryRouter` path codemod in affected existing tests (no assertion rewrites); confirm pre-existing competition list filters (FR-008) and admin delete-guard (FR-007) regression-pass post-consolidation — @qa-engineer

**Checkpoint**: US1 + US2 work; one destination.

---

## Phase 5: User Story 3 — Athlete association + roster (Wave C, P2)

**Goal**: Auto-match (exists) + confirm/fix (exists) + new manual call-up roster with reconciliation.
**Independent Test**: Build a roster on a result-less round; confirm an ambiguous match; after import, see reconciliation (called-up vs results).

### Tests
- [ ] T026 [P] [US3] Migration test: `race_event_roster` table + enum created, chained single-head, upgrade/downgrade on SQLite — @qa-engineer
- [ ] T027 [P] [US3] Router tests roster CRUD (happy; 409 dup; 422 non-club athlete; 404) in `backend/tests/routers/test_race_roster.py` — @qa-engineer
- [ ] T028 [P] [US3] Reconciliation service test (called_up_no_result / result_not_called_up) — @qa-engineer
- [ ] T029 [P] [US3] **Privacy**: parent roster read scoped to own child; vitest+axe for `RosterPanel` — @data-privacy-guard
- [ ] T030 [P] [US3] vitest+axe for roster + match-confirm UI — @qa-engineer

### Implementation
- [ ] T031 [US3] `RaceEventRoster` model + `raceeventrosterstatus` enum in `backend/app/models/race_event_roster.py` (per data-model.md) — @database-architect
- [ ] T032 [US3] Alembic migration (new table + enum), chained to current head, in `backend/alembic/versions/` — @database-architect
- [ ] T033 [P] [US3] Schemas in `backend/app/schemas/race_roster.py` — @fastapi-architect
- [ ] T034 [US3] `roster.py` service (CRUD + reconciliation) in `backend/app/services/race/roster.py` (depends T031) — @fastapi-architect
- [ ] T035 [US3] Roster endpoints (GET/POST/PATCH/DELETE) on `backend/app/routers/race_events.py` (RBAC) — @fastapi-architect
- [ ] T036 [P] [US3] api/types/hooks `frontend/src/api/raceRoster.ts`, `hooks/race/useRaceRoster.ts` — @react-ui-engineer
- [ ] T037 [US3] `RosterPanel.tsx` + integrate into `AthletesTab.tsx` (roster + existing match-confirm/link); include designed loading/empty/error states (FR-032) — @react-ui-engineer

**Checkpoint**: US1–US3 independently functional.

---

## Phase 6: User Story 4 — Reload/fix via diff (Wave D, P2)

**Goal**: Surface existing diff re-ingest in the module; on apply, mark downstream AI runs + newsletters outdated; manual re-execute only.
**Independent Test**: Re-upload corrected PDF → confirm diff → applied atomically; identical SHA256 = no-op; affected `agent_runs.stale_since` set; "outdated" badge + manual re-execute.

### Tests
- [ ] T038 [P] [US4] Service test: re-ingest with changed SHA256 sets `agent_runs.stale_since` + marks affected newsletters outdated; identical = no-op — @qa-engineer
- [ ] T039 [P] [US4] vitest+axe: diff confirm flow + "outdated/Re-ejecutar" badge in `/competitions/:id/import` — @qa-engineer

### Implementation
- [ ] T040 [US4] Wire `stale_since` marking + newsletter `outdated` into ingestor re-ingest path in `backend/app/services/race/ingestor.py` (or invalidate endpoint) — @fastapi-architect
- [ ] T041 [US4] Ensure `/competitions/:id/import` reuses existing `DiffTable` + revision-reason catalog; add "outdated" badge + manual re-execute button (no auto-trigger) — @react-ui-engineer

**Checkpoint**: US1–US4 work.

---

## Phase 7: User Story 5 — Bidirectional calendar sync (Wave E, P3)

**Goal**: Create-with-calendar (default-on), edit propagation (date/name/venue/status), associate existing event; strict 1:1.
**Independent Test**: Create competition (checkbox on) → linked event; edit date/venue → event updates; cancel → event cancelled; associate existing event; 1:1 guard rejects double-link.

### Tests
- [ ] T042 [P] [US5] Service tests: create-with-calendar; propagate date/name/venue/status; 1:1 guard (409 on double-link); opt-out creates none — @qa-engineer
- [ ] T043 [P] [US5] **Regression** test: editing competition keeps linked calendar event in sync — @qa-engineer
- [ ] T044 [P] [US5] vitest: create form calendar checkbox (default-on) + "Asociar a calendario" button when `has_calendar_event=false` — @qa-engineer

### Implementation
- [ ] T045 [US5] `calendar_sync.py` service (create/link/propagate/cancel, race_event source-of-truth) in `backend/app/services/race/calendar_sync.py` — @integration-engineer
- [ ] T046 [US5] Extend `POST /race-events` (`create_calendar_event` flag) + `PATCH /race-events/{id}` propagation + `POST /race-events/{id}/calendar-link` in router — @fastapi-architect
- [ ] T047 [US5] Frontend: calendar checkbox in `CompetitionFormPage`, associate button in detail; use `invalidatePaired()` (T006); include designed loading/error states (FR-032) — @react-ui-engineer

**Checkpoint**: US1–US5 work.

---

## Phase 8: User Story 6 — Insights polish + cleanup (Wave F, P3)

**Goal**: Final placement of round/athlete/club/season insight views inside module; remove legacy pages; redirects 301→410.
**Independent Test**: All insight scopes reachable inside `/competitions`; parent 403; no minor names in output; old links return 410; no orphaned pages.

### Tests
- [ ] T048 [P] [US6] **Property/privacy** test: AI narratives (round/club/season) contain no minor names (`forbidden_names` enforced; `[]` for global) — @data-privacy-guard
- [ ] T049 [P] [US6] vitest: legacy routes now 410; bundle baseline ≤ Wave-B chunk — @qa-engineer

### Implementation
- [ ] T050 [US6] Finalize `InsightsTab` + `/competitions/insights/{athletes/:id,club,season/:year}` placement (reuse hooks, no duplication) — @react-ui-engineer
- [ ] T051 [US6] Remove `RaceAnalysisPage.tsx` + `ClubInsightsByRacePage.tsx` + transitional barrels; switch redirects 301→410 — @react-ui-engineer

**Checkpoint**: All stories functional; single module.

---

## Phase 9: Polish & Cross-Cutting

- [ ] T052 [P] `data-privacy-guard` full audit of new endpoints/UI (ids-only logs, no PII, no names in AI/logs) — @data-privacy-guard
- [ ] T053 [P] Docs: update `docs/12-competitions-unification/` (results/standings/roster/sync), `docs/10-race-results/`, CLAUDE.md module status, README — @technical-writer
- [ ] T054 [P] Bundle-size + LCP check on data-dense competition routes (Principle IV budgets) — @react-ui-engineer
- [ ] T055 Run `quickstart.md` end-to-end verification (coach + parent paths) — @qa-engineer

---

## Dependencies & Execution Order

- **Setup (P1)** → **Foundational (P2)** blocks US1/US3.
- **US1 (Wave A)** is the MVP; ships first. **US2 (Wave B)** is independent (no data changes) and can run in parallel with US1 by a second dev.
- **US3 (Wave C)** needs T004 (scoping) + its own migration. **US4 (Wave D)** depends on import/revision (existing) and benefits from US1 being viewable. **US5 (Wave E)** depends on T006 invalidation helper. **US6 (Wave F)** depends on US2 (routes) and should be last (removals).
- Within a story: tests (fail first) → models → services → endpoints → UI.

### Parallel opportunities
- T001–T003, T005–T007 in parallel.
- Per story, all `[P]` test tasks together; api/types/hooks `[P]` alongside backend services in different files.
- Two-dev split: Dev A US1→US4→US6 (vertical results path); Dev B US2→US5 + US3 backend with @database-architect.

## Implementation Strategy

- **MVP**: Phases 1–2 then US1 (Wave A) → STOP, validate, deploy. This alone delivers the missing results/standings capability.
- **Incremental**: add US2, US3, US4, US5, US6 as independent green increments; each is reversible.
- Commit after each task/logical group; never merge a wave with red CI or a privacy/a11y violation.

## Notes
- Net-new code is small; most tasks wire/expose existing backend (research.md).
- [P] = different files, no incomplete dependency. Owners are recommendations for delegation.
- Total: 55 tasks (T001–T055).
