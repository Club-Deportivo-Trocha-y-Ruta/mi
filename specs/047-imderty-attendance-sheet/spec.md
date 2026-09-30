# Feature Specification: IMDERTY monthly attendance sheet (official format FO-GDD-057 v006)

**Feature Branch**: `main` (owner decision 2026-09-28: no dedicated branch; the `speckit.git.feature` hook and every auto-commit hook are skipped)

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "IMDERTY monthly attendance sheet (official format FO-GDD-057 v006). The Instituto Municipal de Deporte y Recreación de Yumbo requires every month an attendance sheet in its official Excel format; today the coach fills it by hand. Extend the athlete record with the data the format requires (document type and number, address, barrio from the Yumbo catalog with automatic comuna/zona, school and grade, EPS, phone = athlete's own when recorded, otherwise primary guardian's); ethnicity, disability and armed-conflict victim status only with express guardian authorization for sensitive data; sexual orientation never collected; one-time reviewed import of profile data from the club's existing workbook; header in the club configuration with per-download adjustments; generate one month or a period of months from trainings, club outings and joint trainings, and competitions (attended/late = A, excused/injured = E, absent = F, days without activity blank, age at the first day of the month); the file must look exactly like the official format; a readiness check before downloading. Admin and coach only; audited without personal data; no AI use of the new fields; the IMDERTY agreement covers sharing, so the third-party-sharing authorization is not a gate. Everything on main, no branches, no auto-commits."

## Context

The Instituto Municipal de Deporte y Recreación de Yumbo (IMDERTY) is one of the club's funders. Every month it requires the planilla de asistencia in its official format **FO-GDD-057, version 006** (process "Gestión del deporte y la recreación"). The owner shared the workbook the club currently fills by hand; its structure (never its participant data) is the reference for this feature:

- **One sheet per month** (the shared workbook carries AGOSTO to DICIEMBRE) plus a **SECTOR** sheet that maps Yumbo barrios (82 unique entries after collapsing duplicate spellings) to a comuna (1–4) or a rural zone (Zona Norte, Zona Centro, Zona Sur).
- **Header block**: institute name, process, code, version and format date; contractor; training venue; training days; schedule; the IMDERTY program the group belongs to (Masificación, Educación física / deporte escolar, Primera infancia, HEVS, Recreación, Deporte social comunitario, LECYD-CDA, Competencia, Conjunto, Individual, Adaptado), marked with an "X"; the attendance legend (A = asiste, F = falta, E = excusa).
- **Automatic counters** in the header: participants by sex, by age band (0–5, 6–10, 11–14, 15–19, 20–59, 60+), by disability type, by sexual orientation, by ethnicity, by armed-conflict victim status and by comuna/zona.
- **Participant table** (one row per participant, up to about 480 rows): row number, first name, first surname, second surname, birth date, age (computed at the first day of the month), document type (R.C, T.I, C.C, C.E, PPT, PEP, NES), document number, sex (Hombre/Mujer), school/institution/group/club, grade, disability type, sexual orientation, armed-conflict victim (Sí/No), ethnicity, address, barrio, comuna (looked up from the barrio), EPS, phone; then **one column per calendar day** headed by weekday and day number (e.g. "SA1", "DO2"), and the per-row totals of A, F and E.
- Dropdown lists constrain the categorical columns, and text columns are expected in upper case.

Observed in the hand-made August 2026 sheet: 27 participants, many of them in preschool or primary grades; every calendar day marked A or F, including weekends; sexual orientation filled for every row. Today the platform stores only name, birth date, sex and club for an athlete, so it cannot produce the sheet. Attendance, however, is already recorded per training session (presente, ausente, justificado, tarde, lesionado) and per calendar event (outings, joint trainings, competitions).

**Owner decisions taken on 2026-09-28** (interview before this spec):

