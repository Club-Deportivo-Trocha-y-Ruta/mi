/**
 * PercentileChart — curva de percentiles OMS 2007 (feature 040, US3, T050).
 *
 * Reemplaza la gráfica de `PercentileCurves.tsx` (retirada en T052) dentro de
 * `GrowthCurveSection.tsx` (T051), que la monta en la vista `view="chart"` del
 * toolbar (`PercentileToolbar`, T049) junto a `PercentileTable` como
 * alternativa accesible en `view="table"`.
 *
 * Diferencias de diseño respecto a `PercentileCurves.tsx` (`contracts/growth-tab-ui.md`,
 * research.md R-06/R-07/R-08):
 *   - Sin bandas de fondo de 4-5 colores ni leyenda interactiva con toggle:
 *     una sola franja "rango esperado" (P3–P97) en `var(--color-light-gray)`.
 *   - Eje X acotado a una ventana alrededor de las mediciones
 *     (`lib/growth/window.ts`, T048) en vez del rango OMS completo 5–19 años;
 *     el toggle "Ver 5–19 años" llega como `range="full"`.
 *   - Todos los colores son tokens CSS (`var(--color-*)`), nunca hex — el
 *     wave review (T055) audita esto con
 *     `grep -n "#[0-9a-f]\{6\}" frontend/src/components/athletes/growth/`.
 *   - `preset="family"` (FR-016): solo línea del atleta + mediana + franja,
 *     sin marcador PHV/PWV, sin líneas P3/P97/detalle individuales y sin
 *     Z-score/percentil/banda en el tooltip — la familia nunca ve esos
 *     números en ninguna superficie.
 *   - El JSON de referencia OMS se carga con `import()` dinámico dentro de un
 *     `useEffect` (no import estático a nivel de módulo) para que quede en el
 *     mismo chunk perezoso que el resto de `components/athletes/growth/`
 *     (R-08) — nunca se descarga hasta que este componente se monta.
 *
 * Se duplican deliberadamente aquí `getMaturationMarker`, `INDICATOR_PHV_NOTES`,
 * el formateador de ticks en edad biológica, `formatMonthYear` y la extracción
 * de Z-score/percentil almacenado — el mismo criterio ya documentado en
 * `PercentileCurves.tsx` y `useGrowthMetrics.ts`: este componente no depende
 * de esos módulos para no acoplarse a sus mocks en tests, y porque
 * `PercentileCurves.tsx` desaparece en T052.
 *
 * Prioridad Z-score/percentil (idéntica a T026 / R-11): se usa el valor
 * almacenado por el backend solo cuando `record.growth_source === "WHO"`;
 * en cualquier otro caso (registro legado aún no recomputado) se calcula por
 * LMS contra la tabla OMS del cliente — mismo criterio que `useGrowthMetrics`.
 */
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type LegendPayload as RechartsLegendPayload,
} from "recharts";

import { ErrorState } from "@/components/shared/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { classifyBand, getBandVocabulary } from "@/lib/growth/bands";
import type { BandTone, NutritionalStatus } from "@/lib/growth/bands";
import {
  ageMonthsFromDates,
  interpolateReferenceRow,
  percentileFromZ,
  zScoreFromLMS,
  type GrowthIndicator,
  type ReferenceRow,
} from "@/lib/growth/lms";
import { computeAgeWindow, filterReferenceRows, niceTicks, yearTicks } from "@/lib/growth/window";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PercentileChartProps {
  indicator: GrowthIndicator;
  records: AnthropometricRecord[];
  sex: "M" | "F";
  birthDate: string;
  phvAgeMonths?: number;
  /** Eje cronológico o relativo al PHV — ignorado (forzado a "chrono") en `preset="family"` y en `bmi_for_age`. */
  axis: "chrono" | "bio";
  /** Ventana alrededor de las mediciones ("window") o rango OMS completo 5–19 años ("full"). */
  range: "window" | "full";
  /** Muestra P10/P25/P75/P90 además de P3/P50/P97 — sin efecto en `preset="family"`. */
  detail: boolean;
  /** "family" oculta el marcador de maduración y el detalle Z-score/percentil/banda (FR-016). Default "coach". */
  preset?: "coach" | "family";
}

