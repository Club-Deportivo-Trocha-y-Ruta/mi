import axios, { type AxiosError } from "axios";

import { apiClient } from "@/api/client";
import {
  answerFormSchema,
  answerResultSchema,
  assessmentCreatedSchema,
  assessmentReadSchema,
  athleteSeriesSchema,
  batchCreatedSchema,
  groupTriageSchema,
  importResultSchema,
  interpretationResponseSchema,
} from "@/schemas/anxiety.schemas";
import type {
  AnswerForm,
  AnswerResult,
  AssessmentCreated,
  AssessmentRead,
  AthleteSeries,
  BatchCreated,
  CreateAssessmentInput,
  CreateBatchInput,
  GroupTriage,
  ImportResult,
  InterpretationResponse,
} from "@/types/anxiety.types";

const BASE = "/api/anxiety";

/** POST /api/anxiety/assessments — crea una evaluación individual. */
export async function createAssessment(
  input: CreateAssessmentInput,
): Promise<AssessmentCreated> {
  const response = await apiClient.post<unknown>(`${BASE}/assessments`, input);
  return assessmentCreatedSchema.parse(response.data);
}

/** POST /api/anxiety/assessments/batch — crea evaluaciones para un grupo. */
export async function createBatch(
  input: CreateBatchInput,
): Promise<BatchCreated> {
  const response = await apiClient.post<unknown>(
    `${BASE}/assessments/batch`,
    input,
  );
  return batchCreatedSchema.parse(response.data);
}

/** GET /api/anxiety/answer/{token} — formulario del atleta (sin auth). */
export async function getAnswerForm(token: string): Promise<AnswerForm> {
  const response = await apiClient.get<unknown>(
    `${BASE}/answer/${encodeURIComponent(token)}`,
  );
  return answerFormSchema.parse(response.data);
}

/** POST /api/anxiety/answer/{token} — envía respuestas (sin auth). */
export async function submitAnswers(
  token: string,
  answers: Record<number, number>,
): Promise<AnswerResult> {
  const response = await apiClient.post<unknown>(
    `${BASE}/answer/${encodeURIComponent(token)}`,
    { answers },
  );
  return answerResultSchema.parse(response.data);
}

/** GET /api/anxiety/assessments/{id} */
export async function getAssessment(id: number): Promise<AssessmentRead> {
  const response = await apiClient.get<unknown>(`${BASE}/assessments/${id}`);
  return assessmentReadSchema.parse(response.data);
}

/** POST /api/anxiety/assessments/{id}/recompute */
export async function recomputeAssessment(id: number): Promise<AssessmentRead> {
  const response = await apiClient.post<unknown>(
    `${BASE}/assessments/${id}/recompute`,
  );
  return assessmentReadSchema.parse(response.data);
}

/** POST /api/anxiety/assessments/{id}/interpret — on-demand, cacheado. */
export async function interpretAssessment(
  id: number,
  options?: { signal?: AbortSignal },
): Promise<InterpretationResponse> {
  const response = await apiClient.post<unknown>(
    `${BASE}/assessments/${id}/interpret`,
    undefined,
    { signal: options?.signal },
  );
  return interpretationResponseSchema.parse(response.data);
}

/** GET /api/anxiety/athletes/{id}/series?instrument_type= */
export async function getAthleteSeries(
  athleteId: number,
  instrumentType: string,
): Promise<AthleteSeries> {
  const response = await apiClient.get<unknown>(
    `${BASE}/athletes/${athleteId}/series`,
    { params: { instrument_type: instrumentType } },
  );
  return athleteSeriesSchema.parse(response.data);
}

/** GET /api/anxiety/groups/by-event/{eventId} */
export async function getGroupByEvent(eventId: number): Promise<GroupTriage> {
  const response = await apiClient.get<unknown>(
    `${BASE}/groups/by-event/${eventId}`,
  );
  return groupTriageSchema.parse(response.data);
}

/** POST /api/anxiety/import — CSV histórico (multipart). */
export async function importCsv(file: File): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file);
  const response = await apiClient.post<unknown>(`${BASE}/import`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return importResultSchema.parse(response.data);
}

// ---------------------------------------------------------------------------
// Mapeo de errores HTTP a copy en español
// ---------------------------------------------------------------------------

export type AnxietyErrorKind =
  | "consent_missing" // 409
  | "override_needed" // 422
  | "token_gone" // 410
  | "forbidden" // 403
  | "unauthorized" // 401
  | "not_found" // 404
  | "cancelled"
  | "unknown";

export interface AnxietyErrorInfo {
  kind: AnxietyErrorKind;
  message: string;
}

const COPY: Record<AnxietyErrorKind, string> = {
  consent_missing:
    "Falta el consentimiento de la familia para la evaluación psicológica. " +
    "Solicítalo antes de crear la evaluación.",
  override_needed:
    "El instrumento elegido está por debajo del rango validado para menores " +
    "de 13 años. Confirma el override solo con una razón metodológica.",
  token_gone: "Este enlace ya fue usado o expiró.",
  forbidden: "No tienes permiso para esta acción.",
  unauthorized: "Tu sesión expiró. Vuelve a iniciar sesión.",
  not_found: "No se encontró el recurso solicitado.",
  cancelled: "Operación cancelada.",
  unknown: "Ocurrió un error inesperado.",
};

/** Traduce un error de Axios a un objeto consumible por la UI. */
export function mapAnxietyError(error: unknown): AnxietyErrorInfo {
  if (axios.isCancel(error) || (error as Error)?.name === "CanceledError") {
    return { kind: "cancelled", message: COPY.cancelled };
  }
  if (!axios.isAxiosError(error)) {
    return { kind: "unknown", message: COPY.unknown };
  }
  const status = (error as AxiosError).response?.status;
  if (status === 409)
    return { kind: "consent_missing", message: COPY.consent_missing };
  if (status === 422)
    return { kind: "override_needed", message: COPY.override_needed };
  if (status === 410) return { kind: "token_gone", message: COPY.token_gone };
  if (status === 404) return { kind: "not_found", message: COPY.not_found };
  if (status === 403) return { kind: "forbidden", message: COPY.forbidden };
  if (status === 401)
    return { kind: "unauthorized", message: COPY.unauthorized };
  return { kind: "unknown", message: COPY.unknown };
}
