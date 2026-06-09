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
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

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

// HITLApprovalCard — not needed in these tests.
vi.mock("@/components/ai/HITLApprovalCard", () => ({
  HITLApprovalCard: () => null,
}));

import { GroupAnalysisPanel } from "@/components/competitions/insights/GroupAnalysisPanel";

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
