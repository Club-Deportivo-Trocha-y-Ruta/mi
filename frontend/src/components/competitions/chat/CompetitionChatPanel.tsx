/**
 * CompetitionChatPanel — chat de IA scopeado a una válida concreta.
 *
 * Genera un session_id por montaje (crypto.randomUUID()) y lo mantiene
 * estable durante toda la sesión (useRef). Las sesiones son in-memory en
 * el servidor con TTL de 1 hora; el frontend no persiste el historial.
 *
 * Comportamiento:
 *  - Colapsable ("Preguntar a la IA" header con chevron), colapsado por defecto.
 *  - Mensajes: usuario a la derecha, asistente a la izquierda.
 *  - Mensajes asistente: badges de citaciones (citations_used) y línea de
 *    herramientas (tools_called) cuando non-empty.
 *  - Enter envía, Shift+Enter inserta salto de línea.
 *  - Pending: botón deshabilitado + "Pensando…".
 *  - 503 → notice "El asistente de IA no está disponible…" con input deshabilitado.
 *  - Otros errores → mensaje inline retryable, historial intacto.
 *  - aria-live="polite" para nuevos mensajes del asistente.
 *
 * Props: { raceEventId: number }
 * Visibilidad: controlada por InsightsTab (solo coach/admin).
 */
import { useRef, useState } from "react";
import { ChevronDown, ChevronUp, MessageSquare, Send } from "lucide-react";
import type { AxiosError } from "axios";

import { chatTurn } from "@/api/raceAnalysis";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/raceAnalysis.types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type PanelError =
  | { kind: "unavailable" }          // 503 — AI disabled
  | { kind: "turn_error" };          // other errors — retryable, history intact

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function CitationBadge({ citation }: { citation: string }) {
  return (
    <Badge
      variant="secondary"
      className="text-xs px-1.5 py-0.5 font-normal"
      title={citation}
    >
      {citation.length > 24 ? `${citation.slice(0, 24)}…` : citation}
    </Badge>
  );
}

interface MessageBubbleProps {
  message: ChatMessage;
}

function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex flex-col gap-1",
        isUser ? "items-end" : "items-start",
      )}
    >
      <div
        className={cn(
          "max-w-[85%] rounded-xl px-3 py-2 text-sm leading-relaxed",
          isUser
            ? "bg-charcoal text-white"
            : "bg-gray-50 text-charcoal border border-gray-100",
        )}
      >
        {message.content}
      </div>

      {/* Metadata (assistant only) */}
      {!isUser && (
        <>
          {message.citations && message.citations.length > 0 && (
            <div className="flex flex-wrap gap-1 max-w-[85%]">
              {message.citations.map((c) => (
                <CitationBadge key={c} citation={c} />
              ))}
            </div>
          )}
          {message.toolsCalled && message.toolsCalled.length > 0 && (
            <p className="text-xs text-mid-gray max-w-[85%]">
              herramientas: {message.toolsCalled.join(", ")}
            </p>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface CompetitionChatPanelProps {
  raceEventId: number;
}

export function CompetitionChatPanel({
  raceEventId,
}: CompetitionChatPanelProps) {
  // Stable session_id per mount.
  const sessionIdRef = useRef<string>(crypto.randomUUID());

  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<PanelError | null>(null);

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
        race_event_id: raceEventId,
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

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendMessage();
    }
  }

  const inputDisabled = isPending || error?.kind === "unavailable";

  return (
    <section
      className="rounded-xl bg-white shadow-ring-soft"
      aria-label="Chat de IA para esta competencia"
      data-testid="competition-chat-panel"
    >
      {/* Collapsible header */}
      <button
        type="button"
        className={cn(
          "flex w-full items-center justify-between px-5 py-4 text-left",
          "hover:bg-gray-50 transition-colors",
          isOpen ? "rounded-t-xl" : "rounded-xl",
        )}
        aria-expanded={isOpen}
        aria-controls="competition-chat-body"
        onClick={() => setIsOpen((v) => !v)}
        data-testid="competition-chat-toggle"
      >
        <div className="flex items-center gap-2">
          <MessageSquare
            size={16}
            className="text-charcoal shrink-0"
            aria-hidden="true"
          />
          <span
            className="text-sm font-semibold text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif" }}
          >
            Preguntar a la IA
          </span>
        </div>
        {isOpen ? (
          <ChevronUp size={16} className="text-mid-gray" aria-hidden="true" />
        ) : (
          <ChevronDown
            size={16}
            className="text-mid-gray"
            aria-hidden="true"
          />
        )}
      </button>

      {/* Body */}
      {isOpen && (
        <div
          id="competition-chat-body"
          className="border-t border-gray-100 px-5 pb-5 pt-4 space-y-4"
          data-testid="competition-chat-body"
        >
          {/* Message list */}
          {messages.length > 0 && (
            <div
              className="space-y-3 max-h-80 overflow-y-auto pr-1"
              role="log"
              aria-label="Historial de mensajes"
              aria-live="polite"
              data-testid="competition-chat-messages"
            >
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
              {isPending && (
                <p
                  className="text-sm text-mid-gray italic"
                  aria-live="polite"
                  data-testid="competition-chat-thinking"
                >
                  Pensando…
                </p>
              )}
              <div ref={listEndRef} />
            </div>
          )}

          {/* Unavailability notice (503) */}
          {error?.kind === "unavailable" ? (
            <div
              className="rounded-lg bg-gray-50 px-4 py-3 space-y-2 border border-gray-200"
              role="alert"
              data-testid="competition-chat-unavailable"
            >
              <p className="text-sm text-mid-gray">
                El asistente de IA no está disponible en este momento.
              </p>
              <Textarea
                disabled
                placeholder="El asistente no está disponible."
                className="min-h-[60px] opacity-50"
                aria-label="Campo de consulta (deshabilitado)"
              />
            </div>
          ) : (
            /* Input area */
            <div className="space-y-2">
              {error?.kind === "turn_error" && (
                <p
                  className="text-sm text-red-600"
                  role="alert"
                  data-testid="competition-chat-turn-error"
                >
                  No se pudo obtener respuesta. Intenta de nuevo.
                </p>
              )}
              <div className="flex gap-2 items-end">
                <Textarea
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Pregunta sobre esta competencia…"
                  disabled={inputDisabled}
                  className="min-h-[60px] flex-1"
                  aria-label="Consulta al asistente de IA"
                  data-testid="competition-chat-input"
                />
                <Button
                  type="button"
                  size="sm"
                  onClick={() => void sendMessage()}
                  disabled={inputDisabled || !query.trim()}
                  aria-label="Enviar consulta"
                  data-testid="competition-chat-send"
                  className="shrink-0"
                >
                  <Send size={14} aria-hidden="true" />
                  <span className="sr-only">Enviar</span>
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
