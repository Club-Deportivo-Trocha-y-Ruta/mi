import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
  registerAuthHandlers: vi.fn(),
}));

import * as apiClientModule from "@/api/client";
import { deleteParentUser } from "./parents";
import { useDeleteParentUser } from "@/hooks/parents/useDeleteParentUser";

const { apiClient: mockApi } = apiClientModule as unknown as {
  apiClient: { delete: ReturnType<typeof vi.fn> };
};

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

// ---------------------------------------------------------------------------
// deleteParentUser — feature 041: reason_code obligatorio (auditoría)
// ---------------------------------------------------------------------------

describe("deleteParentUser", () => {
  it("envía reason_code como query param al DELETE /api/users/{id}", async () => {
    mockApi.delete.mockResolvedValueOnce({});

    await deleteParentUser(7, "parent_family_request");

    expect(mockApi.delete).toHaveBeenCalledWith("/api/users/7", {
      params: { reason_code: "parent_family_request" },
    });
  });
});

describe("useDeleteParentUser", () => {
  it("llama a deleteParentUser con id y reasonCode", async () => {
    mockApi.delete.mockResolvedValueOnce({});
    const { result } = renderHook(() => useDeleteParentUser(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({ id: 9, reasonCode: "parent_duplicate_account" });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApi.delete).toHaveBeenCalledWith("/api/users/9", {
      params: { reason_code: "parent_duplicate_account" },
    });
  });
});
