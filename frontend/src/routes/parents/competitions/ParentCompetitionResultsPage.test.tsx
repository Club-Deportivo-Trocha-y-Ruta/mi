/**
 * Tests vitest — ParentCompetitionResultsPage
 *
 * Cubre (FR-030 / US1 escenario 5):
 *   - Render de resultados del hijo propio (solo su fila visible)
 *   - Render del header con event_name, event_date, location
 *   - Estado vacío parent-friendly (sin CTA de importar)
 *   - Estado de carga (skeleton)
 *   - axe: 0 violaciones a11y
 *
 * Privacidad:
 *   - El backend ya filtra las filas al hijo del padre autenticado.
 *   - Este test verifica que el nombre de otro menor NO aparece en el DOM.
 */
import {
  describe,
  it,
  expect,
  vi,
  beforeAll,
  afterAll,
  afterEach,
} from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { setupServer } from "msw/node";

import { ParentCompetitionResultsPage } from "./ParentCompetitionResultsPage";
import {
  parentRaceResultsHandlers,
  raceResultsEmptyHandler,
  standingsEmptyHandler,
  makeParentRaceEventResultsResponse,
  makeRaceResultRow,
} from "@/test/msw/raceResultsHandlers";
import { http, HttpResponse } from "msw";
import {
  raceCourseHandlers,
  raceCourseParentNotFoundHandler,
} from "@/test/msw/raceCourseHandlers";

// ---------------------------------------------------------------------------
// Auth mock
// ---------------------------------------------------------------------------

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((selector) =>
    selector({ accessToken: "parent-token", user: { role: "parent", id: 99 } }),
  ),
}));

// ---------------------------------------------------------------------------
// MSW server
// ---------------------------------------------------------------------------

const BASE = "*/api/race-analysis/race-events";

const server = setupServer(...parentRaceResultsHandlers);

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

