---
description: "Task list for feature 044 — Race history backfill"
---

# Tasks: Race history backfill — Copa Valle 2024 and 2025 with cross-season athlete progression

**Input**: Design documents from `/specs/044-race-history-backfill/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md` (R-01…R-16), `data-model.md`, `contracts/` (`reading-integrity.md`, `category-mapping.md`, `third-party-lock.md`, `identity-review-api.md`, `historical-load.md`, `history-progression-api.md`, `ui-history.md`), `quickstart.md`

**Tests**: REQUIRED. Constitution principle II (Testing) is NON-NEGOTIABLE and every contract ends with its test list; test tasks are first-class and sit **before** the implementation they cover inside each phase. Write them, watch them fail, then implement.

**Organization**: Phases follow the seven user stories of `spec.md` in priority order, preceded by Setup and Foundational phases and followed by Polish. Paths are relative to the repository root (`backend/…`, `frontend/…`, `docs/…`).

**Hard ordering rule (spec US3, FR-012)**: Phase 5 (third-party lock) MUST be complete and green before **any** task that commits historical results — i.e. before Phase 7's commit tasks (T064 onwards) and before the real load (T107). `engineering-lead` enforces it at gate G3.

**Privacy rule for every task**: fixtures are synthetic (fake-name generator); no official file, rider name, club or city is committed, logged, traced or pasted into a prompt. Work against a `_test` or local Docker database — a local backend configured with the production database writes to production.

## Format: `[ID] [P?] [Story] Description [agent: name · model]`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: user story the task serves (US1…US7); absent in Setup, Foundational and Polish
- **[agent: … · model]**: who executes it and on which tier

## Agent assignment (owner request: sonnet or opus "según el caso")

Per `.claude/agents/README.md`: leads orchestrate on **opus** and never write code; workers execute on **sonnet**. That README also allows promoting a reasoning-heavy authoring task to opus. This feature uses that clause **per task**, through the Agent tool's `model` override, for the six places where a subtle mistake corrupts data or leaks minors' data: the migration that drops a unique key, the band reader, the identity resolver and review, the third-party guard, the reversal logic, and the history builder's parent gate. Everything that follows a written contract stays on sonnet. `data-privacy-guard` stays on sonnet by policy and is reviewed by an opus lead.

| Agent | Model | Tasks | Used for |
|---|---|---|---|
| `engineering-lead` | opus | 8 | Opens phases, checks exit gates G1–G7, resolves cross-task conflicts. Writes no code. |
| `data-platform-lead` | opus | 3 | Reviews identity rules, the privacy audit and the real-load runbook. Writes no code. |
| `database-architect` | **opus** (override) | 2 | The migration (drops a unique key, backfills signatures) and its MySQL-lane verification. |
| `database-architect` | sonnet | 3 | Models, seeds. |
| `data-analyst` | **opus** (override) | 4 | Band reader, identity candidate rules, resolver, reversal. |
| `data-analyst` | sonnet | 5 | Normalizer aliases, completeness, history builder, staging script. |
| `fastapi-architect` | **opus** (override) | 3 | Third-party guard, ingestor identity wiring, parent gate of the history endpoint. |
| `fastapi-architect` | sonnet | 15 | Schemas, routers and services that follow a contract. |
| `qa-engineer` | sonnet | 36 | Backend and frontend tests, a11y, e2e, fixture builder. |
| `react-ui-engineer` | sonnet | 11 | All frontend api/hooks/components/pages. |
| `ux-researcher` | sonnet | 3 | Copy and heuristic review (coach tablet, parent mobile). |
| `data-privacy-guard` | sonnet | 3 | Lock review, mandatory privacy audit, pre-load check. |
| `parent-communicator` | sonnet | 1 | Privacy-notice wording for families. |
| `technical-writer` | sonnet | 4 | Design doc, runbook, status and technical notes. |
| `release-manager` | sonnet | 2 | Deploy checklist and post-deploy smoke. |
| `product-manager` | opus | 1 | Final acceptance against the spec's success criteria. |
| **Total** | **21 opus · 83 sonnet** | **104** | + T105–T107 owner-only steps (no agent) |

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: working branch, fixture builder and settings that every later phase needs.

- [X] T001 Open the feature — **owner decision 2026-09-18: implementation runs on `feat/044-race-history-backfill`**, per the project's `<type>/<slug>` convention. Only the specification and planning artifacts live on `main` (commits `58669c8`, `b881b29`, `3aeaf08`). `alembic heads` confirmed at the single head `c2314ccd7927`. [agent: engineering-lead · opus]
- [X] T002 [P] Create the synthetic results-PDF builder in `backend/tests/helpers/results_pdf_builder.py` (WeasyPrint; ruled 7-column table; `white-space: nowrap; overflow: visible` on a fixed-width club cell so a long club is printed over the time column; fake-name generator; options: categories with headers, rows, statuses, a removed ordinal, a duplicated ordinal, an unknown header, header line `VALIDA VIII …`) per research R-14 [agent: qa-engineer · sonnet]
- [X] T003 [P] Add a builder self-test in `backend/tests/helpers/test_results_pdf_builder.py` asserting that x-sorted `page.extract_text()` of a long-club row interleaves club letters and time digits (proves the fixture reproduces the defect) and that no generated name comes from a real list [agent: qa-engineer · sonnet]
- [X] T004 [P] Add `RACE_HISTORY_FAMILY_POLICY_VERSION: str = ""` to `backend/app/config.py` with a docstring (empty = pre-registration results hidden from families), plus the variable in `backend/.env.example` with no value [agent: fastapi-architect · sonnet]

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: schema and models every story depends on (data-model §1–§6).

