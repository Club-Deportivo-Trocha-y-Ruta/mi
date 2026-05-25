/**
 * percentileChart — funciones puras para construir el ChartRow consumido
 * por <ComposedChart> de recharts en PercentileCurves.
 *
 * Separado del componente en B5 para:
 *  - aislar lógica testeable (sin recharts).
 *  - permitir reuso en otros visualizadores (sr-only table, exports, etc).
 *  - mantener PercentileCurves bajo 500 LOC.
 */
import growthData from "@/data/growth-reference-who.json";
import { getBandSpec } from "@/lib/growth/bands";
import {
  interpolateReferenceRow,
  percentileFromZ,
  zScoreFromLMS,
  type ReferenceRow,
} from "@/lib/growth/lms";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { GrowthBand } from "@/hooks/athletes/useGrowthMetrics";

export type GrowthIndicator =
  | "height_for_age"
  | "bmi_for_age"
  | "weight_for_age";

export interface ChartRow {
  age_months: number;
  L: number;
  M: number;
  S: number;
  P3: number;
  P10: number;
  P25: number;
  P50: number;
  P75: number;
  P90: number;
  P97: number;
  athleteValue: number | null;
  evaluationDate: string | null;
  // Bandas de color de fondo — cada valor es un tuple [lower, upper] que
  // recharts interpreta como rango cuando dataKey retorna un array de 2 números.
  band_low?: [number, number];
  band_watch?: [number, number];
  band_ok?: [number, number];
  band_high?: [number, number];
  // Extras para bmi_for_age (5 bandas)
  band_obesity?: [number, number];
  band_overweight?: [number, number];
}

export interface TooltipPayloadItem {
  dataKey: string;
  value: number | null;
  payload: ChartRow;
}

export interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: number;
}

// ---------------------------------------------------------------------------
// Constantes públicas
// ---------------------------------------------------------------------------

export const INDICATOR_LABELS: Record<GrowthIndicator, string> = {
  height_for_age: "Talla (cm)",
  bmi_for_age: "IMC (kg/m²)",
  weight_for_age: "Peso (kg)",
};

// Notas pie de gráfica por indicador. Aclaran el significado clínico de la línea
// vertical de maduración para evitar lecturas erróneas (p. ej. interpretar subida
// de IMC peri-PHV como adiposidad cuando refleja masa magra).
export const INDICATOR_PHV_NOTES: Record<GrowthIndicator, string> = {
  height_for_age: "Línea PHV: edad estimada del pico de velocidad de talla (Mirwald).",
  bmi_for_age:
    "Subida del IMC alrededor del PHV refleja aumento de masa magra, no adiposidad.",
  weight_for_age:
    "Pico de velocidad de peso (PWV) coincide con PHV en hombres y se retrasa ~6 meses en mujeres.",
};

export const LEGEND_ORDER = [
  "athleteValue",
  "P50",
  "P25",
  "P75",
  "P10",
  "P90",
  "P3",
  "P97",
] as const;

export type LegendOrderKey = (typeof LEGEND_ORDER)[number];

export interface BandConfig {
  /** dataKey del Area en ComposedChart */
  key: string;
  fill: string;
  fillOpacity: number;
}

export const BAND_CONFIGS: Record<GrowthIndicator, BandConfig[]> = {
  height_for_age: [
    { key: "band_low",   fill: "#ea580c", fillOpacity: 0.10 },
    { key: "band_watch", fill: "#ca8a04", fillOpacity: 0.10 },
    { key: "band_ok",    fill: "#16a34a", fillOpacity: 0.08 },
    { key: "band_high",  fill: "#2563eb", fillOpacity: 0.08 },
  ],
  bmi_for_age: [
    { key: "band_low",        fill: "#dc2626", fillOpacity: 0.10 },
    { key: "band_watch",      fill: "#ea580c", fillOpacity: 0.10 },
    { key: "band_ok",         fill: "#16a34a", fillOpacity: 0.08 },
    { key: "band_overweight", fill: "#ca8a04", fillOpacity: 0.10 },
    { key: "band_obesity",    fill: "#dc2626", fillOpacity: 0.10 },
  ],
  weight_for_age: [
    { key: "band_low",   fill: "#ea580c", fillOpacity: 0.10 },
    { key: "band_watch", fill: "#ca8a04", fillOpacity: 0.10 },
    { key: "band_ok",    fill: "#16a34a", fillOpacity: 0.08 },
    { key: "band_high",  fill: "#2563eb", fillOpacity: 0.08 },
  ],
};

/** Conjunto de keys usados como bandas — para excluirlos de la leyenda */
export const ALL_BAND_KEYS = new Set<string>([
  "band_low", "band_watch", "band_ok", "band_high",
  "band_overweight", "band_obesity",
]);

// Colores de banda para el dot en el tooltip
export const BAND_DOT_COLORS: Record<GrowthBand, string> = {
  low: "#ea580c",
  watch_low: "#ca8a04",
  ok: "#16a34a",
  watch_high: "#2563eb",
  high: "#2563eb",
};

