# Tasks: Guided anthropometric capture (weight, standing height, sitting height, arm span)

**Input**: Design documents from `specs/048-anthropometry-capture-ux/` (plan.md, spec.md, research.md R1–R12, data-model.md, contracts/api.md, contracts/ui.md, quickstart.md)

**Tests**: Required. Constitution Principle II is NON-NEGOTIABLE: every route needs allowed-path and denied-path tests, frontend changes need vitest + jest-axe, and minors' data needs privacy invariants. The owner also asked for **local e2e on the isolated stack**.

**Branch**: `main`. No auto-commits, and no `git stash` / `git clean` by subagents (see memory «Subagentes sin git stash»).

## Format: `[ID] [P?] [Story] Description — agent · model`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task).
- **[Story]**: US1–US5 from spec.md.
- **agent · model** is the project subagent (`.claude/agents/`) to delegate to, plus the model to pass as the Agent `model` override:
  - **opus**: delicate logic or design (derivation extraction, plausibility engine, permissions/audit/privacy, capture and session orchestration).
  - **sonnet**: mechanical or well-bounded work (schemas, API clients, simple components, tests, docs).
  - **orchestrator**: done by the main session itself. This covers the illustrations in Chrome, the owner-approval gates and running the e2e stack.
- **Test-lane commands**: `python -m pytest` from `backend/` with the venv active (WeasyPrint needs `DYLD_FALLBACK_LIBRARY_PATH`), and `npx vitest run <path>` from `frontend/`.

---

## Phase 1: Setup (shared assets and texts)

**Purpose**: the texts and illustrations that US2 and US5 consume. T002–T006 run in the owner's Chrome session, not in a subagent (research R11).

- [X] T001 [P] Create `backend/app/data/anthropometry_measures.json`:
  - Content: `{"precheck": [5 condition strings], "measures": [{key, label, donde, como, alt}] }` for keys `weight`, `standing_height`, `sitting_height`, `arm_span`.
  - Language: español neutro with full diacritics.
  - Pre-check strings: exactly «Sin zapatos», «Ropa liviana», «A una hora parecida a la de la última medición», «Antes de entrenar», «Báscula y tallímetro en superficie plana» (contracts/ui.md).
  - Standing height: include the Frankfort plane and heels/buttocks/back contact.
  - Sitting height: include «resta la altura del banco».
  - Arm span: mark it as optional.
  - Neutral, non-clinical wording; no athlete data.
  - Agent: fastapi-architect · sonnet
- [X] T002 Load the Claude in Chrome tools and open a new tab on Gemini or ChatGPT in the owner's logged-in browser. Confirm with the owner which tool to use. — orchestrator
- [X] T003 Generate `weight` and `standing_height`, one at a time:
  - Upload `frontend/src/assets/skinfolds/triceps.webp` as the style reference.
  - Use the style block and subject prompts from quickstart.md §4. No athlete data in any prompt.
  - Download each result.
  - Stop after 3 failed attempts on one image and ask the owner.
  - Agent: orchestrator
- [X] T004 Generate `sitting_height`, `arm_span` and (optional) `precheck` the same way as T003. — orchestrator
- [X] T005 Show each image to the owner and get explicit approval. Reject any image with faces, text, a recognizable person or a style mismatch. — orchestrator
- [X] T006 Post-process the approved images (done 2026-09-29 with Gemini; `precheck.webp` intentionally skipped — optional, CapturePrecheckStep renders without it):
  - `cwebp -q 82 -resize 768 768` → `frontend/src/assets/anthropometry/{weight,standing_height,sitting_height,arm_span,precheck}.webp`
  - Pillow (backend venv) → `backend/templates/documents/pdf/diagrams/img/anthro_{weight,standing_height,sitting_height,arm_span}.png`, at the same pixel size as the existing `skinfold_*.png`.
  - Agent: orchestrator

**Checkpoint**: approved assets are on disk, and the text JSON exists.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the derivation service, shared validation, the permission helper and the frontend base (API types, Zod, route shells). ⚠️ No user-story work starts before this phase is green.

- [X] T007 Extract the derivation (research R1) into `backend/app/services/anthropometry.py`:
  - Move it from `backend/app/routers/anthropometry.py::create_anthropometry` (lines ~131–205).
  - Add `DerivedFields` (dataclass), `async derive_record_fields(db, athlete, *, evaluation_date, weight_kg, standing_height_cm, sitting_height_cm) -> DerivedFields` and `apply_derived_fields(record, derived) -> None`.
  - Keep, verbatim in behaviour:
    - Mirwald via `calculate_mirwald_offset`;
    - WHO percentiles with the LMS-empty → None fallback;
    - `weight_over_who_range` nulling of weight z/percentile above `WEIGHT_AGE_MAX_MONTHS`;
    - BMI always computed;
    - `nutritional_status` and `growth_source` exactly as today.
  - Make POST call the service.
  - **No behaviour change**: existing `backend/tests/test_athletes.py`, `test_growth_service.py`, `test_audit_athletes.py` and the body-composition tests must stay green.
  - Agent: fastapi-architect · opus
- [X] T008 [P] Add unit tests for the extracted service in `backend/tests/anthropometry/test_derivation_service.py` (create `backend/tests/anthropometry/__init__.py` if the suite needs it):
  - pre/circa/post PHV cases;
  - LMS-empty fallback;
  - age above WHO weight range → weight z/percentile None;
  - BMI rounding to 2 decimals.
  - Agent: qa-engineer · sonnet
