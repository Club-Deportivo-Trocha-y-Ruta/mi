# Tasks: Body composition by skinfolds (plicómetro) for athletes aged 9 and up

**Input**: Design documents from `specs/046-body-composition-skinfolds/` — `plan.md`, `spec.md`, `research.md` (R1–R16), `data-model.md`, `contracts/skinfolds-api.md`, `contracts/body-composition-reading.md`, `contracts/ai-body-composition-leaf.md`, `quickstart.md`; research corpus in `docs/21-body-composition/`.

**Tests**: REQUIRED (constitution Principle II, non-negotiable; spec SC-003/SC-004/SC-008 are test-verified). Test tasks are listed before the implementation they cover; write them first and watch them fail.

**Branch / git**: everything on `main`, no feature branch, **no commits** by agents (owner decision). Never write a minor's name in code, fixtures, logs or prompts; fixtures are synthetic.

**Organization**: phases by user story (US1–US6 from `spec.md`); each phase is an independently testable increment. Waves from `plan.md` map as: W1 = Phases 1–2, W2 = backend halves of Phases 3–6, W3 = frontend of Phase 3, W4 = frontend of Phases 4–6, W5 = Phase 8, W6 = Phase 9.

## Format: `[ID] [P?] [Story] Description — agent · model · effort`

- **[P]**: parallelizable (different files, no dependency on an unfinished task).
- **[Story]**: US1…US6 for story phases only.
- **Trailing annotation** (owner request 2026-09-23, "sonnet, opus y haiku según el caso, effort automático"): `agent` = project agent from `.claude/agents/` (or `general-purpose`); `model` = `haiku` for mechanical, well-specified edits with no design judgement; `sonnet` for standard implementation, tests and content; `opus` for design-heavy, safety-critical or integration-gate work. `effort` is a hint (`low` / `medium` / `high`); the orchestrator may raise it when a task fails its first attempt.

## Path Conventions

Web app: backend under `backend/` (`app/…`, `alembic/…`, `templates/…`, `tests/…`, `evals/…`), frontend under `frontend/` (`src/…`, `e2e/…`). All paths below are repository-relative.

---

## Phase 1: Setup (shared configuration and reference data)

**Purpose**: settings, enum values and the vendored Colombian reference the rest depends on.

- [X] T001 [P] Add `BODY_COMP_MDC_SUM4_MM: float = 7.0`, `BODY_COMP_MDC_SUM6_MM: float = 10.0`, `BODY_COMP_MIN_INTERVAL_DAYS: int = 90`, `BODY_COMP_MIN_AGE_YEARS: int = 9` to `Settings` in `backend/app/config.py` with a docstring block pointing to `specs/046-body-composition-skinfolds/data-model.md` §4; extend the `AI_ANTHRO_PROMPT_VERSION` allowed list to `{"v1", "v2"}` keeping the default `v1` for now (Phase 8 flips it) — devops-engineer · haiku · low
- [X] T002 [P] Add `FUPRECOL = "FUPRECOL"` to `GrowthSource` and `triceps_skinfold_for_age`, `subscapular_skinfold_for_age`, `triceps_subscapular_sum_for_age` to `GrowthIndicator` in `backend/app/models/growth.py` (keep `values_callable` usage intact; no schema change here) — fastapi-architect · haiku · low
- [X] T003 [P] Vendor the FUPRECOL LMS reference: create `backend/app/data/fuprecol_lms/fuprecol_skinfolds.csv` with header `indicator,sex,age_months,L,M,S` and one row per sex × one-year band (`age_months` = band midpoint: 114, 126, 138, 150, 162, 174, 186, 198, 210) × indicator, transcribing L, S and P50 (= M) from Tables 2–4 of Ramírez-Vélez et al. 2016 (PMC5083983, CC BY 4.0; fetch the PMC HTML and parse the tables programmatically, then spot-check 6 values by hand); write `backend/app/data/fuprecol_lms/README.md` with citation, DOI 10.3390/nu8100595, licence, population (Bogotá schoolchildren, n = 9 618), caliper (Holtain), **left side**, age range 9–17.9 and the midpoint convention — data-analyst · sonnet · high

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: table, migration, seed, computation service, schemas and the shared frontend primitives every story uses.

**⚠️ CRITICAL**: no user-story work starts before this phase is complete and `pytest`, `ruff check` and `npm run typecheck` are green.

