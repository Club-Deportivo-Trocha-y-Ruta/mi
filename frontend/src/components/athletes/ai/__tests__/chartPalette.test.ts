/**
 * T034 — palette-validation guard for the chart role palette actually
 * consumed by DistributionChart.tsx / EvolutionChart.tsx (own series /
 * best / worst reference lines rendered via var(--color-primary) /
 * var(--color-success) / var(--color-danger), per contracts/chart-style.md
 * "Color roles") and for the A/B/C ordinal ramp (T001/T015).
 *
 * Complements `src/lib/__tests__/validate-palette.test.ts` (T002, which
 * covers the validator module itself in isolation) by:
 *
 *   1. Cross-checking the vendored CHART_ROLE_PALETTE/TIER_RAMP_* fixtures
 *      against the live --color-primary/--color-success/--color-danger hex
 *      values defined in src/style.css — the tokens the charts actually
 *      render with — so a future edit to either side (the CSS token or the
 *      validator's fixture) fails a test instead of silently drifting
 *      apart from the validated set.
 *   2. Re-asserting lightness-band/chroma-floor/CVD-separation PASS and
 *      overall passed=true for both the chart role palette (pairs:"all",
 *      per chart-style.md's "any two reference lines can sit adjacent on
 *      one curve" rule) and the A/B/C ordinal ramp, in both light and dark.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  CHART_ROLE_PALETTE,
  CHART_ROLE_PALETTE_OPTIONS,
  TIER_RAMP_DARK,
  TIER_RAMP_LIGHT,
  validate,
  validateOrdinal,
} from "../../../../../scripts/validate-palette.mjs";

// process.cwd() is the `frontend/` package root when vitest runs (see
// vitest.config.ts — no custom `root` override), so this resolves the same
// file the app's own <style> import serves at runtime, regardless of how
// the test runner resolves import.meta.url for this module.
const styleCssPath = path.resolve(process.cwd(), "src/style.css");
const styleCss = readFileSync(styleCssPath, "utf-8");

function cssVarHex(name: string): string | undefined {
  const match = styleCss.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`));
  return match?.[1]?.toLowerCase();
}

describe("chart role palette guard (T034) — DistributionChart/EvolutionChart color tokens", () => {
  it("CHART_ROLE_PALETTE matches the live --color-primary/--color-success/--color-danger tokens the charts render with", () => {
    expect(cssVarHex("--color-primary")).toBe(CHART_ROLE_PALETTE[0]);
    expect(cssVarHex("--color-success")).toBe(CHART_ROLE_PALETTE[1]);
    expect(cssVarHex("--color-danger")).toBe(CHART_ROLE_PALETTE[2]);
  });

  it("CHART_ROLE_PALETTE_OPTIONS keeps pairs:'all' — any two rider reference lines can sit adjacent on one curve (contracts/chart-style.md)", () => {
    expect(CHART_ROLE_PALETTE_OPTIONS.pairs).toBe("all");
  });

  describe("chart role palette (own series / best / worst) still passes its validated checks", () => {
    const report = validate(CHART_ROLE_PALETTE, CHART_ROLE_PALETTE_OPTIONS);
    const byName = Object.fromEntries(
      report.checks.map((c: { name: string; status: string }) => [c.name, c.status]),
    );

    it("lightness-band, chroma-floor, and cvd-separation all PASS", () => {
      expect(byName["lightness-band"]).toBe("PASS");
      expect(byName["chroma-floor"]).toBe("PASS");
      expect(byName["cvd-separation"]).toBe("PASS");
    });

    it("overall passed=true (the accent's sub-3:1 contrast WARN is a documented, non-blocking relief obligation satisfied by the table-view twin — T028/T031, not a regression)", () => {
      expect(report.passed).toBe(true);
    });
  });

  describe("A/B/C ordinal ramp still passes in both light and dark", () => {
    it("light ramp passes every check", () => {
      const report = validateOrdinal(TIER_RAMP_LIGHT);
      expect(report.passed).toBe(true);
    });

    it("dark ramp passes against the dark card surface", () => {
      const report = validateOrdinal(TIER_RAMP_DARK, { surface: "#1a1a1a" });
      expect(report.passed).toBe(true);
    });
  });
});
