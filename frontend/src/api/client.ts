import axios from "axios";

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const apiClient = axios.create({
  baseURL,
  headers: {
    "Content-Type": "application/json",
  },
});

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
  const token = getAccessToken?.() ?? null;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
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
