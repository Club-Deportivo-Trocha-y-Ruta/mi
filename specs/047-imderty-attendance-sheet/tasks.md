# Tasks: IMDERTY monthly attendance sheet (official format FO-GDD-057 v006)

**Input**: Design documents from `specs/047-imderty-attendance-sheet/`:
- `plan.md`;
- `spec.md` (US1–US4, FR-001…FR-029);
- `research.md` (R1–R11);
- `data-model.md`;
- `contracts/api.md`;
- `quickstart.md`.

**Tests**: REQUIRED (constitution Principle II, non-negotiable). Test tasks are listed before the implementation they cover; write them first and watch them fail.

**Branch / git**: everything on `main`, no feature branch, and **no commits** by agents (owner decision 2026-09-28). No `git stash`, `git clean` or destructive git in subagents; use a worktree to compare with HEAD.

**Privacy (blocking)**:
- All fixtures are synthetic.
- Never write a real minor's name, birth date, document number, address, EPS, phone or sensitive value in code, tests, logs, prompts or docs.
- The owner's reference workbook `~/Downloads/DOC-20260921-WA0005.xlsx` is **read only where a task says so**, and only for the parts named there. It is never copied into the repo, and its participant rows are never printed.

**Responsive**: every screen is desktop-primary and adapts to 768 px and 360 px as in the plan's layout table (constitution 1.4.0, Principle III).

## Format: `[ID] [P?] [Story] Description — agent · model · effort`

- **[P]**: the task can run in parallel (different files, no dependency on an unfinished task).
- **[Story]**: US1…US4, used in story phases only.
- **Trailing annotation** (owner request 2026-09-28: "asignando a agentes sonnet y opus según el caso"):
  - `agent`: a project agent from `.claude/agents/`;
  - `model`: `sonnet` for bounded, contract-driven implementation, content and tests; `opus` for data model and migration, the attendance-grid rules, the workbook writer and template builder, the privacy audit and integration gates;
  - `effort`: a hint (`low` / `medium` / `high`). The orchestrator may raise it when a task fails its first attempt.
- **Delegation prompts** follow Anthropic's prompting best practices (owner request):
  - state the context and *why*;
  - name the exact files to read and to own;
  - quote the normative constraints;
  - define the output and the "done" check.

## Path Conventions

The backend lives under `backend/` (`app/…`, `alembic/…`, `templates/…`, `scripts/…`, `tests/…`) and the frontend under `frontend/` (`src/…`, `e2e/…`). All paths below are repository-relative.

---

## Phase 1: Setup (dependency, audit catalogue, public reference data)

- [X] T001 [P] Add `openpyxl>=3.1.5` to `backend/requirements.txt` (next to `docxtpl`) and install it in `backend/.venv`. Confirm `python -c "import openpyxl"` works. Add nothing to the frontend — devops-engineer · sonnet · low
- [X] T002 [P] In `backend/app/services/audit.py`:
  - add the `AuditEntityType` values `athlete_imderty_profile`, `athlete_sensitive_authorization`, `athlete_sensitive_data`, `imderty_barrio`, `club_imderty_settings` and `imderty_attendance_sheet`;
  - add `AuditDocumentKind.imderty_attendance_xlsx`;
  - keep the `VALUE_ALLOWLIST` untouched, so no new field values ever enter `diff_json`.

  — fastapi-architect · sonnet · low
- [X] T003 [P] Create `backend/app/services/imderty/__init__.py` and `backend/app/services/imderty/barrios_seed.py`.
  - The seed defines `BARRIOS_YUMBO: tuple[tuple[str, str], ...]`, the 84 `(name, zone)` pairs from the **`SECTOR` sheet only** of the owner's workbook. Read columns A–B of that one sheet with openpyxl; never open the month sheets.
  - Names are upper case with diacritics kept. Zone is one of `"1"`,`"2"`,`"3"`,`"4"`,`"ZONA NORTE"`,`"ZONA CENTRO"`,`"ZONA SUR"`. Collapse duplicate spellings only if both map to the same zone, and list any that do not in a comment.
  - Add `backend/tests/imderty/test_barrios_seed.py`, asserting uniqueness, valid zones and a count in the range 80–84 (report the exact number).

  — data-analyst · sonnet · medium

---

## Phase 2: Foundational (blocking prerequisites)

**⚠️ CRITICAL**: no user-story work starts before this phase is complete and `python -m pytest`, `ruff check` and `npm run typecheck` are green.