**⚠️ CRITICAL**: no user-story work starts until this phase is complete.

- [X] T005 Write the model tests first in `backend/tests/models/test_race_history_models.py`: frozen columns exist and are nullable; two competitors may share `normalized_name`; `race_competitor_signatures` rejects a duplicate `(normalized_name, club_norm, city_norm)` including the all-empty-strings case; `race_identity_candidates.pair_hash` unique; state default `pending` [agent: qa-engineer · sonnet]
- [X] T006 Add `category_label_raw`, `category_age_min_raw`, `category_age_max_raw` to `backend/app/models/race_result.py` (data-model §1) [agent: database-architect · sonnet]
- [X] T007 Update `backend/app/models/race_competitor.py`: replace `uq_race_competitors_normalized_name` with `Index("ix_race_competitors_normalized_name", "normalized_name")`, add `city_text`, add the `signatures` relationship; create `backend/app/models/race_competitor_signature.py` and `backend/app/models/race_identity_candidate.py` (enums with `values_callable`, `NOT NULL DEFAULT ''` on `club_norm`/`city_norm`) and register them in `backend/app/models/__init__.py` (data-model §2–§4) [agent: database-architect · sonnet]
- [X] T008 Write the Alembic revision `backend/alembic/versions/<rev>_race_history_backfill.py` with `down_revision = "c2314ccd7927"`: add the three columns and backfill them from `race_categories`; create both tables; backfill one signature per existing competitor (seasons from its results); only then drop the unique key and create the plain index; symmetric `downgrade` that fails loudly if duplicate names exist. Must run on MySQL 8.4 and on the aiosqlite lane (batch ops where needed) [agent: database-architect · opus]
- [X] T009 [P] Add the three inactive categories (`MAS_B_2025`, `MAS_C_2025`, `PRE_F_U`) to `backend/scripts/seed_race_categories.py` and the two descriptive schemes (`copa_valle_2024`, `copa_valle_2025`, `is_official=false`, empty `position_points`) to the points-scheme seed under `backend/scripts/`; keep both scripts idempotent (category-mapping contract, data-model §5–§6) [agent: database-architect · sonnet]
- [X] T010 Gate G1 — **PASSED 2026-09-18**. Single head `8efe1618cb83`; upgrade → downgrade → upgrade clean; full default lane compared against a clean `main` worktree: `main` 212 failed / 5035 passed vs branch 201 failed / 5121 passed — no regression, every remaining failure pre-existing. Original text: run `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` on a local `_test` MySQL and the full default `pytest` lane; confirm a single head; confirm `tests/services/race/test_ingestor_concurrency.py` still passes or list exactly what Phase 6 must restore [agent: engineering-lead · opus]

**Checkpoint**: schema in place; stories US1, US2, US3 can start in parallel.

---

## Phase 3: User Story 1 — No result is lost in silence (Priority: P1) 🎯 MVP

**Goal**: every printed row of an official file is accounted for; unknown headers and unreadable rows are listed; an incomplete category blocks only itself.

**Independent Test**: spec US1 — builder files with overprinted clubs, an unknown header and a removed ordinal: all rows recovered once, the header listed, the gap named, that category's commit refused while the others commit.

### Tests for User Story 1 ⚠️ write first

- [X] T011 [P] [US1] `backend/tests/services/race/test_band_reader.py`: `_band_text` on hand-built char dicts — overlapping club/time runs in stream order, club flush against the time, club ending in a digit, position without time, `DNF`/`DSQ`/`DNS`/`(-2 VUELTAS)`, empty city and club [agent: qa-engineer · sonnet]
- [X] T012 [P] [US1] `backend/tests/services/race/test_parser_historical_layout.py` on builder PDFs: 100 % of rows recovered with correct ordinal, bib, time, points; unknown header returned with its rows; zero unreadable rows; header numeral VIII parsed; `parse_results_pdf` wrapper keeps today's return shape [agent: qa-engineer · sonnet]
- [X] T013 [P] [US1] `backend/tests/services/race/test_completeness.py` (incl. hypothesis): gap, duplicate, both, empty, single row, acknowledged; `apply_corrections` add/edit/remove then re-check [agent: qa-engineer · sonnet]
- [X] T014 [P] [US1] `backend/tests/routers/test_race_imports_integrity.py`: `/parse` returns `categories[]` with `completeness` and `unreadable_rows[]`; `/corrections` lifts a block; `/acknowledge` with a catalogue reason is audited and rejects an unknown reason (422); denied paths — parent 403, athlete 403, coach of another club [agent: qa-engineer · sonnet]

### Implementation for User Story 1

