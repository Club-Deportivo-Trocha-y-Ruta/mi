import axios from "axios";

import { useServerWakingStore } from "@/store/serverWaking.store";

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const apiClient = axios.create({
  baseURL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Feature 012, US2: pre-calienta el backend (Render Free duerme tras ~15 min).
let warmedUp = false;

/**
 * Dispara una petición de "wake up" al backend una sola vez por carga de la
 * app. Fire-and-forget: sin auth, sin reintentos, ignora la respuesta y los
 * errores, y NO pasa por axios (no alimenta el store de "servidor
 * despertando" — no es una petición del usuario). Ver contracts/health-warmup.md.
 */
export function warmUp(): void {
  if (warmedUp) return;
  warmedUp = true;
  try {
    void fetch(`${baseURL}/health`, { method: "GET" }).catch(() => {
      // Backend dormido/inaccesible — es exactamente lo que estamos
      // despertando; nunca mostramos error por el ping.
    });
  } catch {
    // Entorno sin fetch (no debería ocurrir en navegador) — no-op.
  }
}

/** Test-only: reset the warm-up dedup flag. */
export function __resetWarmUpForTests(): void {
  warmedUp = false;
}

let getAccessToken: (() => string | null) | null = null;
let onUnauthorized: (() => Promise<void> | void) | null = null;

export function registerAuthHandlers(handlers: {
  getAccessToken: () => string | null;
  onUnauthorized: () => Promise<void> | void;
}) {
  getAccessToken = handlers.getAccessToken;
  onUnauthorized = handlers.onUnauthorized;
}

let refreshInFlight: Promise<void> | null = null;

apiClient.interceptors.request.use((config) => {
  // Feature 012, US2: registra cada petición en vuelo para el aviso de
  // "servidor despertando" (umbral ~3 s centralizado en el store).
  useServerWakingStore.getState().requestStarted();
  const token = getAccessToken?.() ?? null;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => {
    // Feature 012, US2: la petición se resolvió — desregistra del aviso.
    useServerWakingStore.getState().requestSettled();
    return response;
  },
  async (error) => {
    // La petición original terminó (con error). El reintento del 401 crea una
    // petición NUEVA con su propio start/settle, así que el conteo se mantiene
    // balanceado.
    useServerWakingStore.getState().requestSettled();
    const status = error?.response?.status as number | undefined;
    const requestUrl = error?.config?.url as string | undefined;
    const originalConfig = error?.config;

    const isAuthBypass =
      requestUrl?.includes("/api/auth/login") ||
      requestUrl?.includes("/api/auth/refresh");

    const alreadyRetried = (originalConfig as { _retry?: boolean })?._retry;

    if (status === 401 && !isAuthBypass && !alreadyRetried && originalConfig) {
      try {
        if (!refreshInFlight) {
          refreshInFlight = Promise.resolve(onUnauthorized?.()).finally(() => {
            refreshInFlight = null;
          }) as Promise<void>;
        }
        await refreshInFlight;

        (originalConfig as { _retry?: boolean })._retry = true;
        const token = getAccessToken?.() ?? null;
        if (token) {
          originalConfig.headers = originalConfig.headers ?? {};
          (originalConfig.headers as Record<string, string>).Authorization = `Bearer ${token}`;
        }
        return apiClient.request(originalConfig);
      } catch (refreshError) {
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  },
);
