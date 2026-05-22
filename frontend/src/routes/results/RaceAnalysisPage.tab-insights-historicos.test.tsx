/**
 * Tests vitest para el refactor FE-2 de RaceAnalysisPage:
 * tab "Insights históricos" con AthleteCombobox que enruta al perfil
 * del deportista con tab=ai_analysis abierto.
 *
 * Cubre:
 *  - Combobox renderiza y aparece en la tab "Insights históricos".
 *  - Selección de un atleta navega a `/athletes/:id?tab=ai_analysis`.
 *  - Padre con un único hijo se redirige automáticamente.
 *
 * Mockeamos los sub-componentes pesados (StartRunForm, ChatConsole,
 * UnlinkedCompetitorsTab, etc.) y los hooks remotos para mantener el
 * test focalizado en el comportamiento del refactor FE-2.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Spy de useNavigate para verificar redirect.
const navigateSpy = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return {
    ...actual,
    useNavigate: () => navigateSpy,
  };
});

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

vi.mock("@/api/raceAnalysis", () => ({
  startRun: vi.fn(),
  getRunStatus: vi.fn(),
  submitHITLDecision: vi.fn(),
  getRunResult: vi.fn(),
  chatTurn: vi.fn(),
  downloadRunPdf: vi.fn(),
  getRunPdfPath: vi.fn(),
}));

vi.mock("@/hooks/athletes/useAthletes", () => ({
  useAthletes: () => ({
    data: {
      items: [
        {
          id: 11,
          first_name: "Sebastián",
          last_name: "García",
          age_decimal: 13.2,
          category: "Pre-juvenil A",
        },
        {
          id: 12,
          first_name: "Laura",
          last_name: "Pérez",
          age_decimal: 14.5,
          category: "Juvenil A",
        },
      ],
    },
    isLoading: false,
  }),
}));

const useMyAthletesMock = vi.fn();
vi.mock("@/hooks/parents/useMyAthletes", () => ({
  useMyAthletes: () => useMyAthletesMock(),
}));

vi.mock("@/components/ai/StartRunForm", () => ({
  StartRunForm: () => <div data-testid="mock-start-run-form" />,
}));
vi.mock("@/components/ai/AnalysisRunTimeline", () => ({
  AnalysisRunTimeline: () => <div data-testid="mock-run-timeline" />,
}));
vi.mock("@/components/ai/HITLApprovalCard", () => ({
  HITLApprovalCard: () => <div data-testid="mock-hitl" />,
}));
vi.mock("@/components/ai/MarkdownReportViewer", () => ({
  MarkdownReportViewer: () => <div data-testid="mock-md" />,
}));
vi.mock("@/components/ai/PdfDownloadButton", () => ({
  PdfDownloadButton: () => <div data-testid="mock-pdf" />,
}));
vi.mock("@/components/ai/ChatConsole", () => ({
  ChatConsole: () => <div data-testid="mock-chat" />,
}));
vi.mock("@/components/ai/ExplainModeBanner", () => ({
  ExplainModeBanner: () => <div data-testid="mock-explain-banner" />,
}));
vi.mock("@/components/ai/ImportWizard", () => ({
  ImportWizard: () => <div data-testid="mock-import-wizard" />,
}));
vi.mock("@/components/ai/ImportsHistoryList", () => ({
  ImportsHistoryList: () => <div data-testid="mock-imports-history" />,
}));
vi.mock("@/components/race/UnlinkedCompetitorsTab", () => ({
  UnlinkedCompetitorsTab: () => <div data-testid="mock-unlinked-tab" />,
}));

import { useAuthStore } from "@/store/auth.store";
import { RaceAnalysisPage } from "@/routes/results/RaceAnalysisPage";
import { UserRole } from "@/types/enums";

function renderPage(initialEntries = ["/coach/race-analysis"]) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/coach/race-analysis" element={<RaceAnalysisPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RaceAnalysisPage — refactor FE-2 tab 'Insights históricos'", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: coach
    vi.mocked(useAuthStore).mockImplementation((sel: never) =>
      (sel as unknown as (s: unknown) => unknown)({
        accessToken: "test-token",
        user: {
          id: 1,
          role: UserRole.coach,
          first_name: "Coach",
          last_name: "Test",
        },
        isAuthenticated: true,
      }),
    );
    useMyAthletesMock.mockReturnValue({ data: [], isLoading: false });
  });

  it("renderiza la tab 'Insights históricos' con el combobox de atletas", async () => {
    const user = userEvent.setup();
    renderPage();
    // Click en el tab "Insights históricos"
    await user.click(screen.getByText(/insights históricos/i));
    await waitFor(() => {
      expect(screen.getByTestId("history-tab-picker")).toBeInTheDocument();
    });
    expect(screen.getByTestId("history-athlete-combobox")).toBeInTheDocument();
  });

  it("seleccionar un atleta navega a /athletes/:id?tab=ai_analysis (coach)", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByText(/insights históricos/i));
    await waitFor(() => {
      expect(screen.getByTestId("history-athlete-combobox")).toBeInTheDocument();
    });

    // El combobox real puede ser un input o un Radix combobox — buscamos
    // un botón disparador y luego una option con el nombre del atleta.
    const trigger =
      screen.queryByRole("combobox") ??
      screen.queryByRole("button", { name: /deportista/i });
    if (!trigger) throw new Error("No se encontró el trigger del combobox");
    await user.click(trigger);

    // Click el atleta Sebastián
    const option = await screen.findByText(/sebastián garcía/i);
    await user.click(option);

    await waitFor(() => {
      expect(navigateSpy).toHaveBeenCalledWith(
        "/athletes/11?tab=ai_analysis",
      );
    });
  });

  it("parent con un único hijo se redirige automáticamente a /my-athletes/:id", async () => {
    // Re-mock auth como parent
    vi.mocked(useAuthStore).mockImplementation((sel: never) =>
      (sel as unknown as (s: unknown) => unknown)({
        accessToken: "test-token",
        user: {
          id: 99,
          role: UserRole.parent,
          first_name: "Parent",
          last_name: "Test",
        },
        isAuthenticated: true,
      }),
    );
    useMyAthletesMock.mockReturnValue({
      data: [{ athlete_id: 42, first_name: "Hijo", last_name: "Único" }],
      isLoading: false,
    });

    renderPage();
    await waitFor(() => {
      expect(navigateSpy).toHaveBeenCalledWith("/my-athletes/42", {
        replace: true,
      });
    });
  });

  it("parent con MÚLTIPLES hijos NO redirige automáticamente", async () => {
    vi.mocked(useAuthStore).mockImplementation((sel: never) =>
      (sel as unknown as (s: unknown) => unknown)({
        accessToken: "test-token",
        user: {
          id: 99,
          role: UserRole.parent,
          first_name: "Parent",
          last_name: "Test",
        },
        isAuthenticated: true,
      }),
    );
    useMyAthletesMock.mockReturnValue({
      data: [
        { athlete_id: 42, first_name: "Hijo", last_name: "A" },
        { athlete_id: 43, first_name: "Hija", last_name: "B" },
      ],
      isLoading: false,
    });

    renderPage();
    // No debería haber navegación auto
    await waitFor(() => {
      // Confirma que la página renderizó la tabla / explain banner
      expect(screen.getByTestId("mock-explain-banner")).toBeInTheDocument();
    });
    expect(navigateSpy).not.toHaveBeenCalled();
  });
});