1. The sheet lists the club's active athletes. Children who attend and are not yet in the platform are registered as regular athletes. There is no separate "IMDERTY-only participant" registry.
2. Ethnicity, disability type and armed-conflict victim status are stored only with the guardian's express authorization for sensitive data, default "no informa", visible only to admin and coach, never used by AI. Sexual orientation is never collected or stored, and its column stays blank.
3. Days with no scheduled activity stay blank. They are not marked F, which is a deliberate change from the hand-made practice.
4. Trainings, club outings and joint trainings, and competitions all count as attendance.
5. The coach or admin fills the new data in the athlete record. There is no file upload or import: the shared workbook is only a reference for the output format (decision revised in clarification 2026-09-28).
6. The header comes from the club configuration and can be adjusted before each download.
7. The coach chooses between one month and a period of months at download time.
8. The barrio is picked from the Yumbo catalog, and the comuna/zona fills in automatically. "Other municipality" leaves comuna/zona empty.
9. The IMDERTY agreement covers sharing this data with IMDERTY, so the per-athlete third-party-sharing authorization is **not** checked for this sheet.
10. The phone is the athlete's own phone when recorded (optional). Otherwise it is the primary guardian's phone.

## Clarifications

### Session 2026-09-28

- Q: For competition days, does attendance count only when the athlete has a recorded result, or also when the coach marked them present at the event? → A: Either one counts as A: a recorded result in that competition, or presence marked by the coach at the calendar event. Otherwise the event's excused/no-show status gives E/F.
- Q: Should the platform import profile data from the club's existing workbook? → A: No. The workbook is only the reference for the output format. The import story and its requirements are removed, and all data is entered in the athlete record.
- Q: The format needs first and second surname separately, but the platform keeps surnames in one field. How are they separated? → A: As two separate fields (first surname required, second surname optional). For existing athletes, the platform proposes a split once and the coach confirms or corrects it.
- Q: When an athlete has two linked guardians, whose phone goes in the sheet? → A: The coach marks one guardian as "contacto principal" in the IMDERTY section. With no mark, the first linked guardian is used and the readiness panel flags it.
- Q: If IMDERTY publishes a new version of the format, how is the platform's template updated? → A: The template ships with the platform. A new version is incorporated through a platform update, with no in-app upload screen.
- Q: How is the guardian's express authorization for sensitive data obtained and evidenced? → A: Only its date and the guardian who gave it are recorded in the platform. The wording and the proof are handled entirely outside the platform.
- Q: How does responsiveness apply? → A: The primary device of every screen in this feature is the desktop. Each screen must still adapt to 768 px and 360 px (constitution 1.4.0, Principle III; FR-029).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generate the month's sheet from recorded attendance (Priority: P1)

At the start of a month the coach opens the IMDERTY sheet screen on the desktop (primary device; a phone also works), picks the previous month and downloads the file. The platform lists every club athlete who was active during that month. It fills each row with the data it holds and marks every day that had a club activity with A, F or E according to what the coach recorded at the time. It leaves days without activity blank and computes the totals and header counters the same way the official format does. The coach sends that file to IMDERTY with no retyping.

**Why this priority**: This is the hours of manual work the feature removes, and it is the one thing IMDERTY actually receives. Even with only the data the platform already holds (name, birth date, age, sex, attendance), the generated sheet is more accurate than today's hand-made one.

**Independent Test**: In a test club, create athletes with only name, birth date and sex. Record a month of trainings, one outing and one competition with mixed statuses, generate the sheet for that month, and verify every row, day mark, total and counter against the recorded data, with the identity columns the platform does not yet hold left blank.

**Acceptance Scenarios**:

