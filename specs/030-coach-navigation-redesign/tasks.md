# Tasks: Coach Navigation Redesign

**Input**: Design documents from `/specs/030-coach-navigation-redesign/`

**Prerequisites**: `plan.md` (required), `spec.md` (required), `research.md`, `data-model.md`, `contracts/navigation-model.md`, `contracts/mobile-navigation.md`, `contracts/header-actions.md`, `quickstart.md` — plus `specs/028-frontend-design-foundation/contracts/shared-components.md` and `.specify/memory/constitution.md`.

**Tests**: Included and mandatory, not optional. Constitution Principle II (Testing Standards, NON-NEGOTIABLE) requires `vitest` + Testing Library coverage for every new/changed component, hook, and page, plus `jest-axe` zero-violations on every page-level and dialog-level surface. This list embeds test tasks alongside each implementation task rather than as a skippable appendix.

**Organization**: Tasks are grouped by user story (US1–US4, `spec.md` priorities P1/P1/P2/P2) so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no ordering dependency at the time it is listed)
- **[Story]**: Which user story a task belongs to (US1–US4). Setup, Foundational, and Polish tasks carry no story label.
- Every task names its exact file path(s).

## Path Conventions

- This feature is a **frontend-only slice** of the existing `frontend/` + `backend/` monorepo (plan.md Project Type). Every path below is `frontend/src/...` or `frontend/e2e/...`, relative to the repository root.
- `backend/` is untouched — zero backend files, zero migrations.
- `frontend/src/App.tsx`'s route table is untouched by design (FR-009: presentation-only regroup) — no task in this list edits it.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the one new primitive this feature needs before any area config or component consumes it.

