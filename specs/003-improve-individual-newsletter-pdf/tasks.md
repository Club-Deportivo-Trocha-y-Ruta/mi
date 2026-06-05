---
description: "Task list for 003-improve-individual-newsletter-pdf"
---

# Tasks: Improve Individual Monthly Newsletter (PDF + parent delivery)

**Input**: Design documents from `specs/003-improve-individual-newsletter-pdf/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/internal-contracts.md, quickstart.md

**Tests**: INCLUDED — the project Constitution (Principle II, NON-NEGOTIABLE) requires tests for every backend/frontend change, regression tests for every bug fix, and explicit privacy invariants for minors' data. Test tasks are therefore mandatory here, not optional.

**Organization**: Tasks are grouped by user story (US1–US4 from spec.md) so each story can be implemented, tested, and deployed independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US4; Setup/Foundational/Polish have no story label
- Exact file paths are included in each task

## Path Conventions

Web app: `backend/app/**`, `backend/templates/**`, `backend/tests/**`, `frontend/src/**`.

## Dynamic-workflow execution note (user request: "Use dynamic workflows for agents")

`/speckit-implement` should run each phase as a **dynamic multi-agent workflow**, fanning out the `[P]` tasks to specialist agents and gating each story on an adversarial privacy review before merge. Suggested agent routing is annotated per phase under **▶ Workflow routing**. The orchestration shape (pipeline by default; barrier only where a phase must complete before the next):

- **Foundational → US1** is a hard barrier (data must be correct before anything renders it).
- **US1 → US2 → US3 → US4** run as a pipeline; each story is independently testable and can ship alone.
- Every story ends with a `data-privacy-guard` verification task before its commit.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the working branch and baseline gates before changes.

- [X] T001 Confirm branch `003-improve-individual-newsletter-pdf` is checked out and clean; run baseline `cd backend && pytest -q` and `cd frontend && npm run test -- --run` to capture the green baseline before changes (record counts in the PR description).
- [X] T002 [P] Verify local toolchain: `backend/.venv` active, `ruff`/`mypy` runnable, `frontend` deps installed, `npx tsc --noEmit` clean on `main`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Vendored CDC reference data + seeding infrastructure that US1 depends on. **No user story can populate anthropometry until this is done.**

**▶ Workflow routing**: `database-architect` + `fastapi-architect` (data plumbing), `qa-engineer` (seed tests). Barrier before Phase 3.

- [X] T003 Vendor the three CDC LMS datasets as committed CSVs under `backend/app/data/cdc_lms/` (`statage.csv` → height_for_age, `bmiagerev.csv` → bmi_for_age, `wtage.csv` → weight_for_age). Include a short `README.md` in that folder citing the CDC source URLs and noting the files contain only population reference constants (no minor data). **Privacy**: confirm no athlete data is present.
- [X] T004 Refactor `backend/app/seed_growth_data.py` to read from the vendored CSVs in `backend/app/data/cdc_lms/` instead of downloading from `cdc.gov` (remove the `urllib.request` network path; keep the existing parse + upsert logic and the `uq_lms_source_indicator_sex_age` idempotency). Keep the `python -m app.seed_growth_data` entrypoint.
- [X] T005 Make seeding idempotent and offline-safe, then wire it into `backend/entrypoint.sh` to run after `alembic upgrade head` on every boot (no-op when already seeded; MUST NOT require outbound internet). Guard it so a partial/failed seed cannot crash startup (log + continue).
- [X] T006 [P] Test (pytest, aiosqlite) in `backend/tests/services/test_growth_seed.py`: seeding a small fixture CSV populates `growth_reference_lms`; all six `(indicator, sex)` groups non-empty over 24–240.5 months; a sample `(age, sex)` lookup yields the known CDC L/M/S and a z-score that matches an expected value; re-running the seed is a no-op (row count unchanged).

**Checkpoint**: LMS reference data is deterministically available in every environment.

---

## Phase 3: User Story 1 — Complete anthropometric & maturation section (Priority: P1) 🎯 MVP

**Goal**: Every record with raw weight+height shows BMI; records in LMS range show percentiles/z-scores; historical rows are backfilled. (FR-001, FR-001a/b/c, FR-002, FR-003)

**Independent test**: Generate a newsletter PDF for an athlete with weight+height+sex+DOB and confirm 0 unexplained `—` cells, including historical records after backfill (SC-001).

**▶ Workflow routing**: `fastapi-architect` (capture path), `database-architect` (backfill), `qa-engineer` (tests), `data-privacy-guard` (verify). Pipeline within story.

- [X] T007 [US1] Fix the BMI-coupling bug in `backend/app/routers/anthropometry.py` (`create_anthropometry`, ~lines 128–175): always compute and persist `bmi = weight_kg / (height_m**2)` whenever weight and height are present, independent of LMS/`growth` being `None`. Keep percentile/z-score fields gated on LMS availability.
- [X] T008 [P] [US1] Regression test in `backend/tests/routers/test_anthropometry_bmi.py`: creating a record with weight+height but with the LMS table empty still persists a non-NULL `bmi`; with LMS seeded, percentiles + z-scores also persist. This test MUST fail on current `main` and pass after T007.
- [X] T009 [US1] Create an idempotent backfill script `backend/app/scripts/backfill_anthropometry.py` (invocable via `python -m app.scripts.backfill_anthropometry`) that, for each `anthropometric_records` row with NULL `bmi` and/or NULL percentiles but present raw measurements, recomputes derived values using `services/growth.py` + the BMI formula and persists them. MUST NOT modify raw measurement columns; already-populated rows are skipped.
- [X] T010 [US1] Wire the backfill to run once on deploy in `backend/entrypoint.sh` after seeding (idempotent; safe to re-run; log a summary count, never log athlete identifiers).
- [X] T011 [P] [US1] Test in `backend/tests/scripts/test_backfill_anthropometry.py`: records with NULL derived values + known raw values are filled to match `growth.py` output and `bmi = weight/height²`; raw columns unchanged; re-running is a no-op; **privacy**: no athlete name/DOB emitted in logs (capture log output and assert).
- [X] T012 [US1] In `backend/templates/documents/pdf/athlete_monthly_newsletter.html` anthropometry block (~lines 564–613), render a plain-language `unavailable_reason` next to any genuinely-missing cell instead of a bare `—` (FR-002), and ensure the latest-measurement pedagogical interpretation (FR-003) reads in español neutro with no diagnostic claims. Wire `unavailable_reason` from `newsletter_builder._build_anthropometry_block` in `backend/app/services/training/newsletter_builder.py` (~lines 657–709).
- [X] T013 [P] [US1] Test in `backend/tests/services/training/test_newsletter_anthropometry.py`: builder emits numeric BMI/percentiles for a complete record; emits `unavailable_reason` (not bare `—`) for a record missing height; anthropometry remains ONLY in `pdf_only_blocks` and never in `email_blocks` (FR-004 / SC-008).
- [X] T014 [US1] **Privacy verification** (`data-privacy-guard`): audit T007–T013 diff for any minor PII in logs/responses and confirm anthropometry is PDF-only. Record the audit line for the PR compliance statement.

**Checkpoint**: US1 independently shippable — sample PDF anthropometry is fully populated.

---

## Phase 4: User Story 2 — Clean page layout without blank gaps (Priority: P1)

**Goal**: Headings stay with their content; the charts row renders as one unit; no oversized blank gaps; remove the Ley 1581 boxed block. (FR-005–FR-008, FR-019)

**Independent test**: Render a PDF with charts + ≥1 record and confirm no orphaned heading, no near-empty page, correct footer/page-count, and no Ley 1581 box (SC-002, SC-010).

**▶ Workflow routing**: `react-ui-engineer`/Jinja templating + `ux-researcher` (layout), `qa-engineer` (pagination tests), `data-privacy-guard` (footer-removal legal note). Independent of US1; can ship alone.

- [X] T015 [US2] In `backend/templates/documents/pdf/athlete_monthly_newsletter.html`, wrap the "Evolución en la temporada" heading + the `display:table` charts row (~lines 539–557) in a plain block container with `break-inside: avoid`; add `break-after: avoid` to the heading. Do NOT put `break-inside` on the `display:table` row (WeasyPrint ignores it there — see research.md R2).
- [X] T016 [P] [US2] Apply the same heading+content `break-inside: avoid` wrapper pattern to the KPI card row (~146–254), the coach-narrative card (~301–350), the badges box (~260–290), and each anthropometry sub-block (table, latest-measurement card) — keeping wrappers smaller than one page so tall tables stay breakable while headings stay attached.
- [X] T017 [US2] Remove the forced `page-break-before: always` on the percentile-curves `<section>` (~line 643) and rely on natural flow + `break-inside: avoid`; in `backend/templates/documents/pdf/base/layout.html` add `widows: 2; orphans: 2;` to `body` (and `.caption`/`p` as needed).
- [X] T018 [US2] Remove the Ley 1581/2012 boxed confidential block (`athlete_monthly_newsletter.html` ~lines 758–768) entirely; verify no empty container/trailing whitespace remains and the preceding section spacing still reads cleanly. (FR-019) Leave the `@page` running footer and `.doc-footer` untouched.
- [X] T019 [P] [US2] Test in `backend/tests/services/notification/test_newsletter_pdf_layout.py`: render the newsletter PDF (WeasyPrint) for a fixture with charts + records and assert (a) the charts heading text and chart content extract on the same page; (b) the rendered PDF does NOT contain the Ley 1581 boxed block string; (c) page count is within an expected bound and no non-last page is <~30% filled where avoidable; (d) the `@bottom-right` page counter appears on every page.
- [X] T020 [US2] **Privacy/legal note** (`data-privacy-guard`): record in the PR that the Ley 1581 boxed notice was removed by explicit user decision (spec Clarifications/Assumptions) and flag for human/legal review.

**Checkpoint**: US2 independently shippable — PDF paginates cleanly with no legal box.

---

## Phase 5: User Story 3 — Parent-friendly insight & guidance (Priority: P2)

**Goal**: Per-block plain-language captions + a "highlights of the month" summary + "support at home" guidance, AI-generated under existing guardrails with a deterministic static fallback. (FR-009–FR-012)

**Independent test**: Generate a newsletter and confirm each data block has a caption, a highlights summary and ≥1 support tip exist, all guardrail-safe; with consent missing, static fallback still renders (SC-004, SC-009).

**▶ Workflow routing**: `integration-engineer` (AI use case + prompt), `training-planner`/`parent-communicator` (static fallback copy in español neutro), `qa-engineer` (guardrail + property tests), `data-privacy-guard` (name-redaction verify). Depends on US1 data for accurate captions but can be developed against fixtures.

- [X] T021 [US3] Extend `backend/app/services/ai/use_cases/athlete_monthly_newsletter.py` output schema (`AthleteNewsletterNarrativeOut`, ~lines 50–58) with optional `block_captions: dict[str,str]` and `month_highlights: str`; route both through the existing `scrub_block` guardrail (≤80 words, medical-term block, `_redact_names`).
- [X] T022 [US3] Update the prompt `backend/app/services/ai/prompts/athlete_monthly_newsletter_v1.j2` to also request `block_captions` (attendance, technical, race_results, anthropometry) and `month_highlights`, preserving all existing constraints (no real names, no medical/comparative-negative language, español neutro, confidence-aware tone).
- [X] T023 [US3] Add a deterministic static-fallback module (e.g., `backend/app/services/training/newsletter_static_copy.py`) producing español-neutro captions, a highlights line, and tip selection from a fixed vetted library, used when AI consent is missing or the LLM times out/errors. Wire the fallback into `_generate_newsletter_for_athlete` in `backend/app/routers/athlete_monthly_newsletters.py` (~lines 138–271) so the newsletter still renders (the legacy `strengths/area/milestone` narrative stays consent-gated with a neutral "valoración no disponible" placeholder — per research.md Open Item default).
- [X] T024 [US3] Wire `block_captions`, `month_highlights`, and the existing `support_at_home` into `newsletter_builder.build_newsletter_metrics` and into both templates: `backend/templates/documents/pdf/athlete_monthly_newsletter.html` (captions under each block; highlights near the top) and `backend/templates/email/athlete_monthly_newsletter.html` (captions/highlights only for email-safe blocks; NEVER anthropometry).
- [X] T025 [P] [US3] Property test in `backend/tests/test_newsletter_ai_captions.py`: across many fixtures, no real athlete name appears in `block_captions`/`month_highlights`; word limits enforced; medical/diagnostic terms blocked. (Constitution AI rule)
- [X] T026 [P] [US3] Test in `backend/tests/routers/test_newsletter_static_fallback.py`: with consent absent, generation does NOT hard-fail — static captions/highlights/support render and the document is produced; with consent present, AI fields populate.
- [X] T027 [US3] **Privacy verification** (`data-privacy-guard`): confirm captions never carry names/medical claims and anthropometry captions stay PDF-only.

**Checkpoint**: US3 independently shippable — newsletter explains itself to parents and degrades gracefully.

---

## Phase 6: User Story 4 — Modern, readable UX/UI (Priority: P3)

**Goal**: Inline-CSS responsive single-column email; restyled PDF + React preview on shared brand tokens; WCAG AA; consistent across all three surfaces. (FR-013–FR-016)

**Independent test**: Review email on a 360px viewport (single column, no h-scroll, no anthropometry), and confirm preview/PDF/email share the design with 0 a11y violations (SC-006, SC-007).

**▶ Workflow routing**: `react-ui-engineer` (preview), Jinja/email templating, `ux-researcher` (mobile/a11y), `qa-engineer` (vitest + jest-axe). Pipeline; ships last.

- [X] T028 [US4] Refactor `backend/templates/email/athlete_monthly_newsletter.html`: inline all visual CSS (color/font/padding) on elements; keep `<style>` only for `@media`/dark-mode progressive enhancement (<8192 chars, valid syntax); ensure the base layout is mobile-correct WITHOUT media queries; set `max-width:600px`, body ≥16px, line-height 1.4–1.5, touch targets ≥44px, `lang="es-CO"`, `role="presentation"` on layout tables, explicit colors + `color-scheme` meta, alt text on images. Keep key info as live text; keep zero anthropometry.
- [X] T029 [P] [US4] Restyle the PDF template headings/spacing/cards in `backend/templates/documents/pdf/athlete_monthly_newsletter.html` and `base/layout.html` to the shared brand tokens (`--brand-lime #8be000`, charcoal, gray scale, 4pt grid) for visual hierarchy consistent with the email; ensure status meaning is not conveyed by color alone (pair with text/icon).
- [X] T030 [US4] Restyle the on-screen preview `frontend/src/components/training/NewsletterPreviewBlocks.tsx` and detail layout `frontend/src/routes/training/AthleteNewsletterDetailPage.tsx` to match the new email/PDF design, reusing existing shadcn/ui (`Card`, `Badge`, `Tooltip`) and Tailwind tokens; render the new `block_captions`/`month_highlights`; keep anthropometry out of the email-equivalent preview.
- [X] T031 [P] [US4] Update/extend frontend tests `frontend/src/components/training/NewsletterPreviewBlocks.test.tsx` and the detail page test: render captions/highlights, assert no anthropometry leaks into the email-preview, and run `jest-axe` with zero violations (SC-007).
- [X] T032 [P] [US4] Test in `backend/tests/services/notification/test_newsletter_email_render.py`: rendered email is single-column, contains `lang="es-CO"` and `role="presentation"`, has inlined styles on key elements, and contains ZERO anthropometric values (FR-004 / SC-008).

**Checkpoint**: All four stories complete; surfaces are consistent and accessible.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final gates, audit, docs, deploy.

- [X] T033 Run full gates: `cd backend && ruff check . && mypy app && pytest -q`; `cd frontend && npm run test -- --run && npx tsc --noEmit`. All green; record before/after test counts.
- [X] T034 [P] Final `data-privacy-guard` audit across the whole feature diff (no minor PII in logs/commits/AI; consent honored; anthropometry PDF-only; no cross-child leakage) and write the one-line PR compliance statement for Principles I–IV.
- [X] T035 [P] Update docs: note the LMS vendored-seed + backfill in `docs/04-percentiles/` (or nearest), and the newsletter changes in `docs/06-parents/`; add a CLAUDE.md status line under the Phase 1.8 newsletter module describing feature 003. Product copy stays español neutro; docs stay English.
- [X] T036 Validate `quickstart.md` end-to-end locally (seed → backfill → generate → inspect PDF/email/preview) and check every box in its acceptance table (SC-001/002/004/006/007/008/009/010).
- [ ] T037 Release: confirm `entrypoint.sh` runs seed + backfill idempotently on Render; post-deploy smoke (generate one newsletter, open PDF, verify populated anthropometry, clean pagination, no Ley 1581 box). Coordinate with `release-manager`/`devops-engineer`; deploy is gated on coach approval per CLAUDE.md.

---

## Dependencies & Execution Order

```
Phase 1 (Setup)  →  Phase 2 (Foundational: vendored CDC + seed)  ──BARRIER──┐
                                                                            ▼
Phase 3 US1 (data integrity, P1, MVP) ──┐
Phase 4 US2 (pagination + footer, P1) ──┤  US2/US3/US4 are independent of each other;
Phase 5 US3 (parent insight, P2) ───────┤  run as a pipeline. US1 should land first
Phase 6 US4 (UX/UI, P3) ────────────────┘  (its data feeds accurate captions in US3/US4).
                                            ▼
                              Phase 7 (Polish, gates, audit, deploy)
```

- **Hard dependency**: Phase 2 blocks Phase 3 (no derived values without LMS). Phase 3 should precede US3/US4 for *accurate* captions, but US2 (pagination/footer) and US4 (templates) are technically independent and can be developed in parallel against fixtures.
- **Story independence**: each of US1–US4 has its own tests and is independently shippable.

## Parallel Execution Examples

- **Foundational**: T006 runs parallel to T003–T005 once the CSVs exist.
- **US1**: T008, T011, T013 ([P] tests) run in parallel after their implementation tasks (T007, T009, T012).
- **US2**: T016 and T019 [P] run alongside T015/T017/T018.
- **US3**: T025, T026 [P] run after T021–T024.
- **US4**: T029, T031, T032 [P] run alongside T028/T030.
- **Polish**: T034, T035 [P] run alongside T033.

## Implementation Strategy

- **MVP = Phase 1 + Phase 2 + Phase 3 (US1)**: fixes the most visible defect (empty anthropometry) and is independently deployable.
- **Increment 2 = US2**: clean pagination + Ley 1581 box removal (small, high-visibility, independent).
- **Increment 3 = US3**: parent-facing insight with guardrails + static fallback.
- **Increment 4 = US4**: responsive email + UX/UI consistency + a11y.
- Each increment ends with its own `data-privacy-guard` verification and green gates before commit. Run `/speckit-implement` per phase as a dynamic workflow (routing annotated above).
