/**
 * ChatConsole — chat consultivo con el agente race-results (§10.2 #ChatConsole).
 *
 * Input + history vertical. POST /chat respuesta completa (sin
 * streaming). Spinner mientras `isPending`.
 *
 * `session_id` se genera localmente con `generateSessionId()` y se
 * mantiene estable durante el lifecycle del componente. El contexto
 * conversacional vive en el backend (in-memory TTL 1h).
 *
 * Mensajes assistant incluyen footers con tools_called + citations
 * para que el coach vea qué herramientas se usaron.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Bot, Loader2, Send, User as UserIcon } from "lucide-react";

import { generateSessionId, useRaceChat } from "@/hooks/ai/useRaceChat";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/raceAnalysis.types";

interface ChatConsoleProps {
  /** Si presente, todas las consultas atan al atleta indicado. */
  athleteId?: number | null;
  /** Nombre del atleta — mejora el placeholder y el header del chat.
   *  Sólo afecta la UI; el body al backend sigue siendo athlete_id. */
  athleteName?: string | null;
  className?: string;
}

export function ChatConsole({
  athleteId = null,
  athleteName = null,
  className,
}: ChatConsoleProps) {
  const sessionId = useMemo(() => generateSessionId(), []);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const mutation = useRaceChat();
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll al último mensaje.
  useEffect(() => {
    if (!scrollRef.current) return;
    try {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    } catch {
      /* jsdom */
    }
  }, [messages.length, mutation.isPending]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const query = input.trim();
    if (!query || mutation.isPending) return;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      role: "user",
      content: query,
      ts: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");

    try {
      const response = await mutation.mutateAsync({
        session_id: sessionId,
        query,
        athlete_id: athleteId ?? undefined,
      });
      const assistantMsg: ChatMessage = {
        id: `a-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        role: "assistant",
        content: response.answer,
        toolsCalled: response.tools_called,
        citations: response.citations_used,
        ts: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errorMsg: ChatMessage = {
        id: `e-${Date.now()}`,
        role: "assistant",
        content:
          err instanceof Error
            ? `Error: ${err.message}`
            : "Error inesperado consultando al agente.",
        ts: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    }
  };

  return (
    <section
      className={cn(
        "flex h-[520px] flex-col rounded-xl bg-white ring-1 ring-light-gray",
        className,
      )}
      aria-label="Chat consultivo con agente race-results"
      data-testid="chat-console"
    >
      <div className="border-b border-light-gray px-4 py-3">
        <h3 className="text-sm font-semibold text-charcoal">
          Pregunta al agente
        </h3>
        <p className="mt-0.5 text-xs text-mid-gray">
          Resultados Copa Valle, principios LTAD, atletas
          {athleteName
            ? ` (contexto: ${athleteName}).`
            : athleteId
              ? ` (contexto: atleta #${athleteId}).`
              : "."}
        </p>
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-3 space-y-3"
        data-testid="chat-history"
      >
        {messages.length === 0 && !mutation.isPending && (
          <div className="flex h-full items-center justify-center text-sm text-mid-gray">
            <p>Haz una pregunta para empezar.</p>
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn(
              "flex gap-2",
              msg.role === "user" ? "justify-end" : "justify-start",
            )}
            data-testid={`chat-message-${msg.role}`}
          >
            {msg.role === "assistant" && (
              <Bot
                size={18}
                className="mt-1 shrink-0 text-mid-gray"
                aria-hidden="true"
              />
            )}
            <div
              className={cn(
                "max-w-[80%] rounded-2xl px-4 py-2 text-sm",
                msg.role === "user"
                  ? "bg-charcoal text-white"
                  : "bg-light-gray/40 text-charcoal",
              )}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
              {msg.role === "assistant" &&
                (msg.toolsCalled?.length || msg.citations?.length) && (
                  <div className="mt-2 flex flex-wrap gap-1 border-t border-light-gray pt-2 text-xs text-mid-gray">
                    {msg.toolsCalled?.length ? (
                      <span data-testid="chat-message-tools">
                        Tools: {msg.toolsCalled.join(", ")}
                      </span>
                    ) : null}
                    {msg.citations?.length ? (
                      <span data-testid="chat-message-citations">
                        Citas: {msg.citations.join(", ")}
                      </span>
                    ) : null}
                  </div>
                )}
            </div>
            {msg.role === "user" && (
              <UserIcon
                size={18}
                className="mt-1 shrink-0 text-mid-gray"
                aria-hidden="true"
              />
            )}
          </div>
        ))}
        {mutation.isPending && (
          <div
            className="flex items-center gap-2 text-sm text-mid-gray"
            data-testid="chat-pending"
            aria-live="polite"
          >
            <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            Pensando...
          </div>
        )}
      </div>

      <form
        onSubmit={handleSubmit}
        className="border-t border-light-gray p-3"
        data-testid="chat-form"
      >
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              athleteName
                ? `¿Cuál es el progreso de ${athleteName} en las últimas 3 válidas?`
                : "Pregunta libre — o selecciona un deportista arriba"
            }
            maxLength={2000}
            disabled={mutation.isPending}
            data-testid="chat-input"
            aria-label="Escribe tu pregunta"
            className="flex-1 rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40 disabled:opacity-50"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          />
          <button
            type="submit"
            disabled={mutation.isPending || input.trim().length === 0}
            data-testid="chat-submit"
            aria-label="Enviar pregunta"
            className="inline-flex items-center justify-center rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {mutation.isPending ? (
              <Loader2 size={16} className="animate-spin" aria-hidden="true" />
            ) : (
              <Send size={16} aria-hidden="true" />
            )}
          </button>
        </div>
      </form>
    </section>
  );
}