- [X] T001 Create `frontend/src/components/ui/collapsible.tsx` — a shadcn-style `Root`/`Trigger`/`Content` wrapper (`forwardRef` + `cn()`, same convention as `frontend/src/components/ui/sheet.tsx`), importing `Collapsible` from the `radix-ui` umbrella package (`frontend/package.json:75`, already a direct dependency) per `research.md` R1. Zero `package.json` changes — do **not** import `@radix-ui/react-collapsible` directly (phantom-dependency risk under pnpm's strict linking, since the repo carries both `package-lock.json` and `pnpm-lock.yaml`). No dedicated unit test required: a thin presentational Radix wrapper with no branching logic is exempt under constitution Principle II, consistent with `sheet.tsx`/`dropdown-menu.tsx` having no test files of their own.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The single-source-of-truth `NavArea[]` configuration that `SidebarNav`, `BottomNav`, and `MoreSheet` all read from.

**⚠️ CRITICAL**: No user story may begin until this phase is complete.

- [X] T002 Define the `NavRole`, `NavItem`, and `NavArea` TypeScript interfaces in `frontend/src/lib/navigation.ts` per `data-model.md` §1 (`NavRole = "coach" | "admin"`; `NavItem { id, label, to, roles }`; `NavArea { id, label, icon, roles, matchPrefixes, items, bottomBarSlot? }`).
- [X] T003 Populate the `NAV_AREAS: NavArea[]` constant in `frontend/src/lib/navigation.ts` — exactly 6 areas (`home`, `training`, `competitions`, `athletes`, `families`, `library`) per `data-model.md` §2 and the full route table in `contracts/navigation-model.md`. Bake in the naming-sweep-corrected labels from the start: "Informes del club" (not "Reportes mensuales") and "Boletines" (not "Boletines Mensuales") for the two `families` items. Include the `competitions` area's "Panorama de temporada" item, whose `to` is `` `/competitions/insights/season/${currentSeason()}` ``; `currentSeason()` is a **028 dependency** (`frontend/src/lib/datetime.ts`, not yet present — confirmed by reading the file's current exports, per `research.md` R9) — if it does not exist when this task runs, inline a local `currentSeason()` (returns the current calendar year) as a temporary shim and swap it for the 028 helper once that feature lands. Depends on T002.
- [X] T004 Implement `resolveAreaDefaultTo(area: NavArea, role: NavRole): string` in `frontend/src/lib/navigation.ts` per `research.md` R4: return the default item's `to` if that item is visible to `role`; otherwise fall back to the `to` of the first `items[]` entry the role can see. This is what sends admin to Boletines (never `/parents`) when opening the Familias area. Depends on T003.
- [X] T005 Implement `isAreaActive(area: NavArea, pathname: string): boolean` in `frontend/src/lib/navigation.ts` — longest-prefix match over `area.matchPrefixes`, per the rule documented in `contracts/navigation-model.md` ("Active-state / auto-expand rule"). Depends on T003.
- [X] T006 Implement `getVisibleAreas(role)`, `getBottomBarAreas(role)` (exactly 4 areas, ordered; admin's 4th slot is `library`, not `athletes`, per `research.md` R6), and `getMoreSheetAreas(role)` (= `getVisibleAreas(role)` minus `getBottomBarAreas(role)`) in `frontend/src/lib/navigation.ts`. Depends on T003.
- [X] T007 Unit tests for `NAV_AREAS` shape and the full role-visibility matrix in `frontend/src/lib/__tests__/navigation.test.ts` (new file): exactly 6 areas; coach sees Atletas + Padres, admin does not — `data-model.md` §3 is the acceptance oracle. Depends on T002, T003.
- [X] T008 Unit tests for `resolveAreaDefaultTo` fallback behavior in `frontend/src/lib/__tests__/navigation.test.ts`: admin on Familias resolves to Boletines (not `/parents`); coach on Familias resolves to Padres; the single-item Inicio area has no fallback branching to test. Matches the required regression named in `quickstart.md`. Depends on T004, T007 (same file — sequential).
- [X] T009 Unit tests for `isAreaActive` longest-prefix matching in `frontend/src/lib/__tests__/navigation.test.ts`, including `/competitions/insights/season/2026` → `"competitions"` (the exact case named in `quickstart.md`). Depends on T005, T008 (same file — sequential).
- [X] T010 Unit tests for `getBottomBarAreas`/`getMoreSheetAreas` role variants in `frontend/src/lib/__tests__/navigation.test.ts`: `getBottomBarAreas("admin")` includes `"library"` and excludes `"athletes"` (the exact case named in `quickstart.md`); `getMoreSheetAreas(role)` never overlaps `getBottomBarAreas(role)` for either role. Depends on T006, T009 (same file — sequential).

**Checkpoint**: `lib/navigation.ts` is the complete, tested single source of truth. Every user story below reads from it.

---

## Phase 3: User Story 1 - A navigation shaped like the coach's work (Priority: P1)

**Goal**: Replace the flat 12-item sidebar with ≤7 collapsible, task-oriented groups; selecting a group's label always lands on its default working view; the active area is visually indicated and expanded; sibling views within an area (Calendario ↔ Sesiones ↔ Actividades) share one consistent secondary-navigation pattern.

**Independent Test**: As coach, starting from login, reach every retained screen using only visible navigation; verify at most 7 top-level areas, that each opens its default view in one interaction, and that the group containing the current screen is visually indicated (spec.md US1).

- [X] T011 [P] [US1] Create `frontend/src/components/layout/SidebarNav.tsx` — desktop (`≥md`) collapsible groups built on `frontend/src/components/ui/collapsible.tsx` (T001); reads `NAV_AREAS`/`getVisibleAreas`/`isAreaActive`/`resolveAreaDefaultTo` from `frontend/src/lib/navigation.ts` (T002–T006). Each multi-item area renders `Collapsible.Root open={isAreaActive(area, pathname) || manuallyOpened[area.id]}` with two independent ≥44×44px controls: the area **label** is a `NavLink to={resolveAreaDefaultTo(area, role)}` (navigates), and a separate chevron button (`aria-expanded`, `aria-controls`) toggles disclosure only. The single-item Inicio area renders as a plain `NavLink` with no disclosure chrome. Per `research.md` R1.
- [X] T012 [P] [US1] Create `frontend/src/components/layout/SiblingViewTabs.tsx` — the shared secondary-navigation pill row, promoting the existing pattern at `frontend/src/routes/competitions/CompetitionDetailPage.tsx:95-172` (`TAB_VALUES`/`TAB_LABELS`/`TabTrigger`, built on `@radix-ui/react-tabs`) into a reusable `{ items: { label: string; to: string }[] }`-driven component. Renders as its own full-width row directly under the page `<h1>` — **never** inside `PageHeader`'s `actions` slot (right-aligned/button-shaped per `specs/028-frontend-design-foundation/contracts/shared-components.md`; mixing the two breaks reflow under ~380px). Per `research.md` R4.
- [X] T013 [US1] Rewrite `frontend/src/components/layout/AppShell.tsx` to compose `<SidebarNav>` from `NAV_AREAS` for `role === "coach" | "admin"` only: replace the 12 duplicated `{(isCoach || isAdmin) && <NavLink>...}` blocks (today's lines 39-146 and 183-191, inside the `navLinks` const spanning 37-193) with `<SidebarNav>`. **Preserve the parent-role experience exactly as it is today**: the `isParent` blocks (today's lines 147-182), the mobile hamburger button (`249-270`) + drawer `<aside>` (`216-235`) + overlay (`207-213`), and the header's "Mi perfil"/"Cerrar sesión" buttons (`279-293`) all remain unchanged for `role === "parent"` — `data-model.md`'s `NavRole` type is coach/admin-only by design, and parent nav is explicitly out of scope (`spec.md` Assumptions). Preserve the skip-link (`199-204`), `ServerWakingBanner`, and the `warmUp()` effect verbatim. Depends on T011, T002–T006.
- [X] T014 [US1] Rewrite `frontend/src/components/layout/__tests__/AppShell.test.tsx` for the new coach/admin sidebar: assert coach sees "Atletas" and "Padres" **nested** under their groups (not bare top-level links); assert "Boletines" (not "Boletines Mensuales") and "Informes del club" (not "Reportes mensuales"); assert admin's whole Atletas group is absent; assert the group containing the current route is expanded and visually indicated on a deep-linked render (e.g. `/anxiety`). **Remove** the now-obsolete expectation `it("NO debería quedar ningún enlace a /competitions/insights en el sidebar", ...)` (today's lines 133-141) — a legitimate "Panorama de temporada" item now lives at a path starting with that prefix, so the old blanket assertion is no longer accurate; replace it with a precise assertion that the exact hub URL `/competitions/insights` (no further path segments) is absent. Keep the existing parent-role and legacy-redirect (`/coach/race-analysis`) assertions unchanged. Depends on T013.
- [X] T015 [P] [US1] Create `frontend/src/components/layout/__tests__/SidebarNav.test.tsx` — role-filtered rendering (coach vs. admin, per `data-model.md` §3), active-area auto-expand on a deep link, the label-vs-chevron split (label navigates; chevron only toggles `aria-expanded`), and manual expand/collapse of a non-active group. Depends on T011.
- [X] T016 [P] [US1] Create `frontend/src/components/layout/__tests__/SiblingViewTabs.test.tsx` — active pill reflects the current route, keyboard operability inherited from `@radix-ui/react-tabs`, renders as a full-width row rather than inside an actions slot. Depends on T012.
- [X] T017 [US1] Add `jest-axe` zero-violations assertions for the default shell and an expanded sidebar group to `frontend/src/components/layout/__tests__/AppShell.test.tsx`, per `quickstart.md`'s automated-validation checklist. Depends on T014.
- [X] T018 [P] [US1] Add `<SiblingViewTabs>` (Calendario | Sesiones | Actividades) to `frontend/src/routes/calendar/CalendarPage.tsx`; update `frontend/src/routes/calendar/CalendarPage.test.tsx` to assert the pill row renders and the active pill matches the route (FR-003). Depends on T012.
- [X] T019 [P] [US1] Add `<SiblingViewTabs>` (Calendario | Sesiones | Actividades) to `frontend/src/routes/training/SessionsListPage.tsx`; update `frontend/src/routes/training/SessionsListPage.test.tsx` to assert the pill row renders. This task adds only the sibling-view pills — the "Crear con IA" button is added separately by T021 (US2) on this same file; sequence T021 after this task. Depends on T012.
- [X] T020 [P] [US1] Add `<SiblingViewTabs>` (Calendario | Sesiones | Actividades) to `frontend/src/routes/activities/ActivityReviewPage.tsx`; update `frontend/src/routes/activities/ActivityReviewPage.test.tsx` to assert the pill row renders. Depends on T012.