1. **Given** a month with executed trainings, **When** the coach generates the sheet, **Then** each athlete's day cell holds A when the recorded status was presente or tarde, E when it was justificado or lesionado, and F when it was ausente.
2. **Given** a calendar day with no training, outing, joint training or competition for the club, **When** the sheet is generated, **Then** that day's cell is blank for every athlete, whatever the weekday.
3. **Given** a cancelled or never-executed training on a day, **When** the sheet is generated, **Then** that training does not produce any mark.
4. **Given** an athlete took part in two activities on the same day with different statuses, **When** the sheet is generated, **Then** the day cell shows a single mark with precedence A over E over F.
5. **Given** a club outing or joint training addressed to only some athletes, **When** the sheet is generated, **Then** only the athletes in its audience receive a mark for that day, and the rest stay blank unless another activity applies to them.
6. **Given** any generated month, **When** the file is opened, **Then** the day columns are headed with the correct weekday abbreviation and day number for that month (for example, a month starting on Saturday begins with "SA1"), and in months with fewer than 31 days the trailing day columns carry only the weekday abbreviation (no day number) and stay blank, as IMDERTY's own sheets do.
7. **Given** any generated month, **When** the file is opened, **Then** each athlete's age is their completed years at the first day of that month, and the age-band, sex and other header counters agree with the rows.
8. **Given** a parent or athlete account, **When** it tries to reach the sheet screen or download a sheet, **Then** access is denied.
9. **Given** a coach of one club, **When** they generate a sheet, **Then** only athletes of that club appear.
10. **Given** the coach is on a phone (360 px wide), **When** they pick a month and download, **Then** the flow completes without horizontal page scroll and the file can be opened or shared from the phone.

---

### User Story 2 - Complete each athlete's IMDERTY data (Priority: P1)

From the athlete record the coach or admin completes a new "Datos IMDERTY" section with these fields:
- first surname and second surname, as separate fields;
- document type and number;
- address, and a barrio picked from the Yumbo catalog (the comuna/zona fills itself in), or "Otro municipio";
- school or institution, and grade;
- EPS;
- an optional phone for the athlete, with a visible hint that the primary guardian's phone is used when it is empty;
- when the athlete has more than one linked guardian, which one is the "contacto principal".

A separate block for ethnicity, disability type and armed-conflict victim status stays locked until the coach records that the guardian gave express authorization for sensitive data. The coach records the date of that authorization and who gave it. Sexual orientation does not appear anywhere.

**Why this priority**: The sheet is only as good as the identity columns. Without this story IMDERTY receives rows without document numbers, barrios or EPS. It shares P1 with Story 1 because both are needed for a sheet IMDERTY will accept without re-work.

**Independent Test**: For one test athlete, fill every non-sensitive field, pick a catalog barrio and confirm the comuna appears. Then try to fill a sensitive field without authorization (it is blocked), record the authorization, fill the three fields, generate the sheet, and confirm each value lands in the right column. Finally withdraw the authorization and confirm the three values are gone.

**Acceptance Scenarios**:

1. **Given** the athlete record, **When** the coach picks a barrio from the catalog, **Then** the matching comuna or zona is shown and cannot be typed by hand.
2. **Given** the coach selects "Otro municipio", **When** the record is saved, **Then** the comuna/zona is empty and the sheet shows the address with an empty comuna cell.
3. **Given** the document type is R.C (registro civil) or T.I (tarjeta de identidad), **When** the number is entered, **Then** only digits are accepted, and a number already used by another athlete of the club raises a warning before saving.
4. **Given** no sensitive-data authorization is on record, **When** the coach opens the sensitive block, **Then** the three fields cannot be edited, and the sheet shows them blank.
5. **Given** an authorization is recorded, **When** the block is first opened, **Then** each field defaults to "No informa" (or its closest official equivalent), and the coach can choose any option from the official lists.
6. **Given** a recorded authorization is withdrawn, **When** the withdrawal is saved, **Then** the three sensitive values are erased, not just hidden, and later sheets show them blank.
7. **Given** the athlete has no phone of their own, **When** the sheet is generated, **Then** the phone column shows the primary guardian's phone. When the athlete has one, it shows the athlete's.
8. **Given** a parent account, **When** it views its own child, **Then** it sees none of the new fields.
9. **Given** the admin, **When** they open the barrio catalog, **Then** they can add, rename or re-map a barrio's comuna/zona, and the change is reflected in sheets generated afterwards.
10. **Given** an existing athlete whose surnames are still stored as one text, **When** the coach opens the section, **Then** a proposed first/second surname split is shown to confirm or correct, and the sheet uses the confirmed values.
11. **Given** the coach edits the section on a phone (360 px wide), **When** they fill it, **Then** the fields stack in one column, document number and phone open a numeric keypad, the barrio picker is searchable, and saving stays reachable with the keyboard open.

