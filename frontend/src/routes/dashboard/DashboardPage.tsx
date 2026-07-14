import { MeasurementAlerts } from "@/components/dashboard/MeasurementAlerts";
import { NextRaceTile } from "@/components/dashboard/NextRaceTile";
import { NextSessionTile } from "@/components/dashboard/NextSessionTile";
import { PendingInbox } from "@/components/dashboard/PendingInbox";
import { WeeklyLoadMeter } from "@/components/dashboard/WeeklyLoadMeter";
import { PageHeader } from "@/components/shared/PageHeader";
import { useDashboardStats } from "@/hooks/athletes/useDashboardStats";

// `useDashboardStats()` (wraps the same `useAlerts()` query `MeasurementAlerts`
// consumes) is only used here for the "no athletes in this club" empty-state
// copy below. Its error case is intentionally NOT rendered here anymore —
// `MeasurementAlerts` already renders its own scoped `ErrorState` + retry for
// this exact query, and rendering a second top-level `ErrorState` for the
// same failure produced two "Reintentar" buttons on screen for one error
// (duplicate-control defect caught by DashboardPage.test.tsx's retry test).
export function DashboardPage() {
  const { total, isLoading, isError } = useDashboardStats();
  const isEmpty = !isLoading && !isError && (total ?? 0) === 0;

  return (
    <section className="space-y-6">
      <PageHeader title="Dashboard" />

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
