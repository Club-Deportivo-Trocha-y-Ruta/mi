import { Info } from "lucide-react";

import type { ParentMonthlySummary } from "@/types/trainingSession.types";
import { rubricToLabel, RUBRIC_TONE, showsRubricToParent } from "@/lib/parentMetrics";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface MonthlyAveragesBannerProps {
  summary: ParentMonthlySummary | undefined;
  athleteAgeDecimal: number | null;
  isLoading: boolean;
  isError: boolean;
  monthLabel: string;
  athleteName: string;
}

// Wave 5: el padre lee mejor "12 de 20 entrenos" que "60%". El número crudo
// con denominador da contexto (¿20 fueron muchas o pocas?), el porcentaje
// abstracto solo se usa como referencia secundaria.
function AttendanceMeter({ percentage }: { percentage: number }) {
  const pct = Math.min(100, Math.max(0, percentage));
  // Wave 5: <50% deja de ser rojo (estigma). Se mantiene ámbar y se
  // acompaña con copy pedagógico aparte ("ausencias justificadas son parte
  // del cuidado") — el rojo lo reservamos para alertas reales del coach.
  const color = pct >= 75 ? "bg-green-500" : "bg-amber-400";
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-light-gray" aria-hidden="true">
      <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-3" aria-hidden="true">
      <div className="h-4 w-1/3 animate-pulse rounded bg-light-gray" />
      <div className="h-2 w-full animate-pulse rounded-full bg-light-gray" />
      <div className="flex gap-2">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-7 flex-1 animate-pulse rounded-full bg-light-gray" />
        ))}
      </div>
    </div>
  );
}

export function MonthlyAveragesBanner({
  summary,
  athleteAgeDecimal,
  isLoading,
  isError,
  monthLabel,
  athleteName,
}: MonthlyAveragesBannerProps) {
  const showRubric = showsRubricToParent(athleteAgeDecimal);

  return (
    <section
      data-testid="parent-monthly-banner"
      aria-label={`Resumen del mes de ${monthLabel} para ${athleteName}`}
      className="rounded-xl bg-white px-5 py-4 shadow-ring-soft"
    >
      <header className="mb-3 flex items-baseline justify-between gap-3">
        <h2
          className="text-base text-charcoal font-heading"
        >
          Cómo va este mes
        </h2>
        <span className="text-xs text-mid-gray capitalize">{monthLabel}</span>
      </header>

      {isLoading && <Skeleton />}

      {!isLoading && isError && (
        <p className="text-sm text-mid-gray" data-testid="monthly-banner-error">
          No fue posible calcular el resumen del mes.
        </p>
      )}

      {!isLoading && !isError && (!summary || summary.count_total === 0) && (
        <p className="text-sm text-mid-gray" data-testid="monthly-banner-empty">
          Aún no hay sesiones cerradas este mes.
        </p>
      )}

      {!isLoading && !isError && summary && summary.count_total > 0 && (
        <dl className="space-y-3">
          {/* Asistencia — Wave 5: el número absoluto domina, el % es referencia */}
          <div data-testid="monthly-stat-attendance">
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <dt className="text-mid-gray">Asistencia</dt>
              <dd className="text-right">
                <span className="font-semibold text-charcoal">
                  {summary.count_present} entrenos de {summary.count_total} programados
                </span>
                <span className="ml-2 text-xs text-mid-gray">
                  {Math.round(summary.percentage)}%
                </span>
              </dd>
            </div>
            <AttendanceMeter percentage={summary.percentage} />
            {summary.percentage < 75 && (
              <p
                className="mt-2 text-xs leading-snug text-text-disclaimer"
                data-testid="monthly-attendance-note"
              >
                Las ausencias justificadas son parte del cuidado. Conversa con
                el entrenador si quieres entender la planificación del mes.
              </p>
            )}
          </div>

          {/* Focos técnicos: siempre visible */}
          {summary.focos_técnicos.length > 0 && (
            <div data-testid="monthly-technical-focuses">
              <dt className="mb-1.5 flex items-center text-xs font-medium uppercase tracking-wide text-mid-gray">
                Foco técnico
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      aria-label="Más información sobre Foco técnico"
                      className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full text-mid-gray transition-colors hover:text-charcoal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30"
                    >
                      <Info size={12} aria-hidden="true" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    Habilidad central que se trabajó. El club rota focos cada
                    2-4 semanas (modelo PMBIA).
                  </TooltipContent>
                </Tooltip>
              </dt>
              <dd>
                <ul className="flex flex-wrap gap-1.5">
                  {summary.focos_técnicos.map((foco) => (
                    <li
                      key={foco}
                      className="rounded-full bg-light-gray px-2.5 py-0.5 text-xs text-charcoal"
                    >
                      {foco}
                    </li>
                  ))}
                </ul>
              </dd>
            </div>
          )}

          {/* Rúbrica con etiquetas cualitativas — solo para ≥13 años */}
          {showRubric && (
            <RubricRow
              avgEffort={summary.avg_rubric_effort ?? null}
              avgAttitude={summary.avg_rubric_attitude ?? null}
              avgTechnique={summary.avg_rubric_technique ?? null}
              avgRpe={summary.avg_rpe ?? null}
            />
          )}
        </dl>
      )}

      {!isLoading && !isError && summary && summary.count_total > 0 && (
        <p className="mt-4 border-t border-light-gray pt-3 text-xs text-mid-gray">
          {showRubric
            ? "Valoraciones del proceso de aprendizaje — no son calificaciones. Cambios semana a semana son normales."
            : "A esta edad lo más importante es que disfrute y descubra nuevas habilidades. Los números son una referencia interna del entrenador."}
        </p>
      )}
    </section>
  );
}