- [X] T004 Create `SkinfoldMeasurement` in `backend/app/models/skinfold_measurement.py` exactly per `data-model.md` §1: `anthropometric_record_id` FK `ondelete=CASCADE` **UNIQUE**; `athlete_id` FK indexed; six `{site}_mm NUMERIC(4,1) NULL`, six `{site}_declined BOOLEAN NOT NULL default false`, six `{site}_readings JSON NULL`; `sum4_mm`/`sum6_mm NUMERIC(5,1) NULL`; `body_fat_pct NUMERIC(4,1) NULL`; `fat_mass_kg`/`fat_free_mass_kg NUMERIC(5,2) NULL`; `equation_version VARCHAR(32) NULL`; `protocol_version VARCHAR(16) NOT NULL default "v1"`; `caliper_model VARCHAR(32) NOT NULL default "slim_guide"`; `measured_by` FK users; same `ActorTimestampMixin` as `AnthropometricRecord`; add `AnthropometricRecord.skinfolds` (`uselist=False`, `cascade="all, delete-orphan"`) in `backend/app/models/anthropometry.py` and export in `backend/app/models/__init__.py` — fastapi-architect · sonnet · medium
- [X] T005 Write Alembic revision `backend/alembic/versions/<rev>_skinfold_measurements_and_fuprecol_lms.py` (parent = current single head, verify with `alembic heads` first): create the table with `batch_alter_table`-compatible operations, unique constraint and index; on MySQL only (`op.get_bind().dialect.name == "mysql"`) alter `growth_reference_lms.source` ENUM to add `FUPRECOL` and `growth_reference_lms.indicator` ENUM to add the three skinfold indicators via `op.alter_column(..., type_=sa.Enum(...), existing_type=sa.Enum(...))`; symmetric `downgrade()` that deletes `FUPRECOL` rows, shrinks both enums (MySQL only) and drops the table — database-architect · opus · high
- [X] T006 [P] Extend `backend/app/seed_growth_data.py` with a `FUPRECOL_SOURCES` entry reading `app/data/fuprecol_lms/fuprecol_skinfolds.csv` (generic `indicator,sex,age_months,L,M,S` parser, idempotent upsert on `uq_lms_source_indicator_sex_age`, source `FUPRECOL`); no change needed in `backend/entrypoint.sh` (verify it already calls the seed) — devops-engineer · sonnet · medium
- [X] T007 [P] Write `backend/tests/services/test_body_composition.py` (fails until T008–T009): `site_value` mean-of-2 / median-of-3; `needs_third_reading` rule: third needed iff |r1−r2| > max(0.05·mean, 1.0 mm), with edges 8.0/9.0 → false (exactly the 1 mm floor), 8.0/9.5 → true, 20.0/21.0 → false (1.0 < 1.025), 20.0/21.5 → true; sums present/absent per declined site; Slaughter TC by sex (M: 0.735·Σ+1.0, F: 0.610·Σ+5.0); FM/FFM from weight; delta codes at Δ = 6.9 → `within_noise`, 7.0 → `up_real`, −7.0 → `down_real`; interval rule (89 days → blocked, 90 → allowed, replacement always allowed, all-declined set ignored); age gate (8.9 y blocked, 9.0 allowed) — qa-engineer · sonnet · medium
- [X] T008 Implement `backend/app/services/body_composition.py` (module docstring: inputs/outputs/side effects): constants `SITES`, `BACKBONE_SITES`, `READING_TOLERANCE_MIN_MM = 1.0`, `READING_TOLERANCE_PCT = 0.05`, `PLAUSIBLE_RANGES` per site/age band (`data-model.md` §4); pure functions `site_value(readings)`, `needs_third_reading(r1, r2)`, `compute_sums(values)`, `estimate_body_fat(sex, triceps_mm, calf_mm)` → `(pct, equation_version="slaughter_tc_1988_v1")`, `fat_masses(weight_kg, pct)`, `plausible_range(site, age_years)`, `classify_sum_change(delta, threshold)`; `apply_set(record, payload, settings)` that fills every column of `SkinfoldMeasurement`; `check_interval(db, athlete_id, record, settings)` raising a domain error with `previous_set_date`/`next_allowed_date`; `check_min_age(athlete, record, settings)`; `recompute_estimates_for_record(record)` for weight corrections — fastapi-architect · sonnet · high
- [X] T009 Implement `build_reading(...)` in `backend/app/services/body_composition.py` exactly per `contracts/body-composition-reading.md` §1–§3 (leg codes, ordered band rules, `band_reason_code`, `legs_missing`, `next_due_date` = latest counted set + `BODY_COMP_MIN_INTERVAL_DAYS`), §3b (`latest_set` = latest counted set; `latest_attempt_declined` when a newer fully declined attempt exists) and §3c (`family_band` projection: rojo → `ambar`, reference-only ámbar → `verde`, helper `is_reference_only_ambar`; `family_band` can never be `rojo`), plus the Spanish sentence tables of §4 as module-level dicts (`FAMILY_COPY` keyed by `family_band` with no rojo entry, `NEWSLETTER_NOTICE`, `COACH_REASON_COPY`, `ESCALATION_COPY`, `CHANGE_COPY`) — sports-science-advisor · opus · high
- [X] T010 [P] Write `backend/tests/services/test_body_composition_reading.py` (fails until T009): parametrised scenarios A–I of `contracts/body-composition-reading.md` §5 asserting both `band` and `family_band` (A→verde, B→verde, C→ambar, D→verde, F→ambar, H: reading from the counted set with `latest_attempt_declined` set, I→ambar) plus: `family_band` is never `rojo` for any generated leg combination (property over the leg-code product); `FAMILY_COPY` has no rojo key and no sentence contains "profesional"; rising Σ4 never yields rojo in any combination; single set never rojo; missing `previous_set` → `legs_missing` contains `previous_set`; every `band_reason_code` has a coach sentence and every band a family sentence with no digit followed by `%` or `mm` — qa-engineer · sonnet · medium
- [X] T011 [P] Implement `backend/app/services/reference_skinfolds.py`: `reference_context(db, sex, age_months, triceps_mm, subscapular_mm)` → per-site `{percentile, code}` using `get_lms_params`/`calculate_z_score`/`z_to_percentile` from `backend/app/services/growth.py` with source `FUPRECOL`; codes `low_extreme` < P5, `low` P5–P10, `normal`, `high` P85–P95, `high_extreme` ≥ P95; `unavailable` outside 108–216 months, when the site is declined, or when no rows are seeded; with `backend/tests/services/test_reference_skinfolds.py` (seed 2 bands in the aiosqlite lane, check interpolation and the `unavailable` cases) — fastapi-architect · sonnet · medium
- [X] T012 [P] Write `backend/tests/test_migration_skinfolds.py` marked `@pytest.mark.mysql`: upgrade head → seed FUPRECOL → assert 3 indicators × 2 sexes × 9 bands rows and enum values present → downgrade one revision → assert rows gone and table dropped → upgrade again (document in the file that this lane is deferred when no MySQL is available) — qa-engineer · sonnet · medium
- [X] T013 Create Pydantic schemas in `backend/app/schemas/body_composition.py` per `contracts/skinfolds-api.md`: `SkinfoldSiteIn` (discriminated: `{declined: true}` or `{readings: list[Decimal]}` with `min_length=2`, `max_length=3`, each `ge=2.0`, `le=60.0`, at most one decimal and multiple of 0.5), `SkinfoldSetIn` (`caliper_model` default `slim_guide`; all six sites required), `SkinfoldSiteOut`, `SkinfoldSetOut` (incl. `margin_pct: int = 4`, `unconfirmed` per site), `BodyCompositionReading`, `BodyCompositionSeries`, `BodyCompositionOut`, `BodyCompositionSummary` (coach; includes `band`, `family_band`, `latest_attempt_declined`) and `BodyCompositionFamilySummary` (`has_data, latest_set_date, family_band, family_label, family_sentence` only, `family_band: Literal["verde", "ambar"]`, `extra="forbid"`); add `skinfolds: SkinfoldSetOut | None = None` to `AnthropometryOut` in `backend/app/schemas/anthropometry.py` and `body_composition: BodyCompositionSummary | BodyCompositionFamilySummary | None = None` to `GrowthSummaryOut` in `backend/app/schemas/growth.py` — fastapi-architect · sonnet · medium
- [X] T014 [P] Create frontend foundations: `frontend/src/types/bodyComposition.types.ts` (mirror of T013 shapes), `frontend/src/schemas/bodyComposition.schema.ts` (Zod mirror for API parsing + wizard form schema where each site is `z.discriminatedUnion` of `{declined: true}` / `{readings: number[2–3]}`), `frontend/src/api/bodyComposition.ts` (`getBodyComposition`, `saveSkinfolds`, `deleteSkinfolds`, `downloadReferralNote`, `downloadFieldGuide`, blob handling as in `frontend/src/api/intervals.ts`), and MSW handlers `frontend/src/mocks/handlers/bodyComposition.ts` registered in the existing handlers index — react-ui-engineer · sonnet · medium
- [X] T015 [P] Implement `frontend/src/lib/bodyComposition/readings.ts` (`computeSiteValue(readings)`, `needsThirdReading(r1, r2)`, `isPlausible(site, ageYears, value)`) with `frontend/src/lib/bodyComposition/__tests__/readings.test.ts` using the **same numeric fixtures** as T007 (copy them into a shared JSON `frontend/src/lib/bodyComposition/__tests__/fixtures.json` and reference the backend file in a comment) — react-ui-engineer · sonnet · low
- [X] T016 [P] Extend `frontend/src/lib/growth/bands.ts` with the body-composition vocabulary (`verde`/`ambar`/`rojo` → `StatusBadge` tone `success`/`warning`/`danger`, coach labels for `band`, family labels keyed by `family_band` — `verde`/`ambar` only, no rojo family label — from `contracts/body-composition-reading.md` §3c–§4) as a sibling of `getBandVocabulary`, plus unit test in `frontend/src/lib/growth/__tests__/bands.test.ts` — react-ui-engineer · haiku · low
- [X] T017 Foundational gate: run `cd backend && source .venv/bin/activate && python -m pytest tests/services -q && ruff check` and `cd frontend && npm run typecheck && npx vitest run src/lib`; fix anything red; confirm `alembic heads` shows exactly one head; record pass/fail per command in `specs/046-body-composition-skinfolds/checklists/gates.md` — engineering-lead · opus · medium

