# Implementation Plan: Session Content Unification

**Branch**: `claude/coach-profile-ux-analysis-kaar7d` | **Date**: 2026-07-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/032-session-content-unification/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Today "attach training content to a session" is three contradictory interactions: intervals attach inline on the session itself (the good pattern — `SessionDetailPage.tsx:855-1037`), strength requires building a block on a separate page and then searching for the target session by name (`BlockBuilderPage.tsx:355-377`, no preselect), and technique can *only* create a brand-new duplicate session through a parallel creation endpoint (`POST /api/technique/sessions`) — there is no way to attach technique exercises to a session that already exists. The backend gap analysis (research.md R1) confirms this precisely: a new endpoint, `POST /api/technique/sessions/{training_session_id}/exercises`, is required, reusing the existing `TechniqueSessionExercise` table with **no migration**; strength needs no backend change at all, only a frontend preselect (`?session_id=` query param) and a new "pick an existing block" picker mirroring the intervals reference component (`TemplatePicker.tsx`); intervals is untouched.

The technical approach: (1) one new backend endpoint (idempotent, append-only, club-scoped, coach/admin RBAC) closing the technique gap; (2) a new shared "attach" interaction generalized from `TemplatePicker.tsx` and applied to both technique (fully inline, no navigation) and strength (preselect + a new pick-existing picker, alongside the existing build-new page); (3) `SessionDetailPage.tsx`'s 7 stacked blocks reorganized into 4 sections (Resumen/Asistencia/Plan/Media) on the shared `ui/tabs.tsx` primitive with `?section=` URL sync copied from `AthleteDetailPage.tsx`'s `?tab=` pattern, defaulting to Asistencia on the day of the session and Resumen otherwise; (4) a "hoy" quick filter and non-color-alone today marker on the sessions list. Every existing age-band safety gate (`AgeBandGuardrailDialog`, `AgeGateDialog`) is reused completely unchanged, at the same trigger points, with zero new gates invented.

## Technical Context

**Language/Version**: Python ≥3.13 (`backend/pyproject.toml:5`) — backend, unchanged. TypeScript ~6.0.2 (`frontend/package.json:39`) — frontend, unchanged.

**Primary Dependencies**: Backend — FastAPI + SQLAlchemy 2 (async) + Alembic + MySQL 8.4 + PyJWT/bcrypt, all existing, no new dependency. Frontend — React 19.2.5, Vite ^8.0.4, shadcn/ui + Tailwind, TanStack Query ^5.101.0, Zustand ^5.0.12, React Hook Form ^7.72.1 + Zod ^4.3.6, all existing; `@radix-ui/react-tabs` (already installed and consumed by `components/ui/tabs.tsx` and `CompetitionDetailPage.tsx`) is **reused**, not newly added.

**Storage**: MySQL 8.4 (Hostinger in prod). **No schema change.** Verified in `data-model.md`: the new endpoint writes into the existing `technique_session_exercises` table (`backend/app/models/technique_exercise.py:256-293`) exactly as `assemble_technique_session` already does today, just without also creating a `TrainingSession` row. Strength (`strength_session_blocks`) and intervals (`interval_structures`) tables are untouched.

**Testing**: Backend — `pytest` + `httpx.AsyncClient` + `aiosqlite`, following the existing `backend/tests/technique/test_technique_*.py` convention. Frontend — `vitest` + Testing Library + `jest-axe`; Playwright (`@playwright/test`, existing infra per `specs/028-frontend-design-foundation/research.md` R7) for the target-size sweep and the end-to-end attach-all-three flow. Full detail in `quickstart.md`.

**Target Platform**: Backend on Render (Docker, Oregon, free tier, ~50s cold start) — unchanged. Frontend SPA — coach tablet (outdoor, gloved, sunlight) and parent Android mobile (intermittent 3G/4G) — unchanged; this feature is coach-only (parents/athletes have no visibility into session-content attach, RBAC unchanged).

**Project Type**: Web application (existing `backend/` + `frontend/` modular monolith). No new services, no new routers beyond one new route handler inside the existing `technique.py` router.

**Performance Goals**: New endpoint p95 ≤ 1500 ms (Constitution IV transactional-write budget). `SessionDetailPage` (already the densest coach route) must not regress its LCP budget (≤ 3.5 s, data-dense route bucket) — sectioning is expected to *help* this (see Constitution Check, Principle IV) by creating the option to defer non-active-section queries, though this plan does not mandate that optimization. Attach interactions: ≤ 3 interactions per content type end-to-end (SC-001).

