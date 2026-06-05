# Phase 1 Contracts: Improve Individual Monthly Newsletter

**Feature**: `003-improve-individual-newsletter-pdf` | **Date**: 2026-06-05

This feature exposes **no new public HTTP endpoints**. Its "contracts" are: (1) the existing newsletter endpoints whose behavior must remain stable, (2) the PDF/email/preview rendering contracts, (3) the seeding & backfill operational contracts, and (4) the extended AI use-case I/O. Each is testable.

---

## C1 — Existing newsletter endpoints (behavior-preserving)

No signature changes. Contracts that MUST continue to hold (regression-tested):

| Endpoint | Contract held |
|---|---|
| `GET /api/athletes/{id}/monthly-newsletters` | Response NEVER includes `pdf_only_blocks`, `sent_to`, `pdf_storage_url`; exposes `has_pdf: bool` |
| `GET …/{newsletterId}` | Email blocks only in JSON; anthropometry absent from email-equivalent payload |
| `POST …/monthly-newsletters` (generate) | Still honors consent gate for the AI narrative; now ALSO returns captions/highlights (AI) or static fallback |
| `GET …/{newsletterId}/pdf` | PDF contains anthropometry; email path never does; **no** Ley 1581 boxed block (FR-019) |
| `POST /api/clubs/{id}/monthly-newsletters/batch` | Multi-child grouping unchanged; one PDF per child, no cross-child leakage (FR-017) |

**Privacy invariants (must stay green):** no minor name in logs/AI output; consent honored; per-parent `userId` in query keys.

---

## C2 — PDF rendering contract (WeasyPrint)

**Given** a newsletter context with season-evolution charts and ≥1 anthropometric record,
**when** the PDF is rendered,
**then**:
- No `<h2>`/`<h3>` heading renders on a different page from its first content block. (FR-005)
- The "Evolución en la temporada" heading + 3-chart row render as one unit. (US2-AS1)
- No avoidable blank vertical gap larger than a normal section margin. (FR-007, SC-002)
- `@page` running header + `@bottom-right` page counter remain correctly placed on every page. (FR-008)
- The Ley 1581/2012 boxed block is absent; document ends cleanly. (FR-019, SC-010)

**Test approach:** render to PDF in a test, assert page count is reasonable, and assert (via WeasyPrint document box tree or pdf text-extraction per page) that the charts heading and chart content share a page and that no page except the last is <~30% filled where avoidable. Snapshot the absence of the Ley 1581 block string.

---

## C3 — Email rendering contract

**Given** any newsletter,
**when** the email body is rendered,
**then**:
- Single-column, `max-width: 600px`, layout correct without `@media` queries. (FR-013)
- All visual CSS inlined; `<style>` only progressive enhancement, <8192 chars, valid. (R5)
- NO anthropometric value anywhere in the email. (FR-004, SC-008)
- `lang="es-CO"`, layout tables `role="presentation"`, explicit colors, alt text on images.
- WCAG AA contrast; no meaning by color alone. (FR-015, SC-007)

**Test approach:** assert absence of anthropometry keys/values in rendered email; assert presence of `role="presentation"`, `lang`, inlined styles on key elements; run contrast check on the token palette.

---

## C4 — LMS seeding contract (operational)

**Command:** idempotent seeding step (extends `app/seed_growth_data.py` to read vendored CSVs).

- **Input:** vendored CDC CSVs committed under the backend (e.g., `backend/app/data/cdc_lms/*.csv`).
- **Effect:** upserts `growth_reference_lms` rows; re-running is a no-op (unique constraint).
- **Postcondition:** all six `(indicator, sex)` groups non-empty across 24–240.5 months.
- **Deploy:** invoked from `entrypoint.sh` after `alembic upgrade head`, guarded to run safely on every boot (idempotent) and to **not** depend on outbound internet.

**Test approach:** seed against aiosqlite from a small fixture CSV; assert row counts and a sample z-score computes to a known CDC value.

---

## C5 — Backfill contract (operational)

**Command:** idempotent backfill script (e.g., `python -m app.scripts.backfill_anthropometry` or equivalent).

- **Precondition:** LMS seeded (C4).
- **Effect:** for each `anthropometric_records` row with NULL `bmi`/percentiles but present raw measurements, compute + persist derived values; raw measurements untouched.
- **Idempotent:** already-populated rows skipped; safe to re-run.
- **Postcondition:** SC-001 holds for historical rows.

**Test approach:** insert records with NULL derived values + known raw values, run backfill, assert derived values match `growth.py` output and BMI = weight/height²; re-run asserts no change.

---

## C6 — Extended AI use-case I/O contract

`AthleteNewsletterUseCase.run(ctx)` returns the existing fields PLUS optional `block_captions: dict[str,str]` and `month_highlights: str`.

- **Guardrails:** new fields pass through `scrub_block` (≤80 words, medical-term block, name redaction). (Constitution AI rule)
- **Fallback:** on missing consent / LLM timeout / schema error, captions + highlights + support degrade to deterministic static strings; the newsletter still renders. (FR-009/FR-010)
- **Property test:** no real athlete name ever appears in any output field, including the new ones.

---

## Contract test matrix (maps to Constitution II)

| Contract | Happy path test | Negative/privacy test |
|---|---|---|
| C1 | generate + read returns email blocks | parent cannot see other child; no pdf_only in GET |
| C2 | charts heading+row same page | no Ley 1581 block; no orphan heading |
| C3 | single-column renders | zero anthropometry in email |
| C4 | seed populates groups | idempotent re-run no-op |
| C5 | backfill fills NULLs | raw untouched; re-run no-op |
| C6 | captions generated under guardrails | name redaction; static fallback on no consent |
