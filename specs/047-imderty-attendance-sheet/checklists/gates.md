# Feature 047: quality gates

## T013: Phase 2 gate (2026-09-28)

| # | Command | Result | Notes |
|---|---------|--------|-------|
| 1 | `cd backend && python -m pytest tests/imderty -q` | PASS | 54 passed, 1 skipped (skip = the `mysql`-marked migration test) |
| 2 | `cd backend && ruff check` (feature files + touched shared files) | PASS | 0 findings in 047 files. The repo-wide `ruff check` reports 360 findings, all of them pre-existing. The only one in a touched file is the unused `ParentInvite` import in `app/models/athlete.py`, which is also present at HEAD. |
| 3 | `cd frontend && npm run typecheck` | PASS | `tsc --noEmit` is clean |
| 4 | `alembic upgrade head` on SQLite through the test setup | PASS | `test_migration_imderty.py`: the 448f7dfbca14 migration runs upgrade → downgrade → upgrade on SQLite, and `compare_metadata` against the models returns `[]`. `alembic heads` gives exactly one head, `448f7dfbca14`. |
| 5 | `cd backend && python -m pytest -q` (full default lane) | PASS (after fixes) | First run: collection error in `tests/test_langchain_provider.py`, then 3 failures. See "Blockers fixed" and "Pre-existing, not 047" below. The final run (ignoring the langchain file) was 6449 passed, 64 skipped, 3 failed. Two of those failures were fixed and re-verified. The third depends on the environment. |
| 6 | `npx vitest run` nav tests touched by T012 | PASS | 112 passed |
| 7 | `pytest -m mysql tests/imderty/test_migration_imderty.py` | NOT RUN | No MySQL credentials available in this session. Deferred to the real-infra gate. |

### Blockers fixed at this gate

- `app/services/audit.py`: T002 added 6 `AuditEntityType` values and `AuditDocumentKind.imderty_attendance_xlsx` without es-CO labels. This broke `tests/services/test_audit_sentences.py` (2 tests). Labels were added to `AUDIT_ENTITY_LABELS` and `AUDIT_DOCUMENT_LABELS`.
- `app/routers/imderty.py::require_athlete_staff` queried `Athlete` without `deleted_at IS NULL`. This broke `tests/test_archive_scope_gate.py`. It now returns 404 for archived athletes, which matches the coach behavior in `athletes.py`.
- `tests/test_audit_mysql.py::CURRENT_HEAD` was bumped from `be4595de1ad2` to `448f7dfbca14` because migration 047 is the new single head.

### Pre-existing, not 047

- `tests/test_langchain_provider.py` fails at collection: `ModelError` cannot be imported from the installed `langchain_core` 1.4.9, which was installed 2026-07-14. This is a local venv version drift, and the file is untouched by 047.
- `tests/test_growth_summary_latest_analysis.py::test_null_when_ai_disabled` fails only when the local `backend/.venv` + `.env` resolves `settings.ai_enabled=True`. The same test passes at HEAD in a clean worktree without `.env`. The failure depends on the environment and is unrelated to 047.

## Stories gate (W3): T022 + T038 + T046 (2026-09-28)

All commands ran from the repo root's `backend/` (`PYTHONPATH=. DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m pytest …`) or `frontend/`. Only fictitious data was used, and the owner's workbook was not opened.

