/**
 * ResumeStatusNotice — aviso legacy (amendment 2026-09-26, `restage_required`,
 * `contracts/ui-review-only.md` §"Legacy imports", T158).
 *
 * Cubre:
 *  - `restage_required` true (o un 409 `restage_required` en la revisión)
 *    muestra el aviso legacy con solo *Descartar*.
 *  - Una fila del tablero (`LoadsSection`) con `restage_required` muestra el
 *    badge «Preparar de nuevo».
 *  - jest-axe: cero violaciones en ambos.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

import { mswServer } from "@/test/setup";
import {
  makeImportDetail,
  makeImportListResponse,
  makeHistoricalImportItem,
} from "@/test/msw/raceImportsHistoryHandlers";
import { LoadsSection } from "@/components/competitions/imports/LoadsSection";
import { ImportWizard } from "@/components/competitions/import/ImportWizard";

const BASE = "*/api/race-analysis/imports";

function renderWizardAt(importId: string | number = "9") {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/competitions/import?import=${importId}`]}>
        <Routes>
          <Route path="/competitions/import" element={<ImportWizard />} />
          <Route
            path="/competitions/imports"
            element={<div data-testid="board-stub">Tablero</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderLoadsSection() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/competitions/imports"]}>
        <LoadsSection />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ResumeStatusNotice — aviso legacy (restage_required)", () => {
  it("detail.restage_required=true: muestra el aviso legacy y solo Descartar", async () => {
    mswServer.use(
      http.get(`${BASE}/9`, () =>
        HttpResponse.json(makeImportDetail({ id: 9, restage_required: true })),
      ),
    );
    renderWizardAt();

    const notice = await screen.findByTestId("resume-status-notice");
    expect(notice).toHaveTextContent(
      "Esta carga se preparó con el método anterior y ya no se puede revisar. Descártala y pide que se prepare de nuevo.",
    );
    expect(screen.queryByTestId("resume-start-new")).not.toBeInTheDocument();
    expect(screen.queryByTestId("resume-view-results")).not.toBeInTheDocument();
    expect(screen.getByTestId("resume-legacy-discard")).toBeInTheDocument();
  });

  it("descartar desde el aviso legacy navega al tablero", async () => {
    mswServer.use(
      http.get(`${BASE}/9`, () =>
        HttpResponse.json(makeImportDetail({ id: 9, restage_required: true })),
      ),
      http.post(`${BASE}/9/discard`, () =>
        HttpResponse.json(
          makeImportDetail({ id: 9, status: "discarded", restage_required: true }),
        ),
      ),
    );
    const user = userEvent.setup();
    renderWizardAt();

    await user.click(await screen.findByTestId("resume-legacy-discard"));
    const dialog = await screen.findByTestId("discard-import-dialog");
    await user.click(screen.getByTestId("confirm-discard-import"));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(await screen.findByTestId("board-stub")).toBeInTheDocument();
  });

  it("board row con restage_required: badge «Preparar de nuevo» y solo Descartar", async () => {
    mswServer.use(
      http.get(`${BASE}/`, () =>
        HttpResponse.json(
          makeImportListResponse({
            items: [
              makeHistoricalImportItem({
                id: "9",
                status: "pending",
                restage_required: true,
              }),
            ],
            total: 1,
          }),
        ),
      ),
      http.get("*/api/race-identity/summary", () =>
        HttpResponse.json({ pending: 0 }),
      ),
    );
    renderLoadsSection();

    await waitFor(() => expect(screen.getByTestId("import-row-9")).toBeInTheDocument());
    const row = screen.getByTestId("import-row-9");
    expect(row).toHaveTextContent("Preparar de nuevo");
    expect(screen.queryByTestId("resume-9")).not.toBeInTheDocument();
    expect(screen.queryByTestId("commit-9")).not.toBeInTheDocument();
    expect(screen.getByTestId("discard-9")).toBeInTheDocument();
  });

  it("jest-axe: cero violaciones en el aviso legacy del wizard", async () => {
    mswServer.use(
      http.get(`${BASE}/9`, () =>
        HttpResponse.json(makeImportDetail({ id: 9, restage_required: true })),
      ),
    );
    const { container } = renderWizardAt();
    await screen.findByTestId("resume-status-notice");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("jest-axe: cero violaciones en el tablero con una fila legacy", async () => {
    mswServer.use(
      http.get(`${BASE}/`, () =>
        HttpResponse.json(
          makeImportListResponse({
            items: [
              makeHistoricalImportItem({
                id: "9",
                status: "pending",
                restage_required: true,
              }),
            ],
            total: 1,
          }),
        ),
      ),
      http.get("*/api/race-identity/summary", () =>
        HttpResponse.json({ pending: 0 }),
      ),
    );
    const { container } = renderLoadsSection();
    await waitFor(() => expect(screen.getByTestId("import-row-9")).toBeInTheDocument());
    expect(await axe(container)).toHaveNoViolations();
  });
});
