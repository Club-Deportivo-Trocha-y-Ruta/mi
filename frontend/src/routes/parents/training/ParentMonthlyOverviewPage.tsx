import { useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useParentMonthlySummary } from "@/api/trainingSessions";
import type { MyAthleteOut } from "@/types/parent.types";
import type { ParentMonthlySummary } from "@/types/trainingSession.types";

const MONTHS = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function defaultPeriod(): { year: number; month: number } {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

// Wave 5: <50% deja de ser rojo. La ausencia justificada de un menor es
// parte legítima del cuidado familiar, no una alerta. Conservamos ámbar
// para <75% y verde para 75%+, sin rojo automático.
function AttendanceBar({ percentage }: { percentage: number }) {
  const pct = Math.min(100, Math.max(0, percentage));
  const color = pct >= 75 ? "bg-green-500" : "bg-amber-400";
  return (
    <div className="h-2 w-full rounded-full bg-light-gray overflow-hidden" aria-hidden="true">
      <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function AthleteSummaryCard({
  athlete,
  summary,
  isLoading,
}: {
  athlete: MyAthleteOut;
  summary: ParentMonthlySummary | undefined;
  isLoading: boolean;
}) {
  return (
    <div
      className="rounded-xl bg-white px-5 py-4 space-y-4 shadow-card"
      aria-label={`Resumen de ${athlete.athlete_first_name} ${athlete.athlete_last_name}`}
    >
      <div>
        <h2
          className="font-display text-base text-charcoal"
        >
          {athlete.athlete_first_name} {athlete.athlete_last_name}
        </h2>
        {athlete.category && (
          <p className="text-xs text-mid-gray mt-0.5">{athlete.category}</p>
        )}
      </div>

      {isLoading && (
        <div
          role="status"
          aria-busy="true"
          aria-label={`Cargando resumen de ${athlete.athlete_first_name} ${athlete.athlete_last_name}`}
          className="space-y-2"
        >
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-2 w-full rounded-full" />
        </div>
      )}

      {!isLoading && !summary && (
        <p className="text-sm text-mid-gray">Aún no hay sesiones cerradas este mes.</p>
      )}

      {!isLoading && summary && (
        <>
          {/* Asistencia — Wave 5: número absoluto domina, % es referencia */}
          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="text-mid-gray">Asistencia</span>
              <span className="text-right">
                <span className="font-semibold text-charcoal">
                  {summary.count_present} entrenos de {summary.count_total} programados
                </span>
                <span className="ml-2 text-xs text-mid-gray">
                  {Math.round(summary.percentage)}%
                </span>
              </span>
            </div>
            <AttendanceBar percentage={summary.percentage} />
            {summary.percentage < 75 && (
              <p className="mt-1.5 text-xs leading-snug text-text-disclaimer">
                Las ausencias justificadas son parte del cuidado. Conversa con
                el entrenador si quieres entender la planificación del mes.
              </p>
            )}
          </div>

          {/* Foco técnico */}
          {summary.focos_técnicos.length > 0 && (
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-mid-gray mb-2">
                Foco técnico
              </p>
              <div className="flex flex-wrap gap-1.5">
                {summary.focos_técnicos.map((foco) => (
                  <span
                    key={foco}
                    className="rounded-full bg-light-gray px-2.5 py-0.5 text-xs text-charcoal"
                  >
                    {foco}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function AthleteWithSummary({
  athlete,
  year,
  month,
}: {
  athlete: MyAthleteOut;
  year: number;
  month: number;
}) {
  const query = useParentMonthlySummary(year, month, athlete.athlete_id);
  const summaries = query.data ?? [];
  const summary = summaries.find((s) => s.athlete_id === athlete.athlete_id);

  return (
    <AthleteSummaryCard
      athlete={athlete}
      summary={summary}
      isLoading={query.isLoading}
    />
  );
}

export function ParentMonthlyOverviewPage() {
  const [period, setPeriod] = useState(defaultPeriod);
  const athletesQuery = useMyAthletes();
  const athletes = athletesQuery.data ?? [];

  const currentYear = new Date().getFullYear();
  const years = [currentYear - 1, currentYear];

  return (
    <section className="space-y-5">
      <div>
        <h1
          className="font-display text-2xl text-charcoal"
        >
          Resumen mensual
        </h1>
        <p className="mt-0.5 text-sm text-mid-gray">Vista de lectura — solo tus atletas.</p>
      </div>

      {/* Selector período */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5">
          <label htmlFor="select-year" className="text-sm text-mid-gray sr-only">
            Año
          </label>
          <select
            id="select-year"
            value={period.year}
            onChange={(e) => setPeriod((p) => ({ ...p, year: Number(e.target.value) }))}
            className="rounded-lg px-3 py-1.5 text-sm text-charcoal outline-none focus-visible:ring-2 focus-visible:ring-charcoal/40 focus-visible:ring-offset-2 shadow-ring"
            aria-label="Seleccionar año"
          >
            {years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-1.5">
          <label htmlFor="select-month" className="text-sm text-mid-gray sr-only">
            Mes
          </label>
          <select
            id="select-month"
            value={period.month}
            onChange={(e) => setPeriod((p) => ({ ...p, month: Number(e.target.value) }))}
            className="rounded-lg px-3 py-1.5 text-sm text-charcoal outline-none focus-visible:ring-2 focus-visible:ring-charcoal/40 focus-visible:ring-offset-2 shadow-ring"
            aria-label="Seleccionar mes"
          >
            {MONTHS.map((name, i) => (
              <option key={i + 1} value={i + 1}>{name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Loading athletes */}
      {athletesQuery.isLoading && (
        <div
          role="status"
          aria-busy="true"
          aria-label="Cargando atletas"
          className="space-y-3"
        >
          {[...Array(2)].map((_, i) => (
            <Skeleton key={i} className="h-32 rounded-xl" />
          ))}
        </div>
      )}

      {/* Sin atletas */}
      {!athletesQuery.isLoading && athletes.length === 0 && (
        <div className="rounded-xl bg-white px-5 py-8 text-center shadow-card">
          <p className="text-sm text-mid-gray">
            No tienes atletas vinculados. Contacta al entrenador.
          </p>
        </div>
      )}

      {/* Una card por atleta */}
      {!athletesQuery.isLoading && athletes.length > 0 && (
        <div className="space-y-4" data-testid="athlete-summaries">
          {athletes.map((athlete) => (
            <AthleteWithSummary
              key={athlete.athlete_id}
              athlete={athlete}
              year={period.year}
              month={period.month}
            />
          ))}
        </div>
      )}
    </section>
  );
}
