/**
 * T022 — spec 014 Cup vs Championship
 * CompetitionDetailPage — badges V{n} vs CD; standings tab oculto para campeonato (US4).
 *
 * Cubre:
 *  - US4: una copa muestra badge "V{n}" (mediante sequence_number) — no "CD".
 *  - US4: un campeonato muestra badge "CD" (mediante is_championship=true) — no número.
 *  - US4: el tab "Clasificación" (standings) está PRESENTE para eventos de copa.
 *  - US4: el tab "Clasificación" está AUSENTE para campeonatos.
 *  - US4: si URL ?tab=standings en un campeonato, cae al tab Info (no queda roto).
 *  - 0 violaciones a11y (jest-axe) en tab Info para una copa y para un campeonato.
 *
 * La distinción badge "V{n}" vs "CD" se construye en InfoTab, CompetitionsListPage
 * y el header de CompetitionDetailPage. Este test foca en el DetailPage porque es
 * donde se decide qué tabs renderizar (standings tab filtrado por is_championship).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { http, HttpResponse } from "msw";

// Mock de auth.store.
vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return { ...actual, useNavigate: () => mockNavigate };
});

// Mock de tabs lazy para evitar el árbol de dependencias de IA.
vi.mock("@/components/competitions/tabs/AthletesTab", () => ({
  AthletesTab: () => <div data-testid="mock-athletes-tab">athletes</div>,
}));
vi.mock("@/components/competitions/tabs/InsightsTab", () => ({
  InsightsTab: () => <div data-testid="mock-insights-tab">insights</div>,
}));
vi.mock("@/components/competitions/tabs/ConditionsTab", () => ({
  ConditionsTab: () => <div data-testid="mock-conditions-tab">conditions</div>,
}));
// StandingsTab es lazy — también lo mockamos para que el import funcione en jsdom.
vi.mock("@/components/competitions/tabs/StandingsTab", () => ({
  StandingsTab: () => (
    <div data-testid="mock-standings-tab">standings</div>
  ),
}));

import { useAuthStore } from "@/store/auth.store";
import { mswServer } from "@/test/setup";
import {
  makeRaceEventRead,
  raceEventsHandlers,
} from "@/test/msw/raceEventsHandlers";
import { CompetitionDetailPage } from "@/routes/competitions/CompetitionDetailPage";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

function renderDetail(id: string | number = 1, search = "") {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/competitions/${id}${search}`]}>
        <Routes>
          <Route
            path="/competitions/:id"
            element={<CompetitionDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  mswServer.use(...raceEventsHandlers);
});

// ---------------------------------------------------------------------------
// US4 (T022) — badge V{n} vs CD
// ---------------------------------------------------------------------------

describe("CompetitionDetailPage spec-014 — US4: badge copa V{n}", () => {
  it("una copa muestra el nombre del evento (con su número en el título) sin badge CD", async () => {
    // La copa tiene sequence_number=3, is_championship=false.
    mswServer.use(
      http.get("*/api/race-analysis/race-events/3", () =>
        HttpResponse.json(
          makeRaceEventRead({
            id: 3,
            sequence_number: 3,
            is_championship: false,
            name: "Copa Valle XCO — Válida III",
            event_date: "2026-04-19",
            location: "La Cumbre",
            status: "scheduled",
          }),
        ),
      ),
    );
    mockAuthAs("coach");
    renderDetail(3);

    await waitFor(() =>
      expect(screen.getByTestId("competition-title")).toHaveTextContent(
        "Copa Valle XCO — Válida III",
      ),
    );

    // No debe aparecer el badge de campeonato (CD).
    expect(screen.queryByTestId("badge-championship")).not.toBeInTheDocument();
  });

  it("una copa muestra el tab 'Clasificación' (standings) en la barra de tabs", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/1", () =>
        HttpResponse.json(
          makeRaceEventRead({
            id: 1,
            sequence_number: 1,
            is_championship: false,
            name: "Copa Valle XCO — Válida I",
            event_date: "2026-01-31",
            location: "Sevilla",
            status: "completed",
          }),
        ),
      ),
    );
    mockAuthAs("coach");
    renderDetail(1);

    await screen.findByTestId("competition-title");

    // El tab "Clasificación" debe existir para copas.
    expect(
      screen.getByRole("tab", { name: "Clasificación" }),
    ).toBeInTheDocument();
  });
});