- [X] T009 [P] Server-side validation in `backend/app/schemas/anthropometry.py`:
  - Add ranges to `AnthropometryCreate`: `weight_kg` 20–150, `standing_height_cm` 100–220, `sitting_height_cm` 50–120, `arm_span_cm` 100–220 or null.
  - Add a model validator: sitting/standing outside [0.40, 0.65] → 422 with `sitting_ratio_impossible` identifiable in the error payload.
  - Add `AnthropometryUpdate` (same fields and validation, `arm_span_cm` and `notes` optional).
  - Add `PlausibilityCheckIn` (Create fields + `record_id: int | None`), `PlausibilityWarningOut {code, measure}`, `PlausibilityCheckOut {warnings, previous_evaluation_date}` and `RosterRowOut` (fields per contracts/api.md).
  - Add optional `can_modify: bool | None` and `plausibility_flags: list[str] | None` to `AnthropometryOut`, excluded from serialization when None (parents get the keys omitted, not null).
  - Agent: fastapi-architect · sonnet
- [X] T010 [P] Add `can_modify_anthropometric_record(user, record) -> bool` to `backend/app/services/permissions.py` (`user.role == UserRole.admin or record.evaluated_by == user.id`), with a docstring citing clarification 3. Add unit tests in `backend/tests/anthropometry/test_permissions_record_author.py` covering admin, evaluator, other coach and parent. — fastapi-architect · opus
- [X] T011 [P] Frontend API types and clients:
  - In `frontend/src/types/anthropometry.types.ts`, add `can_modify?`, `plausibility_flags?`, `PlausibilityCode` (union of the 5 codes in research R5), `PlausibilityMeasure`, `PlausibilityCheckRequest/Response` and `RosterRow`.
  - In `frontend/src/api/athletes.ts` (or wherever the anthropometry calls live today; keep one module), add `updateAnthropometry`, `deleteAnthropometry`, `checkPlausibility` and `getAnthropometryRoster(date)`.
  - Agent: react-ui-engineer · sonnet
- [X] T012 [P] Zod schema in `frontend/src/schemas/anthropometryCapture.schema.ts`:
  - Same ranges and messages as T009: «Mín. 20 kg» / «Máx. 150 kg», etc.
  - Ratio check (message «La talla sentado no es coherente con la talla de pie»).
  - Date not in the future («No puede ser futura»).
  - `bench_height_cm` ≥ 0 (form-only, never sent).
  - Net sitting = gross − bench > 0.
  - Tests in `frontend/src/schemas/__tests__/anthropometryCapture.schema.test.ts`.
  - Agent: react-ui-engineer · sonnet
- [X] T013 [P] Add `frontend/src/lib/anthropometry/devicePrefs.ts`: get/set `tyr.anthro.captureMode` (`"guided"|"quick"`, default `"guided"`) and `tyr.anthro.benchHeightCm` (number | null), with guarded `localStorage` access, plus tests. — react-ui-engineer · sonnet

**Checkpoint**: the derivation is extracted with the suite green, validation is shared, and the permission helper and frontend base are ready.

---

## Phase 3: User Story 1 — Correct or remove a wrong measurement (P1) 🎯 MVP

**Goal**: the evaluator or an admin edits or deletes a record. Derived values are recomputed, AI explanations are invalidated, skinfold rules are re-applied, everything is audited, and the actions are hidden for everyone else.

**Independent Test**: quickstart §2 A3–A6, A9 and A11, plus the `anthropometry-edit-delete.spec.ts` e2e.

### Tests for User Story 1

- [X] T014 [P] [US1] API tests in `backend/tests/anthropometry/test_update_api.py`:
  - The evaluator's PUT recomputes `maturity_offset`/`maturation_status`/percentiles/BMI.
  - A PUT that changes weight recomputes the skinfold estimates.
  - A PUT deletes the `athlete_ai_explanations` rows for the record.
  - A PUT date change colliding with another record → 409 `anthropometry_same_date_exists`.
  - A PUT date change on a record with a skinfold set, breaking age/interval → 409 `athlete_too_young` / `skinfold_interval_too_short` with `next_allowed_date`.
  - A PUT never enqueues a parent notification (assert dispatcher not called).
  - Denied paths: 403 `not_record_author` for `coach2`, 403 for a parent, 404 for another club's athlete, and 404 for a record of another athlete.
  - Agent: qa-engineer · sonnet
- [X] T015 [P] [US1] API tests in `backend/tests/anthropometry/test_delete_api.py`:
  - 204 by the evaluator and by an admin.
  - The skinfold set and AI explanations are gone.
  - Audit `delete` has `meta == {"had_skinfolds": True}`.
  - Denied paths: 403 `not_record_author` for a coach who is not the evaluator, 403 for a parent.
  - After deleting the only record, `GET /athletes/{id}/growth-summary` returns its empty shape.
  - Agent: qa-engineer · sonnet
