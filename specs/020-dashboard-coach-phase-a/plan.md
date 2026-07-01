# Implementation Plan: Coach Dashboard — Phase A (Correctness, Performance & Club-Scope Fixes)

**Branch**: `claude/spec-kit-agent-setup-poepvz` (session branch; feature dir `020-dashboard-coach-phase-a`) | **Date**: 2026-07-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/020-dashboard-coach-phase-a/spec.md`

## Summary

Fix three real defects on the coach `/dashboard` — an **N+1 request storm** (one `GET /api/athletes/{id}` per athlete), an **unbounded actionable list** (~150 rows), and **missing explicit club scoping** for minors' data — plus two low-cost improvements (reframe the PHV metric, surface `training_implications`). The whole feature is **frontend-only**: it re-derives every dashboard datum from the **existing `GET /api/alerts`** endpoint, which already scopes to the coach's clubs server-side and already returns `last_measurement_date`, `measurement_status`, `age_decimal`, `category`, `growth_alerts`, and `training_implications` per athlete. No backend endpoint, schema, or migration changes.

Reuses the existing React 19 + Vite + shadcn/ui + TanStack Query frontend. **No AI/LLM, no external integration, no new runtime dependency.** The 3-band redesign (Hoy/esta semana, Pulso del club, aggregated anxiety) is explicitly deferred to Phase B/C.

**Tooling for processes**: code review of `auth.store.ts`, `alerts.py`, `useDashboardStats.ts`, `MeasurementAlerts.tsx`, and `AthletesListPage.tsx` resolved all three Open Questions (OQ-1/2/3) — see spec "Open Questions — RESOLVED". No web/MCP research required; the design is a straight refactor onto an existing, well-understood contract.

## Technical Context

**Language/Version**: TypeScript 5 / React 19 (frontend only).

**Primary Dependencies**: React 19 + Vite, shadcn/ui + Tailwind v4, TanStack Query, Zustand (auth store), React Router. **No new dependency.**

**Storage**: None touched. Reuses `GET /api/alerts` (read-only). No MySQL/Alembic change.

**Testing**: frontend `vitest` + Testing Library + `jest-axe`. New tests: `useDashboardStats` (no N+1, derives from alerts), `MeasurementAlerts` (truncation + sort + "Ver todas"), `DashboardPage` (loading/error/empty-club/zero-athletes states), and a **cross-club isolation** test (coach of club X sees no club Y / seed athlete).

**Target Platform**: mobile web — coach on a tablet in the field, intermittent 3G/4G, ~50 s Render cold start.

**Project Type**: Web application (existing `frontend/`); backend untouched.

**Performance Goals**: dashboard athlete-data load is **O(1) requests** (single shared `/alerts` query), independent of athlete count; 0 `GET /api/athletes/{id}` requests on load. Explicit loading/error/empty states under cold start.

**Constraints**: minors privacy (Ley 1581) — club scoping (FR-005) is an access-control requirement, verified by an automated isolation test; no new sensitive field surfaced beyond what `/alerts` already returns; español neutro for all product copy; WCAG 2.1 AA maintained on the changed blocks.

**Scale/Scope**: single club per coach today (union of coach's clubs if >1; no selector — OQ-1); ~150 athletes; read-only, low complexity.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Code Quality & Maintainability** — PASS. Refactor collapses `useDashboardStats` onto the same `["alerts"]` query the `MeasurementAlerts` block already uses (single source of truth), removing the `getAthlete`-per-id fan-out. No new abstraction; net code reduction. Passes `eslint` + `tsc --noEmit`.
- **II. Testing (NON-NEGOTIABLE)** — PASS (planned). N+1 regression test (assert 0 `/athletes/{id}` calls); truncation + urgency-sort test; explicit-state tests (loading/error/0-clubs/0-athletes); **cross-club isolation** privacy test; PHV formula test; `jest-axe` on the dashboard.
- **III. UX Consistency & Language** — PASS. All new/changed copy in español neutro ("V de A con medición vigente", "Ver todas (M)", empty states). shadcn/ui + Tailwind unchanged; designed loading/empty/error/cold-start states. This plan/spec in English (dev corpus).
- **IV. Performance** — PASS. Removes the O(N) request storm; single cached `/alerts` round-trip; truncated list caps DOM rows at 8; cold-start handled by the existing query error/loading states.
- **V. Youth Psychological Assessment Safeguards (NON-NEGOTIABLE)** — N/A (no questionnaire). Its data-minimization ethos still governs: FR-005 club scoping + NFR-003 forbid surfacing any athlete outside the coach's clubs or any new sensitive field; no anxiety signal is added in Phase A (deferred to Phase C behind a dedicated privacy review).

**Result**: No violations. Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/020-dashboard-coach-phase-a/
├── plan.md              # This file
├── research.md          # Phase 0 output (OQ resolutions + decisions)
├── data-model.md        # Phase 1 output (no new entities; view-model mapping)
├── quickstart.md        # Phase 1 output (validation scenarios)
├── contracts/
│   └── alerts-consumption.md   # how the dashboard consumes the EXISTING /alerts contract
└── tasks.md             # /speckit-tasks output (not created here)
```

### Source Code (repository root — files touched)

```text
frontend/src/
├── hooks/athletes/
│   ├── useDashboardStats.ts        # REWRITE: derive from useAlerts, drop getAthlete N+1
│   └── useAlerts.ts                # reuse as-is (shared ["alerts"] query cache)
├── routes/dashboard/
│   └── DashboardPage.tsx           # EDIT: explicit loading/error/0-clubs/0-athletes states; PHV card copy
├── components/dashboard/
│   └── MeasurementAlerts.tsx       # EDIT: truncate to 8 + urgency sort + "Ver todas (M)"; training_implications in growth block
└── **/__tests__/                   # NEW/UPDATED vitest specs incl. cross-club isolation
```

Backend: **untouched** (`/api/alerts` already satisfies scope + fields).

## Phase 0 — Research (see research.md)

All unknowns resolved by code review; no NEEDS CLARIFICATION remain. Key decisions:
1. **Data source**: single `GET /api/alerts` (no `club_id`) → coach-club-scoped union; drop `getAthletes` + `getAthlete`-per-id.
2. **PHV formula**: V = athletes with `measurement_status ∉ {overdue, never}`; A = active-club athlete count; copy "V de A con medición vigente"; "--" when A=0.
3. **Truncation**: 8 rows, urgency sort (overdue desc by `days_overdue` → due_soon asc → never); "Ver todas (M)" → `/athletes` (no status filter added).

## Phase 1 — Design & Contracts

- **data-model.md**: no new persisted entity. Documents the `DashboardStats` view-model derived from `AlertsSummary` (existing `alerts.types.ts`), replacing the fields previously computed from `AthleteDetailOut`.
- **contracts/alerts-consumption.md**: documents the existing `/api/alerts` response fields the dashboard now relies on (read-only consumption contract; no API change).
- **quickstart.md**: runnable validation scenarios mapping to the spec's acceptance scenarios (N+1 absence, truncation, isolation, PHV formula, states).
- **Agent context**: update the SPECKIT marker in `CLAUDE.md` to reference this plan.

## Complexity Tracking

Empty — no constitution violations, no new dependencies, no backend change.
