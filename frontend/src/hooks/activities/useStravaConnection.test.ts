/**
 * Tests de los hooks de conexión Strava (feature 025, T027).
 *
 * Cubre `useStravaConnection` (query), `useConnectStrava` y
 * `useDisconnectStrava` (mutations) contra handlers MSW — sin mockear
 * `@/api/stravaActivities` para ejercitar la capa HTTP real (axios +
 * interceptor de MSW), consistente con `useClubInsightsByRace.test.tsx`.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { createElement, type ReactNode } from "react";

import { mswServer } from "@/test/setup";
import {
  stravaHandlers,
  noneConnectionHandler,
  connectionErrorHandler,
  connectErrorHandler,
  disconnectErrorHandler,
  mockStravaConnection,
} from "@/test/msw/stravaHandlers";
import {
  useConnectStrava,
  useDisconnectStrava,
  useStravaConnection,
} from "./useStravaConnection";

function makeWrapper(queryClient?: QueryClient) {
  const qc =
    queryClient ??
    new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
        mutations: { retry: false },
      },
    });
  return {
    qc,
    Wrapper: function Wrapper({ children }: { children: ReactNode }) {
      return createElement(QueryClientProvider, { client: qc }, children);
    },
  };
}

beforeEach(() => {
  mswServer.use(...stravaHandlers);
});

// ---------------------------------------------------------------------------
// useStravaConnection
// ---------------------------------------------------------------------------

describe("useStravaConnection", () => {
  it("devuelve la conexión activa del handler MSW default", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useStravaConnection(42), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.status).toBe("active");
  });

  it("refleja el estado none cuando el atleta nunca se conectó", async () => {
    mswServer.use(noneConnectionHandler);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useStravaConnection(42), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.status).toBe("none");
    expect(result.current.data?.connected_at).toBeNull();
  });

  it("expone isError cuando el endpoint responde 500", async () => {
    mswServer.use(connectionErrorHandler);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useStravaConnection(42), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("no ejecuta la query cuando athleteId es 0", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useStravaConnection(0), {
      wrapper: Wrapper,
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("no ejecuta la query cuando athleteId es negativo", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useStravaConnection(-1), {
      wrapper: Wrapper,
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("no ejecuta la query cuando athleteId es NaN", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useStravaConnection(NaN), {
      wrapper: Wrapper,
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("respeta el flag enabled=false aunque athleteId sea válido", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useStravaConnection(42, false), {
      wrapper: Wrapper,
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("llama al endpoint con el athleteId correcto", async () => {
    const observed: number[] = [];
    mswServer.use(
      http.get("*/api/athletes/:athleteId/strava/connection", ({ params }) => {
        observed.push(Number(params.athleteId));
        return HttpResponse.json(mockStravaConnection());
      }),
    );
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useStravaConnection(99), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(observed).toEqual([99]);
  });
});

// ---------------------------------------------------------------------------
// useConnectStrava
// ---------------------------------------------------------------------------

describe("useConnectStrava", () => {
  it("devuelve authorize_url tras iniciar el flujo OAuth", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useConnectStrava(42), {
      wrapper: Wrapper,
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.authorize_url).toContain(
      "https://www.strava.com/oauth/authorize",
    );
  });

  it("invalida la query de conexión y de actividades tras éxito", async () => {
    const { Wrapper, qc } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useConnectStrava(42), {
      wrapper: Wrapper,
    });

    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["strava-connection", 42],
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["athlete-activities", 42],
    });
  });

  it("expone isError cuando el backend responde con error", async () => {
    mswServer.use(connectErrorHandler);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useConnectStrava(42), {
      wrapper: Wrapper,
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

// ---------------------------------------------------------------------------
// useDisconnectStrava
// ---------------------------------------------------------------------------

describe("useDisconnectStrava", () => {
  it("completa la mutation en éxito (204 sin body)", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useDisconnectStrava(42), {
      wrapper: Wrapper,
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it("invalida la query de conexión y de actividades tras éxito", async () => {
    const { Wrapper, qc } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useDisconnectStrava(7), {
      wrapper: Wrapper,
    });

    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["strava-connection", 7],
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["athlete-activities", 7],
    });
  });

  it("expone isError cuando el endpoint responde 500", async () => {
    mswServer.use(disconnectErrorHandler);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useDisconnectStrava(42), {
      wrapper: Wrapper,
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
