# Implementation Plan: Body composition by skinfolds (plicómetro) for athletes aged 9 and up

**Branch**: `main` (owner decision: no feature branch, no auto-commits) | **Date**: 2026-09-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/046-body-composition-skinfolds/spec.md`; research corpus in `docs/21-body-composition/` (`proposal.md` decisions D1–D17 and coach decisions C1–C8, `technical-fit.md`, `research-protocol.md`, `research-safeguards-referral.md`, `research-measurer-ux.md`).

## Summary

Attach an optional **skinfold set** (six sites, raw readings, per-site decline) to an existing `anthropometric_records` row through a guided, illustrated capture wizard; persist the four-site backbone sum, the six-site sum and the coach-only Slaughter–Lohman (triceps + calf) body-fat / fat-free-mass estimates with an equation version; derive at read time a **noise-aware change reading** and a **coach-only traffic light** (verde / ámbar / rojo, rojo only for the combined energy-availability pattern); seed the **Bogotá FUPRECOL 2016** skinfold LMS tables into the existing `growth_reference_lms` machinery for context percentiles; expose everything through one sub-resource under the anthropometry API plus a `body_composition` block in `growth-summary` that is projected to **band + sentence only** for parents; produce two coach-only PDFs (generic field guide, neutral referral note); extend the feature-042 AI explainer with a qualitative `body_composition` leaf, versioned prompts (`v2`) and two new blocking prechecks (numeric leak to family, diet/weight-loss language). Six waves; W1–W4 have no AI dependency.

## Technical Context

**Language/Version**: Python 3.13 (backend), TypeScript 5 / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async (aiomysql / aiosqlite), Pydantic v2, Alembic, Jinja2 + WeasyPrint (PDF), LangChain adapter of `app/services/llm/` (AI); Vite, TanStack Query, React Hook Form + Zod, shadcn/ui + Tailwind v4, inline SVG (no chart library), MSW + vitest + Testing Library + jest-axe, Playwright

**Storage**: MySQL 8.4 (Hostinger) in production; aiosqlite in-memory in the default test lane; one new table `skinfold_measurements` (1:1 nullable child of `anthropometric_records`), two enum extensions on `growth_reference_lms` (`source` + `indicator`), one vendored CSV under `app/data/fuprecol_lms/`

**Testing**: `pytest` (default lane offline; `-m mysql` for enum alter + downgrade; `-m golden` for the anthropometry analyst eval), `vitest` + jest-axe, Playwright `e2e/body-composition.spec.ts` (deferred to a session with the isolated e2e stack)

**Target Platform**: Render free tier (backend, ~50 s cold start) + Cloudflare Pages (SPA); coach on tablet 1024×768 outdoors; parents on mid-tier Android over 3G/4G

**Project Type**: Web application (FastAPI modular monolith + React SPA)

**Performance Goals**: `PUT …/skinfolds` p95 ≤ 1500 ms (one transaction, ≤ 4 queries); `GET growth-summary` stays p95 ≤ 500 ms with one additional eager-loaded relationship; `GET …/body-composition` ≤ 500 ms for ≤ 40 sets per athlete; capture page chunk ≤ 150 KB gzipped (lazy route, SVG diagrams as code, no image assets); field-guide PDF ≤ 5 s server-side (WeasyPrint, static content)

**Constraints**: Ley 1581 (no names with values in logs, errors, provider prompts); parents never receive numeric body-composition data on any surface (API, PDF, AI text); capture only for athletes aged ≥ 9 at the evaluation date; new sets at most every 90 days; thresholds (7 mm Σ4, 10 mm Σ6, 90 days, min age) as `Settings` values overridable by env; MySQL enum alteration must downgrade cleanly; SQLite test lane must not need the enum alter; production refuses `claude-cli`/Langfuse as before (unchanged)

**Scale/Scope**: ~20 athletes, ≤ 4 sets per athlete per year, one coach measuring; 6 SVG diagrams; ~8 backend files touched + 1 migration + 1 router; ~15 frontend files; 4 golden-eval cases added

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Code quality | `ruff check` clean; `tsc --noEmit` clean; new services (`body_composition.py`, `reference_skinfolds.py`) with module docstrings describing inputs/outputs/side effects; no third copy of the band vocabulary (extend `lib/growth/bands.ts`, not a new colour map) | PASS (design) |
| II. Testing (non-negotiable) | Router tests: happy path + parent `PUT` → 403, foreign-club coach → 403, parent detail `GET` → 403, interval < 90 days → 409; service unit tests for readings, sums, equation, delta classifier, band classifier (fixed scenario set from spec SC-004); privacy invariants: no name + value in logs, prompt leaf allow-listed, family projection has no numeric field (property test); vitest for wizard branching + jest-axe zero violations on `SkinfoldCapturePage`, `BodyCompositionCard`, detail dialog and family card; every bug fix with a regression test | PASS (design) |
| III. UX consistency | All product copy in español (Colombia) with diacritics, no clinical/judgemental wording (copy from `research-safeguards-referral.md` §5); shadcn/ui components only; RHF + Zod wizard; 48 × 48 px on every control incl. reading inputs and "Omitir este sitio"; loading/empty/error states on every async surface; amber = attention for tolerance/range warnings, red reserved for errors, band colours via `StatusBadge` tones; WCAG AA, focus moves to step heading, diagrams with `role="img"` + text alternative | PASS (design) |
| IV. Performance | Budgets above; no N+1 (skinfold rows eager-loaded with the record list via `selectinload`); capture page lazy-loaded; no new client dependency; Sparkline reuse; cold-start state unchanged | PASS (design) |
| V. Youth safeguards (extended by analogy to body composition) | Wellbeing tool not diagnosis (no label; rojo = "consider referral"); baseline-anchored (athlete's own trend first, reference as context); mastery climate (no targets, no comparison); human in the loop (nothing sent automatically); consent-gated (existing `anthropometry` scope for capture, `third_party_sharing` for AI as today); item-level persistence (raw readings stored for recompute) | PASS (design) |

**Gate result (pre-research)**: no violations; Complexity Tracking left empty.

## Project Structure

### Documentation (this feature)

```text
specs/046-body-composition-skinfolds/
├── plan.md                          # This file
├── spec.md
├── research.md                      # Phase 0 — decisions with rationale and alternatives
├── data-model.md                    # Phase 1 — table, enums, derived reading, validation, states
├── quickstart.md                    # Phase 1 — runnable validation scenarios
├── contracts/
│   ├── skinfolds-api.md             # PUT/DELETE skinfolds, GET body-composition, growth-summary block, PDFs
│   ├── body-composition-reading.md  # delta classifier + traffic-light rules + Spanish copy
│   └── ai-body-composition-leaf.md  # AI context leaf, allow-list keys, prompts v2, prechecks R13/R14, golden cases
├── checklists/requirements.md
└── tasks.md                         # Phase 2 (/speckit-tasks) — not created here
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/<rev>_skinfold_measurements_and_fuprecol_lms.py   # new table + enum values (MySQL alter), symmetric downgrade
├── app/
│   ├── config.py                       # BODY_COMP_MDC_SUM4_MM, BODY_COMP_MDC_SUM6_MM, BODY_COMP_MIN_INTERVAL_DAYS, BODY_COMP_MIN_AGE_YEARS; AI_ANTHRO_PROMPT_VERSION default → v2
│   ├── data/fuprecol_lms/              # fuprecol_skinfolds.csv + README.md (provenance, licence CC BY, left side, age bands)
│   ├── models/skinfold_measurement.py  # SkinfoldMeasurement (1:1 with AnthropometricRecord)
│   ├── models/growth.py                # GrowthSource.FUPRECOL; GrowthIndicator.{triceps,subscapular,triceps_subscapular_sum}_skinfold_for_age
│   ├── models/anthropometry.py         # relationship `skinfolds` (uselist=False)
│   ├── schemas/body_composition.py     # SkinfoldSiteIn/Out, SkinfoldSetIn/Out, BodyCompositionOut, BodyCompositionSummary (+ family projection)
│   ├── schemas/anthropometry.py        # AnthropometryOut.skinfolds
│   ├── schemas/growth.py               # GrowthSummaryOut.body_composition
│   ├── services/body_composition.py    # readings → values, sums, Slaughter TC estimate, delta classifier, band classifier, interval rule, plausible ranges
│   ├── services/reference_skinfolds.py # percentile context from growth_reference_lms (FUPRECOL) — thin wrapper over services/growth.py
│   ├── services/growth_summary.py      # builds `body_composition` block (coach vs family projection)
│   ├── seed_growth_data.py             # FUPRECOL source entries
│   ├── routers/body_composition.py     # PUT/DELETE …/anthropometry/{record_id}/skinfolds, GET …/body-composition, GET …/referral-note.pdf, GET /body-composition/field-guide.pdf
│   ├── routers/anthropometry.py        # list: eager-load skinfolds, parent projection strips them
│   ├── services/ai/anthro/context.py   # body_composition leaf + renderer block
│   ├── services/ai/context_builders.py # allow-list keys
│   ├── services/ai/anthro/prechecks.py # R13 (numeric body-comp leak to family), R14 (diet / weight-loss language)
│   ├── services/ai/anthro/fallback.py  # body-composition sentence in the rule-based fallback
│   ├── services/ai/anthro/prompts/anthropometry_analyst_v2.md, anthropometry_critic_v2.md
│   └── main.py                         # mount routers/body_composition
├── templates/documents/pdf/
│   ├── skinfold_field_guide.html       # generic instructivo (coach/admin)
│   ├── body_composition_referral_note.html
│   └── diagrams/skinfold_{site}.svg.jinja   # 6 partials, same landmark data as the React diagrams
├── evals/anthropometry_analyst/golden/case_013…016.json (+ baseline refresh)
└── tests/
    ├── services/test_body_composition.py, test_reference_skinfolds.py, test_seed_fuprecol.py
    ├── routers/test_body_composition.py (RBAC denied paths, interval 409, projection)
    ├── anthro/test_context_body_composition.py, test_prechecks_r13_r14.py, test_privacy_seam.py (property #5)
    └── test_migration_skinfolds.py (mysql lane: upgrade/downgrade + enum values)

frontend/src/
├── api/bodyComposition.ts
├── schemas/bodyComposition.schema.ts          # Zod mirror of the API shapes; wizard form schema (per-site: readings | declined)
├── types/bodyComposition.types.ts
├── lib/bodyComposition/readings.ts            # computeSiteValue, needsThirdReading (pure, unit-tested)
├── lib/bodyComposition/siteDiagrams.ts        # per-site diagram spec (landmark, fold orientation, caliper position, alt text)
├── lib/growth/bands.ts                        # + body-composition band vocabulary (verde/ámbar/rojo → labels, tones)
├── hooks/athletes/useBodyComposition.ts, useSaveSkinfolds.ts, useDeleteSkinfolds.ts
├── hooks/athletes/useAnthropometry.ts         # invalidate growth-summary + body-composition on create
├── routes/athletes/SkinfoldCapturePage.tsx    # lazy route /athletes/:id/anthropometry/:recordId/skinfolds
├── App.tsx                                    # route registration next to /athletes/:id (line ~385), coach/admin guard
├── components/athletes/body-composition/
│   ├── SkinfoldWizard.tsx, SkinfoldPrecheckStep.tsx, SkinfoldSiteStep.tsx, SkinfoldReviewStep.tsx
│   ├── SkinfoldSiteDiagram.tsx                # inline SVG per site (shared silhouette)
│   ├── BodyCompositionCard.tsx                # coach: Σ4/Σ6 sparklines, estimates, delta reading, band + reason
│   ├── BodyCompositionDetailDialog.tsx        # per-site history, reference context, sets table
│   ├── FamilyBodyCompositionCard.tsx, FamilySkinfoldNotice.tsx
│   ├── FieldGuideDownloadButton.tsx, ReferralNoteButton.tsx
│   └── __tests__/…
├── components/athletes/AnthropometryForm.tsx  # two exits after save
├── components/athletes/AnthropometryHistory.tsx  # "Pliegues" marker + "Agregar/Editar pliegues" action
├── components/athletes/growth/GrowthTab.tsx   # mounts BodyCompositionCard (coach) / FamilyBodyCompositionCard + notice (parent)
├── mocks/handlers/bodyComposition.ts          # MSW
└── e2e/body-composition.spec.ts
```

**Structure Decision**: Web application layout already in place (backend modular monolith + React SPA). The feature adds one router, one model, two services and one migration on the backend, and one lazy route plus a `body-composition/` component folder on the frontend, mirroring how feature 040/042 extended the same module.

## Phase 0 — Research (complete)

See [research.md](research.md). All Technical Context items are resolved; no `NEEDS CLARIFICATION` remains. Decisions R1–R16 cover: data model (1:1 child table with fixed site columns), computation placement (persist sums/estimates, derive reading), API shape (sub-resource `PUT`), interval rule semantics, equation and constants, thresholds as settings, FUPRECOL seeding (enum extension + CSV + midpoint months), band classifier rules, family projection and the PDF gap, AI leaf + prompt versioning + prechecks, capture route and draft, diagrams as inline SVG with a shared spec, printable guide, referral note, testing lanes.

## Phase 1 — Design (complete)

- [data-model.md](data-model.md): `skinfold_measurements` columns, relationships, validation, derived `BodyCompositionReading`, state transitions, migration notes.
- [contracts/skinfolds-api.md](contracts/skinfolds-api.md): endpoints, payloads, role projection, error codes.
- [contracts/body-composition-reading.md](contracts/body-composition-reading.md): delta classifier, traffic-light legs and rules, Spanish copy per band and audience.
- [contracts/ai-body-composition-leaf.md](contracts/ai-body-composition-leaf.md): context leaf, allow-list, prompt v2 blocks, R13/R14, fallback, golden cases.
- [quickstart.md](quickstart.md): validation scenarios per user story.

### Constitution Check — post-design re-evaluation

| Principle | Re-check |
|---|---|
| I | No new pattern outside existing conventions; band vocabulary centralised in `lib/growth/bands.ts`; one migration with symmetric downgrade. PASS |
| II | Test list in each contract; scenario set SC-004 encoded as parametrised unit tests; privacy property #5 added to `test_privacy_seam.py`. PASS |
| III | Copy sourced from the safeguards research; warning semantics amber; 48 px floor called out per control; focus contract reused from `SessionWizard`. PASS |
| IV | One `selectinload` on the list endpoint; growth-summary adds one query; lazy route; no dependency added. PASS |
| V | Rojo requires two sets and all three legs; nothing automatic to families; consent scopes unchanged. PASS |

**Gate result (post-design)**: PASS. Complexity Tracking empty.

## Waves (input for `/speckit-tasks`)

| Wave | Scope | Depends on |
|---|---|---|
| W1 Backend core | migration, model, enums + FUPRECOL CSV/seed, `body_composition.py`, `reference_skinfolds.py`, settings, unit tests | — |
| W2 API + summary + PDFs | router, schemas, `AnthropometryOut.skinfolds`, growth-summary block + projection, field guide + referral note templates and SVG partials, RBAC/interval/projection tests | W1 |
| W3 Frontend capture | route, wizard, diagrams, readings lib, draft, MSW, vitest + axe, two-exit form, history actions | W2 contract (can start on MSW) |
| W4 Frontend reading | coach card + detail dialog, family card + notice, bands vocabulary, download buttons, query invalidation fix, tests | W2, W3 |
| W5 AI | context leaf, allow-list, prompts v2, prechecks R13/R14, fallback, privacy property, golden cases + baseline refresh (needs AI key) | W1, W2 |
| W6 Verification & docs | Playwright spec, `pytest -m mysql` (enum alter + downgrade), `data-privacy-guard` audit, `docs/21-body-composition/` as-built notes, `docs/implementation-status.md`, `docs/technical-notes.md` | all |

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

None.
