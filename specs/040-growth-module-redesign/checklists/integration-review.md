# Integration review — feature 040 (Phases 2–7)

**Task**: T073 · **Role**: `engineering-lead` (wave gate) · **Date**: 2026-09-04
**Branch**: `feat/040-growth-module-redesign` · **Base commit**: `046569f`

Scope: verify the Phase 7 wave (T066–T073), close the items held from earlier
waves (T055; T044/T054/T064), and review Phases 2–7 against the Constitution
Check table in `plan.md`, spec 033 FR-003 and the dataviz non-negotiables.

---

## 1. Wave tasks

| Task | Owner | Status | Evidence |
|---|---|---|---|
| **T066** — `MaturationTimeline.test.tsx` + updated `MorphologyCard.test.tsx` / `PHVBadge.test.tsx` | qa-engineer | **[X] Done** | `npx vitest run src/components/athletes/growth/__tests__/MaturationTimeline.test.tsx` → **19/19 pass**. Gate re-ran the whole area: `npx vitest run src/components/athletes src/lib/growth src/routes/athletes src/routes/parents src/components/shared` → **85 files, 1168/1168 pass**. Test file covers the three stages, active-stage highlight, today-marker position + `[-3,+3]` clamp, the offset/PHV-age caption, the `role="img"` text alternative and jest-axe with and without data. |
| **T067** — `AthleteDetailPage.tabs.test.tsx` | qa-engineer | **[X] Done** | New file `frontend/src/routes/athletes/__tests__/AthleteDetailPage.tabs.test.tsx`. `npx vitest run src/routes/athletes/AthleteDetailPage.test.tsx src/routes/athletes/__tests__/AthleteDetailPage.tabs.test.tsx` → **2 files, 43/43 pass**. Written red (2 failing) before T070 and now green without edits, which is what the TDD rule asks for. Fixtures are synthetic ("Atleta Ficticio", fictitious DOB, no notes). |
| **T068** — `MaturationTimeline.tsx` in coach mode | react-ui-engineer | **[X] Done** | Gate read `frontend/src/components/athletes/growth/MaturationTimeline.tsx`: pure CSS/flex (no recharts), three equal segments matching Mirwald's `-1 / +1` cut-offs, marker positioned by inline `left: N%`, `role="img"` + descriptive `aria-label`, caption `Offset {±x.x} · PHV estimado a los {age} años` verbatim from `contracts/growth-tab-ui.md`. Inserted in `GrowthTab.tsx:203`, inside the coach branch between `GrowthCurveSection` (line 200) and `MorphologyCard` (line 209); **absent from the parent branch** (lines 298+), as the contract requires. Exported from `growth/index.ts`. |
| **T069** — `MorphologyCard` → `StatCard`, `PHVBadge` → `StatusBadge`, PHV colour maps deleted | react-ui-engineer | **[X] Done** | `git diff HEAD` confirms: the four hand-rolled tiles in `MorphologyCard.tsx` are now `shared/StatCard` with copy unchanged; `PHVBadge.tsx` lost `badgeClasses()` and delegates to `StatusBadge` (Pre = neutral, Circa = warning, Post = success — icon + label, Constitution III); `PHV_LABELS` + `PHV_BADGE_COLORS` deleted from `TrainingReadiness.tsx` (now renders `<PHVBadge>`); `phvColor()` and its call site deleted from `AthleteDetailPage.tsx`. `npx vitest run src/components/athletes/MorphologyCard.test.tsx src/components/athletes/PHVBadge.test.tsx` → **22/22 pass**. |
| **T070** — top tiles from `useGrowthSummary`, no auto-jump | react-ui-engineer | **[X] Done** | Both pages: page-local `StatCard` and `formatRelativeDate` deleted; tiles are `shared/StatCard` + `shared/StatusBadge` fed by `useGrowthSummary` via `getMeasurementStatusMeta`. `hasSetInitialTab` and the auto-select-growth `useEffect` are gone from `AthleteDetailPage.tsx`; the `?tab=` URL-sync effect is kept. T067 passes unmodified. **One defect found and fixed by this gate — see §3.** |
| **T071** — build gate | react-ui-engineer | **[X] Done** | `npm run build && npm run check:chunks` → `OK — recharts chunk and WHO growth reference are not on the entry path.` Gate re-verified independently: `dist/index.html` module-preloads neither `CartesianChart-*.js` nor `growth-reference-who-*.js`; the entry's only mention of the recharts chunk is inside the `__vitePreload` dependency string array of a **dynamic** `import()`. Growth chunk `GrowthTab-*.js` = **16.9 kB gzip** (budget 150 kB). Entry 336.68 → 283.38 kB gzip. Methodology caveat on the "effective first-paint" figure added to `checklists/build-baseline.md`. |
| **T072** — full frontend gate | qa-engineer | **[ ] Partially done — Playwright leg deferred** | Legs 1–3 re-run and green at this gate (`npm run typecheck`, full `npx vitest run`, the growth/a11y suites — see §2). Leg 4 (`npx playwright test e2e/growth.spec.ts e2e/growth-parent.spec.ts e2e/history.spec.ts e2e/anthropometry.spec.ts e2e/target-size.spec.ts`) **never executed**: the isolated e2e stack cannot boot. Left unchecked in `tasks.md`; reason accepted and recorded in §4. |
| **T073** — integration review | engineering-lead | **[X] Done** | This document. |

