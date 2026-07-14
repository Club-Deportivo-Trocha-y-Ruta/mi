/**
 * Tests vitest — botón "Analizar con IA" por tarjeta en el tab Insights.
 *
 * US4 (feature 010) extendido: el lanzamiento per-atleta también vive en las
 * tarjetas del tab Insights (no solo en la tabla de Resultados).
 *
 * Cubre:
 *  - Visibilidad: coach/admin con season+validaNum ve el botón en cada card
 *    de atleta vinculado (athlete_id > 0); no aparece para masked (id=0),
 *    ni sin season/validaNum, ni para parent.
 *  - Launch directo (sin insight previo) → mutate con {season, valida_nums:[validaNum]}.
 *  - Insight fresco (stale_run_id null) → abre modal; confirmar lanza.
 *  - El click en el botón NO navega al perfil del atleta.
 *  - Label "Analizar con IA" sin insight; "Re-analizar" con insight.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual =
    await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mockUseClubInsightsByRace = vi.fn();
vi.mock("@/hooks/athletes/useClubInsightsByRace", () => ({
  useClubInsightsByRace: (...args: unknown[]) =>
    mockUseClubInsightsByRace(...args),
}));

const mockMutate = vi.fn();
let mockIsPending = false;
vi.mock("@/hooks/athletes/useLaunchAthleteAnalysis", () => ({
  useLaunchAthleteAnalysis: (_athleteId: number) => ({
    mutate: mockMutate,
    isPending: mockIsPending,
  }),
}));

// useAIStatus (T051) — sin datos por defecto: degradación reactiva-only.
vi.mock("@/hooks/ai/useAIStatus", () => ({
  useAIStatus: () => ({ data: undefined, isError: false }),
}));

// useAthleteRunOutcome (FR-013) — no-op en estos tests de visibilidad/flujo;
// su seguimiento del run se prueba en useAthleteRunOutcome.test.ts.
vi.mock("@/hooks/ai/useAthleteRunOutcome", () => ({
  useAthleteRunOutcome: () => ({ failureMessage: null }),
}));

// Aislar de dependencias de hooks/API.
vi.mock("@/components/competitions/insights/GroupAnalysisPanel", () => ({
  GroupAnalysisPanel: () => <div data-testid="group-analysis-panel" />,
}));
vi.mock("@/components/competitions/chat/CompetitionChatPanel", () => ({
  CompetitionChatPanel: () => <div data-testid="competition-chat-panel" />,
}));

import { InsightsTab } from "@/components/competitions/tabs/InsightsTab";

const INSIGHTS = {
  data: {
    race_event_id: 5,
    race_event_label: "Válida IV — Cali",
    total_athletes: 3,
    items: [
      // Con insight fresco (stale_run_id null) → confirmar antes de re-correr.
      {
        athlete_id: 145,
        athlete_display_name: "Isabel Quinonez",
        valida_num: 4,
        insight_id: 99,
        summary_excerpt: "Tercer lugar, progreso en frenada.",
        generated_at: "2026-05-25T19:49:00",
        confidence: "medium",
        stale_run_id: null,
      },
      // Sin insight → launch directo.
      {
        athlete_id: 201,
        athlete_display_name: "Mateo Perez",
        valida_num: 4,
        insight_id: null,
        summary_excerpt: null,
        generated_at: null,
        confidence: null,
      },
      // Masked (vista padre) → nunca botón.
      {
        athlete_id: 0,
        athlete_display_name: "Deportista",
        valida_num: 4,
        insight_id: null,
        summary_excerpt: null,
        generated_at: null,
        confidence: null,
      },
    ],
  },
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
};

function renderTab(
  opts: {
    isCoachOrAdmin?: boolean;
    // null sentinel = pasar undefined explícitamente al componente.
    season?: number | null;
    validaNum?: number | null;
  } = {},
) {
  const season = opts.season === null ? undefined : (opts.season ?? 2026);
  const validaNum =
    opts.validaNum === null ? undefined : (opts.validaNum ?? 4);
  return render(
    <MemoryRouter>
      <InsightsTab
        raceEventId={5}
        hasResults
        isCoachOrAdmin={opts.isCoachOrAdmin ?? true}
        season={season}
        validaNum={validaNum}
      />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockIsPending = false;
  mockUseClubInsightsByRace.mockReturnValue(INSIGHTS);
});

describe("InsightsTab — botón 'Analizar con IA' por tarjeta (visibilidad)", () => {
  it("coach/admin con season+validaNum ve el botón en atletas vinculados", () => {
    renderTab({ isCoachOrAdmin: true });
    expect(screen.getByTestId("ai-launch-btn-145")).toBeInTheDocument();
    expect(screen.getByTestId("ai-launch-btn-201")).toBeInTheDocument();
  });

  it("NO muestra el botón en ítems enmascarados (athlete_id=0)", () => {
    renderTab({ isCoachOrAdmin: true });
    expect(screen.queryByTestId("ai-launch-btn-0")).not.toBeInTheDocument();
  });

  it("NO muestra el botón cuando NO es coach/admin", () => {
    renderTab({ isCoachOrAdmin: false });
    expect(screen.queryByTestId(/^ai-launch-btn-/)).not.toBeInTheDocument();
  });

  it("NO muestra el botón cuando season es undefined", () => {
    renderTab({ isCoachOrAdmin: true, season: null });
    expect(screen.queryByTestId("ai-launch-btn-145")).not.toBeInTheDocument();
  });

  it("NO muestra el botón cuando validaNum es undefined", () => {
    renderTab({ isCoachOrAdmin: true, validaNum: null });
    expect(screen.queryByTestId("ai-launch-btn-145")).not.toBeInTheDocument();
  });

  it("label 'Analizar con IA' sin insight; 'Re-analizar' con insight", () => {
    renderTab({ isCoachOrAdmin: true });
    expect(screen.getByTestId("ai-launch-btn-201")).toHaveTextContent(
      /analizar con ia/i,
    );
    expect(screen.getByTestId("ai-launch-btn-145")).toHaveTextContent(
      /re-analizar/i,
    );
  });
});

describe("InsightsTab — flujo de lanzamiento por tarjeta", () => {
  it("card sin insight → launch directo con {season, valida_nums:[validaNum]}", async () => {
    const user = userEvent.setup();
    renderTab({ isCoachOrAdmin: true });

    await user.click(screen.getByTestId("ai-launch-btn-201"));

    expect(screen.queryByText(/re-ejecutar análisis/i)).not.toBeInTheDocument();
    expect(mockMutate).toHaveBeenCalledWith(
      { season: 2026, valida_nums: [4], event_id: 5 },
      expect.any(Object),
    );
  });

  it("card con insight fresco → abre modal (sin lanzar aún)", async () => {
    const user = userEvent.setup();
    renderTab({ isCoachOrAdmin: true });

    await user.click(screen.getByTestId("ai-launch-btn-145"));

    expect(screen.getByText(/re-ejecutar análisis/i)).toBeInTheDocument();
    expect(mockMutate).not.toHaveBeenCalled();
  });

  it("confirmar en el modal lanza el análisis", async () => {
    const user = userEvent.setup();
    renderTab({ isCoachOrAdmin: true });

    await user.click(screen.getByTestId("ai-launch-btn-145"));
    await user.click(screen.getByRole("button", { name: "Re-ejecutar" }));

    expect(mockMutate).toHaveBeenCalledWith(
      { season: 2026, valida_nums: [4], event_id: 5 },
      expect.any(Object),
    );
  });

  it("on success muestra 'Análisis iniciado' (no link a Insights, ya estamos ahí)", async () => {
    const user = userEvent.setup();
    mockMutate.mockImplementation(
      (_body: unknown, opts: { onSuccess: (res: { run_id: string }) => void }) => {
        opts.onSuccess({ run_id: "run-xyz" });
      },
    );
    renderTab({ isCoachOrAdmin: true });

    await user.click(screen.getByTestId("ai-launch-btn-201"));

    await waitFor(() =>
      expect(screen.getByTestId("ai-launch-success-201")).toBeInTheDocument(),
    );
    expect(screen.getByText(/análisis iniciado/i)).toBeInTheDocument();
    expect(
      screen.queryByTestId("ai-launch-insights-link-201"),
    ).not.toBeInTheDocument();
  });

  it("el click en el botón NO navega al perfil del atleta", async () => {
    const user = userEvent.setup();
    renderTab({ isCoachOrAdmin: true });

    await user.click(screen.getByTestId("ai-launch-btn-201"));

    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