- [X] T004 Create `backend/app/models/imderty.py` exactly per `data-model.md`:
  - **Enums** (with `values_callable`): `ImdertyDocumentType`, `ImdertyGrade`, `ImdertyEthnicity`, `ImdertyDisability`, `ImdertyYesNo` and `ImdertyProgram`, plus a label map to the official sheet text.
  - **`AthleteImdertyProfile`** (`athlete_id` is both PK and FK with `ondelete=CASCADE`):
    - `first_surname`/`second_surname` String(100) NULL;
    - `surname_split_confirmed_at` DateTime NULL, `surname_split_confirmed_by_user_id` FK users NULL;
    - `document_type` NULL, `document_number` String(20) NULL;
    - `address` String(200) NULL;
    - `barrio_id` FK `imderty_barrios.id` NULL `ondelete=RESTRICT`, `other_municipality` Boolean default false, with CHECK `NOT (other_municipality AND barrio_id IS NOT NULL)`;
    - `school` String(150) NULL, `grade` NULL, `eps` String(100) NULL, `phone` String(20) NULL.
  - **`AthleteSensitiveAuthorization`**:
    - `id`, `athlete_id` FK CASCADE, `guardian_user_id` FK users;
    - `authorized_on` Date, `recorded_by_user_id`, `recorded_at`;
    - `withdrawn_at` NULL, `withdrawn_by_user_id` NULL;
    - `active_key` Integer NULL **UNIQUE**.
  - **`AthleteSensitiveData`**:
    - `athlete_id` PK/FK CASCADE, `authorization_id` FK;
    - `ethnicity` NOT NULL, `disability` NOT NULL, `conflict_victim` NULL.
  - **`ImdertyBarrio`**: `id`, `name` String(120) **UNIQUE**, `zone` String(20) with CHECK on the 7 values, `is_active` default true.
  - **`ClubImdertySettings`**:
    - `club_id` PK/FK CASCADE;
    - `contractor_name`/`venue` String(200) NULL, `training_days`/`schedule` String(120) NULL;
    - `programs` JSON list.
  - **Shared rules**: timestamps, and `UpdatedByMixin` on editable tables. There is **no sexual-orientation column or enum anywhere**.
  - **`ParentAthlete`**: add `primary_contact_key` Integer NULL **UNIQUE** in `backend/app/models/athlete.py`.
  - Export everything in `backend/app/models/__init__.py`.

  — database-architect · opus · high
- [X] T005 Write the Alembic revision `backend/alembic/versions/<rev>_imderty_attendance_sheet.py`:
  - Run `alembic heads` first, expect exactly one head (`be4595de1ad2` on 2026-09-28), and use it as the parent.
  - Create the 5 tables with their constraints and unique indexes.
  - Add `parent_athlete.primary_contact_key` with its unique index (use `batch_alter_table` for SQLite compatibility).
  - Seed `imderty_barrios` from `app/services/imderty/barrios_seed.py`, copying the literal list into the migration so it stays frozen.
  - `downgrade()` drops the column, the seed and the tables in reverse order.

  — database-architect · opus · high
- [X] T006 [P] Write `backend/tests/imderty/test_migration_imderty.py` (`@pytest.mark.mysql`): upgrade → seed count equals `len(BARRIOS_YUMBO)` → the unique `active_key`/`primary_contact_key` indexes accept several NULLs and reject a duplicate value → downgrade leaves no table or column behind — qa-engineer · sonnet · medium
- [X] T007 [P] Create `backend/app/schemas/imderty.py` (Pydantic v2) mirroring `contracts/api.md`:
  - `ImdertyProfileRead/Update` (with `confirm_surname_split`), `PrimaryContactUpdate`, `SensitiveAuthorizationCreate/Read`, `SensitiveDataRead/Update`, `BarrioRead/Create/Update`, `ClubImdertySettingsRead/Update`, `SheetRequest` (`from`/`to` as `YYYY-MM`, optional `header`, `save_header_as_default`), `ReadinessRead`.
  - Validators: digits only for `rc`/`ti`/`cc`; `barrio_id` and `other_municipality` exclusive; `authorized_on` not in the future; month range ≤ 12 and `to >= from`.
  - Error messages must never echo field values.

  — fastapi-architect · sonnet · medium
- [X] T008 Write `backend/scripts/build_imderty_template.py` (dev-only CLI: `python scripts/build_imderty_template.py <owner_workbook.xlsx>`) and run it to produce `backend/templates/documents/imderty/fo_gdd_057_v006.xlsx` per research R2:
  - Take the `AGOSTO` sheet as the base and clear every value in rows 24–504 across all columns, keeping formulas: `F` = `DATEDIF`, `R` = `VLOOKUP`, `AZ:BB` = `COUNTIF`.
  - Clear the header values `D7`, `D8`, `D9`, `D10`, `I7` and every "X" program mark. Keep labels, styles, merges, validations and the logo.
  - At the XML level, clone the base into 12 month sheets `ENERO`…`DICIEMBRE`:
    - give each a unique table `name`/`displayName` (`TablaEnero`…) and a unique table id;
    - rewrite each sheet's COUNTIFS structured references;
    - duplicate the drawing, image rels and content types.
  - Rebuild `SECTOR` from `BARRIOS_YUMBO`.
  - The script **never prints cell values** from the source, and exits non-zero if it finds any non-formula value in rows ≥ 24 of the output.
  - Verify the output opens with openpyxl and in LibreOffice (if available) without a repair prompt.

  — data-analyst · opus · high
- [X] T009 [P] Write `backend/tests/imderty/test_template_sanitized.py` over the committed template. It asserts:
  - the 12 month sheets plus `SECTOR` exist in calendar order;
  - rows ≥ 24 hold only formulas or blanks;
  - `D7`–`D10` and `I7` are blank, and there are no "X" marks;
  - the table names are unique;
  - the day header cells equal their table column names;
  - `C3`/`I3` say `FO-GDD-057` and `I4` says `006`.

  — qa-engineer · sonnet · medium
