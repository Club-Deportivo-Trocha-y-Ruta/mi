# Feature 046 — Integration gates

## T017 — Foundational gate (Phase 2), 2026-09-23

| Command | Result | Notes |
|---|---|---|
| `cd backend && python -m pytest tests/services -q` | PASS (for 046) | 2540 passed, 8 skipped, 12 xfailed, 6 xpassed, **3 failed**. The 3 failures are pre-existing and unrelated to 046 (see below). All 046 suites green: `test_body_composition.py`, `test_body_composition_reading.py`, `test_reference_skinfolds.py`, `test_growth_seed.py`. |
| `cd backend && ruff check` (repo-wide) | FAIL (pre-existing) | 363 errors, none in 046 files. They are in older test files (e.g. `tests/test_users.py`) and in feature-045 in-flight files (`tests/routers/test_race_imports.py`, `tests/routers/test_dashboard_summary.py`, `app/routers/club_race_insights.py`). Out of 046 scope. |
| `ruff check` on the 18 files 046 created or touched | PASS | config, models (`__init__`, anthropometry, growth, skinfold_measurement), schemas (anthropometry, growth, body_composition), seed_growth_data, services (body_composition, reference_skinfolds), migration `be4595de1ad2`, and the 046 tests plus the two head-bump tests. |
| `cd backend && alembic heads` | PASS | Exactly one head: `be4595de1ad2`. |
| `cd frontend && npm run typecheck` | PASS | `tsc --noEmit` clean. |
| `cd frontend && npx vitest run src/lib` | PASS | 27 files, 508 tests. |

### Pre-existing backend failures (not 046)

These source and test files are unmodified relative to HEAD, and none of them imports any 046 module:

- `tests/services/race/agents/test_schemas.py::test_analysis_input_age_bounds`: `AnalysisInput` now accepts age 25 (adult athletes).
- `tests/services/race/ai/test_invariants_v2.py::test_resolve_age_logs_warning_when_out_of_range`: `_resolve_age` returns 50 instead of clamping to 12.
- `tests/services/race/test_prompt_v3_blocks.py::test_adult_analyst_prompt_never_claims_maturation_even_with_anthro_context`: the adult prompt still contains "Circa-PHV".

### Deferred (real infrastructure)

- The `pytest -m mysql` migration lane (`tests/test_migration_skinfolds.py`, `tests/test_audit_mysql.py`) was run by the db-core lane against a throwaway MySQL 8.4 container and passed. It was not re-run in this gate and still needs a CI or dev run with the real `TEST_DATABASE_URL`.
- The golden and Playwright lanes do not apply to Phase 2.

### Open integration points carried forward (for later gates)

- `build_reading` ámbar order: `sum_up_velocity_low` is unreachable because `sum_up_unexplained` matches first. It gives the same band and family projection; only the coach sentence differs. The contract owner has to decide.
- Frontend coach band labels in `lib/growth/bands.ts` (`Sin alertas` / `En observación` / `Requiere acompañamiento profesional`) were derived from the contract text rather than quoted from it. Confirm the wording when the first UI consumer lands (US2 card).
- `reference_context` returns top-level keys `triceps` and `subscapular`, and `build_reading` consumes them as-is. They are consistent today, and the router (T035) must pass them through unchanged.
- `tests/test_ai_config.py::test_ai_anthro_prompt_version_default` asserts the v1 default. Update it in Phase 8 when the default moves to v2.

## T032 — US1 gate (capture, replace, delete), 2026-09-24

| Command | Result | Notes |
|---|---|---|
| `cd backend && python -m pytest tests/routers/test_body_composition.py tests/routers/test_anthropometry_bmi.py tests/test_audit_coverage.py tests/test_audit_privacy.py tests/services/test_body_composition*.py tests/services/test_reference_skinfolds.py tests/routers/test_growth_summary.py tests/test_growth_summary_latest_analysis.py tests/services/test_growth_summary.py tests/services/training/test_newsletter_body_composition.py -q` | PASS (for 046) | 269 passed, 1 skipped, **1 failed**. The one failure is `test_growth_summary_latest_analysis.py::test_null_when_ai_disabled`, which is environmental: the local `.env` sets `AI_ENABLED=true`, but the test assumes the default `false`. With `AI_ENABLED=false` in the environment the whole file passes (17/17). Not caused by 046. |
| T018 suite (`tests/routers/test_body_composition.py`) | PASS | Part of the run above (26/26 at the time of this gate). |
| `ruff check` on the 046 backend files (new files, plus the 045/046 shared files 046 touched: config, main, models, schemas, seed, routers anthropometry/growth/newsletters, services growth_summary/audit/newsletter_builder/athlete_newsletter_pdf/ai/anthro, tests) | PASS | "All checks passed!" |
| `cd frontend && npm run typecheck` | PASS | `tsc --noEmit` clean. |
| `npx vitest run src/components/athletes/body-composition src/routes/athletes` (includes the T019 suites SkinfoldSiteStep, SkinfoldWizard, SkinfoldCapturePage) | PASS | 14 files, 183 tests. |
| `npx vitest run src/components/athletes/AnthropometryForm src/components/athletes/AnthropometryHistory` (regression check) | PASS | 4 files (including the new `*.skinfolds.test.tsx`), 64 tests. Nothing needed fixing. |

