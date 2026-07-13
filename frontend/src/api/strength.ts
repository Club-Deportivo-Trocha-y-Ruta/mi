/**
 * Cliente API del módulo Fuerza y Acondicionamiento (feature 021).
 * Mirroring de convenciones de `api/technique.ts` (feature 018).
 *
 * Scaffold: funciones a implementar por tareas posteriores del plan.
 */
import axios, { type AxiosError } from "axios";

import { apiClient } from "@/api/client";
import {
  strengthAthleteProgressSchema,
  strengthAttachOutSchema,
  strengthBlockListSchema,
  strengthBlockOutSchema,
  strengthCatalogListSchema,
  strengthExerciseDetailSchema,
  strengthProgressOutSchema,
  strengthSessionBlocksSchema,
} from "@/schemas/strength.schemas";
import type {
  StrengthAthleteProgress,
  StrengthAttachOut,
  StrengthBlockList,
  StrengthBlockListFilters,
  StrengthBlockOut,
  StrengthBlockSaveInput,
  StrengthCatalogFilters,
  StrengthCatalogList,
  StrengthExerciseDetail,
  StrengthProgressInput,
  StrengthProgressOut,
  StrengthSessionBlocks,
} from "@/schemas/strength.schemas";

const BASE = "/api/strength";

// ---------------------------------------------------------------------------
// Catalog & discovery (US1)
// ---------------------------------------------------------------------------

/** GET /api/strength/exercises — lista/filtra el catálogo. */
export async function listStrengthExercises(
  filters?: StrengthCatalogFilters,
): Promise<StrengthCatalogList> {
  const response = await apiClient.get<unknown>(`${BASE}/exercises`, {
    params: filters,
  });
  return strengthCatalogListSchema.parse(response.data);
}

/** GET /api/strength/exercises/{id} — detalle del ejercicio. */
export async function getStrengthExercise(
  id: number,
): Promise<StrengthExerciseDetail> {
  const response = await apiClient.get<unknown>(`${BASE}/exercises/${id}`);
  return strengthExerciseDetailSchema.parse(response.data);
}

// ---------------------------------------------------------------------------
// Blocks (US2)
// ---------------------------------------------------------------------------

/** POST /api/strength/blocks — crea un bloque de fuerza. */
export async function createStrengthBlock(
  input: StrengthBlockSaveInput,
): Promise<StrengthBlockOut> {
  const response = await apiClient.post<unknown>(`${BASE}/blocks`, input);
  return strengthBlockOutSchema.parse(response.data);
}

/** PUT /api/strength/blocks/{id} — reemplazo completo de un bloque. */
export async function updateStrengthBlock(
  id: number,
  input: StrengthBlockSaveInput,
): Promise<StrengthBlockOut> {
  const response = await apiClient.put<unknown>(
    `${BASE}/blocks/${id}`,
    input,
  );
  return strengthBlockOutSchema.parse(response.data);
}

/** GET /api/strength/blocks — lista los bloques del club del coach. */
export async function listStrengthBlocks(
  filters?: StrengthBlockListFilters,
): Promise<StrengthBlockList> {
  const response = await apiClient.get<unknown>(`${BASE}/blocks`, {
    params: filters,
  });
  return strengthBlockListSchema.parse(response.data);
}

/** GET /api/strength/blocks/{id} — detalle de un bloque. */
export async function getStrengthBlock(id: number): Promise<StrengthBlockOut> {
  const response = await apiClient.get<unknown>(`${BASE}/blocks/${id}`);
  return strengthBlockOutSchema.parse(response.data);
}

/** PATCH /api/strength/blocks/{id}/archive — archiva o desarchiva un bloque. */
export async function archiveStrengthBlock(
  id: number,
  isArchived: boolean,
): Promise<StrengthBlockOut> {
  const response = await apiClient.patch<unknown>(
    `${BASE}/blocks/${id}/archive`,
    { is_archived: isArchived },
  );
  return strengthBlockOutSchema.parse(response.data);
}

// ---------------------------------------------------------------------------
// Session attachment (US2)
// ---------------------------------------------------------------------------

/** POST /api/strength/blocks/{id}/attach — adjunta un bloque a una sesión. */
export async function attachStrengthBlock(
  blockId: number,
  trainingSessionId: number,
): Promise<StrengthAttachOut> {
  const response = await apiClient.post<unknown>(
    `${BASE}/blocks/${blockId}/attach`,
    { training_session_id: trainingSessionId },
  );
  return strengthAttachOutSchema.parse(response.data);
}

/** DELETE /api/strength/blocks/{id}/attach/{sessionId} — desadjunta un bloque. */
export async function detachStrengthBlock(
  blockId: number,
  trainingSessionId: number,
): Promise<void> {
  await apiClient.delete(`${BASE}/blocks/${blockId}/attach/${trainingSessionId}`);
}

