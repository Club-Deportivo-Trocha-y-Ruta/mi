# Research — 047 IMDERTY monthly attendance sheet

Date: 2026-09-28. Inputs:
- the spec;
- a structure-only inspection of the owner's reference workbook (no participant values were read into this document);
- two codebase surveys (athlete/RBAC/export patterns; attendance sources).

## R1. How to produce a file that looks exactly like FO-GDD-057 v006

**Decision**: Fill a sanitized copy of the official workbook with `openpyxl` (new backend dependency, `openpyxl>=3.1.5`). The official workbook is not regenerated from scratch.

**Findings** (openpyxl 3.1.5 round-trip test on the reference file, done in `/tmp` and deleted afterwards):
- **Kept**: the logo image (one per month sheet), the Excel table (`Tabla13…`, ref `A23:BB504`), 11 standard data validations per sheet, merged cells, styles and formulas. The workbook already has `fullCalcOnLoad=True`.
- **Lost**:
  - the one `x14:dataValidation` extension per month sheet, which is the **barrio dropdown** `Q24:Q504 → SECTOR!$A:$A`;
  - `printerSettings*.bin`;
  - `calcChain.xml`, which Excel rebuilds.
- **Consequences**:
  - Re-create the barrio dropdown as a standard list validation pointing at `SECTOR!$A$2:$A$<n>`. Excel 2010+ accepts cross-sheet references in standard validations.
  - Re-apply print setup from code if needed.
  - openpyxl writes formulas without cached values, so viewers without a calculation engine (some phone previewers) show blank counters. Excel, LibreOffice and Google Sheets recalculate on open. Keep `fullCalcOnLoad=True` and document the limitation in the quickstart.

**Alternatives considered**:
- **Build from scratch with xlsxwriter**: rejected. The fidelity risk is too high (logo placement, merged header, table styling), and every template revision would mean re-coding the layout.
- **Edit the XML parts directly**: gives full fidelity, including the x14 validation and cached values, but means writing a bespoke writer (shared or inline strings, styles, table parts). Rejected for runtime. It is used only in the one-off template-builder script (R2).

## R2. The shipped template (never the owner's file)

**Decision**: Commit `backend/templates/documents/imderty/fo_gdd_057_v006.xlsx`. The dev-only script `backend/scripts/build_imderty_template.py` produces it from the owner's workbook, whose path is passed as an argument and which is never copied into the repo. The script:
- keeps one month sheet's structure and **clears every participant cell (rows 24–504, all columns)** and the header values (contractor, venue, days, schedule, "X" program marks);
- keeps the labels and formulas;
- clones it at the XML level into **12 month sheets** (ENERO…DICIEMBRE), each with a unique table name and display name (`TablaEnero`…) and its COUNTIFS structured references rewritten;
- rebuilds `SECTOR` from the seed catalog (R6).

A privacy test asserts that the committed template has no non-formula value in rows ≥ 24 and no header values (FR-026a, Principle "minors' privacy").

**Why 12 pre-built sheets**: openpyxl's `copy_worksheet` copies neither images, tables nor validations. With 12 sheets, generation is "load, drop unrequested months, reorder, fill".

**Alternative considered**: a single month sheet with multi-month assembled at runtime. Rejected for the copy limitation above.

## R3. Day columns, table headers and short months

**Findings**: row 23 is the header row of the Excel table, so each day header (e.g. `SA1`) is also a table column name, and they must stay identical or Excel shows a repair prompt. In the owner's 30-day sheets, IMDERTY keeps the 31st column labelled with the weekday only (e.g. `JU`) and leaves it blank.

**Decision**: When writing row 23, also update `table.tableColumns[i].name`. Day labels are `LU MA MI JU VI SA DO` plus the day number. For short months, the trailing columns get the weekday abbreviation only, stay blank, and must stay unique (e.g. `JU`, then `VI`). Spec scenario US1-6 was aligned to this convention.