---

### User Story 3 - Configure the header and check readiness before downloading (Priority: P2)

Once, the admin or coach fills the club's IMDERTY settings: contractor, training venue, days, schedule and the program(s) to mark. On the download screen those values appear prefilled and can be adjusted for this download only. Before downloading, a readiness panel lists the athletes with missing or suspect data, for example:
- no document number;
- no barrio, or a barrio outside the catalog;
- no EPS;
- no phone for either the athlete or the guardian;
- an athlete who had activities but no recorded attendance.

Each item links to the athlete record to fix it. The coach can still download with gaps.

**Why this priority**: The header is small but mandatory in the format. The readiness panel turns a silent blank cell into a fix the coach can make in seconds, which is what makes the "accepted as-is" outcome achievable month after month.

**Independent Test**: Save club settings, open the download screen, change the schedule for this download, and confirm the file carries the adjusted value while the stored settings remain unchanged. Remove one athlete's document number and confirm the readiness panel names that athlete with a link, and that downloading still works.

**Acceptance Scenarios**:

1. **Given** saved club IMDERTY settings, **When** the download screen opens, **Then** contractor, venue, days, schedule and program are prefilled.
2. **Given** the coach edits a header value on the download screen, **When** the file is generated, **Then** the file uses the edited value, and the stored settings are unchanged unless the coach explicitly saves them.
3. **Given** athletes with missing required data, **When** the readiness panel loads, **Then** each gap is listed per athlete with a link to that athlete's record. On the screen, athletes are identified by name, which is visible only to admin and coach.
4. **Given** readiness gaps exist, **When** the coach chooses to download anyway, **Then** the file is produced with those cells blank.
5. **Given** the coach is on a phone (360 px wide), **When** the readiness panel shows gaps, **Then** each athlete's gaps appear as a stacked card with a tappable link to the record.

---

### User Story 4 - Download a period of months in one workbook (Priority: P3)

For semester or year-end deliveries the coach picks a range of months, for example August to December. The platform produces one workbook with one sheet per month, named in upper case with the month name as the shared workbook does, plus the barrio catalog sheet. Each month follows exactly the rules of Story 1.

**Why this priority**: IMDERTY's own file carries several months, but a single month covers the monthly obligation. This is a convenience over Story 1.

**Independent Test**: Generate August to October for a test club and verify three month sheets whose contents are identical to three single-month downloads, plus the catalog sheet.

**Acceptance Scenarios**:

1. **Given** a range of months within the same year or across a year boundary, **When** the coach generates it, **Then** the workbook contains one sheet per month in chronological order, each identical in content to that month's single download.
2. **Given** an athlete who joined or left mid-period, **When** the workbook is generated, **Then** they appear only in the months in which they were active.
3. **Given** a range longer than 12 months, **When** the coach requests it, **Then** the request is refused with a message asking for a shorter range.

---

### Edge Cases

