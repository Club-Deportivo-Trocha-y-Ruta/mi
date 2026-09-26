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
- [X] T024b [US1] Time cells that are not `H:MM:SS` (found in the real local load, 2026-09-22): lenient lap-deficit, `MM:SS` and two-digit-hour tokens in `pdf_parser._RESULTS_ROW_RE` + glued-token split; `parse_time` reads them (and `""` → FINISHED without time); the ingestor keeps position-without-time and unparseable rows (migration `b4e8d2f61a93` relaxes the time CHECK) and asserts per-category accounting. Empty-time rows on the 15 files 230 → 6; 2026 file 0 → 0. Tests: `test_parser_time_variants.py`, `test_normalizer.py::TestParseTime`, `test_ingestor.py::TestRowsWithoutRecognisableTime`, `tests/models/test_race_result_finished_without_time_migration.py`. See research.md R-01/R-05 addenda [agent: data-analyst · opus]

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

- [X] T038 [P] [US4] `backend/tests/services/race/test_identity_review.py`: candidate rules (extra surname, inverted surnames, accents; `same_valida_two_categories`, `sex_conflict`, `age_path_backwards`, `club_and_city_differ`; club-only change raises nothing), `pair_hash` idempotence across rebuilds, decided candidates never reset [agent: qa-engineer · sonnet]
- [X] T039 [P] [US4] `backend/tests/services/race/test_identity_resolver.py` (incl. hypothesis for idempotence): the five resolver branches of the contract, `athlete_id` persisted for a linked competitor whatever the row's club, `IdentityUnresolved` when no tie-break exists [agent: qa-engineer · sonnet]
- [X] T040 [P] [US4] `backend/tests/routers/test_race_identity.py`: rebuild/list/summary/decide/reverse happy paths; 409 on deciding a non-pending candidate; reversal before and after commit (results move, link cleared on the split-off competitor, audit rows); `linked_athlete_involved`; denied paths parent/athlete 403 [agent: qa-engineer · sonnet]
- [X] T041 [P] [US4] Schema-walk test in `backend/tests/privacy/test_city_not_serialised.py`: `city` / `city_text` / `city_norm` appear in no response model outside `app/schemas/race_identity.py` [agent: qa-engineer · sonnet]
- [X] T042 [P] [US4] Update `backend/tests/services/race/test_ingestor_concurrency.py`: two concurrent ingests of the same new rider yield one competitor through the signature unique key [agent: qa-engineer · sonnet]

### Implementation for User Story 4

- [X] T043 [US4] Review the candidate rules and thresholds of research R-06 against the owner's decision 3 and FR-016/FR-017 before code is written; confirm "club alone is not a signal" and the blocking key; note the outcome in `research.md` R-06 [agent: data-platform-lead · opus]
> **Note from the T036 privacy audit (2026-09-18)**: the structural scan of the third-party lock only indexes public first-level callables whose signature has a literal `competitor_id` parameter. A function taking `competitor_ids: list[int]` — exactly the shape the identity review needs — would **not** be detected. Whoever implements US4 must either keep that shape out of the public surface or extend the scan in `tests/privacy/test_third_party_lock.py` to cover it; a reviewer must check this explicitly at gate G4.

