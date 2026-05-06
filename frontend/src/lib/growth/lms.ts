/**
 * Utilidades LMS oficiales OMS para cálculo de Z-score y percentiles de crecimiento.
 *
 * Fórmulas de referencia:
 *   WHO Child Growth Standards — Methods and development (2006)
 *   https://www.who.int/childgrowth/standards/technical_report/en/
 *
 * Fórmula LMS (Cole & Green, 1992):
 *   Si L ≠ 0 : Z = ((X/M)^L − 1) / (L·S)
 *   Si L = 0 : Z = ln(X/M) / S
 */

// ---------------------------------------------------------------------------
// Tipos públicos
// ---------------------------------------------------------------------------

export interface ReferenceRow {
  /** Edad en meses completos. */
  age: number;
  /** Parámetro de potencia Box-Cox (λ). */
  L: number;
  /** Mediana (μ). */
  M: number;
  /** Coeficiente de variación generalizado (σ). */
  S: number;
  P3: number;
  P10: number;
  P25: number;
  P50: number;
  P75: number;
  P90: number;
  P97: number;
}

export type GrowthIndicator =
  | "height_for_age"
  | "bmi_for_age"
  | "weight_for_age";

// ---------------------------------------------------------------------------
// Funciones públicas
// ---------------------------------------------------------------------------

/**
 * Calcula el Z-score LMS oficial OMS para un valor medido.
 *
 * Si L ≠ 0: Z = ((value/M)^L − 1) / (L·S)
 * Si L = 0: Z = ln(value/M) / S
 *
 * WHO Technical Report Series, p. 300.
 */
export function zScoreFromLMS(value: number, L: number, M: number, S: number): number {
  if (L === 0) {
    return Math.log(value / M) / S;
  }
  return (Math.pow(value / M, L) - 1) / (L * S);
}

/**
 * Convierte un Z-score a percentil entero (1–99) usando la aproximación
 * de la CDF normal estándar por Abramowitz & Stegun (fórmula 26.2.17).
 *
 * El Z se recorta al rango [−3.5, +3.5] antes del cálculo para evitar
 * percentiles fuera del rango clínicamente útil.
 */
export function percentileFromZ(z: number): number {
  const clamped = Math.max(-3.5, Math.min(3.5, z));
  const t = 1 / (1 + 0.2316419 * Math.abs(clamped));
  const poly =
    0.31938153 * t -
    0.356563782 * t * t +
    1.781477937 * t * t * t -
    1.821255978 * t * t * t * t +
    1.330274429 * t * t * t * t * t;
  const pdf = Math.exp(-0.5 * clamped * clamped) / Math.sqrt(2 * Math.PI);
  const cumulative = 1 - pdf * poly;
  const result = clamped >= 0 ? cumulative : 1 - cumulative;
  return Math.max(1, Math.min(99, Math.round(result * 100)));
}

/**
 * Calcula la edad en meses decimales entre dos fechas ISO (yyyy-mm-dd).
 * Usa el mes promedio gregoriano de 30.4375 días (365.25 / 12).
 */
export function ageMonthsFromDates(birthDate: string, evaluationDate: string): number {
  const birth = new Date(birthDate).getTime();
  const evaluation = new Date(evaluationDate).getTime();
  return (evaluation - birth) / (1000 * 60 * 60 * 24 * 30.4375);
}

/**
 * Devuelve la fila de referencia cuya edad (en meses) es la más cercana
 * a `ageMonths`. Si hay empate, devuelve la primera que encuentre.
 * Retorna null si `rows` está vacío.
 */
export function findNearestRow(rows: ReferenceRow[], ageMonths: number): ReferenceRow | null {
  if (rows.length === 0) return null;
  return rows.reduce((best, row) =>
    Math.abs(row.age - ageMonths) < Math.abs(best.age - ageMonths) ? row : best,
  );
}

/**
 * Interpolación lineal de TODOS los campos de una ReferenceRow (L, M, S y P3–P97)
 * entre las dos filas vecinas para la edad dada.
 *
 * Casos borde:
 *   - `rows` vacío → null
 *   - `ageMonths` ≤ primera fila → retorna primera fila sin modificar
 *   - `ageMonths` ≥ última fila → retorna última fila sin modificar
 */
export function interpolateReferenceRow(
  rows: ReferenceRow[],
  ageMonths: number,
): ReferenceRow | null {
  if (rows.length === 0) return null;

  if (ageMonths <= rows[0].age) return { ...rows[0] };
  if (ageMonths >= rows[rows.length - 1].age) return { ...rows[rows.length - 1] };

  for (let i = 0; i < rows.length - 1; i++) {
    const lo = rows[i];
    const hi = rows[i + 1];
    if (ageMonths >= lo.age && ageMonths <= hi.age) {
      const t = (ageMonths - lo.age) / (hi.age - lo.age);
      const lerp = (a: number, b: number): number => a + t * (b - a);
      return {
        age: ageMonths,
        L: lerp(lo.L, hi.L),
        M: lerp(lo.M, hi.M),
        S: lerp(lo.S, hi.S),
        P3: lerp(lo.P3, hi.P3),
        P10: lerp(lo.P10, hi.P10),
        P25: lerp(lo.P25, hi.P25),
        P50: lerp(lo.P50, hi.P50),
        P75: lerp(lo.P75, hi.P75),
        P90: lerp(lo.P90, hi.P90),
        P97: lerp(lo.P97, hi.P97),
      };
    }
  }

  // No debería llegar aquí dado los guards anteriores, pero TypeScript lo requiere.
  return null;
}
