import axios, { type AxiosError } from "axios";

import { apiClient } from "@/api/client";
import {
  aiHealthResponseSchema,
  anthropometricRecordExplanationResponseSchema,
  phvExplanationResponseSchema,
} from "@/schemas/ai.schemas";
import type {
  AIHealthResponse,
  AnthropometricRecordExplanationResponse,
  PHVExplanationResponse,
} from "@/types/ai.types";

/** Llama POST /api/ai/athletes/{id}/phv-explanation.
 *
 * El backend toma la última medición y hasta 3 anteriores para construir
 * la tendencia; el cliente no envía body. La latencia esperada es 5-30 s
 * en producción y hasta ~80 s con cold start del free tier de Render.
 */
export async function getPHVExplanation(
  athleteId: number,
  options?: { signal?: AbortSignal },
): Promise<PHVExplanationResponse> {
  const response = await apiClient.post<unknown>(
    `/api/ai/athletes/${athleteId}/phv-explanation`,
    undefined,
    { signal: options?.signal },
  );
  // Zod aplica allowlist defensiva contra PII filtrada por error.
  return phvExplanationResponseSchema.parse(response.data);
}

/** Llama GET /api/ai/athletes/{id}/phv-explanation — lee la explicación
 * cacheada para la última medición. Devuelve `null` cuando el backend
 * responde 204 (no hay caché o el atleta no tiene mediciones).
 *
 * No requiere `AI_ENABLED` activo en el backend: la lectura sobrevive a
 * outages del LLM.
 */
export async function getPHVExplanationCached(
  athleteId: number,
  options?: { signal?: AbortSignal },
): Promise<PHVExplanationResponse | null> {
  const response = await apiClient.get<unknown>(
    `/api/ai/athletes/${athleteId}/phv-explanation`,
    {
      signal: options?.signal,
      validateStatus: (status) => status === 200 || status === 204,
    },
  );
  if (response.status === 204) return null;
  return phvExplanationResponseSchema.parse(response.data);
}

/** Llama GET /api/ai/health. Solo admin. */
export async function getAIHealth(): Promise<AIHealthResponse> {
  const response = await apiClient.get<unknown>("/api/ai/health");
  return aiHealthResponseSchema.parse(response.data);
}

/** POST /api/ai/athletes/{id}/measurements/{recordId}/explanation
 *  Genera (o regenera) la explicación particular de una medición vs el
 *  historial. Solo coach/admin. */
export async function postMeasurementExplanation(
  athleteId: number,
  recordId: number,
  options?: { signal?: AbortSignal },
): Promise<AnthropometricRecordExplanationResponse> {
  const response = await apiClient.post<unknown>(
    `/api/ai/athletes/${athleteId}/measurements/${recordId}/explanation`,
    undefined,
    { signal: options?.signal },
  );
  return anthropometricRecordExplanationResponseSchema.parse(response.data);
}

/** GET /api/ai/athletes/{id}/measurements/{recordId}/explanation
 *  Lee la explicación cacheada para una medición específica. Devuelve
 *  `null` si el backend responde 204 (sin caché). Sobrevive a outages
 *  del LLM porque no chequea `ai_enabled`. */
export async function getMeasurementExplanationCached(
  athleteId: number,
  recordId: number,
  options?: { signal?: AbortSignal },
): Promise<AnthropometricRecordExplanationResponse | null> {
  const response = await apiClient.get<unknown>(
    `/api/ai/athletes/${athleteId}/measurements/${recordId}/explanation`,
    {
      signal: options?.signal,
      validateStatus: (status) => status === 200 || status === 204,
    },
  );
  if (response.status === 204) return null;
  return anthropometricRecordExplanationResponseSchema.parse(response.data);
}

// ---------------------------------------------------------------------------
// Mapeo de errores HTTP a copy en español
// ---------------------------------------------------------------------------

export type AIErrorKind =
  | "disabled"        // 503: AI_ENABLED=false o provider caído
  | "guardrail"       // 502: la salida violó los principios del club
  | "no_records"      // 422: atleta sin mediciones
  | "not_found"       // 404: medición no pertenece al atleta
  | "forbidden"       // 403
  | "unauthorized"    // 401
  | "consent_missing" // 451: falta consentimiento parental
  | "cancelled"       // AbortController
  | "unknown";

export interface AIErrorInfo {
  kind: AIErrorKind;
  message: string;
  /** True si tiene sentido reintentar (el provider puede recuperarse). */
  retryable: boolean;
}

const COPY: Record<AIErrorKind, string> = {
  disabled:
    "Servicio de IA temporalmente no disponible, intenta en unos minutos.",
  guardrail:
    "La explicación generada no cumple los principios del club. " +
    "Reintenta o avisa al entrenador.",
  no_records:
    "Este atleta aún no tiene mediciones. Registra una medición " +
    "antropométrica primero.",
  not_found: "La medición seleccionada no se encontró.",
  forbidden: "No tienes permiso para ver esta explicación.",
  unauthorized: "Tu sesión expiró. Vuelve a iniciar sesión.",
  consent_missing:
    "Falta consentimiento de la familia para procesamiento con IA. " +
    "Solicita la renovación del consentimiento antes de generar la explicación.",
  cancelled: "Generación cancelada.",
  unknown: "Ocurrió un error inesperado al generar la explicación.",
};

/** Traduce un error de Axios a un objeto consumible por la UI. */
export function mapAIError(error: unknown): AIErrorInfo {
  if (axios.isCancel(error) || (error as Error)?.name === "CanceledError") {
    return { kind: "cancelled", message: COPY.cancelled, retryable: false };
  }
  if (!axios.isAxiosError(error)) {
    return { kind: "unknown", message: COPY.unknown, retryable: false };
  }
  const axiosError = error as AxiosError;
  const status = axiosError.response?.status;
  if (status === 503) return { kind: "disabled", message: COPY.disabled, retryable: true };
  if (status === 502) return { kind: "guardrail", message: COPY.guardrail, retryable: true };
  if (status === 422) return { kind: "no_records", message: COPY.no_records, retryable: false };
  if (status === 451)
    return {
      kind: "consent_missing",
      message: COPY.consent_missing,
      retryable: false,
    };
  if (status === 404) return { kind: "not_found", message: COPY.not_found, retryable: false };
  if (status === 403) return { kind: "forbidden", message: COPY.forbidden, retryable: false };
  if (status === 401) return { kind: "unauthorized", message: COPY.unauthorized, retryable: false };
  return { kind: "unknown", message: COPY.unknown, retryable: false };
}
