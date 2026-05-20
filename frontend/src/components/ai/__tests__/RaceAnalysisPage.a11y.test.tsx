/**
 * A11y test (jest-axe) para RaceAnalysisPage + HITLApprovalCard.
 *
 * Renderiza la página sin run activo (estado inicial) y verifica que no
 * haya violaciones serias/críticas. Mockea la API para evitar
 * llamadas reales. La página requiere el store de auth pero como sólo
 * usamos PdfDownloadButton dentro de un render lazy, no es necesario
 * setearlo aquí.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { createElement, type ReactNode } from "react";

vi.mock("@/api/raceAnalysis", () => ({
  startRun: vi.fn(),
  getRunStatus: vi.fn(),
  submitHITLDecision: vi.fn(),
  getRunResult: vi.fn(),
  chatTurn: vi.fn(),
  downloadRunPdf: vi.fn(),
  getRunPdfPath: vi.fn(),
}));

import { HITLApprovalCard } from "@/components/ai/HITLApprovalCard";
import { RaceAnalysisPage } from "@/routes/results/RaceAnalysisPage";
import { useExplainModeStore } from "@/store/explainMode.store";

expect.extend(toHaveNoViolations);

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(MemoryRouter, null, ui),
    ),
  );
}

describe("a11y: race-analysis", () => {
  beforeEach(() => {
    useExplainModeStore.setState({ enabled: false });
  });

  it("RaceAnalysisPage no tiene violaciones serias/críticas", async () => {
    const { container } = wrap(<RaceAnalysisPage />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("HITLApprovalCard no tiene violaciones serias/críticas", async () => {
    const { container } = wrap(
      <HITLApprovalCard
        runId="r1"
        stepId="hitl_1"
        draftMarkdown="# Borrador\n\nPárrafo de prueba."
        principlesCited={["c1"]}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
