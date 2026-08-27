# Nav & coach-dashboard redesign — design mockups

Visual redesign proposal for (a) the lateral sidebar navigation — coach/admin
and parent portal — and (b) the coach home dashboard. Requested 2026-08-27.

**Live canvas (view, comment, hand-edit, export PNG/PDF):**
<https://claude.ai/code/artifact/83749f61-cecd-4249-8d75-fd96820e6418>

These are **static mockups**, not code. Every value is lifted from the real
design system (`frontend/src/style.css`, `components/ui/*`, `components/layout/*`):
Inter + Cal Sans, brand teal `#20b7c9` / `#008492`, charcoal `#2f2f2f`,
the Cal.com 3-layer `--shadow-card`, 12 px controls / 16 px cards radii,
≥44 px touch targets. No new colors and no new nav destinations — the six
`NAV_AREAS` of `frontend/src/lib/navigation.ts` are only regrouped visually.

## Artboards

| File | Shows |
|---|---|
| `Main.dc.html` | Coach home (1440×900) with the redesigned sidebar in place: greeting header, Próxima sesión / Próxima carrera / Carga semanal row, Semana en curso strip, Pendientes inbox, Alertas de medición, Asistencia mini-chart |
| `NavEntrenador.dc.html` | Sidebar spec sheet: expanded 256 px (state `/training/sessions`) + collapsed 72 px rail (tablet) + anatomy notes |
| `PadresInicio.dc.html` | Parent home on Android (390×844) with the proposed bottom nav (parity with feature 030's coach BottomNav) |
| `PadresMenu.dc.html` | Parent lateral drawer redesign: athlete switcher rows, iconed nav, profile/logout, consent status. Same bar becomes static at ≥768 px |
| `DireccionB.dc.html` | Low-fi alternate direction (dark charcoal sidebar) with its tradeoff, for comparison |

`canvas.json` lays the artboards out on the canvas; `logo-mark.png` is the TR
monogram cropped from `frontend/public/logo.webp`.

## Key proposal points

- **Active state**: teal tint `#e9f8fa` + 3 px brand bar + icon `#008492`;
  label stays charcoal semibold (color is never the only channel).
- **Groups**: two overlines — «Operación» (Inicio, Entrenamiento, Competencias,
  Atletas) and «Club» (Familias, Biblioteca).
- **Badges**: real pending counts from the Pendientes sources; amber dot +
  tooltip in rail mode.
- **Rail 72 px**: manual collapse, suggested default at 768–1024 px (coach on
  tablet in the field). The dual ≥44 px controls and auto-expand from
  feature 030 are preserved.
- **User card** moves to the sidebar foot (menu: perfil, apariencia, atajos,
  salir); header keeps only «Crear».
- **Parents**: bottom nav on mobile (Android + 3G/4G reality), drawer keeps
  athlete switching + profile; parent portal stays light-theme (feature 033).
- **Dark mode**: same token roles; active tint computed over `#1a1a1a`.

## Updating the mockups

Edit the `.dc.html` / `canvas.json` sources here and re-seed with the
`/design` skill in Claude Code (the canvas artifact URL above stays stable),
or hand-edit directly on the live canvas and Save.
