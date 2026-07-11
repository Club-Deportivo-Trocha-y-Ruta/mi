# Implementation Plan: Frontend Design Foundation & Everyday Reliability

**Branch**: `claude/coach-profile-ux-analysis-kaar7d` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/028-frontend-design-foundation/spec.md`

## Summary

Establish the shared frontend foundation the whole redesign program builds on, while fixing every confirmed reliability defect: (1) missing shadcn/ui form + feedback primitives are added and wrapped in shared components (`PageHeader`, `EmptyState`, `ErrorState`, `StatCard`, `ConfirmDialog`, `StatusBadge`, unified `Stepper`); (2) design tokens are consolidated (adopt the already-registered `shadow-ring` utility at 177 inline call sites, register `--color-border-gray` and semantic status tokens in `@theme`, ship Cal Sans self-hosted via `@fontsource/cal-sans`); (3) field usability is enforced (rubric sliders → `ToggleGroup` steppers, ≥48 px targets, sunlight-contrast token adoption); (4) the dead-end bugs are fixed with regression tests (admin dead-click via role-aware `AthleteLink`, retry affordances via `ErrorState`, calendar day-click navigation, hardcoded season, `ConfirmModal` autoFocus, `window.confirm` removal, wizard focus management, batched newsletter summary endpoint). Technical approach grounded in `research.md`; shared component APIs in `contracts/shared-components.md` are the interface features 029–033 consume.

## Technical Context

**Language/Version**: TypeScript ~6.0 (frontend); Python 3.12 (backend, one endpoint)

**Primary Dependencies**: React 19.2, Vite 8, Tailwind CSS 4.2 (`@tailwindcss/vite`, `@theme` in `src/style.css`, `cssVariables: false` in `components.json`), shadcn/ui (new-york style) over Radix (several Radix packages already installed: label, select, popover, radio-group, separator, scroll-area), TanStack Query 5.101 (+persist), React Hook Form 7.72 + Zod 4.3, lucide-react, react-router-dom 7.14. New runtime deps (justified in Constitution Check): `sonner` (toasts), `@fontsource/cal-sans` (self-hosted OFL-1.1 font). Backend: FastAPI + SQLAlchemy 2 async (existing newsletter tables only).

**Storage**: N/A (no schema changes; one new read-only backend aggregate over existing newsletter data)

**Testing**: vitest + Testing Library + jest-axe (unit/a11y), MSW (API mocks), Playwright 1.50 (`frontend/e2e/`, Chromium preinstalled) for target-size + flow verification, pytest + httpx for the new endpoint

**Target Platform**: Mobile-first responsive web; primary device tablet (Android/iPad class) outdoors; desktop for planning; backend on Render free tier

**Project Type**: Web application (existing `frontend/` + `backend/` monorepo)

**Performance Goals**: LCP ≤ 2.5 s on mid-tier Android over simulated 3G for dashboard/athlete-list (constitution IV); newsletter overview requests O(1) vs O(athletes); no route bundle regression ≥ 10%

**Constraints**: WCAG 2.1 AA floor; ≥48×48 px touch targets; focus-trapped, Escape-dismissible dialogs; es-CO product copy; `prefers-reduced-motion` preserved; Render cold start (~50 s) must render as "waking", never as error

**Scale/Scope**: ~46 coach routes / ~117 files touched at token level (177 mechanical shadow swaps), 7 new shared components, 4 shadcn primitive groups added, 1 backend endpoint, ~10 bug regression tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Code Quality | `ruff`/`mypy` (backend endpoint), `eslint`/`tsc --noEmit` (frontend) pass; duplication removed on third copy — this feature exists to enforce the rule of three (59 headers, 81 retry blocks, 5 modal chromes → shared components) | ✅ PASS |
| II. Testing (NON-NEGOTIABLE) | Every bug fix lands with a regression test that fails unfixed (admin dead-click, calendar click, autoFocus, season, N+1); jest-axe on every new/modified page- and dialog-level component; new endpoint gets happy + negative pytest; Playwright target-size spec is deterministic (fixed viewport, seeded data) | ✅ PASS |
| III. UX Consistency | This feature implements the principle: shadcn/ui-sourced components in `components/ui/`, new shared patterns in `components/shared/` (written justification = this plan), RHF+Zod untouched, ≥48 px targets, Radix focus-trap/Escape on all dialogs, loading/empty/error states everywhere, status color semantics tokenized, es-CO copy | ✅ PASS |
| IV. Performance | `sonner` ≈ +4 KB gz in shared bundle; `@fontsource/cal-sans` woff2 (~20–30 KB, `font-display: swap`, cached) — both under the 10% regression bar and justified below; N+1 newsletter fix *improves* p95; no new heavy static imports into shared layouts | ✅ PASS |
| V. Youth Psych. Assessment Safeguards | Not touched — no anxiety-module behavior changes in 028 | ✅ N/A |
| Quality Gates | New runtime deps justification (stack discipline): `sonner` replaces 2+ hand-rolled toast implementations and is the current shadcn-recommended toast (smaller than maintaining our own); `@fontsource/cal-sans` delivers decision D3 with pinned versioned files, no third-party font service at runtime (privacy: zero external requests). Minors' privacy: no PII in new logs/tests; correlation-ID logging on the new endpoint | ✅ PASS |

**Post-design re-check (after Phase 1)**: no new violations introduced; `contracts/shared-components.md` keeps all components presentational (no data-layer coupling); the single backend endpoint is read-only aggregate with RBAC (coach/admin) enforced via the existing permissions service pattern. ✅ PASS

## Project Structure

### Documentation (this feature)

```text
specs/028-frontend-design-foundation/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── shared-components.md          # Props contracts for the shared component kit (consumed by 029–033)
│   └── newsletter-status-summary.md  # New read-only endpoint contract
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
frontend/
├── src/
│   ├── style.css                    # @theme: shadow consolidation, --color-border-gray, semantic status
│   │                                #   tokens, --font-display → 'Cal Sans'; @fontsource imports
│   ├── components/
│   │   ├── ui/                      # ADD: input.tsx, label.tsx, select.tsx, form.tsx, checkbox.tsx,
│   │   │                            #   radio-group.tsx, switch.tsx, alert.tsx, alert-dialog.tsx,
│   │   │                            #   separator.tsx, sonner.tsx (Toaster)
│   │   ├── shared/                  # ADD: PageHeader.tsx, EmptyState.tsx, ErrorState.tsx, StatCard.tsx,
│   │   │                            #   ConfirmDialog.tsx, StatusBadge.tsx, Stepper.tsx, AthleteLink.tsx
│   │   │                            #   (absorb components/common/; move PHVBadge → components/athletes/)
│   │   ├── training/                # RubricSliders → discrete steppers (ToggleGroup); DurationPicker min-h;
│   │   │                            #   NotifyParentsDialog → Radix Dialog; MediaGallery confirm swap;
│   │   │                            #   MediaUploadZone capture; SessionWizard step-focus management
│   │   ├── competitions/import/     # ImportWizard: unified Stepper + step-focus; ad-hoc toast migration
│   │   ├── dashboard/               # MeasurementAlerts → AthleteLink; stat cards → StatCard/Card
│   │   └── layout/                  # AppShell: shadow token adoption only (grouping itself is feature 030)
│   ├── routes/
│   │   ├── calendar/CalendarPage.tsx                     # handleDateClick → navigate with ?date=
│   │   ├── training/AthleteNewslettersDashboardPage.tsx  # batched summary hook + pending affordance
│   │   └── (all list pages)                              # ErrorState/EmptyState adoption; season fix
│   └── hooks/training/useNewsletterStatusSummary.ts      # NEW: one-call summary
├── e2e/
│   └── target-size.spec.ts          # NEW: Playwright ≥48px assertion sweep on key coach screens
backend/
├── app/routers/                     # ADD: GET newsletter status summary (existing newsletters router)
├── app/schemas/                     # NewsletterStatusSummary schema
└── tests/                           # pytest: summary endpoint happy + RBAC-negative
```

**Structure Decision**: Existing web-app monorepo (`frontend/` + `backend/`). All new shared components live in `frontend/src/components/shared/` (absorbing `components/common/`); shadcn primitives in `frontend/src/components/ui/` per `components.json` aliases. Single backend addition follows the existing router/schema/test layout.

## Complexity Tracking

> No constitution violations. New-dependency justifications recorded in the Constitution Check table (`sonner`, `@fontsource/cal-sans`) as required by the stack-discipline gate.
