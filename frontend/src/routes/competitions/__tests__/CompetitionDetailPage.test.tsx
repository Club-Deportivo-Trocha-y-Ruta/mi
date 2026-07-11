/**
 * Tests para CompetitionDetailPage.
 *
 * Cubre:
 *  - Carga event y renderiza header + subtítulo + tab Info por defecto.
 *  - Tabs URL-driven: ?tab=results activa pestaña correcta.
 *  - has_calendar_event=false → boton "Asociar a calendario" visible con href correcto.
 *  - has_calendar_event=true → badge "En calendario" visible sin botón.
 *  - has_calendar_event=undefined → ninguno visible (conservador).
 *  - status=cancelled → botón "Asociar a calendario" oculto incluso con has_calendar_event=false.
 *  - 404 → navigate a /competitions.
 *  - Delete admin → confirm → DELETE → navigate.
 *  - 0 violaciones a11y en tab Info.
 *
 * Mockeamos AthletesTab e InsightsTab para evitar la cascada de Suspense
 * lazy + las queries de useClubInsightsByRace (no son objeto de estos tests).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { http, HttpResponse } from "msw";

// Mock de auth.store — alternable entre coach y admin.
vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

// Mock de useNavigate para asserting redirects.
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock de tabs lazy para evitar cargar dependencias pesadas (insights IA).
vi.mock("@/components/competitions/tabs/AthletesTab", () => ({
  AthletesTab: () => <div data-testid="mock-athletes-tab">athletes</div>,
}));
vi.mock("@/components/competitions/tabs/InsightsTab", () => ({
  InsightsTab: () => <div data-testid="mock-insights-tab">insights</div>,
}));
// Mock del ConditionsTab que requiere el RaceConditionsCard (con su sheet lazy).
vi.mock("@/components/competitions/tabs/ConditionsTab", () => ({
  ConditionsTab: () => <div data-testid="mock-conditions-tab">conditions</div>,
}));

import { useAuthStore } from "@/store/auth.store";
import { mswServer } from "@/test/setup";
import {
  makeRaceEventRead,
  raceEventNotFoundHandler,
  raceEventsHandlers,
} from "@/test/msw/raceEventsHandlers";
import { CompetitionDetailPage } from "@/routes/competitions/CompetitionDetailPage";

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

function renderDetail(
  id: string | number = 1,
  search = "",
) {
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
          <Route path="/competitions/:id" element={<CompetitionDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mswServer.use(...raceEventsHandlers);
});

describe("CompetitionDetailPage — render", () => {
  it("muestra header con nombre y subtítulo (sede + fecha + estado)", async () => {
    mockAuthAs("coach");
    renderDetail(1);
    await waitFor(() =>
      expect(screen.getByTestId("competition-title")).toHaveTextContent(
        "Copa Valle XCO — Válida I",
      ),
    );
    const subtitle = screen.getByTestId("competition-subtitle");
    expect(subtitle.textContent).toMatch(/Sevilla/);
    expect(subtitle.textContent).toMatch(/Completada/);
  });
});

describe("CompetitionDetailPage — tabs URL-driven", () => {
  it("?tab=results activa la pestaña Resultados", async () => {
    mockAuthAs("coach");
    renderDetail(1, "?tab=results");
    await waitFor(() =>
      expect(screen.getByTestId("competition-title")).toBeInTheDocument(),
    );
    // El trigger de "Resultados" debe estar marcado como activo (data-state=active)
    const trigger = screen.getByRole("tab", { name: "Resultados" });
    expect(trigger).toHaveAttribute("data-state", "active");
  });
});

describe("CompetitionDetailPage — CF6 calendar CTA", () => {
  it("has_calendar_event=false → botón 'Asociar a calendario' visible (US1 one-click)", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/:id", () =>
        HttpResponse.json(
          makeRaceEventRead({
            id: 7,
            has_calendar_event: false,
            status: "completed",
          }),
        ),
      ),
    );
    mockAuthAs("coach");
    renderDetail(7);
    const btn = await screen.findByTestId("btn-associate-calendar");
    // US1: es un <button>, no un <Link> — el href vive en getCalendarNewUrl() para US2
    expect(btn.tagName).toBe("BUTTON");
    expect(btn).not.toBeDisabled();
  });

  it("has_calendar_event=true → badge 'En calendario' sin botón", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/:id", () =>
        HttpResponse.json(
          makeRaceEventRead({
            id: 8,
            has_calendar_event: true,
          }),
        ),
      ),
    );
    mockAuthAs("coach");
    renderDetail(8);
    expect(await screen.findByTestId("badge-in-calendar")).toBeInTheDocument();
    expect(
      screen.queryByTestId("btn-associate-calendar"),
    ).not.toBeInTheDocument();
  });

  it("has_calendar_event=undefined → ninguno visible (comportamiento conservador)", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/:id", () => {
        // Construimos manualmente sin el campo has_calendar_event
        const ev = makeRaceEventRead({ id: 9 });
        const { has_calendar_event: _, ...rest } = ev;
        return HttpResponse.json(rest);
      }),
    );
    mockAuthAs("coach");
    renderDetail(9);
    await screen.findByTestId("competition-title");
    expect(
      screen.queryByTestId("btn-associate-calendar"),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("badge-in-calendar")).not.toBeInTheDocument();
  });

  it("status=cancelled oculta 'Asociar a calendario' incluso con has_calendar_event=false", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/:id", () =>
        HttpResponse.json(
          makeRaceEventRead({
            id: 10,
            status: "cancelled",
            has_calendar_event: false,
          }),
        ),
      ),
    );
    mockAuthAs("coach");
    renderDetail(10);
    await screen.findByTestId("competition-title");
    expect(
      screen.queryByTestId("btn-associate-calendar"),
    ).not.toBeInTheDocument();
    // Y el badge cancelled sí aparece
    expect(screen.getByTestId("badge-cancelled")).toBeInTheDocument();
  });
});

describe("CompetitionDetailPage — 404", () => {
  it("404 redirige a /competitions via navigate(replace)", async () => {
    mswServer.use(raceEventNotFoundHandler);
    mockAuthAs("coach");
    renderDetail(999);
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/competitions", {
        replace: true,
      }),
    );
  });
});

describe("CompetitionDetailPage — delete admin", () => {
  it("confirm → DELETE → navigate('/competitions', replace:true)", async () => {
    let deleted = false;
    mswServer.use(
      http.delete("*/api/race-analysis/race-events/1", () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    mockAuthAs("admin");
    const user = userEvent.setup();
    renderDetail(1);
    await screen.findByTestId("competition-title");

    await user.click(screen.getByTestId("btn-delete"));
    expect(
      await screen.findByRole("alertdialog", { name: /Eliminar competencia/i }),
    ).toBeInTheDocument();
    // tone="danger": el foco inicial va a Cancelar, nunca a Eliminar válida.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Cancelar/i })).toHaveFocus(),
    );
    expect(
      screen.getByRole("button", { name: /Eliminar válida/i }),
    ).not.toHaveFocus();
    await user.click(screen.getByRole("button", { name: /Eliminar válida/i }));

    await waitFor(() => expect(deleted).toBe(true));
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/competitions", {
        replace: true,
      }),
    );
  });
});

describe("CompetitionDetailPage — a11y", () => {
  it("0 violaciones jest-axe en tab Info", async () => {
    mockAuthAs("coach");
    const { container } = renderDetail(1);
    await screen.findByTestId("competition-title");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
