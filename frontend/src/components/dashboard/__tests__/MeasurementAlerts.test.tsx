import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { MeasurementAlerts } from "../MeasurementAlerts";
import type { AlertsSummary, AthleteAlert } from "@/types/alerts.types";

vi.mock("@/hooks/athletes/useAlerts", () => ({
  useAlerts: vi.fn(),
}));

import { useAlerts } from "@/hooks/athletes/useAlerts";

const mockUseAlerts = vi.mocked(useAlerts);

function makeAlert(overrides: Partial<AthleteAlert>): AthleteAlert {
  return {
    athlete_id: 1,
    athlete_name: "Atleta Ficticio",
    sex: "M",
    age_decimal: 12,
    category: "sub-13",
    measurement_status: "overdue",
    last_measurement_date: null,
    next_due_date: null,
    days_overdue: 10,
    current_phv_status: null,
    measurement_interval_days: 90,
    growth_velocity_cm_month: null,
    growth_alerts: [],
    training_implications: null,
    ...overrides,
  };
}

function makeSummary(athletes: AthleteAlert[]): AlertsSummary {
  return {
    overdue: athletes.filter((a) => a.measurement_status === "overdue").length,
    due_soon: athletes.filter((a) => a.measurement_status === "due_soon").length,
    ok: athletes.filter((a) => a.measurement_status === "ok").length,
    never_measured: athletes.filter((a) => a.measurement_status === "never").length,
    rapid_growth_count: 0,
    athletes,
  };
}

function renderComponent() {
  return render(
    <MemoryRouter>
      <MeasurementAlerts />
    </MemoryRouter>
  );
}

describe("MeasurementAlerts", () => {
  it("muestra maximo 8 filas cuando hay 40 atletas accionables", () => {
    const athletes: AthleteAlert[] = Array.from({ length: 40 }, (_, i) =>
      makeAlert({
        athlete_id: i + 1,
        athlete_name: `Atleta Ficticio ${i + 1}`,
        measurement_status: "overdue",
        days_overdue: i + 1,
      })
    );
    mockUseAlerts.mockReturnValue({
      data: makeSummary(athletes),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(8);
  });

  it("ordena: vencidas (desc por dias) primero, luego proximas (asc por dias), luego sin medir", () => {
    const athletes: AthleteAlert[] = [
      makeAlert({ athlete_id: 1, athlete_name: "Nunca Medido Ficticio", measurement_status: "never", days_overdue: null }),
      makeAlert({ athlete_id: 2, athlete_name: "Proxima Lejana Ficticio", measurement_status: "due_soon", days_overdue: -10 }),
      makeAlert({ athlete_id: 3, athlete_name: "Vencida Chica Ficticio", measurement_status: "overdue", days_overdue: 5 }),
      makeAlert({ athlete_id: 4, athlete_name: "Vencida Grande Ficticio", measurement_status: "overdue", days_overdue: 20 }),
      makeAlert({ athlete_id: 5, athlete_name: "Proxima Cercana Ficticio", measurement_status: "due_soon", days_overdue: -2 }),
    ];
    mockUseAlerts.mockReturnValue({
      data: makeSummary(athletes),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    const names = screen
      .getAllByRole("listitem")
      .map((li) => li.querySelector("a")?.textContent);

    expect(names).toEqual([
      "Vencida Grande Ficticio",
      "Vencida Chica Ficticio",
      "Proxima Cercana Ficticio",
      "Proxima Lejana Ficticio",
      "Nunca Medido Ficticio",
    ]);
  });

  it('muestra "Ver todas (N)" con link a /athletes cuando hay mas de 8 accionables', () => {
    const athletes: AthleteAlert[] = Array.from({ length: 40 }, (_, i) =>
      makeAlert({ athlete_id: i + 1, athlete_name: `Atleta Ficticio ${i + 1}` })
    );
    mockUseAlerts.mockReturnValue({
      data: makeSummary(athletes),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    const link = screen.getByRole("link", { name: "Ver todas (40)" });
    expect(link).toHaveAttribute("href", "/athletes");
  });

  it('no muestra el link "Ver todas" cuando hay 8 o menos accionables', () => {
    const athletes: AthleteAlert[] = Array.from({ length: 8 }, (_, i) =>
      makeAlert({ athlete_id: i + 1, athlete_name: `Atleta Ficticio ${i + 1}` })
    );
    mockUseAlerts.mockReturnValue({
      data: makeSummary(athletes),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    expect(screen.queryByRole("link", { name: /Ver todas/ })).not.toBeInTheDocument();
  });

  it("omite la lista cuando no hay atletas accionables (todos al dia)", () => {
    const athletes: AthleteAlert[] = [
      makeAlert({ athlete_id: 1, athlete_name: "Al Dia Ficticio", measurement_status: "ok", days_overdue: null }),
    ];
    mockUseAlerts.mockReturnValue({
      data: makeSummary(athletes),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Ver todas/ })).not.toBeInTheDocument();
  });
});

describe("MeasurementAlerts — training_implications en crecimiento acelerado", () => {
  it("muestra training_implications cuando existe, reemplazando la guía genérica", () => {
    const athlete = makeAlert({
      measurement_status: "ok",
      days_overdue: null,
      growth_alerts: ["rapid_growth"],
      growth_velocity_cm_month: 1.2,
      training_implications: "Reducir intensidad de saltos y aterrizajes por 2 semanas.",
    });
    mockUseAlerts.mockReturnValue({
      data: makeSummary([athlete]),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    expect(
      screen.getByText(/Reducir intensidad de saltos y aterrizajes por 2 semanas\./)
    ).toBeInTheDocument();
    expect(screen.queryByText(/Revisar carga de entrenamiento\./)).not.toBeInTheDocument();
  });

  it("usa la guía genérica cuando training_implications es null, sin hueco de texto", () => {
    const athlete = makeAlert({
      measurement_status: "ok",
      days_overdue: null,
      growth_alerts: ["rapid_growth"],
      growth_velocity_cm_month: 1.2,
      training_implications: null,
    });
    mockUseAlerts.mockReturnValue({
      data: makeSummary([athlete]),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    expect(screen.getByText(/Revisar carga de entrenamiento\./)).toBeInTheDocument();
  });
});
