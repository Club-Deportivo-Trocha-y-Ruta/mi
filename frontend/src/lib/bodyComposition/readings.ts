/**
 * Lecturas de pliegue cutáneo: valor por sitio, regla de tercera lectura y
 * rango plausible (feature 046).
 *
 * Réplica exacta de `backend/app/services/body_composition.py`
 * (`site_value`, `needs_third_reading`, `plausible_range`) — mismos
 * fixtures numéricos en `__tests__/fixtures.json`, compartidos con
 * `backend/tests/services/test_body_composition.py` (T007). Cualquier
 * cambio de umbral debe hacerse en ambos lados a la vez.
 *
 * Estas funciones son puras y de sólo lectura de UI: la advertencia de
 * `isPlausible` es informativa (no bloquea el guardado — el rango duro
 * 2.0–60.0 mm ya lo valida `schemas/bodyComposition.schema.ts`).
 */

import type { SkinfoldSite } from "@/types/bodyComposition.types";

/** Tolerancia mínima absoluta, en milímetros (piso del 5 %). */
export const READING_TOLERANCE_MIN_MM = 1.0;
/** Tolerancia relativa: 5 % del promedio de las dos primeras lecturas. */
export const READING_TOLERANCE_PCT = 0.05;

/**
 * Valor de un sitio a partir de sus lecturas: promedio de 2, o mediana de 3
 * (regla ISAK — la tercera lectura descarta el valor atípico sin promediarlo).
 */
export function computeSiteValue(readings: readonly number[]): number {
  if (readings.length === 2) {
    return (readings[0] + readings[1]) / 2;
  }
  if (readings.length === 3) {
    const sorted = [...readings].sort((a, b) => a - b);
    return sorted[1];
  }
  throw new Error(
    `computeSiteValue: se esperaban 2 o 3 lecturas, se recibieron ${readings.length}`,
  );
}

/**
 * Determina si hace falta una tercera lectura: las dos primeras difieren en
 * más que `max(5 % del promedio, 1.0 mm)`. En el límite exacto (`=`) NO hace
 * falta tercera lectura (comparación estricta `>`).
 */
export function needsThirdReading(r1: number, r2: number): boolean {
  const mean = (r1 + r2) / 2;
  const threshold = Math.max(READING_TOLERANCE_PCT * mean, READING_TOLERANCE_MIN_MM);
  return Math.abs(r1 - r2) > threshold;
}

/** Rango plausible (mm) por sitio y banda etaria — advertencia suave, no bloqueante. */
const PLAUSIBLE_RANGES_9_TO_12: Record<SkinfoldSite, [number, number]> = {
  triceps: [4, 30],
  biceps: [2, 20],
  subscapular: [4, 30],
  medial_calf: [4, 30],
  iliac_crest: [4, 40],
  supraspinale: [3, 35],
};

/** 13–17 años: mismo piso, techo +10 mm (data-model.md §4). */
const UPPER_BOUND_INCREMENT_13_TO_17 = 10;

export function plausibleRange(site: SkinfoldSite, ageYears: number): [number, number] {
  const [min, max] = PLAUSIBLE_RANGES_9_TO_12[site];
  if (ageYears >= 13) {
    return [min, max + UPPER_BOUND_INCREMENT_13_TO_17];
  }
  return [min, max];
}

/** true cuando `value` cae dentro del rango plausible del sitio para esa edad. */
export function isPlausible(site: SkinfoldSite, ageYears: number, value: number): boolean {
  const [min, max] = plausibleRange(site, ageYears);
  return value >= min && value <= max;
}
