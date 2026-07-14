import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/ai", () => ({
  getAIStatus: vi.fn(),
}));

import * as aiApi from "@/api/ai";

import { useAIStatus } from "./useAIStatus";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

const mockStatus = {
  budget_status: "ok" as const,
  budget_remaining_pct: 62,
  concurrency_available: true,
  est_wait_seconds: 24,
};

describe("useAIStatus", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("retorna el estado de presupuesto/concurrencia cuando la API responde", async () => {
    vi.mocked(aiApi.getAIStatus).mockResolvedValue(mockStatus);
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAIStatus(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockStatus);
  });

  it("respeta enabled: false para no disparar el request", async () => {
    vi.mocked(aiApi.getAIStatus).mockResolvedValue(mockStatus);
    const wrapper = createWrapper();
    renderHook(() => useAIStatus({ enabled: false }), { wrapper });

    await new Promise((r) => setTimeout(r, 50));
    expect(aiApi.getAIStatus).not.toHaveBeenCalled();
  });

  it("degrada con gracia cuando el fetch falla: isError sin data, sin bloquear al consumidor", async () => {
    vi.mocked(aiApi.getAIStatus).mockRejectedValue(new Error("network error"));
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAIStatus(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    // `data` permanece undefined — un consumidor que hace
    // `data?.budget_status === "exhausted"` nunca deshabilita el botón
    // por un fallo de red, solo cuando el backend responde de verdad.
    expect(result.current.data).toBeUndefined();
  });
});
