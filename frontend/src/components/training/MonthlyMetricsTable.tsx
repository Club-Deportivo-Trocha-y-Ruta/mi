import { formatMinutesAsHms } from "@/lib/datetime";
import type {
  AthleteAttendanceStats,
  MonthlyMetricsSnapshot,
} from "@/types/trainingSession.types";

/**
 * session_date/start_time llegan como fecha/hora "de pared" sin zona
 * (columnas Date/Time puras del backend, no timestamps). Formatear con
 * Date+timeZone desfasaría el día/hora — se formatean como texto plano.
 */
function formatPlainDate(value: string): string {
  const [y, m, d] = value.split("-");
  if (!y || !m || !d) return value;
  return `${d}/${m}/${y}`;
}

function formatPlainTime(value: string): string {
  const [hStr, mStr] = value.split(":");
  const h = Number(hStr);
  if (Number.isNaN(h) || !mStr) return value;
  const period = h >= 12 ? "p. m." : "a. m.";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${String(h12).padStart(2, "0")}:${mStr} ${period}`;
}

interface MonthlyMetricsTableProps {
  metrics: MonthlyMetricsSnapshot;
  /** Mapa id_atleta (str) -> "Nombre Apellido". Solo coach/admin; si falta, cae a "Atleta N". */
  athleteNames?: Record<string, string>;
}

const cardStyle: React.CSSProperties = {
  boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px",
};

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl bg-white p-4 text-center" style={cardStyle}>
      <p className="text-2xl font-bold text-charcoal">{value}</p>
      <p className="mt-0.5 text-xs text-mid-gray">{label}</p>
    </div>
  );
}

function metricLabel(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/D";
  return value.toFixed(1);
}

// Etiquetas de estado de asistencia, en el orden que se muestra.
const STATUS_TOTALS: { key: string; label: string }[] = [
  { key: "presente", label: "Presentes" },
  { key: "tarde", label: "Tarde" },
  { key: "justificado", label: "Justificadas" },
  { key: "ausente", label: "Ausencias" },
  { key: "lesionado", label: "Lesionados" },
];

const SESSION_STATUS_LABELS: Record<string, string> = {
  executed: "Ejecutada",
  cancelled: "Cancelada",
  planned: "Planificada",
};

export function MonthlyMetricsTable({ metrics, athleteNames }: MonthlyMetricsTableProps) {
  const attendanceRows = Object.entries(metrics.attendance_by_athlete ?? {})
    .map(([id, stats]) => ({ id, stats: stats as AthleteAttendanceStats }))
    .sort((a, b) => b.stats.attendance_pct - a.stats.attendance_pct);

  const focusCounts = metrics.technical_focus_counts;
  const focusList = metrics.technical_focus_list ?? [];
  const hasFocus =
    (focusCounts && Object.keys(focusCounts).length > 0) || focusList.length > 0;

  const hasVolume = (metrics.total_minutes_executed ?? 0) > 0;

  const statusTotals = metrics.attendance_status_totals;

  return (
    <div className="space-y-6" data-testid="monthly-metrics-table">
      {/* KPIs */}
      <div className="grid grid-cols-2 gap-2 sm:gap-3">
        <StatCard label="Ejecutadas" value={metrics.total_sessions_executed} />
        <StatCard label="Canceladas" value={metrics.total_sessions_cancelled} />
      </div>

      {/* Volumen de entrenamiento */}
      {hasVolume && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-mid-gray">
            Volumen de entrenamiento
          </h3>
          <div className="grid grid-cols-2 gap-3" data-testid="volume-grid">
            <StatCard label="Ejecutado" value={formatMinutesAsHms(metrics.total_minutes_executed ?? 0)} />
            <StatCard
              label="Prom. semanal"
              value={
                metrics.avg_hours_per_week != null
                  ? formatMinutesAsHms(metrics.avg_hours_per_week * 60)
                  : "N/D"
              }
            />
          </div>
        </div>
      )}

      {/* Detalle de sesiones — fecha/hora/foco/lugar/asistencia (FR-004) */}
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-mid-gray">
          Detalle de sesiones
        </h3>
        {metrics.session_detail === undefined ? (
          <p className="text-sm text-mid-gray" data-testid="session-detail-pending">
            Pendiente — regenerar informe.
          </p>
        ) : metrics.session_detail.length === 0 ? (
          <p className="text-sm text-mid-gray" data-testid="session-detail-empty">
            Sin sesiones registradas para este período.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl bg-white" style={cardStyle}>
            <table className="min-w-full text-sm" data-testid="session-detail-table">
              <caption className="sr-only">Detalle de sesiones del período</caption>
              <thead style={{ borderBottom: "1px solid rgba(34, 42, 53, 0.08)" }}>
                <tr>
                  <th scope="col" className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Fecha
                  </th>
                  <th scope="col" className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Hora
                  </th>
                  <th scope="col" className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Foco técnico
                  </th>
                  <th scope="col" className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Lugar
                  </th>
                  <th scope="col" className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Asistencia
                  </th>
                  <th scope="col" className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Estado
                  </th>
                </tr>
              </thead>
              <tbody>
                {metrics.session_detail.map((s, i) => (
                  <tr
                    key={`${s.session_date}-${i}`}
                    style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
                  >
                    <td className="px-3 py-3 text-mid-gray">{formatPlainDate(s.session_date)}</td>
                    <td className="px-3 py-3 text-mid-gray">{formatPlainTime(s.start_time)}</td>
                    <td className="px-3 py-3 font-medium text-charcoal">{s.technical_focus}</td>
                    <td className="px-3 py-3 text-mid-gray">{s.location}</td>
                    <td className="px-3 py-3 text-mid-gray">
                      {s.present_count}/{s.attendee_total}
                    </td>
                    <td className="px-3 py-3 text-mid-gray">
                      {SESSION_STATUS_LABELS[s.status] ?? s.status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Asistencia por atleta — desglose por estado */}
      {attendanceRows.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-mid-gray">
            Asistencia por atleta
          </h3>
          <div className="overflow-x-auto rounded-xl bg-white" style={cardStyle}>
            <table className="min-w-full text-sm" data-testid="attendance-table">
              <caption className="sr-only">
                Asistencia mensual por atleta y estado
              </caption>
              <thead style={{ borderBottom: "1px solid rgba(34, 42, 53, 0.08)" }}>
                <tr>
                  <th scope="col" className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Atleta
                  </th>
                  <th scope="col" className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Pres.
                  </th>
                  <th scope="col" className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Tarde
                  </th>
                  <th scope="col" className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Justif.
                  </th>
                  <th scope="col" className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Ausente
                  </th>
                  <th scope="col" className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Lesion.
                  </th>
                  <th scope="col" className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    % Asist.
                  </th>
                </tr>
              </thead>
              <tbody>
                {attendanceRows.map(({ id, stats }, index) => (
                  <tr
                    key={id}
                    style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
                  >
                    <td className="px-3 py-3 font-medium text-charcoal">
                      {athleteNames?.[id] ?? `Atleta ${index + 1}`}
                    </td>
                    <td className="px-3 py-3 text-mid-gray">{stats.count_present}</td>
                    <td className="px-3 py-3 text-mid-gray">{stats.count_late}</td>
                    <td className="px-3 py-3 text-mid-gray">{stats.count_justified}</td>
                    <td className="px-3 py-3 text-mid-gray">{stats.count_absent}</td>
                    <td className="px-3 py-3 text-mid-gray">{stats.count_injured}</td>
                    <td className="px-3 py-3">
                      <span
                        className={`font-medium ${
                          stats.attendance_pct >= 75
                            ? "text-green-700"
                            : stats.attendance_pct >= 50
                              ? "text-yellow-700"
                              : "text-red-700"
                        }`}
                      >
                        {stats.attendance_pct.toFixed(0)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Totales del club por estado */}
          {statusTotals && (
            <div
              className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-mid-gray"
              data-testid="status-totals"
            >
              {STATUS_TOTALS.map(({ key, label }) => (
                <span key={key}>
                  {label}:{" "}
                  <span className="font-semibold text-charcoal">
                    {statusTotals[key] ?? 0}
                  </span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Focos técnicos — con frecuencia si está disponible */}
      {hasFocus && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-mid-gray">
            Focos técnicos del mes
          </h3>
          <div className="flex flex-wrap gap-2" data-testid="focos-tecnicos">
            {focusCounts && Object.keys(focusCounts).length > 0
              ? Object.entries(focusCounts).map(([foco, n]) => (
                  <span
                    key={foco}
                    className="rounded-full bg-light-gray px-3 py-1 text-xs font-medium text-charcoal"
                  >
                    {foco} · {n}
                  </span>
                ))
              : focusList.map((foco) => (
                  <span
                    key={foco}
                    className="rounded-full bg-light-gray px-3 py-1 text-xs font-medium text-charcoal"
                  >
                    {foco}
                  </span>
                ))}
          </div>
        </div>
      )}

      {/* Promedios de rúbrica */}
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-mid-gray">
          Promedios de la sesión
        </h3>
        <div className="grid grid-cols-3 gap-3" data-testid="averages-grid">
          {(
            [
              { label: "Esfuerzo", value: metrics.avg_rubric_effort },
              { label: "Actitud", value: metrics.avg_rubric_attitude },
              { label: "Técnica", value: metrics.avg_rubric_technique },
            ] as const
          ).map(({ label, value }) => (
            <div
              key={label}
              className="rounded-xl bg-white px-4 py-3 text-center"
              style={cardStyle}
            >
              <p className="text-lg font-bold text-charcoal">{metricLabel(value)}</p>
              <p className="mt-0.5 text-xs text-mid-gray">{label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
