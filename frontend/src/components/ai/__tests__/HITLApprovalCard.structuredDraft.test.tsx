/**
 * HITLApprovalCard — borrador estructurado v3 (feature 037, T301).
 *
 * `structured_draft` llega en `payload.structured_draft` del evento
 * `hitl_request`/`hitl_required` (nodo `hitl_gate_review`) — cuando la
 * card lo recibe, la vista de lectura muestra `<InsightV3Card
 * mode="coach">` en vez del markdown crudo. El editor de "Editar" sigue
 * intacto (opera sobre `draftMarkdown`).
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

vi.mock("@/api/raceAnalysis", () => ({
  startRun: vi.fn(),
  getRunStatus: vi.fn(),
  submitHITLDecision: vi.fn(),
  getRunResult: vi.fn(),
  cancelRun: vi.fn(),
}));

import { HITLApprovalCard } from "@/components/ai/HITLApprovalCard";
import { buildInsightV3 } from "@/test/fixtures/insightV3";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

describe("HITLApprovalCard — structuredDraft", () => {
  it("renderiza InsightV3Card en vez del markdown crudo cuando structuredDraft está presente", () => {
    const structured = buildInsightV3();
    wrap(
      <HITLApprovalCard
        runId="r1"
        stepId="hitl_1"
        draftMarkdown="# Draft markdown (no debería verse)"
        structuredDraft={structured}
      />,
    );

    expect(screen.getByTestId("insight-v3-card")).toBeInTheDocument();
    expect(screen.getByTestId("insight-v3-headline")).toHaveTextContent(
      structured.headline,
    );
    expect(screen.queryByTestId("markdown-viewer")).not.toBeInTheDocument();
    // La card se monta en modo lectura — sin footer/CoachAnswerForm.
    expect(screen.queryByTestId("coach-answer-form")).not.toBeInTheDocument();
    // Las acciones HITL (aprobar/editar/rechazar) se conservan intactas.
    expect(screen.getByTestId("hitl-approve-button")).toBeInTheDocument();
    expect(screen.getByTestId("hitl-edit-button")).toBeInTheDocument();
  });

  it("sin structuredDraft (runs v2) cae al markdown crudo, sin cambios", () => {
    wrap(
      <HITLApprovalCard
        runId="r1"
        stepId="hitl_1"
        draftMarkdown="# Draft de prueba v2"
      />,
    );

    expect(screen.queryByTestId("insight-v3-card")).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Draft de prueba v2" }),
    ).toBeInTheDocument();
  });
});
