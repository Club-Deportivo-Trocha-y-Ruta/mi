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
 * Y (hotfix multicopa — identidad de válida, 2026-09-16):
 *  - `matchedSeries.short_name` se pasa a InfoTab como `seriesShortName` →
 *    la fila "Serie" muestra el nombre corto, no el completo.
 *
 * Y (feature 045, US6 / T049-T050):
 *  - Pestañas: Información · Resultados · Clasificación (solo copas) ·
 *    «Circuito y condiciones» (`?tab=circuito`) · «Análisis IA».
 *  - `?tab=conditions` es alias de `?tab=circuito` y la URL se reescribe.
 *  - Acción del encabezado: «Editar datos» (ya no «Editar metadata»).
 *
 * Mockeamos InsightsTab para evitar la cascada de Suspense lazy + las
 * queries de useClubInsightsByRace (no son objeto de estos tests).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
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
import { makeRaceSeriesRead } from "@/test/msw/raceSeriesHandlers";
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

/** Expone la URL actual para asertar reescrituras de `?tab=` (alias). */
function LocationProbe() {
  const location = useLocation();
  return (
    <div data-testid="location-probe" hidden>
      {location.pathname}
      {location.search}
    </div>
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
        <LocationProbe />
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
      expect(
        screen.getByRole("heading", { level: 1, name: "Copa Valle XCO — Válida I" }),
      ).toBeInTheDocument(),
    );
    const subtitle = screen.getByText(/Sevilla/, { selector: "p" });
    expect(subtitle.textContent).toMatch(/Completada/);
  });
});

describe("CompetitionDetailPage — hotfix multicopa (nombre corto de la copa)", () => {
  it("pasa matchedSeries.short_name a InfoTab — la fila Serie muestra el nombre corto", async () => {
    mockAuthAs("coach");
    mswServer.use(
      http.get("*/api/race-analysis/race-series", () =>
        HttpResponse.json({
          items: [
            makeRaceSeriesRead({
              id: 1,
              name: "Copa Let's Go Interdepartamental XCO",
              short_name: "Let's GO",
            }),
          ],
          total: 1,
        }),
      ),
    );
    renderDetail(1);

    await screen.findByRole("heading", {
      level: 1,
      name: "Copa Valle XCO — Válida I",
    });

    expect(await screen.findByText("Let's GO")).toBeInTheDocument();
    expect(
      screen.queryByText("Copa Let's Go Interdepartamental XCO"),
    ).not.toBeInTheDocument();
  });
});

describe("CompetitionDetailPage — tabs URL-driven", () => {
  it("?tab=results activa la pestaña Resultados", async () => {
    mockAuthAs("coach");
    renderDetail(1, "?tab=results");
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument(),
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
    await screen.findByRole("heading", { level: 1 });
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
    await screen.findByRole("heading", { level: 1 });
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
    await screen.findByRole("heading", { level: 1 });

    await user.click(screen.getByTestId("btn-delete"));
    expect(
      await screen.findByRole("alertdialog", { name: /Eliminar válida/i }),
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

  // Feature 045 (T083, FR-002): el copy del diálogo sigue el tipo de evento.
  it("un campeonato dice «Eliminar campeonato» y «El campeonato se eliminará…», nunca «válida»", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/9", () =>
        HttpResponse.json(
          makeRaceEventRead({
            id: 9,
            is_championship: true,
            name: "Campeonato Departamental XCO",
          }),
        ),
      ),
    );
    mockAuthAs("admin");
    const user = userEvent.setup();
    renderDetail(9);
    await screen.findByRole("heading", { level: 1 });

    await user.click(screen.getByTestId("btn-delete"));
    const dialog = await screen.findByRole("alertdialog", {
      name: /Eliminar campeonato/i,
    });
    expect(dialog).toHaveTextContent(/El campeonato se eliminará/i);
    expect(dialog).not.toHaveTextContent(/válida/i);
    expect(
      screen.getByRole("button", { name: "Eliminar campeonato" }),
    ).toBeInTheDocument();
  });
});

