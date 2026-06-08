/**
 * InsightsTabStale — pruebas del badge "Análisis desactualizado" en el
 * contexto del tab de insights de competencias (US4 / FR-018 / FR-029).
 *
 * Verifica que:
 *  1. El `StaleAnalysisBadge` aparece en una card cuando el ítem tiene
 *     `stale_run_id` no nulo (análisis invalidado por re-ingesta).
 *  2. El badge NO aparece cuando `stale_run_id` es null/ausente (estado normal).
 *  3. Click en "Re-ejecutar" abre el modal de confirmación (no dispara aún —
 *     respeta el requisito D5/FR-029 de acción manual + confirmación explícita).
 *  4. Confirmar en el modal dispara la mutación `useReExecuteRun` con el runId.
 *  5. El click en "Re-ejecutar" NO propaga al card y no navega al atleta.
 *  6. jest-axe: el tab con badge stale no tiene violaciones a11y.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

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

const mockReExecuteMutate = vi.fn();
vi.mock("@/hooks/ai/useRaceRun", () => ({
  useReExecuteRun: () => ({
    mutate: mockReExecuteMutate,
    isPending: false,
  }),
}));

import { InsightsTab } from "@/components/competitions/tabs/InsightsTab";
import type { ClubInsightByRaceItem } from "@/types/athleteRaceAnalysis.types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const INSIGHT_STALE: ClubInsightByRaceItem = {
  athlete_id: 145,
  athlete_display_name: "Isabel Quinonez",
  valida_num: 4,
  insight_id: 99,
  summary_excerpt: "Tercer lugar, progreso en frenada.",
  generated_at: "2026-05-25T19:49:00",
  confidence: "medium",
  stale_run_id: "run-stale-abc123",
};

const INSIGHT_FRESH: ClubInsightByRaceItem = {
  athlete_id: 201,
  athlete_display_name: "Mateo Perez",
  valida_num: 4,
  insight_id: 77,
  summary_excerpt: "Segunda posición, buen ritmo.",
  generated_at: "2026-05-25T20:00:00",
  confidence: "high",
  stale_run_id: null,
};

const INSIGHT_NO_RUN: ClubInsightByRaceItem = {
  athlete_id: 310,
  athlete_display_name: "Camila Torres",
  valida_num: 4,
  insight_id: null,
  summary_excerpt: null,
  generated_at: null,
  confidence: null,
  stale_run_id: null,
};

function mkResponse(items: ClubInsightByRaceItem[]) {
  return {
    data: {
      race_event_id: 5,
      race_event_label: "Válida IV — Cali",
      total_athletes: items.length,
      items,
    },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  };
}

function renderTab(raceEventId = 5) {
  return render(
    <MemoryRouter>
      <InsightsTab raceEventId={raceEventId} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("InsightsTab — badge Análisis desactualizado (FR-018)", () => {
  it("muestra el StaleAnalysisBadge cuando el ítem tiene stale_run_id", () => {
    mockUseClubInsightsByRace.mockReturnValue(
      mkResponse([INSIGHT_STALE]),
    );
    renderTab();

    expect(
      screen.getByTestId("insights-tab-stale-badge-145"),
    ).toBeInTheDocument();
    // El badge en sí
    expect(screen.getByTestId("stale-analysis-badge")).toBeInTheDocument();
    expect(screen.getByText(/Análisis desactualizado/i)).toBeInTheDocument();
    // El botón de re-ejecutar
    expect(screen.getByTestId("stale-reexecute-button")).toBeInTheDocument();
  });

  it("NO muestra el badge cuando stale_run_id es null (análisis vigente)", () => {
    mockUseClubInsightsByRace.mockReturnValue(
      mkResponse([INSIGHT_FRESH]),
    );
    renderTab();

    expect(
      screen.queryByTestId("insights-tab-stale-badge-201"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("stale-analysis-badge"),
    ).not.toBeInTheDocument();
  });

  it("NO muestra el badge en ítems sin insight_id (sin análisis generado)", () => {
    mockUseClubInsightsByRace.mockReturnValue(
      mkResponse([INSIGHT_NO_RUN]),
    );
    renderTab();

    expect(
      screen.queryByTestId("stale-analysis-badge"),
    ).not.toBeInTheDocument();
  });

  it("con múltiples ítems: solo el stale recibe badge", () => {
    mockUseClubInsightsByRace.mockReturnValue(
      mkResponse([INSIGHT_STALE, INSIGHT_FRESH, INSIGHT_NO_RUN]),
    );
    renderTab();

    // Solo el ítem 145 tiene badge
    expect(
      screen.getByTestId("insights-tab-stale-badge-145"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("insights-tab-stale-badge-201"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("insights-tab-stale-badge-310"),
    ).not.toBeInTheDocument();
  });
});

describe("InsightsTab — acción Re-ejecutar (FR-029: manual + confirmación)", () => {
  it("click en Re-ejecutar abre el modal de confirmación (D5: no dispara aún la mutación)", async () => {
    mockUseClubInsightsByRace.mockReturnValue(
      mkResponse([INSIGHT_STALE]),
    );
    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getByTestId("stale-reexecute-button"));

    // El modal de confirmación aparece con el texto esperado
    expect(
      screen.getByText(/Se generará un nuevo análisis/i),
    ).toBeInTheDocument();
    // La mutación NO se ha disparado aún (requiere confirmación explícita)
    expect(mockReExecuteMutate).not.toHaveBeenCalled();
  });

  it("confirmar en el modal dispara la mutación con el runId correcto", async () => {
    mockUseClubInsightsByRace.mockReturnValue(
      mkResponse([INSIGHT_STALE]),
    );
    mockReExecuteMutate.mockImplementation((_runId: string, opts?: { onSuccess?: (res: { run_id: string }) => void }) => {
      opts?.onSuccess?.({ run_id: "new-run-xyz" });
    });

    const user = userEvent.setup();
    renderTab();

    // Abrir modal
    await user.click(screen.getByTestId("stale-reexecute-button"));

    // Confirmar dentro del modal
    const confirmBtn = screen.getByRole("button", { name: "Re-ejecutar" });
    await user.click(confirmBtn);

    await waitFor(() =>
      expect(mockReExecuteMutate).toHaveBeenCalledWith(
        "run-stale-abc123",
        expect.any(Object),
      ),
    );
  });

  it("click en Re-ejecutar NO navega al perfil del atleta (propagation stopped)", async () => {
    mockUseClubInsightsByRace.mockReturnValue(
      mkResponse([INSIGHT_STALE]),
    );
    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getByTestId("stale-reexecute-button"));

    // La navegación al perfil del atleta NO debe haberse disparado
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});

describe("InsightsTab — a11y con badge stale", () => {
  it("jest-axe: tab con ítem stale no tiene violaciones de accesibilidad", async () => {
    mockUseClubInsightsByRace.mockReturnValue(
      mkResponse([INSIGHT_STALE, INSIGHT_FRESH, INSIGHT_NO_RUN]),
    );
    const { container } = renderTab();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