The wizard lane reported an open item: `SkinfoldSiteStep` could keep a stale reading pair after a reading was deleted. It is already resolved in the tree. `emit()` always forwards the current valid readings, even when there are fewer than two, and the wizard's `min(2)` validation blocks "Siguiente". No change was needed.

## T041 — US2 gate (sums, estimates, noise), 2026-09-24

| Command | Result | Notes |
|---|---|---|
| T033 suite (`tests/routers/test_body_composition.py`: GET body-composition coach/parent/no-data, growth-summary coach `sum4_mm`, parent block has exactly the five family keys) | PASS | 26/26. |
| Query budget: `tests/test_growth_summary_latest_analysis.py` section 7 (reuses `tests/helpers/query_counting.count_selects`, the existing N+1 pattern) | PASS | 1 set vs 3 sets (one fully declined) issue the same number of SELECTs, and the difference against a monkeypatched no-skinfold baseline is ≤ 1. `_load_skinfold_context` is one SELECT, using `contains_eager` on the record join. |
| T034 suites (`BodyCompositionCard.test.tsx`, `BodyCompositionDetailDialog.test.tsx`) | PASS | Included in the sweep below. |
| `ruff check` (046 files) | PASS | Same file set as T032. |
| `npm run typecheck` | PASS | Clean. |
| `npx vitest run src/components/athletes` | PASS | 68 files, 853 tests. |

Follow-up (not blocking): `BodyCompositionCard.tsx` hardcodes `SUM4_MDC_MM = 7.0`, copying the `BODY_COMP_MDC_SUM4_MM` default because the API does not return the threshold. If that environment variable is ever changed in production, the "umbral" copy will drift. The fix would be to add the threshold to `GET …/body-composition` (`reference` block) in a later iteration.

## T048 — US3 gate (traffic light, escalation, referral note), 2026-09-24

| Command | Result | Notes |
|---|---|---|
| T042 suite (`tests/routers/test_body_composition.py`: scenarios A–D via API; referral note coach 200 with "no incluye un diagnóstico", initials only, no `\d+\s*%`, no `\d+(?:[.,]\d+)?\s*mm`, audit event `skinfolds.referral_note_generated`; parent 403; no sets 409 `no_skinfold_data`) | PASS | 26/26. |
| T043 suite (`BodyCompositionBand.test.tsx`) | PASS | Included in `vitest src/components/athletes` (853/853). |
| `ruff check` (046 files) | PASS | |
| `npm run typecheck` | PASS | |
| `npx vitest run src/components/athletes/body-composition` | PASS | Included in the sweep above. |
| No rojo on a rising Σ4 | PASS | Backend: `_is_rojo` requires `sum_change_code == "down_real"`. The property test `test_property_family_band_never_rojo_and_rising_or_single_never_rojo` covers every leg combination with sets_count 1–3. Router scenario C lowers Σ4 between the two sets. Frontend: the only rojo fixture (`BodyCompositionBand.test.tsx` `ROJO_READING`) is asserted to have `down_real` and a negative `sum4_change_mm`. `test/msw/bodyCompositionHandlers.ts` has no rojo fixture. |

## T071 — Final full offline lanes, 2026-09-24

Backend command used: `cd backend && PYTHONPATH=. DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m pytest -q -p no:cacheprovider --ignore=tests/test_langchain_provider.py -m "not golden and not integration and not mysql"`. The marker exclusion is explicit because `pyproject.toml` has no `addopts`, and a real AI key in the local `.env` would otherwise make the golden cases call the provider (see the T065 incident). `tests/test_langchain_provider.py` is ignored because of a known ImportError that predates 046 (`langchain_core` has no `ModelError`).

