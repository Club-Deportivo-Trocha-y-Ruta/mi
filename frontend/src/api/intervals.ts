/**
 * Cliente API del módulo Entrenamiento por Intervalos (feature 026).
 *
 * Convenciones:
 * - Cada respuesta del servidor se valida con `.parse()` (allowlist en cliente).
 * - Mapeo de errores HTTP a copy en español neutro (Colombia).
 * - `extractAgeGateError` espeja `extractAgeBandGuardrail`: distingue el guardrail
 *   de categoría confirmable (FR-007) de cualquier otra validación 422.
 *
 * RBAC: todo `/api/intervals` es coach/admin (el backend responde 403 a padres/atletas).
 * Privacidad (Ley 1581): las vueltas nunca traen GPS/polyline/mapa/cadencia/watts.
 */
import axios, { type AxiosError } from "axios";

import { apiClient } from "@/api/client";
import {
  intervalStructureOutSchema,
  intervalTemplateListSchema,
  intervalTemplateOutSchema,
  matchDetailSchema,
  matchRecalculateResponseSchema,
} from "@/schemas/intervals.schema";
import type {
  AgeGateError,
  InstructivoBrand,
  IntervalAttachInput,
  IntervalErrorInfo,
  IntervalErrorKind,
  IntervalRecalculateInput,
  IntervalStructureCreateInput,
  IntervalStructureOut,
  IntervalStructureUpdateInput,
  IntervalTemplateFilters,
  IntervalTemplateList,
  IntervalTemplateOut,
  IntervalTemplateSaveInput,
  IntervalValidationCode,
  IntervalValidationError,
  MatchDetail,
  MatchRecalculateResponse,
} from "@/types/intervals.types";

const BASE = "/api/intervals";

// ---------------------------------------------------------------------------
// Estructuras (US1)
// ---------------------------------------------------------------------------

/** POST /api/intervals/structures — crea una estructura adjunta a una sesión. */
export async function createStructure(
  input: IntervalStructureCreateInput,
): Promise<IntervalStructureOut> {
  const response = await apiClient.post<unknown>(`${BASE}/structures`, input);
  return intervalStructureOutSchema.parse(response.data);
}

/** GET /api/intervals/sessions/{id}/structure — estructura de una sesión (404 si no existe). */
export async function getSessionStructure(
  trainingSessionId: number,
): Promise<IntervalStructureOut> {
  const response = await apiClient.get<unknown>(
    `${BASE}/sessions/${trainingSessionId}/structure`,
  );
  return intervalStructureOutSchema.parse(response.data);
}

/** PUT /api/intervals/structures/{id} — reemplazo completo de banda + bloques. */
export async function updateStructure(
  structureId: number,
  input: IntervalStructureUpdateInput,
): Promise<IntervalStructureOut> {
  const response = await apiClient.put<unknown>(
    `${BASE}/structures/${structureId}`,
    input,
  );
  return intervalStructureOutSchema.parse(response.data);
}

/** DELETE /api/intervals/structures/{id} — 204 (cascada bloques + comparaciones; vueltas intactas). */
export async function deleteStructure(structureId: number): Promise<void> {
  await apiClient.delete(`${BASE}/structures/${structureId}`);
}

// ---------------------------------------------------------------------------
// Templates (US4)
// ---------------------------------------------------------------------------

/** POST /api/intervals/templates — crea un template reutilizable. */
export async function createTemplate(
  input: IntervalTemplateSaveInput,
): Promise<IntervalTemplateOut> {
  const response = await apiClient.post<unknown>(`${BASE}/templates`, input);
  return intervalTemplateOutSchema.parse(response.data);
}

/** GET /api/intervals/templates — lista/filtra los templates del club del coach. */
export async function listTemplates(
  filters?: IntervalTemplateFilters,
): Promise<IntervalTemplateList> {
  const response = await apiClient.get<unknown>(`${BASE}/templates`, {
    params: filters,
  });
  return intervalTemplateListSchema.parse(response.data);
}

