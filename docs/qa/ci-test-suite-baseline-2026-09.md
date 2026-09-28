# CI Test-Suite Baseline — September 2026

**Date:** 2026-09-25
**Scope:** default `pytest` lane (backend) and `npm test` + `npm run build` (frontend), measured in a clean environment (Docker, no local `.venv`, no local `.env`).
**Privacy:** no real minors' data was added to any fixture, log or message.

## Goal

Make both suites green in an environment equivalent to a GitHub runner, and make sure each test still means something. Rules used: every fix targets the root cause; no `skip`/`xfail`/`|| true`; no loosened assertions without a justification; no production change just to satisfy a test. Mutation-killer tests (`docs/qa/mutation-testing-2026-06.md`) were not deleted or weakened.

## Method (how to reproduce)

- Backend: image `python:3.13` + WeasyPrint system libs + `pip install -r backend/requirements.txt pytest pytest-asyncio pytest-mock ruff`; the whole repo mounted at `/repo` (some tests read `frontend/src/data` and `specs/`); `cd backend && python -m pytest`. **`backend/.env` and `.env` must be shadowed** (e.g. bind-mount an empty file over them): `Settings` reads `backend/.env` from the cwd, so a mounted developer `.env` silently leaks real AI keys and the real MySQL host into the "clean" run (this hung the first attempt on a real golden-eval call).
- Frontend: fresh copy of `frontend/` without `node_modules`, `node:22`, `npm ci && npm test && npm run build`. Use `--cpus=4` to mimic a runner (see "Frontend" below).

## Before / after

| Lane | Before (clean checkout of the working tree) | After |
|---|---|---|
| Backend default lane, with a throwaway MySQL | 41 failed, 6319 passed, 84 skipped, 13 xfailed, 6 xpassed | 6382 passed, 82 skipped, 0 failed, 0 xfail, 0 xpass |
| Backend default lane, **no network, no MySQL** (`--network none`) | 185 of the ~235 tests in the 14 files that use the bare `client` fixture failed at HEAD (measured on that subset) | 6382 passed, 82 skipped, 0 failed (2 consecutive runs) |
| Backend `pytest -m mysql` (throwaway MySQL 8.4, root URL, DB name ends in `_test`) | not measured | 37 passed |
| `ruff check --select E9,F63,F7,F82` (the CI lint gate) | passes | passes |
| Frontend `npm test` | 2 failed (one always, one intermittent) | 406 files / 4944 tests passed, 3 consecutive runs at `--cpus=4` |
| Frontend `npm run build` | passes | passes |

The 82 remaining skips are all explicit lane skips: 35 `mysql` lane (`TEST_DATABASE_URL` absent), 36 golden/integration (no AI key), 11 race-eval version selector (`RACE_EVAL_VERSION=v3` skips the v2-only path). Nothing is skipped silently any more (see the `test_audit_coverage.py` and `test_session_media.py` rows).

## Classification of each failure

Verdict column: CODE = production bug fixed; TEST = obsolete/badly written test fixed; DELETED = test removed.

