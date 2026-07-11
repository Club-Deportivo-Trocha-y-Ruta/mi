# Data Model — 030 Coach Navigation Redesign

No new persisted entities and no schema/migration — this feature is presentation over existing routes and roles (spec Key Entities: "No new domain data"). The one new model is a frontend config module that becomes the **single source of truth** consumed by the sidebar, the bottom bar, and the "Más" sheet.

## 1. `NavItem` / `NavArea` (`frontend/src/lib/navigation.ts`)

```ts
export type NavRole = "coach" | "admin"; // parent nav is unchanged/out of scope for this feature

export interface NavItem {
  id: string;                    // stable key, e.g. "training.calendar"
  label: string;                 // es-CO, exact UI copy (see contracts/navigation-model.md)
  to: string | (() => string);   // static path, or a getter for a dynamic segment (season year)
  roles: NavRole[];               // which roles see this item
}

export interface NavArea {
  id: string;                     // e.g. "training"
  label: string;                  // es-CO
  icon: LucideIcon;
  roles: NavRole[];                // area-level visibility (e.g. Atletas: coach-only)
  matchPrefixes: string[];         // path prefixes counted "inside" this area (active state / auto-expand)
  items: NavItem[];                // ordered; items[0] is the default-resolution fallback
  bottomBarSlot?: Partial<Record<NavRole, boolean>>; // which roles get this area a primary bottom-bar slot
}

export const NAV_AREAS: NavArea[]; // exactly 6: home, training, competitions, athletes, families, library

export function resolveAreaDefaultTo(area: NavArea, role: NavRole): string;
export function isAreaActive(area: NavArea, pathname: string): boolean;      // longest-prefix match
export function getVisibleAreas(role: NavRole): NavArea[];
export function getBottomBarAreas(role: NavRole): NavArea[];  // exactly 4, ordered
export function getMoreSheetAreas(role: NavRole): NavArea[];  // getVisibleAreas(role) minus getBottomBarAreas(role)
```

Pure functions, no data fetching, no side effects — same presentational discipline as the 028 shared-component kit. `NAV_AREAS` and every helper are unit-testable in isolation (`lib/__tests__/navigation.test.ts`) without rendering React.

## 2. The 6 areas

| id | label (es-CO) | roles | default item | other items |
|---|---|---|---|---|
| `home` | Inicio | coach, admin | — (single link, `/dashboard`) | — |
| `training` | Entrenamiento | coach, admin | Calendario → `/calendar` | Sesiones → `/training/sessions`; Actividades → `/activities` |
| `competitions` | Competencias | coach, admin | Válidas → `/competitions` | Sin enlazar → `/competitions/unlinked`; Panorama de temporada → `` /competitions/insights/season/${currentSeason()} `` |
| `athletes` | Atletas | **coach only** | Todos → `/athletes` | Ansiedad competitiva → `/anxiety` |
| `families` | Familias | coach, admin (Padres item coach-only) | Padres → `/parents` (coach); falls back to Boletines for admin | Boletines → `/training/athlete-newsletters`; Informes del club → `/training/reports` |
| `library` | Biblioteca | coach, admin | Técnica y gymkhana → `/technique` | Fuerza → `/strength` |

Full route-by-route membership (all ~39 surviving coach/admin routes) is the routing contract, not the data model — see `contracts/navigation-model.md`.

## 3. Role-visibility matrix

| Area / Item | Coach | Admin |
|---|---|---|
| Inicio | ✅ | ✅ |
| Entrenamiento (Calendario, Sesiones, Actividades) | ✅ | ✅ |
| Competencias (Válidas, Sin enlazar, Panorama de temporada) | ✅ | ✅ |
| **Atletas (whole area, incl. Ansiedad competitiva)** | ✅ | ❌ (research R7) |
| Familias → Padres | ✅ | ❌ |
| Familias → Boletines / Informes del club | ✅ | ✅ |
| Biblioteca (Técnica y gymkhana, Fuerza) | ✅ | ✅ |
| Header → Mi perfil / Cerrar sesión | ✅ | ✅ |
| Header → Salud IA | ❌ | ✅ |
| Quick-create → Nueva sesión / Nueva competencia / Nuevo evento | ✅ | ✅ |
| Quick-create → Nuevo atleta | ✅ | ❌ |
| Bottom-bar 4th slot | Atletas | Biblioteca (research R6) |

This table is the acceptance oracle for FR-004 (role-inaccessible areas/entries absent) and for the parametrized role-based tests in `SidebarNav.test.tsx` / `BottomNav.test.tsx` / `UserMenu.test.tsx` / `QuickCreate.test.tsx`.

## 4. State — none persisted

Expand/collapse is derived from the current route on every render (research R4: `isAreaActive`); a coach's manual expand of a non-active group is transient `useState`, never written to `localStorage` or any backend — keeps the feature strictly presentation-only (FR-009), with no new storage surface and nothing for the data-privacy audit to review.

## 5. Relationship to prerequisite features

- **Consumes from 028** (planned, not yet built): `PageHeader` (every page keeps/gains one), the `ui/dropdown-menu.tsx` and `ui/sheet.tsx` primitives (already built today), `lib/datetime.ts#currentSeason()` (028-R11, not yet present — confirmed by reading the file's current exports), and the `shadow-ring`/status tokens for the bar/menus' chrome.
- **Consumes from 029** (spec-only, not yet planned/built): the surviving-route set this feature's nav must present (season panorama kept; insights hub trio, standalone technique builder, gymkhana composer, interval-template screen removed; technique/strength athlete-progress screens folded into the athlete profile's "Progreso" tab).
- **Produces no new persisted state or backend contract** — everything above is frontend-only configuration and components.
