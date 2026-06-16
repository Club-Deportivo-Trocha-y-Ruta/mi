/**
 * Tests del hook useImportPrefill (feature 015).
 *
 * Cubre:
 *  - ready (copa): mapea evento+serie → values, series_kind derivado, valida_num visible (T006/US1)
 *  - ready (campeonato): valida_num = null (FR-008)
 *  - blocked: series_id irresoluble → status blocked + editMetadataHref (T013/US2, FR-009)
 *  - error: evento 404 → status error
 *  - standalone: raceEventId null → hook devuelve null (FR-007)
 *
 * Privacidad: los fixtures solo contienen metadata de competencia (FR-013).
 */
import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

// useRaceEvent gatea en accessToken — lo proveemos vía mock del store.
vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

import { mswServer } from "@/test/setup";
import { raceSeriesHandlers } from "@/test/msw/raceSeriesHandlers";
import {
  prefillCupEventHandler,
  prefillChampionshipEventHandler,
  prefillUnresolvableSeriesEventHandler,
  raceEventNotFoundHandler,
} from "@/test/msw/raceEventsHandlers";
import { useImportPrefill } from "@/hooks/race/useImportPrefill";

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

describe("useImportPrefill", () => {
  it("ready (copa): mapea evento+serie y deriva series_kind con válida visible", async () => {
    mswServer.use(...raceSeriesHandlers, prefillCupEventHandler);

    const { result } = renderHook(() => useImportPrefill(2), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current?.status).toBe("ready"));

    const values = result.current?.values;
    expect(result.current?.raceEventId).toBe(2);
    expect(values?.series_kind).toBe("cup");
    expect(values?.series_name).toBe("Copa Valle de Ciclomontañismo");
    expect(values?.season).toBe(2026);
    expect(values?.valida_num).toBe(4);
    expect(values?.event_name).toBe("Copa Valle XCO — Válida IV");
    expect(values?.event_date).toBe("2026-05-17");
    expect(values?.location).toBe("Cali");
    // No expone editMetadataHref en ready.
    expect(result.current?.editMetadataHref).toBeUndefined();
  });

  it("ready (campeonato): valida_num = null (FR-008)", async () => {
    mswServer.use(...raceSeriesHandlers, prefillChampionshipEventHandler);

    const { result } = renderHook(() => useImportPrefill(15), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current?.status).toBe("ready"));

    expect(result.current?.values?.series_kind).toBe("championship");
    expect(result.current?.values?.valida_num).toBeNull();
  });

  it("blocked: series_id irresoluble → blocked + editMetadataHref (FR-009)", async () => {
    mswServer.use(...raceSeriesHandlers, prefillUnresolvableSeriesEventHandler);

    const { result } = renderHook(() => useImportPrefill(777), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current?.status).toBe("blocked"));

    expect(result.current?.values).toBeUndefined();
    expect(result.current?.editMetadataHref).toBe("/competitions/777/edit");
  });

  it("error: evento 404 → status error", async () => {
    mswServer.use(...raceSeriesHandlers, raceEventNotFoundHandler);

    const { result } = renderHook(() => useImportPrefill(404), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current?.status).toBe("error"));
    expect(result.current?.values).toBeUndefined();
  });

  it("standalone: raceEventId null → devuelve null (FR-007)", () => {
    const { result } = renderHook(() => useImportPrefill(null), {
      wrapper: wrapper(),
    });
    expect(result.current).toBeNull();
  });
});
