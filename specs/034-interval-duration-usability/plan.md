# Implementation Plan: Interval Block Duration Usability — mm:ss Entry and Open-Ended "Until Lap Button" Blocks

**Branch**: `main` (explicit user request: no dedicated feature branch) | **Date**: 2026-07-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/034-interval-duration-usability/spec.md`

## Summary

Feature 026's interval editor forces raw-seconds duration entry and cannot express an open-ended block ("free until the athlete presses the lap button"), which every reference platform supports (Garmin "Lap Button Press" step type, TrainingPeaks open-ended steps, intervals.icu "Press lap"). Approach: (1) add an explicit per-block `duration_type` discriminator (`fixed` | `open_lap`) with `duration_s` made nullable — additive Alembic migration, existing rows default to `fixed`; (2) replace the raw-seconds input with a reusable `MmSsInput` (Min + Seg 0–59 fields) keeping seconds as the stored unit; (3) matching engine v2: open steps consume a lap positionally with a new informational status `libre`, never judged against the ±30% tolerance; (4) PDF instructivo and template library render/preserve the open type.

## Technical Context

**Language/Version**: Python 3.12 (FastAPI backend), TypeScript 5 / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async + aiomysql, Alembic, Pydantic v2; React 19 + Vite, shadcn/ui + Tailwind, TanStack Query, React Hook Form + Zod; WeasyPrint (PDF instructivo)

**Storage**: MySQL 8.4 — tables `interval_structure_blocks`, `interval_template_blocks` (feature 026, migration `b5c6d7e8f9a0`); `duration_s` stays integer seconds

**Testing**: pytest + httpx.AsyncClient + aiosqlite (backend); vitest + Testing Library + jest-axe (frontend)

**Target Platform**: Web SPA (coach on tablet, parents Android 3G/4G) + Render free tier backend

**Project Type**: Web application (backend + frontend)

**Performance Goals**: No new endpoints or queries — existing budgets apply unchanged (p95 ≤ 500 ms reads / 1500 ms writes); no bundle-relevant additions (one small input component)

**Constraints**: Backward compatibility hard requirement (FR-011/SC-003): existing rows, drafts, and stored plan-vs-actual comparisons must keep meaning without user-visible migration effects. Coach/admin-only surface (parents/athletes 403, unchanged from 026)

**Scale/Scope**: 2 tables altered (2 columns each), ~6 backend files, ~6 frontend files, 1 Jinja PDF template, 1 migration; no new endpoints

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Code Quality | ruff/mypy + eslint/tsc pass; `MmSsInput` named for what it produces; docstrings on changed service functions | ✅ Planned — no violations |
| II. Testing (NON-NEGOTIABLE) | New validators: happy + negative pytest per rule; matching v2 unit tests (libre, sin_dato, mixed shift); frontend tests for `MmSsInput`, `BlockRow` gating, total label, comparison badge; jest-axe on editor + comparison table | ✅ Planned in quickstart/tasks |
| III. UX Consistency | Two-field Min/Seg entry (48px touch targets, native numeric keyboard) beats masked input for gloved tablet use; RHF+Zod inline errors; "Libre" badge uses neutral gray (informational) per color semantics; copy in español neutro ("Libre — hasta botón de vuelta") | ✅ Design conforms |
| IV. Performance | No new endpoints/queries/bundles; PDF change is template-conditional only | ✅ N/A impact |
| V. Youth Psych Safeguards | Not a psychological-assessment feature. Existing age-gate (Z3+ for 10–12) reused unchanged on open blocks | ✅ Not applicable / unchanged |

**Post-Phase-1 re-check**: design introduces no new component patterns, no budget exceptions, no principle violations. Gate PASS.

## Project Structure

### Documentation (this feature)

```text
specs/034-interval-duration-usability/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── api-delta.md     # Phase 1 — schema/endpoint deltas (no new endpoints)
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks (not created here)
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/
│   └── c7d8e9f0a1b2_interval_block_duration_type.py   # NEW — add duration_type, duration_s nullable (both block tables)
├── app/
│   ├── models/interval_structure.py        # +IntervalDurationType enum; duration_type cols; duration_s nullable
│   ├── schemas/intervals.py                # BlockIn/BlockOut: duration_type (default 'fixed'), duration_s optional; cross-field validators
│   └── services/intervals/
│       ├── structures.py                   # validate_structure_blocks: open-only-warmup/cooldown, never-in-repeat, duration presence; flatten_blocks carries open steps
│       ├── matching.py                     # ENGINE_VERSION 2; status 'libre'; skip tolerance for open steps
│       ├── match_runner.py                 # passes duration_type through flatten (no logic change expected)
│       ├── templates.py                    # template validation parity + copy-on-attach preserves duration_type
│       └── instructivo_pdf.py              # context: duration_type per block
├── templates/documents/pdf/session_instructivo.html   # open block → "Libre — hasta botón de vuelta"
└── tests/
    ├── test_interval_structures.py         # validator + schema cases (extend)
    ├── test_interval_matching.py           # engine v2 cases (extend)
    └── test_interval_instructivo.py        # PDF context cases (extend)

