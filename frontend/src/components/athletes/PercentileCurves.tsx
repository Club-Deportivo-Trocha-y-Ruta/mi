import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import growthData from "@/data/growth-reference-cdc.json";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

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

interface ReferenceRow {
  age: number;
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
}

interface ChartRow {
  age_months: number;
  P3: number;
  P10: number;
  P25: number;
  P50: number;
  P75: number;
  P90: number;
  P97: number;
  athleteValue: number | null;
  evaluationDate: string | null;
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

const INDICATOR_LABELS: Record<GrowthIndicator, string> = {
  height_for_age: "Talla (cm)",
  bmi_for_age: "IMC (kg/m²)",
  weight_for_age: "Peso (kg)",
};

const INDICATOR_UNITS: Record<GrowthIndicator, string> = {
  height_for_age: " cm",
  bmi_for_age: " kg/m²",
  weight_for_age: " kg",
};

function getReferenceData(sex: "M" | "F", indicator: GrowthIndicator): ReferenceRow[] {
  const indicatorData = growthData.indicators[indicator] as Record<string, ReferenceRow[]>;
  return indicatorData[sex] ?? [];
}

function ageMonthsFromDates(birthDate: string, evaluationDate: string): number {
  const birth = new Date(birthDate).getTime();
  const evaluation = new Date(evaluationDate).getTime();
  return (evaluation - birth) / (1000 * 60 * 60 * 24 * 30.4375);
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

function approximatePercentile(value: number, row: ReferenceRow): number {
  const percentiles: [number, number][] = [
    [3, row.P3],
    [10, row.P10],
    [25, row.P25],
    [50, row.P50],
    [75, row.P75],
    [90, row.P90],
    [97, row.P97],
  ];

  if (value <= percentiles[0][1]) return 3;
  if (value >= percentiles[percentiles.length - 1][1]) return 97;

  for (let i = 0; i < percentiles.length - 1; i++) {
    const [p0, v0] = percentiles[i];
    const [p1, v1] = percentiles[i + 1];
    if (value >= v0 && value <= v1) {
      const ratio = (value - v0) / (v1 - v0);
      return Math.round(p0 + ratio * (p1 - p0));
    }
  }
  return 50;
}

function buildChartData(
  referenceRows: ReferenceRow[],
  records: AnthropometricRecord[],
  birthDate: string,
  indicator: GrowthIndicator,
): ChartRow[] {
  const athleteMap = new Map<number, { value: number; date: string }>();

  for (const record of records) {
    const ageMonths = ageMonthsFromDates(birthDate, record.evaluation_date);
    const value = getAthleteValue(record, indicator);
    if (value !== null) {
      const rounded = Math.round(ageMonths * 2) / 2;
      athleteMap.set(rounded, { value, date: record.evaluation_date });
    }
  }

  const chartData: ChartRow[] = referenceRows.map((row) => {
    const rounded = Math.round(row.age * 2) / 2;
    const athletePoint = athleteMap.get(rounded);
    const nearest = findNearestAthlete(row.age, records, birthDate, indicator);

    return {
      age_months: row.age,
      P3: row.P3,
      P10: row.P10,
      P25: row.P25,
      P50: row.P50,
      P75: row.P75,
      P90: row.P90,
      P97: row.P97,
      athleteValue: athletePoint?.value ?? nearest ?? null,
      evaluationDate: athletePoint?.date ?? null,
    };
  });

  for (const record of records) {
    const ageMonths = ageMonthsFromDates(birthDate, record.evaluation_date);
    const value = getAthleteValue(record, indicator);
    if (value === null) continue;

    const existsInRef = referenceRows.some(
      (row) => Math.abs(row.age - ageMonths) < 0.3,
    );
    if (!existsInRef) {
      chartData.push({
        age_months: ageMonths,
        P3: 0,
        P10: 0,
        P25: 0,
        P50: 0,
        P75: 0,
        P90: 0,
        P97: 0,
        athleteValue: value,
        evaluationDate: record.evaluation_date,
      });
    }
  }

  return chartData.sort((a, b) => a.age_months - b.age_months);
}

function findNearestAthlete(
  ageMonths: number,
  records: AnthropometricRecord[],
  birthDate: string,
  indicator: GrowthIndicator,
): number | null {
  const TOLERANCE = 0.6;
  for (const record of records) {
    const recAge = ageMonthsFromDates(birthDate, record.evaluation_date);
    if (Math.abs(recAge - ageMonths) <= TOLERANCE) {
      return getAthleteValue(record, indicator);
    }
  }
  return null;
}

function formatAgeAxis(ageMonths: number): string {
  return `${(ageMonths / 12).toFixed(1)} a`;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  const athleteEntry = payload.find((p) => p.dataKey === "athleteValue");
  if (!athleteEntry || athleteEntry.value === null) return null;

  const row = athleteEntry.payload;
  const ageYears = (label ?? row.age_months) / 12;

  const refRow: ReferenceRow | undefined = {
    age: row.age_months,
    L: 1,
    M: row.P50,
    S: 0.05,
    P3: row.P3,
    P10: row.P10,
    P25: row.P25,
    P50: row.P50,
    P75: row.P75,
    P90: row.P90,
    P97: row.P97,
  };

  const approxPercentile = refRow
    ? approximatePercentile(athleteEntry.value, refRow)
    : null;

  return (
    <div className="rounded border border-slate-200 bg-white p-2 text-xs shadow">
      {row.evaluationDate && (
        <p className="font-medium text-slate-700">
          Medicion: {row.evaluationDate}
        </p>
      )}
      <p className="text-slate-600">Edad: {ageYears.toFixed(1)} anos</p>
      <p className="text-blue-700 font-medium">
        Valor: {athleteEntry.value.toFixed(1)}
      </p>
      {approxPercentile !== null && (
        <p className="text-slate-600">
          Percentil aprox.: P{approxPercentile}
        </p>
      )}
    </div>
  );
}

export function PercentileCurves({
  sex,
  birthDate,
  records,
  indicator,
  phvAgeMonths,
}: PercentileCurvesProps) {
  const referenceRows = getReferenceData(sex, indicator);

  if (referenceRows.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-slate-500">
        No hay datos de referencia disponibles para este indicador.
      </p>
    );
  }

  const chartData = buildChartData(referenceRows, records, birthDate, indicator);
  const unit = INDICATOR_UNITS[indicator];
  const yLabel = INDICATOR_LABELS[indicator];

  return (
    <div>
      <p className="mb-1 text-xs text-slate-500 text-right">{yLabel}</p>
      <ResponsiveContainer width="100%" height={480}>
        <ComposedChart
          data={chartData}
          margin={{ top: 8, right: 56, left: 8, bottom: 8 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="age_months"
            type="number"
            scale="linear"
            domain={["dataMin", "dataMax"]}
            tickFormatter={formatAgeAxis}
            tick={{ fontSize: 11 }}
            label={{ value: "Edad", position: "insideBottom", offset: -4, fontSize: 11 }}
          />
          <YAxis
            tick={{ fontSize: 11 }}
            domain={["auto", "auto"]}
            unit={unit}
            width={52}
          />
          <Tooltip content={<CustomTooltip />} />

          {/* SD -3 y +3 (P3 y P97) — rojo sólido */}
          <Line
            type="monotone"
            dataKey="P3"
            stroke="#dc2626"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
            name="SD-3 (P3)"
          />
          <Line
            type="monotone"
            dataKey="P97"
            stroke="#dc2626"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
            name="SD+3 (P97)"
          />

          {/* SD -2 y +2 (P10 y P90) — rojo punteado */}
          <Line
            type="monotone"
            dataKey="P10"
            stroke="#dc2626"
            strokeWidth={1}
            strokeDasharray="4 4"
            dot={false}
            isAnimationActive={false}
            name="SD-2 (P10)"
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
          />

          {/* SD -1 y +1 (P25 y P75) — amarillo sólido */}
          <Line
            type="monotone"
            dataKey="P25"
            stroke="#ca8a04"
            strokeWidth={1}
            dot={false}
            isAnimationActive={false}
            name="SD-1 (P25)"
          />
          <Line
            type="monotone"
            dataKey="P75"
            stroke="#ca8a04"
            strokeWidth={1}
            dot={false}
            isAnimationActive={false}
            name="SD+1 (P75)"
          />

          {/* Mediana P50 — verde sólido */}
          <Line
            type="monotone"
            dataKey="P50"
            stroke="#16a34a"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            name="Mediana (P50)"
          />

          {/* Línea/puntos del atleta — azul */}
          <Line
            type="monotone"
            dataKey="athleteValue"
            stroke="#2563eb"
            strokeWidth={2.5}
            dot={{ r: 4, fill: "#2563eb", stroke: "#1d4ed8" }}
            connectNulls={false}
            isAnimationActive={false}
            name="Atleta"
          />

          {/* Marcador vertical PHV */}
          {phvAgeMonths !== undefined && (
            <ReferenceLine
              x={phvAgeMonths}
              stroke="#7c3aed"
              strokeDasharray="5 3"
              strokeWidth={1.5}
              label={{
                value: "PHV",
                position: "top",
                fontSize: 11,
                fill: "#7c3aed",
              }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
