# Contract — Header Actions (user menu + quick-create)

Implements spec User Story 4 (FR-006). Backing decision: `../research.md` R3. Both built on the existing `ui/dropdown-menu.tsx` (`@radix-ui/react-dropdown-menu`).

## User menu

**Trigger**: replaces the two standalone header buttons at `AppShell.tsx:279-293` ("Mi perfil", "Cerrar sesión"). New trigger: user's full name (already rendered today, `AppShell.tsx:271-273`) + chevron, `aria-haspopup="menu"`.

| Item | Destination | Roles | Notes |
|---|---|---|---|
| Mi perfil | `/perfil` | all authenticated roles | Unchanged destination |
| — separator — | — | admin only | Visually scopes the diagnostic item below |
| Salud IA | `/admin/ai` | admin only | Moved out of main nav (today `AppShell.tsx:183-191`); no longer visually equal to daily-use areas |
| — separator — | — | all roles | |
| Cerrar sesión | calls `logout()` (`useAuthStore`) | all authenticated roles | Same handler as today (`AppShell.tsx:286-293`); no confirmation dialog — sign-out is non-destructive to data, matching current behavior |

Menu items use `min-h-11` (44px) per the existing `DropdownMenuItem` styling (`ui/dropdown-menu.tsx:57`) — already ≥ the 48px rule once padding is included; verified by the target-size Playwright sweep (028-R7), not re-derived here.

## Quick-create

**Trigger**: new header icon button, `Plus` (lucide-react), `aria-label="Crear"`, placed in the header's action cluster alongside the user-menu trigger. Visible on every authenticated coach/admin screen (rendered once in `AppShell`, not per-page).

| Item | Destination | Roles | `?prefill` params |
|---|---|---|---|
| Nueva sesión | `/training/sessions/new` | coach, admin | none — opens the existing blank create form |
| Nueva competencia | `/competitions/new` | coach, admin | none |
| Nuevo evento | `/calendar/events/new` | coach, admin | none (the `?date=` prefill from 028-R11 is a *different* entry point — the calendar day-click — and is contextual to a clicked day; quick-create has no such context) |
| Nuevo atleta | `/athletes/new` | coach only | none |

No target requires a prefill parameter today; the column is documented for completeness and left reserved for a future contextual launch (e.g., quick-create invoked from within an athlete's profile could one day prefill `athlete_id`) — out of scope for this feature.

## Layout

Both triggers render in the header's existing right-hand cluster (`AppShell.tsx:277` `<div className="flex items-center gap-2">`), replacing the two loose `Link`/`button` elements there today. On mobile (`< md`), the header persists above the bottom bar unchanged in position — only the loose buttons collapse into the two new triggers, and the hamburger button (`AppShell.tsx:249-270`) is removed since the bottom bar replaces the drawer it used to open.

## Acceptance mapping

| Spec acceptance (US4) | Satisfied by |
|---|---|
| Quick-create starts a new session/competition/event/athlete from any screen, role-filtered | Table above; rendered once in `AppShell` |
| User menu offers profile + sign-out (all) and diagnostics (admin); none occupy main nav | Table above; removal of `AppShell.tsx:183-191` and `:279-293` from the nav list |