- **Athlete joined mid-month**: they appear in that month's sheet. Days before their join date stay blank.
- **Athlete deactivated or deleted during the month**: they appear in that month's sheet with the marks recorded while active. They do not appear in later months.
- **Activity happened, but the athlete has no attendance record** (not taken, or the athlete was added later): the cell stays blank, and the readiness panel lists it as "actividad sin registro de asistencia".
- **Multi-day club event** (e.g. a two-day outing): the single recorded status for the athlete applies to every day of the event that falls in the month.
- **Future or current month**: the sheet can be generated, and days after today stay blank. The screen warns that the month is not over.
- **Month without any activity**: the sheet is produced with every day blank and the header counters over the athlete list. The screen warns about it.
- **More athletes than the format's rows (about 480)**: generation is refused with a clear message. This is not expected at the club's size (about 20–40 athletes).
- **Official template revised by IMDERTY** (new version or code): the platform keeps producing version 006 until a platform update ships the new template. There is no in-app template upload. The code and version shown in the file always match the template actually used.
- **Names with diacritics or ñ**: text columns are written in upper case, keeping diacritics and ñ (e.g. "PEÑA").
- **Athlete with two guardians and no own phone**: the phone of the guardian marked "contacto principal" is used. With no mark, the first linked guardian's phone is used, and the readiness panel flags it.
- **Guardian marked as "contacto principal" is unlinked**: the mark disappears with the link, and the fallback rule applies.
- **Barrio catalog entry re-mapped after a sheet was generated**: earlier downloaded files are not affected (the platform does not keep them). New generations use the new mapping.
- **Sensitive-data authorization withdrawn between two generations**: the later sheet shows those three columns blank for that athlete.
- **Compound surnames** (e.g. "DE LA CRUZ"): they are kept whole in the first-surname or second-surname field, so the sheet never splits them.
- **Athlete with a single surname**: the second-surname cell stays blank, and this is not a readiness gap.
- **Header counter for sexual orientation**: it always shows zero, because the column is intentionally blank. This is expected and documented for the coach.

## Requirements *(mandatory)*

### Functional Requirements

**Athlete data**

- **FR-001**: The athlete record MUST hold first surname (required) and second surname (optional) as separate fields, plus: document type (official list: R.C, T.I, C.C, C.E, PPT, PEP, NES), document number, address, barrio, school/institution/group, grade, EPS and an optional athlete phone.
- **FR-001a**: For athletes that already exist, the system MUST propose a one-time split of the current surname text into first and second surname. The coach confirms or corrects it per athlete, and nothing changes without that confirmation. Until confirmed, the sheet uses the unsplit surname as the first surname, and the readiness panel flags it.
- **FR-002**: The barrio MUST be chosen from a single platform-wide Yumbo catalog maintained by the admin in which each barrio maps to a comuna (1–4) or zone (Zona Norte, Zona Centro, Zona Sur), or set to "Otro municipio". The comuna/zona MUST be derived from the catalog and never typed.
- **FR-003**: The catalog MUST be preloaded with the barrios of the official SECTOR sheet (82 unique entries after collapsing duplicate spellings). Only the admin can add, rename or re-map entries.
- **FR-004**: The system MUST warn, without blocking, when a document number duplicates another athlete's in the same club. It MUST accept only digits for R.C, T.I and C.C numbers.
- **FR-005**: Grade MUST be chosen from a list covering the Colombian school levels (prejardín, jardín, transición, 1.° to 11.°), plus "No escolarizado" and "Otro".
- **FR-006**: Ethnicity, disability type and armed-conflict victim status MUST be editable only while an express guardian authorization for sensitive data is on record for that athlete. The record MUST store the authorization date, the guardian who gave it, and who recorded it. The platform records only these facts. It provides no authorization text or form and stores no evidence file: obtaining and keeping the proof is the club's responsibility outside the platform.
- **FR-007**: When the sensitive-data authorization is withdrawn, the system MUST erase the three sensitive values and record the withdrawal.
- **FR-008**: The sensitive fields MUST offer exactly the options of the official lists, and default to "No informa" (ethnicity: "NO SABE NO RESPONDE"; disability: "N/A"; victim: no default, it must be chosen) when first authorized.
- **FR-009**: Sexual orientation MUST NOT be collected, stored or shown anywhere in the platform.
- **FR-010**: None of the new athlete fields MUST be visible to parent or athlete accounts, and none of them MUST be sent to any AI provider, included in newsletters, reports other than this sheet, analytics, logs, error messages or telemetry.