- [X] T015 [US1] Implement the band reader in `backend/app/services/race/pdf_parser.py` per research R-01 and `contracts/reading-integrity.md`: `_band_text`, relaxed row regex (single-digit hour with `(?<![\d:])`, optional space before the time), `ParsedCategory`/`ParsedResults`/`UnreadableRow`, category headers interleaved with row bands by vertical position, text-line path kept as fallback with a `row_path_mismatch` warning, `parse_results_pdf` as a back-compat wrapper. Logs carry pages, ordinals and counts only [agent: data-analyst · opus]
- [X] T016 [P] [US1] Extend `_EVENT_HEADER_RE` and `_ROMAN_TO_INT` to I–XII (longest alternation first) in `backend/app/services/race/pdf_parser.py` (R-02) — coordinate with T015, same file, land after it [agent: data-analyst · sonnet]
- [X] T017 [P] [US1] Create `backend/app/services/race/completeness.py` (`CompletenessReport`, `check_completeness`, `apply_corrections`, `AcknowledgeReasonCode` closed catalogue with Spanish labels) [agent: data-analyst · sonnet]
- [X] T018 [US1] Extend `backend/app/schemas/race_imports.py`: `ParsedCategoryRead`, `CompletenessRead`, `UnreadableRowRead`, `RowCorrectionIn` (`extra="forbid"`), `AcknowledgeIn`, `AcknowledgeReasonsResponse`; add `categories`, `unreadable_rows` to `ImportParseResponse` and `pending_categories` to `ImportCommitResponse` — all additive [agent: fastapi-architect · sonnet]
- [X] T019 [US1] Wire `/parse` to `parse_results_document`, persist `categories`/`unreadable_rows` in `parse_meta_json`, and add `POST /{id}/corrections`, `POST /{id}/acknowledge`, `GET /acknowledge-reasons` in `backend/app/routers/race_imports.py` with `record_audit` on both mutations; `_reload_parsed_from_storage` applies stored corrections before the check [agent: fastapi-architect · sonnet]
- [X] T020 [US1] Run the untouched 2026 oracles `backend/tests/services/race/test_parser.py` and `test_parser_edge_cases.py`, plus `test_csv_parser.py`; any diff is a defect in T015, never an oracle edit (FR-007) [agent: qa-engineer · sonnet]
- [X] T021 [P] [US1] Frontend types, Zod and API for the preview in `frontend/src/types/raceImports.types.ts`, `frontend/src/schemas/raceImportCorrections.ts`, `frontend/src/api/raceImports.ts` (corrections, acknowledge, reasons) [agent: react-ui-engineer · sonnet]
- [X] T022 [US1] Completeness badges, the list of missing/duplicated positions and the unreadable-rows notice in `frontend/src/components/competitions/import/ImportWizard.tsx`; `RowCorrectionDialog.tsx` and `AcknowledgeGapDialog.tsx` in the same folder (RHF + Zod, ≥ 48 px, inline Spanish errors) [agent: react-ui-engineer · sonnet]
- [X] T023 [P] [US1] vitest + MSW + jest-axe for the two dialogs and the wizard preview states in `frontend/src/components/competitions/import/__tests__/` [agent: qa-engineer · sonnet]
- [X] T024 [US1] Gate G2 — **PASSED 2026-09-18**. Reading integrity verified end to end on builder files; SC-001 met (0 rows lost, 0 categories silently dropped). Beyond the synthetic fixtures, the fix recovered **2 real rows the old parser was losing in the 2026 official file** (`PREINFANTIL B` position 17 and `MASTER B1` position 5), so its oracle was corrected from 227 to 229 rows with a per-category completeness regression test. Original text: US1 independent test passes end to end; spec SC-001 verified on builder files (0 lost rows, 0 silently dropped categories) [agent: engineering-lead · opus]

**Checkpoint**: reading is trustworthy. Nothing historical is committed yet.

---

## Phase 4: User Story 2 — Historical categories keep their own meaning (Priority: P1)

**Goal**: renames resolve to current categories, season-specific groups stay their own, every result freezes its label and age range.

**Independent Test**: spec US2 — a renamed header and a `MASTER B` header resolve as specified; stored label/range survive a catalogue edit.

### Tests for User Story 2 ⚠️ write first

- [X] T025 [P] [US2] Extend `backend/tests/services/race/test_normalizer.py`: every alias row of `contracts/category-mapping.md` (with/without diacritics and hyphen), `mapping_kind` derivation for exact/rename/season_specific/unknown [agent: qa-engineer · sonnet]
- [X] T026 [P] [US2] `backend/tests/services/race/test_ingestor_frozen_labels.py`: label and age range written at insert; unchanged after a catalogue edit and after a revision import; existing rows backfilled by the migration [agent: qa-engineer · sonnet]
- [X] T027 [P] [US2] `backend/tests/routers/test_inactive_categories_hidden.py`: the three season-specific codes are absent from every current-season selector source (import wizard categories, course setups, results filters, standings filters) [agent: qa-engineer · sonnet]

### Implementation for User Story 2

- [X] T028 [US2] Add the aliases, `HEADER_ALIASES` and `mapping_kind_for(header, category)` to `backend/app/services/race/normalizer.py`; keep exact-match lookup (no substring) [agent: data-analyst · sonnet]
- [X] T029 [US2] In `backend/app/services/race/ingestor.py` write `category_label_raw`/`category_age_min_raw`/`category_age_max_raw` on insert from the parsed header and the catalogue row; accept `ParsedCategory` input; never update them afterwards (check `backend/app/services/race/revision.py` inserts, not updates) [agent: fastapi-architect · sonnet]
- [X] T030 [P] [US2] Add `category_label` (frozen label or catalogue label) to the stored-result read schemas in `backend/app/schemas/race_results.py` and `backend/app/services/race/results_read.py`; make every current-season category source filter `is_active` [agent: fastapi-architect · sonnet]
- [X] T031 [P] [US2] `CategoryMappingTable.tsx` in `frontend/src/components/competitions/import/` (encabezado impreso · categoría · tipo · filas · estado) mounted in the wizard preview, with its vitest + jest-axe test [agent: react-ui-engineer · sonnet]

**Checkpoint**: US1 + US2 give a faithful, reviewable preview.

---

