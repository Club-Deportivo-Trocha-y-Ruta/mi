# Implementation Plan: Coach Navigation Redesign

**Branch**: `claude/coach-profile-ux-analysis-kaar7d` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/030-coach-navigation-redesign/spec.md`

## Summary

Replace the flat, 12-item, ungrouped `AppShell` sidebar (`frontend/src/components/layout/AppShell.tsx:37-193`) with a single `NavArea[]` configuration (`frontend/src/lib/navigation.ts`) driving three coordinated surfaces: a desktop sidebar with 6 collapsible task-oriented groups (Inicio, Entrenamiento, Competencias, Atletas, Familias, Biblioteca), a mobile/tablet bottom tab bar (4 areas + "Más" sheet) below the `md` breakpoint, and a header user menu + quick-create control replacing today's loose "Mi perfil"/"Cerrar sesión"/"Salud IA" buttons. Clicking an area label always navigates straight to its default sub-view (no hub interstitials, preserving today's 1-click cost to Calendario/Atletas/Competencias); sibling views within an area (Calendario ↔ Sesiones ↔ Actividades; Válidas ↔ Sin enlazar ↔ Panorama de temporada) share one promoted pill pattern already proven in `CompetitionDetailPage`. The change is presentation-only — **zero route or permission changes** (FR-009) — and folds in the three previously-orphaned entry points (AI session assistant, season panorama, strength-block builder) plus a one-term-per-concept naming sweep (FR-008). Technical approach grounded in `research.md`; the full route inventory and role matrix live in `contracts/` and `data-model.md`.

## Technical Context

**Language/Version**: TypeScript ~6.0 (frontend only — no backend files touched by this feature)

**Primary Dependencies**: React 19.2, react-router-dom 7.14, Tailwind CSS 4.2, the `radix-ui` umbrella package (already a direct dependency — its `Collapsible` export is used for sidebar disclosure, confirmed resolvable at zero marginal size, research R1), existing shadcn primitives `ui/dropdown-menu.tsx` and `ui/sheet.tsx`, lucide-react icons. **No new runtime dependency added.**

**Storage**: N/A — no schema, no persisted nav state (data-model.md §4)

**Testing**: vitest + Testing Library + jest-axe (component/a11y), Playwright 1.50 (`frontend/e2e/`, Chromium preinstalled) for the breakpoint sweep and target-size reuse from 028-R7

**Target Platform**: Mobile-first responsive web; tablet is the coach's primary field device; desktop for planning — same as 028/029

**Project Type**: Web application (existing `frontend/` + `backend/` monorepo) — this feature is a **frontend-only slice**; `backend/` is untouched

**Performance Goals**: `AppShell` and its config render on every authenticated route, so its own bundle weight is on the critical path for all of them — zero bundle regression is the target (not just under the 10% ceiling); LCP budgets (constitution IV) carry over unchanged since no page's own content changes

**Constraints**: WCAG 2.1 AA floor; ≥48×48 px interactive targets; full keyboard operability; es-CO product copy; no URL changes (FR-009); no RBAC/permission changes; skip-to-content affordance must survive the shell rewrite

**Scale/Scope**: 39 surviving coach/admin routes remapped into 6 areas (`contracts/navigation-model.md`); ~7 new frontend components + 1 rewritten (`AppShell`); 0 backend files; 0 migrations; depends on 028 (shared components/tokens, planned not yet built) and 029 (route survivor set, spec-only not yet planned) landing first per program order

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — no changes.*

| Principle | Gate | Status |
|---|---|---|
| I. Code Quality | `eslint`/`tsc --noEmit` pass; `lib/navigation.ts` replaces 12 duplicated `{(isCoach \|\| isAdmin) && <NavLink>}` blocks (`AppShell.tsx:39-191`) with one data-driven map — rule-of-three duplication removed, not added; new components (`SidebarNav`, `BottomNav`, `MoreSheet`, `UserMenu`, `QuickCreate`, `SiblingViewTabs`) are each named for what they render, not how | ✅ PASS |
| II. Testing (NON-NEGOTIABLE) | `AppShell.test.tsx` rewritten (assertions enumerated in `quickstart.md`); new component tests for `SidebarNav`/`BottomNav`/`MoreSheet`/`UserMenu`/`QuickCreate`; pure-function unit tests for `resolveAreaDefaultTo`/`isAreaActive`/`getBottomBarAreas` (`lib/__tests__/navigation.test.ts`) — including the role-filtered-nav regression the task requires; jest-axe zero-violations on the shell and every opened menu/sheet state; Playwright breakpoint sweep is deterministic (fixed viewports, no seeded data needed since it's structural, not data-driven) | ✅ PASS |
| III. UX Consistency | All new interactive controls ≥48×48 px (contracts/mobile-navigation.md, header-actions.md); skip-link (`AppShell.tsx:199-204`) preserved verbatim; es-CO labels throughout (research R5 naming sweep); every new primitive is shadcn-sourced or built on an already-installed Radix primitive (`ui/collapsible.tsx` new, `ui/dropdown-menu.tsx` and `ui/sheet.tsx` reused) — no ad-hoc component pattern introduced; keyboard operability full (native `<a>`/`<button>`, Radix-provided focus trap/Escape/return on menus and the sheet) | ✅ PASS |
| IV. Performance | No new npm dependency (research R1 — Collapsible ships via the already-direct `radix-ui` umbrella at zero marginal KB); `AppShell`'s own code is kept small since it is shared by every authenticated route — no heavy import (charts, editors) is added to the shared layout; bundle-size check required in review (target: 0% regression, hard ceiling per constitution is 10%) | ✅ PASS |
| V. Youth Psych. Assessment Safeguards | No scoring/consent/interpretation logic touched. The "Ansiedad competitiva" nav entry moves under the coach-only Atletas group with its URL (`/anxiety`) and RBAC (`allowedRoles=[admin, coach]`) unchanged — safeguards intact. **Disclosed trade-off** (research R7): admin loses a *nav* path to `/anxiety` (URL/RBAC unaffected) because the spec's own US1 Acceptance #5 marks the whole Atletas area coach-only-and-admin-absent; recorded explicitly for reviewer sign-off rather than silently decided | ✅ PASS (with disclosed, spec-directed trade-off) |
| Quality Gates — stack discipline | No new runtime dependency (see IV); no new component pattern outside `shadcn/ui` + existing Radix wrappers | ✅ PASS |
| Quality Gates — security | RBAC unchanged everywhere (FR-009); role-filtering is presentation-only, mirrored 1:1 from existing `allowedRoles` on each route — verified by the role-visibility matrix (`data-model.md` §3), not re-derived ad hoc | ✅ PASS |
| Quality Gates — privacy | No athlete-identifiable data in any nav label, config, test fixture, or log — this feature touches only static labels, icons, and routes | ✅ PASS |

## Project Structure

### Documentation (this feature)

```text
specs/030-coach-navigation-redesign/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   ├── navigation-model.md    # Area → routes mapping, role matrix, active-state rule, URL guarantee
│   ├── mobile-navigation.md   # Bottom bar + "Más" sheet contract
│   └── header-actions.md      # User menu + quick-create contract
└── tasks.md              # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
frontend/
├── src/
│   ├── lib/
│   │   ├── navigation.ts                          # NEW — NavArea[]/NavItem config + resolveAreaDefaultTo,
│   │   │                                           #   isAreaActive, getVisibleAreas, getBottomBarAreas,
│   │   │                                           #   getMoreSheetAreas (single source of truth)
│   │   └── __tests__/navigation.test.ts            # NEW — pure-function unit tests
│   ├── components/
│   │   ├── ui/
│   │   │   └── collapsible.tsx                     # NEW — shadcn-style wrapper over radix-ui's Collapsible
│   │   └── layout/
│   │       ├── AppShell.tsx                        # REWRITE — composes the pieces below from lib/navigation.ts;
│   │       │                                        #   removes the 12 duplicated conditional NavLinks
│   │       ├── SidebarNav.tsx                       # NEW — desktop collapsible groups (≥md)
│   │       ├── BottomNav.tsx                        # NEW — mobile/tablet bottom bar (<md)
│   │       ├── MoreSheet.tsx                        # NEW — "Más" sheet content (built on ui/sheet.tsx)
│   │       ├── UserMenu.tsx                         # NEW — header user dropdown (built on ui/dropdown-menu.tsx)
│   │       ├── QuickCreate.tsx                       # NEW — header quick-create dropdown
│   │       ├── SiblingViewTabs.tsx                   # NEW — shared secondary-nav pill (promoted from
│   │       │                                        #   CompetitionDetailPage.tsx:95-172 pattern)
│   │       └── __tests__/
│   │           ├── AppShell.test.tsx                 # REWRITE (assertions enumerated in quickstart.md)
│   │           ├── SidebarNav.test.tsx               # NEW
│   │           ├── BottomNav.test.tsx                # NEW
│   │           ├── MoreSheet.test.tsx                # NEW
│   │           ├── UserMenu.test.tsx                 # NEW
│   │           └── QuickCreate.test.tsx              # NEW
│   ├── routes/
│   │   ├── training/SessionsListPage.tsx             # ADD "Crear con IA" button (FR-007) + SiblingViewTabs
│   │   ├── training/ReportsListPage.tsx              # :390 naming sweep ("Informes del club")
│   │   ├── training/ReportDetailPage.tsx             # :465 naming sweep (back-link only, :472 kept — research R5)
│   │   ├── training/ProjectProfilePage.tsx           # :214 naming sweep + matching test update
│   │   ├── training/AthleteNewslettersDashboardPage.tsx  # :468 naming sweep ("Boletines") + test update
│   │   ├── athletes/AthleteDetailPage.tsx            # :608 tab label naming sweep ("Insights IA")
│   │   ├── GonePage.tsx                              # :15 label naming sweep only (target URL is a 029 concern)
│   │   ├── strength/CatalogPage.tsx                  # ADD "Armar bloque" button (FR-007)
│   │   ├── calendar/CalendarPage.tsx                 # ADD SiblingViewTabs (Calendario | Sesiones | Actividades)
│   │   ├── activities/ActivityReviewPage.tsx         # ADD SiblingViewTabs
│   │   ├── competitions/CompetitionsListPage.tsx     # ADD SiblingViewTabs (Válidas | Sin enlazar | Panorama)
│   │   ├── competitions/UnlinkedCompetitorsPage.tsx  # ADD SiblingViewTabs
│   │   └── competitions/insights/SeasonInsightsPage.tsx  # ADD SiblingViewTabs
│   └── App.tsx                                       # UNCHANGED — no route table edits (FR-009)
├── e2e/
│   └── coach-navigation.spec.ts                      # NEW — breakpoint sweep, role variants, target-size reuse
backend/                                              # UNCHANGED — no server-side work in this feature
```

**Structure Decision**: Frontend-only slice of the existing web-app monorepo. All new/rewritten code lives under `frontend/src/{lib,components/layout,components/ui}`; `App.tsx`'s route table is untouched by design (grouping and labeling only). Depends on 028's shared components/tokens and 029's route-survivor set landing first (program order 028 → 029 → 030); this plan can be authored ahead of that landing since it only references their **contracts** (`specs/028-frontend-design-foundation/contracts/shared-components.md`, `specs/029-coach-surface-subtraction/spec.md`), not their shipped code.

## Complexity Tracking

No constitution violations to justify. No new runtime dependency is introduced — `research.md` R1 confirms the one primitive this feature needs (`Collapsible`) already resolves through the `radix-ui` umbrella package the project depends on today, at zero marginal bundle size. The one cross-cutting risk this design surfaces (Familias' role-dependent default view) is resolved structurally in `data-model.md`/`research.md` R4 rather than carried as a tracked violation, and the one intentional trade-off (admin's nav-reachability of the demoted anxiety entry, research R7) is a disclosed, spec-directed decision, not a constitutional violation.
