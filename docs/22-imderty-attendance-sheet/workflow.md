# IMDERTY monthly attendance sheet — Workflow

## Context

The Instituto Municipal de Deporte y Recreación de Yumbo (IMDERTY) is one of the club's
funders. Every month it requires the planilla de asistencia in its official format
**FO-GDD-057, version 006**. Before feature 047 the coach filled that spreadsheet by hand
from memory and paper notes. The platform already records attendance per training session,
per calendar event (club outings, joint trainings) and per competition, so feature 047
extends the athlete record with the identity fields IMDERTY's format requires and generates
the file directly from that recorded data.

This is a coach-facing operational tool, not a family-facing feature: parents never see the
new fields, and the sheet itself is downloaded and sent to IMDERTY outside the platform.

## Scope

- In scope: an "Datos IMDERTY" section on the athlete record (surnames, document, address,
  barrio/comuna, school/grade, EPS, phone precedence); sensitive-data fields (ethnicity,
  disability, armed-conflict victim status) behind an express-authorization gate; club-level
  IMDERTY header configuration; a monthly/period sheet generator that reads training,
  calendar-event and competition attendance and writes the official `.xlsx` format; a
  readiness check before download; audit trail with no personal-data values.
- Out of scope: sexual orientation (never collected); import from the club's existing
  workbook (removed in clarification, see `specs/047-imderty-attendance-sheet/spec.md`);
  a per-athlete "IMDERTY-only participant" registry (every participant is a regular athlete);
  AI use of any new field.

## Monthly routine (coach)

1. Once a month (or before a IMDERTY period), open each athlete's "Datos IMDERTY" section and
   fill or confirm surnames, document, address, barrio, school/grade, EPS and — if the
   athlete has two linked guardians — mark one as "contacto principal". This is a one-time
   setup per athlete; only new athletes or corrections need attention in later months.
2. For families that gave express authorization for sensitive data, record the authorization
   (guardian + date) once; the ethnicity/disability/armed-conflict fields default to
   "no informa" until a coach or admin sets them. Withdrawing the authorization deletes the
   stored values immediately.
3. Confirm the club's IMDERTY header (contractor, training venue, days, schedule, program)
   under club settings; adjust it per download if a detail changed for that period.
4. Open *Planilla IMDERTY*, pick the month (or a period of months), and read the readiness
   panel: it lists athletes with a missing identity field, an unresolved surname split, or no
   marked "contacto principal" guardian.
5. Download. The file has one sheet per requested month, filled from the training/calendar/
   competition attendance already recorded for that period — no retyping.
6. Send the file to IMDERTY through the club's usual channel (outside the platform).

## Acceptance criteria

- [x] Each athlete's day cell reflects the precedence A (presente/tarde) over E
      (justificado/lesionado) over F (ausente); days without club activity stay blank.
- [x] Age, age-band and sex counters are computed at the first day of the requested month.
- [x] Parent and athlete accounts, and a coach of another club, are denied access to the
      sheet screen and its data.
- [x] Sensitive fields render blank without an active authorization and are deleted (not just
      hidden) on withdrawal.
- [x] The generated file opens without a repair prompt in Excel/LibreOffice, keeps the barrio
      dropdown, and its day-column headers match the official format's convention (see
      `research.md` R3 in the spec folder).
- [x] The audit trail for export/write actions carries no personal-data values.
- [ ] Owner confirms the file is accepted by IMDERTY as-is on the first real delivery
      (post-deploy, manual — see `runbook.md`).

## References

- `specs/047-imderty-attendance-sheet/spec.md` — full scenarios and owner decisions.
- `specs/047-imderty-attendance-sheet/research.md` — R1–R11 (template fidelity, day headers,
  barrio catalog, sensitive-data isolation, "contacto principal").
- `backend/app/routers/imderty_sheet.py`, `backend/app/services/imderty/` — grid, workbook
  writer, readiness check.
- `backend/app/models/imderty.py`, `backend/app/schemas/imderty.py`.
- `frontend/src/routes/imderty/ImdertySheetPage.tsx`, `frontend/src/components/imderty/`.
- `docs/22-imderty-attendance-sheet/runbook.md`, `docs/22-imderty-attendance-sheet/qa.md`.
