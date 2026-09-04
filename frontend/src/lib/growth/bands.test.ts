/**
 * Tests de `lib/growth/bands.ts`.
 *
 * `classifyBand` se prueba con 10 valores de Z por indicador — cortes en
 * paridad exacta con `backend/app/services/growth.py`
 * (`classify_nutritional_status_height` / `classify_nutritional_status_bmi`),
 * incluyendo el fix D2: para talla y peso, `1 < z ≤ 2` cae en
 * `talla_adecuada` (no una banda separada) y `talla_alta` sólo aplica por
 * encima de +2.
 */

import { describe, it, expect } from "vitest";

import {
  BAND_VOCABULARY,
  classifyBand,
  getBandSpec,
  getBandVocabulary,
  type NutritionalStatus,
} from "@/lib/growth/bands";
import type { GrowthIndicator } from "@/lib/growth/lms";

// ---------------------------------------------------------------------------
// classifyBand — paridad con cortes del backend (10 z por indicador)
// ---------------------------------------------------------------------------

describe("classifyBand — height_for_age (paridad con classify_nutritional_status_height)", () => {
  it.each<[number, NutritionalStatus]>([
    [-3, "retraso_talla"],
    [-2.5, "retraso_talla"],
    [-2, "riesgo_retraso_talla"], // −2 ≤ z < −1 (límite inferior inclusive)
    [-1.5, "riesgo_retraso_talla"],
    [-1, "talla_adecuada"], // −1 ≤ z ≤ 2 (límite inferior inclusive)
    [0, "talla_adecuada"],
    [1, "talla_adecuada"],
    [2, "talla_adecuada"], // D2: límite superior inclusive — ya NO es talla_alta
    [2.01, "talla_alta"],
    [3, "talla_alta"],
  ])("z=%s → %s", (z, expected) => {
    expect(classifyBand("height_for_age", z)).toBe(expected);
  });
});

describe("classifyBand — weight_for_age (misma forma que talla — sin enum propio)", () => {
  it.each<[number, NutritionalStatus]>([
    [-3, "retraso_talla"],
    [-2.5, "retraso_talla"],
    [-2, "riesgo_retraso_talla"],
    [-1.5, "riesgo_retraso_talla"],
    [-1, "talla_adecuada"],
    [0, "talla_adecuada"],
    [1, "talla_adecuada"],
    [2, "talla_adecuada"],
    [2.01, "talla_alta"],
    [3, "talla_alta"],
  ])("z=%s → %s", (z, expected) => {
    expect(classifyBand("weight_for_age", z)).toBe(expected);
  });
});

describe("classifyBand — bmi_for_age (paridad con classify_nutritional_status_bmi)", () => {
  it.each<[number, NutritionalStatus]>([
    [-3, "delgadez_severa"],
    [-2.5, "delgadez_severa"],
    [-2, "delgadez"], // −2 ≤ z < −1
    [-1.5, "delgadez"],
    [-1, "adecuado"], // −1 ≤ z ≤ 1
    [0, "adecuado"],
    [1, "adecuado"],
    [1.5, "sobrepeso"], // 1 < z ≤ 2
    [2, "sobrepeso"],
    [3, "obesidad"], // z > 2
  ])("z=%s → %s", (z, expected) => {
    expect(classifyBand("bmi_for_age", z)).toBe(expected);
  });
});

// ---------------------------------------------------------------------------
// BAND_VOCABULARY — cobertura completa
// ---------------------------------------------------------------------------

describe("BAND_VOCABULARY", () => {
  const statuses = Object.keys(BAND_VOCABULARY) as NutritionalStatus[];

  it("define las 9 claves de NutritionalStatus", () => {
    expect(statuses.sort()).toEqual(
      [
        "adecuado",
        "delgadez",
        "delgadez_severa",
        "obesidad",
        "retraso_talla",
        "riesgo_retraso_talla",
        "sobrepeso",
        "talla_adecuada",
        "talla_alta",
      ].sort(),
    );
  });

  it.each(statuses)("%s tiene coachLabel, familyLabel y narrative no vacíos, y tone válido", (status) => {
    const entry = BAND_VOCABULARY[status];
    expect(entry.coachLabel).toBeTruthy();
    expect(entry.familyLabel).toBeTruthy();
    expect(entry.narrative).toBeTruthy();
    expect(["success", "warning", "danger", "neutral"]).toContain(entry.tone);
    expect(typeof entry.referral).toBe("boolean");
  });

  it("referral es true sólo para las bandas severas (retraso_talla, delgadez_severa, obesidad)", () => {
    const withReferral = statuses.filter((s) => BAND_VOCABULARY[s].referral);
    expect(withReferral.sort()).toEqual(["delgadez_severa", "obesidad", "retraso_talla"].sort());
  });

  it("talla_alta tiene tono neutral (informativo, no clínico)", () => {
    expect(BAND_VOCABULARY.talla_alta.tone).toBe("neutral");
  });
});

