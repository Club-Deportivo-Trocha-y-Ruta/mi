/**
 * Tests vitest — SessionAssistantPage.
 *
 * Cubre:
 *  - Regresión T045: el h1 es "Insights IA" (no "Asistente IA").
 *  - T053: la pista pre-lanzamiento de presupuesto/concurrencia de IA
 *    (`AIBudgetHint`, mismo patrón que `AnalyzeAthleteButton`/
 *    `GroupAnalysisPanel`) se muestra en el entry point de la página —
 *    sin dato → sin hint; warning → hint ámbar; exhausted → explicación
 *    en texto plano antes de cualquier interacción con el asistente.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { AIStatusResponse } from "@/types/ai.types";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel) =>
    sel({
      user: { id: 7, role: "coach", club_ids: [1] },
    }),
  ),
}));

vi.mock("@/hooks/athletes/useAthletes", () => ({
  useAthletes: () => ({ data: { items: [] } }),
}));

let mockAIStatusData: AIStatusResponse | undefined = undefined;
vi.mock("@/hooks/ai/useAIStatus", () => ({
  useAIStatus: () => ({ data: mockAIStatusData, isError: false }),
}));

// Lazy-loaded panel — mocked to avoid pulling its full dependency tree.
vi.mock(
  "@/components/training/session-wizard/ai-assistant/SessionAssistantPanel",
  () => ({
    SessionAssistantPanel: () => (
      <div data-testid="session-assistant-panel" />
    ),
  }),
);

import { SessionAssistantPage } from "@/routes/training/SessionAssistantPage";

function renderPage() {
  return render(
    <MemoryRouter>
      <SessionAssistantPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAIStatusData = undefined;
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SessionAssistantPage — naming (regresión T045)", () => {
  it('renderiza el h1 "Insights IA"', () => {
    renderPage();
    expect(
      screen.getByRole("heading", { level: 1, name: "Insights IA" }),
    ).toBeInTheDocument();
  });
});

describe("SessionAssistantPage — pista pre-lanzamiento de IA (T053)", () => {
  it("sin dato de useAIStatus() no muestra ningún hint", () => {
    renderPage();
    expect(
      screen.queryByTestId("ai-budget-hint-warning"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("ai-budget-hint-exhausted"),
    ).not.toBeInTheDocument();
  });

  it("budget_status='warning' muestra el hint ámbar con el % restante", () => {
    mockAIStatusData = {
      budget_status: "warning",
      budget_remaining_pct: 15,
      concurrency_available: true,
      est_wait_seconds: 20,
    };
    renderPage();
    expect(screen.getByTestId("ai-budget-hint-warning")).toHaveTextContent(
      "Presupuesto de IA: 15% restante",
    );
  });

  it("budget_status='exhausted' muestra la explicación en texto plano", () => {
    mockAIStatusData = {
      budget_status: "exhausted",
      budget_remaining_pct: 0,
      concurrency_available: true,
      est_wait_seconds: 0,
    };
    renderPage();
    expect(
      screen.getByTestId("ai-budget-hint-exhausted"),
    ).toHaveTextContent(
      "Presupuesto mensual de IA agotado. Los análisis se reactivan el próximo ciclo.",
    );
  });

  it("concurrency_available=false muestra la pista de alta demanda", () => {
    mockAIStatusData = {
      budget_status: "ok",
      budget_remaining_pct: 80,
      concurrency_available: false,
      est_wait_seconds: 12,
    };
    renderPage();
    expect(
      screen.getByTestId("ai-budget-hint-concurrency"),
    ).toHaveTextContent("Alta demanda — espera ≈12s");
  });
});
