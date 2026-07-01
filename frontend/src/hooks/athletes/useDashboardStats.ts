import { useAlerts } from "@/hooks/athletes/useAlerts";

export function useDashboardStats() {
  const alertsQuery = useAlerts();

  const athletes = alertsQuery.data?.athletes ?? [];

  const total = alertsQuery.isPending ? null : athletes.length;

  const lastEvaluation: string | null =
    (athletes
      .map((a) => a.last_measurement_date)
      .filter((d): d is string => d !== null)
      .sort((a, b) => b.localeCompare(a))[0] as string | undefined) ?? null;

  const phvVigentes = athletes.filter(
    (a) => a.measurement_status !== "overdue" && a.measurement_status !== "never",
  ).length;

  const phvTotal = athletes.length;

  return {
    total,
    lastEvaluation,
    phvVigentes,
    phvTotal,
    isLoading: alertsQuery.isPending,
    isError: alertsQuery.isError,
  };
}