| Command | Result | Notes |
|---|---|---|
| `python -m pytest` (full offline lane, command above) | PASS for 046 | 6066 passed, 209 failed, 3 skipped, 88 deselected, 13 xfailed, 6 xpassed (1 min 53 s). **All 209 failures are environmental or predate 046**; the breakdown is below. |
| `ruff check` (whole backend) | PASS for 046 | 363 errors repo-wide (224 F401, 102 E402, 32 F841, 3 E741, 2 F811). This is the same count as at T017, and all of them are in files 046 did not create. `ruff check` on the 70 Python files that are untracked or mention skinfold/body_comp/BodyComposition/FUPRECOL (app, tests, alembic) → "All checks passed!" |
| `cd frontend && npm run typecheck` | PASS | `tsc --noEmit` clean. |
| `cd frontend && npm test` | PASS for 046 | 401 files, 4906 tests: 4905 passed and **1 failed**, which predates 046 (see below). |
| `cd frontend && npm run build` | PASS | `tsc --noEmit && vite build` completed. |
| Capture route chunk ≤ 150 KB gzipped | PASS | `SkinfoldCapturePage-*.js` is 22.59 kB raw / **7.43 kB gzip**. It shares small 046 chunks with the growth tab: `bodyComposition.schema` 1.30 kB gz, `useBodyComposition` 0.55 kB gz, `bodyComposition` API 0.31 kB gz. `BodyCompositionCard` (growth tab, lazy) is 3.57 kB gz. |

### 046 regression found and fixed in this gate

- `tests/test_archive_scope_gate.py::test_every_athlete_query_filters_or_is_exempt` failed on `services/training/newsletter_builder.py::_build_body_composition_block`. That function called `select(Athlete).where(Athlete.id == athlete_id)` with no archived filter. Fixed by adding `Athlete.deleted_at.is_(None)`, the same filter the builder already uses at its other `select(Athlete)` site. As a result, an archived athlete gets no body-composition annex. After the fix, the archive gate and `tests/services/training/` pass (269 passed), and ruff is clean.

### Backend failures that are not 046 (209 total)

- **183 environmental**: `sqlalchemy.exc.OperationalError: Can't connect to MySQL server on 'mysql'`. These are the docker-compose-host tests in `test_training_session_router.py` (44), `test_onboarding_consent.py`, `test_athletes.py`, `test_consent_endpoints.py`, `test_users.py`, `test_clubs.py`, `test_parent_register.py`, `test_parent_athletes.py`, `test_auth.py`, `test_security.py`, `test_ai_consent_enablement.py` and `test_privacy.py`. They need the compose MySQL service and do not run offline.
- **18 predate 046**: `tests/test_circuit_diagram_partial.py`, with `TemplateNotFound: documents/pdf/charts/circuit_diagram.svg.jinja`. The template was removed in committed history (last touched by `718d249`), and 046 did not touch it.
- **2 predate 046, in calendar**: `test_calendar_models.py::TestEventCreate::test_event_data_competition_valid` fails because competitions now require `race_event_id`. `test_calendar_audiences.py::TestSetAudiences::test_set_audiences_borra_y_reinserta` fails because delete is not awaited. The calendar sources and tests are unmodified relative to HEAD.
- **3 predate 046, in race (already listed at T017)**: `test_schemas::test_analysis_input_age_bounds`, `test_invariants_v2::test_resolve_age_logs_warning_when_out_of_range` and `test_prompt_v3_blocks::test_adult_analyst_prompt_never_claims_maturation_even_with_anthro_context`.
- **1 from feature 045**: `tests/evals/test_race_analyst_eval.py::test_v3_cases_declare_data_gaps_when_a_block_is_missing` (`case_014_adult_athlete`). The 045 golden_v3 dataset is being edited in the tree.
- **1 environmental**: `tests/test_growth_summary_latest_analysis.py::test_null_when_ai_disabled`. The local `.env` sets `AI_ENABLED=true`, and with `AI_ENABLED=false` the file passes 17/17.
- **1 order-dependent and environmental**: `tests/test_llm_factory.py::test_factory_module_does_not_import_claude_cli_package_eagerly`. `langchain_claude_cli` is installed in the local venv, and `tests/services/race/agents/test_llm_helpers.py` (a race test, unmodified, not 046) imports it earlier in the same session. The test passes alone, and together with `tests/anthro` or `tests/evals/test_anthropometry_analyst_eval.py`, so the 046 suites do not trigger it. In CI the package is not installed.

### Frontend failure that predates 046

- `src/routes/training/SessionWizardRouteNotify.test.tsx`, test "si falla la creación, muestra error y conserva el formulario". The test rejects with `new Error("boom")`, and `lib/apiError.ts::extractErrorDetail` returns `err.message` ("boom") ahead of the fallback "No se pudo crear la sesión…". The test, `SessionWizard.tsx` and `apiError.ts` are all unmodified relative to HEAD, and the test fails the same way when run alone.

