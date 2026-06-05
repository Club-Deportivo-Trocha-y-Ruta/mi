# Phase 0 Research: Improve Individual Monthly Newsletter

**Feature**: `003-improve-individual-newsletter-pdf` | **Date**: 2026-06-05

This document resolves the open technical questions for the four user stories, grounded in (a) direct inspection of the existing code and (b) external best-practice research via context7 (WeasyPrint docs) and web search (email + CDC growth data).

---

## R1 — Root cause of the empty anthropometric cells (US1)

**Finding (code-verified):**
- `newsletter_builder._build_anthropometry_block` already wires `bmi`, `height_z_score`, `height_percentile`, `bmi_z_score`, `bmi_percentile`, `weight_*` from `AnthropometricRecord` into the template (`newsletter_builder.py:687–692`). The template renders `—` when these are `None`.
- The columns are **NULL in storage**. On capture, `routers/anthropometry.py:128–175` calls `calculate_growth_percentiles(...)`; when the `growth_reference_lms` table is empty it returns no z-scores, the code sets `growth = None` (`anthropometry.py:146`), and then writes `NULL` for **all** percentile fields **and for `bmi`** (`bmi=growth.bmi if growth else None`, line ~169).
- `growth_reference_lms` is populated only by `app/seed_growth_data.py`, a **manual** script (`python -m app.seed_growth_data`) that **downloads CDC CSVs at runtime** from `cdc.gov`. It is **not** wired into `entrypoint.sh` or the dev seed, and seed does not run in production → the table is empty in prod → NULLs.

**Decision:**
1. **Decouple BMI** — compute `bmi = weight_kg / (height_m**2)` unconditionally on capture and persist it, independent of LMS availability. BMI never needs a reference table. (FR-001a)
2. **Make LMS reference data available in production deterministically** — vendor the three CDC LMS CSVs into the repo as committed data files and load them via an idempotent seeding step that runs on deploy (not a live `cdc.gov` download). Reuse the existing `seed_growth_data` parsing logic but read from the vendored files. (FR-001b)
3. **Backfill** existing records — a one-time, idempotent data script/migration that, for every `AnthropometricRecord` with NULL derived values, recomputes BMI + percentiles + z-scores from the stored raw measurements (using the same `growth.py` math) and persists them, without touching raw measurements. (FR-001c)

**Rationale:** The scientific math already exists (`services/growth.py`, `services/phv.py`); the defect is missing reference data + a BMI-coupling bug, not missing science. Vendoring the CSV avoids a fragile network dependency during Render deploys (free tier, cold start) and keeps seeding deterministic and testable.

**Alternatives considered:**
- *Keep live cdc.gov download in deploy* — rejected: non-deterministic, network-dependent, fails offline/CI, slows cold start.
- *Compute percentiles lazily in the newsletter builder at render time* — rejected: duplicates persistence logic, re-computes every render, leaves the DB inconsistent for other consumers (anthropometry GET, AI context, technical report).
- *Wire-through only (original clarification)* — rejected by the user after the root cause was surfaced; it would leave the sample PDF mostly dashes.

**Privacy note:** The CDC LMS table contains only population reference constants (L/M/S by age/sex) — no minor data. Backfill reads/writes only derived stats already classified as sensitive; it runs server-side with no new exposure.

---

## R2 — Eliminating page-break gaps & orphaned headings (US2)

**Finding (code-verified):** The PDF uses WeasyPrint ≥62.3 with CSS Paged Media (`base/layout.html`: `@page` with running header via `position: running(page_header)` and `@bottom-left`/`@bottom-right` counters). The season-evolution charts are a `display: table; table-layout: fixed` row (`athlete_monthly_newsletter.html:542–555`) with **no** `page-break-inside: avoid`, and the percentile-curves section forces `page-break-before: always` (`:643`). Either can strand a heading or open a near-full-page gap.

