import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { UserRole } from "@/types/enums";
import type { MeResponse, TokenResponse } from "@/types/auth.types";

// ---------------------------------------------------------------------------
// Mocks declarados ANTES de importar el store porque el store ejecuta código
// de módulo (registerAuthHandlers) al importarse.
// ---------------------------------------------------------------------------

vi.mock("@/api/auth", () => ({
  login: vi.fn(),
  refreshToken: vi.fn(),
  getMe: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: {},
  registerAuthHandlers: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Importaciones después de los mocks
// ---------------------------------------------------------------------------

import { useAuthStore } from "./auth.store";
import * as authApi from "@/api/auth";
import * as apiClient from "@/api/client";
import {
  setQueryClient,
  __resetQueryClientHandleForTests,
} from "@/lib/queryClientHandle";

// ---------------------------------------------------------------------------
// Captura de handlers de registerAuthHandlers
// El store llama a registerAuthHandlers({...}) al cargarse el módulo.
// Capturamos los handlers AQUÍ (antes de cualquier beforeEach/clearAllMocks)
// para poder invocar los closures onUnauthorized y getAccessToken en tests.
// ---------------------------------------------------------------------------

type AuthHandlers = {
  getAccessToken: () => string | null;
  onUnauthorized: () => Promise<void>;
};

// Se captura inmediatamente después de la importación del store.
// En este punto el mock ya tiene la llamada registrada.
const _capturedHandlers: AuthHandlers | null =
  (vi.mocked(apiClient.registerAuthHandlers).mock.calls[0]?.[0] as AuthHandlers) ?? null;

// ---------------------------------------------------------------------------
// Datos de prueba
// ---------------------------------------------------------------------------

const mockTokens: TokenResponse = {
  access_token: "test-access-token",
  refresh_token: "test-refresh-token",
  token_type: "bearer",
};

const mockUser: MeResponse = {
  id: 1,
  email: "entrenador@trochyruta.com",
  first_name: "Juan",
  last_name: "García",
  phone: null,
  role: UserRole.coach,
  is_active: true,
  can_login: true,
  club_ids: [1],
  created_at: "2026-01-01T00:00:00Z",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resetStore() {
  useAuthStore.setState({
    accessToken: null,
    refreshToken: null,
    user: null,
    isAuthenticated: false,
    isLoading: false,
  });
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------

describe("useAuthStore", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
    // Asegurar que entre tests no quede un QueryClient registrado
    // del bloque "logout — purga del cache" (sino, logout() de tests
    // previos limpiaría un cache que el siguiente test no espera).
    __resetQueryClientHandleForTests();
    // Silenciar sessionStorage en jsdom
    Object.defineProperty(window, "sessionStorage", {
      value: {
        getItem: vi.fn(() => null),
        setItem: vi.fn(),
        removeItem: vi.fn(),
        clear: vi.fn(),
      },
      writable: true,
    });
  });

  afterEach(() => {
    resetStore();
  });

  // -------------------------------------------------------------------------
  // Estado inicial
  // -------------------------------------------------------------------------
  describe("estado inicial", () => {
    it("debería tener isAuthenticated = false por defecto", () => {
      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(false);
    });

    it("debería tener accessToken = null por defecto", () => {
      expect(useAuthStore.getState().accessToken).toBeNull();
    });

    it("debería tener refreshToken = null por defecto", () => {
      expect(useAuthStore.getState().refreshToken).toBeNull();
    });

    it("debería tener user = null por defecto", () => {
      expect(useAuthStore.getState().user).toBeNull();
    });

    it("debería tener isLoading = false por defecto", () => {
      expect(useAuthStore.getState().isLoading).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // login exitoso
  // -------------------------------------------------------------------------
  describe("cuando el login es exitoso", () => {
    beforeEach(() => {
      vi.mocked(authApi.login).mockResolvedValue(mockTokens);
      vi.mocked(authApi.getMe).mockResolvedValue(mockUser);
    });

    it("debería guardar los tokens después del login", async () => {
      await useAuthStore.getState().login("entrenador@trochyruta.com", "Coach2026!");
      const state = useAuthStore.getState();
      expect(state.accessToken).toBe(mockTokens.access_token);
      expect(state.refreshToken).toBe(mockTokens.refresh_token);
    });

    it("debería marcar isAuthenticated = true después del login", async () => {
      await useAuthStore.getState().login("entrenador@trochyruta.com", "Coach2026!");
      expect(useAuthStore.getState().isAuthenticated).toBe(true);
    });

    it("debería cargar el usuario (fetchMe) después del login", async () => {
      await useAuthStore.getState().login("entrenador@trochyruta.com", "Coach2026!");
      expect(useAuthStore.getState().user).toEqual(mockUser);
    });

    it("debería resetear isLoading = false al finalizar", async () => {
      await useAuthStore.getState().login("entrenador@trochyruta.com", "Coach2026!");
      expect(useAuthStore.getState().isLoading).toBe(false);
    });

    it("debería llamar a la API de login con las credenciales correctas", async () => {
      await useAuthStore.getState().login("entrenador@trochyruta.com", "Coach2026!");
      expect(authApi.login).toHaveBeenCalledWith({
        email: "entrenador@trochyruta.com",
        password: "Coach2026!",
      });
    });
  });

  // -------------------------------------------------------------------------
  // login fallido
  // -------------------------------------------------------------------------
  describe("cuando el login falla", () => {
    beforeEach(() => {
      vi.mocked(authApi.login).mockRejectedValue(new Error("Credenciales inválidas"));
    });

    it("debería propagar el error cuando el login falla", async () => {
      await expect(
        useAuthStore.getState().login("bad@mail.com", "wrong")
      ).rejects.toThrow("Credenciales inválidas");
    });

    it("debería resetear isLoading = false aunque falle el login", async () => {
      try {
        await useAuthStore.getState().login("bad@mail.com", "wrong");
      } catch {
        // esperado
      }
      expect(useAuthStore.getState().isLoading).toBe(false);
    });

    it("debería mantener isAuthenticated = false después de un login fallido", async () => {
      try {
        await useAuthStore.getState().login("bad@mail.com", "wrong");
      } catch {
        // esperado
      }
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
    });

    it("debería mantener accessToken = null después de un login fallido", async () => {
      try {
        await useAuthStore.getState().login("bad@mail.com", "wrong");
      } catch {
        // esperado
      }
      expect(useAuthStore.getState().accessToken).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // logout
  // -------------------------------------------------------------------------
  describe("cuando se hace logout", () => {
    beforeEach(() => {
      // Simular sesión activa
      useAuthStore.setState({
        accessToken: "token",
        refreshToken: "refresh",
        user: mockUser,
        isAuthenticated: true,
        isLoading: false,
      });
    });

    it("debería limpiar accessToken al hacer logout", () => {
      useAuthStore.getState().logout();
      expect(useAuthStore.getState().accessToken).toBeNull();
    });

    it("debería limpiar refreshToken al hacer logout", () => {
      useAuthStore.getState().logout();
      expect(useAuthStore.getState().refreshToken).toBeNull();
    });

    it("debería limpiar user al hacer logout", () => {
      useAuthStore.getState().logout();
      expect(useAuthStore.getState().user).toBeNull();
    });

    it("debería marcar isAuthenticated = false al hacer logout", () => {
      useAuthStore.getState().logout();
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
    });

    it("debería resetear isLoading = false al hacer logout", () => {
      useAuthStore.setState({ isLoading: true });
      useAuthStore.getState().logout();
      expect(useAuthStore.getState().isLoading).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // refreshSession exitoso
  // -------------------------------------------------------------------------
  describe("cuando refreshSession tiene éxito", () => {
    beforeEach(() => {
      useAuthStore.setState({
        refreshToken: "old-refresh-token",
        user: mockUser,
        isAuthenticated: true,
        accessToken: null,
        isLoading: false,
      });
      vi.mocked(authApi.refreshToken).mockResolvedValue({
        access_token: "new-access-token",
        refresh_token: "new-refresh-token",
        token_type: "bearer",
      });
    });

    it("debería actualizar los tokens después de refresh", async () => {
      await useAuthStore.getState().refreshSession();
      const state = useAuthStore.getState();
      expect(state.accessToken).toBe("new-access-token");
      expect(state.refreshToken).toBe("new-refresh-token");
    });

    it("debería mantener isAuthenticated = true después del refresh", async () => {
      await useAuthStore.getState().refreshSession();
      expect(useAuthStore.getState().isAuthenticated).toBe(true);
    });

    it("debería resetear isLoading = false al finalizar el refresh", async () => {
      await useAuthStore.getState().refreshSession();
      expect(useAuthStore.getState().isLoading).toBe(false);
    });

    it("debería NO llamar fetchMe si ya hay un usuario cargado", async () => {
      await useAuthStore.getState().refreshSession();
      expect(authApi.getMe).not.toHaveBeenCalled();
    });

    it("debería llamar fetchMe si no hay usuario cargado", async () => {
      useAuthStore.setState({ user: null });
      vi.mocked(authApi.getMe).mockResolvedValue(mockUser);
      await useAuthStore.getState().refreshSession();
      expect(authApi.getMe).toHaveBeenCalledOnce();
    });
  });

  // -------------------------------------------------------------------------
  // refreshSession sin token
  // -------------------------------------------------------------------------
  describe("cuando refreshSession se llama sin refreshToken", () => {
    it("debería hacer logout y lanzar error si no hay refreshToken", async () => {
      useAuthStore.setState({ refreshToken: null });
      await expect(useAuthStore.getState().refreshSession()).rejects.toThrow(
        "No hay refresh token"
      );
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // refreshSession fallido
  // -------------------------------------------------------------------------
  describe("cuando refreshSession falla en la API", () => {
    beforeEach(() => {
      useAuthStore.setState({
        refreshToken: "expired-token",
        user: mockUser,
        isAuthenticated: true,
        accessToken: "old-token",
        isLoading: false,
      });
      vi.mocked(authApi.refreshToken).mockRejectedValue(new Error("Token expirado"));
    });

    it("debería hacer logout cuando el refresh falla", async () => {
      try {
        await useAuthStore.getState().refreshSession();
      } catch {
        // esperado
      }
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
      expect(useAuthStore.getState().user).toBeNull();
    });

    it("debería propagar el error cuando el refresh falla", async () => {
      await expect(useAuthStore.getState().refreshSession()).rejects.toThrow("Token expirado");
    });

    it("debería resetear isLoading = false aunque falle el refresh", async () => {
      try {
        await useAuthStore.getState().refreshSession();
      } catch {
        // esperado
      }
      expect(useAuthStore.getState().isLoading).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // registerAuthHandlers — getAccessToken y onUnauthorized (líneas 97-104)
  // _capturedHandlers captura los argumentos del mock antes de clearAllMocks().
  // -------------------------------------------------------------------------
  describe("registerAuthHandlers callbacks", () => {
    it("debería haber registrado los handlers al cargar el módulo", () => {
      expect(_capturedHandlers).not.toBeNull();
    });

    it("getAccessToken debería retornar el accessToken actual del store", () => {
      expect(_capturedHandlers).not.toBeNull();
      useAuthStore.setState({ accessToken: "handler-token" });
      expect(_capturedHandlers!.getAccessToken()).toBe("handler-token");
    });

    it("getAccessToken debería retornar null cuando el store no tiene token", () => {
      expect(_capturedHandlers).not.toBeNull();
      useAuthStore.setState({ accessToken: null });
      expect(_capturedHandlers!.getAccessToken()).toBeNull();
    });

    it("onUnauthorized debería llamar refreshSession exitosamente cuando hay refreshToken", async () => {
      expect(_capturedHandlers).not.toBeNull();
      useAuthStore.setState({
        refreshToken: "valid-refresh",
        accessToken: null,
        isAuthenticated: true,
        user: mockUser,
        isLoading: false,
      });
      vi.mocked(authApi.refreshToken).mockResolvedValue({
        access_token: "refreshed-access",
        refresh_token: "refreshed-refresh",
        token_type: "bearer",
      });
      vi.mocked(authApi.getMe).mockResolvedValue(mockUser);

      await _capturedHandlers!.onUnauthorized();

      expect(useAuthStore.getState().accessToken).toBe("refreshed-access");
      expect(useAuthStore.getState().isAuthenticated).toBe(true);
    });

    it("onUnauthorized debería hacer logout y redirigir a /login cuando refreshSession falla", async () => {
      expect(_capturedHandlers).not.toBeNull();
      useAuthStore.setState({
        refreshToken: "expired-refresh",
        isAuthenticated: true,
        user: mockUser,
        accessToken: "old",
        isLoading: false,
      });
      vi.mocked(authApi.refreshToken).mockRejectedValue(new Error("Token expirado"));

      const originalLocation = window.location;
      const assignMock = vi.fn();
      Object.defineProperty(window, "location", {
        value: { ...originalLocation, assign: assignMock },
        writable: true,
      });

      await _capturedHandlers!.onUnauthorized();

      expect(useAuthStore.getState().isAuthenticated).toBe(false);
      expect(useAuthStore.getState().user).toBeNull();
      expect(assignMock).toHaveBeenCalledWith("/login");

      Object.defineProperty(window, "location", {
        value: originalLocation,
        writable: true,
      });
    });
  });

  // -------------------------------------------------------------------------
  // logout — purga del cache de TanStack Query (Wave 2 — R1 privacy)
  //
  // En máquinas/tablets compartidas (uso típico en familias), si el padre A
  // cierra sesión y el padre B entra, el cache de React Query sobrevive al
  // logout. Sin esta purga, B podría ver datos sensibles de los hijos de A
  // (atletas menores → Ley 1581 Colombia).
  // -------------------------------------------------------------------------
  describe("logout — purga el cache de TanStack Query (privacy R1)", () => {
    afterEach(() => {
      __resetQueryClientHandleForTests();
    });

    it("logout() invoca queryClient.clear() y deja el cache vacío", () => {
      const qc = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      setQueryClient(qc);

      // Sembramos cache con datos sensibles del "padre A"
      qc.setQueryData(["my-athletes", 1], [{ athlete_id: 42, name: "Sensible" }]);
      qc.setQueryData(["parent-sessions", 1, undefined, undefined], [{ id: 99 }]);
      qc.setQueryData(["my-consent", 1], { needs_renewal: false });

      expect(qc.getQueryCache().getAll().length).toBeGreaterThan(0);

      // Simular sesión activa
      useAuthStore.setState({
        accessToken: "tok",
        refreshToken: "ref",
        user: mockUser,
        isAuthenticated: true,
        isLoading: false,
      });

      useAuthStore.getState().logout();

      // Cache totalmente purgado
      expect(qc.getQueryCache().getAll()).toEqual([]);
      // Estado del store limpio
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
      expect(useAuthStore.getState().user).toBeNull();
    });

    it("logout() no falla cuando no hay QueryClient registrado (loguea warning)", () => {
      // __resetQueryClientHandleForTests garantiza singleton null
      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

      useAuthStore.setState({
        accessToken: "tok",
        refreshToken: "ref",
        user: mockUser,
        isAuthenticated: true,
        isLoading: false,
      });

      expect(() => useAuthStore.getState().logout()).not.toThrow();
      expect(warnSpy).toHaveBeenCalled();
      // Estado del store limpio igualmente
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
      expect(useAuthStore.getState().accessToken).toBeNull();

      warnSpy.mockRestore();
    });

    it("refreshSession fallido propaga al logout que también purga el cache", async () => {
      const qc = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      setQueryClient(qc);

      qc.setQueryData(["my-athletes", 1], [{ leak: "no debe quedar" }]);

      useAuthStore.setState({
        refreshToken: "expired",
        user: mockUser,
        accessToken: "old",
        isAuthenticated: true,
        isLoading: false,
      });
      vi.mocked(authApi.refreshToken).mockRejectedValue(new Error("expired"));

      try {
        await useAuthStore.getState().refreshSession();
      } catch {
        // esperado
      }

      // refreshSession llama logout() en catch → cache debe estar vacío
      expect(qc.getQueryCache().getAll()).toEqual([]);
    });
  });
});
