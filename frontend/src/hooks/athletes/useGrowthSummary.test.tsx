/**
 * Tests de useGrowthSummary (feature 040, US2).
 *
 * Cubre:
 *  - Datos del handler MSW default y forma de la respuesta parseada.
 *  - Query key exacta `["growth-summary", athleteId]` (allowlist de caché
 *    apunta a esta key, T036 no debe cambiarla sin tocar el gate de privacidad).
 *  - Hook deshabilitado cuando athleteId no es válido (<= 0, no finito).
 *  - Variante "sin registros" (`never`).
 *  - Estado de error cuando el endpoint responde 500.
 *
 * Fixture ficticia — sin datos reales de atletas.
 */
import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";

import { mswServer } from "@/test/setup";
import { useGrowthSummary } from "@/hooks/athletes/useGrowthSummary";
import {
  makeGrowthSummary,
  makeNeverGrowthSummary,
} from "@/test/msw/growthSummaryHandlers";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useGrowthSummary", () => {
  it("devuelve el resumen del handler MSW default", async () => {
    const { result } = renderHook(() => useGrowthSummary(2), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.athlete_id).toBe(2);
    expect(result.current.data?.records_count).toBe(3);
    expect(result.current.data?.stage).toBe("Post-PHV");
    expect(result.current.data?.velocity?.cm_per_year).toBe(3.7);
    expect(result.current.data?.latest?.height?.band).toBe("riesgo_retraso_talla");
  });

  it('cachea bajo la key canónica ["growth-summary", athleteId]', async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useGrowthSummary(7), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const cached = qc.getQueryData(["growth-summary", 7]);
    expect(cached).toBeDefined();
    expect(qc.getQueryData(["growth-summary", ""])).toBeUndefined();
  });

  it("no dispara la query cuando athleteId es 0", async () => {
    const { result } = renderHook(() => useGrowthSummary(0), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("no dispara la query cuando athleteId es negativo", async () => {
    const { result } = renderHook(() => useGrowthSummary(-3), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("no dispara la query cuando athleteId no es finito", async () => {
    const { result } = renderHook(() => useGrowthSummary(Infinity), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it('no dispara la query cuando "enabled" es false', async () => {
    const { result } = renderHook(() => useGrowthSummary(2, false), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it('variante "sin registros" — status never, latest null', async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/growth-summary", () =>
        HttpResponse.json(makeNeverGrowthSummary({ athlete_id: 9 })),
      ),
    );

    const { result } = renderHook(() => useGrowthSummary(9), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.records_count).toBe(0);
    expect(result.current.data?.measurement.status).toBe("never");
    expect(result.current.data?.velocity).toBeNull();
    expect(result.current.data?.latest).toBeNull();
  });

  it("expone isError cuando el endpoint responde 500", async () => {
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/growth-summary",
        () => new HttpResponse(null, { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useGrowthSummary(2), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true), {
      timeout: 3000,
    });
  });

  it("descarta claves no declaradas del payload (defensa en profundidad Zod)", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/growth-summary", () =>
        HttpResponse.json({
          ...makeGrowthSummary({ athlete_id: 5 }),
          first_name: "no-debería-llegar",
        }),
      ),
    );

    const { result } = renderHook(() => useGrowthSummary(5), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).not.toHaveProperty("first_name");
  });
});
