import { describe, expect, it } from "vitest";

import {
  ageMonthsFromDates,
  findNearestRow,
  interpolateReferenceRow,
  percentileFromZ,
  type ReferenceRow,
  zScoreFromLMS,
} from "./lms";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRow(overrides: Partial<ReferenceRow> & { age: number }): ReferenceRow {
  return {
    L: 1,
    M: 100,
    S: 0.1,
    P3: 80,
    P10: 87,
    P25: 94,
    P50: 100,
    P75: 106,
    P90: 113,
    P97: 120,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// zScoreFromLMS
// ---------------------------------------------------------------------------

describe("zScoreFromLMS", () => {
  it("usa la fórmula logarítmica cuando L=0", () => {
    // Z = ln(value / M) / S
    const z = zScoreFromLMS(110, 0, 100, 0.1);
    const expected = Math.log(110 / 100) / 0.1;
    expect(z).toBeCloseTo(expected, 6);
  });

  it("usa la fórmula de potencia cuando L≠0", () => {
    // Z = ((value/M)^L − 1) / (L·S)
    const z = zScoreFromLMS(110, 1, 100, 0.1);
    const expected = (Math.pow(110 / 100, 1) - 1) / (1 * 0.1);
    expect(z).toBeCloseTo(expected, 6);
  });

  it("valor de referencia OMS talla varón ~11 años (L≈0.1, M≈143.5, S≈0.045), valor 140 cm → Z ≈ -0.5 ± 0.05", () => {
    // Fila aproximada OMS height-for-age boys 132 meses
    const z = zScoreFromLMS(140, 0.1, 143.5, 0.045);
    expect(z).toBeGreaterThan(-0.55);
    expect(z).toBeLessThan(-0.45);
  });

  it("devuelve Z=0 cuando value=M con L≠0", () => {
    expect(zScoreFromLMS(100, 1, 100, 0.1)).toBeCloseTo(0, 8);
  });

  it("devuelve Z=0 cuando value=M con L=0", () => {
    expect(zScoreFromLMS(100, 0, 100, 0.1)).toBeCloseTo(0, 8);
  });
});

// ---------------------------------------------------------------------------
// percentileFromZ
// ---------------------------------------------------------------------------

describe("percentileFromZ", () => {
  it("Z=0 devuelve percentil 50", () => {
    expect(percentileFromZ(0)).toBe(50);
  });

  it("Z=-1.881 devuelve P3 (tolerancia ±1)", () => {
    const p = percentileFromZ(-1.881);
    expect(p).toBeGreaterThanOrEqual(2);
    expect(p).toBeLessThanOrEqual(4);
  });

  it("Z=+1.881 devuelve P97 (tolerancia ±1)", () => {
    const p = percentileFromZ(1.881);
    expect(p).toBeGreaterThanOrEqual(96);
    expect(p).toBeLessThanOrEqual(98);
  });

  it("Z=-3 (extremo negativo) devuelve percentil ≥ 1", () => {
    expect(percentileFromZ(-3)).toBeGreaterThanOrEqual(1);
  });

  it("Z=+3 (extremo positivo) devuelve percentil ≤ 99", () => {
    expect(percentileFromZ(3)).toBeLessThanOrEqual(99);
  });

  it("Z muy negativo (<-3.5) está recortado — sigue devolviendo 1", () => {
    expect(percentileFromZ(-10)).toBe(1);
  });

  it("Z muy positivo (>3.5) está recortado — sigue devolviendo 99", () => {
    expect(percentileFromZ(10)).toBe(99);
  });
});

// ---------------------------------------------------------------------------
// ageMonthsFromDates
// ---------------------------------------------------------------------------

describe("ageMonthsFromDates", () => {
  it("nacimiento 2014-05-01 a evaluación 2026-05-01 → ~144 meses", () => {
    const months = ageMonthsFromDates("2014-05-01", "2026-05-01");
    // 12 años × 12 = 144. Tolerancia ±0.5 por variación de días bisiestos.
    expect(months).toBeGreaterThan(143.5);
    expect(months).toBeLessThan(144.5);
  });

  it("misma fecha → 0 meses", () => {
    expect(ageMonthsFromDates("2020-01-01", "2020-01-01")).toBeCloseTo(0, 6);
  });

  it("exactamente 1 mes (30.4375 días) → ~1 mes", () => {
    const birth = new Date("2020-01-01");
    const evalDate = new Date(birth.getTime() + 30.4375 * 24 * 60 * 60 * 1000);
    const result = ageMonthsFromDates("2020-01-01", evalDate.toISOString().split("T")[0]);
    expect(result).toBeCloseTo(1, 1);
  });
});

// ---------------------------------------------------------------------------
// findNearestRow
// ---------------------------------------------------------------------------

describe("findNearestRow", () => {
  const rows: ReferenceRow[] = [
    makeRow({ age: 120 }),
    makeRow({ age: 130 }),
    makeRow({ age: 140 }),
  ];

  it("retorna null para array vacío", () => {
    expect(findNearestRow([], 125)).toBeNull();
  });

  it("ageMonths 134 → fila 130 (más cercana)", () => {
    // Distancias: |120-134|=14, |130-134|=4, |140-134|=6 → ganadora: 130
    const row = findNearestRow(rows, 134);
    expect(row?.age).toBe(130);
  });

  it("ageMonths 120 → fila 120 (match exacto)", () => {
    expect(findNearestRow(rows, 120)?.age).toBe(120);
  });

  it("ageMonths 140 → fila 140 (match exacto)", () => {
    expect(findNearestRow(rows, 140)?.age).toBe(140);
  });

  it("ageMonths 100 (fuera de rango inferior) → fila 120", () => {
    expect(findNearestRow(rows, 100)?.age).toBe(120);
  });

  it("ageMonths 200 (fuera de rango superior) → fila 140", () => {
    expect(findNearestRow(rows, 200)?.age).toBe(140);
  });
});

// ---------------------------------------------------------------------------
// interpolateReferenceRow
// ---------------------------------------------------------------------------

describe("interpolateReferenceRow", () => {
  const rowA = makeRow({
    age: 100,
    L: 0.2,
    M: 100,
    S: 0.04,
    P3: 80,
    P10: 86,
    P25: 93,
    P50: 100,
    P75: 107,
    P90: 114,
    P97: 120,
  });
  const rowB = makeRow({
    age: 120,
    L: 0.4,
    M: 110,
    S: 0.06,
    P3: 88,
    P10: 95,
    P25: 102,
    P50: 110,
    P75: 118,
    P90: 125,
    P97: 132,
  });

  it("retorna null para array vacío", () => {
    expect(interpolateReferenceRow([], 110)).toBeNull();
  });

  it("ageMonths exacto en rowA → devuelve rowA sin modificar", () => {
    const result = interpolateReferenceRow([rowA, rowB], 100);
    expect(result).not.toBeNull();
    expect(result!.age).toBeCloseTo(100, 6);
    expect(result!.M).toBeCloseTo(rowA.M, 6);
    expect(result!.P50).toBeCloseTo(rowA.P50, 6);
  });

  it("ageMonths exacto en rowB → devuelve rowB sin modificar", () => {
    const result = interpolateReferenceRow([rowA, rowB], 120);
    expect(result).not.toBeNull();
    expect(result!.M).toBeCloseTo(rowB.M, 6);
  });

  it("punto medio (ageMonths=110) → interpolación lineal exacta de todos los campos", () => {
    const result = interpolateReferenceRow([rowA, rowB], 110);
    expect(result).not.toBeNull();
    // t = (110-100)/(120-100) = 0.5 → cada campo es promedio exacto
    expect(result!.L).toBeCloseTo((rowA.L + rowB.L) / 2, 8);
    expect(result!.M).toBeCloseTo((rowA.M + rowB.M) / 2, 8);
    expect(result!.S).toBeCloseTo((rowA.S + rowB.S) / 2, 8);
    expect(result!.P3).toBeCloseTo((rowA.P3 + rowB.P3) / 2, 8);
    expect(result!.P10).toBeCloseTo((rowA.P10 + rowB.P10) / 2, 8);
    expect(result!.P25).toBeCloseTo((rowA.P25 + rowB.P25) / 2, 8);
    expect(result!.P50).toBeCloseTo((rowA.P50 + rowB.P50) / 2, 8);
    expect(result!.P75).toBeCloseTo((rowA.P75 + rowB.P75) / 2, 8);
    expect(result!.P90).toBeCloseTo((rowA.P90 + rowB.P90) / 2, 8);
    expect(result!.P97).toBeCloseTo((rowA.P97 + rowB.P97) / 2, 8);
  });

  it("ageMonths menor que primera fila → retorna primera fila", () => {
    const result = interpolateReferenceRow([rowA, rowB], 50);
    expect(result).not.toBeNull();
    expect(result!.M).toBeCloseTo(rowA.M, 8);
    expect(result!.age).toBe(rowA.age);
  });

  it("ageMonths mayor que última fila → retorna última fila", () => {
    const result = interpolateReferenceRow([rowA, rowB], 200);
    expect(result).not.toBeNull();
    expect(result!.M).toBeCloseTo(rowB.M, 8);
    expect(result!.age).toBe(rowB.age);
  });

  it("interpolación no-simétrica (t=0.25) respeta la fórmula lineal", () => {
    // ageMonths=105 → t=(105-100)/(120-100)=0.25
    const result = interpolateReferenceRow([rowA, rowB], 105);
    expect(result).not.toBeNull();
    const expectedM = rowA.M + 0.25 * (rowB.M - rowA.M);
    expect(result!.M).toBeCloseTo(expectedM, 8);
  });
});
