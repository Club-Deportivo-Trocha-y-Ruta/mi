# Quickstart — validating 047 IMDERTY monthly attendance sheet

Everything below uses **fictitious** athletes. Never use the owner's reference workbook in tests, and never commit it.

## Prerequisites

- Backend venv (`backend/.venv`) with `openpyxl` installed from `requirements.txt`.
- For local runs, follow the WeasyPrint/pytest note: use `python -m pytest` (see the project memory on the local environment).
- Frontend deps installed.
- Optional: MySQL for `pytest -m mysql`; Excel, LibreOffice or Google Sheets to open the generated file.

## 1. Automated checks (default lane, offline)

```bash
cd backend && source .venv/bin/activate
python -m pytest tests/imderty -q          # grid rules, workbook writer, RBAC, privacy
ruff check
cd ../frontend && npm run typecheck && npx vitest run src/routes/imderty src/components/imderty
```

Expected results:
- **Attendance grid**: every mapping in research R4 has a test, including precedence, the linked-event exclusion, multi-day events, activity windows, and short months.
- **Workbook writer**: the output reopens with openpyxl without errors. Table column names equal the row-23 headers. The barrio validation points at `SECTOR`. No sexual-orientation value is present. Sensitive cells are blank without authorization.
- **Access**: every route returns 403 for parent and athlete accounts, and for a coach of another club.
- **Parent view**: parent responses contain none of the new keys.
- **Template privacy test**: the committed template has no values in rows ≥ 24 and no header values.
- **Structural test**: no new model is imported by AI, LLM, race, newsletter or report modules.
- **Frontend**: jest-axe reports zero violations on the new pages and dialogs.

## 2. Migration lane

```bash
cd backend && alembic heads                # expect exactly one head before adding the migration
TEST_DATABASE_URL=mysql+aiomysql://…_test python -m pytest -m mysql -q
```

The migration must upgrade, seed 82 barrios (the official SECTOR sheet after collapsing duplicate spellings), and downgrade cleanly. If MySQL is not available in the session, report this lane as **pending**, not as passed.

## 3. Manual end-to-end (local, demo data — never the production DB)

1. `docker compose up`, then log in as a coach on the demo club.
2. **Datos IMDERTY section:**
   - Open a demo athlete and confirm the proposed surname split.
   - Fill in the document, barrio (the comuna fills itself in), school, grade and EPS.
   - Mark one guardian as "contacto principal".
3. **Sensitive data:**
   - Record an authorization; the fields show their defaults.
   - Set the values.
   - Withdraw the authorization; the values disappear.
4. **Club settings:** save contractor, venue, days, schedule and program.
5. **Generate a single month:**
   - Open *Planilla IMDERTY*.
   - Pick last month; the readiness panel lists the gaps.
   - Download.
   - Open the file in Excel or LibreOffice: the logo, layout and dropdowns are present, and the day headers match the month.
   - Check marks and totals against the platform, and check that the counters recalculate.
6. **Generate a period:** download a 3-month range. The sheets come in chronological order, and each sheet's content is identical to its single-month download.
7. **Phone check (Principle III):**
   - Repeat steps 2 and 5 at 360 px (device emulation or a real Android phone): no horizontal page scroll, the gaps appear as cards, and the numeric keypad opens for document and phone.
   - Download from the phone. Previewers without a calculation engine may show blank counters; that is expected (research R1). Opening the file in Excel or Sheets fixes it.

## 4. Post-deploy (owner)

- Smoke-check `/health`, then call one authenticated `GET /api/clubs/{id}/imderty-settings`.
- Regenerate August 2026 and compare its non-sensitive columns with the hand-made sheet, on the owner's machine only (SC-004).
- Deliver the first real sheet to IMDERTY and record whether it was accepted as-is (SC-003).