**Checkpoint**: table, seed, service, schemas and shared frontend libs exist and are green.

---

## Phase 3: User Story 1 — Guided, illustrated skinfold capture (Priority: P1) 🎯 MVP

**Goal**: coach attaches a six-site skinfold set to an evaluation through the illustrated wizard, with per-site skip, third-reading rule, soft range warnings and draft restore.

**Independent Test**: create an evaluation for a synthetic athlete, add skinfolds with one skipped site and one third reading, reload mid-way, finish, and see the set stored on that evaluation with "Omitido" shown neutrally.

### Tests for User Story 1

- [X] T018 [P] [US1] Write `backend/tests/routers/test_body_composition.py` (fails until T020–T022): coach `PUT` happy path returns `sum4_mm` and estimates; `PUT` again replaces; `DELETE` → 204 then 404; parent `PUT` → 403; coach of another club → 403; record of another athlete → 404; readings `[8.5]` → 422; `[8.5, 9.0, 9.5, 10.0]` → 422; value 1.5 → 422; age 8.9 → 409 `athlete_too_young`; second record 30 days later → 409 `skinfold_interval_too_short` with `next_allowed_date`; audit-log row without values; `GET …/anthropometry` as coach includes `skinfolds`, as parent `skinfolds == null` — qa-engineer · sonnet · medium
- [X] T019 [P] [US1] Write vitest specs (fail until T024–T031): `frontend/src/components/athletes/body-composition/__tests__/SkinfoldSiteStep.test.tsx` (third-reading prompt appears at 8.0/9.5, not at 8.0/9.0 nor 20.0/21.0; median shown; skip records `declined`; soft range warning is `role="status"` not `alert`; inputs `step="0.5"`), `SkinfoldWizard.test.tsx` (pre-check never blocks; "Hoy prefiere no medirse" on the pre-check submits one `saveSkinfolds` call with all six sites `{declined: true}` without visiting site steps and shows no reason field; focus moves to step heading; draft restore banner after remount; review lists "Omitido"; submit calls `saveSkinfolds` with the contract payload; offline message on network error), `SkinfoldCapturePage.test.tsx` with `jest-axe` zero violations — qa-engineer · sonnet · medium

### Implementation for User Story 1 (backend)

- [X] T020 [US1] Create `backend/app/routers/body_composition.py` with `PUT /api/athletes/{athlete_id}/anthropometry/{record_id}/skinfolds` and `DELETE` per `contracts/skinfolds-api.md` §1–§2: `require_role([admin, coach])` + `verify_athlete_access`; record must belong to athlete (404); `check_min_age` (409 `athlete_too_young`); `check_interval` (409 `skinfold_interval_too_short` with `previous_set_date`, `next_allowed_date`); `apply_set`; audit-log events `skinfolds.saved` / `skinfolds.deleted` with ids and site count only; `HTTPException.detail` never contains a value or a name — fastapi-architect · sonnet · medium
- [X] T021 [US1] Mount the router in `backend/app/main.py` under `/api/athletes` (same include pattern as `routers/anthropometry.py`) and add the module to the routers index docstring — fastapi-architect · haiku · low
- [X] T022 [US1] Extend `list_anthropometry` in `backend/app/routers/anthropometry.py`: `selectinload(AnthropometricRecord.skinfolds)`, serialise `skinfolds` via `SkinfoldSetOut`, and set `out.skinfolds = None` inside the existing parent projection block (the one nulling `notes`/`morphology`); hook `recompute_estimates_for_record` wherever `weight_kg` can be corrected (verify whether an update route exists; if none, document in the router docstring) — fastapi-architect · sonnet · medium

### Implementation for User Story 1 (frontend)