**Constraints**: 48×48 px interactive targets (Constitution III, non-negotiable) — `ui/tabs.tsx`'s `TabsTrigger` currently defaults to `min-h-11` (44 px, `tabs.tsx:42`), one step short of the club floor; adopting it on the session-detail page (the first heavy consumer of this primitive) requires bumping it to `min-h-12` (48 px) as part of this feature. Zero new runtime dependencies. Zero DB migration. Zero regression in either existing age-band gate (SC-007, non-negotiable). Español neutro (Colombia) for all new UI copy. 3G/cold-start tolerant (reuses `ErrorState`'s `isColdStartError` detector from `specs/028-frontend-design-foundation/contracts/shared-components.md`).

**Scale/Scope**: 1 new backend endpoint (+1 new service function, +2 new Pydantic schemas, 0 new models). Frontend: `SessionDetailPage.tsx` refactored into 4 sections; 2 new picker components (`TechniqueAttachPicker`, `StrengthBlockPicker`, both modeled on `TemplatePicker.tsx`); 1 new shared "which session?" picker (reused at 2 entry points); `BlockBuilderPage.tsx` gains `?session_id=` read + auto-attach; `SessionFiltersBar.tsx` + `SessionsTable.tsx` gain the "hoy" affordance; `lib/datetime.ts` gains 2 small exported helpers. No new routes — every existing path is reused (FR-008).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — no new violations surfaced; table reflects the post-design state.*

