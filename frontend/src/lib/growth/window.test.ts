/**
 * Tests de `lib/growth/window.ts` (feature 040, T046).
 *
 * Cubre R-07 (research.md): ventana de edad −24/+36 meses alrededor de las
 * mediciones, clamp a 61.5–228.5 (rango OMS 5–19 años), el toggle a rango
 * completo, ticks de eje X en años enteros, `niceTicks` con pasos 1/2/5/10 y
 * el filtrado de filas de referencia con una fila extra a cada lado para que
 * la línea no se corte de forma abrupta en el borde de la ventana.
 */

import { describe, expect, it } from "vitest";

import {
  AGE_WINDOW_MAX_MONTHS,
  AGE_WINDOW_MIN_MONTHS,
  computeAgeWindow,
  filterReferenceRows,
  niceTicks,
  yearTicks,
} from "@/lib/growth/window";

describe("computeAgeWindow", () => {
  it("aplica −24/+36 meses alrededor del rango de mediciones en modo 'auto'", () => {
    expect(computeAgeWindow([100, 120], "auto")).toEqual([76, 156]);
  });

  it("usa una sola edad como min y max de las mediciones", () => {
    expect(computeAgeWindow([90], "auto")).toEqual([66, 126]);
  });

  it("hace clamp del límite inferior a 61.5 meses cuando la resta se sale del rango OMS", () => {
    expect(computeAgeWindow([80, 100], "auto")).toEqual([AGE_WINDOW_MIN_MONTHS, 136]);
  });

  it("hace clamp del límite superior a 228.5 meses cuando la suma se sale del rango OMS", () => {
    expect(computeAgeWindow([200, 220], "auto")).toEqual([176, AGE_WINDOW_MAX_MONTHS]);
  });

  it("no depende del orden de las edades de entrada", () => {
    expect(computeAgeWindow([120, 100], "auto")).toEqual([76, 156]);
  });

  it("con range='full' siempre devuelve el rango OMS completo, con o sin mediciones", () => {
    expect(computeAgeWindow([100, 120], "full")).toEqual([
      AGE_WINDOW_MIN_MONTHS,
      AGE_WINDOW_MAX_MONTHS,
    ]);
    expect(computeAgeWindow([], "full")).toEqual([AGE_WINDOW_MIN_MONTHS, AGE_WINDOW_MAX_MONTHS]);
  });

  it("sin mediciones y range='auto' cae de vuelta al rango completo", () => {
    expect(computeAgeWindow([], "auto")).toEqual([AGE_WINDOW_MIN_MONTHS, AGE_WINDOW_MAX_MONTHS]);
  });

  it("es defensivo ante edades muy fuera del rango OMS (min > max tras el padding)", () => {
    // 300 − 24 = 276 (> 228.5) y 300 + 36 = 336 → clamp deja min > max;
    // el helper debe caer de vuelta al rango completo en vez de romper el chart.
    expect(computeAgeWindow([300, 300], "auto")).toEqual([
      AGE_WINDOW_MIN_MONTHS,
      AGE_WINDOW_MAX_MONTHS,
    ]);
  });
});

describe("yearTicks", () => {
  it("devuelve los múltiplos de 12 (años completos) dentro de la ventana, incluyendo los extremos exactos", () => {
    expect(yearTicks(60, 84)).toEqual([60, 72, 84]);
  });

  it("excluye el múltiplo de 12 inmediatamente anterior al mínimo cuando no coincide exacto", () => {
    expect(yearTicks(61.5, 228.5)).toEqual([
      72, 84, 96, 108, 120, 132, 144, 156, 168, 180, 192, 204, 216, 228,
    ]);
  });

  it("funciona sobre una ventana angosta 'auto' típica", () => {
    expect(yearTicks(76, 156)).toEqual([84, 96, 108, 120, 132, 144, 156]);
  });

  it("devuelve arreglo vacío cuando la ventana no contiene ningún múltiplo de 12", () => {
    expect(yearTicks(61, 71)).toEqual([]);
  });
});

describe("niceTicks", () => {
  it("elige paso 20 (escala del paso base 2) para un rango de talla típico", () => {
    expect(niceTicks(90, 190)).toEqual([80, 100, 120, 140, 160, 180, 200]);
  });

  it("elige paso 5 para un rango de IMC típico", () => {
    expect(niceTicks(14, 26)).toEqual([10, 15, 20, 25, 30]);
  });

  it("elige paso 10 para un rango de peso", () => {
    expect(niceTicks(15, 55)).toEqual([10, 20, 30, 40, 50, 60]);
  });

  it("elige paso 1 para un rango pequeño", () => {
    expect(niceTicks(2, 6, 4)).toEqual([2, 3, 4, 5, 6]);
  });

  it("respeta el targetCount al elegir la magnitud del paso", () => {
    // Mismo rango que el caso de talla, pero pidiendo menos marcas → paso mayor.
    expect(niceTicks(90, 190, 2)).toEqual([50, 100, 150, 200]);
  });

  it("devuelve un único valor cuando min === max", () => {
    expect(niceTicks(50, 50)).toEqual([50]);
  });

  it("todo paso generado es 1, 2, 5 o 10 multiplicado por una potencia de 10", () => {
    const ticks = niceTicks(3.2, 47.9);
    const step = ticks[1] - ticks[0];
    for (let i = 2; i < ticks.length; i++) {
      expect(ticks[i] - ticks[i - 1]).toBeCloseTo(step, 9);
    }
    const magnitude = Math.pow(10, Math.floor(Math.log10(step)));
    const normalized = Number((step / magnitude).toFixed(6));
    expect([1, 2, 5, 10]).toContain(normalized);
  });
});

