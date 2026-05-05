import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AxiosError, AxiosHeaders } from "axios";
import { createElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/ai", async () => {
  const actual = await vi.importActual<typeof import("@/api/ai")>("@/api/ai");
  return {
    ...actual,
    getPHVExplanation: vi.fn(),
  };
});

import * as aiApi from "@/api/ai";
import { MaturationStatus } from "@/types/enums";
import type { PHVExplanationResponse } from "@/types/ai.types";

import { PHVExplanationCard } from "./PHVExplanationCard";

function withQuery() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
}

const mockResponse: PHVExplanationResponse = {
  text: "Su hijo está en Pre-PHV. Recomendamos juego, técnica y descanso.",
  model: "fake-model",
  provider: "fake",
  generated_at: "2026-05-05T15:30:00Z",
  age_group: "10-12",
  maturation_status: MaturationStatus.PrePHV,
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

describe("PHVExplanationCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("estado idle", () => {
    it("muestra el botón habilitado cuando hay mediciones", () => {
      render(<PHVExplanationCard athleteId={1} hasRecords={true} />, {
        wrapper: withQuery(),
      });
      expect(
        screen.getByRole("button", { name: /Generar explicación/i }),
      ).toBeEnabled();
    });

    it("deshabilita el botón cuando no hay mediciones y muestra ayuda", () => {
      render(<PHVExplanationCard athleteId={1} hasRecords={false} />, {
        wrapper: withQuery(),
      });
      expect(
        screen.getByRole("button", { name: /Generar explicación/i }),
      ).toBeDisabled();
      expect(
        screen.getByText(/Registra una medición antropométrica/i),
      ).toBeInTheDocument();
    });
  });

  describe("camino feliz", () => {
    it("renderiza la explicación al completarse la mutación", async () => {
      vi.mocked(aiApi.getPHVExplanation).mockResolvedValue(mockResponse);
      render(<PHVExplanationCard athleteId={42} hasRecords={true} />, {
        wrapper: withQuery(),
      });

      fireEvent.click(
        screen.getByRole("button", { name: /Generar explicación/i }),
      );

      expect(
        await screen.findByText(/Recomendamos juego, técnica y descanso/i),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Regenerar/i }),
      ).toBeInTheDocument();
    });
  });

  describe("manejo de errores", () => {
    it("muestra copy específica para 422 (sin mediciones) con CTA", async () => {
      vi.mocked(aiApi.getPHVExplanation).mockRejectedValue(
        axiosErrorWith(422),
      );
      const onMeasurementCTA = vi.fn();
      render(
        <PHVExplanationCard
          athleteId={1}
          hasRecords={true}
          onMeasurementCTA={onMeasurementCTA}
        />,
        { wrapper: withQuery() },
      );

      fireEvent.click(
        screen.getByRole("button", { name: /Generar explicación/i }),
      );

      const errorMsg = await screen.findByText(
        /Este atleta aún no tiene mediciones/i,
      );
      expect(errorMsg).toBeInTheDocument();

      const cta = screen.getByRole("button", { name: /Registrar medición/i });
      fireEvent.click(cta);
      expect(onMeasurementCTA).toHaveBeenCalledTimes(1);
      // 422 no es retryable: no debe haber botón Reintentar.
      expect(
        screen.queryByRole("button", { name: /Reintentar/i }),
      ).not.toBeInTheDocument();
    });

    it("muestra Reintentar para 503 (servicio no disponible)", async () => {
      // 503 dispara hasta 2 retries con backoff exponencial (5s, 10s).
      // Usamos timers falsos para no esperar 15s reales.
      vi.useFakeTimers({ shouldAdvanceTime: true });
      vi.mocked(aiApi.getPHVExplanation).mockRejectedValue(
        axiosErrorWith(503),
      );
      try {
        render(<PHVExplanationCard athleteId={1} hasRecords={true} />, {
          wrapper: withQuery(),
        });

        fireEvent.click(
          screen.getByRole("button", { name: /Generar explicación/i }),
        );

        // Avanzamos lo suficiente para agotar todos los retries.
        await vi.advanceTimersByTimeAsync(30_000);

        expect(
          await screen.findByText(/temporalmente no disponible/i),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: /Reintentar/i }),
        ).toBeInTheDocument();
      } finally {
        vi.useRealTimers();
      }
    });

    it("muestra copy específica para 502 (guardrail)", async () => {
      vi.mocked(aiApi.getPHVExplanation).mockRejectedValue(
        axiosErrorWith(502),
      );
      render(<PHVExplanationCard athleteId={1} hasRecords={true} />, {
        wrapper: withQuery(),
      });

      fireEvent.click(
        screen.getByRole("button", { name: /Generar explicación/i }),
      );

      expect(
        await screen.findByText(/no cumple los principios del club/i),
      ).toBeInTheDocument();
    });
  });

  describe("estado pending", () => {
    it("muestra skeleton y botón Cancelar mientras genera", async () => {
      let resolveFn: (v: PHVExplanationResponse) => void = () => {};
      vi.mocked(aiApi.getPHVExplanation).mockImplementation(
        () => new Promise((resolve) => {
          resolveFn = resolve;
        }),
      );

      render(<PHVExplanationCard athleteId={1} hasRecords={true} />, {
        wrapper: withQuery(),
      });

      fireEvent.click(
        screen.getByRole("button", { name: /Generar explicación/i }),
      );

      await waitFor(() =>
        expect(
          screen.getByTestId("phv-explanation-pending"),
        ).toBeInTheDocument(),
      );
      expect(
        screen.getByRole("button", { name: /Cancelar/i }),
      ).toBeInTheDocument();

      // Limpieza: resolvemos para que la promesa pendiente no quede colgada.
      resolveFn(mockResponse);
    });
  });
});
