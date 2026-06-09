/**
 * T020 — ImportWizard post-commit: "Analizar con IA ahora" button (FR-004).
 *
 * Tests:
 *  - Button rendered in success panel
 *  - Click → launchGroupAnalysis called with race_event_id, then navigate to insights tab
 *  - No click → launchGroupAnalysis never called
 *  - 503 error → budget copy shown
 *  - 429 error → concurrency copy shown
 *  - 422 error → no results copy shown
 *  - other error → generic copy shown
 *
 * Rendering strategy: drives the full wizard through steps 1-3 using the
 * same `fillStep1AndSubmit` helper pattern as ImportWizard.test.tsx. This
 * avoids duplicating component logic and keeps mocking consistent.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  waitFor,
  fireEvent,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { createElement, type ReactNode } from "react";

// ---------------------------------------------------------------------------
// Mocks — must be declared before any dynamic imports
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock("@/api/raceImports", () => ({
  parseRaceImport: vi.fn(),
  dryRunRaceImport: vi.fn(),
  commitRaceImport: vi.fn(),
  listRaceImports: vi.fn(),
  getRevisionReasons: vi.fn(),
  getRaceEventDiff: vi.fn(),
}));

vi.mock("@/api/athletes", () => ({
  getAthletes: vi.fn(),
  getAthlete: vi.fn(),
}));

vi.mock("@/api/raceAnalysis", () => ({
  launchGroupAnalysis: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

// ---------------------------------------------------------------------------
// Deferred imports (after vi.mock declarations)
// ---------------------------------------------------------------------------

import * as importsApi from "@/api/raceImports";
import * as athletesApi from "@/api/athletes";
import * as raceAnalysisApi from "@/api/raceAnalysis";
import { ImportWizard } from "@/components/competitions/import/ImportWizard";
import { Sex } from "@/types/enums";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const PARSE_RESPONSE = {
  parse_id: "p-ai-1",
  sha256: "abcd1234",
  header: {
    series_name: "Copa Valle",
    season: 2026,
    valida_num: 4,
    event_name: "IV — Cali",
  },
  n_rows_resultados: 50,
  n_rows_general: 0,
  warnings: [],
};

const DRY_RUN_CONFIRMED = {
  parse_id: "p-ai-1",
  matches: [
    {
      competitor_normalized_name: "juan perez",
      competitor_name: "Juan Pérez",
      tyr_athlete: { id: 1, full_name: "Juan Pérez" },
      confidence: 0.95,
      is_ambiguous: false,
    },
  ],
  counts: { confirmed: 1, ambiguous: 0, no_match: 0, total: 1 },
  warnings: [],
};

const COMMIT_RESPONSE = {
  parse_id: "p-ai-1",
  race_event_id: 7,
  n_results_inserted: 50,
  n_competitors_created: 49,
  n_competitors_linked: 1,
};

const LAUNCH_SUCCESS_RESPONSE = {
  race_event_id: 7,
  season: 2026,
  valida_num: 4,
  started_count: 1,
  skipped_count: 0,
  items: [],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(MemoryRouter, null, ui),
    ),
  );
}

function makeValidPdf(name = "resultados.pdf"): File {
  const header = new TextEncoder().encode("%PDF-1.4\n");
  return new File([header, new Uint8Array(512)], name, {
    type: "application/pdf",
  });
}

/** Fills step 1 fields and submits — mirrors ImportWizard.test.tsx pattern. */
async function fillStep1AndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByTestId("wizard-event-name"), "Válida IV — Cali");
  fireEvent.change(screen.getByTestId("wizard-event-date"), {
    target: { value: "2026-05-17" },
  });
  await user.type(screen.getByTestId("wizard-location"), "Cali");

  const input = screen.getByTestId(
    "race-upload-resultados-input",
  ) as HTMLInputElement;
  const pdf = makeValidPdf();
  Object.defineProperty(input, "files", { value: [pdf] });
  fireEvent.change(input);

  await waitFor(() =>
    expect(
      screen.getByTestId("race-upload-resultados-preview"),
    ).toBeInTheDocument(),
  );

  await user.click(screen.getByTestId("wizard-step1-submit"));
}