- [X] T016 [P] [US1] Privacy and audit tests in `backend/tests/anthropometry/test_anthropometry_privacy.py`:
  - The PUT audit has `changed_fields` names only, with values only for `evaluation_date` (VALUE_ALLOWLIST).
  - No weight/height numbers in audit `meta`/`diff`, in 4xx response bodies or in captured logs (caplog) for PUT/DELETE/plausibility/roster.
  - Parent GET omits `can_modify` and `plausibility_flags` keys.
  - Agent: qa-engineer · sonnet

### Implementation for User Story 1

- [X] T017 [US1] Add `async check_interval_for_date(db, athlete_id, record, new_date, settings)` to `backend/app/services/body_composition.py`:
  - Same rule and 409 detail/`next_allowed_date` as `check_interval`.
  - Evaluated at `new_date` and excluding `record`'s own set (the existing `check_interval` no-ops once a set exists).
  - Unit tests in `backend/tests/anthropometry/test_check_interval_for_date.py`.
  - Agent: fastapi-architect · opus
- [X] T018 [US1] Add `PUT /api/athletes/{athlete_id}/anthropometry/{record_id}` in `backend/app/routers/anthropometry.py` (contracts/api.md):
  - Order: `require_role([admin, coach])` + `verify_athlete_access` → load the record scoped to the athlete (else 404) → `can_modify_anthropometric_record` (else 403 `{"detail":"not_record_author"}`).
  - Same-date collision check when the date changes → 409.
  - If a skinfold set exists and the date changed: `check_min_age` + `check_interval_for_date`.
  - Assign the editable fields → `derive_record_fields` + `apply_derived_fields`.
  - If the weight changed and a set exists: `recompute_estimates_for_record(record)`.
  - Delete all `AthleteAIExplanation` rows for the record, auditing each per the existing AI-explanation audit pattern.
  - `record_audit(action=update, entity_type=anthropometric_record, changed_fields=[changed names])`.
  - **Never send notifications** (research R3).
  - Return `AnthropometryOut`.
  - Agent: fastapi-architect · opus
- [X] T019 [US1] Add `DELETE /api/athletes/{athlete_id}/anthropometry/{record_id}` in `backend/app/routers/anthropometry.py`:
  - Same access sequence as T018.
  - Explicitly delete AI explanations (audited).
  - Delete the record (the skinfold set goes by ORM cascade).
  - `record_audit(action=delete, meta={"had_skinfolds": bool})`.
  - 204.
  - Agent: fastapi-architect · opus
- [X] T020 [US1] Register PUT and DELETE in the route-policy map in `backend/app/services/audit.py` (~lines 917–930, `Audited(...)`) so the route-walk coverage test (`backend/tests/test_audit_coverage.py`) passes. — fastapi-architect · sonnet
- [X] T021 [US1] In `backend/app/routers/anthropometry.py` GET list, set `can_modify` per record for coach/admin (via `can_modify_anthropometric_record`). Leave it None (omitted) for parents. Tests in `backend/tests/anthropometry/test_list_flags_can_modify.py`. — fastapi-architect · sonnet
- [X] T022 [P] [US1] Hooks in `frontend/src/hooks/athletes/useAnthropometry.ts`:
  - Add `useUpdateAnthropometry(athleteId)` and `useDeleteAnthropometry(athleteId)`.
  - Invalidate the same keys as `useCreateAnthropometry` (`["anthropometry", id]`, `["athlete", id]`, `["growth-summary", id]`, `["ai","phv",id]`) plus `["body-composition", id]` and the record-explanation AI keys.
  - Agent: react-ui-engineer · sonnet
- [X] T023 [US1] Create `frontend/src/components/athletes/anthropometry-capture/QuickCaptureForm.tsx` by refactoring `frontend/src/components/athletes/AnthropometryForm.tsx`'s grid:
  - RHF + `anthropometryCapture.schema.ts`.
  - Fields: date, weight, standing, sitting with `BenchHeightField` (net value line «Talla sentado neta: X cm»; the bench is pre-filled from `devicePrefs`, 0 on edit), and arm span (optional).
  - Numeric inputs `inputMode="decimal"`, 48 px targets.
  - Accepts `defaultValues` and `onReview(values)`.
  - Create `BenchHeightField.tsx` in the same folder.
  - Agent: react-ui-engineer · sonnet
- [X] T024 [US1] Create `frontend/src/routes/athletes/AnthropometryEditPage.tsx` (`/athletes/:id/anthropometry/:recordId/edit`):
  - Loads the record from `useAnthropometry` and renders `QuickCaptureForm` pre-filled.
  - Note «Al guardar se recalculan el estado de maduración, los percentiles y la explicación de IA de esta medición.»
  - «Revisar y guardar» → `CaptureReviewStep` (T036) with `record_id`; if T036 isn't merged yet, a plain save button.
  - Error mapping: 403 → «Solo quien tomó esta medición o un administrador puede modificarla.»; 409 same-date / skinfold codes → the same copy as the 046 wizard.
  - Register the lazy route in `frontend/src/App.tsx` (coach/admin only).
  - Agent: react-ui-engineer · opus
- [X] T025 [US1] In `frontend/src/components/athletes/AnthropometryHistory.tsx` (coach mode only), add row actions «Editar» (link to the edit route) and «Eliminar» when `record.can_modify`:
  - «Eliminar» opens `frontend/src/components/shared/ConfirmDialog.tsx` with `tone="danger"`, title «¿Eliminar la medición del {fecha}?» and body «Se eliminarán también los pliegues cutáneos y la explicación de IA de esta fecha, si existen. Esta acción no se puede deshacer.»
  - At narrow widths the actions live in the row detail sheet.
  - Parent mode is unchanged.
  - Agent: react-ui-engineer · sonnet
