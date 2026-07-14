/**
 * Type declarations for `validate-palette.mjs` — lets TypeScript
 * consumers (the `vitest` test) import the vendored validator with
 * proper types without turning on project-wide `allowJs`.
 */

export interface PaletteCheck {
  name: string;
  status: "PASS" | "WARN" | "FAIL";
  detail: string;
  perColor?: Array<{ hex: string; ratio: number }>;
  worstDeltaE?: number | null;
  worstPair?: [string, string] | null;
}

export interface PaletteReport {
  passed: boolean;
  checks: PaletteCheck[];
}

export interface ValidateOptions {
  mode?: "light" | "dark";
  surface?: string;
  pairs?: "all" | "adjacent";
  lightnessBand?: [number, number];
  chromaFloor?: number;
  cvdTarget?: number;
  contrastFloor?: number;
}

export interface ValidateOrdinalOptions {
  surface?: string;
  minAdjacentDeltaL?: number;
  lightContrastFloor?: number;
  hueSpreadMax?: number;
}

export function validate(colors: string[], options?: ValidateOptions): PaletteReport;

export function validateOrdinal(
  colors: string[],
  options?: ValidateOrdinalOptions
): PaletteReport;

export const CHART_ROLE_PALETTE: string[];
export const CHART_ROLE_PALETTE_OPTIONS: ValidateOptions;
export const TIER_RAMP_LIGHT: string[];
export const TIER_RAMP_DARK: string[];