/** GET /api/strength/sessions/{id}/blocks — bloques adjuntos a una sesión. */
export async function getSessionStrengthBlocks(
  trainingSessionId: number,
): Promise<StrengthSessionBlocks> {
  const response = await apiClient.get<unknown>(
    `${BASE}/sessions/${trainingSessionId}/blocks`,
  );
  return strengthSessionBlocksSchema.parse(response.data);
}

// ---------------------------------------------------------------------------
// Per-athlete progress notes (US4)
// ---------------------------------------------------------------------------

/** GET /api/strength/athletes/{athlete_id}/progress — último registro por ejercicio. */
export async function getAthleteStrengthProgress(
  athleteId: number,
): Promise<StrengthAthleteProgress> {
  const response = await apiClient.get<unknown>(
    `${BASE}/athletes/${athleteId}/progress`,
  );
  return strengthAthleteProgressSchema.parse(response.data);
}

/** POST /api/strength/athletes/{athlete_id}/progress — registra una nota de progreso (append-only). */
export async function addStrengthProgress(
  athleteId: number,
  input: StrengthProgressInput,
): Promise<StrengthProgressOut> {
  const response = await apiClient.post<unknown>(
    `${BASE}/athletes/${athleteId}/progress`,
    input,
  );
  return strengthProgressOutSchema.parse(response.data);
}

// ---------------------------------------------------------------------------
// Mapeo de errores HTTP a copy en español (mirror de mapTechniqueError)
// ---------------------------------------------------------------------------

export type StrengthErrorKind =
  | "not_found"
  | "forbidden"
  | "unauthorized"
  | "validation"
  | "cancelled"
  | "unknown";

export interface StrengthErrorInfo {
  kind: StrengthErrorKind;
  message: string;
}

const ERROR_COPY: Record<StrengthErrorKind, string> = {
  not_found: "No se encontró el ejercicio o recurso solicitado.",
  forbidden: "No tienes permiso para esta acción.",
  unauthorized: "Tu sesión expiró. Vuelve a iniciar sesión.",
  validation: "Los datos ingresados no son válidos. Revisa el formulario.",
  cancelled: "Operación cancelada.",
  unknown: "Ocurrió un error inesperado.",
};

export interface AgeBandGuardrailInfo {
  /** Explicación en español devuelta por el backend (FR-011, US3). */
  message: string;
}

/**
 * Detecta si un error de Axios es el guardrail 422 `AGE_BAND_GUARDRAIL`
 * (FR-011, US3 — `POST/PUT /blocks`) y extrae su mensaje en español. Devuelve
 * `null` para cualquier otro error (incluida cualquier otra validación 422),
 * para que el llamador distinga "abrir `AgeBandGuardrailDialog`" de "mostrar
 * el error de validación genérico".
 */
export function extractAgeBandGuardrail(
  error: unknown,
): AgeBandGuardrailInfo | null {
  if (!axios.isAxiosError(error)) return null;
  const response = (error as AxiosError).response;
  if (response?.status !== 422) return null;
  const detail = (response.data as { detail?: unknown } | undefined)?.detail;
  if (
    !detail ||
    typeof detail !== "object" ||
    (detail as { code?: unknown }).code !== "AGE_BAND_GUARDRAIL"
  ) {
    return null;
  }
  const message = (detail as { detail?: unknown }).detail;
  return {
    message: typeof message === "string" ? message : ERROR_COPY.validation,
  };
}

/**
 * Detecta si un error de Axios es el 409 "ya está adjunto" de
 * `POST /blocks/{id}/attach` (`uq_strength_session_block`, feature 032
 * research.md R2/R11). El llamador debe tratarlo como un aviso suave, no
 * como un error bloqueante — el adjunto ya existe, que es el resultado que
 * el coach buscaba.
 */
export function isAlreadyAttachedError(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return false;
  return (error as AxiosError).response?.status === 409;
}

/** Traduce un error de Axios a un objeto consumible por la UI. */
export function mapStrengthError(error: unknown): StrengthErrorInfo {
  if (axios.isCancel(error) || (error as Error)?.name === "CanceledError") {
    return { kind: "cancelled", message: ERROR_COPY.cancelled };
  }
  if (!axios.isAxiosError(error)) {
    return { kind: "unknown", message: ERROR_COPY.unknown };
  }
  const status = (error as AxiosError).response?.status;
  if (status === 404)
    return { kind: "not_found", message: ERROR_COPY.not_found };
  if (status === 403)
    return { kind: "forbidden", message: ERROR_COPY.forbidden };
  if (status === 401)
    return { kind: "unauthorized", message: ERROR_COPY.unauthorized };
  if (status === 422)
    return { kind: "validation", message: ERROR_COPY.validation };
  return { kind: "unknown", message: ERROR_COPY.unknown };
}

export { BASE, apiClient };
