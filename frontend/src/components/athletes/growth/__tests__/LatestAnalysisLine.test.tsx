/**
 * LatestAnalysisLine.test.tsx — feature 042, Wave 3 (T073).
 *
 * Cubre los siete estados descritos en el docstring del componente y el
 * contrato `contracts/growth-summary-latest-analysis.md` + FR-027/FR-016:
 * not-rendered, loading, none (coach/familia), current, stale
 * (coach/familia), flagged (coach/familia-defensivo) y error.
 *
 * `AnthropometricRecordExplanationCard` se mockea: su propio
 * comportamiento (idle/pending/success/error, gating por rol, etc.) ya
 * tiene su propia suite. Aquí solo interesa que el diálogo de esta fila lo
 * monte con los props correctos (`athleteId`, `recordId`, `readOnly`)
 * cuando el enlace se abre.
 *
 * Privacidad Ley 1581: fixtures 100% sintéticas.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UseQueryResult } from "@tanstack/react-query";
import { axe } from "jest-axe";

vi.mock("@/components/ai/AnthropometricRecordExplanationCard", () => ({
  AnthropometricRecordExplanationCard: ({
    athleteId,
    recordId,
    readOnly,
  }: {
    athleteId: number;
    recordId: number;
    readOnly?: boolean;
  }) => (
    <div
      data-testid="mock-record-explanation-card"
      data-athlete-id={athleteId}
      data-record-id={recordId}
      data-readonly={readOnly ?? false}
    >
      mock explanation
    </div>
  ),
}));

import { LatestAnalysisLine } from "@/components/athletes/growth/LatestAnalysisLine";
import { AI_ANALYSIS_NOT_YET_AVAILABLE_MESSAGE } from "@/lib/ai/notYetAvailableMessage";
import { MaturationStatus } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { CriticVerdict } from "@/types/ai.types";
import type { GrowthSummary, LatestAiAnalysis } from "@/types/growth.types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRecord(overrides: Partial<AnthropometricRecord> = {}): AnthropometricRecord {
  return {
    id: 41,
    athlete_id: 2,
    evaluation_date: "2026-08-14",
    weight_kg: 45.0,
    standing_height_cm: 150.0,
    arm_span_cm: null,
    sitting_height_cm: 78.0,
    leg_length_cm: 72.0,
    leg_sitting_ratio: 0.923,
    maturity_offset: 1.2,
    age_at_phv: 12.9,
    maturation_status: MaturationStatus.PostPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-08-14T10:00:00",
    notes: null,
    ...overrides,
  };
}

function makeAnalysis(overrides: Partial<LatestAiAnalysis> = {}): LatestAiAnalysis {
  return {
    record_id: 41,
    generated_at: "2026-08-14T12:00:00Z",
    schema_version: "v2",
    summary_line: "Talla estable, sin cambios relevantes frente a la medición anterior.",
    has_warning_signs: false,
    critic_verdict: "approved" as CriticVerdict,
    is_stale: false,
    ...overrides,
  };
}

function makeSummary(overrides: Partial<GrowthSummary> = {}): GrowthSummary {
  return {
    athlete_id: 2,
    computed_at: "2026-09-04",
    records_count: 1,
    latest_evaluation_date: "2026-08-14",
    stage: MaturationStatus.PostPHV,
    maturity_offset: 1.2,
    age_at_phv: 12.9,
    months_from_phv: 16.4,
    velocity: null,
    measurement: {
      status: "ok",
      interval_days: 120,
      next_due_date: "2026-12-12",
      days_overdue: null,
    },
    alerts: [],
    latest: null,
    ...overrides,
  };
}

function makeSummaryQuery(
  overrides: Partial<UseQueryResult<GrowthSummary, Error>> = {},
): UseQueryResult<GrowthSummary, Error> {
  return {
    isLoading: false,
    isError: false,
    data: makeSummary(),
    error: null,
    ...overrides,
  } as UseQueryResult<GrowthSummary, Error>;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("LatestAnalysisLine", () => {
  describe("not-rendered", () => {
    it("no renderiza nada cuando el atleta no tiene mediciones", () => {
      const { container } = render(
        <LatestAnalysisLine
          summaryQuery={makeSummaryQuery({ data: makeSummary({ records_count: 0 }) })}
          records={[]}
          athleteId={2}
          mode="coach"
        />,
      );
      expect(container).toBeEmptyDOMElement();
    });
  });

  describe("loading", () => {
    it('muestra un estado de carga (role="status") mientras el resumen no resuelve', () => {
      render(
        <LatestAnalysisLine
          summaryQuery={makeSummaryQuery({ isLoading: true, data: undefined })}
          records={[]}
          athleteId={2}
          mode="coach"
        />,
      );
      const line = screen.getByTestId("latest-analysis-line");
      expect(line).toHaveAttribute("data-state", "loading");
      expect(screen.getByRole("status")).toBeInTheDocument();
    });
  });

  describe("error", () => {
    it("muestra un mensaje discreto cuando la petición del resumen falla", () => {
      render(
        <LatestAnalysisLine
          summaryQuery={makeSummaryQuery({
            isError: true,
            data: undefined,
            error: new Error("network"),
          })}
          records={[]}
          athleteId={2}
          mode="coach"
        />,
      );
      const line = screen.getByTestId("latest-analysis-line");
      expect(line).toHaveAttribute("data-state", "error");
      expect(
        screen.getByText("No se pudo cargar el estado del análisis de IA."),
      ).toBeInTheDocument();
    });
  });

  describe("none", () => {
    it("coach: muestra el mensaje accionable y un enlace para generar", async () => {
      const user = userEvent.setup();
      const record = makeRecord();
      render(
        <LatestAnalysisLine
          summaryQuery={makeSummaryQuery({
            data: makeSummary({ latest_ai_analysis: null }),
          })}
          records={[record]}
          athleteId={2}
          mode="coach"
        />,
      );
      const line = screen.getByTestId("latest-analysis-line");
      expect(line).toHaveAttribute("data-state", "none");
      expect(
        screen.getByText("Aún no hay un análisis de IA para la medición más reciente."),
      ).toBeInTheDocument();

      const link = screen.getByTestId("latest-analysis-line-link");
      expect(link).toHaveTextContent("Generar análisis");
      expect(screen.queryByTestId("mock-record-explanation-card")).not.toBeInTheDocument();

      await user.click(link);
      const card = await screen.findByTestId("mock-record-explanation-card");
      expect(card).toHaveAttribute("data-athlete-id", "2");
      expect(card).toHaveAttribute("data-record-id", String(record.id));
      expect(card).toHaveAttribute("data-readonly", "false");
    });

    it("familia: solo muestra el mensaje pasivo compartido, sin enlace ni acción de generar", () => {
      render(
        <LatestAnalysisLine
          summaryQuery={makeSummaryQuery({
            data: makeSummary({ latest_ai_analysis: null }),
          })}
          records={[makeRecord()]}
          athleteId={2}
          mode="parent"
        />,
      );
      const line = screen.getByTestId("latest-analysis-line");
      expect(line).toHaveAttribute("data-state", "none");
      expect(
        screen.getByText(AI_ANALYSIS_NOT_YET_AVAILABLE_MESSAGE),
      ).toBeInTheDocument();
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
      expect(screen.queryByTestId("latest-analysis-line-link")).not.toBeInTheDocument();
    });
  });

  describe("current", () => {
    it("muestra la línea de resumen, la fecha de la medición y el enlace, en modo coach", async () => {
      const user = userEvent.setup();
      const record = makeRecord();
      const analysis = makeAnalysis();
      render(
        <LatestAnalysisLine
          summaryQuery={makeSummaryQuery({
            data: makeSummary({ latest_ai_analysis: analysis }),
          })}
          records={[record]}
          athleteId={2}
          mode="coach"
        />,
      );
      const line = screen.getByTestId("latest-analysis-line");
      expect(line).toHaveAttribute("data-state", "current");
      expect(screen.getByText(analysis.summary_line)).toBeInTheDocument();
      expect(screen.getByText("Medición del 14 ago 2026")).toBeInTheDocument();
      expect(screen.queryByText("Desactualizado")).not.toBeInTheDocument();

      const link = screen.getByTestId("latest-analysis-line-link");
      expect(link).toHaveTextContent("Ver análisis completo");
      await user.click(link);
      const card = await screen.findByTestId("mock-record-explanation-card");
      expect(card).toHaveAttribute("data-readonly", "false");
    });

    it("en modo familia el enlace abre el diálogo de solo lectura", async () => {
      const user = userEvent.setup();
      const record = makeRecord();
      const analysis = makeAnalysis();
      render(
        <LatestAnalysisLine
          summaryQuery={makeSummaryQuery({
            data: makeSummary({ latest_ai_analysis: analysis }),
          })}
          records={[record]}
          athleteId={2}
          mode="parent"
        />,
      );
      await user.click(screen.getByTestId("latest-analysis-line-link"));
      const card = await screen.findByTestId("mock-record-explanation-card");
      expect(card).toHaveAttribute("data-readonly", "true");
    });

    it("omite el enlace si la medición analizada todavía no está cargada", () => {
      const analysis = makeAnalysis({ record_id: 999 });
      render(
        <LatestAnalysisLine
          summaryQuery={makeSummaryQuery({
            data: makeSummary({ latest_ai_analysis: analysis }),
          })}
          records={[]}
          athleteId={2}
          mode="coach"
        />,
      );
      expect(screen.getByText(analysis.summary_line)).toBeInTheDocument();
      expect(screen.queryByTestId("latest-analysis-line-link")).not.toBeInTheDocument();
      expect(screen.queryByText(/Medición del/)).not.toBeInTheDocument();
    });
  });

  describe("stale", () => {
    it('coach: agrega la insignia "Desactualizado" y mantiene el resumen anterior legible', () => {
      const analysis = makeAnalysis({ is_stale: true });
      render(
        <LatestAnalysisLine
          summaryQuery={makeSummaryQuery({
            data: makeSummary({ latest_ai_analysis: analysis }),
          })}
          records={[makeRecord()]}
          athleteId={2}
          mode="coach"
        />,
      );
      const line = screen.getByTestId("latest-analysis-line");
      expect(line).toHaveAttribute("data-state", "stale");
      expect(screen.getByText("Desactualizado")).toBeInTheDocument();
      // El resumen anterior sigue siendo legible — no se oculta ni se
      // reemplaza por un mensaje de error (data-model.md §4).
      expect(screen.getByText(analysis.summary_line)).toBeInTheDocument();
    });

    it("familia: se ve idéntico al estado 'current' — sin la palabra 'Desactualizado'", () => {
      const analysis = makeAnalysis({ is_stale: true });
      render(
        <LatestAnalysisLine
          summaryQuery={makeSummaryQuery({
            data: makeSummary({ latest_ai_analysis: analysis }),
          })}
          records={[makeRecord()]}
          athleteId={2}
          mode="parent"
        />,
      );
      const line = screen.getByTestId("latest-analysis-line");
      // El estado interno sigue siendo "stale" (para poder probarlo), pero
      // la redacción de "Desactualizado" nunca llega a una familia.
      expect(line).toHaveAttribute("data-state", "stale");
      expect(screen.queryByText("Desactualizado")).not.toBeInTheDocument();
      expect(screen.getByText(analysis.summary_line)).toBeInTheDocument();
    });
  });

  describe("flagged", () => {
    it("coach: muestra el resumen con la nota de observaciones y 'Revisar análisis'", () => {
      const analysis = makeAnalysis({ critic_verdict: "flagged" });
      render(
        <LatestAnalysisLine
          summaryQuery={makeSummaryQuery({
            data: makeSummary({ latest_ai_analysis: analysis }),
          })}
          records={[makeRecord()]}
          athleteId={2}
          mode="coach"
        />,
      );
      const line = screen.getByTestId("latest-analysis-line");
      expect(line).toHaveAttribute("data-state", "flagged");
      expect(screen.getByText(analysis.summary_line)).toBeInTheDocument();
      expect(screen.getByTestId("latest-analysis-line-verdict-note")).toBeInTheDocument();
      expect(screen.getByTestId("latest-analysis-line-link")).toHaveTextContent(
        "Revisar análisis",
      );
    });

    it.each(["flagged", "fallback", "skipped"] as const)(
      "familia: un veredicto bloqueado (%s) que llegara por error se trata igual que 'sin análisis' (FR-016)",
      (verdict) => {
        const analysis = makeAnalysis({ critic_verdict: verdict });
        render(
          <LatestAnalysisLine
            summaryQuery={makeSummaryQuery({
              data: makeSummary({ latest_ai_analysis: analysis }),
            })}
            records={[makeRecord()]}
            athleteId={2}
            mode="parent"
          />,
        );
        const line = screen.getByTestId("latest-analysis-line");
        expect(line).toHaveAttribute("data-state", "none");
        expect(
          screen.getByText(AI_ANALYSIS_NOT_YET_AVAILABLE_MESSAGE),
        ).toBeInTheDocument();
        // Nunca debe insinuarse que existe un análisis retenido: ni el
        // resumen real, ni la nota de veredicto, ni un enlace.
        expect(screen.queryByText(analysis.summary_line)).not.toBeInTheDocument();
        expect(
          screen.queryByTestId("latest-analysis-line-verdict-note"),
        ).not.toBeInTheDocument();
        expect(screen.queryByTestId("latest-analysis-line-link")).not.toBeInTheDocument();
      },
    );
  });

  describe("privacidad — nunca expone detalles técnicos", () => {
    it("no renderiza el veredicto crudo, un slug de modelo ni un id de traza", () => {
      const analysis = makeAnalysis({ critic_verdict: "flagged" });
      render(
        <LatestAnalysisLine
          summaryQuery={makeSummaryQuery({
            data: makeSummary({ latest_ai_analysis: analysis }),
          })}
          records={[makeRecord()]}
          athleteId={2}
          mode="coach"
        />,
      );
      expect(screen.queryByText(/flagged/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/gemini|gpt|claude|anthropic|openai/i)).not.toBeInTheDocument();
    });
  });

  describe("accesibilidad", () => {
    it("sin violaciones jest-axe en el estado 'current' (coach)", async () => {
      const { container } = render(
        <LatestAnalysisLine
          summaryQuery={makeSummaryQuery({
            data: makeSummary({ latest_ai_analysis: makeAnalysis() }),
          })}
          records={[makeRecord()]}
          athleteId={2}
          mode="coach"
        />,
      );
      expect(await axe(container)).toHaveNoViolations();
    });

    it("sin violaciones jest-axe en el estado 'none' (familia)", async () => {
      const { container } = render(
        <LatestAnalysisLine
          summaryQuery={makeSummaryQuery({
            data: makeSummary({ latest_ai_analysis: null }),
          })}
          records={[makeRecord()]}
          athleteId={2}
          mode="parent"
        />,
      );
      expect(await axe(container)).toHaveNoViolations();
    });
  });
});