- [X] T010 Create `backend/app/routers/imderty.py` with shared dependencies and an aggregate `router` that includes four sub-routers, each created here as an empty `APIRouter` stub so stories own disjoint files (implementation-time decision, 2026-09-28): `backend/app/routers/imderty_profile.py` (profile, primary contact, sensitive), `imderty_barrios.py`, `imderty_settings.py` and `imderty_sheet.py` (sheet + readiness). Mount the aggregate in `backend/app/main.py` under `/api`. Add no business routes yet.
  - **`require_athlete_staff(athlete_id)`**: admin, or a coach whose `_coach_club_ids` contains the athlete's club; 403 otherwise, 404 for an unknown athlete.
  - **`require_club_staff(club_id)`**: same pattern for a club.
  - **`require_admin`**.
  - Follow `backend/app/routers/athletes.py`. Add `backend/tests/imderty/conftest.py` with synthetic fixtures: one club, a second club, admin, coach, foreign coach, a parent with 2 athletes, and one athlete with two guardians.

  — fastapi-architect · sonnet · medium
- [X] T011 [P] Write `backend/tests/imderty/test_imderty_privacy.py`:
  1. **AST/grep sweep**: no module under `app/services/ai/`, `app/services/llm/`, `app/services/race/`, `app/services/notification/` or `app/services/training/newsletter*` imports `app.models.imderty` or `app.services.imderty`.
  2. **Parent view**: a parent `GET /api/athletes/{id}` response contains none of the new keys (`document_number`, `eps`, `barrio`, `ethnicity`, `disability`, `conflict_victim`, `first_surname`, …).
  3. **No sexual orientation**: the strings `orientation`/`orientacion` appear in no model, schema or column of this feature.

  Extend this file in later phases with log and audit assertions — qa-engineer · sonnet · medium
- [X] T012 [P] Add the frontend foundations:
  - `frontend/src/api/imderty.ts`: typed axios calls for every route in `contracts/api.md`; the sheet download uses `responseType: "blob"`.
  - `frontend/src/schemas/imderty.ts`: Zod enums, and Spanish display labels with full diacritics for every enum (document types, grades, ethnicities, disabilities, programs).
  - `frontend/src/hooks/useImderty.ts`: TanStack Query hooks and mutations with query keys under `["imderty", …]`.
  - Route registration: register the lazy routes `/imderty/planilla` (admin/coach) and `/imderty/barrios` (admin) and the «Planilla IMDERTY» nav entry now, pointing at minimal placeholder pages `frontend/src/routes/imderty/ImdertySheetPage.tsx` and `BarrioCatalogPage.tsx` that later tasks replace. Later tasks never touch the router or nav files.
  - Do **not** add these keys to `src/lib/persistAllowList.ts`, so minors' data is never persisted in the browser cache.

  — react-ui-engineer · sonnet · medium
- [X] T013 Phase 2 gate. Run the following and record pass/fail in `specs/047-imderty-attendance-sheet/checklists/gates.md`:
  - `cd backend && python -m pytest tests/imderty -q && ruff check`;
  - `cd frontend && npm run typecheck`;
  - `alembic upgrade head` on SQLite through the test setup.

  Fix blockers before any story starts — engineering-lead · opus · medium

---

## Phase 3: User Story 1 — Generate the month's sheet from recorded attendance (Priority: P1) 🎯 MVP

**Goal**: admin or coach downloads a single month in the official format, with day marks, totals and counters derived from recorded attendance. Only the data the platform already holds is required (name, birth date, sex).

**Independent Test**: in a synthetic club, create athletes with only name, birth date and sex. Record a month of executed and cancelled sessions, one outing (two days, partial audience), one joint training linked to a session, and one competition with a result and an attended-only athlete. Generate the month and verify every row, day mark, total, header and counter; identity columns without data stay blank.

### Tests for User Story 1

- [X] T014 [P] [US1] Write `backend/tests/imderty/test_attendance_grid.py` (unit plus DB, SQLite). One test per rule in research R4/R5:
  - **Session mapping**: presente/tarde→A, justificado/lesionado→E, ausente→F.
  - **Sessions excluded**: archived `session_attendance` rows, and planned or cancelled sessions.
  - **Events**: `club_event`/`group_training` `actual_status` attended/excused/no_show → A/E/F; `unknown` → blank. Cancelled events are ignored.
  - **Double counting**: an event linked to a `TrainingSession` is not counted twice.
  - **Competitions**: a result alone → A; attended with no result → A; excused → E; no_show → F; neither → blank.
  - **Excluded event types**: `personal_training`, `rest_day`, `birthday`, `training_session`.
  - **Per-cell rules**: precedence A>E>F on the same day; a multi-day event marks each in-month day.
  - **Active window**: `club_join_date` after day 10 → earlier days blank; `deleted_at` on day 20 → later days blank; an athlete inactive the whole month is excluded.
  - **Dates**: naive `start_at` at 23:30 stays on its local date.

  — qa-engineer · sonnet · high
- [X] T015 [P] [US1] Write `backend/tests/imderty/test_workbook.py` (single month). It asserts:
  - **Structure**: the output reopens with openpyxl; exactly one month sheet plus `SECTOR`.
  - **Header**: `I7` = the first day of the month; logo present.
  - **Day headers and table**: row 23 labels for August 2026 start `SA1`, `DO2`; September 2026 ends with `MI30` followed by a weekday-only label; table column names equal the row-23 headers.
  - **Participant rows**: rows ordered by first surname, second surname and first name, numbered from 1; text in upper case with `ñ` and diacritics kept (fictitious "PEÑA"); the sexual-orientation column (M) blank for every row; sensitive columns blank without an authorization.
  - **Validations and calculation**: the barrio validation on `Q24:Q504` references `SECTOR`; `SECTOR` rows equal the active catalog; `fullCalcOnLoad` true.
  - **Limit**: 481 athletes → a raised `SheetTooLarge`.

  — qa-engineer · sonnet · high
