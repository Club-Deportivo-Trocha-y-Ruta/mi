# Body composition (skinfolds) — QA record

Feature `specs/046-body-composition-skinfolds`. See `docs/21-body-composition/proposal.md` for
what was decided and `runbook-coach.md` for the coach-facing procedure. This document records
how the feature was tested and, honestly, which lanes were deferred and why — same convention
as `docs/20-traceable-growth-ai/qa.md` and `docs/19-multi-coach-governance/qa.md`.

This file is a skeleton opened during implementation (T070); each section below is filled in
by the task that owns the corresponding gate, not rewritten wholesale at the end.

## 1. Headline numbers

_To be filled by T071 (offline lanes) once the full implementation lands._

| Suite | Result |
|---|---|
| Backend `pytest -q` (offline, aiosqlite) | pending |
| `ruff check` | pending |
| Frontend `npm run typecheck` | pending |
| Frontend `npm test` (vitest) | pending |
| Frontend `npm run build` (incl. capture-route chunk size ≤ 150 KB gzipped) | pending |

## 2. Deferred lanes

Each row below is filled in, with a dated entry, by the task named — not run speculatively by
an earlier task.

| Lane | Owning task | Needs | Status |
|---|---|---|---|
| `pytest -m golden tests/evals/test_anthropometry_analyst_eval.py` (US6 prompt v2 + case_013…018, baseline refresh) | T068 | `AI_API_KEY` (app stack, never `RACE_AI_*`) | **Executed, green — 2026-09-24** (see §2.1) |
| `frontend/e2e/body-composition.spec.ts` (Playwright, isolated e2e stack from feature 040) | T072 | Docker/isolated e2e stack up | **Executed, green — 2026-09-24** (see §2.3) |
| `pytest -m mysql tests/test_migration_skinfolds.py` (enum alter + downgrade) | T073 | Reachable MySQL 8.4, `TEST_DATABASE_URL` ending in `_test` | **Executed, green — 2026-09-24** (see §2.2) |
| Post-deploy smoke (`/health`, coach field-guide PDF, real parent `growth-summary`) | T075 | Merged + deployed build | pending |

### 2.1 Golden lane (T068, 2026-09-24)

- Offline `pytest tests/anthro`: 145 passed. Offline sanity tests of
  `tests/evals/test_anthropometry_analyst_eval.py` (`-m "not golden"`): 8 passed, 1 skipped (the
  "skip without key" self-test, skipped because a key was present).
- Real golden run, **CI provider/model** (`AI_PROVIDER=google`,
  `gemini-3.1-flash-lite`, v2 prompt pair, 18 cases): **composite 0.786** (rule 0.883, judge
  0.722), 18/18 cases, threshold 0.75 **PASS**, SC-003 **PASS** (early-signal velocity never
  stated as reliable; no uncorroborated phase crossing stated as confirmed). `baseline.json` was
  refreshed from this run.
- Cross-check, **local-only** `AI_PROVIDER=claude-cli` (`claude-sonnet-5`, developer
  subscription; not a substitute for the CI gate): composite 0.804 (rule 0.789, judge 0.814),
  18/18, threshold PASS, SC-003 PASS.
- How it was run: `tests/conftest.py` forces `AI_PROVIDER=google` and the per-case results
  accumulate in a module-level list (no `pytest-xdist`), so both runs used an out-of-repo,
  single-process parallel runner. It imports the eval module, points the `Settings` singleton at
  the provider, runs `test_golden_case` for every case under `asyncio.gather` with a semaphore,
  then calls `test_eval_average_meets_threshold` and
  `test_sc003_velocity_and_phase_crossing_calibration`. The Gemini run took about 6 min at
  concurrency 4, and the claude-cli run about 10 min at concurrency 7. A single-case
  `pytest -m golden -k "test_golden_case and 001"` through the normal conftest path also passed.
  So the in-repo command works; it is just serial and takes about 30 min.
