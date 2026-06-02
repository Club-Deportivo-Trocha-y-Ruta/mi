/**
 * Tests vitest — AthleteInsightsPage (PR3 unificación /competitions).
 *
 * Cubre:
 *  - Monta AthleteAIAnalysisTab en modo coach cuando el atleta carga.
 *  - Loading skeleton mientras carga.
 *  - Error state.
 *  - ID inválido.
 *
 * AthleteAIAnalysisTab se mockea (sentinel) para no arrastrar su árbol de
 * subcomponentes/hooks IA — aquí probamos el wiring de la página.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// Sentinel del tab IA (PR7: import directo, sin barrel).
vi.mock("@/components/athletes/ai/AthleteAIAnalysisTab", () => ({
  AthleteAIAnalysisTab: ({ mode }: { mode: string }) => (
    <div data-testid="athlete-ai-tab-sentinel">{`tab-${mode}`}</div>
  ),
}));

const mockUseAthlete = vi.fn();
vi.mock("@/hooks/athletes/useAthlete", () => ({
  useAthlete: (...args: unknown[]) => mockUseAthlete(...args),
}));

let mockId = "144";
vi.mock("react-router-dom", async () => {
  const actual =
    await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useParams: () => ({ id: mockId }),
    Link: actual.Link,
  };
});

import { AthleteInsightsPage } from "@/routes/competitions/insights/AthleteInsightsPage";

function renderPage() {
  return render(
    <MemoryRouter>
      <AthleteInsightsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockId = "144";
});

describe("AthleteInsightsPage", () => {
  it("monta AthleteAIAnalysisTab en modo coach al cargar el atleta", () => {
    mockUseAthlete.mockReturnValue({
      data: { id: 144, first_name: "Juan", last_name: "Garcia" },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getByTestId("athlete-ai-tab-sentinel")).toHaveTextContent(
      "tab-coach",
    );
    expect(screen.getByText("Juan Garcia")).toBeInTheDocument();
  });

  it("muestra skeleton mientras carga", () => {
    mockUseAthlete.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getByTestId("athlete-insights-loading")).toBeInTheDocument();
  });

  it("muestra error state cuando falla la carga", () => {
    mockUseAthlete.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getByTestId("athlete-insights-error")).toBeInTheDocument();
  });

  it("ID inválido muestra alerta y NO consulta", () => {
    mockId = "abc";
    mockUseAthlete.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getByText(/ID de deportista inválido/i)).toBeInTheDocument();
    // useAthlete se llama con enabled=false (segundo arg).
    expect(mockUseAthlete).toHaveBeenCalledWith(NaN, false);
  });
});
