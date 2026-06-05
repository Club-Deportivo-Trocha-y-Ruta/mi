# Implementation Plan: RPE OMNI Scale Labels Refactor

**Branch**: `002-rpe-omni-scale-labels` | **Date**: 2026-06-05 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-rpe-omni-scale-labels/spec.md`

## Summary

Fix the confusing verbal descriptors on the coach-facing OMNI perceived-exertion (RPE) slider. Today "Moderado" is shown at value **3** on a 0–10 scale; web research into the validated OMNI scale (Robertson) and the modern 0–10 training scale confirms that "moderate"-class wording belongs at the **middle (5–6)**, with effort rising symmetrically from rest (0) to maximal (10). The change is **frontend copy only**: redistribute the descriptor words (and align the emoji faces) so each integer 0–10 carries an intuitive word with "Moderado" centered at 5. The stored value (`rpe_omni`, integer 0–10) and everything downstream are untouched — no backend, schema, migration, or data change. See [research.md](./research.md) for the evidence and the final Spanish mapping.

## Technical Context

**Language/Version**: TypeScript 5 / React 19 (Vite). No backend changes.

**Primary Dependencies**: React, React Hook Form (already wraps the control via `Controller`). No new dependency.

**Storage**: N/A — `rpe_omni` value unchanged (backend `int 0–10`, CHECK `BETWEEN 0 AND 10`). No Alembic migration.

**Testing**: `vitest` + Testing Library. Update `frontend/src/components/training/RubricSliders.test.tsx`; existing a11y tests (`RubricSliders.a11y.test.tsx`) must stay green.

**Target Platform**: Web SPA — coach on tablet (primary surface for this control).

**Project Type**: Web application (frontend touched only).

**Performance Goals**: No change — static string array; zero bundle/runtime impact.

**Constraints**: español neutro (Colombia) per Constitution III; WCAG 2.1 AA preserved (the `aria-label`/`aria-valuenow` wiring is unchanged; descriptor text is decorative relative to the slider's value semantics).

**Scale/Scope**: One component (`RubricSliders.tsx`), one constant array (`RPE_LABELS`), optionally the `RPE_FACES` array; one test file updated. ~15 lines.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan satisfies it |
|-----------|----------------------------|
| **I. Code Quality** | Change is a rename/reorder of an existing constant array; `eslint` + `tsc --noEmit` must pass. No new abstraction, no duplication introduced. Constant gets a short comment citing the OMNI source. |
| **II. Testing (NON-NEGOTIABLE)** | The slider value→label mapping is branching display logic, so `vitest` tests are added asserting the new label for representative values (0, 3, 5, 10) and the monotonic/`Moderado`-at-5 invariant. This is effectively a regression test for the reported defect (label was wrong at 3). a11y suite must remain at zero violations. |
| **III. UX Consistency** | Descriptors stay español neutro (Colombia) with diacritics; non-judgmental, age-appropriate wording (no clinical terms). Reuses the existing control pattern (native range input already in the codebase) — no new component pattern, so no justification needed. Touch target and focus behavior unchanged. |
| **IV. Performance** | Static string array; no bundle-size, query, or render-cost impact. No lazy-loading concerns. |

**Privacy (Ley 1581)**: No athlete-identifiable data involved (generic effort words). No `data-privacy-guard` audit required; no PII, no AI, no logs touched.

**Result**: PASS. No violations → Complexity Tracking table omitted.

## Project Structure

### Documentation (this feature)

```text
specs/002-rpe-omni-scale-labels/
├── plan.md              # This file
├── spec.md              # Feature spec
├── research.md          # Phase 0 — OMNI scale evidence + final Spanish mapping
├── data-model.md        # Phase 1 — value contract (unchanged) + label-mapping table
├── quickstart.md        # Phase 1 — how to implement & verify
├── contracts/
│   └── rpe-omni-labels.md  # UI contract: number → descriptor → face
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
frontend/
└── src/
    └── components/
        └── training/
            ├── RubricSliders.tsx          # EDIT: RPE_LABELS (+ RPE_FACES alignment)
            ├── RubricSliders.test.tsx     # EDIT: assert new labels + invariants
            └── RubricSliders.a11y.test.tsx# UNCHANGED (must stay green)
```

**Structure Decision**: Existing web-app layout. The entire change is localized to the `frontend/src/components/training/` directory; no backend (`backend/app/**`) file is touched. The OMNI value contract lives in `backend/app/schemas/training_session.py` and `backend/app/models/training_session.py` and is explicitly **out of scope** (referenced only to confirm the 0–10 range is preserved).

## Complexity Tracking

> No Constitution violations — section intentionally empty.