## Phase 5: User Story 3 — A third party can never be profiled over time (Priority: P1)

**Goal**: cross-válida data is structurally impossible for a competitor not linked to a club athlete. **Must be complete before Phase 7 commits anything.**

**Independent Test**: spec US3 — unlinked competitor refused for four roles; no third-party name in logs, prompts, newsletter context or family output.

### Tests for User Story 3 ⚠️ write first

- [X] T032 [P] [US3] `backend/tests/privacy/test_third_party_lock.py` — structural part: walk `app.services.race`, collect public callables with a `competitor_id` parameter, fail unless marked `@club_competitor_only` or listed in `ALLOWED_SINGLE_EVENT` with a justification [agent: qa-engineer · sonnet]
- [X] T033 [P] [US3] Same file — behavioural part: unlinked competitor with three seasons refused as admin, coach, parent, athlete; linked served; refused right after an unlink; sweep of `caplog`, fake-LLM `last_request`, newsletter context and family responses finds none of the synthetic third-party names [agent: qa-engineer · sonnet]

### Implementation for User Story 3

- [X] T034 [US3] Create `backend/app/services/race/third_party_guard.py` (`ThirdPartyProgressionForbidden`, `require_club_competitor`, `club_competitor_only`) per `contracts/third-party-lock.md`; reads current link state on every call [agent: fastapi-architect · opus]
- [X] T035 [US3] Apply the guard to every cross-válida entry point: `backend/app/services/race/analytics.py` (`athlete_progression`, `podium_gap`, `projection`), the loaders behind `compute_field_metrics` in `backend/app/services/race/ai/nodes/compute_metrics.py` and `backend/app/services/training/newsletter_builder.py`, and anything else T032 reports; map the exception to `403 third_party_progression_forbidden` at the router edge; emit `third_party_progression_refused` with ids only [agent: fastapi-architect · sonnet]
- [X] T036 [US3] Review T034–T035 against FR-012…FR-015: allow-list entries justified, no bypass path, `city` not yet serialised anywhere; write findings to `specs/044-race-history-backfill/privacy-audit.md` §1 [agent: data-privacy-guard · sonnet]
- [X] T037 [US3] Gate G3 — **PASSED 2026-09-18**. `tests/privacy/test_third_party_lock.py` 32 green; T036 audit APPROVED WITH CONDITIONS and its single condition closed (the refusal message no longer reaches `agent_run_events`). No task from T064 on may start before this line is checked. Original text: T032–T033 green in CI lane, T036 without blocker. Record the date in `tasks.md`. No task from T064 on may start before this line is checked [agent: engineering-lead · opus]

**Checkpoint**: the guarantee exists before the data does.

---

## Phase 6: User Story 4 — The coach decides who is who (Priority: P1)

**Goal**: same-person and homonym candidates over the whole universe; nothing merges automatically; decisions audited, remembered, reversible; commit gated.

**Independent Test**: spec US4 — extra-surname pair and two-towns homonym both raised, commit refused while pending, one competitor for the first and two for the second after deciding, nothing re-asked on re-preview.

### Tests for User Story 4 ⚠️ write first

- [ ] T038 [P] [US4] `backend/tests/services/race/test_identity_review.py`: candidate rules (extra surname, inverted surnames, accents; `same_valida_two_categories`, `sex_conflict`, `age_path_backwards`, `club_and_city_differ`; club-only change raises nothing), `pair_hash` idempotence across rebuilds, decided candidates never reset [agent: qa-engineer · sonnet]
- [ ] T039 [P] [US4] `backend/tests/services/race/test_identity_resolver.py` (incl. hypothesis for idempotence): the five resolver branches of the contract, `athlete_id` persisted for a linked competitor whatever the row's club, `IdentityUnresolved` when no tie-break exists [agent: qa-engineer · sonnet]
- [ ] T040 [P] [US4] `backend/tests/routers/test_race_identity.py`: rebuild/list/summary/decide/reverse happy paths; 409 on deciding a non-pending candidate; reversal before and after commit (results move, link cleared on the split-off competitor, audit rows); `linked_athlete_involved`; denied paths parent/athlete 403 [agent: qa-engineer · sonnet]
- [ ] T041 [P] [US4] Schema-walk test in `backend/tests/privacy/test_city_not_serialised.py`: `city` / `city_text` / `city_norm` appear in no response model outside `app/schemas/race_identity.py` [agent: qa-engineer · sonnet]
- [ ] T042 [P] [US4] Update `backend/tests/services/race/test_ingestor_concurrency.py`: two concurrent ingests of the same new rider yield one competitor through the signature unique key [agent: qa-engineer · sonnet]

### Implementation for User Story 4

- [ ] T043 [US4] Review the candidate rules and thresholds of research R-06 against the owner's decision 3 and FR-016/FR-017 before code is written; confirm "club alone is not a signal" and the blocking key; note the outcome in `research.md` R-06 [agent: data-platform-lead · opus]
> **Note from the T036 privacy audit (2026-09-18)**: the structural scan of the third-party lock only indexes public first-level callables whose signature has a literal `competitor_id` parameter. A function taking `competitor_ids: list[int]` — exactly the shape the identity review needs — would **not** be detected. Whoever implements US4 must either keep that shape out of the public surface or extend the scan in `tests/privacy/test_third_party_lock.py` to cover it; a reviewer must check this explicitly at gate G4.

