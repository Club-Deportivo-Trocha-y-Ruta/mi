/**
 * Tests para hooks de race-imports.
 *
 * Verifica que cada hook llama el endpoint correcto y propaga errores.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor, act } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/raceImports", () => ({
  parseRaceImport: vi.fn(),
  dryRunRaceImport: vi.fn(),
  commitRaceImport: vi.fn(),
  listRaceImports: vi.fn(),
}));

import * as importsApi from "@/api/raceImports";

import {
  useImportCommit,
  useImportDryRun,
  useImportParse,
  useImportsHistory,
} from "./useRaceImports";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("useImportParse", () => {
  beforeEach(() => vi.clearAllMocks());

  it("llama parseRaceImport con campos y archivos correctos", async () => {
    vi.mocked(importsApi.parseRaceImport).mockResolvedValue({
      parse_id: "p1",
      sha256: "abc",
      header: {
        series_name: "Copa Valle",
        season: 2026,
        valida_num: 4,
        event_name: "IV Cali",
      },
      n_rows_resultados: 200,
      n_rows_general: 0,
      warnings: [],
    });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useImportParse(), { wrapper });

    const pdf = new File(["%PDF-1.4"], "ok.pdf", { type: "application/pdf" });
    await act(async () => {
      await result.current.mutateAsync({
        fields: {
          series_name: "Copa Valle",
          season: 2026,
          valida_num: 4,
          event_name: "IV Cali",
          event_date: "2026-05-17",
          location: "Cali",
        },
        files: { resultadosPdf: pdf },
      });
    });

    expect(importsApi.parseRaceImport).toHaveBeenCalledTimes(1);
    const args = vi.mocked(importsApi.parseRaceImport).mock.calls[0];
    expect(args[0].season).toBe(2026);
    expect(args[1].resultadosPdf).toBe(pdf);
  });

  it("propaga el error si parse falla", async () => {
    vi.mocked(importsApi.parseRaceImport).mockRejectedValue(
      new Error("boom"),
    );
    const wrapper = createWrapper();
    const { result } = renderHook(() => useImportParse(), { wrapper });

    await act(async () => {
      await expect(
        result.current.mutateAsync({
          fields: {
            series_name: "x",
            season: 2026,
            valida_num: 1,
            event_name: "x",
            event_date: "2026-01-01",
            location: "x",
          },
          files: {
            resultadosPdf: new File([""], "x.pdf"),
          },
        }),
      ).rejects.toThrow("boom");
    });
  });
});

describe("useImportDryRun", () => {
  beforeEach(() => vi.clearAllMocks());

  it("llama dryRunRaceImport con parseId", async () => {
    vi.mocked(importsApi.dryRunRaceImport).mockResolvedValue({
      parse_id: "p1",
      matches: [],
      counts: { confirmed: 0, ambiguous: 0, no_match: 0, total: 0 },
      warnings: [],
    });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useImportDryRun(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ parseId: "p1" });
    });

    expect(importsApi.dryRunRaceImport).toHaveBeenCalledWith("p1");
  });
});

describe("useImportCommit", () => {
  beforeEach(() => vi.clearAllMocks());

  it("llama commitRaceImport con resolved_matches", async () => {
    vi.mocked(importsApi.commitRaceImport).mockResolvedValue({
      parse_id: "p1",
      race_event_id: 4,
      n_results_inserted: 200,
      n_competitors_created: 198,
      n_competitors_linked: 3,
    });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useImportCommit(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        parseId: "p1",
        body: {
          resolved_matches: [
            { competitor_normalized_name: "juan perez", athlete_id: 7 },
          ],
        },
      });
    });

    expect(importsApi.commitRaceImport).toHaveBeenCalledWith("p1", {
      resolved_matches: [
        { competitor_normalized_name: "juan perez", athlete_id: 7 },
      ],
    });
  });
});

describe("useImportsHistory", () => {
  beforeEach(() => vi.clearAllMocks());

  it("llama listRaceImports con params y devuelve items", async () => {
    vi.mocked(importsApi.listRaceImports).mockResolvedValue({
      items: [
        {
          id: "1",
          kind: "resultados",
          status: "committed",
          created_at: "2026-05-17T10:00:00Z",
          event_id: 4,
          original_filename: "valida_iv.pdf",
          uploaded_by: { id: 1, full_name: "Coach" },
          n_results: 200,
        },
      ],
      total: 1,
    });

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useImportsHistory({ limit: 10 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(importsApi.listRaceImports).toHaveBeenCalledWith({ limit: 10 });
    expect(result.current.data?.items).toHaveLength(1);
  });
});