- [X] T023 [P] [US1] Author `frontend/src/lib/bodyComposition/siteDiagrams.ts`: for each of the six sites (`triceps`, `biceps`, `subscapular`, `medial_calf`, `iliac_crest`, `supraspinale`) a spec `{silhouette: "arm"|"back"|"leg"|"hip", landmark: {x,y}, foldOrientation: "vertical"|"oblique_down_lateral"|"oblique_down_medial", caliper: {x,y,angle}, sideTag: "D", donde: string, como: string, alt: string}` with the Spanish text from `docs/21-body-composition/research-protocol.md` §1 (right side; pinch 1 cm above the mark; caliper on the mark; read at 2 s), ≤ 3 lines each — ux-researcher · sonnet · high
- [X] T024 [P] [US1] Build `frontend/src/components/athletes/body-composition/SkinfoldSiteDiagram.tsx`: inline SVG (`viewBox`, `preserveAspectRatio="xMidYMid meet"`, `role="img"`, `<title>`/`<desc>` from the spec alt), shared silhouettes drawn as simple paths, landmark as a labelled cross, fold as a dashed guideline, caliper as an outlined jaw pair, side tag "D"; strokes ≥ 2 px using theme tokens (`currentColor`/CSS variables), never colour-only distinctions — react-ui-engineer · sonnet · high
- [X] T025 [P] [US1] Build `frontend/src/components/athletes/body-composition/SkinfoldPrecheckStep.tsx`: checklist of reminders (not right after training; dry skin without lotion or sunscreen; private space; second adult present; athlete standing relaxed) as non-blocking checkboxes, one line stating the athlete may decline any site without consequence, "Siguiente" always enabled, and a secondary "Hoy prefiere no medirse" button (≥ 48 px, neutral tone, never error-styled) that calls an `onDeclineAll` prop (spec FR-002) — react-ui-engineer · sonnet · low
- [X] T026 [US1] Build `frontend/src/components/athletes/body-composition/SkinfoldSiteStep.tsx`: diagram + "Dónde"/"Cómo" + two numeric inputs (`inputMode="decimal"`, `step="0.5"`, min 2, max 60, ≥ 48 px) + live difference using `needsThirdReading` → amber `role="status"` message "Diferencia mayor a lo esperado: toma una tercera lectura" revealing a third input; live "Valor del sitio" via `computeSiteValue`; soft `isPlausible` warning "¿Seguro? Ese valor es alto/bajo para este pliegue" (never blocks); "Omitir este sitio" as a secondary button ≥ 48 px in the step header that sets `{declined: true}` and advances — react-ui-engineer · sonnet · medium
- [X] T027 [P] [US1] Build `frontend/src/components/athletes/body-composition/SkinfoldReviewStep.tsx`: table site → value (or "Omitido" in neutral tone) → readings count, computed Σ4/Σ6 preview ("suma incompleta" when a backbone site is declined), primary "Guardar medición" — react-ui-engineer · sonnet · low
- [X] T028 [US1] Build `frontend/src/components/athletes/body-composition/SkinfoldWizard.tsx`: RHF form with the Zod schema from T014, `Stepper` from `@/components/shared/Stepper` (steps: Precheck, six sites, Revisar), per-step `trigger()` validation, the `SessionWizard` focus contract (`stepHeadingRef` + `tabIndex={-1}` + effect on step change), `useFormDraft` with target `skinfolds:{recordId}` and the existing restore/discard banner copy, submit through `useSaveSkinfolds`, `onDeclineAll` from the pre-check builds the all-declined payload and submits it directly (then clears the draft), error states: 409 interval → explanatory message with `next_allowed_date`, network error → "Sin conexión: se guardará cuando vuelvas a tener señal" with retry (draft kept) — react-ui-engineer · opus · high
- [X] T029 [US1] Create `frontend/src/routes/athletes/SkinfoldCapturePage.tsx` (lazy) and register `/athletes/:id/anthropometry/:recordId/skinfolds` in `frontend/src/App.tsx` next to `/athletes/:id` with the same coach/admin guard; page loads the record (age ≥ 9 else redirect with toast), renders `SkinfoldWizard`, returns to `/athletes/:id?tab=growth` on success — react-ui-engineer · sonnet · medium
- [X] T030 [P] [US1] Add hooks `useSaveSkinfolds(athleteId, recordId)` and `useDeleteSkinfolds` in `frontend/src/hooks/athletes/useBodyComposition.ts` invalidating `["body-composition", id]`, `["anthropometry", id]`, `["growth-summary", id]`, `["ai", "phv", id]`; also add the missing `["growth-summary", id]` invalidation to `useCreateAnthropometry` in `frontend/src/hooks/athletes/useAnthropometry.ts`; do **not** touch `frontend/src/lib/persistAllowList.ts` — react-ui-engineer · haiku · low
- [X] T031 [US1] Add the two exits to `frontend/src/components/athletes/AnthropometryForm.tsx` after a successful save ("Guardar y terminar" = current behaviour; "Guardar y agregar pliegues" navigates to the capture route, hidden when the athlete is under 9 or when the interval blocks it — read `next_due_date` from `useBodyComposition`), and add a "Pliegues" marker plus "Agregar pliegues" / "Editar pliegues" row action in `frontend/src/components/athletes/AnthropometryHistory.tsx` (coach only) — react-ui-engineer · sonnet · medium
- [X] T032 [US1] US1 gate: run T018/T019 suites, `ruff check`, `npm run typecheck`, `npx vitest run src/components/athletes/body-composition src/routes/athletes`; fix regressions in `AnthropometryForm.test.tsx` / `AnthropometryHistory.test.tsx` — engineering-lead · opus · medium

**Checkpoint**: a coach can capture, replace and delete a skinfold set; parents never see it in the list.

---

## Phase 4: User Story 2 — Reading the change: sums, estimates and noise (Priority: P1)

**Goal**: the coach sees Σ4/Σ6 trends, per-site history, coach-only estimates, the noise-aware change and the Colombian reference context, plus the next-due date.

**Independent Test**: two synthetic sets ≥ 90 days apart with Σ4 +7.0 mm show "cambio real"; +6.9 mm shows "dentro del margen de medición"; estimates carry "estimado".

### Tests for User Story 2

- [X] T033 [P] [US2] Extend `backend/tests/routers/test_body_composition.py`: `GET …/body-composition` as coach returns `sets`, `series.sum4` (skipping incomplete points), `reading.sum_change_code`, `estimates_latest.margin_pct == 4`, `reference.side == "izquierdo"`; parent → 403; athlete without sets → `has_data=false` shape; `GET …/growth-summary` as coach includes `body_composition.sum4_mm`, as parent the block has **exactly** the five family keys `{has_data, latest_set_date, family_band, family_label, family_sentence}` (assert set equality) and no `band` key — qa-engineer · sonnet · medium
- [X] T034 [P] [US2] Write `frontend/src/components/athletes/body-composition/__tests__/BodyCompositionCard.test.tsx` and `BodyCompositionDetailDialog.test.tsx`: sparkline aria-labels, "estimado (±4 puntos)" label, change copy for `within_noise`/`up_real`/`none`, "suma incompleta" rendering, "falta tríceps" when estimate missing, next-due copy, jest-axe zero violations on the dialog — qa-engineer · sonnet · medium

### Implementation for User Story 2