| Test(s) | Root cause | Verdict | Action |
|---|---|---|---|
| `tests/test_circuit_diagram_partial.py` (18) | Commit `718d249` (bulletin redesign) deleted `templates/documents/pdf/charts/circuit_diagram.svg.jinja` together with `test_circuit_renderer_equivalence.py`; nothing else references the template. | DELETED | File removed (see list below). |
| `tests/models/test_race_import_revision.py` (2), `tests/models/test_race_import_upload_columns.py::test_alembic_migration_upgrade_adds_all_columns` | Absolute paths of the developer's Mac. | TEST | Paths resolved from `__file__`; existence asserted first. |
| `test_llm_helpers.py::test_build_chat_llm_constructs_claude_cli_instance_without_calling_api` | Needs `langchain-claude-cli`, deliberately absent from `requirements.txt` (local-only, never on Render). | TEST | A fake module is injected in `sys.modules`; the test now pins our wiring exactly (`{"model", "timeout"}` and no `temperature`/`max_tokens`) and fails if the model is invoked. No `importorskip`. |
| `test_notification_changes.py::TestAnthropometryNotificationLogic` (7) | `create_anthropometry` now does `await db.commit()` (fix for a real POST→GET race); the test's `db` mock was a bare `MagicMock`. | TEST | `db.commit = AsyncMock()`; new regression test asserts exactly one commit, after the flush, with and without notification. |
| `test_session_media.py` (skipped in clean env) | Fixture used `piexif`, which is not a project dependency (production strips EXIF by re-encoding with Pillow), so the GPS-stripping privacy test silently skipped. | TEST | Fixture rebuilt with Pillow only; added a precondition (the fixture really carries GPS) and a check that the thumbnail is clean too. |
| `test_training_session_router.py::test_past_date_returns_422` | The past-date validator was removed on purpose in `eadb34d` (retroactive logging; the service gained an `is_future` guard so past sessions never e-mail parents). Test hard-coded `2000-01-01` and expected 422. | TEST | Replaced by two tests with relative dates: a past date is accepted (201); a past date never notifies parents while a future one does. |
| `test_calendar_models.py::test_event_data_competition_valid` | Since `5a6a07a` a competition requires `race_event_id`. The sibling "invalid shape" test was passing for the wrong reason. | TEST | Fixtures updated; the shape test now asserts the failure is about `race_category`; two new tests cover the `race_event_id` rules. |
| `test_clubs.py::TestAddMember::test_admin_adds_member_to_club` | Feature 041: staff accounts require `club_id` and have no password at creation; notification service must be stubbed. | TEST | Payload and setup updated (two fresh clubs, coach created in one and added to the other). |
| `test_calendar_audiences.py::test_set_audiences_borra_y_reinserta` | Since `2cc1431` the service issues one bulk `DELETE` (avoids an async lazy-load) instead of `db.delete()` per row. | TEST | Now asserts the emitted statement, the inserted row and that DELETE happens before INSERT; the empty-list test no longer asserts a vacuous `db.delete` not-awaited. |
| `test_parent_register.py::...reactivates_inactive_pre_created_user` | Feature 041: deactivating an account requires `reason_code`. | TEST | Payload updated. |
| `routers/test_body_composition.py::test_field_guide_...` (3 == 2) | Real, environment-dependent layout bug: the skinfold field-guide PDF had ~0 pt of slack on page 2 and spilled its footer to a third page under Linux/Pango metrics (the production container and CI). | CODE | Template CSS in `skinfold_field_guide.html` (scoped margins/header) now leaves real slack; test unchanged. |
| `services/notification/test_stage_log_pdf.py::test_heaviest_month_with_annex_still_within_three_pages` (4 pages > 3) | Real production bug: `templates/documents/pdf/base/layout.html` declared `@font-face` with `url('../static/fonts/...')`, but WeasyPrint's `base_url` is `backend/templates`, so the brand fonts never loaded; PDFs silently fell back to Arial (macOS) or DejaVu (Linux/production), which changed pagination (spec 038 AC-5.2: 3 pages). | CODE | Font URLs fixed to `static/fonts/...`; footer spacing tightened in `athlete_stage_log.html`; new `test_pdf_brand_fonts.py` checks statically that every `@font-face` URL resolves to a bundled file and that the rendered PDF embeds Inter / Plus Jakarta Sans. |
| `race/agents/test_schemas.py::test_analysis_input_age_bounds`, `race/ai/test_invariants_v2.py::test_resolve_age_logs_warning_when_out_of_range` | Commit `4c549eb` (adult athlete path) widened the plausible age range to 6..80; the tests still expected a ceiling of 20 (an adult of 50 fell back to age 12). | TEST | Bounds updated (valid: 6, 18, 31, 80; invalid: 5, 81), 50 now asserted as valid and silent. |
| `race/test_prompt_v3_blocks.py::test_adult_analyst_prompt_never_claims_maturation_...` | The adult branch of `race_analyst_v3.md` and `race_season_summary_v3.md` named the labels "Pre-PHV, Circa-PHV, Post-PHV" in order to forbid them; naming a forbidden term in the prompt seeds it in the output, and the adult golden case lists those labels in `forbidden_terms`. | CODE (prompt) | Prompt reworded to forbid "any phase label relative to the growth peak" without naming the labels; test now checks the whole maturation block and all three labels, adds a positive control for a minor and covers the season prompt. **The golden eval baseline was not re-run** (needs an AI key): re-run `pytest -m golden` before relying on the new wording. |
| `evals/test_race_analyst_eval.py::test_v3_cases_declare_data_gaps_when_a_block_is_missing` (case_014 adult) | Adult maturation is not a data gap; the prompt forbids mentioning it and `scorer_v3` scans `data_gaps` against `forbidden_terms`. The dataset case was right, the structural test was wrong for adults. | TEST | Adults are held to the opposite rule (the ideal must NOT declare anthropometry/maturation as a gap), using the same adulthood rule as `scorer_v3`. |
| `privacy/test_city_not_serialised.py::test_race_identity_routes_are_actually_mounted_...` | FastAPI 0.14x keeps each `include_router` as a lazy `_IncludedRouter` in `app.routes`, so the scan iterated over zero `/api/*` routes: the whole city-privacy sweep would have passed vacuously. Not a leak of `city`. | TEST (scan) | The sweep now walks routes through `tests/helpers/app_routes.iter_api_routes` (extended with `response_model`); a new self-test proves it reaches routes outside `race-identity`. |
| `services/test_strava_ingest.py::TestStravaClientRefreshIntegrationBug` (xfail) | Real production bug: `StravaClient` read attributes (`result.access_token`) from `oauth.refresh_access_token`, which returns Strava's raw dict, so any token refresh raised `AttributeError`. The xfail documented it; a second test (`test_strava_client_laps.py`) mocked the wrong shape. | CODE | `app/services/strava/client.py` consumes the dict (validates keys; a malformed response counts as a failed refresh); xfail removed; the mock now uses the real shape. |
| `test_users_delete_deactivate.py::test_delete_parent_with_training_session_maps_to_409` (xfail) | The SQLite harness did not enforce FKs. | TEST | `PRAGMA foreign_keys=ON` after seeding; asserts the 409 detail and that the parent survives; xfail removed. |
| `test_audit_coverage.py` (silent "empty parameter set" skip) | A parametrization over an empty list reported as a skip on every run. | TEST | Replaced by `test_dynamic_audit_smoke_is_not_silently_bypassed`, which fails if an `Audited` entry ever declares a `request_factory` without the dynamic smoke test existing. |
| `race/ai/test_guardrails_race_v2.py`, `race/ai/test_analyst_agent_v2.py` (8 + 3 xfail, 6 xpass) | Pre-implementation sketches written against a guessed API ("xfail if the API is not there"). The real implementation landed with other names and is covered elsewhere. | TEST / DELETED | Rewritten against the real API; sketches already covered elsewhere removed (list below). |
| Frontend `SessionWizardRouteNotify.test.tsx` "si falla la creación…" | The wizard renders errors through `extractErrorDetail`: backend `detail` wins, an unanswered request shows the calm cold-start copy, and only an empty error falls back to "No se pudo crear la sesión…". The test rejected with a bare `Error("boom")` whose message is now shown verbatim. UI is correct. | TEST | Three tests (backend 409 detail + retry succeeds, cold-start copy, generic fallback), all asserting the alert and that the form is kept. |
| Frontend `DistributionChart.test.tsx` "un fallo de red (forma cold-start)… (T039)" | The component always requests `/races`; with no MSW handler the request bypassed to the real network (`onUnhandledRequest: "bypass"`), so a second error state with the same copy could appear in the same commit and `findByText` saw two nodes; outcome depended on the machine. | TEST | Default `racesListHandler` registered in `beforeEach`; tests that need another list override it. |