function renderPage(raceEventId = "1") {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/parents/competitions/${raceEventId}`]}>
        <Routes>
          <Route
            path="/parents/competitions/:raceEventId"
            element={<ParentCompetitionResultsPage />}
          />
          <Route path="/parents/calendar" element={<div>Calendario</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests — resultados del hijo
// ---------------------------------------------------------------------------

describe("ParentCompetitionResultsPage — resultados propios", () => {
  it("renderiza la fila del hijo propio en la pestaña Resultados", async () => {
    renderPage();

    // Esperamos que la tabla cargue
    const row = await screen.findByTestId("results-row-101", {}, { timeout: 4000 });
    expect(row).toBeInTheDocument();
    expect(screen.getByText("Mi Hijo")).toBeInTheDocument();
  });

  it("NO renderiza filas de otros menores", async () => {
    // El backend devuelve solo 1 fila (el hijo propio); verificamos que
    // no hay nombres de otros menores en el DOM.
    renderPage();

    await screen.findByTestId("results-row-101", {}, { timeout: 4000 });

    // Corredor Rival NO debe aparecer (no está en la respuesta)
    expect(screen.queryByText("Corredor Rival")).not.toBeInTheDocument();
    expect(screen.queryByText("Otro Menor")).not.toBeInTheDocument();
  });

  it("la pestaña Clasificación general muestra la fila del hijo al cambiar de tab", async () => {
    const user = userEvent.setup();
    renderPage();

    // Esperamos que Resultados cargue
    await screen.findByTestId("results-row-101", {}, { timeout: 4000 });

    // Cambiar a Clasificación general
    await user.click(screen.getByTestId("tab-btn-standings"));

    // La fila del standings del hijo
    const standingRow = await screen.findByTestId(
      "standings-row-101",
      {},
      { timeout: 4000 },
    );
    expect(standingRow).toBeInTheDocument();
    expect(screen.getByText("Mi Hijo")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests — estado de resultado en palabras (decisión del dueño 2026-09-23):
// la familia nunca debe ver los códigos crudos DNF/DNS/DSQ.
// ---------------------------------------------------------------------------

describe("ParentCompetitionResultsPage — estado de resultado", () => {
  it("muestra el estado en palabras, nunca el código crudo DNS", async () => {
    server.use(
      http.get(`${BASE}/:id/results`, ({ params }) => {
        const id = Number(params.id);
        return HttpResponse.json(
          makeParentRaceEventResultsResponse({
            race_event_id: id,
            categories: [
              {
                category_id: 1,
                code: "INF_M",
                label: "Infantil Masculino",
                rows: [
                  makeRaceResultRow({
                    competitor_id: 101,
                    display_name: "Mi Hijo",
                    athlete_id: 55,
                    is_our_club: true,
                    position: null,
                    status: "dns",
                    race_time_ms: null,
                  }),
                ],
              },
            ],
          }),
        );
      }),
    );
    renderPage();

    const row = await screen.findByTestId(
      "results-row-101",
      {},
      { timeout: 4000 },
    );
    // Comparte etiqueta con el catálogo de Historial (raceHistory.types.ts).
    expect(within(row).getAllByText("No salió").length).toBeGreaterThan(0);
    expect(within(row).queryByText("DNS")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests — header del evento
// ---------------------------------------------------------------------------

describe("ParentCompetitionResultsPage — header", () => {
  it("muestra el nombre del evento cuando el backend lo provee", async () => {
    renderPage();

    await screen.findByTestId("event-name", {}, { timeout: 4000 });
    expect(screen.getByTestId("event-name")).toHaveTextContent(
      "Copa Valle IV — Cali",
    );
  });

  it("muestra la fecha formateada cuando el backend la provee", async () => {
    renderPage();

    await screen.findByTestId("event-header", {}, { timeout: 4000 });
    // "17 de mayo de 2026" — formatDate con locale es-CO
    expect(screen.getByTestId("event-header")).toHaveTextContent(/mayo/i);
    expect(screen.getByTestId("event-header")).toHaveTextContent(/2026/);
  });

  it("muestra la ubicación cuando el backend la provee", async () => {
    renderPage();

    await screen.findByTestId("event-header", {}, { timeout: 4000 });
    expect(screen.getByTestId("event-header")).toHaveTextContent("Cali");
  });

  it("muestra breadcrumb con enlace al calendario", async () => {
    renderPage();

    await screen.findByTestId("event-header", {}, { timeout: 4000 });
    const backLink = screen.getByTestId("breadcrumb-back");
    expect(backLink).toHaveAttribute("href", "/parents/calendar");
    expect(backLink).toHaveTextContent(/Calendario/i);
  });
});

// ---------------------------------------------------------------------------
// Tests — estado vacío
// ---------------------------------------------------------------------------

describe("ParentCompetitionResultsPage — estado vacío", () => {
  it("muestra el estado vacío parent-friendly cuando no hay resultados", async () => {
    server.use(raceResultsEmptyHandler, standingsEmptyHandler);
    renderPage();

    const emptyState = await screen.findByTestId(
      "parent-results-empty",
      {},
      { timeout: 4000 },
    );
    expect(emptyState).toBeInTheDocument();
    expect(
      screen.getByText(/Aún no se han publicado resultados/i),
    ).toBeInTheDocument();
  });

  it("NO muestra CTA de 'Importar resultados' (solo para coach)", async () => {
    server.use(raceResultsEmptyHandler, standingsEmptyHandler);
    renderPage();

    await screen.findByTestId("parent-results-empty", {}, { timeout: 4000 });
    // El link de importar es exclusivo del coach; no debe aparecer para padres
    expect(
      screen.queryByText(/Importar resultados/i),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests — loading skeleton
// ---------------------------------------------------------------------------

describe("ParentCompetitionResultsPage — estado de carga", () => {
  it("renderiza sin errores (no hay crash en carga inicial)", () => {
    // Antes de que el MSW responda, el componente muestra skeleton
    renderPage();
    // No hay alert de error en el render inicial
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Tests — hideClubFilter (integración con ResultsTable/StandingsTable)
// ---------------------------------------------------------------------------

describe("ParentCompetitionResultsPage — hideClubFilter", () => {
  it("el toggle 'Solo mi club' NO aparece en la vista de padre", async () => {
    renderPage();

    // Esperamos que la tabla cargue
    await screen.findByTestId("results-row-101", {}, { timeout: 4000 });

    // El toggle de filtrado por club no debe estar presente
    expect(
      screen.queryByTestId("results-club-only-toggle"),
    ).not.toBeInTheDocument();
  });

  it("el toggle 'Solo mi club' tampoco aparece en la pestaña de standings", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByTestId("results-row-101", {}, { timeout: 4000 });
    await user.click(screen.getByTestId("tab-btn-standings"));
    await screen.findByTestId("standings-row-101", {}, { timeout: 4000 });

    expect(
      screen.queryByTestId("standings-club-only-toggle"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests — error
// ---------------------------------------------------------------------------

describe("ParentCompetitionResultsPage — estado de error", () => {
  it("muestra banner de error cuando el endpoint falla", async () => {
    server.use(
      http.get(`${BASE}/:id/results`, () =>
        HttpResponse.json({ detail: "Error" }, { status: 500 }),
      ),
      http.get(`${BASE}/:id/standings`, () =>
        HttpResponse.json({ detail: "Error" }, { status: 500 }),
      ),
    );
    renderPage();

    const errorBanner = await screen.findByTestId(
      "parent-results-error",
      {},
      { timeout: 4000 },
    );
    expect(errorBanner).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests — circuito (CourseSummary, feature 043 T054/US5)
//
// Bug fix (T059): estas dos pruebas originalmente sobreescribían el
// endpoint de circuito vía `mswServer.use(...)` — el servidor MSW GLOBAL de
// `src/test/setup.ts` — asumiendo que podía coexistir con el `server` local
// de este archivo (que sólo registra resultados/standings). En la práctica,
// dos instancias `setupServer` escuchando a la vez en el mismo entorno
// jsdom NO se combinan: la instancia registrada más recientemente
// (`server`, aquí) decide sola si una petición sin handler propio se
// intercepta o se deja pasar, así que las peticiones a `.../course`
// (solo registradas en `mswServer`) escapaban como una petición de red
// real fallida en vez de resolver el fixture — dejando estas dos pruebas
// en rojo sin importar cómo se cableara la página. Confirmado
// reproduciendo el hang/network-error con `useRaceCourse` en aislamiento.
// Arreglo: registrar los handlers de circuito en el `server` LOCAL de este
// archivo (igual que resultados/standings), no en el `mswServer` global.
//
// `course_not_available` (404) es un estado NORMAL para este endpoint (el
// padre puede consultar una válida sin circuito registrado aún) — a
// diferencia de los 500 de resultados/standings, NO debe mostrarse ningún
// banner de error ni toast; simplemente no hay tarjeta.
// ---------------------------------------------------------------------------

describe("ParentCompetitionResultsPage — circuito (CourseSummary)", () => {
  it("useRaceCourse 200 con has_course_data=true: muestra la tarjeta de resumen del circuito", async () => {
    server.use(...raceCourseHandlers);
    renderPage();

    await screen.findByTestId("results-row-101", {}, { timeout: 4000 });
    expect(
      await screen.findByTestId("course-summary", {}, { timeout: 4000 }),
    ).toBeInTheDocument();
  });

  it("GET .../course 404 course_not_available: NO renderiza la tarjeta de circuito y NO aparece ningún toast/banner de error", async () => {
    server.use(raceCourseParentNotFoundHandler);
    renderPage();

    await screen.findByTestId("results-row-101", {}, { timeout: 4000 });
    expect(screen.queryByTestId("course-summary")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Accessibility (axe)
// ---------------------------------------------------------------------------

describe("ParentCompetitionResultsPage — accesibilidad", () => {
  it("no tiene violaciones axe con datos cargados", async () => {
    const { container } = renderPage();

    await screen.findByTestId("results-row-101", {}, { timeout: 5000 });

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones axe en estado vacío", async () => {
    server.use(raceResultsEmptyHandler, standingsEmptyHandler);
    const { container } = renderPage();

    await screen.findByTestId("parent-results-empty", {}, { timeout: 4000 });

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
