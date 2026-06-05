# Implementation Plan: Improve Individual Monthly Newsletter (PDF + parent delivery)

**Branch**: `003-improve-individual-newsletter-pdf` | **Date**: 2026-06-05 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-improve-individual-newsletter-pdf/spec.md`

## Summary

Fix two visible defects and raise the quality of the per-athlete Monthly Newsletter delivered to families (email + attached PDF + on-screen preview):

1. **Anthropometry shows all values** — root cause (verified) is NULL storage: the CDC LMS reference table is unpopulated in production and BMI is nulled alongside percentiles. Fix = decouple BMI (always computed), seed LMS deterministically from vendored CDC CSVs, and backfill existing records. (US1)
2. **No page-break gaps** — wrap headings with their content using WeasyPrint-honored `break-inside: avoid` blocks and remove a forced `page-break-before: always`. (US2)
3. **Parent-friendly insight** — extend the existing guardrailed AI use case with per-block captions, a "highlights of the month" summary, and "support at home" guidance, with a deterministic static fallback when consent is missing. (US3)
4. **Modern, consistent UX/UI** — inline-CSS responsive single-column email, restyle the PDF and the React preview on shared brand tokens, WCAG AA. Also **remove the Ley 1581 boxed footer block** from the PDF (user decision, FR-019). (US4)

No new tables, columns, or HTTP endpoints. The approach reuses existing science (`services/growth.py`, `services/phv.py`) and the audited AI guardrail pipeline.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async + aiomysql, Alembic, WeasyPrint ≥62.3 (PDF), Jinja2 (email/PDF templates), Google Gemini via existing AI provider; React 19 + Vite + shadcn/ui + Tailwind + TanStack Query + Zustand + RHF + Zod

**Storage**: MySQL 8.4 (Hostinger prod); existing tables `anthropometric_records`, `growth_reference_lms`, `athlete_monthly_newsletters` — **no schema change**

**Testing**: pytest + httpx.AsyncClient + aiosqlite (backend); vitest + Testing Library + jest-axe (frontend)

**Target Platform**: Render Free (Docker, Oregon) backend; Cloudflare Pages (pending) frontend; parents on mid-tier Android over 3G/4G

**Project Type**: Web application (backend + frontend)

**Performance Goals**: PDF generation stays within existing newsletter budget; seeding/backfill are one-time/idempotent and MUST NOT depend on outbound internet at deploy (no live cdc.gov fetch); email payload small for slow connections; frontend preview within data-dense LCP ≤3.5 s budget

**Constraints**: Ley 1581 privacy contract (anthropometry PDF-only, no cross-child leakage, no minor PII in logs/AI); español neutro product copy; WCAG 2.1 AA; reuse shadcn/ui design system; no new runtime dependencies

**Scale/Scope**: ~dozens of athletes; multi-child families; backfill over the full history of `anthropometric_records` (small volume)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | How this plan satisfies it |
|---|---|
| **I. Code Quality** | Reuses `growth.py`/`phv.py` math and the existing guardrail pipeline (no duplication; rule-of-three respected). BMI decoupling is a named fix, not a new abstraction. Lint/type gates (`ruff`, `mypy`, `eslint`, `tsc`) required green. Vendored-CSV seeding documented. |
| **II. Testing (NON-NEGOTIABLE)** | New tests: BMI-always-computed (regression for the coupling bug), LMS seed coverage, backfill idempotency, PDF pagination contract (no orphaned heading / no Ley 1581 block), email no-anthropometry + a11y, AI captions guardrail + name-redaction property test + static fallback. Each defect lands with a failing-then-passing regression test. Privacy invariants included. |
| **III. UX Consistency** | Email/PDF/preview unified on shared brand tokens; responsive single-column email; español neutro; shadcn/ui reused; WCAG AA contrast; status meaning not by color alone; `jest-axe` zero violations. |
| **IV. Performance** | Seeding/backfill are idempotent, offline (vendored CSV), and one-time — no per-request cost and no cold-start network dependency. AI captions reuse one LLM call path; static fallback avoids blocking on cold LLM. Frontend preview keeps lazy-loading; no new heavy bundle. |

**Compliance constraints:** `data-privacy-guard` audit is mandatory (reads/writes athlete-identifiable data). AI captions run through forbidden-names + word-limit + redaction guardrails; `AI_LOG_PROMPTS=false` in prod. No new runtime dependency (vendored CSV uses stdlib `csv`).

**Gate result:** PASS (no violations). One deliberate, user-owned policy exception is tracked below.

## Project Structure

### Documentation (this feature)

```text
specs/003-improve-individual-newsletter-pdf/
├── plan.md              # This file
├── spec.md              # Feature spec (clarified)
├── research.md          # Phase 0 — root cause + best practices (context7 + web)
├── data-model.md        # Phase 1 — populate LMS + backfill records; block shapes
├── contracts/
│   └── internal-contracts.md   # Phase 1 — rendering/seed/backfill/AI contracts
├── quickstart.md        # Phase 1 — end-to-end validation steps
├── checklists/
│   └── requirements.md  # Spec quality checklist (16/16)
└── tasks.md             # Phase 2 — created by /speckit-tasks (NOT here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── routers/anthropometry.py            # BMI decoupling on capture (compute always)
│   ├── services/
│   │   ├── growth.py                        # reused math (no change to formulas)
│   │   └── training/newsletter_builder.py   # captions + highlights wiring; anthro block
│   ├── services/ai/
│   │   ├── use_cases/athlete_monthly_newsletter.py   # +block_captions, +month_highlights
│   │   └── prompts/athlete_monthly_newsletter_v1.j2   # extended prompt + static fallback
│   ├── seed_growth_data.py                  # read vendored CSVs (no live download)
│   ├── data/cdc_lms/*.csv                    # NEW vendored CDC reference data (no minor data)
│   └── scripts/backfill_anthropometry.py     # NEW idempotent backfill
├── templates/
│   ├── documents/pdf/athlete_monthly_newsletter.html   # pagination wrappers; remove Ley 1581 box
│   ├── documents/pdf/base/layout.html        # widows/orphans; shared tokens (minimal)
│   └── email/athlete_monthly_newsletter.html # inline CSS, single-column, a11y
├── entrypoint.sh                            # invoke idempotent seed (+ optional backfill)
└── tests/                                   # new pagination/seed/backfill/email/AI tests

frontend/
├── src/components/training/
│   ├── NewsletterPreviewBlocks.tsx          # restyle to new design; render captions
│   └── NewsletterNarrativeEditor.tsx        # show highlights; confidence unchanged
├── src/routes/training/AthleteNewsletterDetailPage.tsx  # layout polish, token consistency
└── (tests) *.test.tsx                       # vitest + jest-axe updates
```

**Structure Decision**: Existing web-app layout (backend + frontend). All changes are edits to existing files plus two new backend assets (vendored CDC CSVs, backfill script). No new module boundaries, tables, or endpoints.

## Implementation phasing (for /speckit-tasks)

Ordered by spec priority; each slice independently testable and deployable.

1. **P1 — Anthropometry data integrity (US1):** BMI decoupling on capture → vendored CDC CSV + idempotent seed wired into `entrypoint.sh` → idempotent backfill script → tests (BMI regression, seed coverage, backfill idempotency).
2. **P1 — PDF pagination (US2):** wrap heading+content in `break-inside: avoid` blocks; remove forced `page-break-before`; `widows/orphans`; remove Ley 1581 box (FR-019) → pagination + footer-absence contract tests.
3. **P2 — Parent insight (US3):** extend AI use case (`block_captions`, `month_highlights`) under guardrails + static fallback; builder wires captions into email & PDF blocks; keep support_at_home → guardrail/redaction/fallback tests.
4. **P3 — UX/UI (US4):** inline-CSS responsive email; restyle PDF + React preview on shared tokens; a11y → vitest + jest-axe, email no-anthropometry assertions.
5. **Cross-cutting:** `data-privacy-guard` audit; backend `pytest`, frontend `vitest`/`tsc` green; deploy (seed + backfill run idempotently on Render).

> Implementation will be executed via a **dynamic multi-agent workflow** (user request): each slice fans out to the appropriate specialists (`fastapi-architect`/`database-architect` for data integrity, `react-ui-engineer` + Jinja for templates, `integration-engineer` for the AI use case, `qa-engineer` for tests) with adversarial privacy verification by `data-privacy-guard` before merge. This is orchestrated at `/speckit-implement` time.

## Complexity Tracking

> Constitution Check passed with no principle violations. The table records one deliberate, user-owned **policy** exception (not a principle violation).

| Item | Why / decision | Simpler alternative rejected because |
|---|---|---|
| Remove Ley 1581/2012 boxed legal notice from the PDF (FR-019) | Explicit user decision after being advised of the legal/compliance risk on a minor's sensitive-data document; recorded in spec Clarifications/Assumptions; flagged for human/legal review at PR | Keeping/compacting the notice was offered and declined by the user |
| Vendor CDC LMS CSVs into the repo | Deterministic, offline, fast seeding on Render free tier | Live `cdc.gov` download at deploy is non-deterministic, network-dependent, and slows cold start |
| Static fallback for AI captions/highlights when consent missing | Spec FR-009/010 require the newsletter to still render; serves families even when LLM is cold/unavailable | Hard-fail (current behavior) leaves parents with no document |
