/**
 * AthleteAnalystChatPanel — "Preguntar al analista" (feature 037, T302).
 *
 * Chat de IA scopeado al atleta (envía `athlete_id`, no `race_event_id`),
 * reutilizando la lógica de sesión de `useChatSession` (misma que
 * `CompetitionChatPanel`: session_id estable por montaje, historial
 * in-memory sin persistencia, 503 → deshabilitado, otros errores →
 * retryable con historial intacto) y los mismos sub-componentes de
 * burbuja/citación.
 *
 * A diferencia de `CompetitionChatPanel` no es colapsable — vive montado
 * en el sub-tab "Analizar con IA" bajo `LaunchAnalysisForm`, siempre
 * visible para el coach.
 *
 * Chips de sugerencias iniciales: rellenan el input, no envían solos —
 * el coach conserva el control de cuándo disparar la consulta.
 *
 * Props: { athleteId: number }
 * Visibilidad: montado solo en mode="coach" por `AthleteAIAnalysisTab`.
 */
import { Send, Sparkles } from "lucide-react";

import {
  MessageBubble,
} from "@/components/competitions/chat/CompetitionChatPanel";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useChatSession } from "@/hooks/ai/useChatSession";

const SUGGESTED_QUESTIONS = [
  "¿Qué explica el resultado de la última válida?",
  "¿Cómo va la asistencia este mes?",
  "¿Qué trabajar antes de la próxima carrera?",
];

export interface AthleteAnalystChatPanelProps {
  athleteId: number;
}

export function AthleteAnalystChatPanel({
  athleteId,
}: AthleteAnalystChatPanelProps) {
  const {
    query,
    setQuery,
    messages,
    isPending,
    error,
    inputDisabled,
    sendMessage,
    listEndRef,
  } = useChatSession({ athleteId });

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendMessage();
    }
  }

  return (
    <section
      className="rounded-xl bg-white p-5 shadow-card space-y-4"
      aria-label="Preguntar al analista de IA"
      data-testid="athlete-analyst-chat-panel"
    >
      <div className="flex items-center gap-2">
        <Sparkles size={16} className="text-charcoal shrink-0" aria-hidden="true" />
        <h3 className="font-display text-sm font-semibold text-charcoal">
          Preguntar al analista
        </h3>
      </div>

      <p
        className="text-xs text-mid-gray"
        data-testid="athlete-analyst-chat-non-persistence-notice"
      >
        Esta conversación no se guarda — se pierde al cerrar o recargar la página.
      </p>

      {/* Chips de sugerencias — solo antes del primer envío para no
          desordenar la conversación en curso. */}
      {messages.length === 0 && (
        <div className="flex flex-wrap gap-2" data-testid="athlete-analyst-chat-suggestions">
          {SUGGESTED_QUESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              className="rounded-full border border-gray-200 px-3 py-1.5 text-xs text-charcoal hover:bg-gray-50 transition-colors"
              onClick={() => setQuery(suggestion)}
              disabled={inputDisabled}
              data-testid="athlete-analyst-chat-suggestion-chip"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}

      {/* Message list */}
      {messages.length > 0 && (
        <div
          className="space-y-3 max-h-80 overflow-y-auto pr-1"
          role="log"
          aria-label="Historial de mensajes"
          aria-live="polite"
          data-testid="athlete-analyst-chat-messages"
        >
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          {isPending && (
            <p
              className="text-sm text-mid-gray italic"
              aria-live="polite"
              data-testid="athlete-analyst-chat-thinking"
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
          data-testid="athlete-analyst-chat-unavailable"
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
        <div className="space-y-2">
          {error?.kind === "turn_error" && (
            <p
              className="text-sm text-red-600"
              role="alert"
              data-testid="athlete-analyst-chat-turn-error"
            >
              No se pudo obtener respuesta. Intenta de nuevo.
            </p>
          )}
          <div className="flex gap-2 items-end">
            <Textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Pregunta sobre este atleta…"
              disabled={inputDisabled}
              className="min-h-[60px] flex-1"
              aria-label="Consulta al asistente de IA"
              data-testid="athlete-analyst-chat-input"
            />
            <Button
              type="button"
              size="sm"
              onClick={() => void sendMessage()}
              disabled={inputDisabled || !query.trim()}
              aria-label="Enviar consulta"
              data-testid="athlete-analyst-chat-send"
              className="shrink-0"
            >
              <Send size={14} aria-hidden="true" />
              <span className="sr-only">Enviar</span>
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