/** Drives wizard to the post-commit success panel. */
async function reachSuccessPanel(user: ReturnType<typeof userEvent.setup>) {
  wrap(<ImportWizard />);
  await fillStep1AndSubmit(user);

  await waitFor(() =>
    expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
  );
  await user.click(screen.getByTestId("wizard-step2-confirm"));

  await waitFor(() =>
    expect(screen.getByTestId("wizard-step3-success")).toBeInTheDocument(),
  );
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.resetAllMocks();
  mockNavigate.mockReset();

  vi.mocked(importsApi.parseRaceImport).mockResolvedValue(PARSE_RESPONSE as any);
  vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue(DRY_RUN_CONFIRMED as any);
  vi.mocked(importsApi.commitRaceImport).mockResolvedValue(COMMIT_RESPONSE as any);
  vi.mocked(importsApi.getRevisionReasons).mockResolvedValue({
    reasons: [],
  } as any);
  vi.mocked(athletesApi.getAthletes).mockResolvedValue({
    items: [
      {
        id: 1,
        first_name: "Juan",
        last_name: "Pérez",
        sex: Sex.M,
        category: "PJUV-B-M",
        club_id: 1,
        is_active: true,
        user_id: null,
      },
    ] as any,
    total: 1,
  } as any);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ImportWizard — post-commit AI button (T020)", () => {
  it("renders 'Analizar con IA ahora' button in the success panel", async () => {
    const user = userEvent.setup();
    await reachSuccessPanel(user);

    expect(
      screen.getByTestId("wizard-step3-launch-ai"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("wizard-step3-launch-ai"),
    ).toHaveTextContent(/Analizar con IA ahora/i);
  });

  it("clicking the button calls launchGroupAnalysis with race_event_id and navigates to insights tab", async () => {
    vi.mocked(raceAnalysisApi.launchGroupAnalysis).mockResolvedValue(
      LAUNCH_SUCCESS_RESPONSE as any,
    );

    const user = userEvent.setup();
    await reachSuccessPanel(user);

    await user.click(screen.getByTestId("wizard-step3-launch-ai"));

    await waitFor(() =>
      expect(raceAnalysisApi.launchGroupAnalysis).toHaveBeenCalledTimes(1),
    );
    expect(raceAnalysisApi.launchGroupAnalysis).toHaveBeenCalledWith(
      COMMIT_RESPONSE.race_event_id,
      {},
    );

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledTimes(1));
    expect(mockNavigate).toHaveBeenCalledWith(
      `/competitions/${COMMIT_RESPONSE.race_event_id}?tab=insights`,
    );
  });

  it("not clicking the button → launchGroupAnalysis is never called", async () => {
    const user = userEvent.setup();
    await reachSuccessPanel(user);

    // Interact with other buttons to confirm no accidental side-effects.
    expect(
      screen.getByTestId("wizard-step3-link-analysis"),
    ).toBeInTheDocument();

    expect(raceAnalysisApi.launchGroupAnalysis).not.toHaveBeenCalled();
  });

  it("503 error → shows budget-exhausted copy", async () => {
    const err = Object.assign(new Error("budget"), {
      response: { status: 503 },
    });
    vi.mocked(raceAnalysisApi.launchGroupAnalysis).mockRejectedValue(err);

    const user = userEvent.setup();
    await reachSuccessPanel(user);

    await user.click(screen.getByTestId("wizard-step3-launch-ai"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-ai-error")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step3-ai-error")).toHaveTextContent(
      /Presupuesto mensual de IA agotado/i,
    );
  });

  it("429 error → shows concurrency-limit copy", async () => {
    const err = Object.assign(new Error("concurrency"), {
      response: { status: 429 },
    });
    vi.mocked(raceAnalysisApi.launchGroupAnalysis).mockRejectedValue(err);

    const user = userEvent.setup();
    await reachSuccessPanel(user);

    await user.click(screen.getByTestId("wizard-step3-launch-ai"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-ai-error")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step3-ai-error")).toHaveTextContent(
      /Límite de análisis simultáneos/i,
    );
  });

  it("422 error → shows no-results copy", async () => {
    const err = Object.assign(new Error("no results"), {
      response: { status: 422 },
    });
    vi.mocked(raceAnalysisApi.launchGroupAnalysis).mockRejectedValue(err);

    const user = userEvent.setup();
    await reachSuccessPanel(user);

    await user.click(screen.getByTestId("wizard-step3-launch-ai"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-ai-error")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step3-ai-error")).toHaveTextContent(
      /no tiene resultados importados/i,
    );
  });

  it("unknown error → shows generic copy", async () => {
    vi.mocked(raceAnalysisApi.launchGroupAnalysis).mockRejectedValue(
      new Error("network failure"),
    );

    const user = userEvent.setup();
    await reachSuccessPanel(user);

    await user.click(screen.getByTestId("wizard-step3-launch-ai"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-ai-error")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step3-ai-error")).toHaveTextContent(
      /No se pudo lanzar el análisis/i,
    );
  });
});
