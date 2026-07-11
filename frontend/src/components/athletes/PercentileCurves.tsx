import { useMemo, useRef, useState } from "react";
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
import { Info } from "lucide-react";

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
import { UserRole } from "@/types/enums";
import { useAuthStore } from "@/store/auth.store";
import { PercentileInterpretationBlock } from "./PercentileInterpretationBlock";

export type GrowthIndicator =
  | "height_for_age"
  | "bmi_for_age"
  | "weight_for_age";

export interface PercentileCurvesProps {
  sex: "M" | "F";
  birthDate: string;
  records: AnthropometricRecord[];
  indicator: GrowthIndicator;
  phvAgeMonths?: number;
}

interface ChartRow {
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

interface TooltipPayloadItem {
  dataKey: string;
  value: number | null;
  payload: ChartRow;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: number;
}

const LEGEND_ORDER = [
  "athleteValue",
  "P50",
  "P25",
  "P75",
  "P10",
  "P90",
  "P3",
  "P97",
] as const;

type LegendOrderKey = (typeof LEGEND_ORDER)[number];

interface LineStrokePayload {
  strokeWidth?: number;
  strokeDasharray?: string;
}

// ---------------------------------------------------------------------------
// B3.26 — CustomLegend con click para toggle visibilidad
// ---------------------------------------------------------------------------

function CustomLegend({
  payload,
  hiddenKeys,
  onToggle,
}: {
  payload?: ReadonlyArray<RechartsLegendPayload>;
  hiddenKeys: Set<string>;
  onToggle: (key: string) => void;
}) {
  if (!payload?.length) return null;
  // Excluir bandas de fondo de la leyenda (double-guard: legendType="none" ya las filtra en recharts)
  const filtered = payload.filter(
    (entry) => !ALL_BAND_KEYS.has(String(entry.dataKey ?? "")),
  );
  const sorted = [...filtered].sort(
    (a, b) =>
      LEGEND_ORDER.indexOf((a.dataKey ?? "") as LegendOrderKey) -
      LEGEND_ORDER.indexOf((b.dataKey ?? "") as LegendOrderKey),
  );
  return (
    <div className="mt-1 flex flex-wrap justify-center gap-x-4 gap-y-1 text-[11px] text-mid-gray">
      {sorted.map((entry) => {
        const key = String(entry.dataKey ?? "");
        const isHidden = hiddenKeys.has(key);
        const strokePayload = entry.payload as LineStrokePayload | undefined;
        return (
          <button
            key={key}
            type="button"
            onClick={() => onToggle(key)}
            className="flex cursor-pointer items-center gap-1.5 border-none bg-transparent p-0 transition-opacity"
            style={{ opacity: isHidden ? 0.4 : 1 }}
            aria-pressed={isHidden}
            aria-label={`${isHidden ? "Mostrar" : "Ocultar"} ${entry.value}`}
          >
            <svg width="22" height="10" aria-hidden="true">
              <line
                x1="0"
                y1="5"
                x2="22"
                y2="5"
                stroke={entry.color}
                strokeWidth={strokePayload?.strokeWidth ?? 1}
                strokeDasharray={strokePayload?.strokeDasharray ?? undefined}
              />
            </svg>
            {entry.value}
          </button>
        );
      })}
    </div>
  );
}

const INDICATOR_LABELS: Record<GrowthIndicator, string> = {
  height_for_age: "Talla (cm)",
  bmi_for_age: "IMC (kg/m²)",
  weight_for_age: "Peso (kg)",
};

// Notas pie de gráfica por indicador. Aclaran el significado clínico de la línea
// vertical de maduración para evitar lecturas erróneas (p. ej. interpretar subida
// de IMC peri-PHV como adiposidad cuando refleja masa magra).
const INDICATOR_PHV_NOTES: Record<GrowthIndicator, string> = {
  height_for_age: "Línea PHV: edad estimada del pico de velocidad de talla (Mirwald).",
  bmi_for_age:
    "Subida del IMC alrededor del PHV refleja aumento de masa magra, no adiposidad.",
  weight_for_age:
    "Pico de velocidad de peso (PWV) coincide con PHV en hombres y se retrasa ~6 meses en mujeres.",
};

interface MaturationMarker {
  ageMonths: number;
  label: string;
}

// Dada la edad PHV en meses, indicador y sexo, calcula la línea vertical apropiada:
// — Talla / IMC: línea en PHV.
// — Peso ♂: PWV coincide con PHV → línea en PHV con etiqueta "PHV/PWV".
// — Peso ♀: PWV ~6 meses post-PHV → línea desplazada con etiqueta "PWV".
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

function getReferenceData(sex: "M" | "F", indicator: GrowthIndicator): ReferenceRow[] {
  const indicatorData = growthData.indicators[indicator] as Record<string, ReferenceRow[]>;
  return indicatorData[sex] ?? [];
}

function ageMonthsFromDates(birthDate: string, evaluationDate: string): number {
  const birth = new Date(birthDate).getTime();
  const evaluation = new Date(evaluationDate).getTime();
  return (evaluation - birth) / (1000 * 60 * 60 * 24 * 30.4375);
}

const MONTH_NAMES_ES = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

// Privacy: ofuscar fecha de evaluacion completa a "mes anio" (ej: "ene 2026")
// para reducir precision identificable en tooltip + tabla sr-only.
function formatMonthYear(isoDate: string | null): string {
  if (!isoDate) return "";
  const [yearStr, monthStr] = isoDate.split("-");
  const monthIdx = Number(monthStr) - 1;
  if (monthIdx < 0 || monthIdx > 11) return isoDate;
  return `${MONTH_NAMES_ES[monthIdx]} ${yearStr}`;
}

function getAthleteValue(
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
function classifyBand(z: number): GrowthBand {
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
function computeDomain(referenceRows: ReferenceRow[]): [number, number] {
  if (referenceRows.length === 0) return [0, 100];
  const minP3 = Math.min(...referenceRows.map((r) => r.P3));
  const maxP97 = Math.max(...referenceRows.map((r) => r.P97));
  const margin = (maxP97 - minP3) * 0.05;
  return [minP3 - margin, maxP97 + margin];
}

/**
 * Construye el ChartRow usando interpolateReferenceRow de lms.ts para obtener
 * L, M y S que permiten el cálculo exacto de Z-score en el tooltip.
 * También añade los campos de banda de color de fondo para cada fila.
 */
function buildChartData(
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
// Configuración de bandas de color de fondo
// ---------------------------------------------------------------------------

interface BandConfig {
  /** dataKey del Area en ComposedChart */
  key: string;
  fill: string;
  fillOpacity: number;
}

const BAND_CONFIGS: Record<GrowthIndicator, BandConfig[]> = {
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
const ALL_BAND_KEYS = new Set<string>([
  "band_low", "band_watch", "band_ok", "band_high",
  "band_overweight", "band_obesity",
]);

/**
 * Calcula los campos de banda para una fila de referencia.
 * domainMin y domainMax representan el límite visual del eje Y (extendido).
 */
function computeBandFields(
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

// Colores de banda para el dot en el tooltip
const BAND_DOT_COLORS: Record<GrowthBand, string> = {
  low: "#ea580c",
  watch_low: "#ca8a04",
  ok: "#16a34a",
  watch_high: "#2563eb",
  high: "#2563eb",
};

// Tooltip con indicador en closure para getBandSpec correcto por indicador
function makeCustomTooltip(indicator: GrowthIndicator) {
  return function CustomTooltipWithIndicator(props: CustomTooltipProps) {
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
              Valor: {(athleteEntry.value as number).toFixed(1)}
            </p>
            {zScore !== null && (
              <p className="text-mid-gray">
                Z-score: {zScore.toFixed(2)}
              </p>
            )}
            {percentile !== null && (
              <p className="text-mid-gray">
                Percentil: P{percentile}
              </p>
            )}
            {band !== null && (
              <p className="flex items-center gap-1 text-mid-gray">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: BAND_DOT_COLORS[band] }}
                />
                {getBandSpec(indicator, band).label}
              </p>
            )}
          </>
        )}
      </div>
    );
  };
}

// ---------------------------------------------------------------------------
// B3.27 — PHV Info Popover (nativo, sin Radix — @radix-ui/react-popover no instalado)
// ---------------------------------------------------------------------------

function PhvInfoPopover({ note }: { note: string }) {
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);

