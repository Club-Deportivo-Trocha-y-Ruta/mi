/**
 * Smoke + regression coverage for `frontend/scripts/validate-palette.mjs`
 * (feature 033, T002) — confirms the vendored validator is importable
 * from `vitest` (not only the Node CLI) and that this app's own chart
 * role palette + A/B/C ordinal ramp (T001/R2/R3) keep passing their
 * lightness-band/chroma-floor/CVD/contrast checks.
 *
 * Later tasks (T034, T060) extend this same import with more fixtures
 * (dark-theme token pairs); this file only covers the validator itself.
 */
import { describe, expect, it } from "vitest";
import {
  CHART_ROLE_PALETTE,
  CHART_ROLE_PALETTE_OPTIONS,
  TIER_RAMP_DARK,
  TIER_RAMP_LIGHT,
  validate,
  validateOrdinal,
} from "../../../scripts/validate-palette.mjs";

describe("validate-palette.mjs", () => {
  it("is importable as an ESM module with the expected named exports", () => {
    expect(typeof validate).toBe("function");
    expect(typeof validateOrdinal).toBe("function");
  });

  describe("validate() — chart role palette", () => {
    const report = validate(CHART_ROLE_PALETTE, CHART_ROLE_PALETTE_OPTIONS);

    it("passes lightness-band, chroma-floor, and cvd-separation", () => {
      const byName = Object.fromEntries(report.checks.map((c) => [c.name, c.status]));
      expect(byName["lightness-band"]).toBe("PASS");
      expect(byName["chroma-floor"]).toBe("PASS");
      expect(byName["cvd-separation"]).toBe("PASS");
    });

    it("flags the accent's sub-3:1 contrast as WARN (relief required), not FAIL", () => {
      const contrast = report.checks.find((c) => c.name === "contrast-vs-surface");
      expect(contrast?.status).toBe("WARN");
      const accent = contrast?.perColor?.find((c) => c.hex === "#20b7c9");
      expect(accent?.ratio).toBeCloseTo(2.42, 1);
    });

    it("passed=true overall (WARN does not block)", () => {
      expect(report.passed).toBe(true);
    });
  });

  describe("validateOrdinal() — A/B/C ramp", () => {
    it("light ramp passes every check, tier C sits exactly at the 2:1 ordinal floor", () => {
      const report = validateOrdinal(TIER_RAMP_LIGHT);
      expect(report.passed).toBe(true);
      const lightEnd = report.checks.find((c) => c.name === "light-end-contrast");
      expect(lightEnd?.status).toBe("PASS");
      expect(lightEnd?.detail).toContain("#5bc6d5");
    });

    it("dark ramp variant passes against the dark card surface (#1a1a1a)", () => {
      const report = validateOrdinal(TIER_RAMP_DARK, { surface: "#1a1a1a" });
      expect(report.passed).toBe(true);
    });

    it("rejects a ramp that is not monotone in lightness", () => {
      const report = validateOrdinal(["#5bc6d5", "#008492", "#1cb5c7"]);
      const monotone = report.checks.find((c) => c.name === "lightness-monotone");
      expect(monotone?.status).toBe("FAIL");
      expect(report.passed).toBe(false);
    });

    it("rejects a ramp spanning more than one hue", () => {
      const report = validateOrdinal(["#5bc6d5", "#1cb5c7", "#d03b3b"]);
      const hue = report.checks.find((c) => c.name === "single-hue");
      expect(hue?.status).toBe("FAIL");
      expect(report.passed).toBe(false);
    });
  });
});
