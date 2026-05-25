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
    <section className="space-y-6">
      <h1
        className="text-2xl text-charcoal font-heading"
      >
        Dashboard
      </h1>

      <div className="grid gap-4 md:grid-cols-3">
        {/* Stat card */}
        <article
          className="rounded-xl bg-white p-5"
        >
          <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">Total atletas</p>
          <p className="mt-2 text-2xl font-bold text-charcoal">
            {isLoading ? "…" : (total ?? "--")}
          </p>
        </article>

        <article
          className="rounded-xl bg-white p-5"
        >
          <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">Última evaluación</p>
          <p className="mt-2 text-2xl font-bold text-charcoal">
            {isDetailLoading ? "…" : lastEvaluation ? formatDate(lastEvaluation) : "--"}
          </p>
        </article>

        <article
          className="rounded-xl bg-white p-5"
        >
          <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">Estado PHV</p>
          <p className="mt-2 text-2xl font-bold text-charcoal">
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