/** PUT /api/intervals/templates/{id} — edita un template (no muta sesiones que lo usaron). */
export async function updateTemplate(
  templateId: number,
  input: IntervalTemplateSaveInput,
): Promise<IntervalTemplateOut> {
  const response = await apiClient.put<unknown>(
    `${BASE}/templates/${templateId}`,
    input,
  );
  return intervalTemplateOutSchema.parse(response.data);
}

/** PATCH /api/intervals/templates/{id}/archive — archiva o desarchiva un template. */
export async function archiveTemplate(
  templateId: number,
  isArchived: boolean,
): Promise<IntervalTemplateOut> {
  const response = await apiClient.patch<unknown>(
    `${BASE}/templates/${templateId}/archive`,
    { is_archived: isArchived },
  );
  return intervalTemplateOutSchema.parse(response.data);
}

/**
 * POST /api/intervals/templates/{id}/attach — clona el template en una sesión.
 * Corre la validación completa (age-gate/cadencia/grupos) contra la banda del template.
 * Devuelve la estructura recién creada (`StructureOut`).
 */
export async function attachTemplate(
  templateId: number,
  input: IntervalAttachInput,
): Promise<IntervalStructureOut> {
  const response = await apiClient.post<unknown>(
    `${BASE}/templates/${templateId}/attach`,
    input,
  );
  return intervalStructureOutSchema.parse(response.data);
}

// ---------------------------------------------------------------------------
// Matching (US2)
// ---------------------------------------------------------------------------

/**
 * GET /api/intervals/sessions/{id}/match — payload de la vista de detalle (FR-017).
 * `activityId` es opcional cuando existe exactamente una actividad enlazada.
 * Nunca lanza por estado: `no_activity` / `computing` / `failed` llegan como `200`.
 */
export async function getSessionMatch(
  trainingSessionId: number,
  activityId?: number,
): Promise<MatchDetail> {
  const response = await apiClient.get<unknown>(
    `${BASE}/sessions/${trainingSessionId}/match`,
    { params: activityId != null ? { activity_id: activityId } : undefined },
  );
  return matchDetailSchema.parse(response.data);
}

/**
 * POST /api/intervals/structures/{id}/recalculate — recálculo manual (FR-015).
 * Re-descarga vueltas de Strava y recomputa (deferred) → `202 { status: "computing" }`.
 */
export async function recalculateMatch(
  structureId: number,
  input?: IntervalRecalculateInput,
): Promise<MatchRecalculateResponse> {
  const response = await apiClient.post<unknown>(
    `${BASE}/structures/${structureId}/recalculate`,
    input ?? {},
  );
  return matchRecalculateResponseSchema.parse(response.data);
}

// ---------------------------------------------------------------------------
// Instructivo PDF (US3)
// ---------------------------------------------------------------------------

/**
 * GET /api/intervals/sessions/{id}/instructivo?brand=... — descarga el PDF por marca.
 * Devuelve el `Blob` crudo; el llamador lo pasa a `triggerBlobDownload`.
 */
export async function downloadInstructivo(
  trainingSessionId: number,
  brand: InstructivoBrand,
): Promise<Blob> {
  const response = await apiClient.get(
    `${BASE}/sessions/${trainingSessionId}/instructivo`,
    { params: { brand }, responseType: "blob" },
  );
  return response.data as Blob;
}

// ---------------------------------------------------------------------------
// Mapeo de errores HTTP a copy en español
// ---------------------------------------------------------------------------

