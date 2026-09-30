# Privacy audit: feature 047 (IMDERTY monthly attendance sheet)

**Task**: T051 (`data-privacy-guard`)
**Date**: 2026-09-28
**Scope**: every new or changed backend and frontend file of feature 047, uncommitted on `main`.

- **Backend**: `models/imderty.py`, `models/athlete.py`, `models/__init__.py`, `schemas/imderty.py`, `routers/imderty*.py` (5 files), `routers/athletes.py`, `services/imderty/*` (8 modules), `services/audit.py`, `main.py`, the `448f7dfbca14` migration, `scripts/build_imderty_template.py`, `templates/documents/imderty/fo_gdd_057_v006.xlsx`, `tests/imderty/*`, `tests/test_audit_mysql.py`.
- **Frontend**: `api/imderty.ts`, `hooks/useImderty.ts`, `schemas/imderty.ts`, `components/imderty/*`, `routes/imderty/*`, `components/athletes/AthleteInfoCard.tsx`, `App.tsx`, `lib/navigation.ts` and the tests of each.
- **Also scanned**: `mockup.html` and the spec documents in this folder.

The owner's reference workbook was not opened. No production data was read.

```
PRIVACY AUDIT

Files reviewed: 71 (42 backend incl. template, migration, script and tests; 29 frontend incl. tests)
Findings: 0 critical, 1 high (fixed), 3 medium (1 fixed, 2 open recommendations), 4 low/info

Status: APPROVED (after the fixes below). The open items are recommendations or owner decisions, not blockers.
```

## Findings

### [HIGH, fixed] P-1: Over-long values could leak a minor's data into the error log

**Where**: `backend/app/schemas/imderty.py`: `ImdertyProfileUpdate`, plus `BarrioCreate`/`BarrioUpdate`, `ClubImdertySettingsUpdate` and `ImdertySheetHeader`.

**What happened**: no free-text field had a `max_length`, but the columns are sized: `document_number`/`phone` 20, `address` 200, `school` 150, `eps` and the surnames 100.

**How it leaks**: on MySQL in strict mode (the 8.4 default), a longer value fails at `db.flush()` with error 1406 "Data too long".

- Nothing catches that error, so `main.py::unhandled_exception_handler` logs it with `exc_info`.
- SQLAlchemy's error text includes `[SQL: ...]` and `[parameters: (...)]`, so the submitted document number, address, phone, EPS or surname of a minor would be written to the Render logs.
- This was checked with a fictitious value: `str(DataError(...))` prints the parameters verbatim.
- SQLite does not enforce `String(n)`, so the default lane could never catch it.

**Fix**:

- Every free-text field of the five schemas now has `Field(max_length=<column length>)`.
- The value is rejected before it reaches the database.
- The 422 comes from the app-wide validation handler, which drops `input`, `ctx` and `url`. The `string_too_long` message states only the limit.

**Tests**: `backend/tests/imderty/test_privacy_audit_047.py` has 12 tests.

- A structural test fails if any free-text field's `max_length` stops matching its column.
- For six profile fields and one settings field, the API returns 422, the response does not echo the value, and nothing is written.

**Still to check**: the real MySQL behaviour is covered by the reasoning above, not by a MySQL run (`pytest -m mysql` is deferred in this session).

### [MEDIUM, open, platform-wide] P-2: The database engine does not hide SQL parameters

**Where**: `backend/app/database.py` (not a feature-047 file).

**Problem**: `create_async_engine(...)` does not set `hide_parameters=True`. P-1 closes the reachable length path for feature 047, but any other database error during an IMDERTY write would still log the bound values. Examples: a lost connection mid-flush, or an `IntegrityError` race on `uq_parent_athlete_primary_contact_key` or on the sensitive-data primary key.

The same exposure exists for every feature that writes minors' data.

**Recommendation**:

- Set `hide_parameters=True` on the engine. SQLAlchemy then prints `[SQL parameters hidden due to hide_parameters=True]`.
- Debugging needs the statement text only.
- This is a one-line change to a shared file, so the owner or a platform task should apply it rather than feature 047.

### [MEDIUM, fixed] P-3: Erased sensitive values stayed in the in-memory query cache after withdrawal

**Where**: `frontend/src/hooks/useImderty.ts`, `useWithdrawSensitiveAuthorization`.

**Problem**: after a withdrawal (FR-007) the hook only *invalidated* `["imderty","sensitive-data",id]`.