- [X] T026 [P] [US1] Vitest + jest-axe:
  - `frontend/src/routes/athletes/__tests__/AnthropometryEditPage.test.tsx`: prefill, save, 403 copy, 409 copy, axe.
  - `frontend/src/components/athletes/__tests__/AnthropometryHistory.actions.test.tsx`: actions only when `can_modify`, delete confirm flow, parent mode has no actions, axe on the dialog.
  - Agent: qa-engineer · sonnet

**Checkpoint**: US1 is shippable alone. Wrong records can be fixed or removed by the right people, with a full audit.

---

## Phase 4: User Story 2 — Guided, trustworthy single-athlete capture (P1)

**Goal**: pre-check → illustrated single-reading steps → review with server plausibility warnings and a plain PHV summary → the two 046 save exits. Quick mode, the bench subtraction, the same-date rule and the «Revisar» marker in the history.

**Independent Test**: quickstart §2 A1, A2, A7, A8, plus `anthropometry-capture.spec.ts`.

### Tests for User Story 2

- [X] T027 [P] [US2] Rule boundary tests in `backend/tests/anthropometry/test_plausibility_rules.py` (research R5 table):
  - `height_decreased` at −1.0 (no) and −1.1 cm (yes).
  - `height_velocity_implausible` at 59 days (skipped) and 60 days; 15.0 cm/yr (no) and 15.1 (yes).
  - `weight_change_large` at 10 % (no) and 10.1 % (yes), both directions.
  - `sitting_ratio_atypical` at 0.47/0.57 (no) and outside (yes).
  - `arm_span_ratio_atypical` at 0.90/1.10 and arm span None → never.
  - First evaluation → only ratio rules.
  - Agent: qa-engineer · sonnet
- [X] T028 [P] [US2] API tests in `backend/tests/anthropometry/test_plausibility_api.py` and `test_create_same_date.py`:
  - The dry-run writes nothing (row count unchanged, no audit).
  - `record_id` excludes the edited record from "previous".
  - 422 on hard ranges.
  - Denied paths (parent 403, other club 404).
  - POST same date + same values → 409 `same_values: true`.
  - POST same date + different values → 409 `same_values: false` + `existing_record_id`.
  - POST ratio 0.75 → 422 `sitting_ratio_impossible`.
  - GET list returns `plausibility_flags` for coach/admin and omits them for parents.
  - Agent: qa-engineer · sonnet

### Implementation for User Story 2

- [X] T029 [US2] Implement `backend/app/services/anthropometry_plausibility.py` (research R5):
  - Frozen dataclass inputs.
  - `check_plausibility(current: MeasureSet, previous: MeasureSet | None) -> list[PlausibilityWarning]`, pure and deterministic.
  - Constants at module top: `HEIGHT_DROP_CM = 1.0`, `MIN_VELOCITY_INTERVAL_DAYS = 60`, `MAX_VELOCITY_CM_PER_YEAR = 15.0`, `MAX_WEIGHT_CHANGE_RATIO = 0.10`, `SITTING_RATIO_RANGE = (0.47, 0.57)`, `ARM_SPAN_RATIO_RANGE = (0.90, 1.10)`.
  - Codes `height_decreased`, `height_velocity_implausible`, `weight_change_large`, `sitting_ratio_atypical`, `arm_span_ratio_atypical`, with `measure` in `weight|standing_height|sitting_height|arm_span`.
  - Also `flags_for_series(records_sorted_by_date) -> dict[record_id, list[code]]` for the history marker.
  - Agent: fastapi-architect · opus
- [X] T030 [US2] Changes in `backend/app/routers/anthropometry.py`:
  - POST: same-date check before insert → 409 body `{"detail":"anthropometry_same_date_exists","existing_record_id":id,"same_values":bool}` (compare the 4 measures after Decimal quantization) (research R4).
  - New `POST /api/athletes/{athlete_id}/anthropometry/plausibility` (coach/admin + `verify_athlete_access`; previous = latest record with `evaluation_date` < request date, excluding `record_id`; no write, no audit).
  - GET list: `plausibility_flags` via `flags_for_series` for coach/admin only.
  - Register the plausibility route as non-mutating in the `backend/app/services/audit.py` route-policy map.
  - Agent: fastapi-architect · opus
- [X] T031 [P] [US2] Create `frontend/src/lib/anthropometry/measureGuides.ts`, the same texts as `backend/app/data/anthropometry_measures.json` typed as `Record<MeasureKey, {label, donde, como, alt}>` plus `PRECHECK_CONDITIONS`. Add the parity test `frontend/src/lib/anthropometry/__tests__/measureGuides.parity.test.ts`, which reads the backend JSON via `fs` relative to the repo root and asserts deep equality. — react-ui-engineer · sonnet
- [X] T032 [P] [US2] Create `frontend/src/lib/anthropometry/measureIllustrations.ts`, with static imports of `@/assets/anthropometry/{weight,standing_height,sitting_height,arm_span}.webp` (and `precheck.webp` if T006 produced it) and `getMeasureIllustration(key)`, mirroring `lib/bodyComposition/siteIllustrations.ts`. A missing file must fail the Vite build (FR-031). If T006 has not landed, stop and report rather than adding placeholders. — react-ui-engineer · sonnet
- [X] T033 [P] [US2] Copy and label modules, with tests:
  - `frontend/src/lib/anthropometry/plausibilityCopy.ts`: the exact 5 Spanish messages from contracts/ui.md, plus measure labels.
  - `frontend/src/lib/anthropometry/phvPlain.ts`: `MaturationStatus.PrePHV` → «Aún no llega al estirón», `CircaPHV` → «Está en pleno estirón», `PostPHV` → «Ya pasó el estirón».
  - Agent: react-ui-engineer · sonnet
