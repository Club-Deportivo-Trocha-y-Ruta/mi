import { useState } from "react";

import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useParentMonthlySummary } from "@/api/trainingSessions";
import type { MyAthleteOut } from "@/types/parent.types";
import type { ParentMonthlySummary } from "@/types/trainingSession.types";

const CARD_SHADOW =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

const MONTHS = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function defaultPeriod(): { year: number; month: number } {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

function AttendanceBar({ percentage }: { percentage: number }) {
  const pct = Math.min(100, Math.max(0, percentage));
  const color = pct >= 75 ? "bg-green-500" : pct >= 50 ? "bg-amber-400" : "bg-red-400";
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
      className="rounded-xl bg-white px-5 py-4 space-y-4"
      style={{ boxShadow: CARD_SHADOW }}
      aria-label={`Resumen de ${athlete.athlete_first_name} ${athlete.athlete_last_name}`}
    >
      <div>
        <h3
          className="text-base text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
        >
          {athlete.athlete_first_name} {athlete.athlete_last_name}
        </h3>
        {athlete.category && (
          <p className="text-xs text-mid-gray mt-0.5">{athlete.category}</p>
        )}
      </div>

      {isLoading && (
        <div className="space-y-2">
          <div className="h-4 animate-pulse rounded bg-light-gray w-3/4" />
          <div className="h-2 animate-pulse rounded-full bg-light-gray" />
        </div>
      )}

      {!isLoading && !summary && (
        <p className="text-sm text-mid-gray">Sin datos para este mes.</p>
      )}

      {!isLoading && summary && (
        <>
          {/* Asistencia */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-sm">
              <span className="text-mid-gray">Asistencia</span>
              <span className="font-semibold text-charcoal">
                {summary.count_present}/{summary.count_total} sesiones ({Math.round(summary.percentage)}%)
              </span>
            </div>
            <AttendanceBar percentage={summary.percentage} />
          </div>

          {/* Focos técnicos */}
          {summary.focos_técnicos.length > 0 && (
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-mid-gray mb-2">
                Focos técnicos cubiertos
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
          className="text-2xl text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
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
            className="rounded-lg px-3 py-1.5 text-sm text-charcoal outline-none"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
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
            className="rounded-lg px-3 py-1.5 text-sm text-charcoal outline-none"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
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
        <div className="space-y-3">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="h-32 animate-pulse rounded-xl bg-light-gray" />
          ))}
        </div>
      )}

      {/* Sin atletas */}
      {!athletesQuery.isLoading && athletes.length === 0 && (
        <div className="rounded-xl bg-white px-5 py-8 text-center" style={{ boxShadow: CARD_SHADOW }}>
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
