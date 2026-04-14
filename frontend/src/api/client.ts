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

    if (status === 401 && requestUrl && !requestUrl.includes("/api/auth")) {
      await onUnauthorized?.();
    }

    return Promise.reject(error);
  },
);

export async function pingHealth(): Promise<{ status: string }> {
  const response = await apiClient.get<{ status: string }>("/health");
  return response.data;
}