### Still deferred (real infrastructure; not part of the offline lanes)

- The Playwright spec `frontend/e2e/body-composition.spec.ts` (T072) was not run; it needs the isolated e2e stack.
- `pytest -m mysql` and `pytest -m golden` were run by T073 and T068 respectively and are not re-run here.

## T032 / T041 — Round 2 re-run of the US1 and US2 gates against the current tree, 2026-09-24

Backend command prefix: `cd backend && PYTHONPATH=. DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m pytest <files> -q -p no:cacheprovider -m "not golden and not integration and not mysql" --ignore=tests/test_langchain_provider.py`.

| Gate | Command | Result | Notes |
|---|---|---|---|
| T032 + T041 | pytest on the T018/T033/T042 suite `tests/routers/test_body_composition.py`, plus `tests/test_growth_summary_latest_analysis.py`, `tests/routers/test_anthropometry_bmi.py`, `tests/test_audit_coverage.py`, `tests/test_audit_privacy.py`, `tests/routers/test_growth_summary.py`, `tests/services/test_body_composition.py`, `tests/services/test_body_composition_reading.py`, `tests/services/test_body_composition_load_reading.py`, `tests/services/test_reference_skinfolds.py` | PASS (for 046) | 257 passed, 1 skipped, **1 failed**. The one failure is `test_null_when_ai_disabled`, which is environmental because the local `.env` sets `AI_ENABLED=true`. Re-running the file with `AI_ENABLED=false` gives 17/17 passed. |
| T041 | Query budget: `tests/test_growth_summary_latest_analysis.py::test_body_composition_adds_at_most_one_query` (uses `count_selects`) | PASS | Part of the 17/17 above. |
| T032 + T041 | `ruff check` on every uncommitted or untracked backend `.py` file that mentions skinfold/body_comp/BodyComposition/FUPRECOL | PASS | "All checks passed!" |
| T032 + T041 | `cd frontend && npm run typecheck` | PASS | `tsc --noEmit` clean. |
| T032 + T041 | `npx vitest run src/components/athletes src/routes/athletes` (covers the T019 and T034 suites, `body-composition/`, `AnthropometryForm*`, `AnthropometryHistory*`) | PASS | 74 files, 949 tests. No regressions and nothing to fix. |

No 046-caused failures were found in this round, and no code was changed.

## T048 / T054 / T059 — Round 2 gates for US3, US4 and US5, 2026-09-24

Backend command for every backend row: `cd backend && PYTHONPATH=. DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m pytest <files> -q -p no:cacheprovider -m "not golden and not integration and not mysql" --ignore=tests/test_langchain_provider.py`.

### T048 — US3 gate (re-run against the current tree)

| Command | Result | Notes |
|---|---|---|
| T042 suite (`tests/routers/test_body_composition.py`: scenarios A–D, referral note coach/parent/409) | PASS | The file now holds 33 tests (US1–US5 plus T049), and all of them pass. See the combined run under T054. |
| T043 suite (`BodyCompositionBand.test.tsx`), via `npx vitest run src/components/athletes/body-composition` | PASS | 8 files, 87 tests. |
| `ruff check` on the 046 backend files (`routers/body_composition.py`, `services/body_composition.py`, `services/reference_skinfolds.py`, `schemas/body_composition.py`, `models/skinfold_measurement.py`, `services/growth_summary.py`, `services/training/newsletter_builder.py`, and the 046 tests) | PASS | "All checks passed!" |
| `cd frontend && npm run typecheck` | PASS | `tsc --noEmit` is clean. |
| No rojo on a rising Σ4 | PASS | This is unchanged since the round-1 T048 entry. `_is_rojo` requires `down_real`, the property test covers it, and the only frontend rojo fixture has a negative `sum4_change_mm`. |

### T054 — US4 gate (family card, notice, newsletter)

