# Traceable growth AI — QA record

Feature `specs/042-traceable-growth-ai`. See [`design.md`](design.md) for what was built.
This document says how it was tested, what each quickstart scenario's status actually is,
the three real defects the test suite caught before release, and — in full honesty, the
same standard `docs/19-multi-coach-governance/qa.md` set for feature 041 — what still needs
a local machine to close out.

Scope: waves 1-3 (the shipped code). Wave 4 is this documentation pass itself.

## 1. Headline numbers

Measured in this environment (no Docker daemon, no reachable MySQL, no real model API key):

| Suite | Result |
|---|---|
| Backend, pre-042 baseline (isolated worktree) | 4498 passed / 212 failed / 9 errors |
| Backend, after wave 3 | 4796 passed / 211 failed / 9 errors — **identical under both `AI_USE_LANGCHAIN` values** |
| Backend regressions | Zero at every wave — the set-diff of failing test ids was empty each time. One baseline failure was fixed along the way: `test_factory_openai_not_implemented`. |
| Backend remaining red | All 211 failures and 9 errors require a real MySQL connection; there is no docker daemon in this container. Identical before and after the feature — none of them belong to this feature. |
| Frontend unit (vitest) | 4280 / 4281 passed. The one failure (`src/routes/training/SessionWizardRouteNotify.test.tsx`) is pre-existing and unrelated to this feature. |
| Frontend typecheck | `tsc --noEmit` clean |
| Frontend build | `npm run build` clean |
| `ruff check` | 361 findings before and after this feature — zero net change |
| `pytest -m golden` | 35 skipped, every one with an explicit no-model-key reason string — never a silent pass (confirmed live in this pass: 14 anthropometry + 21 race, see §3) |

Re-verified live in this pass, narrower slices (all green, all offline, no network):

```
tests/anthro tests/test_growth_summary_latest_analysis.py
tests/test_langchain_switch_matrix.py tests/test_ai_router.py        → 154 passed
tests/test_ai_record_router.py tests/test_ai_record_explainer.py
tests/test_ai_phv_explainer.py                                       → 59 passed
tests/test_ai_explanation_columns_mysql.py (no TEST_DATABASE_URL)    → 4 skipped, explicit reason
pytest -m golden -k anthropometry                                    → 14 skipped, explicit reason
npx vitest run src/components/athletes/growth
  src/schemas/ai.schemas.test.ts src/hooks/ai                        → 273 passed
npx vitest run src/components/ai                                     → 177 passed
npx vitest run -t "a11y" (whole frontend)                             → 91 passed, 0 axe violations
```

## 2. Quickstart scenarios — coverage and actual status

One row per scenario in `specs/042-traceable-growth-ai/quickstart.md` §3. "Executed" means
run in this environment during this pass or the implementation passes that produced the
numbers in §1; "written, not executed" names the missing prerequisite.

