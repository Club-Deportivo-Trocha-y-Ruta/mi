import axios, { type AxiosError } from "axios";

import { apiClient } from "@/api/client";
import {
  assembleResultSchema,
  athleteProgressSchema,
  catalogListSchema,
  exerciseDetailSchema,
  materialSchema,
  sessionItemsSchema,
  skillProgressEventSchema,
  skillSchema,
  visibilityResponseSchema,
} from "@/schemas/technique.schemas";
import type {
  AssembleSessionInput,
  AssembleSessionResult,
  AthleteProgress,
  CatalogFilters,
  CatalogList,
  ExerciseCreateInput,
  ExerciseDetail,
  ExerciseUpdateInput,
  MaterialRead,
  ProgressInput,
  SkillProgressEvent,
  SkillRead,
  TechniqueSessionItem,
} from "@/types/technique.types";

const BASE = "/api/technique";

// ---------------------------------------------------------------------------
// Catalog & discovery (US1)
// ---------------------------------------------------------------------------

/** GET /api/technique/exercises — lista/filtra el catálogo. */
export async function listExercises(
  filters?: CatalogFilters,
): Promise<CatalogList> {
  const response = await apiClient.get<unknown>(`${BASE}/exercises`, {
    params: filters,
  });
  return catalogListSchema.parse(response.data);
}

/** GET /api/technique/exercises/{id} — detalle del ejercicio. */
export async function getExercise(id: number): Promise<ExerciseDetail> {
  const response = await apiClient.get<unknown>(`${BASE}/exercises/${id}`);
  return exerciseDetailSchema.parse(response.data);
}

/** GET /api/technique/skills — taxonomía de habilidades (para filtros). */
export async function listSkills(): Promise<SkillRead[]> {
  const response = await apiClient.get<unknown>(`${BASE}/skills`);
  return skillSchema.array().parse(response.data);
}

/** GET /api/technique/materials — listado de materiales (para filtros). */
export async function listMaterials(): Promise<MaterialRead[]> {
  const response = await apiClient.get<unknown>(`${BASE}/materials`);
  return materialSchema.array().parse(response.data);
}

// ---------------------------------------------------------------------------
// Session assembly (US3)
// ---------------------------------------------------------------------------

/** POST /api/technique/sessions — arma una sesión de entrenamiento con ejercicios. */
export async function assembleSession(
  input: AssembleSessionInput,
): Promise<AssembleSessionResult> {
  const response = await apiClient.post<unknown>(`${BASE}/sessions`, input);
  return assembleResultSchema.parse(response.data);
}

/** GET /api/technique/sessions/{training_session_id}/exercises — ejercicios de una sesión guardada. */
export async function getSessionExercises(
  sessionId: number,
): Promise<TechniqueSessionItem[]> {
  const response = await apiClient.get<unknown>(
    `${BASE}/sessions/${sessionId}/exercises`,
  );
  return sessionItemsSchema.parse(response.data);
}

// ---------------------------------------------------------------------------
// Per-athlete skill progress (US4)
// ---------------------------------------------------------------------------

/** GET /api/technique/athletes/{athlete_id}/progress — progreso de habilidades del atleta. */
export async function getAthleteProgress(
  athleteId: number,
): Promise<AthleteProgress> {
  const response = await apiClient.get<unknown>(
    `${BASE}/athletes/${athleteId}/progress`,
  );
  return athleteProgressSchema.parse(response.data);
}

/** POST /api/technique/athletes/{athlete_id}/progress — registra un evento de progreso. */
export async function addProgress(
  athleteId: number,
  input: ProgressInput,
): Promise<SkillProgressEvent> {
  const response = await apiClient.post<unknown>(
    `${BASE}/athletes/${athleteId}/progress`,
    input,
  );
  return skillProgressEventSchema.parse(response.data);
}

// ---------------------------------------------------------------------------
// Curation (US5)
// ---------------------------------------------------------------------------

/** POST /api/technique/exercises — crea un ejercicio personalizado. */
export async function createExercise(
  input: ExerciseCreateInput,
): Promise<ExerciseDetail> {
  const response = await apiClient.post<unknown>(`${BASE}/exercises`, input);
  return exerciseDetailSchema.parse(response.data);
}

/** PUT /api/technique/exercises/{id} — edita un ejercicio (incluyendo seedeados). */
export async function updateExercise(
  id: number,
  input: ExerciseUpdateInput,
): Promise<ExerciseDetail> {
  const response = await apiClient.put<unknown>(
    `${BASE}/exercises/${id}`,
    input,
  );
  return exerciseDetailSchema.parse(response.data);
}

/** PATCH /api/technique/exercises/{id}/visibility — oculta o muestra un ejercicio. */
export async function setVisibility(
  id: number,
  isHidden: boolean,
): Promise<{ id: number; is_hidden: boolean }> {
  const response = await apiClient.patch<unknown>(
    `${BASE}/exercises/${id}/visibility`,
    { is_hidden: isHidden },
  );
  return visibilityResponseSchema.parse(response.data);
}

// ---------------------------------------------------------------------------
// Mapeo de errores HTTP a copy en español
// ---------------------------------------------------------------------------

export type TechniqueErrorKind =
  | "not_found"
  | "forbidden"
  | "unauthorized"
  | "validation"
  | "cancelled"
  | "unknown";

export interface TechniqueErrorInfo {
  kind: TechniqueErrorKind;
  message: string;
}

const COPY: Record<TechniqueErrorKind, string> = {
  not_found: "No se encontró el ejercicio o recurso solicitado.",
  forbidden: "No tienes permiso para esta acción.",
  unauthorized: "Tu sesión expiró. Vuelve a iniciar sesión.",
  validation: "Los datos ingresados no son válidos. Revisa el formulario.",
  cancelled: "Operación cancelada.",
  unknown: "Ocurrió un error inesperado.",
};

/** Traduce un error de Axios a un objeto consumible por la UI. */
export function mapTechniqueError(error: unknown): TechniqueErrorInfo {
  if (axios.isCancel(error) || (error as Error)?.name === "CanceledError") {
    return { kind: "cancelled", message: COPY.cancelled };
  }
  if (!axios.isAxiosError(error)) {
    return { kind: "unknown", message: COPY.unknown };
  }
  const status = (error as AxiosError).response?.status;
  if (status === 404) return { kind: "not_found", message: COPY.not_found };
  if (status === 403) return { kind: "forbidden", message: COPY.forbidden };
  if (status === 401)
    return { kind: "unauthorized", message: COPY.unauthorized };
  if (status === 422) return { kind: "validation", message: COPY.validation };
  return { kind: "unknown", message: COPY.unknown };
}
