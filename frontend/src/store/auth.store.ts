import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { getMe, login as loginRequest, refreshToken } from "@/api/auth";
import { registerAuthHandlers } from "@/api/client";
import type { MeResponse } from "@/types/auth.types";

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