- The last ethnicity, disability and victim values stayed in the TanStack in-memory cache until `gcTime`.
- The forced refetch then hit a 404.
- The values were never written to device storage: the `["imderty",…]` keys are not in `lib/persistAllowList.ts`, which is default-deny.

**Fix**: `queryClient.removeQueries(...)` for that key, then the profile invalidation as before. 81 IMDERTY frontend tests pass and `npm run typecheck` is clean.

### [MEDIUM, open, owner decision] P-4: Reads of the sensitive block are not audited

**Where**: `GET /api/athletes/{id}/sensitive-data` and `GET /api/athletes/{id}/imderty-profile`.

**Current state**: these reads are not recorded. This follows the platform rule from feature 041 (FR-005: plain page reads are not recorded; only exports and mutating GETs are). Spec 047 asks only for audited generations (FR-028), so this is **not a deviation**.

**Risk**: the three values are Ley 1581 "sensitive data" (ethnicity, disability, conflict victim). This is the strongest category the platform holds, and the audit rule for sensitive data says accesses should be traceable.

**Recommendation**: the owner decides whether `GET .../sensitive-data` becomes an audited read. It would be an `Audited` entry with `action=read`, no meta and no values. If yes, do it in a follow-up, because it changes the 041 audit contract.

### [LOW, open] P-5: The AUDIT_STRICT detector does not know the new tables

**Where**: `services/audit.py::_AUDIT_STRICT_TABLES`.

**Problem**: `athlete_imderty_profiles`, `athlete_sensitive_authorizations`, `athlete_sensitive_data`, `imderty_barrios` and `club_imderty_settings` are not listed.

Every write is audited explicitly today, and T038 verifies this. But the test-lane detector would not catch a future write that forgets `record_audit`.

**Why it stays open**: adding the tables is not a drop-in change. `clear_surname_confirmation` deliberately writes without its own audit row (the athlete `update` row already names `last_name`), so it would need an exemption. It is left as a recommendation.

### [LOW, open] P-6: Some fixture and mockup names look realistic

**Where**:

- `tests/imderty/test_rows.py`: "Ana Sofía", "Pérez Gómez", "Ramírez Soto".
- `tests/imderty/test_imderty_profile_api.py`: "Quintero Del Valle" (needed for the compound-particle split).
- `mockup.html`: "RAMÍREZ" / "GÓMEZ", "Juan D.".

**Assessment**:

- Nothing suggests they are real. The conftest states that every value is fictitious, and document numbers and phones are obvious placeholders (`1000000047`, `3000000000`, `CALLE FICTICIA`).
- The auditor cannot confirm there is no collision with the club roster without reading real data, which is forbidden.

**Recommendation**: the owner checks at a glance that none of these names matches a current rider, or they are renamed to the `Ficticio`/`Prueba` style used elsewhere in the suite.

### [LOW, open] P-7: The owner's local workbook path appears in a docstring

**Where**: `backend/app/services/imderty/barrios_seed.py` line 5 names `~/Downloads/DOC-20260921-WA0005.xlsx`. The same path is in `tasks.md`.

**Assessment**: this is a file name only. It has no minor's data and the file is not versioned. Deleting the path from the docstring when convenient is optional.

### [INFO] P-8: The exported file carries CRITICAL data by design

The official FO-GDD-057 format requires most of this data. The rest (the sensitive block) is written only under an active authorization.

**Contents**:

- Birth date (column E).
- Document type and number.
- Address, barrio and comuna.
- EPS and phone.
- The sensitive block (L/N/O), only under an active authorization.

**Controls verified**:

- The file is built in memory and never stored (FR-026).
- Access is limited to admin and to a coach of the club (403 for parent, athlete and foreign coach, all tested).
- The export audit row carries exactly `{document_kind, from_month, to_month, row_count, gap_count}`.
- The file name is `FO-GDD-057_asistencia_YYYY-MM_YYYY-MM.xlsx`, with no names.
- The third-party-sharing authorization is not a gate because the IMDERTY agreement covers sharing (FR-024, owner decision).

**Column M (sexual orientation)**:

- The template keeps the official column M header and the official orientation dropdown list. Both are part of the official format and its header counter.
- `workbook.py` forces M blank on every row, so the counter shows zero (spec edge case).

**Recommendation**:

- Once downloaded, the file is outside platform control. The coach runbook (`docs/22-…`) should tell the coach to send it only through the channel IMDERTY designates.
- The coach should delete local copies after sending.
- The coach should never fill column M by hand.

### [INFO] P-9: The frontend schema has no length limits