- [ ] T044 [US4] Implement `backend/app/services/race/identity_review.py::build_candidates` (pure core + DB shell): universe = staged imports' parsed rows + existing competitors; blocked `token_set_ratio ≥ 90`; homonym signals; snapshots without logging names; named constants `SAME_PERSON_MIN_SCORE`, `DIVERGENCE_MAX_SCORE` [agent: data-analyst · opus]
- [ ] T045 [US4] Implement `backend/app/services/race/identity_resolver.py::IdentityResolver` per the contract's resolver table, including signature upsert with `first_season`/`last_season` widening and `source_candidate_id` [agent: data-analyst · opus]
- [ ] T046 [US4] Replace both name-only upserts in `backend/app/services/race/ingestor.py` with the resolver; store `city_text`; persist `athlete_id` whenever the resolved competitor is linked; keep `is_trocha_y_ruta` only for deciding whether the wizard asks for a match [agent: fastapi-architect · opus]
- [ ] T047 [US4] Decisions and reversal in `backend/app/services/race/identity_review.py` (`decide`, `reverse`, post-commit split/merge exactly as in the contract's "Reversal semantics"), each with `record_audit` [agent: data-analyst · opus]
- [ ] T048 [P] [US4] `backend/app/schemas/race_identity.py` (`IdentityRecordRead` — the only schema with `city`, `IdentityCandidateRead`, `IdentityDecisionIn`, `IdentitySummaryRead`, `RebuildResultRead`; `extra="forbid"`) [agent: fastapi-architect · sonnet]
- [ ] T049 [US4] `backend/app/routers/race_identity.py` (prefix `/api/race-identity`, `require_role([admin, coach])`, rebuild in a worker thread with 30 s timeout and the budget in the docstring) and mount it in `backend/app/main.py` [agent: fastapi-architect · sonnet]
- [ ] T050 [US4] Commit gate in `backend/app/routers/race_imports.py`: `409 {"code":"identity_review_pending","pending":n}` on `/commit` while any candidate is pending [agent: fastapi-architect · sonnet]
- [ ] T051 [P] [US4] `frontend/src/api/raceIdentity.ts`, `frontend/src/types/raceIdentity.types.ts`, `frontend/src/hooks/race/useIdentityReview.ts` [agent: react-ui-engineer · sonnet]
- [ ] T052 [US4] `frontend/src/routes/competitions/history/IdentityReviewPage.tsx` per `contracts/ui-history.md` §4 (side-by-side cards, signals in words, two ≥ 48 px actions, keyboard shortcuts, progress, state filter, "Deshacer" with confirmation, linked-athlete chip) and its route registration [agent: react-ui-engineer · sonnet]
- [ ] T053 [P] [US4] vitest + MSW + jest-axe for `IdentityReviewPage` (pending, empty, error, resume, undo) in `frontend/src/routes/competitions/history/__tests__/` [agent: qa-engineer · sonnet]
- [ ] T054 [P] [US4] Heuristic and copy review of the identity review on a tablet viewport (one decision ≤ 15 s, SC-009); findings to `specs/044-race-history-backfill/ux-review.md` [agent: ux-researcher · sonnet]
- [ ] T055 [US4] Gate G4: US4 independent test passes; measure `POST /rebuild` on a synthetic universe of 3 000 names; if > 10 s, record the figure and the mitigation in `plan.md` Complexity Tracking [agent: engineering-lead · opus]

**Checkpoint**: identity is decided by a person, before any merge.

---

## Phase 7: User Story 5 — The fifteen válidas through the same trusted path (Priority: P1)

**Goal**: staging, partial commit and a board for the historical load, on the existing preview → dry-run → commit path. Contract: `contracts/historical-load.md` (FR-023…FR-029).

**Independent Test**: spec US5 — two synthetic válidas of one season: season and válidas created, full fields, calculated standings, re-load creates nothing, audit trail complete.

**⛔ Requires gate G3 (T037) checked.**

### Tests for User Story 5 ⚠️ write first

- [ ] T056 [P] [US5] `backend/tests/services/race/test_import_staging.py`: the extracted staging service produces the same `RaceImport` and response as today's `/parse` for a 2026 file (golden comparison), stages a historical builder file with season/válida/date/venue taken from the inputs, never assumed (FR-025), and emits `header_mismatch` when the printed header disagrees [agent: qa-engineer · sonnet]
- [ ] T057 [P] [US5] `backend/tests/routers/test_race_imports_history.py`: the full start list is committed, including categories where no club athlete raced (FR-028); printed points kept verbatim (FR-026); partial commit ingests consistent/acknowledged categories and lists `pending_categories`; `/commit-pending` finishes them, returns `409 nothing_pending` afterwards and obeys the same `409 identity_review_pending` gate as `/commit`; re-staging or re-committing an identical file creates nothing in any table (FR-027); interrupted load resumes; standings carry `is_calculated` [agent: qa-engineer · sonnet]
- [ ] T058 [P] [US5] `backend/tests/services/race/test_2026_unchanged.py`: with two historical seasons loaded, `GET /evolution`, results and standings of 2026 and the race-AI analyst context are identical to the baseline without them (FR-029, R-15) [agent: qa-engineer · sonnet]

### Implementation for User Story 5

- [ ] T059 [US5] Extract the body of `parse_import` into `backend/app/services/race/import_staging.py::stage_results_file` and make `backend/app/routers/race_imports.py` a thin caller (no behaviour change; T056 is the safety net) [agent: fastapi-architect · sonnet]
- [ ] T060 [US5] `only_categories` support in `backend/app/services/race/ingestor.py::ingest_event` (bypasses the SHA-256 short-circuit only for a restricted re-run) and unknown-header / inconsistent categories skipped into `pending_categories` [agent: fastapi-architect · sonnet]
- [ ] T061 [US5] `POST /{id}/commit-pending` (behind the same identity-review gate as `/commit`, FR-018) and the `pending_categories` bookkeeping in `backend/app/routers/race_imports.py`; `pending_categories_count` in the import list schema [agent: fastapi-architect · sonnet]
- [ ] T062 [P] [US5] `is_calculated: true` on the standings read schema in `backend/app/schemas/race_results.py` and `backend/app/services/race/standings.py` [agent: fastapi-architect · sonnet]
- [ ] T063 [P] [US5] `backend/scripts/stage_race_history.py`: reads a manifest (season, válida, date, venue, path) located **outside the repository**, calls `stage_results_file`, supports `--dry`, never commits, prints ids and counts only; refuses a manifest or file path inside the repo and any cumulative-standings file (FR-024) [agent: data-analyst · sonnet]
- [ ] T064 [US5] `frontend/src/routes/competitions/history/HistoricalLoadPage.tsx` per `contracts/ui-history.md` §3 (board by season and state, pending-category counters, identity banner, commit and commit-pending actions with the gate reason) and its route + navigation entry for coach/admin [agent: react-ui-engineer · sonnet]
- [ ] T065 [P] [US5] "Clasificación calculada por la plataforma" label on the standings table component under `frontend/src/components/competitions/` [agent: react-ui-engineer · sonnet]
- [ ] T066 [P] [US5] vitest + MSW + jest-axe for `HistoricalLoadPage` in `frontend/src/routes/competitions/history/__tests__/` [agent: qa-engineer · sonnet]
- [ ] T067 [US5] Gate G5: US5 independent test passes on synthetic seasons; G3 re-verified green on the same commit [agent: engineering-lead · opus]

**Checkpoint**: the historical load works end to end on synthetic data.

---

## Phase 8: User Story 6 — Is the athlete improving across seasons? (Priority: P2)

**Goal**: one continuous series per athlete with category-change markers, thresholds, caveats.

**Independent Test**: spec US6 — three seasons, one category change, a skipped válida, a DNF, a four-finisher válida.

### Tests for User Story 6 ⚠️ write first

- [ ] T068 [P] [US6] `backend/tests/services/race/test_history.py` with in-memory ORM objects (pattern of `test_field_metrics.py`): category-change flag (real change vs rename), thresholds at 4/5 (`field_size` for percentile, `timed_finishers` for the gap), even-sized median, lapped athlete, DNF/DSQ/DNS, position without time, skipped válida/season, speed only with a course setup, season completion counts, no cross-season aggregate [agent: qa-engineer · sonnet]
- [ ] T069 [P] [US6] `backend/tests/routers/test_athlete_race_history.py`: coach/admin 200, other coach and other parent refused as `verify_athlete_access` does today, statement count ≤ 4, response schema has no third-party field, `series_kind` filter [agent: qa-engineer · sonnet]

### Implementation for User Story 6

- [ ] T070 [US6] `backend/app/services/race/history.py::build_history_points` — pure, reuses `field_metrics.compute_field_metrics` per season and `course/derived.py::derive_figures`; adds `timed_finishers`, thresholds (`MIN_FIELD = 5`), frozen label, `category_changed`/`previous_category_label`, `SeasonCompletion`; does **not** modify `compute_field_metrics` [agent: data-analyst · sonnet]
- [ ] T071 [P] [US6] `AthleteRaceHistoryRead`, `HistoryPoint`, `SeasonCompletion` (`extra="forbid"`) in `backend/app/schemas/athlete_race_analysis.py` [agent: fastapi-architect · sonnet]
- [ ] T072 [US6] Loader (≤ 4 statements, field rows restricted to the athlete's `(event_id, category_id)` pairs) and `GET /{athlete_id}/race-analysis/history` in `backend/app/routers/athlete_race_analysis.py` behind `verify_athlete_access`; caveat codes constant [agent: fastapi-architect · sonnet]
- [ ] T073 [P] [US6] `frontend/src/api/raceHistory.ts`, `frontend/src/types/raceHistory.types.ts`, `frontend/src/hooks/race/useAthleteRaceHistory.ts` [agent: react-ui-engineer · sonnet]
- [ ] T074 [US6] `frontend/src/components/race/history/`: `HistoryProgressionCard.tsx` (lazy), `HistoryChart.tsx` (single axis, metric toggle, inverted gap axis with "Mediana de su categoría", `ReferenceLine` per category change, dashed connector over gaps, hollow marker for non-finishers, field size in every tooltip), `HistoryTable.tsx` (grouped by season → category, "sin dato"), `CaveatsNote.tsx` (`role="note"`), `SeasonCompletionChips.tsx`; consult the `dataviz` skill before writing chart code [agent: react-ui-engineer · sonnet]
- [ ] T075 [US6] Mount the card (audience `coach`) on the race-analysis surface of `frontend/src/routes/athletes/AthleteDetailPage.tsx` behind `React.lazy` + Suspense with the text-first block [agent: react-ui-engineer · sonnet]
- [ ] T076 [P] [US6] vitest + MSW + jest-axe in `frontend/src/components/race/history/__tests__/`: loading, empty, error, all-null metrics, category marker, non-finisher marker, percentile never joined across groups, caveats always present [agent: qa-engineer · sonnet]
- [ ] T077 [P] [US6] Tablet heuristic review of the card: can the coach answer "¿mejoró entre 2024 y 2026 y dónde cambió de categoría?" in under one minute (SC-008); findings appended to `specs/044-race-history-backfill/ux-review.md` [agent: ux-researcher · sonnet]

**Checkpoint**: the coach has the answer that motivated the feature.

---

## Phase 9: User Story 7 — Families see their child's complete history (Priority: P2)

**Goal**: the same series for families, no third parties, pre-registration results only once the notice is in force.

**Independent Test**: spec US7 — parent sees both periods with the gate open, only post-registration results with it closed and no hint of missing data, never a third-party row.

### Tests for User Story 7 ⚠️ write first

- [ ] T078 [P] [US7] Extend `backend/tests/routers/test_athlete_race_history.py`: parent with gate closed (setting empty; setting naming a not-yet-effective policy) gets only results dated on/after `athlete.created_at`, `seasons` recomputed, no count or flag of withheld rows; gate open returns everything; coach never filtered [agent: qa-engineer · sonnet]
- [ ] T079 [P] [US7] `frontend/src/routes/parents/__tests__/MyAthleteDetailPage.history.test.tsx`: family wording, category-change explainer, no third-party text, jest-axe, text-first block before the lazy chart [agent: qa-engineer · sonnet]

### Implementation for User Story 7

- [ ] T080 [US7] Parent gate in the history loader (`backend/app/routers/athlete_race_analysis.py` / `backend/app/services/race/history.py` shell): resolve `RACE_HISTORY_FAMILY_POLICY_VERSION` through `app/services/privacy.py`, filter server-side for role `parent` only, leak nothing about what was removed (contract "Parent filter", data-model invariant 6) [agent: fastapi-architect · opus]
- [ ] T081 [P] [US7] Draft the privacy-notice paragraph for families in español neutro (published historical results, including those before joining, are displayed; only the child's own results; field shown as aggregates; how to ask questions) in `docs/10-race-results/history-family-notice.md`, ready for the owner to publish as a new policy version [agent: parent-communicator · sonnet]
- [ ] T082 [US7] `audience="family"` variant of `HistoryProgressionCard` (explainer "Subió de categoría: ahora corre con deportistas mayores. Es normal que el puesto baje al comienzo.", no comparative wording) mounted on `frontend/src/routes/parents/MyAthleteDetailPage.tsx` [agent: react-ui-engineer · sonnet]
- [ ] T083 [P] [US7] Review all family-facing copy of the card against FR-042 and the constitution's youth safeguards on a 360 px viewport; findings appended to `specs/044-race-history-backfill/ux-review.md` [agent: ux-researcher · sonnet]
- [ ] T084 [US7] Gate G6: US6 + US7 independent tests pass; a parent account on the isolated stack shows zero third-party strings (SC-010) [agent: engineering-lead · opus]

**Checkpoint**: all seven stories functional on synthetic data.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: real-infrastructure verification, mandatory audit, docs, release.

- [ ] T085 [P] `backend/tests/mysql/test_race_history_models.py` (`-m mysql`): the signature triple with empty strings, the dropped unique + plain index, the three frozen columns round-trip, both enums' stored values [agent: qa-engineer · sonnet]
- [ ] T086 Run `pytest -m mysql` against a `_test` database and `alembic upgrade head` / `downgrade -1` on MySQL 8.4; fix what it surfaces in the migration [agent: database-architect · opus]
- [ ] T087 [P] Playwright `frontend/e2e/race-history.spec.ts` on the isolated stack: stage two synthetic files → correct a gap → decide identity → commit → coach series with marker → parent view without third parties [agent: qa-engineer · sonnet]
- [ ] T088 [P] Run `pytest -m golden` once to confirm no drift (no AI change expected); record the composite in `docs/technical-notes.md` [agent: qa-engineer · sonnet]
- [ ] T089 Full gates: `pytest`, `ruff check`, `npm run typecheck`, `npm test`, `npm run build`; bundle check that the history chunk is lazy and the athlete route stays under budget [agent: qa-engineer · sonnet]
- [ ] T090 Mandatory privacy audit over parser changes, staging, identity review and resolver, guard, history endpoint, both UI audiences, the script and every new log event; verdict and conditions in `specs/044-race-history-backfill/privacy-audit.md` [agent: data-privacy-guard · sonnet]
- [ ] T091 Review T090 (policy: a sonnet safety worker is reviewed by an opus lead); confirm FR-043's deferred items are written down with an owner; sign off or return it [agent: data-platform-lead · opus]
- [ ] T092 [P] `docs/10-race-results/history-backfill-design.md`: the overprint finding and the band reader, category vocabulary by season, signatures and the review, the lock, thresholds, the legal basis (legitimate interest; "public on a blog" ≠ public data), deferred erasure/retention [agent: technical-writer · sonnet]
- [ ] T093 [P] `docs/10-race-results/runbook-ops.md` §11 — real-load runbook from `quickstart.md` §8, including the pre-load checklist line "third-party lock green" and the reminder that a local backend may point at production [agent: technical-writer · sonnet]
- [ ] T094 [P] Update `docs/implementation-status.md` and `docs/technical-notes.md`; rewrite the Feature 044 paragraph of `CLAUDE.md` (it lives **below** the `SPECKIT` markers — the block between them is machine-managed and gets replaced by `/speckit-agent-context-update`) to the shipped state [agent: technical-writer · sonnet]
- [ ] T095 [P] Record the pre-existing concern of research R-14 (real official files under `backend/tests/fixtures/race/`) as an open item in `docs/technical-notes.md` for an owner decision; do not delete or replace them in this feature [agent: technical-writer · sonnet]
- [ ] T096 Review the real-load runbook (T093) from the data side: order of operations, spot-check procedure against official files, rollback of a bad season (delete by `imported_from_id`) [agent: data-platform-lead · opus]
- [ ] T097 Pre-deploy checklist: single Alembic head, migration dry-run timing on a production-sized copy, `RACE_HISTORY_FAMILY_POLICY_VERSION` unset in Render, seeds to run after migrate [agent: release-manager · sonnet]
- [ ] T098 Gate G7: every gate above green; constitution re-check of `plan.md` still PASS; hand over to the owner for deploy [agent: engineering-lead · opus]
- [ ] T099 Post-deploy smoke: `/health`, one authenticated endpoint, `GET …/race-analysis/history` for one athlete as coach, the lock returns 403 for an unlinked competitor [agent: release-manager · sonnet]
- [ ] T100 Pre-load privacy check on production after deploy and before the owner stages real files: lock green, no `city` in any non-identity response, logs clean on a synthetic staged file that is then discarded [agent: data-privacy-guard · sonnet]
- [ ] T101 [P] Verify `frontend` copy strings added by this feature are español neutro with full diacritics (grep for ASCII fallbacks) [agent: qa-engineer · sonnet]
- [ ] T102 [P] Add the two new pages and the card to the a11y inventory / test index the project keeps under `frontend/src/test/` if one exists; otherwise note "n/a" in `tasks.md` [agent: qa-engineer · sonnet]
- [ ] T103 [P] Mutation-testing scope: add `app/services/race/completeness.py`, `identity_resolver.py`, `history.py` and `third_party_guard.py` to `[tool.mutmut]` in `backend/pyproject.toml` [agent: qa-engineer · sonnet]
- [ ] T104 Final acceptance against SC-001…SC-012 of `spec.md` on the deployed build; list any criterion still unverified with its owner [agent: product-manager · opus]

### Owner-only steps (no agent — real data, real people)

- [ ] T105 Obtain the fifteen official files and write the manifest **outside the repository**; stage them with `backend/scripts/stage_race_history.py`
- [ ] T106 Resolve pending categories (correct or acknowledge) and complete the identity review in the UI
- [ ] T107 Commit season by season; spot-check three club athletes against the official files; publish the privacy-notice version, set `RACE_HISTORY_FAMILY_POLICY_VERSION`, re-check a parent account

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (1)** → **Foundational (2)** → stories.
- **US1 (3)**, **US2 (4)**, **US3 (5)** are independent of each other after Phase 2 and can run in parallel.
- **US4 (6)** needs Phase 2; its ingestor wiring (T046) lands after T029 (same file).
- **US5 (7)** needs US1, US2, US4 **and gate G3 (US3)**.
- **US6 (8)** needs Phase 2 and T029/T030 (frozen label); it does not need the historical load to be testable.
- **US7 (9)** needs US6.
- **Polish (10)** needs everything; T105–T107 need T099–T100.

### Same-file serialisation (never parallel)

- `backend/app/services/race/pdf_parser.py`: T015 → T016
- `backend/app/services/race/ingestor.py`: T029 → T046 → T060
- `backend/app/routers/race_imports.py`: T019 → T050 → T059 → T061
- `backend/app/schemas/race_imports.py`: T018 → T061
- `backend/app/routers/athlete_race_analysis.py`: T072 → T080
- `frontend/src/components/competitions/import/ImportWizard.tsx`: T022 → T031
- `backend/tests/routers/test_athlete_race_history.py`: T069 → T078

### Within Each User Story

Tests first and failing → models/schemas → services → routers → UI → story gate.

### Parallel Opportunities

After G1, three tracks can run at once: **reading** (T011–T024), **categories** (T025–T031) and **lock** (T032–T037). Inside each story every `[P]` test task can be launched together.

## Parallel Example: after gate G1

```text
Track A (US1): qa-engineer·sonnet T011 T012 T013 T014  →  data-analyst·opus T015  →  …
Track B (US2): qa-engineer·sonnet T025 T026 T027       →  data-analyst·sonnet T028 →  …
Track C (US3): qa-engineer·sonnet T032 T033            →  fastapi-architect·opus T034 → …
```

## Implementation Strategy

### MVP First

Phases 1–3 alone already fix a live defect: the same overprint can lose rows in a 2026 file with a long club name. US1 is shippable on its own.

### Incremental Delivery

1. US1 + US2 → faithful preview (deployable, no historical commit possible yet because of the identity gate — by design).
2. US3 → lock (deployable, invisible to users).
3. US4 + US5 → historical load on synthetic data, then the owner's real load (T105–T107).
4. US6 → coach series. 5. US7 → families, once the notice is published.

### Waves for a multi-agent run (owner preference: work in waves, pause at 80 % of session usage)

- **W1**: Phases 1–2. **W2**: Phases 3, 4, 5 in parallel. **W3**: Phase 6. **W4**: Phases 7 and 8 in parallel (8 has no dependency on 7). **W5**: Phases 9–10.
- Opus is spent on 21 tasks only. If session budget is tight, the only opus overrides that may fall back to sonnet with a lead review are T086 and T080 — never T008, T015, T034 or T044–T047.

## Notes

- `[P]` = different files, no dependency on an incomplete task.
- Commit after each task or logical group; Conventional Commits, type in English, description in español latino, no mention of AI tooling.
- Never edit the 2026 parser oracles to make a test pass (T020).
- Stop at every gate; a lead signs it in this file with the date.
