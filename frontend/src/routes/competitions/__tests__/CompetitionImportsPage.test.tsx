/**
 * CompetitionImportsPage — «Cargas e identidades» (feature 045, US3, T053).
 *
 * Ruta: /competitions/imports?seccion=cargas|identidades|sin-enlazar[&import=<id>]
 *
 * Cubre: sección por defecto y valores desconocidos, cada sección con
 * `?seccion=`, cambio de sección que se refleja en la URL (y suelta
 * `import` fuera de «¿Es la misma persona?»), insignias con los conteos
 * (cargas en curso, decisiones pendientes), el regreso a la carga desde
 * `?import=<id>`, y cero violaciones axe a nivel de página.
 *
 * Datos sintéticos — nunca datos reales de un menor.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe } from "jest-axe";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// La API de competidores se mockea para devolver una lista vacía → «Sin
// enlazar» monta su estado vacío de forma determinista (sin red real).
vi.mock("@/api/raceCompetitors", () => ({
  listUnlinkedCompetitors: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  getCompetitorSuggestions: vi.fn(),
  linkCompetitor: vi.fn(),
  unlinkCompetitor: vi.fn(),
}));
vi.mock("@/api/athletes", () => ({
  getAthletes: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  getAthlete: vi.fn(),
}));

// jsdom no implementa estos métodos de Pointer Events — Radix Select (filtro
// de estado de «¿Es la misma persona?») los invoca.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {};
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

import { mswServer } from "@/test/setup";
import {
  makeHistoricalImportItem,
  makeImportListResponse,
  raceImportsHistoryHandlers,
} from "@/test/msw/raceImportsHistoryHandlers";
import { raceIdentityHandlers } from "@/test/msw/raceIdentityHandlers";
import { http, HttpResponse } from "msw";
import { CompetitionImportsPage } from "@/routes/competitions/CompetitionImportsPage";

function LocationProbe() {
  const location = useLocation();
  return (
    <div data-testid="loc">
      {location.pathname}
      {location.search}
    </div>
  );
}

function renderPage(entry = "/competitions/imports") {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[entry]}>
        <LocationProbe />
        <Routes>
          <Route path="/competitions/imports" element={<CompetitionImportsPage />} />
          <Route path="/competitions" element={<p>Competencias</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CompetitionImportsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mswServer.use(...raceImportsHistoryHandlers, ...raceIdentityHandlers);
  });

  it("muestra el título del área y el regreso a Competencias", async () => {
    renderPage();
    expect(
      screen.getByRole("heading", { level: 1, name: "Cargas e identidades" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Volver a competencias/i }),
    ).toHaveAttribute("href", "/competitions");
    await screen.findByTestId("loads-section");
  });

  it("sin ?seccion abre «Cargas»", async () => {
    renderPage();
    expect(await screen.findByTestId("loads-section")).toBeInTheDocument();
    expect(screen.getByTestId("seccion-cargas")).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("?seccion desconocida cae en «Cargas»", async () => {
    renderPage("/competitions/imports?seccion=otra-cosa");
    expect(await screen.findByTestId("loads-section")).toBeInTheDocument();
  });

  it("?seccion=identidades abre «¿Es la misma persona?»", async () => {
    renderPage("/competitions/imports?seccion=identidades");
    expect(await screen.findByTestId("identity-section")).toBeInTheDocument();
    expect(screen.getByTestId("seccion-identidades")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.queryByTestId("loads-section")).not.toBeInTheDocument();
  });

  it("?seccion=sin-enlazar abre «Sin enlazar»", async () => {
    renderPage("/competitions/imports?seccion=sin-enlazar");
    expect(await screen.findByTestId("unlinked-section")).toBeInTheDocument();
    await screen.findByTestId("unlinked-competitors-tab");
  });

  it("cambiar de sección se refleja en la URL", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("loads-section");

    await user.click(screen.getByTestId("seccion-identidades"));
    expect(await screen.findByTestId("identity-section")).toBeInTheDocument();
    expect(screen.getByTestId("loc")).toHaveTextContent("seccion=identidades");

    await user.click(screen.getByTestId("seccion-sin-enlazar"));
    expect(await screen.findByTestId("unlinked-section")).toBeInTheDocument();
    expect(screen.getByTestId("loc")).toHaveTextContent("seccion=sin-enlazar");
  });

  it("?import solo vive en «¿Es la misma persona?»: al salir de esa sección se suelta", async () => {
    const user = userEvent.setup();
    renderPage("/competitions/imports?seccion=identidades&import=7");
    await screen.findByTestId("identity-section");
    expect(screen.getByTestId("loc")).toHaveTextContent("import=7");

    await user.click(screen.getByTestId("seccion-cargas"));
    await screen.findByTestId("loads-section");
    expect(screen.getByTestId("loc")).toHaveTextContent("seccion=cargas");
    expect(screen.getByTestId("loc")).not.toHaveTextContent("import=");
  });

  it("desde el bloqueo de una carga (?import=<id>) ofrece volver a ella", async () => {
    renderPage("/competitions/imports?seccion=identidades&import=7");
    expect(await screen.findByTestId("identity-back-to-import")).toHaveAttribute(
      "href",
      "/competitions/import?import=7",
    );
  });

  it("insignias: cargas en curso y decisiones pendientes (para lectores de pantalla, en palabras)", async () => {
    // Handlers por defecto: 1 carga `pending` y 2 candidatos de identidad.
    renderPage();
    await waitFor(() => {
      expect(
        within(screen.getByTestId("seccion-cargas")).getByText("1 carga en curso"),
      ).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(
        within(screen.getByTestId("seccion-identidades")).getByText(
          "2 decisiones pendientes",
        ),
      ).toBeInTheDocument();
    });
  });

  it("insignia de cargas cuenta solo las en curso (no las ya confirmadas)", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/imports/", () =>
        HttpResponse.json(
          makeImportListResponse({
            items: [
              makeHistoricalImportItem({ id: "1", status: "committed" }),
              makeHistoricalImportItem({ id: "2", status: "dry_run" }),
              makeHistoricalImportItem({ id: "3", status: "pending" }),
            ],
            total: 3,
          }),
        ),
      ),
    );
    renderPage();
    await waitFor(() => {
      expect(
        within(screen.getByTestId("seccion-cargas")).getByText("2 cargas en curso"),
      ).toBeInTheDocument();
    });
  });

  it("sin violaciones de accesibilidad (sección «Cargas»)", async () => {
    const { container } = renderPage();
    await screen.findByTestId("import-row-1");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones de accesibilidad (sección «¿Es la misma persona?»)", async () => {
    const { container } = renderPage("/competitions/imports?seccion=identidades");
    await screen.findByTestId("candidate-left");
    expect(await axe(container)).toHaveNoViolations();
  });
});
