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
/**
 * `isChampionship` viene de `EvolutionPoint.series_kind` (siempre presente
 * en este endpoint — feature 014/016), no del `valida_num === 99` retirado
 * (feature 036, T030): un campeonato moderno trae su propio `valida_num` de
 * secuencia dentro de la serie y aun así debe leerse "Cto." en el tooltip.
 *
 * Fix F-2 (integration-review.md) — el nivel del campeonato viene de
 * `EvolutionPoint.series_level` (`"departmental"` | `"national"`, feature
 * 039). Antes se devolvía `"CD"` sin condicionar, así que un campeonato
 * nacional aislado (temporada con `groups.length <= 1`, el único caso en
 * que el filtro de copa no se activa y un punto de campeonato llega hasta
 * acá) mostraba la etiqueta equivocada. `series_level` ausente (fixtures
 * previas a la feature) cae al default "departmental" — mismo criterio que
 * `championshipDotLabel` en `EvolutionChart.tsx`.
 */
export function romanForValida(
  num: number,
  isChampionship: boolean,
  seriesLevel?: string,
): string {
  if (isChampionship) return seriesLevel === "national" ? "CN" : "CD";
  if (num === 0) return "Σ";
  return ROMAN[num] ?? String(num);
}

export function MiniSparkline({ athleteId }: MiniSparklineProps) {
  const season = getCurrentSeason();
  const query = useAthleteEvolution(athleteId, season, EvolutionMetric.RANKING);

  const groups = query.data?.groups ?? [];
  const firstCupGroup = groups.find((g) => g.kind === "cup");
  // Feature 039 (research.md D5/D11) — el sparkline solo lee la copa: un
  // campeonato es una carrera suelta, no "una válida más" de la tendencia.
  // Solo activamos el filtro cuando la temporada trae más de un grupo
  // (multi-copa/campeonato) — con 0-1 grupos no hay nada que separar y
  // preservamos el comportamiento anterior a la feature (fixtures cuyos
  // puntos no traen `series_id` por punto, p. ej.
  // `cupAndChampionshipConflictHandler`).
  const seasonHasOnlyChampionships = groups.length > 1 && !firstCupGroup;

  const chartData = useMemo(() => {
    if (!query.data) return [];
    let source = query.data.series;
    if (groups.length > 1) {
      if (!firstCupGroup) {
        source = [];
      } else {
        const filtered = query.data.series.filter(
          (p) => p.series_id === firstCupGroup.series_id,
        );
        source = filtered.length > 0 ? filtered : query.data.series;
      }
    }
    return source
      .filter((p) => p.value !== null)
      .map((p) => ({
        roman: romanForValida(
          p.valida_num,
          p.series_kind === "championship",
          p.series_level,
        ),
        value: p.value as number,
      }));
  }, [query.data, groups.length, firstCupGroup]);

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

  // Empty state feature 039 — la temporada solo tiene campeonatos, ninguna
  // copa (research.md D13): distinto del "faltan datos" genérico de abajo.
  if (seasonHasOnlyChampionships) {
    return (
      <div
        data-testid="mini-evolution-sparkline"
        className="rounded-xl bg-white px-4 py-5 text-center shadow-card"
      >
        <p className="text-xs text-mid-gray">
          Sin válidas de copa en esta temporada.
        </p>
      </div>
    );
  }

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