**Decision (context7 + web research):**
- Wrap each heading **together with its content** in a plain **block** container and apply `break-inside: avoid` to the wrapper; add `break-after: avoid` to the heading as defense-in-depth. Apply to: the "Evolución en la temporada" heading + charts row, KPI card row, narrative card, badges box, and each anthropometry sub-block.
- **Do not** put `break-inside: avoid` directly on the `display: table` row — WeasyPrint **ignores** `break-inside` inside `display:table` cells / on `tr`. The wrapper must be a normal block.
- **Remove** the hard `page-break-before: always` on the percentile section; rely on natural flow + `break-inside: avoid` grouping so a new page starts only when the current one is genuinely full. Reserve a forced break only for a true "start on new page" boundary if one is ever required.
- Set `widows: 2; orphans: 2;` on body text.
- Keep wrappers **smaller than one printable page**; `break-inside: avoid` is a hint that WeasyPrint drops when content can't fit, so very tall groups (e.g., the full longitudinal table) should remain breakable while their *headings* stay attached.

**Rationale:** Matches WeasyPrint's documented fragmentation support (CSS Fragmentation L3/L4 + legacy `page-break-*` aliases are equivalent) and known engine behavior (break-inside ignored on table internals). Grouping + removing forced breaks is the canonical fix for "title alone at page bottom" and "near-empty page."

**Alternatives considered:** `break-inside: avoid` on the table itself (rejected — ignored on table layout); keeping the forced break (rejected — it is the direct cause of one blank band); JS/headless-Chrome rendering (rejected — out of stack, heavier, unnecessary).

**Gotchas to honor:** background colors don't slice across breaks (`box-decoration-break: slice` repeats), so don't rely on a continuous background across a page boundary; SVG-in-table-cell paginates with the table — another reason to wrap, not split.

Sources: context7 `/websites/doc_courtbouillon_weasyprint_stable`; Kozea/WeasyPrint issues #209, #1547, #2456, #333.

---

## R3 — Removing the Ley 1581 footer block (US4 / FR-019)

**Finding:** The boxed "Información confidencial — Ley 1581/2012 (Habeas Data)" block is `athlete_monthly_newsletter.html:758–768`, isolated from `base/layout.html`. The separate, smaller running notice (`@bottom-left`: "Documento confidencial — datos de menor de edad protegidos.") and the `.doc-footer` line are **not** part of the block the user asked to remove.

**Decision:** Delete the boxed block from the newsletter template only. Leave the `@page` running footer and `.doc-footer` as-is unless the user later asks otherwise. Verify removal leaves no empty container/trailing whitespace (the preceding section already has `margin-bottom`).

**Recorded risk:** Removing this legal notice from a minor's sensitive-data document is a user-owned decision documented in spec Clarifications/Assumptions; it contradicts the original FR-018 (revised). No code-level mitigation; flagged for human/legal review at PR time.

---

## R4 — Extending the AI use case for captions, highlights & "support at home" (US3)

**Finding (code-verified):**
- `AthleteNewsletterUseCase.run()` returns `{strengths, area_to_develop, milestone, confidence, model, prompt_version}` (`use_cases/athlete_monthly_newsletter.py:50–58, 234–314`) under `AthleteNewsletterGuardrails` (80-word/block cap, medical-term regex block, name redaction via `_redact_names`).
- Consent gate `assert_ai_consent_for_newsletter` (`privacy.py:204–227`) currently **raises HTTP 409 with no static fallback** — without consent the whole newsletter fails.
- `support_at_home` is **static/templated** today (`newsletter_builder._build_support_block:610–654`, 4 fixed tips). There are **no** per-block captions today.

**Decision:**
- Extend the use case output schema with optional `block_captions` (short plain-language line per data block) and a `month_highlights` summary, produced under the **same** guardrails (extend the `.j2` prompt + add keys, keep the 80-word cap and name redaction). Keep `support_at_home` content but allow the AI to select/adapt which static tips are surfaced (tips stay from a fixed, vetted library to avoid medical drift).
- **Introduce a static/deterministic fallback** (per FR-009/FR-010): when AI consent is missing or the LLM errors/times out, captions/highlights/support degrade to deterministic templated text instead of failing the newsletter. This changes the current hard-fail behavior for the *captions/highlights* path; the existing `strengths/area/milestone` narrative retains its consent gate but the document still renders with static captions. (Confirm the exact gate behavior for the legacy narrative in planning — see Open Items.)

