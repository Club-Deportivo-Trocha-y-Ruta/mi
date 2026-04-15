import { Link } from "react-router-dom";

import { useAlerts } from "@/hooks/athletes/useAlerts";
import type { AthleteAlert, MeasurementStatus } from "@/types/alerts.types";

const STATUS_CONFIG: Record<MeasurementStatus, { color: string; bg: string; label: string }> = {
  overdue: { color: "bg-red-500", bg: "bg-red-50 text-red-700", label: "vencidas" },
  due_soon: { color: "bg-amber-400", bg: "bg-amber-50 text-amber-700", label: "proximas" },
  ok: { color: "bg-green-500", bg: "bg-green-50 text-green-700", label: "al dia" },
  never: { color: "bg-slate-300", bg: "bg-slate-50 text-slate-600", label: "sin medir" },
};

function formatDaysText(alert: AthleteAlert): string {
  if (alert.measurement_status === "never") return "Sin medicion";
  if (alert.days_overdue === null) return "";
  if (alert.days_overdue > 0) {
    return `${alert.days_overdue}d de atraso`;
  }
  return `Vence en ${Math.abs(alert.days_overdue)}d`;
}

export function MeasurementAlerts() {
  const { data, isPending, isError } = useAlerts();

  if (isPending) {
    return (
      <section className="mt-6">
        <h2 className="mb-3 text-lg font-semibold">Mediciones pendientes</h2>
        <p className="text-sm text-slate-400">Cargando alertas...</p>
      </section>
    );
  }

  if (isError) {
    return (
      <section className="mt-6">
        <h2 className="mb-3 text-lg font-semibold">Mediciones pendientes</h2>
        <p className="text-sm text-red-500">Error al cargar alertas</p>
      </section>
    );
  }

  if (!data || data.athletes.length === 0) return null;

  const actionable = data.athletes.filter(
    (a) => a.measurement_status !== "ok"
  );

  const rapidGrowth = data.athletes.filter(
    (a) => a.growth_alerts.includes("rapid_growth")
  );

  return (
    <section className="mt-6">
      <h2 className="mb-3 text-lg font-semibold">Mediciones pendientes</h2>

      {/* Barra de resumen */}
      <div className="mb-4 flex flex-wrap gap-2">
        {data.overdue > 0 && (
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${STATUS_CONFIG.overdue.bg}`}>
            <span className={`h-2 w-2 rounded-full ${STATUS_CONFIG.overdue.color}`} />
            {data.overdue} vencidas
          </span>
        )}
        {data.due_soon > 0 && (
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${STATUS_CONFIG.due_soon.bg}`}>
            <span className={`h-2 w-2 rounded-full ${STATUS_CONFIG.due_soon.color}`} />
            {data.due_soon} proximas
          </span>
        )}
        <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${STATUS_CONFIG.ok.bg}`}>
          <span className={`h-2 w-2 rounded-full ${STATUS_CONFIG.ok.color}`} />
          {data.ok} al dia
        </span>
        {data.never_measured > 0 && (
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${STATUS_CONFIG.never.bg}`}>
            <span className={`h-2 w-2 rounded-full ${STATUS_CONFIG.never.color}`} />
            {data.never_measured} sin medir
          </span>
        )}
      </div>

      {/* Alertas de crecimiento acelerado */}
      {rapidGrowth.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
          <p className="mb-1 text-sm font-medium text-amber-800">Crecimiento acelerado detectado</p>
          {rapidGrowth.map((a) => (
            <p key={a.athlete_id} className="text-sm text-amber-700">
              <Link to={`/athletes/${a.athlete_id}`} className="font-medium underline">
                {a.athlete_name}
              </Link>
              {" — "}{a.growth_velocity_cm_month} cm/mes. Revisar carga de entrenamiento.
            </p>
          ))}
        </div>
      )}

      {/* Lista de atletas que requieren accion */}
      {actionable.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white">
          <ul className="divide-y divide-slate-100">
            {actionable.map((a) => {
              const config = STATUS_CONFIG[a.measurement_status];
              return (
                <li key={a.athlete_id} className="flex items-center gap-3 px-4 py-2.5">
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${config.color}`} />
                  <Link
                    to={`/athletes/${a.athlete_id}`}
                    className="min-w-0 flex-1 truncate text-sm font-medium text-slate-900 hover:text-blue-600"
                  >
                    {a.athlete_name}
                  </Link>
                  {a.current_phv_status ? (
                    <span className="shrink-0 rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                      {a.current_phv_status}
                    </span>
                  ) : (
                    <span className="text-xs text-slate-400">—</span>
                  )}
                  <span className="shrink-0 text-xs text-slate-500">
                    {formatDaysText(a)}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}