- Caveats, recorded honestly:
  - On Gemini, 13/18 cases ended in `critic_verdict=fallback`. This is the same pattern as the
    042 baseline (10/12). For body-composition cases 013–018 this means the deterministic
    fallback copy, not the model's text, carried most of the score.
  - Case 007's judge call hit a Gemini 503 (`judge_parse_ok=false`, neutral 0.5 per dimension), so
    its judge score is not a real grade.
  - Transient 5xx / `ClaudeCliTimeoutError` retries were seen in both runs.
  - The run rewrote the versioned `evals/anthropometry_analyst/results/last_run.md`, which now
    holds the claude-cli scoreboard. Do not commit it as a gate artifact; `baseline.json` is the
    record.

### 2.1.1 Fallback reduction, v2 prompt pair (claude-cli only, 2026-09-24)

Goal: fewer runs ending in the deterministic fallback or `skipped`. Scope: all work and
measurement used the **local-only** `claude-cli` provider (`claude-sonnet-5`, developer
subscription), as the owner asked. `baseline.json` was **not** refreshed, because the CI gate is
Gemini.

- **Method:** an out-of-repo instrumented runner (same single-process `asyncio.gather` pattern as
  §2.1) wrapped `run_analyst`, `run_prechecks`, `run_critic` and the critic's JSON parser. For
  each case it recorded the analyst parse errors, the precheck violations, the critic decision
  and its validation errors. The scoreboard was redirected to `/tmp`, so the repo's
  `results/last_run.md` was not rewritten.
