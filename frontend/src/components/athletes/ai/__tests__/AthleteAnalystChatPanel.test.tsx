/**
 * Tests vitest — AthleteAnalystChatPanel (feature 037, T302).
 *
 * Cubre:
 *  - envía `athlete_id` (no `race_event_id`) en cada turno.
 *  - clic en un chip de sugerencia rellena el input sin enviar solo.
 *  - render de la respuesta del asistente.
 *  - a11y cero violaciones.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

const mockChatTurn = vi.fn();

vi.mock("@/api/raceAnalysis", () => ({
  chatTurn: (...args: unknown[]) => mockChatTurn(...args),
}));

import { AthleteAnalystChatPanel } from "@/components/athletes/ai/AthleteAnalystChatPanel";

function renderPanel(athleteId = 42) {
  return render(<AthleteAnalystChatPanel athleteId={athleteId} />);
}

describe("AthleteAnalystChatPanel", () => {
  beforeEach(() => {
    mockChatTurn.mockReset();
  });

  it("envía athlete_id (no race_event_id) al hacer una consulta", async () => {
    mockChatTurn.mockResolvedValueOnce({
      answer: "La válida IV mostró una caída en el ritmo del segundo giro.",
      citations_used: [],
      tools_called: [],
    });
    const user = userEvent.setup();
    renderPanel(42);

    await user.type(
      screen.getByTestId("athlete-analyst-chat-input"),
      "¿Qué explica el resultado de la última válida?",
    );
    await user.click(screen.getByTestId("athlete-analyst-chat-send"));

    await waitFor(() => {
      expect(mockChatTurn).toHaveBeenCalledWith(
        expect.objectContaining({
          athlete_id: 42,
          query: "¿Qué explica el resultado de la última válida?",
        }),
      );
    });
    expect(mockChatTurn.mock.calls[0][0].race_event_id).toBeUndefined();

    await screen.findByText(
      "La válida IV mostró una caída en el ritmo del segundo giro.",
    );
  });

  it("un chip de sugerencia rellena el input sin enviar la consulta automáticamente", async () => {
    const user = userEvent.setup();
    renderPanel();

    const chips = screen.getAllByTestId("athlete-analyst-chat-suggestion-chip");
    expect(chips.length).toBeGreaterThan(0);
    await user.click(chips[0]);

    expect(screen.getByTestId("athlete-analyst-chat-input")).toHaveValue(
      chips[0].textContent,
    );
    expect(mockChatTurn).not.toHaveBeenCalled();
  });

  it("a11y — cero violaciones", async () => {
    const { container } = renderPanel();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
