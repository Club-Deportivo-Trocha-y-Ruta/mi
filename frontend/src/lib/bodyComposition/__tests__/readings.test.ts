/**
 * Tests de `lib/bodyComposition/readings.ts`.
 *
 * Usa los mismos fixtures numéricos que
 * `backend/tests/services/test_body_composition.py` (T007) — ver
 * `fixtures.json` en este directorio.
 */
import { describe, it, expect } from "vitest";

import {
  computeSiteValue,
  isPlausible,
  needsThirdReading,
  plausibleRange,
} from "@/lib/bodyComposition/readings";

import fixtures from "./fixtures.json";

describe("computeSiteValue", () => {
  it.each(fixtures.siteValue.meanOfTwo)(
    "promedio de 2 lecturas $readings -> $expected",
    ({ readings, expected }) => {
      expect(computeSiteValue(readings)).toBeCloseTo(expected, 5);
    },
  );

  it.each(fixtures.siteValue.medianOfThree)(
    "mediana de 3 lecturas $readings -> $expected",
    ({ readings, expected }) => {
      expect(computeSiteValue(readings)).toBeCloseTo(expected, 5);
    },
  );

  it("lanza con una cantidad de lecturas inválida", () => {
    expect(() => computeSiteValue([8.0])).toThrow();
    expect(() => computeSiteValue([8.0, 9.0, 9.5, 10.0])).toThrow();
  });
});

describe("needsThirdReading", () => {
  it.each(fixtures.needsThirdReading)(
    "$r1 / $r2 -> $expected",
    ({ r1, r2, expected }) => {
      expect(needsThirdReading(r1, r2)).toBe(expected);
    },
  );
});

describe("plausibleRange / isPlausible", () => {
  it.each(
    Object.entries(fixtures.plausibleRanges9to12) as [string, [number, number]][],
  )("rango 9-12 años de %s es %s", (site, range) => {
    expect(plausibleRange(site as never, 10)).toEqual(range);
  });

  it("suma el incremento de techo para 13-17 años", () => {
    const [min9, max9] = plausibleRange("triceps", 11);
    const [min13, max13] = plausibleRange("triceps", 14);
    expect(min13).toBe(min9);
    expect(max13).toBe(max9 + fixtures.upperBoundIncrement13to17Mm);
  });

  it("isPlausible usa el rango correcto por edad", () => {
    expect(isPlausible("triceps", 10, 30)).toBe(true);
    expect(isPlausible("triceps", 10, 31)).toBe(false);
    expect(isPlausible("triceps", 14, 31)).toBe(true);
    expect(isPlausible("triceps", 14, 41)).toBe(false);
  });
});
