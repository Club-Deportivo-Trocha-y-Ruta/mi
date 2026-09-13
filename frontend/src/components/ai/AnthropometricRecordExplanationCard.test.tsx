import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AxiosError, AxiosHeaders } from "axios";
import { axe, toHaveNoViolations } from "jest-axe";
import { createElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

expect.extend(toHaveNoViolations);

vi.mock("@/api/ai", async () => {
  const actual = await vi.importActual<typeof import("@/api/ai")>("@/api/ai");
  return {
    ...actual,
    postMeasurementExplanation: vi.fn(),
    getMeasurementExplanationCached: vi.fn(),
  };
});

// useAIStatus (FR-032) — sin datos por defecto: degradación reactiva-only,
// ningún hint visible, control habilitado. La sección "presupuesto de IA"
// sobreescribe `mockAIStatusData`. Mismo patrón que `PHVExplanationCard.test.tsx`.
let mockAIStatusData: AIStatusResponse | undefined = undefined;
vi.mock("@/hooks/ai/useAIStatus", () => ({
  useAIStatus: () => ({ data: mockAIStatusData, isError: false }),
}));

import * as aiApi from "@/api/ai";
import { MaturationStatus } from "@/types/enums";
import type {
  AIStatusResponse,
  AnthropometricRecordExplanationResponse,
} from "@/types/ai.types";

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
  schema_version: "v1",
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

const structuredInsight = {
  summary_line: "Talla +1.0 cm en 14 semanas, dentro del rango esperado.",
  changes: ["El cambio de talla supera el ruido instrumental."],
  meaning: ["La velocidad estimada está por encima de lo típico."],
  next_weeks: ["Compatible con fuerza progresiva."],
  warning_signs: [],
  confidence: { level: "high" as const, reason: "Intervalo de 14 semanas consistente." },
  data_gaps: [],
};

const v2Response: AnthropometricRecordExplanationResponse = {
  ...baseResponse,
  schema_version: "v2",
  text: "Talla +1.0 cm en 14 semanas, dentro del rango esperado.",
  structured: structuredInsight,
  critic_verdict: "approved",
  is_fallback: false,
  prompt_version: "anthropometry_analyst_v1",
  trace_id: "a1b2c3d4e5f60718",
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
    mockAIStatusData = undefined;
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
  // Análisis estructurado v2 (FR-026) — colapsado por defecto, degradación
  // ante `structured` corrupto, avisos de veredicto solo-coach (FR-016).
  // -------------------------------------------------------------------------

  describe("análisis estructurado v2", () => {
    it("renderiza el análisis v2 colapsado vía StructuredInsight, antes del texto plano", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        v2Response,
      );

      render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );

      await waitFor(() => {
        expect(screen.getByTestId("structured-insight")).toBeInTheDocument();
      });
      // Colapsado por defecto: "qué significa"/"próximas semanas" ocultos.
      expect(
        screen.queryByTestId("structured-insight-details"),
      ).not.toBeInTheDocument();
      const toggle = screen.getByTestId("structured-insight-toggle");
      expect(toggle).toHaveAttribute("aria-expanded", "false");

      // El texto plano (AIGeneratedContent) sigue disponible debajo.
      expect(
        screen.getAllByText(
          "Talla +1.0 cm en 14 semanas, dentro del rango esperado.",
        ).length,
      ).toBeGreaterThan(0);

      fireEvent.click(toggle);
      expect(
        await screen.findByTestId("structured-insight-details"),
      ).toBeInTheDocument();
    });

    it("una fila v1 (legacy) no muestra StructuredInsight — solo el texto plano de siempre", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        baseResponse,
      );

      render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );

      await waitFor(() => {
        expect(screen.getByTestId("record-explanation-success")).toBeInTheDocument();
      });
      expect(
        screen.queryByTestId("structured-insight"),
      ).not.toBeInTheDocument();
    });

    it("un `structured` corrupto degrada al texto plano en vez de reventar el modal", async () => {
      const corrupt: AnthropometricRecordExplanationResponse = {
        ...v2Response,
        // `structured` corrupto: falta casi todo lo que StructuredInsight
        // necesita para iterar (`.map`) sin lanzar.
        structured: { summary_line: "x" } as unknown as typeof structuredInsight,
      };
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(corrupt);

      render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );

      await waitFor(() => {
        expect(screen.getByTestId("record-explanation-success")).toBeInTheDocument();
      });
      expect(screen.queryByTestId("structured-insight")).not.toBeInTheDocument();
      // El texto (`text`, siempre poblado por el backend) sigue visible.
      expect(
        screen.getByText(
          "Talla +1.0 cm en 14 semanas, dentro del rango esperado.",
        ),
      ).toBeInTheDocument();
    });

    it.each([
      ["flagged", /Con observaciones/i],
      ["fallback", /Análisis de respaldo/i],
      ["skipped", /Sin revisión/i],
    ] as const)(
      "coach ve el aviso de veredicto '%s'",
      async (verdict, expectedText) => {
        vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue({
          ...v2Response,
          critic_verdict: verdict,
        });

        render(
          <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
          { wrapper: withQuery() },
        );

        expect(
          await screen.findByTestId("record-explanation-verdict-marker"),
        ).toHaveTextContent(expectedText);
      },
    );

    it("una fila v2 aprobada no muestra ningún aviso de veredicto", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        v2Response,
      );

      render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );

      await waitFor(() => {
        expect(screen.getByTestId("record-explanation-success")).toBeInTheDocument();
      });
      expect(
        screen.queryByTestId("record-explanation-verdict-marker"),
      ).not.toBeInTheDocument();
    });

    it("muestra el chip 'Desactualizado' cuando isStale=true", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        baseResponse,
      );

      render(
        <AnthropometricRecordExplanationCard
          athleteId={1}
          recordId={42}
          isStale
        />,
        { wrapper: withQuery() },
      );

      expect(
        await screen.findByTestId("record-explanation-stale-chip"),
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Presupuesto de IA (FR-032) — hint sobre el control + deshabilitado
  // mientras el presupuesto está agotado.
  // -------------------------------------------------------------------------

  describe("presupuesto de IA", () => {
    it("sin caché: muestra el hint de presupuesto agotado y deshabilita 'Analizar esta medición'", async () => {
      mockAIStatusData = {
        budget_status: "exhausted",
        budget_remaining_pct: 0,
        concurrency_available: true,
        est_wait_seconds: 0,
      };

      render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );

      expect(
        await screen.findByTestId("ai-budget-hint-exhausted"),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Analizar esta medición/i }),
      ).toBeDisabled();
    });

    it("con caché: muestra el hint sobre 'Regenerar análisis' y lo deshabilita si el presupuesto está agotado", async () => {
      mockAIStatusData = {
        budget_status: "exhausted",
        budget_remaining_pct: 0,
        concurrency_available: true,
        est_wait_seconds: 0,
      };
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        baseResponse,
      );

      render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );

      expect(
        await screen.findByTestId("ai-budget-hint-exhausted"),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Regenerar análisis/i }),
      ).toBeDisabled();
    });

    it("sin presupuesto agotado, 'Regenerar análisis' mide al menos 48 px y está habilitado", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        baseResponse,
      );

      render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );

      const btn = await screen.findByRole("button", {
        name: /Regenerar análisis/i,
      });
      expect(btn).not.toBeDisabled();
      expect(btn.className).toMatch(/min-h-\[48px\]/);
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

    it("un padre ve el análisis v2 colapsado vía StructuredInsight igual que el coach", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        v2Response,
      );

      render(
        <AnthropometricRecordExplanationCard
          athleteId={1}
          recordId={42}
          readOnly={true}
        />,
        { wrapper: withQuery() },
      );

      expect(
        await screen.findByTestId("structured-insight"),
      ).toBeInTheDocument();
      // Nunca un aviso de veredicto (solo-coach, FR-016) en modo padre.
      expect(
        screen.queryByTestId("record-explanation-verdict-marker"),
      ).not.toBeInTheDocument();
    });

    it("sin caché en modo padre → muestra el mensaje pasivo compartido (FR-033), nunca la sección vacía", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(null);

      render(
        <AnthropometricRecordExplanationCard
          athleteId={1}
          recordId={42}
          readOnly={true}
        />,
        { wrapper: withQuery() },
      );

      expect(
        await screen.findByTestId("record-explanation-empty"),
      ).toHaveTextContent(
        /Todavía no hay un análisis disponible\. El entrenador lo generará pronto\./,
      );
      expect(
        screen.queryByTestId("record-explanation-readonly"),
      ).not.toBeInTheDocument();
      // Nunca insinúa que el generar botón existe para un padre.
      expect(
        screen.queryByRole("button", { name: /Analizar|Regenerar/i }),
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

  // -------------------------------------------------------------------------
  // Accesibilidad (FR-034) — jest-axe sin violaciones, colapsado y expandido.
  // -------------------------------------------------------------------------

  describe("accesibilidad", () => {
    it("sin violaciones en el estado idle (coach, sin caché)", async () => {
      const { container } = render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );
      await screen.findByTestId("record-explanation-idle");
      expect(await axe(container)).toHaveNoViolations();
    });

    it("sin violaciones en éxito v1 (texto plano, sin StructuredInsight)", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        baseResponse,
      );

      const { container } = render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );
      await screen.findByTestId("record-explanation-success");
      expect(await axe(container)).toHaveNoViolations();
    });

    it("sin violaciones en éxito v2 con StructuredInsight colapsado", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        v2Response,
      );

      const { container } = render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );
      await screen.findByTestId("structured-insight");
      expect(
        screen.queryByTestId("structured-insight-details"),
      ).not.toBeInTheDocument();
      expect(await axe(container)).toHaveNoViolations();
    });

    it("sin violaciones en éxito v2 con StructuredInsight expandido", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        v2Response,
      );

      const { container } = render(
        <AnthropometricRecordExplanationCard athleteId={1} recordId={42} />,
        { wrapper: withQuery() },
      );
      const toggle = await screen.findByTestId("structured-insight-toggle");
      fireEvent.click(toggle);
      await screen.findByTestId("structured-insight-details");
      expect(await axe(container)).toHaveNoViolations();
    });

    it("sin violaciones en modo padre con el mensaje pasivo (sin caché)", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(null);

      const { container } = render(
        <AnthropometricRecordExplanationCard
          athleteId={1}
          recordId={42}
          readOnly
        />,
        { wrapper: withQuery() },
      );
      await screen.findByTestId("record-explanation-empty");
      expect(await axe(container)).toHaveNoViolations();
    });

    it("sin violaciones en modo padre con contenido v2 (StructuredInsight + disclaimer)", async () => {
      vi.mocked(aiApi.getMeasurementExplanationCached).mockResolvedValue(
        v2Response,
      );

      const { container } = render(
        <AnthropometricRecordExplanationCard
          athleteId={1}
          recordId={42}
          readOnly
        />,
        { wrapper: withQuery() },
      );
      await screen.findByTestId("structured-insight");
      expect(await axe(container)).toHaveNoViolations();
    });
  });
});
