# Family view — Phase 6 gate (US4)

**Feature**: 040 growth module redesign · **Phase**: 6 — User Story 4 "Families see growth in family language"
**Branch**: `feat/040-growth-module-redesign` · **Gate date**: 2026-09-04
**Gate**: `engineering-lead` (wave review) · **Workers**: `qa-engineer` (T056, T057, T064), `react-ui-engineer` ×3 (T058/T059, T061/T062), `fastapi-architect` (T060), `parent-communicator` (T063), `data-privacy-guard` (T065)
**Scope reviewed**: T056–T065.

---

## 1. Task verdicts

| Task | Owner | Status | Evidence |
|---|---|---|---|
| **T056** — `GrowthTab.parent.test.tsx` | qa-engineer | **Done** | 15 tests, all green after T058/T059/T062 landed. `npx vitest run src/components/athletes/growth` → **13 files / 141 tests passed**. The file keeps `GrowthCurveSection → PercentileToolbar → PercentileChart → PercentileInterpretationBlock` **real** (only recharts and the WHO JSON are mocked), so the two privacy assertions (`/Z=|P\d{1,2}\b|offset/i` absent from the rendered text; no axis/detail toggles) are not vacuous. Fixtures use two synthetic records with deliberately opposite bands/stages, so "latest record drives the cards" is a real regression guard. |
| **T057** — backend tests, coach audience | qa-engineer | **Done** | `cd backend && .venv/bin/python -m pytest tests -k "phv or explanation" -q` → **134 passed, 3838 deselected**. Covers separate cache row (`use_case="phv_explanation_coach"`), `cm/año` in the coach prompt output, and guardrail scrubbing. The cache-filter test inspects the compiled SQL bound param rather than re-asserting the call, so it is not tautological. |
| **T058** — `FamilyStageCard` + `FamilyBandCards` | react-ui-engineer | **Done** (one gate fix) | Both components read; family copy only (`familyLabel` + `narrative`, never `coachLabel`/Z/percentile); evaluation date obfuscated to month-year (Ley 1581); BMI card carries the D3 tooltip ("Índice de masa corporal para la edad, OMS 2007") under the family title "Peso para su estatura". `grep -rn "#[0-9a-fA-F]\{6\}" frontend/src/components/athletes/growth/` → **no matches** (tokens only). **Gate fix**: the tooltip trigger was `h-5 w-5` (20 px) — an interactive control below the 48 px floor of SC-006 / constitution III. Enlarged to a 48×48 hit area with `-m-3.5` so the glyph and the layout footprint are unchanged. |
| **T059** — `preset="family"` on the curve | react-ui-engineer | **Done** (one gate fix) | `GrowthCurveSection` passes `preset={isFamily ? "family" : "coach"}` to `PercentileChart` (athlete line + P50 + P3–P97 band, no PHV/PWV marker, legend "Deportista / Promedio / Rango esperado", caption "Línea gris: promedio para su edad. Franja: rango esperado."), `hideAdvanced` to `PercentileInterpretationBlock`, `showDetailToggle={false}` and `showAxisToggle=false` to the toolbar. **Gate fix**: the delivered code left the "Tabla" toggle **visible but inert** in family mode (`onView={() => {}}`, view forced to `"chart"`) because `PercentileTable` had no family-safe variant. That is a dead control and it removes the accessible alternative to the chart's `role="img"` — `docs/18-growth-module-redesign/proposal.md` §5.2 requires "table view available" for parents and SC-006 requires a visible table alternative. Fixed by adding `preset` to `PercentileTable` (drops the Z and Percentil columns, header "Estado", `familyLabel` badge) and restoring the real `setView`. |
| **T060** — backend `audience` | fastapi-architect | **Done** | `PHVExplainerUseCase.run(..., audience: Literal["family","coach"] = "family")`; `phv_explanation_coach` registered in the prompt registry (`phv_explanation_coach_v1.md`, ≤ 120 words, addresses the coach as "tu deportista", never a name, includes `growth_velocity_cm_per_year` and `months_from_phv`, same anti-diagnostic restrictions as the family prompt). `?audience=` exposed on both the cached GET and the generating POST; `_ensure_audience_allowed()` returns **403** for any non-coach/non-admin asking for `audience=coach`, on the GET too (where parents legitimately have read access). Cache partitioned by the existing free-text `use_case` discriminator — **no migration required**. `ruff check` on the six wave-owned backend files → **All checks passed**. |
| **T061** — frontend `audience` wiring | react-ui-engineer | **Done** | `PHVAudience` exported from `api/ai.ts`; `getPHVExplanation`/`getPHVExplanationCached` send `?audience=` (default `family`); `usePHVExplanation`/`usePHVExplanationCached` partition the TanStack Query cache with `["ai","phv",athleteId,audience]`; `PHVExplanationCard` shows the fixed title "Explicación PHV" in every state and defaults to `family` in read-only/parent mode. `npx vitest run src/hooks/ai src/components/ai` green inside the scoped run below. |
| **T062** — parent-mode composition | react-ui-engineer | **Done** | `GrowthTab mode="parent"` renders exactly `FamilyStageCard → FamilyBandCards → GrowthCurveSection(mode="parent") → PHVExplanationCard(readOnly, audience="family") → AnthropometryHistory(mode="parent")`, with its own loading/error/empty states from `useGrowthSummary`; no `GrowthAlerts`/`GrowthStatusRow`/`NextMeasurementCard`/`TrainingReadiness`/`MorphologyCard`/`ResearchReferences`/`NutritionalClassification`. `MyAthleteDetailPage.tsx` now lazy-loads `GrowthTab` with `key={athlete.id}` and its duplicated "Estado PHV" card (which printed the **exact** evaluation date to parents) is retired — a net privacy improvement. |
| **T063** — family copy review | parent-communicator | **Done** | Six `bands.ts` narratives rewritten: clinical jargon removed ("patológico", "disponibilidad energética insuficiente"), two ungrammatical fragments fixed, and the five BMI narratives now open with "El peso para su estatura…" so they match the family card title instead of reintroducing the acronym D3 deliberately avoids. `phv_explanation_coach_v1.md` anglicism "vs." replaced. All strings carry full diacritics. Recorded in `checklists/family-copy.md`. |
| **T064** — Playwright `e2e/growth-parent.spec.ts` | qa-engineer | **Deferred — written, not executed** (accepted, see §4) | File authored and statically valid: `npx playwright test --list e2e/growth-parent.spec.ts` → **2 tests discovered** (`E2E-040-003`, `E2E-040-004`), imports resolve. Assertions cross-checked against the shipped components and their green vitest suites. Not executed; the gate independently reproduced the blocker (§4). |
| **T065** — mandatory privacy audit | data-privacy-guard | **Done — APPROVED** | `checklists/privacy.md`: **no CRITICAL and no HIGH findings**, therefore Phase 6 is not blocked. Three LOW/informational notes, two of which are positive confirmations (export filename carries no athlete-identifying data; `training_implications` is name- and diagnosis-scrubbed before reaching any LLM prompt). L1 (an unstructured `console.error` of the `html-to-image` error object) is a defense-in-depth suggestion with no reproduced leak. |

