import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/hooks/parents/useMyAthletes");
vi.mock("@/api/trainingSessions");

import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useParentMonthlySummary } from "@/api/trainingSessions";
import { ParentMonthlyOverviewPage } from "./ParentMonthlyOverviewPage";
import type { MyAthleteOut } from "@/types/parent.types";
import type { ParentMonthlySummary } from "@/types/trainingSession.types";

function makeAthlete(id: number, name: string): MyAthleteOut {
  return {
    athlete_id: id,
    athlete_first_name: name,
    athlete_last_name: "García",
    birth_date: "2013-01-01",
    sex: "M" as any,
    age_decimal: 13.2,
    category: "U15",
    relationship: "padre" as any,
    latest_anthropometry_date: null,
    maturation_status: null,
    standing_height_cm: null,
    weight_kg: null,
    measurement_status: "never",
  };
}

function makeSummary(athleteId: number, name: string): ParentMonthlySummary {
  return {
    athlete_id: athleteId,
    athlete_name: name,
    year: 2026,
    month: 4,
    count_present: 8,
    count_total: 10,
    percentage: 80,
    focos_técnicos: ["Frenada", "Virajes"],
  };
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

function renderPage() {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ParentMonthlyOverviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  queryClient.clear();
});

describe("ParentMonthlyOverviewPage", () => {
  it("renderiza una card por atleta", () => {
    const atleta1 = makeAthlete(10, "Sebastián");
    const atleta2 = makeAthlete(20, "Valentina");

    (useMyAthletes as any).mockReturnValue({
      data: [atleta1, atleta2],
      isLoading: false,
      isError: false,
    });

    (useParentMonthlySummary as any).mockReturnValue({
      data: [makeSummary(10, "Sebastián García"), makeSummary(20, "Valentina García")],
      isLoading: false,
    });

    renderPage();

    expect(screen.getByText("Sebastián García")).toBeInTheDocument();
    expect(screen.getByText("Valentina García")).toBeInTheDocument();
  });

  it("muestra el porcentaje de asistencia", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián")],
      isLoading: false,
      isError: false,
    });

    (useParentMonthlySummary as any).mockReturnValue({
      data: [makeSummary(10, "Sebastián García")],
      isLoading: false,
    });

    renderPage();

    expect(screen.getByText(/8\/10 sesiones \(80%\)/)).toBeInTheDocument();
  });

  it("muestra los focos técnicos cubiertos", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián")],
      isLoading: false,
      isError: false,
    });

    (useParentMonthlySummary as any).mockReturnValue({
      data: [makeSummary(10, "Sebastián García")],
      isLoading: false,
    });

    renderPage();

    expect(screen.getByText("Frenada")).toBeInTheDocument();
    expect(screen.getByText("Virajes")).toBeInTheDocument();
  });

  it("muestra 'Sin datos para este mes' si no hay summary", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián")],
      isLoading: false,
      isError: false,
    });

    (useParentMonthlySummary as any).mockReturnValue({ data: [], isLoading: false });

    renderPage();

    expect(screen.getByText("Sin datos para este mes.")).toBeInTheDocument();
  });

  it("NO llama al endpoint de reportes del club (solo resumen propio)", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(10, "Sebastián")],
      isLoading: false,
      isError: false,
    });

    (useParentMonthlySummary as any).mockReturnValue({ data: [], isLoading: false });

    renderPage();

    // Si el componente llamara a un endpoint de clubes, aparecería ai_summary o
    // texto del reporte agregado. Verificamos que no haya nada de eso.
    expect(screen.queryByText(/ai_summary/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Reporte generado por IA/i)).not.toBeInTheDocument();
    // Verificamos que useParentMonthlySummary se llamó (endpoint de padres)
    expect(useParentMonthlySummary).toHaveBeenCalled();
  });
});
