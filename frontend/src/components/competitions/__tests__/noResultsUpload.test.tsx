/**
 * Guard de no-upload (amendment 2026-09-26, `contracts/ui-review-only.md`,
 * T157): la app ya no sube archivos de resultados en ninguna pantalla — la
 * carga se prepara fuera de la app (skill/CLI de resultados) y se revisa
 * desde «Cargas».
 *
 * Renderiza la revisión (`?import=<id>`), el tablero de cargas, la lista de
 * competencias, el detalle de una competencia y el tab de resultados, y
 * afirma que ninguna de ellas tiene `input[type=file]` ni el texto «Cargar
 * resultados», «Importar resultados» o «Cargar archivo».
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

// Evita cargar la cascada pesada de InsightsTab/ConditionsTab en el detalle.
vi.mock("@/components/competitions/tabs/InsightsTab", () => ({
  InsightsTab: () => <div data-testid="mock-insights-tab">insights</div>,
}));
vi.mock("@/components/competitions/tabs/ConditionsTab", () => ({
  ConditionsTab: () => <div data-testid="mock-conditions-tab">conditions</div>,
}));

import { useAuthStore } from "@/store/auth.store";
import { mswServer } from "@/test/setup";
import {
  makeRaceEventRead,
  raceEventsHandlers,
} from "@/test/msw/raceEventsHandlers";
import {
  makeImportDetail,
  raceImportsHistoryEmptyHandler,
} from "@/test/msw/raceImportsHistoryHandlers";
import { raceResultsEmptyHandler } from "@/test/msw/raceResultsHandlers";
import { CompetitionImportPage } from "@/routes/competitions/CompetitionImportPage";
import { CompetitionsListPage } from "@/routes/competitions/CompetitionsListPage";
import { CompetitionDetailPage } from "@/routes/competitions/CompetitionDetailPage";
import { LoadsSection } from "@/components/competitions/imports/LoadsSection";
import { ResultsTab } from "@/components/competitions/tabs/ResultsTab";

const FORBIDDEN_TEXT = [/Cargar resultados/i, /Importar resultados/i, /Cargar archivo/i];

function mockAuthAs(role: "admin" | "coach") {
  const state = {
    accessToken: "test-token",
    user: { id: 1, role, first_name: "U", last_name: "T" },
    isAuthenticated: true,
  };
  vi.mocked(useAuthStore).mockImplementation(
    ((sel: (s: typeof state) => unknown) => sel(state)) as unknown as typeof useAuthStore,
  );
}

function renderAt(ui: React.ReactElement, initialEntry: string, routePath: string) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path={routePath} element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Ninguna pantalla del módulo sube archivos — sin dropzone ni copy de carga. */
function assertNoUploadSurface(container: HTMLElement) {
  expect(container.querySelectorAll('input[type="file"]')).toHaveLength(0);
  for (const pattern of FORBIDDEN_TEXT) {
    expect(container.textContent).not.toMatch(pattern);
  }
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAuthAs("coach");
  mswServer.use(...raceEventsHandlers, raceImportsHistoryEmptyHandler, raceResultsEmptyHandler);
});

describe("Guard de no-upload (amendment 2026-09-26)", () => {
  it("la revisión de una carga (?import=<id>) no tiene input[type=file] ni copy de subida", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/imports/1", () =>
        HttpResponse.json(makeImportDetail({ id: 1 })),
      ),
      http.post("*/api/race-analysis/imports/1/dry-run", () =>
        HttpResponse.json({
          parse_id: "1",
          matches: [],
          counts: { confirmed: 0, ambiguous: 0, no_match: 0, total: 0 },
          warnings: [],
        }),
      ),
    );
    const { container } = renderAt(
      <CompetitionImportPage />,
      "/competitions/import?import=1",
      "/competitions/import",
    );
    await waitFor(() =>
      expect(screen.getByTestId("import-wizard")).toBeInTheDocument(),
    );
    assertNoUploadSurface(container);
  });

  it("el tablero de cargas (LoadsSection) no tiene input[type=file] ni copy de subida", async () => {
    const { container } = renderAt(<LoadsSection />, "/competitions/imports", "/competitions/imports");
    await waitFor(() =>
      expect(screen.getByTestId("loads-section")).toBeInTheDocument(),
    );
    assertNoUploadSurface(container);
  });

  it("la lista de competencias no tiene input[type=file] ni copy de subida", async () => {
    const { container } = renderAt(
      <CompetitionsListPage />,
      "/competitions",
      "/competitions",
    );
    await waitFor(() => expect(container.querySelector("table, [role=table]")).toBeTruthy());
    assertNoUploadSurface(container);
  });

  it("el detalle de una competencia no tiene input[type=file] ni copy de subida", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/1", () =>
        HttpResponse.json(makeRaceEventRead({ id: 1 })),
      ),
    );
    const { container } = renderAt(
      <CompetitionDetailPage />,
      "/competitions/1",
      "/competitions/:id",
    );
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument(),
    );
    assertNoUploadSurface(container);
  });

  it("el tab de resultados (vacío) no tiene input[type=file] ni copy de subida", async () => {
    const { container } = renderAt(
      <ResultsTab raceEventId={1} />,
      "/competitions/1?tab=results",
      "/competitions/:id",
    );
    await waitFor(() =>
      expect(screen.getByTestId("results-tab-empty")).toBeInTheDocument(),
    );
    assertNoUploadSurface(container);
    expect(screen.getByTestId("results-tab-import-cta")).toHaveTextContent("Ir a Cargas");
  });
});
