# Implementation Plan: Race course profile — course track, laps per category and track description per válida

**Branch**: `feat/043-race-course-profile` | **Date**: 2026-09-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/043-race-course-profile/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

A válida gains an optional **course profile**: one or more **route variants** ("Circuito completo", "Recorrido reducido"), each extracted server-side from a GPX the coach recorded with their own device and reduced in memory to the simplified shape of **one lap** (position + elevation only — timestamps, Garmin extensions, metadata and the original file are discarded and never stored); a **laps-per-category table** (laps 1–20 + variant, pre-filled from the previous válida of the same series); and a **structured track description** (terrain type, difficulty 1–5, key sectors, ≤ 1 000-char notes). From these, the existing results read derives **real distance and average speed per classified rider** at read time (never stored, never estimated: "sin dato" whenever an input is missing), the race AI analysis receives a `course_block` under the same "present / SIN DATO" veto discipline as conditions (notes structurally excluded), and coach and registered families get a read-only **reconnaissance view** (Leaflet polyline from the stored JSON, Recharts elevation profile, figures, laps of their child's category, description). Two new tables + four columns on `race_events`, one Alembic revision from `d5b125474e2b`, seven endpoints under the existing race-events router, no new runtime dependency on either side (`gpxpy`, `defusedxml`, `leaflet`, `recharts` already pinned). GPX only (FIT deferred, spec amended); storage in the database because Render's disk is ephemeral; detection of a closed lap with a 300 m minimum / 30 m radius / ±10 % validation and a coach override by "vueltas grabadas"; elevation gain after distance-windowed smoothing plus 3 m hysteresis; RDP simplification at 3 m keeping distance within 1 %.

## Technical Context

**Language/Version**: Python 3.13 (backend, venv `backend/.venv`); TypeScript 5 / React 19 (frontend, Vite)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async (aiomysql), Alembic, Pydantic v2; `gpxpy>=1.6`, `defusedxml>=0.7` (already in `requirements.txt:25-26`). Frontend: shadcn/ui, Tailwind v4, TanStack Query, Zustand, RHF + Zod, `leaflet ^1.9.4` (plain `L.polyline`; `leaflet-gpx` is **not** used by this feature), `recharts ^3.8.1`. **No new runtime dependency.**

**Storage**: MySQL 8.4 (Hostinger in prod). New tables `race_course_variants` (lap geometry as `JSON`, ≤ ~15 KB per variant) and `race_course_category_setups`; four nullable columns on `race_events`. No files on disk, no SFTP.

**Testing**: pytest default lane (aiosqlite; synthetic GPX builder in `tests/helpers/gpx_builder.py`; hypothesis for the privacy-stripping invariant and fuzzed inputs); opt-in `-m mysql` for the JSON column, the enum and the `RESTRICT` FK; `-m golden` with two new race-analyst cases; vitest + Testing Library + MSW; jest-axe zero violations on the new tab, both sheets, the summary and the parents page; Playwright `race-course.spec.ts` on the isolated stack.

**Target Platform**: Render free tier (backend, ephemeral disk, cold start ~50 s), Cloudflare Pages (frontend); coach on tablet, parents on mid-tier Android over 3G.

**Project Type**: Web application (FastAPI backend + React SPA), Spec Kit feature.

**Performance Goals**: `GET /course` p95 ≤ 500 ms (≤ 3 statements, ≤ 15 KB per variant); `GET /results` adds exactly one statement; `POST /course/variants` p95 ≤ 1 500 ms for a typical 1–2 MB three-lap recording (processing ≤ 300 ms at 20 000 points locally, asserted); map and chart chunks lazy so the results route stays under the 150 KB gzipped per-lazy-route budget; parents' figures/laps/description render as plain DOM before the lazy chunks (LCP ≤ 3.5 s on throttled 3G for the results route).

**Constraints**: minors' privacy (Ley 1581) — the uploaded recording is the coach's personal data and must be reduced to lap shape in memory with nothing else persisted, logged or traced; `course_notes` never reaches an AI prompt or a trace; parents see course data only for válidas their children are registered in, and derived figures only for their own children; the race AI keeps its anti-fabrication veto when data is absent and the golden composite stays ≥ 0.75; single Alembic head; product copy in español neutro with diacritics; planning corpus in English; GPX only (no FIT, no compressed uploads); no file may be written to the backend filesystem.

**Scale/Scope**: ~7 válidas/season, ≤ 3 variants each, ≤ 26 categories; 2 new tables, 4 columns, 1 migration; ~6 new backend modules (processing, derived figures, service, schemas, queries, tests helpers) and 5 extended (router, results read, analytics rows, AI loader/formatter/prompts); ~10 new frontend components + api/hooks/types/schemas, 3 pages extended; 2 golden cases; docs in `docs/10-race-results/` (course-profile design + runbook addendum) and status/technical-notes updates.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan satisfies it | Status |
|---|---|---|
| I. Code Quality | One pure processing function (`process_gpx`) with named constants and typed error codes; one derivation helper (`derive_figures`) used by results read and season rows (rule of three respected: results, season rows, AI context all call it); the course service owns validation, the router only maps errors; existing patterns reused (tri-state card, URL tabs, `ActorTimestampMixin` + `record_audit`, "present / SIN DATO" block); `ruff` + `tsc --noEmit` gates; docstrings on the new `app/services/race/course/` package. | PASS |
| II. Testing (NON-NEGOTIABLE) | Every contract ends with its tests: processing (synthetic circle / 3-lap / out-and-back / figure-eight / flat-noise / XXE / gzip / fuzz), router happy + denied paths (parent without child 404, athlete 403, foreign coach 403, wrong format 422/415/413, 409s), derived figures (the spec's numeric case, `minus_laps` without count, query-count +1), AI (context keys, formatter, render of v2 and v3, fake-provider end-to-end, notes never in prompt), golden ≥ 0.75 with two new cases, `-m mysql` round-trip, vitest branches by role and state, jest-axe on six surfaces, Playwright flow. Privacy invariants explicit (data-model §7). | PASS |
| III. UX Consistency | Reuses shared `Sheet`/`Dialog`, the tri-state card pattern of conditions, URL-driven tab, ≥ 48 px controls, RHF + Zod with inline Spanish errors and no HTML5 validation, designed loading/empty/error states (skeleton for map/chart, card absent on 404, error-code table → copy), neutral colour for course series (status colours untouched), WCAG AA via jest-axe, all copy in español neutro with diacritics. | PASS |
| IV. Performance | `GET /course` ≤ 3 statements and `GET /results` +1 statement (no N+1, `selectinload` on variant), both asserted by statement count; geometry capped at 800 points; upload processing bounded and timed; map and chart behind `React.lazy` + Suspense; text-first rendering for 3G; cold-start state already handled by the frontend. Upload endpoint is a transactional write with CPU-bound parsing — budget documented in the route docstring; if a 5 MB worst case exceeds 1 500 ms on Render it is recorded in Complexity Tracking, not silently accepted. | PASS |
| V. Youth Psych. Safeguards | Not a psychological instrument. Adjacent rule honoured: AI text about a minor keeps the existing guardrails; the new block only adds course facts, never rider comparisons; notes (unreviewed coach text) are excluded from prompts. | N/A / respected |
| Quality gate — Privacy | `data-privacy-guard` audit is a mandatory task over `gpx_processing.py`, the course router/service, `results_read` changes, the AI loader and the parent endpoint; the recording (coach's personal data) is stripped in memory and never persisted, logged or traced; structured log carries only ids, counts and codes; parents' `my_categories` lists only their own athletes; no name, date or medical field is touched. Fixtures synthetic. | PASS |
| Quality gate — Stack discipline | No new runtime dependency; FIT deferred precisely to avoid one; `leaflet-gpx` left unused rather than replaced. | PASS |
| Quality gate — Security | Content-type allow-list, extension check, gzip/zip sniff, 5 MB cap, defusedxml pre-parse (fail closed) before gpxpy, root-element check ("magic bytes" for a text format), no filename in logs, RBAC via existing `require_role` + `allowed_athlete_ids_for`, 404 (not 403) to parents outside the válida. | PASS |
| Quality gate — AI features | Course facts enter through the same veto-guarded block as conditions; forbidden-names guardrails unchanged on output; two golden cases pin presence/absence behaviour; `RACE_AI_PROMPT_VERSION=race_analyst_v2` remains a no-deploy rollback (v2 prompts untouched and render with the extended context). | PASS |
| Quality gate — Observability | Structured event `race_course_variant_processed` with ids/counts/method/reason only; audit trail via `record_audit` on every mutation; no bodies in logs. | PASS |
| Workflow — Branching | `feat/043-race-course-profile` (Spec Kit hook, renamed to the project's `<type>/<slug>` convention). Conventional Commits, no AI mention. | PASS |

**Post-design re-check (after Phase 1)**: unchanged. Two spec-level adjustments were made during planning and are recorded in `spec.md` Assumptions: (1) GPX only, FIT deferred (R-01); (2) the wizard's "optional Circuito step" is realised as a panel in the existing step 3 after commit, because the válida only exists once the import is committed (R-13) — the `STEPS` array and its focus contract are untouched. No Complexity Tracking entry is needed.

## Project Structure

### Documentation (this feature)

```text
specs/043-race-course-profile/
├── plan.md                          # This file
├── spec.md                          # Feature specification (owner decisions of 2026-09-15 in Assumptions)
├── research.md                      # Phase 0 — R-01…R-16
├── data-model.md                    # Phase 1 — two tables, four columns, value objects, migration, invariants
├── quickstart.md                    # Phase 1 — validation scenarios
├── contracts/
│   ├── course-api.md                # seven endpoints, CourseRead, error table, tests
│   ├── gpx-processing.md            # process_gpx steps, constants, tests
│   ├── results-derived-figures.md   # ResultRow deltas, derivation rule, season rows
│   ├── ai-course-block.md           # state key, loader, formatter, prompt block, golden cases
│   └── ui-course.md                 # tab, wizard panel, results columns, parent card, a11y, tests
├── checklists/requirements.md       # spec quality checklist
└── tasks.md                         # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/<rev>_race_course_profile.py      # new, down_revision=d5b125474e2b
├── app/
│   ├── models/
│   │   ├── race_event.py                              # + terrain_type, technical_difficulty, key_sectors, course_notes; relationships
│   │   ├── race_course_variant.py                     # new
│   │   └── race_course_category_setup.py              # new
│   ├── schemas/
│   │   ├── race_course.py                             # new: CourseRead, VariantRead, SetupIn/Read, DescriptionUpdate, enums
│   │   ├── race_event.py                              # RaceEventRead + description fields + has_course_data
│   │   └── race_results.py                            # ResultRow/CategoryResults/EventResultsRead deltas
│   ├── routers/race_events.py                         # + 7 course routes (same prefix, same deps, record_audit)
│   └── services/race/
│       ├── course/
│       │   ├── __init__.py
│       │   ├── gpx_processing.py                      # process_gpx, constants, CourseProcessingError
│       │   ├── derived.py                             # derive_figures(setup, status, race_time_ms, laps_behind)
│       │   └── service.py                             # get_course (coach/parent scoping, suggestion), variants CRUD, setups replace, description patch
│       ├── results_read.py                            # + one query, figures per row, has_course_data
│       ├── analytics.py                               # athlete per-válida rows + avg_speed_kmh (no aggregates)
│       ├── ai/state.py                                # + course_context
│       ├── ai/queries.py                              # + fetch_course_context (never selects course_notes)
│       ├── ai/nodes/load_race_data.py                 # fills course_context
│       ├── agents/analyst.py                          # + format_course_meta, AnalystV3Input.course_meta, "course_block"
│       └── prompts/race_analyst_v3.md, race_season_summary_v3.md   # + course block (v2 untouched)
├── evals/race_analyst/golden_v3/case_0XX_course_present.json, case_0XX_course_absent.json
└── tests/
    ├── helpers/gpx_builder.py                         # synthetic GPX generator (circle, laps, jitter, extensions)
    ├── services/race/test_gpx_processing.py
    ├── services/race/test_results_derived.py
    ├── services/race/ai/test_course_block.py
    └── routers/test_race_course.py

frontend/src/
├── api/raceCourse.ts · types/raceCourse.types.ts · schemas/raceCourse.ts · hooks/race/useRaceCourse.ts
├── components/race/course/                            # CourseTab, VariantsCard, VariantUploadDialog, CategorySetupTable,
│                                                      # CourseDescriptionCard, EditCourseDescriptionDialog, CourseSummary,
│                                                      # CourseMap (lazy), ElevationProfile (lazy), __tests__/
├── components/competitions/results/ResultsTable.tsx   # + Distancia / Vel. prom. columns when has_course_data
├── components/competitions/import/ImportWizard.tsx    # step-3 "Circuito (opcional)" panel
├── routes/competitions/CompetitionDetailPage.tsx      # + "circuito" tab (lazy)
├── routes/competitions/CompetitionFormPage.tsx        # success link "Agregar circuito"
├── routes/parents/competitions/ParentCompetitionResultsPage.tsx   # + CourseSummary card (404 → absent)
├── routes/parents/calendar/ParentEventDetailPage.tsx  # + CourseSummary card when a válida is linked
└── test/msw/raceCourseHandlers.ts
frontend/e2e/race-course.spec.ts · e2e/fixtures/course_3laps.gpx, course_reduced.gpx (synthetic)

docs/10-race-results/course-profile-design.md (new) · runbook-ops.md (addendum) · docs/implementation-status.md · docs/technical-notes.md · CLAUDE.md (Alembic head)
```

**Structure Decision**: Web application layout already in place (`backend/` modular monolith + `frontend/` SPA). The feature adds a cohesive `app/services/race/course/` package rather than spreading helpers across the race module, extends the existing race-events router instead of mounting a new one (parents already reach that prefix for results/roster), and groups all new UI under `components/race/course/` so the same `CourseSummary` serves coach tab, wizard panel and both parent pages.

## Implementation waves (input for `/speckit-tasks`)

1. **W1 — Backend core**: models, migration, `gpx_processing.py` + builder + tests, `service.py`, schemas, router routes with denied paths, privacy tests, `-m mysql` round-trip.
2. **W2 — Derived figures & AI**: `derived.py`, `results_read` + `analytics` deltas and tests, AI state/loader/formatter/prompts, golden cases and run, `data-privacy-guard` audit.
3. **W3 — Frontend**: api/hooks/types/schemas + MSW, course components with jest-axe, tab + wizard panel + form link, results columns, parent cards, Playwright spec.
4. **W4 — Docs & release**: design doc + runbook addendum, implementation-status and technical-notes, CLAUDE.md head note, post-deploy smoke.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. (If the 5 MB worst-case upload measures above the 1 500 ms write budget on Render, record it here with the measured value and the mitigation chosen — e.g. lowering the cap to 3 MB — before merge.)