- [X] T035 [US2] Add `GET /api/athletes/{athlete_id}/body-composition` to `backend/app/routers/body_composition.py` per `contracts/skinfolds-api.md` §4 (coach/admin only): load sets ascending with records (one query, `selectinload`), build `series` (`sum4`, `sum6`, `per_site`), call `build_reading` with velocity from `growth_summary` helpers and `reference_context` from T011, `estimates_latest`, `reference` metadata block; `has_data=false` shape when no sets — fastapi-architect · sonnet · medium
- [X] T036 [US2] Extend `build_growth_summary` in `backend/app/services/growth_summary.py` with `_build_body_composition(latest, previous, velocity, sex, settings)` returning `BodyCompositionSummary`, and project to `BodyCompositionFamilySummary` in `backend/app/routers/growth.py` when `current_user.role == parent` (construct the family model explicitly from `family_band`; never pass the coach model or the coach `band` through) — fastapi-architect · sonnet · medium
- [X] T037 [P] [US2] Add `useBodyComposition(athleteId, enabled)` (query key `["body-composition", athleteId]`, coach/admin only) to `frontend/src/hooks/athletes/useBodyComposition.ts` and extend the `GrowthSummary` type/Zod schema with `body_composition` in `frontend/src/types` and `frontend/src/schemas` — react-ui-engineer · haiku · low
- [X] T038 [US2] Build `frontend/src/components/athletes/body-composition/BodyCompositionCard.tsx` (coach): `StatCard` Σ4 with `Sparkline` (`values`, `ariaLabel`), Σ6 when available, "Masa libre de grasa (est.)" + "% grasa (est.) ±4 puntos" tier, change reading via `StatusBadge` (neutral for `within_noise`, coloured for real change) with the threshold, "Próxima toma de pliegues" date reusing the `NextMeasurementCard` wording, "Ver detalle por sitio" button, `EmptyState` when `has_data=false` ("Aún no hay pliegues registrados") and `ErrorState` — react-ui-engineer · sonnet · medium
- [X] T039 [US2] Build `frontend/src/components/athletes/body-composition/BodyCompositionDetailDialog.tsx` (focus trap, Escape, close button): per-site sparklines with "Omitido" gaps, sets table (date, Σ4, Σ6, estimates, caliper), reference context badges for triceps/subscapular with the caption "Referencia: escolares de Bogotá 2016, medida en lado izquierdo; contexto, no veredicto", "sin referencia para esta edad" state — react-ui-engineer · sonnet · medium
- [X] T040 [US2] Mount `BodyCompositionCard` in the coach composition of `frontend/src/components/athletes/growth/GrowthTab.tsx` after `MorphologyCard` (lazy import to keep the chunk small), passing `useBodyComposition` results — react-ui-engineer · haiku · low
- [X] T041 [US2] US2 gate: run T033/T034 suites, `ruff check`, `npm run typecheck`, `npx vitest run src/components/athletes`; verify `GET growth-summary` adds at most one query (extend the existing query-count assertion pattern); record pass/fail per command in `specs/046-body-composition-skinfolds/checklists/gates.md` — engineering-lead · opus · medium

**Checkpoint**: the coach answers "lean, fat or both?" from one screen with the noise reading.

---

## Phase 5: User Story 3 — Traffic light, escalation and referral note (Priority: P2)

**Goal**: coach-only verde/ámbar/rojo with reason and escalation prompt; rojo only for the combined pattern; neutral referral-note PDF.

**Independent Test**: scenarios A–D of the contract yield verde, verde, rojo, ámbar through the API; the referral PDF contains no `%`, no `mm` value, no institution.

### Tests for User Story 3

- [X] T042 [P] [US3] Extend `backend/tests/routers/test_body_composition.py` with API-level scenarios A–D (build records + sets through the ORM, assert `reading.band` and `band_reason_code`), referral note: coach → 200 PDF whose extracted text (pdfplumber, already a dependency) contains "no incluye un diagnóstico", the initials only, and matches neither `\d+\s*%` nor `\d+(?:[.,]\d+)?\s*mm`; parent → 403; no sets → 409 `no_skinfold_data`; audit event `skinfolds.referral_note_generated` — qa-engineer · sonnet · medium
- [X] T043 [P] [US3] Write `frontend/src/components/athletes/body-composition/__tests__/BodyCompositionBand.test.tsx`: band badge + reason for each `band_reason_code`, escalation prompt shown only for ámbar/rojo, `ReferralNoteButton` rendered only on rojo, jest-axe — qa-engineer · sonnet · low

### Implementation for User Story 3

- [X] T044 [P] [US3] Create `backend/templates/documents/pdf/body_composition_referral_note.html` (extends `documents/pdf/base/layout.html`) following `docs/21-body-composition/research-safeguards-referral.md` §4: initials, age band (e.g. "12–13 años"), sex, observed-pattern sentences rendered from `band_reason_code` and leg codes (Spanish, neutral), approximate weekly training hours from the 28-day window, the fixed paragraph "Esta nota NO incluye un diagnóstico…", the line "Se adjunta historial … solo con autorización expresa de la familia", contact placeholder; no numbers with `%` or `mm`, no institution names — parent-communicator · sonnet · medium
- [X] T045 [US3] Add `GET /api/athletes/{athlete_id}/body-composition/referral-note.pdf` to `backend/app/routers/body_composition.py` (coach/admin; 409 `no_skinfold_data`; WeasyPrint via the existing document service pattern in `backend/app/services/notification` / `routers/reports.py`; audit `skinfolds.referral_note_generated`) — fastapi-architect · sonnet · medium
- [X] T046 [US3] Add the band section to `frontend/src/components/athletes/body-composition/BodyCompositionCard.tsx`: `StatusBadge` with the band vocabulary from T016, `coach_reason` sentence, `legs_missing` line ("No evaluado: …"), escalation prompt (`ESCALATION_COPY` texts) for ámbar/rojo in an amber/red `Alert` that is coach-only by construction (component only receives coach data) — react-ui-engineer · sonnet · medium
- [X] T047 [P] [US3] Build `frontend/src/components/athletes/body-composition/ReferralNoteButton.tsx` (blob download like `InstructivoDownloadButton`, label "Generar nota de remisión", shown by the card only when `band === "rojo"`, error copy on 409) — react-ui-engineer · haiku · low
- [X] T048 [US3] US3 gate: run T042/T043 suites, `ruff check`, `npm run typecheck`, vitest for `body-composition`; confirm no rojo appears in any rising-Σ4 fixture; record pass/fail per command in `specs/046-body-composition-skinfolds/checklists/gates.md` — engineering-lead · opus · medium

**Checkpoint**: the coach gets a reasoned reading and a neutral note; families still see nothing from this story.

---

## Phase 6: User Story 4 — Family card and in-app notice (Priority: P2)

**Goal**: parents see a band capped at ámbar and one sentence, an explanatory notice, and no number anywhere (API, PDF, list); the monthly newsletter carries the same band and a short notice as fixed copy, only in the month of a set, never through the newsletter AI.

**Independent Test**: as a linked parent, the growth view shows the card with band + sentence and the notice; the anthropometry PDF and the list contain no skinfold value; an unlinked parent is denied.

### Tests for User Story 4

