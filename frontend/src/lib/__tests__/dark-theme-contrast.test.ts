/**
 * Dark-theme contrast audit (feature 033, US5, T060).
 *
 * Re-runs the T002 validator (`validate`/`validateOrdinal` from
 * `frontend/scripts/validate-palette.mjs`) against every hex-parseable
 * token pair actually defined in `style.css`'s dark block — the three
 * cascade layers under "Dark theme tokens (feature 033, US5 / FR-008,
 * optional story)":
 *
 *   1. `@media (prefers-color-scheme: dark) { :root:not([data-theme]) {...} }`
 *   2. `:root[data-theme="dark"] {...}`
 *   3. `:root[data-theme="light"] {...}` (explicit light restated)
 *
 * All three blocks carry IDENTICAL values per mode (the media-query block
 * and the explicit `data-theme="dark"` block are kept in lockstep by
 * design — see the block comment in style.css), so this file hardcodes
 * one light/dark value pair per token and audits both `data-theme="light"`
 * and `data-theme="dark"`, per FR-008 ("the same contrast bars as light
 * mode"). If style.css's dark block ever drifts from these values, this
 * test's own numbers (matched 1:1 against `contracts/dark-theme-tokens.md`'s
 * table) will no longer describe the shipped CSS — update both together.
 *
 * Scope note — tokens deliberately NOT audited here:
 *   - `--color-page-plane` / `--color-surface` / `--color-white`: these
 *     ARE the surface, not a foreground-vs-surface pair — nothing to
 *     contrast them against.
 *   - `--color-light-gray` (subtle panel fill): a fill, not text — the
 *     contract explicitly notes "no contrast floor" for this role.
 *   - `--color-border-gray` / `--shadow-card` / `--shadow-card-alt`: rgba()
 *     values, not hex — `validate-palette.mjs`'s `hexToRgb255` only parses
 *     `#rrggbb`/`#rgb`, so these are structurally out of reach for this
 *     validator. Border/shadow legibility is covered by the T061 jest-axe
 *     dark-mode sweep instead (rendered-DOM check, not a token-math one).
 *   - `--color-primary` / `--color-success` / `--color-warning` /
 *     `--color-danger`: NOT part of style.css's dark block at all — the
 *     contract states them "unchanged" between modes, so `:root[data-theme=
 *     "dark"]` never redefines them. Their contrast is exercised by the
 *     existing chart-role-palette check in `validate-palette.test.ts`
 *     (T002/T034) and by `StatusBadge.tsx`'s own design (status color is
 *     an aria-hidden 12px icon + a 10%-opacity tinted pill, never the
 *     label text itself — see that component's header comment for why a
 *     literal color-vs-white text contrast number would not describe how
 *     it actually renders).
 */
import { describe, expect, it } from "vitest";
import {
  TIER_RAMP_DARK,
  TIER_RAMP_LIGHT,
  validate,
  validateOrdinal,
} from "../../../scripts/validate-palette.mjs";

const SURFACE_LIGHT = "#ffffff";
const SURFACE_DARK = "#1a1a1a";

/** WCAG 2.x AA floor for normal-size body/label text. */
const TEXT_CONTRAST_FLOOR = 4.5;

/**
 * One row per text-role token redefined in style.css's dark block.
 * `dark` values and `expectedDark` mirror `contracts/dark-theme-tokens.md`'s
 * table exactly (15.53 / 6.90 / 8.77) — this test fails loudly if the CSS
 * and the contract ever drift apart.
 */
const TEXT_TOKEN_PAIRS = [
  {
    role: "Primary text (--color-charcoal / --color-text-primary)",
    light: "#2f2f2f",
    dark: "#f2f2f0",
    expectedDark: 15.53,
  },
  {
    role: "Secondary text (--color-mid-gray)",
    light: "#717171",
    dark: "#a3a3a3",
    expectedDark: 6.9,
  },
  {
    role: "Disclaimer text (--color-text-disclaimer)",
    light: "#5a5a5a",
    dark: "#b8b8b8",
    expectedDark: 8.77,
  },
];

/** Extracts the single-color contrast ratio the validator computed. */
function contrastRatioFor(hex: string, surface: string): number {
  // Neutralize the categorical checks (lightness band / chroma floor / CVD
  // separation) — they're meaningless for a single grayscale text color and
  // are already exercised elsewhere (validate-palette.test.ts). This test
  // audits one thing only: the contrast-vs-surface number.
  const report = validate([hex], {
    surface,
    lightnessBand: [0, 1],
    chromaFloor: 0,
    contrastFloor: 0,
  });
  const contrastCheck = report.checks.find((c) => c.name === "contrast-vs-surface");
  if (!contrastCheck || !contrastCheck.perColor) {
    throw new Error(`validate() did not return a contrast-vs-surface check for ${hex}`);
  }
  return contrastCheck.perColor[0].ratio;
}

describe("dark-theme contrast audit (T060)", () => {
  describe.each(TEXT_TOKEN_PAIRS)("$role", ({ light, dark, expectedDark }) => {
    it(`clears WCAG AA (${TEXT_CONTRAST_FLOOR}:1) in data-theme="light"`, () => {
      const ratio = contrastRatioFor(light, SURFACE_LIGHT);
      expect(ratio).toBeGreaterThanOrEqual(TEXT_CONTRAST_FLOOR);
    });

    it(`clears WCAG AA (${TEXT_CONTRAST_FLOOR}:1) in data-theme="dark"`, () => {
      const ratio = contrastRatioFor(dark, SURFACE_DARK);
      expect(ratio).toBeGreaterThanOrEqual(TEXT_CONTRAST_FLOOR);
      // Locks the dark value to contracts/dark-theme-tokens.md's published
      // number — catches silent drift between the CSS and the contract.
      expect(ratio).toBeCloseTo(expectedDark, 1);
    });

    it("dark mode meets or exceeds light mode's contrast bar (FR-008)", () => {
      const lightRatio = contrastRatioFor(light, SURFACE_LIGHT);
      const darkRatio = contrastRatioFor(dark, SURFACE_DARK);
      expect(darkRatio).toBeGreaterThanOrEqual(lightRatio);
    });
  });

  describe("A/B/C ordinal ramp (--color-tier-a/-b/-c)", () => {
    it("passes every validateOrdinal() check in data-theme=\"light\"", () => {
      const report = validateOrdinal(TIER_RAMP_LIGHT, { surface: SURFACE_LIGHT });
      expect(report.passed).toBe(true);
    });

    it("passes every validateOrdinal() check in data-theme=\"dark\"", () => {
      const report = validateOrdinal(TIER_RAMP_DARK, { surface: SURFACE_DARK });
      expect(report.passed).toBe(true);
    });
  });
});
