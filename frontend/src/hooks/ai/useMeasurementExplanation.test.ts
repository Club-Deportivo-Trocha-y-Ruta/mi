import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { AxiosError, AxiosHeaders } from "axios";
import { createElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/ai", async () => {
  const actual = await vi.importActual<typeof import("@/api/ai")>("@/api/ai");
  return {
    ...actual,
    postMeasurementExplanation: vi.fn(),
    getMeasurementExplanationCached: vi.fn(),
  };
});

import * as aiApi from "@/api/ai";
import { MaturationStatus } from "@/types/enums";
import type { AnthropometricRecordExplanationResponse } from "@/types/ai.types";

import {
  useMeasurementExplanation,
  useMeasurementExplanationCached,
} from "./useMeasurementExplanation";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

const mockResponse: AnthropometricRecordExplanationResponse = {
  text: "Su hijo creció en este periodo.",
  model: "fake-model",
  provider: "fake",
  generated_at: "2026-05-05T10:00:00Z",
  age_group: "10-12",
  maturation_status: MaturationStatus.PrePHV,
  record_id: 42,
  num_previous_measurements: 1,
  delta_height_cm: 2.5,
  delta_weight_kg: 1.5,
};

function axiosErrorWith(status: number): AxiosError {
  return new AxiosError(
    `Request failed with status code ${status}`,
    String(status),
    undefined,
    undefined,
    {
      data: { detail: "x" },
      status,
      statusText: "",
      headers: {},
      config: { headers: new AxiosHeaders() },
    },
  );
}

describe("useMeasurementExplanationCached", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("invoca getMeasurementExplanationCached con (athleteId, recordId)", async () => {
    vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
      mockResponse,
    );

    const { result } = renderHook(
      () => useMeasurementExplanationCached(7, 42, true),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockResponse);
    expect(aiApi.getMeasurementExplanationCached).toHaveBeenCalledWith(7, 42);
  });

  it("devuelve null cuando no hay caché (204)", async () => {
    vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(null);

    const { result } = renderHook(
      () => useMeasurementExplanationCached(7, 42, true),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
  });

  it("no llama la API cuando enabled=false", async () => {
    vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
      mockResponse,
    );

    renderHook(() => useMeasurementExplanationCached(7, 42, false), {
      wrapper: createWrapper(),
    });

    // Esperamos un microtask para confirmar que no se llamó
    await new Promise((r) => setTimeout(r, 10));
    expect(aiApi.getMeasurementExplanationCached).not.toHaveBeenCalled();
  });

  it("no llama la API cuando recordId=0", async () => {
    vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
      mockResponse,
    );

    renderHook(() => useMeasurementExplanationCached(7, 0, true), {
      wrapper: createWrapper(),
    });

    await new Promise((r) => setTimeout(r, 10));
    expect(aiApi.getMeasurementExplanationCached).not.toHaveBeenCalled();
  });
});

describe("useMeasurementExplanation (mutation)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("retorna éxito y sincroniza la queryKey individual", async () => {
    vi.mocked(aiApi.postMeasurementExplanation).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useMeasurementExplanation(7, 42), {
      wrapper: createWrapper(),
    });

    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockResponse);
  });

  it("no reintenta 422 (sin historial)", async () => {
    vi.mocked(aiApi.postMeasurementExplanation).mockRejectedValue(
      axiosErrorWith(422),
    );

    const { result } = renderHook(() => useMeasurementExplanation(7, 42), {
      wrapper: createWrapper(),
    });

    result.current.mutate();
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(aiApi.postMeasurementExplanation).toHaveBeenCalledTimes(1);
  });

  it("no reintenta 451 (consent missing)", async () => {
    vi.mocked(aiApi.postMeasurementExplanation).mockRejectedValue(
      axiosErrorWith(451),
    );

    const { result } = renderHook(() => useMeasurementExplanation(7, 42), {
      wrapper: createWrapper(),
    });

    result.current.mutate();
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(aiApi.postMeasurementExplanation).toHaveBeenCalledTimes(1);
  });

  it("no reintenta 502 (guardrail) — solo retry manual", async () => {
    vi.mocked(aiApi.postMeasurementExplanation).mockRejectedValue(
      axiosErrorWith(502),
    );

    const { result } = renderHook(() => useMeasurementExplanation(7, 42), {
      wrapper: createWrapper(),
    });

    result.current.mutate();
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(aiApi.postMeasurementExplanation).toHaveBeenCalledTimes(1);
  });

  it("no reintenta 403 (parent forbidden)", async () => {
    vi.mocked(aiApi.postMeasurementExplanation).mockRejectedValue(
      axiosErrorWith(403),
    );

    const { result } = renderHook(() => useMeasurementExplanation(7, 42), {
      wrapper: createWrapper(),
    });

    result.current.mutate();
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(aiApi.postMeasurementExplanation).toHaveBeenCalledTimes(1);
  });

  it("propaga AbortController vía signal", async () => {
    vi.mocked(aiApi.postMeasurementExplanation).mockResolvedValue(mockResponse);

    const controller = new AbortController();
    const { result } = renderHook(() => useMeasurementExplanation(7, 42), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ signal: controller.signal });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const callArgs = vi.mocked(aiApi.postMeasurementExplanation).mock.calls[0];
    expect(callArgs[0]).toBe(7);
    expect(callArgs[1]).toBe(42);
    expect(callArgs[2]?.signal).toBe(controller.signal);
  });
});
