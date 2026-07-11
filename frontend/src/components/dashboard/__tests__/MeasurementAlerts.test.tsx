import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { MeasurementAlerts } from "../MeasurementAlerts";
import type { AlertsSummary, AthleteAlert } from "@/types/alerts.types";

vi.mock("@/hooks/athletes/useAlerts", () => ({
  useAlerts: vi.fn(),
}));

// `vi.hoisted` corre antes de que los imports se resuelvan — mismo patrón
// que ActivityCard.test.tsx / AthleteLink.test.tsx para poder alternar el rol
// entre tests del mismo archivo. Default "coach" porque los tests
// preexistentes de esta suite asumen que el nombre del atleta es un <a>
// navegable (AthleteLink solo renderiza <Link> para coach — ver
// src/components/shared/AthleteLink.tsx).
const authState = vi.hoisted(() => ({
  role: "coach" as string | undefined,
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (s: { user: { id: number; role: string | undefined } | null }) => unknown,
  ) => selector({ user: { id: 1, role: authState.role } }),
}));

import { useAlerts } from "@/hooks/athletes/useAlerts";

const mockUseAlerts = vi.mocked(useAlerts);

beforeEach(() => {
  authState.role = "coach";
});

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

describe("MeasurementAlerts — enlace al detalle del atleta según rol (AthleteLink)", () => {
  it('admin: el nombre del atleta se renderiza como texto plano, sin navegación (ProtectedRoute bounce en "/athletes/:id")', () => {
    authState.role = "admin";
    const athlete = makeAlert({
      athlete_id: 7,
      athlete_name: "Admin Ficticio",
      measurement_status: "overdue",
      days_overdue: 3,
      growth_alerts: ["rapid_growth"],
      growth_velocity_cm_month: 1.0,
    });
    mockUseAlerts.mockReturnValue({
      data: makeSummary([athlete]),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    // Ningún link en toda la sección — ni en la lista de accionables ni en
    // el banner de crecimiento acelerado (con un solo atleta y sin superar
    // MAX_VISIBLE, tampoco aparece "Ver todas").
    expect(screen.queryAllByRole("link")).toHaveLength(0);

    // El nombre sigue visible como texto plano en ambos sitios de render.
    const nameNodes = screen.getAllByText("Admin Ficticio");
    expect(nameNodes.length).toBeGreaterThan(0);
    nameNodes.forEach((node) => expect(node.tagName).not.toBe("A"));
  });

  it("coach: el nombre del atleta es un link funcional a /athletes/{id}", () => {
    authState.role = "coach";
    const athlete = makeAlert({
      athlete_id: 9,
      athlete_name: "Coach Ficticio",
      measurement_status: "overdue",
      days_overdue: 4,
    });
    mockUseAlerts.mockReturnValue({
      data: makeSummary([athlete]),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    const link = screen.getByRole("link", { name: "Coach Ficticio" });
    expect(link).toHaveAttribute("href", "/athletes/9");
  });

  it("coach: el nombre del atleta en el banner de crecimiento acelerado también es un link funcional", () => {
    authState.role = "coach";
    const athlete = makeAlert({
      athlete_id: 11,
      athlete_name: "Crecimiento Ficticio",
      measurement_status: "ok",
      days_overdue: null,
      growth_alerts: ["rapid_growth"],
      growth_velocity_cm_month: 1.5,
    });
    mockUseAlerts.mockReturnValue({
      data: makeSummary([athlete]),
      isPending: false,
      isError: false,
    } as ReturnType<typeof useAlerts>);

    renderComponent();

    const link = screen.getByRole("link", { name: "Crecimiento Ficticio" });
    expect(link).toHaveAttribute("href", "/athletes/11");
  });
});