- [X] T034 [P] [US2] Add `usePlausibilityCheck(athleteId)` (a mutation calling `checkPlausibility`, not cached) in `frontend/src/hooks/athletes/useAnthropometry.ts`. — react-ui-engineer · sonnet
- [X] T035 [P] [US2] Presentational components in `frontend/src/components/athletes/anthropometry-capture/`:
  - `CapturePrecheckStep.tsx`: illustration if available, non-blocking checklist from `PRECHECK_CONDITIONS`, date field, «Empezar», and `FieldGuideDownloadButton`.
  - `MeasureStep.tsx`: illustration + «Dónde»/«Cómo» + one numeric input. Two columns ≥ 768 px, illustration on top at 360 px, max 280 px. Envergadura shows «Omitir (opcional)»; sitting height embeds `BenchHeightField`.
  - `PlausibilityWarnings.tsx`: amber callouts, «Volver a medir» (callback with measure) and «Está bien así».
  - `PhvPlainSummary.tsx`: headline label, training implication, and a collapsible «Detalle técnico» with offset / age at PHV / leg length from `lib/phv.ts`.
  - Agent: react-ui-engineer · sonnet
- [X] T036 [US2] Create `frontend/src/components/athletes/anthropometry-capture/CaptureReviewStep.tsx`:
  - Values table (a definition list at 360 px) with the net sitting height.
  - Calls `usePlausibilityCheck` on mount with the values (+ `record_id` when editing) and shows `PlausibilityWarnings`.
  - `PhvPlainSummary`.
  - Save exits: «Guardar y terminar», plus «Guardar y agregar pliegues» only when age ≥ 9 at the date and the 046 interval is open. Reuse `ageFromBirthDate`, `isIntervalBlocked` and `SKINFOLD_MIN_AGE_YEARS` from `lib/bodyComposition/eligibility.ts` and keep the interval note exactly as in `AnthropometryForm.tsx`.
  - Props: `mode: "create"|"edit"`, `onSaved(recordId, intent)`.
  - Agent: react-ui-engineer · opus
- [X] T037 [US2] Create `frontend/src/components/athletes/anthropometry-capture/AnthropometryCapture.tsx`, the orchestrator:
  - Mode segmented control «Guiado»/«Rápido» persisted via `devicePrefs`.
  - Guided: `Stepper` (`frontend/src/components/shared/Stepper.tsx`) Preparación → Peso → Talla de pie → Talla sentado → Envergadura → Revisar.
  - Quick: `QuickCaptureForm` → inline `CaptureReviewStep`.
  - One RHF form shared across steps; bench height saved to `devicePrefs` on change.
  - «Volver a medir» jumps to the step of that measure.
  - Save via `useCreateAnthropometry`, with the net sitting height sent.
  - 409 `anthropometry_same_date_exists` with `same_values=false` → dialog «Ya existe una medición de esta fecha» with «Abrir la existente» (edit route if `can_modify`, else the history) / «Cambiar la fecha».
  - Props `athlete`, `lockedDate?`, `onDone(result)` so US3 can embed it.
  - **No `useFormDraft`** (clarification 1).
  - Agent: react-ui-engineer · opus
- [X] T038 [US2] Wire the page and entry point:
  - Create `frontend/src/routes/athletes/AnthropometryCapturePage.tsx` (`/athletes/:id/anthropometry/new`, lazy, coach/admin) rendering `AnthropometryCapture`.
  - On «Guardar y terminar», navigate to the athlete's Antropometría tab.
  - On «Guardar y agregar pliegues», navigate to `skinfoldCapturePath(athleteId, recordId)`.
  - In `frontend/src/routes/athletes/AthleteDetailPage.tsx` (~lines 835–862), replace the inline `showForm` toggle + `AnthropometryForm` with a link «+ Nueva medición».
  - Delete `frontend/src/components/athletes/AnthropometryForm.tsx` and its tests once no import remains, moving still-relevant assertions to the new component tests.
  - Register the route in `frontend/src/App.tsx`.
  - Agent: react-ui-engineer · sonnet
