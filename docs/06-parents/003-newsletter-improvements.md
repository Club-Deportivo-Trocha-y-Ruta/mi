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

## Season evolution charts read cup and championships separately (feature 039, 2026-09-03)

- The "Evolución en la temporada" section (PDF only) now shows one set of
  three charts (position per round, gap to the winner, accumulated points)
  **per cup** the athlete raced, each headed `Evolución en la {nombre de la
  copa}`. A season with two cups renders two chart sets, each with only its
  own rounds — a cup round from one cup never appears on the other cup's
  chart.
- Below the cup charts, a **"Campeonatos"** block shows one card per
  departmental or national championship the athlete raced in the season:
  position, size of the field in their category, gap to the winner (%) and
  percentile within that field, plus a short note in español neutro
  explaining that a championship gathers a different field and is read on
  its own — it is never plotted on the same line as the cup rounds.
- When the athlete did not finish a championship, the card shows a calm "No
  completó la prueba" state instead of numbers.
- The block appears only when the athlete raced a championship that season;
  it is absent otherwise. Likewise, the cup evolution charts appear only
  when the athlete raced at least one cup round — a season with only
  championships shows the "Campeonatos" block with no chart above it.
- This section no longer depends on a growth measurement being recorded in
  the reporting month (it used to be nested inside the anthropometry annex);
  it now lives on its own page. Both the cup charts and the "Campeonatos"
  block share the same reporting-month gate as the rest of the newsletter
  (same rule as feature 038): they only render in a month where the athlete
  actually raced (any cup round or championship, not necessarily the one
  shown) — a month with no race shows neither block. Once the section
  renders, its content still covers the season to date, not just the
  reporting month: each cup chart plots every round of that cup raced so
  far, and a championship card reflects that one race whenever it falls
  earlier in the same season.
- Coach-facing detail: `specs/039-season-comparison-groups/spec.md` and
  `docs/implementation-status.md`'s own entry for this feature. The same
  cup-vs-championship separation also reaches the athlete detail's
  "Competencia" selector and the AI-generated insights, so the newsletter,
  the coach view and the AI narrative never contradict each other.