function RubricRow({
  avgEffort,
  avgAttitude,
  avgTechnique,
  avgRpe,
}: {
  avgEffort: number | null;
  avgAttitude: number | null;
  avgTechnique: number | null;
  avgRpe: number | null;
}) {
  const items = [
    { key: "effort", label: "Esfuerzo", value: avgEffort, testId: "monthly-stat-effort" },
    { key: "attitude", label: "Actitud", value: avgAttitude, testId: "monthly-stat-attitude" },
    { key: "technique", label: "Técnica", value: avgTechnique, testId: "monthly-stat-technique" },
  ] as const;

  const someRubric = items.some((it) => it.value != null);
  if (!someRubric && avgRpe == null) return null;

  return (
    <div>
      <dt className="mb-1.5 text-xs font-medium uppercase tracking-wide text-mid-gray">
        Tendencia del proceso
      </dt>
      <dd>
        <ul className="flex flex-col gap-1.5">
          {items.map((it) => {
            const label = rubricToLabel(it.value);
            return (
              <li
                key={it.key}
                data-testid={it.testId}
                className="flex items-center justify-between gap-3 text-sm"
              >
                <span className="text-mid-gray">{it.label}</span>
                {label ? (
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${RUBRIC_TONE[label]}`}
                    aria-label={`${it.label} promedio del mes: ${label}`}
                  >
                    {label}
                  </span>
                ) : (
                  <span className="text-xs text-mid-gray italic">Sin datos</span>
                )}
              </li>
            );
          })}
          {avgRpe != null && (
            <li
              data-testid="monthly-stat-rpe"
              className="flex items-center justify-between gap-3 border-t border-light-gray pt-1.5 text-sm"
            >
              <span className="text-mid-gray">
                <abbr title="Esfuerzo percibido registrado por el entrenador" className="no-underline">
                  RPE
                </abbr>{" "}
                promedio
              </span>
              <span
                className="text-xs font-medium text-charcoal"
                aria-label={`Esfuerzo percibido promedio: ${avgRpe.toFixed(1)} de 10`}
              >
                {avgRpe.toFixed(1)} / 10
              </span>
            </li>
          )}
        </ul>
      </dd>
    </div>
  );
}
