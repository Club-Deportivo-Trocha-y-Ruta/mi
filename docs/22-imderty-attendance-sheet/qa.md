# IMDERTY monthly attendance sheet — QA plan

## Test plan

| Area | Coverage | Location |
|---|---|---|
| Attendance grid | Every mapping in research R4 (precedence A>E>F, linked-event exclusion, multi-day events, activity windows, short months, blank days) | `backend/tests/imderty/` |
| Workbook writer | Reopens with `openpyxl` without errors; table column names equal the row-23 headers; barrio validation points at `SECTOR`; no sexual-orientation value present; sensitive cells blank without authorization; short-month trailing day columns carry only the weekday abbreviation and stay blank | `backend/tests/imderty/test_workbook.py` |
| Template privacy | The committed template (`fo_gdd_057_v006.xlsx`) has no non-formula value in rows ≥ 24 and no header value | `backend/tests/imderty/` |
| RBAC | 403 for parent, athlete, and a coach of another club; 200 for admin/coach of the athlete's own club | `backend/tests/imderty/` |
| Parent view | `AthleteParentView` responses carry none of the new keys | `backend/tests/imderty/`, `backend/tests/test_audit_mysql.py` region |
| Structural / privacy isolation | No new IMDERTY model is imported by `app/services/ai/**`, `app/services/llm/**`, `app/services/race/**`, or newsletter/report modules | `backend/tests/imderty/` |
| Sensitive-data lifecycle | Authorization → defaults set → values recorded → withdrawal deletes the row and its audit entry carries no values | `backend/tests/imderty/` |
| No-echo / audit privacy | `TestFeatureFlowNeverLeaksValues` runs the full flow and scans application logs (`caplog`) and every `audit_log` column for leaked field values, after first confirming the markers are actually present in the sheet | `backend/tests/imderty/test_imderty_privacy.py` |
| 422 handling | Request-validation errors strip `input`/`ctx`/`url` app-wide (not just for this feature) | `backend/tests/` (main app-level handler) |
| Migration | `alembic upgrade`/`downgrade` round trip; seeds exactly 82 barrios | `backend/tests/imderty/test_barrios_seed.py`, `pytest -m mysql` |
| Frontend components | `BarrioCombobox`, `HeaderOverridesForm`, `ImdertyProfileCard`, `ImdertyProfileForm`, `PrimaryContactSelect`, `ReadinessPanel`, `SensitiveDataCard`, `SurnameSplitConfirm`; jest-axe zero violations, including heading order on `SensitiveDataCard` and `ImdertyProfileCard` error/locked states | `frontend/src/components/imderty/*.test.tsx` |
| Frontend routes | `BarrioCatalogPage`, `ImdertySheetPage`; anchor scroll to `#imderty-profile` from `ReadinessPanel` links | `frontend/src/routes/imderty/*.test.tsx`, `frontend/src/components/imderty/anchors.ts` |
| Schema | `imderty.schema.test.ts` including `effective_phone_source` accepting `first_guardian`; `SheetRequest` month format `YYYY-MM` (zero-padded, ASCII digits only) | `frontend/src/schemas/imderty.schema.test.ts`, `backend/tests/imderty/` |
| Audit registry completeness | `_IMDERTY` block in `AUDITED_ROUTES` covers the 9 write/export routes | `backend/tests/test_audit_mysql.py` |
| Manual end-to-end | Full quickstart flow (profile fill, sensitive-data lifecycle, club settings, single-month and period downloads, 360 px phone pass) | `specs/047-imderty-attendance-sheet/quickstart.md` |

## Fixtures

- All test athletes and guardians use unmistakably fictitious names, matching the club's
  existing fixture convention (Ley 1581).
- The owner's reference workbook is never used in tests and never copied into the repo; only
  the sanitized shipped template (`backend/templates/documents/imderty/fo_gdd_057_v006.xlsx`)
  and synthetic month data generated through the service layer are used.
- The barrio catalog fixture is the 82-entry seed (see `runbook.md` §1 and
  `specs/047-imderty-attendance-sheet/research.md` R6), not a subset.

## Target coverage

- Default (offline) lane: `backend/tests/imderty/` and the frontend `imderty` test files pass
  on every run; this is the CI-blocking bar for the feature.
- `pytest -m mysql`: migration upgrade/downgrade and the 82-barrio seed, against real MySQL.
- Manual/E2E: the quickstart's desktop and 360 px phone passes, plus opening the downloaded
  file in Excel or LibreOffice with no repair prompt.

## Deferred lanes

| Lane | Status (2026-09-28) | Reason | Owner action needed |
|---|---|---|---|
| Playwright `frontend/e2e/imderty-sheet.spec.ts` (T052) | **Ran, passed** | 2/2 on the isolated e2e stack (backend :8001, MySQL :3307), passing both fresh and on an idempotent rerun: the desktop flow (gap → fill profile → gap clears → download `FO-GDD-057_asistencia_*.xlsx`) and a 375 px readiness-panel card check | None. Re-run it before release if the UI changes. |
| `pytest -m mysql tests/imderty/test_migration_imderty.py` (T055) | **Ran, passed** | 1 passed on local MySQL 8.4 (docker compose) after two test-only fixes (explicit `user_id`; CHECK violation raises `OperationalError` 3819 on MySQL) | None. The real-MySQL check of the P-1 `max_length`/strict-mode path is covered only by the offline 422 tests. |
| Quickstart §3 manual end-to-end, including the 360 px phone pass (§3.7) | **Deferred** | Needs an interactive session with a running stack, a browser/phone and a spreadsheet app. It was not run at the T056 gate. | Walk through quickstart §3 on demo data (never the production DB). |
| Open the file in Microsoft Excel with no repair prompt (§3.5) | **Deferred** | Needs interactive Excel. LibreOffice headless opened and recalculated the synthetic file without errors. | Open one generated month in Excel during the owner demo. |
| Post-deploy (T057): `/health`, `GET /api/clubs/{id}/imderty-settings`, SC-004 comparison of August 2026, SC-003 IMDERTY acceptance | **Deferred** | Needs merge and deploy. | Owner, after deploy. Record the acceptance result here. |
| Program marks for MASIFICACIÓN / COMPETENCIA (research R3 addendum) | **Decided** | Owner decision 2026-09-29: leave them empty (the format has no "X" cell for these two group headings) | None. To mark them later, map the program in `PROGRAM_HEADING_CELLS`. |
| Pre-existing local-env failures | **Known, unrelated** | `tests/test_langchain_provider.py` collection error (outdated `langchain_core`), `test_growth_summary_latest_analysis.py::test_null_when_ai_disabled` (local `.env` enables AI), and `tests/evals` golden_case[002] hanging with the local AI config | Refresh the venv and isolate AI settings in those tests (outside 047). |