describe("filterReferenceRows", () => {
  const rows = [60, 66, 72, 78, 84, 90].map((age) => ({ age }));

  it("mantiene las filas dentro de la ventana más una fila extra a cada lado", () => {
    expect(filterReferenceRows(rows, 72, 78)).toEqual([
      { age: 66 },
      { age: 72 },
      { age: 78 },
      { age: 84 },
    ]);
  });

  it("no agrega fila extra del lado en el que la ventana ya toca el borde del set", () => {
    expect(filterReferenceRows(rows, 60, 66)).toEqual([{ age: 60 }, { age: 66 }, { age: 72 }]);
    expect(filterReferenceRows(rows, 84, 90)).toEqual([{ age: 78 }, { age: 84 }, { age: 90 }]);
  });

  it("no depende de que las filas de entrada ya vengan ordenadas", () => {
    const shuffled = [{ age: 90 }, { age: 66 }, { age: 60 }, { age: 84 }, { age: 78 }, { age: 72 }];
    expect(filterReferenceRows(shuffled, 72, 78)).toEqual([
      { age: 66 },
      { age: 72 },
      { age: 78 },
      { age: 84 },
    ]);
  });

  it("devuelve arreglo vacío cuando no hay filas de entrada", () => {
    expect(filterReferenceRows([], 72, 78)).toEqual([]);
  });

  it("cuando ninguna fila cae dentro de la ventana, devuelve las filas que la bordean", () => {
    expect(filterReferenceRows(rows, 73, 74)).toEqual([{ age: 72 }, { age: 78 }]);
  });
});

/**
 * SC-008 (feature 040, T055) — medición del criterio de legibilidad,
 * enmendado el 2026-09-04 en `spec.md`: sobre un fixture de TRES mediciones
 * en 14 meses, las mediciones deben ocupar ≥ 18 % del ancho de la curva y
 * al menos el DOBLE de lo que ocupaban en la gráfica retirada (rango OMS
 * completo 5–19 años), y dos mediciones consecutivas deben quedar a ≥ 60 px
 * en un viewport de 1024 px.
 *
 * La cifra original ("≥ 60 % del ancho") era inalcanzable bajo FR-011 para
 * cualquier edad: el padding fijo de −24/+36 meses ya suma 60 meses de
 * contexto clínico, así que 14 meses de mediciones nunca pueden pasar de
 * 14/74 ≈ 19 % sin romper ese padding.
 *
 * Geometría del plot usada para los píxeles (conservadora, de
 * `PercentileChart.tsx`): viewport 1024 − 48 (padding horizontal de página)
 * − 40 (padding de la tarjeta) = 936 px de contenedor; menos el margen
 * `left: 8` + `right: 24` del `ComposedChart` y el `width={40}` del
 * `YAxis` ⇒ 864 px de área de trazado.
 */
describe("SC-008 — legibilidad de la ventana por defecto", () => {
  /** Tres mediciones ficticias separadas 7 meses (14 meses en total). */
  const RECORD_AGES_MONTHS = [144, 151, 158];
  const MEASUREMENT_SPAN_MONTHS = 158 - 144;
  const CONSECUTIVE_GAP_MONTHS = 7;
  const VIEWPORT_PX = 1024;
  const PLOT_WIDTH_PX = VIEWPORT_PX - 48 - 40 - (8 + 24 + 40);

  const widthOf = ([min, max]: [number, number]) => max - min;

  const autoWidth = widthOf(computeAgeWindow(RECORD_AGES_MONTHS, "auto"));
  const fullWidth = widthOf(computeAgeWindow(RECORD_AGES_MONTHS, "full"));
  const autoShare = MEASUREMENT_SPAN_MONTHS / autoWidth;
  const fullShare = MEASUREMENT_SPAN_MONTHS / fullWidth;

  it("las mediciones ocupan ≥ 18 % del ancho de la ventana por defecto", () => {
    expect(autoWidth).toBe(74); // [120, 194] meses
    expect(autoShare).toBeGreaterThanOrEqual(0.18);
  });

  it("ocupan al menos el doble que en la gráfica retirada (rango completo)", () => {
    expect(fullWidth).toBe(167); // [61.5, 228.5] meses
    expect(fullShare).toBeLessThan(0.09);
    expect(autoShare / fullShare).toBeGreaterThanOrEqual(2);
  });

  it("dos mediciones consecutivas quedan a ≥ 60 px en un viewport de 1024 px", () => {
    const gapPx = (CONSECUTIVE_GAP_MONTHS / autoWidth) * PLOT_WIDTH_PX;
    expect(gapPx).toBeGreaterThanOrEqual(60);
  });

  it("el toggle 'Ver 5–19 años' restituye el rango completo de referencia", () => {
    expect(computeAgeWindow(RECORD_AGES_MONTHS, "full")).toEqual([
      AGE_WINDOW_MIN_MONTHS,
      AGE_WINDOW_MAX_MONTHS,
    ]);
  });
});