| # | Scenario | Covered by | Status |
|---|---|---|---|
| 1 | Offline lane green under both `AI_USE_LANGCHAIN` values (SC-006, FR-025, FR-038) | `tests/test_langchain_switch_matrix.py` (byte-identical assertions for all five migrated use cases, the fake-provider bypass, `FakeLLMProvider.last_request` still exposed) | **Executed, green.** Both transport values produce identical output against the fake model; the ~40 pre-existing `test_pii_never_reaches_llm`-style assertions are unmodified and still pass. |
| 2 | Structured, grounded per-measurement reading (SC-002, SC-003, SC-008) | `tests/anthro/test_context.py`, `test_analyst.py`, `test_critic.py`, `test_pipeline.py`, `test_prechecks.py`; `tests/test_ai_record_router.py` (happy path, cardinalities, word budgets); frontend `StructuredInsight.test.tsx`, `AIGeneratedContent.test.tsx` (discriminated-union renderer) | **Executed, green** for every part that does not require a real model: node/pipeline unit tests, the router's cardinality/word-budget assertions, the frontend renderer. The **golden eval's own grounding/uncertainty-calibration verdicts against a real model** (the part of SC-002/SC-003 that judges actual generated prose) is written-but-not-executed — see §4, no `AI_API_KEY`. The 45 s/p95 timing claim (SC-008) was not measured against a real provider in this environment; it is a code-level property of the pipeline (five bounded async steps, no polling) not verified under load. |
| 3 | A flagged draft never reaches a family (SC-002, SC-004, FR-013, FR-016) | `tests/anthro/test_pipeline.py` (state-machine transitions to `flagged`/`fallback`/`skipped`); `tests/test_ai_record_router.py::test_parent_gate_by_critic_verdict`, `test_parent_missing_row_and_only_flagged_analysis_both_look_like_no_analysis`, `test_coach_sees_flagged_content_unfiltered` | **Executed, green.** The family gate (`critic_verdict ∈ {approved, revised}` only) is asserted directly against the router, including the "flagged and absent look identical to a parent" case. |
| 4 | Staleness is a server fact (SC-005, FR-027) | `tests/test_growth_summary_latest_analysis.py` (`test_is_stale_true_on_newer_record`, `test_is_stale_true_on_corrected_record`, `test_is_stale_false_when_current`, `test_coach_vs_parent_visibility_by_verdict`, `test_no_extra_query_per_measurement`); frontend `LatestAnalysisLine.test.tsx`, `GrowthStatusRow.test.tsx` | **Executed, green** for the server computation and its component rendering. The "without opening any dialog" clause of SC-005 itself is a moderated usability check — see §5, not run. |
| 5 | Every generation traces once, redacted, right tags (SC-001, FR-017…FR-021) | `tests/test_llm_observability.py` (`test_allowed_metadata_keys_snapshot`, `test_quasi_identifiers_are_not_on_the_allow_list`, the `build_mask`/redact-always tests, the keyed-session-id family of tests including domain separation from the race anonymiser) | **Written and unit-tested at the config/allow-list level — executed, green** (part of the 123-test run below). The end-to-end claim — "open the local Langfuse UI and see one real trace per use case, seven traced entry points, the keyed-hash session id on an actual trace" — needs the local Langfuse stack (`docker-compose.langfuse.yml`) up, which this environment does not have. Treat the unit-level result (mask/allow-list/tags are provably correct in isolation) and the live-UI claim (never opened a real trace in this pass) as two separate facts. |
| 6 | Three settings forbidden in production (SC-009) | `tests/test_ai_config.py` (`test_langfuse_enabled_forbidden_in_prod`, `test_langfuse_structural_metadata_forbidden_in_prod`, `test_ai_provider_claude_cli_forbidden_in_prod`, `test_race_ai_provider_claude_cli_forbidden_in_prod`, `test_ai_provider_claude_cli_forbidden_in_prod_via_race_inheritance`, and each one's dev-mode-allowed counterpart) | **Executed, green** — 123 passed across `tests/test_ai_config.py` + `tests/test_llm_factory.py` + `tests/test_llm_observability.py`, re-run live in this pass. All three forbidden settings fail startup with a message naming the variable; a legitimate production config with all three unset/false still boots. |
| 7 | Every generation accounted, race budget untouched (SC-001, FR-022, FR-023) | `tests/test_ai_explanation_columns_mysql.py` (the nine columns, MySQL-only — see §4); `tests/anthro/test_pipeline.py` (persist step populates the accounting fields against aiosqlite); `tests/test_app_stack_spend_by_user.py` and `tests/test_spend_by_user.py` (`stack="app"` breakdown for `GET /api/race-analysis/admin/ai-usage`, separate from race spend) | **Executed, green** (14 passed across the two spend-by-user files, re-run live in this pass) on the aiosqlite lane: accounting fields populate, `stack="app"` is separate from race spend, no `503` for this stack. The MySQL-specific claims — exact `Numeric(10,6)` precision, the real `ON DUPLICATE KEY UPDATE` overwrite, `NOT NULL text` enforced by the engine itself — are written-but-not-executed, see §4. |
| 8 | Golden eval blocks a bad prompt/model change (SC-003) | `backend/tests/evals/test_anthropometry_analyst_eval.py`, `backend/evals/anthropometry_analyst/*` | **Written, not executed against a real model** — no `AI_API_KEY`. See §4 for the placeholder baseline and what running it for real requires. The eval's own **rule-only** assertions (word budgets, forbidden terms, sub-8-week/uncorroborated-crossing classification against the deterministic layer, no dependency on a real model) do run and pass as part of `tests/anthro/test_prechecks.py`. |
| 9 | MySQL lane proves the nine columns round-trip (FR-022, SC-002) | `tests/test_ai_explanation_columns_mysql.py` | **Written, not executed.** No `TEST_DATABASE_URL` / reachable MySQL in this environment. Confirmed to at least collect and self-skip cleanly with an explicit reason (4 tests, 4 skips) rather than error. See §4. |
| 10 | Touch targets, focus and a11y hold (SC-007) | `AnthropometryHistory.test.tsx` (focus-trap/return, 48 px controls), `GrowthTab.a11y.test.tsx` and the other `*.a11y.test.tsx` files, jest-axe across the AI surfaces; Playwright `e2e/growth.spec.ts`, `e2e/anthropometry.spec.ts` | **Executed, green** for everything that runs against jsdom/vitest: 91 a11y-tagged tests pass with zero axe violations across the measurement dialog and `GrowthTab` (both coach and family paths), the focus-trap/return unit tests pass. The **Playwright** run against a real browser + live stack was not executed in this environment (no Docker) — see §4. |
| 11 | A pre-042 free-prose row still renders forever (FR-026) | `tests/test_ai_record_router.py::test_legacy_v1_row_renders_without_structured_fields`, `test_corrupt_structured_json_degrades_gracefully`; frontend Zod discriminated-union tests in `ai.schemas.test.ts` | **Executed, green.** A `schema_version IS NULL` row renders through the unchanged prose path with no expander and no auto-regeneration; a corrupt `structured_json` on a nominally-v2 row degrades to prose rather than raising. |

## 3. The golden-eval skip is honest, not silent

Confirmed live in this pass, `pytest -m golden -q -rs`:

```
14 skipped  tests/evals/test_anthropometry_analyst_eval.py — AI_API_KEY (o GOOGLE_API_KEY)
            no configurada — el juez del eval de antropometría (stack app, nunca RACE_AI_*)
            no puede invocar un modelo real.
21 skipped  tests/evals/test_race_analyst_eval.py — RACE_AI_API_KEY/GOOGLE_API_KEY no
            disponible, or RACE_EVAL_VERSION pinned to v3 (v2 path only runs under 'v2').
```

35 skipped total, matching the number in the task brief for this pass. Every skip carries a
reason string naming the missing variable and pointing at the spec edge case
("the developer runs the golden evaluation without a real model key: the run is skipped with
an explicit reason, never silently passed") — nothing in this run reports a false green.

## 4. What still needs a local machine

Everything below was **written** during waves 1-3 and is believed correct by code review and
by the parts of it that *can* run offline, but its live result is unknown in this environment
— same posture feature 041's qa.md took for its own `mysql`/Playwright/moderated-check gaps.

1. **The `-m mysql` column test** — `backend/tests/test_ai_explanation_columns_mysql.py`.
   Needs a `TEST_DATABASE_URL` (`mysql+aiomysql://…`, database name ending in `_test`)
   pointed at a reachable MySQL 8.4 instance. What it would prove that aiosqlite structurally
   cannot: `Numeric(10, 6)` doesn't silently round `cost_usd`; the real MySQL
   `INSERT ... ON DUPLICATE KEY UPDATE` overwrites the nine columns in place rather than the
   sqlite upsert shim other tests use; `text NOT NULL` is enforced by the engine itself under
   `STRICT_TRANS_TABLES`, not only by SQLAlchemy/Pydantic. Confirmed in this pass that the
   file at least collects and self-skips with an explicit reason (not a collection error) —
   run it for real before calling this feature verified.
2. **`frontend/e2e/growth-analysis.spec.ts`** (Playwright, T077, 247 lines). Explicitly
   requires a real stack — `docker compose up`, a real AI provider (the `fake` provider
   cannot exercise this spec: it needs the real 20-40 s wait and a genuine `schema_version=
   "v2"` structured output from the five-step pipeline), and a seeded demo athlete linked to
   a parent with active AI consent. Not executed — no Docker daemon in this environment.
3. **The golden eval against a real model** — `pytest -m golden -k anthropometry`. Needs
   `AI_API_KEY` (a **new**, separate secret from `RACE_AI_API_KEY` — the app stack never
   reads `RACE_AI_*`). Until it runs for real:
   - `backend/evals/anthropometry_analyst/baseline.json` holds `"status": "PLACEHOLDER"`
     scores (`avg_composite_score: 0.79`, estimated from the deterministic `rule_score` plus a
     conservative flat `judge_score` of 0.70 for an untuned v1 prompt — the same convention
     `evals/race_analyst/baseline_2026-05-20.json` used at its own equivalent stage). These
     numbers are **not** evidence the prompt clears 0.75 against a real model; they are a
     placeholder so the file has a shape to diff against once a real run exists.
   - The file embeds its own regenerate command:
     `AI_API_KEY=$your_key pytest backend/tests/evals/test_anthropometry_analyst_eval.py -m golden -k anthropometry -v`.
   - `.github/workflows/anthropometry-eval.yml` (cloned from `race-eval.yml`) needs a **new**
     GitHub Actions secret named `AI_API_KEY` added by a repo admin. Nobody has added it yet;
     the job hard-fails with a clear message identifying the missing secret until someone
     does — this is a real, outstanding release blocker for the *blocking-in-CI* half of
     FR-035, not a documentation nicety.
4. **SC-005's moderated check** — see §5 below, recorded but not performed.

## 5. SC-005 — the moderated check, recorded the way feature 041's SC-002 was

`docs/19-multi-coach-governance/qa.md` §4 recorded SC-002 ("a coach can answer *who changed
this athlete's record, and when?* from the athlete page in under 30 seconds, 5/5 in a
moderated test") as not run, with the exact assertion, the reason, and what running it later
requires. SC-005 gets the identical treatment here.

**SC-005, verbatim**: "The coach can tell from the Crecimiento tab, without opening any
dialog, whether the latest analysis is current and which of the last four measurements carry
a warning sign."

**What the automated suite proves, and its limit.** `LatestAnalysisLine.test.tsx` and
`GrowthStatusRow.test.tsx` assert that the summary line, the "Desactualizado" badge and the
"Con señal para revisar" row marker render correctly in the tab's own DOM tree for every
state the server can report (current, stale-by-correction, stale-by-newer-measurement, no
analysis yet). That is necessary but not sufficient: a component test can confirm the right
text and attribute exist in the tree, but it cannot confirm a real coach, glancing at a real
screen without being told what to look for, actually notices it and answers correctly inside
whatever time bar matters in the field. That gap is exactly what a moderated check closes and
what no unit or Playwright assertion can substitute for.

**Status: NOT performed.** It needs a live UI and an actual coach from the club, neither of
which this environment has.

**What the person running it must do**, once a live stack and a coach are available:

1. Seed (or use) an athlete with at least four analysed measurements, at least one carrying
   a warning sign, and the latest one made stale by either an edit or a newer unanalysed
   measurement — so both the "Desactualizado" and the row-marker paths are live at once.
2. Sit the coach in front of the Crecimiento tab, freshly loaded, with no prior explanation
   of what changed in this feature.
3. Ask two questions without pointing at anything: "Is the latest analysis still current?"
   and "Which of the last few measurements have something worth a second look?" — both to be
   answered without opening any measurement dialog.
4. Record whether the coach answers both correctly, and roughly how long it takes. Feature
   041's own SC-002 used a 5/5-moderated-runs bar with a time ceiling; adopt the same shape
   here (5 runs, record each) unless the owner sets a different bar before this is run.
5. Log the dated result as an addendum to this section — pass/fail per run, any wording in
   the tab that caused hesitation — the same way §4 of `docs/19-multi-coach-governance/qa.md`
   left space for its own SC-002 addendum.

## 6. Three real defects the test suite caught before release

These are the most useful thing in this document — each is a case where a shipped-looking
diff would have reached production broken or unsafe, and a test (not a manual read) is what
caught it. All three are already fixed and committed; kept here so nobody "fixes" them again
from scratch, and so the shape of each is legible to whoever next touches this code.

### 6.1 Every v2 response would have 500'd — `AnthropometryInsightOut` validated the wrong thing

`AnthropometryInsightOut` (the API-facing mirror of the stored insight) is defined with
`model_config = ConfigDict(extra="forbid")`, matching the project's own pattern for turning a
hallucinated or unexpected field into a hard `ValidationError` instead of a silent
pass-through. The bug: `structured_json` in the database stores the **complete**
`AnthropometryInsightV1.model_dump(mode="json")` — which includes `schema_version` (the
insight-payload version, not the row discriminator, see `data-model.md` §0),
`audience` (redundant with which endpoint/parameter was called), and `word_count` (model
telemetry, never trusted). `AnthropometryInsightOut` deliberately excludes those three. Feed
the raw stored dict straight into `AnthropometryInsightOut.model_validate(...)` and every one
of those three extra keys trips `extra="forbid"` — **every** v2 row, not an edge case, would
have raised a 500 on its very first read.

**Fix**: an explicit `from_stored()` classmethod that projects the stored dict field-by-field
onto `AnthropometryInsightOut.model_fields`, rather than validating the raw dict. This keeps
the original protection intact in the direction that matters: a new field added later to the
internal `AnthropometryInsightV1` schema is **not** exposed on the wire just because it now
exists in the stored JSON — someone has to add it to the wire schema on purpose. What changed
is only that the *expected* mismatch (the three known-excluded fields) stops being an error,
while an *unexpected* one (a wire field missing from what was actually stored) still is.

Caught by: the new router/schema tests in `tests/test_ai_record_router.py` exercising an
actual round-trip through a real `structured_json` payload, not a hand-built dict shaped to
avoid the extra fields.

### 6.2 A CRITICAL privacy finding — a forbidden name could re-enter the next prompt

The mandatory `data-privacy-guard` audit (T057) is not a formality on this project — it
returned a genuine **FAIL** on a **CRITICAL** finding before this feature could ship.

`previous_analysis.summary_line` is the one free-text field the context allow-list admits
into the analyst prompt (`contracts/analysis-context.md` §2.6) — it is what lets the model
talk about continuity rather than only "since last time" (FR-010). The deterministic
guardrail rule that screens for leaked names (R06) only screens the **new** draft the model
just produced, after generation. It never looked at `previous_analysis.summary_line`, which
was interpolated into the prompt **before** generation even started. So: a name that ended up
inside an already-persisted insight — or a name that was fine when that insight was generated
but became club-forbidden afterward (a family withdraws consent, a name is added to the
forbidden list for any reason) — would silently re-enter the very next prompt sent to the
external model provider, with no guardrail anywhere in the pipeline positioned to catch it.

**Fix**: the pipeline (`app/services/ai/anthro/pipeline.py::run_analysis`) now loads the
club's forbidden-names list from the database **before** building the analysis context, and
threads it through pipeline state. `context.py::_scrub_previous_summary` then removes any
forbidden name from `previous_analysis.summary_line` by **exact string match** — deliberately
the primary defense, because it is the only approach that works against a name of arbitrary
shape (nicknames, single names, unusual capitalization); a `"Nombre Apellido"`-style regex is
kept as a second, defense-in-depth layer, not the primary one, because it would miss anything
that doesn't fit that shape.

**Two tests pin this so it cannot silently regress**:
`tests/anthro/test_privacy_seam.py::test_forbidden_name_in_previous_summary_never_reaches_rendered_prompt`
is a hypothesis property test — for any synthetically generated forbidden name embedded in a
previous summary line, that name must not appear in the final rendered prompt string.
`test_pipeline_carga_la_lista_prohibida_antes_de_construir_el_contexto` is a separate wiring
test that asserts `run_analysis` actually resolves and passes the forbidden-names list into
`build_context` — specifically so that a future refactor which reorders the pipeline steps
cannot pass the scrub a silently empty list and have the property test above still pass
vacuously (an empty forbidden-names list trivially "contains no violations").

### 6.3 Focus did not return to the trigger on closing the measurement dialog

Radix's `Dialog` restores focus to whatever opened it automatically — but only when the
opener is an actual `DialogTrigger` component. The measurement history renders **N** rows
(one per historical measurement, both the mobile card list and the desktop table), and the
dialog itself is controlled (`open={selectedRecord !== null}`), not driven by a
`DialogTrigger` per row. Radix has no way to know *which* of the N rows was clicked, so on
close it fell back to `document.body` — a real, FR-031-violating regression on exactly the
touch-target/focus surface this feature explicitly promised to fix (US6).

**Fix** (`frontend/src/components/athletes/AnthropometryHistory.tsx`): the component now
remembers the row element itself. `openRecord()` captures `event.currentTarget` into a
`triggerRef` at the moment a row is clicked, and the dialog's `onCloseAutoFocus` restores
focus to that captured element explicitly, rather than relying on Radix's trigger-inference
that cannot work for a controlled, multi-row dialog.

Caught by the focus-trap/return assertions in `AnthropometryHistory.test.tsx`
(`npx vitest run src/components/athletes/AnthropometryHistory.test.tsx`, part of the a11y
suite that runs green — §1).

## 7. Fixtures and privacy invariants in tests

- No real athlete name, birth date, or measurement appears anywhere in this feature's tests,
  fixtures, evals, or this document — every example above is described by field/behaviour,
  never by a concrete value, per the quickstart's own rule ("a generated `qué_cambió` /
  `qué_significa` string is exactly as sensitive as the free prose it replaces").
- `backend/evals/anthropometry_analyst/*` (the twelve golden cases) are synthetic
  constructions — ages, deltas and intervals chosen to exercise a rule, never drawn from a
  real athlete's history.
- `tests/anthro/test_privacy_seam.py` is itself the privacy-invariant test for this feature's
  prompt seam: hypothesis-generated names, dates and numeric leaves, never a real club
  member — a failure there means the renderer leaks, not that a fixture was built wrong (see
  the file's own docstring, quoted in §6.2's fix description).
- The `data-privacy-guard` audit (T057, §6.2) ran against the feature's actual diff, not a
  synthetic stand-in, and its one CRITICAL finding is the fix recorded above — not a
  hypothetical caught in review, a real defect a shipped diff would have carried.

## 8. Summary — what to do before calling this feature verified

In priority order, based on what each step would actually catch (mirrors
`docs/19-multi-coach-governance/qa.md` §7's structure):

1. **Add the `AI_API_KEY` GitHub Actions secret** (§4.3) — until this exists,
   `.github/workflows/anthropometry-eval.yml` hard-fails on every run, and FR-035's
   "blocking in CI" half is not actually enforced for this feature. This is the single
   highest-priority item: everything else in this list is missing evidence, this one is a
   broken gate.
2. **Run the golden eval for real** once the key exists, and replace
   `backend/evals/anthropometry_analyst/baseline.json`'s `PLACEHOLDER` scores with the real
   composite/rule/judge numbers per case (§4.3) — this is what actually proves SC-003's
   "composite ≥ 0.75 on the shipped prompt and model", not the placeholder's estimate.
3. **Point `TEST_DATABASE_URL` at a real MySQL 8.4 `_test` database and run**
   `pytest -m mysql tests/test_ai_explanation_columns_mysql.py` (§4.1) — closes the one
   dialect-specific gap this environment cannot exercise.
4. **Bring up the isolated stack and run** `npx playwright test e2e/growth-analysis.spec.ts
   e2e/anthropometry.spec.ts e2e/growth.spec.ts` (§4.2) — the only way to confirm the real
   20-40 s generation wait, the escalating pending-message copy, and the generate →
   render → reopen-from-cache flow work against a live backend rather than a fake model.
5. **Run the SC-005 moderated check** (§5) with an actual coach — schedule it the same way
   feature 041 eventually scheduled its own SC-002, and log the dated result as an addendum
   to §5 rather than a new document.
6. Everything else in this feature's own test suite — the offline lane, the config
   validators, the a11y suite, the frontend build/typecheck, `ruff` — is green today and
   needs no further action beyond normal maintenance.