## Tests deleted

| File / test | Evidence |
|---|---|
| `backend/tests/test_circuit_diagram_partial.py` (18 tests) | Template `circuit_diagram.svg.jinja` deleted in `718d249` (the same commit deleted its sibling `test_circuit_renderer_equivalence.py`); no code or template references it (grep over `backend/`, `frontend/src`, `docs/`). Only specs mention it historically. |
| Sketch tests in `test_guardrails_race_v2.py` / `test_analyst_agent_v2.py` (forbidden real names, empty forbidden list, veto N=1) | Exact behaviours covered by `test_race_ai_privacy_invariants.py::TestGuardrailForbiddenNamesUnit` and `test_guardrails_race_v2_n1.py`. The word-cap sketches were NOT simply dropped: `check_v2_section_word_limits` exists in production (120 + 10 % per section) and had no real test, so new tests were written against it (132 passes, 133 flagged, only the offending section flagged, unknown sections unlimited). The sketch's 4th section ("Resumen de temporada", 200 words) is not part of the v2 guardrail and was not carried over. |

## Structural finding: the `client` fixture was not hermetic

`tests/conftest.py::client` used `ASGITransport(app=app)` without overriding `get_db`. Fourteen files (~235 tests: login, users, clubs, consents, sessions, athletes, parent register, privacy, security…) plus some tests in nine more talked to whatever MySQL `Settings` resolved, and assumed the dev seed. Consequences: default lane not offline (Principle II violation), order/state dependence, and, with a `.env` pointing at production, real writes (users, athletes, consents, clubs) from a test run. The 041 close-out note (233 failures offline) is the same symptom.

