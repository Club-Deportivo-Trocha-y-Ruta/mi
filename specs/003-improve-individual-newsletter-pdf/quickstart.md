# Quickstart: Improve Individual Monthly Newsletter

**Feature**: `003-improve-individual-newsletter-pdf` | **Branch**: `003-improve-individual-newsletter-pdf`

How to validate this feature end-to-end locally.

## Prerequisites

```bash
source backend/.venv/bin/activate
cd backend
```

## 1. Seed CDC LMS reference data (deterministic, vendored)

```bash
# Idempotent; reads vendored CSVs (no cdc.gov download). Safe to re-run.
python -m app.seed_growth_data        # after: alembic upgrade head
```
Expect: all six (indicator × sex) groups populated, 24–240.5 months.

## 2. Backfill existing anthropometric records

```bash
python -m app.scripts.backfill_anthropometry   # idempotent
```
Expect: rows with raw weight+height now have non-NULL BMI; rows in range get percentiles.

## 3. Generate a newsletter and inspect the PDF

```bash
cd backend && uvicorn app.main:app --reload
# Coach login: entrenador@trochyruta.com / Coach2026!
# POST /api/athletes/{id}/monthly-newsletters  (year, month)
# GET  /api/athletes/{id}/monthly-newsletters/{nid}/pdf  -> save & open
```
Verify in the PDF:
- [ ] Anthropometry table shows numeric BMI / percentiles / z-scores (no unexplained `—`). (US1)
- [ ] "Evolución en la temporada" heading sits on the same page as its charts; no near-empty page. (US2)
- [ ] No Ley 1581/2012 boxed block at the end. (FR-019)
- [ ] Page counter + running header correct on every page. (FR-008)
- [ ] Per-block captions + "highlights of the month" + a "support at home" tip present. (US3)

## 4. Inspect the email body (no PDF)

```bash
# Render the email template / use the dispatcher preview
```
Verify:
- [ ] Single column, readable on a 360px-wide viewport, no horizontal scroll. (US4)
- [ ] Zero anthropometric values in the email. (FR-004)
- [ ] `lang="es-CO"`, inlined styles, alt text. (R5)

## 5. Frontend preview consistency

```bash
cd frontend && npm run dev
# /training/athlete-newsletters  -> open a newsletter detail
```
Verify the on-screen preview matches the new email/PDF design and reuses shadcn/ui tokens. (FR-014)

## 6. Run the gates

```bash
cd backend && pytest           # incl. new privacy/pagination/backfill/seed tests
cd frontend && npm run test    # vitest + jest-axe (0 a11y violations)
cd frontend && npx tsc --noEmit
```

## Acceptance (maps to Success Criteria)

| Check | SC |
|---|---|
| 0 unexplained `—` for complete records (incl. history) | SC-001 |
| No blank gaps / no orphaned headings | SC-002 |
| Every block has a caption + ≥1 support tip | SC-004 |
| Email single-column, no h-scroll | SC-006 |
| 0 a11y contrast violations | SC-007 |
| 0 anthropometry in email; 0 cross-child leak | SC-008 |
| No diagnostic/ranking/discouraging language | SC-009 |
| 0 Ley 1581 boxed blocks in PDF | SC-010 |
