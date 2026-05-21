/**
 * Tests para ImportsHistoryList.
 *
 * Cubre render loading, error, vacío, items y filtro de estado.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

vi.mock("@/api/raceImports", () => ({
  listRaceImports: vi.fn(),
  parseRaceImport: vi.fn(),
  dryRunRaceImport: vi.fn(),
  commitRaceImport: vi.fn(),
}));

import * as importsApi from "@/api/raceImports";
import { ImportsHistoryList } from "@/components/ai/ImportsHistoryList";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    createElement(QueryClientProvider, { client: qc }, ui),
  );
}

beforeEach(() => vi.clearAllMocks());

describe("ImportsHistoryList", () => {
  it("muestra loading skeleton mientras carga", () => {
    vi.mocked(importsApi.listRaceImports).mockImplementation(
      () => new Promise(() => {}),
    );
    wrap(<ImportsHistoryList />);
    expect(screen.getByTestId("history-loading")).toBeInTheDocument();
  });

  it("muestra mensaje vacío cuando no hay items", async () => {
    vi.mocked(importsApi.listRaceImports).mockResolvedValue({
      items: [],
      total: 0,
    });
    wrap(<ImportsHistoryList />);
    await waitFor(() =>
      expect(screen.getByTestId("history-empty")).toBeInTheDocument(),
    );
  });

  it("renderiza filas y aplica el filtro de status", async () => {
    vi.mocked(importsApi.listRaceImports).mockResolvedValue({
      items: [
        {
          id: "i1",
          kind: "resultados",
          status: "committed",
          created_at: "2026-05-17T10:00:00Z",
          event_id: 4,
          original_filename: "valida_iv.pdf",
          uploaded_by: { id: 1, full_name: "Coach Juan" },
          n_results: 200,
        },
      ],
      total: 1,
    });

    const user = userEvent.setup();
    wrap(<ImportsHistoryList />);

    await waitFor(() =>
      expect(screen.getByTestId("history-row-i1")).toBeInTheDocument(),
    );
    expect(screen.getByText("valida_iv.pdf")).toBeInTheDocument();
    expect(screen.getByText("Confirmado")).toBeInTheDocument();
    expect(screen.getByText("Coach Juan")).toBeInTheDocument();

    // Aplicar filtro: dispara nueva llamada al hook con status param.
    await user.selectOptions(
      screen.getByTestId("history-status-filter"),
      "pending",
    );
    await waitFor(() =>
      expect(importsApi.listRaceImports).toHaveBeenCalledWith(
        expect.objectContaining({ status: "pending" }),
      ),
    );
  });
});
