/**
 * T022 — Tests para la acción "Analizar con IA" por fila en ResultsTable.
 *
 * Cubre:
 *  - Visibilidad: coach/admin ve el botón solo en filas is_our_club con
 *    athlete_id vinculado; parent nunca lo ve.
 *  - Fila is_our_club pero sin athlete_id → botón no visible.
 *  - Fila rival (is_our_club=false) → botón no visible aunque sea coach.
 *  - Flujo con insight fresco: modal de confirmación → launch al confirmar.
 *  - Flujo sin insight previo: launch directo sin modal.
 *  - Error 429 → copia de error "Límite de análisis simultáneos...".
 *  - Error 503 → copia "Presupuesto mensual de IA agotado...".
 *  - Éxito → link "Ver progreso en Insights".
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

// ---------------------------------------------------------------------------
// Mock: useAuthStore
// ---------------------------------------------------------------------------

const mockUser = vi.fn();
vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((selector: (s: { accessToken: string; user: unknown }) => unknown) =>
    selector({ accessToken: "test-token", user: mockUser() }),
  ),
}));

// ---------------------------------------------------------------------------
// Mock: useLaunchAthleteAnalysis
// ---------------------------------------------------------------------------

const mockMutate = vi.fn();
let mockIsPending = false;
vi.mock("@/hooks/athletes/useLaunchAthleteAnalysis", () => ({
  useLaunchAthleteAnalysis: (_athleteId: number) => ({
    mutate: mockMutate,
    isPending: mockIsPending,
  }),
}));

// ---------------------------------------------------------------------------
// Import after mocks
// ---------------------------------------------------------------------------

import { ResultsTable } from "@/components/competitions/results/ResultsTable";
import { UserRole } from "@/types/enums";
import type { RaceEventResultsResponse, RaceResultRow } from "@/types/raceResults.types";
import type { MeResponse } from "@/types/auth.types";

// insightFreshnessMap helpers

/** No prior insight: athlete 55 is absent from the map */
const NO_INSIGHT_MAP = new Map<number, string | null>();

/** Fresh insight: athlete 55 has stale_run_id == null */
const FRESH_INSIGHT_MAP = new Map<number, string | null>([[55, null]]);

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

/** Base row for our club with a linked athlete. */
function makeOurClubRow(overrides?: Partial<RaceResultRow>): RaceResultRow {
  return {
    result_id: 1001,
    coach_note: null,
    coach_note_updated_at: null,
    position: 1,
    competitor_id: 101,
    display_name: "Isabel Quiñones",
    club_text: "Club Trocha y Ruta",
    athlete_id: 55,
    is_our_club: true,
    status: "finished",
    race_time_ms: 3_540_000,
    laps_behind: null,
    points_awarded: 25,
    bib_number: 7,
    ...overrides,
  };
}

/** Rival row — different club, no athlete_id. */
function makeRivalRow(overrides?: Partial<RaceResultRow>): RaceResultRow {
  return {
    result_id: 1002,
    coach_note: null,
    coach_note_updated_at: null,
    position: 2,
    competitor_id: 202,
    display_name: "Corredor Rival",
    club_text: "Club Rival XCO",
    athlete_id: null,
    is_our_club: false,
    status: "finished",
    race_time_ms: 3_600_000,
    laps_behind: null,
    points_awarded: 20,
    bib_number: 12,
    ...overrides,
  };
}

/** Two-category response with one our-club row (athlete 55) and one rival. */
function makeData(
  ourClubOverrides?: Partial<RaceResultRow>,
): RaceEventResultsResponse {
  return {
    race_event_id: 10,
    categories: [
      {
        category_id: 1,
        code: "INF_M",
        label: "Infantil Masculino",
        rows: [makeOurClubRow(ourClubOverrides), makeRivalRow()],
      },
    ],
  };
}

const COACH_USER: MeResponse = {
  id: 1,
  email: "entrenador@trochyruta.com",
  first_name: "Coach",
  last_name: "Test",
  phone: null,
  role: UserRole.coach,
  is_active: true,
  can_login: true,
  club_ids: [1],
  created_at: "2026-01-01T00:00:00Z",
};

const ADMIN_USER: MeResponse = {
  ...COACH_USER,
  id: 2,
  role: UserRole.admin,
};

const PARENT_USER: MeResponse = {
  ...COACH_USER,
  id: 3,
  role: UserRole.parent,
};

/** No-insight freshness: athlete 55 is absent from the map → undefined */

function renderTable(
  opts: {
    isCoachOrAdmin?: boolean;
    season?: number | null;
    validaNum?: number | null;
    ourClubRow?: Partial<RaceResultRow>;
    insightFreshnessMap?: Map<number, string | null>;
  } = {},
) {
  const qc = makeQueryClient();
  // null sentinel means "explicitly pass undefined to the component"
  const season = opts.season === null ? undefined : (opts.season ?? 2026);
  const validaNum = opts.validaNum === null ? undefined : (opts.validaNum ?? 4);
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ResultsTable
          data={makeData(opts.ourClubRow)}
          season={season}
          validaNum={validaNum}
          isCoachOrAdmin={opts.isCoachOrAdmin ?? true}
          insightFreshnessMap={opts.insightFreshnessMap ?? NO_INSIGHT_MAP}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  mockIsPending = false;
  // Default: coach user
  mockUser.mockReturnValue(COACH_USER);
});