| # | Command | Result | Notes |
|---|---------|--------|-------|
| 1 | `python -m pytest tests/imderty -q` | PASS | 276 passed, 1 skipped. The skip is the `mysql`-marked migration test. |
| 2 | `python -m pytest -q --ignore=tests/test_langchain_provider.py` (full default lane) | PASS (after fix) | First run: 6681 passed, 64 skipped, 2 failed. (a) `test_archive_scope_gate.py::test_every_athlete_query_filters_or_is_exempt` flagged `services/imderty/profile.py::set_primary_contact`. This is a substring false positive: `ParentAthlete.id.in_(` matches `Athlete.id.in_(`. It was introduced in W2 and was fixed here with a keyed UPDATE per link (at most one row, because the column is UNIQUE). A re-run of the gate plus `tests/imderty` passed. (b) `test_growth_summary_latest_analysis.py::test_null_when_ai_disabled`: pre-existing and environment-dependent (local `.env` enables AI), unrelated to 047. |
| 3 | `python -m pytest tests/test_audit_coverage.py tests/test_archive_scope_gate.py tests/services/test_audit_sentences.py tests/services/test_audit_helper.py tests/test_audit_privacy.py -q` | PASS | 276 passed. This includes T4.1 registry completeness (the 9 new IMDERTY mutating routes are now in `AUDITED_ROUTES`) and T4.4a static reachability for each of them. |
| 4 | `ruff check` on the 047 backend files plus `app/services/audit.py` and `app/main.py` | PASS | All checks passed |
| 5 | `npm run typecheck` | PASS | `tsc --noEmit` clean |
| 6 | `npx vitest run src/schemas/imderty.schema.test.ts src/routes/imderty src/components/imderty src/components/athletes` | PASS | 78 files, 956 tests |
| 7 | Synthetic August 2026 through the service layer (`upsert_profile`, `create_authorization`, `update_sensitive_data`, `active_athletes_in_range`, `build_attendance_grid`, `load_authorized_sensitive_data`, `build_rows`, `build_sheet`). The file was written to `/tmp`, reopened with openpyxl, then deleted. | PASS | 14/14 checks passed: table column names == row-23 headers and unique; sheets `AGOSTO, SECTOR`; marks A/E/F in the expected day columns; L/N/O filled for the authorized athlete and blank for the others; M blank; profile columns G/H/Q/T; `OTRO MUNICIPIO` in Q and as the last SECTOR row with zone `=""`; validation covers it; program marks `E18=X` and `MASIFICACIÓN X`; `fullCalcOnLoad`; `I7` is the month. |
| 8 | The same file opened with LibreOffice headless (`soffice --convert-to csv`) | PASS | Opened and recalculated with no error. EDAD (F) was computed, COMUNA (R) resolved for a catalog barrio and stayed **blank** for `OTRO MUNICIPIO`, and the AZ:BB counters matched the marks. The CSVs were deleted. |
| 9 | Opening in Microsoft Excel with no repair prompt | DEFERRED | Needs an interactive Excel session. It stays in quickstart §3.5 for the owner/demo. |
| 10 | `pytest -m mysql tests/imderty/test_migration_imderty.py` | DEFERRED | No MySQL in this session |

### Fixes applied at this gate

- **Sensitive columns never filled (bug)**: `routers/imderty_sheet.py` now loads `load_authorized_sensitive_data` for each month and passes it to `build_rows`. API tests: an authorized athlete gets L/N/O, the others stay blank, a withdrawal blanks the columns, and M is always blank.
- **Export audit contract**: `META_ALLOWLIST` gained `from_month`, `to_month`, `row_count` and `gap_count`. The sheet POST writes exactly `{document_kind, from_month, to_month, row_count, gap_count}`. `row_count` counts rows across all month sheets. `gap_count` is the number of athletes with at least one readiness gap.
- **Withdrawal reason**: added `AuditReasonCode.withdrawn` (label «Autorización retirada»). It is used by `withdraw_authorization`.
- **Route registry**: a new `_IMDERTY` block in `AUDITED_ROUTES` lists the 9 write/export routes.
- **422 echo**: `app/main.py` has an app-wide `RequestValidationError` handler that drops `input`, `ctx` and `url` from every error entry. The full default lane stayed green.
- **Strict month format**: `SheetRequest` enforces `^\d{4}-(0[1-9]|1[0-2])$` with `re.ASCII`, which also rejects fullwidth digits.
- **Program headings**: `MASIFICACIÓN X` / `COMPETENCIA X` (research.md R3 addendum, reversible).
- **SECTOR**: `OTRO MUNICIPIO` is now the last row, with zone `=""`.
- **Frontend**:
  - `effective_phone_source` accepts `first_guardian`.
  - `SensitiveDataCard` and `ImdertyProfileCard` no longer use `AlertTitle` (h5) under the h3. The strict axe locked-state cases pass.
  - The card has `id="imderty-profile"` and scrolls into view when the hash is present.
  - The readiness links go to `/athletes/{id}#imderty-profile`.
- **Docs**: the barrio count is 82, the SECTOR/`OTRO MUNICIPIO` behavior is documented in R6, and the audit meta keys are documented in R8. `test_barrios_seed.py` now asserts `== 82`.

### T038 privacy scans

