# QA — Competitions in one place (045)

## T065 — Privacy audit (2026-09-23)

**Verdict: PASS-WITH-FINDINGS.** One HIGH finding (parent payload carried the gap to the winner and to the podium) was found and **fixed with tests**. The MEDIUM finding (F-2) and the LOW finding (F-3) were closed by owner decision on 2026-09-23, as were the three decisions recorded at the end as *known* (see [Follow-up fixes](#follow-up-fixes-2026-09-23)). The text below is the audit as written on the day.

**Scope.** Commit `71eb816` (W1) plus the uncommitted working tree: 34 files in W1, and in the tree 125 modified, 15 deleted and 58 new files. Privacy-critical paths (the audience policy, the results read, history, evolution, insight detail, run status, pending analyses, the import gate/detail/discard endpoints, the dashboard summary, the newsletter and stage-log builders and templates, the family UI) were read in full. Everything else (tests, fixtures, e2e, MSW handlers, docs) was scanned by pattern over the added lines: names, dates of birth, contact data, medical/document terms, e-mails, `console.*`, `localStorage`, URL building. No `.env*` file was read.

Audited against: Ley 1581 / Ley 1098 (minors' data), root `CLAUDE.md`, `spec.md` FR-020..FR-022, FR-060/FR-061, SC-004, `data-model.md` §1..§9, `contracts/api.md`.

### Findings

| # | Sev. | Status | Where | Finding | Action |
|---|---|---|---|---|---|
| F-1 | HIGH | **Fixed** | `backend/app/routers/athlete_race_analysis.py` — `GET /athletes/{id}/race-analysis/insights/{insight_id}` (`_insight_to_detail`) | For a **parent**, `metrics_snapshot` was served as stored. The stored snapshot (`persist_insight`) holds `progression[].gap_to_winner_pct/ms`, `podium_gap[].gap_pct/gap_to_p3_ms`, `season_comparative[].gap_to_winner_ms/gap_pct`, `podium_context` and `category_stats` (field times). The phase-0b redaction only covered `structured`. Reproduced with a probe (parent got `gap_to_winner_pct`, `gap_pct`, `gap_to_p3_ms` in the body). The UI never drew them, but `data-model.md` §1 says the family payload must not carry them ("removed from the payload, not merely hidden"). | Parents now get an **allow-list** projection (`_FAMILY_SNAPSHOT_KEYS = {"progression_assessment"}`, the only key the family client reads: `InsightsTimeline`). Default-deny: a new snapshot key does not reach families until someone approves it. Coach/admin unchanged. |
| F-2 | MEDIUM | **Fixed 2026-09-23** (owner decision 3: coach/admin only) | `athlete_race_analysis.py::get_distribution` — `GET /athletes/{id}/race-analysis/distribution` | Parents can call it (200, pseudonymised). The body lists **every rider's finish time** in the category (`points[].time_ms`), so the winner's and third place's times, and therefore the gap to them, are derivable. `contracts/api.md` says this endpoint is «Coach only, as today», but the router docstring and two tests (`test_get_distribution_parent_receives_display_name_none`, `test_distribution_parent_no_real_names`) deliberately keep parent access. After 045 no family UI calls it (only `CompareView`, coach-only, FR-015). | Not changed: it flips a documented RBAC rule and two tests. Recommended fix: `Depends(_coach_or_admin)` on `get_distribution`, and turn those two tests into «parent → 403». Two lines of code plus the test flip; confirm first that the contract line, not the docstring, is the intended rule. |
| F-3 | LOW | **Fixed 2026-09-23** (names renamed to unmistakably fictitious ones) | `frontend/e2e/ai-insights-coach.spec.ts` (pre-existing since 036, touched by 045): «Camila Restrepo», «Nicolás Duarte», «Valeria Ospina»; `backend/tests/services/training/test_stage_log_builder.py`: `athlete_first_name="Camila"` | Realistic-looking Colombian full names. The e2e header declares them synthetic ("fake names, no real minor"), and the mocks never leave the browser, but the DB forbidden-names list was not available to check them against. | Owner: check the three names against the forbidden-names list, or rename them to obviously fictional ones (e.g. «Atleta Ficticio Uno»). No other realistic full name was found in the added lines: the rest are «Ana Prueba Uno», «Bruno Ficticio Tres», «Nombre Ficticio Uno», etc. |
| F-4 | INFO | No action | `dashboard_summary.compute_identity_decisions_pending` | The count covers the whole identity queue, not the coach's club (documented in `data-model.md` §7). It is an integer only; the app is single-club. | None. |
| F-5 | INFO | Done | `frontend/src/lib/persistAllowList.ts` | `["dashboard","coach-summary"]` is persisted on the device; 045 adds three counts to it. Re-reviewed: integers only. The comment listing its fields was out of date. | Comment updated; no behaviour change. |

### Fixes made

1. `backend/app/routers/athlete_race_analysis.py` — `_FAMILY_SNAPSHOT_KEYS` and `_family_metrics_snapshot()`; `_insight_to_detail` applies it when `for_parent`. `is_first_in_season` and `season_validas_count` are still derived from the stored snapshot before the projection, so they are unchanged.
2. `backend/tests/routers/test_athlete_race_analysis.py` — two regression tests:
   - `test_get_insight_detail_parent_snapshot_has_no_leader_or_podium_gap` (coach keeps the full snapshot; parent gets exactly `{"progression_assessment": …}`; none of the gap values appear anywhere in the body);
   - `test_get_insight_detail_parent_typed_snapshot_keeps_only_allowed_keys` (a snapshot that validates as `MetricsSnapshotV1` — `podium_gap_ms`, `category_time_min_ms` — is projected too, with the keys absent rather than `null`).
3. `frontend/src/lib/persistAllowList.ts` — comment only (F-5).

### Checks that passed

| Check | Result | Evidence |
|---|---|---|
| Winner/podium fields **excluded, not nulled**, for parents in **history** | PASS | `get_history` → `serialize_for_audience` (JSON built from the policy, so keys are absent); `test_athlete_race_history.py`, `test_audience.py` |
| … in **evolution** | PASS | `podium_gap_ms` → 403 before any computation; points omit `gap_pct`; `test_athlete_race_analysis_evolution.py` |
| … in **results read** (coach competition detail and parent page) | PASS | Parent rows are filtered *after* the engine runs (so `field_size` is the whole category) and typed as `FamilyMetricSet`; `CoachMetricSet`'s extra fields are required, so the response re-validation cannot bring them back as `null`; `coach_note` is dropped for parents; `test_results_read_metrics.py` pins the field sets |
| … in **run status** | PASS | `GET /runs/{id}/status` is coach/admin only; a parent gets 403 with and without `since`/ETag and the key never appears in the body; `test_race_run_status_family_gap.py` |
| Family UI does not render them | PASS | `CarrerasTab audience="family"` never mounts «Comparar» (a `?view=comparar` link falls back to «Progresión»); `ProgressionView` narrows with `"gap_to_winner_pct" in point`; `ResultsTable` derives `showLeaderGaps` fail-closed (no role → family); `ParentCompetitionResultsPage` passes `audience="family"`; `HistoryTable`/`EvolutionChart` hide coach-only metrics; `InsightV3Card mode="parent"` hides `gap_to_p3_hhmmss` |
| No PII in logs | PASS | New logger calls carry ids, counts and enum values only: `pending_analyses.list state=… club_scoped=… season=… returned=…`, `race_import_discard import_id=… from=…`, `race_import_<op> identity_pending parse_id=… pending_for_import=N`, `dashboard.*: fallo … (club_ids=…)`. `identity_review.py` adds no logger call. `family_gap_mentions.py` has no logging at all (draft text is never logged or persisted). |
| `athlete_ref` never logged | PASS | Response-only; `test_athlete_ref_never_logged` (caplog) |
| `family_gap_mentions` reaches only coach/admin | PASS | It is computed only in `get_run_status` (`_coach_or_admin`), only on the `hitl_request` event, at read time (nothing persisted); rendered only by `HITLApprovalCard` (coach) as plain React text |
| `GET /imports/{id}` `parse_meta` | PASS | Allow-list (`_PUBLIC_PARSE_META_KEYS`); storage paths, `parse_uuid`, `results_ext` and `corrections` (rows with name/club/city) are excluded; `unreadable_rows` is `{page, ordinal}`; `categories[].completeness` holds ordinal integers; `test_parse_meta_omits_storage_paths_and_manual_corrections` |
| New `409 identity_pending` body and `review_path` | PASS | Body is `{detail, pending_for_import, review_path}`; `review_path` is `/competitions/imports?seccion=identidades&import=<id>` (numeric id only); the log line carries `parse_id` and a count |
| Other new error messages | PASS | `import_id=<n> no existe.`, `import_not_discardable` (status word only), `Run no encontrado`, «El análisis no está desactualizado» — no personal data |
| RBAC and denied paths on new endpoints | PASS | `pending-analyses` (parent 403, other club scoped, admin all), `dismiss-stale` (parent 403, other-club coach 403, 404, 409), `GET/POST /imports/{id}` (parent 403; other club → 404, so existence is not revealed), `discard` audited once and idempotent |
| Fixtures and seeds | PASS-WITH-FINDING | Names are fictional and marked («Ana Prueba Uno», «Beto Imaginario», «Club Ficticio», «… Rival Ficticia»); dates are placeholders (2012-01-15, 2013-01-01); the only e-mail is `coach.prueba@example.com`; see F-3 |
| Device storage | PASS | The only new `localStorage` key is `tyr:045-notice-dismissed:v1:{userId}` = `"1"` (no athlete data). The new query keys (`race-pending-analyses`, `athlete-race-history`, `race-imports`) are not in the persist allow-list, so they are never written to the device |
| URLs | PASS | Only numeric ids and enums (`?tab=races&view=analisis&insight=<id>`, `?seccion=…&import=<id>`); no names or dates |
| Docs and artefacts | PASS | `baseline.md`, `qa.md`, `docs/10-race-results/competitions-one-place.md` carry no personal data; `backend/evals/anthropometry_analyst/results/last_run.md` (rewritten by golden runs) holds aggregate scores only |
| Family newsletter and PDF surfaces | PASS (see known decision 2) | `stage_log_builder` no longer reads `gap_to_winner_*` (a guard test asserts «al P1» is absent); the PDF templates and the summit caption use only `gap_to_median_pct` / `median_gap_pcts`; no template reads `gap_to_winner_*`, `gap_pct` or `gap_to_p3_*` |
| Migration `a76c264449a5` | PASS | Enum change only; the downgrade counts rows and names nobody |

### Tests run

- Backend, default lane: audience/family/results/history/evolution/run-status/pending/identity-gate/dashboard set → **269 passed**; `test_athlete_race_analysis.py` + `_privacy.py` (with the two new tests) → **48 passed**; imports, discard, parent newsletters, stage log, newsletter builder/copy/SVG/PDF, identity review → **330 passed**. `ruff check` clean on the two backend files touched.
- Frontend: `src/components/athletes/races`, `competitions/results`, `routes/parents`, `race/history`, `HITLApprovalCard`, `changeNotice`, `hooks/race`, `identityGate`, `components/athletes/ai` → **761 passed** (62 files); `persistAllowList` → **14 passed**.
- **Not run** (deferred lanes, T068–T070): `pytest -m mysql`, `pytest -m golden`, Playwright. This audit is therefore not a verification of those lanes.

### Known, pending owner decision (recorded on the audit day; all three resolved by the follow-up below)

1. **v3 `summary_text` reaches parents unredacted** via the athlete insights API (`athlete_race_analysis.py::_insight_to_out`). Observed: the same class covers `recommendations[]` and `principles_cited[]` free text in the detail response. F-1 covers the structured *numbers* only; the FR-022 coach warning (`family_gap_mentions`) is the mitigation for free text.
2. **Persisted `stage_log_json` snapshots keep «+N % al P1»; the newsletter v2 prompt passes `gap_to_winner_pct` to the LLM; the stage-log PDF and the parent newsletter pass the full `race_results` to templates.** Observed: `newsletter_builder._build_race_block` still writes `gap_to_winner_*` and `championships[].gap_pct` into the snapshot; `parent_newsletters.py` hands `email_blocks["race_results"]` to the PDF generator. Today no template reads those keys, so nothing is rendered (see the check above); the exposure is the stored/LLM path only.
3. **The identity gate does not cover GENERAL triples; the rebuild ignores `/corrections`.** Not evaluated in this audit. Closed by the 2026-09-23 follow-up (`research.md` §R-08).

### Status

**APPROVED.** F-1 was fixed the day of the audit; F-2 and F-3 were closed by the 2026-09-23 follow-up.

## Deferred lanes and final gate (2026-09-23)

| Task | Lane | Result |
|------|------|--------|
| T068 | `pytest -m mysql` on local `trocha_ruta_test` (root credentials read from the container, never echoed; the app user cannot create the scratch DB used by `test_audit_mysql.py`) | **35 passed**. Single head `a76c264449a5`; `alembic upgrade → downgrade -1 → upgrade` round trip clean. |
| T069 | `pytest -m golden` | **Run 2026-09-23.** Race-analyst golden v3 (the one guarding 045) via `claude-cli` (analyst `claude-sonnet-5`, critic `claude-haiku-4-5`, judge per-provider default): **14/14 cases, composite 0.820 ≥ 0.75 — PASS**, no fallbacks (lowest: 011_course_absent 0.656, 007 0.660, 013 0.692). Run out-of-repo with a parallel runner (`asyncio.gather`, 7 concurrent) because `tests/conftest.py` forces `AI_PROVIDER=google`; not comparable 1:1 with the Gemini-calibrated CI gate, which still runs on the PR (`race-eval.yml`). Anthropometry golden: 12/12 cases, average 0.724 < 0.75 (pre-existing; 045 touches no anthropometry code). Golden fixtures still need regeneration with the time-based percentile (R-02). Both evals rewrite their tracked `results/last_run.md` — exclude from the commit. |
| T070 | Playwright specs from T064 | **Run 2026-09-23 on the isolated stack** — see «T070 — Playwright (isolated stack, 2026-09-23)» below. Not fully green: 1 real 045 finding (HistoryTable desktop link 17 px — **fixed** with `min-h-12` + unit assertion), 2 real pre-existing 043 findings, 3 specs blocked on data the isolated seed lacks. |
| T071 | LCP of family «Carreras» on mid-tier Android / 3G | **Not run** — manual device check. Lazy chunks: CarrerasTab 2.98 KB, ProgressionView 4.84 KB, CompareView 7.87 KB, AnalysisView 14.47 KB, CompetitionImportsPage 5.16 KB (gzip). |
| T072 | Coach tablet check (SC-009) | **Not run** — in-person owner check. |

### T073 — Final gate

- Backend default lane (`MYSQL_HOST=127.0.0.1 MYSQL_DB=trocha_ruta_test`, `--ignore=tests/test_langchain_provider.py`): **214 failed / 5794 passed**. Failures are the `baseline.md` set (login `ProgrammingError` family, `test_resolve_age_*`, v3 prompt/schema/eval age tests, calendar) plus two environment-dependent ones outside 045: `test_growth_summary_latest_analysis::test_null_when_ai_disabled` (reads local `.env`; passes in a clean worktree) and `test_anthropometry_analyst_eval::test_eval_average_meets_threshold` (real-AI eval, 0.724 < 0.75; 045 touches no anthropometry code). Its side effect rewrites `backend/evals/anthropometry_analyst/results/last_run.md` — exclude that file from the 045 commit.
- Race/router suites after the T065 fix: 2979 passed, 3 failed (baseline).
- `ruff` on changed backend files: only pre-existing E402 (`test_dashboard_summary.py`) and F401 (`test_race_imports.py`, also present at HEAD).
- Frontend: `npm run typecheck` clean; `npx vitest run` 4732 passed / 1 failed (`SessionWizardRouteNotify`, baseline); `npm run build` OK.
- Untracked user scripts in `backend/scripts/` intact.
- Flake hardened: `ImportWizard.resume.test.tsx` regression test got a 15 s timeout (timed out once under full-suite load).

## Follow-up fixes (2026-09-23)

### Family payload privacy — owner decisions 1–4 (athlete insights API, `distribution`, stage log, family PDF)

Closes F-2 and «known decision» 1 and 2 of the T065 audit, except the two residuals listed below. Every backend change was written failing-first; the router tests were also re-run with the fix neutralised (plugin in `/tmp`, no tree edits) and fail for the expected reason.

| # | Decision | What changed | Where |
|---|---|---|---|
| 1 | v3 insight free text must not reach parents | For a **v3 row** (`structured_json` present) a parent no longer receives `summary_text` (list **and** detail), nor the top-level `recommendations` and `principles_cited` (detail). Keys are **omitted, not nulled** (the family variant is serialised by hand and returned as `JSONResponse`, same pattern as `/history`). Coach/admin keep the full `response_model` path, unchanged. Why it mattered: the v3 `summary_text` is the markdown rendered from `structured_json`, and it contains «gap a P3 …» and expected-vs-real (`insight_v3._field_reading_line`), i.e. the very figures `_structured_for_response` strips from `structured`. | `athlete_race_analysis.py` (`_is_v3_row`, `_strip_v3_free_text`, `list_insights`, `get_insight_detail`); module docstring |
| 2 | `GET /athletes/{id}/race-analysis/distribution` coach/admin only | `Depends(_coach_or_admin)`; a parent (own child included) gets 403 before any query, and the body has no `points`/`time_ms`. `test_get_distribution_parent_receives_display_name_none` → `test_get_distribution_parent_own_child_returns_403`; `test_distribution_parent_no_real_names` now asserts 403 and no times or names. Router docstring updated (RBAC list and Privacy section). No family screen calls it (`CompareView` is coach-only; `CarrerasTab audience="family"` never mounts it). | `athlete_race_analysis.py::get_distribution` |
| 3 | Persisted `stage_log_json` still says «+N % al P1» | Cleaned **at read time** in `to_parent_dto` (the choke point for the portal, the family e-mail, the coach preview and both PDF routes); **no DB writes** and the input model is not mutated. Drops the winner/podium-gap part from `trail[].sublabel` and `summit.detail` («Copa Valle · +4,1 % al P1» → «Copa Valle»), replaces a `summit.caption` that says «llegó a 4.1 % del primer lugar» (the pre-045 static copy) with the neutral race sentence, drops sentences with the same pattern from `observations[]` (an observation left without claim or evidence is dropped) and from `next_segment.text`. The pattern is narrow on purpose: a percentage glued to «al/del … P1·P3·podio·ganador/a·líder·primer lugar». «Brecha vs. mediana: +4,1 %» and «86 % de asistencia» pass untouched. The result also goes through `redact_for_audience(FAMILY)` (defence in depth: `StageLog` is `extra="forbid"`, so `gap_to_winner_*`-style keys cannot exist today). | `services/training/stage_log.py` |
| 4 | Family templates receive winner/podium data | `_build_stage_log_pdf_context` now passes `race_results` and `charts_context` through `redact_for_audience(FAMILY)` on a copy (the persisted `metrics_snapshot` is not touched). Done in the render module, not in each router, so `parent_newsletters` **and** the coach PDF route are covered. To make the legacy `charts_context.gap_pcts` series (winner gap, present in pre-045 snapshots) go too, `gap_pcts` was added to `FAMILY_EXCLUDED_METRIC_FIELDS` — the single list in `audience.py`. The existing F-9 test that compared `race_results` to the raw fixture now expects it without `gap_pct`. | `services/notification/athlete_newsletter_pdf.py`, `services/race/audience.py`; comment in `routers/parent_newsletters.py` |

**Frontend (decision 1 only).** Reads of the omitted keys had to tolerate their absence: `AthleteInsightOut.summary_text`, `AthleteInsightDetailOut.recommendations` and `.principles_cited` are now optional in `types/athleteRaceAnalysis.types.ts`; `HeroLastInsightCard.tsx` and `InsightsTimeline.tsx` read them with `?? ""` / `?? []` (`insight.recommendations.length` would have thrown on a family v3 detail). The family card itself is unchanged: `InsightV3Card mode="parent"` reads `headline` + `structured` only. The family detail no longer draws the duplicated «Recomendaciones» list for v3 rows (the same actions are in the card).

**Decisions taken while implementing (flag if you disagree).**
- `structured.principles_cited` (inside `structured`) **stays**: the family card renders «Principios citados» from it and the items are section titles of the theory framework. Only the top-level `principles_cited` list is omitted.
- Pre-v3 rows (v1/v2, `structured_json` NULL) keep `summary_text` and `recommendations` — the family UI renders those rows from that text and has no structured card for them. Pinned by `test_get_insight_detail_pre_v3_parent_keeps_free_text`. Fallback rows (`is_fallback`, no `structured`) keep the placeholder text for the same reason.

**Tests.**
- Backend: `test_athlete_race_analysis*.py` + `test_race_analysis_privacy.py` + `test_athlete_race_analysis_privacy.py` → 113 passed; `test_stage_log.py` (18 new, 16 red before the fix; the other two are guards) + `test_stage_log_pdf.py` (context tests + full WeasyPrint renders) + `test_parent_newsletters.py` (4 new, incl. the PDF template context captured with a fake generator and the «no write-back» check) → 77 passed; audience/results-read/history/evolution/newsletter/notification/training/privacy suites → 663 passed, 4 failed (`tests/test_privacy.py`, login-helper `ProgrammingError` family already in `baseline.md`); all `*newsletter*` test files → 195 passed, 1 skipped. `ruff check` clean on the ten touched backend files.
- Frontend: `npm run typecheck` clean; `npx vitest run src/components/athletes/ai src/routes/parents` → 34 files / 431 passed, including two new `InsightsTimeline.v3` cases with family-shaped payloads (keys absent).
- Not run: `pytest -m mysql`, `pytest -m golden`, Playwright. The frontend tests were not proven red before the fix (no `git stash`/checkout in the shared tree); the backend ones were.

**Residuals (not closed here).**
1. **Free text without a number.** The read-time clean-up recognises the pattern the deterministic builder and the v2 prompt produced («N % al P1», «N % del primer lugar»). AI or coach text like «a pocos segundos del ganador» cannot be pattern-scrubbed reliably; it still relies on the FR-022 coach warning (`family_gap_mentions`). `coach_note`, `analyst_reading` and `family_compass` are not scrubbed.
2. **Prompt path** — closed 2026-09-23 (owner decision 5): the newsletter v2 prompt cites only «Brecha vs. mediana» and its context is built from `redact_for_audience(FAMILY)` rows, so the LLM never receives winner or podium gaps.
3. **Docs** — closed 2026-09-23: `docs/technical-notes.md`, `docs/implementation-status.md` and `docs/10-race-results/competitions-one-place.md` now describe the read-time scrub (the stored JSON is unchanged).

Still open after the follow-up: season summaries never become stale automatically; the read-time scrub is numeric-pattern only (`coach_note`, `analyst_reading`, `family_compass` and free text without figures rely on the FR-022 notice); the correction-triggered identity rebuild repeats when it yields no new candidate; golden fixtures need regeneration with the time-based percentile (R-02).

## Follow-up re-audit (2026-09-23)

**Verdict: APPROVED, with one new finding (F-6) found and fixed in this pass.** F-2 and F-3 are **closed and verified**. Scope: the working-tree changes of the follow-up (`athlete_race_analysis.py`, `training/stage_log.py`, `athlete_newsletter_pdf.py`, `parent_newsletters.py`, `audience.py`, `athlete_monthly_newsletter_v2.py` + `.j2`, `race_imports.py`, `identity_review.py`, `pending_analyses.py`, `family_gap_mentions.py`, renamed tests) plus every other reader of the insight text columns (`grep summary_text|structured_json|metrics_snapshot_json|recommendations_json` over `app/`). No `.env*` file was read; no git command that mutates the tree was run.

| # | Sev. | Status | Where | Finding | Action |
|---|---|---|---|---|---|
| F-2 | MEDIUM | **Closed — verified** | `get_distribution` | `Depends(_coach_or_admin)`: a parent (own child included) gets 403 before any query. The only frontend consumer is `CompareView` → `DistributionChart`, and `CarrerasTab` mounts «Comparar» only for `audience === "coach"` (family `view=comparar` falls back to «Progresión»). `build_distribution` has no other caller. | None. |
| F-3 | LOW | **Closed — verified** | e2e / stage-log builder tests | The three realistic names and `athlete_first_name="Camila"` no longer exist anywhere in `frontend/`, `backend/` or `docs/` (grep). They are now «Atleta Prueba Uno», «Ciclista Ficticia Dos», «Deportista Ficticia Tres», «Atleta Prueba». A scan of every added/untracked line for first-name + surname pairs found only marked-fictional names («Mateo Nunca Igual», «… Rival Ficticia»). Dates of birth are placeholders (`2012-01-15`, `2014-05-05`). | None. |
| F-6 | MEDIUM | **Fixed (with tests)** | `backend/app/routers/club_race_insights.py` — `GET /api/races/{race_event_id}/club-insights` (parent, own child) | A sibling reader of the same column that owner decision 1 omits. For a parent the item's `summary_excerpt` was `summary_text[:200]`. On a v3 row that is the rendered markdown: `## Hallazgo principal`, the headline, then `## Lectura del pelotón` with «… terminó en P4 frente a P6 esperada (-2 lugares) · gap a P3 …». Reproduced with a probe: the parent body contained «esperada (-2 lugares)» — the expected-vs-real that `_structured_for_response` strips — and «gap a P3» when the headline is short. The list/detail endpoints of `athlete_race_analysis.py` were fixed, this one was not, and no test covered it. | `_parent_excerpt_source()`: for a v3 row (`structured_json` present) the parent's excerpt comes only from `structured.headline` (family-visible by design); no usable headline → `null`. v1/v2 rows keep `summary_text`. Coach/admin unchanged. 3 new tests in `tests/routers/test_club_insights_by_race.py` (parent v3 → headline only and none of «gap a P3», «esperada», «-2 lugares», «Pregunta para el coach» in the body; parent v3 without headline → `null`; coach keeps the markdown extract). The first was red before the fix. |

### Checks that passed

| Check | Result | Evidence |
|---|---|---|
| Parent list/detail of insights omit v3 free text | PASS | `_strip_v3_free_text` on `summary_text`, `recommendations`, top-level `principles_cited` (keys absent, `JSONResponse`); v1/v2 and fallback rows keep text by design; `metrics_snapshot` allow-list keeps only `progression_assessment` (an enum string). `coach_answer_*`, `coach_question`, expected-vs-real and `gap_to_p3_hhmmss` already stripped. |
| `to_parent_dto` read-time scrub | PASS | Regex probe: «+4,1 % al P1» (also with NBSP), «4.1 % del primer lugar», «a 3,2 % de la ganadora», «12% del líder», «2,5 % del podio», «3 % al P3» are removed; «Brecha vs. mediana: +4,1 %», «86 % de asistencia al primer entrenamiento», «80 % a la primera vuelta» pass. Both legacy builder strings (`_race_position_gap_sublabel`, `summit` detail, `static_summit_caption`) are matched. No DB write; `redact_for_audience(FAMILY)` applied on the copy. |
| Stage-log PDF / parent newsletter | PASS | `_build_stage_log_pdf_context` redacts `race_results` and `charts_context` on a copy (covers `parent_newsletters` and the coach PDF route); `gap_pcts` is in `FAMILY_EXCLUDED_METRIC_FIELDS` (the single list). |
| Newsletter v2 prompt | PASS for structured data | `race_results` goes through `redact_for_audience(FAMILY)` and the template reads only `gap_to_median_pct` (rule 9 forbids leader/podium gaps). `race_block` contributes nothing else to the context. See residual R-1 for carried-forward free text. |
| Identity gate (GENERAL + corrections) | PASS | New log lines: `race_import_<op> identity_pending parse_id=… pending_for_import=N` and `race_import_discard import_id=… from=<status>`; the 409 body carries ids/counts and a numeric `review_path`; `identity_review.py` adds no logger call (keys are name/club/city triples but live only in the DB snapshot and in-memory sets, never in a response or log). Correction handling reads only the `at` timestamps. |
| `pending_analyses` (`kind`) | PASS | Coach/admin only, club-scoped; `kind` is an enum derived from `input_json` (only `event_id`, `season`, `analysis_kind`, `valida_nums` are read); the only log is a `debug` line with state/flag/season/count. |
| `family_gap_mentions.py` | PASS | Pure, no logging, coach/admin only (`get_run_status`), computed at read time, nothing persisted. |
| Fixtures | PASS | See F-3. No e-mails other than `example.com`; the only new `localStorage` key stores `"1"`. |

### Tests run (default lane, `MYSQL_DB=trocha_ruta_test`)

- `test_athlete_race_analysis*.py`, `test_race_analysis_privacy.py`, evolution, history, run-status family gap, pending analyses, club insights → **171 passed** (after F-6).
- `tests/services/training`, stage-log PDF/e-mail, parent newsletters, newsletter v2 use case, audience, identity review, identity gate, race imports (+history) → **554 passed**.
- `ruff check` on `club_race_insights.py` and its test: only pre-existing F401 (`ClubRole`, `ClubMember`), also present at HEAD.
- Not run: `pytest -m mysql`, `pytest -m golden`, Playwright (unchanged deferred lanes).

### Residuals (report only, no change)

- **R-1 — carried-forward free text reaches the LLM.** `analyst_reading_input.headline` / `.action_text` (approved v3 text, via `filter_for_family`) and `previous_stage_title` (last month's persisted title) are rendered into the newsletter prompt without a scrub. Numeric winner/podium gaps do not reach the LLM (verified above), but the v3 `headline` / `field_reading.summary` can still mention «gap a P3» or a percentage to the winner (the season-summary prompt's own example is «mejora sostenida del gap (12.8 % a 7.9 %)», a gap to the winner). Those texts are scanned by the FR-022 notice at approval and are family-visible by design; the notice has no rule for a bare «gap»/«brecha» plus a figure. Suggested (owner decision): run `_LEADER_GAP_RE` over `previous_stage_title` before rendering, and add a «gap/brecha + cifra» rule to `MENTION_PATTERNS`.
- **R-2 — `stage_title` and `family_compass` are not scrubbed** at read time either (only `trail`, `summit`, `observations`, `next_segment`); same class as the existing residual for `coach_note` / `analyst_reading`.

**Status: APPROVED.** F-2, F-3 closed; F-6 fixed. R-1/R-2 are recorded, not blocking.

## T070 — Playwright (isolated stack, 2026-09-23)

**Verdict: the 045 UI works end to end against a real backend and a fresh MySQL, with one real 045 finding (target size) and three specs that could not be exercised for lack of data.** Everything else that failed is spec drift (fixed in `frontend/e2e/`), a pre-existing 043 defect, or environment/data assumptions of the real dev DB.

### Environment

- `frontend/scripts/e2e-stack.sh up` from the working tree (compose project `trocha-e2e`, ports 8001/3307/8026). **`alembic upgrade head` from an empty MySQL 8.4 volume replays cleanly to the single head `a76c264449a5`** (repeated on four fresh volumes), demo seed OK, coach login 200. The stack was reset with `down -v` between iterations and torn down at the end; volume, network and containers are gone. The `me` project was never touched (same container states before and after; nothing on :8000 during the runs).
- The isolated demo seed has **no race data** (only the `Campeonato Departamental 2026` series created by a migration; no events, results or insights). For the data-dependent specs I added, through the public API of the isolated backend only (ad hoc script, not committed): 3 cup series for 2026 and 5 completed events (ids 1–5, so «event 5» exists). No results, no athlete insights.
- Playwright: `E2E_APP_PORT=5175 E2E_API_BASE_URL=http://localhost:8001`, default workers (5); `cup-vs-championship` also run with `--workers=1` (its create/guard tests share one championship series).

### Results — the 12 requested specs (best state after the spec fixes below)

| Spec | Pass | Fail | Skip | Notes |
|------|-----:|-----:|-----:|-------|
| `ai-insights-coach` | 4 | 0 | 0 | incl. `?tab=ai_analysis&insight=` → «Carreras › Análisis IA» |
| `ai-insights-parent` | 3 | 0 | 0 | |
| `ai-insights-hitl` | 2 | 0 | 0 | |
| `ai-insights-newsletter` | 2 | 0 | 0 | 1 was red: stale fixture (see B-3) |
| `race-analysis-championship` | 0 | 0 | 3 | **not verified** — self-skips: needs a season with imported results |
| `race-history` | 1 | 0 | 0 | 045 identity gate exercised for real (see below); needs a fresh volume per run (SHA256 idempotency) |
| `race-course` | 1 | 2 | 1 | 043-005 green after B-6; 043-003 self-skips (needs a completed event with results); 043-001/002 red = A-2 |
| `prefill-import-from-competition` | 4 | 0 | 0 | was 3 red: hardcoded `:8000` (B-1) |
| `target-size` | 8 | 1 | 0 | progresión sweep red = A-1; dashboard test was stale copy (B-5) |
| `competitions-unification` | 13 | 3 | 2 | CU-004/013/006 red = C-1; CU-011/012 are the documented skips |
| `dashboard-coach` | 9 | 0 | 0 | incl. the two new 045 inbox rows and their links |
| `cup-vs-championship` | 7 | 0 | 0 | was 4 red (B-1, B-2, B-4) |

First pass over these specs, before any fix or seed: 66 tests → 40 passed / 20 failed / 6 skipped. Full suite afterwards (minus `race-history`, already consumed, and `cup-vs-championship`, run first): **146 tests → 108 passed / 28 failed / 10 skipped**.

### A — Real defects (app code untouched, per instructions)

| # | Owner | Evidence | Finding |
|---|-------|----------|---------|
| A-1 | **045** | `target-size.spec.ts` «athlete Carreras — progresión» → 3 violations: `<a>` «Válida 1 — Cali» 97×17, «Válida 4 — Palmira» 125×17, «Cto. Departamental — Tuluá» 188×17 px. Source: `frontend/src/components/race/history/HistoryTable.tsx` ~L362–367 (the `md:` table variant renders the race `<Link>` with no `min-h-12`; the mobile `<ul>` variant at ~L277 has it, with a comment saying only mobile was considered). | Constitution III («touch targets ≥ 48×48 px», coach on a tablet ≥ 768 px = table variant). The link is the only way from «Progresión» to a válida. New sweep from T064 is what caught it; unit tests cannot measure layout. Fix: `inline-flex min-h-12 items-center` on the table-variant link (row height is not the constraint). |
| A-2 | 043 (not 045) | `race-course` 043-001: with the first variant uploaded the variant persists (row + «137 puntos» in the failure snapshot) but `variant-upload-question` never renders (3/3 serial runs; it did render once when two workers ran). 043-002: description persists (all four fields on reload) but the success toast is never observed. Sources: `components/race/course/CourseTab.tsx` L152–167 hosts the upload `VariantUploadDialog` inside the `!has_course_data` branch, and the mutation's `invalidateQueries` flips that branch → the sheet unmounts mid-flow. `CourseDescriptionCard.tsx` renders two different `EditCourseDescriptionDialog` elements (L174 for `empty`, L251 for `complete`); saving flips empty → complete → the instance holding the toast unmounts. Both files are unchanged in the 045 working tree. | The race the spec header predicted (first real-infra run of 043). User-visible: after uploading the first GPX the coach is not asked to confirm the detected laps, and gets no «guardada» feedback on the first description. Fix belongs in 043 code (mount the dialog outside the state-dependent branch). I left both assertions as they are — loosening them would hide the bug. |

### B — Spec drift, fixed in `frontend/e2e/` (all category (b); no app code changed)

| # | File | Fix |
|---|------|-----|
| B-1 | `cup-vs-championship`, `prefill-import-from-competition`, `race-analysis-championship`, `race-course` | `BACKEND` was the literal `http://localhost:8000` (the developer's **real** backend) in specs that **write** (create series/events, upload GPX). Now `process.env.E2E_API_BASE_URL ?? "http://localhost:8000"`, same default as the other helpers. Without this, on a day when the `me` backend is up these specs would have created data in the real club DB (the isolated stack signs tokens with the same JWT secret via the shared root `.env`). |
| B-2 | `cup-vs-championship` | Post-create navigation is now `/competitions/:id?tab=circuito` (045, `CompetitionFormPage.tsx` L464); the two `toHaveURL(/\/competitions\/\d+$/)` accept the query. |
| B-3 | `ai-insights-newsletter` + new `e2e/helpers/stage-log.ts` | NEWSLETTER-001's newsletter mock predates Bitácora (038): without `stage_log` the studio shows «todavía no tiene contenido generado» and no `<h1>`. Mock now returns a StageLog v2 (same shape as `newsletter-conflict.spec.ts`, which was left alone). |
| B-4 | `cup-vs-championship` | `CHAMPIONSHIP_SERIES_ID = 4` (an id of the real DB; on a fresh DB the championship series is id 1 and 4 is a cup) → discovered by `kind === "championship"`. |
| B-5 | `target-size` (dashboard test) | `getByText("Próxima carrera Copa Valle")` matches no node since the 035 dashboard redesign (label «Próxima carrera» + a separate name paragraph; only the link's accessible name has both). Now `getByText("Próxima carrera", { exact: true })`. The two new 045 inbox rows pass the 48 px floor. |
| B-6 | `race-course` | 043-005: `getByText(/circuito/i)` counted the page title («E2E Circuito — válida de prueba …», the spec's own event name); filtered out. 043-001: «Sí, guardar» only **closes** the sheet (`VariantUploadDialog` L471), it never reaches `variant-upload-success`; the assertion now waits for the question to disappear. Header note about `BACKEND` updated. |
| B-7 | `race-history` | (1) The identity queue only raises candidates when one side is already linked to a club athlete (`identity_review.in_club_scope`, 044 decision 2026-09-22), and the spec linked «Mateo» only **after** both commits, so the 2025 commit met no gate, «Mateo» stayed two competitors and the progression had one season. The link now happens right after the 2024 commit, and reaching the 2025 commit without a 409 is a hard failure instead of a tolerated branch. (2) The gate-copy regex `decisiones? de identidad …` cannot match «decisión»; now `decisi(ón|ones)`. |

With B-7 the spec verifies, for real: `409 identity_pending` on the 2025 commit with «Hay 1 decisión de identidad pendiente para esta carga. Resuélvelas en «Cargas e identidades» y vuelve: tu carga queda guardada.», the `wizard-identity-review-link` to `/competitions/imports?seccion=identidades&import=<id>`, the decision, the final commit from «Cargas», the category-change marker in «Carreras › Progresión», and no third-party names / no «brecha vs. 1.ª posición o podio» / no «Comparar» in the family view.

Product note (not a bug): because of `in_club_scope`, a historical load of an athlete who is **not yet linked** never raises an identity gate; the same person then lives as two competitors until someone links one of them and reruns the queue. That is the 044 design, but the spec's original assumption («casi seguro bloqueada aquí») was wrong for that case.

### C — Environment / data assumptions of the real dev DB (not 045; not fixed)

| Spec(s) | Cause |
|---------|-------|
| C-1 `competitions-unification` CU-004, CU-013, CU-006 | Need a season with imported results and athletes with club insights (spec comment: «4 atletas con club-insights, temporada 2026 con 5 atletas»). The isolated seed has none; the pages render their empty states correctly («No hay resultados registrados para la temporada 2026», «No hay insights generados para esta válida aún»). **Not verified** — the Temporada table, row → «Carreras › Análisis IA» and the scoped insights grid still need a fixture with results + approved insights. |
| `invitations` ×7, `parents` PAD-006 | Hardcoded parent id / «Carlos Garcia» of the real DB («Padre / acudiente no encontrado»). |
| `anthropometry-record-explanation` ×2, `growth-analysis` | Stack runs `AI_ENABLED=false` / fake provider; the explanation stays `record-explanation-pending`. |
| `calendar-parent` CAL-P-05, `session-content-unification` | Expect real seeded events / session content. |
| `cold-start` 012-3 | Mocked login, but a live backend answers 401 to the endpoints the mock does not cover and the app logs out (the spec assumes no backend). Not root-caused beyond that. |

### D — Other red specs, pre-existing and unrelated to 045 (not fixed)

`athlete-archive` ×2 (strict-mode: `archived-athlete-row` matches both the card list and the table); `parents` PAD-005 (the «Padres» link lives under the collapsed «Familias» area since the 035 nav; 045 did not touch that group); `newsletters-coach` NL-006/007 (`narrative-editor-form` no longer exists since Bitácora); `monthly-technical-report-coach` ITR-002 (editor order differs: `plan_entrenamiento` and `competencia` moved) and ITR-006 (`download-pdf-button` not found, not analysed); `auth` E2E-010 (logout menu item «outside of the viewport», already force-clicked in the spec, not analysed). None of these files is in the 045 working-tree diff; I did not compare against HEAD in a worktree.

### Not verified by this run

- `race-analysis-championship` (3, self-skipped), CU-004/006/013, 043-003: need results/insights in the isolated DB. Suggested follow-up: an e2e seed step (results + one approved insight per athlete) so these stop being data-dependent.
- Everything AI-driven end to end (fake provider); `pytest -m golden` and T071/T072 unchanged.

### Files changed (all under `frontend/e2e/`)

`cup-vs-championship.spec.ts`, `prefill-import-from-competition.spec.ts`, `race-analysis-championship.spec.ts`, `race-course.spec.ts`, `race-history.spec.ts`, `target-size.spec.ts`, `ai-insights-newsletter.spec.ts`, new `helpers/stage-log.ts`. Reproduce: `frontend/scripts/e2e-stack.sh up` → seed the three cup series + five events above → `cd frontend && E2E_APP_PORT=5175 E2E_API_BASE_URL=http://localhost:8001 npx playwright test <specs>` → `frontend/scripts/e2e-stack.sh down -v`. `race-history` needs a fresh volume each time.

## Phase 9 — Convergence (2026-09-23)

`/speckit-converge` appended T074–T084 (3 HIGH, 5 MEDIUM, 3 LOW); all implemented the same night:
season summaries go stale on a revised import (T074), progression points and championship cards link to
their competition (T075–T076), plain-language run timeline (T077), 48 px edit-dialog buttons (T078),
«sin dato» on the championship card in app and PDF (T079–T080), unlinked competitors counted in the
«Cargas e identidades» badge (T081, count == list), golden v3 metrics regenerated with the engine via
a one-off golden-metrics regeneration script, since removed (T082), championship delete copy (T083), Home row
«Análisis desactualizados» (T084).

Verification: backend default lane 213 failed (baseline set, 0 new), frontend vitest 4779 passed /
2 failed (`SessionWizardRouteNotify` baseline; `useRaceRun` polling-ceiling test flaky only under the
full suite, 21/21 in isolation), typecheck and build clean. Race-analyst golden v3 with the regenerated
fixtures via `claude-cli`: 14/14 cases, composite **0.828** (case 008 hit a CLI timeout → fallback 0.205
in the parallel run, re-run alone 0.870; parallel average as recorded 0.780) vs 0.820 before
regeneration — SC-008 holds (≥ 0.75, no drop > 0.03). Not run: `pytest -m mysql`, Playwright.
Residuals: the worked examples in `race_analyst_v3.md` / `race_season_summary_v3.md` still quote
position-based percentiles; `test_v3_cases_declare_data_gaps_when_a_block_is_missing` fails for
case_014 (adult, pre-existing); the championship card formats «P4»/«78» while tables use «4°»/«P78»;
sent newsletters are marked outdated only by per-válida insights, not season summaries.
