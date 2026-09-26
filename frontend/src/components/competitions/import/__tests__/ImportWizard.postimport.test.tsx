/**
 * T020 — ImportWizard post-commit: "Analizar con IA ahora" button (FR-004).
 * Amendment 2026-09-26 (T159): la app ya no sube archivos — el wizard
 * arranca desde `?import=<id>` con MSW (patrón de
 * `ImportWizard.resume.test.tsx`) en vez de llenar el paso 1.
 *
 * Tests:
 *  - Button rendered in success panel
 *  - Click → launchGroupAnalysis called with race_event_id, then navigate to insights tab
 *  - No click → launchGroupAnalysis never called
 *  - 503 error → budget copy shown
 *  - 429 error → concurrency copy shown
 *  - 422 error → no results copy shown
 *  - other error → generic copy shown
 *  - Panel "Circuito (opcional)" tras commit exitoso (feature 043)
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock("@/api/raceAnalysis", () => ({
  launchGroupAnalysis: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

import * as raceAnalysisApi from "@/api/raceAnalysis";
import { ImportWizard } from "@/components/competitions/import/ImportWizard";
import { mswServer } from "@/test/setup";
import { makeImportDetail } from "@/test/msw/raceImportsHistoryHandlers";
import { raceCourseEmptyHandler } from "@/test/msw/raceCourseHandlers";
import type { ImportDryRunMatchesResponse } from "@/types/raceImports.types";

const BASE = "*/api/race-analysis/imports";

const DRY_RUN_CONFIRMED: ImportDryRunMatchesResponse = {
  parse_id: "7",
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
  parse_id: "7",
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

function renderAt() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/competitions/import?import=7"]}>
        <Routes>
          <Route path="/competitions/import" element={<ImportWizard />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Drives wizard to the post-commit success panel. */
async function reachSuccessPanel() {
  mswServer.use(
    http.get(`${BASE}/7`, () => HttpResponse.json(makeImportDetail({ id: 7 }))),
    http.post(`${BASE}/7/dry-run`, () => HttpResponse.json(DRY_RUN_CONFIRMED)),
    http.post(`${BASE}/7/commit`, () => HttpResponse.json(COMMIT_RESPONSE)),
  );
  const user = userEvent.setup();
  renderAt();

  await waitFor(() =>
    expect(screen.getByTestId("wizard-step2-confirm")).toBeEnabled(),
  );
  await user.click(screen.getByTestId("wizard-step2-confirm"));

  await waitFor(() =>
    expect(screen.getByTestId("wizard-step3-success")).toBeInTheDocument(),
  );
  return user;
}

beforeEach(() => {
  vi.resetAllMocks();
  mockNavigate.mockReset();
});

describe("ImportWizard — post-commit AI button (T020)", () => {
  it("renders 'Analizar con IA ahora' button in the success panel", async () => {
    await reachSuccessPanel();

    expect(screen.getByTestId("wizard-step3-launch-ai")).toBeInTheDocument();
    expect(screen.getByTestId("wizard-step3-launch-ai")).toHaveTextContent(
      /Analizar con IA ahora/i,
    );
  });

  it("clicking the button calls launchGroupAnalysis with race_event_id and navigates to insights tab", async () => {
    vi.mocked(raceAnalysisApi.launchGroupAnalysis).mockResolvedValue(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      LAUNCH_SUCCESS_RESPONSE as any,
    );

    const user = await reachSuccessPanel();
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
    await reachSuccessPanel();

    expect(screen.getByTestId("wizard-step3-link-analysis")).toBeInTheDocument();
    expect(raceAnalysisApi.launchGroupAnalysis).not.toHaveBeenCalled();
  });

  it("503 error → shows budget-exhausted copy", async () => {
    const err = Object.assign(new Error("budget"), { response: { status: 503 } });
    vi.mocked(raceAnalysisApi.launchGroupAnalysis).mockRejectedValue(err);

    const user = await reachSuccessPanel();
    await user.click(screen.getByTestId("wizard-step3-launch-ai"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-ai-error")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step3-ai-error")).toHaveTextContent(
      /Presupuesto mensual de IA agotado/i,
    );
  });

  it("429 error → shows concurrency-limit copy", async () => {
    const err = Object.assign(new Error("concurrency"), { response: { status: 429 } });
    vi.mocked(raceAnalysisApi.launchGroupAnalysis).mockRejectedValue(err);

    const user = await reachSuccessPanel();
    await user.click(screen.getByTestId("wizard-step3-launch-ai"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-ai-error")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step3-ai-error")).toHaveTextContent(
      /Límite de análisis simultáneos/i,
    );
  });

  it("422 error → shows no-results copy", async () => {
    const err = Object.assign(new Error("no results"), { response: { status: 422 } });
    vi.mocked(raceAnalysisApi.launchGroupAnalysis).mockRejectedValue(err);

    const user = await reachSuccessPanel();
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

    const user = await reachSuccessPanel();
    await user.click(screen.getByTestId("wizard-step3-launch-ai"));

    await waitFor(() =>
      expect(screen.getByTestId("wizard-step3-ai-error")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("wizard-step3-ai-error")).toHaveTextContent(
      /No se pudo lanzar el análisis/i,
    );
  });
});

describe("ImportWizard — panel 'Circuito (opcional)' tras commit (feature 043)", () => {
  it("muestra el encabezado y el panel CourseTab tras un commit exitoso", async () => {
    mswServer.use(raceCourseEmptyHandler);
    await reachSuccessPanel();

    expect(
      await screen.findByRole("heading", { name: "Circuito (opcional)" }),
    ).toBeInTheDocument();
    expect(await screen.findByTestId("course-tab")).toBeInTheDocument();
    expect(screen.getByTestId("course-tab-empty")).toBeInTheDocument();
  });
});
