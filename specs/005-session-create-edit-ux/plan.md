# Implementation Plan: Session Create/Edit Flow & UX Overhaul

**Branch**: `claude/session-create-edit-ux-Ogacm` | **Date**: 2026-06-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-session-create-edit-ux/spec.md`

## Summary

Rebuild the coach/admin "Create / Edit Training Session" experience as a guided
multi-step wizard (reusing the `ImportWizard` stepper pattern) that is reliable on a
tablet/phone in the field over intermittent 3G/4G. The work fixes a confirmed
end-to-end persistence defect (`session_kind` and `objectives` render in the form and
validate client-side but are dropped by the backend `TrainingSessionCreate`/
`TrainingSessionUpdate` schemas and `create_session` service), exposes `coach_notes` in
the form (already accepted by the backend), adds local draft autosave + restore so field
work is never lost, upgrades validation to inline/per-step with a blocking summary,
improves athlete call-up, folds route-file attach and the parent-notification choice into
a single pass (route file auto-uploaded to the existing endpoint right after create), and
guarantees ≥48 px touch targets, WCAG 2.1 AA, and minors' privacy. Scope is a frontend UX
overhaul plus a minimal backend contract fix; the `planned → executed → cancelled`
lifecycle model is unchanged and **no Alembic migration is required** (the
`training_sessions.session_kind` enum and `objectives` columns already exist since
migration `d4e5f6a7b8c9`, Phase 1.9).

## Technical Context

**Language/Version**: Backend Python 3.14 (FastAPI); Frontend TypeScript 5 + React 19 (Vite)

**Primary Dependencies**: Backend — FastAPI, SQLAlchemy 2 async, Pydantic v2 (no new deps).
Frontend — React Hook Form + Zod (`@hookform/resolvers`), TanStack Query, Zustand,
shadcn/ui + Tailwind v4, `lucide-react`. **No new runtime dependency** — draft autosave
uses the browser `localStorage` API directly via a small custom hook (no external library).

**Storage**: MySQL 8.4 (existing `training_sessions`, `session_attendance` tables — no
schema change). Client-side `localStorage` for transient drafts only (never synced).

**Testing**: Backend `pytest` + `httpx.AsyncClient` + `aiosqlite`. Frontend `vitest` +
Testing Library + `jest-axe`. MSW for API mocking.

**Target Platform**: Web SPA. Primary surfaces: coach tablet (landscape) and parent/coach
Android phone over simulated 3G. Backend on Render free tier + MySQL Hostinger.

**Project Type**: Web application (FastAPI backend + React frontend).

**Performance Goals**: Wizard initial route bundle stays within the constitution's
≤250 KB gzip budget (heavy/optional pieces lazy-loaded, mirroring `ImportWizard`'s lazy
`DiffTable`). Create/update writes p95 ≤ 1500 ms; reads p95 ≤ 500 ms (Principle IV).
Autosave writes are debounced and never block typing.

**Constraints**: español neutro (Colombia) for all UI copy; no minors' PII in logs,
errors, or `localStorage` left behind after save/discard; ≥48 px touch targets; 0 axe
violations; no native HTML5 validation competing with Zod (`noValidate`); Render cold-start
(~50 s) surfaced as an explicit state, not a spinner.

**Scale/Scope**: One club's roster (tens of athletes, occasionally ~60). ~2 pages
refactored (create + edit share `SessionFormPage`), ~6–8 new/changed frontend components
+ 1 draft hook, ~5 backend schema/service touch-points.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**I. Code Quality & Maintainability** — PASS. Reuses existing patterns (`ImportWizard`
stepper, `DurationPicker`, `ToggleGroup` chips, `AthletesMultiSelect`, `NotifyParentsDialog`,
`sessionDiff` helpers). New step components are named by what they render. The autosave hook
is a single documented utility (rule-of-three respected: it is the first generic draft
hook, kept minimal). Backend change is additive and typed. `ruff` + `tsc` + `eslint` must
pass.

**II. Testing Standards (NON-NEGOTIABLE)** — PASS (planned). Backend: new tests asserting
`session_kind`/`objectives` round-trip on create AND update (the regression tests that fail
on today's code), plus a privacy test asserting no athlete name appears in logs on
create/update. Frontend: vitest for the wizard (step navigation, per-step validation block,
draft save/restore/discard, athlete selection, route-file auto-upload success+failure,
notification outcome states) and `jest-axe` on the page and every dialog/sheet (0
violations). Bug-fix-as-regression-test rule honored for the persistence defect.

**III. User Experience Consistency** — PASS. shadcn/ui + Tailwind only; RHF + Zod with
inline localized errors and `noValidate`; ≥48 px targets; dialogs/sheets trap focus and
close on Escape; loading/empty/error states for every async surface (sessions/athletes
load, route-file upload, save, notification). Status color semantics reused (green success,
amber attention, red blocking). Copy in español neutro.

**IV. Performance Requirements** — PASS. No new N+1 (athletes already fetched once via
`useAthletes`; sessions/attendance via existing hooks). Wizard steps and any heavy subview
lazy-loaded to respect bundle budget. Autosave debounced; writes within budget. Cold-start
state surfaced.

**Quality Gates** — Privacy (Ley 1581): `data-privacy-guard` audit required (reads/writes
minor-identifiable data). Drafts in `localStorage` treated as sensitive and cleared on
save/discard; logs stay ids-only. Stack discipline respected (no new dependency). No AI in
this feature.

**Result**: PASS — no violations; Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/005-session-create-edit-ux/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (API contract delta)
│   └── training-session-api.md
├── checklists/
│   └── requirements.md  # from /speckit-specify
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── schemas/training_session.py        # ADD session_kind, objectives to Create/Update/Read(+Parent)
│   ├── services/training/sessions.py      # set session_kind/objectives on create; add _FIELD_LABELS entries
│   └── routers/training_sessions.py       # (no signature change; verify enum serialization on read)
└── tests/
    ├── routers/test_training_sessions*.py # round-trip + privacy regression tests
    └── services/                          # service-level create/update field persistence

frontend/
├── src/
│   ├── routes/training/SessionFormPage.tsx        # REWRITE as wizard host (create+edit)
│   ├── components/training/
│   │   ├── session-wizard/                         # NEW: Stepper, StepGeneral, StepAthletes,
│   │   │   ├── SessionWizard.tsx                   #      StepRouteNotes, StepReview, ErrorSummary
│   │   │   ├── SessionStepper.tsx
│   │   │   ├── StepGeneral.tsx
│   │   │   ├── StepAthletes.tsx
│   │   │   ├── StepRouteNotes.tsx
│   │   │   └── SessionErrorSummary.tsx
│   │   ├── AthletesMultiSelect.tsx                 # ENHANCE: chips, sticky count, ≥48px rows
│   │   ├── RouteFileDropzone.tsx                   # NEW: pick .gpx/.fit in-form (auto-upload after create)
│   │   ├── DurationPicker.tsx                      # reused
│   │   └── NotifyParentsDialog.tsx                 # reused/extended for outcome states
│   ├── hooks/useFormDraft.ts                       # NEW: debounced localStorage autosave + restore
│   ├── schemas/trainingSession.schema.ts          # per-step refinement; coach_notes; shared Strava regex
│   ├── types/trainingSession.types.ts             # already has session_kind/objectives (verify)
│   └── api/trainingSessions.ts                     # reuse create/update + uploadRouteFile
└── test/ (vitest + msw handlers)
```

**Structure Decision**: Existing Option-2 web layout (`backend/` + `frontend/`). The wizard
lives under `frontend/src/components/training/session-wizard/`; `SessionFormPage.tsx` becomes
a thin host that loads session+attendance for edit mode and mounts the wizard. No new
top-level directories.

## Complexity Tracking

> No constitution violations — section intentionally empty.