- [X] T039 [US2] In `frontend/src/components/athletes/AnthropometryHistory.tsx` (coach mode), show an amber «Revisar» badge on rows with non-empty `plausibility_flags`. Details come from `plausibilityCopy`, shown on tap/click as a popover (not hover-only). No badge in parent mode. — react-ui-engineer · sonnet
- [X] T040 [P] [US2] Vitest + jest-axe in `frontend/src/components/athletes/anthropometry-capture/__tests__/`:
  - `AnthropometryCapture.test.tsx`: guided path end to end with MSW; bench 40 + gross 112.0 → net 72.0 sent; mode preference persisted; «Volver a medir» jumps; 409 dialogs; skinfold exit hidden under 9 years; axe per step.
  - `CaptureReviewStep.test.tsx`: warnings rendered with exact copy; PHV plain label.
  - `MeasureStep.test.tsx`: arm-span skip; `inputmode`.
  - `AnthropometryHistory.flags.test.tsx`.
  - Update MSW handlers in `frontend/src/test/msw/` for plausibility, 409, PUT and DELETE.
  - Agent: qa-engineer · sonnet

**Checkpoint**: US1 + US2 are the core release. Guided capture prevents errors, and US1 fixes whatever slips through.

---

## Phase 5: User Story 3 — Measure the whole group in one session (P2)

**Goal**: roster picker → queue embedding the capture → summary. In-memory only (clarification 1), with a skinfold detour that returns to the queue.

**Independent Test**: `anthropometry-session.spec.ts` + quickstart A10.

- [X] T041 [P] [US3] API tests in `backend/tests/anthropometry/test_roster_api.py`:
  - Only accessible, non-archived athletes.
  - `has_record_on_date` and `last_evaluation_date` are correct.
  - `skinfolds_eligible` false under 9 years and inside the 90-day interval.
  - Future `date` → 422.
  - Parent → 403.
  - **Query-count test ≤ 4** for 30 athletes (the pattern used in existing query-count tests).
  - Agent: qa-engineer · sonnet
- [X] T042 [US3] Create `backend/app/routers/anthropometry_roster.py` (`GET /api/anthropometry/roster?date=`, coach/admin):
  - Club-scope the same way `verify_athlete_access` does (admin: all; coach: athletes of their `ClubRole.coach` clubs), non-archived.
  - One query for athletes, one grouped `max(evaluation_date)`, one exists-on-date, one batch for skinfold interval eligibility (reuse `body_composition` settings: min age 9, 90 days).
  - Return `RosterRowOut`.
  - Mount it in `backend/app/main.py` under `/api/anthropometry`, and register it in the audit route-policy map as non-mutating.
  - Agent: fastapi-architect · opus
- [X] T043 [P] [US3] Add `useAnthropometryRoster(date)` to `frontend/src/hooks/athletes/useAnthropometry.ts` (key `["anthropometry-roster", date]`), invalidated by create/update/delete. — react-ui-engineer · sonnet
- [X] T044 [US3] Create `frontend/src/store/measurementSession.store.ts`:
  - Zustand **without `persist`**.
  - State `{date, athleteIds, statusById: Record<id, "pending"|"measured"|"skipped">, recordIdById, warningsById, currentId}`.
  - Actions `start(date, ids)`, `markMeasured(id, recordId, hasWarnings)`, `skip(id)`, `reopen(id)`, `goTo(id)`, `next()`, `reset()`.
  - Call `reset()` from `auth.store.ts` `logout()`.
  - Tests in `frontend/src/store/__tests__/measurementSession.store.test.ts`, including that nothing is written to `localStorage`/`sessionStorage`.
  - Agent: react-ui-engineer · opus
- [X] T045 [US3] Create `frontend/src/routes/anthropometry/MeasurementSessionPage.tsx` (`/anthropometry/session`, lazy, coach/admin) with three views driven by the store:
  1. **Picker**: date (default today, not in the future), category chips (client-side filter over the roster), stacked selectable cards with the last evaluation date and a «Medido hoy» badge, «Seleccionar todos los visibles», «Empezar jornada (N)».
  2. **Queue**: progress «3 de 12» + bar, current athlete name/category, embedded `AnthropometryCapture` with `lockedDate`. After save: toast «Guardado» → `markMeasured` → next pending; if `skinfolds_eligible`, offer «Agregar pliegues». Also «Omitir por hoy» and «Ver lista» (a bottom sheet at 360 px).
  3. **Summary**: Medidos (links + «Revisar» badge), Omitidos («Medir ahora»), Pendientes, and «Terminar jornada» → `reset()`.
  - Opening the page with no session shows the picker.
  - Register it in `frontend/src/App.tsx` and add a «Jornada de medición» button in `frontend/src/routes/athletes/AthletesListPage.tsx`.
  - Agent: react-ui-engineer · opus
- [X] T046 [US3] Skinfold detour return:
  - In `frontend/src/routes/athletes/SkinfoldCapturePage.tsx` (navigations at ~lines 51 and 100), honour a `returnTo` query param restricted to the internal path `/anthropometry/session` (reject anything else to avoid an open redirect) on finish and cancel.
  - The queue builds the link as `skinfoldCapturePath(id, recordId) + "?returnTo=/anthropometry/session"`.
  - Tests in the existing SkinfoldCapturePage test file.
  - Agent: react-ui-engineer · sonnet
- [X] T047 [P] [US3] Vitest + jest-axe in `frontend/src/routes/anthropometry/__tests__/MeasurementSessionPage.test.tsx`: picker filter and selection, measure → next, skip → summary, reopen skipped, «Medido hoy» badge, axe for picker/queue/summary. — qa-engineer · sonnet

**Checkpoint**: a group measurement day works end to end.

---

## Phase 6: User Story 4 — Clear behaviour when the connection fails (P2)

