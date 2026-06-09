/**
 * Tests vitest — CompetitionChatPanel (Feature 010, T026).
 *
 * Cubre:
 *  1. Send round-trip: user + assistant messages renderizan; race_event_id y
 *     stable session_id pasan al API en cada turno.
 *  2. Stable session_id across two turns (mismo valor en ambas llamadas).
 *  3. 503 → notice "El asistente de IA no está disponible…" + input deshabilitado.
 *  4. Error genérico → mensaje retry visible, historial previo intacto.
 *  5. Citations y tools_called se muestran cuando non-empty.
 *
 * Patrones: mismo approach que InsightsTab.test.tsx / GroupAnalysisPanel.test.tsx —
 *   vi.mock del módulo api, overrides per test.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosError } from "axios";

// ---------------------------------------------------------------------------
// Mock API module
// ---------------------------------------------------------------------------

const mockChatTurn = vi.fn();

vi.mock("@/api/raceAnalysis", () => ({
  chatTurn: (...args: unknown[]) => mockChatTurn(...args),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

import { CompetitionChatPanel } from "@/components/competitions/chat/CompetitionChatPanel";

function renderPanel(raceEventId = 42) {
  return render(<CompetitionChatPanel raceEventId={raceEventId} />);
}

/** Opens the collapsible panel. */
async function openPanel(user: ReturnType<typeof userEvent.setup>) {
  const toggle = screen.getByTestId("competition-chat-toggle");
  await user.click(toggle);
}

/** Types in the textarea and clicks send. */
async function sendQuery(
  user: ReturnType<typeof userEvent.setup>,
  text: string,
) {
  const input = screen.getByTestId("competition-chat-input");
  await user.type(input, text);
  const sendBtn = screen.getByTestId("competition-chat-send");
  await user.click(sendBtn);
}

const HAPPY_RESPONSE = {
  answer: "Isabel mejoró 2 posiciones respecto a Ginebra.",
  citations_used: ["copavalle_iv_2026"],
  tools_called: ["get_race_results"],
};

const EMPTY_RESPONSE = {
  answer: "Sin datos suficientes.",
  citations_used: [],
  tools_called: [],
};

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("CompetitionChatPanel — collapsible UI", () => {
  it("empieza colapsado y abre al hacer click en el toggle", async () => {
    const user = userEvent.setup();
    renderPanel();

    // Body not visible initially
    expect(screen.queryByTestId("competition-chat-body")).not.toBeInTheDocument();

    await openPanel(user);

    expect(screen.getByTestId("competition-chat-body")).toBeInTheDocument();
  });

  it("el header tiene aria-expanded correcto", async () => {
    const user = userEvent.setup();
    renderPanel();

    const toggle = screen.getByTestId("competition-chat-toggle");
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await openPanel(user);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });
});

describe("CompetitionChatPanel — send round-trip (T026 §1–2)", () => {
  it("renderiza mensaje de usuario y respuesta del asistente", async () => {
    mockChatTurn.mockResolvedValue(HAPPY_RESPONSE);
    const user = userEvent.setup();
    renderPanel(42);
    await openPanel(user);

    await sendQuery(user, "¿Quién mejoró más?");

    // User message visible
    await waitFor(() => {
      expect(screen.getByText("¿Quién mejoró más?")).toBeInTheDocument();
    });

    // Assistant message visible
    await waitFor(() => {
      expect(
        screen.getByText("Isabel mejoró 2 posiciones respecto a Ginebra."),
      ).toBeInTheDocument();
    });
  });

  it("pasa race_event_id correcto al API", async () => {
    mockChatTurn.mockResolvedValue(EMPTY_RESPONSE);
    const user = userEvent.setup();
    renderPanel(99);
    await openPanel(user);
    await sendQuery(user, "¿Cuál fue el mejor tiempo?");

    await waitFor(() => {
      expect(mockChatTurn).toHaveBeenCalledWith(
        expect.objectContaining({ race_event_id: 99 }),
      );
    });
  });

  it("usa el mismo session_id en dos turnos consecutivos", async () => {
    mockChatTurn.mockResolvedValue(EMPTY_RESPONSE);
    const user = userEvent.setup();
    renderPanel(42);
    await openPanel(user);

    // First turn
    await sendQuery(user, "Pregunta uno");
    await waitFor(() => expect(mockChatTurn).toHaveBeenCalledTimes(1));

    // Second turn — input should be clear now, type again
    await sendQuery(user, "Pregunta dos");
    await waitFor(() => expect(mockChatTurn).toHaveBeenCalledTimes(2));

    const call1 = mockChatTurn.mock.calls[0][0] as { session_id: string };
    const call2 = mockChatTurn.mock.calls[1][0] as { session_id: string };

    expect(call1.session_id).toBeTruthy();
    expect(call1.session_id).toBe(call2.session_id);
  });
});