- [X] T016 [P] [US1] Write `backend/tests/imderty/test_sheet_api.py` for `POST /api/clubs/{club_id}/imderty-sheet` with `from == to`:
  - **200 response**: xlsx media type; filename `FO-GDD-057_asistencia_2026-08_2026-08.xlsx` without personal data.
  - **403**: parent, athlete account and foreign coach.
  - **Audit**: `export` with `meta` holding only `document_kind`, `from_month`, `to_month`, `row_count` and `gap_count`.
  - **Not stored**: no file is written to disk or storage.
  - **Logs**: a `caplog` assertion that no log line holds a synthetic athlete's name.

  — qa-engineer · sonnet · medium

### Implementation for User Story 1

- [X] T017 [US1] Implement `backend/app/services/imderty/attendance_grid.py`:
  - `active_athletes_in_range(db, club_id, start, end) -> list[Athlete]`, per R5, batch-loading `imderty_profile`, `parents` (with `User.phone`) and the active sensitive rows via `selectinload`;
  - `build_attendance_grid(db, club_id, start, end) -> dict[int, dict[date, Mark]]`, with `Mark = Literal["A","E","F"]` and blank = absent key.

  Use the three range queries of R4, reusing the filters of `training/reports.py` (`get_conjoint_sessions` for the linked-event exclusion, `_resolve_race_dates` generalized to `(athlete_id, event_date)`). Also return `unrecorded: dict[int, set[date]]` for readiness. Take `.date()` on naive `start_at`/`end_at` without `astimezone` — fastapi-architect · opus · high
- [X] T018 [US1] Implement `backend/app/services/imderty/workbook.py` per R1–R3 and R6:
  - **Signature**: `build_sheet(months: list[date], rows_by_month, header, barrios) -> bytes`.
  - **Load**: load the template with openpyxl and keep only the requested month sheets.
  - **Header and day row**:
    - write `I7` and the header cells;
    - write row 23 day labels (`LU MA MI JU VI SA DO` plus the day number; weekday-only trailing labels, kept unique);
    - update `table.tableColumns[i].name` to match.
  - **Participant rows**:
    - write participant values from row 24, leaving formula columns (`F`, `R`, `AZ:BB`) intact;
    - upper-case the text and set dates as real dates;
    - column M always blank.
  - **Barrio and SECTOR**: rewrite `SECTOR` from the catalog, and re-add the barrio list validation `Q24:Q504` = `SECTOR!$A$2:$A$<n>`.
  - **Finish**: set `wb.calculation.fullCalcOnLoad = True`; raise `SheetTooLarge` over 480 rows.

  Profile columns may be empty in this story; they are filled in T032 — fastapi-architect · opus · high
- [X] T019 [US1] Add `POST /api/clubs/{club_id}/imderty-sheet` to `backend/app/routers/imderty_sheet.py`:
  - validate `SheetRequest`;
  - build the rows (grid plus basic athlete data; header from `ClubImdertySettings` if present, otherwise blank);
  - return `Response(content, media_type=…, headers={Content-Disposition, Content-Length})` as `download_monthly_report_docx` does;
  - write `record_audit(action=export, entity_type=imderty_attendance_sheet, meta={…counts})`;
  - map `SheetTooLarge` to a 422 with a Spanish message and no values.

  — fastapi-architect · sonnet · medium
- [X] T020 [US1] Replace the placeholder `frontend/src/routes/imderty/ImdertySheetPage.tsx` (route and nav already registered in T012):
  - a month picker defaulting to the previous month;
  - a «Descargar planilla» button calling the API and `lib/download.ts::triggerBlobDownload`;
  - a warning when the month is the current one («El mes aún no termina»);
  - cold-start and error states (never a bare spinner; the existing «Iniciando servidor…» pattern);
  - responsive per the plan table (full-width button at 360 px).

  All copy in español neutro — react-ui-engineer · sonnet · medium
- [X] T021 [P] [US1] Write `frontend/src/routes/imderty/ImdertySheetPage.test.tsx` (vitest + Testing Library + MSW + jest-axe):
  - the download calls the API with the chosen month;
  - an error shows a Spanish message;
  - a parent role cannot reach the route;
  - zero axe violations.

  — qa-engineer · sonnet · medium
- [X] T022 [US1] US1 gate. Run the backend tests for T014–T016 and the frontend tests for T021. Generate a synthetic month locally, open it in LibreOffice/Excel with no repair prompt, and check marks against the fixtures. Record the results in `checklists/gates.md` — engineering-lead · opus · medium

---

## Phase 4: User Story 2 — Complete each athlete's IMDERTY data (Priority: P1)

**Goal**: admin or coach fills the "Datos IMDERTY" section, sensitive data under authorization, the "contacto principal" and the admin barrio catalog, and the sheet carries them.

