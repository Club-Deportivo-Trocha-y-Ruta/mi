/**
 * MiniSparkline — gráfico compacto de evolución posición/ranking para el
 * tab Panorama del atleta.
 *
 * Usa ``useAthleteEvolution`` con métrica ``ranking`` (posición en categoría),
 * temporada actual. El eje Y está invertido (menor posición = mejor).
 *
 * Altura fija 120px, sin grid, sin labels de eje X → lectura rápida de
 * tendencia sin sobrecarga cognitiva.
 *
 * Privacidad: ningún dato PII — solo métricas agregadas de posición.
 */
import { useMemo } from "react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import { Skeleton } from "@/components/ui/skeleton";
import { useAthleteEvolution } from "@/hooks/athletes/useAthleteEvolution";
import { EvolutionMetric } from "@/types/athleteRaceAnalysis.types";

interface MiniSparklineProps {
  athleteId: number;
}

function getCurrentSeason(): number {
  return new Date().getFullYear();
}

const ROMAN: Record<number, string> = {
  1: "I", 2: "II", 3: "III", 4: "IV",
  5: "V", 6: "VI", 7: "VII",
};
function romanForValida(num: number): string {
  if (num === 99) return "CD";
  if (num === 0) return "Σ";
  return ROMAN[num] ?? String(num);
}

export function MiniSparkline({ athleteId }: MiniSparklineProps) {
  const season = getCurrentSeason();
  const query = useAthleteEvolution(athleteId, season, EvolutionMetric.RANKING);

  const chartData = useMemo(() => {
    if (!query.data) return [];
    return query.data.series
      .filter((p) => p.value !== null)
      .map((p) => ({
        roman: romanForValida(p.valida_num),
        value: p.value as number,
      }));
  }, [query.data]);

  if (query.isLoading) {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label="Cargando sparkline de evolución"
        data-testid="mini-evolution-sparkline"
        className="rounded-xl bg-white p-4 shadow-card"
      >
        <Skeleton className="h-[120px] w-full rounded-lg" />
      </div>
    );
  }

  // Error silencioso — Panorama no debe bloquearse por un error del sparkline.
  if (query.isError) return null;

  // Empty state: menos de 2 puntos.
  if (chartData.length < 2) {
    return (
      <div
        data-testid="mini-evolution-sparkline"
        className="rounded-xl bg-white px-4 py-5 text-center shadow-card"
      >
        <p className="text-xs text-mid-gray">
          Necesitas al menos 2 análisis para ver evolución.
        </p>
      </div>
    );
  }

  return (
    <div
      data-testid="mini-evolution-sparkline"
      className="rounded-xl bg-white p-4 shadow-card"
      aria-label="Sparkline de evolución de posición en categoría"
    >
      <p
        className="font-display mb-2 text-[11px] font-medium uppercase tracking-wide text-mid-gray"
      >
        Evolución posición — {season}
      </p>
      <ResponsiveContainer width="100%" height={120}>
        <LineChart
          data={chartData}
          margin={{ top: 8, right: 8, bottom: 4, left: 8 }}
        >
          {/* Eje Y invertido: posición 1 arriba (mejor) */}
          <Tooltip
            content={(props: unknown) => {
              const p = props as { active?: boolean; payload?: Array<{ payload?: { roman: string; value: number } }> };
              if (!p.active || !p.payload?.length) return null;
              const pt = p.payload[0]?.payload;
              if (!pt) return null;
              return (
                <div
                  className="rounded-lg bg-white px-2 py-1 text-xs shadow-md"
                >
                  <span className="font-semibold text-charcoal">V-{pt.roman}</span>
                  {" "}
                  <span className="text-mid-gray">P{pt.value}</span>
                </div>
              );
            }}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#131316"
            strokeWidth={2}
            dot={{ r: 3, fill: "#131316" }}
            activeDot={{ r: 5 }}
            // reversed: 1 arriba (mejor posición)
            yAxisId={0}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