**Checkpoint**: Coach/admin now have a fully grouped, ≤7-area desktop sidebar with the Entrenamiento sibling-view pattern in place. `spec.md` US1 Acceptance Scenarios 1–5 are independently verifiable.

---

## Phase 4: User Story 2 - Previously hidden tools become visible (Priority: P1) 🎯 MVP

**Goal**: Surface the three fully-built-but-invisible tools through normal navigation: the AI session assistant next to manual session creation, the season panorama inside Competencias, and strength-block building from the strength library.

**Independent Test**: Without typing any URL, reach the AI session assistant from the sessions area, the season panorama from Competencias, and strength-block creation from Biblioteca → Fuerza (spec.md US2).

- [X] T021 [P] [US2] Add a "Crear con IA" button next to the existing "+ Nueva sesión" action, linking to `/training/sessions/assistant`, in `frontend/src/routes/training/SessionsListPage.tsx`; update `frontend/src/routes/training/SessionsListPage.test.tsx` to assert it renders (FR-007, US2 Acceptance #1). Same file as T019 (US1) — sequence after it; the two changes are otherwise unrelated.
- [X] T022 [P] [US2] Add an "Armar bloque" button linking to `/strength/blocks/new` to `frontend/src/routes/strength/CatalogPage.tsx`; create `frontend/src/routes/strength/__tests__/CatalogPage.test.tsx` (this page has no existing test file — follow the `__tests__/` convention already used by `strength/__tests__/AthleteProgressPage.test.tsx`) asserting the button renders and links correctly (FR-007, US2 Acceptance #3).
- [X] T023 [P] [US2] Add `<SiblingViewTabs>` (Válidas | Sin enlazar | Panorama de temporada) to `frontend/src/routes/competitions/CompetitionsListPage.tsx`; update `frontend/src/routes/competitions/__tests__/CompetitionsListPage.test.tsx` to assert all 3 pills render and the Panorama pill navigates to `` /competitions/insights/season/${currentSeason()} `` (FR-007, US2 Acceptance #2). Reuses `SiblingViewTabs.tsx` from T012 (US1) — if US2 must ship before US1 lands, inline a minimal local tab row here instead and refactor onto `SiblingViewTabs` once T012 exists.
- [X] T024 [P] [US2] Add `<SiblingViewTabs>` (Válidas | Sin enlazar | Panorama de temporada) to `frontend/src/routes/competitions/UnlinkedCompetitorsPage.tsx`; update `frontend/src/routes/competitions/__tests__/UnlinkedCompetitorsPage.test.tsx` to assert all 3 pills render. Same `SiblingViewTabs.tsx` reuse caveat as T023.
- [X] T025 [P] [US2] Add `<SiblingViewTabs>` (Válidas | Sin enlazar | Panorama de temporada) to `frontend/src/routes/competitions/insights/SeasonInsightsPage.tsx`; update `frontend/src/routes/competitions/insights/__tests__/SeasonInsightsPage.test.tsx` to assert all 3 pills render and the active pill is "Panorama de temporada" — this is the destination page itself gaining the shared wayfinding pattern, completing its promotion from hidden to nav-level-visible (`research.md` R9). Same `SiblingViewTabs.tsx` reuse caveat as T023.

**Checkpoint** 🎯 **MVP complete**: Setup + Foundational + US1 + US2 together deliver the regrouped desktop sidebar *and* all three previously-hidden tools now reachable through normal navigation. `spec.md` US1 and US2 Independent Tests both pass; this is a demo/deploy-ready increment on its own.

---

## Phase 5: User Story 3 - Thumb-first navigation on phone and tablet (Priority: P2)

**Goal**: A persistent bottom bar with the four most-used areas (Inicio, Entrenamiento, Competencias, Atletas — Biblioteca for admin) plus a "Más" overflow for everything else, on phone/tablet widths.

**Independent Test**: On a phone/tablet viewport, verify the bottom bar shows the four areas plus "Más"; every remaining destination is reachable through the overflow; the bar never overlaps content or the on-screen keyboard (spec.md US3).

- [X] T026 [P] [US3] Create `frontend/src/components/layout/BottomNav.tsx` — `<nav aria-label="Navegación principal" class="fixed inset-x-0 bottom-0 z-40 md:hidden">`, 5 slots (each a `NavLink`/button ≥48×48px): `getBottomBarAreas(role)` (4 areas) plus a 5th "Más" trigger button (`aria-haspopup="dialog"`, `aria-expanded`). Active slot via `NavLink`'s built-in `aria-current="page"`. Safe-area padding `env(safe-area-inset-bottom)` on the bar. Per `contracts/mobile-navigation.md`. Rendered only for `role === "coach" | "admin"` — parent keeps its existing mobile drawer (see T013's scope note).
- [X] T027 [P] [US3] Create `frontend/src/components/layout/MoreSheet.tsx` — built on the existing `frontend/src/components/ui/sheet.tsx` (`side="bottom"`); lists `getMoreSheetAreas(role)` (coach: Familias, Biblioteca; admin: Familias only — Atletas is entirely absent per `research.md` R7), then a separator, "Mi perfil" (`/perfil`, all roles), "Salud IA" (`/admin/ai`, admin-only), "Cerrar sesión" (all roles). Every row ≥48×48px. Per `contracts/mobile-navigation.md`.
- [X] T028 [US3] Integrate `<BottomNav>` and `<MoreSheet>` into `frontend/src/components/layout/AppShell.tsx` for `role === "coach" | "admin"`: render below the `md` breakpoint, hide `<SidebarNav>` below `md` (and vice versa at `≥md` — no dead zone at any width). Remove the mobile hamburger button and drawer overlay **for coach/admin only** (the bottom bar replaces the drawer it used to open, per `contracts/header-actions.md`) — **the parent-role hamburger/drawer preserved in T013 remains untouched**. Add matching bottom padding to `<main>` below `md` so content/focused inputs are never trapped under the fixed bar. Depends on T013, T026, T027.
- [X] T029 [US3] Update `frontend/src/components/layout/__tests__/AppShell.test.tsx`: render `<BottomNav>`/`<MoreSheet>` at a mobile viewport; assert coach's 4 bottom-bar slots (Inicio, Entrenamiento, Competencias, Atletas) plus "Más"; assert admin's 4th slot is Biblioteca (not Atletas, per `research.md` R6); assert "Más" lists the remaining role-visible areas plus Mi perfil, Cerrar sesión, and (admin) Salud IA. Depends on T028, T017 (same file — sequential).
- [X] T030 [US3] Add `jest-axe` zero-violations assertions for the open "Más" sheet state to `frontend/src/components/layout/__tests__/AppShell.test.tsx`, per `quickstart.md`. Depends on T029.
- [X] T031 [P] [US3] Create `frontend/src/components/layout/__tests__/BottomNav.test.tsx` — role variants (coach vs. admin 4th slot), `aria-current` on the active slot, ≥48×48px target sizing, the "Más" trigger's `aria-haspopup`/`aria-expanded`. Depends on T026.
- [X] T032 [P] [US3] Create `frontend/src/components/layout/__tests__/MoreSheet.test.tsx` — role-filtered content list (coach: Familias + Biblioteca; admin: Familias only, Atletas entirely absent per `research.md` R7), focus trap/Escape/focus-return inherited from `ui/sheet.tsx`, ≥48×48px rows. Depends on T027.
- [X] T033 [US3] Create `frontend/e2e/coach-navigation.spec.ts` (Chromium is preinstalled — do **not** run `playwright install`): viewport ≥768px shows the sidebar and hides the bottom bar; viewport <768px shows the bottom bar (4 areas + Más) and hides the sidebar, with no width where neither renders; admin login shows Biblioteca (not Atletas) in the bottom bar's 4th slot; every bottom-bar/Más-sheet control measures ≥48×48px (reuse the 028 target-size Playwright helper — `specs/028-frontend-design-foundation/research.md` R7). Depends on T028.

**Checkpoint**: Coach/admin have thumb-reachable mobile navigation (bottom bar + "Más") in addition to the desktop sidebar. `spec.md` US3's Independent Test passes without US4.

---

## Phase 6: User Story 4 - Account actions and quick creation from anywhere (Priority: P2)

**Goal**: Profile, sign-out, and admin diagnostics move into a user menu; a global quick-create control starts a new session/competition/calendar event/athlete from any screen; naming is unified to one term per concept across nav, titles, and actions.

**Independent Test**: From several unrelated screens, create each of the four record types via quick-create (role-permitting); open the user menu and reach profile, sign-out, and (as admin) diagnostics (spec.md US4).

- [X] T034 [P] [US4] Create `frontend/src/components/layout/UserMenu.tsx` — built on the existing `frontend/src/components/ui/dropdown-menu.tsx`. Trigger = the user's full name + chevron (`aria-haspopup="menu"`), replacing the two standalone header buttons. Items: "Mi perfil" (`/perfil`, all roles) → separator (admin only) → "Salud IA" (`/admin/ai`, admin-only — relocated out of the sidebar) → separator → "Cerrar sesión" (calls `logout()` from `useAuthStore`, all roles). Per `contracts/header-actions.md`.
- [X] T035 [P] [US4] Create `frontend/src/components/layout/QuickCreate.tsx` — built on `frontend/src/components/ui/dropdown-menu.tsx`. Trigger = `Plus` (lucide-react) icon button, `aria-label="Crear"`. Role-filtered items: "Nueva sesión" (`/training/sessions/new`, coach+admin), "Nueva competencia" (`/competitions/new`, coach+admin), "Nuevo evento" (`/calendar/events/new`, coach+admin), "Nuevo atleta" (`/athletes/new`, coach-only). No `?prefill` params on any target. Per `contracts/header-actions.md`.
- [X] T036 [US4] Integrate `<UserMenu>` and `<QuickCreate>` into `frontend/src/components/layout/AppShell.tsx`'s header action cluster (today's `flex items-center gap-2` div at line 277) for `role === "coach" | "admin"`, replacing the two loose "Mi perfil"/"Cerrar sesión" elements — the admin-only "Salud IA" sidebar entry was already removed by T013, and is now reachable only via `<UserMenu>`. **Parent's header buttons remain untouched** (same scope note as T013/T028). Depends on T013, T028, T034, T035.
- [X] T037 [US4] Update `frontend/src/components/layout/__tests__/AppShell.test.tsx`: assert the user-menu trigger renders the user's name and opens to reveal "Mi perfil"/"Cerrar sesión" (plus "Salud IA" for admin only); assert the quick-create trigger opens to reveal the role-filtered items, with "Nuevo atleta" absent for admin; assert "Salud IA" is **not** a sidebar or bottom-bar link but **is** reachable inside the opened user menu. Depends on T036, T030 (same file — sequential).
- [X] T038 [US4] Add `jest-axe` zero-violations assertions for the open user-menu and open quick-create-menu states to `frontend/src/components/layout/__tests__/AppShell.test.tsx`, per `quickstart.md` — this completes the full 5-state axe sweep (default shell, expanded sidebar group, open Más sheet, open user menu, open quick-create menu). Depends on T037.
- [X] T039 [P] [US4] Create `frontend/src/components/layout/__tests__/UserMenu.test.tsx` — item visibility per role (Salud IA admin-only), `logout()` invoked on "Cerrar sesión", Radix roving-tabindex/Escape/focus-return. Depends on T034.
- [X] T040 [P] [US4] Create `frontend/src/components/layout/__tests__/QuickCreate.test.tsx` — role-filtered items (Nuevo atleta coach-only), each item links to its documented route with no `?prefill` params, ≥48×48px trigger. Depends on T035.
- [X] T041 [US4] Extend `frontend/e2e/coach-navigation.spec.ts` (created in T033): user-menu and quick-create triggers/items measure ≥48×48px and are keyboard-operable (Tab/Enter/Escape); "Nuevo atleta" is absent for admin at the E2E level. Depends on T033, T036.

### Naming sweep (FR-008 — one term per concept; `research.md` R5, all 8 documented sites)

- [X] T042 [US4] Confirm the naming-sweep sites inside `frontend/src/components/layout/AppShell.tsx` (`research.md` R5 rows 1–2, formerly lines :90 "Reportes mensuales" and :99 "Boletines Mensuales"): both are already resolved structurally — `NAV_AREAS`'s corrected labels (T003) flow through `<SidebarNav>` (T011/T013). Add or confirm explicit "Informes del club" and "Boletines" assertions in `frontend/src/components/layout/__tests__/AppShell.test.tsx` if T014 did not already cover them; no further source edit is needed. Depends on T038 (same file — sequential).
- [X] T043 [P] [US4] Naming sweep: rename the `<h1>` "Reportes Mensuales" → "Informes del club" in `frontend/src/routes/training/ReportsListPage.tsx:390` (no existing test asserts this string — none to update).
- [X] T044 [P] [US4] Naming sweep: rename the back-link "← Informes mensuales" → "← Informes del club" in `frontend/src/routes/training/ReportDetailPage.tsx:465`. Leave `ReportDetailPage.tsx:472` ("Informe Técnico — {month} {year}") and its passing assertion at `frontend/src/routes/training/ReportDetailPage.test.tsx:201` untouched — it names the generated document instance, not the nav category (`research.md` R5).
- [X] T045 [P] [US4] Naming sweep: rename the back-link "← Informes mensuales" → "← Informes del club" in `frontend/src/routes/training/ProjectProfilePage.tsx:214`; update the matching assertion in `frontend/src/routes/training/ProjectProfilePage.test.tsx:281`.
- [X] T046 [P] [US4] Naming sweep: rename the `<h1>` "Boletines Mensuales" → "Boletines" in `frontend/src/routes/training/AthleteNewslettersDashboardPage.tsx:468`; update the matching assertion in `frontend/src/routes/training/AthleteNewslettersDashboardPage.test.tsx:132`.
- [X] T047 [P] [US4] Naming sweep: rename the tab label "Análisis IA" → "Insights IA" in `frontend/src/routes/athletes/AthleteDetailPage.tsx:608` (no existing assertion in `AthleteDetailPage.test.tsx` or `AthleteDetailPage.strava.test.tsx` targets this string — none to update).
- [X] T048 [P] [US4] Naming sweep: rename the default `toLabel` prop "Ir a Análisis IA" → "Ir a Insights IA" in `frontend/src/routes/GonePage.tsx:15`. Leave the default `to="/competitions/insights"` at `GonePage.tsx:14` untouched — it points at the hub route 029 deletes, a 029/Wave-F concern, not this feature's (`research.md` R5).

**Checkpoint**: All four user stories are independently functional; naming is unified per SC-006.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Whole-feature validation that spans every story.

- [X] T049 Run the full automated-validation sweep from `specs/030-coach-navigation-redesign/quickstart.md`: `cd frontend && npm run typecheck && npm test` green, including every new/updated test from T007–T048.
- [X] T050 [P] Naming-sweep grep verification (SC-006) across `frontend/src/components/layout/`, `frontend/src/routes/training/`, `frontend/src/routes/athletes/AthleteDetailPage.tsx`, and `frontend/src/routes/GonePage.tsx`: confirm zero remaining hits of "Reportes Mensuales", "Boletines Mensuales", and coach-nav "Análisis IA" outside the deliberately-excluded sites (`ReportDetailPage.tsx:472`, `CompetitionDetailPage.tsx`'s "Ver análisis" CTA, `GonePage.tsx:14`'s `to`), per `research.md` R5 and `quickstart.md` scenario 5.
- [X] T051 [P] Manual SC-007 bookmark/no-URL-change verification per `specs/030-coach-navigation-redesign/quickstart.md` scenario 6: open pre-redesign URLs directly (a competition detail, an athlete detail, `/training/reports/2026/6`, `/anxiety`) and confirm each resolves to the same screen as before, with its containing nav area correctly expanded/highlighted.
- [X] T052 [P] Manual SC-008 discoverability check per `specs/030-coach-navigation-redesign/quickstart.md` scenario 7: hand the running app to a first-time observer (e.g., the admin account) and time locating "Panorama de temporada" and "Armar bloque de fuerza" via navigation only — target under 30 seconds each.
- [X] T053 [P] Manual FR-010 keyboard/assistive-technology sweep per `specs/030-coach-navigation-redesign/quickstart.md` scenario 9: Tab from the skip-link through the sidebar groups, header quick-create, user menu, and (at a narrow viewport) the bottom bar and "Más" sheet; confirm every control is reachable and operable with Enter/Space, Escape closes menus/sheet with focus returned to the trigger, and "Saltar a contenido" still lands on `#main-content`.
- [X] T054 [P] Bundle-size regression check for `frontend/src/components/layout/AppShell.tsx` and its new sibling components against constitution Principle IV's budget (target 0% regression, hard ceiling 10%, per `specs/030-coach-navigation-redesign/plan.md` Constitution Check row IV) — compare gzipped chunk size before/after via the frontend production build.
- [X] T055 [P] Execute the two remaining `quickstart.md` edge-case checks: role switch mid-session (sign out and back in as a different role; confirm no stale nav entries) and narrow desktop windows (resize continuously through the `md` breakpoint; confirm no width renders neither the sidebar nor the bottom bar) — record results per `specs/030-coach-navigation-redesign/quickstart.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. **BLOCKS every user story** — nothing in US1–US4 may start before T002–T010 land.
- **User Stories (Phase 3–6)**: All depend on Foundational; see the precise per-story dependencies below (they are not all mutually independent at the file level, unlike a from-scratch backend feature).
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### User Story Dependencies (precise, per file — this feature shares more infrastructure across stories than a typical backend slice)

- **US1 → Foundational only.** No dependency on US2/US3/US4.
- **US2 → Foundational only**, with one disclosed reuse: T023/T024/T025 consume `SiblingViewTabs.tsx` from US1's T012. If US2 must ship before US1, inline a minimal local tabs row in those three tasks and refactor onto `SiblingViewTabs` once T012 lands (noted inline on each task).
- **US3 → Foundational + US1's T013** (AppShell rewrite), because T028 edits the same `AppShell.tsx` file T013 produced. `BottomNav.tsx`/`MoreSheet.tsx` (T026–T027) and their unit tests (T031–T032) have no such dependency and can be built the moment Foundational lands.
- **US4 → Foundational + US1's T013**, same reasoning as US3, same file. `UserMenu.tsx`/`QuickCreate.tsx` (T034–T035) and their unit tests (T039–T040) can be built the moment Foundational lands.
- **US3 ↔ US4 share `AppShell.tsx` and `AppShell.test.tsx`.** If both are staffed concurrently, land US3's T028–T030 and US4's T036–T038 as one coordinated sequence on that file (either internal order works, but they are not truly parallel) rather than as two branches that will conflict on merge.
- **Cross-feature (029 — coach-surface-subtraction)**: this feature is recommended to run after `specs/029-coach-surface-subtraction` lands, so the nav only presents surviving screens — but no task here hard-depends on 029's files being deleted. `NAV_AREAS` (T003) simply omits the routes 029 removes; if 029 has not landed yet when T003 runs, the config still omits them (they were never added to `NAV_AREAS` in the first place), so no rework is required either way.
- **Cross-feature (028 — frontend-design-foundation)**: `currentSeason()` (`frontend/src/lib/datetime.ts`) is a 028 deliverable referenced by T003; the inline shim documented on T003 keeps Foundational unblocked if 028 hasn't landed yet. `PageHeader` (028) is consumed by pages this feature touches but is not itself built or modified by any task here.

### Disclosed trade-off: temporary "Salud IA" reachability gap

T013 (US1) removes the sidebar's admin-only "Salud IA" `NavLink` (it is not part of `NAV_AREAS` — it belongs only to `UserMenu`, built in US4's T034/T036). Between US1 landing and US4 landing, admin has **no nav path at all** to `/admin/ai` (the route itself is unaffected — this is a nav-visibility gap only, mirroring the disclosed trade-off `research.md` R7 records for the Atletas/anxiety demotion). This is acceptable for incremental development and matches the recommended Implementation Strategy below (US4 ships shortly after US1 in the same delivery), but do not leave a production deploy sitting on US1-without-US4 for an extended period without a mitigation.

### Within-File Sequencing

- `frontend/src/lib/navigation.ts` (T002 → T003 → T004/T005/T006, in that order — types before data before functions) and `frontend/src/lib/__tests__/navigation.test.ts` (T007 → T008 → T009 → T010) are each edited sequentially despite spanning multiple tasks; none of T002–T010 are marked `[P]`.
- `frontend/src/components/layout/AppShell.tsx` and its test file are each touched across three phases — T013/T014/T017 (US1), T028/T029/T030 (US3), T036/T037/T038/T042 (US4) — always sequential within the file, in task-ID order.
- `frontend/src/routes/training/SessionsListPage.tsx` (+ its test) is touched by both T019 (US1) and T021 (US2) — sequential, either order.

### Parallel Opportunities

- Within Foundational: none marked `[P]` (only two files, each edited sequentially) — but the T002–T006 (config/logic) and T007–T010 (tests) groups can be split across two people once the interface is agreed.
- Within US1: T011/T012 (two independent new components) are mutually parallel; then T015/T016/T018/T019/T020 (five independent files) are mutually parallel.
- Within US2: all five tasks (T021–T025) touch five different files and are mutually parallel (mind the T019/T021 same-file note above).
- Within US3: T026/T027 (components) and T031/T032 (their tests) are mutually parallel; T028–T030/T033 are sequential (shared/dependent files).
- Within US4: T034/T035 (components), T039/T040 (their tests), and T043–T048 (six independent naming-sweep files) are all mutually parallel; T036–T038/T042 are sequential (shared `AppShell` files).
- Within Polish: T050–T055 are mutually parallel manual/verification checks; T049 is the automated gate that should run first.

---

## Parallel Example: Foundational → User Story 1

```bash
# Once T002-T006 (lib/navigation.ts) are complete, these five US1 tasks touch five different files:
Task: "T011 [US1] Create SidebarNav.tsx in frontend/src/components/layout/SidebarNav.tsx"
Task: "T012 [US1] Create SiblingViewTabs.tsx in frontend/src/components/layout/SiblingViewTabs.tsx"
Task: "T018 [US1] Add SiblingViewTabs to frontend/src/routes/calendar/CalendarPage.tsx"
Task: "T019 [US1] Add SiblingViewTabs to frontend/src/routes/training/SessionsListPage.tsx"
Task: "T020 [US1] Add SiblingViewTabs to frontend/src/routes/activities/ActivityReviewPage.tsx"
```

## Parallel Example: User Story 2 (surfacing hidden tools)

```bash
Task: "T021 [US2] Add 'Crear con IA' button in frontend/src/routes/training/SessionsListPage.tsx"
Task: "T022 [US2] Add 'Armar bloque' button in frontend/src/routes/strength/CatalogPage.tsx"
Task: "T023 [US2] Add SiblingViewTabs to frontend/src/routes/competitions/CompetitionsListPage.tsx"
Task: "T024 [US2] Add SiblingViewTabs to frontend/src/routes/competitions/UnlinkedCompetitorsPage.tsx"
Task: "T025 [US2] Add SiblingViewTabs to frontend/src/routes/competitions/insights/SeasonInsightsPage.tsx"
```

## Parallel Example: User Story 4 naming sweep

```bash
Task: "T043 [US4] Rename 'Reportes Mensuales' in frontend/src/routes/training/ReportsListPage.tsx:390"
Task: "T044 [US4] Rename back-link in frontend/src/routes/training/ReportDetailPage.tsx:465"
Task: "T045 [US4] Rename back-link in frontend/src/routes/training/ProjectProfilePage.tsx:214"
Task: "T046 [US4] Rename 'Boletines Mensuales' in frontend/src/routes/training/AthleteNewslettersDashboardPage.tsx:468"
Task: "T047 [US4] Rename 'Análisis IA' tab in frontend/src/routes/athletes/AthleteDetailPage.tsx:608"
Task: "T048 [US4] Rename toLabel in frontend/src/routes/GonePage.tsx:15"
```

---

## Implementation Strategy

### MVP First (Setup + Foundational + US1 + US2)

1. Complete Phase 1: Setup (T001).
2. Complete Phase 2: Foundational (T002–T010) — CRITICAL, blocks everything.
3. Complete Phase 3: US1 (T011–T020) — grouped desktop sidebar + Entrenamiento sibling tabs.
4. Complete Phase 4: US2 (T021–T025) — surface the three hidden tools.
5. **STOP and VALIDATE**: run `quickstart.md`'s automated checks plus the Independent Tests for US1 and US2. This is the MVP — desktop-only, but every screen is reachable within ≤7 grouped areas and the three previously-orphaned features are now visible.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. + US1 → grouped sidebar; test/demo on desktop.
3. + US2 → hidden tools surfaced; **MVP complete** — deploy/demo if ready.
4. + US3 → thumb-first mobile bottom bar; test/demo on phone/tablet widths.
5. + US4 → user menu, quick-create, naming unified; full feature complete.
6. Polish → cross-cutting validation (bookmarks, findability, keyboard, bundle size).

### Parallel Team Strategy

With multiple developers, after Foundational lands:

1. Developer A: US1 (sidebar + Entrenamiento tabs) — T011–T020.
2. Developer B: US2 (surfacing) — T021–T025, coordinating with Developer A on `SessionsListPage.tsx` (T019/T021) and on reusing `SiblingViewTabs.tsx` once T012 lands.
3. Once US1's T013 (AppShell rewrite) lands: Developer C picks up US3 (T026–T033), Developer D picks up US4 (T034–T048) — both coordinate on the shared `AppShell.tsx`/`AppShell.test.tsx` sequence rather than editing it on independent branches.

---

## Notes

- `[P]` tasks touch different files with no ordering dependency at the time they are listed.
- `[Story]` labels map each task to `spec.md`'s US1–US4 for traceability; Setup, Foundational, and Polish carry none.
- `AppShell.tsx`/`AppShell.test.tsx` are the one deliberately shared file pair across US1/US3/US4 — always sequence tasks touching them in task-ID order, even across a story boundary.
- Naming-sweep tasks (T042–T048) are self-contained one-file renames (T042 excepted, which only adds/confirms test assertions); run them in any order relative to each other.
- Verify new/updated tests actually exercise the new behavior (and fail on the pre-change code where practical) before considering a task done.
- Stop at any checkpoint to validate a story independently per its own Independent Test in `spec.md`.
- No task in this list edits `backend/`, `frontend/src/App.tsx`'s route table, `.specify/`, or `CLAUDE.md`.