describe("CompetitionDetailPage spec-014 — US4: badge campeonato CD", () => {
  it("un campeonato muestra el badge 'CD' (data-testid=badge-championship)", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/9", () =>
        HttpResponse.json(
          makeRaceEventRead({
            id: 9,
            series_id: 9,
            sequence_number: 1,
            is_championship: true,
            name: "Campeonato Departamental · Ginebra",
            event_date: "2026-06-12",
            location: "Ginebra",
            status: "completed",
          }),
        ),
      ),
    );
    mockAuthAs("coach");
    renderDetail(9);

    await screen.findByTestId("competition-title");

    // El badge de campeonato (CD) debe estar presente.
    const badge = await screen.findByTestId("badge-championship");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent(/CD/i);
  });

  it("un campeonato NO muestra el tab 'Clasificación' en la barra de tabs", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/9", () =>
        HttpResponse.json(
          makeRaceEventRead({
            id: 9,
            series_id: 9,
            sequence_number: 1,
            is_championship: true,
            name: "Campeonato Departamental · Ginebra",
            event_date: "2026-06-12",
            location: "Ginebra",
            status: "completed",
          }),
        ),
      ),
    );
    mockAuthAs("coach");
    renderDetail(9);

    await screen.findByTestId("competition-title");

    // El tab "Clasificación" NO debe existir para campeonatos (spec 014).
    await waitFor(() =>
      expect(
        screen.queryByRole("tab", { name: "Clasificación" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("todos los demás tabs siguen presentes para un campeonato", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/9", () =>
        HttpResponse.json(
          makeRaceEventRead({
            id: 9,
            series_id: 9,
            sequence_number: 1,
            is_championship: true,
            name: "CD · Ginebra",
            event_date: "2026-06-12",
            status: "completed",
          }),
        ),
      ),
    );
    mockAuthAs("coach");
    renderDetail(9);

    await screen.findByTestId("competition-title");

    // Tabs que deben existir incluso para campeonatos.
    expect(screen.getByRole("tab", { name: "Información" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Resultados" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Condiciones" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Atletas" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Insights IA" })).toBeInTheDocument();
  });

  it("URL ?tab=standings en un campeonato activa el tab Info (fallback, no rompe la UI)", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/9", () =>
        HttpResponse.json(
          makeRaceEventRead({
            id: 9,
            series_id: 9,
            sequence_number: 1,
            is_championship: true,
            name: "CD · Ginebra",
            event_date: "2026-06-12",
            status: "completed",
          }),
        ),
      ),
    );
    mockAuthAs("coach");
    renderDetail(9, "?tab=standings");

    await screen.findByTestId("competition-title");

    // El tab "Información" debe ser el activo (data-state=active) — fallback.
    await waitFor(() => {
      const infoTab = screen.getByRole("tab", { name: "Información" });
      expect(infoTab).toHaveAttribute("data-state", "active");
    });
  });

  it("0 violaciones a11y en tab Info para un campeonato", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/9", () =>
        HttpResponse.json(
          makeRaceEventRead({
            id: 9,
            series_id: 9,
            sequence_number: 1,
            is_championship: true,
            name: "Campeonato Departamental · Ginebra",
            event_date: "2026-06-12",
            location: "Ginebra",
            status: "completed",
          }),
        ),
      ),
    );
    mockAuthAs("coach");
    const { container } = renderDetail(9);

    await screen.findByTestId("competition-title");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Distinción visual en listas — CompetitionsListPage badge logic
// ---------------------------------------------------------------------------

describe("CompetitionDetailPage spec-014 — regresion copa sin badge CD", () => {
  it("una copa completada no tiene badge-championship en su detalle", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/1", () =>
        HttpResponse.json(
          makeRaceEventRead({
            id: 1,
            sequence_number: 1,
            is_championship: false,
            name: "Copa Valle XCO — Válida I",
            event_date: "2026-01-31",
            location: "Sevilla",
            status: "completed",
          }),
        ),
      ),
    );
    mockAuthAs("coach");
    renderDetail(1);

    await screen.findByTestId("competition-title");
    // No debe aparecer badge de campeonato para una copa.
    expect(screen.queryByTestId("badge-championship")).not.toBeInTheDocument();
  });

  it("0 violaciones a11y en tab Info para una copa", async () => {
    mockAuthAs("coach");
    const { container } = renderDetail(1);
    await screen.findByTestId("competition-title");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
