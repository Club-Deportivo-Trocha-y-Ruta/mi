# Implementation Plan: Technique & Gymkhana Library + Session Builder

**Branch**: `claude/dazzling-maxwell-uvdqoz` (session branch; feature dir `018-technique-gymkhana-library`) | **Date**: 2026-06-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/018-technique-gymkhana-library/spec.md`

## Summary

Build a coach/admin-facing module that turns the club's verified technique research (`docs/14-tecnica-gymkana-7-15/research.md`) into an in-app, searchable **catalog** of technique drills and gymkhana exercises (filterable by skill, age band 7–9 / 10–12 / 13–15, difficulty, and available materials), each with a runnable detail card and an **illustrative circuit layout**. The coach assembles chosen exercises into a technique session that is persisted **through the existing Training Sessions module** (no parallel session store) and — for athletes with a record — tracks per-skill progress (introducido / en progreso / dominado) across the season, always as individual growth anchored to biological age and **never** as an athlete-vs-athlete comparison. The catalog is **pre-seeded** (≈24 exercises + A–H skill taxonomy + materials + ASCII circuit layouts) via an idempotent Alembic data migration, in español neutro, and is editable/hideable by coach/admin.

Reuses the existing FastAPI + SQLAlchemy 2 async + Alembic + MySQL backend and the React 19 + Vite + shadcn/ui + TanStack Query frontend. **No AI/LLM and no external integration** are required for this feature.

**Tooling for processes (per request)**: best-practices research used **MCP** (Context7 for SQLAlchemy 2 async relationship/loading docs) and **web search** (ASCII-vs-SVG layout rendering & accessibility; async many-to-many filtering). Seeded catalog content is loaded as **data** sourced verbatim (Spanish) from the verified research report — never invented.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript 5 / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 (async, aiomysql), Alembic, Pydantic v2, PyJWT + bcrypt (existing auth); React 19 + Vite, shadcn/ui + Tailwind v4, TanStack Query, Zustand, React Hook Form + Zod. **No new runtime dependency.**

**Storage**: MySQL 8.4 (Hostinger prod). New tables + seed via a single Alembic migration. Seeding pattern mirrors `alembic/versions/c4d5e6f7a8b9_seed_race_categories.py`.

**Testing**: backend `pytest` + `httpx.AsyncClient` + `aiosqlite`; frontend `vitest` + Testing Library + `jest-axe`.

**Target Platform**: Linux server (Render free tier, Oregon) + mobile web (coach on a tablet in the field, intermittent 3G/4G, ~50 s cold start).

**Project Type**: Web application (existing `backend/` + `frontend/`).

**Performance Goals**: catalog/detail read endpoints p95 ≤ 500 ms; session-assemble + progress writes p95 ≤ 1500 ms; catalog route LCP ≤ 2.5 s on mid-tier Android/3G; assume ~50 s Render cold start with an explicit "starting the server" UI state. Catalog is small (~24+ rows) and aggressively cached client-side.

**Constraints**: minors privacy (Ley 1581) — per-athlete progress (US4) is the only minors-data surface: coach/admin only, no PII in logs, no comparative/ranking surface anywhere; español neutro for all product copy and seeded content; WCAG 2.1 AA including a **text alternative** for the monospace circuit layout; 7–15 content must function even when a 7–9 athlete record does not exist.

**Scale/Scope**: single club; ~24 seeded exercises growing with curation; dozens of athletes; A–H skill taxonomy; read-heavy catalog, low write volume (assemble/curate/progress).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Code Quality & Maintainability** — PASS. Extends the existing models/schemas/routers/services layering; new public services (`services/technique/*`) get docstrings. Normalized join tables (no premature "generic content engine"). Seed content lives in one data module, loaded by the migration.
- **II. Testing (NON-NEGOTIABLE)** — PASS (planned). Filtering logic (skill/age/difficulty/material subset incl. "sin material") gets unit + router tests; RBAC negative tests (parent/athlete denied, cross-club denied); a test asserts session-assemble creates a **real `TrainingSession`** (visible in the existing list, no parallel store) and that hiding/editing an exercise leaves a saved session intact (FR-020); progress append/current-state + "no comparison surface" invariant tests; a privacy test asserts no minor PII leaks in progress responses/logs; frontend vitest + `jest-axe` on every page/dialog incl. the layout text alternative.
- **III. UX Consistency & Language** — PASS. All product copy and seeded catalog content in español neutro; shadcn/ui + Tailwind; filters and forms via RHF + Zod with localized inline errors; 48×48 touch targets; designed loading/empty/error states (incl. empty-filter and cold-start); circuit layout rendered responsively with a screen-reader text alternative. This plan/spec/docs in English (dev corpus).
- **IV. Performance** — PASS. `selectinload` for exercise→skills/materials/age_bands to avoid N+1; small catalog cached in TanStack Query; progress board and any heavy table lazy-loaded; cold-start banner on every async surface; no >50 KB static imports added to shared layouts.
- **V. Youth Psychological Assessment Safeguards (NON-NEGOTIABLE)** — N/A as a clinical instrument (this module administers **no** psychological questionnaire). Its **mastery-climate ethos** still governs: per-skill progress is framed as personal growth anchored to biological age (PHV) with **zero** ranking/comparison surfaces (FR-017, SC-005), and seeded content embodies the club non-negotiables (fun first, skills > fitness, cadence ≥70, RPE primary, no structured intervals 7–9). Domain correctness reviewed by `technique-coach` + `sports-science-advisor`.

**Result**: No violations. Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/018-technique-gymkhana-library/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (REST contracts)
│   └── rest-api.md
├── checklists/
│   └── requirements.md  # from /speckit-specify
└── tasks.md             # /speckit-tasks output (not created here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── models/
│   │   ├── technique_skill.py          # A–H taxonomy (seeded)
│   │   ├── technique_material.py       # materials incl. "sin material" (seeded)
│   │   └── technique_exercise.py       # exercise, age-band/skill/material joins,
│   │                                   #   technique_session_exercises, athlete_skill_progress
│   ├── schemas/
│   │   └── technique.py                # catalog filter/read, detail, assemble, progress, curation
│   ├── routers/
│   │   └── technique.py                # catalog read+filter, detail, assemble-session,
│   │                                   #   progress CRUD, curation (add/edit/hide)
│   ├── services/
│   │   └── technique/
│   │       ├── catalog.py              # filter query (skill/age/difficulty/material subset)
│   │       ├── assembler.py            # build a TrainingSession via training_svc + join rows
│   │       └── progress.py             # append progress event; current + season history
│   ├── data/
│   │   └── technique_catalog.py        # seed payload (skills, materials, ~24 exercises, layouts)
│   └── tests/                          # filtering, RBAC, assemble, progress, privacy, a11y
└── alembic/versions/                   # new migration: technique_* tables + idempotent seed

frontend/
└── src/
    ├── routes/technique/               # CatalogPage, ExerciseDetailPage, SessionBuilderPage,
    │                                   #   AthleteProgressPage (P2), CatalogAdmin (P3)
    ├── components/technique/           # CatalogGrid, FilterBar, ExerciseCard, CircuitLayout,
    │                                   #   SessionAssembler (warmup/main/cooldown), MixedAgeNotice,
    │                                   #   SkillProgressBoard, ExerciseForm
    ├── hooks/                          # useTechniqueCatalog, useTechniqueExercise,
    │                                   #   useAssembleTechniqueSession, useAthleteSkillProgress
    └── api/technique.ts                # technique API client
```

**Structure Decision**: Web-application layout, extending the existing `backend/` and `frontend/` trees and their established conventions (models/schemas/routers/services; routes/components/hooks/api). Session assembly **reuses** `app/services/training` (`create_session`) so the result is an ordinary `TrainingSession` — it does not fork session management.

## Phase 0 — Research (→ research.md)

Resolved unknowns: (1) **illustrative-layout representation** — store the ASCII croquis from the research report as preformatted monospace text + a shared legend, render in a responsive `<pre>` with a screen-reader text alternative; SVG/image upload deferred. (2) **catalog data model** — normalized M2M join tables (exercise↔skill, exercise↔material) + an age-band join, with `selectinload` and a NOT-EXISTS subset filter for materials. (3) **seeding** — idempotent Alembic data migration from a Python seed module (precedent: `seed_race_categories`). (4) **session reuse** — wrap `training_svc.create_session` + a `technique_session_exercises` link table (FR-011/013/020). (5) **progress shape** — append-only `athlete_skill_progress` events → latest-per-skill is "current", full set is the season history; 3-state status. See [research.md](./research.md).

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md): `technique_skills`, `technique_materials`, `technique_exercises` (+ `technique_exercise_age_bands`, `technique_exercise_skills`, `technique_exercise_materials`), `technique_session_exercises`, `athlete_skill_progress`; reuse `training_sessions`, `athletes`, `clubs`, `users`.
- [contracts/rest-api.md](./contracts/rest-api.md): catalog list+filter, exercise detail, assemble-session (wraps Training Sessions), per-athlete progress read/set, curation (create/edit/hide).
- [quickstart.md](./quickstart.md): end-to-end validation scenarios mapped to the user stories.
- Agent context: CLAUDE.md SPECKIT marker updated to point at this plan.

## Phase 2 — Tasks (handled by `/speckit-tasks`)

`/speckit-tasks` will generate `tasks.md`, group tasks by user story (P1 → P3) for independent delivery, and **assign each task to a specialized subagent** (see Appendix A). Dependency-ordered, `[P]` for parallelizable.

## Phase 3 — Implementation (handled by `/speckit-implement`)

`/speckit-implement` will run a **dynamic workflow**: dispatch tasks to the assigned specialized agents, respecting dependencies, parallelizing independent `[P]` tasks per phase, and re-checking the Constitution gates (esp. minors-privacy and the no-comparison rule for US4) before completion.

## Appendix A — Specialized-agent assignment (feeds /speckit-tasks & /speckit-implement)

| Work area | Specialized agent |
|---|---|
| Migration, table design, indexes, M2M join tables, enums (`values_callable`), idempotent seed migration | `database-architect` |
| Models, schemas, routers, RBAC, catalog filter / assembler / progress services | `fastapi-architect` |
| Catalog grid, filter bar, exercise detail + circuit layout, session assembler, progress board, curation form, hooks, API client | `react-ui-engineer` |
| Field/tablet usability, filter & assemble flow (<3 min), layout legibility + WCAG AA text alternative, cold-start/empty states | `ux-researcher` |
| Backend tests (filtering, RBAC, assemble-creates-real-session, progress, privacy invariants) + frontend vitest + `jest-axe` | `qa-engineer` |
| Minors-privacy audit on US4 (no PII in logs, coach-only, no comparison surface) | `data-privacy-guard` |
| Verify seeded content embodies non-negotiables (fun first, skills>fitness, cadence ≥70, no 7–9 intervals, mastery climate) | `technique-coach` + `sports-science-advisor` |
| Seed-data extraction/normalization from `docs/14-tecnica-gymkana-7-15/research.md` into the seed module | `data-analyst` |
| Module doc in `docs/`, cross-link research report, CLAUDE.md status + implementation-status update | `technical-writer` |
| Run seed migration on Render, deploy, smoke test, cold-start mitigation | `devops-engineer` / `release-manager` |

Orchestration delegated by `engineering-lead` (full-stack), with `head-coach-lead` consulted for domain/methodology correctness.

## Complexity Tracking

No constitution violations — table intentionally empty.