### Items held from earlier waves

| Task | Status | Evidence |
|---|---|---|
| **T055** — SC-008 wave review | **[X] Done** | SC-008 was amended in `spec.md:168` on 2026-09-04 (option 1 of the three the Phase 5 gate escalated). Re-measured against the **shipped** `frontend/src/lib/growth/window.ts` on the 14-month / three-measurement fixture: **18.92 %** of the window width (≥ 18 % required), **2.26×** the retired full-range chart's 8.38 % (≥ 2× required), **81.7 px** between consecutive points at 1024 px (≥ 60 px required), and `"full"` restores `[61.5, 228.5]`. Plot geometry read out of `PercentileChart.tsx:572` (`margin`) and `:591–596` (`YAxis width={40}`), not estimated. `npx vitest run src/lib/growth/window.test.ts` → **28/28 pass**. Full table in `checklists/coach-tab.md` § "SC-008 — re-measured against the amended criterion". FR-011 and `computeAgeWindow` were **not** changed. |
| **T044** — Playwright `growth.spec.ts` part 1 | **[ ] Not done** | Spec file written and typechecks, but never executed green on the isolated stack. Blocker in §4. |
| **T054** — Playwright `growth.spec.ts` part 2 | **[ ] Not done** | Same. |
| **T064** — Playwright `growth-parent.spec.ts` | **[ ] Not done** | Same. |

---

## 2. Verification commands run by this gate