**Rationale:** Reuses the audited guardrail + forbidden-names pipeline (Constitution AI rule) rather than inventing a parallel one. Static fallback satisfies the spec requirement that the newsletter still generates without consent and keeps parents served on the free tier even when the LLM is cold/unavailable.

**Alternatives considered:** A second AI use case just for captions (rejected — duplicates guardrails, rule-of-three not met); fully static captions with no AI (rejected — the clarification chose AI-with-fallback); coach-authored captions only (rejected — too much manual burden monthly).

---

## R5 — Responsive email + UX/UI consistency across PDF, email, and on-screen preview (US4)

**Finding (code-verified):** `templates/email/athlete_monthly_newsletter.html` is already table-based, single-column, `max-width: 580px`, CSS in a `<style>` block (not fully inlined), with header/badges/attendance/race/AI-narrative/PDF-CTA/Ley-1581 sections, multi-child loop. Frontend preview is `NewsletterPreviewBlocks.tsx` (renders `email_blocks` only — correctly excludes anthropometry), detail page `AthleteNewsletterDetailPage.tsx`, narrative editor `NewsletterNarrativeEditor.tsx`; shared shadcn/ui (`Card`, `Badge`, `Tooltip`, `Dialog`) + Tailwind tokens (`charcoal`, `mid-gray`, brand lime).

**Decision (web research):**
- Email: keep table-based single-column; **inline all visual CSS** (move the critical color/font/padding declarations inline; keep `<style>` only for `@media` + dark-mode as progressive enhancement, under 8192 chars, valid syntax). Ensure the base inline layout is mobile-correct **without** media queries (Gmail Android strips them). Bump body to ≥16px, line-height 1.4–1.5, touch targets ≥44px, max-width 600px. Add `lang="es-CO"`, `role="presentation"` on layout tables, explicit colors everywhere (+ `color-scheme` meta) so dark-mode inversion stays legible, alt text on images, key info as live text. **No** sensitive minor data in body (unchanged).
- Visual consistency: align email + PDF + frontend preview on the shared brand tokens already in `base/layout.html` (`--brand-lime #8be000`, charcoal, gray scale, 4pt spacing grid) and the frontend Tailwind equivalents. Per-block captions (R4) render in all three surfaces. Reuse existing shadcn/ui components for the preview restyle (Constitution III — no new component patterns without justification).
- Accessibility: WCAG 2.1 AA contrast (Constitution III floor), no meaning by color alone (pair status colors with text/icon), `jest-axe` zero violations on preview/detail pages.

**Rationale:** Smallest-change path to Constitution III consistency and the spec's mobile-readability + accessibility criteria; reuses the design system already in place.

**Alternatives considered:** MJML/build-step email (rejected — adds tooling outside the current hand-written Jinja flow); CSS-grid/flex email layout (rejected — stripped by Gmail/Outlook).

Sources: Cerberus hybrid templates; Email on Acid (fluid-hybrid, Gmail 8192-char limit); Litmus (dark mode, accessible emails); Uplers (`#FDFDFD` Apple flip).

---

## Open items carried into Phase 1 / planning

- Confirm exact desired behavior of the **legacy `strengths/area/milestone` narrative** when consent is missing: does it also degrade to static, or stay gated while only captions/highlights/support fall back? (Spec FR-009/010 require the *captions/highlights/support* to fall back; the legacy narrative's consent gate is a separate, pre-existing control.) Default assumption for the plan: keep the legacy narrative consent-gated, render the rest with static fallback, and surface a neutral "valoración del entrenador no disponible este mes" placeholder.
- Confirm whether backfill should run as an Alembic data migration vs a standalone idempotent script invoked from `entrypoint.sh`. Default: standalone idempotent script + deploy-time invocation, to keep schema migrations free of heavy row updates and allow safe re-runs.
