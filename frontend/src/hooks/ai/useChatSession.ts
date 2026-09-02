/**
 * useChatSession — lógica compartida del chat de IA (feature 037, T302).
 *
 * Extraída de `CompetitionChatPanel` (feature 010) para reutilizarla en
 * `AthleteAnalystChatPanel` sin duplicar el manejo de sesión, mensajes,
 * pending y errores. Mismas reglas de negocio:
 *  - session_id estable por montaje (crypto.randomUUID(), in-memory TTL
 *    1h en el servidor — el frontend no persiste historial).
 *  - 503 → "unavailable" (input deshabilitado); otros errores →
 *    "turn_error" (retryable, historial intacto).
 *
 * `scope` fija el resto de campos de `ChatRequestBody` (race_event_id
 * para el chat scopeado a una válida, athlete_id para el chat del
 * atleta) — se envían tal cual en cada turno.
 */
import { useRef, useState } from "react";
import type { AxiosError } from "axios";

import { chatTurn } from "@/api/raceAnalysis";
import type { ChatMessage } from "@/types/raceAnalysis.types";

export type ChatSessionError =
  | { kind: "unavailable" } // 503 — AI disabled
  | { kind: "turn_error" }; // other errors — retryable, history intact

export interface ChatSessionScope {
  raceEventId?: number;
  athleteId?: number;
}

function buildUserMessage(content: string): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: "user",
    content,
    ts: new Date().toISOString(),
  };
}

function buildAssistantMessage(
  answer: string,
  citations: string[],
  tools: string[],
): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    content: answer,
    citations: citations.length > 0 ? citations : undefined,
    toolsCalled: tools.length > 0 ? tools : undefined,
    ts: new Date().toISOString(),
  };
}

export function useChatSession(scope: ChatSessionScope) {
  // Stable session_id per mount.
  const sessionIdRef = useRef<string>(crypto.randomUUID());

  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<ChatSessionError | null>(null);

  // Used to scroll to the bottom of the message list after each new message.
  const listEndRef = useRef<HTMLDivElement>(null);

  async function sendMessage() {
    const trimmed = query.trim();
    if (!trimmed || isPending || error?.kind === "unavailable") return;

    // Optimistically append user message and clear input.
    const userMsg = buildUserMessage(trimmed);
    setMessages((prev) => [...prev, userMsg]);
    setQuery("");
    setIsPending(true);
    setError(null);

    try {
      const response = await chatTurn({
        session_id: sessionIdRef.current,
        query: trimmed,
        race_event_id: scope.raceEventId,
        athlete_id: scope.athleteId,
      });

      const assistantMsg = buildAssistantMessage(
        response.answer,
        response.citations_used,
        response.tools_called,
      );
      setMessages((prev) => [...prev, assistantMsg]);

      // Scroll into view (guard for jsdom which lacks scrollIntoView).
      setTimeout(() => {
        if (typeof listEndRef.current?.scrollIntoView === "function") {
          listEndRef.current.scrollIntoView({ behavior: "smooth" });
        }
      }, 50);
    } catch (err) {
      const axiosErr = err as AxiosError;
      if (axiosErr?.response?.status === 503) {
        setError({ kind: "unavailable" });
      } else {
        setError({ kind: "turn_error" });
      }
    } finally {
      setIsPending(false);
    }
  }

  const inputDisabled = isPending || error?.kind === "unavailable";

  return {
    query,
    setQuery,
    messages,
    isPending,
    error,
    inputDisabled,
    sendMessage,
    listEndRef,
  };
}
