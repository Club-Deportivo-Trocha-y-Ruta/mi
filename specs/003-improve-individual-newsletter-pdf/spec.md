# Feature Specification: Improve Individual Monthly Newsletter (PDF + parent delivery)

**Feature Branch**: `003-improve-individual-newsletter-pdf`

**Created**: 2026-06-05

**Status**: Draft

**Input**: User description: "Improve the file boletin-2-2026-05.pdf. We need to show all about the Anthropometric & Maturation tracking section (Image #1), improve the white jump between pages (Image #2). And research for better insight for delivering this with the parents. Also improve the UX/UI of that report or newsletters."

## Overview

The Individual Monthly Newsletter (Phase 1.8) delivers each athlete's monthly summary to their family as an HTML email plus an attached confidential PDF. Two concrete defects and two improvement themes were observed in the production sample `boletin-2-2026-05.pdf`:

1. **Incomplete anthropometric section** — the "Seguimiento Antropométrico y Maduración" table renders several derived metrics (IMC, Z-Talla, P-Talla, Z-IMC, P-IMC) as empty dashes (`—`) even though weight, height, PHV offset and maturation status are present. The family receives a half-empty table that looks broken and omits the growth/maturation insight that is the section's purpose.
2. **Large blank vertical gap across page breaks** — the season-evolution charts ("Posición por válida", "Gap al P1 %", "Puntos acumulados") render their titles at the bottom of one page with the chart bodies pushed to the next page, leaving an oversized white band. The document looks unfinished and wastes a near-empty page.
3. **Weak parent-facing insight** — the report presents data but does little to help non-technical parents understand what it *means* for their child and what to do next.
4. **Inconsistent / dated UX-UI** — visual hierarchy, readability on mobile email clients, and overall polish of the newsletter (email body + PDF) can be improved.

