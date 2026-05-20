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
  chatTurn: vi.fn(),
}));

import * as raceApi from "@/api/raceAnalysis";

import { ChatConsole } from "@/components/ai/ChatConsole";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

describe("ChatConsole", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renderiza estado inicial vacío", () => {
    wrap(<ChatConsole />);
    expect(screen.getByText(/Haz una pregunta/i)).toBeInTheDocument();
    expect(screen.getByTestId("chat-input")).toBeInTheDocument();
    expect(screen.getByTestId("chat-submit")).toBeDisabled();
  });

  it("submit activa la mutation y agrega mensajes user + assistant", async () => {
    vi.mocked(raceApi.chatTurn).mockResolvedValue({
      answer: "Respuesta del agente con citas.",
      citations_used: ["c1", "c2"],
      tools_called: ["fetch_athlete_progression"],
    });
    const user = userEvent.setup();
    wrap(<ChatConsole athleteId={42} />);

    await user.type(screen.getByTestId("chat-input"), "Hola?");
    await user.click(screen.getByTestId("chat-submit"));

    await waitFor(() => {
      expect(raceApi.chatTurn).toHaveBeenCalledWith(
        expect.objectContaining({
          query: "Hola?",
          athlete_id: 42,
        }),
      );
    });
    // Mensaje user visible
    expect(screen.getByText("Hola?")).toBeInTheDocument();
    // Mensaje assistant visible
    expect(
      await screen.findByText(/Respuesta del agente/),
    ).toBeInTheDocument();
    expect(screen.getByTestId("chat-message-tools")).toHaveTextContent(
      /fetch_athlete_progression/,
    );
    expect(screen.getByTestId("chat-message-citations")).toHaveTextContent(
      /c1, c2/,
    );
  });

  it("muestra mensaje de error si la API falla", async () => {
    vi.mocked(raceApi.chatTurn).mockRejectedValue(new Error("502 Bad Gateway"));
    const user = userEvent.setup();
    wrap(<ChatConsole />);
    await user.type(screen.getByTestId("chat-input"), "?");
    await user.click(screen.getByTestId("chat-submit"));
    expect(await screen.findByText(/502 Bad Gateway/)).toBeInTheDocument();
  });

  it("limpia el input tras submit exitoso", async () => {
    vi.mocked(raceApi.chatTurn).mockResolvedValue({
      answer: "ok",
      citations_used: [],
      tools_called: [],
    });
    const user = userEvent.setup();
    wrap(<ChatConsole />);
    const input = screen.getByTestId("chat-input") as HTMLInputElement;
    await user.type(input, "ping");
    await user.click(screen.getByTestId("chat-submit"));
    await waitFor(() => expect(input.value).toBe(""));
  });

  it("usa el mismo session_id en peticiones consecutivas", async () => {
    vi.mocked(raceApi.chatTurn).mockResolvedValue({
      answer: "ok",
      citations_used: [],
      tools_called: [],
    });
    const user = userEvent.setup();
    wrap(<ChatConsole />);
    const input = screen.getByTestId("chat-input");
    await user.type(input, "a");
    await user.click(screen.getByTestId("chat-submit"));
    await waitFor(() => expect(raceApi.chatTurn).toHaveBeenCalledTimes(1));
    await user.type(input, "b");
    await user.click(screen.getByTestId("chat-submit"));
    await waitFor(() => expect(raceApi.chatTurn).toHaveBeenCalledTimes(2));

    const firstSession = (raceApi.chatTurn as ReturnType<typeof vi.fn>).mock
      .calls[0][0].session_id;
    const secondSession = (raceApi.chatTurn as ReturnType<typeof vi.fn>).mock
      .calls[1][0].session_id;
    expect(firstSession).toBe(secondSession);
    expect(typeof firstSession).toBe("string");
    expect(firstSession.length).toBeGreaterThan(0);
  });
});
