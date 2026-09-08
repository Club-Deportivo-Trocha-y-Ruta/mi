/**
 * Ventana del eje de edad y ticks para `PercentileChart` (feature 040, T048).
 *
 * Ver research.md R-07: en vez de mostrar siempre el rango completo OMS
 * (5–19 años), el eje X se acota alrededor de las mediciones del deportista
 * (−24 / +36 meses de contexto clínico fijo, FR-011) para que las mediciones
 * ocupen una fracción legible del ancho de la gráfica. SC-008, enmendado el
 * 2026-09-04: ≥ 18 % del ancho y al menos el doble de lo que ocupaban en la
 * gráfica retirada de rango completo — medido en `window.test.ts` (18.9 % vs
 * 8.4 %, 2.26×). El toggle "Ver 5–19 años" del `PercentileToolbar` vuelve al
 * rango completo.
 */

import type { ReferenceRow } from "@/lib/growth/lms";

/** Límite inferior del set de referencia OMS 5–19 años (60 meses + medio mes). */
export const AGE_WINDOW_MIN_MONTHS = 61.5;
/** Límite superior del set de referencia OMS 5–19 años (19 años + medio mes). */
export const AGE_WINDOW_MAX_MONTHS = 228.5;
/** Meses que se agregan antes de la primera medición en modo 'auto'. */
export const AGE_WINDOW_PAD_BEFORE_MONTHS = 24;
/** Meses que se agregan después de la última medición en modo 'auto'. */
export const AGE_WINDOW_PAD_AFTER_MONTHS = 36;

/** Cantidad de marcas objetivo por defecto para `niceTicks`. */
const DEFAULT_NICE_TICK_COUNT = 5;
/** Pasos "redondos" permitidos para el eje Y, escalados por potencias de 10. */
const NICE_STEP_MULTIPLES = [1, 2, 5, 10] as const;

/**
 * `"auto"`: ventana −24/+36 meses alrededor de las mediciones (copy del
 * toolbar: "Ver alrededor de las mediciones", default).
 * `"full"`: rango OMS completo 5–19 años (copy: "Ver 5–19 años").
 */
export type AgeWindowRange = "auto" | "full";

/**
 * Calcula `[min, max]` en meses para el dominio numérico del `XAxis`.
 *
 * En modo `"auto"`, la ventana es `[primeraEdad − 24, últimaEdad + 36]`
 * (min/max de `recordAgesMonths`, sin importar el orden de entrada),
 * recortada a `[AGE_WINDOW_MIN_MONTHS, AGE_WINDOW_MAX_MONTHS]`. Sin
 * mediciones, o si el recorte deja `min > max` (edades muy fuera del rango
 * OMS), cae de vuelta al rango completo en lugar de producir un dominio
 * inválido para el chart.
 */
export function computeAgeWindow(
  recordAgesMonths: readonly number[],
  range: AgeWindowRange,
): [number, number] {
  const fullRange: [number, number] = [AGE_WINDOW_MIN_MONTHS, AGE_WINDOW_MAX_MONTHS];

  if (range === "full" || recordAgesMonths.length === 0) {
    return fullRange;
  }

  const firstAge = Math.min(...recordAgesMonths);
  const lastAge = Math.max(...recordAgesMonths);

  const windowMin = Math.max(AGE_WINDOW_MIN_MONTHS, firstAge - AGE_WINDOW_PAD_BEFORE_MONTHS);
  const windowMax = Math.min(AGE_WINDOW_MAX_MONTHS, lastAge + AGE_WINDOW_PAD_AFTER_MONTHS);

  if (windowMin > windowMax) {
    return fullRange;
  }

  return [windowMin, windowMax];
}

/**
 * Ticks del eje X en años completos (múltiplos de 12 meses) dentro de
 * `[min, max]`, ambos extremos inclusive.
 */
export function yearTicks(min: number, max: number): number[] {
  const ticks: number[] = [];
  const firstYear = Math.ceil(min / 12) * 12;
  for (let months = firstYear; months <= max; months += 12) {
    ticks.push(months);
  }
  return ticks;
}

/**
 * Ticks "redondos" del eje Y entre `min` y `max`, con paso igual a
 * `1`, `2`, `5` o `10` multiplicado por una potencia de 10, elegido para
 * acercarse a `targetCount` marcas. Los extremos del arreglo cubren
 * `[min, max]` (pueden quedar levemente por fuera para que el paso sea
 * "redondo").
 */
export function niceTicks(
  min: number,
  max: number,
  targetCount: number = DEFAULT_NICE_TICK_COUNT,
): number[] {
  if (min === max) return [min];

  const range = max - min;
  const rawStep = range / Math.max(1, targetCount);
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const normalizedStep = rawStep / magnitude;
  const niceMultiple =
    NICE_STEP_MULTIPLES.find((multiple) => multiple >= normalizedStep) ??
    NICE_STEP_MULTIPLES[NICE_STEP_MULTIPLES.length - 1];
  const step = niceMultiple * magnitude;

  const start = Math.floor(min / step) * step;
  const end = Math.ceil(max / step) * step;

  const ticks: number[] = [];
  // Margen de tolerancia para errores de punto flotante al acumular `step`.
  const epsilon = step * 1e-9;
  for (let value = start; value <= end + epsilon; value += step) {
    ticks.push(Number(value.toFixed(6)));
  }
  return ticks;
}

/**
 * Filtra filas de referencia OMS (ordenadas o no por `age`) a las que caen
 * dentro de `[min, max]`, agregando una fila extra inmediatamente antes del
 * borde inferior y una inmediatamente después del borde superior — así la
 * línea/banda no se corta de forma abrupta en el límite de la ventana.
 *
 * Si ninguna fila cae dentro de la ventana (ventana más angosta que el paso
 * entre filas), devuelve las filas que la bordean por fuera para que la
 * ventana siga teniendo algo que interpolar/dibujar.
 */
export function filterReferenceRows<T extends Pick<ReferenceRow, "age">>(
  rows: readonly T[],
  min: number,
  max: number,
): T[] {
  if (rows.length === 0) return [];

  const sorted = [...rows].sort((a, b) => a.age - b.age);

  let firstInside = -1;
  let lastInside = -1;
  for (let i = 0; i < sorted.length; i++) {
    if (sorted[i].age >= min && sorted[i].age <= max) {
      if (firstInside === -1) firstInside = i;
      lastInside = i;
    }
  }

  if (firstInside === -1) {
    const closestBefore = [...sorted].reverse().find((row) => row.age < min);
    const closestAfter = sorted.find((row) => row.age > max);
    return [closestBefore, closestAfter].filter((row): row is T => row !== undefined);
  }

  const from = firstInside > 0 ? firstInside - 1 : firstInside;
  const to = lastInside < sorted.length - 1 ? lastInside + 1 : lastInside;
  return sorted.slice(from, to + 1);
}