`frontend/src/schemas/imderty.ts` has no `.max()` matching the new backend limits. The backend guard is authoritative, so this is not a privacy defect. Adding `.max()` would give the coach an inline message instead of a generic 422 error.

## Checks that passed

| Area | Result |
|---|---|
| **Logs** | No `logger`, `print` or `console.*` in `services/imderty/*`, `routers/imderty*.py` or `components|routes|hooks|api` for IMDERTY. The 422 handler in `main.py` drops `input`/`ctx`/`url` app-wide and logs nothing. The unhandled handler logs only method, path and exception type (plus the traceback, see P-1/P-2). T038's end-to-end `caplog` scan passes. |
| **`HTTPException.detail`** | Every detail is a fixed Spanish string. `ReadinessTooLarge`/`SheetTooLarge` carry only a month and a count. `_parse_month_range` returns the validator's own message, never the input. Custom validator messages in `schemas/imderty.py` name the problem, never the value. |
| **Audit `meta` / `diff_json`** | Every `record_audit` call in feature 047 passes `changed_fields` only (names). The new entity types have no `VALUE_ALLOWLIST` entry, so no value reaches `diff_json`. The only `META_ALLOWLIST` additions are `from_month`, `to_month`, `row_count` and `gap_count`. Withdrawal uses `reason_code=withdrawn`. The `_IMDERTY` block covers all 9 write/export routes. |
| **Fixtures and file names** | The IDs are in the 47xx namespace. Names follow the `Ficticio`/`Acudiente` pattern (see P-6 for the exceptions), and addresses, EPS, documents and phones are obvious placeholders. The download file name carries months only. |
| **Parent projections** | `grep` across `backend/app` finds no reader of `AthleteImdertyProfile`, `AthleteSensitive*`, `primary_contact_key`, `document_number`, `eps`, `ethnicity`, `disability` or `conflict_victim` outside the IMDERTY modules. No schema serializes `primary_contact_key`. `test_parent_view_has_no_imderty_keys` passes. Every IMDERTY route returns 403 to parent and athlete (tested). `AthleteInfoCard` renders the IMDERTY card only for admin and coach. |
| **Browser cache persistence** | All keys are under `["imderty", …]`, and none is in `persistAllowList.ts`. There is no `localStorage` or `sessionStorage` use. The only URL additions are `/imderty/planilla`, `/imderty/barrios` and the `#imderty-profile` hash, none of which identifies anyone. `autoComplete="off"` is set on surnames, document number, address, school, EPS and phone. |
| **Committed template** | It has 13 sheets (12 months plus `SECTOR`). Month sheets have zero literal values in rows 24 and below; only the F/R/AZ:BB formulas remain. The header value cells are empty. `sharedStrings` holds only official labels and the 82 barrios. `docProps` `creator`/`lastModifiedBy` are empty. There are no comments, external links, `customXml`, `printerSettings` or `calcChain`. The only image is the IMDERTY logo. `build_imderty_template.py` never prints a source cell value; its errors name only cell references. |
| **No sexual orientation** | There is no enum, column, field, label or import path in `models/imderty.py`, `schemas/imderty.py`, the migration, `services/imderty/*`, the frontend schema or any component. `workbook.py` forces column M to `None`. The `TestNoSexualOrientationField` tests pass. |
| **AI isolation** | No AI, race or newsletter module imports or references IMDERTY (`TestNoForbiddenImports`, AST and grep sweeps). |

## Commands run

- `cd backend && PYTHONPATH=. DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m pytest tests/imderty -q`: 291 passed, 1 skipped (includes the 12 new P-1 tests).
- Full default lane, `... -m pytest -q --ignore=tests/test_langchain_provider.py --ignore=tests/evals`: 6651 passed, 37 skipped, 1 failed. The failure is the known local-env `test_growth_summary_latest_analysis.py::test_null_when_ai_disabled` (local `.env` enables AI). `tests/evals` was excluded because `test_anthropometry_analyst_eval.py::test_golden_case[002]` hangs at 0 % CPU with the local AI configuration; that is unrelated to feature 047 and is **deferred**. `tests/test_langchain_provider.py` is excluded because of the known collection error (outdated `langchain_core` in the local venv).
- `cd frontend && npx vitest run src/components/imderty src/routes/imderty src/schemas/imderty.schema.test.ts`: 9 files, 81 tests passed.
- `cd frontend && npm run typecheck`: clean.
- `pytest -m mysql`: **deferred**, no MySQL in this session. P-1 on real MySQL is inferred, not run.
