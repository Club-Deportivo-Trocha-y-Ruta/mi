# Guided anthropometric capture — QA

Feature `specs/048-anthropometry-capture-ux`. Scenario list: `specs/048-anthropometry-capture-ux/quickstart.md`.
Status as of 2026-09-29: implemented on `main`, uncommitted, not deployed, not verified on real
infrastructure. This file states what ran and what did not; it does not claim more than the
reports below.

## 1. What ran

| Lane | Command / scope | Result |
|---|---|---|
| Frontend typecheck | `npm run typecheck` | Passed |
| Frontend full vitest | `npx vitest run` (after the wave-3 fixes) | 429 files, 5121/5121 passed |
| Frontend 048 vitest, after the e2e-found fix | `src/components/athletes/anthropometry-capture`, `AnthropometryEditPage.test.tsx`, `src/routes/anthropometry` | 7 files, 57/57 passed |
| Frontend capture folder | `src/components/athletes/anthropometry-capture` | 39/39 passed (before the StrictMode test was added) |
| Frontend privacy-audit subset | session store, `lib/anthropometry`, capture components, roster hook, edit page | 12 files, 78/78 passed |
| Backend anthropometry lane | `tests/anthropometry` | 227/227 passed (privacy audit run) |
| Backend template/document/body-composition subset | `tests/test_template_registry.py tests/test_document_generator.py tests/routers/test_body_composition.py tests/anthropometry/test_field_guide_basic_measures.py` | 52/52 passed |
| Backend audit lane | route-policy and audit coverage tests | Reported green in waves 1–2 (no count recorded) |
| Build | `npm run build` | Reported OK in waves 1–2 (proves the four webp assets exist) |
| Playwright, isolated stack | `frontend/scripts/e2e-stack.sh` (API :8001, MySQL :3307), 6 files touching 048 | 16 passed, 2 failed (same on two consecutive runs) |

Backend test command used: `cd backend && PYTHONPATH=. DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib AI_ENABLED=false .venv/bin/python -m pytest <paths> -q`.

Mutation check: the StrictMode regression test in `CaptureReviewStep.test.tsx` fails without
the fix and passes with it.

## 2. E2E detail

New specs (all clean up what they create; athletes are synthetic and named «Ficticio…»):

| Spec | Tests | Covers |
|---|---|---|
| `frontend/e2e/anthropometry-capture.spec.ts` | 5 | Guided path with net sitting height, +20 % weight warning, plain PHV label, history «Revisar»; quick mode persisted across reload; same-date dialog; offline retry with exactly one record; 360 px path with no horizontal scroll |
| `frontend/e2e/anthropometry-edit-delete.spec.ts` | 3 | Evaluator edits (Pre-PHV to Circa-PHV) and deletes; `coach2` gets 403 `not_record_author` and sees no actions; parent view has no actions and no `can_modify`/`plausibility_flags` keys |
| `frontend/e2e/anthropometry-session.spec.ts` | 3 | Pick 3, measure/skip/measure, summary 2/1/0; skinfold detour and return; reload loses the session; 360 px picker plus one capture |

Updated: `anthropometry.spec.ts` (E2E-005, E2E-006), `body-composition.spec.ts` (link entry,
local-date fix, athlete 1 record cleanup in `beforeAll`/`afterAll`),
`anthropometry-record-explanation.spec.ts` (navigation and fallback capture).

Target set result: 16 passed, 2 failed. The 2 failures are both in
`anthropometry-record-explanation.spec.ts`: the AI explanation POST returns 503 because
`docker-compose.e2e.yml` sets `AI_ENABLED=false` while the spec asks for `AI_ENABLED=true` with
`AI_PROVIDER=fake`. This is an environment mismatch, not a 048 defect. Owner decision pending:
enable the fake provider in the e2e compose file, or skip those tests when AI is off.

Full Playwright suite, run once: 33 failed, 14 skipped, 123 passed (2.9 min). None of the failures
are in 048 specs except the AI pair above. A rerun of the 14 failing non-048 files with
`--workers=1` gave 29 failed, 6 skipped, 45 passed; two cup-vs-championship tests
(E2E-014-001, E2E-014-004) passed alone and are a parallel-load flake. The 29 deterministic
failures are in specs and UI that 048 did not touch (ai-insights-coach, athlete-archive,
calendar-parent, cold-start, competitions-unification, cup-vs-championship 005a,
growth-analysis, growth 040-001, invitations, monthly-technical-report, newsletters-coach,
parents, race-course, session-content-unification). No HEAD baseline e2e was run, so
"pre-existing" rests on which files each spec touches plus the single-worker reproduction.
`growth.spec` 040-001 probably comes from the feature 047 `AthleteInfoCard` change; unconfirmed.

## 3. Real defect found by e2e and fixed

The review-step plausibility dry-run hung in dev/StrictMode (see `design.md`, implementation-time
findings). Before the fix `anthropometry-capture` had 2 failed / 3 passed; after, 5 passed.

## 4. What did not run

