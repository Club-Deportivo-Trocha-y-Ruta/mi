import { MeasurementAlerts } from "@/components/dashboard/MeasurementAlerts";
import { ErrorState } from "@/components/shared/ErrorState";
import { PageHeader } from "@/components/shared/PageHeader";
import { useDashboardStats } from "@/hooks/athletes/useDashboardStats";
import { formatDateMedium } from "@/lib/datetime";

export function DashboardPage() {
  const { total, lastEvaluation, phvVigentes, phvTotal, isLoading, isError, refetch } =
    useDashboardStats();
  const isEmpty = !isLoading && !isError && (total ?? 0) === 0;

  return (
    <section className="space-y-6">
      <PageHeader title="Dashboard" />

      {isError && (
        <ErrorState
          message="No pudimos cargar la información del dashboard. Intenta de nuevo más tarde."
          onRetry={() => void refetch()}
        />
      )}

      {isEmpty && (
        <p className="text-sm text-mid-gray">No tienes atletas asignados a un club</p>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        {/* Stat card */}
        <article className="rounded-xl bg-white p-5 shadow-card">
          <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">Total atletas</p>
          <p className="mt-2 text-2xl font-bold text-charcoal">
            {isLoading ? "…" : isError || !total ? "--" : total}
          </p>
        </article>

        <article className="rounded-xl bg-white p-5 shadow-card">
          <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">Última evaluación</p>
          <p className="mt-2 text-2xl font-bold text-charcoal">
            {isLoading
              ? "…"
              : !isError && lastEvaluation
                ? formatDateMedium(`${lastEvaluation}T12:00:00`)
                : "--"}
          </p>
        </article>

        <article className="rounded-xl bg-white p-5 shadow-card">
          <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">Estado PHV</p>
          <p className="mt-2 text-2xl font-bold text-charcoal">
            {isLoading
              ? "…"
              : !isError && phvTotal > 0
                ? `${phvVigentes} de ${phvTotal} con medición vigente`
                : "--"}
          </p>
        </article>
      </div>

      <MeasurementAlerts />
    </section>
  );
}