---

## 2. Gate checks (commands and results)

| Command | Result |
|---|---|
| `cd backend && ruff check app tests` | **329 errors** — all pre-existing repo-wide lint debt. Baseline at `merge-base(main, HEAD)` = `84c8061`: **331 errors**. Wave-owned files (`app/routers/ai.py`, `app/services/ai/use_cases/phv_explainer.py`, `app/services/ai/prompts/registry.py`, `app/services/ai/context_builders.py`, `tests/test_ai_phv_explainer.py`, `tests/test_ai_router.py`) → **All checks passed**. |
| `cd backend && .venv/bin/python -m pytest tests -k "phv or explanation" -q` | **134 passed**, 3838 deselected, 0 failed. |
| `cd frontend && npm run typecheck` | **Pass** — `tsc --noEmit` clean, 0 errors. |
| `cd frontend && npx vitest run src/components/athletes src/components/ai src/routes/parents src/hooks/ai src/lib/growth` | **85 files / 1052 tests passed**, 0 failed. |
| `cd frontend && npx vitest run src/components/athletes/growth` | **13 files / 141 tests passed**. |
| `cd frontend && npx vitest run` (full suite) | **326/327 files, 3925/3926 tests passed**; the single failure is `src/lib/__tests__/datetime.test.ts` — **proven pre-existing**, see §3. |
| `cd frontend && npx playwright test --list e2e/growth-parent.spec.ts` | **2 tests discovered**, syntax and imports valid (no browser, no network, no database touched). |
| `grep -rn "#[0-9a-fA-F]\{6\}" frontend/src/components/athletes/growth/` | **No matches** — tokens only, no raw hex in the growth folder. |
| `curl -s -X POST http://localhost:8000/api/auth/login` (seeded parent) | **401** while `GET /health` returns **200** — the T064 blocker, reproduced by the gate itself. |