**Goal**: online-only capture with an explicit «no se guardó» state, «Reintentar», and no duplicates on retry.

**Independent Test**: the offline block in `anthropometry-capture.spec.ts` (route abort → retry → exactly one record).

- [X] T048 [US4] Offline and retry handling in `frontend/src/components/athletes/anthropometry-capture/AnthropometryCapture.tsx` and `CapturePrecheckStep.tsx`:
  - If `navigator.onLine === false` when opening, show «Necesitas conexión a internet para registrar mediciones.» and disable «Empezar».
  - Network error on save → red banner «Sin conexión — no se guardó. Revisa tu conexión y vuelve a intentar.» + «Reintentar», with values kept.
  - On a retry, a 409 with `same_values: true` is treated as success using `existing_record_id`.
  - Keep the existing «Iniciando servidor…» cold-start pattern (`serverWaking.store.ts`).
  - Agent: react-ui-engineer · opus
- [X] T049 [P] [US4] Vitest in `frontend/src/components/athletes/anthropometry-capture/__tests__/AnthropometryCapture.offline.test.tsx`: offline-on-open message; network error keeps values; retry after a lost response → 409 `same_values: true` → success callback called once; 409 `same_values: false` on first attempt → dialog, not success. — qa-engineer · sonnet

**Checkpoint**: the coach always knows whether a child was saved.

---

## Phase 7: User Story 5 — Printable field guide for the basic measures (P3)

**Goal**: the field guide PDF opens with «Antes de medir» + the four basic measures, from the same JSON as the app.

**Independent Test**: quickstart A12.

- [X] T050 [US5] In `backend/app/routers/body_composition.py` (field-guide handler, ~line 601+), load `backend/app/data/anthropometry_measures.json` alongside `skinfold_sites.json`. In `backend/templates/documents/pdf/skinfold_field_guide.html`, add a first section «Antes de medir» (pre-check list) and one block per measure (`anthro_<key>.png`, «Dónde», «Cómo»), in the same visual style as the skinfold blocks, before the skinfold sections. Keep the athlete-independent contract (no athlete data). — fastapi-architect · sonnet
- [X] T051 [P] [US5] Tests in `backend/tests/anthropometry/test_field_guide_basic_measures.py`: 200 PDF; the rendered HTML (render the template directly, like the existing field-guide tests) contains «Antes de medir», the 4 labels and the 4 image references before the first skinfold label; no athlete fields. — qa-engineer · sonnet

**Checkpoint**: the paper fallback and helper training material are available.

---

## Phase 8: Polish, local e2e and cross-cutting

- [X] T052 [P] E2E in `frontend/e2e/anthropometry-capture.spec.ts` using `frontend/e2e/helpers/demo-athlete.ts` (`loginAsCoach`, `gotoDemoAthlete`):
  - Guided path: pre-check, 4 steps, bench 40 → net shown, a weight +20 % vs the previous → warning on Revisar, PHV plain label, save → the history row exists.
  - Quick mode persisted across reload.
  - Same-date second capture → dialog.
  - Offline block: `page.route` abort on POST → banner → unroute → «Reintentar» → exactly one new row.
  - A `test.describe` with `test.use({ viewport: { width: 360, height: 780 }, hasTouch: true })` repeats the guided path and asserts `scrollWidth <= 360` and the illustration above the input.
  - Clean up the records it creates via the API.
  - Agent: qa-engineer · sonnet
- [X] T053 [P] E2E in `frontend/e2e/anthropometry-edit-delete.spec.ts` with `realTokens` from `frontend/e2e/helpers/session.ts`:
  - The coach creates a record, edits the sitting height (the PHV label changes in the history detail) and deletes it via the confirm dialog.
  - `coach2` sees no «Editar»/«Eliminar» on a record created by `coach`, and a direct `PUT` returns 403.
  - A parent sees no actions and no «Revisar» badge.
  - Agent: qa-engineer · sonnet
- [X] T054 [P] E2E in `frontend/e2e/anthropometry-session.spec.ts`:
  - Picker → select 3 → measure 1 → skip 1 → measure 1 → summary counts.
  - Reload mid-session → the picker shows «Medido hoy» for the saved athletes (the session is gone by design).
  - Skinfold detour for an eligible athlete returns to the queue.
  - A 360 px variant of the picker + one capture.
  - Agent: qa-engineer · sonnet
- [X] T055 Update `frontend/e2e/anthropometry.spec.ts` and `frontend/e2e/body-composition.spec.ts` for the new entry point: «+ Nueva medición» is now a link to the capture page, and «Guardar y agregar pliegues» sits on the Revisar step. Check `frontend/e2e/target-size.spec.ts` covers the new pages, adding them if it enumerates routes. — qa-engineer · sonnet
- [X] T056 Run the local e2e on the isolated stack:
  - `cd frontend && ./scripts/e2e-stack.sh up`
  - `npm run test:e2e:isolated -- e2e/anthropometry-capture.spec.ts e2e/anthropometry-edit-delete.spec.ts e2e/anthropometry-session.spec.ts e2e/anthropometry.spec.ts e2e/body-composition.spec.ts`
  - Then run the full e2e suite once to catch regressions, and `./scripts/e2e-stack.sh down`.
  - Report pass/fail counts verbatim. If the stack cannot start, report e2e as **not run**.
  - Never point at the production DB.
  - Agent: orchestrator
