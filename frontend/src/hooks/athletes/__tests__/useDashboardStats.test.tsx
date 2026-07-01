/**
 * Tests vitest para useDashboardStats (specs/020-dashboard-coach-phase-a).
 *
 * Cubre:
 *  - Deriva las tarjetas del dashboard a partir del payload de
 *    GET /api/athletes/alerts (total, última evaluación, PHV vigentes).
 *  - Regresión N+1: NO debe disparar ningún GET /api/athletes/{id} por
 *    atleta — el dashboard consume únicamente el endpoint de alerts.
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";

import { mswServer } from "@/test/setup";
import { useDashboardStats } from "@/hooks/athletes/useDashboardStats";
import { useAuthStore } from "@/store/auth.store";
import type { AlertsSummary } from "@/types/alerts.types";

const alertsPayload: AlertsSummary = {
  overdue: 1,
  due_soon: 1,
  ok: 1,
  never_measured: 0,
  rapid_growth_count: 0,
  athletes: [
    {
      athlete_id: 1,
      athlete_name: "Juan Pérez Ficticio",
      sex: "M",
      age_decimal: 12.3,
      category: "Sub-13",
      measurement_status: "overdue",
      last_measurement_date: "2026-01-10",
      next_due_date: "2026-03-10",
      days_overdue: 20,
      current_phv_status: "Pre-PHV",
      measurement_interval_days: 60,
      growth_velocity_cm_month: null,
      growth_alerts: [],
      training_implications: null,
    },
    {
      athlete_id: 2,
      athlete_name: "María Gómez Ficticia",
      sex: "F",
      age_decimal: 13.1,
      category: "Sub-15",
      measurement_status: "due_soon",
      last_measurement_date: "2026-04-01",
      next_due_date: "2026-06-01",
      days_overdue: -5,
      current_phv_status: "Circa-PHV",
      measurement_interval_days: 60,
      growth_velocity_cm_month: null,
      growth_alerts: [],
      training_implications: null,
    },
    {
      athlete_id: 3,
      athlete_name: "Ana Ruiz Ficticia",
      sex: "F",
      age_decimal: 14.5,
      category: "Sub-15",
      measurement_status: "ok",
      last_measurement_date: "2026-05-20",
      next_due_date: "2026-07-20",
      days_overdue: null,
      current_phv_status: "Post-PHV",
      measurement_interval_days: 60,
      growth_velocity_cm_month: null,
      growth_alerts: [],
      training_implications: null,
    },
  ],
};

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useDashboardStats", () => {
  beforeEach(() => {
    useAuthStore.setState({ accessToken: "fake-access-token" });
  });

  afterEach(() => {
    useAuthStore.setState({ accessToken: null });
  });

  it("deriva las tarjetas del dashboard desde /api/athletes/alerts", async () => {
    mswServer.use(
      http.get("*/api/athletes/alerts", () => HttpResponse.json(alertsPayload)),
    );

    const { result } = renderHook(() => useDashboardStats(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.total).toBe(3);
    expect(result.current.lastEvaluation).toBe("2026-05-20");
    expect(result.current.phvVigentes).toBe(2);
    expect(result.current.phvTotal).toBe(3);
    expect(result.current.isError).toBe(false);
  });

  it("no dispara ningún GET /api/athletes/{id} (regresión N+1)", async () => {
    const athleteDetailCalls: string[] = [];

    mswServer.use(
      http.get("*/api/athletes/alerts", () => HttpResponse.json(alertsPayload)),
      http.get("*/api/athletes/:id", ({ params }) => {
        athleteDetailCalls.push(String(params.id));
        return HttpResponse.json({});
      }),
    );

    const { result } = renderHook(() => useDashboardStats(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(athleteDetailCalls).toHaveLength(0);
  });
});
