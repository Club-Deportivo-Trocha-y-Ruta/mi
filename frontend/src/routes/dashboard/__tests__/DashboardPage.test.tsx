import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

import type { AlertsSummary, AthleteAlert } from "@/types/alerts.types";

import { DashboardPage } from "../DashboardPage";

vi.mock("@/api/alerts", () => ({
  getAlerts: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (state: { accessToken: string }) => unknown) =>
    selector({ accessToken: "fake-token" }),
}));

import { getAlerts } from "@/api/alerts";

function buildAlert(overrides: Partial<AthleteAlert>): AthleteAlert {
  return {
    athlete_id: 1,
    athlete_name: "Juan Pérez Ficticio",
    sex: "M",
    age_decimal: 12.5,
    category: "Sub-13",
    measurement_status: "ok",
    last_measurement_date: null,
    next_due_date: null,
    days_overdue: null,
    current_phv_status: null,
    measurement_interval_days: 90,
    growth_velocity_cm_month: null,
    growth_alerts: [],
    training_implications: null,
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.mocked(getAlerts).mockReset();
  });

  it("renders total, last evaluation and PHV vigentes from alerts data", async () => {
    const summary: AlertsSummary = {
      overdue: 1,
      due_soon: 0,
      ok: 2,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: [
        buildAlert({
          athlete_id: 1,
          measurement_status: "ok",
          last_measurement_date: "2026-05-10",
        }),
        buildAlert({
          athlete_id: 2,
          measurement_status: "due_soon",
          last_measurement_date: "2026-06-20",
        }),
        buildAlert({
          athlete_id: 3,
          measurement_status: "overdue",
          last_measurement_date: "2026-04-01",
        }),
      ],
    };
    vi.mocked(getAlerts).mockResolvedValue(summary);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("3")).toBeInTheDocument();
    });

    // Última evaluación: max(last_measurement_date) = 2026-06-20
    const lastEvalHeading = screen.getByText("Última evaluación");
    const lastEvalValue = lastEvalHeading.parentElement?.querySelector("p:last-child");
    expect(lastEvalValue).toHaveTextContent(/20/);
    expect(lastEvalValue).toHaveTextContent(/jun/i);
    expect(lastEvalValue).toHaveTextContent(/2026/);

    // Estado PHV: 2 de 3 con medición vigente (due_soon + ok cuentan, overdue no)
    expect(screen.getByText("2 de 3 con medición vigente")).toBeInTheDocument();
  });

  it("renders \"--\" for last evaluation when no athlete has a measurement date", async () => {
    const summary: AlertsSummary = {
      overdue: 0,
      due_soon: 0,
      ok: 0,
      never_measured: 1,
      rapid_growth_count: 0,
      athletes: [
        buildAlert({
          athlete_id: 1,
          measurement_status: "never",
          last_measurement_date: null,
        }),
      ],
    };
    vi.mocked(getAlerts).mockResolvedValue(summary);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("1")).toBeInTheDocument();
    });

    const lastEvalHeading = screen.getByText("Última evaluación");
    const lastEvalValue = lastEvalHeading.parentElement?.querySelector("p:last-child");
    expect(lastEvalValue).toHaveTextContent("--");

    // Estado PHV: 0 de 1 con medición vigente ("never" no cuenta como vigente)
    expect(screen.getByText("0 de 1 con medición vigente")).toBeInTheDocument();
  });

  it("shows the empty state and \"--\" cards when there are no athletes", async () => {
    const summary: AlertsSummary = {
      overdue: 0,
      due_soon: 0,
      ok: 0,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: [],
    };
    vi.mocked(getAlerts).mockResolvedValue(summary);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("No tienes atletas asignados a un club")).toBeInTheDocument();
    });

    const totalHeading = screen.getByText("Total atletas");
    expect(totalHeading.parentElement?.querySelector("p:last-child")).toHaveTextContent("--");

    const phvHeading = screen.getByText("Estado PHV");
    expect(phvHeading.parentElement?.querySelector("p:last-child")).toHaveTextContent("--");
  });

  it("shows the error state when the alerts request fails", async () => {
    vi.mocked(getAlerts).mockRejectedValue(new Error("network error"));

    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText(
          "No pudimos cargar la información del dashboard. Intenta de nuevo más tarde.",
        ),
      ).toBeInTheDocument();
    });

    const totalHeading = screen.getByText("Total atletas");
    expect(totalHeading.parentElement?.querySelector("p:last-child")).toHaveTextContent("--");
  });

  it("retries the alerts query when clicking \"Reintentar\" and recovers on success", async () => {
    const user = userEvent.setup();
    const summary: AlertsSummary = {
      overdue: 0,
      due_soon: 0,
      ok: 1,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: [
        buildAlert({
          athlete_id: 1,
          measurement_status: "ok",
          last_measurement_date: "2026-06-01",
        }),
      ],
    };
    vi.mocked(getAlerts)
      .mockRejectedValueOnce(new Error("network error"))
      .mockResolvedValueOnce(summary);

    renderPage();

    const retryButton = await screen.findByRole("button", { name: "Reintentar" });
    await user.click(retryButton);

    await waitFor(() => {
      expect(getAlerts).toHaveBeenCalledTimes(2);
    });

    // La consulta se recupera con los datos frescos y el estado de error desaparece.
    await waitFor(() => {
      expect(screen.getByText("1")).toBeInTheDocument();
    });
    expect(
      screen.queryByText(
        "No pudimos cargar la información del dashboard. Intenta de nuevo más tarde.",
      ),
    ).not.toBeInTheDocument();
  });
});