| Principle | Status | Notes |
|---|---|---|
| **I. Code Quality & Maintainability** | PASS | This feature *is* a rule-of-three cleanup: 3 divergent "attach" implementations (intervals-inline / strength-search-then-attach / technique-create-new-session) collapse to 1 generalized pattern (`TemplatePicker.tsx` as the template). New backend code reuses existing helpers verbatim (`_load_exercises_by_ids`, `_coach_club_id`, `_require_coach_or_admin`) rather than duplicating them. New frontend pickers are modeled on, not copy-pasted from, `TemplatePicker.tsx`. Public service function (`attach_exercises_to_session`) will carry a docstring per the project's existing convention (every other function in `assembler.py`/`blocks.py` does). |
| **II. Testing (NON-NEGOTIABLE)** | PASS (planned) | New endpoint: happy path, RBAC-negative, not-found-negative, validation-negative, **and an idempotency regression test** (contracts/attach-technique-to-session.md — this is the specific regression FR-009 requires). Frontend: vitest for all 3 attach flows + `?section=` URL-sync + "hoy" filter + jest-axe on every new component. Explicit **gate-regression tests** assert `AgeBandGuardrailDialog`/`AgeGateDialog` still fire from the unified entry points (SC-007's zero-regression bar) — see `quickstart.md`. |
| **III. User Experience Consistency** | PASS | Single attach pattern across all three content types (the feature's whole purpose). One tab primitive (`ui/tabs.tsx`) adopted instead of perpetuating the 2 other existing tab implementations (`AthleteDetailPage.tsx`'s hand-rolled buttons, `CompetitionDetailPage.tsx`'s raw `TabsPrimitive`) — new code does not add a 4th variant. `ConfirmDialog`/`EmptyState`/`sonner` toasts (028 primitives) adopted in the new pickers. Es-CO copy throughout. 48 px targets enforced, including a found-and-fixed pre-existing shortfall in the shared `ui/tabs.tsx` default (44→48 px) discovered while designing this feature. |
| **IV. Performance Requirements** | PASS | No new dependency; no bundle-size risk beyond code already installed. Sectioning `SessionDetailPage` creates (but does not mandate, to avoid scope creep) the option to defer non-active-section queries — today all 6 of the page's queries fire unconditionally on mount (`SessionDetailPage.tsx:376-398`) regardless of scroll position; this is flagged as a natural low-risk follow-on in `contracts/session-sections.md`, not a requirement of this plan. New endpoint budgeted at p95 ≤ 1500 ms per Constitution IV's write budget; no N+1 (bounded queries regardless of item-batch size, tested per `quickstart.md`). |
| **V. Youth Psychological Assessment Safeguards** | N/A | This feature does not touch psychological instruments. **Adjacent minors-safety note** (not Principle V, but the same spirit): the two existing **physical-training age-band gates** — `AgeBandGuardrailDialog` (strength, 10-12 bodyweight-only override recording) and `AgeGateDialog` (intervals, Z3+ hard block / confirm-and-record for 10-12) — are preserved verbatim, at the same trigger points, with zero new bypass path (research.md R9; SC-007 is the measurable form of this requirement). |

**Quality Gates**: No PII in the new endpoint (numeric IDs only — technique exercises carry no athlete data). RBAC on the new endpoint reuses the existing coach/admin dependency already on `technique.py` (no new permission logic to test in isolation — the existing dependency's tests already cover it; the new endpoint's own RBAC test confirms it is actually applied). Stack discipline: no new runtime dependency (verified above).

## Project Structure

### Documentation (this feature)

```text
specs/032-session-content-unification/
├── plan.md              # This file
├── research.md          # Phase 0 output — backend gap analysis + 10 other decisions
├── data-model.md         # Phase 1 output — entity cardinalities, new payload shapes, no-migration verification
├── quickstart.md         # Phase 1 output — validation guide
├── contracts/
│   ├── attach-technique-to-session.md   # new backend endpoint contract
│   ├── session-sections.md              # UI contract — 4 sections, ?section= sync
│   └── unified-attach-flow.md           # interaction contract — 3 content types, 1 pattern
├── checklists/
│   └── requirements.md   # already existed, all items pass
└── tasks.md              # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── routers/
│   │   └── technique.py                     # + POST /sessions/{id}/exercises (new route handler)
│   ├── schemas/
│   │   └── technique.py                      # + AttachExercisesRequest, AttachExercisesResponse
│   ├── services/
│   │   └── technique/
│   │       └── assembler.py                  # + attach_exercises_to_session() (new function)
│   └── models/
│       └── technique_exercise.py             # unchanged — TechniqueSessionExercise reused as-is
└── tests/
    └── technique/
        └── test_technique_attach_to_session.py   # new

frontend/
├── src/
│   ├── routes/
│   │   ├── training/
│   │   │   └── SessionDetailPage.tsx         # refactor: 7 stacked blocks → 4 ui/tabs sections
│   │   └── strength/
│   │       └── BlockBuilderPage.tsx          # + ?session_id= read/lock, + auto-attach + redirect to session
│   ├── components/
│   │   ├── training/
│   │   │   ├── SessionFiltersBar.tsx         # + "Hoy" quick filter action
│   │   │   ├── SessionsTable.tsx             # + today row/card marker (icon + label, not color alone)
│   │   │   └── session-plan/                 # NEW folder — the unified Plan section
│   │   │       ├── PlanSection.tsx           # NEW — hosts technique + strength + intervals + empty state
│   │   │       ├── TechniqueAttachPicker.tsx # NEW — mirrors TemplatePicker.tsx for catalog exercises
│   │   │       ├── StrengthBlockPicker.tsx   # NEW — mirrors TemplatePicker.tsx for existing blocks
│   │   │       └── SessionPickerDialog.tsx   # NEW — "¿a qué sesión?" for library-initiated attach
│   │   ├── strength/
│   │   │   └── AgeBandGuardrailDialog.tsx    # unchanged — reused verbatim
│   │   ├── intervals/
│   │   │   ├── AgeGateDialog.tsx             # unchanged — reused verbatim
│   │   │   └── TemplatePicker.tsx            # unchanged — the reference component
│   │   └── ui/
│   │       └── tabs.tsx                      # TabsTrigger min-h-11 → min-h-12 (48px floor fix)
│   ├── hooks/
│   │   ├── technique/
│   │   │   └── useTechnique.ts               # + useAttachTechniqueItems()
│   │   └── strength/
│   │       └── useStrength.ts                # unchanged — useAttachBlock() reused as-is
│   ├── api/
│   │   └── technique.ts                      # + attachExercisesToSession()
│   ├── store/
│   │   └── trainingFiltersStore.ts           # + setToday() action
│   └── lib/
│       └── datetime.ts                       # + todayISODate(), isToday() (club-timezone helpers)
└── e2e/
    └── session-content-unification.spec.ts   # new Playwright flow (or extends target-size.spec.ts)
```

**Structure Decision**: existing web-application layout (`backend/` FastAPI monolith + `frontend/` React SPA) is unchanged — this feature adds files inside the existing `technique` module (backend) and the existing `training`/`strength`/`intervals` component families (frontend); no new top-level directory beyond one new frontend component folder (`components/training/session-plan/`) that groups the unified Plan-section pieces, mirroring the existing `components/technique/`, `components/strength/`, `components/intervals/` per-domain grouping convention already in the repo.

## Complexity Tracking

*No entries.* No Constitution Check violation was identified (table above is all PASS/N/A). No Alembic migration is required — `data-model.md` verifies every table this feature touches (`technique_session_exercises`, `strength_session_blocks`, `interval_structures`) is reused exactly as it exists today; the one new backend endpoint adds Pydantic request/response schemas only. No new runtime dependency is introduced.
