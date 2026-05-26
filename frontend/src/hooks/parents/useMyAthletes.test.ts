import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

import { useMyAthletes } from "./useMyAthletes";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";
import type { MeResponse } from "@/types/auth.types";

// ---------------------------------------------------------------------------
// Mocks — la query API se mockea para verificar el lado `enabled` (Bug #2).
// ---------------------------------------------------------------------------

vi.mock("@/api/parents", () => ({
  getMyAthletes: vi.fn(),
}));

import { getMyAthletes } from "@/api/parents";

function makeUser(role: UserRole): MeResponse {
  return {
    id: 42,
    email: "test@trochayruta.com",
    role,
    is_active: true,
  } as unknown as MeResponse;
}

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

function setAuth(role: UserRole | null, token: string | null = "tok") {
  useAuthStore.setState({
    accessToken: token,
    refreshToken: token,
    user: role ? makeUser(role) : null,
    isAuthenticated: token !== null,
    isLoading: false,
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useMyAthletes — guard de rol (Bug #2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      accessToken: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
  });

  it("NO dispara request cuando el usuario es coach", async () => {
    setAuth(UserRole.coach);
    renderHook(() => useMyAthletes(), { wrapper: wrapper() });
    // Esperamos a que React-Query estabilice el estado.
    await new Promise((r) => setTimeout(r, 30));
    expect(getMyAthletes).not.toHaveBeenCalled();
  });

  it("NO dispara request cuando el usuario es admin", async () => {
    setAuth(UserRole.admin);
    renderHook(() => useMyAthletes(), { wrapper: wrapper() });
    await new Promise((r) => setTimeout(r, 30));
    expect(getMyAthletes).not.toHaveBeenCalled();
  });

  it("NO dispara request cuando no hay token (anónimo)", async () => {
    setAuth(null, null);
    renderHook(() => useMyAthletes(), { wrapper: wrapper() });
    await new Promise((r) => setTimeout(r, 30));
    expect(getMyAthletes).not.toHaveBeenCalled();
  });

  it("dispara request cuando el usuario es parent autenticado", async () => {
    vi.mocked(getMyAthletes).mockResolvedValue([]);
    setAuth(UserRole.parent);
    const { result } = renderHook(() => useMyAthletes(), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(getMyAthletes).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
  });
});
