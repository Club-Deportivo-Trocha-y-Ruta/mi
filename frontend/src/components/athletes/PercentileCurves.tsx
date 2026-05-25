/**
 * PercentileCurves — chart de percentiles WHO/CDC con marker PHV.
 *
 * Estructura (post-B5):
 *  - `lib/growth/percentileChart.ts` → helpers puros (buildChartData,
 *    computeDomain, classifyBand, makeCustomTooltip, etc).
 *  - `hooks/athletes/usePercentileChartData.ts` → memoiza data + dominio.
 *  - `BioAgeToggle`, `PhvInfoPopover` → sub-componentes UI.
 *
 * Este componente queda como el "orquestador": dispone los recharts elements
 * (Lines/Areas/ReferenceLine) y la leyenda interactiva.
 */
import { useMemo, useState } from "react";
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

import { usePercentileChartData } from "@/hooks/athletes/usePercentileChartData";
import {
  ALL_BAND_KEYS,
  BAND_CONFIGS,
  INDICATOR_LABELS,
  INDICATOR_PHV_NOTES,
  LEGEND_ORDER,
  formatMonthYear,
  getMaturationMarker,
  makeCustomTooltip,
  percentileFromZ,
  zScoreFromLMS,
  type GrowthIndicator,
  type LegendOrderKey,
} from "@/lib/growth/percentileChart";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import { UserRole } from "@/types/enums";
import { useAuthStore } from "@/store/auth.store";
import { BioAgeToggle } from "./BioAgeToggle";
import { PhvInfoPopover } from "./PhvInfoPopover";
import { PercentileInterpretationBlock } from "./PercentileInterpretationBlock";

export type { GrowthIndicator } from "@/lib/growth/percentileChart";

export interface PercentileCurvesProps {
  sex: "M" | "F";
  birthDate: string;
  records: AnthropometricRecord[];
  indicator: GrowthIndicator;
  phvAgeMonths?: number;
}

interface LineStrokePayload {
  strokeWidth?: number;
  strokeDasharray?: string;
}

// ---------------------------------------------------------------------------
// CustomLegend — interactivo (click toggle visibilidad)
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

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

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

  const { rows: chartData, domain: yDomain, referenceLoaded } =
    usePercentileChartData(records, sex, indicator, birthDate);

  const latestRecord =
    records.length > 0
      ? [...records].sort(
          (a, b) =>
            new Date(b.evaluation_date).getTime() -
            new Date(a.evaluation_date).getTime(),
        )[0]
      : null;

  if (!referenceLoaded) {
    return (
      <p className="py-4 text-center text-sm text-mid-gray">
        No hay datos de referencia disponibles para este indicador.
      </p>
    );
  }

  const yLabel = INDICATOR_LABELS[indicator];
  const marker = getMaturationMarker(indicator, sex, phvAgeMonths);
  const phvNote = INDICATOR_PHV_NOTES[indicator];
  const bandConfigs = BAND_CONFIGS[indicator];

  // Estabilizar la referencia del componente de tooltip para evitar remounts en cada render
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
  const markerX =
    useBioAge && phvAgeMonths !== undefined && marker !== null
      ? marker.ageMonths // recharts usa el mismo dataKey age_months; el label cambia
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
          {marker !== null && <PhvInfoPopover note={phvNote} />}
        </span>

        {/* B3.25 — Toggle pill: solo coach/admin, con PHV definido, no en bmi_for_age */}
        {canSeeBioToggle && (
          <BioAgeToggle useBioAge={useBioAge} onChange={setUseBioAge} />
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