**Independent Test**: fill every field for a synthetic athlete and confirm the surname split. Pick a barrio and check the comuna. Sensitive data is blocked without authorization; record it, set the values, generate, and verify the columns. Withdraw it, and the values are gone and blank in the next sheet.

### Tests for User Story 2

- [X] T023 [P] [US2] Write `backend/tests/imderty/test_surnames.py`:
  - **Proposal**: `"GARCÍA PÉREZ"` → (`GARCÍA`, `PÉREZ`); `"DE LA CRUZ GÓMEZ"` → (`DE LA CRUZ`, `GÓMEZ`); `"SÁNCHEZ DEL RÍO"` → (`SÁNCHEZ`, `DEL RÍO`); a single surname → (x, None). All examples are fictitious.
  - **Rebuild invariant**: accent- and case-insensitive; a mismatch is rejected.

  — qa-engineer · sonnet · medium
- [X] T024 [P] [US2] Write `backend/tests/imderty/test_imderty_profile_api.py`:
  - **Reads**: GET of an empty profile → 200 with nulls and a proposed split.
  - **Writes**:
    - PUT validations (digits-only for `rc`/`ti`/`cc`, barrio + other_municipality → 422, a confirmed split that does not rebuild `last_name` → 422);
    - a duplicate document in the same club → 200 with the `duplicate_document_in_club` warning;
    - PUT primary contact: a non-linked user → 422, OK → one primary; switching it moves the mark; unlinking the guardian drops the mark.
  - **Side effect**: `PATCH /api/athletes/{id}` changing `last_name` clears the confirmation.
  - **Access**: 403 for parent and foreign coach.
  - **Audit**: `changed_fields` only, with no values in `diff_json`.

  — qa-engineer · sonnet · high
- [X] T025 [P] [US2] Write `backend/tests/imderty/test_sensitive_api.py`:
  - **Creation**: authorization create → 201 with defaults `NO SABE NO RESPONDE` / `N/A` / `null`; a second active one → 409; an unlinked guardian or a future date → 422.
  - **Gated write**: PUT without authorization → 403; PUT with an invalid value → 422.
  - **Withdrawal**: withdraw → the data row is deleted and `active_key` becomes NULL; GET afterwards → 404; re-authorizing creates a new row with defaults.
  - **Logs and audit**: never contain a sensitive value (`caplog` and `audit_log` scan).
  - **Access**: parent → 403 on every route.

  — qa-engineer · sonnet · high
- [X] T026 [P] [US2] Write `backend/tests/imderty/test_barrios_api.py`:
  - a coach can list and gets 403 on POST/PATCH;
  - the admin can create, rename, re-map the zone and deactivate;
  - a duplicate name → 409;
  - inactive entries are hidden by default.

  — qa-engineer · sonnet · low

### Implementation for User Story 2

- [X] T027 [P] [US2] Implement `backend/app/services/imderty/surnames.py`:
  - `propose_split(last_name) -> tuple[str, str | None]`, keeping the particles `DE`, `DEL`, `DE LA`, `DE LOS`, `DE LAS` attached to the following token;
  - `rebuilds(last_name, first, second) -> bool`, normalized by accent, case and whitespace.

  — fastapi-architect · sonnet · medium
- [X] T028 [US2] Implement `backend/app/services/imderty/profile.py`:
  - **Profile**: `get_or_empty_profile`; `upsert_profile`, which validates the split with `surnames.rebuilds`, sets `surname_split_confirmed_at/by` and computes the duplicate-document warning.
  - **Contacto principal**: `set_primary_contact`, which clears the previous key and sets `primary_contact_key = athlete_id` in one transaction.
  - **Authorization**: `create_authorization`, which checks the guardian is linked and creates the data row with defaults; `withdraw_authorization`, which sets `withdrawn_at/by` and `active_key=NULL` and **deletes** `AthleteSensitiveData` in the same transaction.
  - **Sensitive data**: `update_sensitive_data`, which requires an active authorization.
  - **Phone**: `effective_phone(athlete) -> tuple[str | None, source]`, following the FR-022 chain.
  - **Audit**: every write calls `record_audit` with `changed_fields` only.
  - **Logging**: none of the values.

  — fastapi-architect · opus · high
- [X] T029 [US2] Add to `backend/app/routers/imderty_profile.py` the profile, primary-contact and sensitive-data routes exactly as in `contracts/api.md`, using `require_athlete_staff` and the T028 services — fastapi-architect · sonnet · medium
- [X] T030 [P] [US2] Add the barrio routes (`GET /api/imderty/barrios`; `POST`/`PATCH` with `require_admin`) to `backend/app/routers/imderty_barrios.py` — fastapi-architect · sonnet · low
- [X] T031 [US2] In `backend/app/routers/athletes.py` (`PATCH /{id}`), when `last_name` changes and a profile exists, clear `surname_split_confirmed_at/by`, inside the same transaction — fastapi-architect · sonnet · low
- [X] T032 [US2] Extend `backend/app/services/imderty/workbook.py` row building (and `test_workbook.py`) to fill:
  - **Names**: `B` first name; `C`/`D` the confirmed surnames, or `last_name` in `C` while unconfirmed.
  - **Identity**: `G`/`H` document label and number; `I` `HOMBRE`/`MUJER`; `J` school; `K` grade label.
  - **Sensitive**: `L` disability, `N` victim and `O` ethnicity, **only** with an active authorization.
  - **Address and contact**: `P` address; `Q` barrio name or `OTRO MUNICIPIO`; `S` EPS; `T` `effective_phone`.

  Column M stays blank. Add tests for each column and for the phone chain — fastapi-architect · opus · medium
