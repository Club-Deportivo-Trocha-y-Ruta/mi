import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

import { AnthropometricRecordExplanationCard } from "./AnthropometricRecordExplanationCard";

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

const baseResponse: AnthropometricRecordExplanationResponse = {
  text: "Su hijo creció desde la última medición.",
  model: "fake-model",
  provider: "fake",
  generated_at: "2026-05-05T15:30:00Z",
  age_group: "10-12",
  maturation_status: MaturationStatus.PrePHV,
  record_id: 42,
  num_previous_measurements: 2,
  delta_height_cm: 2.5,
  delta_weight_kg: 1.8,
};

const firstMeasurement: AnthropometricRecordExplanationResponse = {
  ...baseResponse,
  text: "Esta es la primera medición registrada.",
  num_previous_measurements: 0,
  delta_height_cm: null,
  delta_weight_kg: null,
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

describe("AnthropometricRecordExplanationCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(null);
  });

  // -------------------------------------------------------------------------
  // Coach mode — idle / pending / success / error states
  // -------------------------------------------------------------------------

  describe("modo coach", () => {
    it("renderiza idle cuando no hay caché y permite generar", async () => {
      vi.mocked(aiApi.postMeasurementExplanation).mockResolvedValue(baseResponse);

      render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );

      await waitFor(() => {
        expect(screen.getByTestId("record-explanation-idle")).toBeInTheDocument();
      });

      const btn = screen.getByRole("button", { name: /Analizar esta medición/i });
      fireEvent.click(btn);

      await waitFor(() => {
        expect(screen.getByTestId("record-explanation-success")).toBeInTheDocument();
      });
      expect(
        screen.getByText("Su hijo creció desde la última medición."),
      ).toBeInTheDocument();
    });

    it("muestra resumen de deltas cuando hay mediciones previas", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        baseResponse,
      );

      render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );

      await waitFor(() => {
        expect(screen.getByTestId("record-explanation-deltas")).toBeInTheDocument();
      });
      expect(screen.getByTestId("delta-height")).toHaveTextContent("Δ talla +2.5 cm");
      expect(screen.getByTestId("delta-weight")).toHaveTextContent("Δ peso +1.8 kg");
      expect(screen.getByTestId("record-explanation-deltas")).toHaveTextContent(
        "2 mediciones previas",
      );
    });

    it("oculta deltas y muestra 'primera medición' cuando num_previous=0", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        firstMeasurement,
      );

      render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );

      await waitFor(() => {
        expect(
          screen.getByTestId("record-explanation-no-history"),
        ).toBeInTheDocument();
      });
      expect(screen.queryByTestId("delta-height")).not.toBeInTheDocument();
      expect(screen.queryByTestId("delta-weight")).not.toBeInTheDocument();
    });

    it("mapea 451 a mensaje de consentimiento sin botón reintentar", async () => {
      vi.mocked(aiApi.postMeasurementExplanation).mockRejectedValue(
        axiosErrorWith(451),
      );

      render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );

      await waitFor(() => {
        expect(screen.getByTestId("record-explanation-idle")).toBeInTheDocument();
      });
      fireEvent.click(
        screen.getByRole("button", { name: /Analizar esta medición/i }),
      );

      await waitFor(() => {
        expect(screen.getByTestId("record-explanation-error")).toBeInTheDocument();
      });
      expect(
        screen.getByText(/consentimiento de la familia/i),
      ).toBeInTheDocument();
      // 451 no es retryable
      expect(
        screen.queryByRole("button", { name: /Reintentar/i }),
      ).not.toBeInTheDocument();
    });

    it("muestra error con botón Reintentar para 502 (guardrail)", async () => {
      // 502 no se auto-reintenta según la política del hook → entra al
      // estado error rápido y muestra el botón Reintentar manual.
      vi.mocked(aiApi.postMeasurementExplanation).mockRejectedValue(
        axiosErrorWith(502),
      );

      render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );

      await waitFor(() => {
        expect(screen.getByTestId("record-explanation-idle")).toBeInTheDocument();
      });
      fireEvent.click(
        screen.getByRole("button", { name: /Analizar esta medición/i }),
      );

      await waitFor(
        () => {
          expect(
            screen.getByTestId("record-explanation-error"),
          ).toBeInTheDocument();
        },
        { timeout: 5000 },
      );
      // 502 es retryable según el mapper (transitorio puede liberar el
      // guardrail), pero no se auto-reintenta — solo botón manual.
      expect(
        screen.getByRole("button", { name: /Reintentar/i }),
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Parent mode — read-only with disclaimer
  // -------------------------------------------------------------------------

  describe("modo padre", () => {
    it("renderiza disclaimer cuando hay caché", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        baseResponse,
      );

      render(
        <AnthropometricRecordExplanationCard
          athleteId={1}
          recordId={42}
          readOnly={true}
        />,
        { wrapper: withQuery() },
      );

      await waitFor(() => {
        expect(
          screen.getByTestId("record-explanation-readonly"),
        ).toBeInTheDocument();
      });
      expect(
        screen.getByTestId("record-explanation-disclaimer"),
      ).toHaveTextContent(/IA.*entrenador.*médico/i);
    });

    it("no muestra botón generar en modo padre", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        baseResponse,
      );

      render(
        <AnthropometricRecordExplanationCard
          athleteId={1}
          recordId={42}
          readOnly={true}
        />,
        { wrapper: withQuery() },
      );

      await waitFor(() => {
        expect(
          screen.getByTestId("record-explanation-readonly"),
        ).toBeInTheDocument();
      });
      expect(
        screen.queryByRole("button", { name: /Analizar esta medición/i }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /Regenerar/i }),
      ).not.toBeInTheDocument();
    });

    it("sin caché en modo padre → no renderiza la sección", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(null);

      const { container } = render(
        <AnthropometricRecordExplanationCard
          athleteId={1}
          recordId={42}
          readOnly={true}
        />,
        { wrapper: withQuery() },
      );

      // Esperar a que el fetch resuelva — query queda en success con null
      await waitFor(() => {
        // El componente con null retorna null; no debería haber readonly ni idle
        expect(
          screen.queryByTestId("record-explanation-readonly"),
        ).not.toBeInTheDocument();
        expect(
          screen.queryByTestId("record-explanation-idle"),
        ).not.toBeInTheDocument();
      });
      // El container puede tener loading-cache mientras carga, pero al final no tiene contenido
      // Garantizamos al menos que no haya botones generables
      expect(
        container.querySelector('[data-testid="record-explanation-idle"]'),
      ).not.toBeInTheDocument();
    });

    it("modo padre NO instancia la mutation (no llama POST)", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        baseResponse,
      );

      render(
        <AnthropometricRecordExplanationCard
          athleteId={1}
          recordId={42}
          readOnly={true}
        />,
        { wrapper: withQuery() },
      );

      await waitFor(() => {
        expect(
          screen.getByTestId("record-explanation-readonly"),
        ).toBeInTheDocument();
      });
      expect(aiApi.postMeasurementExplanation).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // Caché aislamiento por recordId
  // -------------------------------------------------------------------------

  it("invoca GET con el recordId correcto", async () => {
    vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(null);

    render(
      <AnthropometricRecordExplanationCard athleteId={1} recordId={99} />,
      { wrapper: withQuery() },
    );

    await waitFor(() => {
      expect(aiApi.getMeasurementExplanationCached).toHaveBeenCalledWith(
        1,
        99,
      );
    });
  });
});