- [X] T049 [P] [US4] Extend `backend/tests/routers/test_body_composition.py` / `tests/routers/test_anthropometry_bmi.py`: parent list → every item `skinfolds is None`; parent growth-summary block equals the five keys and `family_sentence` contains no digit; for the rojo fixture (scenario C) `family_band == "ambar"` and the response body contains neither "Requiere acompañamiento profesional" nor "profesional de la salud"; for the reference-only fixture (scenario D) `family_band == "verde"`; with a newer fully declined attempt (scenario H) the parent block is unchanged; `GET /api/athletes/{id}/reports/anthropometry` (existing PDF) text contains neither "pliegue" nor `mm` values after a set exists; unlinked parent → 403/404 as today — qa-engineer · sonnet · medium
- [X] T050 [P] [US4] Write `frontend/src/components/athletes/body-composition/__tests__/FamilyBodyCompositionCard.test.tsx` and `FamilySkinfoldNotice.test.tsx`: renders label + sentence for each `family_band` (`verde`, `ambar`; the type rejects `rojo`), "Aún no hay datos suficientes para mostrar esta medida." when `has_data=false`, no numeral in the DOM (regex over `container.textContent`), notice collapsible with `aria-expanded`, jest-axe zero violations — qa-engineer · sonnet · low

### Implementation for User Story 4

- [X] T051 [P] [US4] Build `frontend/src/components/athletes/body-composition/FamilyBodyCompositionCard.tsx` mirroring `FamilyBandCards.tsx` (title "Composición corporal", `StatusBadge` family label, one sentence, info tooltip "Suma de pliegues cutáneos tomada por el entrenador; se muestra solo como banda"); never receives numeric props (type the props as `BodyCompositionFamilySummary`) — react-ui-engineer · sonnet · low
- [X] T052 [P] [US4] Build `frontend/src/components/athletes/body-composition/FamilySkinfoldNotice.tsx`: collapsible "¿Qué es la medición de pliegues?" with the approved addendum paragraph from `docs/21-body-composition/research-safeguards-referral.md` §5 (verbatim, full diacritics), shown for athletes aged ≥ 9 regardless of data — parent-communicator · sonnet · low
- [X] T053 [US4] Mount both components in the parent composition of `frontend/src/components/athletes/growth/GrowthTab.tsx` after `FamilyBandCards`, fed only from `useGrowthSummary().body_composition` (never from `useBodyComposition`) — react-ui-engineer · haiku · low
- [X] T076 [P] [US4] Write `backend/tests/services/training/test_newsletter_body_composition.py` (fails until T077–T078): block present only when a counted set's `evaluation_date` is in the newsletter month, absent in other months and when that month's only set is fully declined; block keys exactly `{family_label, family_sentence, notice_text}`; rojo fixture renders the ámbar copy; reference-only fixture renders the verde copy; rendered stage-log PDF text (pdfplumber) contains "Composición corporal" and the notice in the set's month and matches neither `\d+\s*%` nor `\d+(?:[.,]\d+)?\s*mm` nor "Requiere acompañamiento profesional"; the fake-provider request of `athlete_monthly_newsletter_v2` never contains `body_composition`, `family_band`, "pliegue" or any band code (spec FR-036, SC-003) — qa-engineer · sonnet · medium
- [X] T077 [US4] Add `_build_body_composition_block(db, athlete_id, year, month)` to `backend/app/services/training/newsletter_builder.py` as a **PDF-only** block next to `_build_anthropometry_block` (never in `email_blocks`, never in the AI context): reuses `build_reading` from `services/body_composition.py` for `family_band`, returns `{family_label, family_sentence, notice_text}` from `FAMILY_COPY`/`NEWSLETTER_NOTICE` only in the month of a counted set, else `None`; make sure the AI use case `backend/app/services/ai/use_cases/athlete_monthly_newsletter_v2.py` drops the key before building its context (explicit exclusion, prompt files untouched) — fastapi-architect · sonnet · medium
- [X] T078 [US4] Carry the block through `backend/app/services/training/stage_log_builder.py` and `_build_stage_log_pdf_context` in `backend/app/services/notification/athlete_newsletter_pdf.py`, and render a fixed-copy "Composición corporal" section in `backend/templates/documents/pdf/athlete_stage_log.html` (title, family label, sentence, notice; no numbers; omitted entirely when the block is `None`) — fastapi-architect · sonnet · low
- [X] T054 [US4] US4 gate: run T049/T050/T076, plus a repo grep proving no family-facing component imports `useBodyComposition`; `npm run typecheck`; record pass/fail per command in `specs/046-body-composition-skinfolds/checklists/gates.md` — engineering-lead · opus · low

**Checkpoint**: family surfaces are number-free by construction and by test.

---

## Phase 7: User Story 5 — Printable field guide (Priority: P3)

**Goal**: coach downloads a generic instructivo with the six illustrated sites and the protocol; parents cannot.

**Independent Test**: coach download returns a PDF listing six sites; parent request → 403; PDF text contains no athlete data.

### Tests for User Story 5

- [X] T055 [P] [US5] Extend `backend/tests/routers/test_body_composition.py`: `GET /api/body-composition/field-guide.pdf` coach → 200 `application/pdf`, `Cache-Control: private, max-age=86400`, text contains the six Spanish site names and "no contiene datos de ningún deportista"; parent → 403 — qa-engineer · sonnet · low

### Implementation for User Story 5

- [X] T056 [P] [US5] Create six Jinja SVG partials `backend/templates/documents/pdf/diagrams/skinfold_{triceps,biceps,subscapular,medial_calf,iliac_crest,supraspinale}.svg.jinja` reproducing the coordinates and labels of `frontend/src/lib/bodyComposition/siteDiagrams.ts` (copy the spec values into a small YAML/JSON under `backend/app/data/skinfold_sites.json` and render from it so both renderers share one source), black-and-white safe — react-ui-engineer · sonnet · medium
- [X] T057 [US5] Create `backend/templates/documents/pdf/skinfold_field_guide.html` (extends the base layout; sections: title "Instructivo de toma de pliegues cutáneos", pre-check checklist, one section per site with partial + "Dónde"/"Cómo", protocol callout box: dos lecturas, tolerancia, tercera lectura, rotar sitios, leer a los 2 segundos, lado derecho, footer "Este instructivo no contiene datos de ningún deportista") and add `GET /api/body-composition/field-guide.pdf` (coach/admin, 403 parent, cache header) to `backend/app/routers/body_composition.py` — technical-writer · sonnet · medium
- [X] T058 [P] [US5] Build `frontend/src/components/athletes/body-composition/FieldGuideDownloadButton.tsx` (same shape as `InstructivoDownloadButton`) and place it in the coach `BodyCompositionCard` header and in the capture page pre-check step — react-ui-engineer · haiku · low
- [X] T059 [US5] US5 gate: run T055, render the PDF locally (`DYLD_FALLBACK_LIBRARY_PATH` per project memory) and eyeball the six diagrams in grayscale; record pass/fail per command in `specs/046-body-composition-skinfolds/checklists/gates.md` — engineering-lead · opus · low