// ---------------------------------------------------------------------------
// Visibility rules
// ---------------------------------------------------------------------------

describe("ResultsTable — visibilidad del botón 'Analizar con IA'", () => {
  it("coach ve el botón en fila is_our_club con athlete_id", () => {
    renderTable({ isCoachOrAdmin: true });
    expect(screen.getByTestId("ai-launch-btn-55")).toBeInTheDocument();
  });

  it("admin ve el botón en fila is_our_club con athlete_id", () => {
    mockUser.mockReturnValue(ADMIN_USER);
    renderTable({ isCoachOrAdmin: true });
    expect(screen.getByTestId("ai-launch-btn-55")).toBeInTheDocument();
  });

  it("parent NUNCA ve el botón (isCoachOrAdmin=false)", () => {
    mockUser.mockReturnValue(PARENT_USER);
    renderTable({ isCoachOrAdmin: false });
    expect(screen.queryByTestId("ai-launch-btn-55")).not.toBeInTheDocument();
  });

  it("el botón NO se muestra en filas de rival (is_our_club=false)", () => {
    renderTable({ isCoachOrAdmin: true });
    // rival competitor_id=202, no athlete_id — button must not be present
    expect(screen.queryByTestId("ai-launch-btn-null")).not.toBeInTheDocument();
    expect(screen.queryByTestId(/ai-launch-btn-202/)).not.toBeInTheDocument();
  });

  it("el botón NO se muestra si is_our_club pero athlete_id es null", () => {
    renderTable({
      isCoachOrAdmin: true,
      ourClubRow: { athlete_id: null },
    });
    // No linked athlete — button for any athlete_id must not appear
    expect(screen.queryByTestId(/^ai-launch-btn-/)).not.toBeInTheDocument();
  });

  it("el botón NO se muestra cuando season es undefined (null sentinel)", () => {
    renderTable({ isCoachOrAdmin: true, season: null });
    expect(screen.queryByTestId("ai-launch-btn-55")).not.toBeInTheDocument();
  });

  it("el botón NO se muestra cuando validaNum es undefined (null sentinel)", () => {
    renderTable({ isCoachOrAdmin: true, validaNum: null });
    expect(screen.queryByTestId("ai-launch-btn-55")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Direct launch (no fresh insight)
// ---------------------------------------------------------------------------

describe("ResultsTable — launch directo cuando no hay insight previo", () => {
  it("clic en Analizar llama mutate directamente sin modal", async () => {
    const user = userEvent.setup();
    renderTable({ isCoachOrAdmin: true, insightFreshnessMap: NO_INSIGHT_MAP });

    await user.click(screen.getByTestId("ai-launch-btn-55"));

    // No modal — no "Re-ejecutar análisis" title
    expect(
      screen.queryByText(/re-ejecutar análisis/i),
    ).not.toBeInTheDocument();

    // mutate called with correct body
    expect(mockMutate).toHaveBeenCalledWith(
      { season: 2026, valida_nums: [4], event_id: 10 },
      expect.any(Object),
    );
  });

  it("on success muestra el link 'Ver progreso en Insights'", async () => {
    const user = userEvent.setup();
    mockMutate.mockImplementation((_body: unknown, opts: { onSuccess: (res: { run_id: string }) => void }) => {
      opts.onSuccess({ run_id: "run-xyz" });
    });
    renderTable({ isCoachOrAdmin: true, insightFreshnessMap: NO_INSIGHT_MAP });

    await user.click(screen.getByTestId("ai-launch-btn-55"));

    await waitFor(() =>
      expect(
        screen.getByTestId("ai-launch-insights-link-55"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/ver progreso en insights/i),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Confirm-on-fresh flow
// ---------------------------------------------------------------------------

describe("ResultsTable — modal de confirmación cuando existe insight fresco", () => {
  it("clic en Analizar abre el modal de confirmación (sin lanzar aún)", async () => {
    const user = userEvent.setup();
    renderTable({ isCoachOrAdmin: true, insightFreshnessMap: FRESH_INSIGHT_MAP });

    await user.click(screen.getByTestId("ai-launch-btn-55"));

    // Modal visible
    expect(screen.getByText(/re-ejecutar análisis/i)).toBeInTheDocument();
    expect(
      screen.getByText(/ya existe un análisis para este deportista/i),
    ).toBeInTheDocument();

    // mutate NOT called yet
    expect(mockMutate).not.toHaveBeenCalled();
  });

  it("confirmar en el modal lanza el análisis", async () => {
    const user = userEvent.setup();
    renderTable({ isCoachOrAdmin: true, insightFreshnessMap: FRESH_INSIGHT_MAP });

    await user.click(screen.getByTestId("ai-launch-btn-55"));

    // Click confirm button inside modal
    const confirmBtn = screen.getByRole("button", { name: "Re-ejecutar" });
    await user.click(confirmBtn);

    expect(mockMutate).toHaveBeenCalledWith(
      { season: 2026, valida_nums: [4], event_id: 10 },
      expect.any(Object),
    );
  });

  it("cancelar en el modal NO lanza el análisis", async () => {
    const user = userEvent.setup();
    renderTable({ isCoachOrAdmin: true, insightFreshnessMap: FRESH_INSIGHT_MAP });

    await user.click(screen.getByTestId("ai-launch-btn-55"));

    const cancelBtn = screen.getByRole("button", { name: "Cancelar" });
    await user.click(cancelBtn);

    expect(mockMutate).not.toHaveBeenCalled();
    // Modal should close
    await waitFor(() =>
      expect(
        screen.queryByText(/ya existe un análisis para este deportista/i),
      ).not.toBeInTheDocument(),
    );
  });
});

// ---------------------------------------------------------------------------
// Error copy
// ---------------------------------------------------------------------------

describe("ResultsTable — copias de error AI", () => {
  function makeError(status: number) {
    return { response: { status } };
  }

  it("error 429 muestra copia 'Límite de análisis simultáneos'", async () => {
    const user = userEvent.setup();
    mockMutate.mockImplementation((_body: unknown, opts: { onError: (e: unknown) => void }) => {
      opts.onError(makeError(429));
    });
    renderTable({ isCoachOrAdmin: true });

    await user.click(screen.getByTestId("ai-launch-btn-55"));

    await waitFor(() =>
      expect(screen.getByTestId("ai-launch-error-55")).toBeInTheDocument(),
    );
    expect(
      screen.getByText(
        /límite de análisis simultáneos alcanzado\. intenta de nuevo en unos minutos\./i,
      ),
    ).toBeInTheDocument();
  });

  it("error 503 muestra copia 'Presupuesto mensual de IA agotado'", async () => {
    const user = userEvent.setup();
    mockMutate.mockImplementation((_body: unknown, opts: { onError: (e: unknown) => void }) => {
      opts.onError(makeError(503));
    });
    renderTable({ isCoachOrAdmin: true });

    await user.click(screen.getByTestId("ai-launch-btn-55"));

    await waitFor(() =>
      expect(screen.getByTestId("ai-launch-error-55")).toBeInTheDocument(),
    );
    expect(
      screen.getByText(
        /presupuesto mensual de ia agotado\. los análisis se reactivan el próximo ciclo\./i,
      ),
    ).toBeInTheDocument();
  });

  it("error genérico muestra fallback genérico", async () => {
    const user = userEvent.setup();
    mockMutate.mockImplementation((_body: unknown, opts: { onError: (e: unknown) => void }) => {
      opts.onError(new Error("Network error"));
    });
    renderTable({ isCoachOrAdmin: true });

    await user.click(screen.getByTestId("ai-launch-btn-55"));

    await waitFor(() =>
      expect(screen.getByTestId("ai-launch-error-55")).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/no se pudo iniciar el análisis\. intenta de nuevo\./i),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// insightFreshnessMap prop semantics
// ---------------------------------------------------------------------------

describe("ResultsTable — semántica del mapa de frescura de insights", () => {
  it("mapa vacío (sin insight previo) → launch directo sin modal", async () => {
    const user = userEvent.setup();
    renderTable({ isCoachOrAdmin: true, insightFreshnessMap: NO_INSIGHT_MAP });
    await user.click(screen.getByTestId("ai-launch-btn-55"));
    // No modal
    expect(screen.queryByText(/re-ejecutar análisis/i)).not.toBeInTheDocument();
    expect(mockMutate).toHaveBeenCalled();
  });

  it("mapa con athlete 55 → null (fresco) → abre modal", async () => {
    const user = userEvent.setup();
    renderTable({ isCoachOrAdmin: true, insightFreshnessMap: FRESH_INSIGHT_MAP });
    await user.click(screen.getByTestId("ai-launch-btn-55"));
    expect(screen.getByText(/re-ejecutar análisis/i)).toBeInTheDocument();
    expect(mockMutate).not.toHaveBeenCalled();
  });

  it("mapa con athlete 55 → stale run_id → launch directo sin modal", async () => {
    const user = userEvent.setup();
    const staleMap = new Map<number, string | null>([[55, "stale-run-abc"]]);
    renderTable({ isCoachOrAdmin: true, insightFreshnessMap: staleMap });
    await user.click(screen.getByTestId("ai-launch-btn-55"));
    // Stale means it's not fresh → no confirmation needed
    expect(screen.queryByText(/re-ejecutar análisis/i)).not.toBeInTheDocument();
    expect(mockMutate).toHaveBeenCalled();
  });
});
