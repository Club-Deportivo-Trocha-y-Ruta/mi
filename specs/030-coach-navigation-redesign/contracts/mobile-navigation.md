# Contract — Mobile Navigation (bottom bar + "Más" sheet)

Implements spec User Story 3 (FR-005). Backing decisions: `../research.md` R2, R6.

## Breakpoint

Bottom bar and sidebar are mutually exclusive by the `md` breakpoint (768px, Tailwind default — the same token `AppShell.tsx` already uses for `md:static`/`md:hidden`):

- `< md` (phone/tablet portrait and most tablet landscape): bottom bar visible, sidebar hidden.
- `≥ md`: sidebar visible (`SidebarNav`), bottom bar hidden. No dead zone — exactly one of the two renders at any width (no third "neither" state), satisfying the spec's "narrow desktop windows" edge case.

## Bottom bar structure

```html
<nav aria-label="Navegación principal" class="fixed inset-x-0 bottom-0 z-40 md:hidden ...">
  <!-- 5 slots, each ≥48×48px -->
  <NavLink to={area1.defaultTo}> icon + label </NavLink>   <!-- aria-current="page" when active -->
  <NavLink to={area2.defaultTo}> icon + label </NavLink>
  <NavLink to={area3.defaultTo}> icon + label </NavLink>
  <NavLink to={area4.defaultTo}> icon + label </NavLink>
  <button aria-haspopup="dialog" aria-expanded={open}> icon + "Más" </button>
</nav>
```

- **Coach slots (order fixed)**: Inicio, Entrenamiento, Competencias, Atletas, Más.
- **Admin slots**: Inicio, Entrenamiento, Competencias, **Biblioteca**, Más (research R6 — Familias is not promoted because its role-appropriate default differs by role and would need the same fallback logic the sidebar already carries; simpler to keep the always-role-uniform Biblioteca in the fixed 4th slot).
- Active slot uses the same `resolveAreaDefaultTo`/`isAreaActive` logic as the sidebar (`../data-model.md` — single source of truth; no separate mobile config).
- Target size: every slot ≥48×48px (constitution III / FR-005); safe area: `padding-bottom: env(safe-area-inset-bottom)` on the bar; `<main>` receives matching bottom padding below `md` so no content or focused input is ever trapped behind the bar (FR-005's "never obscure content or inputs").

## "Más" sheet

Opens the existing `ui/sheet.tsx` (`side="bottom"`), triggered by the 5th bottom-bar slot. Contents, in order:

1. Remaining `NavArea`s the role can see, minus the 4 already on the bar (`getMoreSheetAreas(role)`):
   - Coach: Familias, Biblioteca.
   - Admin: Familias (Padres item still hidden inside it), Atletas is absent entirely (research R7).
2. Separator.
3. "Mi perfil" (`/perfil`, all roles).
4. "Salud IA" (`/admin/ai`, admin only).
5. "Cerrar sesión" (all roles).

Every row ≥48×48px (FR-005 acceptance #2). Opening the sheet uses `Sheet`'s existing Radix `Dialog` primitive: focus trap, Escape-to-close, focus return to the "Más" trigger on close — no new a11y work, inherited from the primitive per `ui/sheet.tsx`.

## Keyboard / on-screen-keyboard / assistive-technology behavior

- **Keyboard**: all 5 bottom-bar controls and every "Más" row are native `<a>`/`<button>` elements — full Tab/Enter/Space operability with no custom key handling required.
- **Screen readers**: `<nav aria-label="Navegación principal">` distinguishes the bar from the sidebar's own `aria-label="Menú de navegación"` (`AppShell.tsx:221`, unchanged) when both exist in the DOM (Tailwind responsive classes keep both trees mounted; only `display` toggles) — assistive tech users on a resized viewport are never presented two identically-labeled navigation landmarks.
- **On-screen keyboard (OSK) coexistence**: no coach flow today places a persistent input directly above a fixed bottom region — attendance/rubric/session forms are full-page, not modal-over-bar. Dialogs/sheets portal above the bar (`z-50` > bar's `z-40`) with Radix's focus trap already handling scroll-into-view. Real OSK occlusion cannot be simulated in jsdom or Playwright (no real virtual keyboard) — verified manually per `quickstart.md`, not gated by an automated test.
- **Page scroll**: the bar is `position: fixed`, so it never participates in `<main>`'s scroll; `<main>`'s bottom padding (above) guarantees the last scrollable row is never rendered underneath it.

## Acceptance mapping

| Spec acceptance (US3) | Satisfied by |
|---|---|
| Persistent bottom bar with 4 areas + "Más"; active area indicated | Structure above; `aria-current="page"` |
| "Más" lists remaining areas + profile/sign-out/(admin) diagnostics; all targets ≥48×48px | "Más sheet" section above |
| Admin variant substitutes the coach-only 4th slot | Biblioteca substitution (research R6) |
| Bar never obscures content or the on-screen keyboard | `fixed` positioning + safe-area + `<main>` padding; manual OSK check |