describe("CompetitionChatPanel — 503 unavailable (T026 §3)", () => {
  it("muestra notice de no disponible y deshabilita el input", async () => {
    const err = {
      response: { status: 503 },
      message: "Service Unavailable",
    } as AxiosError;
    mockChatTurn.mockRejectedValue(err);

    const user = userEvent.setup();
    renderPanel(42);
    await openPanel(user);

    await sendQuery(user, "Consulta cualquiera");

    await waitFor(() => {
      expect(
        screen.getByTestId("competition-chat-unavailable"),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByText(
        /El asistente de IA no está disponible en este momento/i,
      ),
    ).toBeInTheDocument();

    // Input should be disabled (rendered inside the unavailable notice)
    const disabledArea = screen
      .getByTestId("competition-chat-unavailable")
      .querySelector("textarea");
    expect(disabledArea).toBeDisabled();
  });
});

describe("CompetitionChatPanel — error genérico retryable (T026 §4)", () => {
  it("muestra mensaje de error retryable con historial previo intacto", async () => {
    // First turn succeeds.
    mockChatTurn.mockResolvedValueOnce(EMPTY_RESPONSE);
    // Second turn fails with a non-503 error.
    mockChatTurn.mockRejectedValueOnce(new Error("Network Error"));

    const user = userEvent.setup();
    renderPanel(42);
    await openPanel(user);

    // First successful turn
    await sendQuery(user, "Primera consulta");
    await waitFor(() => {
      expect(screen.getByText("Primera consulta")).toBeInTheDocument();
    });

    // Second turn fails
    await sendQuery(user, "Segunda consulta");
    await waitFor(() => {
      expect(
        screen.getByTestId("competition-chat-turn-error"),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByText(/No se pudo obtener respuesta\. Intenta de nuevo\./i),
    ).toBeInTheDocument();

    // History from first turn still visible
    expect(screen.getByText("Primera consulta")).toBeInTheDocument();

    // Input NOT disabled — user can retry
    const input = screen.getByTestId("competition-chat-input");
    expect(input).not.toBeDisabled();
  });
});

describe("CompetitionChatPanel — citations y tools_called (T026 §5)", () => {
  it("muestra badges de citaciones y línea de herramientas", async () => {
    mockChatTurn.mockResolvedValue({
      answer: "Resultados de la válida IV.",
      citations_used: ["copavalle_iv_2026", "fixture_cali"],
      tools_called: ["get_race_results", "compare_seasons"],
    });

    const user = userEvent.setup();
    renderPanel(42);
    await openPanel(user);

    await sendQuery(user, "Dame los resultados");

    await waitFor(() => {
      expect(screen.getByText("copavalle_iv_2026")).toBeInTheDocument();
    });

    // Second citation
    expect(screen.getByText("fixture_cali")).toBeInTheDocument();

    // Tools line (partial match for the tools string)
    expect(
      screen.getByText(/herramientas:.*get_race_results/i),
    ).toBeInTheDocument();
  });

  it("NO muestra metadata de citaciones si están vacías", async () => {
    mockChatTurn.mockResolvedValue(EMPTY_RESPONSE);

    const user = userEvent.setup();
    renderPanel(42);
    await openPanel(user);

    await sendQuery(user, "Consulta");

    await waitFor(() => {
      expect(screen.getByText("Sin datos suficientes.")).toBeInTheDocument();
    });

    expect(screen.queryByText(/herramientas:/i)).not.toBeInTheDocument();
  });
});