const ERROR_COPY: Record<IntervalErrorKind, string> = {
  not_found: "No se encontró la estructura o recurso solicitado.",
  conflict: "La sesión ya tiene una estructura. Editá la existente.",
  forbidden: "No tienes permiso para esta acción.",
  unauthorized: "Tu sesión expiró. Vuelve a iniciar sesión.",
  validation: "Los datos ingresados no son válidos. Revisa el formulario.",
  rate_limited:
    "Strava limitó las solicitudes temporalmente. Intentá de nuevo en unos minutos.",
  cancelled: "Operación cancelada.",
  unknown: "Ocurrió un error inesperado.",
};

/** Extrae el `detail` (objeto) de un error 422 de Axios, o `null`. */
function getValidationDetail(error: unknown): Record<string, unknown> | null {
  if (!axios.isAxiosError(error)) return null;
  const response = (error as AxiosError).response;
  if (response?.status !== 422) return null;
  const detail = (response.data as { detail?: unknown } | undefined)?.detail;
  if (!detail || typeof detail !== "object") return null;
  return detail as Record<string, unknown>;
}

const VALIDATION_CODES: readonly IntervalValidationCode[] = [
  "cadence_below_minimum",
  "age_gate_z3_blocked",
  "age_gate_confirmation_required",
  "invalid_repeat_group",
];

/**
 * Detecta si un error de Axios es una validación 422 legible por máquina de
 * `/api/intervals` (`cadence_below_minimum`, `age_gate_z3_blocked`,
 * `age_gate_confirmation_required`, `invalid_repeat_group`) y extrae
 * `code`/`message`/`positions`. Devuelve `null` para cualquier otro error.
 */
export function extractIntervalValidationError(
  error: unknown,
): IntervalValidationError | null {
  const detail = getValidationDetail(error);
  const code = detail?.code;
  if (
    typeof code !== "string" ||
    !VALIDATION_CODES.includes(code as IntervalValidationCode)
  ) {
    return null;
  }
  const message = detail?.message;
  const positions = detail?.positions;
  return {
    code: code as IntervalValidationCode,
    message: typeof message === "string" ? message : ERROR_COPY.validation,
    positions:
      Array.isArray(positions) &&
      positions.every((p): p is number => typeof p === "number")
        ? positions
        : undefined,
  };
}

/**
 * Detecta el guardrail de categoría **confirmable** (FR-007,
 * `age_gate_confirmation_required`) y extrae su mensaje en español. Devuelve
 * `null` para cualquier otro error — incluido el bloqueo duro Z3+
 * (`age_gate_z3_blocked`, sin override) — para que el llamador distinga
 * "abrir `AgeGateDialog` y reenviar con `age_gate_confirmed: true`" de
 * "mostrar el error de validación genérico". Espeja `extractAgeBandGuardrail`.
 */
export function extractAgeGateError(error: unknown): AgeGateError | null {
  const validation = extractIntervalValidationError(error);
  if (validation?.code !== "age_gate_confirmation_required") return null;
  return { message: validation.message };
}

/** Traduce un error de Axios a un objeto consumible por la UI. */
export function mapIntervalError(error: unknown): IntervalErrorInfo {
  if (axios.isCancel(error) || (error as Error)?.name === "CanceledError") {
    return { kind: "cancelled", message: ERROR_COPY.cancelled };
  }
  if (!axios.isAxiosError(error)) {
    return { kind: "unknown", message: ERROR_COPY.unknown };
  }
  const status = (error as AxiosError).response?.status;
  if (status === 404)
    return { kind: "not_found", message: ERROR_COPY.not_found };
  if (status === 409)
    return { kind: "conflict", message: ERROR_COPY.conflict };
  if (status === 403)
    return { kind: "forbidden", message: ERROR_COPY.forbidden };
  if (status === 401)
    return { kind: "unauthorized", message: ERROR_COPY.unauthorized };
  if (status === 422)
    return { kind: "validation", message: ERROR_COPY.validation };
  if (status === 429)
    return { kind: "rate_limited", message: ERROR_COPY.rate_limited };
  return { kind: "unknown", message: ERROR_COPY.unknown };
}

export { BASE, apiClient };