**Club settings**

- **FR-011**: The club MUST have IMDERTY settings: contractor name, training venue, training days, schedule, and one or more programs from the official program list to mark with "X". Admin and coach can edit them.
- **FR-012**: The download screen MUST prefill the settings and allow per-download edits that do not change the stored settings unless the user explicitly saves them.

**Sheet generation**

- **FR-013**: The system MUST generate the sheet for a single month, or for a range of up to 12 consecutive months as one workbook with one sheet per month (sheet name = month name in upper case), plus the barrio catalog sheet. The coach chooses at download time.
- **FR-014**: Each month sheet MUST list every athlete of the club who was active on at least one day of that month, ordered by first surname, second surname and first name, and numbered consecutively.
- **FR-015**: The file MUST reproduce the official format FO-GDD-057 v006: title block, code, version and format date, layout, header counters, dropdown lists, total formulas and styling. It MUST be regenerated per month with the correct weekday/day column headers and the reference date used for age.
- **FR-016**: Each day cell MUST be derived from the club's recorded activities on that date: executed trainings; club outings and joint trainings from the calendar; and competitions. The mapping MUST be: presente or tarde / attended → A; justificado or lesionado / excused → E; ausente / no-show → F. Days without any applicable activity for that athlete MUST be blank.
- **FR-017**: When several activities fall on the same day for one athlete, the cell MUST show one mark with precedence A > E > F.
- **FR-018**: Cancelled or planned-but-not-executed trainings, rest days, birthdays and personal (individual) training entries MUST NOT produce marks.
- **FR-019**: On a competition day, an athlete MUST be marked A when they have a recorded result in that competition **or** the coach marked them present at the competition event in the calendar. They MUST be marked E or F from the event's recorded status (excused / no-show) when neither applies. Athletes outside the event's audience and without a result stay blank.
- **FR-020**: Age MUST be the athlete's completed years at the first day of the sheet's month.
- **FR-021**: Text columns MUST be written in upper case, keeping diacritics and ñ. First name(s), first surname and second surname MUST come from their own fields, never from splitting text at generation time.
- **FR-022**: The phone column MUST show the athlete's phone when recorded; otherwise the phone of the guardian the coach marked as "contacto principal"; otherwise the phone of the first linked guardian (earliest link); otherwise blank.
- **FR-022a**: Admin and coach MUST be able to mark exactly one linked guardian per athlete as "contacto principal" in the IMDERTY section. The mark is optional, and athletes with two or more guardians and no mark appear in the readiness panel.
- **FR-023**: The sexual-orientation column MUST always be blank. The sensitive columns MUST be blank for athletes without an authorization on record.
- **FR-024**: The per-athlete third-party-sharing authorization MUST NOT gate inclusion in this sheet (owner decision: covered by the IMDERTY agreement).
- **FR-025**: Before download, the system MUST show a readiness panel listing, per athlete, missing document type or number, missing or uncatalogued barrio, missing EPS, missing phone (athlete and guardians), no linked guardian, unconfirmed surname split, and activities without an attendance record, each linked to where it can be fixed. Downloading MUST remain possible with gaps.
- **FR-026**: Generated files MUST be produced on demand and MUST NOT be stored by the platform.
- **FR-026a**: The official template MUST ship with the platform. Changing to a new IMDERTY version is done through a platform update, and no user can replace the template from the application.

**Access and audit**

- **FR-027**: Only admin and coach accounts of the club MUST be able to view or edit the new fields, the settings and the catalog, and to generate sheets. Every denied path MUST be verifiable.
- **FR-028**: Every generation MUST be recorded in the audit trail with who, when, which month(s), and counts (rows, readiness gaps), without any personal data of athletes.

**Devices**