const MONTH_NAMES_ES = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

// ---------------------------------------------------------------------------
// Marker de maduración
// ---------------------------------------------------------------------------

export interface MaturationMarker {
  ageMonths: number;
  label: string;
}

// Dada la edad PHV en meses, indicador y sexo, calcula la línea vertical apropiada:
// — Talla / IMC: línea en PHV.
// — Peso ♂: PWV coincide con PHV → línea en PHV con etiqueta "PHV/PWV".
// — Peso ♀: PWV ~6 meses post-PHV → línea desplazada con etiqueta "PWV".
export function getMaturationMarker(
  indicator: GrowthIndicator,
  sex: "M" | "F",
  phvAgeMonths: number | undefined,
): MaturationMarker | null {
  if (phvAgeMonths === undefined) return null;
  if (indicator === "weight_for_age") {
    if (sex === "F") {
      return { ageMonths: phvAgeMonths + 6, label: "PWV" };
    }
    return { ageMonths: phvAgeMonths, label: "PHV/PWV" };
  }
  return { ageMonths: phvAgeMonths, label: "PHV" };
}

// ---------------------------------------------------------------------------
// Helpers de fechas / valores
// ---------------------------------------------------------------------------

export function getReferenceData(
  sex: "M" | "F",
  indicator: GrowthIndicator,
): ReferenceRow[] {
  const indicatorData = growthData.indicators[indicator] as Record<string, ReferenceRow[]>;
  return indicatorData[sex] ?? [];
}

export function ageMonthsFromDates(birthDate: string, evaluationDate: string): number {
  const birth = new Date(birthDate).getTime();
  const evaluation = new Date(evaluationDate).getTime();
  return (evaluation - birth) / (1000 * 60 * 60 * 24 * 30.4375);
}

// Privacy: ofuscar fecha de evaluacion completa a "mes anio" (ej: "ene 2026")
// para reducir precision identificable en tooltip + tabla sr-only.
export function formatMonthYear(isoDate: string | null): string {
  if (!isoDate) return "";
  const [yearStr, monthStr] = isoDate.split("-");
  const monthIdx = Number(monthStr) - 1;
  if (monthIdx < 0 || monthIdx > 11) return isoDate;
  return `${MONTH_NAMES_ES[monthIdx]} ${yearStr}`;
}

export function getAthleteValue(
  record: AnthropometricRecord,
  indicator: GrowthIndicator,
): number | null {
  if (indicator === "height_for_age") {
    return Number(record.standing_height_cm);
  }
  if (indicator === "weight_for_age") {
    return Number(record.weight_kg);
  }
  if (indicator === "bmi_for_age") {
    const heightM = Number(record.standing_height_cm) / 100;
    if (heightM <= 0) return null;
    return Number(record.weight_kg) / (heightM * heightM);
  }
  return null;
}

/**
 * Clasifica el Z-score en una banda clínica según cortes OMS estándar.
 * Duplica classifyBand de useGrowthMetrics para no importar el hook en un
 * componente de presentación.
 */
export function classifyBand(z: number): GrowthBand {
  if (z < -2) return "low";
  if (z < -1) return "watch_low";
  if (z <= 1) return "ok";
  if (z <= 2) return "watch_high";
  return "high";
}

/**
 * Calcula los límites del dominio Y a partir de los datos de referencia.
 * Usa el mínimo de P3 y el máximo de P97 con un margen del 5 %.
 */
export function computeDomain(referenceRows: ReferenceRow[]): [number, number] {
  if (referenceRows.length === 0) return [0, 100];
  const minP3 = Math.min(...referenceRows.map((r) => r.P3));
  const maxP97 = Math.max(...referenceRows.map((r) => r.P97));
  const margin = (maxP97 - minP3) * 0.05;
  return [minP3 - margin, maxP97 + margin];
}

/**
 * Calcula los campos de banda para una fila de referencia.
 * domainMin y domainMax representan el límite visual del eje Y (extendido).
 */
export function computeBandFields(
  row: Pick<ChartRow, "P3" | "P10" | "P90" | "P97">,
  indicator: GrowthIndicator,
  domainMin: number,
  domainMax: number,
): Pick<ChartRow, "band_low" | "band_watch" | "band_ok" | "band_high" | "band_overweight" | "band_obesity"> {
  if (indicator === "bmi_for_age") {
    return {
      band_low:        [domainMin,   row.P3],
      band_watch:      [row.P3,      row.P10],
      band_ok:         [row.P10,     row.P90],
      band_overweight: [row.P90,     row.P97],
      band_obesity:    [row.P97,     domainMax],
    };
  }
  // height_for_age y weight_for_age comparten la misma estructura de 4 bandas
  return {
    band_low:   [domainMin, row.P3],
    band_watch: [row.P3,    row.P10],
    band_ok:    [row.P10,   row.P90],
    band_high:  [row.P90,   domainMax],
  };
}