This feature fixes the two defects and raises the quality of the parent-facing experience, without changing the strict privacy contract already in place (anthropometry only in the PDF, never in the email body; no other athlete's data exposed to a parent).

## Clarifications

### Session 2026-06-05

- Q: What is the underlying cause of the empty BMI/percentile/z-score cells the fix must address? → A: The derived values are already stored on the anthropometric record; the fix is to wire them through to the newsletter (no new percentile/z-score computation in scope).
- Q: How should the new parent-facing captions, "highlights of the month" summary, and "support at home" guidance be produced? → A: Extend the existing `athlete_monthly_newsletter` AI use case (same guardrails + consent gate), with a static/deterministic fallback when AI consent is missing or AI is unavailable.
- Q: Does the UX/UI improvement include the on-screen frontend preview, or only the delivered email + PDF? → A: Include all three — PDF, email, and the React on-screen preview/detail pages must share the new design and stay consistent.
- Q: Is the ≥70% page-fill target a hard acceptance gate or a guideline? → A: Guideline. The hard pass/fail gates are "no oversized blank gap" and "no heading separated from its content" (SC-002); page-fill is aspirational guidance.
- Q: Verified root cause of the empty anthropometric cells — the derived values are NULL in storage because the CDC/WHO LMS reference table is unpopulated in production and BMI is nulled alongside the percentiles. How far should the fix go? → A: **Full fix** (supersedes the earlier "wire-through only" answer, which was based on the incorrect premise that values were already stored): seed the CDC LMS reference data in production, decouple BMI so it always computes from weight & height, recompute & persist percentiles on capture, and backfill existing records so historical rows also display values.
- Q: Should the Ley 1581/2012 (Habeas Data) confidentiality footer block be kept, restyled, or removed from the PDF? → A: Remove the block from the PDF entirely. The user made this decision after being explicitly advised that it removes the legal Habeas Data notice from a document containing a minor's sensitive data and contradicts the original FR-018; FR-018 is revised accordingly and the legal risk is acknowledged by the user.
- Q: When AI consent is missing, does newsletter generation succeed with static fallback or still hard-fail with HTTP 409? → A: Generation **succeeds**. Static/deterministic captions, highlights, and support tips render, and the newsletter (email + PDF + preview) is produced. Only the personalized **AI-authored** content (the legacy `strengths`/`area_to_develop`/`milestone` narrative and any AI-authored captions/highlights) is suppressed and replaced with neutral placeholders/static copy. The existing consent gate no longer fails the whole newsletter — it gates only the AI-authored content, not document generation.
- Q: If the deploy-time anthropometry backfill errors mid-run, should it fail startup or log-and-continue? → A: **Log and continue** (non-fatal), mirroring the seed step. The backfill error is caught, logged as a summary count with no athlete identifiers, and startup proceeds; because the backfill is idempotent, the next boot retries the still-unfilled rows. The backend MUST stay up, and any record still missing a derived value renders as `—` with a plain-language reason until a later boot fills it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Complete, trustworthy anthropometric & maturation section (Priority: P1)

A parent opens the attached PDF and reads the "Seguimiento Antropométrico y Maduración" section. Every measurement row shows the full set of values it can support — weight, height, BMI, height/BMI percentiles and z-scores, PHV offset, and maturation stage — so the family sees a complete, professional growth-tracking picture rather than a table full of dashes.

**Why this priority**: This is the section the user explicitly pointed to ("show all about"). It is the unique medical/maturation value of the PDF and the most visible defect. A half-empty table erodes trust in the whole product.

**Independent Test**: Generate a newsletter for an athlete who has at least one anthropometric record with weight, height and date of birth, and confirm that the rendered PDF shows numeric values (not `—`) for every derived metric that is mathematically computable from the available inputs, with dashes appearing only where an input is genuinely missing.

**Acceptance Scenarios**:

1. **Given** an athlete with a recorded weight, height, sex and date of birth, **When** the newsletter PDF is generated, **Then** the anthropometric row displays computed BMI, height percentile & z-score, BMI percentile & z-score, PHV offset and maturation stage as numbers (none of these appear as `—` solely because they were not computed).
2. **Given** an athlete with multiple historical records, **When** the PDF is generated, **Then** the longitudinal table lists each record chronologically with the latest highlighted, and a plain-language reading of the latest measurement (what the maturation stage means for training) is shown alongside the numbers.
3. **Given** a record that is genuinely missing an input (e.g., no height captured that day), **When** the PDF is generated, **Then** only the metrics that depend on that missing input show `—`, and a short note explains the value is unavailable because the measurement was not recorded.
4. **Given** any anthropometric content, **When** the email body is generated, **Then** no anthropometric value appears in the email (it remains PDF-only).

---

### User Story 2 - Clean page layout without oversized blank gaps (Priority: P1)

A parent scrolls through the PDF and sees content that flows naturally page to page. Section headings stay attached to the content they introduce, and charts render as complete groups on a single page instead of being split with their titles stranded on the previous page.

**Why this priority**: The blank-page defect is the second item the user explicitly flagged. It makes the deliverable look broken and unprofessional, and it is independently fixable and testable.

**Independent Test**: Generate a newsletter PDF that contains the season-evolution charts and visually/programmatically confirm there is no blank vertical gap larger than a normal section margin, and that no chart title appears on a different page from its chart.

**Acceptance Scenarios**:

1. **Given** the season-evolution charts block, **When** the PDF is rendered, **Then** the "Evolución en la temporada" heading and all three charts appear together as one unit (the heading never sits alone at the bottom of a page with charts on the next).
2. **Given** any section that does not fit in the remaining space on a page, **When** it moves to the next page, **Then** the leftover space on the prior page is only normal margin/whitespace, not an oversized empty band approaching a full page height.
3. **Given** a multi-page PDF, **When** rendered, **Then** every page (except possibly the last) is substantially filled, and the page footer/page-count remains correctly positioned at the bottom of each page.

---

### User Story 3 - Parent-friendly insight and guidance (Priority: P2)

A non-technical parent reads the newsletter and immediately understands how their child is doing, what improved or needs attention this month, and one or two concrete things they can do at home — without needing to interpret raw numbers, percentiles or charts on their own.

**Why this priority**: Adds durable value beyond fixing defects and directly addresses the user's "research for better insight for delivering this with the parents." It depends on the data being complete (Stories 1–2) but is a distinct slice.

**Independent Test**: Show the generated newsletter to a parent persona and confirm that each data block carries a one-line plain-language interpretation, and that the report includes a short "what this means / how to help" summary, all in neutral Colombian Spanish and free of medical-diagnostic or comparative-judgment language about the minor.

**Acceptance Scenarios**:

1. **Given** any metric block (attendance, technical, competition, growth), **When** the newsletter is rendered, **Then** each block includes a short plain-language caption explaining what the number means in everyday terms.
2. **Given** the month's data, **When** the newsletter is rendered, **Then** it presents a concise "highlights of the month" summary and at least one concrete, age-appropriate "how to support at home" suggestion.
3. **Given** the minor's privacy rules, **When** any narrative or caption is produced, **Then** it never includes diagnostic claims, never ranks the child against named peers, and never uses discouraging or fear-based language.
4. **Given** low-confidence data (few sessions/races), **When** the newsletter is rendered, **Then** the limited-data context is communicated honestly and reassuringly rather than as a deficiency of the child.

---

### User Story 4 - Modern, readable UX/UI on email and PDF (Priority: P3)

A parent receiving the email on an Android phone over a slow connection, and later opening the PDF, experiences a clean, well-organized, easy-to-scan layout with clear hierarchy, comfortable typography, and a consistent visual identity across the email and the PDF.

**Why this priority**: Polish that lifts perceived quality across the whole deliverable. Valuable but lower urgency than correctness defects. Scope spans all three surfaces: the PDF, the email, and the on-screen frontend preview/detail pages, which must stay visually consistent.

**Independent Test**: Review the email in common mobile email clients and the PDF, confirming consistent branding, legible type sizes, clear section separation, accessible color contrast, and a layout that reads well on a narrow mobile viewport and on A4 print.

**Acceptance Scenarios**:

1. **Given** the email body on a mobile client, **When** opened, **Then** content is single-column, readable without horizontal scrolling, and key information is visible without opening the PDF.
2. **Given** the PDF, **When** opened, **Then** sections have consistent spacing, headings, and a clear visual hierarchy, and the brand identity (logo, color, typography) matches the email.
3. **Given** the design system already used by the product, **When** the newsletter is restyled, **Then** it reuses existing tokens/components and remains visually consistent with the rest of the platform.
4. **Given** accessibility expectations, **When** the newsletter is reviewed, **Then** text/background color contrast meets the established accessibility standard and information is not conveyed by color alone.
5. **Given** the previous Ley 1581/2012 (Habeas Data) confidentiality footer block, **When** the PDF is generated, **Then** that block no longer appears and the document ends cleanly without an empty container or trailing blank space.

---

### Edge Cases

- Athlete with **no anthropometric records at all** → the section is omitted gracefully (no empty table, no broken layout).
- Record present but missing **date of birth / sex** needed for percentile & z-score computation → metrics that require it show `—` with a clear, non-alarming reason; PHV/maturation still shown if computable.
- Athlete with **no competition results** → season-evolution charts block is omitted without leaving a blank page.
- **Single** anthropometric record (no history) → longitudinal view still renders cleanly without implying a trend.
- **Multi-child family** → grouped email still attaches one correct PDF per child; one child's data never leaks into another's section.
- Very long narrative or many records → content paginates without oversized gaps; the Ley 1581/2012 footer block is removed per FR-019 and is therefore not rendered on any page.
- Missing consent for AI narrative → newsletter generation **succeeds** (HTTP 200, document produced): static/deterministic captions, highlights, and support tips render, and the AI-authored narrative fields are suppressed/replaced with neutral placeholders. The consent gate withholds AI-authored content but MUST NOT return HTTP 409 for the document generation itself.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The newsletter PDF MUST display every anthropometric/maturation metric for each record (BMI, height percentile, height z-score, BMI percentile, BMI z-score, PHV offset, age-at-PHV, maturation stage). Per the 2026-06-05 full-fix decision, the values MUST be present in storage (not NULL) for records whose raw measurements support them, and MUST be wired through to the template; `—` appears only when the raw input is genuinely missing.
- **FR-002**: When a derived metric cannot be shown because a raw input is genuinely missing, the newsletter MUST indicate the reason in plain language (e.g., the measurement was not recorded) rather than leaving an unexplained dash.
- **FR-001a**: BMI MUST be computed and displayed from weight and height for every record that has both, independent of whether the CDC/WHO LMS reference table is available (BMI MUST NOT be nulled when percentiles cannot be computed).
- **FR-001b**: The CDC/WHO LMS reference data MUST be available in production so that height/BMI/weight percentiles and z-scores are computed and persisted when a measurement is captured.
- **FR-001c**: Existing anthropometric records whose percentiles/BMI were stored as NULL due to the previously-unpopulated reference table MUST be backfilled so historical rows also display values, without altering the original raw measurements. The backfill MUST be idempotent; when run at deploy time, a backfill error MUST be non-fatal (logged as a summary count with no athlete identifiers) so it cannot crash startup, and a later boot retries the still-unfilled rows.
- **FR-003**: The anthropometric section MUST include a plain-language interpretation of the latest measurement (what the maturation stage implies pedagogically) without making medical-diagnostic claims.
- **FR-004**: Anthropometric data MUST remain exclusively in the PDF and MUST NOT appear in the email body, preserving the existing privacy contract.
- **FR-005**: Section headings MUST stay attached to the content they introduce; a heading MUST NOT render on a different page from its first content block.
- **FR-006**: Grouped visual units (the season-evolution charts row, KPI cards, narrative cards, growth-percentile charts) MUST render together on a single page and MUST NOT be split such that an oversized blank gap is produced.
- **FR-007**: The PDF MUST NOT contain blank vertical gaps larger than a normal section margin caused by avoidable page breaks; pages other than the last MUST be substantially filled.
- **FR-008**: Page footer and page-count elements MUST remain correctly positioned at the bottom of every page after the layout changes.
- **FR-009**: Each data block (attendance, technical, competition, growth) MUST carry a concise plain-language caption explaining what its numbers mean for the family. Captions and narrative MUST be produced by extending the existing `athlete_monthly_newsletter` AI use case under its current guardrails and consent gate, with a static/deterministic fallback when AI consent is missing or AI is unavailable.
- **FR-010**: The newsletter MUST include a concise "highlights of the month" summary and at least one concrete, age-appropriate "how to support at home" suggestion, generated via the same AI-with-static-fallback path as FR-009.
- **FR-011**: All parent-facing copy MUST be in neutral Colombian Spanish and MUST avoid diagnostic claims, peer-ranking against named individuals, and discouraging/fear-based language about the minor.
- **FR-012**: Low-confidence (limited-data) situations MUST be communicated honestly and reassuringly, framed as context rather than as a shortcoming of the child.
- **FR-013**: The email body MUST be single-column, mobile-readable without horizontal scrolling, and surface the month's key information before the PDF is opened.
- **FR-014**: The email, the PDF, and the on-screen frontend newsletter preview/detail pages MUST share a consistent brand identity (logo, color palette, typography) and reuse the product's existing design system tokens/components; the screen preview MUST visually match the delivered artifacts.
- **FR-015**: Parent-facing text and visual elements MUST meet the project's established accessibility standard for color contrast and MUST NOT rely on color alone to convey meaning.
- **FR-016**: The newsletter MUST omit any section that has no data (e.g., no records, no races) without producing empty tables or blank pages.
- **FR-017**: Multi-child grouped delivery MUST continue to attach exactly one correct PDF per child with no cross-child data leakage.
- **FR-018**: All changes MUST preserve the consent gating already required by the module, with this clarified semantics: missing AI consent MUST gate only the **AI-authored** content (the legacy `strengths`/`area_to_develop`/`milestone` narrative and any AI-authored captions/highlights), replacing it with neutral placeholders/static copy; it MUST NOT cause the document generation itself to fail (no HTTP 409 for generation). The newsletter (email + PDF + preview) still renders via the static/deterministic fallback (see FR-009/FR-010). (The Ley 1581/2012 confidentiality footer block is removed per FR-019 — see the 2026-06-05 clarification; this requirement no longer mandates that footer's presence.)
- **FR-019**: The Ley 1581/2012 (Habeas Data) confidentiality footer block (the boxed notice at the end of the PDF body) MUST be removed from the generated PDF. The rendered document MUST NOT display that block, and removing it MUST NOT leave a broken layout, empty container, or trailing blank space.

### Key Entities *(include if feature involves data)*

- **Individual Monthly Newsletter**: the per-athlete monthly deliverable composed of email-safe blocks (no anthropometry) and PDF-only blocks (anthropometry + charts), an optional coach/AI narrative, and a confidence level.
- **Anthropometric Record**: a dated measurement of an athlete (weight, height, plus derived BMI, percentiles, z-scores, PHV offset, age-at-PHV, maturation stage). Multiple records form the longitudinal/maturation view.
- **Season-Evolution Charts**: the position-per-round, gap-to-leader %, and accumulated-points visualizations for the athlete's competition results, each with a confidence indicator.
- **Parent / Guardian recipient**: the family member who receives the email and the attached PDF; must only ever see their own child's data.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For athletes whose records contain weight, height, sex and date of birth, 100% of derivable anthropometric metrics render as numeric values (0 unexplained `—` cells) in the generated PDF — including BMI for every record with weight + height, and including historical records after backfill.
- **SC-002**: A generated multi-page PDF contains zero avoidable blank vertical gaps larger than a standard section margin, and zero instances of a chart/section title separated from its content across a page boundary.
- **SC-003**: Average page fill (content area used) for all pages except the last targets at least 70% as a design guideline (not a hard acceptance gate; SC-002 is the hard gate for blank gaps and orphaned headings).
- **SC-004**: Every data block in the newsletter carries a plain-language caption, and the report contains at least one concrete "support at home" suggestion, verified across sample newsletters.
- **SC-005**: In a review with parent personas, at least 80% can correctly state how their child did this month and one thing they can do to help, after reading only the newsletter.
- **SC-006**: The email renders single-column and readable without horizontal scrolling in the common mobile email clients tested.
- **SC-007**: All parent-facing text and UI meet the established accessibility color-contrast standard with zero violations in automated checks.
- **SC-008**: Zero instances of anthropometric data appearing in the email body, and zero cross-child data leakage, across the full test suite (existing privacy invariants remain green).
- **SC-009**: No diagnostic, peer-ranking, or discouraging language appears in any generated narrative or caption, verified by automated/property checks.
- **SC-010**: The generated PDF contains zero instances of the Ley 1581/2012 (Habeas Data) confidentiality footer block, with no resulting empty container or trailing blank space.

## Assumptions

- "Show all about" the anthropometric section means making the derived metrics genuinely present and displayed. Per the corrected 2026-06-05 full-fix decision, the empty cells are caused by NULL storage (unpopulated CDC LMS reference table + BMI nulled with the percentiles), so scope includes: decoupling BMI, seeding LMS reference data in production, persisting percentiles on capture, and backfilling existing records. The underlying scientific methods (Mirwald PHV, CDC/WHO LMS percentile math) already exist in the code and are reused, not redefined.
- Scope is the Individual Monthly Newsletter deliverable across three surfaces — the attached PDF, the email body, and the on-screen frontend preview/detail pages, which must stay visually consistent; it does not include redesigning unrelated reports (e.g., the Monthly Technical Report) except where shared design tokens are reused.
- New parent-facing captions and narrative reuse the existing `athlete_monthly_newsletter` AI use case and its guardrails/consent gate, degrading to static/deterministic text when consent is missing or AI is unavailable.
- Reference data and methods for derived metrics already exist in the product (Mirwald PHV; OMS/CDC percentile references adapted per Res. 2465/2016). This feature makes the newsletter *use* them, not redefine them.
- The existing privacy contract, consent gating, RBAC, and Ley 1581 notice are fixed constraints and remain unchanged.
- "Research for better insight for the parents" is delivered as improved on-document interpretation/guidance and information design, not as a new external integration.
- Charts remain self-contained printable visuals (no interactivity required in the PDF); the fix is layout/pagination, not a charting-engine change.
- The Ley 1581/2012 (Habeas Data) confidentiality footer block is removed from the PDF at the user's explicit request. The user was advised this removes a legal data-protection notice from a document containing a minor's sensitive data and contradicted the original FR-018; the user accepted this and owns the associated legal/compliance risk. Other privacy controls (consent gating, PDF-only anthropometry, no cross-child leakage, RBAC) remain unchanged.

## Out of Scope

- Adding new external integrations or new data sources.
- Redefining the scientific formulas for PHV/percentiles (the existing Mirwald + CDC/WHO LMS methods are reused as-is; this feature only ensures their inputs/outputs are populated, persisted, and backfilled).
- Redesigning other report types beyond shared design-token reuse.
- Introducing individualized medical advice, calorie counting, or any guidance that violates the club's non-negotiable principles.
