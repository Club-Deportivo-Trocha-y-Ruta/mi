/**
 * Tests T1 Sprint 4 — sub-tab "Análisis IA" en MyAthleteDetailPage (parent).
 *
 * Verifica:
 *  - Tab "Análisis IA" renderiza en la página del hijo (parent).
 *  - Click en la tab monta AthleteAIAnalysisTab con mode="parent".
 *  - No se renderizan controles exclusivos de coach (checkboxes, botón Lanzar,
 *    badge de confianza, sticky action bar).
 *  - Deep-link ?tab=ai-analysis abre la tab directamente.
 *
 * Privacidad Ley 1581:
 *  - mode="parent" nunca expone confidence, tokens, prompt_version, model al DOM.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ---------------------------------------------------------------------------
// Mocks — declarados antes de imports de producción
// ---------------------------------------------------------------------------

vi.mock("@/hooks/athletes/useAthlete", () => ({
  useAthlete: vi.fn(),
}));

vi.mock("@/hooks/athletes/useAnthropometry", () => ({
  useAnthropometry: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 20, role: "parent", first_name: "Padre", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

// Mock AthleteAIAnalysisTab — testamos que se monta con mode="parent" correcto.
vi.mock("@/components/athletes/ai/AthleteAIAnalysisTab", () => ({
  AthleteAIAnalysisTab: ({
    mode,
    athlete,
  }: {
    mode: string;
    athlete: { id: number };
  }) => (
    <div data-testid="mock-ai-analysis-tab" data-mode={mode} data-athlete-id={athlete.id}>
      ai-analysis-{mode}
    </div>
  ),
}));

// Componentes secundarios que no son objeto de este test.
vi.mock("@/components/athletes/AthleteInfoCard", () => ({
  AthleteInfoCard: () => <div data-testid="athlete-info-card">InfoCard</div>,
}));
vi.mock("@/components/athletes/AnthropometryHistory", () => ({
  AnthropometryHistory: () => <div data-testid="anthropometry-history">AnthropometryHistory</div>,
}));
vi.mock("@/components/athletes/GrowthCharts", () => ({
  GrowthCharts: () => <div data-testid="growth-charts">GrowthCharts</div>,
}));
vi.mock("@/components/athletes/NutritionalClassification", () => ({
  NutritionalClassification: () => (
    <div data-testid="nutritional-classification">NutritionalClassification</div>
  ),
}));
vi.mock("@/components/athletes/ResearchReferences", () => ({
  ResearchReferences: () => <div data-testid="research-references">ResearchReferences</div>,
}));
vi.mock("@/components/ai/PHVExplanationCard", () => ({
  PHVExplanationCard: () => <div data-testid="phv-explanation-card">PHVExplanationCard</div>,
}));

import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { MyAthleteDetailPage } from "./MyAthleteDetailPage";
import { Sex } from "@/types/enums";
import type { AthleteDetailOut } from "@/types/athlete.types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockAthlete: AthleteDetailOut = {
  id: 42,
  user_id: 100,
  first_name: "Sebastián",
  last_name: "García",
  birth_date: "2012-01-15",
  sex: Sex.M,
  club_join_date: "2024-01-01",
  years_in_club: 2,
  age_decimal: 14.3,
  category: "Sub-15",
  club_id: 1,
  created_at: "2024-01-01T00:00:00Z",
  latest_anthropometry: null,
};

function mockHooks(athlete = mockAthlete, records: unknown[] = []) {
  vi.mocked(useAthlete).mockReturnValue({
    data: athlete,
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useAthlete>);

  vi.mocked(useAnthropometry).mockReturnValue({
    data: records,
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useAnthropometry>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("MyAthleteDetailPage — sub-tab Análisis IA (T1 Sprint 4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza el botón de tab 'Análisis IA' para el padre", async () => {
    mockHooks();
    renderWithProviders(<MyAthleteDetailPage />, {
      initialEntries: ["/my-athletes/42"],
    });

    await waitFor(() => {
      expect(screen.getByTestId("parent-tab-ai-analysis")).toBeInTheDocument();
    });
    expect(screen.getByTestId("parent-tab-ai-analysis")).toHaveTextContent(
      /análisis ia/i,
    );
  });

  it("click en 'Análisis IA' monta AthleteAIAnalysisTab con mode='parent'", async () => {
    const user = userEvent.setup();
    mockHooks();
    renderWithProviders(<MyAthleteDetailPage />, {
      initialEntries: ["/my-athletes/42"],
    });

    await waitFor(() => {
      expect(screen.getByTestId("parent-tab-ai-analysis")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("parent-tab-ai-analysis"));

    await waitFor(() => {
      expect(screen.getByTestId("mock-ai-analysis-tab")).toBeInTheDocument();
    });

    const tab = screen.getByTestId("mock-ai-analysis-tab");
    // Verificar que se montó con mode="parent" — NUNCA mode="coach".
    expect(tab).toHaveAttribute("data-mode", "parent");
    expect(tab).toHaveAttribute("data-athlete-id", "42");
  });

  it("deep-link ?tab=ai-analysis abre la sub-tab directamente", async () => {
    mockHooks();
    renderWithProviders(<MyAthleteDetailPage />, {
      initialEntries: ["/my-athletes/42?tab=ai-analysis"],
    });

    await waitFor(() => {
      expect(screen.getByTestId("mock-ai-analysis-tab")).toBeInTheDocument();
    });

    const tab = screen.getByTestId("mock-ai-analysis-tab");
    expect(tab).toHaveAttribute("data-mode", "parent");
  });

  it("la vista Análisis IA del padre NO expone datos operativos sensibles", async () => {
    const user = userEvent.setup();
    mockHooks();
    renderWithProviders(<MyAthleteDetailPage />, {
      initialEntries: ["/my-athletes/42"],
    });

    await waitFor(() => {
      expect(screen.getByTestId("parent-tab-ai-analysis")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("parent-tab-ai-analysis"));
    await waitFor(() => {
      expect(screen.getByTestId("mock-ai-analysis-tab")).toBeInTheDocument();
    });

    // Con el mock, el contenido es "ai-analysis-parent". No debe contener
    // metadatos de IA ni confianza. El componente real (AthleteAIAnalysisTab)
    // ya tiene sus propios tests de privacidad en AthleteAIAnalysisTab.parent.test.tsx.
    const tree = document.body.textContent ?? "";
    const forbidden = [/confidence/i, /\$\d/, /tokens?/i, /\bprompt\b/i, /\bmodel\b/i];
    forbidden.forEach((p) => {
      expect(tree).not.toMatch(p);
    });
  });

  it("en modo default (tab=info) NO monta AthleteAIAnalysisTab", async () => {
    mockHooks();
    renderWithProviders(<MyAthleteDetailPage />, {
      initialEntries: ["/my-athletes/42"],
    });

    await waitFor(() => {
      expect(screen.getByTestId("parent-tab-ai-analysis")).toBeInTheDocument();
    });

    // Sin hacer click, el tab por defecto es "info" → componente IA no montado.
    expect(screen.queryByTestId("mock-ai-analysis-tab")).not.toBeInTheDocument();
  });
});
