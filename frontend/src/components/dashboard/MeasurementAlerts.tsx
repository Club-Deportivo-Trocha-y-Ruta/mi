import { Link } from "react-router-dom";

import { AthleteLink } from "@/components/shared/AthleteLink";
import { ErrorState } from "@/components/shared/ErrorState";
import { useAlerts } from "@/hooks/athletes/useAlerts";
import type { AthleteAlert, MeasurementStatus } from "@/types/alerts.types";

const STATUS_CONFIG: Record<MeasurementStatus, { dot: string; bg: string; label: string }> = {
  overdue: { dot: "bg-red-500", bg: "bg-red-50 text-red-700", label: "vencidas" },
  due_soon: { dot: "bg-amber-400", bg: "bg-amber-50 text-amber-700", label: "próximas" },
  ok: { dot: "bg-green-500", bg: "bg-green-50 text-green-700", label: "al día" },
  never: { dot: "bg-mid-gray", bg: "bg-light-gray text-mid-gray", label: "sin medir" },
};

function formatDaysText(alert: AthleteAlert): string {
  if (alert.measurement_status === "never") return "Sin medición";
  if (alert.days_overdue === null) return "";
  if (alert.days_overdue > 0) {
    return `${alert.days_overdue}d de atraso`;
  }
  return `Vence en ${Math.abs(alert.days_overdue)}d`;
}

export function MeasurementAlerts() {
  const { data, isPending, isError, refetch } = useAlerts();

  if (isPending) {
    return (
      <section className="mt-6">
        <h2 className="font-display mb-3 text-lg text-charcoal">
          Mediciones pendientes
        </h2>
        <p className="text-sm text-mid-gray">Cargando alertas...</p>
      </section>
    );
  }

  if (isError) {
    return (
      <section className="mt-6">
        <h2 className="font-display mb-3 text-lg text-charcoal">
          Mediciones pendientes
        </h2>
        <ErrorState
          message="No se pudieron cargar las alertas de medición."
          onRetry={() => void refetch()}
        />
      </section>
    );
  }

  if (!data || data.athletes.length === 0) return null;

  const STATUS_ORDER: Record<MeasurementStatus, number> = {
    overdue: 0,
    due_soon: 1,
    never: 2,
    ok: 3,
  };

  const actionable = data.athletes
    .filter((a) => a.measurement_status !== "ok")
    .sort((a, b) => {
      const statusDiff = STATUS_ORDER[a.measurement_status] - STATUS_ORDER[b.measurement_status];
      if (statusDiff !== 0) return statusDiff;
      if (a.measurement_status === "overdue") {
        return (b.days_overdue ?? 0) - (a.days_overdue ?? 0);
      }
      if (a.measurement_status === "due_soon") {
        const aDays = a.days_overdue === null ? Infinity : Math.abs(a.days_overdue);
        const bDays = b.days_overdue === null ? Infinity : Math.abs(b.days_overdue);
        return aDays - bDays;
      }
      return 0;
    });

  const MAX_VISIBLE = 8;
  const visibleActionable = actionable.slice(0, MAX_VISIBLE);
  const remainingCount = actionable.length;

  const rapidGrowth = data.athletes.filter(
    (a) => a.growth_alerts.includes("rapid_growth")
  );

  return (
    <section className="mt-6 space-y-4">
      <h2
        className="font-display text-lg text-charcoal"
      >
        Mediciones pendientes
      </h2>

      {/* Barra de resumen */}
      <div className="flex flex-wrap gap-2">
        {data.overdue > 0 && (
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${STATUS_CONFIG.overdue.bg}`}>
            <span className={`h-2 w-2 rounded-full ${STATUS_CONFIG.overdue.dot}`} />
            {data.overdue} vencidas
          </span>
        )}
        {data.due_soon > 0 && (
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${STATUS_CONFIG.due_soon.bg}`}>
            <span className={`h-2 w-2 rounded-full ${STATUS_CONFIG.due_soon.dot}`} />
            {data.due_soon} próximas
          </span>
        )}
        <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${STATUS_CONFIG.ok.bg}`}>
          <span className={`h-2 w-2 rounded-full ${STATUS_CONFIG.ok.dot}`} />
          {data.ok} al día
        </span>
        {data.never_measured > 0 && (
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${STATUS_CONFIG.never.bg}`}>
            <span className={`h-2 w-2 rounded-full ${STATUS_CONFIG.never.dot}`} />
            {data.never_measured} sin medir
          </span>
        )}
      </div>

      {/* Alertas de crecimiento acelerado */}
      {rapidGrowth.length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p className="mb-2 text-sm font-medium text-amber-800">Crecimiento acelerado detectado</p>
          {rapidGrowth.map((a) => (
            <p key={a.athlete_id} className="text-sm text-amber-700">
              <AthleteLink athleteId={a.athlete_id} className="font-medium underline">
                {a.athlete_name}
              </AthleteLink>
              {" — "}{a.growth_velocity_cm_month} cm/mes. {a.training_implications ?? "Revisar carga de entrenamiento."}
            </p>
          ))}
        </div>
      )}

      {/* Lista de atletas que requieren accion */}
      {actionable.length > 0 && (
        <div className="rounded-xl bg-white shadow-card">
          <ul>
            {visibleActionable.map((a, idx) => {
              const config = STATUS_CONFIG[a.measurement_status];
              return (
                <li
                  key={a.athlete_id}
                  className="flex items-center gap-3 px-4 py-3"
                  style={idx > 0 ? { borderTop: "1px solid rgba(34, 42, 53, 0.06)" } : undefined}
                >
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${config.dot}`} />
                  <AthleteLink
                    athleteId={a.athlete_id}
                    className="min-w-0 flex-1 truncate text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
                  >
                    {a.athlete_name}
                  </AthleteLink>
                  {a.current_phv_status ? (
                    <span className="shrink-0 rounded-full bg-light-gray px-2.5 py-0.5 text-xs text-charcoal">
                      {a.current_phv_status}
                    </span>
                  ) : (
                    <span className="text-xs text-mid-gray">—</span>
                  )}
                  <span className="shrink-0 text-xs text-mid-gray">
                    {formatDaysText(a)}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {remainingCount > MAX_VISIBLE && (
        <Link
          to="/athletes"
          className="inline-block text-sm font-medium text-primary underline transition-opacity hover:opacity-70"
        >
          Ver todas ({remainingCount})
        </Link>
      )}
    </section>
  );
}
