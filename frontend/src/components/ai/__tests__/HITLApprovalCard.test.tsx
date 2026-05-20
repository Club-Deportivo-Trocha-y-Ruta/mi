import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

vi.mock("@/api/raceAnalysis", () => ({
  startRun: vi.fn(),
  getRunStatus: vi.fn(),
  submitHITLDecision: vi.fn(),
  getRunResult: vi.fn(),
}));

import * as raceApi from "@/api/raceAnalysis";

import { HITLApprovalCard } from "@/components/ai/HITLApprovalCard";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

const ACK = {
  accepted: true,
  run_id: "r1",
  step_id: "hitl_1",
  next_state: "running" as const,
};

describe("HITLApprovalCard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renderiza draft + acciones aprobar/editar/rechazar", () => {
    wrap(
      <HITLApprovalCard
        runId="r1"
        stepId="hitl_1"
        draftMarkdown="# Draft de prueba"
      />,
    );
    expect(screen.getByRole("region", { name: /revisión humana/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Draft de prueba" })).toBeInTheDocument();
    expect(screen.getByTestId("hitl-approve-button")).toBeInTheDocument();
    expect(screen.getByTestId("hitl-edit-button")).toBeInTheDocument();
    expect(screen.getByTestId("hitl-reject-button")).toBeInTheDocument();
  });

  it("Aprobar dispara mutation con decision=approve", async () => {
    vi.mocked(raceApi.submitHITLDecision).mockResolvedValue(ACK);
    const onSubmitted = vi.fn();
    wrap(
      <HITLApprovalCard
        runId="r1"
        stepId="hitl_1"
        draftMarkdown="texto"
        onSubmitted={onSubmitted}
      />,
    );
    await userEvent.setup().click(screen.getByTestId("hitl-approve-button"));
    await waitFor(() =>
      expect(raceApi.submitHITLDecision).toHaveBeenCalledWith(
        "r1",
        "hitl_1",
        { decision: "approve" },
      ),
    );
    expect(onSubmitted).toHaveBeenCalledWith("approve");
  });

  it("Rechazar incluye notes opcionales", async () => {
    const user = userEvent.setup();
    vi.mocked(raceApi.submitHITLDecision).mockResolvedValue(ACK);
    wrap(
      <HITLApprovalCard runId="r1" stepId="hitl_1" draftMarkdown="t" />,
    );
    await user.type(
      screen.getByTestId("hitl-reject-notes-input"),
      "No cumple principios LTAD",
    );
    await user.click(screen.getByTestId("hitl-reject-button"));
    await waitFor(() =>
      expect(raceApi.submitHITLDecision).toHaveBeenCalledWith(
        "r1",
        "hitl_1",
        { decision: "reject", notes: "No cumple principios LTAD" },
      ),
    );
  });

  it("muestra feedback del crítico cuando se provee", () => {
    wrap(
      <HITLApprovalCard
        runId="r1"
        stepId="hitl_1"
        draftMarkdown="t"
        criticFeedback={[
          { section: "Recomendaciones", problem: "Sin evidencia LTAD" },
        ]}
      />,
    );
    expect(screen.getByTestId("hitl-critic-feedback")).toBeInTheDocument();
    expect(screen.getByText(/Sin evidencia LTAD/)).toBeInTheDocument();
  });

  it("muestra error cuando la mutation falla", async () => {
    vi.mocked(raceApi.submitHITLDecision).mockRejectedValue(
      new Error("422 invalid edits"),
    );
    const user = userEvent.setup();
    wrap(
      <HITLApprovalCard runId="r1" stepId="hitl_1" draftMarkdown="t" />,
    );
    await user.click(screen.getByTestId("hitl-approve-button"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /422 invalid edits/i,
    );
  });
});
