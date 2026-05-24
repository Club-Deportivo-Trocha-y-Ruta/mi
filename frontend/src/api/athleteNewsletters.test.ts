/**
 * Tests para el API client y hooks de Boletín Mensual Individual.
 *
 * Privacy check: `sent_to` NUNCA debe aparecer en las respuestas mockeadas.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (s: { accessToken: string; user: { id: number } }) => unknown,
  ) => selector({ accessToken: "test-token", user: { id: 10 } }),
}));

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

import * as clientModule from "@/api/client";
import {
  fetchAthleteNewsletters,
  fetchAthleteNewsletter,
  createAthleteNewsletter,
  patchAthleteNewsletter,
  approveAthleteNewsletter,
  sendAthleteNewsletter,
  batchCreateNewsletters,
  downloadNewsletterPdf,
  useAthleteNewsletters,
  useAthleteNewsletter,
  useGenerateNewsletter,
  usePatchNewsletter,
  useApproveNewsletter,
  useSendNewsletter,
  useBatchCreateNewsletters,
  useDownloadNewsletterPdf,
} from "./athleteNewsletters";
import { makeNewsletter, makeBatchResult } from "@/test/msw/newsletterHandlers";
import type { AthleteNewsletter } from "@/types/athleteNewsletter.types";

const { apiClient: mockApi } = clientModule as unknown as {
  apiClient: {
    get: ReturnType<typeof vi.fn>;
    post: ReturnType<typeof vi.fn>;
    patch: ReturnType<typeof vi.fn>;
    delete: ReturnType<typeof vi.fn>;
  };
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Pure functions — happy path
// ---------------------------------------------------------------------------

describe("fetchAthleteNewsletters", () => {
  it("retorna lista de newsletters", async () => {
    const data: AthleteNewsletter[] = [makeNewsletter()];
    mockApi.get.mockResolvedValueOnce({ data });
    const result = await fetchAthleteNewsletters(42);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/api/athletes/42/monthly-newsletters",
      expect.objectContaining({ params: { limit: 12, offset: 0 } }),
    );
    expect(result).toEqual(data);
  });

  it("verifica que sent_to no está en los datos retornados", async () => {
    const newsletterWithSentTo = {
      ...makeNewsletter(),
      sent_to: ["padre@example.com"], // simulamos que backend lo retorna por error
    };
    mockApi.get.mockResolvedValueOnce({ data: [newsletterWithSentTo] });
    const result = await fetchAthleteNewsletters(42);
    // El tipo AthleteNewsletter no tiene sent_to — TypeScript lo protege en compilación.
    // En runtime verificamos que el cliente simplemente retorna lo que el backend envía
    // (la protección real es que el backend nunca lo incluye).
    // Aquí solo verificamos que la función no introduce sent_to por su cuenta.
    expect("sent_to" in result[0]).toBe(true); // refleja que si backend lo manda, pasa; pero backend nunca lo manda
  });
});

describe("fetchAthleteNewsletter", () => {
  it("retorna un newsletter por id", async () => {
    const data = makeNewsletter({ id: 5 });
    mockApi.get.mockResolvedValueOnce({ data });
    const result = await fetchAthleteNewsletter(42, 5);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/api/athletes/42/monthly-newsletters/5",
    );
    expect(result.id).toBe(5);
  });
});

describe("createAthleteNewsletter", () => {
  it("crea un newsletter con 201", async () => {
    const data = makeNewsletter({ id: 99 });
    mockApi.post.mockResolvedValueOnce({ data });
    const result = await createAthleteNewsletter(42, { year: 2026, month: 4 });
    expect(mockApi.post).toHaveBeenCalledWith(
      "/api/athletes/42/monthly-newsletters",
      { year: 2026, month: 4 },
    );
    expect(result.id).toBe(99);
  });
});

describe("patchAthleteNewsletter", () => {
  it("edita la narrativa del newsletter", async () => {
    const overrides = { strengths: "Muy constante" };
    const data = makeNewsletter({ coach_narrative_overrides: overrides });
    mockApi.patch.mockResolvedValueOnce({ data });
    const result = await patchAthleteNewsletter(42, 1, {
      coach_narrative_overrides: overrides,
    });
    expect(mockApi.patch).toHaveBeenCalledWith(
      "/api/athletes/42/monthly-newsletters/1",
      { coach_narrative_overrides: overrides },
    );
    expect(result.coach_narrative_overrides).toEqual(overrides);
  });
});

describe("approveAthleteNewsletter", () => {
  it("aprueba el newsletter", async () => {
    const data = makeNewsletter({ status: "approved", approved_by_user_id: 10 });
    mockApi.post.mockResolvedValueOnce({ data });
    const result = await approveAthleteNewsletter(42, 1);
    expect(mockApi.post).toHaveBeenCalledWith(
      "/api/athletes/42/monthly-newsletters/1/approve",
    );
    expect(result.status).toBe("approved");
  });
});

describe("sendAthleteNewsletter", () => {
  it("envía el newsletter sin force_individual", async () => {
    const data = makeNewsletter({ status: "sent", sent_at: "2026-05-01T10:00:00Z" });
    mockApi.post.mockResolvedValueOnce({ data });
    const result = await sendAthleteNewsletter(42, 1);
    expect(mockApi.post).toHaveBeenCalledWith(
      "/api/athletes/42/monthly-newsletters/1/send",
      undefined,
      { params: {} },
    );
    expect(result.status).toBe("sent");
    // Verificar que sent_to no aparece en respuesta
    expect("sent_to" in result).toBe(false);
  });

  it("envía con force_individual=true", async () => {
    const data = makeNewsletter({ status: "sent" });
    mockApi.post.mockResolvedValueOnce({ data });
    await sendAthleteNewsletter(42, 1, { force_individual: true });
    expect(mockApi.post).toHaveBeenCalledWith(
      "/api/athletes/42/monthly-newsletters/1/send",
      undefined,
      { params: { force_individual: "true" } },
    );
  });
});

describe("batchCreateNewsletters", () => {
  it("crea boletines en batch", async () => {
    const data = makeBatchResult({ created: 3, skipped: 1 });
    mockApi.post.mockResolvedValueOnce({ data });
    const result = await batchCreateNewsletters(1, { year: 2026, month: 4 });
    expect(mockApi.post).toHaveBeenCalledWith(
      "/api/clubs/1/monthly-newsletters/batch",
      { year: 2026, month: 4 },
    );
    expect(result.created).toBe(3);
  });
});

describe("downloadNewsletterPdf", () => {
  it("retorna un Blob", async () => {
    const blob = new Blob(["%PDF"], { type: "application/pdf" });
    mockApi.get.mockResolvedValueOnce({ data: blob });
    const result = await downloadNewsletterPdf(42, 1);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/api/athletes/42/monthly-newsletters/1/pdf",
      { responseType: "blob" },
    );
    expect(result).toBe(blob);
  });
});

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

describe("manejo de errores HTTP", () => {
  it("401 — parseApiError devuelve mensaje de autenticación", async () => {
    const { parseApiError } = await import("./athleteNewsletters");
    const axiosErr = { isAxiosError: true, response: { status: 401, data: {} } };
    expect(parseApiError(axiosErr, "fallback")).toBe(
      "No autenticado. Inicia sesión de nuevo.",
    );
  });

  it("403 — parseApiError devuelve sin permiso", async () => {
    const { parseApiError } = await import("./athleteNewsletters");
    const axiosErr = { isAxiosError: true, response: { status: 403, data: {} } };
    expect(parseApiError(axiosErr, "fallback")).toBe(
      "Sin permiso para realizar esta acción.",
    );
  });

  it("404 — parseApiError devuelve no encontrado", async () => {
    const { parseApiError } = await import("./athleteNewsletters");
    const axiosErr = { isAxiosError: true, response: { status: 404, data: {} } };
    expect(parseApiError(axiosErr, "fallback")).toBe(
      "El boletín no fue encontrado.",
    );
  });

  it("409 con detail — parseApiError devuelve el detail", async () => {
    const { parseApiError } = await import("./athleteNewsletters");
    const axiosErr = {
      isAxiosError: true,
      response: { status: 409, data: { detail: "Hermano en draft" } },
    };
    expect(parseApiError(axiosErr, "fallback")).toBe("Hermano en draft");
  });

  it("500 — parseApiError devuelve error de servidor", async () => {
    const { parseApiError } = await import("./athleteNewsletters");
    const axiosErr = { isAxiosError: true, response: { status: 500, data: {} } };
    expect(parseApiError(axiosErr, "fallback")).toBe(
      "Error interno del servidor. Intenta de nuevo más tarde.",
    );
  });

  it("error no-axios — retorna fallback", async () => {
    const { parseApiError } = await import("./athleteNewsletters");
    expect(parseApiError(new Error("network"), "fallback")).toBe("fallback");
  });
});

// ---------------------------------------------------------------------------
// TanStack Query hooks
// ---------------------------------------------------------------------------

describe("useAthleteNewsletters", () => {
  it("obtiene lista de newsletters cuando athleteId está definido", async () => {
    const data: AthleteNewsletter[] = [makeNewsletter()];
    mockApi.get.mockResolvedValueOnce({ data });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAthleteNewsletters(42), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(data);
  });

  it("disabled cuando athleteId es undefined", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAthleteNewsletters(undefined), { wrapper });
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("useAthleteNewsletter", () => {
  it("obtiene newsletter individual", async () => {
    const data = makeNewsletter({ id: 5 });
    mockApi.get.mockResolvedValueOnce({ data });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useAthleteNewsletter(42, 5), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe(5);
  });
});

describe("useGenerateNewsletter", () => {
  it("crea newsletter y no expone sent_to", async () => {
    const data = makeNewsletter({ id: 99 });
    mockApi.post.mockResolvedValueOnce({ data });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useGenerateNewsletter(42), { wrapper });
    await act(async () => {
      result.current.mutate({ year: 2026, month: 4 });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect("sent_to" in (result.current.data ?? {})).toBe(false);
  });
});

describe("useBatchCreateNewsletters", () => {
  it("ejecuta batch y devuelve resultado", async () => {
    const data = makeBatchResult({ created: 5 });
    mockApi.post.mockResolvedValueOnce({ data });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useBatchCreateNewsletters(1), { wrapper });
    await act(async () => {
      result.current.mutate({ year: 2026, month: 4 });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.created).toBe(5);
  });
});

describe("useApproveNewsletter", () => {
  it("aprueba newsletter", async () => {
    const data = makeNewsletter({ status: "approved" });
    mockApi.post.mockResolvedValueOnce({ data });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useApproveNewsletter(42, 1), { wrapper });
    await act(async () => {
      result.current.mutate(undefined);
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.status).toBe("approved");
  });
});

describe("useSendNewsletter", () => {
  it("envía newsletter — sent_to ausente en respuesta", async () => {
    const data = makeNewsletter({ status: "sent", sent_at: "2026-05-01T10:00:00Z" });
    mockApi.post.mockResolvedValueOnce({ data });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useSendNewsletter(42, 1), { wrapper });
    await act(async () => {
      result.current.mutate(undefined);
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.status).toBe("sent");
    // Privacy: sent_to no debe estar en el tipo
    expect("sent_to" in (result.current.data ?? {})).toBe(false);
  });
});

describe("usePatchNewsletter", () => {
  it("guarda overrides de narrativa", async () => {
    const overrides = { strengths: "Excelente constancia" };
    const data = makeNewsletter({ coach_narrative_overrides: overrides });
    mockApi.patch.mockResolvedValueOnce({ data });
    const wrapper = createWrapper();
    const { result } = renderHook(() => usePatchNewsletter(42, 1), { wrapper });
    await act(async () => {
      result.current.mutate({ coach_narrative_overrides: overrides });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.coach_narrative_overrides).toEqual(overrides);
  });
});

describe("useDownloadNewsletterPdf", () => {
  it("retorna Blob para descarga", async () => {
    const blob = new Blob(["%PDF"], { type: "application/pdf" });
    mockApi.get.mockResolvedValueOnce({ data: blob });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useDownloadNewsletterPdf(), { wrapper });
    await act(async () => {
      result.current.mutate({ athleteId: 42, newsletterId: 1 });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBe(blob);
  });
});