| Item | State |
|---|---|
| `pytest -m mysql` (real FK cascade on DELETE, quickstart A6) | Not run. No MySQL lane in these sessions. The optional T058 cascade test is not recorded as done |
| `pytest -m golden` | Not run. Not required: no prompt or model changed |
| Full backend `pytest -q` | Not run. A broad collection hit an error in `tests/test_langchain_provider.py` (see section 6) |
| `ruff check` | No result recorded |
| Bundle-size check (lazy routes ≤ 150 KB gzip each, T057) | No result recorded |
| Playwright mobile project | Does not exist (open TODO in `CLAUDE.md`); 360 px is covered by in-spec viewport blocks only |
| 48 px touch-target sweep on the new pages | Not covered: `e2e/target-size.spec.ts` sweeps a curated set of mocked screens with no route list to extend |
| Tablet check by the owner (T061): guided capture under 2 minutes (SC-003) and a 3-athlete session | Pending (owner) |
| Post-deploy smoke: `/health` plus GET anthropometry of the demo athlete | Pending until deploy |
| SC-006 (coach rates the flow easier; corrections within 7 days tracked) | Needs a real measurement day; no result |

Tablet check result (T061): pending. Record it here when done.

| Date | Device | Guided time (4 measures) | 3-athlete session | Notes |
|---|---|---|---|---|
| — | — | — | — | — |

## 5. Privacy audit summary

`specs/048-anthropometry-capture-ux/privacy-audit.md`: approved with recommendations (0 blockers,
1 major, 3 minor). It ran before the 048 e2e specs existed, so those specs were not audited.

| # | Severity | Item | State |
|---|---|---|---|
| P-1 | Major | `notes` in `backend/app/schemas/anthropometry.py` has no `max_length` (frontend caps at 2000); over MySQL's TEXT limit a DataError reaches the generic 500 handler and SQLAlchemy's error text can include bound values, since `app/database.py` does not set `hide_parameters`. Only the MySQL lane would reproduce it | Open. Proposed fix: `Field(default=None, max_length=2000)` plus a 422 test; `hide_parameters=True` as a platform-wide change (pending decision) |
| P-2 | Minor | Roster could return `age_decimal` instead of `birth_date` | Open (proposed) |
| P-3 | Minor | PUT 409 bodies carry the minimum age and skinfold-set dates | Accepted in the audit |
| P-4 | Minor | `e2e/anthropometry-record-explanation.spec.ts` references the demo-seed name «Santiago López» | Open: confirm it is fictional |

## 6. Known issues outside 048

| Issue | Note |
|---|---|
| `lib/datetime` `formatDate` parses `YYYY-MM-DD` as UTC midnight | Possible off-by-one day in America/Bogota. Not fixed here |
| `test_null_when_ai_disabled` (`test_growth_summary_latest_analysis.py`) depends on the local `AI_ENABLED` value | Fails when the local environment enables AI |
| `tests/test_langchain_provider.py` collection error | Import error from the installed `langchain_core` version in the local venv; not investigated further |
| 29 deterministic + 2 flaky Playwright failures in other features | Listed in section 2 |

## 7. Other open points

- `ConfirmDialog` has no hook to control focus on close; the date focus relies on a 150 ms timeout.
- The StrictMode fix leaves the dry-run firing twice in dev. A `useQuery` keyed by the payload would be cleaner (proposed).
- `body-composition.spec.ts` deletes athlete 1's record from today in `beforeAll`/`afterAll`; under full parallelism `record-explanation` could open that record. It did not occur in these runs.
- Archived «Ficticio…» athletes remain in the e2e volume by design.

## 8. Illustrations

The four illustrations (`frontend/src/assets/anthropometry/{weight,standing_height,sitting_height,arm_span}.webp`,
with PNG copies in `backend/templates/documents/pdf/diagrams/img/anthro_*.png`) were generated
with Gemini in the owner's browser, using the skinfold illustration as style reference, and each
was approved by the owner before entering the repository. The privacy audit viewed all eight
files: faceless, no text or numbers, no EXIF/XMP/C2PA metadata.

## 9. Before calling the feature verified

1. Owner tablet check (T061) recorded in section 4.
2. Decide and apply P-1, or accept it in writing.
3. Run `pytest -m mysql` once against a `_test` database.
4. Decide the `AI_ENABLED` handling for `anthropometry-record-explanation.spec.ts` and rerun it.
5. Deploy, then run the post-deploy smoke.

## Follow-up 2026-09-29 (after the final gate)

- Privacy finding P-1 fixed: backend `notes` capped at 2000 characters (same as the frontend Zod), with a schema test.
- Flaky privacy test fixed (log timing fields excluded from the token scan). `tests/anthropometry` + `tests/test_athletes.py`: 254 passed, 6 consecutive runs.
- `lib/datetime` off-by-one **fixed** (was listed as out of scope): date-only strings (`YYYY-MM-DD`) are now anchored at 12:00 UTC in `toDate`, so every formatter shows the right calendar day in America/Bogota. Visible effect before the fix: the coach home tile «Próxima sesión» showed one day less (a session in 2 days read «Mañana»); `NextSessionTile.test.tsx` and `DashboardPage.test.tsx` had that wrong label encoded and were corrected. Regression test in `datetime.test.ts` fails on the old code. Full vitest 5122/5122, typecheck clean.
