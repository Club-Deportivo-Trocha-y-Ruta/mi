# IMDERTY monthly attendance sheet — Ops runbook

## 1. Rebuilding the template when IMDERTY publishes a new format version

The platform ships a sanitized copy of the official workbook at
`backend/templates/documents/imderty/fo_gdd_057_v006.xlsx`. That file — never the owner's
reference workbook — is the only thing committed to the repo.

When IMDERTY publishes a new version of FO-GDD-057:

1. Get the new official workbook from IMDERTY (or the owner's filled copy of it). Keep it
   **outside the repo** at all times; it contains real participant data of minors.
2. Run the builder script against it:

   ```bash
   cd backend && source .venv/bin/activate
   python scripts/build_imderty_template.py /path/to/owners_workbook.xlsx
   ```

3. The script clears every participant cell (rows 24–504, all columns) and every header
   value on the reference month sheet, keeps the labels and formulas, clones the result into
   the 12 month sheets (`ENERO`…`DICIEMBRE`, each with its own table name and structured
   references), and rebuilds `SECTOR` from the seeded barrio catalog
   (`backend/app/models/imderty.py`, `imderty_barrios`).
4. If the script detects a non-formula value in rows ≥ 24 or any header value on the output,
   it exits with code 2 and does **not** write the template — that is the privacy guard
   described in `specs/047-imderty-attendance-sheet/research.md` R2. Do not bypass it; find
   and fix the cell it flagged in the source workbook copy instead.
5. Confirm the update against `tests/imderty/test_workbook.py` and the template-privacy test
   before committing the new `.xlsx` (rows ≥ 24 empty, no header values, barrio validation
   still points at `SECTOR!$A$2:$A$<n>`).
6. Commit only the regenerated `.xlsx` under `backend/templates/documents/imderty/`. Never
   commit the owner's source workbook, and never paste its cell values into a commit message,
   PR description, or chat.

There is no in-app upload screen for this — template updates go out through a platform
release, per the owner decision recorded in `specs/047-imderty-attendance-sheet/spec.md`.

## 2. Phone-previewer blank-counter limitation

`openpyxl` writes formulas without cached values. Excel, LibreOffice and Google Sheets
recalculate on open (the workbook has `fullCalcOnLoad=True`), so the header counters and
per-row A/F/E totals populate correctly there. Some phone file previewers (the built-in
Android/iOS "quick look" panes, not a full spreadsheet app) have no calculation engine and
render those cells blank on first look.

This is expected and not a bug — see `specs/047-imderty-attendance-sheet/research.md` R1 and
R11. Guidance for the coach: open the downloaded file in the Excel, LibreOffice or Google
Sheets app (not the phone's file preview) to see the counters recalculate.

## 3. Sensitive-authorization custody note

The platform records only the **fact** of the guardian's express authorization for sensitive
data (ethnicity, disability type, armed-conflict victim status): the authorizing guardian and
the date, in `athlete_sensitive_authorizations`. It does not store the authorization wording
or a scanned/signed proof.

The club keeps the physical or otherwise-recorded proof of that authorization **outside the
platform**, per the owner decision in `specs/047-imderty-attendance-sheet/spec.md`
("Clarifications" session 2026-09-28). If a question ever arises about whether a given
authorization was properly obtained, the answer is not in the platform — it is in the club's
own custody of that proof. Withdrawing the authorization in the platform deletes the stored
field values (`athlete_sensitive_data` row) in the same transaction, with an audit entry that
carries no values (`AuditReasonCode.withdrawn`).

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Header counters show 0 or blank right after download | Phone previewer with no calc engine | See §2; open in Excel/LibreOffice/Sheets |
| Excel shows a "repair" prompt on open | Day-header text and the Excel table column name drifted apart | Re-check `workbook.py` writes both together (research R3); regenerate from a clean template |
| Barrio dropdown missing or not pointing at `SECTOR` | Template built with a plain `copy_worksheet` instead of the XML-level builder | Rebuild with `scripts/build_imderty_template.py` (§1), never `openpyxl.copy_worksheet` |
| Readiness panel flags "no contacto principal" for an athlete with one guardian | Expected — single-guardian athletes still need an explicit mark once two guardians could exist | Coach marks the guardian in `PrimaryContactSelect` |
| A club's `SECTOR` comuna looks wrong for "Otro municipio" | Working as designed — zone cell is the formula `=""`, not blank, so `VLOOKUP` doesn't fall through to 0 | No action; see research R6 |

## Contacts and escalation

- Product/spec owner: the club coach (owner of the feature spec and IMDERTY relationship).
- Technical owner: see `docs/implementation-status.md` for the feature-047 entry and current
  branch/commit state.
- IMDERTY itself: contacted through the club's usual channel, outside the platform.