- **FR-029**: The primary device for every screen of this feature is the desktop. Each screen (athlete IMDERTY section, sensitive block, barrio catalog, club settings, surname-split confirmation, download and readiness panel) MUST also adapt to 768 px and 360 px with no page-level horizontal scroll, multi-column lists turning into stacked cards on phones. Generating and downloading MUST work from a phone browser (constitution Principle III).

### Key Entities *(include if feature involves data)*

- **Athlete IMDERTY profile**: the non-sensitive identity and contact data the format requires, attached to an athlete: first and second surname as separate fields, document type and number, address, barrio (catalog reference or "other municipality"), school/institution/group, grade, EPS, optional own phone.
- **Sensitive-data authorization**: the guardian's express authorization for sensitive socio-demographic data for one athlete: who authorized, when, who recorded it, and its withdrawal, if any.
- **Sensitive socio-demographic data**: ethnicity, disability type and armed-conflict victim status for one athlete. It exists only while an authorization is in force. There is deliberately no sexual-orientation entity.
- **Barrio catalog entry**: a Yumbo barrio or sector name and the comuna (1–4) or zone it belongs to, maintained per club by the admin.
- **Club IMDERTY settings**: contractor, venue, days, schedule and marked program(s) for the club's sheet header.
- **Day attendance mark** (derived, not stored): for one athlete and one calendar day, the A/E/F/blank result of combining that day's applicable activities.
- **Sheet generation record**: the audit entry for one generation (actor, time, months, counts), with no participant data.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The coach produces a month's sheet for the whole group in under 5 minutes from opening the screen, with zero attendance cells typed by hand.
- **SC-002**: For any generated month, 100 % of day marks and per-row A/F/E totals, and every header counter, match the attendance recorded in the platform for that month. This is verified on a test club with at least one activity of each kind and every attendance status.
- **SC-003**: IMDERTY accepts the first generated monthly sheet without asking for corrections to its format.
- **SC-004**: When August 2026 is regenerated from the platform, every non-sensitive participant column matches the hand-made August sheet for the athletes present in both. Every difference in day marks is explained by the documented rules (blank days without activity, recorded statuses).
- **SC-005**: Within the first month of use, at least 90 % of active athletes show no readiness gaps.
- **SC-006**: No test, log, audit entry, fixture or AI request produced by this feature contains a real athlete's name, birth date, document number, address, EPS, phone or sensitive value. Sexual orientation is stored nowhere, which is verified by automated privacy checks.
- **SC-007**: Once the server is awake, a single-month sheet for 40 athletes is ready to download within 10 seconds, and a 5-month workbook within 30 seconds.

## Assumptions

- The club's size stays around 20–40 active athletes, far below the format's row capacity.
- "Active in the month" means the athlete was a member of the club (joined and not deactivated or deleted) on at least one day of that month.
- Guardian phones already exist on guardian accounts. If the relevant one is missing, the readiness panel reports it.
- Attendance statuses already recorded in the platform (per session and per calendar event) are the single source of truth. The feature adds no new way to take attendance.
- The official blank template (version 006, no participant data) can be kept with the platform. Any filled sheet, and the owner's reference workbook, never enter the repository.
- The program(s) marked in the header are the same for the whole club sheet, not per athlete.
- The express sensitive-data authorization, its wording and its proof (e.g. a signed paper) are obtained and kept by the club outside the platform (owner decision 2026-09-28). The platform only records date, guardian and recorder. A parent-portal authorization flow is out of scope.
- The IMDERTY agreement, as stated by the owner, is the legal basis for sharing the sheet with IMDERTY. This spec does not re-examine it.

## Out of Scope

- Sending the sheet to IMDERTY automatically; the coach delivers it.
- Other IMDERTY or funder formats, and changes to the existing monthly technical report.
- Uploading or importing any spreadsheet (profile data or historical attendance): the owner's workbook is only the format reference.
- Capture or authorization of the new data from the parent portal.
- Any use of the new fields in AI features, newsletters, dashboards or analytics.
- A registry of non-athlete participants.