- [X] T057 [P] Run the full offline gates and report the results: backend `python -m pytest -q` + `ruff check`; frontend `npm run typecheck`, `npm test`, `npm run build` (the build proves all webp assets exist); a bundle check that the new lazy routes are ≤ 150 KB gzip each. — qa-engineer · sonnet
- [ ] T058 [P] Optional `mysql` lane: run `pytest -m mysql` once with a DELETE cascade test added to `backend/tests/anthropometry/test_delete_api.py` under the `mysql` marker (skinfold set + AI explanation rows gone on real FK cascade), against a `_test` database only. Report it as deferred if no MySQL is available. — qa-engineer · sonnet
- [X] T059 `data-privacy-guard` audit of the whole change:
  - Audit meta/diff, logs, 4xx bodies, parent payloads (no `can_modify`/`plausibility_flags`), the session store not persisted, `localStorage` keys holding no personal data, image prompts free of athlete data, and the e2e fixtures.
  - Write findings to `specs/048-anthropometry-capture-ux/privacy-audit.md` and fix any blocker before completion.
  - Agent: data-privacy-guard · opus
- [X] T060 [P] Docs:
  - `docs/23-anthropometry-capture/design.md` (flows, plausibility rules and thresholds, decisions R1–R12).
  - `docs/23-anthropometry-capture/runbook-coach.md` (how to measure, bench height, session day, correcting a record; español for the coach-facing runbook, per the existing 21-body-composition runbook convention).
  - `docs/23-anthropometry-capture/qa.md` (what ran and what was deferred).
  - A row in `docs/README.md`, a step table in `docs/implementation-status.md` and a dated entry in `docs/technical-notes.md`.
  - Agent: technical-writer · sonnet
- [ ] T061 Owner check on a real tablet, from quickstart §5: guided capture timed under 2 minutes (SC-003) and a 3-athlete session. Record the result in `docs/23-anthropometry-capture/qa.md`. Post-deploy smoke (`/health` + GET anthropometry of the demo athlete) stays open until deploy. — orchestrator

---

## Dependencies & execution order

- **Phase 1 (T001–T006)**: T001 is independent. T002 → T003/T004 → T005 → T006 run sequentially in Chrome with the owner. They can run while Phase 2 runs in subagents.
- **Phase 2 (T007–T013)** blocks all stories:
  - T007 comes first (it touches the router).
  - T008 and T009 can start after T007.
  - T010–T013 are independent of T007.
- **US1 (T014–T026)**:
  - T017 → T018 → T019 → T020 → T021 run sequentially (same router/audit files).
  - T014–T016 can be written in parallel with them.
  - T022/T023 can run in parallel with the backend.
  - T024 needs T022 + T023 (it uses T036 if present).
  - T025 needs T022.
  - T026 comes last.
- **US2 (T027–T040)**:
  - Needs Phase 2.
  - T029 → T030; T030 comes after T021 (same router file).
  - T031/T032/T033/T034/T035 run in parallel. T032 needs T006.
  - T036 needs T033–T035.
  - T037 needs T023 + T036.
  - T038 needs T037.
  - T039 needs T030 + T033.
- **US3 (T041–T047)**: needs T037 (embedded capture). T042 is independent of the frontend, and T044 is independent of T042.
- **US4 (T048–T049)**: needs T037.
- **US5 (T050–T051)**: needs T001 + T006. It is independent of the frontend.
- **Polish**:
  - T052–T055 come after the stories they test.
  - T056 comes after T052–T055.
  - T059 comes after all implementation.
  - T060 can start once the behaviour is stable.
  - T061 comes last.

### Parallel waves (suggested orchestration)

1. **Wave A**: T001, T007 (fastapi-architect/opus) ∥ T010 ∥ T011 ∥ T012 ∥ T013 ∥ orchestrator T002–T006 in Chrome.
2. **Wave B**: T008 ∥ T009 → the US1 backend chain T017–T021 (one fastapi-architect/opus lane) ∥ T014–T016 (qa/sonnet) ∥ T022–T023 (react/sonnet).
3. **Wave C**: T029–T030 (fastapi/opus lane) ∥ T027–T028 (qa) ∥ T031–T035 (react/sonnet) ∥ T050–T051.
4. **Wave D**: T036 → T037 (react/opus) → T038, T039, T024, T025, T026, T040.
5. **Wave E**: T041–T047 (US3) ∥ T048–T049 (US4).
6. **Wave F**: T052–T055 ∥ T057 ∥ T058 → T056 (orchestrator) → T059 → T060 → T061.

Rule for every wave: one subagent per file set, so backend router edits (T018–T021, T030) stay in a single sequential lane. Per the memory rule, no new agents are launched once session usage reaches 80 %.

## Implementation strategy

- **MVP = Phase 2 + US1**: correction and removal alone fix the data-quality hole. They can ship before the new capture.
- **Core release = MVP + US2 + US4**: guided capture with warnings and honest failure states. This requires the approved illustrations from Phase 1.
- **Then US3** (group day) and **US5** (paper guide).
- **Stop at every checkpoint** to run that story's tests.
- **Illustrations gate US2**: if Chrome generation stalls, US1, US3's backend and US5's text can still progress, but T032 must not use placeholders.
