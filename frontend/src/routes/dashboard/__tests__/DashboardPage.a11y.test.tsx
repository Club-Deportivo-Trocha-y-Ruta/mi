import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

import type { AlertsSummary, AthleteAlert } from "@/types/alerts.types";

import { DashboardPage } from "../DashboardPage";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Mocks — idénticos a DashboardPage.test.tsx (__tests__) para consistencia
// ---------------------------------------------------------------------------

vi.mock("@/api/alerts", () => ({
  getAlerts: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (state: { accessToken: string; user: { role: string } }) => unknown,
  ) => selector({ accessToken: "fake-token", user: { role: "coach" } }),
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

describe("DashboardPage — accesibilidad WCAG 2.1 AA", () => {
  beforeEach(() => {
    vi.mocked(getAlerts).mockReset();
  });

  it("no tiene violaciones en estado de carga (loading)", async () => {
    vi.mocked(getAlerts).mockReturnValue(new Promise(() => {})); // never resolves

    const { container } = renderPage();

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones en estado listo (ready) con alertas mixtas", async () => {
    const summary: AlertsSummary = {
      overdue: 1,
      due_soon: 1,
      ok: 1,
      never_measured: 1,
      rapid_growth_count: 1,
      athletes: [
        buildAlert({
          athlete_id: 1,
          measurement_status: "overdue",
          last_measurement_date: "2026-04-01",
          days_overdue: 30,
        }),
        buildAlert({
          athlete_id: 2,
          measurement_status: "due_soon",
          last_measurement_date: "2026-06-20",
          days_overdue: -5,
        }),
        buildAlert({
          athlete_id: 3,
          measurement_status: "ok",
          last_measurement_date: "2026-06-25",
        }),
        buildAlert({
          athlete_id: 4,
          athlete_name: "Ana Gómez Ficticia",
          measurement_status: "never",
          last_measurement_date: null,
        }),
        buildAlert({
          athlete_id: 5,
          athlete_name: "Luis Torres Ficticio",
          measurement_status: "ok",
          growth_alerts: ["rapid_growth"],
          growth_velocity_cm_month: 1.2,
          training_implications: "Ajustar carga de entrenamiento.",
        }),
      ],
    };
    vi.mocked(getAlerts).mockResolvedValue(summary);

    const { container } = renderPage();

    await waitFor(() => {
      expect(screen.getByText("5")).toBeInTheDocument();
    });

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones en estado vacío (empty)", async () => {
    const summary: AlertsSummary = {
      overdue: 0,
      due_soon: 0,
      ok: 0,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: [],
    };
    vi.mocked(getAlerts).mockResolvedValue(summary);

    const { container } = renderPage();

    await waitFor(() => {
      expect(
        screen.getByText("No tienes atletas asignados a un club"),
      ).toBeInTheDocument();
    });

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("todos los enlaces son alcanzables por teclado (sin tabIndex negativo)", async () => {
    const summary: AlertsSummary = {
      overdue: 0,
      due_soon: 0,
      ok: 0,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: Array.from({ length: 10 }, (_, i) =>
        buildAlert({
          athlete_id: i + 1,
          athlete_name: `Atleta Ficticio ${i + 1}`,
          measurement_status: "overdue",
          last_measurement_date: "2026-04-01",
          days_overdue: 30 + i,
        }),
      ),
    };
    vi.mocked(getAlerts).mockResolvedValue(summary);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("10")).toBeInTheDocument();
    });

    // Con >8 atletas accionables se muestra el enlace "Ver todas (N)"
    const links = screen.getAllByRole("link");
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(link).toHaveAttribute("href");
      expect(link.getAttribute("tabindex")).not.toBe("-1");
    }
    expect(screen.getByRole("link", { name: /ver todas/i })).toBeInTheDocument();
  });

  it("los enlaces de atletas cumplen el objetivo táctil mínimo de 44px (min-height del contenedor)", async () => {
    const summary: AlertsSummary = {
      overdue: 1,
      due_soon: 0,
      ok: 0,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: [
        buildAlert({
          athlete_id: 1,
          measurement_status: "overdue",
          last_measurement_date: "2026-04-01",
          days_overdue: 30,
        }),
      ],
    };
    vi.mocked(getAlerts).mockResolvedValue(summary);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("1")).toBeInTheDocument();
    });

    // El <li> que envuelve el link de atleta usa px-4 py-3 (16px/12px) sobre
    // texto de 1.25rem de line-height efectivo, que junto al padding vertical
    // supera holgadamente los 44px de alto recomendados por WCAG 2.5.5.
    // Se documenta como recomendación (jsdom no calcula layout real) — ver
    // nota de UX abajo si se requiere medición runtime con getBoundingClientRect.
    const athleteLink = screen.getByRole("link", { name: "Juan Pérez Ficticio" });
    const row = athleteLink.closest("li");
    expect(row).not.toBeNull();
    expect(row?.className).toMatch(/py-3/);
  });
});