- [X] T033 [P] [US2] Create `frontend/src/components/imderty/BarrioCombobox.tsx`, following the accessible, diacritic-insensitive pattern of `components/ai/AthleteCombobox.tsx`. Add an «Otro municipio» option and show the zone next to each name. Add the test `BarrioCombobox.test.tsx` (keyboard navigation, search «yumbo» matches «YUMBO», axe) — react-ui-engineer · sonnet · medium
- [X] T034 [US2] Create `ImdertyProfileCard.tsx`, `ImdertyProfileForm.tsx`, `SurnameSplitConfirm.tsx` and `PrimaryContactSelect.tsx` in `frontend/src/components/imderty/`, and mount the card in `frontend/src/components/athletes/AthleteInfoCard.tsx` for admin/coach only.
  - **Form**: RHF + Zod with inline Spanish errors; `inputmode="numeric"` for document and phone; a hint «Si está vacío, se usa el teléfono del contacto principal».
  - **Warnings**: the duplicate-document warning appears as a non-blocking amber notice.
  - **Layout**: two columns at ≥ 768 px, one column at 360 px, sticky save bar.

  — react-ui-engineer · sonnet · high
- [X] T035 [US2] Create `frontend/src/components/imderty/SensitiveDataCard.tsx`:
  - **Locked state**: the block is locked with an explanation.
  - **Recording**: «Registrar autorización» opens a dialog with guardian select and date; no `window.confirm`.
  - **Editing**: the three official-list selects, with «No sabe no responde» / «N/A» defaults.
  - **Withdrawal**: «Retirar autorización» opens a confirmation dialog explaining that the data will be erased.
  - **Mobile**: a full-height scrollable sheet at 360 px.

  — react-ui-engineer · sonnet · medium
- [X] T036 [US2] Replace the placeholder `frontend/src/routes/imderty/BarrioCatalogPage.tsx` (route already registered in T012, admin only): a table with inline edit at ≥ 768 px, and cards with a sheet edit at 360 px. Add, rename, change zone and deactivate. Handle the 409 duplicate message — react-ui-engineer · sonnet · medium
- [X] T037 [P] [US2] Write vitest + jest-axe tests for T034–T036 in `frontend/src/components/imderty/*.test.tsx` and `frontend/src/routes/imderty/BarrioCatalogPage.test.tsx`:
  - **Behaviour**: validation messages; the sensitive block locked vs. unlocked; the withdraw flow; the coach cannot see the catalog admin actions.
  - **Accessibility**: zero violations.

  — qa-engineer · sonnet · medium
- [X] T038 [US2] US2 gate:
  - run the backend and frontend tests of the phase;
  - regenerate the synthetic month and confirm the profile and sensitive columns;
  - extend `test_imderty_privacy.py` with the log and audit scans;
  - record the results in `checklists/gates.md`.

  — engineering-lead · opus · medium

---

## Phase 5: User Story 3 — Configure the header and check readiness before downloading (Priority: P2)

**Goal**: the header comes from the club settings and can be adjusted per download without changing them. A readiness panel lists the gaps per athlete with links.

**Independent Test**: save the settings, override the schedule for one download (the file changes, the settings do not), remove a document number (the gap is listed with a link), and download anyway.

### Tests for User Story 3

- [X] T039 [P] [US3] Write `backend/tests/imderty/test_settings_api.py`: GET before save → nulls and `[]`; PUT get-or-create; invalid program → 422; foreign coach and parent → 403; audit `changed_fields` — qa-engineer · sonnet · low
- [X] T040 [P] [US3] Write `backend/tests/imderty/test_readiness.py`:
  - **Gap codes**: one case per code in `data-model.md` (`missing_document`, `missing_barrio`, `missing_eps`, `missing_phone`, `no_guardian`, `multiple_guardians_no_primary`, `surname_split_unconfirmed`, `activity_without_record` with dates).
  - **Month flags**: `month_in_progress`, `months_without_activity`.
  - **Access**: 403 paths.
  - **Size limit**: 422 over 480 athletes.
  - **Header override**: `POST` with a `header` override writes the override into the file and leaves the settings unchanged unless `save_header_as_default=true`.

  — qa-engineer · sonnet · medium

### Implementation for User Story 3

- [X] T041 [US3] Add `GET`/`PUT /api/clubs/{club_id}/imderty-settings` to `backend/app/routers/imderty_settings.py`, copying the get-or-create and audit pattern of `routers/monthly_reports.py` project-profile (~L803-947) — fastapi-architect · sonnet · low
- [X] T042 [US3] Implement the readiness service and route:
  - `backend/app/services/imderty/readiness.py::build_readiness(db, club_id, months)`, which reuses `active_athletes_in_range` and `build_attendance_grid(...).unrecorded`;
  - audience resolution through `services/calendar/audiences.py::resolve_athletes`;
  - `GET /api/clubs/{club_id}/imderty-sheet/readiness` in `backend/app/routers/imderty_sheet.py`;
  - `display_name` only in the response, never logged.

  — fastapi-architect · sonnet · medium
