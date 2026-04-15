import growthData from "@/data/growth-reference-cdc.json";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

interface NutritionalClassificationProps {
  record: AnthropometricRecord;
  sex: "M" | "F";
  birthDate: string;
}

interface ClassificationResult {
  label: string;
  color: "green" | "yellow" | "orange" | "red";
  zScore: number;
  percentile: number;
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

function ageMonthsFromDates(birthDate: string, evaluationDate: string): number {
  const birth = new Date(birthDate).getTime();
  const evaluation = new Date(evaluationDate).getTime();
  return (evaluation - birth) / (1000 * 60 * 60 * 24 * 30.4375);
}

function findNearestRow(rows: ReferenceRow[], ageMonths: number): ReferenceRow | null {
  if (rows.length === 0) return null;
  return rows.reduce((best, row) =>
    Math.abs(row.age - ageMonths) < Math.abs(best.age - ageMonths) ? row : best,
  );
}

function computeZScore(value: number, row: ReferenceRow): number {
  if (row.L === 0) {
    return Math.log(value / row.M) / row.S;
  }
  return (Math.pow(value / row.M, row.L) - 1) / (row.L * row.S);
}

function zScoreToPercentile(z: number): number {
  const clamped = Math.max(-3.5, Math.min(3.5, z));
  const t = 1 / (1 + 0.2316419 * Math.abs(clamped));
  const poly =
    0.319381530 * t -
    0.356563782 * t * t +
    1.781477937 * t * t * t -
    1.821255978 * t * t * t * t +
    1.330274429 * t * t * t * t * t;
  const pdf = Math.exp(-0.5 * clamped * clamped) / Math.sqrt(2 * Math.PI);
  const cumulative = 1 - pdf * poly;
  const result = clamped >= 0 ? cumulative : 1 - cumulative;
  return Math.max(1, Math.min(99, Math.round(result * 100)));
}

function getReferenceRows(
  sex: "M" | "F",
  indicator: "height_for_age" | "bmi_for_age" | "weight_for_age",
): ReferenceRow[] {
  const indicatorData = growthData.indicators[indicator] as Record<string, ReferenceRow[]>;
  return indicatorData[sex] ?? [];
}

function classifyHeight(z: number): ClassificationResult["label"] {
  if (z < -3) return "Talla muy baja";
  if (z < -2) return "Talla baja";
  if (z < -1) return "Riesgo talla baja";
  return "Talla adecuada";
}

function classifyHeightColor(z: number): ClassificationResult["color"] {
  if (z < -3) return "red";
  if (z < -2) return "orange";
  if (z < -1) return "yellow";
  return "green";
}

function classifyBmi(z: number): ClassificationResult["label"] {
  if (z < -3) return "Delgadez severa";
  if (z < -2) return "Delgadez";
  if (z < 1) return "Adecuado";
  if (z < 2) return "Sobrepeso";
  return "Obesidad";
}

function classifyBmiColor(z: number): ClassificationResult["color"] {
  if (z < -3) return "red";
  if (z < -2) return "orange";
  if (z < 1) return "green";
  if (z < 2) return "yellow";
  return "red";
}

function computeClassification(
  value: number | null,
  backendZ: number | null,
  backendPercentile: number | null,
  rows: ReferenceRow[],
  ageMonths: number,
  classifyLabel: (z: number) => string,
  classifyColor: (z: number) => ClassificationResult["color"],
): ClassificationResult | null {
  if (value === null) return null;

  let z: number;
  let percentile: number;

  if (backendZ !== null && backendPercentile !== null) {
    z = Number(backendZ);
    percentile = Number(backendPercentile);
  } else {
    const row = findNearestRow(rows, ageMonths);
    if (!row) return null;
    z = computeZScore(value, row);
    percentile = zScoreToPercentile(z);
  }

  return {
    label: classifyLabel(z),
    color: classifyColor(z),
    zScore: z,
    percentile,
  };
}

const COLOR_DOT: Record<ClassificationResult["color"], string> = {
  green: "bg-green-500",
  yellow: "bg-yellow-400",
  orange: "bg-orange-500",
  red: "bg-red-600",
};

const COLOR_TEXT: Record<ClassificationResult["color"], string> = {
  green: "text-green-700",
  yellow: "text-yellow-700",
  orange: "text-orange-700",
  red: "text-red-700",
};

interface ClassificationRowProps {
  indicatorLabel: string;
  result: ClassificationResult | null;
}

function ClassificationRow({ indicatorLabel, result }: ClassificationRowProps) {
  if (!result) {
    return (
      <div className="flex items-center gap-3 py-2">
        <span className="w-28 shrink-0 text-sm text-mid-gray">{indicatorLabel}:</span>
        <span className="text-sm text-mid-gray">Sin datos</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 py-2">
      <span className="w-28 shrink-0 text-sm text-mid-gray">{indicatorLabel}:</span>
      <span
        className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${COLOR_DOT[result.color]}`}
        aria-label={result.color}
      />
      <span className={`text-sm font-medium ${COLOR_TEXT[result.color]}`}>
        {result.label}
      </span>
      <span className="ml-auto text-xs tabular-nums text-mid-gray">
        Z={result.zScore >= 0 ? "+" : ""}{result.zScore.toFixed(2)}{" "}
        (P{result.percentile})
      </span>
    </div>
  );
}

export function NutritionalClassification({
  record,
  sex,
  birthDate,
}: NutritionalClassificationProps) {
  const ageMonths = ageMonthsFromDates(birthDate, record.evaluation_date);

  const heightRows = getReferenceRows(sex, "height_for_age");
  const bmiRows = getReferenceRows(sex, "bmi_for_age");

  const bmiValue: number | null =
    (record.bmi !== undefined && record.bmi !== null)
      ? record.bmi
      : (() => {
          const heightM = record.standing_height_cm / 100;
          return heightM > 0 ? record.weight_kg / (heightM * heightM) : null;
        })();

  const heightResult = computeClassification(
    record.standing_height_cm,
    record.height_z_score !== undefined ? (record.height_z_score ?? null) : null,
    record.height_percentile !== undefined ? (record.height_percentile ?? null) : null,
    heightRows,
    ageMonths,
    classifyHeight,
    classifyHeightColor,
  );

  const bmiResult = computeClassification(
    bmiValue,
    record.bmi_z_score !== undefined ? (record.bmi_z_score ?? null) : null,
    record.bmi_percentile !== undefined ? (record.bmi_percentile ?? null) : null,
    bmiRows,
    ageMonths,
    classifyBmi,
    classifyBmiColor,
  );

  return (
    <div
      className="rounded-xl bg-white p-5"
      style={{ boxShadow: "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px" }}
    >
      <h4
        className="mb-4 text-sm text-charcoal"
        style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600, letterSpacing: "0.2px" }}
      >
        Clasificación Nutricional{" "}
        <span
          className="font-normal text-mid-gray"
          style={{ fontFamily: "Inter, system-ui, sans-serif" }}
        >
          (Res. 2465/2016)
        </span>
      </h4>

      <div style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}>
        <ClassificationRow indicatorLabel="Talla/Edad" result={heightResult} />
        <div style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}>
          <ClassificationRow indicatorLabel="IMC/Edad" result={bmiResult} />
        </div>
      </div>

      <div
        className="mt-3 space-y-1 pt-3"
        style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
      >
        <p className="text-xs text-mid-gray">
          Fuente: CDC 2000 / Res. 2465/2016 — MinSalud Colombia
        </p>
        <p className="text-xs text-mid-gray">
          El IMC puede subestimar adiposidad en atletas. Úsese como referencia.
        </p>
      </div>
    </div>
  );
}