**Checkpoint**: the station has a printable guide consistent with the app.

---

## Phase 8: User Story 6 — AI explanation extended to body composition (Priority: P3)

**Goal**: the growth explanation covers body composition qualitatively for both audiences, with new blocking prechecks and versioned prompts; nothing numeric reaches the provider or the family.

**Independent Test**: offline lane shows the prompt leaf contains only allow-listed qualitative codes and the family text has no `%`/`mm`; golden lane stays ≥ 0.75.

### Tests for User Story 6

- [X] T060 [P] [US6] Write `backend/tests/anthro/test_context_body_composition.py` (fails until T063): leaf absent without a set; present with exactly the ten keys of `contracts/ai-body-composition-leaf.md` §1; the family-audience rendered block never contains `rojo`, `band_reason_code` values or "profesional"; `sanitize_insight_context` keeps them; adversarial leaf with `sum4_mm` is dropped; renderer block appears only when the leaf exists and contains no digit followed by `%`/`mm`; `fake.last_request` never contains `_mm`, `_pct`, `_kg` — qa-engineer · sonnet · medium
- [X] T061 [P] [US6] Write `backend/tests/anthro/test_prechecks_r13_r14.py` (fails until T064): R13 blocks family texts with "18 %", "18,5%", "32 mm"; passes coach texts and family texts without numbers; R14 blocks "dieta", "bajar de peso", "déficit calórico", "quemar grasa", "porcentaje de grasa 18" in both audiences; passes "alimentación variada" — qa-engineer · sonnet · low
- [X] T062 [P] [US6] Add hypothesis property #5 to `backend/tests/anthro/test_privacy_seam.py`: for random synthetic sets/readings, the rendered family prompt block and the fake-provider request contain no `\d+\s*(%|mm)` and no forbidden name — qa-engineer · sonnet · medium

### Implementation for User Story 6

- [X] T063 [US6] Extend `backend/app/services/ai/anthro/context.py`: `body_composition: dict | None` field on `AnalysisContext` (update the docstring's "verbatim from data-model" note to cite feature 046), `_build_body_composition_dict(latest_record, previous_record, reading)` producing the ten qualitative keys (incl. `family_band`; `band`/`band_reason_code` rendered only in the coach-audience block), `_render_body_composition_block(leaf)` appended to `context_blocks` only when present; add the ten keys to `ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS` in `backend/app/services/ai/context_builders.py` — fastapi-architect · sonnet · medium
- [X] T064 [P] [US6] Add `check_r13_body_comp_numeric_leak_to_family` and `check_r14_diet_or_weight_loss_language` to `backend/app/services/ai/anthro/prechecks.py` per `contracts/ai-body-composition-leaf.md` §3 (`must_block=True`, category `privacy` / `safety`, rule ids `R13`/`R14`, diacritic-insensitive lexicon), register them in `run_prechecks`, and describe them in the critic issue vocabulary — fastapi-architect · sonnet · medium
- [X] T065 [P] [US6] Create `backend/app/services/ai/anthro/prompts/anthropometry_analyst_v2.md` and `anthropometry_critic_v2.md` (copies of v1 plus the optional "Composición corporal" section: family = reassurance-first, process language, no numbers, no diet/weight talk; coach = pattern + suggested conversation; critic rule list + R13/R14), then flip the `AI_ANTHRO_PROMPT_VERSION` default to `v2` in `backend/app/config.py` keeping `v1` allowed — prompt-engineer · opus · high
- [X] T066 [P] [US6] Extend `backend/app/services/ai/anthro/fallback.py` with one body-composition sentence per audience when the leaf exists — family from `FAMILY_COPY[family_band]` (never a rojo sentence), coach from `COACH_REASON_COPY[band_reason_code]` — fastapi-architect · haiku · low
- [X] T067 [US6] Add golden cases `backend/evals/anthropometry_analyst/golden/case_013.json` … `case_018.json` per `contracts/ai-body-composition-leaf.md` §6 (family verde `expected_pubertal_gain`; coach rojo `energy_availability_pattern`; family ámbar `sum_up_unexplained`; coach `first_set` with two declined sites; family coach-side rojo → `family_band = ambar` forbidding "profesional de la salud"/"remisión"/"requiere acompañamiento"; family reference-only ámbar → `family_band = verde` forbidding "observación"/"percentil"), extend `forbidden_terms` of every family case with `%` and `mm` patterns, and document in `backend/evals/anthropometry_analyst/README.md` that `baseline.json` must be refreshed with `pytest -m golden` in a session with an AI key — prompt-engineer · sonnet · medium
- [X] T068 [US6] US6 gate: run `pytest tests/anthro` offline; if an AI key is available run `pytest -m golden tests/evals/test_anthropometry_analyst_eval.py` and refresh `baseline.json`; otherwise record the deferral explicitly in `docs/21-body-composition/qa.md` — engineering-lead · opus · medium

**Checkpoint**: explanations mention body composition qualitatively; R13/R14 block leaks; rollback = `AI_ANTHRO_PROMPT_VERSION=v1`.

---

## Phase 9: Polish & cross-cutting concerns

- [X] T069 [P] Run the `data-privacy-guard` audit over every new backend/frontend file: logs, `HTTPException.detail`, prompts, fixtures, PDFs, family projections; write findings to `specs/046-body-composition-skinfolds/privacy-audit.md` and fix blockers — data-privacy-guard · opus · high
- [X] T070 [P] Write `docs/21-body-composition/runbook-coach.md` (English doc, Spanish quoted copy): W0 checklist — caliper zero check, reference-block reading, two calibration sessions on adult volunteers with the TEM formula, private-space and second-adult practice, how to read verde/ámbar/rojo, when to generate the referral note; and `docs/21-body-composition/qa.md` skeleton listing the deferred lanes — technical-writer · sonnet · medium
- [X] T071 Run the full offline lanes: `cd backend && python -m pytest -q && ruff check`; `cd frontend && npm run typecheck && npm test && npm run build` (check the capture route chunk ≤ 150 KB gzipped in the build output); record pass/fail per command in `specs/046-body-composition-skinfolds/checklists/gates.md` — engineering-lead · opus · medium
- [X] T072 [P] Write `frontend/e2e/body-composition.spec.ts` (Playwright, isolated e2e stack helpers from feature 040): capture with a skip and a third reading, draft restore after reload, coach card shows Σ4 and "estimado", parent sees band + sentence only, interval message before 90 days; run it if the stack is available, otherwise mark deferred in `docs/21-body-composition/qa.md` — qa-engineer · sonnet · medium
- [X] T073 Run `pytest -m mysql tests/test_migration_skinfolds.py` against a local MySQL (docker compose) to prove the enum alter and downgrade; if no MySQL is available, state it as deferred in `docs/21-body-composition/qa.md` — devops-engineer · sonnet · medium
- [X] T074 [P] Update `docs/implementation-status.md` (new feature-046 step table), `docs/technical-notes.md` (dated entry: table, enums, prompt v2, R13/R14, interval rule), `docs/README.md` row 21 (as-built pointer) and `docs/21-body-composition/proposal.md` status line — technical-writer · sonnet · low
- [X] T079 Fix ámbar rule order in `contracts/body-composition-reading.md` §3 and `backend/app/services/body_composition.py`: evaluate `sum_up_velocity_low` before `sum_up_unexplained` (today it is unreachable); add a parametrised case to `backend/tests/services/test_body_composition_reading.py` (gates.md T017 note 1) — sports-science-advisor · sonnet · low
- [X] T080 Shared `load_reading(db, athlete, …)` helper in `backend/app/services/body_composition.py` (velocity, previous velocity, reference context, latest counted set / latest attempt) used by `GET …/body-composition`, `growth_summary._build_body_composition`, `newsletter_builder._build_body_composition_block` and the anthro AI pipeline; wire `body_composition_reading` into the anthro pipeline state (`services/ai/anthro/pipeline.py`, `routers/ai.py`) so the AI leaf is actually built (privacy-audit F6, F7; spec FR-029); keep the growth-summary query-count budget; tests prove coach detail, family card and newsletter agree and that a real pipeline run with a set produces the leaf — fastapi-architect · opus · high
- [X] T081 Skinfold capture draft expiry: `useFormDraft` target `skinfolds:{recordId}` expires after 24 h and is cleared on logout (spec US1 scenario 7 "same day"; privacy-audit F8), with vitest coverage; align FR-008 wording in spec.md — react-ui-engineer · sonnet · low
- [ ] T075 Post-deploy smoke (owner runs after merge/deploy): `/health`, `GET /api/body-composition/field-guide.pdf` as coach, `GET …/growth-summary` as a real parent showing `body_composition` without numbers; record in `docs/21-body-composition/qa.md` — release-manager · sonnet · low

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)** → no dependencies; T001–T003 in parallel.
- **Phase 2 (Foundational)** → after Phase 1; T004 → T005; T006 after T002/T003; T007/T010/T012 (tests) in parallel with T008/T009/T011; T013 after T004; T014–T016 in parallel; T017 gate last.
- **Phase 3 (US1)** → after T017. Backend T020 → T021 → T022 (T018 first). Frontend T023/T024/T025/T027 in parallel → T026 → T028 → T029 → T031; T030 in parallel; T032 gate.
- **Phase 4 (US2)** → after Phase 2; independent of Phase 3 for the backend (T035/T036 need only T009/T011/T013), frontend T038/T039 need T037; T040 after T038; T041 gate.
- **Phase 5 (US3)** → after Phase 4 (uses the reading and the card).
- **Phase 6 (US4)** → after T036 (growth-summary block); frontend independent of Phases 3–5; newsletter T076 → T077 → T078 need only T009 (reading + copy dicts).
- **Phase 7 (US5)** → after T023 (diagram spec); backend PDF independent of everything else.
- **Phase 8 (US6)** → after T009 (reading codes) and T013; independent of frontend phases.
- **Phase 9 (Polish)** → after every story the owner wants shipped.

