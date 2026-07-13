import { MeasurementAlerts } from "@/components/dashboard/MeasurementAlerts";
import { NextRaceTile } from "@/components/dashboard/NextRaceTile";
import { NextSessionTile } from "@/components/dashboard/NextSessionTile";
import { PendingInbox } from "@/components/dashboard/PendingInbox";
import { WeeklyLoadMeter } from "@/components/dashboard/WeeklyLoadMeter";
import { ErrorState } from "@/components/shared/ErrorState";
import { PageHeader } from "@/components/shared/PageHeader";
import { useDashboardStats } from "@/hooks/athletes/useDashboardStats";

export function DashboardPage() {
  const { total, isLoading, isError, refetch } = useDashboardStats();
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

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <NextSessionTile />

        <NextRaceTile />

        <WeeklyLoadMeter />
      </div>

      <PendingInbox />

      <MeasurementAlerts />
    </section>
  );
}
