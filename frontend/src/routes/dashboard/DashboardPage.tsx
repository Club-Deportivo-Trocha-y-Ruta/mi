import { MeasurementAlerts } from "@/components/dashboard/MeasurementAlerts";
import { useDashboardStats } from "@/hooks/athletes/useDashboardStats";

function formatDate(isoDate: string): string {
  return new Intl.DateTimeFormat("es-CO", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(`${isoDate}T12:00:00`));
}

export function DashboardPage() {
  const { total, evaluatedCount, totalCount, lastEvaluation, isLoading, isDetailLoading } =
    useDashboardStats();

  return (
    <section>
      <h1 className="mb-4 text-2xl font-bold">Dashboard</h1>
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-sm text-slate-500">Total atletas</p>
          <p className="mt-1 text-xl font-semibold">
            {isLoading ? "…" : (total ?? "--")}
          </p>
        </article>
        <article className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-sm text-slate-500">Última evaluación</p>
          <p className="mt-1 text-xl font-semibold">
            {isDetailLoading ? "…" : lastEvaluation ? formatDate(lastEvaluation) : "--"}
          </p>
        </article>
        <article className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-sm text-slate-500">Estado PHV</p>
          <p className="mt-1 text-xl font-semibold">
            {isDetailLoading
              ? "…"
              : totalCount > 0
                ? `${evaluatedCount} / ${totalCount} evaluados`
                : "--"}
          </p>
        </article>
      </div>
      <MeasurementAlerts />
    </section>
  );
}
