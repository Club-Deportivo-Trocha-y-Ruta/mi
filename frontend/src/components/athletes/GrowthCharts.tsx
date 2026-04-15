import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { AnthropometricRecord } from "@/types/anthropometry.types";
import { PercentileCurves } from "@/components/athletes/PercentileCurves";
import type { GrowthIndicator } from "@/components/athletes/PercentileCurves";

interface GrowthChartsProps {
  records: AnthropometricRecord[];
  sex?: "M" | "F";
  birthDate?: string;
  phvAgeMonths?: number;
}

type ViewMode = "longitudinal" | "percentiles";

interface ChartPoint {
  date: string;
  label: string;
  standingHeight: number;
  weight: number;
  maturityOffset: number;
}

function formatDateLabel(dateStr: string): string {
  const [year, month] = dateStr.split("-");
  return `${month}/${year}`;
}

function formatDateTooltip(dateStr: string): string {
  const [year, month, day] = dateStr.split("-");
  return `${day}/${month}/${year}`;
}

export function GrowthCharts({
  records,
  sex,
  birthDate,
  phvAgeMonths,
}: GrowthChartsProps) {
  const [view, setView] = useState<ViewMode>("longitudinal");
  const [activeIndicator, setActiveIndicator] =
    useState<GrowthIndicator>("height_for_age");

  const canShowPercentiles = sex !== undefined && birthDate !== undefined;

  const viewBtnBase =
    "px-3 py-1.5 text-sm font-medium rounded-md transition-colors";
  const viewBtnActive = "bg-slate-900 text-white";
  const viewBtnInactive =
    "border border-slate-300 text-slate-600 hover:bg-slate-100";

  const indicatorBtnBase =
    "px-3 py-1 text-xs font-medium rounded-full border transition-colors";
  const indicatorBtnActive = "bg-slate-900 text-white border-slate-900";
  const indicatorBtnInactive =
    "border-slate-300 text-slate-600 hover:bg-slate-100";

  const INDICATORS: { key: GrowthIndicator; label: string }[] = [
    { key: "height_for_age", label: "Talla" },
    { key: "bmi_for_age", label: "IMC" },
    { key: "weight_for_age", label: "Peso" },
  ];

  return (
    <div className="space-y-4" data-testid="growth-charts">
      {/* Toggle de vista */}
      <div className="flex gap-2">
        <button
          type="button"
          className={`${viewBtnBase} ${view === "longitudinal" ? viewBtnActive : viewBtnInactive}`}
          onClick={() => setView("longitudinal")}
        >
          Longitudinal
        </button>
        {canShowPercentiles && (
          <button
            type="button"
            className={`${viewBtnBase} ${view === "percentiles" ? viewBtnActive : viewBtnInactive}`}
            onClick={() => setView("percentiles")}
          >
            Curvas de percentiles
          </button>
        )}
      </div>

      {/* Vista longitudinal — sin cambios */}
      {view === "longitudinal" && <LongitudinalCharts records={records} />}

      {/* Vista percentiles */}
      {view === "percentiles" && canShowPercentiles && (
        <div className="space-y-4">
          {/* Selector de indicador */}
          <div className="flex gap-2 flex-wrap">
            {INDICATORS.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                className={`${indicatorBtnBase} ${activeIndicator === key ? indicatorBtnActive : indicatorBtnInactive}`}
                onClick={() => setActiveIndicator(key)}
              >
                {label}
              </button>
            ))}
          </div>
          <PercentileCurves
            sex={sex}
            birthDate={birthDate}
            records={records}
            indicator={activeIndicator}
            phvAgeMonths={phvAgeMonths}
          />
        </div>
      )}
    </div>
  );
}

// Componente interno para la vista longitudinal — lógica original sin cambios
interface LongitudinalChartsProps {
  records: AnthropometricRecord[];
}

function LongitudinalCharts({ records }: LongitudinalChartsProps) {
  if (records.length < 2) {
    return (
      <p className="py-6 text-center text-sm text-slate-500">
        Se necesitan al menos 2 mediciones para generar la grafica.
      </p>
    );
  }

  const sorted = [...records].sort(
    (a, b) =>
      new Date(a.evaluation_date).getTime() -
      new Date(b.evaluation_date).getTime(),
  );

  const data: ChartPoint[] = sorted.map((r) => ({
    date: r.evaluation_date,
    label: formatDateLabel(r.evaluation_date),
    standingHeight: Number(r.standing_height_cm),
    weight: Number(r.weight_kg),
    maturityOffset: Number(r.maturity_offset),
  }));

  return (
    <div className="space-y-6">
      {/* Talla vs Tiempo */}
      <div>
        <h4 className="mb-2 text-sm font-medium text-slate-700">
          Talla vs Tiempo
        </h4>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="label" tick={{ fontSize: 12 }} />
            <YAxis
              tick={{ fontSize: 12 }}
              domain={["dataMin - 2", "dataMax + 2"]}
              unit=" cm"
            />
            <Tooltip
              formatter={(value) => [`${value} cm`, "Talla"]}
              labelFormatter={(_, payload) =>
                payload[0] ? formatDateTooltip(payload[0].payload.date) : ""
              }
            />
            <Line
              type="monotone"
              dataKey="standingHeight"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={{ r: 4 }}
              name="Talla"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Peso vs Tiempo */}
      <div>
        <h4 className="mb-2 text-sm font-medium text-slate-700">
          Peso vs Tiempo
        </h4>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="label" tick={{ fontSize: 12 }} />
            <YAxis
              tick={{ fontSize: 12 }}
              domain={["dataMin - 2", "dataMax + 2"]}
              unit=" kg"
            />
            <Tooltip
              formatter={(value) => [`${value} kg`, "Peso"]}
              labelFormatter={(_, payload) =>
                payload[0] ? formatDateTooltip(payload[0].payload.date) : ""
              }
            />
            <Line
              type="monotone"
              dataKey="weight"
              stroke="#22c55e"
              strokeWidth={2}
              dot={{ r: 4 }}
              name="Peso"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Maturity Offset vs Tiempo */}
      <div>
        <h4 className="mb-2 text-sm font-medium text-slate-700">
          Maturity Offset vs Tiempo
        </h4>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="label" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} domain={["auto", "auto"]} />
            <Tooltip
              formatter={(value) => [
                Number(value) > 0 ? `+${value}` : `${value}`,
                "Offset",
              ]}
              labelFormatter={(_, payload) =>
                payload[0] ? formatDateTooltip(payload[0].payload.date) : ""
              }
            />
            <ReferenceLine
              y={0}
              stroke="#94a3b8"
              strokeDasharray="4 4"
              label={{ value: "PHV", position: "right", fontSize: 11 }}
            />
            <ReferenceLine
              y={-1}
              stroke="#22c55e"
              strokeDasharray="4 4"
              label={{ value: "Pre-PHV", position: "right", fontSize: 10 }}
            />
            <ReferenceLine
              y={1}
              stroke="#3b82f6"
              strokeDasharray="4 4"
              label={{ value: "Post-PHV", position: "right", fontSize: 10 }}
            />
            <Line
              type="monotone"
              dataKey="maturityOffset"
              stroke="#8b5cf6"
              strokeWidth={2}
              dot={{ r: 4 }}
              name="Offset"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