// ---------------------------------------------------------------------------
// Datos de referencia OMS — carga perezosa (R-08)
// ---------------------------------------------------------------------------

interface WhoReferenceData {
  indicators: Record<GrowthIndicator, Record<"M" | "F", ReferenceRow[]>>;
}

type ReferenceState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; rows: ReferenceRow[] };

async function loadReferenceRows(
  indicator: GrowthIndicator,
  sex: "M" | "F",
): Promise<ReferenceRow[]> {
  const mod = await import("@/data/growth-reference-who.json");
  const data = mod.default as unknown as WhoReferenceData;
  return data.indicators[indicator]?.[sex] ?? [];
}

// ---------------------------------------------------------------------------
// Constantes e indicador → etiqueta/nota (portadas de PercentileCurves.tsx)
// ---------------------------------------------------------------------------

const INDICATOR_LABELS: Record<GrowthIndicator, string> = {
  height_for_age: "Talla (cm)",
  bmi_for_age: "IMC (kg/m²)",
  weight_for_age: "Peso (kg)",
};

// Notas pie de gráfica por indicador — aclaran el significado clínico de la
// línea vertical de maduración para evitar lecturas erróneas (p. ej.
// interpretar la subida de IMC peri-PHV como adiposidad cuando refleja masa
// magra). Ocultas en `preset="family"` junto con el propio marcador (FR-016).
const INDICATOR_PHV_NOTES: Record<GrowthIndicator, string> = {
  height_for_age: "Línea PHV: edad estimada del pico de velocidad de talla (Mirwald).",
  bmi_for_age:
    "Subida del IMC alrededor del PHV refleja aumento de masa magra, no adiposidad.",
  weight_for_age:
    "Pico de velocidad de peso (PWV) coincide con PHV en hombres y se retrasa ~6 meses en mujeres.",
};

/**
 * Leyenda fija de la vista familiar (T059, `contracts/growth-tab-ui.md`
 * §Copy — "Family: … curve caption"): reemplaza la nota de maduración
 * (`INDICATOR_PHV_NOTES`), que no aplica en `preset="family"` porque esa
 * vista nunca dibuja el marcador PHV/PWV.
 */
const FAMILY_CURVE_CAPTION = "Línea gris: promedio para su edad. Franja: rango esperado.";

const MONTH_NAMES_ES = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

interface MaturationMarker {
  ageMonths: number;
  label: string;
}

/**
 * Dada la edad PHV en meses, indicador y sexo, calcula la línea vertical
 * apropiada — talla/IMC: línea en PHV; peso ♂: PWV coincide con PHV
 * ("PHV/PWV"); peso ♀: PWV ~6 meses post-PHV ("PWV").
 */