- [X] T044 [US4] Implement `backend/app/services/race/identity_review.py::build_candidates` (pure core + DB shell): universe = staged imports' parsed rows + existing competitors; blocked `token_set_ratio ≥ 90`; homonym signals; snapshots without logging names; named constants `SAME_PERSON_MIN_SCORE`, `DIVERGENCE_MAX_SCORE` [agent: data-analyst · opus]
- [X] T045 [US4] Implement `backend/app/services/race/identity_resolver.py::IdentityResolver` per the contract's resolver table, including signature upsert with `first_season`/`last_season` widening and `source_candidate_id` [agent: data-analyst · opus]
- [X] T046 [US4] Replace both name-only upserts in `backend/app/services/race/ingestor.py` with the resolver; store `city_text`; persist `athlete_id` whenever the resolved competitor is linked; keep `is_trocha_y_ruta` only for deciding whether the wizard asks for a match [agent: fastapi-architect · opus]
- [X] T047 [US4] Decisions and reversal in `backend/app/services/race/identity_review.py` (`decide`, `reverse`, post-commit split/merge exactly as in the contract's "Reversal semantics"), each with `record_audit` [agent: data-analyst · opus]
- [X] T047b [US4] Owner decision 2026-09-21 "separar por categoría": `discriminator` on `race_competitor_signatures` (revision `a7c3e5d91f20`, unique key on the quadruple), category-split records and `age_incompatible_categories` in `identity_review.py`, intra-triple `different_people` split, discriminator-aware `IdentityResolver`; docs in `data-model.md` §3, `research.md` R-06 §9, `spec.md` Assumptions; tests incl. `tests/models/test_race_signature_discriminator_migration.py` and `-m mysql` `tests/mysql/test_race_signature_discriminator_mysql.py` [agent: data-analyst · opus]
- [X] T047c [US4] Owner decision 2026-09-22 "revisión acotada al club": `build_candidates` only raises pairs with a side linked to a club athlete (`in_club_scope`); `IdentityResolver` attaches by name only to linked competitors, resolves third-party same-válida collisions with `collision_discriminators` (category, else `bib:`, else `row:`) and falls back instead of raising for third-party triples; `rebuild` deletes out-of-scope pending candidates (`removed` in `RebuildResult`/`RebuildResultRead`, rebuild toast in `IdentityReviewPage.tsx`); docs in `spec.md` Assumptions, `research.md` R-06 §10, contract, `data-model.md` §3 [agent: data-analyst]
- [X] T048 [P] [US4] `backend/app/schemas/race_identity.py` (`IdentityRecordRead` — the only schema with `city`, `IdentityCandidateRead`, `IdentityDecisionIn`, `IdentitySummaryRead`, `RebuildResultRead`; `extra="forbid"`) [agent: fastapi-architect · sonnet]
- [X] T049 [US4] `backend/app/routers/race_identity.py` (prefix `/api/race-identity`, `require_role([admin, coach])`, rebuild in a worker thread with 30 s timeout and the budget in the docstring) and mount it in `backend/app/main.py` [agent: fastapi-architect · sonnet]
- [X] T050 [US4] Commit gate in `backend/app/routers/race_imports.py`: `409 {"code":"identity_review_pending","pending":n}` on `/commit` while any candidate is pending [agent: fastapi-architect · sonnet]
- [X] T051 [P] [US4] `frontend/src/api/raceIdentity.ts`, `frontend/src/types/raceIdentity.types.ts`, `frontend/src/hooks/race/useIdentityReview.ts` [agent: react-ui-engineer · sonnet]
- [X] T052 [US4] `frontend/src/routes/competitions/history/IdentityReviewPage.tsx` per `contracts/ui-history.md` §4 (side-by-side cards, signals in words, two ≥ 48 px actions, keyboard shortcuts, progress, state filter, "Deshacer" with confirmation, linked-athlete chip) and its route registration [agent: react-ui-engineer · sonnet]
- [X] T053 [P] [US4] vitest + MSW + jest-axe for `IdentityReviewPage` (pending, empty, error, resume, undo) in `frontend/src/routes/competitions/history/__tests__/` [agent: qa-engineer · sonnet]
- [X] T054 [P] [US4] Heuristic and copy review of the identity review on a tablet viewport (one decision ≤ 15 s, SC-009); findings to `specs/044-race-history-backfill/ux-review.md` [agent: ux-researcher · sonnet]
- [X] T055 [US4] Gate G4 — **PASSED 2026-09-21**. US4 tests green (identity services 149 + router 16 + city schema-walk 6; race/privacy/routers/models lane 2 775 passed, only the 3 known pre-existing failures). `/rebuild` core on 3 000 synthetic names: 0.22 s (0.09 s idempotent); end-to-end cost is dominated by re-parsing staged PDFs (0.60 s/file) — figure and mitigation recorded in `plan.md` Complexity Tracking. Structural scan of the third-party lock extended to `competitor_ids` and public methods (T036 note closed). Original text: Gate G4: US4 independent test passes; measure `POST /rebuild` on a synthetic universe of 3 000 names; if > 10 s, record the figure and the mitigation in `plan.md` Complexity Tracking [agent: engineering-lead · opus]

**Checkpoint**: identity is decided by a person, before any merge.

---

## Phase 7: User Story 5 — The fifteen válidas through the same trusted path (Priority: P1)

**Goal**: staging, partial commit and a board for the historical load, on the existing preview → dry-run → commit path. Contract: `contracts/historical-load.md` (FR-023…FR-029).

**Independent Test**: spec US5 — two synthetic válidas of one season: season and válidas created, full fields, calculated standings, re-load creates nothing, audit trail complete.

**⛔ Requires gate G3 (T037) checked.**

### Tests for User Story 5 ⚠️ write first

- [X] T056 [P] [US5] `backend/tests/services/race/test_import_staging.py`: the extracted staging service produces the same `RaceImport` and response as today's `/parse` for a 2026 file (golden comparison), stages a historical builder file with season/válida/date/venue taken from the inputs, never assumed (FR-025), and emits `header_mismatch` when the printed header disagrees [agent: qa-engineer · sonnet]
- [X] T057 [P] [US5] `backend/tests/routers/test_race_imports_history.py`: the full start list is committed, including categories where no club athlete raced (FR-028); printed points kept verbatim (FR-026); partial commit ingests consistent/acknowledged categories and lists `pending_categories`; `/commit-pending` finishes them, returns `409 nothing_pending` afterwards and obeys the same `409 identity_review_pending` gate as `/commit`; re-staging or re-committing an identical file creates nothing in any table (FR-027); interrupted load resumes; standings carry `is_calculated` [agent: qa-engineer · sonnet]
- [X] T058 [P] [US5] `backend/tests/services/race/test_2026_unchanged.py`: with two historical seasons loaded, `GET /evolution`, results and standings of 2026 and the race-AI analyst context are identical to the baseline without them (FR-029, R-15) [agent: qa-engineer · sonnet]

### Implementation for User Story 5

- [X] T059 [US5] Extract the body of `parse_import` into `backend/app/services/race/import_staging.py::stage_results_file` and make `backend/app/routers/race_imports.py` a thin caller (no behaviour change; T056 is the safety net) [agent: fastapi-architect · sonnet]
- [X] T060 [US5] `only_categories` support in `backend/app/services/race/ingestor.py::ingest_event` (bypasses the SHA-256 short-circuit only for a restricted re-run) and unknown-header / inconsistent categories skipped into `pending_categories` [agent: fastapi-architect · sonnet]
> **Note from gate G4 (2026-09-21), closed same day by W4**: cached the corrected parsed rows per staged import (key `(sha256, corrections revision)`, plus a second cache of the raw parse keyed by `sha256` alone) so `/rebuild` and the commit gate stop re-downloading and re-parsing every staged PDF — two process-local bounded LRUs in `routers/race_imports.py` (comment above `_reload_results_document`). Re-measured against 15 staged imports through the real path: first rebuild 1.513 s, second (same corrections revision) 0.002 s. See `plan.md` Complexity Tracking for the full figure and `tests/routers/test_race_imports_history.py::TestG4CacheAvoidsReparseOnSecondRebuild` for the regression test (counts `storage_sftp.download_to_tempfile` calls, not wall-clock).

- [X] T061 [US5] `POST /{id}/commit-pending` (behind the same identity-review gate as `/commit`, FR-018 — reuse its rebuild-then-check pattern: run `identity_review.rebuild` with `load_identity_rows` first, then 409 `identity_review_pending` when pending > 0) and the `pending_categories` bookkeeping in `backend/app/routers/race_imports.py`; `pending_categories_count` in the import list schema [agent: fastapi-architect · sonnet]
- [X] T062 [P] [US5] `is_calculated: true` on the standings read schema in `backend/app/schemas/race_results.py` and `backend/app/services/race/standings.py` [agent: fastapi-architect · sonnet]
- [X] T063 [P] [US5] `backend/scripts/stage_race_history.py`: reads a manifest (season, válida, date, venue, path) located **outside the repository**, calls `stage_results_file`, supports `--dry`, never commits, prints ids and counts only; refuses a manifest or file path inside the repo and any cumulative-standings file (FR-024) [agent: data-analyst · sonnet]
- [X] T064 [US5] `frontend/src/routes/competitions/history/HistoricalLoadPage.tsx` per `contracts/ui-history.md` §3 (board by season and state, pending-category counters, identity banner, commit and commit-pending actions with the gate reason) and its route + navigation entry for coach/admin [agent: react-ui-engineer · sonnet]
- [X] T065 [P] [US5] "Clasificación calculada por la plataforma" label on the standings table component under `frontend/src/components/competitions/` [agent: react-ui-engineer · sonnet]
- [X] T066 [P] [US5] vitest + MSW + jest-axe for `HistoricalLoadPage` in `frontend/src/routes/competitions/history/__tests__/` [agent: qa-engineer · sonnet]
- [X] T067 [US5] Gate G5 — **PASSED 2026-09-22**. US5 tests green on synthetic seasons (staging golden, partial commit + `/commit-pending` behind the same identity gate, `matches_unresolved` 409, idempotent re-stage/re-commit, 2026 unchanged); G3 re-verified on the same tree (`tests/privacy` green). Lead fix during the gate: a partially committed import kept its pending categories out of the identity universe, so a homonym between those rows and a later file would reach `/commit-pending` unreviewed — `load_universe` and `load_identity_rows` now include only the pending categories of such imports (regression test in `test_identity_review.py`). G4 cache re-measured: 15 staged imports 1.51 s → 0.002 s. Backend lane 2 856 passed / 3 pre-existing failures; frontend affected suites 1 058 passed (one intermittent failure seen once in four runs, not reproduced). Original text: Gate G5: US5 independent test passes on synthetic seasons; G3 re-verified green on the same commit [agent: engineering-lead · opus]

**Checkpoint**: the historical load works end to end on synthetic data.

---

## Phase 8: User Story 6 — Is the athlete improving across seasons? (Priority: P2)

**Goal**: one continuous series per athlete with category-change markers, thresholds, caveats.

**Independent Test**: spec US6 — three seasons, one category change, a skipped válida, a DNF, a four-finisher válida.

### Tests for User Story 6 ⚠️ write first

- [X] T068 [P] [US6] `backend/tests/services/race/test_history.py` with in-memory ORM objects (pattern of `test_field_metrics.py`): category-change flag (real change vs rename), thresholds at 4/5 (`field_size` for percentile, `timed_finishers` for the gap), even-sized median, lapped athlete, DNF/DSQ/DNS, position without time, skipped válida/season, speed only with a course setup, season completion counts, no cross-season aggregate [agent: qa-engineer · sonnet]
- [X] T069 [P] [US6] `backend/tests/routers/test_athlete_race_history.py`: coach/admin 200, other coach and other parent refused as `verify_athlete_access` does today, statement count ≤ 4, response schema has no third-party field, `series_kind` filter [agent: qa-engineer · sonnet]

### Implementation for User Story 6

- [X] T070 [US6] `backend/app/services/race/history.py::build_history_points` — pure, reuses `field_metrics.compute_field_metrics` per season and `course/derived.py::derive_figures`; adds `timed_finishers`, thresholds (`MIN_FIELD = 5`), frozen label, `category_changed`/`previous_category_label`, `SeasonCompletion`; does **not** modify `compute_field_metrics` [agent: data-analyst · sonnet]
- [X] T071 [P] [US6] `AthleteRaceHistoryRead`, `HistoryPoint`, `SeasonCompletion` (`extra="forbid"`) in `backend/app/schemas/athlete_race_analysis.py` [agent: fastapi-architect · sonnet]
- [X] T072 [US6] Loader (≤ 4 statements, field rows restricted to the athlete's `(event_id, category_id)` pairs) and `GET /{athlete_id}/race-analysis/history` in `backend/app/routers/athlete_race_analysis.py` behind `verify_athlete_access`; caveat codes constant [agent: fastapi-architect · sonnet]
- [X] T073 [P] [US6] `frontend/src/api/raceHistory.ts`, `frontend/src/types/raceHistory.types.ts`, `frontend/src/hooks/race/useAthleteRaceHistory.ts` [agent: react-ui-engineer · sonnet]
- [X] T074 [US6] `frontend/src/components/race/history/`: `HistoryProgressionCard.tsx` (lazy), `HistoryChart.tsx` (single axis, metric toggle, inverted gap axis with "Mediana de su categoría", `ReferenceLine` per category change, dashed connector over gaps, hollow marker for non-finishers, field size in every tooltip), `HistoryTable.tsx` (grouped by season → category, "sin dato"), `CaveatsNote.tsx` (`role="note"`), `SeasonCompletionChips.tsx`; consult the `dataviz` skill before writing chart code [agent: react-ui-engineer · sonnet]
- [X] T075 [US6] Mount the card (audience `coach`) on the race-analysis surface of `frontend/src/routes/athletes/AthleteDetailPage.tsx` behind `React.lazy` + Suspense with the text-first block [agent: react-ui-engineer · sonnet]
- [X] T076 [P] [US6] vitest + MSW + jest-axe in `frontend/src/components/race/history/__tests__/`: loading, empty, error, all-null metrics, category marker, non-finisher marker, percentile never joined across groups, caveats always present [agent: qa-engineer · sonnet]
- [X] T077 [P] [US6] Tablet heuristic review of the card: can the coach answer "¿mejoró entre 2024 y 2026 y dónde cambió de categoría?" in under one minute (SC-008); findings appended to `specs/044-race-history-backfill/ux-review.md` [agent: ux-researcher · sonnet]

**Checkpoint**: the coach has the answer that motivated the feature.

---

## Phase 9: User Story 7 — Families see their child's complete history (Priority: P2)

**Goal**: the same series for families, no third parties, pre-registration results only once the notice is in force.

**Independent Test**: spec US7 — parent sees both periods with the gate open, only post-registration results with it closed and no hint of missing data, never a third-party row.

### Tests for User Story 7 ⚠️ write first

- [X] T078 [P] [US7] Extend `backend/tests/routers/test_athlete_race_history.py`: parent with gate closed (setting empty; setting naming a not-yet-effective policy) gets only results dated on/after `athlete.created_at`, `seasons` recomputed, no count or flag of withheld rows; gate open returns everything; coach never filtered [agent: qa-engineer · sonnet]
- [X] T079 [P] [US7] `frontend/src/routes/parents/__tests__/MyAthleteDetailPage.history.test.tsx`: family wording, category-change explainer, no third-party text, jest-axe, text-first block before the lazy chart [agent: qa-engineer · sonnet]

### Implementation for User Story 7

- [X] T080 [US7] Parent gate in the history loader (`backend/app/routers/athlete_race_analysis.py` / `backend/app/services/race/history.py` shell): resolve `RACE_HISTORY_FAMILY_POLICY_VERSION` through `app/services/privacy.py`, filter server-side for role `parent` only, leak nothing about what was removed (contract "Parent filter", data-model invariant 6) [agent: fastapi-architect · opus]
- [X] T081 [P] [US7] Draft the privacy-notice paragraph for families in español neutro (published historical results, including those before joining, are displayed; only the child's own results; field shown as aggregates; how to ask questions) in `docs/10-race-results/history-family-notice.md`, ready for the owner to publish as a new policy version [agent: parent-communicator · sonnet]
- [X] T082 [US7] `audience="family"` variant of `HistoryProgressionCard` (explainer overridden 2026-09-22 by lead's UX review to the neutral wording already shipped in `HistoryTable.tsx`: "Cambió de categoría (de {anterior} a {nueva}). En la nueva categoría compite con otro grupo, así que el puesto no se compara directamente con el anterior." — never the "Subió de categoría… deportistas mayores… el puesto baje" text originally drafted here) mounted on `frontend/src/routes/parents/MyAthleteDetailPage.tsx` [agent: react-ui-engineer · sonnet]
- [X] T083 [P] [US7] Review all family-facing copy of the card against FR-042 and the constitution's youth safeguards on a 360 px viewport; findings appended to `specs/044-race-history-backfill/ux-review.md` [agent: ux-researcher · sonnet]
- [X] T084 [US7] Gate G6 — **PASSED 2026-09-22**. US6 + US7 tests green (history 224, family gate incl. no-withheld-hint, parent Carreras tab 387 frontend); SC-010 verified end to end by `frontend/e2e/race-history.spec.ts` on the isolated Docker stack (1 passed): the parent view shows no third-party string. T083 blocker/majors fixed (mobile cards, `category_change_kind`, plain-language metric explainer). Original text: Gate G6: US6 + US7 independent tests pass; a parent account on the isolated stack shows zero third-party strings (SC-010) [agent: engineering-lead · opus]

**Checkpoint**: all seven stories functional on synthetic data.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: real-infrastructure verification, mandatory audit, docs, release.

- [X] T085 [P] `backend/tests/mysql/test_race_history_models.py` (`-m mysql`): the signature triple with empty strings, the dropped unique + plain index, the three frozen columns round-trip, both enums' stored values [agent: qa-engineer · sonnet] — 4 tests; run for real 2026-09-22 against the throwaway MySQL 8.4 container from T086 (`TEST_DATABASE_URL=mysql+aiomysql://root:testroot@127.0.0.1:3407/trocha_ruta_test`), all 4 green. One real-MySQL bug found and fixed: the raw INSERT in `test_signature_server_default_lands_as_empty_string_not_null` omitted `created_at`/`updated_at` (Python-only default, no `server_default` — unlike `club_norm`/`city_norm`/`discriminator`, which do declare one), failing 1364 on strict MySQL; fixed with explicit `UTC_TIMESTAMP()`. Full `-m mysql` lane (33 tests, `--ignore=tests/test_langchain_provider.py`) green: `33 passed, 5660 deselected`.
- [X] T086 — **Done 2026-09-22** on a throwaway MySQL 8.4 container (`_test` DB, isolated from production). `upgrade head` → `downgrade c2314ccd7927` → `upgrade head` clean after one fix: the downgrade of `8efe1618cb83` dropped `ix_race_competitor_signatures_competitor_id` before its table, which MySQL refuses because the index backs a FK (error 1553) and, DDL being non-transactional, left the schema half-reverted; the explicit `drop_index` calls are gone (`DROP TABLE` takes its indexes). Upgrade of both revisions on an empty DB: 4.2 s wall. `tests/test_audit_mysql.py::CURRENT_HEAD` bumped to `a7c3e5d91f20`. Original text: Run `pytest -m mysql` against a `_test` database and `alembic upgrade head` / `downgrade -1` on MySQL 8.4; fix what it surfaces in the migration [agent: database-architect · opus]
- [X] T087 [P] Playwright `frontend/e2e/race-history.spec.ts` on the isolated stack: stage two synthetic files → correct a gap → decide identity → commit → coach series with marker → parent view without third parties [agent: qa-engineer · sonnet] — written with a companion `backend/scripts/generate_e2e_race_history_fixtures.py`; run for real 2026-09-22 against a freshly-created `docker-compose.e2e.yml` stack (Docker became available mid-task) — **`1 passed (6.9s)`**. Four real bugs found and fixed while getting it green (all documented in the spec's own comments, not just here): a successful commit navigates straight out of the wizard (`CompetitionImportPage.tsx::handleCompleted`), so `import-wizard-step3` is never the observable success state; the confirm button can render enabled before `matchesData` is ready, so a too-early click is a silent no-op (`submitCommit`'s `if (!matchesData) return`) — fixed by waiting for `toBeEnabled` first; a Playwright coordinate-based click (even `force: true`) can land on an unrelated sonner toast instead of the covered button — fixed with `.evaluate(el => el.click())` (native DOM click) on every wizard/identity-review/board action button; the app session lives in `sessionStorage`, not cookies, so switching to the parent login needs `sessionStorage.clear()`, not `clearCookies()`. Re-running against the same seeded stack hits the SHA256 commit-dedupe guard on the first file ("ya fue commiteado") — the stack needs `down -v` + `up` between runs, now noted in the spec header. Isolated stack torn down after the passing run; the lead's `tyr-044-mysql-test` container (T086/T085) was left untouched throughout.
- [X] T088 **Closed 2026-09-22 without a golden run (lead decision, owner consulted)**: 044 changes no prompt, model or pipeline; `tests/services/race/test_2026_unchanged.py` (T058) proves the analyst context is identical with two historical seasons loaded. The eval only has a Gemini path (`RACE_AI_API_KEY`/`GOOGLE_API_KEY`) and its baseline is Gemini's, so a local `claude-cli` run would not be comparable; CI `race-eval.yml` keeps guarding it. Original text: [P] Run `pytest -m golden` once to confirm no drift (no AI change expected); record the composite in `docs/technical-notes.md` [agent: qa-engineer · sonnet]
- [X] T089 **Done 2026-09-22** (QA): typecheck + build clean; history card, chart and both new pages are separate lazy chunks, `AthleteDetailPage` chunk +0.25 kB gzip vs `main`; full vitest 1 failure pre-existing on `main` (`SessionWizardRouteNotify`); backend default lane (`-m "not golden and not integration and not mysql"`) failure set identical to `main`; ruff on files touched by the branch 37 findings vs 38 on `main` for the same files (pre-existing). Original text: Full gates: `pytest`, `ruff check`, `npm run typecheck`, `npm test`, `npm run build`; bundle check that the history chunk is lazy and the athlete route stays under budget [agent: qa-engineer · sonnet]
- [X] T090 — **Done 2026-09-22.** Mandatory privacy audit over parser changes, staging, identity review and resolver, guard, history endpoint, both UI audiences, the script and every new log event. Verdict: APROBADO CON CONDICIONES — 0 critical/high, 3 non-blocking medium findings (unfiltered process-local parse caches relying on router RBAC; an inaccurate docstring claiming `IdentityRecordRead` is the only schema serializing `city`; a "list of competitor ids" guard extension named in a commit message and recognized by the structural sweep test but with no matching runtime primitive). None block the real load or G5; all three are write-the-intention-down fixes to close before the feature is considered done. Full detail in `specs/044-race-history-backfill/privacy-audit.md` §2 [agent: data-privacy-guard · sonnet]
- [X] T091 **Done 2026-09-22** (lead review, `privacy-audit.md` §3): §2 verdict confirmed, its three conditions closed on the branch, FR-043 deferred items written down with an owner. Original text: Review T090 (policy: a sonnet safety worker is reviewed by an opus lead); confirm FR-043's deferred items are written down with an owner; sign off or return it [agent: data-platform-lead · opus]
- [X] T092 [P] `docs/10-race-results/history-backfill-design.md`: the overprint finding and the band reader, category vocabulary by season, signatures and the review, the lock, thresholds, the legal basis (legitimate interest; "public on a blog" ≠ public data), deferred erasure/retention [agent: technical-writer · sonnet]
- [X] T093 [P] `docs/10-race-results/runbook-ops.md` §12 — real-load runbook from `quickstart.md` §8, including the pre-load checklist line "third-party lock green" and the reminder that a local backend may point at production. Numbered §12, not §11 as originally planned — the multi-cup hotfix (§11) landed first [agent: technical-writer · sonnet]
- [X] T094 [P] Updated `docs/implementation-status.md` and `docs/technical-notes.md`; rewrote the Feature 044 paragraph of `CLAUDE.md` (below the `SPECKIT` markers) to the shipped-on-branch state — US7 and Polish explicitly called out as not started [agent: technical-writer · sonnet]
- [X] T095 [P] Recorded the pre-existing concern of research R-14 (real official files under `backend/tests/fixtures/race/`) as an open item in `docs/technical-notes.md` for an owner decision; files untouched [agent: technical-writer · sonnet]
- [X] T096 **Done 2026-09-22** (lead review): runbook §12 gained a mandatory pre-load backup; §12.6 rollback rewritten — only `race_results` carries `imported_from_id`, so the old one-line rollback left orphan competitors/signatures/candidates. Original text: Review the real-load runbook (T093) from the data side: order of operations, spot-check procedure against official files, rollback of a bad season (delete by `imported_from_id`) [agent: data-platform-lead · opus]
- [X] T097 — **Done 2026-09-22.** Added as `runbook-ops.md` §12.1 (former 12.1–12.6 renumbered 12.2–12.7, cross-references fixed): single Alembic head `a7c3e5d91f20`; migration timing 4.2 s on an empty MySQL 8.4 database (T086) — **production-sized dry-run timing is explicitly flagged as still open**, not measured against a copy of the real database; `RACE_HISTORY_FAMILY_POLICY_VERSION` unset in Render; post-migrate seeds verified against `entrypoint.sh` (neither runs automatically there) and each script's own docstring: `python -m scripts.seed_race_categories` and `python -m scripts.seed_race_points_schemes`, both idempotent UPSERT-by-`code`. Original text: Pre-deploy checklist: single Alembic head, migration dry-run timing on a production-sized copy, `RACE_HISTORY_FAMILY_POLICY_VERSION` unset in Render, seeds to run after migrate [agent: release-manager · sonnet]
- [X] T098 Gate G7 — **PASSED 2026-09-22, handed to the owner for deploy**. G1–G6 green; T090 audit approved with its three conditions closed; constitution re-check of `plan.md` unchanged (I–IV PASS, V respected: family copy states a promotion only when the catalogue proves it, no ranking among club athletes). Open for the owner: production-sized migration timing (T097), merge to `main` (Render deploys from it), T099/T100/T104 after deploy, T105–T107 real load. Original text: Gate G7: every gate above green; constitution re-check of `plan.md` still PASS; hand over to the owner for deploy [agent: engineering-lead · opus]
- [ ] T099 Post-deploy smoke: `/health`, one authenticated endpoint, `GET …/race-analysis/history` for one athlete as coach, the lock returns 403 for an unlinked competitor [agent: release-manager · sonnet]
- [ ] T100 Pre-load privacy check on production after deploy and before the owner stages real files: lock green, no `city` in any non-identity response, logs clean on a synthetic staged file that is then discarded [agent: data-privacy-guard · sonnet]
- [X] T101 [P] Verify `frontend` copy strings added by this feature are español neutro with full diacritics (grep for ASCII fallbacks) [agent: qa-engineer · sonnet] — grepped `git diff main...HEAD -- frontend/src` for common ASCII fallbacks; only hits were a synthetic uppercase-PDF fixture string (`"CATEGORIA RARA"`, intentionally unaccented printed text) and a `data-testid`; no real user-visible copy affected
- [X] T102 [P] Add the two new pages and the card to the a11y inventory / test index the project keeps under `frontend/src/test/` if one exists; otherwise note "n/a" in `tasks.md` [agent: qa-engineer · sonnet] — n/a: the project keeps no central a11y inventory under `frontend/src/test/` (only `setup.ts` wires jest-axe globally); a11y is asserted inline per component, and `HistoricalLoadPage.test.tsx`, `IdentityReviewPage.test.tsx` and `HistoryProgressionCard.test.tsx` already have inline `axe`/`toHaveNoViolations` checks
- [X] T103 [P] Mutation-testing scope: add `app/services/race/completeness.py`, `identity_resolver.py`, `history.py` and `third_party_guard.py` to `[tool.mutmut]` in `backend/pyproject.toml` [agent: qa-engineer · sonnet] — none were in `do_not_mutate`, so all four were already in scope by default; added a comment documenting that inclusion is deliberate (same pattern as `standings.py`), matching the file's existing per-module audit trail
- [ ] T104 Final acceptance against SC-001…SC-012 of `spec.md` on the deployed build; list any criterion still unverified with its owner [agent: product-manager · opus]

### Owner-only steps (no agent — real data, real people)

- ~~T105 Obtain the fifteen official files and write the manifest **outside the repository**; stage them with `backend/scripts/stage_race_history.py`~~ — **superseded 2026-09-26** by T190–T192 (the upload and that script are retired)
- ~~T106 Resolve pending categories (correct or acknowledge) and complete the identity review in the UI~~ — **superseded 2026-09-26** by T192 (same UI steps, on válidas staged by the skill)
- ~~T107 Commit season by season; spot-check three club athletes against the official files; publish the privacy-notice version, set `RACE_HISTORY_FAMILY_POLICY_VERSION`, re-check a parent account~~ — **superseded 2026-09-26** by T192

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

---

# Amendment 2026-09-26 — Skill-only results loading (T108…T192)

**Input**: `spec.md` (Clarifications 2026-09-26; FR-044…FR-049; corrected FR-027; Assumptions "Planning adjustments (2026-09-26)"), `plan.md` § Amendment 2026-09-26, `research.md` R-17…R-31, `data-model.md` §11, and six new contracts: `contracts/masked-view.md`, `contracts/reading-profile.md`, `contracts/results-skill-cli.md`, `contracts/staged-import.md`, `contracts/revision-via-skill.md` and `contracts/ui-review-only.md`. Also `quickstart.md` §9.

**Scope.** Every results-file upload is removed. Results enter only through the `race-results-load` skill:
- a local script masks the file;
- the LLM writes a reading profile from the masked view;
- a tested engine applies it locally;
- the same script stages the válida, locally by default and in production only when explicit.

The web app keeps review and commit. The amendment also wires the half-built revision path, and retires GENERAL, the fixed parsers, `/parse`, the old staging script and the two real fixtures.

**Tests**: REQUIRED, as for Phases 1–10: test tasks sit before the code they cover. Ported tests keep their assertions; only how they stage changes. A test deleted with the code it covered is listed by name in the commit body of the task that deletes it.

**Story labels**: the amendment changes two existing stories:
- `[US1]`: reading, which is now the masked view plus the reading-profile engine.
- `[US5]`: the load path: staging, CLI, upload removal, review-only web app and revisions.

Setup, Foundational, Skill and Polish tasks carry no label.

**Hard ordering rules**:
1. **No real official file is masked, applied or staged** before T180 (skill signed off) and T185 (audit reviewed). Until then everything runs on builder output.
2. **Phases 16 and 17 ship in the same deploy**: the frontend must never call a removed route.
3. **Phase 18 may be deferred.** While it is, the `revision_not_available` guard of T147 stays on: `stage` refuses a different reading of a committed válida (CLI exit 12) rather than staging a revision whose commit would only add rows.
4. **T122 generates the parity golden files with the retired parser before T153 deletes it.**

**Privacy rule for every task** (unchanged): fixtures are synthetic, and no official file, rider name, club or city is committed, logged, traced or pasted into a prompt. This now also covers the development session itself: the LLM reads only `masked/` and `report.json` of a run.

## Agent assignment (owner request: sonnet or opus "según el caso")

This follows the same policy as Phases 1–10:
- Leads orchestrate on **opus** and write no code.
- Workers execute on **sonnet**.
- A worker is promoted to opus through the Agent tool's `model` override only where one subtle mistake leaks minors' data or corrupts results. That is the case for seven tasks:
  - T126: masking, the only barrier between rider data and the LLM;
  - T128: run-to-column assignment, which decides every name, club and time;
  - T138: rewiring the six review routes that feed commit and the identity gate;
  - T145: the target guard, the only barrier between a laptop and the production database;
  - T173: identity-aware diff, which decides whose result changes or disappears;
  - T174: applying revisions to committed results under a lock;
  - T177: the skill instructions, which keep an LLM session away from minors' data.
- `data-privacy-guard` stays on sonnet by policy and is reviewed by an opus lead.

| Agent | Model | Tasks | Used for |
|---|---|---|---|
| `engineering-lead` | opus | 8 | T108 and gates G8–G14 (T117, T130, T142, T150, T156, T168, T176). Writes no code. |
| `data-platform-lead` | opus | 2 | Signs the skill for real files (T180); reviews the amendment's privacy audit (T185). |
| `product-manager` | opus | 1 | Final acceptance (T189). |
| `data-analyst` | **opus** (override) | 4 | Masking, apply engine, identity-aware diff, skill authoring (T126, T128, T173, T177). |
| `data-analyst` | sonnet | 5 | Type move, run primitives, vocabulary, profile schema, profiles (T113, T124, T125, T127, T129). |
| `fastapi-architect` | **opus** (override) | 2 | Review routes on staged documents; revision wiring (T138, T174). |
| `fastapi-architect` | sonnet | 12 | Loader, staging service, identity loader, legacy flag, GENERAL removal, CLI, removals, guard flip. |
| `devops-engineer` | **opus** (override) | 1 | Target guard (T145). |
| `devops-engineer` | sonnet | 1 | Claude Code deny rules (T178). |
| `database-architect` | sonnet | 2 | Migration and model of the new table (T114, T115). |
| `integration-engineer` | sonnet | 1 | Evidence upload and cleanup on SFTP (T149). |
| `qa-engineer` | sonnet | 30 | Every test task, the port of about 60 router tests, e2e, lanes and gates. |
| `react-ui-engineer` | sonnet | 5 | Review-only wizard, removals, routes, entry points, copy (T161–T165). |
| `ux-researcher` | sonnet | 1 | Copy and states review (T166). |
| `data-privacy-guard` | sonnet | 3 | Real-fixture removal, skill review, mandatory audit (T155, T179, T184). |
| `technical-writer` | sonnet | 3 | Runbook, design doc and CLAUDE.md bullet, status and notes (T181–T183). |
| `release-manager` | sonnet | 1 | Pre-deploy checklist and post-deploy smoke (T188). |
| **Total** | **18 opus · 64 sonnet** | **82** | + T190–T192 owner-only steps (no agent) |

---

## Phase 11: Setup (amendment)

**Purpose**: open the amendment and add the synthetic material every later phase needs.

- [ ] T108 Open the amendment:
  - record the owner's choice of implementation branch here;
  - run `alembic heads` and expect exactly one line (`be4595de1ad2` at planning), then record it;
  - confirm that T098 (G7) passed and record where T099/T100 stand;
  - confirm that the only real official files in the tree are the two in `backend/tests/fixtures/race/`.

  [agent: engineering-lead · opus]
- [ ] T109 [P] Extend `backend/tests/helpers/results_pdf_builder.py` (fake names only):
  - an **unruled fictional layout**: no rulings; columns in the order position, surname, given names, club, city, time, points;
  - a `--layout {historical,2026,unruled}` option;
  - a CLI entry, `python -m tests.helpers.results_pdf_builder --layout … --out …`, for quickstart §9.4.

  Add a synthetic delimited generator in `backend/tests/helpers/results_csv_builder.py`: `;`, `,` and tab delimiters, with categories as a column or as separator rows. Add self-tests to `backend/tests/helpers/test_results_pdf_builder.py`.

  [agent: qa-engineer · sonnet]
- [ ] T110 [P] Add `backend/tests/helpers/name_sweep.py::assert_no_fake_names(text, generator)`. It fails if any accent-folded word of three or more letters from the generator's names, clubs or cities appears in `text`. The masking, CLI and stdout tests reuse it.

  [agent: qa-engineer · sonnet]

---

## Phase 12: Foundational (amendment)

**Purpose**: the staged-document table and the neutral types that both stories need. **Blocks Phases 13–18.**

- [ ] T111 [P] Write `backend/tests/mysql/test_race_import_staged_documents.py` (`-m mysql`). It checks:
  - the table exactly as in `data-model.md` §11.1: `import_id INT PK, FK → race_imports.id ON DELETE CASCADE`, `schema_version SMALLINT NOT NULL`, `profile_id VARCHAR(64) NOT NULL`, `profile_sha256 CHAR(64) NOT NULL`, `engine_version VARCHAR(16) NOT NULL`, `document_json JSON NOT NULL`, `created_at DATETIME NOT NULL`;
  - that deleting the import cascades;
  - a JSON round-trip of a 300-row synthetic document;
  - upgrade → downgrade → upgrade, clean.

  [agent: qa-engineer · sonnet]
- [ ] T112 [P] Write `backend/tests/services/race/test_staged_document.py`. It covers:
  - a `save` → `load` round-trip into `ParsedResults` that preserves category order, `code: null` for an unrecognised header, `time_raw == ""` and unreadable rows;
  - `StagedDocumentMissing` when no row exists;
  - `delete` is idempotent;
  - no log record carries a row value (caplog plus `assert_no_fake_names`).

  [agent: qa-engineer · sonnet]
- [ ] T113 Move `ResultsRow` (seven fields: `position`, `bib`, `name`, `city`, `club`, `time_raw`, `points`), `ParsedCategory`, `ParsedResults` and `UnreadableRow`, unchanged, to `backend/app/services/race/staged_document.py`.
  - Keep a temporary re-export in `pdf_parser.py`, which T153 removes.
  - Update the imports in `completeness.py`, `routers/race_imports.py` and `import_staging.py`, the `TYPE_CHECKING` imports in `ingestor.py` and `revision.py`, and every test that imports these types (`identity_support.py`, `test_completeness.py`, `test_ingestor_*.py`, `test_reingest_staleness.py`, `test_inactive_categories_hidden.py`).
  - No behaviour change; the default lane stays green.

  [agent: data-analyst · sonnet]
- [ ] T114 Write the Alembic revision `backend/alembic/versions/<rev>_race_import_staged_documents.py`, with `down_revision` = the single head recorded in T108. It creates `race_import_staged_documents` exactly as in `data-model.md` §11.1, with no index beyond the primary key. It adds no enum value to any existing column. The downgrade drops the table.

  [agent: database-architect · sonnet]
- [ ] T115 Create the model `backend/app/models/race_import_staged_document.py` (`RaceImportStagedDocument`) and register it in `backend/app/models/__init__.py`. Do not add an implicitly loaded relationship on `RaceImport`; the loader selects by primary key, which avoids async lazy-load errors. Its docstring states the privacy class.

  [agent: database-architect · sonnet]
- [ ] T116 Implement `save(db, import_id, document, profile_meta)`, `load(db, imp) -> ParsedResults`, `delete(db, import_id)`, `StagedDocumentMissing` and the `document_to_json` / `document_from_json` helpers (`schema_version` 1) in `backend/app/services/race/staged_document.py`. The module docstring covers inputs, outputs and side effects: the rows hold minors' names and are never logged. T112 goes green.

  [agent: fastapi-architect · sonnet]
- [ ] T117 Gate G8 — foundations:
  - default lane green;
  - T111 run against a `_test` MySQL, or explicitly deferred here with the reason;
  - single Alembic head;
  - a lead's sign-off in `specs/044-race-history-backfill/tasks.md` with the date.

  [agent: engineering-lead · opus]

**Checkpoint**: Phases 13 and 14 can run in parallel.

---

## Phase 13: User Story 1 (amended) — the LLM reads a masked view; a tested engine reads the file (Priority: P1)

**Goal**: any organiser's layout is read by a reading profile applied locally, and the LLM only ever sees the masked layout view (FR-001, FR-002, FR-045, FR-046, SC-013).

**Independent Test**: builder files in the historical, 2026 and unruled layouts, plus synthetic CSVs:
- every masked view contains no fake name, club or city;
- `copa-valle-results-pdf` reproduces the retired parser's rows;
- the unruled layout is read completely with its own profile.

### Tests for User Story 1 (amended) ⚠️ write first

- [ ] T118 [P] [US1] Write `backend/tests/services/race/results_skill/test_vocabulary.py`. It pins:
  - every word of the `normalizer.HEADER_TO_CODE` keys, plus `CAT`, is present;
  - the column, document, roman-numeral and connector lists of `contracts/masked-view.md` are present;
  - no month or weekday name;
  - only `[A-Z0-9]` after accent folding;
  - no word longer than 14 letters.

  [agent: qa-engineer · sonnet]
- [ ] T119 [P] [US1] Write `backend/tests/services/race/results_skill/test_masking.py`, covering every case listed in `contracts/masked-view.md` § Tests:
  - no fake name, club or city in any layout;
  - every `WORD`, `INT` and `TIME` is masked in content lines;
  - `STATUS` stays verbatim, including the T024b lap-deficit variants;
  - glued tokens are split;
  - structural lines are verbatim, and a header with an unknown word renders as content;
  - a Hypothesis property with names equal to vocabulary words;
  - `leak_count` catches a vocabulary-only continuation line;
  - determinism;
  - refusals: no text layer, more than 8 MB, neither PDF nor UTF-8 delimited text.

  [agent: qa-engineer · sonnet]
- [ ] T120 [P] [US1] Port every case of `backend/tests/services/race/test_band_reader.py` to `backend/tests/services/race/results_skill/test_pdf_runs.py`: hand-built char dicts, stream order, a gap above `run_gap_pt`, a backwards x jump, an overprinted club.

  [agent: qa-engineer · sonnet]
- [ ] T121 [P] [US1] Write `backend/tests/services/race/results_skill/test_profile_schema.py` and `test_profiles_valid.py`.
  - Schema v1 accepts the contract example.
  - It rejects:
    - unknown keys;
    - `run_gap_pt` outside 0.3–5.0;
    - a `profile_id` that does not match `^[a-z0-9-]{3,64}$`;
    - a `description` longer than 120 characters;
    - non-vocabulary words in `category_aliases` keys or in `skip_structural_lines_starting_with`;
    - a missing required field (`position`, `name`, `club`, `time_or_status`).
  - Every file under `backend/race_reading_profiles/` and `backend/tests/fixtures/race_profiles/` validates.

  [agent: qa-engineer · sonnet]
- [ ] T122 [P] [US1] Generate the parity golden files **with the retired parser, before T153 deletes it**. Run `pdf_parser.parse_results_document` on builder output of the historical-overprint and 2026 layouts and write `backend/tests/fixtures/race/parity/{historical,2026}.json` (synthetic, fake names; sweep them with `assert_no_fake_names` against a non-generator list).

  Then write `backend/tests/services/race/results_skill/test_apply_profile.py`, asserting that `apply_profile(copa-valle-results-pdf)` equals the golden rows one by one. It also covers:
  - removed and duplicated ordinals;
  - an unknown header (`code` None, rows kept);
  - lap-deficit variants in `time_raw`;
  - a position with no time;
  - a category continuing across a page break;
  - rows before the first header ending up in `SIN CATEGORÍA`;
  - an unreadable band becoming `UnreadableRow(page, ordinal)`.

  [agent: qa-engineer · sonnet]
- [ ] T123 [P] [US1] Write `backend/tests/services/race/results_skill/test_apply_second_layout.py` and `test_apply_delimited.py`.
  - The unruled layout with `backend/tests/fixtures/race_profiles/fictional-unruled.json` (surname and given names in separate columns, a different column order) is recovered completely.
  - Delimited text covers a category column, separator rows, multi-column names, and the `;` and tab delimiters.

  [agent: qa-engineer · sonnet]

### Implementation for User Story 1 (amended)

- [ ] T124 [US1] Create the package `backend/app/services/race/results_skill/`:
  - `__init__.py` holds `ENGINE_VERSION = "1"` and a module docstring (never imported by a router);
  - `pdf_runs.py` receives the band and run primitives moved out of `pdf_parser.py` (content-stream order, run segmentation with `run_gap_pt`, start x, `find_tables` row bands, baseline bands for unruled layouts), with identical behaviour.

  `pdf_parser.py` imports them from the new module until T153. T120 goes green.

  [agent: data-analyst · sonnet]
- [ ] T125 [P] [US1] Implement `backend/app/services/race/results_skill/vocabulary.py`: a frozen set built from `normalizer.HEADER_TO_CODE` plus the fixed lists of `contracts/masked-view.md`. Its docstring explains the review rule for adding words. T118 goes green.

  [agent: data-analyst · sonnet]
- [ ] T126 [US1] Implement `backend/app/services/race/results_skill/masking.py`: `build_masked_view`, `render_masked_view` and `leak_count`, exactly as in `contracts/masked-view.md`.
  - Token classes and the glued-token split.
  - The structural-line rule.
  - PDF geometry through `pdf_runs` (start x per run, page width, ruling x).
  - Delimited-text rendering.
  - Refusals: text layer, 8 MB, magic bytes.

  The functions are pure, with no logging of content. T119 goes green.

  [agent: data-analyst · opus]
- [ ] T127 [P] [US1] Implement `backend/app/services/race/results_skill/profile.py`:
  - `ReadingProfile`, Pydantic v2 with `extra="forbid"`, schema v1 as in `contracts/reading-profile.md`, with validators: vocabulary-only words in aliases and skip lists, numeric ranges, `profile_id` pattern, required fields;
  - `load_profile(id_or_path)`;
  - `profile_sha256(path)`.

  T121's schema cases go green.

  [agent: data-analyst · sonnet]
- [ ] T128 [US1] Implement `apply_profile(file_bytes, results_ext, profile) -> ParsedResults` in `backend/app/services/race/results_skill/apply.py`, as in `contracts/reading-profile.md` § Engine.
  - PDF:
    - rows from `table_bands` or `baselines`;
    - start-x assignment of runs to columns;
    - the header rule, then aliases, then `normalizer.HEADER_TO_CODE`;
    - skip lines;
    - `SIN CATEGORÍA`;
    - unreadable rows.
  - Delimited text: column mapping, a category column or separator rows, multi-column names.

  The engine never parses times itself; `time_raw` is kept for `normalizer.parse_time`.

  [agent: data-analyst · opus]
- [ ] T129 [US1] Author two profiles **from the masked views of builder files only**:
  - `backend/race_reading_profiles/copa-valle-results-pdf.json`;
  - `backend/tests/fixtures/race_profiles/fictional-unruled.json`.

  Iterate until T121, T122 and T123 are green.

  [agent: data-analyst · sonnet]
- [ ] T130 [US1] Gate G9 — engine:
  - T118–T123 green;
  - golden and profile files swept, with no real names;
  - no module under `app/routers` imports `results_skill` (grep);
  - sign-off in `specs/044-race-history-backfill/tasks.md`.

  [agent: engineering-lead · opus]

**Checkpoint**: the engine reads every synthetic layout, and the masked view is proven clean.

---

## Phase 14: User Story 5 (amended) — review steps read the staged document; the server never re-reads a file (Priority: P1)

**Goal**: staged rows are persisted, and every review route reads them from the database. Legacy imports are handled, and GENERAL is retired (FR-048, FR-049, R-20, R-25, R-27).

**Independent Test**: stage a synthetic document through the service, with storage downloads monkeypatched to raise. Then:
- dry-run, corrections, acknowledge, commit, commit-pending and discard all work;
- the document is deleted on full commit, on commit-pending completion and on discard;
- a legacy import answers `409 restage_required`.

### Tests for User Story 5 — staged documents ⚠️ write first

- [ ] T131 [P] [US5] Rewrite `backend/tests/services/race/test_import_staging.py` for `stage_extracted_results`, following `contracts/staged-import.md` § Tests.
  - Dedupe, for a pending and for a committed import.
  - An empty document is refused (`empty_document`).
  - An upload failure leaves no import.
  - A transaction failure deletes the uploaded object and leaves neither an import nor a document.
  - `imported_at` comes from the database clock: freeze the Python clock and assert the value differs from it.
  - Public meta keys equal `_PUBLIC_PARSE_META_KEYS`, plus `results_ext`, `results_storage_path`, `parse_uuid`, `source`, `profile_id`.
  - `conditions` are all null, `n_rows_general == 0` and `kind == resultados`.
  - The audit row carries `meta.via == "results_skill"`.
  - A different reading of a committed válida is flagged `is_revision`.

  [agent: qa-engineer · sonnet]
- [ ] T132 [P] [US5] Write `backend/tests/helpers/staging.py::stage_for_test(db, document, header, actor, *, file_bytes=None, results_ext="pdf")`. It builds a synthetic document when none is given, calls `stage_extracted_results` with storage on the local fallback, and returns `StageResult`.

  [agent: qa-engineer · sonnet]
- [ ] T133 [P] [US5] Write `backend/tests/routers/test_race_imports_staged_rows.py`, with `storage_sftp.download_to_tempfile` monkeypatched to raise.
  - dry-run, corrections, acknowledge, commit and commit-pending succeed from the document.
  - The document is deleted on full commit, on commit-pending completion and on discard, and kept on a partial commit.

  [agent: qa-engineer · sonnet]
- [ ] T134 [P] [US5] Write `backend/tests/routers/test_race_imports_legacy.py`, for an import created without a document.
  - `409 {"detail": "restage_required", "import_id": …}` on dry-run, commit, corrections and acknowledge.
  - A committed import with `pending_categories` and no document gets the same 409 on commit-pending.
  - GET detail and discard still work.
  - `restage_required` is true on detail and list, and false for a staged import. The list is checked with a statement-count assertion (no N+1).
  - The identity rebuild reports the import as unreadable.

  [agent: qa-engineer · sonnet]
- [ ] T135 [US5] Port the first batch from HTTP `/parse` to `stage_for_test`:
  - `backend/tests/routers/test_race_imports.py`
  - `test_race_imports_revision.py`
  - `test_race_series_014.py`
  - `backend/tests/test_race_imports_series_level.py`
  - `backend/tests/test_audit_race_results.py`

  Keep every assertion that is not about upload mechanics. Delete the tests of size cap, magic bytes, timeout, 410 re-upload and download, and list each one by name in the commit body.

  [agent: qa-engineer · sonnet]
- [ ] T136 [US5] Port the second batch:
  - `backend/tests/routers/test_race_imports_club_scope.py`
  - root `backend/tests/test_race_imports_club_scope.py`: replace the "dry-run hits a missing file" trick with a real staged document
  - `test_race_imports_integrity.py`
  - `test_race_imports_history.py`: drop the cache no-redownload test and the file path of the direct `load_identity_rows` call
  - `test_race_imports_identity_gate.py`: drop `GeneralRow`
  - `backend/tests/services/race/identity_support.py`

  [agent: qa-engineer · sonnet]

### Implementation for User Story 5 — staged documents

- [ ] T137 [US5] Implement `stage_extracted_results` in `backend/app/services/race/import_staging.py`, following steps 1–6 of `contracts/staged-import.md`.
  - Reuse `_get_or_create_series`, `_categories_read` and `detect_revision`.
  - Upload the evidence to `race-imports/pending/{parse_uuid}/resultados.{ext}`.
  - Write one transaction with the import, the document and the audit `create`.
  - Take `imported_at` from `func.now()`.
  - On failure, delete the uploaded object best-effort.
  - Return `StageResult`.

  Keep `stage_results_file` until T152. T131 goes green.

  [agent: fastapi-architect · sonnet]
- [ ] T138 [US5] In `backend/app/routers/race_imports.py`, replace `_reload_results_document`, `_reload_parsed_from_storage`, `_RAW_PARSE_CACHE`, `_CORRECTED_CATEGORIES_CACHE`, `_lru_get`/`_lru_put` and `clear_parsed_rows_caches` with `staged_document.load`.
  - Corrections and acknowledge validate against the loaded rows.
  - Dry-run, commit and commit-pending build `{code: rows}`, `category_headers_raw` and `categories` from the document.
  - Remove the "release the connection before SFTP" commits (around lines 1021, 1129, 1296, 1570, 1767 and 1859, and `identity_review.py:778`).
  - Map `StagedDocumentMissing` → `409 {"detail": "restage_required", "import_id": id}`.
  - Delete the document on full commit, on commit-pending completion and on discard.
  - Remove the cache-clear autouse fixture from `backend/tests/conftest.py`.

  T133 and T134 go green (all but the list flag).

  [agent: fastapi-architect · opus]
- [ ] T139 [US5] Make `load_identity_rows` (`backend/app/routers/race_imports.py`) and `load_universe` (`backend/app/services/race/identity_review.py`) read the staged document. A legacy import is reported as unreadable, as unreadable files are today. Remove the GENERAL rows handling (`GENERAL_VALIDA_NUM`); the `kind=general` skip stays for legacy rows.

  [agent: fastapi-architect · sonnet]
- [ ] T140 [US5] Add `restage_required: bool` to `ImportDetailRead` and `ImportListItem` (`backend/app/schemas/race_imports.py`). Compute it in `GET /{id}` and `GET /` with one batched `EXISTS` per page. It is true for `pending` with no document, and for committed with `pending_categories` and no document. T134 goes fully green.

  [agent: fastapi-architect · sonnet]
- [ ] T141 [US5] Retire GENERAL in `backend/app/services/race/ingestor.py`:
  - remove the "GENERAL first" step (`_upsert_competitor_from_general`), the `general_by_category` parameter and the unused `pdf_general_sha256`;
  - adjust callers and the `test_ingestor*.py` cases that fed GENERAL rows;
  - keep `RaceImportKind.general` and `both` for legacy rows.

  [agent: fastapi-architect · sonnet]
- [ ] T142 [US5] Gate G10 — review API on documents:
  - T131–T136 green;
  - `grep -rn "download_to_tempfile" backend/app/routers/race_imports.py backend/app/services/race/identity_review.py` finds nothing;
  - finding A of the privacy audit is ready to close in T184;
  - sign-off in `specs/044-race-history-backfill/tasks.md`.

  [agent: engineering-lead · opus]

---

## Phase 15: User Story 5 (amended) — one CLI stages the válida, local first (Priority: P1)

**Goal**: `python -m scripts.race_results` masks, applies, compares and stages. It is local by default, production only when explicit, and never prints rider data (FR-045, FR-047, FR-048, FR-049).

**Independent Test**: the CLI suite on aiosqlite, with fake env files in a tmp dir and no network.

### Tests for User Story 5 — CLI ⚠️ write first

- [ ] T143 [P] [US5] Write `backend/tests/scripts/test_race_results_cli.py`, following `contracts/results-skill-cli.md` § Tests.
  - The happy path `mask` → `profile-check` → `apply` → `stage`.
  - The local guard.
  - The production guard: missing `--confirm`, missing SFTP, head mismatch.
  - Actor refusals: unknown, inactive, parent, athlete.
  - Duplicates: the same file staged twice gives one import; a committed same file exits 8.
  - A revision exits 12 while T175 is pending.
  - `--dry` changes no race table count.
  - A file inside the repository and a scanned PDF are refused.
  - Every exit code of the contract.
  - `assert_no_fake_names` over stdout, stderr and `report.json` of every subcommand.

  [agent: qa-engineer · sonnet]
- [ ] T144 [P] [US5] Write `backend/tests/services/race/results_skill/test_target.py` for `resolve_target`.
  - Local allow-list hosts: `localhost`, `127.0.0.1`, `::1`, `mysql`, `host.docker.internal`.
  - `APP_ENV=production` refused.
  - A `(MYSQL_HOST, MYSQL_DB)` pair equal to `.env.production` refused.
  - Production requires `--confirm produccion`.
  - Incomplete SFTP refused.
  - An `alembic_version` mismatch refused (fake version table).
  - `scrub()` replaces every loaded value.

  [agent: qa-engineer · sonnet]

### Implementation for User Story 5 — CLI

- [ ] T145 [US5] Implement `backend/app/services/race/results_skill/target.py`:
  - `resolve_target(target, confirm, env_dir)`;
  - production keys loaded from `backend/.env.production` before `app.*` is imported: only `MYSQL_*`, `HOSTINGER_SFTP_*` and `HOSTINGER_PUBLIC_BASE_URL`, and set `APP_ENV=development`, `AI_ENABLED=false`, `STRAVA_ENABLED=false`;
  - the local allow-list, and the pair comparison without printing;
  - the SFTP completeness check;
  - `alembic_version` against the repository head (`ScriptDirectory`);
  - `scrub(text)`.

  T144 goes green.

  [agent: devops-engineer · opus]
- [ ] T146 [US5] Create `backend/scripts/race_results.py` with argparse subcommands `mask`, `profile-check`, `apply`, `compare` and `stage`.
  - The run folder is `output/race-results/<YYYYMMDD-HHMMSS>-<sha8>/{masked,private}/`, plus `report.json`.
  - Refuse paths inside the repository, reusing `_find_repo_root` and `_assert_outside_repo` from the retired script.
  - Exit codes exactly as in the contract (0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12).
  - Operator messages in Spanish.
  - Stdout discipline: never a name, club, city, bib, time or points value. Exceptions become class name plus code.

  [agent: fastapi-architect · sonnet]
- [ ] T147 [US5] Wire `stage` in `backend/scripts/race_results.py`.
  - Manifest validation:
    - the explicit form: `series_name`, `series_kind`, `series_level`, `season`, `valida_num`, `event_name`, `event_date` as an ISO date, `location`;
    - or `{"race_event_id": N}`, resolved from `RaceEvent` plus `RaceSeries` in the target;
    - unknown keys refused, and no conditions.
  - The actor must be an active `admin` or `coach` (the `_load_actor` semantics).
  - Call `stage_extracted_results` with the profile id, hash and engine version.
  - `--dry`.
  - The `revision_not_available` guard (exit 12), a module constant that T175 turns off.
  - Print the review path `/competitions/import?import=<id>`.

  [agent: fastapi-architect · sonnet]
- [ ] T148 [US5] Implement `compare` in `backend/scripts/race_results.py`:
  - a read-only session: `SET TRANSACTION READ ONLY` on MySQL, and always `rollback()`;
  - per-category matched, changed, missing and extra counts against the válida's committed, non-deleted results;
  - exit 7 when the válida is not found.

  [agent: fastapi-architect · sonnet]
- [ ] T149 [US5] Handle the evidence file in `stage`:
  - magic bytes: `%PDF-`, or UTF-8 plus a delimiter;
  - an 8 MB cap constant;
  - `storage_sftp.upload_bytes`;
  - a best-effort delete on failure: add `storage_sftp.delete_object` if missing, with tests in `backend/tests/services/race/test_storage_race_uploads.py`;
  - production refuses the local fallback.

  [agent: integration-engineer · sonnet]
- [ ] T150 [US5] Gate G11 — CLI:
  - T143 and T144 green;
  - quickstart §9.4 run once on the local docker stack with a builder file; record the counts only;
  - sign-off in `specs/044-race-history-backfill/tasks.md`.

  [agent: engineering-lead · opus]

---

## Phase 16: User Story 5 (amended) — no results upload remains (Priority: P1)

**Goal**: no endpoint or backend script accepts a results file, and the fixed parsers and the real fixtures are gone (FR-044, SC-014, R-26, R-28).

**Independent Test**: `test_no_results_upload.py` (allow-list, denied path for four roles, engine not imported by routers).

- [ ] T151 [P] [US5] Write `backend/tests/privacy/test_no_results_upload.py`, following `contracts/staged-import.md` § Structural guards:
  - the file-parameter allow-list has exactly four entries;
  - a multipart POST to `/api/race-analysis/imports/parse` returns 404 or 405 for admin, coach, parent and athlete;
  - no router imports `app.services.race.results_skill`.

  [agent: qa-engineer · sonnet]
- [ ] T152 [US5] Delete, in `backend/app/routers/race_imports.py`:
  - `POST /parse` (`parse_import`);
  - `_is_pdf`, `_is_csv_like`, `_read_with_cap`, `_validate_results_magic`, `_validate_general_magic`, `_sanitize_filename`, `_compute_sha256`;
  - the upload constants, the `File`/`Form`/`UploadFile` imports, and the upload parts of the module docstring.

  In `import_staging.py`, delete `stage_results_file`, `_response_for_already_staged`, `_parse_results_with_timeout` and `_parse_general_with_timeout`.

  Remove `("POST", "/api/race-analysis/imports/parse")` from the registry in `backend/app/services/audit.py`; `tests/test_audit_coverage.py` stays green.

  [agent: fastapi-architect · sonnet]
- [ ] T153 [US5] Delete the fixed parsers and their tests.
  - Delete `backend/app/services/race/pdf_parser.py` and `csv_parser.py`, including the temporary re-exports.
  - Delete `test_parser.py`, `test_parser_edge_cases.py`, `test_parser_historical_layout.py`, `test_parser_time_variants.py`, `test_band_reader.py` (ported in T120) and `test_csv_parser.py`. In the commit body, list what each covered and where that coverage now lives (T120, T122, T123).
  - Move the four `test_ingestor.py` cases that read real fixtures to builder output.
  - Update the mutmut entries in `backend/pyproject.toml`.

  [agent: fastapi-architect · sonnet]
- [ ] T154 [US5] Remove `race_max_pdf_mb`, `race_parse_timeout_seconds` and `race_pending_ttl_hours` from `backend/app/config.py` and `.env.example`. Delete `backend/scripts/stage_race_history.py` and `backend/tests/scripts/test_stage_race_history.py`.

  [agent: fastapi-architect · sonnet]
- [ ] T155 [US5] Once `grep -rn valida_iv_2026 backend/` finds only the fixtures themselves:
  - delete the real official files `backend/tests/fixtures/race/valida_iv_2026_resultados.pdf` and `valida_iv_2026_general.pdf`;
  - update `backend/tests/services/race/conftest.py`;
  - record in `privacy-audit.md` that both files remain in git history and that purging them is an owner decision. No history rewrite is performed.

  [agent: data-privacy-guard · sonnet]
- [ ] T156 [US5] Gate G12 — removal:
  - `pytest -q` and `ruff check` green;
  - `grep -rn "pdf_parser\|csv_parser\|imports/parse" backend/app` finds nothing;
  - T151 green;
  - sign-off in `specs/044-race-history-backfill/tasks.md`.

  [agent: engineering-lead · opus]

---

## Phase 17: User Story 5 (amended) — the web app reviews and commits, never uploads (Priority: P1)

**Goal**: the coach reviews staged imports in the existing screens, with no upload anywhere (FR-044, FR-048, SC-014, `contracts/ui-review-only.md`). **Ships in the same deploy as Phase 16.**

**Independent Test**:
- `noResultsUpload.test.tsx` passes;
- the ported wizard suites start from `?import=<id>`;
- the e2e stages through the CLI.

### Tests for User Story 5 — web ⚠️ write first

- [ ] T157 [P] [US5] Write `frontend/src/components/competitions/__tests__/noResultsUpload.test.tsx`. Render the review page, the board, the competitions list and detail, and the results tab. Assert there is no `input[type=file]` and no «Cargar resultados», «Importar resultados» or «Cargar archivo».

  [agent: qa-engineer · sonnet]
- [ ] T158 [P] [US5] Write `frontend/src/components/competitions/imports/__tests__/ResumeStatusNotice.legacy.test.tsx`:
  - `restage_required` true, or a 409 `restage_required`, shows the legacy notice with only *Descartar*;
  - a board row shows the «Preparar de nuevo» badge;
  - jest-axe reports zero violations.

  [agent: qa-engineer · sonnet]
- [ ] T159 [P] [US5] Port the wizard suites to start from `?import=<id>` with MSW: extend `frontend/src/test/msw/raceImportsHistoryHandlers.ts` with detail and dry-run handlers, following the `ImportWizard.resume.test.tsx` pattern.
  - `ImportWizard.test.tsx`: steps 2–3, matches, one 409 message per code (`already_committed`, `restage_required`).
  - `ImportWizard.categories.test.tsx`
  - `ImportWizard.postimport.test.tsx`
  - the upload-only case of `ImportWizard.resume.test.tsx`

  [agent: qa-engineer · sonnet]
- [ ] T160 [P] [US5] Update the entry-point tests: `CompetitionsListPage.test.tsx`, `ResultsTable.test.tsx`, `EventForm.race-event-id.test.tsx`, `CompetitionImportPage.test.tsx`, `navigation.test.ts`, `competitionsRedirects.test.tsx` (no `?import` goes to the board; `?import` still routes), `LoadsSection.test.tsx` and `CompetitionImportsPage.test.tsx`.

  Delete `RaceUploadZone.test.tsx`, `api/__tests__/raceImports.conditions.test.ts`, the `useImportParse` cases in `useRaceImports.test.tsx`, `ImportWizard.{prefill,locked,championship,standalone,conditions}.test.tsx`, and the step-1 parts of `ImportWizard.014.test.tsx`.

  [agent: qa-engineer · sonnet]

### Implementation for User Story 5 — web

- [ ] T161 [US5] Remove step 1 from `frontend/src/components/competitions/import/ImportWizard.tsx`, as in the contract.
  - `STEPS` becomes «Revisar carga», «Resultado».
  - Delete `step1Schema` and its `useForm`, the prefill blocks and wiring, the metadata and conditions sections, the upload zones, `submitStep1` and the file state.
  - *Volver*, `reset()`, *Empezar una carga nueva*, *Cargar otro* and a successful discard all navigate to `/competitions/imports?seccion=cargas`.

  [agent: react-ui-engineer · sonnet]
- [ ] T162 [US5] Delete:
  - `frontend/src/components/competitions/import/RaceUploadZone.tsx`;
  - `parseRaceImport` (`src/api/raceImports.ts`);
  - `useImportParse` and `UseImportParseVariables` (`src/hooks/ai/useRaceImports.ts`);
  - `ImportParseRequestFields` and `ImportPrefill*` (`src/types/raceImports.types.ts`); keep `ImportParseResponse`;
  - `src/hooks/race/useImportPrefill.ts`;
  - `VITE_RACE_MAX_PDF_MB` (`src/vite-env.d.ts`).

  Add `restage_required` to the list and detail types.

  [agent: react-ui-engineer · sonnet]
- [ ] T163 [US5] In `frontend/src/App.tsx`, redirect `/competitions/import` and `/competitions/:id/import` without `?import` to `/competitions/imports?seccion=cargas`; with `?import` they render the review. Set the review copy in `routes/competitions/CompetitionImportPage.tsx`: «Revisar carga de resultados» / «Revisa la lectura, resuelve lo pendiente y confirma.».

  [agent: react-ui-engineer · sonnet]
- [ ] T164 [US5] Change the entry points as in the contract table: `CompetitionsListPage.tsx`, `CompetitionDetailPage.tsx`, `tabs/ResultsTab.tsx` (copy plus «Ir a Cargas»), `imports/LoadsSection.tsx` (no «Cargar archivo»; «Revisar la carga»; the legacy badge with only *Descartar*) and `calendar/EventForm.tsx`. Add the legacy state to `imports/ResumeStatusNotice.tsx`.

  [agent: react-ui-engineer · sonnet]
- [ ] T165 [US5] Sweep the copy using the contract's copy table:
  - `DiscardImportDialog.tsx`;
  - the `DiffTable.tsx` aria-label;
  - the per-code 409 messages in `ImportWizard.tsx`;
  - «Confirmar carga» and «Carga confirmada»;
  - the loading fallbacks in `App.tsx` and `CompetitionImportPage.tsx`;
  - the board's description and empty state;
  - the results-tab empty state;
  - the calendar hint.

  Everything is in español neutro with full diacritics.

  [agent: react-ui-engineer · sonnet]
- [ ] T166 [US5] Review the new copy, the legacy state and the redirects on the coach's tablet, against the Nielsen heuristics and the no-dead-entry-point rule. Record the review as a new section of `specs/044-race-history-backfill/ux-review.md`.

  [agent: ux-researcher · sonnet]
- [ ] T167 [US5] Update the Playwright specs.
  - `frontend/e2e/race-history.spec.ts`: stage the builder files with `python -m scripts.race_results` (`mask` → `apply` with the test profile → `stage --target local`) against the e2e stack's database instead of `setInputFiles`. Everything after staging stays unchanged.
  - Delete `e2e/prefill-import-from-competition.spec.ts`.
  - `e2e/cup-vs-championship.spec.ts` E2E-014-006: assert the staged level in the review header.
  - Update the skipped test's comment in `e2e/competitions-unification.spec.ts`.

  [agent: qa-engineer · sonnet]
- [ ] T168 [US5] Gate G13 — web:
  - `npm run typecheck`, `npm run build` and `npm test` green;
  - T167 run on the isolated stack, or explicitly deferred with the reason;
  - Phases 16 and 17 confirmed to ship together;
  - sign-off in `specs/044-race-history-backfill/tasks.md`.

  [agent: engineering-lead · opus]

**Checkpoint (amendment MVP)**: Phases 11–17 + 19 give skill-only loading end to end for first loads. Revisions are refused with exit 12 until Phase 18.

---

## Phase 18: User Story 5 (amended) — corrections are real revisions (Priority: P2 within the amendment; deferrable)

**Goal**: a different reading of a committed válida is reviewed as a diff and applied as a whole with a reason. Athlete links survive, and removed results disappear from every read (FR-027 corrected, SC-006, `contracts/revision-via-skill.md`).

**Independent Test**: commit a synthetic válida, then stage an edited reading (one time changed, one row removed, one row added).
- The dry-run shows 1 update, 1 delete and 1 create.
- A commit without a reason gets 422.
- A commit with a reason applies the three changes with `race_result_revisions` rows.
- The removed row disappears from `history`, `field_metrics`, `standings` and the family views.

### Tests for User Story 5 — revisions ⚠️ write first

- [ ] T169 [P] [US5] Write `backend/tests/services/race/test_revision_diff_identity.py`:
  - two same-name competitors in one category (decided "different people") are diffed separately;
  - a surname correction resolves through the fuzzy fallback with `fuzzy_matched: true`;
  - a club athlete's fuzzy candidate stays `create`;
  - a category move yields `delete` plus `create`;
  - `unchanged` rows are counted but omitted from `diff_rows`.

  [agent: qa-engineer · sonnet]
- [ ] T170 [P] [US5] Extend `backend/tests/routers/test_race_imports_revision.py`:
  - dry-run returns the `ImportDryRunRevisionResponse` shape;
  - commit without `revision_reason` gets 422;
  - `409 revision_incomplete` when a category is inconsistent;
  - `409 event_locked` when the event is locked;
  - an identity-gate 409 on a revision with a new name;
  - the applied update, create and delete, with `race_result_revisions` rows;
  - `parent_import_id` is set;
  - an athlete link survives;
  - `invalidate_runs_for_event` is called;
  - the staged document is deleted.

  [agent: qa-engineer · sonnet]
- [ ] T171 [P] [US5] Write `backend/tests/services/race/test_deleted_results_excluded.py`. After a revision soft-deletes one result, it is absent from `history`, `field_metrics` / `compute_category_metrics`, `standings`, `results_read` (coach and family), the analyst context (`queries.py`), the season panorama and the family results views.

  [agent: qa-engineer · sonnet]
- [ ] T172 [P] [US5] Port `frontend/src/components/competitions/import/__tests__/DiffConfirm.test.tsx` to the real revision dry-run shape through MSW: the diff table renders, the reason is required, and the commit payload carries `revision_reason`.

  [agent: qa-engineer · sonnet]

### Implementation for User Story 5 — revisions

- [ ] T173 [US5] Adapt `revision.compute_diff` in `backend/app/services/race/revision.py`.
  - Resolve each row through the read-only path of `identity_resolver` (signature plus the discriminator of R-06 §9–10), and diff by `(category_code, competitor_id)`.
  - Keep the fuzzy `partial_ratio ≥ 92` fallback only for rows that resolve to "new", flagged `fuzzy_matched: true`. It never auto-matches a club athlete.
  - Count `unchanged` rows but omit them from the rows returned.

  T169 goes green.

  [agent: data-analyst · opus]
- [ ] T174 [US5] Wire the revision branch in `backend/app/routers/race_imports.py`, as in `contracts/revision-via-skill.md`.
  - **Dry-run** returns the new `ImportDryRunRevisionResponse` schema (`backend/app/schemas/race_imports.py`, mirroring the frontend type).
  - **Commit**:
    1. `revision_reason` is mandatory (422).
    2. The per-import identity gate runs.
    3. `revision_incomplete` 409 when a category is not consistent.
    4. The diff is recomputed server-side.
    5. `commit_revision` applies it, with creations through the ingestor's resolver, signature writing and frozen labels.
    6. `parent_import_id`, `revision_reason` and `committed_*` are set.
    7. The document is deleted and the evidence moved.
    8. `invalidate_runs_for_event` runs.
    9. The audit records counts only.
  - Widen `commit_revision`'s reason rule to every revision.

  T170, T171 and T172 go green.

  [agent: fastapi-architect · opus]
- [ ] T175 [US5] Turn off the `revision_not_available` guard in `backend/scripts/race_results.py`, and change T143's revision case to expect a staged revision (exit 0 and the `revisión de la importación #N` line).

  [agent: fastapi-architect · sonnet]
- [ ] T176 [US5] Gate G14 — revisions:
  - T169–T172 and T143 green;
  - the read sweep green;
  - one legacy partial commit completed through a revision on the local stack, with a builder file;
  - sign-off in `specs/044-race-history-backfill/tasks.md`.

  [agent: engineering-lead · opus]

---

## Phase 19: The skill and the session guardrails

**Purpose**: the operator's procedure, written for the LLM, with its guardrails (R-29, `contracts/results-skill-cli.md` § Skill procedure).

- [ ] T177 [P] Write the skill in English:
  - `.claude/skills/race-results-load/SKILL.md`:
    - the eight rules of the contract;
    - the prerequisites;
    - the local-first loop;
    - the production-only-on-request rule;
    - the report format;
    - a trigger description in Spanish and English.
  - `references/masked-view.md`: how to read the geometry, and what never to ask.
  - `references/reading-profile.md`: schema v1 with a worked example built on a builder file's masked view (fake names only).
  - `references/manifest.md`: both forms, with placeholders.

  [agent: data-analyst · opus]
- [ ] T178 [P] Add `permissions.deny` for `Read(./output/race-results/**/private/**)` to `.claude/settings.json`, checking the exact rule syntax against the current Claude Code documentation (the `update-config` skill). Document in `SKILL.md` the optional local deny rule for the operator's official-files folder. Confirm that `output/` is still git-ignored.

  [agent: devops-engineer · sonnet]
- [ ] T179 Review the skill, its references, the deny rules and the vocabulary against FR-046 / SC-013 and the CLAUDE.md hard rules. Record the findings in `specs/044-race-history-backfill/privacy-audit.md` §4 (new).

  [agent: data-privacy-guard · sonnet]
- [ ] T180 Review T179, then sign the skill as usable on real files, or list the blockers, in `privacy-audit.md` §4. **No real official file is masked before this sign-off.**

  [agent: data-platform-lead · opus]

---

## Phase 20: Polish & cross-cutting (amendment)

- [ ] T181 [P] Update `docs/10-race-results/runbook-ops.md`:
  - §12.1: the pre-deploy legacy count (quickstart §9.6 step 1) and the new migration;
  - §12.2: the CLI's target guard replaces the reminder about a local backend pointed at production;
  - §12.3: rewritten for the skill, local first and production only when explicit;
  - §12.7: staged documents and revisions;
  - §1.2: the Hostinger remote-MySQL allow-list for the operator's IP.

  [agent: technical-writer · sonnet]
- [ ] T182 [P] Documentation:
  - an addendum to `docs/10-race-results/history-backfill-design.md` summarising R-17…R-31;
  - "superseded" banners on `docs/10-race-results/upload-design.md` and `upload-workflow.md`;
  - a minimal correction of the race-results bullet in `CLAUDE.md`: loading is done by the results skill; the web app reviews and commits; there is no upload endpoint. No history in that file.

  [agent: technical-writer · sonnet]
- [ ] T183 [P] Add the amendment's step table to `docs/implementation-status.md` and a dated entry to `docs/technical-notes.md`.

  [agent: technical-writer · sonnet]
- [ ] T184 Run the mandatory privacy audit of the amendment: engine and vocabulary, CLI and its output, staged documents, router deltas, revision wiring, frontend deltas and deleted fixtures. Record the verdict in `privacy-audit.md` §4 and close finding A of §2.

  [agent: data-privacy-guard · sonnet]
- [ ] T185 Review T184's verdict and record it in `privacy-audit.md` §5.

  [agent: data-platform-lead · opus]
- [ ] T186 Run `pytest -m mysql backend/tests/mysql/test_race_import_staged_documents.py` (T111 and the migration round-trip) against a `_test` database, and record the result in `docs/implementation-status.md`, or state explicitly there that it was not run and why.

  [agent: qa-engineer · sonnet]
- [ ] T187 Run the full offline gates: backend `pytest -q` and `ruff check`; frontend `npm run typecheck`, `npm run build` and `npm test`. Compare lazy-chunk sizes of the competitions routes before and after; they must not grow. Record `pytest -m golden` as not affected (no prompt or pipeline change), as in T088. Write every result in `docs/implementation-status.md`.

  [agent: qa-engineer · sonnet]
- [ ] T188 Pre-deploy checklist:
  - single head;
  - backup;
  - legacy count;
  - migration timing;
  - Phases 16 and 17 in one deploy;
  - obsolete `RACE_*` variables noted for removal in Render.

  Post-deploy smoke:
  - `/health`;
  - one authenticated endpoint;
  - `GET /api/race-analysis/imports/` lists with `restage_required`;
  - `POST /api/race-analysis/imports/parse` answers 404 or 405.

  [agent: release-manager · sonnet]
- [ ] T189 Final acceptance on the deployed build against FR-044…FR-049, corrected FR-027, SC-006, SC-013 and SC-014, together with the SC items still open from T104. List every unverified criterion with its owner in `specs/044-race-history-backfill/tasks.md`.

  [agent: product-manager · opus]

### Owner-only steps (no agent — real data, real people)

- [ ] T190 Before the deploy, run the legacy count (`specs/044-race-history-backfill/quickstart.md` §9.6 step 1) and decide, for each open import, whether to discard it or re-stage it after the deploy.
- [ ] T191 After T180 and T185, prepare each historical válida locally with the skill (`.claude/skills/race-results-load/SKILL.md`): the official file stays outside the repository; `mask` → profile → `apply` → `stage` locally → review and commit in the local app → spot-check.
- [ ] T192 On an explicit decision, stage in production with `--target production --confirm produccion`, season by season, oldest first. The coach resolves pending categories and the identity review and commits in the production app. Then:
  - spot-check three club athletes against the official files;
  - publish the privacy-notice version, set `RACE_HISTORY_FAMILY_POLICY_VERSION`, and re-check a parent account (`docs/10-race-results/runbook-ops.md` §12.6).

---

## Dependencies & Execution Order (amendment)

### Phase dependencies

- **Setup (11)** → **Foundational (12)** → Phases 13 and 14, which are independent and can run in parallel.
- **CLI (15)** needs 13 (engine) and 14 (staging service).
- **Removal (16)** needs:
  - 14, because the tests are ported first;
  - T122, because the golden files are generated before the parser is deleted;
  - 15, because the skill must exist before the upload goes.
- **Web (17)**: component work can start after 12. T167 (e2e) needs 15. **16 and 17 ship in one deploy.**
- **Revisions (18)** need 14; T175 needs 15. The phase is deferrable (hard ordering rule 3).
- **Skill (19)** needs 15.
- **Polish (20)** needs everything that ships. The owner steps T190–T192 need T188, T180 and T185.

### Same-file serialisation (never parallel)

- `backend/app/routers/race_imports.py`: T138 → T140 → T152 → T174
- `backend/app/services/race/import_staging.py`: T137 → T152
- `backend/app/services/race/pdf_parser.py`: T113 → T124 → T153 (deleted)
- `backend/app/services/race/identity_review.py`: T138 → T139
- `backend/app/services/race/ingestor.py`: T141 → T174
- `backend/app/services/race/revision.py`: T173 → T174
- `backend/scripts/race_results.py`: T146 → T147 → T148 → T175
- `backend/tests/routers/test_race_imports_revision.py`: T135 → T170
- `backend/tests/scripts/test_race_results_cli.py`: T143 → T175
- `frontend/src/components/competitions/import/ImportWizard.tsx`: T161 → T165
- `frontend/src/components/competitions/imports/LoadsSection.tsx`: T164 → T165

### Parallel example: after gate G8

```text
Track A (US1 engine): qa-engineer·sonnet T118 T119 T120 T121 T122 T123 → data-analyst·sonnet T124 T125 T127
                      → data-analyst·opus T126 T128 → data-analyst·sonnet T129 → G9 (T130)
Track B (US5 staging): qa-engineer·sonnet T131 T132 T133 T134 → fastapi-architect·sonnet T137
                      → fastapi-architect·opus T138 → fastapi-architect·sonnet T139 T140 T141 → qa-engineer·sonnet T135 T136 → G10 (T142)
Track C (US5 web, components only): qa-engineer·sonnet T157 T158 T159 T160 → react-ui-engineer·sonnet T161 … T165
```

## Implementation Strategy (amendment)

1. **Amendment MVP**: Phases 11–17, plus 19, deployed together with 16 and 17 in one release. The result is skill-only loading end to end: the LLM sees only masked views, local is the default, production requires an explicit request, and the coach reviews and commits in the app. A different reading of a committed válida is refused with a clear message.
2. **Revisions (18)**: needed before any correction of a committed válida, and to complete legacy partial commits.
3. **Real load (owner, T190–T192)**: only after the skill is signed (T180) and the audit reviewed (T185).

**Waves** (owner preference: work in waves, pause at 80 % of session usage):
- **W6**: Phases 11–12.
- **W7**: Phases 13 and 14 in parallel.
- **W8**: Phase 15, T151, and Phase 17 component work.
- **W9**: Phase 16 implementation, T167, and Phase 18.
- **W10**: Phases 19–20.

Opus is spent on 18 tasks. If the session budget is tight, only T177 may fall back to sonnet, because T179 and T180 review it anyway. **Never** T126, T128, T138, T145, T173 or T174.

## Notes (amendment)

- Wherever an open task of Phases 1–10 (T099, T100, T104) says "stage", it means the results skill since 2026-09-26.
- Commit after each task or logical group. Use Conventional Commits, with the type in English and the description in español latino, and no mention of AI tooling.
- Stop at every gate; a lead signs it in this file with the date.
