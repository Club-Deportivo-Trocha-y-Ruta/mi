# Feature 003 — Individual Monthly Newsletter improvements

**Branch**: `003-improve-individual-newsletter-pdf` · **Date**: 2026-06-05

Improvements to the per-athlete Monthly Newsletter (email + attached PDF +
on-screen preview). No new tables, columns, or HTTP endpoints.

## US1 — Complete anthropometry (PDF)

- BMI now always shown (see [04-percentiles/003-lms-seed-and-backfill.md](../04-percentiles/003-lms-seed-and-backfill.md)).
- Genuinely-missing cells render a **plain-language reason** (español neutro, no
  diagnostic claims) instead of a bare `—`.
- Anthropometry stays **PDF-only** — never in the email body.

## US2 — Clean pagination (PDF)

- Headings are wrapped with their content using WeasyPrint-honored
  `break-inside: avoid` blocks; the "Evolución en la temporada" heading renders
  with its charts as one unit.
- Removed a forced `page-break-before: always` that opened a blank band; added
  `widows/orphans` to body text.
- **Removed the Ley 1581/2012 boxed legal notice** (explicit user decision,
  FR-019). ⚠️ Flagged for human/legal review before production — the `@page`
  running confidential footer and `.doc-footer` remain.

## US3 — Parent-friendly insight

- Per-block plain-language **captions**, a **"highlights of the month"** summary,
  and **"support at home"** guidance.
- AI-generated under the existing guardrails (name redaction, ≤80 words,
  medical-term block). When AI consent is missing or the LLM errors, a
  **deterministic static fallback** (`newsletter_static_copy.py`) still renders
  the newsletter; the legacy coach narrative stays consent-gated with a neutral
  placeholder.

## US4 — Modern, consistent UX/UI

- Responsive single-column **email** with inlined CSS, `lang="es-CO"`,
  `role="presentation"` layout tables, ≥16px body, ≥44px touch targets,
  dark-mode-safe colors — correct on a 360px viewport without media queries.
- PDF + React preview restyled on shared brand tokens; status never conveyed by
  color alone (text/icon pairing). WCAG AA; `jest-axe` zero violations.
- **Zero anthropometry** in the email/preview (enforced by tests).
