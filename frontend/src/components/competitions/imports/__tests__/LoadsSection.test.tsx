/**
 * Tests de LoadsSection — «Cargas» de «Cargas e identidades» (feature 045,
 * US3; antes `HistoricalLoadPage`, feature 044 US5, T066).
 *
 * Cubre: loading, vacío, error, agrupación por temporada, estados del tablero
 * (listo / categorías por revisar / identidad por revisar / cargado), banner de
 * identidad (informativo: YA NO bloquea las demás cargas), acciones commit y
 * commit-pending con sus códigos de gate (409 identity_pending por carga,
 * 409 nothing_pending, 409 matches_unresolved), retomar y descartar una carga
 * en curso; cero violaciones axe.
 *
 * Nombres/archivos siempre sintéticos — nunca datos reales de un menor.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from "sonner";
import { mswServer } from "@/test/setup";
import {
  makeHistoricalImportItem,
  makeImportDetail,
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
import { LoadsSection } from "@/components/competitions/imports/LoadsSection";

function renderSection() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <LoadsSection />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LoadsSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mswServer.use(...raceImportsHistoryHandlers, ...raceIdentityHandlers);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("muestra el skeleton de carga", () => {
    renderSection();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Cargando cargues históricos...",
    );
  });

  it("vacío: sin cargues históricos ofrece cargar el primer archivo", async () => {
    mswServer.use(raceImportsHistoryEmptyHandler);
    renderSection();
    expect(
      await screen.findByText("Todavía no hay cargues históricos"),
    ).toBeInTheDocument();
  });

  it("error: falla la carga y ofrece reintentar", async () => {
    mswServer.use(raceImportsHistoryErrorHandler);
    renderSection();
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
    renderSection();

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
    renderSection();

    expect(await screen.findByText("Categorías por revisar")).toBeInTheDocument();
    expect(screen.getByTestId("pending-categories-1")).toHaveTextContent(
      "2 categorías pendientes",
    );
    // Sin pendientes de categoría, el botón de commit directo no aplica.
    expect(screen.queryByTestId("commit-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("commit-pending-1")).toBeInTheDocument();
  });

  it("US3 (a): candidatos pendientes en la cola NO marcan ni bloquean las cargas del tablero", async () => {
    // raceIdentityHandlers default: pending=2 en la cola global. Con el
    // candado por carga, el tablero no puede saber cuáles cargas afecta: la
    // fila sigue «Listo para cargar» y con el botón habilitado; el bloqueo,
    // si aplica, lo decide el servidor al confirmar (409 identity_pending).
    renderSection();
    expect(await screen.findByTestId("identity-banner")).toHaveTextContent(
      "Hay 2 decisiones de identidad por tomar",
    );
    expect(screen.getByText("Listo para cargar")).toBeInTheDocument();
    expect(screen.queryByText("Identidad por revisar")).not.toBeInTheDocument();
    expect(await screen.findByTestId("commit-1")).toBeEnabled();
    expect(
      screen.getByRole("link", { name: "Ver decisiones" }),
    ).toHaveAttribute("href", "/competitions/imports?seccion=identidades");
  });

  it("no muestra el banner de identidad cuando no hay pendientes", async () => {
    mswServer.use(raceIdentityEmptySummaryHandler);
    renderSection();
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
    renderSection();
    expect(await screen.findByText("Cargado")).toBeInTheDocument();
    expect(screen.queryByTestId("commit-1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("commit-pending-1")).not.toBeInTheDocument();
    // Una carga confirmada no se retoma ni se descarta.
    expect(screen.queryByTestId("resume-1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("discard-1")).not.toBeInTheDocument();
  });

  it("confirmar carga: éxito muestra el toast con el conteo de resultados", async () => {
    mswServer.use(raceIdentityEmptySummaryHandler);
    const user = userEvent.setup();
    renderSection();
    const button = await screen.findByTestId("commit-1");
    await user.click(button);
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        "Válida cargada: 42 resultado(s).",
      );
    });
  });

  it("confirmar carga: 409 identity_pending muestra el conteo de ESTA carga, el link a review_path y marca la fila", async () => {
    mswServer.use(
      raceIdentityEmptySummaryHandler,
      raceImportsHistoryCommitIdentityPendingHandler,
    );
    const user = userEvent.setup();
    renderSection();
    const button = await screen.findByTestId("commit-1");
    await user.click(button);

    expect(
      await screen.findByTestId("import-row-error-1"),
    ).toHaveTextContent(
      "Hay 3 decisiones de identidad pendientes para esta carga. Resuélvelas en «Cargas e identidades» y vuelve: tu carga queda guardada.",
    );
    expect(screen.getByTestId("import-row-identity-link-1")).toHaveAttribute(
      "href",
      "/competitions/imports?seccion=identidades&import=1",
    );
    // La fila, y solo ella, pasa a «Identidad por revisar»; conserva la carga.
    expect(screen.getByText("Identidad por revisar")).toBeInTheDocument();
    expect(screen.getByTestId("resume-1")).toBeInTheDocument();
  });

  it("confirmar carga: 409 matches_unresolved enlaza a RETOMAR la carga en el asistente", async () => {
    mswServer.use(
      raceIdentityEmptySummaryHandler,
      raceImportsHistoryCommitMatchesUnresolvedHandler,
    );
    const user = userEvent.setup();
    renderSection();
    const button = await screen.findByTestId("commit-1");
    await user.click(button);

    expect(
      await screen.findByTestId("import-row-error-1"),
    ).toHaveTextContent(
      "Hay 2 corredores del club sin coincidencia resuelta. Complétala en el asistente de importación.",
    );
    // El asistente ahora conserva el archivo ya subido: se retoma por id.
    expect(
      screen.getByTestId("import-row-wizard-link-1"),
    ).toHaveAttribute("href", "/competitions/import?import=1");
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
    renderSection();
    const button = await screen.findByTestId("commit-pending-1");
    await user.click(button);

    expect(
      await screen.findByTestId("import-row-error-1"),
    ).toHaveTextContent(
      "No hay categorías pendientes por cargar en esta válida.",
    );
  });

  it("carga en curso: ofrece «Retomar» hacia el asistente con ?import=<id>", async () => {
    mswServer.use(raceIdentityEmptySummaryHandler);
    renderSection();
    const resume = await screen.findByTestId("resume-1");
    expect(resume).toHaveAttribute("href", "/competitions/import?import=1");
    expect(resume).toHaveTextContent("Retomar");
  });

  it("carga en curso: «Descartar» pide confirmación y llama a POST /discard", async () => {
    mswServer.use(raceIdentityEmptySummaryHandler);
    const discarded: string[] = [];
    mswServer.use(
      http.post("*/api/race-analysis/imports/:id/discard", ({ params }) => {
        discarded.push(String(params.id));
        return HttpResponse.json(
          makeImportDetail({ id: Number(params.id), status: "discarded" }),
        );
      }),
    );
    const user = userEvent.setup();
    renderSection();

    await user.click(await screen.findByTestId("discard-1"));
    const dialog = await screen.findByTestId("discard-import-dialog");
    // Nada se descartó todavía: primero hay que confirmar.
    expect(discarded).toEqual([]);
    expect(within(dialog).getByText("¿Descartar esta carga?")).toBeInTheDocument();

    await user.click(within(dialog).getByTestId("confirm-discard-import"));
    await waitFor(() => expect(discarded).toEqual(["1"]));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("Carga descartada."),
    );
  });

  it("carga en curso: cancelar el diálogo no descarta nada", async () => {
    mswServer.use(raceIdentityEmptySummaryHandler);
    const discarded: string[] = [];
    mswServer.use(
      http.post("*/api/race-analysis/imports/:id/discard", ({ params }) => {
        discarded.push(String(params.id));
        return HttpResponse.json(makeImportDetail({ status: "discarded" }));
      }),
    );
    const user = userEvent.setup();
    renderSection();

    await user.click(await screen.findByTestId("discard-1"));
    const dialog = await screen.findByTestId("discard-import-dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    await waitFor(() =>
      expect(
        screen.queryByTestId("discard-import-dialog"),
      ).not.toBeInTheDocument(),
    );
    expect(discarded).toEqual([]);
  });

  it("sin violaciones de accesibilidad", async () => {
    mswServer.use(raceIdentityEmptySummaryHandler);
    const { container } = renderSection();
    await screen.findByTestId("import-row-1");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones de accesibilidad con el banner de identidad visible", async () => {
    const { container } = renderSection();
    await screen.findByTestId("identity-banner");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
