# Contract — Dark Theme Tokens (optional story, FR-008)

Scope: coach surfaces only (this program is coach-experience-specific throughout; the parent portal is out of scope). Ships only if capacity allows (User Story 5, P3). **Hard dependency**: `specs/028-frontend-design-foundation`'s shadow/token consolidation must be merged first — inline `boxShadow`/color styles cannot respond to a CSS variant or a `prefers-color-scheme` media query, so every one of the ~13 files 028 tracks for shadow-token migration must be off inline styles before this ships, or each gets patched twice.

## Tailwind v4 activation

```css
@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));
```

Verified against Tailwind v4 docs in `specs/028-frontend-design-foundation/research.md` R5 — this variant targets the `data-theme` attribute, not `prefers-color-scheme` directly. The system-preference path is a separate, lower-priority CSS rule (below) so a manual choice always wins over the OS default.

```css
:root {
  /* light values — unchanged, already in style.css */
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme]) {
    /* dark values apply ONLY when the user hasn't made an explicit choice */
  }
}

:root[data-theme="dark"] {
  /* dark values — explicit override, always wins */
}

:root[data-theme="light"] {
  /* light values restated explicitly, so an explicit "light" choice overrides
     a dark OS preference too */
}
```

## Token mapping (final — contrast-checked against the real dark surface `#1a1a1a`, not eyeballed)

| Role | Token | Light | Dark | Contrast (dark) |
|---|---|---|---|---|
| Page plane | *(new)* `--color-page-plane` | implicit white | `#0d0d0d` | — |
| Card/chart surface | `--color-surface` / `--color-white` | `#ffffff` | `#1a1a1a` | — |
| Primary text | `--color-charcoal` | `#2f2f2f` | `#f2f2f0` | 15.53:1 |
| Secondary text | `--color-mid-gray` | `#717171` | `#a3a3a3` | 6.90:1 |
| Disclaimer text | `--color-text-disclaimer` | `#5a5a5a` | `#b8b8b8` | 8.77:1 |
| Subtle panel fill | `--color-light-gray` | `#f5f5f5` | `#242424` | *(fill, not text — no contrast floor)* |
| Border (hairline) | `--color-border-gray` | `rgba(34,42,53,0.08)` | `rgba(255,255,255,0.10)` | — |
| Card elevation | `--shadow-card` | multi-layer rgba shadow | replaced by 1px `rgba(255,255,255,0.08)` ring | *(shadows don't read against an already-dark surface — standard dark-mode adaptation)* |
| Accent | `--color-primary` | `#20b7c9` | **unchanged**, `#20b7c9` | 7.19:1 |
| Status success | `--color-success` | `#0ca30c` | **unchanged** | 5.19:1 |
| Status warning | `--color-warning` | `#fab219` | **unchanged** | 9.49:1 |
| Status danger | `--color-danger` | `#d03b3b` | **unchanged** | 3.62:1 |
| A/B/C ordinal ramp | (§ chart-style / data-model §2) | `#5bc6d5`/`#1cb5c7`/`#008492` | `#6dd6e6`/`#2fbfd1`/`#0d97a7` | validated (`--ordinal`) against `#1a1a1a` |

**Zero new hex values needed for accent + all four status tokens** — every one already clears an adequate contrast on the dark surface as shipped. Only surface, text, border, and shadow tokens need dark-specific values. This is the "monochrome base makes dark mode cheap" property, now with numbers behind it.

## Activation mechanism

```ts
type ThemePreference = "system" | "light" | "dark";
const STORAGE_KEY = "tyr:theme-preference:v1";

// On load: read STORAGE_KEY; if "light"|"dark", set document.documentElement
// dataset.theme accordingly; if "system"/missing, leave the attribute unset
// (the @media(prefers-color-scheme) rule above handles it).
```

- **Default**: follows `prefers-color-scheme: dark` (no attribute set) — zero-configuration, respects the device.
- **Manual override**: a 3-state control (Sistema / Claro / Oscuro) in the user menu (030's shell already builds this menu, `specs/030-coach-navigation-redesign/spec.md` FR-006) — persisted to `localStorage`, applied by toggling `data-theme` on `<html>`.
- **No flash-of-wrong-theme**: the stored preference is read and the attribute applied in an inline `<script>` in `index.html` (before first paint), not after React hydrates — standard pattern, avoids a light→dark flash on load for users with a stored "dark" preference.

## Activation rules / scope guardrails

- Applies to coach routes only. Parent-portal routes (`/parent/*` or equivalent) are explicitly out of scope for this optional story and keep light-only styling regardless of the stored preference — if a shared layout component is reused by both, it must read a "surface scope" flag rather than blindly honoring `data-theme`.
- Generated documents (PDF reports, newsletters, instructivos) are completely unaffected — FR-010 excludes them categorically; dark mode is an app-chrome concept only.
- Charts (`contracts/chart-style.md`) must render legibly in both modes — the accent/status/ordinal tokens above were chosen specifically so the chart contract's color roles need no dark-specific override beyond the surface/grid/axis-ink tokens already in this table.

## Test obligations (Constitution II / III)

- A contrast audit (automated, not manual) re-running the same validator logic used to derive this table against every token pair actually used in a component, for both `data-theme="light"` and `data-theme="dark"`.
- `jest-axe` pass in both modes for every page-level/dialog-level component (WCAG 2.1 AA is the floor in both modes, Constitution III — "meeting the same contrast bars as light mode" is FR-008's literal wording).
- A visual regression / manual audit checklist per coach module (tracked in `quickstart.md`) confirming no dark-on-dark invisible marks (spec's own edge case: "photos, illustrations, and charts must remain legible on dark surfaces").