**Addendum (2026-09-28, stories gate W3) — program marks.** The header's program block has an "X" cell directly below nine of the eleven program labels (`C14`…`I14`, `C18`/`E18`/`H18`). `MASIFICACIÓN` (`C12:I12`) and `COMPETENCIA` (`C16:I16`) are merged group headings with no "X" cell of their own. **Decision (owner, 2026-09-29): leave them empty.** Selecting `masificacion` or `competencia` writes no mark and leaves the heading text untouched (`workbook.py::PROGRAM_HEADING_CELLS` is an empty map, covered by `test_workbook.py::test_heading_programs_are_left_unmarked_when_selected`). To mark them later, map the program to its heading cell (` X` is appended).

## R4. Attendance grid sources and rules

**Decision**: Add a new pure-data service `app/services/imderty/attendance_grid.py`. It builds `{(athlete_id, date): Mark}` for a date range from three queries, reusing the filters of `training/reports.py` (`get_conjoint_sessions`, `_resolve_race_dates`). It does not extend `compute_monthly_metrics`, which aggregates away the date.

| Source | Rows counted | Mapping |
|---|---|---|
| Training sessions | `TrainingSession.status == EXECUTED`; `SessionAttendance.archived_at IS NULL`; day = `scheduled_date` | presente/tarde → A; justificado/lesionado → E; ausente → F |
| Club outings / joint trainings | `CalendarEvent.event_type IN (club_event, group_training)`; `status != cancelled`; **excluding events linked to a TrainingSession** (same `not_in(linked_event_ids)` guard as `get_conjoint_sessions`, prevents double counting); `EventAttendance.actual_status` | attended → A; excused → E; no_show → F; unknown → blank + readiness gap |
| Competitions | `CalendarEvent.event_type == competition` (not cancelled) joined to `RaceEvent`; `RaceResult.athlete_id` with `deleted_at IS NULL` on `RaceEvent.event_date` | A if a result exists **or** `actual_status == attended`; else excused → E, no_show → F; unknown → blank |

Additional rules:
- **Precedence per cell**: A > E > F.
- **Excluded**: `personal_training`, `rest_day`, `birthday` and `training_session`-type events. The last are covered by `session_attendance` (docstring of `EventAttendance`).
- **Multi-day events**: the single `EventAttendance` status applies to every date in `[start_at.date(), end_at.date()]` ∩ month. Spec edge case added.
- **Dates**: `CalendarEvent.start_at/end_at` are naive Bogotá wall-clock values. Take `.date()` directly and **never** `astimezone()` first, which would cause an off-by-one day. `scheduled_date` and `event_date` are already local dates.
- **Race results**: queried by `RaceResult.athlete_id` (club-scoped), never by a bare `competitor_id`, so `third_party_guard` does not apply.
- **Readiness**: "activity without record" = the athlete is in the resolved audience of a counted event (`services/calendar/audiences.py::_resolve_single_audience` or its public wrapper) but has no `EventAttendance` row or an `unknown` status.

## R5. Active athletes in a month

There is no existing helper; a new one is added. An athlete is active on day D when `(club_join_date IS NULL OR club_join_date <= D) AND (deleted_at IS NULL OR deleted_at::date > D)`. They are included in a month when active on at least one day of it. Days outside the athlete's active window stay blank (FR-014, edge cases).

## R6. Barrio catalog

**Decision**: One platform-wide table `imderty_barrios` (spec FR-002 was aligned: admin-maintained, not per club). It is seeded by the migration with the entries of the official SECTOR sheet (82 unique entries after collapsing duplicate spellings). That is public geographic data, not personal, so it may be committed. Zone values are `1`–`4`, `ZONA NORTE`, `ZONA CENTRO` or `ZONA SUR`. The generated workbook's `SECTOR` sheet is rewritten from the table, so the sheet's `VLOOKUP` comuna formula and the platform-derived comuna always agree. "Otro municipio" is a flag on the profile (barrio NULL). The sheet writes `OTRO MUNICIPIO` in the barrio cell. `SECTOR` gets `OTRO MUNICIPIO` as its last row so Excel's list validation on `Q24:Q504` accepts it. Its zone cell is the empty-text formula `=""` rather than an empty cell, because a `VLOOKUP` onto an empty cell returns `0`; with `=""` the comuna column stays blank.

