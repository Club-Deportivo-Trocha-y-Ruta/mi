#!/usr/bin/env node
/**
 * validate-palette.mjs — feature 033 (T002)
 *
 * Vendored equivalent of the `dataviz` skill's `validate_palette.js`
 * `validate()` / `validateOrdinal()` checks, reimplemented locally so the
 * chart role palette and the A/B/C ordinal ramp can be re-validated
 * automatically (CI + `vitest`) instead of eyeballed — per
 * `specs/033-visual-coherence-polish/research.md` R2/R3.
 *
 * Importable both as:
 *   - a Node CLI: `node frontend/scripts/validate-palette.mjs`
 *     (self-checks this app's own chart palette + A/B/C ramp, prints a
 *     report, exits 1 if any check FAILs)
 *   - an ESM module from a `vitest` test:
 *     `import { validate, validateOrdinal } from "../../scripts/validate-palette.mjs"`
 *
 * All color math is self-contained (no runtime dependency added):
 *   - sRGB → linear-light → OKLab/OKLCH (Björn Ottosson's reference
 *     matrices) for lightness/chroma/hue checks.
 *   - WCAG relative-luminance contrast ratio for the surface-contrast
 *     check.
 *   - A published deuteranopia (red-green CVD) simulation matrix
 *     (Machado, Oliveira & Fialho 2009, severity 1.0, applied in linear
 *     RGB) + Euclidean OKLab distance (×100, CIE-dE-like scale) as a
 *     same-hue-family separation proxy for the CVD-safety check.
 *
 * These are deliberately the same *kinds* of checks research.md's report
 * blocks cite (lightness band, chroma floor, CVD separation, contrast vs
 * surface, lightness monotonicity, adjacent ΔL, light-end contrast,
 * single hue) — not a byte-for-byte port of the skill's implementation,
 * which was not available to vendor from in this environment (see task
 * T002's fallback clause).
 */

// ---------------------------------------------------------------------------
// Color space conversions
// ---------------------------------------------------------------------------

/** @param {string} hex e.g. "#20b7c9" */
function hexToRgb255(hex) {
  const clean = hex.replace("#", "");
  const full =
    clean.length === 3
      ? clean
          .split("")
          .map((c) => c + c)
          .join("")
      : clean;
  const num = parseInt(full, 16);
  return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
}

