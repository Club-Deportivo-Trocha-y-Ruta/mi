/**
 * Tests de HistoricalLoadPage — tablero de carga histórica (feature 044,
 * US5, T066).
 *
 * Cubre: loading, vacío, error, agrupación por temporada, estados del
 * tablero (listo / categorías por revisar / identidad por revisar /
 * cargado), banner de identidad, acciones commit y commit-pending con sus
 * códigos de gate (409 identity_review_pending, 409 nothing_pending); cero
 * violaciones axe.
 *
 * Nombres/archivos siempre sintéticos — nunca datos reales de un menor.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from "sonner";
import { mswServer } from "@/test/setup";
import {
  makeHistoricalImportItem,
  makeImportListResponse,
  raceImportsHistoryCommitIdentityPendingHandler,
  raceImportsHistoryCommitMatchesUnresolvedHandler,
  raceImportsHistoryCommitPendingNothingHandler,
  raceImportsHistoryEmptyHandler,
  raceImportsHistoryErrorHandler,
  raceImportsHistoryHandlers,
} from "@/test/msw/raceImportsHistoryHandlers";
import {
  raceIdentityEmptySummaryHandler,
  raceIdentityHandlers,
} from "@/test/msw/raceIdentityHandlers";
import { HistoricalLoadPage } from "@/routes/competitions/history/HistoricalLoadPage";

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/competitions/history"]}>
        <Routes>
          <Route path="/competitions/history" element={<HistoricalLoadPage />} />
          <Route
            path="/competitions/identity-review"
            element={<p>Revisión de identidad</p>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("HistoricalLoadPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mswServer.use(...raceImportsHistoryHandlers, ...raceIdentityHandlers);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("muestra el skeleton de carga", () => {
    renderPage();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Cargando cargues históricos...",
    );
  });

  it("vacío: sin cargues históricos ofrece cargar el primer archivo", async () => {
    mswServer.use(raceImportsHistoryEmptyHandler);
    renderPage();
    expect(
      await screen.findByText("Todavía no hay cargues históricos"),
    ).toBeInTheDocument();
  });

  it("error: falla la carga y ofrece reintentar", async () => {
    mswServer.use(raceImportsHistoryErrorHandler);
    renderPage();
    expect(
      await screen.findByText(
        "No se pudo cargar el tablero de cargas históricas.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Reintentar/i }),
    ).toBeInTheDocument();
  });

  it("agrupa por temporada y muestra el estado 'listo' cuando no hay pendientes", async () => {
    mswServer.use(
      raceIdentityEmptySummaryHandler,
      http.get("*/api/race-analysis/imports/", () =>
        HttpResponse.json(
          makeImportListResponse({
            items: [
              makeHistoricalImportItem({
                id: "1",
                season: 2024,
                valida_num: 1,
                pending_categories_count: 0,
              }),
              makeHistoricalImportItem({
                id: "2",
                season: 2025,
                valida_num: 3,
                pending_categories_count: 0,
              }),
            ],
            total: 2,
          }),
        ),
      ),
    );
    renderPage();

    expect(await screen.findByText("Temporada 2025")).toBeInTheDocument();
    expect(screen.getByText("Temporada 2024")).toBeInTheDocument();
    // Orden: 2025 antes que 2024 (descendente).
    const headings = screen.getAllByRole("heading", { level: 2 });
    expect(headings[0]).toHaveTextContent("Temporada 2025");
    expect(headings[1]).toHaveTextContent("Temporada 2024");

    expect(screen.getAllByText("Listo para cargar")).toHaveLength(2);
    expect(screen.getByTestId("commit-1")).toBeInTheDocument();
  });

  it("muestra 'categorías por revisar' con el contador cuando hay pendientes", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/imports/", () =>
        HttpResponse.json(
          makeImportListResponse({
            items: [
              makeHistoricalImportItem({
                id: "1",
                pending_categories_count: 2,
              }),
            ],
          }),
        ),
      ),
    );
    renderPage();

    expect(await screen.findByText("Categorías por revisar")).toBeInTheDocument();
    expect(screen.getByTestId("pending-categories-1")).toHaveTextContent(
      "2 categorías pendientes",
    );
    // Sin pendientes de categoría, el botón de commit directo no aplica.
    expect(screen.queryByTestId("commit-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("commit-pending-1")).toBeInTheDocument();
  });

  it("muestra 'identidad por revisar' y el banner cuando hay candidatos pendientes", async () => {
    renderPage(); // raceIdentityHandlers default: pending=2
    expect(
      await screen.findByText("Identidad por revisar"),
    ).toBeInTheDocument();
    expect(await screen.findByTestId("identity-banner")).toHaveTextContent(
      "Hay 2 posibles coincidencias de identidad por revisar",
    );
    expect(
      screen.getByRole("link", { name: "Revisar identidad" }),
    ).toHaveAttribute("href", "/competitions/identity-review");
  });

  it("no muestra el banner de identidad cuando no hay pendientes", async () => {
    mswServer.use(raceIdentityEmptySummaryHandler);
    renderPage();
    await screen.findByTestId("import-row-1");
    expect(screen.queryByTestId("identity-banner")).not.toBeInTheDocument();
  });

  it("muestra 'cargado' para un import ya confirmado, sin acciones", async () => {
    mswServer.use(
      raceIdentityEmptySummaryHandler,
      http.get("*/api/race-analysis/imports/", () =>
        HttpResponse.json(
          makeImportListResponse({
            items: [makeHistoricalImportItem({ id: "1", status: "committed" })],
          }),
        ),
      ),
    );
    renderPage();
    expect(await screen.findByText("Cargado")).toBeInTheDocument();
    expect(screen.queryByTestId("commit-1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("commit-pending-1")).not.toBeInTheDocument();
  });

  it("confirmar carga: éxito muestra el toast con el conteo de resultados", async () => {
    mswServer.use(raceIdentityEmptySummaryHandler);
    const user = userEvent.setup();
    renderPage();
    const button = await screen.findByTestId("commit-1");
    await user.click(button);
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        "Válida cargada: 42 resultado(s).",
      );
    });
  });

  it("confirmar carga: 409 identity_review_pending muestra el motivo y el link", async () => {
    mswServer.use(
      raceIdentityEmptySummaryHandler,
      raceImportsHistoryCommitIdentityPendingHandler,
    );
    const user = userEvent.setup();
    renderPage();
    const button = await screen.findByTestId("commit-1");
    await user.click(button);

    expect(
      await screen.findByTestId("import-row-error-1"),
    ).toHaveTextContent(
      "Hay 3 posibles coincidencias de identidad por revisar antes de confirmar la carga.",
    );
    expect(
      screen.getByRole("link", { name: "Ir a la revisión de identidad" }),
    ).toHaveAttribute("href", "/competitions/identity-review");
  });

  it("confirmar carga: 409 matches_unresolved enlaza al asistente de esa válida", async () => {
    mswServer.use(
      raceIdentityEmptySummaryHandler,
      raceImportsHistoryCommitMatchesUnresolvedHandler,
    );
    const user = userEvent.setup();
    renderPage();
    const button = await screen.findByTestId("commit-1");
    await user.click(button);

    expect(
      await screen.findByTestId("import-row-error-1"),
    ).toHaveTextContent(
      "Hay 2 corredores del club sin coincidencia resuelta. Complétala en el asistente de importación.",
    );
    // `makeHistoricalImportItem` default trae `event_id: 501` — el link debe
    // ir al wizard scoped a esa válida, no al genérico standalone.
    expect(
      screen.getByTestId("import-row-wizard-link-1"),
    ).toHaveAttribute("href", "/competitions/501/import");
  });

  it("confirmar carga: 409 matches_unresolved sin event_id enlaza al asistente genérico", async () => {
    mswServer.use(
      raceIdentityEmptySummaryHandler,
      raceImportsHistoryCommitMatchesUnresolvedHandler,
      http.get("*/api/race-analysis/imports/", () =>
        HttpResponse.json(
          makeImportListResponse({
            items: [makeHistoricalImportItem({ id: "1", event_id: null })],
          }),
        ),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    const button = await screen.findByTestId("commit-1");
    await user.click(button);

    expect(
      await screen.findByTestId("import-row-wizard-link-1"),
    ).toHaveAttribute("href", "/competitions/import");
  });

  it("completar pendientes: 409 nothing_pending muestra el motivo", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/imports/", () =>
        HttpResponse.json(
          makeImportListResponse({
            items: [
              makeHistoricalImportItem({
                id: "1",
                pending_categories_count: 1,
              }),
            ],
          }),
        ),
      ),
      raceImportsHistoryCommitPendingNothingHandler,
    );
    const user = userEvent.setup();
    renderPage();
    const button = await screen.findByTestId("commit-pending-1");
    await user.click(button);

    expect(
      await screen.findByTestId("import-row-error-1"),
    ).toHaveTextContent(
      "No hay categorías pendientes por cargar en esta válida.",
    );
  });

  it("sin violaciones de accesibilidad", async () => {
    mswServer.use(raceIdentityEmptySummaryHandler);
    const { container } = renderPage();
    await screen.findByTestId("import-row-1");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones de accesibilidad con el banner de identidad visible", async () => {
    const { container } = renderPage();
    await screen.findByTestId("identity-banner");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