- [X] T043 [US3] Extend the sheet `POST` and the workbook:
  - **Header**: apply `header` overrides; persist them only when `save_header_as_default`.
  - **Program marks**: map each `ImdertyProgram` to its "X" mark cell. Locate the label cells in the template once and record the map as a constant in `workbook.py`, with a test that asserts each mapped cell sits next to its label.
  - **Audit**: `gap_count` from readiness.

  — fastapi-architect · sonnet · medium
- [X] T044 [US3] Create `frontend/src/components/imderty/HeaderOverridesForm.tsx` (prefilled from the settings, a «Guardar como predeterminado» checkbox) and `frontend/src/components/imderty/ReadinessPanel.tsx`, and wire both into `ImdertySheetPage.tsx`, with a settings section on the same page.
  - **Readiness panel**:
    - a table at ≥ 768 px and one card per athlete at 360 px;
    - gap chips with Spanish labels and a link to the athlete's «Datos IMDERTY» section;
    - green «Todo listo» when there are no gaps, amber when there are.
  - **Download**: stays enabled with gaps.

  — react-ui-engineer · sonnet · high
- [X] T045 [P] [US3] Write vitest + jest-axe tests for T044 in `frontend/src/components/imderty/ReadinessPanel.test.tsx` and `HeaderOverridesForm.test.tsx`: overrides are sent, the default checkbox is honoured, gap links point to the athlete, and there are zero violations — qa-engineer · sonnet · medium
- [X] T046 [US3] US3 gate: run the phase tests and record the results in `checklists/gates.md` — engineering-lead · opus · medium

---

## Phase 6: User Story 4 — Download a period of months in one workbook (Priority: P3)

**Goal**: one workbook with one sheet per month, in chronological order, across a year boundary, up to 12 months.

**Independent Test**: generate Aug–Oct: three sheets, each identical in content to the single-month downloads, plus `SECTOR`. Generate Nov–Feb: the sheets are in chronological order.

- [X] T047 [P] [US4] Extend `backend/tests/imderty/test_workbook.py` and `test_sheet_api.py`:
  - **Content**: each period sheet has the same cell values as the single-month build.
  - **Order**: Nov 2026–Feb 2027 → `NOVIEMBRE, DICIEMBRE, ENERO, FEBRERO, SECTOR`.
  - **Per-month membership**: an athlete joining in September is absent from August.
  - **Limits**: 13 months → 422.
  - **File name**: `FO-GDD-057_asistencia_2026-11_2027-02.xlsx`.

  — qa-engineer · sonnet · medium
- [X] T048 [US4] Extend `backend/app/services/imderty/workbook.py` for several months: keep the requested month sheets, remove the rest, reorder them chronologically with `SECTOR` last, and compute the rows and the grid per month — fastapi-architect · opus · medium
- [X] T049 [US4] Wire the `from`/`to` range end to end in the `POST` and readiness routes (`backend/app/routers/imderty_sheet.py`), with the per-range file name — fastapi-architect · sonnet · low
- [X] T050 [US4] Add a «Un mes / Varios meses» toggle with a from/to month picker to `frontend/src/routes/imderty/ImdertySheetPage.tsx`, disabling ranges over 12 months with an inline message. Extend `ImdertySheetPage.test.tsx` — react-ui-engineer · sonnet · medium

---

## Phase 7: Polish & cross-cutting concerns

- [X] T051 [P] Run the `data-privacy-guard` audit over every new or changed backend and frontend file:
  - logs, `HTTPException.detail`, audit `meta`/`diff_json`;
  - fixtures, file names;
  - parent projections, browser cache persistence;
  - the committed template;
  - the absence of sexual orientation.

  Write the findings to `specs/047-imderty-attendance-sheet/privacy-audit.md` and fix the blockers — data-privacy-guard · opus · high
- [X] T052 [P] Write `frontend/e2e/imderty-sheet.spec.ts` (Playwright, desktop project, isolated e2e stack helpers from feature 040): the coach fills in the IMDERTY data of a demo athlete, sees and resolves a readiness gap, and downloads a month (assert the download event and file name). Run it if the stack is available; otherwise mark it deferred in `docs/22-imderty-attendance-sheet/qa.md`. Mobile run: recommended — qa-engineer · sonnet · medium
- [X] T053 [P] Add `backend/tests/imderty/test_sheet_performance.py`:
  - **Query count**: the query count for a month is independent of the athlete count (40 vs 5 synthetic athletes; no N+1).
  - **Timing**: a 40-athlete month builds in under 10 s and 5 months in under 30 s on the test machine (SC-007); mark the timing test `slow` if needed.

  — performance-engineer · sonnet · medium
- [X] T054 [P] Write `docs/22-imderty-attendance-sheet/`:
  - **`workflow.md`**: the monthly routine for the coach.
  - **`runbook.md`**:
    - how to rebuild the template when IMDERTY publishes a new version, using `scripts/build_imderty_template.py`;
    - the phone-previewer blank-counter limitation;
    - the sensitive-authorization custody note (proof kept by the club outside the platform).
  - **`qa.md`**: the deferred lanes.

  Also add a feature-047 step table to `docs/implementation-status.md` and a dated entry to `docs/technical-notes.md` — technical-writer · sonnet · low
