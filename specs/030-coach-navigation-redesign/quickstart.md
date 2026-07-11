# Quickstart — 030 Coach Navigation Redesign

Validation guide proving the feature end-to-end. Details live in [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/). Assumes 028 (shared components/tokens) and 029 (surface subtraction) have landed first, per program order.

## Prerequisites

```bash
cd frontend && npm install          # no new runtime deps expected for 030 itself
docker compose up                   # full stack with seed data (dev credentials in CLAUDE.md)
```

## Automated validation

```bash
# Unit + component + a11y
cd frontend && npm run typecheck && npm test

# Must exist and pass (fail on the pre-redesign shell):
#  - lib/__tests__/navigation.test.ts:
#      resolveAreaDefaultTo falls back to Boletines for admin on Familias (not /parents)
#      isAreaActive longest-prefix-matches /competitions/insights/season/2026 → "competitions"
#      getBottomBarAreas("admin") includes "library", excludes "athletes"
#  - components/layout/__tests__/AppShell.test.tsx (rewritten):
#      coach sees Atletas + Padres NESTED under their groups (not bare top-level links)
#      "Boletines" (not "Boletines Mensuales"), "Informes del club" (not "Reportes mensuales")
#      admin: "Salud IA" is NOT a sidebar/bottom-bar link; IS reachable inside the opened user menu
#      admin: Atletas group entirely absent; bottom bar 4th slot is Biblioteca
#      the group containing the current route is expanded + visually indicated (deep-link test)
#      quick-create: "Nuevo atleta" absent for admin
#      zero jest-axe violations on: default shell, expanded sidebar group, open "Más" sheet,
#        open user menu, open quick-create menu
#  - SessionsListPage: "Crear con IA" visible next to "+ Nueva sesión" (FR-007)
#  - strength/CatalogPage: "Armar bloque" visible (FR-007)
#  - AthleteDetailPage tab renamed "Insights IA" (was "Análisis IA")
#  - No test still asserts the old "Reportes mensuales" / "Boletines Mensuales" / "Análisis IA" strings

# E2E (Chromium preinstalled; do NOT run `playwright install`)
cd frontend && npm run test:e2e -- e2e/coach-navigation.spec.ts
#  - viewport ≥768px (md): sidebar visible, bottom bar absent
#  - viewport <768px: bottom bar visible (4 areas + Más), sidebar absent — no width with neither
#  - every interactive nav/menu/sheet control ≥48×48px (reuses the 028 target-size helper)
#  - admin login: bottom bar shows Biblioteca in the 4th slot, not Atletas
```

## Manual validation scenarios (tied to spec Success Criteria)

1. **SC-001 / SC-002 — reach everything, 0 orphans**: as coach, starting from login, open every one of the 39 routes in `contracts/navigation-model.md` using only visible navigation (sidebar on desktop, bottom bar + "Más" on mobile width) — no typed URLs. Confirm the AI session assistant (via "Crear con IA"), the season panorama (via Competencias), and strength-block creation (via Biblioteca → Fuerza) are each one visible interaction away (US2).
2. **SC-003 — no regression on the fastest paths**: from any screen, reach Calendario, Sesiones, Atletas, and Competencias in exactly 1 interaction (click the sidebar/bottom-bar item).
3. **SC-004 — mobile thumb reach**: on a phone-width viewport, reach Inicio/Entrenamiento/Competencias/Atletas in 1 tap; reach every other destination (Familias, Biblioteca, Mi perfil, Salud IA as admin) in ≤3 taps via "Más."
4. **SC-005 — quick-create**: from an unrelated screen (e.g., Fuerza catalog), create a session, a competition, and a calendar event in ≤2 interactions each via the header "+" ; confirm "Nuevo atleta" is absent for admin.
5. **SC-006 — naming**: grep the running app for "Reportes Mensuales," "Boletines Mensuales," and "Análisis IA" — zero hits; "Informes del club," "Boletines," and "Insights IA"/"Analizar con IA" are each used exactly once per concept (cross-check the table in `research.md` R5).
6. **SC-007 — bookmarks**: open 3–4 pre-redesign bookmarked URLs (a competition detail, an athlete detail, `/training/reports/2026/6`, `/anxiety`) directly — each resolves to the same screen as before, with its containing nav area correctly expanded/highlighted (deep-entry edge case).
7. **SC-008 — discoverability**: hand the running app to a first-time observer (e.g., the admin account) and time how long it takes to locate "Panorama de temporada" and "Armar bloque de fuerza" using navigation alone — target under 30 seconds each.
8. **Admin variant (US1 acceptance #5)**: log in as `admin@trochyruta.com`; confirm Atletas and Padres are absent everywhere (sidebar, bottom bar, "Más"), and every remaining visible item opens successfully (no dead-click bounce).
9. **Keyboard/AT sweep (FR-010)**: Tab from the skip-link through the sidebar groups, header quick-create, user menu, and (at a narrow viewport) the bottom bar and "Más" sheet — every control reachable, operable with Enter/Space, Escape closes menus/sheet and returns focus to the trigger; confirm "Saltar a contenido" still lands on `#main-content`.
10. **Anxiety reachability (edge case)**: confirm `/anxiety` still opens directly (URL unchanged) and is now found one level under Atletas rather than top-level; note admin's nav-visibility trade-off is expected per `research.md` R7, not a bug.

## Expected outcomes

All items in `spec.md` Success Criteria SC-001…SC-008 hold; `AppShell` and its new sibling components (`SidebarNav`, `BottomNav`, `MoreSheet`, `UserMenu`, `QuickCreate`) are zero-jest-axe-violation; the Playwright viewport sweep is green at both breakpoints; no pre-existing URL returns a different result than before the feature.
