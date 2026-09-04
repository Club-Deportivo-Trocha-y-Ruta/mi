# Checklist — Phase 4 / User Story 2: the coach reads the decision before the evidence (feature 040)

**Wave**: Phase 4 — decision-first coach tab + growth-summary endpoint · **Date**: 2026-09-04 · **Branch**: `feat/040-growth-module-redesign`
**Gate**: `engineering-lead` (wave review, T045) · **Workers**: `fastapi-architect` (T033–T035 + T030/T031), `react-ui-engineer` ×3 (T036–T042), `qa-engineer` (T032, T043, T044)

## Result

| Task | Owner | Status | Evidence (command → result) |
|---|---|---|---|
| T030 — service tests `test_growth_summary.py` | qa-engineer / fastapi-architect | **Done** | `backend/tests/services/test_growth_summary.py` — **19 tests**. Covers cm/month→cm/year conversion, `interval_short` < 30 días suppressing `rapid_growth`, expected ranges by stage and sex, `months_from_phv` sign, `phase_changed`, `approaching_circa`, and the no-records / one-record shapes. Fixtures are synthetic in-memory ORM objects (`birth_date` values are invented dates, no name). Gate re-ran → **PASS 19/19**. |
| T031 — router tests (11 contract cases) | qa-engineer / fastapi-architect | **Done** | `backend/tests/routers/test_growth_summary.py` — **11 tests**, one per numbered case of `contracts/growth-summary-api.md`: coach 200, admin 200, own parent 200, other parent 403, 404, never-measured, one record, short interval, rapid growth, circa alert + 30-day interval, privacy invariant. Uses the `app.main.app` + `get_db`/`get_current_user` override pattern from `test_dashboard_summary.py`, so `verify_athlete_access` executes for real → the 403/404 coverage is genuine, not mocked. Gate re-ran → **PASS 11/11**. |
| T032 — frontend hook/lib/component tests | qa-engineer | **Done** | All six required files present and green: `src/hooks/athletes/useGrowthSummary.test.tsx` (MSW happy/403/network error), `src/lib/growth/rules.test.ts` (`rulesFor`/`differsFromDefault`, plus an explicit `expect(rule.text).not.toMatch(/\d+\s*(lpm\|bpm)/i)` guard), and `growth/__tests__/{GrowthStatusRow,NextMeasurementCard,GrowthAlerts,Sparkline}.test.tsx`. Hook test uses the `mswServer`/`http.use` convention (not `vi.mock`). Gate verified existence file-by-file and re-ran → **PASS**. |
| T033 — `backend/app/schemas/growth.py` | fastapi-architect | **Done** | `GrowthSummaryOut`, `GrowthVelocity`, `MeasurementDue`, `BandReading`, `LatestBands` per `data-model.md` §3. Reuses the existing `MaturationStatus` / `NutritionalStatus` / `GrowthSource` enums and `schemas/alerts.py::MeasurementStatus` rather than duplicating vocabulary. **Judgment call accepted by the gate**: a new `GrowthSummaryAlert` enum was added because the pre-existing `schemas/alerts.py::GrowthAlert` only carries 3 of the 6 tab alert codes and that file was outside the worker's ownership. Correct call — the dashboard's 3-code vocabulary stays untouched. |
| T034 — `backend/app/services/growth_summary.py` | fastapi-architect | **Done** | `build_growth_summary(athlete, latest, previous, today)` is a **pure function, no DB access** — reuses `services/measurement_alerts.py` helpers (`calculate_growth_velocity`, `calculate_next_due`, `get_measurement_interval`, `detect_approaching_circa`) and `services/growth.py::classify_nutritional_status_height` for the height/weight bands. Gate diffed `EXPECTED_VELOCITY_CM_YEAR` against `research.md` R-05 → **exact match**. `records_count` reflects the 0/1/2 rows actually fetched (deliberately no extra `COUNT(*)`, honouring the contract's single-query requirement); `days_overdue` stays `null` unless genuinely overdue, matching the contract's JSON example. |
| T035 — `GET /athletes/{id}/growth-summary` | fastapi-architect | **Done** | `backend/app/routers/growth.py:104`. Gate verified: `athlete: Athlete = Depends(verify_athlete_access)` (RBAC centralised, not re-implemented) and exactly one `…order_by(AnthropometricRecord.evaluation_date.desc()).limit(2)` query — the contract's non-functional requirement. Router is mounted under `/api`, so the effective path is `/api/athletes/{id}/growth-summary`. Pure addition; `/growth-reference` untouched. |
| T036 — frontend data layer | react-ui-engineer | **Done** | `types/growth.types.ts` + `schemas/growth.schemas.ts` (Zod mirror via `z.infer`, same pattern as `intervals`), `api/growth.ts::getGrowthSummary` (parses with `growthSummarySchema.parse` — defence in depth), `hooks/athletes/useGrowthSummary.ts` (query key `["growth-summary", athleteId]`), MSW `test/msw/growthSummaryHandlers.ts` registered in `test/setup.ts`. Gate verified the **`persistAllowList.ts` requirement**: `git diff` on that file is **empty**, so the new query stays under default-deny and never reaches the persisted cache. `nutritionalStatusSchema` is anchored to `lib/growth/bands.ts` via `z.ZodType<>` so the two band vocabularies cannot silently diverge. |
| T037 — `lib/growth/rules.ts` | react-ui-engineer | **Done** | Ports the nine `buildRules()` criteria out of `TrainingReadiness.tsx` into a flat `(id, ageGroup, stage)` table with `stage: "any"` defaults and Circa-PHV overrides only where behaviour actually differs — which reproduces the original logic, since it never distinguished Pre- from Post-PHV. `rulesFor()` / `differsFromDefault()` per `data-model.md` §5. No heart-rate number (already removed in T008). |
| T038 — `Sparkline.tsx` + `GrowthStatusRow.tsx` | react-ui-engineer | **Done** | 4 × `shared/StatCard`: Etapa, Velocidad de talla (embeds the Sparkline over up to 12 chronologically sorted height readings), Talla para la edad, IMC para la edad. Copy matches `contracts/growth-tab-ui.md` verbatim — gate spot-checked `"PHV estimado a los … años"`, `"{v} cm/año"`, `"esperado {a}–{b} cm/año (orientativo)"`, `"Se necesitan 2 mediciones"`, `"Intervalo corto: valor orientativo"`. Band tiles carry a `StatusBadge` (icon + label) and the source caption `"OMS 2007 · Res. 2465/2016"` vs `"Referencia anterior — pendiente de actualizar"`. Etapa deliberately carries **no tone/badge** — PHV colour maps are on the contract's *Removed* list. |
| T039 — `NextMeasurementCard.tsx` + `GrowthAlerts.tsx` | react-ui-engineer | **Done** | Card renders `"Próxima medición: {fecha} · cada {n} días{ en etapa}"` with the `Vencida / Próxima / Al día / Sin medir` badge from `lib/measurementStatus.ts` (the T009 extraction — reused, not re-declared). Date formatting avoids `new Date(dateOnlyString)` to dodge the America/Bogotá off-by-one, matching `AnthropometryHistory.tsx`. **Scope split accepted by the gate**: `GrowthAlerts` renders only `rapid_growth` / `approaching_circa` / `phase_changed` and silently ignores `circa_phv` / `height_p3` / `bmi_p3`, which `TrainingReadiness` already owns — this prevents the same alert appearing twice on one screen while keeping the full `summary.alerts` array as the input contract. |
| T040 — refactor `TrainingReadiness.tsx` | react-ui-engineer | **Done** | Now takes `{ athlete, latestRecord, alerts? }` and consumes `lib/growth/rules.ts`. Renders only the rules that differ from the age-group default as `StatusBadge` chips (Permitido / Con cuidado / No permitido — icon + label, never colour alone), with a shadcn `Collapsible` "Ver todas las reglas" (trigger `min-h-12`) listing all nine. Athlete-name chip removed; title is now the contract's `"Qué cambia en el entrenamiento"`; `data-testid="growth-rules"` added. `alerts` is optional, so the component still works standalone with its local computation — which is why the T042 call site kept compiling. Test file rewritten 12 → **18 cases**. Fixed a missing diacritic in surviving copy (`medico` → `médico`). |
| T041 — `GrowthTab.tsx` | react-ui-engineer | **Done** | Composition order matches the contract exactly (gate read the file): coach = GrowthAlerts → GrowthStatusRow → NextMeasurementCard → TrainingReadiness → GrowthCharts (temporary slot) → MorphologyCard → PHVExplanationCard → AnthropometryHistory(coach) → ResearchReferences. Only the summary-dependent block is gated by `useGrowthSummary`'s loading (`StatCard isLoading` skeletons) / error (`ErrorState` + retry → `refetch`) / empty (`records_count === 0` → `EmptyState` "Registra la primera medición" + CTA) states; the rest of the tab renders independently, which is what satisfies **acceptance scenario 6** (a failing summary does not take the tab down). Parent mode is at parity with today minus `ResearchReferences` (coach-only per contract); the narrative family redesign is Phase 6 / T058–T062. |
| T042 — wire `AthleteDetailPage.tsx` | react-ui-engineer | **Done** | `React.lazy` + `Suspense` (skeleton fallback) with `key={athlete.id}`; the inline growth block and its now-dead imports/locals removed (`noUnusedLocals` is on, so `npm run typecheck` is the proof). Tab button and its `records.length > 0` guard kept; the auto-select-growth effect and the "Enviar informe" button deliberately left for Phase 7 / T070, per the task text. |
| T043 — jest-axe `GrowthTab.a11y.test.tsx` | qa-engineer | **Done** | 2 scenarios — coach mode with records (including active `rapid_growth` + `phase_changed` alerts rendered) and coach mode with zero records (EmptyState) → **0 axe violations**. Mocks the pre-existing heavy children that have no axe coverage of their own and renders the real new-for-this-feature pieces, the same convention as `SessionDetailPage.a11y.test.tsx`. |
| T044 — Playwright `e2e/growth.spec.ts` part 1 | qa-engineer | **Deferred — written, not executed** (accepted, see *Deferrals*) | File authored and statically valid: `npx playwright test --list e2e/growth.spec.ts` → **1 test discovered**, imports resolve. Asserts the five readings are `toBeInViewport()` at 1024×768 and that "Ver todas las reglas" flips `aria-expanded`. Clicks the "Crecimiento" tab explicitly rather than relying on the auto-select effect (still present until T070) — same convention as the T010 fix to `history.spec.ts`. **Could not be run green**: `loginAsCoach` fails against the local stack for every existing spec, not just this one. |
| T045 — wave review | engineering-lead | **Done** | This document. SC-002 and SC-003 signed off below; gate commands and the baseline differential in the next two sections. |

## Verification commands run by the gate

| Command | Result |
|---|---|
| `cd backend && ruff check app tests` | **330 errors** — see baseline differential. Zero new lint debt; **one fewer** error than `HEAD`. |
| `cd backend && .venv/bin/python -m pytest tests/services/test_growth_summary.py tests/routers/test_growth_summary.py -q` | **PASS — 30 passed** in 0.17 s |
| `cd frontend && npm run typecheck` | **PASS — `tsc --noEmit` clean, 0 errors** |
| `cd frontend && npx vitest run src/components/athletes src/hooks/athletes src/lib/growth src/routes/athletes` | **PASS — 898 passed / 898, 65 files** (after the gate fix described under *Fixes applied by the gate*; it was 3 failed / 898 on arrival) |
| `cd frontend && npx vitest run` (full suite) | **3871 passed / 3872, 322 files passed / 323**. The single failure is `src/lib/__tests__/datetime.test.ts` — pre-existing, proven below. |
| `cd backend && .venv/bin/python -m pytest -q` (offline lane, no overrides) | 225 failed / 3686 passed — all 225 are environment failures (the local `.env` points the test DB at the docker-internal host `mysql`, unreachable from the host shell; plus WeasyPrint native libs). |
| `cd backend && MYSQL_HOST=127.0.0.1 DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m pytest -q` (low-noise lane) | **169 failed / 3742 passed** — same 169-failure count the Phase 2 gate recorded, with the passing count strictly higher (3697 → 3742 across Phases 3 + 4). |
| `npx playwright test --list e2e/growth.spec.ts` | **PASS — 1 test discovered**, syntax and imports valid (`e2e/` sits outside `tsc`'s `src` include, so this is the applicable static gate). |

## Baseline differential (clean `git worktree` at `HEAD` = `84c8061`)

Per the wave-gate rule, "pre-existing" is **proven**, not asserted.

| Comparison | Branch | Baseline at `HEAD` | Verdict |
|---|---|---|---|
| `ruff check app tests` | 330 errors | **331 errors** | Zero new lint debt (branch is 1 better). |
| `pytest -q --tb=no` — full failure **set**, not just the count | 225 failed / 3686 passed | 225 failed / 3656 passed | `diff` of the two sorted failure lists → **identical sets, byte for byte**. Zero backend regressions; the wave adds +30 passing tests. |
| `npx vitest run src/lib/__tests__/datetime.test.ts` | 1 failed / 42 passed | 1 failed / 42 passed | Identical — the `currentSeason()` year-boundary assertion is timezone-dependent and fails on any machine not set to America/Bogotá. Pre-existing. |

> **Methodology note for the next gate.** The first baseline run reported only 182 failures and looked like a 43-failure regression. It was an artefact: `git worktree` does not carry gitignored files, so the worktree had no `backend/.env` and silently fell back to a different database configuration. Symlinking the main checkout's `.env` into the worktree (never opening or printing it) made the two runs comparable and produced the identical sets above. **A baseline worktree must be given the same environment files as the working tree, or the differential is meaningless.** The symlink was removed before `git worktree remove`; `backend/.env` in the working tree is untouched.

## Fixes applied by the gate

`frontend/src/routes/athletes/AthleteDetailPage.test.tsx` — 3 assertions encoding the **old** coach-tab composition were failing. No task in `tasks.md` owns this file (T067 adds a *new* `AthleteDetailPage.tabs.test.tsx` in Phase 7), so the gate updated them in place after confirming each change is what `contracts/growth-tab-ui.md` requires:

1. `"renderiza NutritionalClassification"` → `"NO renderiza NutritionalClassification en modo coach"`. The contract's component tree has no `NutritionalClassification` in coach mode; its two classifications are superseded by `GrowthStatusRow`'s band tiles, which read server-computed values instead of recomputing LMS in the browser. Still asserted in parent mode by `MyAthleteDetailPage.growth.test.tsx`.
2. `"NO renderiza AnthropometryHistory en tab Crecimiento"` → `"renderiza AnthropometryHistory (compacto) en tab Crecimiento"`. The contract explicitly lists `AnthropometryHistory` inside the tree.
3. `"volver a Crecimiento desde Antropometría restaura GrowthCharts"` — the trailing `not.toBeInTheDocument()` on `anthropometry-history` replaced with `getAllByTestId(...).toHaveLength(1)`, which keeps the test's real intent (no duplicate mounts when switching tabs) now that the component legitimately appears in both tabs.

Each replacement carries an inline comment naming feature 040 / T041 so the intent survives.

## Success criteria

**SC-002 — five readings visible without scrolling (1024 px tablet; within one scroll on a 390 px phone)**: **Partially signed — structure verified, viewport measurement deferred.** The gate read `GrowthTab.tsx` and confirmed the DOM order puts the decision before the evidence: `GrowthSummarySection` (GrowthAlerts → GrowthStatusRow → NextMeasurementCard) renders **before** `TrainingReadiness` and before the `GrowthCharts` slot, with no chart above the fold. The status row is a `grid gap-3 sm:grid-cols-2 lg:grid-cols-4`, so the four tiles land on one row at ≥ 1024 px and two rows on a phone. The actual pixel measurement at 1024×768 and 390 px, for athletes with 1, 2 and 6 measurements, is asserted by T044 (`toBeInViewport()`) and by `quickstart.md` — **both of which need the dev stack**, so the empirical half of SC-002 rides with the T044 deferral and the Phase 7 e2e gate (T072).

**SC-003 — the five coach questions answerable from the tab alone**: **Signed (static dry-run).** Each question maps to a surface the gate located in the code:

| Question | Surface |
|---|---|
| ¿En qué etapa está? | `StatCard label="Etapa"` + hint `"PHV estimado a los {age} años · hace/en {n} meses"` |
| ¿Cuánto ha crecido? | `StatCard label="Velocidad de talla"` → `"{v} cm/año"` + `"esperado {a}–{b} cm/año (orientativo)"`, with the `"Se necesitan 2 mediciones"` and `"Intervalo corto"` fallbacks |
| ¿Cuándo mido de nuevo? | `NextMeasurementCard` → `"Próxima medición: {fecha} · cada {n} días en {etapa}"` + status badge |
| ¿Está en su canal? | `StatCard "Talla para la edad"` and `"IMC para la edad"`, each with a `StatusBadge` (icon + label) and the reference-source caption |
| ¿Qué no debe hacer esta semana? | `TrainingReadiness` → `"Qué cambia en el entrenamiento"`, differing rules only, Permitido / Con cuidado / No permitido |

Zero navigations away are required. The moderated timing test with the club's coach (< 30 s per question, 5/5) remains a human step for the quickstart run (T077).

## Privacy

- **New fixtures**: `PASS`. `backend/tests/routers/test_growth_summary.py` uses `first_name="Atleta"`, `last_name="Prueba"` and a synthetic birth date; the service tests use invented `date(2014, 1, 1)`-style values with no name at all. The worker explicitly avoided the shared `race_history_fixtures.py` default, which reuses the repo owner's real name. No minor-identifiable data in any new file.
- **Endpoint response**: the contract's privacy invariant is enforced by a test, not just by review — case 11 asserts `first_name` / `last_name` / `birth_date` appear nowhere in the response body.
- **Tokens / status**: no raw hex in any new frontend file under `components/athletes/growth/`, `lib/growth/rules.ts`, `hooks/athletes/useGrowthSummary.ts`, `api/growth.ts`, `types/growth.types.ts`, `schemas/growth.schemas.ts`. Status is always `StatusBadge` (icon + label).
- **Touch targets**: `min-h-12` on the `NextMeasurementCard` row and the `TrainingReadiness` collapsible trigger; `size="lg"` on the EmptyState CTA.
- **Action item for the owner (not a code defect)**: while diagnosing the `loginAsCoach` failure, the T044 worker ran a read-only `SELECT id, email, role FROM users LIMIT 20` against the **local docker MySQL**, whose output included real parent email addresses. No minor's name, birth date or anthropometric data was queried or printed, and nothing was modified, but email is borderline identifying data under Ley 1581. The worker stopped immediately. **Recommendation: reset the local docker stack to the demo seed fixture, or stand up a dedicated e2e-only stack, before the Phase 7 e2e gate (T072).** This also fixes the T044 blocker. The full privacy audit for the feature is T065 (`data-privacy-guard`).

## Deferrals (accepted)

| Item | Reason | Where it lands |
|---|---|---|
| **T044** — run `e2e/growth.spec.ts` green | The local dev DB already contains a real Club, so `backend/scripts/seed.py` early-returns and the fixture account every e2e spec assumes does not exist. **Pre-existing and not specific to this wave**: `e2e/anthropometry.spec.ts` and `e2e/history.spec.ts`, both committed and untouched here, fail at the identical `loginAsCoach` line against the same stack. `/health` and `:5173` both respond, so this is a seed-data problem, not an infrastructure one. | Phase 7 **T072** (full e2e gate) after the local stack is reset to the demo seed; the spec file itself is complete and discovered by Playwright. |
| **SC-002 empirical viewport check** | Needs a running browser at 1024×768 and 390 px with 1-, 2- and 6-measurement athletes. | T044 / T072 and `quickstart.md` §2 (T077). |
| **SC-003 moderated timing** | Requires the club's coach in a moderated session. | T077 quickstart run. |

## Blockers for the next wave

**None.** Phase 5 (US3, the readable curve) can start: it depends on `GrowthTab.tsx` (T041), which is in place with the temporary `GrowthCharts` slot that T052 replaces with `GrowthCurveSection`, and on the T011 characterization tests, which are green.

---

**Signed**: `engineering-lead` (wave gate, Phase 4 / US2) — 2026-09-04
**Verdict**: Phase 4 **PASS**. 15 of 16 tasks verified complete and marked `[X]` in `tasks.md`; T044 left unchecked and deferred with the accepted reason above. Zero regressions against the `HEAD` baseline in backend tests, backend lint and frontend tests.

---

# Checklist — Phase 5 / User Story 3: one growth curve that can actually be read (feature 040)

**Wave**: Phase 5 — windowed, tokenized percentile chart + table view, old chart components deleted · **Date**: 2026-09-04 · **Branch**: `feat/040-growth-module-redesign`
**Gate**: `engineering-lead` (wave review, T055) · **Workers**: `react-ui-engineer` ×3 (T048, T049/T051, T050, T052/T053), `qa-engineer` (T046, T047, T054)

## Result

| Task | Owner | Status | Evidence (command → result) |
|---|---|---|---|
| T046 — `lib/growth/window.test.ts` | qa-engineer | **Done** | 27 cases across 4 `describe`s: `computeAgeWindow` (−24/+36 padding, single age, clamp low 61.5, clamp high 228.5, order-independence, `range="full"`, no records, defensive `min > max`), `yearTicks` (multiples of 12 inclusive, narrow window, empty), `niceTicks` (steps 20/5/10/1, `targetCount`, `min === max`, and a property check that every step is 1/2/5/10 × 10^k), `filterReferenceRows` (one extra row per edge, edge-touching, unsorted input, empty, window narrower than the row spacing). Gate ran `npx vitest run src/lib/growth/window.test.ts` → **PASS 24/24 at worker time, 27/27 at gate time**. |
| T047 — component tests for the four new files | qa-engineer | **Done** | `growth/__tests__/{PercentileChart,PercentileToolbar,PercentileTable,GrowthCurveSection}.test.tsx`. Gate verified the task's required coverage exists: indicator list by age (`age_decimal > 10` drops Peso), axis toggle hidden for IMC **and** for a non-coach role, detail toggle adding/removing P10/P25/P75/P90, table rows = one per record with stored values, export button + filename, `role="img"` + `aria-label`. All four ran against the **real** implementations (the workers landed concurrently), not stubs. |
| T048 — `lib/growth/window.ts` | react-ui-engineer | **Done** | `computeAgeWindow` / `yearTicks` / `niceTicks` / `filterReferenceRows`, with `AGE_WINDOW_{MIN,MAX,PAD_BEFORE,PAD_AFTER}_MONTHS` exported. Gate read the source and confirmed it implements FR-011 / research R-07 exactly: `[max(61.5, min(ages) − 24), min(228.5, max(ages) + 36)]`, falling back to the full range with no records or on an inverted clamp. `filterReferenceRows` keeps one row beyond each edge so the reference lines do not stop short of the plot border. |
| T049 — `PercentileToolbar.tsx` | react-ui-engineer | **Done** | Controlled component, four shadcn `ToggleGroup`s + two `Button`s. Copy matches `contracts/growth-tab-ui.md` line 52 **verbatim**: "Talla"/"IMC"/"Peso", "Cronológica"/"Biológica", "Ver 5–19 años"/"Ver alrededor de las mediciones", "Detalle", "Gráfica"/"Tabla", "Descargar PNG". Touch targets: every `ToggleGroupItem` carries `min-h-12` (overriding `toggle.tsx`'s native `h-9`/`h-10`), buttons use `size="lg"`. Axis group renders only when `showAxisToggle`; export button only when `onExport` is passed. Each group has an `aria-label`. |
| T050 — `PercentileChart.tsx` | react-ui-engineer | **Done** | recharts `ComposedChart` with `XAxis type="number" domain={[min,max]} allowDataOverflow` fed by `computeAgeWindow`. Gate grepped the file: **every** colour is a `var(--color-*)` token — band `--color-light-gray`, P50 `--color-charcoal`, P3/P97 + intermediates `--color-mid-gray`, athlete line `--color-primary`, grid `--color-border-gray`, tooltip cursor `--color-mid-gray`. WHO reference JSON behind `await import("@/data/growth-reference-who.json")` inside an effect (feeds the R-08 lazy-chunk goal, gated later in T071), with loading / error+retry / empty-reference states. `role="img"` + summarizing `aria-label`; PHV/PWV `ReferenceLine`; `getMaturationMarker`, `INDICATOR_PHV_NOTES` and the bio-age tick formatter ported from the retired `PercentileCurves.tsx`; T026's stored-Z-with-LMS-fallback rule preserved. |
| T051 — `PercentileTable.tsx` + `GrowthCurveSection.tsx` | react-ui-engineer | **Done** | Table = shadcn `Table`, one row per record via a per-row subcomponent (calling `useGrowthMetrics` inside the parent's `.map()` would break the Rules of Hooks), month obfuscated to "mes año" (no exact day) for Ley 1581, empty state "Sin mediciones" exactly as the contract's state table requires. `GrowthCurveSection` owns `indicator`/`axis`/`range`/`detail`/`view` + the `html-to-image` export (`crecimiento-<indicator>-<timestamp>.png`, background from `var(--color-surface)`, no hex literal). `showAxisToggle` requires `mode === "coach"` **and** a live coach/admin role from `useAuthStore` — stricter than the task text and correct (a parent must not get the biological axis even if the coach view were mounted by mistake). |
| T052 — replace the slot, delete the old components | react-ui-engineer | **Done** | `GrowthTab.tsx` (both modes) and `MyAthleteDetailPage.tsx` now render `GrowthCurveSection`; the dead `phvAgeMonths` plumbing is gone from both call sites (the section derives it internally from the newest record). `git status` confirms `GrowthCharts.tsx`, `GrowthCharts.test.tsx`, `PercentileCurves.tsx`, `PercentileCurves.test.tsx`, `PercentileCurves.a11y.test.tsx` deleted (plus the untracked `PercentileCurves.characterization.test.tsx`). `e2e/history.spec.ts:98` now targets `growth-curve`. Barrel `growth/index.ts` exports the four new components + types. **Re-homing of T011 checked by the gate**: PHV/PWV marker matrix → `PercentileChart.test.tsx`; PNG filename without PII → `GrowthCurveSection.test.tsx`; sr-only rows → superseded by the now-visible `PercentileTable`; bio-axis tick relabeling → added to `PercentileChart.test.tsx`. The legend-toggle behaviour was **deliberately not** re-homed: the redesign's legend is static (R-06/R-07/R-08), a documented scope decision, not a lost assertion. |
| T053 — diacritics | react-ui-engineer | **Done** | "Interpretacion" → "Interpretación" and "Detalles tecnicos" → "Detalles técnicos" in `PercentileInterpretationBlock.tsx` (+ the 5 matching regexes in its sibling test). The new toolbar shipped with correct diacritics already. Grep gate result below. |
| T054 — Playwright `e2e/growth.spec.ts` part 2 | qa-engineer | **Deferred — written, not executed** (accepted, see *Deferrals*) | `E2E-040-002` added alongside the untouched `E2E-040-001`, covering all four required surfaces and ordered to match the real component logic (the "Biológica" toggle only exists while the indicator is not IMC, so it is exercised **before** switching to IMC). `npx tsc --noEmit -p .` → **0 errors**. Execution blocked by the same `loginAsCoach` 401 that already blocked T044; the worker proved it is not caused by this file by running the repo's untouched `e2e/auth.spec.ts::E2E-001`, which fails identically. |
| T055 — wave review | engineering-lead | **Not done — see the SC-008 finding** | Tokens audit passes; SC-008 as written does **not** hold and cannot hold under FR-011. Section below. |

## Verification commands run by the gate

| Command | Result |
|---|---|
| `cd frontend && npm run typecheck` | **PASS — `tsc --noEmit` clean, 0 errors** |
| `cd frontend && npx vitest run src/components/athletes src/lib/growth src/routes` | **PASS — 106 files, 1307/1307** (on arrival it was 2 files / 10 tests failing; see *Fixes applied by the gate*) |
| `cd frontend && npx vitest run` (full suite) | **324 files: 323 pass / 1 fail · 3883 tests: 3882 pass / 1 fail.** The single failure is `src/lib/__tests__/datetime.test.ts > currentSeason` — **pre-existing**, see the differential below. |
| `cd frontend && grep -rn "Cronologica\|Biologica\|Interpretacion\|tecnicos" src` | 3 hits, **all accepted**: `test/msw/newsletterHandlers.ts:38`, `components/training/MonthlyMetricsTable.tsx:261` and its test — the snake-case backend field `focos_tecnicos` (emitted by `backend/app/services/training/newsletter_builder.py`) and a `focos-tecnicos` test id derived from it. These are **identifiers in the unrelated training module, not user-facing copy**; renaming them would break the newsletter API contract for zero user benefit. No growth-module hit remains. |
| `cd frontend && grep -rn "#[0-9a-fA-F]\{6\}" src/components/athletes/growth` | **PASS — no output.** |
| `cd frontend && npx vitest run src/components/athletes/growth` | **PASS — 12 files, 133/133** |

## Baseline differential (pre-existing failure, proven)

| Comparison | Branch | Baseline | Verdict |
|---|---|---|---|
| `src/lib/__tests__/datetime.test.ts > currentSeason` | 1 failed | 1 failed at `HEAD` (recorded by the Phase 4 gate's clean-worktree run) | `git diff HEAD -- frontend/src/lib/datetime.ts frontend/src/lib/__tests__/datetime.test.ts` → **empty**: both the source and the test are byte-identical to `HEAD`, so the branch cannot have caused the failure. Root cause is environmental: the test's own control line asserts `new Date("2027-01-01T02:00:00Z").getFullYear() === 2027`, which is false on this machine (`Intl…timeZone` = `America/Bogota`, UTC−5 → 2026-12-31 local). **Pre-existing, timezone-dependent, unrelated to feature 040.** |

## SC-008 — measured, and **not met** (blocking finding for the owner)

The task asked for SC-008 to be measured on a three-measurement fixture. It was, against the real `computeAgeWindow` constants read out of `frontend/src/lib/growth/window.ts`:

| Fixture (ages in months) | Data span | Default window | Plot width | **Share of width covered** | Old behaviour (`domain={["dataMin","dataMax"]}` over the full reference) |
|---|---|---|---|---|---|
| **3 measurements over 14 months** (141, 148, 155) — the SC-008 fixture | 14 mo | [117, 191] | 74 mo | **18.9 %** | 8.4 % |
| 3 measurements over 24 months (136, 148, 160) | 24 mo | [112, 196] | 84 mo | 28.6 % | 14.4 % |
| 3 measurements over 48 months (112, 136, 160) | 48 mo | [88, 196] | 108 mo | 44.4 % | 28.7 % |

**SC-008 requires ≥ 60 %. The delivered window yields 18.9 %.** This is not an implementation defect: `window.ts` implements **FR-011 exactly** ("window its age axis to [first measurement − 2 years, last measurement + 3 years] clamped to the reference range") and research R-07's `−24/+36`. The two requirements are arithmetically incompatible — with fixed 60 months of padding, the share is `span / (span + 60)`, so reaching 60 % would need a data span of **≥ 90 months (7.5 years)**. No athlete in the 10–15 age band can ever satisfy SC-008 under FR-011.

Secondary observation: the spec's stated baseline ("under 5 % today") also does not reproduce — the retired chart measured **8.4 %** on the same fixture. Both SC-008 numbers appear to be estimates rather than measurements.

**The gate did not change the window**, because moving it is a specification decision, not a defect fix: it would contradict a `MUST` (FR-011), invalidate the T046 bounds tests and T048's implementation, and change the clinical reading of the curve (less reference context around the measurements). Options for the owner / `product-manager`, in the order the gate would recommend them:

1. **Amend SC-008** to the achieved, measurable improvement (e.g. "≥ 18 %, at least double today's 8.4 %") and keep FR-011 as the normative rule. Lowest risk; no code change.
2. **Amend FR-011 to proportional padding**, e.g. `pad = max(6, 0.35 × span)` per side, which puts a 14-month span at ~59 % while still showing context. Requires reworking `computeAgeWindow`, the T046 tests and the T047 chart expectations.
3. Keep both and accept a documented, permanent gap — not recommended; an unachievable success criterion will resurface at every future gate.

Until one of these is chosen, **T055 stays unchecked in `tasks.md`** and Phase 5 is not signed off.

## Fixes applied by the gate

1. **`src/routes/athletes/AthleteDetailPage.test.tsx`** (8 failing) and **`src/routes/parents/__tests__/MyAthleteDetailPage.growth.test.tsx`** (2 failing) — collateral breakage from T052 flagged by its own worker. Both files mocked `@/components/athletes/GrowthCharts`, a module that no longer exists, so the mocks silently went inert and the real `GrowthCurveSection` rendered instead. The gate repointed the mocks to `@/components/athletes/growth/GrowthCurveSection` with the new `growth-curve` test id (also in the three sibling files whose fixtures happen to have zero records — `AthleteDetailPage.strava.test.tsx`, `MyAthleteDetailPage.test.tsx`, `MyAthleteDetailPage.activities.test.tsx` — so their isolation survives a future fixture change).
2. **T004/T005 regression guard preserved, not deleted.** The parent-page assertion "`phvAgeMonths` comes from the newest record" no longer has a page-level observation point, because T052 correctly moved that derivation into `GrowthCurveSection`. Rather than drop the guard, the gate **split** it: the page test now asserts the page hands the curve the backend's list unreordered (`data-record-ids = "3,2,1"`), and three new cases in `growth/__tests__/GrowthCurveSection.test.tsx` assert `findLatestRecord` drives `phvAgeMonths` (162 months, not 144) **including when the input array is shuffled**, plus the no-PHV fallback. Net effect: the defect the audit found is now guarded closer to the code that can reintroduce it.
3. **`src/components/athletes/growth/PercentileToolbar.tsx`** — the toggle items used the arbitrary value `border-[rgba(34,42,53,0.12)]` instead of the design token. It passed the hex grep but breaks the dark-mode override (`--color-border-gray` flips to `rgba(255,255,255,0.1)` in `style.css:258`) and sits at a different opacity than the rest of the product. Replaced with `border-border-gray`. Toolbar tests re-run green.

## Design-system spot check (T055 tokens audit)

- **Tokens**: no raw hex anywhere under `components/athletes/growth/`, and after fix 3 above no arbitrary `rgba()` either — every colour resolves through `var(--color-*)` or its Tailwind utility.
- **Status is icon + label**: the band column in `PercentileTable` renders a `StatusBadge`-style label, never a bare colour; the chart's status palette (`success`/`warning`/`danger`) is used only for band semantics, and the athlete series uses the accent, per 033 FR-003.
- **Touch targets**: every `ToggleGroupItem` and `Button` in the toolbar is `min-h-12` (≥ 48 px).
- **Chart non-negotiables**: solid 1 px grid, thin marks, one recessive P3–P97 band (no full-height alarm fills), text never in the series colour, table view as the accessible alternative to the chart.

## Deferrals (accepted)

| Item | Reason | Where it lands |
|---|---|---|
| **T054** — run `e2e/growth.spec.ts` part 2 green | Same blocker as T044 and unchanged since the Phase 4 gate: the local docker MySQL volume predates the current seed fixture, so `backend/scripts/seed.py` early-returns and the coach account every spec assumes does not authenticate. Proven not specific to this wave — the untouched `e2e/auth.spec.ts::E2E-001` fails at the identical line against the same stack. Needs the local stack reset to the demo seed (or a dedicated e2e stack). | Phase 7 **T072** (full e2e gate); the spec file is complete, typechecks and already targets the post-T052 DOM. |
| Visual review of the curve on a real tablet | Needs the dev stack and a device. | `quickstart.md` §3 during T077. |

## Blockers for the next wave

**One, and it is a decision, not code.** Phase 6 (US4, family view) depends on T059 adding `preset="family"` to `PercentileChart`/`GrowthCurveSection` — that work is unblocked and can start, since the `preset="family"` code path already exists in `PercentileChart.tsx` (built ahead of schedule by the T050 worker) and only needs wiring plus the family copy. **But Phase 5 cannot be signed off until the owner or `product-manager` resolves the SC-008 vs FR-011 conflict above**, because option 2 would change `computeAgeWindow` and therefore the family chart's default window as well — doing Phase 6 first and the window change second would mean redoing the family-chart tests.

---

**Signed**: `engineering-lead` (wave gate, Phase 5 / US3) — 2026-09-04
**Verdict**: Phase 5 **FAIL (blocked on a specification conflict, not on code quality)**. 8 of 10 tasks verified complete and marked `[X]` in `tasks.md` (T046–T053); **T054** unchecked and deferred with the accepted environment reason above; **T055** unchecked because SC-008 measures 18.9 % against a required 60 % and the requirement as written is unachievable under FR-011. Frontend typecheck clean, 3882/3883 tests green with the one failure proven pre-existing, both grep gates satisfied, zero regressions introduced by this wave.

---

# Phase 5 repair pass — 2026-09-04 (`engineering-lead`)

Second pass over the two items the Phase 5 gate left open (T054, T055). No source file was changed in this pass; the work was independent verification, a corrected impact analysis and a re-scoped hand-off.

## 1. SC-008 re-measured against the module itself (T055)

The first gate measured with a script that had the `AGE_WINDOW_*` constants copied out of `window.ts`. This pass re-measured by **importing `src/lib/growth/window.ts` directly** (`npx jiti`), so the numbers come from the shipped `computeAgeWindow`, not from a transcription.

| Case | Data span | Window (months) | Width | Measurements cover |
|---|---|---|---|---|
| **SC-008 fixture** — 3 measurements over 14 months (141, 148, 155) | 14 mo | [117, 191] | 74 mo | **18.92 %** |
| Same fixture on the retired chart (full 5–19 range) | 14 mo | [61.5, 228.5] | 167 mo | 8.38 % |
| Same span at the top of the product band (166, 173, 180) | 14 mo | [142, 216] | 74 mo | 18.92 % |
| Same span with maximal bottom clamping (62, 69, 76) | 14 mo | [61.5, 112] | 50.5 mo | 27.72 % |
| Same span with maximal top clamping (214, 221, 228) — age 17.8–19, outside the product band | 14 mo | [190, 228.5] | 38.5 mo | **36.36 %** |

**Stronger conclusion than the first gate reached.** 36.36 % is the *absolute ceiling* for a 14-month span under FR-011 — it requires an athlete at the WHO ceiling (19 years) so that clamping removes the whole +3-year pad. SC-008 is therefore unachievable for a 14-month span **at any age**, not merely in the 10–15 band. Unclamped, 60 % needs a span ≥ 90 months; even with top clamping helping, 72 months of span still only reaches 58.78 %.

Confirmed unchanged from the first gate: `window.ts` implements FR-011 (`[first − 2 y, last + 3 y]`, clamped) and R-07 exactly, so this is a **specification conflict**, not a defect. The window was again **not** retuned: overriding a `MUST` to make a success criterion pass needs the owner, not a gate.

## 2. Correction — Phase 6 is **not** blocked by the SC-008 decision

The first gate held Phase 6 back on the grounds that option 2 (proportional padding) would also change the family chart and force redoing the T059 tests. That coupling does not hold, verified by reference search:

- `computeAgeWindow` is referenced in exactly three files: `src/lib/growth/window.ts`, `src/lib/growth/window.test.ts` and `src/components/athletes/growth/PercentileChart.tsx` (one memoised call site, line 478). Nothing else in `src/` or `e2e/` consumes the window API.
- The window is asserted **only** in `window.test.ts` (11 `computeAgeWindow` assertions). No component or route test pins window bounds.
- T059's subject is the family preset — which series render, the legend, the caption, and the hidden axis/detail toggles (FR-016). `range` reaches the chart as an independent prop; the family preset does not read the padding constants.

**Net:** whichever option the owner picks, its blast radius is `window.ts` + `window.test.ts` (plus the one call site if the signature changes) — disjoint from T059. Phase 6 can start while the SC-008 decision is pending. What stays blocked is **signing Phase 5**, not the next wave.

## 3. T054 — re-diagnosed, and it now has a privacy blocker

The first gate attributed T054 to "no working dev stack". That is not the state of the machine, and the real reason is more restrictive:

- The stack **is** up and healthy: `me-backend-1`, `me-mysql-1` (healthy) and `me-mailhog-1` running; `GET /health` → 200.
- The 401 is reproducible outside Playwright: `POST /api/auth/login` with the seeded coach credentials returns `401 {"detail":"Email o contraseña incorrectos"}`. The `users` table confirms why — the coach account the specs assume does not exist (of the `@trochyruta.com` demo addresses, only the admin and one parent security-test account are present), because `backend/scripts/seed.py` early-returns whenever a `clubs` row already exists.
- **New, and decisive: the local database does not contain demo data.** Cross-checking the 15 `athletes` rows against the first names in the committed demo seed returns **0 matches**, and the user table holds 28 coach and 29 parent accounts — far beyond what the demo seed creates. Playwright writes screenshots, traces and videos on failure, so running the growth specs against this database would produce artifacts containing identifiable data about minors. **That is forbidden by the project's privacy rule regardless of whether the login is fixed**, so T054 must not simply be unblocked by creating the missing coach account on this stack.
- Fixture gap on top of that: no athlete in this database has more than 2 anthropometric records (distribution 2,1,1,1,1,1 across 6 athletes), while the growth specs and SC-008 assume three measurements spanning ≥ 14 months.
- `docker compose down -v` would destroy the owner's local dataset. Not a gate decision, and not necessary — see the hand-off below.

**Hand-off (revised).** Owner: `devops-engineer`, then `qa-engineer`.

1. Stand up a **dedicated e2e stack** — separate compose project name and volume, so the existing dev database is untouched — with `APP_ENV=development` so the demo seed runs on an empty schema.
2. Extend the demo seed with a synthetic athlete carrying **≥ 3 anthropometric records spanning ≥ 14 months**, so `growth.spec.ts` part 2 and the SC-008 check have a fixture (synthetic names only).
3. Point Playwright at that stack, then run `e2e/growth.spec.ts` (T044 + T054), `e2e/growth-parent.spec.ts` (T064) and the Phase 7 gate `T072`.

This same stack is a prerequisite for T064 and for the `quickstart.md` run in T077 — it is a Phase 7 dependency, not a Phase 5 one.

## 4. Regression evidence (baseline differential at `HEAD` = 84c8061)

Per the wave-gate rule, "pre-existing" was proven with a detached `git worktree` at `HEAD` (venv, `.env` and `data/` symlinked in so both lanes take the same code path), not asserted.

| Lane | Baseline (`HEAD`) | Branch | Verdict |
|---|---|---|---|
| `backend`: `.venv/bin/python -m pytest -q` | 225 failed / 3640 passed | 225 failed / 3686 passed | **Failure sets byte-identical** (`diff` on the sorted `FAILED` lists is empty) → zero regressions, **+46 new passing tests**. All 225 are the same environmental failure: the suite resolves the docker hostname `mysql`, unreachable from the host. |
| `backend`: `ruff check app tests` | 331 errors | 330 errors | No new lint debt (one error fewer). |
| `frontend`: `npx vitest run src/lib/__tests__/datetime.test.ts` | 1 failed / 42 passed | 1 failed / 42 passed | The `currentSeason` failure reproduces at `HEAD`; its own control line (`new Date("2027-01-01T02:00:00Z").getFullYear() === 2027`) is false in `America/Bogota` (UTC−5). Pre-existing and timezone-driven. |
| `frontend`: `npx vitest run` (full) | — | 323/324 files, 3882/3883 tests | The single failure is the row above. |
| `frontend`: `npm run typecheck` | — | 0 errors | — |
| `frontend`: `npx vitest run src/components/athletes src/lib/growth src/routes` | — | 106/106 files, 1307/1307 tests | — |

## 5. Contract and design-system re-verification

- Props match the Phase 5 contract exactly, read from source: `PercentileChart` (`indicator, records, sex, birthDate, phvAgeMonths?, axis, range, detail, preset?`), `PercentileToolbar` (`indicators, indicator, onIndicator, axis, onAxis, showAxisToggle, range, onRange, detail, onDetail, view, onView, onExport?, exporting?`), `PercentileTable` (`records, indicator, sex, birthDate`), `GrowthCurveSection` (`athlete, records, mode`). No extra public surface.
- Tokens: `grep` for raw hex and for arbitrary `rgba()/hsl()` under `components/athletes/growth/` both return nothing.
- Touch targets: all four `ToggleGroup` sets share one class constant carrying `min-h-12`; both `Button`s use `size="lg"` (`min-h-12` native). ≥ 48 px everywhere.
- Diacritics gate: the only three hits repo-wide are the snake_case backend field `focos_tecnicos` in the unrelated training module and a test id derived from it — identifiers, not user-facing copy.

---

**Signed**: `engineering-lead` (repair pass, Phase 5 / US3) — 2026-09-04
**Verdict**: unchanged — Phase 5 **FAIL**, blocked on one specification decision. T046–T053 stand verified. **T055 is OPEN pending the owner's choice between amending SC-008 (recommended) and amending FR-011**; a gate cannot make that call on the owner's behalf, and the measurement now proves the criterion is unreachable at any athlete age, which should make the decision straightforward. **T054 is blocked and re-scoped** to a dedicated, synthetically-seeded e2e stack owned by `devops-engineer`, for privacy reasons in addition to the missing account. Correction to the previous signature: **Phase 6 may start now** — it is not coupled to the SC-008 outcome.

---

# Phase 5 gate — third pass, 2026-09-04 (`engineering-lead`)

Third verification pass over Phase 5 (T046–T055). **No source file was changed in this pass** — everything below is independent re-verification plus one new quantitative finding that changes the recommendation the owner should act on. `tasks.md` was not modified either: T046–T053 already carry `[X]` and this pass confirms those marks are earned; T054 and T055 remain unchecked.

## Task-by-task verdict

| Task | Status | Evidence (command → result) |
|---|---|---|
| T046 — `lib/growth/window.test.ts` | **Done (verified)** | Included in `npx vitest run src/lib/growth` → part of **106 files / 1307 tests, all passing**. |
| T047 — component tests ×4 | **Done (verified)** | Gate enumerated the case names directly from the four files: `PercentileChart.test.tsx` **15**, `PercentileToolbar.test.tsx` **12**, `PercentileTable.test.tsx` **7**, `GrowthCurveSection.test.tsx` **12**. Every coverage item the task names is present: Peso dropped above 10 y (`GrowthCurveSection` "con age_decimal > 10 no ofrece Peso"), axis toggle hidden for IMC **and** for a parent role (3 cases), detail toggle on/off, one table row per record with stored values, export button + filename without identifiable data, `role="img"` + non-empty `aria-label`. The re-homed T011 assertions are visible too (PHV/PWV by indicator × sex ×4, bio-axis tick relabel, newest-record derivation under a shuffled list). |
| T048 — `lib/growth/window.ts` | **Done (verified)** | Gate read the source. `computeAgeWindow` = `[max(61.5, min(ages) − 24), min(228.5, max(ages) + 36)]` with a full-range fallback for no records and for an inverted clamp — **FR-011 and R-07 implemented exactly**. |
| T049 — `PercentileToolbar.tsx` | **Done (verified)** | Single shared class constant carries `min-h-12` on every `ToggleGroupItem` (line 58) and both `Button`s use `size="lg"` — ≥ 48 px confirmed by grep, not by assertion. Copy carries correct diacritics ("Cronológica", "Biológica"). |
| T050 — `PercentileChart.tsx` | **Done (verified)** | Token grep under `components/athletes/growth/` returns **nothing** for raw hex and **nothing** for arbitrary `rgba()/hsl()`. Behaviour pinned by the 15 chart tests above. |
| T051 — `PercentileTable.tsx` + `GrowthCurveSection.tsx` | **Done (verified)** | Both present; privacy-relevant behaviour is test-pinned ("no expone el día exacto de la evaluación", "genera un enlace de descarga sin datos identificables"). |
| T052 — slot replaced, old components deleted | **Done (verified)** | `git status` shows `GrowthCharts.tsx`, `GrowthCharts.test.tsx`, `PercentileCurves.tsx`, `PercentileCurves.test.tsx`, `PercentileCurves.a11y.test.tsx` as `D`; `ls` confirms they are gone from disk. `e2e/history.spec.ts:98` targets `growth-curve`. The `growth/index.ts` barrel exports the four new components and their prop types. |
| T053 — diacritics | **Done (verified)** | `grep -rn "Cronologica\|Biologica\|Interpretacion\|tecnicos" src` → 3 hits, all the snake_case backend field `focos_tecnicos` in the unrelated training module plus a test id derived from it. **Identifiers, not user-facing copy.** No growth-module hit. |
| T054 — run `e2e/growth.spec.ts` part 2 | **Deferred (accepted)** | Spec file complete and statically valid: `npx playwright test --list e2e/growth.spec.ts` → **2 tests discovered** (`E2E-040-001`, `E2E-040-002`). Not executed; see *Deferral* below. |
| T055 — wave review / SC-008 | **OPEN — escalated to the owner** | Measurement re-run independently this pass (below). Tokens audit passes; SC-008 does not, and cannot, under FR-011. |

## Gate commands (this pass)

| Command | Result |
|---|---|
| `cd frontend && npm run typecheck` | **PASS** — `tsc --noEmit`, 0 errors |
| `cd frontend && npx vitest run src/components/athletes src/lib/growth src/routes` | **PASS — 106/106 files, 1307/1307 tests** |
| `cd frontend && npx vitest run` (full suite) | **323/324 files, 3882/3883 tests.** Single failure = `src/lib/__tests__/datetime.test.ts > currentSeason`, **pre-existing** (proof below). |
| `git diff HEAD -- frontend/src/lib/datetime.ts frontend/src/lib/__tests__/datetime.test.ts` | **Empty** — both files byte-identical to `HEAD` (`84c8061`), so this branch cannot have caused the failure. The test's own control line asserts `new Date("2027-01-01T02:00:00Z").getFullYear() === 2027`, false in `America/Bogota` (UTC−5). Environmental, unrelated to feature 040. |
| `grep -rnE "#[0-9a-fA-F]{6}" src/components/athletes/growth/` | **PASS — no output** |
| `grep -rnE "\[(rgba?\|hsla?)\(" src/components/athletes/growth/` | **PASS — no output** |
| `npx playwright test --list e2e/growth.spec.ts` | **PASS — 2 tests discovered**, imports and syntax valid |
| `npx jiti` against the shipped `src/lib/growth/window.ts` | SC-008 measurement, table below |

Phase 5 touched **no backend file** (`git status backend` shows only Phase 2–4 work), so the Phase 4 / repair-pass backend baseline differential — identical 225-failure sets against a clean `HEAD` worktree, all from the unreachable docker hostname `mysql`, plus 330 vs 331 ruff errors — still stands unchanged and was not re-run.

## SC-008 — re-measured independently, and the recommendation sharpened

Measured by importing the **shipped** `computeAgeWindow` (no transcribed constants), synthetic ages in months only:

| Case (ages in months) | Span | Window | Width | Coverage |
|---|---|---|---|---|
| **SC-008 fixture** (141, 148, 155) | 14 mo | [117, 191] | 74 mo | **18.92 %** |
| Same fixture, retired full-range chart | 14 mo | [61.5, 228.5] | 167 mo | 8.38 % |
| Same span, maximal top clamp (214, 221, 228) | 14 mo | [190, 228.5] | 38.5 mo | **36.36 % — absolute ceiling** |
| Same span, maximal bottom clamp (62, 69, 76) | 14 mo | [61.5, 112] | 50.5 mo | 27.72 % |
| 72-month span (100, 136, 172) | 72 mo | [76, 208] | 132 mo | 54.55 % |
| 90-month span (100, 145, 190) | 90 mo | [76, 226] | 150 mo | 60.00 % |

Reproduces the repair pass exactly. **SC-008 requires ≥ 60 %; the delivered chart yields 18.92 %** — a 2.26× improvement on the 8.38 % the retired chart achieved, but not the number in the spec. This is **not** an implementation defect: `window.ts` implements FR-011 verbatim. With fixed padding the coverage is `span / (span + 60)`, so 60 % needs a data span of **exactly 90 months (7.5 years)** — impossible for a 10–15-year-old cohort, and 36.36 % is the ceiling for a 14-month span **at any age**.

**New this pass — the previously recommended "option 2" also fails SC-008.** The repair pass proposed `pad = max(6, 0.35 × span)` per side and estimated ~59 %. That estimate is wrong. Coverage is `span / (span + 2·pad)`; solving for 60 % gives `pad = span / 3`, and since `0.35 > 1/3` that rule caps out at 58.82 % for *any* span:

| Span | Pad per side needed for 60 % | Pad under `max(6, 0.35 × span)` | Coverage it actually yields |
|---|---|---|---|
| 12 mo | 4.00 | 6.00 | 50.00 % |
| **14 mo** | **4.67** | 6.00 | **53.85 %** |
| 24 mo | 8.00 | 8.40 | 58.82 % |
| 48 mo | 16.00 | 16.80 | 58.82 % |

So satisfying SC-008 at 14 months requires a padding rule with a floor **below ~4.7 months per side** — a curve showing under five months of reference context on either side of the measurements, which is worse clinically than what FR-011 asks for and would make the chart nearly useless for a two-measurement athlete. **Option 2 is therefore not a viable repair, and the choice collapses to amending SC-008.**

### Recommendation to the owner / `product-manager`

1. **Amend SC-008** to the achieved and measurable improvement — e.g. *"the measurements span at least 18 % of the curve's horizontal width by default, at least double the 8.4 % of the previous full-range chart"* — and keep FR-011 as the normative rule. **No code change; recommended.**
2. Amend FR-011 to proportional padding with a floor `≤ 4.67` months per side. Reworks `window.ts` + `window.test.ts` + the single call site, and buys the number at the cost of clinical context. **Not recommended** — and note the previously suggested `max(6, 0.35 × span)` formulation does *not* deliver 60 %.
3. Accept a documented permanent gap. Not recommended — an unreachable criterion resurfaces at every future gate.

The gate did **not** retune `computeAgeWindow`. Overriding a `MUST` (FR-011) so a success criterion reports green is an owner decision; a workflow instruction to "resolve the item" is not that consent.

**Follow-up bound to this decision (deliberately not done now):** the header docstring of `frontend/src/lib/growth/window.ts` still claims the window exists *"para que ocupen ≥ 60 % del ancho de la gráfica (spec FR-011/SC-008)"*. That sentence is inaccurate today. It was left untouched rather than reworded twice, because its correct wording depends on which option the owner picks — a one-line edit once the decision lands.

## Phase 6 coupling — re-confirmed unblocked

`computeAgeWindow` is referenced in exactly three files (`window.ts`, `window.test.ts`, `PercentileChart.tsx`), window bounds are asserted only in `window.test.ts`, and T059's subject (family preset series/legend/caption/hidden toggles) is a disjoint surface. Whatever the owner decides, the blast radius is two source files and one test file. **Phase 6 may start; what stays unsigned is Phase 5.**

## Deferral (accepted)

| Item | Reason | Where it lands |
|---|---|---|
| **T054** — execute `e2e/growth.spec.ts` part 2 | Needs a dev stack that does not yet exist. Two independent reasons: (a) `backend/scripts/seed.py` early-returns when a `clubs` row exists, so the coach account every spec assumes was never created — `POST /api/auth/login` returns 401 outside Playwright too, while `GET /health` returns 200, so the stack is healthy and this is a seed problem; (b) **privacy** — the local database holds real, non-demo data, and Playwright writes screenshots, traces and videos on failure, so the growth specs must not run against it even after the login is fixed. `docker compose down -v` would destroy the owner's dataset and is not a gate decision. | `devops-engineer` stands up a dedicated e2e stack (separate compose project + volume, `APP_ENV=development` so the demo seed runs on an empty schema) with a synthetic athlete carrying ≥ 3 anthropometric records over ≥ 14 months; then `qa-engineer` runs T044 / T054 / T064 at the Phase 7 gate **T072**. Same prerequisite for the `quickstart.md` run in T077. |

---

**Signed**: `engineering-lead` (wave gate, Phase 5 / US3 — third pass) — 2026-09-04
**Verdict**: Phase 5 **FAIL**, unchanged in outcome and sharpened in analysis. **T046–T053 verified complete** and correctly marked `[X]`; typecheck clean, 1307/1307 tests green on the wave's paths, 3882/3883 on the full suite with the one failure proven pre-existing, both token greps and the diacritics gate clean, zero regressions. **T054 deferred** with an accepted environment + privacy reason. **T055 is OPEN and escalated**: SC-008 measures 18.92 % against a required 60 %, is unreachable at any athlete age under FR-011, and the padding rule previously floated as the alternative fix does not reach 60 % either — leaving "amend SC-008" as the single viable resolution, which only the owner may authorise.