// ---------------------------------------------------------------------------
// getBandVocabulary — ajuste de texto para weight_for_age
// ---------------------------------------------------------------------------

describe("getBandVocabulary", () => {
  it("para height_for_age retorna el coachLabel de talla sin ajuste", () => {
    expect(getBandVocabulary("height_for_age", "retraso_talla").coachLabel).toBe("Talla baja");
  });

  it("para weight_for_age sustituye el coachLabel por vocabulario de peso", () => {
    expect(getBandVocabulary("weight_for_age", "retraso_talla").coachLabel).toBe("Peso bajo");
    expect(getBandVocabulary("weight_for_age", "talla_adecuada").coachLabel).toBe("Adecuado");
    expect(getBandVocabulary("weight_for_age", "talla_alta").coachLabel).toBe("Peso muy alto");
  });

  it("para weight_for_age conserva el tone y referral del estado base", () => {
    const base = BAND_VOCABULARY.retraso_talla;
    const weight = getBandVocabulary("weight_for_age", "retraso_talla");
    expect(weight.tone).toBe(base.tone);
    expect(weight.referral).toBe(base.referral);
  });

  it("para bmi_for_age no aplica ajuste (no tiene overrides)", () => {
    expect(getBandVocabulary("bmi_for_age", "sobrepeso").coachLabel).toBe("Sobrepeso");
  });
});

// ---------------------------------------------------------------------------
// getBandSpec — capa de compatibilidad (bandas antiguas + NutritionalStatus)
// ---------------------------------------------------------------------------

describe("getBandSpec — banda antigua de 5 niveles (compatibilidad PercentileCurves)", () => {
  it("height_for_age / ok → Adecuada, verde", () => {
    const spec = getBandSpec("height_for_age", "ok");
    expect(spec.label).toBe("Adecuada");
    expect(spec.color).toBe("green");
  });

  it("height_for_age / watch_high → Adecuada (D2: ya no es una banda separada)", () => {
    const spec = getBandSpec("height_for_age", "watch_high");
    expect(spec.label).toBe("Adecuada");
    expect(spec.color).toBe("green");
  });

  it("height_for_age / high → Talla alta, azul (neutral)", () => {
    const spec = getBandSpec("height_for_age", "high");
    expect(spec.label).toBe("Talla alta");
    expect(spec.color).toBe("blue");
  });

  it("height_for_age / low → Talla baja, rojo (danger)", () => {
    const spec = getBandSpec("height_for_age", "low");
    expect(spec.label).toBe("Talla baja");
    expect(spec.color).toBe("red");
  });

  it("bmi_for_age / low → Delgadez, rojo", () => {
    const spec = getBandSpec("bmi_for_age", "low");
    expect(spec.label).toBe("Delgadez");
    expect(spec.color).toBe("red");
    expect(spec.narrative).not.toBe("");
  });

  it("weight_for_age / high → Peso muy alto (vocabulario de peso, no de talla)", () => {
    const spec = getBandSpec("weight_for_age", "high");
    expect(spec.label).toBe("Peso muy alto");
  });

  it("fallback seguro cuando la combinación no existe en runtime", () => {
    const spec = getBandSpec(
      "height_for_age" as GrowthIndicator,
      "nonexistent_band" as unknown as NutritionalStatus,
    );
    expect(spec.label).toBeTruthy();
    expect(spec.color).toBeTruthy();
    expect(spec.narrative).toBeTruthy();
  });
});

describe("getBandSpec — NutritionalStatus nuevo (usado por useGrowthMetrics)", () => {
  it("acepta directamente una clave NutritionalStatus", () => {
    const spec = getBandSpec("bmi_for_age", "obesidad");
    expect(spec.label).toBe("Obesidad");
    expect(spec.color).toBe("red");
  });

  it("height_for_age / talla_adecuada → Adecuada, verde", () => {
    const spec = getBandSpec("height_for_age", "talla_adecuada");
    expect(spec.label).toBe("Adecuada");
    expect(spec.color).toBe("green");
  });
});