frontend/src/
├── components/intervals/
│   ├── MmSsInput.tsx                       # NEW — Min/Seg (0–59) pair ⇄ seconds
│   ├── BlockRow.tsx                        # MmSsInput replaces raw seconds; duration-type select (warmup/cooldown only, disabled in repeat group)
│   ├── StructureEditor.tsx                 # total = fixed-only sum + "+ calentamiento libre / + libre" suffix
│   ├── PlanVsActualTable.tsx               # planned cell "Libre"; neutral 'libre' badge
│   └── (template editor reuses BlockRow — verify path)
├── schemas/intervals.schema.ts             # duration_type literal; duration_s nullable; refinements (open rules, seg 0–59 handled in component)
└── components/intervals/__tests__/         # MmSsInput, BlockRow gating, totals, table badge, axe
```

**Structure Decision**: Web application layout (existing `backend/` + `frontend/`); feature is a delta on the feature-026 module — no new modules, no new endpoints, one new reusable input component under the existing `components/intervals/`.

## Complexity Tracking

No constitution violations — table not needed.

## Design Decisions (from Phase 0 research + sequential analysis)

1. **Explicit `duration_type` discriminator** (`fixed` | `open_lap`) over nullable-`duration_s`-as-sentinel: mirrors Garmin's step-duration-type enum, unambiguous, extensible (distance later), migrates old rows via `server_default='fixed'` without touching values. Stored as project-convention `values_callable` enum.
2. **Matching engine version 1 → 2**: output vocabulary changes (new status `libre`). Stored comparisons keep their recorded engine version and render unchanged (FR-008, SC-003). Open step + lap → `libre` (informational, actual duration shown, no tolerance division); open step without lap → existing `sin_dato`; noise threshold (<10 s laps) unchanged.
3. **`MmSsInput` = two numeric fields (Min / Seg 0–59)**, not a masked `mm:ss` input: better for gloved tablet use (48 px targets, native numeric keyboard), simpler RHF/Zod integration, per-field accessible labels. Form source of truth stays `duration_s` (seconds); the component converts both ways — no schema unit change, totals/formatMmSs untouched.
4. **Contract stays additive**: `duration_type` optional-in with default `fixed`; `total_planned_duration_s` documented as fixed-only sum; frontend derives the "+ libre" suffix from blocks it already receives — no new response fields.
5. **Validation enforced twice** (Zod UI + server `validate_structure_blocks`), order-independent: open→{warmup,cooldown}, open→no repeat group, open→no duration, fixed→duration > 0.

## Phase 0 → research.md; Phase 1 → data-model.md, contracts/api-delta.md, quickstart.md (see files).