  return (
    <span className="relative inline-flex items-center">
      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
        aria-label="Información sobre el marcador de maduración"
        aria-expanded={open}
        className="ml-1 flex h-4 w-4 items-center justify-center rounded-full text-mid-gray transition-colors hover:text-charcoal focus:outline-none focus-visible:ring-2 focus-visible:ring-charcoal"
      >
        <Info size={12} aria-hidden="true" />
      </button>
      {open && (
        <div
          role="tooltip"
          className="absolute left-5 top-0 z-50 w-56 rounded-md bg-white p-2.5 text-[11px] leading-relaxed text-mid-gray shadow-card"
        >
          {note}
        </div>
      )}
    </span>
  );
}

export function PercentileCurves({
  sex,
  birthDate,
  records,
  indicator,
  phvAgeMonths,
}: PercentileCurvesProps) {
  // B3.25 — Toggle edad biológica / cronológica (gated por rol)
  const user = useAuthStore((s) => s.user);
  const canSeeBioToggle =
    (user?.role === UserRole.coach || user?.role === UserRole.admin) &&
    phvAgeMonths !== undefined &&
    indicator !== "bmi_for_age";

  const [useBioAge, setUseBioAge] = useState(false);

  // B3.26 — Leyenda interactiva: claves ocultas
  const [hiddenKeys, setHiddenKeys] = useState<Set<string>>(new Set());

  const handleLegendToggle = (key: string) => {
    setHiddenKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const referenceRows = getReferenceData(sex, indicator);

  const latestRecord =
    records.length > 0
      ? [...records].sort(
          (a, b) =>
            new Date(b.evaluation_date).getTime() -
            new Date(a.evaluation_date).getTime(),
        )[0]
      : null;

  if (referenceRows.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-mid-gray">
        No hay datos de referencia disponibles para este indicador.
      </p>
    );
  }

  // B3.29 — Memoize chartData para evitar recalculo en cada render
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const { rows: chartData, domain: yDomain } = useMemo(
    () => buildChartData(referenceRows, records, birthDate, indicator),
    // referenceRows se recalcula de getReferenceData en cada render, pero su
    // contenido es estable (JSON estático). Se excluye del dep array para evitar
    // re-memoización innecesaria; sex + indicator + birthDate la cubren.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [records, sex, indicator, birthDate],
  );

  const yLabel = INDICATOR_LABELS[indicator];
  const marker = getMaturationMarker(indicator, sex, phvAgeMonths);
  const phvNote = INDICATOR_PHV_NOTES[indicator];
  const bandConfigs = BAND_CONFIGS[indicator];

  // Estabilizar la referencia del componente de tooltip para evitar remounts en cada render
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const TooltipContent = useMemo(() => makeCustomTooltip(indicator), [indicator]);

  // B3.25 — XAxis tickFormatter: modo biológico resta offset PHV
  const xTickFormatter = useMemo(() => {
    if (useBioAge && phvAgeMonths !== undefined) {
      return (ageMonths: number) => {
        const offset = (ageMonths - phvAgeMonths) / 12;
        const sign = offset >= 0 ? "+" : "";
        return `${sign}${offset.toFixed(1)} a`;
      };
    }
    return (ageMonths: number) => `${(ageMonths / 12).toFixed(1)} a`;
  }, [useBioAge, phvAgeMonths]);

  // B3.25 — Posición del marker PHV en eje biológico: siempre en 0 cuando useBioAge
  const markerX = useBioAge && phvAgeMonths !== undefined && marker !== null
    ? marker.ageMonths  // recharts usa el mismo dataKey age_months; el label cambia
    : marker?.ageMonths;

  // Leyenda con closure sobre hiddenKeys y onToggle
  const legendContent = useMemo(
    () =>
      (props: { payload?: ReadonlyArray<RechartsLegendPayload> }) => (
        <CustomLegend
          payload={props.payload}
          hiddenKeys={hiddenKeys}
          onToggle={handleLegendToggle}
        />
      ),
    // handleLegendToggle es estable (definida en render body con closure),
    // hiddenKeys cambia solo al toggle — ambas son deps correctas.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [hiddenKeys],
  );

  // Datos de la tabla sr-only: solo registros con valor de atleta
  const athleteRows = chartData.filter(
    (row) => row.athleteValue !== null && row.evaluationDate !== null,
  );

  return (
    <div>
      {/* Header: label Y + toggle bio/crono (B3.25) + popover info (B3.27) */}
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="flex items-center text-xs text-mid-gray">
          {yLabel}
          {marker !== null && (
            <PhvInfoPopover note={phvNote} />
          )}
        </span>

        {/* B3.25 — Toggle pill: solo coach/admin, con PHV definido, no en bmi_for_age */}
        {canSeeBioToggle && (
          <div
            role="group"
            aria-label="Modo de eje de edad"
            className="flex rounded-full border border-mid-gray/30 bg-white text-[11px]"
          >
            <button
              type="button"
              onClick={() => setUseBioAge(false)}
              className={`rounded-l-full px-2.5 py-0.5 transition-colors ${
                !useBioAge
                  ? "bg-charcoal text-white"
                  : "text-mid-gray hover:text-charcoal"
              }`}
              aria-pressed={!useBioAge}
            >
              Cronologica
            </button>
            <button
              type="button"
              onClick={() => setUseBioAge(true)}
              className={`rounded-r-full px-2.5 py-0.5 transition-colors ${
                useBioAge
                  ? "bg-charcoal text-white"
                  : "text-mid-gray hover:text-charcoal"
              }`}
              aria-pressed={useBioAge}
            >
              Biologica
            </button>
          </div>
        )}
      </div>

      {/* Mejora 3 — wrapper accesible para el chart */}
      <div
        role="img"
        aria-label={`Curva de percentiles ${INDICATOR_LABELS[indicator]} con ${records.length} medicion(es) del atleta.`}
      >
        <ResponsiveContainer width="100%" height={480}>
          <ComposedChart
            data={chartData}
            margin={{ top: 24, right: 56, left: 8, bottom: 8 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(34,42,53,0.08)" />
            <XAxis
              dataKey="age_months"
              type="number"
              scale="linear"
              domain={["dataMin", "dataMax"]}
              tickFormatter={xTickFormatter}
              tick={{ fontSize: 11, fill: "#898989" }}
              label={{
                value: useBioAge ? "Edad (relativa a PHV)" : "Edad",
                position: "insideBottom",
                offset: -4,
                fontSize: 11,
                fill: "#898989",
              }}
            />
            {/* B3.28 — Sin unit en YAxis para evitar etiquetas partidas en 2 lineas.
                La unidad ya aparece en el label superior (yLabel). Width reducido a 40. */}
            <YAxis
              tick={{ fontSize: 11, fill: "#898989" }}
              tickFormatter={(v: number) => v.toFixed(0)}
              domain={yDomain}
              allowDataOverflow={false}
              width={40}
            />
            {/* Mejora 2 — crosshair + tooltip activo en cualquier punto del eje X */}
            <Tooltip
              content={<TooltipContent />}
              cursor={{ stroke: "#898989", strokeWidth: 1, strokeDasharray: "3 3" }}
            />
            <Legend content={legendContent} />

            {/* Bandas de color de fondo — renderizadas antes que los Line para quedar detrás.
                Las bandas NO se ocultan con la leyenda interactiva (B3.26). */}
            {bandConfigs.map((band) => (
              <Area
                key={band.key}
                type="monotone"
                dataKey={band.key}
                fill={band.fill}
                fillOpacity={band.fillOpacity}
                stroke="none"
                isAnimationActive={false}
                legendType="none"
                dot={false}
                activeDot={false}
              />
            ))}

            {/* SD -3 y +3 (P3 y P97) — patrón "2 2" para daltonismo */}
            <Line
              type="monotone"
              dataKey="P3"
              stroke="#dc2626"
              strokeWidth={1.5}
              strokeDasharray="2 2"
              dot={false}
              isAnimationActive={false}
              name="SD-3 (P3)"
              hide={hiddenKeys.has("P3")}
            />
            <Line
              type="monotone"
              dataKey="P97"
              stroke="#dc2626"
              strokeWidth={1.5}
              strokeDasharray="2 2"
              dot={false}
              isAnimationActive={false}
              name="SD+3 (P97)"
              hide={hiddenKeys.has("P97")}
            />

            {/* SD -2 y +2 (P10 y P90) — patrón "4 4" */}
            <Line
              type="monotone"
              dataKey="P10"
              stroke="#dc2626"
              strokeWidth={1}
              strokeDasharray="4 4"
              dot={false}
              isAnimationActive={false}
              name="SD-2 (P10)"
              hide={hiddenKeys.has("P10")}
            />
            <Line
              type="monotone"
              dataKey="P90"
              stroke="#dc2626"
              strokeWidth={1}
              strokeDasharray="4 4"
              dot={false}
              isAnimationActive={false}
              name="SD+2 (P90)"
              hide={hiddenKeys.has("P90")}
            />

            {/* SD -1 y +1 (P25 y P75) — patrón "6 2" diferenciado */}
            <Line
              type="monotone"
              dataKey="P25"
              stroke="#ca8a04"
              strokeWidth={1}
              strokeDasharray="6 2"
              dot={false}
              isAnimationActive={false}
              name="SD-1 (P25)"
              hide={hiddenKeys.has("P25")}
            />
            <Line
              type="monotone"
              dataKey="P75"
              stroke="#ca8a04"
              strokeWidth={1}
              strokeDasharray="6 2"
              dot={false}
              isAnimationActive={false}
              name="SD+1 (P75)"
              hide={hiddenKeys.has("P75")}
            />

            {/* Mediana P50 — sin dasharray, strokeWidth 2.5 */}
            <Line
              type="monotone"
              dataKey="P50"
              stroke="#16a34a"
              strokeWidth={2.5}
              dot={false}
              isAnimationActive={false}
              name="Mediana (P50)"
              hide={hiddenKeys.has("P50")}
            />

            {/* Linea del atleta — charcoal, sin dasharray */}
            <Line
              type="monotone"
              dataKey="athleteValue"
              stroke="#242424"
              strokeWidth={2.5}
              dot={{ r: 4, fill: "#242424", stroke: "#111111" }}
              connectNulls={true}
              isAnimationActive={false}
              name="Atleta"
              hide={hiddenKeys.has("athleteValue")}
            />

            {/* Marcador vertical de maduración (PHV o PWV según indicador y sexo) */}
            {marker !== null && markerX !== undefined && (
              <ReferenceLine
                x={markerX}
                stroke="#898989"
                strokeDasharray="5 3"
                strokeWidth={1.5}
                label={{
                  value: marker.label,
                  position: "top",
                  fontSize: 11,
                  fill: "#898989",
                }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Mejora 3 — tabla sr-only: alternativa textual WCAG 2.1 AA */}
      {athleteRows.length > 0 && (
        <table className="sr-only" aria-label="Datos del atleta">
          <thead>
            <tr>
              <th scope="col">Fecha</th>
              <th scope="col">Edad</th>
              <th scope="col">{yLabel}</th>
              <th scope="col">Z-score</th>
              <th scope="col">Percentil</th>
            </tr>
          </thead>
          <tbody>
            {athleteRows.map((row, idx) => {
              const z = zScoreFromLMS(row.athleteValue as number, row.L, row.M, row.S);
              const p = percentileFromZ(z);
              return (
                <tr key={`${row.evaluationDate}-${row.age_months}-${idx}`}>
                  <td>{formatMonthYear(row.evaluationDate)}</td>
                  <td>{(row.age_months / 12).toFixed(1)} años</td>
                  <td>{(row.athleteValue as number).toFixed(1)}</td>
                  <td>{z.toFixed(2)}</td>
                  <td>P{p}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {latestRecord && (
        <div className="mt-3">
          <PercentileInterpretationBlock
            record={latestRecord}
            sex={sex}
            birthDate={birthDate}
            indicator={indicator}
          />
        </div>
      )}
      {marker !== null && (
        <p className="mt-2 text-[11px] text-mid-gray italic">{phvNote}</p>
      )}
    </div>
  );
}
