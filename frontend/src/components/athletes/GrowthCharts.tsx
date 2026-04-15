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
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
            view === "longitudinal"
              ? "bg-charcoal text-white"
              : "bg-white text-mid-gray hover:text-charcoal"
          }`}
          style={view !== "longitudinal" ? { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" } : undefined}
          onClick={() => setView("longitudinal")}
        >
          Longitudinal
        </button>
        {canShowPercentiles && (
          <button
            type="button"
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              view === "percentiles"
                ? "bg-charcoal text-white"
                : "bg-white text-mid-gray hover:text-charcoal"
            }`}
            style={view !== "percentiles" ? { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" } : undefined}
            onClick={() => setView("percentiles")}
          >
            Curvas de percentiles
          </button>
        )}
      </div>

      {/* Vista longitudinal */}
      {view === "longitudinal" && <LongitudinalCharts records={records} />}

      {/* Vista percentiles */}
      {view === "percentiles" && canShowPercentiles && (
        <div className="space-y-4">
          {/* Selector de indicador — pill buttons */}
          <div className="flex flex-wrap gap-2">
            {INDICATORS.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  activeIndicator === key
                    ? "bg-charcoal text-white"
                    : "bg-white text-mid-gray hover:text-charcoal"
                }`}
                style={activeIndicator !== key ? { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" } : undefined}
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

// Componente interno para la vista longitudinal
interface LongitudinalChartsProps {
  records: AnthropometricRecord[];
}

function LongitudinalCharts({ records }: LongitudinalChartsProps) {
  if (records.length < 2) {
    return (
      <p className="py-6 text-center text-sm text-mid-gray">
        Se necesitan al menos 2 mediciones para generar la gráfica.
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
        <h4 className="mb-2 text-sm font-medium text-mid-gray">
          Talla vs Tiempo
        </h4>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(34,42,53,0.08)" />
            <XAxis dataKey="label" tick={{ fontSize: 12, fill: "#898989" }} />
            <YAxis
              tick={{ fontSize: 12, fill: "#898989" }}
              domain={["dataMin - 2", "dataMax + 2"]}
              unit=" cm"
            />
            <Tooltip
              formatter={(value) => [`${value} cm`, "Talla"]}
              labelFormatter={(_, payload) =>
                payload[0] ? formatDateTooltip(payload[0].payload.date) : ""
              }
              contentStyle={{
                borderRadius: "8px",
                border: "none",
                boxShadow:
                  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
              }}
            />
            <Line
              type="monotone"
              dataKey="standingHeight"
              stroke="#242424"
              strokeWidth={2}
              dot={{ r: 4, fill: "#242424" }}
              name="Talla"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Peso vs Tiempo */}
      <div>
        <h4 className="mb-2 text-sm font-medium text-mid-gray">
          Peso vs Tiempo
        </h4>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(34,42,53,0.08)" />
            <XAxis dataKey="label" tick={{ fontSize: 12, fill: "#898989" }} />
            <YAxis
              tick={{ fontSize: 12, fill: "#898989" }}
              domain={["dataMin - 2", "dataMax + 2"]}
              unit=" kg"
            />
            <Tooltip
              formatter={(value) => [`${value} kg`, "Peso"]}
              labelFormatter={(_, payload) =>
                payload[0] ? formatDateTooltip(payload[0].payload.date) : ""
              }
              contentStyle={{
                borderRadius: "8px",
                border: "none",
                boxShadow:
                  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
              }}
            />
            <Line
              type="monotone"
              dataKey="weight"
              stroke="#898989"
              strokeWidth={2}
              dot={{ r: 4, fill: "#898989" }}
              name="Peso"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Maturity Offset vs Tiempo */}
      <div>
        <h4 className="mb-2 text-sm font-medium text-mid-gray">
          Maturity Offset vs Tiempo
        </h4>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={data} margin={{ top: 5, right: 64, left: 5, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(34,42,53,0.08)" />
            <XAxis dataKey="label" tick={{ fontSize: 12, fill: "#898989" }} />
            <YAxis tick={{ fontSize: 12, fill: "#898989" }} domain={["auto", "auto"]} />
            <Tooltip
              formatter={(value) => [
                Number(value) > 0 ? `+${value}` : `${value}`,
                "Offset",
              ]}
              labelFormatter={(_, payload) =>
                payload[0] ? formatDateTooltip(payload[0].payload.date) : ""
              }
              contentStyle={{
                borderRadius: "8px",
                border: "none",
                boxShadow:
                  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
              }}
            />
            <ReferenceLine
              y={0}
              stroke="rgba(34,42,53,0.3)"
              strokeDasharray="4 4"
              label={{ value: "PHV", position: "right", fontSize: 11, fill: "#898989" }}
            />
            <ReferenceLine
              y={-1}
              stroke="rgba(34,42,53,0.2)"
              strokeDasharray="4 4"
              label={{ value: "Pre-PHV", position: "right", fontSize: 10, fill: "#898989" }}
            />
            <ReferenceLine
              y={1}
              stroke="rgba(34,42,53,0.2)"
              strokeDasharray="4 4"
              label={{ value: "Post-PHV", position: "right", fontSize: 10, fill: "#898989" }}
            />
            <Line
              type="monotone"
              dataKey="maturityOffset"
              stroke="#242424"
              strokeWidth={2}
              dot={{ r: 4, fill: "#242424" }}
              name="Offset"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
