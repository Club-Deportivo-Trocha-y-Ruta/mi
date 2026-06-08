/**
 * API client para el módulo Asistente IA de sesiones (Feature 006).
 *
 * Endpoints:
 *   POST /api/clubs/{clubId}/session-assistant/clarify
 *   POST /api/clubs/{clubId}/session-assistant/draft
 *
 * Privacy contract: selected_athlete_ids se usa solo server-side para calcular
 * mezcla de edades; nunca se envía nombre o identificador de menor al modelo IA.
 */
import { apiClient } from "@/api/client";

// ---------------------------------------------------------------------------
// Tipos — espejo del contrato en contracts/session-assistant.md
// ---------------------------------------------------------------------------

export type AthleteCallUpCriterion =
  | "todos_convocados"
  | "grupo_10_12"
  | "grupo_13_15"
  | "ninguno";

export interface ClarifyOption {
  label: string;
  description: string;
}

export interface ClarifyQuestion {
  id: string;
  header: string;
  question: string;
  multi_select: boolean;
  allow_other: boolean;
  options: ClarifyOption[];
}

export interface SessionClarifyResponse {
  questions: ClarifyQuestion[];
  model: string;
}

export interface SessionAnswer {
  question_id: string;
  selected_labels: string[];
  other_text: string | null;
}

export interface SessionDraftResponse {
  technical_focus: string;
  objectives: string | null;
  description: string | null;
  duration_min: number;
  session_kind: "entrenamiento" | "actividad_conjunta" | "salida" | "otro";
  location: string | null;
  scheduled_date: string | null;
  scheduled_start_time: string | null;
  athlete_call_up: AthleteCallUpCriterion;
  notes: string | null;
  model: string;
}

// ---------------------------------------------------------------------------
// Request shapes
// ---------------------------------------------------------------------------

export interface SessionClarifyRequest {
  intent_text?: string | null;
  selected_athlete_ids?: number[];
}

export interface SessionDraftRequest {
  intent_text?: string | null;
  selected_athlete_ids?: number[];
  answers?: SessionAnswer[];
}

// ---------------------------------------------------------------------------
// Funciones de cliente
// ---------------------------------------------------------------------------

const BASE = (clubId: number) =>
  `/api/clubs/${clubId}/session-assistant`;

/**
 * Solicita un lote de preguntas de clarificación al asistente IA.
 * 0 preguntas en la respuesta → el cliente puede llamar directamente a draft().
 */
export async function clarify(
  clubId: number,
  payload: SessionClarifyRequest,
): Promise<SessionClarifyResponse> {
  const response = await apiClient.post<SessionClarifyResponse>(
    `${BASE(clubId)}/clarify`,
    payload,
  );
  return response.data;
}

/**
 * Solicita un borrador de sesión basado en la intención y las respuestas.
 * Acepta respuestas parciales o vacías (FR-015).
 */
export async function draft(
  clubId: number,
  payload: SessionDraftRequest,
): Promise<SessionDraftResponse> {
  const response = await apiClient.post<SessionDraftResponse>(
    `${BASE(clubId)}/draft`,
    payload,
  );
  return response.data;
}
