---

description: "Task list for feature 040 — growth module redesign: one reference standard, decision-first tab, family view"
---

# Tasks: Growth module redesign

**Input**: Design documents from `/specs/040-growth-module-redesign/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md); audit in `docs/18-growth-module-redesign/proposal.md`

**Prerequisites**: plan.md, spec.md; contracts in `contracts/growth-summary-api.md`, `contracts/anthropometry-source.md`, `contracts/band-vocabulary.md`, `contracts/growth-tab-ui.md`, `contracts/who-lms-seed.md`

**Tests**: Included — the constitution (Principle II) makes tests part of the deliverable and every bug fix needs a regression test that fails first. Test tasks precede the implementation task they guard.

**Organization**: Phase 2 carries the "correctness first, no visual change" wave and the blocking schema work; then one phase per user story in spec priority order (US1 reference standard, US2 decision-first coach tab, US3 readable curve, US4 family view, US5 product coherence), then close-out.

## Format: `[ID] [P?] [Story] Description → agent · model`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1..US5 from spec.md
- **→ agent · model**: subagent from `.claude/agents/` and the model tier to launch it with. Policy from `.claude/agents/README.md`: bounded execution → `sonnet`; orchestration, integration review and reasoning-heavy authoring → `opus`. **Effort**: automatic — do not pass a reasoning-effort override; let each agent use its default.

## Path Conventions

Web app: `backend/app/…`, `backend/tests/…`, `backend/scripts/…`, `backend/alembic/versions/…`, `frontend/src/…`, `frontend/e2e/…`, `frontend/scripts/…`.

## Agent roster for this feature

| Agent | Model | Used for |
|---|---|---|
| `engineering-lead` | opus | Wave coordination (Phases 2, 4–7), integration review, PR description |
| `data-platform-lead` | opus | Coordination of the reference-standard wave (Phase 3) and the recompute rollout |
| `fastapi-architect` | sonnet | Routers, schemas, services, seed/backfill scripts, PDF builder, AI use case |
| `database-architect` | sonnet | Alembic migration, WHO seed rows, `-m mysql` verification |
| `react-ui-engineer` | sonnet (×2 in parallel in Phases 4–5) | Components, hooks, libs, page wiring |
| `qa-engineer` | sonnet | pytest / vitest / jest-axe / MSW / Playwright, build gate script |
| `data-privacy-guard` | sonnet | Mandatory privacy audit (checklist) |
| `parent-communicator` | sonnet | Family-mode copy review |
| `technical-writer` | sonnet | Docs updates |
| `release-manager` | sonnet | Post-deploy smoke, prod recompute confirmation |

---

## Phase 1: Setup

**Purpose**: Branch, baseline and skeletons so every wave starts from the same facts.

- [X] T001 Verify the working branch is `feat/040-growth-module-redesign` and record the baseline build numbers from `research.md` R-08 (entry 336.68 kB gzip; statically imported recharts chunk 107.39 kB gzip; WHO JSON inside entry) at the top of `specs/040-growth-module-redesign/checklists/build-baseline.md` → engineering-lead · opus
- [X] T002 [P] Create the folder skeleton `frontend/src/components/athletes/growth/` with an empty `index.ts` barrel and `__tests__/` directory, and `backend/app/data/who_lms/` with a placeholder `README.md` per `contracts/who-lms-seed.md` → react-ui-engineer · sonnet
- [X] T003 [P] Add `frontend/scripts/check-chart-chunk.sh` that fails when `frontend/dist/index.html` module-preloads, or the entry `dist/assets/index-*.js` statically imports, the chunk containing the string `recharts-wrapper`, or when the entry chunk contains `WHO 2007 Growth Reference`; wire it as `npm run check:chunks` in `frontend/package.json` (expected to FAIL until Phase 7) → qa-engineer · sonnet

---

## Phase 2: Foundational — correctness first (no visual change) + blocking schema

**Purpose**: Fix the defects the audit found regardless of the redesign, align the band vocabulary, and land the additive column every later story needs.

**⚠️ CRITICAL**: T004–T015 must be green before any user-story phase starts.

- [X] T004 Regression test (fails on current code): parent view classifies the **latest** record — render `MyAthleteDetailPage` with three MSW records newest-first whose newest band differs from the oldest and assert the `NutritionalClassification` label matches the newest, in `frontend/src/routes/parents/__tests__/MyAthleteDetailPage.growth.test.tsx` → qa-engineer · sonnet
- [X] T005 Fix `frontend/src/routes/parents/MyAthleteDetailPage.tsx` lines 195–198 and 405 to use `records[0]` (API is newest-first) for `phvAgeMonths` and the classification record; T004 must pass → react-ui-engineer · sonnet
- [X] T006 [P] Extend `frontend/src/lib/growth/bands.ts` to the `NutritionalStatus`-keyed vocabulary of `contracts/band-vocabulary.md` (`coachLabel`, `familyLabel`, `narrative`, `tone`, `referral`), keep `getBandSpec` working for existing callers via a mapping, and make `classifyBand(indicator, z)` indicator-aware (height: `1 < z ≤ 2` → `talla_adecuada`, `talla_alta` only above +2); update `frontend/src/lib/growth/bands.test.ts` with 10 z values per indicator (parity with backend cut-offs) → react-ui-engineer · sonnet
- [X] T007 [P] Update `frontend/src/hooks/athletes/useGrowthMetrics.ts` to return the new band keys and add the indicator argument to its internal classification; fix its consumers' tests (`NutritionalClassification.test.tsx`, `PercentileInterpretationBlock.test.tsx`, `PercentileCurves.test.tsx`) → react-ui-engineer · sonnet
- [X] T008 [P] Remove the numeric maximum-heart-rate estimate from `frontend/src/components/athletes/TrainingReadiness.tsx` (rules `max-hr` read "Sin test de FC máxima — no se estima ni se usa para zonas"), and update `frontend/src/components/athletes/TrainingReadiness.test.tsx` to assert no `lpm` text renders → react-ui-engineer · sonnet
- [X] T009 [P] Extract `STATUS_META` (measurement status → tone/labels) from `frontend/src/components/dashboard/MeasurementAlerts.tsx` into `frontend/src/lib/measurementStatus.ts` and re-import it there; add `frontend/src/lib/measurementStatus.test.ts` → react-ui-engineer · sonnet
- [X] T010 [P] Decouple `frontend/e2e/history.spec.ts` (lines 34, 90–93) from the auto-select behaviour: click the `Crecimiento` tab explicitly before asserting on `growth-charts` → qa-engineer · sonnet
- [X] T011 [P] Characterization tests for behaviours that must survive the chart split — legend toggle hides a series, bio-age toggle relabels ticks and is coach-only, PHV/PWV marker placement by indicator and sex, sr-only table rows equal the athlete points, PNG export file name contains no name — in `frontend/src/components/athletes/PercentileCurves.characterization.test.tsx` → qa-engineer · sonnet
- [X] T012 Alembic migration `backend/alembic/versions/<id>_growth_source_on_anthropometry.py` (down-revision = current head, verify with `alembic heads`) adding nullable `growth_source Enum('WHO','CDC')` to `anthropometric_records`; downgrade drops it → database-architect · sonnet
- [X] T013 Add `growth_source: Mapped[GrowthSource | None]` to `backend/app/models/anthropometry.py` and `growth_source: str | None = None` to `AnthropometryOut` in `backend/app/schemas/anthropometry.py`; extend `backend/tests/routers/test_anthropometry_bmi.py` to assert the field is present and `null` for legacy rows → fastapi-architect · sonnet
- [X] T014 [P] Add `growth_source?: "WHO" | "CDC" | null` to `frontend/src/types/anthropometry.types.ts` and to the anthropometry Zod schema in `frontend/src/schemas/` (find the existing anthropometry schema file) → react-ui-engineer · sonnet
- [X] T015 Run the offline lane (`cd backend && .venv/bin/python -m pytest -q`) and `cd frontend && npm run typecheck && npx vitest run src/lib src/components/athletes src/routes/parents`; all green → qa-engineer · sonnet

**Checkpoint**: Defects G-02, G-03, G-04 closed with regression tests; column available; characterization tests pinned.

---

## Phase 3: User Story 1 — Every growth number comes from one reference standard (Priority: P1) 🎯 MVP

**Goal**: WHO 2007 is the only reference on the server; stored Z/percentile/band are what every surface shows; historical rows recomputed once with a band-change report.

**Independent Test**: Record a measurement; tab tile, curve hover, table and family PDF show one Z/percentile/band with the caption "OMS 2007 · Res. 2465/2016"; recompute on a copy leaves raw values untouched, is a no-op on re-run and emits the band-change list.

### Tests for User Story 1

- [X] T016 [P] [US1] Seed tests in `backend/tests/services/test_growth_seed.py`: WHO row counts (168/168/60 per sex), idempotency, and parity of 6 (indicator, sex, age) L/M/S triples with `frontend/src/data/growth-reference-who.json` to 6 decimals (read the JSON from the repo path) → qa-engineer · sonnet
- [X] T017 [P] [US1] Recompute tests in `backend/tests/scripts/test_backfill_anthropometry.py`: a CDC-tagged row is switched to WHO values and `growth_source='WHO'`; raw columns unchanged; weight Z is `NULL` above 120.5 months; second run recomputes 0; band-change report shape (ids only); caplog contains no `first_name`/`birth_date` → qa-engineer · sonnet
- [X] T018 [P] [US1] POST tests in `backend/tests/routers/test_anthropometry_bmi.py`: new record stores `growth_source='WHO'`, height/BMI Z match a hand-computed WHO value (±0.02), weight fields `NULL` for a 14-year-old, populated for an 8-year-old → qa-engineer · sonnet
- [X] T019 [P] [US1] Frontend parity test `frontend/src/lib/growth/lms.parity.test.ts`: `zScoreFromLMS` on the same 6 fixture points equals the backend values recorded as constants in the test (synthetic fixtures, no minors) → qa-engineer · sonnet

### Implementation for User Story 1

- [X] T020 [US1] Write `backend/scripts/export_who_lms_csv.py` (reads `frontend/src/data/growth-reference-who.json`, writes `backend/app/data/who_lms/who_{height_for_age,bmi_for_age,weight_for_age}.csv` with columns `sex,age_months,L,M,S`, sorted, deterministic) and commit the generated CSVs plus the provenance `README.md` per `contracts/who-lms-seed.md` → fastapi-architect · sonnet
- [X] T021 [US1] Extend `backend/app/seed_growth_data.py` with the WHO sources (same dialect-aware upsert, `source=GrowthSource.WHO`); T016 passes → database-architect · sonnet
- [X] T022 [US1] Switch `backend/app/routers/anthropometry.py::create_anthropometry` to `source=GrowthSource.WHO`, null weight Z/percentile when `age_months > 120.5`, persist `growth_source`; T018 passes → fastapi-architect · sonnet
- [X] T023 [US1] Add `recompute_to_source(session, target=GrowthSource.WHO)` to `backend/app/scripts/backfill_anthropometry.py` per `contracts/anthropometry-source.md` §3 (selection, writes, never-write list, stdout summary, `./data/growth_band_changes_<YYYYMMDD>.json`), call it from `run()` after the existing pass; T017 passes → fastapi-architect · sonnet
- [X] T024 [P] [US1] Switch `backend/app/services/training/growth_chart_builder.py` to `GrowthSource.WHO` and omit the weight chart when the athlete is older than 10 y; update its tests under `backend/tests/` (find `growth_chart_builder` tests) → fastapi-architect · sonnet
- [X] T025 [P] [US1] Make `frontend/src/hooks/athletes/useGrowthMetrics.ts` prefer stored Z/percentile/band **only** when `record.growth_source === "WHO"`, and expose `source: "stored" | "computed"` so callers can show the "Referencia anterior — pendiente de actualizar" caption; update `useGrowthMetrics` tests → react-ui-engineer · sonnet
- [X] T026 [US1] Make the current `frontend/src/components/athletes/PercentileCurves.tsx` tooltip and sr-only table read the record's stored `z`/`percentile`/band when available (WHO) instead of recomputing, and show the source caption in `NutritionalClassification.tsx` (caption text per `contracts/band-vocabulary.md`); T011 characterization tests still pass → react-ui-engineer · sonnet
- [X] T027 [US1] Run the migration + seed + recompute once against a real MySQL `_test` database (`TEST_DATABASE_URL`, name ends in `_test`) with `pytest -m mysql` for the migration/backfill tests, and record row counts and the band-change summary (ids only) in `specs/040-growth-module-redesign/checklists/reference-standard.md` → database-architect · sonnet
- [X] T028 [US1] Regenerate one family newsletter PDF for a **test** athlete in the dev stack (`docker compose up`, `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` locally) and confirm the growth chart label reads OMS 2007 and the weight chart is absent above 10 y; note the result in `checklists/reference-standard.md` → qa-engineer · sonnet
- [X] T029 [US1] Wave review: verify SC-001 manually per `quickstart.md` §1 (tile = hover = table = PDF for one record) and sign the checklist → data-platform-lead · opus

**Checkpoint**: One standard everywhere; recompute proven idempotent; PDF aligned. Deployable on its own.

---

## Phase 4: User Story 2 — The coach reads the decision before the evidence (Priority: P2, second P1 in spec)

**Goal**: The growth tab opens on stage, velocity, two bands, next-measurement status and alerts, followed by a compact rule block; served by a new growth-summary endpoint.

**Independent Test**: On a 1024 px tablet the five readings and alerts are visible without scrolling; the five coach questions are answerable from the tab; parent of another athlete gets 403 on the endpoint.

### Tests for User Story 2

- [X] T030 [P] [US2] Service tests `backend/tests/services/test_growth_summary.py`: velocity cm/month→cm/year, `interval_short` < 30 days suppresses `rapid_growth`, expected ranges by stage and sex, `months_from_phv` sign, `phase_changed`, `approaching_circa`, no-records and one-record shapes → qa-engineer · sonnet
- [X] T031 [P] [US2] Router tests `backend/tests/routers/test_growth_summary.py` — the 11 cases of `contracts/growth-summary-api.md` (coach 200, admin 200, own parent 200, other parent 403, 404, never, one record, short interval, rapid growth, circa alert + 30-day interval, privacy invariant) → qa-engineer · sonnet
- [X] T032 [P] [US2] Frontend tests: `frontend/src/hooks/athletes/useGrowthSummary.test.tsx` (MSW happy/403/network error), `frontend/src/lib/growth/rules.test.ts` (rulesFor / differsFromDefault, no `lpm` text), component tests `GrowthStatusRow.test.tsx`, `NextMeasurementCard.test.tsx`, `GrowthAlerts.test.tsx`, `Sparkline.test.tsx` under `frontend/src/components/athletes/growth/__tests__/` → qa-engineer · sonnet

### Implementation for User Story 2

- [X] T033 [P] [US2] Create `backend/app/schemas/growth.py` with `GrowthSummaryOut`, `GrowthVelocity`, `MeasurementDue`, `LatestBands`, `BandReading` per `data-model.md` §3 → fastapi-architect · sonnet
- [X] T034 [P] [US2] Create `backend/app/services/growth_summary.py` (pure derivation over the two latest records, `EXPECTED_VELOCITY_CM_YEAR` constants from `research.md` R-05, docstrings); T030 passes → fastapi-architect · sonnet
- [X] T035 [US2] Add `GET /athletes/{athlete_id}/growth-summary` to `backend/app/routers/growth.py` guarded by `verify_athlete_access`, one `ORDER BY evaluation_date DESC LIMIT 2` query; T031 passes → fastapi-architect · sonnet
- [X] T036 [P] [US2] Frontend data layer: `frontend/src/types/growth.types.ts`, `frontend/src/schemas/growth.schemas.ts` (Zod mirror), `frontend/src/api/growth.ts::getGrowthSummary`, `frontend/src/hooks/athletes/useGrowthSummary.ts` (query key `["growth-summary", id]`, **not** added to `persistAllowList`), MSW `frontend/src/test/msw/growthSummaryHandlers.ts` registered where the other handlers are → react-ui-engineer · sonnet
- [X] T037 [P] [US2] Create `frontend/src/lib/growth/rules.ts` (`TRAINING_RULES`, `rulesFor`, `differsFromDefault`) per `data-model.md` §5, porting the nine rules from `TrainingReadiness.tsx` without the heart-rate number → react-ui-engineer · sonnet
- [X] T038 [P] [US2] Build `Sparkline.tsx` (inline SVG, 12 points, accent last point) and `GrowthStatusRow.tsx` (4 × `shared/StatCard` with `tone`/`badge`, copy per `contracts/growth-tab-ui.md`) in `frontend/src/components/athletes/growth/` → react-ui-engineer · sonnet
- [X] T039 [P] [US2] Build `NextMeasurementCard.tsx` (uses `lib/measurementStatus.ts`) and `GrowthAlerts.tsx` (shadcn `Alert` rows, dashboard wording) in `frontend/src/components/athletes/growth/` → react-ui-engineer · sonnet
- [X] T040 [US2] Refactor `frontend/src/components/athletes/TrainingReadiness.tsx` to consume `lib/growth/rules.ts`, render only differing rules as `StatusBadge` chips with a `Collapsible` "Ver todas las reglas", take alerts from the summary, drop the athlete-name chip; update `TrainingReadiness.test.tsx` → react-ui-engineer · sonnet
- [X] T041 [US2] Create `frontend/src/components/athletes/growth/GrowthTab.tsx` (mode-aware container: alerts → status row → next measurement → rules → existing `GrowthCharts` as a temporary chart slot → `MorphologyCard` → `PHVExplanationCard` → `AnthropometryHistory` compact → `ResearchReferences`), with loading/empty/error states per contract and `data-testid="growth-tab"` → react-ui-engineer · sonnet
- [X] T042 [US2] Wire `frontend/src/routes/athletes/AthleteDetailPage.tsx`: `React.lazy` import of `GrowthTab` with `Suspense` skeleton and `key={athlete.id}`, replacing the inline growth block; keep the tab button; leave auto-select for Phase 7 → react-ui-engineer · sonnet
- [X] T043 [US2] jest-axe test `frontend/src/components/athletes/growth/__tests__/GrowthTab.a11y.test.tsx` (coach mode, with records and without) — zero violations → qa-engineer · sonnet
- [X] T044 [US2] Playwright `frontend/e2e/growth.spec.ts` part 1: login as coach, open `/athletes/:id?tab=growth`, assert the five readings are visible in the initial viewport at 1024×768, expand "Ver todas las reglas" → qa-engineer · sonnet
- [X] T045 [US2] Wave review: SC-002 on tablet and phone viewports, SC-003 dry-run of the five questions, sign `checklists/coach-tab.md` → engineering-lead · opus

**Checkpoint**: Decision-first tab live for coaches with the old chart still embedded.

---

## Phase 5: User Story 3 — One growth curve that can actually be read (Priority: P2)

**Goal**: A windowed, tokenized percentile chart with a visible table view, detail toggle, axis toggle (coach), PHV/PWV marker and export, replacing `GrowthCharts`/`PercentileCurves`.

**Independent Test**: For three measurements over 14 months the points span ≥ 60 % of the plot; hover, table and tiles agree; "Detalle" adds intermediate lines; biological axis puts PHV at zero; export file name has no name.

### Tests for User Story 3

- [X] T046 [P] [US3] `frontend/src/lib/growth/window.test.ts`: window bounds (−24/+36 months, clamped to 61.5–228.5), full-range switch, whole-year ticks, `niceTicks` steps 1/2/5/10, reference-row filtering → qa-engineer · sonnet
- [X] T047 [P] [US3] Component tests `PercentileChart.test.tsx`, `PercentileToolbar.test.tsx`, `PercentileTable.test.tsx`, `GrowthCurveSection.test.tsx` under `frontend/src/components/athletes/growth/__tests__/` covering: indicator list by age (no Peso > 10 y), axis toggle hidden for BMI and for parents, detail toggle, table rows = records with stored values, export button, `role="img"` label → qa-engineer · sonnet

### Implementation for User Story 3

- [X] T048 [P] [US3] Create `frontend/src/lib/growth/window.ts` (`computeAgeWindow`, `yearTicks`, `niceTicks`, `filterReferenceRows`); T046 passes → react-ui-engineer · sonnet
- [X] T049 [P] [US3] Build `PercentileToolbar.tsx` (shadcn `ToggleGroup`s ≥ 48 px: indicator, axis (coach), range, view; `Button`s: Detalle, Descargar PNG) with copy per `contracts/growth-tab-ui.md` → react-ui-engineer · sonnet
- [X] T050 [US3] Build `PercentileChart.tsx`: recharts `ComposedChart` with `XAxis type="number" domain={[min,max]} allowDataOverflow`, P3–P97 `Area` band in `var(--color-light-gray)`, P50 in `var(--color-charcoal)`, P3/P97 in `var(--color-mid-gray)`, optional P10/P25/P75/P90, athlete line `var(--color-primary)` with 2 px surface-ring dots, solid 1 px grid `var(--color-border-gray)`, PHV/PWV `ReferenceLine`, tooltip with stored values, `role="img"` + aria-label, dynamic `import("@/data/growth-reference-who.json")`; port `getMaturationMarker`, `INDICATOR_PHV_NOTES`, bio-age tick formatter from `PercentileCurves.tsx` → react-ui-engineer · sonnet
- [X] T051 [P] [US3] Build `PercentileTable.tsx` (shadcn `Table`: mes-año, edad, valor, Z, percentil, banda badge) and `GrowthCurveSection.tsx` (composes toolbar + chart/table + `PercentileInterpretationBlock` + PHV note; owns the `html-to-image` export with the existing file-name pattern) → react-ui-engineer · sonnet
- [X] T052 [US3] Replace the temporary `GrowthCharts` slot in `GrowthTab.tsx` with `GrowthCurveSection`; delete `frontend/src/components/athletes/GrowthCharts.tsx`, `PercentileCurves.tsx`, their tests and `PercentileCurves.a11y.test.tsx`; re-home the surviving assertions from T011 into the new component tests; update `frontend/e2e/history.spec.ts` to the new `growth-curve` test id → react-ui-engineer · sonnet
- [X] T053 [US3] Fix diacritics in surviving copy ("Cronológica", "Biológica", "Interpretación", "Detalles técnicos") in `PercentileInterpretationBlock.tsx` and the new toolbar; grep gate `grep -rn "Cronologica\|Biologica\|tecnicos" frontend/src` returns nothing → react-ui-engineer · sonnet
- [X] T054 [US3] Playwright `frontend/e2e/growth.spec.ts` part 2: switch Talla → IMC, toggle Biológica, open Tabla and compare one row with the tile, click Descargar PNG and assert the download name matches `/^crecimiento-.*\.png$/` → qa-engineer · sonnet
- [X] T055 [US3] Wave review: SC-008 (as amended 2026-09-04: ≥ 18 % width and ≥ 2× the retired chart on a three-measurement/14-month fixture, ≥ 60 px between consecutive points at 1024 px) measured against the shipped `lib/growth/window.ts`, tokens audit (`grep -n "#[0-9a-f]\{6\}" frontend/src/components/athletes/growth/` returns nothing), sign `checklists/coach-tab.md` → engineering-lead · opus

**Checkpoint**: The old chart components are gone; one readable curve with table view.

---

## Phase 6: User Story 4 — Families see growth in family language (Priority: P2)

**Goal**: Parent mode of `GrowthTab` with narrative cards, simplified chart, read-only AI explanation, no numerals or clinical labels, always the latest measurement.

**Independent Test**: As a parent of an athlete whose latest band differs from the oldest: cards reflect the latest; no `Z=`/`P\d+` text; no "Fuentes bibliográficas"; AI card read-only.

### Tests for User Story 4

- [X] T056 [P] [US4] `frontend/src/components/athletes/growth/__tests__/GrowthTab.parent.test.tsx`: latest record drives cards; page text has no `/Z=|P\d{1,2}\b|offset/i`; no bibliography; axis/detail toggles absent; jest-axe zero violations in parent mode → qa-engineer · sonnet
- [X] T057 [P] [US4] Backend tests for the coach-audience explanation in `backend/tests/` (find the existing PHV explainer tests): `use_case="phv_explanation_coach"` cached separately from the family one, prompt output mentions velocity in cm/año, guardrails still scrub names → qa-engineer · sonnet

### Implementation for User Story 4

- [X] T058 [P] [US4] Build `FamilyStageCard.tsx` (reuse `phvParentMessage` copy from `MyAthleteDetailPage.tsx`, evaluated month-year) and `FamilyBandCards.tsx` (two cards: "Estatura para su edad", "Peso para su estatura" with tooltip; `familyLabel` + narrative + `StatusBadge`) in `frontend/src/components/athletes/growth/` → react-ui-engineer · sonnet
- [X] T059 [P] [US4] Add a `preset="family"` to `PercentileChart.tsx`/`GrowthCurveSection.tsx` (athlete line, P50, P3–P97 band only; no axis/detail toggles; legend "Deportista / Promedio / Rango esperado"; caption per contract) and pass `hideAdvanced` to `PercentileInterpretationBlock` in parent mode → react-ui-engineer · sonnet
- [X] T060 [P] [US4] Backend: add `audience: Literal["family","coach"]` to `PHVExplainer.run` in `backend/app/services/ai/use_cases/phv_explainer.py`, register `phv_explanation_coach_v1.md` in `backend/app/services/ai/prompts/registry.py` (coach-addressed, includes velocity cm/año and months from PHV, ≤ 120 words, same guardrails), map to `use_case="phv_explanation_coach"`, expose `?audience=` on the existing PHV explanation endpoints in `backend/app/routers/ai.py` (coach/admin only for `coach`); T057 passes → fastapi-architect · sonnet
- [X] T061 [US4] Frontend: `frontend/src/hooks/ai/usePHVExplanation.ts` and `frontend/src/api/ai.ts` take `audience`; `frontend/src/components/ai/PHVExplanationCard.tsx` gains the title "Explicación PHV" and passes `audience` by mode → react-ui-engineer · sonnet
- [X] T062 [US4] Wire parent mode: `GrowthTab mode="parent"` renders stage card → band cards → family curve → AI (read-only) → `AnthropometryHistory mode="parent"`; no `TrainingReadiness`, `MorphologyCard`, `MaturationTimeline`, `ResearchReferences`; replace the inline growth block in `frontend/src/routes/parents/MyAthleteDetailPage.tsx` with the lazy `GrowthTab` (`key={athlete.id}`) → react-ui-engineer · sonnet
- [X] T063 [US4] Review every family-facing string introduced in Phases 4–6 (`bands.ts` family labels/narratives, `FamilyStageCard`, `FamilyBandCards`, family chart caption, coach/family AI prompt) for español neutro, diacritics and non-judgmental tone; apply edits directly and list them in `specs/040-growth-module-redesign/checklists/family-copy.md` → parent-communicator · sonnet
- [X] T064 [US4] Playwright `frontend/e2e/growth-parent.spec.ts`: login as the seeded parent, open the child, assert latest-record cards, absence of numerals/bibliography, AI card without a generate button → qa-engineer · sonnet
- [X] T065 [US4] Mandatory privacy audit of the feature (growth components, growth-summary endpoint, recompute report, export names, logs, AI audience prompt) with findings and fixes recorded in `specs/040-growth-module-redesign/checklists/privacy.md`; any HIGH finding blocks the phase → data-privacy-guard · sonnet

**Checkpoint**: Families see the family view; audit signed.

---

## Phase 7: User Story 5 — The tab belongs to the product (Priority: P3)

**Goal**: Shared components and tokens everywhere on the tab, maturation timeline, no auto-jump, growth assets lazy (build gate green).

**Independent Test**: Athlete page opens on "Info general"; `npm run check:chunks` passes; visual review against the design-system checklist; timeline has a text alternative.

### Tests for User Story 5

- [X] T066 [P] [US5] Tests `MaturationTimeline.test.tsx` (three stages, today marker by stage, PHV age caption, text alternative) and updated `MorphologyCard.test.tsx` / `PHVBadge.test.tsx` for the `StatCard`/`StatusBadge` rendering, under `frontend/src/components/athletes/` and `growth/__tests__/` → qa-engineer · sonnet
- [X] T067 [P] [US5] Page tests: `frontend/src/routes/athletes/__tests__/AthleteDetailPage.tabs.test.tsx` — with records and no `?tab`, "Info general" is active; top tiles show stage, talla + P, velocity, next-measurement badge from the summary; `?tab=growth` still works → qa-engineer · sonnet

### Implementation for User Story 5

- [X] T068 [P] [US5] Build `MaturationTimeline.tsx` (SVG/CSS, Pre → Circa → Post, today's position from `maturity_offset`, caption "Offset ±x.x · PHV estimado a los N años", `aria-label` text alternative) and insert it in coach mode of `GrowthTab.tsx` after the curve → react-ui-engineer · sonnet
- [X] T069 [P] [US5] Refactor `frontend/src/components/athletes/MorphologyCard.tsx` tiles onto `shared/StatCard` (copy unchanged) and `frontend/src/components/athletes/PHVBadge.tsx` onto `StatusBadge` (Pre = neutral, Circa = warning, Post = success); delete the PHV colour maps in `TrainingReadiness.tsx` and `AthleteDetailPage.tsx` → react-ui-engineer · sonnet
- [X] T070 [US5] In `frontend/src/routes/athletes/AthleteDetailPage.tsx` and `frontend/src/routes/parents/MyAthleteDetailPage.tsx`: delete the page-local `StatCard`, render the top tiles with `shared/StatCard` fed by `useGrowthSummary` (stage, talla + P, velocidad, próxima medición badge), remove the auto-select-growth effect and `hasSetInitialTab`; T067 passes → react-ui-engineer · sonnet
- [X] T071 [US5] Run `npm run build && npm run check:chunks`; if the entry still imports the recharts chunk, lazy-wrap the remaining static importers reachable from the entry (`frontend/src/components/newsletter/StageLogView.tsx` → `EffortProfile`, `frontend/src/components/athletes/ai/PanoramaView.tsx` → `MiniSparkline`) with `React.lazy` + `Suspense`; repeat until the gate passes; record final sizes in `checklists/build-baseline.md` (entry gzip, growth chunk gzip ≤ 150 kB) → react-ui-engineer · sonnet
- [X] T072 [US5] Full frontend gate: `npm run typecheck`, `npx vitest run`, jest-axe suites, `npx playwright test e2e/growth.spec.ts e2e/growth-parent.spec.ts e2e/history.spec.ts e2e/anthropometry.spec.ts e2e/target-size.spec.ts` → qa-engineer · sonnet
- [X] T073 [US5] Integration review of Phases 2–7 against the constitution table in `plan.md` and the design-system rules (033 FR-003, dataviz non-negotiables), with fixes delegated back to the owning worker; sign `checklists/integration-review.md` → engineering-lead · opus

**Checkpoint**: All five stories complete; gates green.

---

## Phase 8: Polish & close-out

- [X] T074 [P] Update `docs/implementation-status.md` (feature 040 step table) and `docs/technical-notes.md` (dated entry: WHO switch, `growth_source`, recompute report, growth-summary contract, lazy growth chunk with measured before/after sizes, removed components) → technical-writer · sonnet
- [X] T075 [P] Add a "Superseded by docs/18 / specs/040" banner to `docs/04-percentiles/workflow.md`, mark `docs/06-parents/workflow.md` line 26 (family mode) as done, and update `docs/README.md` row 04/18 pointers → technical-writer · sonnet
- [X] T076 [P] Refresh the CLAUDE.md managed block and the "Active feature" paragraph via `/speckit-agent-context-update` (plan path `specs/040-growth-module-redesign/plan.md`) → technical-writer · sonnet
- [X] T077 Run `quickstart.md` end to end (§1–§6) on the dev stack and tick each section in `specs/040-growth-module-redesign/checklists/quickstart-run.md` → qa-engineer · sonnet
- [ ] T078 Post-merge/deploy: confirm the Render startup log shows the WHO seed and the recompute summary (counts only), smoke `GET /health` and `GET /api/athletes/{id}/growth-summary` with a coach token, open the athlete page on a real Android device and confirm the growth chunk loads on tap; hand the band-change report (ids) to the coach for review before the next newsletter cycle → release-manager · sonnet
- [X] T079 Write the PR description (Conventional Commits title in English type + español latino description, no AI-tool mention) summarising the five stories, the recompute impact and the measured bundle change → engineering-lead · opus

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** → **Foundational (Phase 2)**: T004→T005; T006→T007; T012→T013→T014; T011 independent; T015 last.
- **US1 (Phase 3)** depends on Phase 2 (column, band vocabulary). T020→T021→T016 green; T022 needs T013; T023 needs T021+T022; T024 needs T021; T025/T026 need T006/T007 and T014; T027 needs T012, T021, T023; T028 needs T024; T029 last.
- **US2 (Phase 4)** depends on Phase 2 and on T022/T023 (stored WHO values feed `latest`). T033→T034→T035; T036 needs T033 (contract); T037 independent; T038/T039 need T036 types; T040 needs T037; T041 needs T038–T040; T042 needs T041; T043/T044 need T042; T045 last.
- **US3 (Phase 5)** depends on US2's `GrowthTab` (T041). T048→T050; T049/T051 parallel with T050; T052 needs T049–T051 and T011 (characterization) ; T053 after T052; T054 after T052; T055 last.
- **US4 (Phase 6)** depends on US3 (family chart preset) and T006 (family labels). T058/T059/T060 parallel; T061 needs T060; T062 needs T058, T059, T061; T063 after T062; T064/T065 after T062.
- **US5 (Phase 7)** depends on US2 (tiles from summary) and US3 (old components deleted). T068/T069 parallel; T070 needs T069; T071 needs T052 and T070; T072 after T071; T073 last.
- **Polish (Phase 8)** after Phase 7; T074–T076 parallel; T077 then T078; T079 with T078.

### User Story Dependencies

- **US1** → standalone after Phase 2 (deployable MVP: correct numbers everywhere).
- **US2** → needs US1's stored WHO values for the band tiles (works with the "Referencia anterior" caption otherwise).
- **US3** → needs US2's container; keeps US1's stored-value rule.
- **US4** → needs US3's chart preset; the latest-record fix already landed in Phase 2.
- **US5** → needs US2 + US3.

### Parallel Opportunities

- Phase 2: T006, T007(after T006), T008, T009, T010, T011, T012→T013, T014 across two `react-ui-engineer`, one `qa-engineer`, one `database-architect`.
- Phase 3: T016–T019 tests together; T024 and T025/T026 in parallel with T022/T023.
- Phase 4: backend (T033–T035) in parallel with frontend data layer (T036) and libs/components (T037–T039).
- Phase 5: T049 and T051 in parallel with T050 (two `react-ui-engineer`).
- Phase 6: T058, T059, T060 in parallel; T063 and T065 in parallel after T062.
- Phase 7: T068 and T069 in parallel.
- Phase 8: T074, T075, T076 in parallel.

---

## Parallel Example: Phase 4 (User Story 2)

```bash
# Backend wave (fastapi-architect · sonnet)
Task: "T033 Create backend/app/schemas/growth.py"
Task: "T034 Create backend/app/services/growth_summary.py"
# Frontend wave A (react-ui-engineer · sonnet)
Task: "T036 Frontend data layer: types, Zod schema, api, hook, MSW handler"
Task: "T038 Sparkline.tsx + GrowthStatusRow.tsx"
# Frontend wave B (react-ui-engineer · sonnet)
Task: "T037 lib/growth/rules.ts"
Task: "T039 NextMeasurementCard.tsx + GrowthAlerts.tsx"
# Tests (qa-engineer · sonnet) — written first, must fail
Task: "T030 test_growth_summary.py (service)"
Task: "T031 test_growth_summary.py (router)"
Task: "T032 frontend hook/lib/component tests"
```

---

## Implementation Strategy

### MVP First (Phase 2 + User Story 1)

1. Phase 1 setup, Phase 2 correctness fixes and column.
2. Phase 3: WHO everywhere + recompute + PDF. **Stop and validate** SC-001 and SC-007 on the `_test` MySQL. Deployable: no visual change beyond captions, numbers become trustworthy.

### Incremental Delivery

3. Phase 4 (US2) → coach tab decision-first, old chart embedded → validate SC-002/SC-003.
4. Phase 5 (US3) → curve split, old components deleted → validate SC-008, tokens.
5. Phase 6 (US4) → family mode + privacy audit → validate SC-004.
6. Phase 7 (US5) → timeline, shared tiles, no auto-jump, build gate → validate SC-005/SC-006/SC-009.
7. Phase 8 → docs, quickstart run, deploy smoke, band-change hand-off.

### Wave orchestration

Run each phase as a Workflow wave (`engineering-lead` / `data-platform-lead` on opus coordinating sonnet workers), tests first inside every story, `[P]` tasks fanned out to at most two `react-ui-engineer` workers at a time, and every checkpoint signed in `checklists/` before the next wave starts. Do not launch new waves past 80 % of the session budget; the owner will say when to resume.

---

## Notes

- Never put a minor's name, birth date or note in a test fixture committed to git, a log line, a report or a screenshot attached to a checklist.
- All new product copy: español neutro with diacritics; the AI instruction/docs corpus stays in English.
- Keep `RACE_AI_*`/`AI_*` configuration untouched; the coach-audience prompt runs through the existing session-assistant stack (`AI_*`).
- Commit only when the owner asks; the Spec Kit auto-commit hooks are optional and disabled in `git-config.yml`.
