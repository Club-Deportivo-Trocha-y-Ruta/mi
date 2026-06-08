/**
 * Hooks TanStack Query para el Asistente IA de sesiones (Feature 006).
 *
 * - `useClarify()` → mutation POST clarify; mapea 503 vs 422 a estados tipados.
 * - `useDraft()`   → mutation POST draft; mismo mapeo de errores.
 *
 * Error semantics:
 *   503 → AssistantUnavailableError (IA desactivada / timeout / servidor frío)
 *   422 → AssistantValidationError (JSON malformado / violación de principios)
 *   otros → error genérico (relanzado)
 */
import { useMutation } from "@tanstack/react-query";

import {
  clarify,
  draft,
  type SessionClarifyRequest,
  type SessionClarifyResponse,
  type SessionDraftRequest,
  type SessionDraftResponse,
} from "@/api/sessionAssistant";
import { useAuthStore } from "@/store/auth.store";

// ---------------------------------------------------------------------------
// Tipos de error tipados para la UI
// ---------------------------------------------------------------------------

export class AssistantUnavailableError extends Error {
  readonly kind = "unavailable" as const;
  constructor(message = "El asistente no está disponible en este momento.") {
    super(message);
    this.name = "AssistantUnavailableError";
  }
}

export class AssistantValidationError extends Error {
  readonly kind = "validation" as const;
  constructor(message = "El asistente devolvió una respuesta inválida.") {
    super(message);
    this.name = "AssistantValidationError";
  }
}

/**
 * Mapea un error de Axios al tipo semántico correcto.
 * 503 → unavailable (IA desactivada / timeout / cold start)
 * 422 → validation (JSON malformado / violación de principios)
 */
function mapApiError(err: unknown): Error {
  const status = (err as { response?: { status?: number; data?: { detail?: string } } })
    ?.response?.status;
  const detail =
    (err as { response?: { status?: number; data?: { detail?: string } } })?.response
      ?.data?.detail ?? undefined;

  if (status === 503) {
    return new AssistantUnavailableError(
      typeof detail === "string"
        ? detail
        : "El asistente no está disponible en este momento.",
    );
  }
  if (status === 422) {
    return new AssistantValidationError(
      typeof detail === "string" ? detail : "La solicitud no es válida.",
    );
  }
  return err instanceof Error ? err : new Error(String(err));
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useClarify(clubId: number) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useMutation<
    SessionClarifyResponse,
    AssistantUnavailableError | AssistantValidationError | Error,
    SessionClarifyRequest
  >({
    mutationKey: ["session-assistant", clubId, "clarify"],
    mutationFn: async (payload) => {
      if (!accessToken) throw new Error("No autenticado.");
      try {
        return await clarify(clubId, payload);
      } catch (err) {
        throw mapApiError(err);
      }
    },
  });
}

export function useDraft(clubId: number) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useMutation<
    SessionDraftResponse,
    AssistantUnavailableError | AssistantValidationError | Error,
    SessionDraftRequest
  >({
    mutationKey: ["session-assistant", clubId, "draft"],
    mutationFn: async (payload) => {
      if (!accessToken) throw new Error("No autenticado.");
      try {
        return await draft(clubId, payload);
      } catch (err) {
        throw mapApiError(err);
      }
    },
  });
}