### Story independence

US1 (capture) and US2 (reading) are both P1 and together form the MVP; each is testable alone (US2 via ORM-seeded sets). US3 depends on US2's card; US4 depends only on the growth-summary block (T036); US5 shares the diagram spec with US1; US6 is backend-only and can run in parallel with US3–US5.

## Parallel examples

```text
# Phase 2 after T004/T005:
T006 seed | T007 tests | T008 service | T010 tests | T011 reference | T012 mysql test | T014 FE foundations | T015 readings lib | T016 bands

# Phase 3 frontend after T014–T016:
T023 siteDiagrams | T024 SkinfoldSiteDiagram | T025 Precheck | T027 Review | T030 hooks   → then T026 → T028 → T029 → T031

# Cross-story after Phase 2:
US2 backend (T035, T036) | US6 backend (T063–T066) | US5 backend (T056, T057)
```

## Implementation strategy

1. **MVP** = Phases 1–4 (capture + reading). Stop, run the US1/US2 gates and the quickstart §1–§3; demo to the owner with a synthetic athlete.
2. **Increment 2** = Phase 6 (family card) then Phase 5 (traffic light + referral) — family surface first because it is the safeguard, then the coach's escalation.
3. **Increment 3** = Phase 7 (field guide) and Phase 8 (AI), in parallel.
4. **Close** = Phase 9; report explicitly which real-infrastructure lanes (`-m mysql`, `-m golden`, Playwright, post-deploy smoke) were not run.

## Agent assignment summary

| Model | Tasks | Rationale |
|---|---|---|
| **opus** | T005, T009, T017, T028, T032, T041, T048, T054, T059, T065, T068, T069, T071 | migration with MySQL enum alter, band classifier, wizard orchestration, prompt v2, privacy audit, integration gates |
| **sonnet** | all implementation, content and test tasks not listed elsewhere | bounded, contract-driven work |
| **haiku** | T001, T002, T016, T021, T030, T037, T040, T047, T053, T058, T066 | mechanical edits with an exact spec and a single file |

Effort hints: `high` on T003, T005, T008, T009, T023, T024, T028, T065, T069; `low` on the haiku tasks and small tests; `medium` elsewhere. Respect the owner's session-budget rule (no new agents past 80 % of the session budget) and the "no git stash / no destructive git" rule for subagents.

## Notes

- Constraints quoted from `data-model.md` are normative; when a task and a contract disagree, the contract wins and the task must be corrected in this file.
- Never add `body-composition` to `frontend/src/lib/persistAllowList.ts`.
- Never extend `templates/documents/pdf/anthropometry_report.html` with skinfolds (R9).
- Owner decisions C1–C8 in `docs/21-body-composition/proposal.md` §7–8 are closed; do not reopen them in task execution.