describe("CompetitionDetailPage — a11y", () => {
  it("0 violaciones jest-axe en tab Info", async () => {
    mockAuthAs("coach");
    const { container } = renderDetail(1);
    await screen.findByRole("heading", { level: 1 });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

describe("CompetitionDetailPage — tab «Circuito y condiciones» (feature 043 T029 + 045 T049)", () => {
  it("?tab=circuito renderiza CourseTab y las condiciones juntos; 0 violaciones jest-axe", async () => {
    mockAuthAs("coach");
    const { container } = renderDetail(1, "?tab=circuito");
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument(),
    );

    const trigger = screen.getByRole("tab", { name: "Circuito y condiciones" });
    expect(trigger).toHaveAttribute("data-state", "active");

    // Fixture feliz por defecto (`raceCourseHandlers`, registrado global).
    expect(await screen.findByTestId("course-tab")).toBeInTheDocument();
    expect(
      await screen.findByTestId("course-variants-card"),
    ).toBeInTheDocument();
    // Las condiciones ya no son otra pestaña: viven en el mismo panel.
    expect(screen.getByTestId("mock-conditions-tab")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "Circuito" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "Condiciones" }),
    ).toBeInTheDocument();

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("?tab=conditions es alias de ?tab=circuito: activa «Circuito y condiciones» y reescribe la URL conservando el resto", async () => {
    mockAuthAs("coach");
    renderDetail(1, "?tab=conditions&foo=bar");
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument(),
    );

    const trigger = screen.getByRole("tab", { name: "Circuito y condiciones" });
    expect(trigger).toHaveAttribute("data-state", "active");
    expect(screen.getByTestId("mock-conditions-tab")).toBeInTheDocument();

    await waitFor(() => {
      const url = screen.getByTestId("location-probe").textContent ?? "";
      expect(url).toContain("tab=circuito");
      expect(url).toContain("foo=bar");
      expect(url).not.toContain("conditions");
    });
  }, 15_000);

  it("ya no hay pestañas sueltas «Condiciones» ni «Circuito»", async () => {
    mockAuthAs("coach");
    renderDetail(1);
    await screen.findByRole("tab", { name: "Circuito y condiciones" });
    expect(
      screen.queryByRole("tab", { name: "Condiciones" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "Circuito" }),
    ).not.toBeInTheDocument();
  });
});

describe("CompetitionDetailPage — pestañas del detalle (feature 045, US6)", () => {
  it("una copa muestra Información · Resultados · Clasificación · Circuito y condiciones · Análisis IA, en ese orden", async () => {
    mockAuthAs("coach");
    renderDetail(1);
    await screen.findByRole("tab", { name: "Información" });
    expect(
      screen.getAllByRole("tab").map((tab) => tab.textContent),
    ).toEqual([
      "Información",
      "Resultados",
      "Clasificación",
      "Circuito y condiciones",
      "Análisis IA",
    ]);
  });

  it("un campeonato omite «Clasificación» y conserva el resto", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/9", () =>
        HttpResponse.json(
          makeRaceEventRead({ id: 9, is_championship: true }),
        ),
      ),
    );
    mockAuthAs("coach");
    renderDetail(9);
    await screen.findByRole("tab", { name: "Información" });
    expect(
      screen.getAllByRole("tab").map((tab) => tab.textContent),
    ).toEqual([
      "Información",
      "Resultados",
      "Circuito y condiciones",
      "Análisis IA",
    ]);
  });

  it("la acción del encabezado se llama «Editar datos» (no «Editar metadata»)", async () => {
    mockAuthAs("coach");
    renderDetail(1);
    const edit = await screen.findByTestId("btn-edit");
    expect(edit).toHaveTextContent("Editar datos");
    expect(edit).toHaveAttribute("href", "/competitions/1/edit");
    expect(screen.queryByText(/metadata/i)).not.toBeInTheDocument();
  });
});

describe("CompetitionDetailPage — Análisis IA tab label (T054 lock-in, updated by feature 045)", () => {
  // Cambio deliberado (feature 045, US6 + glosario de contracts/ui-copy.md):
  // el lock-in de la feature 033 fijaba «Insights IA» como sustantivo de este
  // tab. 045 retira «Insights IA» como nombre de pestaña en todo el producto
  // y el último tab del detalle pasa a «Análisis IA» (mismo nombre que la
  // vista de «Carreras» del atleta). Este test sigue siendo el candado: no
  // debe volver a «Insights IA» ni derivar a «Análisis con IA».
  it("el último tab se llama 'Análisis IA', no «Insights IA» ni «Análisis con IA»", async () => {
    mockAuthAs("coach");
    renderDetail(1);
    const trigger = await screen.findByRole("tab", { name: "Análisis IA" });
    expect(trigger).toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "Insights IA" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "Análisis con IA" }),
    ).not.toBeInTheDocument();
  });
});
