/**
 * Smoke tests para GROWTH_BANDS_WHO y getBandSpec.
 *
 * Verifica que cada combinación (indicador, banda) devuelve un spec con
 * label, color y narrative no vacíos, y que getBandSpec tiene fallback seguro.
 */

import { describe, it, expect } from "vitest";
import { GROWTH_BANDS_WHO, getBandSpec } from "@/lib/growth/bands";
import type { GrowthBand } from "@/hooks/athletes/useGrowthMetrics";
import type { GrowthIndicator } from "@/lib/growth/lms";

const INDICATORS: GrowthIndicator[] = ["height_for_age", "bmi_for_age", "weight_for_age"];
const BANDS: GrowthBand[] = ["low", "watch_low", "ok", "watch_high", "high"];

describe("GROWTH_BANDS_WHO — cobertura completa de combinaciones", () => {
  for (const indicator of INDICATORS) {
    for (const band of BANDS) {
      it(`${indicator} / ${band} tiene label, color y narrative no vacíos`, () => {
        const spec = GROWTH_BANDS_WHO[indicator][band];
        expect(spec.label).toBeTruthy();
        expect(spec.color).toBeTruthy();
        expect(spec.narrative).toBeTruthy();
      });
    }
  }
});

describe("getBandSpec", () => {
  it("retorna el spec correcto para height_for_age / ok", () => {
    const spec = getBandSpec("height_for_age", "ok");
    expect(spec.label).toBe("Adecuada");
    expect(spec.color).toBe("green");
    expect(spec.narrative).not.toBe("");
  });

  it("retorna el spec correcto para bmi_for_age / low", () => {
    const spec = getBandSpec("bmi_for_age", "low");
    expect(spec.label).toBe("Delgadez");
    expect(spec.color).toBe("red");
    expect(spec.narrative).not.toBe("");
  });

  it("retorna el spec correcto para weight_for_age / high", () => {
    const spec = getBandSpec("weight_for_age", "high");
    expect(spec.label).toBe("Peso muy alto");
    expect(spec.color).toBe("orange");
    expect(spec.narrative).not.toBe("");
  });

  it("retorna el spec correcto para height_for_age / watch_high (color blue)", () => {
    const spec = getBandSpec("height_for_age", "watch_high");
    expect(spec.label).toBe("Talla alta");
    expect(spec.color).toBe("blue");
  });

  it("retorna el spec correcto para height_for_age / low (color orange)", () => {
    const spec = getBandSpec("height_for_age", "low");
    expect(spec.label).toBe("Talla baja");
    expect(spec.color).toBe("orange");
  });

  it("fallback seguro cuando la combinación no existe en runtime", () => {
    // Forzar una combinación inválida con casting para testear el fallback
    const spec = getBandSpec(
      "height_for_age" as GrowthIndicator,
      "nonexistent_band" as GrowthBand,
    );
    expect(spec.label).toBeTruthy();
    expect(spec.color).toBeTruthy();
    expect(spec.narrative).toBeTruthy();
  });
});