| Command | Result |
|---|---|
| `cd frontend && npm run typecheck` | **PASS** — `tsc --noEmit`, 0 errors |
| `cd frontend && npx vitest run` (full suite, clean run) | **329 files: 327 pass / 2 fail · 3952 tests: 3950 pass / 2 fail.** Both failures pre-existing — see §5 |
| `cd frontend && npx vitest run src/components/athletes src/lib/growth src/routes/athletes src/routes/parents src/components/shared` | **PASS — 85 files, 1168/1168** |
| `cd frontend && npx vitest run src/lib/growth/window.test.ts` | **PASS — 28/28** (includes the four SC-008 cases) |
| `cd frontend && npm run build` | **PASS** — entry 1,093.90 kB / 283.38 kB gzip; `GrowthTab-*.js` 61.61 kB / 17.42 kB gzip |
| `cd frontend && npm run check:chunks` | **PASS** — `recharts chunk and WHO growth reference are not on the entry path` |
| `cd backend && .venv/bin/python -m pytest tests/routers/test_growth_summary.py tests/services/test_growth_summary.py tests/services/test_growth_seed.py tests/scripts/test_backfill_anthropometry.py tests/routers/test_anthropometry_bmi.py -q` | **PASS — 50/50** |
| `cd backend && .venv/bin/python -m pytest -q` (whole suite, informational) | 3699 pass / 225 fail — **every** failure is environmental, see §5 |
| `cd backend && ruff check app tests scripts` | 342 findings **repo-wide, all pre-existing**; scoped to the files this feature touches or created (`tests/test_ai_router.py`, `app/services/ai/prompts/`, `app/services/growth_summary.py`, `app/schemas/growth.py`, `app/routers/growth.py`, `app/routers/anthropometry.py`, `app/scripts/backfill_anthropometry.py`, `app/seed_growth_data.py`, `scripts/export_who_lms_csv.py`, `app/services/training/growth_chart_builder.py`, `app/services/ai/use_cases/phv_explainer.py`) → **All checks passed!** |
| `cd frontend && grep -rn "#[0-9a-fA-F]\{6\}" src/components/athletes/growth/` | **PASS — no output** |
| `cd frontend && grep -rn "Cronologica\|Biologica\|tecnicos" src/` | 3 hits, all the unrelated `focos_tecnicos` backend field / test id in the training module — no growth-module hit (unchanged from the Phase 5 gate's accepted result) |

---

## 3. Defect found and fixed by this gate

**FR-016 violation on the parent page top tiles** (introduced by T070, this wave).

`T070` instructs both `AthleteDetailPage.tsx` and `MyAthleteDetailPage.tsx` to
render the top tiles from `useGrowthSummary` as "stage, talla + P, velocidad,
próxima medición". Applied literally to the parent page that shipped
`Etapa: Circa-PHV` and `Talla 155 cm / P1` to a family — but **FR-016 is a
MUST**: the family view "MUST NOT show Z-scores, percentiles, maturity offset,
clinical headline labels…". The privacy audit (T065) could not catch it: it
scoped itself to `frontend/src/components/athletes/growth/**`, and this page
sits outside that folder — and T070 landed after the audit.

The existing FR-016 assertion in `MyAthleteDetailPage.growth.test.tsx` used
`/P\d{1,2}\b/`, which does not match: in `container.textContent` the tiles
concatenate to `…P1Velocidad…`, so there is no word boundary after the digit.

Fix (test first, seen red, then implementation, then green):

1. `frontend/src/routes/parents/__tests__/MyAthleteDetailPage.growth.test.tsx` —
   new case *"las tarjetas superiores usan lenguaje familiar: sin percentil ni
   etiqueta clínica de etapa (FR-016)"*, asserting on the tiles **before**
   opening the growth tab, with `/P\d{1,2}/` (no `\b`) and `/PHV/`.
   Verified failing against the pre-fix page.
2. `frontend/src/routes/parents/MyAthleteDetailPage.tsx` — added
   `FAMILY_STAGE_LABEL` (`Desarrollo temprano` / `Pico de crecimiento` /
   `Crecimiento estabilizándose`, the short form of
   `growth/FamilyStageCard.tsx::stageMessage`) for the Etapa tile, and dropped
   the `P{percentile}` hint from the Talla tile (`Sin medición registrada`
   when there is no height). Velocity in cm/año stays: it is not on FR-016's
   prohibited list and it is the family-legible number.

The coach page keeps stage + percentile — correct there, and unchanged.

`npx vitest run src/routes/parents/` → **13 files, 115/115 pass**;
`npm run typecheck` → clean.

---

## 4. Deferrals (accepted) and their blocker

| Item | Reason | Owner to close |
|---|---|---|
| **T044, T054, T064** (Playwright specs) and the Playwright leg of **T072** | The isolated e2e stack (`docker-compose.e2e.yml`, project `trocha-e2e`) cannot boot. `alembic upgrade head` crashes on any fresh MySQL volume. | `database-architect`, then `qa-engineer` re-runs the specs |

**Blocker, verified independently by this gate (not taken on the worker's word)**:
`backend/alembic/versions/e1f2a3b4c5d6_technique_gymkhana_library.py:270` executes
`from app.data.technique_catalog import EXERCISES, MATERIALS, SKILLS` at upgrade
time. `backend/app/data/` contains only `cdc_lms/` and `who_lms/` — the module
was deleted by commit `718d249` (feature 038), which removed the whole technique
module. Two sibling migrations have the same defect:
`f1a2b3c4d5e6_add_layout_json_to_technique_exercises.py:54`
(`technique_catalog.GYMKHANA_LAYOUT_BACKFILL`) and
`a7b8c9d0e1f2_strength_training_library.py:278` (`app.data.strength_catalog`).

This is **pre-existing and outside feature 040** — `git diff --name-only HEAD --
backend/` returns two files, neither of them a migration, and `718d249` predates
this feature's commit `046569f`. Production is unaffected today only because the
migration is already applied there; **any fresh database — a new Render
instance, a restored backup, the e2e stack — cannot migrate**. A later migration
(`d0e1f2a3b4c5_remove_technique_strength_catalog.py`) drops those tables again,
so the seed block has no downstream consumer; the cheapest fix is likely to make
the three imports tolerant of the missing module. This gate deliberately did
**not** apply it: it is a migration-chain change in another feature's area and
should not ride inside the growth PR.

The same `718d249` cleanup also left `backend/tests/test_circuit_diagram_partial.py`
behind without its Jinja template (18 failures, §5) — worth folding into the
same fix.

---

## 5. Pre-existing failures (not caused by this wave)

| Failure | Count | Proof it is pre-existing |
|---|---|---|
| `frontend/src/lib/__tests__/datetime.test.ts > currentSeason > usa el año en CLUB_TIMEZONE…` | 1 | `git diff HEAD -- frontend/src/lib/datetime.ts frontend/src/lib/__tests__/datetime.test.ts` → **empty**. The test's own control line asserts `new Date("2027-01-01T02:00:00Z").getFullYear() === 2027`, which is false on a machine whose system TZ is `America/Bogota`. Environment-dependent; green in CI (UTC). |
| `frontend/src/hooks/ai/useRaceRun.test.ts > … no se marca como 'no responde'` | 1 | Fake-timer/polling test, flaky under a loaded full-suite run. Isolated re-runs: **3× 21/21 pass**. `git diff HEAD` on both `useRaceRun.ts` and its test → **empty**. |
| Backend suite: `OperationalError (2003, "Can't connect to MySQL server on 'mysql'")` | 193 | These suites need the docker MySQL host `mysql`; not the offline aiosqlite lane. No growth/anthropometry test is among them. |
| Backend suite: `OSError: cannot load library 'libgobject-2.0-0'` (`tests/services/notification/test_stage_log_pdf.py`) | 13 | WeasyPrint native libs absent on this machine. |
| Backend suite: `jinja2.TemplateNotFound` (`tests/test_circuit_diagram_partial.py`) | 18 | Same root cause as the §4 blocker: commit `718d249` removed the technique module and its gymkhana-circuit template, but left this test file behind. Pre-existing, unrelated to feature 040. |
| Backend suite: `test_ai_factory.py::test_factory_openai_not_implemented` | 1 | Expects `LLMConfigError` for the OpenAI provider, which is now implemented. Untouched by this feature (only `phv_explanation_coach_v1.md` and `test_ai_router.py` changed on the backend). |
| `ruff check app tests scripts` — 342 findings | 342 | None in any file this feature touches or created (scoped re-run → "All checks passed!"). Dominated by `tests/privacy/`, `tests/test_mutation_kills.py`, `tests/routers/test_dashboard_summary.py`. |

---

## 6. Constitution / design-system review (Phases 2–7)

Against the Constitution Check table in `plan.md` and spec 033 FR-003:

| Rule | Verdict | Evidence |
|---|---|---|
| **I — code quality** | PASS | Scoped `ruff` clean; `tsc --noEmit` clean; no new runtime dependency (`MaturationTimeline` is CSS/flex, not a chart). |
| **II — testing (non-negotiable)** | PASS | Every wave task landed with its test task first; the gate's own fix in §3 followed red→green. 1168/1168 in the feature's area. |
| **III — UX consistency (status = icon + label, never colour alone)** | PASS | `PHVBadge` and `NextMeasurementCard`/`PercentileTable` render `shared/StatusBadge` (icon + text). `MaturationTimeline`'s active stage carries the brand accent **plus** semibold text **plus** the marker and caption repeating the same fact — colour is never the only channel, and the stage has no per-stage palette (the Pre = blue / Circa = amber / Post = green maps are deleted, T069). |
| **IV — performance budgets** | PASS with the recorded pre-existing violation | Growth lazy chunk 16.9 kB gzip ≤ 150 kB. Entry 336.68 → 283.38 kB gzip, still above the 250 kB route budget — the pre-existing violation already justified in `plan.md` Complexity Tracking; closing it needs the `App.tsx` route-splitting pass that plan.md scopes out. |
| **V — youth psychological-assessment safeguards** | PASS | `checklists/privacy.md` (T065): 0 critical / 0 high / 0 medium. `checklists/family-copy.md` (T063) signed. The one gap that audit could not see is closed in §3. |
| **033 FR-003 — solid hairline grid** | PASS | `<CartesianGrid stroke="var(--color-border-gray)" />`, no `strokeDasharray`. |
| **033 FR-003 — accent for the athlete's own series** | PASS | Athlete line and dots `var(--color-primary)`; reference series in `--color-charcoal` / `--color-mid-gray`; the P3–P97 band is the recessive `--color-light-gray`. |
| **033 FR-003 — status colours only for status** | PASS | `success`/`warning`/`danger` appear only in `PercentileChart.tsx`'s band-status map and in `StatusBadge`. No status colour on a data series, no full-height alarm fill. |
| **033 FR-003 — table view of charted data** | PASS | `PercentileTable.tsx` behind the toolbar's `Gráfica`/`Tabla` toggle, one row per record with the stored Z / percentile / band badge. |
| **Touch targets ≥ 48 px** | PASS | Every `ToggleGroupItem` in `PercentileToolbar.tsx` is `min-h-12`; its buttons are `size="lg"`; `StatCard`'s link wrapper is `min-h-12`. `MaturationTimeline` is non-interactive. |
| **Tokens, no raw hex** | PASS | Hex grep over `components/athletes/growth/` returns nothing; `MaturationTimeline.tsx` uses only `bg-primary/15`, `text-mid-gray`, `border-border-gray`, `bg-light-gray`, `text-charcoal`. |
| **Español neutro with diacritics** | PASS | Diacritics grep clean for the growth module; the strings added in §3 carry full diacritics. |
| **Minors' privacy (Ley 1581)** | PASS | New fixtures are synthetic ("Atleta Ficticio", fictitious DOB, no notes); no `first_name`/`last_name`/`birth_date` render in any growth component; evaluation dates obfuscated to "mes año". |

### Residual design-system debt (not blocking, not in this feature's task list)

- `frontend/src/components/athletes/MorphologyCard.tsx` still uses raw palette
  classes for the bike-fit category chip (`bg-blue-100 text-blue-800`,
  `bg-purple-100 text-purple-800`), the posture/ape-index notices
  (`amber-*` / `blue-*`) and an inline `rgba(34, 42, 53, 0.08)` separator. All
  **pre-existing**; T069 only scoped the PHV colour maps. Bike-fit is a
  category, not a status, so it should not borrow the status palette.

---

## 7. Files changed on the branch (uncommitted, `git status --short`)

Work from Phases 1–6 that was already committed is in `046569f`; the list below
is the delta on top of it.

**Modified (37)**

```
backend/app/services/ai/prompts/phv_explanation_coach_v1.md
backend/tests/test_ai_router.py
frontend/e2e/ai-insights-hitl.spec.ts
frontend/e2e/ai-insights-newsletter.spec.ts
frontend/e2e/ai-insights-parent.spec.ts
frontend/package.json
frontend/playwright.config.ts
frontend/src/api/ai.ts
frontend/src/components/ai/PHVExplanationCard.test.tsx
frontend/src/components/ai/PHVExplanationCard.tsx
frontend/src/components/athletes/MorphologyCard.test.tsx
frontend/src/components/athletes/MorphologyCard.tsx
frontend/src/components/athletes/PHVBadge.test.tsx
frontend/src/components/athletes/PHVBadge.tsx
frontend/src/components/athletes/TrainingReadiness.tsx
frontend/src/components/athletes/growth/FamilyBandCards.tsx
frontend/src/components/athletes/growth/GrowthCurveSection.tsx
frontend/src/components/athletes/growth/GrowthTab.tsx
frontend/src/components/athletes/growth/PercentileTable.tsx
frontend/src/components/athletes/growth/__tests__/GrowthCurveSection.test.tsx
frontend/src/components/athletes/growth/__tests__/GrowthTab.parent.test.tsx
frontend/src/components/athletes/growth/__tests__/GrowthTab.test.tsx
frontend/src/components/athletes/growth/__tests__/PercentileTable.test.tsx
frontend/src/components/athletes/growth/index.ts
frontend/src/components/newsletter/StageLogView.tsx
frontend/src/hooks/ai/usePHVExplanation.test.ts
frontend/src/hooks/ai/usePHVExplanation.ts
frontend/src/lib/growth/bands.ts
frontend/src/lib/growth/window.test.ts
frontend/src/lib/growth/window.ts
frontend/src/routes/athletes/AthleteDetailPage.test.tsx
frontend/src/routes/athletes/AthleteDetailPage.tsx
frontend/src/routes/parents/MyAthleteDetailPage.tsx
frontend/src/routes/parents/__tests__/MyAthleteDetailPage.growth.test.tsx
specs/040-growth-module-redesign/checklists/build-baseline.md
specs/040-growth-module-redesign/checklists/coach-tab.md
specs/040-growth-module-redesign/tasks.md
```

**Added / untracked (11)**

```
docker-compose.e2e.yml
frontend/e2e/growth-parent.spec.ts
frontend/scripts/e2e-stack.sh
frontend/src/components/athletes/growth/MaturationTimeline.tsx
frontend/src/components/athletes/growth/__tests__/MaturationTimeline.test.tsx
frontend/src/routes/athletes/__tests__/AthleteDetailPage.tabs.test.tsx
specs/040-growth-module-redesign/checklists/e2e-stack.md
specs/040-growth-module-redesign/checklists/family-copy.md
specs/040-growth-module-redesign/checklists/family-view.md
specs/040-growth-module-redesign/checklists/frontend-gate.md
specs/040-growth-module-redesign/checklists/privacy.md
specs/040-growth-module-redesign/checklists/integration-review.md  (this file)
```

**Deleted**: none in this wave. The Phase 5 deletions (`GrowthCharts.tsx`,
`PercentileCurves.tsx` and their tests) are already in `046569f`.

Of the modified files, this gate touched exactly two:
`frontend/src/routes/parents/MyAthleteDetailPage.tsx` and
`frontend/src/routes/parents/__tests__/MyAthleteDetailPage.growth.test.tsx`
(§3), plus the three checklist/tasks documents.

---

## 8. Outstanding before Phase 8

1. Fix the three migrations importing deleted `app.data.*` modules
   (`database-architect`), then run T044 / T054 / T064 and the Playwright leg of
   T072 (`qa-engineer`).
2. T027 / T028 (US1) still need a real MySQL `_test` database and the dev stack
   with WeasyPrint — unchanged from the Phase 3 gate.
3. Optional cleanup: the `MorphologyCard` palette debt in §6.

---

**Signed**: `engineering-lead` — 2026-09-04
