import type { MonthlyMetricsSnapshot } from "@/types/trainingSession.types";

interface MonthlyMetricsTableProps {
  metrics: MonthlyMetricsSnapshot;
}

const cardStyle: React.CSSProperties = {
  boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px",
};

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl bg-white p-4 text-center" style={cardStyle}>
      <p className="text-2xl font-bold text-charcoal">{value}</p>
      <p className="mt-0.5 text-xs text-mid-gray">{label}</p>
    </div>
  );
}

function metricLabel(value: number | null): string {
  if (value === null) return "N/D";
  return value.toFixed(1);
}

export function MonthlyMetricsTable({ metrics }: MonthlyMetricsTableProps) {
  const sortedAttendance = [...(metrics.attendance_stats ?? [])].sort(
    (a, b) => b.percentage - a.percentage,
  );

  return (
    <div className="space-y-6" data-testid="monthly-metrics-table">
      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-3">
        <StatCard label="Planificadas" value={metrics.total_sessions_planned} />
        <StatCard label="Ejecutadas" value={metrics.total_sessions_executed} />
        <StatCard label="Canceladas" value={metrics.total_sessions_cancelled} />
      </div>

      {/* Asistencia */}
      {sortedAttendance.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-mid-gray">
            Asistencia por atleta
          </h3>
          <div className="overflow-x-auto rounded-xl bg-white" style={cardStyle}>
            <table className="min-w-full text-sm" data-testid="attendance-table">
              <caption className="sr-only">Métricas mensuales del club</caption>
              <thead>
                <tr>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Atleta
                  </th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Presencias
                  </th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                    Asistencia
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedAttendance.map((stat) => (
                  <tr
                    key={stat.pseudonym}
                  >
                    <td className="px-4 py-3 font-medium text-charcoal">
                      {stat.pseudonym}
                    </td>
                    <td className="px-4 py-3 text-mid-gray">
                      {stat.count_present} / {stat.count_total}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`font-medium ${
                          stat.percentage >= 75
                            ? "text-green-700"
                            : stat.percentage >= 50
                              ? "text-yellow-700"
                              : "text-red-700"
                        }`}
                      >
                        {stat.percentage.toFixed(0)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Focos técnicos */}
      {metrics.focos_técnicos && metrics.focos_técnicos.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-mid-gray">
            Focos técnicos del mes
          </h3>
          <div className="flex flex-wrap gap-2" data-testid="focos-tecnicos">
            {metrics.focos_técnicos.map((foco) => (
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

      {/* Promedios */}
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-mid-gray">
          Promedios de la sesión
        </h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="averages-grid">
          {(
            [
              { label: "RPE", value: metrics.avg_rpe },
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
