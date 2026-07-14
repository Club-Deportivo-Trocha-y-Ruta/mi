/**
 * Tests vitest — GroupAnalysisPanel (Feature 010, T012).
 *
 * Cubre:
 *  1. Happy path: launch muestra filas por atleta.
 *  2. Deshabilitado cuando hasResults=false (FR-002).
 *  3. Outcomes parciales: detail visible + retry button llama al subset (FR-011).
 *  4. Error 503 → copy de presupuesto agotado (FR-010).
 *  5. Recovery on mount: runs recuperados vía GET /runs → estado in-progress,
 *     botón launch deshabilitado (FR-012).
 *  6. Pista pre-lanzamiento de presupuesto/concurrencia (feature 033 / T055,
 *     T052): las tres presentaciones de `budget_status`, la pista de espera
 *     por concurrencia, y la degradación con gracia cuando falla el fetch de
 *     `GET /api/ai/status`.
 *  7. jest-axe (feature 033 / T056): 0 violaciones en el estado por defecto
 *     y con el hint de presupuesto agotado (botón deshabilitado + alert).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import type { AIStatusResponse } from "@/types/ai.types";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockLaunch = vi.fn();
const mockRetry = vi.fn();
const mockNotify = vi.fn();

// Default hook state — overridden per test.
let mockGroupAnalysis = {
  runs: [] as import("@/hooks/ai/useGroupAnalysis").TrackedRunEntry[],
  groupState: "idle" as import("@/hooks/ai/useGroupAnalysis").GroupState,
  launch: mockLaunch,
  retry: mockRetry,
  isLaunching: false,
  launchError: null as unknown,
  lastLaunchData: null,
  isRecovering: false,
  notifyRunTerminated: mockNotify,
};

vi.mock("@/hooks/ai/useGroupAnalysis", () => ({
  useGroupAnalysis: () => mockGroupAnalysis,
}));

// GroupRunRow uses useRunStatus — mock it to avoid polling.
vi.mock("@/hooks/ai/useRaceRun", () => ({
  useRunStatus: () => ({ data: undefined, isLoading: false }),
  isTerminalState: () => false,
}));

// useAIStatus (T052) — sin datos por defecto: degradación reactiva-only,
// ningún hint visible, comportamiento idéntico al pre-existente.
let mockAIStatusData: AIStatusResponse | undefined = undefined;
let mockAIStatusIsError = false;
vi.mock("@/hooks/ai/useAIStatus", () => ({
  useAIStatus: () => ({ data: mockAIStatusData, isError: mockAIStatusIsError }),
}));

// HITLApprovalCard — not needed in these tests.
vi.mock("@/components/ai/HITLApprovalCard", () => ({
  HITLApprovalCard: () => null,
}));

import { GroupAnalysisPanel } from "@/components/competitions/insights/GroupAnalysisPanel";
import { groupRunStatus } from "@/components/competitions/insights/GroupRunRow";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderPanel(hasResults = true) {
  return render(<GroupAnalysisPanel raceEventId={42} hasResults={hasResults} />);
}

const ATHLETE_STARTED = {
  athlete_id: 12,
  name: "Juan P.",
  run_id: "run-a1b2",
  outcome: "started" as const,
  detail: null,
};

const ATHLETE_BACKPRESSURE = {
  athlete_id: 15,
  name: "Sofía R.",
  run_id: null,
  outcome: "backpressure" as const,
  detail: "Límite de análisis simultáneos alcanzado. Intenta de nuevo en unos minutos.",
};

beforeEach(() => {
  vi.clearAllMocks();
  mockAIStatusData = undefined;
  mockAIStatusIsError = false;
  mockGroupAnalysis = {
    runs: [],
    groupState: "idle",
    launch: mockLaunch,
    retry: mockRetry,
    isLaunching: false,
    launchError: null,
    lastLaunchData: null,
    isRecovering: false,
    notifyRunTerminated: mockNotify,
  };
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("GroupAnalysisPanel", () => {
  it("1. happy path: launch renders rows with athlete names", () => {
    mockGroupAnalysis = {
      ...mockGroupAnalysis,
      runs: [ATHLETE_STARTED],
      groupState: "in_progress",
    };
    renderPanel();

    // Rows are visible
    expect(screen.getByTestId("group-run-row-12")).toBeInTheDocument();
    expect(screen.getByText("Juan P.")).toBeInTheDocument();
  });

  it("1b. clicking launch calls launch()", async () => {
    const user = userEvent.setup();
    renderPanel();

    const btn = screen.getByTestId("group-launch-button");
    await user.click(btn);
    expect(mockLaunch).toHaveBeenCalledOnce();
  });

  it("2. disabled when hasResults=false — button is disabled and tooltip copy present", () => {
    renderPanel(false);
    const btn = screen.getByTestId("group-launch-button");
    expect(btn).toBeDisabled();
    // aria-label contains the tooltip copy
    expect(btn).toHaveAttribute(
      "aria-label",
      "La competencia no tiene resultados importados.",
    );
  });

  it("2b. launch is NOT called when button is disabled (hasResults=false)", () => {
    renderPanel(false);
    // Button is disabled — verify state and that no launch occurred.
    const btn = screen.getByTestId("group-launch-button");
    expect(btn).toBeDisabled();
    expect(mockLaunch).not.toHaveBeenCalled();
  });

  it("3. partial outcomes: detail text visible + retry button calls subset", async () => {
    mockGroupAnalysis = {
      ...mockGroupAnalysis,
      runs: [ATHLETE_STARTED, ATHLETE_BACKPRESSURE],
      groupState: "partial",
    };
    const user = userEvent.setup();
    renderPanel();

    // Detail message for the backpressure athlete is visible
    expect(
      screen.getByTestId("group-run-detail-15"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Límite de análisis simultáneos/i),
    ).toBeInTheDocument();

    // Retry button is visible
    const retryBtn = screen.getByTestId("group-retry-button");
    expect(retryBtn).toBeInTheDocument();

    // Clicking retry calls retry with the backpressure athlete_id only
    await user.click(retryBtn);
    expect(mockRetry).toHaveBeenCalledWith([15]);
  });

  it("4. 503 error shows budget copy", () => {
    mockGroupAnalysis = {
      ...mockGroupAnalysis,
      launchError: { response: { status: 503 }, message: "Service Unavailable" },
    };
    renderPanel();

    expect(screen.getByTestId("group-launch-error")).toBeInTheDocument();
    expect(
      screen.getByText(/Presupuesto mensual de IA agotado/i),
    ).toBeInTheDocument();
  });

  it("4b. 429 error shows concurrency copy", () => {
    mockGroupAnalysis = {
      ...mockGroupAnalysis,
      launchError: { response: { status: 429 }, message: "Too Many Requests" },
    };
    renderPanel();
    expect(
      screen.getByText(/Límite de análisis simultáneos alcanzado/i),
    ).toBeInTheDocument();
  });

  it("5. recovery on mount: recovered run shown, launch button disabled while in_progress", () => {
    mockGroupAnalysis = {
      ...mockGroupAnalysis,
      runs: [{ ...ATHLETE_STARTED, outcome: "recovered" as const }],
      groupState: "in_progress",
    };
    renderPanel();

    // Row for the recovered run is visible
    expect(screen.getByTestId("group-run-row-12")).toBeInTheDocument();

    // Launch button is disabled while in_progress
    const btn = screen.getByTestId("group-launch-button");
    expect(btn).toBeDisabled();
  });
});

describe("groupRunStatus (adaptador puro, T014)", () => {
  // Live runState takes priority over outcome.
  it("runState='hitl_waiting' → warning/'Esperando aprobación'", () => {
    expect(groupRunStatus("hitl_waiting", "started")).toEqual({
      status: "warning",
      label: "Esperando aprobación",
    });
  });

  it("runState='done' → success/'Completado'", () => {
    expect(groupRunStatus("done", "started")).toEqual({
      status: "success",
      label: "Completado",
    });
  });

  it("runState='failed' → danger/'Fallido'", () => {
    expect(groupRunStatus("failed", "started")).toEqual({ status: "danger", label: "Fallido" });
  });

  it("runState='error' → danger/'Fallido'", () => {
    expect(groupRunStatus("error", "started")).toEqual({ status: "danger", label: "Fallido" });
  });

  it("runState='cancelled' → neutral/'Rechazado'", () => {
    expect(groupRunStatus("cancelled", "started")).toEqual({
      status: "neutral",
      label: "Rechazado",
    });
  });

  it("runState='running' → null (estado 'en curso', no es un badge)", () => {
    expect(groupRunStatus("running", "started")).toBeNull();
  });

  // No live runState: falls back to launch outcome.
  it("outcome='already_running' (sin runState) → neutral/'Ya en curso'", () => {
    expect(groupRunStatus(undefined, "already_running")).toEqual({
      status: "neutral",
      label: "Ya en curso",
    });
  });

  it("outcome='backpressure' (sin runState) → warning/'Límite alcanzado'", () => {
    expect(groupRunStatus(undefined, "backpressure")).toEqual({
      status: "warning",
      label: "Límite alcanzado",
    });
  });

  it("outcome='error' (sin runState) → danger/'Fallido'", () => {
    expect(groupRunStatus(undefined, "error")).toEqual({ status: "danger", label: "Fallido" });
  });

  it("outcome='no_results' (sin runState) → danger/'Fallido'", () => {
    expect(groupRunStatus(undefined, "no_results")).toEqual({
      status: "danger",
      label: "Fallido",
    });
  });

  it("outcome='budget_exceeded' (sin runState) → danger/'Fallido'", () => {
    expect(groupRunStatus(undefined, "budget_exceeded")).toEqual({
      status: "danger",
      label: "Fallido",
    });
  });

  it("outcome='started' (sin runState) → null (estado 'en curso', no es un badge)", () => {
    expect(groupRunStatus(undefined, "started")).toBeNull();
  });

  it("outcome='recovered' (sin runState) → null (estado 'en curso', no es un badge)", () => {
    expect(groupRunStatus(undefined, "recovered")).toBeNull();
  });
});

describe("GroupRunRow — regresión: StateChip eliminado (T023)", () => {
  it("estados terminales (outcome) usan StatusBadge (ícono presente) — no las clases hand-rolled del StateChip legado", () => {
    mockGroupAnalysis = {
      ...mockGroupAnalysis,
      runs: [ATHLETE_BACKPRESSURE],
      groupState: "partial",
    };
    const { container } = renderPanel();

    const nameEl = screen.getByText("Sofía R.");
    const row = nameEl.closest("div");
    expect(row?.querySelector("svg")).toBeInTheDocument();

    // Clases utility hand-rolled del StateChip legado (una por cada estado
    // terminal que el StateChip pintaba a mano) ya no aparecen en el DOM.
    const legacyClassPattern =
      /bg-orange-50|text-orange-700|bg-sky-50|text-sky-700|bg-emerald-50|text-emerald-700|bg-gray-100 text-gray-600|bg-amber-50 text-amber-700/;
    expect(container.innerHTML).not.toMatch(legacyClassPattern);
  });

  it("el estado 'en curso' (outcome=started, sin runState) renderiza el timeline compacto (T050)", () => {
    mockGroupAnalysis = {
      ...mockGroupAnalysis,
      runs: [ATHLETE_STARTED],
      groupState: "in_progress",
    };
    renderPanel();

    expect(screen.getByTestId("analysis-run-timeline")).toBeInTheDocument();
    // No hay `<ol>` de nodos en la densidad compacta — solo el header.
    expect(screen.queryByTestId("timeline-nodes-list")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Pista pre-lanzamiento de presupuesto/concurrencia (feature 033 / T055, T052)
// ---------------------------------------------------------------------------

describe("GroupAnalysisPanel — pista pre-lanzamiento de IA (T055)", () => {
  it("budget_status='ok' + concurrencia disponible + sin ETA: no muestra ningún hint", () => {
    mockAIStatusData = {
      budget_status: "ok",
      budget_remaining_pct: 80,
      concurrency_available: true,
      est_wait_seconds: 0,
    };
    renderPanel();
    expect(screen.queryByTestId("ai-budget-hint-warning")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-budget-hint-exhausted")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-budget-hint-concurrency")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-budget-hint-duration")).not.toBeInTheDocument();
    expect(screen.getByTestId("group-launch-button")).not.toBeDisabled();
  });

  it("budget_status='ok' con ETA>0 muestra el hint neutro '≈Ns'", () => {
    mockAIStatusData = {
      budget_status: "ok",
      budget_remaining_pct: 80,
      concurrency_available: true,
      est_wait_seconds: 30,
    };
    renderPanel();
    expect(screen.getByTestId("ai-budget-hint-duration")).toHaveTextContent("≈30s");
  });

  it("budget_status='warning' muestra el hint ámbar con % restante, launch sigue habilitado", () => {
    mockAIStatusData = {
      budget_status: "warning",
      budget_remaining_pct: 18,
      concurrency_available: true,
      est_wait_seconds: 20,
    };
    renderPanel();
    expect(screen.getByTestId("ai-budget-hint-warning")).toHaveTextContent(
      "Presupuesto de IA: 18% restante",
    );
    expect(screen.getByTestId("group-launch-button")).not.toBeDisabled();
  });

  it("budget_status='exhausted' deshabilita el botón de lanzamiento grupal y muestra la explicación ANTES de cualquier click", () => {
    mockAIStatusData = {
      budget_status: "exhausted",
      budget_remaining_pct: 0,
      concurrency_available: true,
      est_wait_seconds: 0,
    };
    renderPanel();
    const btn = screen.getByTestId("group-launch-button");
    expect(btn).toBeDisabled();
    expect(screen.getByTestId("ai-budget-hint-exhausted")).toHaveTextContent(
      "Presupuesto mensual de IA agotado. Los análisis se reactivan el próximo ciclo.",
    );
  });

  it("concurrency_available=false muestra 'Alta demanda — espera ≈Ns', launch sigue habilitado", () => {
    mockAIStatusData = {
      budget_status: "ok",
      budget_remaining_pct: 90,
      concurrency_available: false,
      est_wait_seconds: 50,
    };
    renderPanel();
    expect(screen.getByTestId("ai-budget-hint-concurrency")).toHaveTextContent(
      "Alta demanda — espera ≈50s",
    );
    expect(screen.getByTestId("group-launch-button")).not.toBeDisabled();
  });

  it("degrada con gracia cuando GET /api/ai/status falla — sin hint, botón sigue funcional", async () => {
    const user = userEvent.setup();
    mockAIStatusData = undefined;
    mockAIStatusIsError = true;
    renderPanel();

    expect(screen.queryByTestId("ai-budget-hint-warning")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-budget-hint-exhausted")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-budget-hint-concurrency")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-budget-hint-duration")).not.toBeInTheDocument();

    const btn = screen.getByTestId("group-launch-button");
    expect(btn).not.toBeDisabled();
    await user.click(btn);
    expect(mockLaunch).toHaveBeenCalledOnce();
  });
});

// ---------------------------------------------------------------------------
// jest-axe (feature 033 / T056)
// ---------------------------------------------------------------------------

describe("GroupAnalysisPanel — accesibilidad (T056)", () => {
  it("jest-axe: 0 violaciones en el estado por defecto", async () => {
    const { container } = renderPanel();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("jest-axe: 0 violaciones con budget_status='exhausted' (botón deshabilitado + alert)", async () => {
    mockAIStatusData = {
      budget_status: "exhausted",
      budget_remaining_pct: 0,
      concurrency_available: true,
      est_wait_seconds: 0,
    };
    const { container } = renderPanel();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("jest-axe: 0 violaciones con filas en curso (timeline compacto montado, T050)", async () => {
    mockGroupAnalysis = {
      ...mockGroupAnalysis,
      runs: [ATHLETE_STARTED],
      groupState: "in_progress",
    };
    const { container } = renderPanel();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