## R7. Surnames without breaking 279 `last_name` usages

**Decision**: Keep `Athlete.last_name` untouched as the full surname text. Race matching, the forbidden-names guardrail, newsletters and reports keep working, and the guardrail keeps seeing the second surname, so there is **no privacy regression**. Add `first_surname` and `second_surname` plus `surname_split_confirmed_at/by` to the new IMDERTY profile. The split is valid only while `normalize(first + " " + second) == normalize(last_name)`. When `last_name` changes (`PATCH /api/athletes/{id}`), the confirmation is cleared and a new split is proposed. The proposal heuristic takes the first token as the first surname, keeping Spanish particles (`DE`, `DEL`, `DE LA`, `DE LOS`, `DE LAS`) attached to the following token, and the rest as the second surname.

**Alternative considered**: adding `second_last_name` to `athletes` and shrinking `last_name`. Rejected because it would silently drop the second surname from the forbidden-names list and from race identity matching.

## R8. Sensitive data isolation and erasure

**Decision**:
- **Separate tables**: `athlete_sensitive_authorizations` (append-only: guardian, `authorized_on`, recorder, `withdrawn_at/by`) and `athlete_sensitive_data` (one row per athlete, three enum columns).
- **Withdrawal** sets `withdrawn_at` and **deletes** the `athlete_sensitive_data` row in the same transaction (FR-007), with an audit entry that has no values.
- **At most one active authorization per athlete**, enforced with the nullable-unique trick: the `active_key` column equals `athlete_id` while active and is NULL once withdrawn, under a UNIQUE index. This works on MySQL and SQLite.
- **This is a new concept**, distinct from `ParentalConsent.third_party_sharing`, which gates AI and is not reused (FR-024).
- **Structural test**: none of the new models may be imported under `app/services/ai/**`, `app/services/llm/**`, `app/services/race/**`, or the newsletter/report builders. This mirrors the `third_party_guard` CI sweep (FR-010).

## R9. "Contacto principal"

**Decision**: Add a nullable `primary_contact_key` column to `parent_athlete`, set to `athlete_id` when that link is the primary one, with a UNIQUE index. This allows at most one primary per athlete with the same nullable-unique trick. Unlinking removes the row, so the mark disappears with it. The fallback is the earliest link by `parent_athlete.id`.

## R10. Patterns reused

- **RBAC**: `require_role([admin, coach])` plus the `_coach_club_ids` membership check, as in `routers/athletes.py`. Denied-path tests follow `tests/test_athletes.py::test_coach_cannot_create_in_foreign_club`.
- **Club settings**: `ClubProjectProfile` get-or-create and PATCH with `record_audit(changed_fields=…)` (`routers/monthly_reports.py` ~L803-947).
- **Download**: plain `Response(content=bytes, media_type=…, headers={"Content-Disposition": 'attachment; filename="…"', "Content-Length": …})`, as in `download_monthly_report_docx`. On the frontend, `lib/download.ts::triggerBlobDownload` with axios `responseType: "blob"`.
- **Audit**: `services/audit.py::record_audit(action=AuditAction.export, entity_type=…, meta={document_kind, from_month, to_month, row_count, gap_count})`. New `AuditEntityType` values and `AuditDocumentKind.imderty_attendance_xlsx`.
- **Parent-hiding**: the new data lives in new tables that `AthleteParentView` never loads. Tests assert that parent responses carry none of the new keys.
- **Barrio picker**: `components/ai/AthleteCombobox.tsx` (accessible, diacritic-insensitive) as the pattern; no new dependency.

## R11. Open risks

- Some phone previewers show blank counters because cached values are missing (R1). IMDERTY opens the file in Excel; this is covered in the quickstart check.
- IMDERTY may validate the file in a way that is not visible to us. SC-003 is verified on the first real delivery (post-deploy, owner action).
- `pytest -m mysql` is needed for the migration (enum types, partial-unique indexes) and is usually deferred in sessions without MySQL. It must be reported as pending if not run.
