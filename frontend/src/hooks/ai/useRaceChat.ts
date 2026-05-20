/**
 * Hook para el chat consultivo race-analysis (Fase 6.9).
 *
 * Mutation simple POST /chat. session_id se genera en cliente
 * (uuid v4 si está disponible, fallback hex random) y se mantiene
 * estable durante la conversación.
 */
import { useMutation } from "@tanstack/react-query";

import { chatTurn } from "@/api/raceAnalysis";
import type { ChatRequestBody, ChatResponse } from "@/types/raceAnalysis.types";

/** Genera un ID de sesión razonablemente único.
 *
 * Usa `crypto.randomUUID()` cuando está disponible (todos los browsers
 * modernos + jsdom 22+); fallback simple basado en `Math.random` para
 * entornos antiguos.
 */
export function generateSessionId(): string {
  if (
    typeof globalThis !== "undefined" &&
    typeof globalThis.crypto !== "undefined" &&
    typeof globalThis.crypto.randomUUID === "function"
  ) {
    return globalThis.crypto.randomUUID();
  }
  // Fallback no criptográfico (suficiente para identificador local).
  const seed = Math.random().toString(36).slice(2);
  const ts = Date.now().toString(36);
  return `s-${ts}-${seed}`;
}

export function useRaceChat() {
  return useMutation<ChatResponse, unknown, ChatRequestBody>({
    mutationKey: ["race-analysis", "chat"],
    mutationFn: (body) => chatTurn(body),
  });
}