`tests/imderty/test_imderty_privacy.py::TestFeatureFlowNeverLeaksValues` runs the whole admin/coach flow: barrio, a rejected PUT, profile, primary contact, authorization, sensitive values, settings, sheet download and withdrawal. It asserts:

- the downloaded sheet does carry every marker value, so the scan is not vacuous;
- no application log record contains any of them, in message or `extra`;
- no `audit_log` column in any row (`changed_fields`, `diff_json`, `meta_json`, `reason_code`) contains any of them;
- the IMDERTY rows have `diff_json = NULL`;
- the export meta has exactly the contract keys;
- the withdrawal carries `reason_code = withdrawn`.

## Final gate (W5) — T056, 2026-09-28

| # | Command | Result | Notes |
|---|---------|--------|-------|
| 1 | `cd backend && python -m pytest -q` (literal T056 command) | FAIL (pre-existing, env) | Stops at collection: `tests/test_langchain_provider.py` cannot import `langchain_core.exceptions.ModelError` because the local venv's `langchain_core` is outdated. This is unrelated to 047. |
| 2 | `python -m pytest -q --ignore=tests/test_langchain_provider.py --ignore=tests/evals` (full default lane) | PASS except 1 known env failure | 6651 passed, 37 skipped, 1 failed in 5:16. The failure is `test_growth_summary_latest_analysis.py::test_null_when_ai_disabled`: the local `.env` enables AI, so it is pre-existing and unrelated. `tests/evals` is excluded because `test_anthropometry_analyst_eval.py::test_golden_case[002]` hangs with the local AI config (unrelated). Includes `tests/imderty` (with the T053 performance tests and the T051 `test_privacy_audit_047.py`). |
| 3 | `ruff check` on the 047 backend files (models, routers, schemas, services, migration, script, `tests/imderty`) plus the touched shared files (`app/main.py`, `app/services/audit.py`, `app/models/athlete.py`, `app/models/__init__.py`, `app/routers/athletes.py`) | PASS for 047 code | 2 F401 findings, both already present at `HEAD`: `app/models/athlete.py` (`ParentInvite`) and `app/routers/athletes.py` (`parent_athlete_ids`). They were not introduced by 047 and are left as-is. A repo-wide `ruff check` reports 360 findings. That is the historical baseline, not 047. |
| 4 | `cd frontend && npm run typecheck` | PASS | `tsc --noEmit` clean |
| 5 | `npm test` (full vitest) | PASS | 415 files, 5025 tests |
| 6 | `npm run build` + `/imderty` chunk budget (≤ 150 KB gzipped) | PASS | `ImdertySheetPage` 4.00 KB gz, plus the shared `useImderty` 2.85 KB gz, for about 6.9 KB. `BarrioCatalogPage` is 4.86 KB gz. All are far under 150 KB. |
| 7 | Playwright `e2e/imderty-sheet.spec.ts` (T052) on the isolated e2e stack | PASS (in T052) | 2/2 tests passed twice, fresh and rerun: the desktop flow and a 375 px readiness-panel check. It was not re-run at this gate. |
| 8 | `pytest -m mysql tests/imderty/test_migration_imderty.py` (T055) on local MySQL 8.4 | PASS (in T055) | 1 passed after two test-only fixes (explicit `user_id`; MySQL raises `OperationalError` 3819 for CHECK violations). It was not re-run at this gate. |
| 9 | Quickstart §3 manual flow, including the 360 px check of §3.7 | DEFERRED | It needs an interactive session with a running stack, a real browser/phone and Excel. It was **not** run at this gate. Part of it is covered by #7, but that does not replace it. |
| 10 | Opening in Microsoft Excel with no repair prompt (quickstart §3.5) | DEFERRED | Owner/demo session. LibreOffice headless opened and recalculated the file at the stories gate. |
| 11 | Post-deploy (T057): `/health`, authenticated `GET imderty-settings`, SC-004 comparison, SC-003 acceptance | DEFERRED | Owner, after merge and deploy. |
| 12 | `data-privacy-guard` audit (T051) | APPROVED | See `privacy-audit.md`: P-1 (HIGH) and P-3 (MEDIUM) are fixed. P-2, P-4 to P-9 are open recommendations and none of them block. |

**Verdict:** the offline lanes are green for 047. The only failures are the two pre-existing local-env issues. The feature is **not fully verified**: rows 9–11 remain deferred.
