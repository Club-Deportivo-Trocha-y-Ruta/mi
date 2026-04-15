import { apiClient } from "@/api/client";
import type { AlertsSummary } from "@/types/alerts.types";

export async function getAlerts(params?: {
  club_id?: number;
}): Promise<AlertsSummary> {
  const response = await apiClient.get<AlertsSummary>("/api/athletes/alerts", { params });
  return response.data;
}
