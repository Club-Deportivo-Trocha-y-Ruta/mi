import type { AnthropometricRecord } from "@/types/anthropometry.types";
import { getBandSpec, type BandColor } from "@/lib/growth/bands";
import { useGrowthMetrics } from "@/hooks/athletes/useGrowthMetrics";

interface NutritionalClassificationProps {
  record: AnthropometricRecord;
  sex: "M" | "F";
  birthDate: string;
}

interface ClassificationResult {
  label: string;
  color: BandColor;
  zScore: number;
  percentile: number;
}

const COLOR_DOT: Record<BandColor, string> = {
  green: "bg-green-500",
  yellow: "bg-yellow-400",
  orange: "bg-orange-500",
  red: "bg-red-600",
  blue: "bg-blue-500",
};

const COLOR_TEXT: Record<BandColor, string> = {
  green: "text-green-700",
  yellow: "text-yellow-700",
  orange: "text-orange-700",
  red: "text-red-700",
  blue: "text-blue-700",
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
  const heightMetrics = useGrowthMetrics({ record, sex, birthDate, indicator: "height_for_age" });
  const bmiMetrics = useGrowthMetrics({ record, sex, birthDate, indicator: "bmi_for_age" });

  const heightResult: ClassificationResult | null = heightMetrics
    ? {
        ...getBandSpec("height_for_age", heightMetrics.band),
        zScore: heightMetrics.zScore,
        percentile: heightMetrics.percentile,
      }
    : null;

  const bmiResult: ClassificationResult | null = bmiMetrics
    ? {
        ...getBandSpec("bmi_for_age", bmiMetrics.band),
        zScore: bmiMetrics.zScore,
        percentile: bmiMetrics.percentile,
      }
    : null;

  return (
    <div
      className="rounded-xl bg-white p-5 shadow-card"
    >
      <h4
        className="mb-4 text-sm text-charcoal font-heading tracking-[0.2px]"
      >
        Clasificación Nutricional{" "}
        <span
          className="font-normal text-mid-gray"
          style={{ fontFamily: "Inter, system-ui, sans-serif" }}
        >
          (Res. 2465/2016)
        </span>
      </h4>

      <div>
        <ClassificationRow indicatorLabel="Talla/Edad" result={heightResult} />
        <div>
          <ClassificationRow indicatorLabel="IMC/Edad" result={bmiResult} />
        </div>
      </div>

      <div
        className="mt-3 space-y-1 pt-3"
      >
        <p className="text-xs text-mid-gray">
          Fuente: OMS 2007 / Res. 2465/2016 — MinSalud Colombia
        </p>
        <p className="text-xs text-mid-gray">
          El IMC puede subestimar adiposidad en atletas. Úsese como referencia.
        </p>
      </div>
    </div>
  );
}