- **Baseline causes (claude-cli, 18 cases, 6 non-approved):**
  - 3 × `skipped`: the critic's JSON failed validation. In two cases `violations[].problem` was
    over 200 characters. In the third, `revised_output.summary_line` was over 140 characters.
  - 2 × `fallback` from R01 (`must_block`): the analyst wrote "por debajo de lo esperado", which
    matches the population-comparison regex.
  - 1 × `fallback` from R11 (`must_block`): the analyst *negated* a phase crossing ("este cambio
    de fase todavía no está confirmado"). The regex does not understand negation.
  - Other non-blocking hits: R07 word budget on 17/18 cases (the analyst prompt never stated
    the 180/110 budget), R03 on 4/4 coach cases, R08 once (negated "salto de crecimiento"), and
    analyst schema retries for `summary_line` > 140 characters.
- **Changes:**
  - `anthropometry_analyst_v2.md`: new "Filtros automáticos" section. It lists the phrases that
    trip R01/R02/R05/R08/R11/R12/R13/R14 *even when negated* and gives a safe rewording for each.
    New "Extensión" section: family ≤170 words, coach ≤100, which fields count, and the
    `summary_line`/`confidence.reason` character limits. None of the privacy or safety rules
    were relaxed.
  - `anthropometry_critic_v2.md`: explicit revision policy (which rule ids are mechanical, and
    `revised_output` must be complete and valid or `null`), a hard 200-character limit on
    `problem` and `suggested_fix`, at most 3 violations, "low severity ⇒ approve", and a
    "not a violation" list (the mandatory uncertainty note, continuity with a persisting
    pattern, `data_gaps` entries).
  - `prechecks.py` R03: added `"28"` to `_R03_STRUCTURAL_NUMBERS`. The rule was objectively
    misfiring. The analyst's own training block says "últimos 28 días", but 28 only appears in
    key suffixes (`sessions_count_28d`), never as a value. R03 only degrades confidence; it
    never blocks. A new test in `tests/anthro/test_prechecks.py` checks that the entry stays in
    sync with `context._TRAINING_WINDOW_DAYS` and that other numbers (29) still fire.
- **Results (claude-cli, 18 cases):**

| Run | CLI timeout | Composite | Rule | Judge | approved / revised / skipped / fallback / flagged |
|---|---|---|---|---|---|
| Baseline, pre-change | 120 s | 0.806 | 0.780 | 0.823 | 11 / 1 / 3 / 3 / 0 |
| After change, run A | 240 s | 0.882 | 0.911 | 0.863 | 18 / 0 / 0 / 0 / 0 |
| After change, run B (same conditions as baseline) | 120 s | **0.890** | 0.913 | 0.874 | 14 / 3 / 0 / **1** / 0 |

  All three runs PASSED the threshold and SC-003. In run B, the single fallback (case 016) was
  two `ClaudeCliTimeoutError`s on the analyst call. That is an infrastructure timeout, not a
  prompt or precheck outcome. The earlier, pre-change §2.1 claude-cli run had scored 0.804.
  An intermediate iteration (before the R05 phrasing and the critic's "not a violation" list
  were added) scored 0.804 and failed SC-003 on case 013. Its R05 hit came from a *negated*
  "tendencia confiable" in `data_gaps`, and that is why the R05 line was added.
- **Still required:** these are prompt changes, so the constitution requires re-running the
  **Gemini CI gate** (`pytest -m golden -k anthropometry` with `AI_PROVIDER=google`,
  `gemini-3.1-flash-lite`) and refreshing `baseline.json` from that run. The claude-cli numbers
  above do not substitute for it.

### 2.2 MySQL migration lane (T073, 2026-09-24)

- Ran against the local docker-compose MySQL 8.4 instance (`me-mysql-1`, already up) with a
  disposable database name ending in `_test`, per the test's own contract — the test module
  drops/creates its own working sibling database (`<name>_skinfolds_migrations_test`) and never
  touches the dev/prod schema. No `.env` value was read into this transcript; credentials were
  sourced from `../.env` inside the shell only, never echoed.
- Command: `TEST_DATABASE_URL="mysql+aiomysql://root:***@127.0.0.1:3306/trocha_ruta_test" python -m pytest -m mysql -q tests/test_migration_skinfolds.py`.
- Result: **2 passed** — `test_migration_parent_is_the_045_head` (chain wiring: `be4595de1ad2`
  parents `a76c264449a5`) and `test_upgrade_seed_downgrade_upgrade_roundtrip` (upgrade to head
  creates `skinfold_measurements` + widens the two enums to include `fuprecol` /
  `triceps_skinfold_for_age` / `subscapular_skinfold_for_age` / `triceps_subscapular_sum_for_age`;
  idempotent FUPRECOL upsert lands the expected 54 rows; downgrade drops the table, removes the
  FUPRECOL rows, narrows both enums back, and leaves a synthetic non-FUPRECOL `WHO`/`bmi_for_age`
  row untouched; a second upgrade returns to head cleanly).
- No production or shared dev database was connected to for this lane.

### 2.3 Playwright E2E lane (T072, 2026-09-24)

- **Result: `frontend/e2e/body-composition.spec.ts` — 3/3 passed**, against the real (non-mocked)
  isolated e2e stack (`frontend/scripts/e2e-stack.sh up`, backend :8001 / MySQL :3307,
  `trocha-e2e` compose project, synthetic seed only). Took six runs to get green; the first two
  surfaced real app bugs (below), the rest were spec/locator fixes.
- The spec covers, against the real isolated backend: a coach capture flow with one skipped site
  (cresta ilíaca, outside Σ4) and one site needing a third reading (subescapular, 7.0/8.5 mm), a
  mid-wizard page reload that restores the draft from `localStorage` at the same step with the
  same readings, the coach's `body-composition-card` showing a real Σ4 mm value and the word
  "estimado", a second same-day evaluation showing the minimum-interval note
  (`skinfolds-interval-note`) and hiding the "Guardar y agregar pliegues" exit, and the parent's
  `family-body-composition-card` containing no digits, `%`, or `mm` — band and sentence only. The
  three tests run `mode: "serial"` because the second and third depend on data the first creates.
- To run: `frontend/scripts/e2e-stack.sh up` then, from `frontend/`,
  `E2E_APP_PORT=5175 E2E_API_BASE_URL=http://localhost:8001 npx playwright test e2e/body-composition.spec.ts`.

#### 2.3.1 Real app bugs found and fixed

- **`GET /api/athletes/{id}` returned 500 once the latest anthropometric record had a skinfold
  set.** `routers/athletes.py::get_athlete` (coach/admin branch) eager-loaded
  `Athlete.anthropometric_records` but not the nested `.skinfolds` relationship; `AnthropometryOut`
  gained a `skinfolds` field in feature 046, so `model_validate` tried to read `record.skinfolds`
  synchronously and hit `sqlalchemy.exc.MissingGreenlet` (a lazy load outside the async greenlet).
  Fixed by extending the `selectinload` chain (`Athlete.anthropometric_records` →
  `AnthropometricRecord.skinfolds` → `SkinfoldMeasurement.record`, mirroring the pattern already
  used in `routers/anthropometry.py::list_anthropometry`) and calling `skinfold_set_out()` to
  populate the field. Regression test:
  `backend/tests/test_athletes.py::TestGetAthlete::test_get_athlete_detail_when_latest_record_has_skinfolds`.
- **A record created via `POST /api/athletes/{id}/anthropometry` could be invisible to the very
  next `GET` on the same athlete — a read-your-writes race, not skinfolds-specific.**
  `create_anthropometry` only did `db.add()` + `await db.flush()`; the actual `COMMIT` was left to
  `get_db()`'s post-`yield` teardown. FastAPI (`fastapi.routing.request_response::app`) sends the
  HTTP response (`await response(scope, receive, send)`) *inside* the dependencies'
  `AsyncExitStack` but *before* that stack exits — so the 201 could reach the client before the
  transaction was actually committed. Reproduced with plain `httpx` against the isolated MySQL:
  ~80% of back-to-back POST→GET pairs missed the just-created row. This is how the "coach captura
  pliegues" test surfaced it — "Guardar y agregar pliegues" creates the record and immediately
  navigates to `/athletes/:id/anthropometry/:recordId/skinfolds`, which re-fetches the list and
  couldn't find its own record ("No encontramos esta evaluación"). Fixed with an explicit
  `await db.commit()` at the end of `create_anthropometry`, before `return out` (the redundant
  commit in `get_db()`'s teardown becomes a harmless no-op). Regression test:
  `backend/tests/test_athletes.py::TestCreateAnthropometry::test_create_record_commits_before_returning`
  (spies on `AsyncSession.commit` — `httpx.ASGITransport`, used by the rest of the suite, runs
  fully in-process with no real network boundary, so it cannot reproduce the timing race itself;
  the test instead asserts the endpoint issues its own commit call, not just the teardown's).
  **This pattern (`db.add()`/`flush()` with no explicit commit, relying only on `get_db()`
  teardown) is used by roughly 23 of the 33 router files** — this fix only touches
  `create_anthropometry`; the same risk likely exists elsewhere and probably deserves a dedicated
  follow-up, but auditing/fixing all of them was out of scope here.
- **Draft could be lost on a reload that happened within the 800 ms debounce window.**
  `useFormDraft` (`frontend/src/hooks/useFormDraft.ts`, shared with the training
  `SessionWizard`) only persisted to `localStorage` inside a debounced `setTimeout`; a reload
  right after the last keystroke (exactly what "recarga a mitad de captura" does, and exactly what
  the E2E test does with no artificial delay) could fire before the timer, losing the pending
  save. Fixed by tracking the latest not-yet-persisted `{values, step}` in a ref and flushing it
  synchronously on `pagehide`/`beforeunload`. Additive change (existing debounce behavior
  unchanged); verified against both consumers —
  `frontend/src/components/athletes/body-composition/__tests__/SkinfoldWizard*.test.tsx` (23
  tests) and the four `session-wizard` test files (40 tests) still pass. New regression tests:
  `frontend/src/hooks/useFormDraft.test.ts` ("flush síncrono en pagehide/beforeunload", 2 tests,
  fake timers).

#### 2.3.2 Spec bugs fixed (in `body-composition.spec.ts` itself)

- `getByText(/tercera lectura/i)` was a strict-mode violation (matched both the `role="status"`
  warning and the field `<label>`); narrowed to
  `getByRole("status").filter({ hasText: /tercera lectura/i })` — the plain `getByRole("status", {
  name })` variant tried first does **not** work here: the `<p role="status">` has no
  `aria-label`, and `status` only supports "name from author", not "name from content", so its
  computed accessible name is empty.

#### 2.3.3 Other e2e specs touching growth/anthropometry — run to check for 046 regressions

Ran (same isolated stack, one combined invocation for the final clean pass):
`anthropometry.spec.ts`, `anthropometry-record-explanation.spec.ts`, `growth-analysis.spec.ts`,
`growth-parent.spec.ts`, `growth.spec.ts`.

- **`anthropometry.spec.ts` and `anthropometry-record-explanation.spec.ts` — found and fixed a
  real 046 regression in two other specs.** Both had a fallback path that fills the anthropometry
  form and clicks a button named `/guardar medici[óo]n/i`. Feature 046 changed
  `AnthropometryForm`'s primary submit label to "Guardar y terminar" whenever the athlete is
  skinfolds-eligible (adding the second "Guardar y agregar pliegues" exit next to it) — "Guardar
  medición" only remains for an ineligible athlete. `anthropometry.spec.ts` happened to pass
  anyway (its `gotoDemoAthlete()` helper resolves to whichever athlete sorts first, order-
  dependent); `anthropometry-record-explanation.spec.ts` hit the renamed button directly and timed
  out. Fixed both locators to accept either label
  (`/guardar (medici[óo]n|y terminar)/i`) — neither test is about skinfolds, they just need to
  seed a measurement. After the fix: **`anthropometry.spec.ts` 2/2 green.**
- **`anthropometry-record-explanation.spec.ts` — 0/2 green, pre-existing, not a 046 regression.**
  After the button-label fix both tests get past record creation and fail later, waiting up to 30 s
  for `record-explanation-success` (AI-generated per-record explanation, feature 042 area). The
  spec's own header comment requires `AI_ENABLED=true AI_PROVIDER=fake`; `docker-compose.e2e.yml`
  (feature 040) sets `AI_ENABLED=false` deliberately, "so the seed and every request are
  deterministic and offline for Playwright." Not touched — out of scope for 046, and changing the
  isolated stack's AI config is feature-040-owned.
- **`growth-analysis.spec.ts` — 0/1 green, pre-existing, not a 046 regression.** Its own header is
  explicit: "Requiere STACK REAL... AI_ENABLED=true... El proveedor `fake` NO sirve para este
  spec: no ejerce la espera real de 20-40 s... ni produce un `schema_version=\"v2\"`." This spec
  is documented as fundamentally incompatible with the isolated/fake-AI e2e stack — it needs the
  real `docker compose up` dev stack with a real AI key, not this one. Left as-is.
- **`growth-parent.spec.ts` (2/2) and `growth.spec.ts` (2/2) — green, no regression.**

Not run: `session-coaches.spec.ts` / `session-content-unification.spec.ts` (the training
`SessionWizard`, the other consumer of the `useFormDraft` fix) were not part of the requested
growth/anthropometry scope; risk was assessed instead via the 40 passing `session-wizard` vitest
files (§2.3.1) since the fix is additive.

## 3. Quickstart scenario coverage

_To be filled once User Stories 1–6 are implemented and their independent tests run — one row
per `specs/046-body-composition-skinfolds/spec.md` acceptance scenario, in the same table shape
as `docs/20-traceable-growth-ai/qa.md` §2 (Covered by / Status: Executed, green | Written, not
executed | Not performed)._

## 4. Real defects caught before release

_To be filled as they are found — same convention as `docs/20-traceable-growth-ai/qa.md` §6:
one subsection per defect, what would have shipped broken, the fix, and the test that caught
it. Do not backfill a defect that was never actually hit._

### 4.1 Golden judge could not see the body-composition leaf (T068)

- **What would have shipped broken:** `app/services/ai/anthro/eval/judge.py::_render_context_json`
  serialized the 042 context blocks but not `body_composition`. As a result, every
  body-composition statement in cases 013–018 looked ungrounded to the judge. The first claude-cli
  golden run on 2026-09-24 scored **0.739 (FAIL)**, with judge scores of 0.40–0.76 on 013–018.
- **Fix:** the judge payload now carries the leaf, projected for the family audience exactly as
  the analyst sees it (`band` / `band_reason_code` removed, same as
  `context._render_body_composition_block`).
- **Test:** `backend/tests/anthro/test_judge_context.py`. After the fix, the golden lane passes on
  both providers (§2.1).

## 5. Fixtures and privacy invariants

- No real athlete name, birth date, or measurement value appears in this feature's tests,
  fixtures, evals, or this document.
- `backend/evals/anthropometry_analyst/golden/case_013.json`…`case_018.json` (T067) are
  synthetic constructions only.
- The `data-privacy-guard` audit (T069) result is recorded in
  `specs/046-body-composition-skinfolds/privacy-audit.md`, not duplicated here.

## 6. Summary — what to do before calling this feature verified

_To be filled last (T075 or the owner), in priority order, mirroring
`docs/20-traceable-growth-ai/qa.md` §8._
