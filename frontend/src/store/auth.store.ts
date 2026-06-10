import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { getMe, login as loginRequest, refreshToken } from "@/api/auth";
import { getAthletes } from "@/api/athletes";
import { registerAuthHandlers } from "@/api/client";
import { getMyAthletes } from "@/api/parents";
import { getQueryClient } from "@/lib/queryClientHandle";
import { wipePersistedCache } from "@/lib/queryPersister";
import { useParentContextStore } from "@/store/parentContext.store";
import type { MeResponse } from "@/types/auth.types";
import { UserRole } from "@/types/enums";

/**
 * Feature 012, US3 (FR-011): tras un login exitoso, pre-carga la query
 * principal de la página de aterrizaje del rol (Dashboard → ["athletes"],
 * Mis Atletas → ["my-athletes", userId]) para que abra sin estado de carga.
 * Fire-and-forget: nunca bloquea ni rompe el flujo de login. Mismas
 * queryKey/fn autenticadas de los hooks de esas páginas (RBAC sin cambios).
 */
function prefetchLandingData(user: MeResponse): void {
  const qc = getQueryClient();
  if (!qc) return;
  try {
    if (user.role === UserRole.parent) {
      void qc.prefetchQuery({
        queryKey: ["my-athletes", user.id],
        queryFn: getMyAthletes,
      });
    } else if (user.role === UserRole.coach || user.role === UserRole.admin) {
      void qc.prefetchQuery({
        queryKey: ["athletes"],
        queryFn: () => getAthletes(),
      });
    }
  } catch {
    // El prefetch es un mejor-esfuerzo; el aterrizaje carga normal si falla.
  }
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: MeResponse | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshSession: () => Promise<void>;
  fetchMe: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,

      login: async (email, password) => {
        set({ isLoading: true });
        try {
          const tokens = await loginRequest({ email, password });
          set({
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
            isAuthenticated: true,
          });
          try {
            await get().fetchMe();
          } catch (error) {
            get().logout();
            throw error;
          }
        } finally {
          set({ isLoading: false });
        }
      },

      logout: () => {
        // Privacy R1: purga el cache de TanStack Query ANTES de limpiar el
        // estado del store. Sin esto, datos de un padre podrían quedar
        // accesibles para el siguiente login en la misma máquina/tablet
        // (uso compartido en familias). Crítico para Ley 1581 (menores).
        const qc = getQueryClient();
        if (qc) {
          qc.clear();
        } else {
          // En runtime real esto no debería ocurrir (App.tsx registra el
          // client antes de cualquier render). En tests, los suites que
          // no mocean queryClientHandle verán este warning — es esperado.
          // eslint-disable-next-line no-console
          console.warn(
            "[auth.store] logout() sin QueryClient registrado — cache no purgado",
          );
        }
        // Feature 012: además del cache en memoria, borramos el cache
        // PERSISTIDO en localStorage. Sin esto, en una tablet compartida los
        // datos persistidos de una cuenta quedarían en el dispositivo tras el
        // logout (Ley 1581 — menores).
        wipePersistedCache();
        // Privacy R4 (Wave 4): además del cache, limpiamos el "athlete
        // activo" persistido del padre. Sin esto, en tablets compartidas
        // el padre B heredaría el activeAthleteId del padre A hasta que
        // `useActiveAthlete` corra su efecto defensivo (ventana visual
        // de al menos un frame con label/avatar del hijo equivocado).
        // El `reset()` del parentContext store solo escribe state local —
        // el middleware `persist` se encarga de actualizar localStorage.
        try {
          useParentContextStore.getState().reset();
        } catch {
          // Defensa: si el store aún no se inicializó (improbable —
          // ambos viven en el mismo bundle), no debe romper el logout.
        }
        set({
          accessToken: null,
          refreshToken: null,
          user: null,
          isAuthenticated: false,
          isLoading: false,
        });
      },

      refreshSession: async () => {
        const currentRefresh = get().refreshToken;
        if (!currentRefresh) {
          get().logout();
          throw new Error("No hay refresh token");
        }
        set({ isLoading: true });
        try {
          const tokens = await refreshToken({ refresh_token: currentRefresh });
          set({
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
            isAuthenticated: true,
          });
          if (!get().user) {
            await get().fetchMe();
          }
        } catch (error) {
          get().logout();
          throw error;
        } finally {
          set({ isLoading: false });
        }
      },

      fetchMe: async () => {
        const me = await getMe();
        set({ user: me, isAuthenticated: true });
        prefetchLandingData(me);
      },
    }),
    {
      name: "auth-session",
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);

registerAuthHandlers({
  getAccessToken: () => useAuthStore.getState().accessToken,
  onUnauthorized: async () => {
    const store = useAuthStore.getState();
    try {
      await store.refreshSession();
    } catch {
      store.logout();
      window.location.assign("/login");
    }
  },
});
