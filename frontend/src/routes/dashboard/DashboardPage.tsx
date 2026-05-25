import { MeasurementAlerts } from "@/components/dashboard/MeasurementAlerts";
import { useDashboardStats } from "@/hooks/athletes/useDashboardStats";
import { formatDateMedium } from "@/lib/datetime";

export function DashboardPage() {
  const { total, evaluatedCount, totalCount, lastEvaluation, isLoading, isDetailLoading } =
    useDashboardStats();

  return (
    <section className="space-y-6">
      <h1
        className="text-2xl text-charcoal"
        style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
      >
        Dashboard
      </h1>

      <div className="grid gap-4 md:grid-cols-3">
        {/* Stat card */}
        <article
          className="rounded-xl bg-white p-5"
          style={{ boxShadow: "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px" }}
        >
          <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">Total atletas</p>
          <p className="mt-2 text-2xl font-bold text-charcoal">
            {isLoading ? "…" : (total ?? "--")}
          </p>
        </article>

        <article
          className="rounded-xl bg-white p-5"
          style={{ boxShadow: "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px" }}
        >
          <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">Última evaluación</p>
          <p className="mt-2 text-2xl font-bold text-charcoal">
            {isDetailLoading ? "…" : lastEvaluation ? formatDateMedium(`${lastEvaluation}T12:00:00`) : "--"}
          </p>
        </article>

        <article
          className="rounded-xl bg-white p-5"
          style={{ boxShadow: "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px" }}
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
