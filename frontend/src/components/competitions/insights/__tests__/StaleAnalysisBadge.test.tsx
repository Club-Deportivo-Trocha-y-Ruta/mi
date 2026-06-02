/**
 * Tests del StaleAnalysisBadge (PR5).
 *
 * Cubre:
 *  - Renderiza el badge "Análisis desactualizado" + botón Re-ejecutar.
 *  - Click en Re-ejecutar abre confirmación (D5: manual + confirmación).
 *  - Confirmar dispara la mutación y llama onReExecuted con el nuevo run_id.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const mockMutate = vi.fn();
let mockIsPending = false;
vi.mock("@/hooks/ai/useRaceRun", () => ({
  useReExecuteRun: () => ({ mutate: mockMutate, isPending: mockIsPending }),
}));

import { StaleAnalysisBadge } from "@/components/competitions/insights/StaleAnalysisBadge";

beforeEach(() => {
  vi.clearAllMocks();
  mockIsPending = false;
});

describe("StaleAnalysisBadge", () => {
  it("muestra el badge y el botón re-ejecutar", () => {
    render(<StaleAnalysisBadge runId="run-abc" />);
    expect(screen.getByTestId("stale-analysis-badge")).toBeInTheDocument();
    expect(screen.getByText(/Análisis desactualizado/i)).toBeInTheDocument();
    expect(screen.getByTestId("stale-reexecute-button")).toBeInTheDocument();
  });

  it("click en re-ejecutar abre confirmación (no dispara aún la mutación)", async () => {
    const user = userEvent.setup();
    render(<StaleAnalysisBadge runId="run-abc" />);
    await user.click(screen.getByTestId("stale-reexecute-button"));
    expect(screen.getByText(/Se generará un nuevo análisis/i)).toBeInTheDocument();
    expect(mockMutate).not.toHaveBeenCalled();
  });

  it("confirmar dispara la mutación con el runId y llama onReExecuted", async () => {
    const onReExecuted = vi.fn();
    mockMutate.mockImplementation((_runId, opts) => {
      opts?.onSuccess?.({ run_id: "new-run" });
    });
    const user = userEvent.setup();
    render(<StaleAnalysisBadge runId="run-abc" onReExecuted={onReExecuted} />);

    await user.click(screen.getByTestId("stale-reexecute-button"));
    // Botón de confirmación dentro del modal.
    const confirmBtn = screen.getByRole("button", { name: "Re-ejecutar" });
    await user.click(confirmBtn);

    await waitFor(() =>
      expect(mockMutate).toHaveBeenCalledWith("run-abc", expect.any(Object)),
    );
    expect(onReExecuted).toHaveBeenCalledWith("new-run");
  });
});
