/**
 * Tests para AnxietyDashboardPage — soporte de query string `?athlete=`.
 *
 * Contexto (tarea previa, ya completada): sin `?athlete=`, la página arranca
 * en la pestaña "Crear" (comportamiento previo, sin cambios). Con
 * `?athlete=42` (entero positivo), arranca en la pestaña "Individual" y
 * pre-siembra el selector de deportista para que la consulta de la serie
 * dispare de inmediato, sin que el coach tenga que volver a seleccionar en
 * el desplegable ni pulsar "Ver".
 *
 * Se mockean los sub-componentes pesados (AssessmentWizard, GroupPanel,
 * ImportDialog, IndividualPanel) — cada uno ya tiene su propia suite — y los
 * hooks que llaman a la API (useAthleteSeries, useGroupByEvent, useAthletes)
 * para que esta suite se enfoque exclusivamente en la selección de pestaña y
 * el pre-sembrado del deportista, sin HTTP real.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";

import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { AnxietyDashboardPage } from "../AnxietyDashboardPage";
import {
  useAthleteSeries,
  useGroupByEvent,
} from "@/hooks/anxiety/useAnxietyDashboards";
import { useAthletes } from "@/hooks/athletes/useAthletes";
import type { AthleteListOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Mocks — hooks que llaman a la API
// ---------------------------------------------------------------------------

vi.mock("@/hooks/anxiety/useAnxietyDashboards", () => ({
  useAthleteSeries: vi.fn(),
  useGroupByEvent: vi.fn(),
}));

vi.mock("@/hooks/athletes/useAthletes", () => ({
  useAthletes: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Mocks — sub-componentes pesados (ya probados en sus propias suites)
// ---------------------------------------------------------------------------

vi.mock("@/components/anxiety/AssessmentWizard", () => ({
  AssessmentWizard: () => <div data-testid="assessment-wizard">Crear evaluación</div>,
}));

vi.mock("@/components/anxiety/GroupPanel", () => ({
  GroupPanel: () => <div data-testid="group-panel">Panel grupal</div>,
}));

vi.mock("@/components/anxiety/ImportDialog", () => ({
  ImportDialog: () => <div data-testid="import-dialog">Importar CSV</div>,
}));

vi.mock("@/components/anxiety/IndividualPanel", () => ({
  IndividualPanel: ({ series }: { series: { athlete_id: number } }) => (
    <div data-testid="individual-panel">Serie de {series.athlete_id}</div>
  ),
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ATHLETES: AthleteListOut = {
  items: [
    {
      id: 42,
      user_id: 100,
      first_name: "Ana",
      last_name: "Pérez",
      birth_date: "2013-06-15",
      sex: Sex.F,
      club_join_date: "2024-01-01",
      years_in_club: 2.3,
      age_decimal: 12.8,
      category: "Pre-juvenil A",
      club_id: 1,
      created_at: "2026-01-01T00:00:00Z",
    },
    {
      id: 7,
      user_id: 101,
      first_name: "Luis",
      last_name: "Gómez",
      birth_date: "2012-03-10",
      sex: Sex.M,
      club_join_date: "2023-01-01",
      years_in_club: 3.5,
      age_decimal: 13.4,
      category: "Juvenil A",
      club_id: 1,
      created_at: "2026-01-01T00:00:00Z",
    },
  ],
  total: 2,
};

function getSelectedTab() {
  return screen.getAllByRole("tab").find((t) => t.getAttribute("aria-selected") === "true");
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();

  vi.mocked(useAthletes).mockReturnValue({
    data: ATHLETES,
    isLoading: false,
  } as unknown as ReturnType<typeof useAthletes>);

  vi.mocked(useAthleteSeries).mockReturnValue({
    data: undefined,
    isLoading: false,
  } as unknown as ReturnType<typeof useAthleteSeries>);

  vi.mocked(useGroupByEvent).mockReturnValue({
    data: undefined,
    isLoading: false,
  } as unknown as ReturnType<typeof useGroupByEvent>);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AnxietyDashboardPage — query string ?athlete=", () => {
  it('sin parámetro de query, arranca en la pestaña "Crear"', () => {
    renderWithProviders(<AnxietyDashboardPage />, {
      initialEntries: ["/anxiety"],
    });

    const selected = getSelectedTab();
    expect(selected).toHaveTextContent("Crear");
    expect(screen.getByTestId("assessment-wizard")).toBeInTheDocument();
    expect(screen.queryByTestId("individual-panel")).not.toBeInTheDocument();

    // La pestaña "Individual" no se monta -> no debe pre-sembrar ni disparar
    // la consulta de la serie.
    expect(useAthleteSeries).not.toHaveBeenCalled();
  });

  it('con ?athlete=42, arranca en la pestaña "Individual"', () => {
    renderWithProviders(<AnxietyDashboardPage />, {
      initialEntries: ["/anxiety?athlete=42"],
    });

    const selected = getSelectedTab();
    expect(selected).toHaveTextContent("Individual");
    expect(screen.queryByTestId("assessment-wizard")).not.toBeInTheDocument();
  });

  it("con ?athlete=42, pre-siembra el selector de deportista y dispara la consulta de la serie sin pulsar “Ver”", () => {
    renderWithProviders(<AnxietyDashboardPage />, {
      initialEntries: ["/anxiety?athlete=42"],
    });

    // El hook de la serie se llamó de inmediato con el atleta 42, instrumento
    // por defecto csai2r, y enabled=true — sin interacción del coach.
    expect(useAthleteSeries).toHaveBeenCalledWith(42, "csai2r", true);

    // El desplegable de deportista queda pre-seleccionado en el 42 (Ana Pérez).
    const select = screen.getByLabelText("Deportista") as HTMLSelectElement;
    expect(select.value).toBe("42");
  });

  it("con ?athlete=42, renderiza el panel individual cuando la serie ya resolvió", () => {
    vi.mocked(useAthleteSeries).mockReturnValue({
      data: { athlete_id: 42 },
      isLoading: false,
    } as unknown as ReturnType<typeof useAthleteSeries>);

    renderWithProviders(<AnxietyDashboardPage />, {
      initialEntries: ["/anxiety?athlete=42"],
    });

    expect(screen.getByTestId("individual-panel")).toHaveTextContent("Serie de 42");
  });

  it('con un ?athlete= inválido (0, negativo o no numérico), arranca en "Crear" igual que sin parámetro', () => {
    renderWithProviders(<AnxietyDashboardPage />, {
      initialEntries: ["/anxiety?athlete=-3"],
    });

    const selected = getSelectedTab();
    expect(selected).toHaveTextContent("Crear");
  });

  it("no tiene violaciones de accesibilidad en el estado por defecto (pestaña Crear)", async () => {
    const { container } = renderWithProviders(<AnxietyDashboardPage />, {
      initialEntries: ["/anxiety"],
    });

    await waitFor(() => expect(screen.getByTestId("assessment-wizard")).toBeInTheDocument());

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de accesibilidad con ?athlete=42 (pestaña Individual pre-sembrada)", async () => {
    const { container } = renderWithProviders(<AnxietyDashboardPage />, {
      initialEntries: ["/anxiety?athlete=42"],
    });

    await waitFor(() =>
      expect(screen.getByLabelText("Deportista")).toBeInTheDocument(),
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