| Command | Result | Notes |
|---|---|---|
| T049 + T076 (`tests/routers/test_body_composition.py tests/routers/test_anthropometry_bmi.py tests/services/training/test_newsletter_body_composition.py`) | PASS | **48 passed** in 2.2 s. T049 covers: parent list returns `skinfolds is None` for every item; the parent growth-summary block has exactly the five keys and no digit; scenario C gives `family_band == "ambar"`; scenario D gives `verde`; a newer fully declined attempt leaves the parent block unchanged; the anthropometry PDF has no "pliegue" and no mm values; an unlinked parent gets 403 and a nonexistent athlete gets 404. T076 has 8 tests. |
| T050 (`FamilyBodyCompositionCard.test.tsx`, `FamilySkinfoldNotice.test.tsx`) | PASS | Part of the body-composition vitest run above (87/87). |
| Repo grep: `grep -rln useBodyComposition frontend/src` (excluding tests) | PASS, with one note | The hits are `hooks/athletes/useBodyComposition.ts`, `SkinfoldWizard.tsx`, `BodyCompositionCard.tsx` (all coach-only), `AnthropometryForm.tsx` (coach route `AthleteDetailPage`; the hook is gated by `enabled = !!onAddSkinfolds`), and `growth/GrowthTab.tsx`. No file under `routes/parents/` and neither `Family*` body-composition component imports the hook. `GrowthTab.tsx` serves both modes: the parent route mounts it with `mode="parent"`, but the hook is only *called* inside `CoachGrowthTab`, and `ParentGrowthTab` renders only `FamilyBodyCompositionCard`/`FamilySkinfoldNotice` from `growth-summary`. Nothing tested that at runtime, so this gate adds a regression test (below). |
| New test: `GrowthTab.parent.test.tsx` › "GrowthTab modo padre — composición corporal (feature 046)" › "nunca consulta el endpoint coach-only de composición corporal" | PASS | Additive edit: `vi.mock("@/api/bodyComposition")` plus `expect(getBodyComposition).not.toHaveBeenCalled()` in parent mode. `GrowthTab.parent.test.tsx` and `GrowthTab.test.tsx` both pass: 31/31. |
| `cd frontend && npm run typecheck` | PASS | Clean. |

Observation, not blocking and not fixed here because T049 belongs to the qa lane: the scenario-C assertion that the body contains neither "Requiere acompañamiento profesional" nor "profesional de la salud" runs against the **coach** `GET …/body-composition` response. The parent growth-summary block for a rojo fixture is still covered, because the parent test asserts exactly five keys with no digit and the property test says `family_band` is never rojo. It is not string-checked for the escalation copy.

### T059 — US5 gate (printable field guide)

| Command | Result | Notes |
|---|---|---|
| T055 (`test_field_guide_coach_happy_path_lists_six_sites_no_athlete_data`, `test_field_guide_parent_forbidden`) | PASS | Coach: 200 `application/pdf`, `Cache-Control: private, max-age=86400`, the six Spanish site names, and "no contiene datos de ningún deportista". Parent: 403. Both are part of the 48-pass run above. |
| Local render: `NotificationService.generate_document_only` with `DocumentTemplate.BODY_COMPOSITION_FIELD_GUIDE` and `_build_field_guide_sites()` (a throwaway script in `/tmp`, same code path as the endpoint), then `pdftoppm -gray` at 100 dpi, plus a 300 dpi crop of the diagrams | PASS | Output: 25 KB, 3 pages, A4. |
| Visual check in grayscale | PASS, with observations | Page 1 has the intro, "Antes de empezar" (6 prechecks), and sites 1–2 (Tríceps, Bíceps). Page 2 has sites 3–6 (Subescapular, Pantorrilla, Cresta ilíaca, Supraespinal) and "Protocolo de lectura" (two readings, right side, 5 % / 1,0 mm tolerance for a third reading, rotate sites, 2 s). All six diagrams render as line-art silhouettes with a dashed landmark line, a fold-orientation stroke and a caliper marker, plus the "D" side tag. No color is needed, and everything stays legible in grayscale at 300 dpi. Diacritics render correctly. No athlete data and no numbers other than the protocol constants (1 cm, 2 s, 45°, 90°, 5 %, 1,0 mm). |

Observations from the render, all cosmetic, none a privacy leak, and none changed here:

1. Page 3 holds only the line "Este instructivo no contiene datos de ningún deportista." and the generated-at footer. It is a mostly blank sheet when printed. Tightening the spacing or moving that line into the page-2 protocol box would bring the guide to 2 pages.
2. The base layout (`templates/documents/pdf/base/layout.html`, shared by every PDF) hardcodes "Documento confidencial — datos de menor de edad protegidos." in both the `@page @bottom-left` box and the `.doc-footer`. That contradicts the guide's own "no contiene datos de ningún deportista" line. Fixing it needs a new overridable block in the shared layout, so it is left to the template owner.
3. The Cresta ilíaca and Supraespinal diagrams share the same trunk silhouette, and only the marker position and angle differ. Printed at a small size they are easy to confuse. The captions "Dónde"/"Cómo" disambiguate them.

No failures caused by 046 were found in T048, T054 or T059.