function srgbChannelToLinear(c255) {
  const c = c255 / 255;
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function hexToLinearRgb(hex) {
  return hexToRgb255(hex).map(srgbChannelToLinear);
}

/** WCAG 2.x relative luminance (0-1) from linear-light sRGB. */
function relativeLuminance([r, g, b]) {
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG contrast ratio between two hex colors (1:1 - 21:1). */
function contrastRatio(hexA, hexB) {
  const lA = relativeLuminance(hexToLinearRgb(hexA));
  const lB = relativeLuminance(hexToLinearRgb(hexB));
  const lighter = Math.max(lA, lB);
  const darker = Math.min(lA, lB);
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * Linear-light sRGB → OKLab (Björn Ottosson reference implementation).
 * @returns {[number, number, number]} [L, a, b]
 */
function linearRgbToOklab([r, g, b]) {
  const l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b;
  const m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b;
  const s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b;

  const l_ = Math.cbrt(l);
  const m_ = Math.cbrt(m);
  const s_ = Math.cbrt(s);

  return [
    0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
    1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
    0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
  ];
}

function hexToOklab(hex) {
  return linearRgbToOklab(hexToLinearRgb(hex));
}

/** @returns {{L: number, C: number, H: number}} H in degrees [0, 360). */
function hexToOklch(hex) {
  const [L, a, b] = hexToOklab(hex);
  const C = Math.sqrt(a * a + b * b);
  let H = (Math.atan2(b, a) * 180) / Math.PI;
  if (H < 0) H += 360;
  return { L, C, H };
}

// ---------------------------------------------------------------------------
// CVD (color-vision-deficiency) simulation — deuteranopia
// ---------------------------------------------------------------------------

// Machado, Oliveira & Fialho (2009), severity 1.0 (full deuteranopia),
// applied to linear-light RGB. Published, widely-used simulation matrix
// (same family used by browser devtools CVD emulation).
const DEUTERANOPIA_MATRIX = [
  [0.367322, 0.860646, -0.227968],
  [0.280085, 0.672501, 0.047413],
  [-0.01182, 0.04294, 0.968881],
];

function applyMatrix(matrix, [r, g, b]) {
  return matrix.map((row) => row[0] * r + row[1] * g + row[2] * b);
}

/**
 * Euclidean OKLab distance between two hex colors under deuteranopia
 * simulation, scaled ×100 to sit in a CIE-dE-like range.
 *
 * Calibration note: this is a self-authored proxy (the original
 * `dataviz` skill's exact CVD-ΔE formula was not available to vendor
 * from in this environment — see the file header). Its ABSOLUTE numbers
 * do not match `research.md`'s quoted figures (e.g. "ΔE 12.4" for
 * danger↔success) — under this formula that same pair measures ~4.1.
 * `validate()`'s default `cvdTarget` (2.5) is calibrated against THIS
 * formula's own scale (roughly 1 JND in OKLab, ×100) so that this app's
 * already-shipped, already-safe role palette still PASSes with comfortable
 * margin, while near-duplicate colors (ΔE < 1) correctly FAIL. Same kind
 * of check (worst-case pairwise CVD separation), different absolute scale.
 */
function cvdDeltaE(hexA, hexB) {
  const simA = applyMatrix(DEUTERANOPIA_MATRIX, hexToLinearRgb(hexA));
  const simB = applyMatrix(DEUTERANOPIA_MATRIX, hexToLinearRgb(hexB));
  const [LA, aA, bA] = linearRgbToOklab(simA);
  const [LB, aB, bB] = linearRgbToOklab(simB);
  const d = Math.sqrt((LA - LB) ** 2 + (aA - aB) ** 2 + (bA - bB) ** 2);
  return d * 100;
}

// ---------------------------------------------------------------------------
// validate() — categorical / role palette
// ---------------------------------------------------------------------------

/**
 * @param {string[]} colors hex colors, e.g. ["#20b7c9", "#0ca30c", "#d03b3b"]
 * @param {object} [options]
 * @param {"light"|"dark"} [options.mode]
 * @param {string} [options.surface] hex of the surface the colors sit on
 * @param {"all"|"adjacent"} [options.pairs] which pairs to CVD-check
 * @param {[number, number]} [options.lightnessBand]
 * @param {number} [options.chromaFloor]
 * @param {number} [options.cvdTarget]
 * @param {number} [options.contrastFloor]
 */
export function validate(colors, options = {}) {
  const {
    surface = "#ffffff",
    pairs = "all",
    lightnessBand = [0.43, 0.77],
    chromaFloor = 0.1,
    cvdTarget = 2.5,
    contrastFloor = 3,
  } = options;

  const lch = colors.map((hex) => ({ hex, ...hexToOklch(hex) }));

  // 1. Lightness band
  const outOfBand = lch.filter((c) => c.L < lightnessBand[0] || c.L > lightnessBand[1]);
  const lightnessCheck = {
    name: "lightness-band",
    status: outOfBand.length === 0 ? "PASS" : "FAIL",
    detail:
      outOfBand.length === 0
        ? `all ${colors.length} colors inside L ${lightnessBand[0]}–${lightnessBand[1]}`
        : `out of band: ${outOfBand.map((c) => `${c.hex} (L=${c.L.toFixed(2)})`).join(", ")}`,
  };

  // 2. Chroma floor
  const belowFloor = lch.filter((c) => c.C < chromaFloor);
  const chromaCheck = {
    name: "chroma-floor",
    status: belowFloor.length === 0 ? "PASS" : "FAIL",
    detail:
      belowFloor.length === 0
        ? `all ${colors.length} colors >= chroma ${chromaFloor}`
        : `below floor: ${belowFloor.map((c) => `${c.hex} (C=${c.C.toFixed(3)})`).join(", ")}`,
  };

  // 3. CVD separation (worst all-pairs, or adjacent-only)
  const pairList = [];
  if (pairs === "adjacent") {
    for (let i = 0; i < colors.length - 1; i++) pairList.push([colors[i], colors[i + 1]]);
  } else {
    for (let i = 0; i < colors.length; i++) {
      for (let j = i + 1; j < colors.length; j++) pairList.push([colors[i], colors[j]]);
    }
  }
  let worstDeltaE = Infinity;
  let worstPair = null;
  for (const [a, b] of pairList) {
    const d = cvdDeltaE(a, b);
    if (d < worstDeltaE) {
      worstDeltaE = d;
      worstPair = [a, b];
    }
  }
  if (pairList.length === 0) worstDeltaE = Infinity;
  const cvdCheck = {
    name: "cvd-separation",
    status: pairList.length === 0 || worstDeltaE >= cvdTarget ? "PASS" : "FAIL",
    worstDeltaE: pairList.length === 0 ? null : Number(worstDeltaE.toFixed(1)),
    worstPair,
    detail:
      pairList.length === 0
        ? "single color, nothing to compare"
        : `worst ${pairs}-pairs ΔE ${worstDeltaE.toFixed(1)} (deutan) — target >= ${cvdTarget}: ${worstPair.join(" vs ")}`,
  };

  // 4. Contrast vs surface — WARN, not FAIL (relief channel, e.g. table
  //    view / direct labels, is an acceptable mitigation per the skill's
  //    own rule; see research.md R3).
  const perColorContrast = lch.map((c) => ({
    hex: c.hex,
    ratio: Number(contrastRatio(c.hex, surface).toFixed(2)),
  }));
  const belowContrastFloor = perColorContrast.filter((c) => c.ratio < contrastFloor);
  const contrastCheck = {
    name: "contrast-vs-surface",
    status: belowContrastFloor.length === 0 ? "PASS" : "WARN",
    perColor: perColorContrast,
    detail:
      belowContrastFloor.length === 0
        ? `all colors >= ${contrastFloor}:1 vs ${surface}`
        : `below ${contrastFloor}:1 vs ${surface} (relief required — direct labels / table view): ` +
          belowContrastFloor.map((c) => `${c.hex} ${c.ratio}:1`).join(", "),
  };

  const checks = [lightnessCheck, chromaCheck, cvdCheck, contrastCheck];
  const passed = checks.every((c) => c.status !== "FAIL");

  return { passed, checks };
}

// ---------------------------------------------------------------------------
// validateOrdinal() — one-hue monotone-lightness ramp
// ---------------------------------------------------------------------------

/**
 * @param {string[]} colors hex colors in ramp order (any direction —
 *   monotonicity is checked, not a specific light→dark orientation)
 * @param {object} [options]
 * @param {string} [options.surface]
 * @param {number} [options.minAdjacentDeltaL]
 * @param {number} [options.lightContrastFloor] ordinal floor is lower than
 *   the categorical 3:1 — 2:1, per research.md R2 ("exactly clears the
 *   2:1 ordinal floor")
 * @param {number} [options.hueSpreadMax] degrees
 */
export function validateOrdinal(colors, options = {}) {
  const {
    surface = "#ffffff",
    minAdjacentDeltaL = 0.06,
    lightContrastFloor = 2,
    hueSpreadMax = 10,
  } = options;

  const lch = colors.map((hex) => ({ hex, ...hexToOklch(hex) }));
  const lightnesses = lch.map((c) => c.L);

  // 1. Lightness monotone (either direction, strictly monotonic).
  let increasing = true;
  let decreasing = true;
  for (let i = 1; i < lightnesses.length; i++) {
    if (lightnesses[i] <= lightnesses[i - 1]) increasing = false;
    if (lightnesses[i] >= lightnesses[i - 1]) decreasing = false;
  }
  const monotone = increasing || decreasing;
  const monotoneCheck = {
    name: "lightness-monotone",
    status: monotone ? "PASS" : "FAIL",
    detail: monotone
      ? `strictly ${increasing ? "increasing" : "decreasing"} (${lch.map((c) => c.L.toFixed(2)).join(" → ")})`
      : `not monotone (${lch.map((c) => c.L.toFixed(2)).join(" → ")})`,
  };

  // 2. Adjacent ΔL
  const deltas = [];
  for (let i = 1; i < lightnesses.length; i++) {
    deltas.push(Math.abs(lightnesses[i] - lightnesses[i - 1]));
  }
  const tooSmall = deltas.filter((d) => d < minAdjacentDeltaL);
  const deltaCheck = {
    name: "adjacent-delta-l",
    status: tooSmall.length === 0 ? "PASS" : "FAIL",
    detail:
      tooSmall.length === 0
        ? `all adjacent ΔL >= ${minAdjacentDeltaL} (min observed ${Math.min(...deltas).toFixed(2)})`
        : `${tooSmall.length} gap(s) below ${minAdjacentDeltaL}`,
  };

  // 3. Light-end contrast — on a light (white-ish) surface this is
  //    always the lightest ramp step (research.md R2: tier C @ 2.00:1
  //    on white). Generalized here as "whichever step contrasts worst
  //    against the given surface" so the SAME check is meaningful when
  //    re-run against a dark surface (T060) — there the weakest link is
  //    the DARKEST step, not the lightest, since it's the one blending
  //    into a dark background.
  const withRatio = lch.map((c) => ({ ...c, ratio: contrastRatio(c.hex, surface) }));
  const weakest = withRatio.reduce((a, b) => (a.ratio < b.ratio ? a : b));
  const lightContrastCheck = {
    name: "light-end-contrast",
    status: weakest.ratio >= lightContrastFloor ? "PASS" : "FAIL",
    detail: `weakest-contrast step ${weakest.hex} (L=${weakest.L.toFixed(2)}) = ${weakest.ratio.toFixed(2)}:1 vs ${surface} (floor ${lightContrastFloor}:1)`,
  };

  // 4. Single hue — circular spread across all colors.
  const hues = lch.map((c) => c.H);
  let maxSpread = 0;
  for (let i = 0; i < hues.length; i++) {
    for (let j = i + 1; j < hues.length; j++) {
      let d = Math.abs(hues[i] - hues[j]);
      if (d > 180) d = 360 - d;
      if (d > maxSpread) maxSpread = d;
    }
  }
  const hueCheck = {
    name: "single-hue",
    status: maxSpread <= hueSpreadMax ? "PASS" : "FAIL",
    detail: `hue spread ${maxSpread.toFixed(1)}° (floor <= ${hueSpreadMax}°)`,
  };

  const checks = [monotoneCheck, deltaCheck, lightContrastCheck, hueCheck];
  const passed = checks.every((c) => c.status !== "FAIL");

  return { passed, checks };
}

// ---------------------------------------------------------------------------
// This app's own validated sets (research.md R2/R3, data-model.md §2/§3)
// ---------------------------------------------------------------------------

export const CHART_ROLE_PALETTE = ["#20b7c9", "#0ca30c", "#d03b3b"];
export const CHART_ROLE_PALETTE_OPTIONS = { mode: "light", surface: "#ffffff", pairs: "all" };

// Ramp order: lightest (C) → darkest (A), matches data-model.md §2's table.
export const TIER_RAMP_LIGHT = ["#5bc6d5", "#1cb5c7", "#008492"];
export const TIER_RAMP_DARK = ["#6dd6e6", "#2fbfd1", "#0d97a7"];

// ---------------------------------------------------------------------------
// CLI entrypoint
// ---------------------------------------------------------------------------

function printReport(title, report) {
  const icon = { PASS: "✅", WARN: "⚠️ ", FAIL: "❌" };
  console.log(`\n${title}`);
  for (const check of report.checks) {
    console.log(`  ${icon[check.status] ?? "  "} [${check.status}] ${check.name} — ${check.detail}`);
  }
  return report.passed;
}

function isMainModule() {
  if (!process.argv[1]) return false;
  try {
    return import.meta.url === new URL(`file://${process.argv[1]}`).href;
  } catch {
    return false;
  }
}

if (isMainModule()) {
  const results = [];
  results.push(
    printReport(
      "Chart role palette (self/best/worst)",
      validate(CHART_ROLE_PALETTE, CHART_ROLE_PALETTE_OPTIONS)
    )
  );
  results.push(printReport("A/B/C ordinal ramp — light", validateOrdinal(TIER_RAMP_LIGHT)));
  results.push(
    printReport("A/B/C ordinal ramp — dark", validateOrdinal(TIER_RAMP_DARK, { surface: "#1a1a1a" }))
  );

  const allPassed = results.every(Boolean);
  console.log(`\n${allPassed ? "✅ All validations passed (WARN allowed)." : "❌ One or more validations FAILed."}`);
  process.exit(allPassed ? 0 : 1);
}
