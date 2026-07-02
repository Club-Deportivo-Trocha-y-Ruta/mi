# Implementation Plan: Strength Training Exercise Library

**Branch**: `claude/spec-kit-agent-setup-poepvz` (spec dir `021-strength-training-library`; work continues on the current branch per coach instruction) | **Date**: 2026-07-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/021-strength-training-library/spec.md`

## Summary

Coach-facing, searchable, illustrated catalog of youth strength-training exercises (bodyweight vs. gym-equipment; age bands 10-12 / 13-15), assembled into reusable "strength blocks" with a live ≤30-minute duration indicator and an age-band guardrail (warn-and-allow with recorded override), attached to existing Training Sessions. Coach-only per-athlete progress notes, no comparisons. Static curated content — no AI. Technical approach: mirror feature 018 (technique-gymkhana-library) end to end — same model/service/router split, same seed-in-migration pattern, same frontend routes/components/hooks layout — with three deltas: (a) a first-class reusable **StrengthBlock** entity instead of direct session assembly, (b) free-text search in addition to facet filters, (c) a duration budget indicator and override recording.

## Technical Context

**Language/Version**: Python 3.12+ (backend), TypeScript / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async + aiomysql, Alembic, Pydantic v2 (backend); Vite, shadcn/ui + Tailwind, TanStack Query, Zustand, React Hook Form + Zod (frontend). **No new runtime dependencies.**

**Storage**: MySQL 8.4 (Hostinger prod, Docker local). New tables chained off Alembic head `f1a2b3c4d5e6`.

**Testing**: pytest + httpx.AsyncClient + aiosqlite (backend, `backend/tests/strength/`); vitest + Testing Library + jest-axe + MSW (frontend).

**Target Platform**: Web SPA — coach on tablet in the field (primary), admin on desktop. Backend on Render free tier.

**Project Type**: Web application (existing FastAPI monolith + React SPA).

**Performance Goals**: Constitution IV budgets — p95 ≤ 500 ms reads / ≤ 1500 ms writes; catalog list eager-loads via `selectinload` (no N+1); lazy-loaded routes ≤ 150 KB gzipped each.

**Constraints**: Coach-only RBAC (`require_role([admin, coach])`); minors privacy (no PII in logs/AI/exports); original illustrations only (ASCII + alt text, zero third-party images); 30-min ceiling is a configurable business rule (single constant), never presented as clinical; offline-tolerant catalog browsing (TanStack Query cache).

**Scale/Scope**: 1 club, ~20-30 athletes, 1-2 coach users. Seed catalog ~22 exercises. 4 new pages, ~6 new tables, 1 migration.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance |
|---|---|
| **I. Code Quality** | Mirrors 018's proven structure (models/services/routers split, key-factory hooks). `slug` idempotent seeds, soft-hide (`is_hidden`) not hard-delete. Ruff/mypy + eslint/tsc gates. Docstrings on new services. |
| **II. Testing (NON-NEG)** | Backend: happy + negative path per router/service/permission (`tests/strength/` mirroring 018's 12-file suite incl. `test_rbac.py`, `test_progress_privacy.py`, `test_perf_queries.py`). Frontend: vitest for filter bar, block builder (duration indicator boundaries: within/at/over), guardrail dialog, progress board; jest-axe on all page-level components. Privacy invariants: progress notes never leak athlete PII in list endpoints. |
| **III. UX Consistency** | shadcn/ui components only; product copy in español neutro (Colombia); RHF + Zod forms; 48×48 px touch targets; loading/empty/error states on every async surface (incl. sparse "gym-equipment + 10-12" empty state); amber = guardrail warning, red = blocked, consistent tokens. WCAG AA: ASCII illustrations wrapped in `role="img"` + `aria-label` (018 `CircuitLayout` fallback pattern). |
| **IV. Performance** | Catalog query eager-loads age bands/equipment via `selectinload` + query-count test. Routes lazy via `React.lazy`. Duration indicator computed client-side (no chatty API). Render cold-start banner already global. |
| **V. Youth Psych Safeguards** | **N/A** — no psychological instruments administered, scored, or interpreted. Adjacent guardrails honored: no diagnosis-like copy, mastery-climate wording in progress notes UI, no athlete comparisons (FR-015). |
| **Quality Gates** | Privacy: progress notes coach-only, no PII in logs; no AI provider involved (FR-018). Stack discipline: zero new deps. Security: RBAC in router deps + `services/permissions.py` club scope, exercised by tests. No file uploads in v1 (ASCII illustrations are text). |

**Gate result: PASS** — no violations; Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/021-strength-training-library/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── strength-api.md  # Phase 1 output
├── checklists/
│   └── requirements.md  # From /speckit-specify
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── models/
│   │   └── strength.py                    # StrengthExercise, StrengthExerciseAgeBand,
│   │                                      # StrengthBlock, StrengthBlockEntry,
│   │                                      # StrengthSessionBlock, StrengthProgressNote + enums
│   ├── schemas/
│   │   └── strength.py                    # Pydantic schemas
│   ├── routers/
│   │   └── strength.py                    # /api/strength (mirrors routers/technique.py)
│   ├── services/
│   │   └── strength/
│   │       ├── catalog.py                 # search/filter (facets + free-text LIKE)
│   │       ├── blocks.py                  # block CRUD, duration totals, override recording
│   │       └── progress.py                # per-athlete notes (mirrors technique/progress.py)
│   └── data/
│       └── strength_catalog.py            # ~22 seeded exercises (mirrors technique_catalog.py)
├── alembic/versions/
│   └── a7b8c9d0e1f2_strength_training_library.py   # down_revision = "f1a2b3c4d5e6"; schema + seed
└── tests/
    └── strength/                          # mirrors tests/technique/ suite

frontend/src/
├── routes/strength/
│   ├── CatalogPage.tsx
│   ├── ExerciseDetailPage.tsx
│   ├── BlockBuilderPage.tsx               # assembly + duration indicator + guardrail
│   └── AthleteProgressPage.tsx
├── components/strength/
│   ├── CatalogGrid.tsx / ExerciseCard.tsx / FilterBar.tsx
│   ├── ExerciseIllustration.tsx           # <pre> ASCII + role="img" (018 CircuitLayout fallback pattern)
│   ├── BlockAssembler.tsx                 # running total + within/at/over indicator
│   ├── AgeBandGuardrailDialog.tsx         # warn-and-allow + recorded override
│   └── ProgressNotesBoard.tsx
├── hooks/strength/useStrength.ts          # strengthKeys factory + queries/mutations
├── api/strength.ts                        # BASE = "/api/strength"
├── schemas/strength.schemas.ts            # Zod
├── types/strength.types.ts
└── test/msw/strengthHandlers.ts
```

**Structure Decision**: Existing web-app layout (backend monolith + frontend SPA). Feature 018's directory conventions replicated 1:1 under `strength/` naming — a reviewer familiar with 018 can navigate 021 without a map.

## Complexity Tracking

> No constitution violations. Table intentionally empty.