/**
 * Construye el ChartRow usando interpolateReferenceRow de lms.ts para obtener
 * L, M y S que permiten el cálculo exacto de Z-score en el tooltip.
 * También añade los campos de banda de color de fondo para cada fila.
 */
export function buildChartData(
  referenceRows: ReferenceRow[],
  records: AnthropometricRecord[],
  birthDate: string,
  indicator: GrowthIndicator,
): { rows: ChartRow[]; domain: [number, number] } {
  const [domainMin, domainMax] = computeDomain(referenceRows);

  const chartData: ChartRow[] = referenceRows.map((row) => ({
    age_months: row.age,
    L: row.L,
    M: row.M,
    S: row.S,
    P3: row.P3,
    P10: row.P10,
    P25: row.P25,
    P50: row.P50,
    P75: row.P75,
    P90: row.P90,
    P97: row.P97,
    athleteValue: null,
    evaluationDate: null,
    ...computeBandFields(row, indicator, domainMin, domainMax),
  }));

  for (const record of records) {
    const ageMonths = ageMonthsFromDates(birthDate, record.evaluation_date);
    const value = getAthleteValue(record, indicator);
    if (value === null) continue;

    // Usar interpolateReferenceRow que retorna L, M, S interpolados
    const interpolated = interpolateReferenceRow(referenceRows, ageMonths);
    if (!interpolated) continue;

    chartData.push({
      age_months: ageMonths,
      L: interpolated.L,
      M: interpolated.M,
      S: interpolated.S,
      P3: interpolated.P3,
      P10: interpolated.P10,
      P25: interpolated.P25,
      P50: interpolated.P50,
      P75: interpolated.P75,
      P90: interpolated.P90,
      P97: interpolated.P97,
      athleteValue: value,
      evaluationDate: record.evaluation_date,
      ...computeBandFields(interpolated, indicator, domainMin, domainMax),
    });
  }

  const rows = chartData.sort((a, b) => a.age_months - b.age_months);
  return { rows, domain: [domainMin, domainMax] };
}

// ---------------------------------------------------------------------------
// Tooltip factory — devuelve un componente React listo para <Tooltip content={...}/>
// Lo mantenemos aquí (no en un .tsx separado) porque devuelve JSX puro de
// inspección de datos; PercentileCurves lo memoiza por indicator.
// ---------------------------------------------------------------------------

import { createElement, type FC } from "react";

export function makeCustomTooltip(indicator: GrowthIndicator): FC<CustomTooltipProps> {
  const CustomTooltipWithIndicator: FC<CustomTooltipProps> = (props) => {
    const { active, payload, label } = props;
    if (!active || !payload || payload.length === 0) return null;

    const ageMonths = label ?? 0;
    const ageYears = ageMonths / 12;

    const athleteEntry = payload.find((p) => p.dataKey === "athleteValue");
    const hasAthleteData = athleteEntry != null && athleteEntry.value !== null;

    let zScore: number | null = null;
    let percentile: number | null = null;
    let band: GrowthBand | null = null;

    if (hasAthleteData && athleteEntry) {
      const row = athleteEntry.payload;
      const value = athleteEntry.value as number;
      zScore = zScoreFromLMS(value, row.L, row.M, row.S);
      percentile = percentileFromZ(zScore);
      band = classifyBand(zScore);
    }

    return createElement(
      "div",
      {
        className: "rounded-lg bg-white p-2.5 text-xs shadow-card",
      },
      createElement("p", { className: "text-mid-gray" }, `Edad: ${ageYears.toFixed(1)} años`),
      hasAthleteData && athleteEntry
        ? [
            athleteEntry.payload.evaluationDate
              ? createElement(
                  "p",
                  { key: "date", className: "font-medium text-charcoal" },
                  `Medición: ${formatMonthYear(athleteEntry.payload.evaluationDate)}`,
                )
              : null,
            createElement(
              "p",
              { key: "value", className: "font-medium text-charcoal" },
              `Valor: ${(athleteEntry.value as number).toFixed(1)}`,
            ),
            zScore !== null
              ? createElement(
                  "p",
                  { key: "z", className: "text-mid-gray" },
                  `Z-score: ${zScore.toFixed(2)}`,
                )
              : null,
            percentile !== null
              ? createElement(
                  "p",
                  { key: "p", className: "text-mid-gray" },
                  `Percentil: P${percentile}`,
                )
              : null,
            band !== null
              ? createElement(
                  "p",
                  {
                    key: "band",
                    className: "flex items-center gap-1 text-mid-gray",
                  },
                  createElement("span", {
                    className: "inline-block h-2 w-2 rounded-full",
                    style: { backgroundColor: BAND_DOT_COLORS[band] },
                  }),
                  getBandSpec(indicator, band).label,
                )
              : null,
          ]
        : null,
    );
  };
  CustomTooltipWithIndicator.displayName = "PercentileCustomTooltip";
  return CustomTooltipWithIndicator;
}

export { percentileFromZ, zScoreFromLMS };