**Decision (Phase B): done.** Feasibility was measured before touching anything: all 51 tables compile on SQLite; the 23 affected files contain zero MySQL-specific SQL (`JSON_EXTRACT`, `ON DUPLICATE KEY`, `FOR UPDATE`, `DATETIME(fsp=6)`, `VARBINARY` collisions) in the paths they exercise; the dev seed (`scripts.seed.seed(session)`) and the LMS growth tables load on SQLite. Implementation (`tests/conftest.py`):

- One seeded in-memory aiosqlite template DB per session (schema + privacy-policy rows reused from the migrations + LMS data + dev seed); each `client` test gets a fresh copy through SQLite's backup API (~20 ms), so tests are isolated from each other.
- `app.database.AsyncSessionLocal`/`engine`, the name imported by `app.dependencies`, and the race-AI `db_factory` are pointed at SQLite for the whole session, so code that opens its own session (background tasks, Strava, race analysis) cannot reach MySQL either.
- Tripwire: a `do_connect` listener on the original MySQL engine raises if anything connects to it in the default lane. The `mysql` lane uses its own engine from `TEST_DATABASE_URL` (with the existing `_test` name guard) and is unaffected (37 tests pass).
- Cost: wall time is unchanged within noise (bcrypt on seed-user logins dominates, not the DB).
- One test was strengthened: `TestParentIDORFilterByForeignAthleteId` skipped silently on a fresh DB; it now creates a synthetic foreign athlete so the IDOR invariant is always exercised.

**Behaviour change to be aware of (reported, not hidden):** running plain `pytest` locally no longer touches the MySQL from `.env`, and it fails loudly if some test tries to. Anyone who relied on the default lane exercising the local MySQL must use the `mysql` lane. Uvicorn/dev flow is unaffected.

**Risk to check by hand:** before this change, every local default-lane run with a production `.env` could have created synthetic users/athletes/clubs in production. Look in production for accounts with synthetic e-mails (`test-<hex>@test.com`, `parent_sec_test@…`) and clubs with codes like `test-<hex>`. This was not checked (no access to production data or `.env` from this work).

Additional hardening proposed, **not** implemented (would affect scripts that build their own engine from `settings.database_url`, e.g. `app/seed_growth_data.py`, `scripts/retention_audit_log.py`, `alembic/env.py`): in `conftest.py`, before importing `app`, force `MYSQL_HOST=invalid.test` and `MYSQL_DB=guard_not_a_db_test`.

## Frontend note: CPU oversubscription

At `--cpus=4` (a GitHub-hosted runner) the suite passes 3/3. In a Docker VM with 10 CPUs and 7.7 GB (many parallel jsdom workers) three unrelated tests failed consistently in the full run and pass alone: `MyAthleteDetailPage.test.tsx` ("ninguna vista muestra «Brecha…»"), `MyAthleteDetailPage.growth.test.tsx` (FR-016) and `CircuitAndConditionsTab.test.tsx`. They use the default 1000 ms `findBy*` timeout on lazily loaded pages. Not fixed: it is load-induced, not a logic error. If it shows up in CI, set `configure({ asyncUtilTimeout: … })` in `src/test/setup.ts` or cap `maxWorkers`.

## Open items

- CI workflow: `ci-backend.yml` can now drop the MySQL service, `MYSQL_*` env and the migrate+seed step (the job would need no database). It was left untouched in this change (the edit was blocked by the tool's permission policy); the existing workflow still passes with MySQL present. The `mysql` lane could get its own optional job.
- The default lane is still not deselecting `golden`/`integration`/`mysql` by marker (`pyproject.toml` has no `addopts`); they rely on self-skips when keys/URLs are missing. With a real AI key in a local `.env`, plain `pytest` runs the paid golden evals. Suggested: `addopts = -m "not golden and not integration and not mysql"` (a later `-m` on the command line overrides it).
- The removed sketch assumed a 200-word "Resumen de temporada" cap; the production v2 guardrail limits only the three válida sections. Product decision needed if the summary cap is mandatory.
- The adult prompt wording change needs a real `pytest -m golden` run (AI key) to confirm the composite stays above the blocking threshold (0.75).
- Not run here: Playwright e2e, `pytest -m golden`, `pytest -m integration`.