function getMaturationMarker(
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

/** Privacidad: ofusca la fecha completa de evaluación a "mes año" (ej. "ene 2026"). */
function formatMonthYear(isoDate: string | null): string {
  if (!isoDate) return "";
  const [yearStr, monthStr] = isoDate.split("-");
  const monthIdx = Number(monthStr) - 1;
  if (monthIdx < 0 || monthIdx > 11) return isoDate;
  return `${MONTH_NAMES_ES[monthIdx]} ${yearStr}`;
}

function formatValue(value: number, indicator: GrowthIndicator): string {
  switch (indicator) {
    case "height_for_age":
      return `${value.toFixed(1)} cm`;
    case "weight_for_age":
      return `${value.toFixed(1)} kg`;
    case "bmi_for_age":
      return `${value.toFixed(1)} kg/m²`;
  }
}

function getAthleteValue(
  record: AnthropometricRecord,
  indicator: GrowthIndicator,
): number | null {
  if (indicator === "height_for_age") {
    const v = Number(record.standing_height_cm);
    return v > 0 ? v : null;
  }
  if (indicator === "weight_for_age") {
    const v = Number(record.weight_kg);
    return v > 0 ? v : null;
  }
  if (record.bmi != null) {
    const v = Number(record.bmi);
    return v > 0 ? v : null;
  }
  const heightM = Number(record.standing_height_cm) / 100;
  if (heightM <= 0) return null;
  return Number(record.weight_kg) / (heightM * heightM);
}

/**
 * Extrae el Z-score/percentil almacenados por el backend para el indicador
 * exacto, solo cuando `record.growth_source === "WHO"` (T026/R-11) — un
 * registro `CDC`/`null` (legado) tiene un Z-score de otra población y no debe
 * mostrarse junto a las curvas OMS de este componente.
 */
function extractStoredZ(
  record: AnthropometricRecord,
  indicator: GrowthIndicator,
): { zScore: number; percentile: number | null } | null {
  if (record.growth_source !== "WHO") return null;
  switch (indicator) {
    case "height_for_age":
      return record.height_z_score != null
        ? { zScore: record.height_z_score, percentile: record.height_percentile ?? null }
        : null;
    case "bmi_for_age":
      return record.bmi_z_score != null
        ? { zScore: record.bmi_z_score, percentile: record.bmi_percentile ?? null }
        : null;
    case "weight_for_age":
      return record.weight_z_score != null
        ? { zScore: record.weight_z_score, percentile: record.weight_percentile ?? null }
        : null;
  }
}

// ---------------------------------------------------------------------------
// Construcción de filas del chart
// ---------------------------------------------------------------------------

interface ChartRow {
  age_months: number;
  P3: number;
  P10: number;
  P25: number;
  P50: number;
  P75: number;
  P90: number;
  P97: number;
  /** Tupla [P3, P97] — `Area` la interpreta como rango de banda. */
  bandRange: [number, number];
  athleteValue: number | null;
  evaluationDate: string | null;
  zScore?: number | null;
  percentile?: number | null;
  band?: NutritionalStatus | null;
}

function referenceRowToChartRow(row: ReferenceRow): ChartRow {
  return {
    age_months: row.age,
    P3: row.P3,
    P10: row.P10,
    P25: row.P25,
    P50: row.P50,
    P75: row.P75,
    P90: row.P90,
    P97: row.P97,
    bandRange: [row.P3, row.P97],
    athleteValue: null,
    evaluationDate: null,
  };
}

function buildChartRows(
  windowedRows: ReferenceRow[],
  fullRows: ReferenceRow[],
  records: AnthropometricRecord[],
  birthDate: string,
  indicator: GrowthIndicator,
): ChartRow[] {
  const rows: ChartRow[] = windowedRows.map(referenceRowToChartRow);

  for (const record of records) {
    const value = getAthleteValue(record, indicator);
    if (value === null) continue;

    const ageMonths = ageMonthsFromDates(birthDate, record.evaluation_date);
    const interpolated = interpolateReferenceRow(fullRows, ageMonths);
    if (!interpolated) continue;

    const stored = extractStoredZ(record, indicator);
    const zScore = stored?.zScore ?? zScoreFromLMS(value, interpolated.L, interpolated.M, interpolated.S);
    const percentile = stored?.percentile ?? percentileFromZ(zScore);

    rows.push({
      age_months: ageMonths,
      P3: interpolated.P3,
      P10: interpolated.P10,
      P25: interpolated.P25,
      P50: interpolated.P50,
      P75: interpolated.P75,
      P90: interpolated.P90,
      P97: interpolated.P97,
      bandRange: [interpolated.P3, interpolated.P97],
      athleteValue: value,
      evaluationDate: record.evaluation_date,
      zScore,
      percentile,
      band: classifyBand(indicator, zScore),
    });
  }

  return rows.sort((a, b) => a.age_months - b.age_months);
}

/** Dominio + ticks "redondos" del eje Y a partir de las filas visibles (P3 min … P97 max, margen 5 %). */
function computeYAxis(rows: ReferenceRow[]): { domain: [number, number]; ticks: number[] } {
  if (rows.length === 0) {
    const ticks = niceTicks(0, 100);
    return { domain: [ticks[0], ticks[ticks.length - 1]], ticks };
  }
  const minP3 = Math.min(...rows.map((r) => r.P3));
  const maxP97 = Math.max(...rows.map((r) => r.P97));
  const margin = (maxP97 - minP3) * 0.05 || 1;
  const ticks = niceTicks(minP3 - margin, maxP97 + margin);
  return { domain: [ticks[0], ticks[ticks.length - 1]], ticks };
}

// ---------------------------------------------------------------------------
// Leyenda — estática (sin toggle), solo las series que el contrato enumera
// ---------------------------------------------------------------------------

const LEGEND_ORDER = ["athleteValue", "P50", "bandRange"] as const;

function GrowthLegend({ payload }: { payload?: ReadonlyArray<RechartsLegendPayload> }) {
  if (!payload?.length) return null;
  const sorted = [...payload].sort(
    (a, b) =>
      LEGEND_ORDER.indexOf(String(a.dataKey ?? "") as (typeof LEGEND_ORDER)[number]) -
      LEGEND_ORDER.indexOf(String(b.dataKey ?? "") as (typeof LEGEND_ORDER)[number]),
  );
  return (
    <ul className="mt-1 flex flex-wrap justify-center gap-x-4 gap-y-1 text-[11px] text-mid-gray">
      {sorted.map((entry) => (
        <li key={String(entry.dataKey)} className="flex items-center gap-1.5">
          <svg width="14" height="10" aria-hidden="true">
            {entry.type === "rect" ? (
              <rect x="0" y="2" width="14" height="6" fill={entry.color} />
            ) : (
              <line x1="0" y1="5" x2="14" y2="5" stroke={entry.color} strokeWidth={2} />
            )}
          </svg>
          {entry.value}
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

interface TooltipPayloadItem {
  dataKey?: string;
  value: number | null;
  payload: ChartRow;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: number;
}

const TONE_TEXT_VAR: Record<BandTone, string> = {
  success: "var(--color-success)",
  warning: "var(--color-warning)",
  danger: "var(--color-danger)",
  neutral: "var(--color-mid-gray)",
};

function makeTooltip(indicator: GrowthIndicator, isFamily: boolean) {
  return function GrowthTooltip({ active, payload, label }: CustomTooltipProps) {
    if (!active || !payload || payload.length === 0) return null;

    const ageMonths = label ?? 0;
    const ageYears = ageMonths / 12;

    const athleteEntry = payload.find((p) => p.dataKey === "athleteValue");
    const hasAthleteData = athleteEntry != null && athleteEntry.value !== null;

    return (
      <div className="rounded-lg bg-white p-2.5 text-xs shadow-card">
        <p className="text-mid-gray">Edad: {ageYears.toFixed(1)} años</p>

        {hasAthleteData && athleteEntry && (
          <>
            {athleteEntry.payload.evaluationDate && (
              <p className="font-medium text-charcoal">
                Medición: {formatMonthYear(athleteEntry.payload.evaluationDate)}
              </p>
            )}
            <p className="font-medium text-charcoal">
              Valor: {formatValue(athleteEntry.value as number, indicator)}
            </p>

            {/* FR-016 — la vista familiar nunca muestra Z-score/percentil/banda. */}
            {!isFamily && (
              <>
                {athleteEntry.payload.zScore != null && (
                  <p className="text-mid-gray">Z-score: {athleteEntry.payload.zScore.toFixed(2)}</p>
                )}
                {athleteEntry.payload.percentile != null && (
                  <p className="text-mid-gray">Percentil: P{athleteEntry.payload.percentile}</p>
                )}
                {athleteEntry.payload.band != null && (
                  <p className="flex items-center gap-1 text-mid-gray">
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{
                        backgroundColor:
                          TONE_TEXT_VAR[getBandVocabulary(indicator, athleteEntry.payload.band).tone],
                      }}
                      aria-hidden="true"
                    />
                    {getBandVocabulary(indicator, athleteEntry.payload.band).coachLabel}
                  </p>
                )}
              </>
            )}
          </>
        )}
      </div>
    );
  };
}

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function PercentileChart({
  indicator,
  records,
  sex,
  birthDate,
  phvAgeMonths,
  axis,
  range,
  detail,
  preset = "coach",
}: PercentileChartProps) {
  const isFamily = preset === "family";

  const [referenceState, setReferenceState] = useState<ReferenceState>({ status: "loading" });
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setReferenceState({ status: "loading" });
    loadReferenceRows(indicator, sex)
      .then((rows) => {
        if (!cancelled) setReferenceState({ status: "ready", rows });
      })
      .catch(() => {
        if (!cancelled) setReferenceState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [indicator, sex, retryToken]);

  const fullReferenceRows = referenceState.status === "ready" ? referenceState.rows : [];

  const recordAgesMonths = useMemo(
    () => records.map((r) => ageMonthsFromDates(birthDate, r.evaluation_date)),
    [records, birthDate],
  );

  const [windowMin, windowMax] = useMemo(
    () => computeAgeWindow(recordAgesMonths, range === "full" ? "full" : "auto"),
    [recordAgesMonths, range],
  );

  const windowedReferenceRows = useMemo(
    () => filterReferenceRows(fullReferenceRows, windowMin, windowMax),
    [fullReferenceRows, windowMin, windowMax],
  );

  const { domain: yDomain, ticks: yTicks } = useMemo(
    () => computeYAxis(windowedReferenceRows),
    [windowedReferenceRows],
  );

  const xTicks = useMemo(() => yearTicks(windowMin, windowMax), [windowMin, windowMax]);

  const chartRows = useMemo(
    () => buildChartRows(windowedReferenceRows, fullReferenceRows, records, birthDate, indicator),
    [windowedReferenceRows, fullReferenceRows, records, birthDate, indicator],
  );

  const TooltipContent = useMemo(() => makeTooltip(indicator, isFamily), [indicator, isFamily]);

  // No hay eje biológico para BMI (FR-015) ni en la vista familiar (FR-016).
  const supportsBioAxis = indicator !== "bmi_for_age" && phvAgeMonths !== undefined;
  const effectiveAxis: "chrono" | "bio" = isFamily || !supportsBioAxis ? "chrono" : axis;
  const showDetail = !isFamily && detail;
  const marker = isFamily ? null : getMaturationMarker(indicator, sex, phvAgeMonths);
  const phvNote = INDICATOR_PHV_NOTES[indicator];

  const xTickFormatter = useMemo(() => {
    if (effectiveAxis === "bio" && phvAgeMonths !== undefined) {
      return (ageMonths: number) => {
        const offset = (ageMonths - phvAgeMonths) / 12;
        const sign = offset >= 0 ? "+" : "";
        return `${sign}${offset.toFixed(1)} a`;
      };
    }
    return (ageMonths: number) => `${(ageMonths / 12).toFixed(1)} a`;
  }, [effectiveAxis, phvAgeMonths]);

  // Última medición con valor válido — resume el estado actual en el aria-label del gráfico.
  const latestAthleteRow = [...chartRows]
    .filter((row) => row.athleteValue !== null)
    .sort((a, b) => b.age_months - a.age_months)[0];
  const latestBandLabel =
    latestAthleteRow?.band != null
      ? isFamily
        ? getBandVocabulary(indicator, latestAthleteRow.band).familyLabel
        : getBandVocabulary(indicator, latestAthleteRow.band).coachLabel
      : null;
  const measurementCount = records.length;
  const ariaLabel =
    `Curva de percentiles de ${INDICATOR_LABELS[indicator]} con ` +
    `${measurementCount} ${measurementCount === 1 ? "medición" : "mediciones"} del atleta.` +
    (latestBandLabel ? ` Última clasificación: ${latestBandLabel}.` : "");

  if (referenceState.status === "loading") {
    return (
      <div role="status" aria-busy="true" aria-label="Cargando curva de crecimiento…">
        <Skeleton className="relative aspect-[3/2] w-full min-h-[280px] rounded-xl" />
      </div>
    );
  }

  if (referenceState.status === "error") {
    return (
      <ErrorState
        message="No se pudo cargar la referencia de crecimiento."
        onRetry={() => setRetryToken((t) => t + 1)}
      />
    );
  }

  if (fullReferenceRows.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-mid-gray">
        No hay datos de referencia disponibles para este indicador.
      </p>
    );
  }

  return (
    <div>
      <div role="img" aria-label={ariaLabel} className="relative aspect-[3/2] w-full min-h-[280px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartRows} margin={{ top: 24, right: 24, left: 8, bottom: 8 }}>
            <CartesianGrid stroke="var(--color-border-gray)" />

            <XAxis
              dataKey="age_months"
              type="number"
              domain={[windowMin, windowMax]}
              ticks={xTicks}
              allowDataOverflow
              tickFormatter={xTickFormatter}
              tick={{ fontSize: 11, fill: "var(--color-mid-gray)" }}
              label={{
                value: effectiveAxis === "bio" ? "Edad relativa al PHV" : "Edad",
                position: "insideBottom",
                offset: -4,
                fontSize: 11,
                fill: "var(--color-mid-gray)",
              }}
            />
            <YAxis
              domain={yDomain}
              ticks={yTicks}
              tickFormatter={(v: number) => v.toFixed(0)}
              tick={{ fontSize: 11, fill: "var(--color-mid-gray)" }}
              width={40}
            />

            <Tooltip
              content={<TooltipContent />}
              cursor={{ stroke: "var(--color-mid-gray)", strokeWidth: 1, strokeDasharray: "3 3" }}
            />
            <Legend content={(p) => <GrowthLegend payload={p.payload} />} itemSorter={null} />

            {/* Franja "rango esperado" (P3–P97) — dibujada primero para quedar detrás de las líneas. */}
            <Area
              type="monotone"
              dataKey="bandRange"
              name={isFamily ? "Rango esperado" : "P3–P97"}
              legendType="rect"
              fill="var(--color-light-gray)"
              fillOpacity={0.6}
              stroke="none"
              isAnimationActive={false}
              dot={false}
              activeDot={false}
            />

            {!isFamily && (
              <>
                <Line
                  type="monotone"
                  dataKey="P3"
                  stroke="var(--color-mid-gray)"
                  strokeWidth={1.5}
                  strokeDasharray="2 2"
                  legendType="none"
                  dot={false}
                  isAnimationActive={false}
                  name="P3"
                />
                <Line
                  type="monotone"
                  dataKey="P97"
                  stroke="var(--color-mid-gray)"
                  strokeWidth={1.5}
                  strokeDasharray="2 2"
                  legendType="none"
                  dot={false}
                  isAnimationActive={false}
                  name="P97"
                />
              </>
            )}

            {showDetail && (
              <>
                <Line
                  type="monotone"
                  dataKey="P10"
                  stroke="var(--color-mid-gray)"
                  strokeWidth={1}
                  strokeDasharray="4 4"
                  legendType="none"
                  dot={false}
                  isAnimationActive={false}
                  name="P10"
                />
                <Line
                  type="monotone"
                  dataKey="P90"
                  stroke="var(--color-mid-gray)"
                  strokeWidth={1}
                  strokeDasharray="4 4"
                  legendType="none"
                  dot={false}
                  isAnimationActive={false}
                  name="P90"
                />
                <Line
                  type="monotone"
                  dataKey="P25"
                  stroke="var(--color-mid-gray)"
                  strokeWidth={1}
                  strokeDasharray="6 2"
                  legendType="none"
                  dot={false}
                  isAnimationActive={false}
                  name="P25"
                />
                <Line
                  type="monotone"
                  dataKey="P75"
                  stroke="var(--color-mid-gray)"
                  strokeWidth={1}
                  strokeDasharray="6 2"
                  legendType="none"
                  dot={false}
                  isAnimationActive={false}
                  name="P75"
                />
              </>
            )}

            <Line
              type="monotone"
              dataKey="P50"
              name={isFamily ? "Promedio" : "Mediana (P50)"}
              stroke="var(--color-charcoal)"
              strokeWidth={2}
              legendType="line"
              dot={false}
              isAnimationActive={false}
            />

            <Line
              type="monotone"
              dataKey="athleteValue"
              name="Deportista"
              stroke="var(--color-primary)"
              strokeWidth={2}
              legendType="line"
              connectNulls
              isAnimationActive={false}
              dot={{ r: 4, fill: "var(--color-primary)", stroke: "var(--color-white)", strokeWidth: 2 }}
              activeDot={{ r: 6, fill: "var(--color-primary)", stroke: "var(--color-white)", strokeWidth: 2 }}
            />

            {marker !== null && (
              <ReferenceLine
                x={marker.ageMonths}
                stroke="var(--color-mid-gray)"
                strokeDasharray="5 3"
                strokeWidth={1.5}
                label={{
                  value: marker.label,
                  position: "top",
                  fontSize: 11,
                  fill: "var(--color-mid-gray)",
                }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {isFamily ? (
        <p className="mt-2 text-[11px] italic text-mid-gray">{FAMILY_CURVE_CAPTION}</p>
      ) : (
        marker !== null && <p className="mt-2 text-[11px] italic text-mid-gray">{phvNote}</p>
      )}
    </div>
  );
}
