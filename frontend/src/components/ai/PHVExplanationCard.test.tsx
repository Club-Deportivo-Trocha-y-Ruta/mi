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
    getPHVExplanationCached: vi.fn(),
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

const cachedResponse: PHVExplanationResponse = {
  text: "Texto cacheado de la última generación.",
  model: "cached-model",
  provider: "google",
  generated_at: "2026-05-04T10:00:00Z",
  age_group: "10-12",
  maturation_status: MaturationStatus.PrePHV,
};

const regeneratedResponse: PHVExplanationResponse = {
  ...mockResponse,
  text: "Texto regenerado, pisa al cacheado.",
  generated_at: "2026-05-05T16:00:00Z",
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
    // Default: cache vacío (204 → null). Cada test puede sobreescribir.
    vi.mocked(aiApi.getPHVExplanationCached).mockResolvedValue(null);
  });

  // -------------------------------------------------------------------------
  // Cache load: GET en mount
  // -------------------------------------------------------------------------

  describe("carga inicial desde caché", () => {
    it("muestra el contenido cacheado sin pedir generación al montar", async () => {
      vi.mocked(aiApi.getPHVExplanationCached).mockResolvedValue(cachedResponse);

      render(<PHVExplanationCard athleteId={42} hasRecords={true} />, {
        wrapper: withQuery(),
      });

      // Aparece el texto del caché tras resolver el GET.
      expect(
        await screen.findByText(/Texto cacheado de la última generación/i),
      ).toBeInTheDocument();
      // Aparece el botón Regenerar (no "Generar explicación").
      expect(
        screen.getByRole("button", { name: /Regenerar/i }),
      ).toBeInTheDocument();
      // Y NO se llamó a la mutación (POST) automáticamente.
      expect(aiApi.getPHVExplanation).not.toHaveBeenCalled();
    });

    it("queda en idle cuando el caché está vacío (204 → null)", async () => {
      vi.mocked(aiApi.getPHVExplanationCached).mockResolvedValue(null);

      render(<PHVExplanationCard athleteId={1} hasRecords={true} />, {
        wrapper: withQuery(),
      });

      const generateBtn = await screen.findByRole("button", {
        name: /Generar explicación/i,
      });
      expect(generateBtn).toBeEnabled();
    });

    it("no hace GET si el atleta no tiene mediciones", async () => {
      render(<PHVExplanationCard athleteId={1} hasRecords={false} />, {
        wrapper: withQuery(),
      });
      // Botón deshabilitado y mensaje de ayuda visibles desde el primer render.
      expect(
        screen.getByRole("button", { name: /Generar explicación/i }),
      ).toBeDisabled();
      // Sin records no tiene sentido consultar caché.
      expect(aiApi.getPHVExplanationCached).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // Estado idle clásico (sin caché)
  // -------------------------------------------------------------------------

  describe("estado idle", () => {
    it("muestra el botón habilitado cuando hay mediciones", async () => {
      render(<PHVExplanationCard athleteId={1} hasRecords={true} />, {
        wrapper: withQuery(),
      });
      const btn = await screen.findByRole("button", {
        name: /Generar explicación/i,
      });
      expect(btn).toBeEnabled();
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

  // -------------------------------------------------------------------------
  // Camino feliz: Generar
  // -------------------------------------------------------------------------

  describe("camino feliz", () => {
    it("renderiza la explicación al completarse la mutación", async () => {
      vi.mocked(aiApi.getPHVExplanation).mockResolvedValue(mockResponse);
      render(<PHVExplanationCard athleteId={42} hasRecords={true} />, {
        wrapper: withQuery(),
      });

      const generateBtn = await screen.findByRole("button", {
        name: /Generar explicación/i,
      });
      fireEvent.click(generateBtn);

      expect(
        await screen.findByText(/Recomendamos juego, técnica y descanso/i),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Regenerar/i }),
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Regenerar: la nueva generación pisa el contenido cacheado
  // -------------------------------------------------------------------------

  describe("regenerar", () => {
    it("la respuesta de la mutación reemplaza al texto cacheado", async () => {
      vi.mocked(aiApi.getPHVExplanationCached).mockResolvedValue(cachedResponse);
      vi.mocked(aiApi.getPHVExplanation).mockResolvedValue(regeneratedResponse);

      render(<PHVExplanationCard athleteId={42} hasRecords={true} />, {
        wrapper: withQuery(),
      });

      // Primero aparece el caché.
      expect(
        await screen.findByText(/Texto cacheado de la última generación/i),
      ).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /Regenerar/i }));

      // Después aparece el regenerado y el cacheado desaparece.
      expect(
        await screen.findByText(/Texto regenerado, pisa al cacheado/i),
      ).toBeInTheDocument();
      expect(
        screen.queryByText(/Texto cacheado de la última generación/i),
      ).not.toBeInTheDocument();
    });

    it("un error al regenerar conserva el contenido cacheado y muestra alerta", async () => {
      vi.mocked(aiApi.getPHVExplanationCached).mockResolvedValue(cachedResponse);
      // 502 (guardrail) es error inmediato — no reintenta. 503 dispararía
      // retries con backoff y tendríamos que avanzar timers.
      vi.mocked(aiApi.getPHVExplanation).mockRejectedValue(axiosErrorWith(502));

      render(<PHVExplanationCard athleteId={42} hasRecords={true} />, {
        wrapper: withQuery(),
      });

      const regenBtn = await screen.findByRole("button", {
        name: /Regenerar/i,
      });
      fireEvent.click(regenBtn);

      // La alerta de error inline aparece cuando la mutación termina.
      expect(
        await screen.findByTestId("phv-explanation-regenerate-error"),
      ).toBeInTheDocument();
      // Y el texto cacheado SIGUE visible (no fue borrado por el error).
      expect(
        screen.getByText(/Texto cacheado de la última generación/i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/no cumple los principios del club/i),
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Manejo de errores de la primera generación (sin caché previa)
  // -------------------------------------------------------------------------

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
        await screen.findByRole("button", { name: /Generar explicación/i }),
      );

      expect(
        await screen.findByText(/Este atleta aún no tiene mediciones/i),
      ).toBeInTheDocument();

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

        await vi.advanceTimersByTimeAsync(50);
        fireEvent.click(
          screen.getByRole("button", { name: /Generar explicación/i }),
        );

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
        await screen.findByRole("button", { name: /Generar explicación/i }),
      );

      expect(
        await screen.findByText(/no cumple los principios del club/i),
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Estado pending
  // -------------------------------------------------------------------------

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
        await screen.findByRole("button", { name: /Generar explicación/i }),
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

  // -------------------------------------------------------------------------
  // Modo readOnly — vista de padres
  // -------------------------------------------------------------------------

  describe("modo readOnly", () => {
    it("muestra el texto cacheado pero NO el botón Regenerar", async () => {
      vi.mocked(aiApi.getPHVExplanationCached).mockResolvedValue(cachedResponse);

      render(
        <PHVExplanationCard athleteId={42} hasRecords={true} readOnly />,
        { wrapper: withQuery() },
      );

      // El contenido cacheado debe aparecer
      expect(
        await screen.findByText(/Texto cacheado de la última generación/i),
      ).toBeInTheDocument();

      // NO debe haber botón Regenerar
      expect(
        screen.queryByRole("button", { name: /Regenerar/i }),
      ).not.toBeInTheDocument();
    });

    it("muestra mensaje pasivo y NO el botón Generar cuando no hay caché (204)", async () => {
      vi.mocked(aiApi.getPHVExplanationCached).mockResolvedValue(null);

      render(
        <PHVExplanationCard athleteId={1} hasRecords={true} readOnly />,
        { wrapper: withQuery() },
      );

      // Mensaje pasivo para el padre
      expect(
        await screen.findByText(/El entrenador la generará pronto/i),
      ).toBeInTheDocument();

      // NO debe haber botón Generar
      expect(
        screen.queryByRole("button", { name: /Generar explicación/i }),
      ).not.toBeInTheDocument();
    });

    it("no llama a getPHVExplanation (mutation) en ningún momento", async () => {
      vi.mocked(aiApi.getPHVExplanationCached).mockResolvedValue(cachedResponse);

      render(
        <PHVExplanationCard athleteId={42} hasRecords={true} readOnly />,
        { wrapper: withQuery() },
      );

      // Esperamos a que resuelva el GET
      await screen.findByText(/Texto cacheado de la última generación/i);

      // La mutation POST no debe haberse invocado en ningún momento
      expect(aiApi.getPHVExplanation).not.toHaveBeenCalled();
    });

    it("sin caché y sin records: muestra mensaje pasivo (no bloquea la query)", async () => {
      // hasRecords=false deshabilita la query GET en el hook
      vi.mocked(aiApi.getPHVExplanationCached).mockResolvedValue(null);

      render(
        <PHVExplanationCard athleteId={1} hasRecords={false} readOnly />,
        { wrapper: withQuery() },
      );

      // El idle de readOnly debe aparecer (la query no corre pero el estado
      // es el mismo: sin contenido → mensaje pasivo)
      expect(
        await screen.findByText(/El entrenador la generará pronto/i),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /Generar explicación/i }),
      ).not.toBeInTheDocument();
    });
  });
});