### Baseline differential (regression proof)

Both lanes were run serially against a throwaway `git worktree` at `merge-base(main, HEAD)` = `84c8061`, with the main checkout's `.env`, `.venv` and `node_modules` symlinked in so the two runs take the same code path (a worktree carries tracked content only; without the symlinks the baseline silently picks a different database path and fakes a regression).

| Lane | Baseline `84c8061` | Branch | Delta |
|---|---|---|---|
| `pytest -q` (backend, offline lane) | 225 failed / 3640 passed | 225 failed / **3699** passed | **0 new failures**, +59 passing tests |
| Failure **set** diff (`comm` on sorted `FAILED` lines) | — | — | **Empty in both directions** — not one test swapped |
| `ruff check app tests` | 331 errors | 329 errors | **−2** (one is the gate's own fix, see §5) |
| `vitest run` (frontend, full) | 1 failed (`datetime.test.ts`) | 1 failed (`datetime.test.ts`) | **0 new failures** |

The worktree was removed after the run (`git worktree remove --force`); the main checkout's `.env` is untouched and was never read or printed.

---

## 3. Pre-existing failures (not attributable to this wave)

| Failure | Count | Proof |
|---|---|---|
| Backend: `OperationalError: Can't connect to MySQL server on 'mysql'` — the `client` fixture in `tests/conftest.py` resolves the docker-compose hostname `mysql`, unreachable from outside the container network. | **225** | Identical count **and identical failure set** at `84c8061`. |
| Frontend: `src/lib/__tests__/datetime.test.ts > currentSeason > usa el año en CLUB_TIMEZONE` — system-timezone-dependent. | **1** | `git diff 84c8061 -- frontend/src/lib/datetime.ts frontend/src/lib/__tests__/datetime.test.ts` is **empty** (the feature never touched either file) and the test fails identically in the baseline worktree. |
| `npm run check:chunks` fails. | 1 | Expected until Phase 7 — stated verbatim in T003's own docstring ("expected to FAIL until Phase 7"). T062 actually improves it: `MyAthleteDetailPage.tsx` previously imported `GrowthCurveSection` statically, pulling recharts into the entry chunk from the parent page too; it is now lazy. Remaining offenders (`StageLogView.tsx → EffortProfile`, `PanoramaView.tsx → MiniSparkline`) are **T071**'s scope. |

---

## 4. Deferral (accepted)

| Item | Reason | Re-scoped to |
|---|---|---|
| **T064** — execute `e2e/growth-parent.spec.ts` green | Two independent blockers, both reconfirmed by this gate rather than taken on the worker's word. **(a) Seed desync**: `POST /api/auth/login` for the seeded parent returns **401** while `GET /health` returns **200** — `backend/scripts/seed.py` early-returns when a `clubs` row exists, so the demo accounts every spec assumes were never created on this volume. **(b) Privacy, and decisive**: the local docker MySQL volume holds real, non-demo data, and Playwright writes screenshots, traces and videos on failure — running the spec against it would produce artifacts containing identifiable data about minors, which Ley 1581 forbids regardless of whether the login is fixed. `docker compose down -v` would destroy the owner's dataset and is not a gate decision. Same blocker and same resolution the Phase 5 gate already recorded for T044/T054 in `checklists/coach-tab.md`. | `devops-engineer` stands up a dedicated e2e stack (separate compose project + volume, `APP_ENV=development` so the demo seed runs on an empty schema, synthetic athlete with ≥ 3 records over ≥ 14 months); `qa-engineer` then runs T044 / T054 / **T064** at the Phase 7 gate **T072**. Same prerequisite for `quickstart.md` in T077. |

`T064` is therefore left **unchecked** in `tasks.md`, consistent with how T044 and T054 were handled.

---

## 5. Changes made by the gate

Three defects were found and fixed directly rather than bounced back, since each is a one-file mechanical correction with a regression test.

| # | File | Change | Why |
|---|---|---|---|
| 1 | `frontend/src/components/athletes/growth/PercentileTable.tsx` | New optional `preset?: "coach" \| "family"` (default `"coach"`, backward-compatible). In `family` the Z and Percentil columns are dropped, the last header reads "Estado" and the badge uses `familyLabel`. | FR-016 forbids showing families Z-scores, percentiles and clinical headline labels; proposal §5.2 nonetheless requires "table view available" for parents. |
| 2 | `frontend/src/components/athletes/growth/GrowthCurveSection.tsx` | `onView={setView}` restored (was `() => {}` in family mode), the forced `effectiveView = "chart"` removed, and `preset` passed through to `PercentileTable`. Module docstring rewritten to match. | The delivered family view rendered a "Tabla" button that did nothing, and left the chart's `role="img"` without its accessible alternative (SC-006). |
| 3 | `frontend/src/components/athletes/growth/FamilyBandCards.tsx` | BMI tooltip trigger `h-5 w-5` → `h-12 w-12` with `-m-3.5`, so the hit area is 48×48 while the glyph and the layout footprint stay as designed. | SC-006 / constitution III: every interactive control ≥ 48×48 px. |
| 4 | `frontend/src/components/athletes/growth/__tests__/PercentileTable.test.tsx` | +4 tests for `preset="family"`: no Z/Percentil headers, no `+0.30`/`P62` in any cell, `familyLabel` not `coachLabel`, and the default preset still renders the full coach table. | Regression guard for fix 1. |
| 5 | `frontend/src/components/athletes/growth/__tests__/GrowthCurveSection.test.tsx` | The `PercentileTable` mock now captures props; +2 tests asserting that in parent mode the view toggle actually mounts the table with `preset="family"`, and that coach mode still gets `preset="coach"`. Also pins `PercentileChart.preset`, which nothing asserted before. | Regression guard for fix 2. |
| 6 | `backend/tests/test_ai_router.py` | Removed the unused `require_role` import (`F401`). | Pre-existing, but the file is wave-owned; `ruff check` on the wave's backend files is now clean. |

Net test delta from the gate: **+6 frontend tests**, all green.

---

## 6. Observations handed forward (not blocking Phase 6)

1. **`PercentileInterpretationBlock` inherits the T063 copy change.** `bands.ts::narrative` has exactly two consumers: `FamilyBandCards` (family) and `PercentileInterpretationBlock.tsx:121` (**both** modes). The BMI narratives now read "El peso para su estatura…" on the coach surface too. Defensible — BMI *is* weight-for-height, and the coach still sees the `coachLabel` headline plus Z and percentile in the advanced block — but it is a coach-facing wording change that the copy task did not scope. Confirm or revert at **T073** (integration review).
2. **Family table columns.** The family table now shows month-year, age and the raw value (e.g. "152.4 cm"). That is the same information the parent measurement history (`AnthropometryHistory mode="parent"`) already shows, so it introduces no new surface — noted so T072's a11y/e2e pass checks it deliberately.
3. **L1 from the privacy audit** (`GrowthCurveSection.tsx` logging the raw `html-to-image` error object) is still open as an informational item; suggest logging `err instanceof Error ? err.message : String(err)` when T071 next touches that file.
4. **Inherited from Phase 5, still open**: **T055** (SC-008 specification conflict, escalated to the owner) and **T054** (same e2e stack blocker as T064). Neither couples to Phase 6 — the Phase 5 gate explicitly corrected itself on this point.

---

## 7. Verdict

**Phase 6 — PASS.**

9 of 10 tasks verified complete and marked `[X]` in `tasks.md` (T056–T063, T065). **T064 is unchecked and deferred** with the accepted environment + privacy reason in §4, re-scoped to the Phase 7 gate T072. The mandatory `data-privacy-guard` audit is **APPROVED with no HIGH or CRITICAL findings**, so nothing blocks the phase on privacy grounds. Three real defects were found by the gate and fixed with regression tests. Zero regressions against the `84c8061` baseline in backend tests (identical 225-failure set), backend lint (−2 errors) and frontend tests (identical single pre-existing failure).

**Phase 7 (US5) may start.**

---

*Signed: `engineering-lead` (wave gate, Phase 6 / US4) — 2026-09-04.*
