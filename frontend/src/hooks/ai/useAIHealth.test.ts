import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/ai", () => ({
  getAIHealth: vi.fn(),
}));

import * as aiApi from "@/api/ai";

import { useAIHealth } from "./useAIHealth";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

const mockHealth = {
  enabled: true,
  provider: "anthropic",
  model: "claude-sonnet-4-5",
};

describe("useAIHealth", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("retorna el estado del proveedor cuando la API responde", async () => {
    vi.mocked(aiApi.getAIHealth).mockResolvedValue(mockHealth);
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAIHealth(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockHealth);
  });

  it("respeta enabled: false para no disparar el request", async () => {
    vi.mocked(aiApi.getAIHealth).mockResolvedValue(mockHealth);
    const wrapper = createWrapper();
    renderHook(() => useAIHealth({ enabled: false }), { wrapper });

    await new Promise((r) => setTimeout(r, 50));
    expect(aiApi.getAIHealth).not.toHaveBeenCalled();
  });

  it("propaga el error cuando la API falla (admin verá el error)", async () => {
    vi.mocked(aiApi.getAIHealth).mockRejectedValue(new Error("403"));
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAIHealth(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