- [X] T055 Run `python -m pytest -m mysql tests/imderty/test_migration_imderty.py` against local MySQL (docker compose). If MySQL is not available, record it as **deferred** in `docs/22-imderty-attendance-sheet/qa.md` — devops-engineer · sonnet · medium
- [X] T056 Final gate. Run the full offline lanes:
  - `cd backend && python -m pytest -q && ruff check`;
  - `cd frontend && npm run typecheck && npm test && npm run build`, checking that the `/imderty` route chunk is ≤ 150 KB gzipped;
  - the quickstart §3 manual flow, including the 360 px check of §3.7.

  Record pass/fail per command in `checklists/gates.md`, and list every unrun lane (mysql, Playwright, post-deploy) explicitly — engineering-lead · opus · medium
- [ ] T057 Post-deploy (owner, after merge/deploy):
  - `/health`, then `GET /api/clubs/{id}/imderty-settings` as a coach;
  - regenerate August 2026 on the owner's machine and compare its non-sensitive columns with the hand-made sheet (SC-004);
  - deliver to IMDERTY and record acceptance (SC-003) in `docs/22-imderty-attendance-sheet/qa.md`.

  — release-manager · sonnet · low

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1**: no dependencies; T001–T003 run in parallel.
- **Phase 2**: after Phase 1.
  - T004 → T005 → T006.
  - T007 after T004.
  - T008 after T003 (it needs the seed); T009 after T008.
  - T010 after T004.
  - T011 and T012 run in parallel, after T004/T007.
  - The T013 gate runs last.
- **Phase 3 (US1)**: after T013.
  - T014–T016 first, in parallel.
  - T017 and T018 run in parallel (different files).
  - T019 after both.
  - T020 → T021.
  - The T022 gate runs last.
- **Phase 4 (US2)**: after T013.
  - The backend is independent of US1 except T032, which needs T018.
  - T023–T026 first. T027 → T028 → T029; T030 and T031 run in parallel.
  - Frontend: T033 → T034; T035 and T036 run in parallel; then T037.
  - The T038 gate runs last.
- **Phase 5 (US3)**: T041 needs only Phase 2; T042 needs T017; T043 needs T019; T044 needs T020.
- **Phase 6 (US4)**: after T019 (and T043 if US3 has shipped).
- **Phase 7**: after the stories the owner wants shipped.

### Story independence

- **US1**: shippable alone (MVP: marks from existing data, identity columns partly blank).
- **US2**: testable alone through its API. Its only coupling to US1 is T032, the workbook columns.
- **US3**: builds on US1's page and generator.
- **US4**: builds on US1's generator.

## Parallel examples

```text
# Phase 1
T001 openpyxl | T002 audit catalogue | T003 barrio seed

# Phase 2 after T004
T005 migration → T006 | T007 schemas | T008 template builder → T009 | T010 router deps | T011 privacy tests | T012 FE foundations

# US1 after T013
T014 grid tests | T015 workbook tests | T016 API tests → T017 grid (opus) | T018 workbook (opus) → T019 → T020 → T021

# US2 alongside US1 backend
T023–T026 tests | T027 surnames → T028 profile (opus) → T029 | T030 barrios | T031 PATCH hook | T033 combobox
```

## Implementation strategy

1. **MVP**: Phases 1–3 (US1). Stop, run the T022 gate and quickstart §1 and §3.5 with synthetic data, and demo to the owner.
2. **Increment 2**: Phase 4 (US2). This is the one that makes the sheet acceptable to IMDERTY, so it follows right after the MVP.
3. **Increment 3**: Phase 5 (US3), then Phase 6 (US4).
4. **Close**: Phase 7. Report explicitly which real-infrastructure lanes (`-m mysql`, Playwright, post-deploy) were not run.

## Agent assignment summary

| Model | Tasks | Rationale |
|---|---|---|
| **opus** | T004, T005, T008, T013, T017, T018, T022, T028, T032, T038, T046, T048, T051, T056 | data model and migration with partial-unique tricks; XML-level template builder; attendance-grid rules (double counting, dates, windows); workbook writer fidelity; sensitive-data erasure transaction; privacy audit; integration gates |
| **sonnet** | T001–T003, T006, T007, T009–T012, T014–T016, T019–T021, T023–T027, T029–T031, T033–T037, T039–T045, T047, T049, T050, T052–T055, T057 | bounded, contract-driven implementation, tests, UI, docs and ops |

**Effort hints**: `high` for T004, T005, T008, T014, T015, T017, T018, T024, T025, T028, T034, T044 and T051; `low` for T001, T002, T026, T030, T031, T039, T041, T049, T054 and T057; `medium` elsewhere.

**Rules for the orchestrator**:
- Respect the owner's session-budget rule: no new agents past 80 % of the session budget.
- Respect the "no git stash / no destructive git" rule for subagents.
- Give each agent disjoint file ownership within a wave.

## Notes

- Constraints quoted from `data-model.md` and `contracts/api.md` are normative. When a task and a contract disagree, the contract wins and the task must be corrected in this file.
- Never add `imderty` query keys to `frontend/src/lib/persistAllowList.ts`.
- Never add a sexual-orientation field, enum, column, label or import path.
- The owner's reference workbook is used only by T003 (the `SECTOR` sheet) and T008 (structure). It is never copied, committed or printed.
- Owner decisions from the 2026-09-28 interview and clarifications are closed; do not reopen them during task execution.
