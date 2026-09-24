/**
 * Métricas graficables de la progresión histórica (feature 045, T036).
 *
 * Vive fuera de `HistoryChart.tsx` a propósito: el selector de métrica de
 * «Carreras › Progresión» necesita estas etiquetas sin arrastrar recharts
 * (la gráfica es un chunk lazy).
 *
 * Reglas de audiencia (Ley 1581 + salvaguarda de la 045): las métricas que
 * comparan contra el líder o el podio son SOLO para coach — la familia
 * únicamente ve mediana, percentil y posición. Las claves de líder/podio ni
 * siquiera llegan en el payload de familia (ver `LEADER_GAP_METRIC_KEYS`).
 */
import {
  formatGapPct,
  formatPercentile,
  formatPosition,
} from "@/lib/raceHistoryFormat";
import type { RaceHistoryPoint } from "@/types/raceHistory.types";

export type HistoryMetric =
  | "gap_to_median_pct"
  | "percentile"
  | "position"
  | "gap_to_winner_pct"
  | "gap_to_podium_pct";

export type HistoryAudience = "coach" | "family";

export const DEFAULT_HISTORY_METRIC: HistoryMetric = "gap_to_median_pct";

export interface HistoryMetricConfig {
  /** Etiqueta del glosario (`contracts/ui-copy.md`). */
  label: string;
  /** `true` = menor es mejor → eje Y invertido (arriba = mejor). */
  lowerIsBetter: boolean;
  /** Solo coach: compara contra líder/podio. */
  coachOnly: boolean;
  /** Línea de referencia en 0, si la métrica es una brecha firmada. */
  referenceLabel: string | null;
  /** Pista de lectura del eje. */
  axisHint: string;
  format: (value: number | null) => string;
  /** Formato de las marcas del eje Y. */
  formatTick: (value: number) => string;
  /** Dominio fijo (percentil 0–100); `null` = se calcula de los datos. */
  fixedDomain: [number, number] | null;
  /** Eje de enteros ≥ 1 (posición): el dominio calculado se redondea. */
  integerAxis: boolean;
  /** Valor de la métrica en un punto (`null` = sin dato / no aplica). */
  select: (point: RaceHistoryPoint) => number | null;
}

/** `p.gap_*` solo existe en la variante de coach — ver `RaceHistoryPoint`. */
function leaderGap(
  point: RaceHistoryPoint,
  key: "gap_to_winner_pct" | "gap_to_podium_pct",
): number | null {
  return key in point
    ? ((point as Record<typeof key, number | null>)[key] ?? null)
    : null;
}

const round1 = (v: number) => `${Math.round(v * 10) / 10} %`;

export const HISTORY_METRICS: Record<HistoryMetric, HistoryMetricConfig> = {
  gap_to_median_pct: {
    label: "Brecha vs. mediana",
    lowerIsBetter: true,
    coachOnly: false,
    referenceLabel: "Mediana de su categoría",
    axisHint: "Más rápido que la mediana ↑ · Más lento ↓",
    format: formatGapPct,
    formatTick: round1,
    fixedDomain: null,
    integerAxis: false,
    select: (p) => p.gap_to_median_pct,
  },
  percentile: {
    label: "Percentil",
    lowerIsBetter: false,
    coachOnly: false,
    referenceLabel: null,
    axisHint: "Más rápido dentro de su categoría ↑ · Más lento ↓",
    format: formatPercentile,
    formatTick: (v) => `P${Math.round(v)}`,
    fixedDomain: [0, 100],
    integerAxis: false,
    select: (p) => p.percentile,
  },
  position: {
    label: "Posición",
    lowerIsBetter: true,
    coachOnly: false,
    referenceLabel: null,
    axisHint: "Mejor posición ↑ · Peor posición ↓",
    format: formatPosition,
    formatTick: (v) => `${Math.round(v)}°`,
    fixedDomain: null,
    integerAxis: true,
    select: (p) => p.position,
  },
  gap_to_winner_pct: {
    label: "Brecha vs. 1.ª posición",
    lowerIsBetter: true,
    coachOnly: true,
    referenceLabel: "1.ª posición",
    axisHint: "Más cerca de la 1.ª posición ↑ · Más lejos ↓",
    format: formatGapPct,
    formatTick: round1,
    fixedDomain: null,
    integerAxis: false,
    select: (p) => leaderGap(p, "gap_to_winner_pct"),
  },
  gap_to_podium_pct: {
    label: "Brecha vs. podio",
    lowerIsBetter: true,
    coachOnly: true,
    referenceLabel: "Podio",
    axisHint: "Más cerca del podio ↑ · Más lejos ↓",
    format: formatGapPct,
    formatTick: round1,
    fixedDomain: null,
    integerAxis: false,
    select: (p) => leaderGap(p, "gap_to_podium_pct"),
  },
};

const METRIC_ORDER: readonly HistoryMetric[] = [
  "gap_to_median_pct",
  "percentile",
  "position",
  "gap_to_winner_pct",
  "gap_to_podium_pct",
];

/** Métricas ofrecidas a una audiencia, en orden de presentación. */
export function historyMetricsFor(audience: HistoryAudience): HistoryMetric[] {
  return METRIC_ORDER.filter(
    (m) => audience === "coach" || !HISTORY_METRICS[m].coachOnly,
  );
}

/** Una métrica solo-coach pedida por la familia cae en la mediana. */
export function resolveHistoryMetric(
  metric: HistoryMetric,
  audience: HistoryAudience,
): HistoryMetric {
  return historyMetricsFor(audience).includes(metric)
    ? metric
    : DEFAULT_HISTORY_METRIC;
}
