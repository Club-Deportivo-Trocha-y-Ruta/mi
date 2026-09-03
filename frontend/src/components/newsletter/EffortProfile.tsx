/**
 * EffortProfile — "Perfil de esfuerzo": barras semanales de sesiones
 * planificadas vs. asistidas (la "altimetría" del mes), feature 038, T301.
 *
 * Reglas del skill `dataviz` aplicadas:
 *   - Un solo eje (conteo de sesiones). `mean_rpe` es una escala distinta
 *     (0-10 OMNI) — nunca comparte eje: solo aparece en el tooltip y en la
 *     tabla de texto alternativa, jamás como segunda línea/eje.
 *   - Color por el rol de la marca, no cíclico: "Asistidas" usa el acento
 *     único de marca (`--color-primary`, la serie "self" del design
 *     system — docs/05-design-system/design.md §2); "Planificadas" es un
 *     gris neutro (objetivo/target), no una segunda identidad categórica.
 *   - Leyenda siempre presente con 2+ series; barras <=24px, extremo
 *     redondeado 4px, base cuadrada; grid solo horizontal, hairline, gris
 *     recesivo.
 *   - Alternativa de tabla `sr-only` (mismo patrón que
 *     `PercentileCurves.tsx`) — cubre además el RPE, que el gráfico no
 *     representa visualmente.
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { EffortWeek } from "@/types/stageLog.types";

export interface EffortProfileProps {
  weeks: EffortWeek[];
}

interface TooltipLikeProps {
  active?: boolean;
  payload?: Array<{ payload?: unknown }>;
}

function EffortTooltip({ active, payload }: TooltipLikeProps) {
  if (!active || !payload || payload.length === 0) return null;
  const week = payload[0].payload as EffortWeek;
  return (
    <div className="rounded-lg bg-white px-3 py-2 text-xs shadow-ambient">
      <p className="font-semibold text-charcoal">{week.week_label}</p>
      <p className="text-mid-gray">
        {week.sessions_attended} de {week.sessions_planned} sesiones
      </p>
      {week.mean_rpe !== null && (
        <p className="text-mid-gray">RPE promedio: {week.mean_rpe.toFixed(1)}</p>
      )}
    </div>
  );
}

function legendLabel(value: string): string {
  return value === "sessions_planned" ? "Planificadas" : "Asistidas";
}

export function EffortProfile({ weeks }: EffortProfileProps) {
  if (weeks.length === 0) return null;

  return (
    <section aria-label="Perfil de esfuerzo" data-testid="effort-profile">
      <h3 className="font-display text-base font-semibold text-charcoal">
        Perfil de esfuerzo
      </h3>
      <p className="mt-0.5 text-xs text-mid-gray">
        Sesiones planificadas frente a sesiones asistidas, semana a semana.
      </p>
      <div className="mt-2 h-56 w-full" data-testid="effort-profile-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={weeks}
            barGap={4}
            margin={{ top: 8, right: 8, bottom: 4, left: -16 }}
          >
            <CartesianGrid stroke="var(--color-border-gray)" vertical={false} />
            <XAxis
              dataKey="week_label"
              tick={{ fontSize: 11, fill: "var(--color-mid-gray)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--color-border-gray)" }}
            />
            <YAxis
              allowDecimals={false}
              tick={{ fontSize: 11, fill: "var(--color-mid-gray)" }}
              tickLine={false}
              axisLine={false}
              width={28}
            />
            <Tooltip
              content={(props: unknown) => (
                <EffortTooltip {...(props as TooltipLikeProps)} />
              )}
            />
            <Legend
              wrapperStyle={{ fontSize: 12, color: "var(--color-mid-gray)" }}
              formatter={legendLabel}
            />
            <Bar
              dataKey="sessions_planned"
              name="sessions_planned"
              fill="var(--color-light-gray)"
              stroke="var(--color-border-gray)"
              radius={[4, 4, 0, 0]}
              maxBarSize={24}
              isAnimationActive={false}
            />
            <Bar
              dataKey="sessions_attended"
              name="sessions_attended"
              fill="var(--color-primary)"
              radius={[4, 4, 0, 0]}
              maxBarSize={24}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Alternativa textual WCAG 2.1 AA — incluye RPE, ausente del gráfico */}
      <table className="sr-only" aria-label="Datos de perfil de esfuerzo semanal">
        <thead>
          <tr>
            <th scope="col">Semana</th>
            <th scope="col">Sesiones planificadas</th>
            <th scope="col">Sesiones asistidas</th>
            <th scope="col">RPE promedio</th>
          </tr>
        </thead>
        <tbody>
          {weeks.map((w, idx) => (
            <tr key={idx}>
              <td>{w.week_label}</td>
              <td>{w.sessions_planned}</td>
              <td>{w.sessions_attended}</td>
              <td>{w.mean_rpe !== null ? w.mean_rpe.toFixed(1) : "Sin dato"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
