/**
 * API client del módulo Strava Activity Sync (feature 025).
 *
 * Auth: JWT via interceptor en apiClient.
 *
 * Endpoints cubiertos (contracts/api.md §A y §C):
 *   - GET    /api/athletes/{athlete_id}/strava/connection  → getStravaConnection
 *   - POST   /api/athletes/{athlete_id}/strava/connect      → connectStrava
 *   - DELETE /api/athletes/{athlete_id}/strava/connection   → disconnectStrava
 *   - GET    /api/athletes/{athlete_id}/activities           → getAthleteActivities
 *   - GET    /api/activities                                 → getActivities (revisión coach, T031)
 *   - GET    /api/training-sessions/{session_id}/activities  → getSessionActivities
 *   - GET    /api/activities/{id}/session-suggestions         → getSessionSuggestions (T032)
 *   - PATCH  /api/activities/{id}/link                        → linkActivity (T032)
 *
 * Privacidad (Ley 1581): las respuestas de actividades NUNCA incluyen
 * coordenadas, polyline, mapa ni descripción — ver types/strava.types.ts.
 */
import { apiClient } from "@/api/client";
import type {
  ActivityListParams,
  ActivityListResponse,
  ActivityOut,
  SessionActivitiesOut,
  SessionSuggestionListResponse,
  StravaConnectResponse,
  StravaConnectionOut,
} from "@/types/strava.types";

/**
 * GET /api/athletes/{athlete_id}/strava/connection
 *
 * Estado actual de la conexión Strava del atleta.
 * RBAC: admin, coach (club del atleta), padre/acudiente (su hijo).
 *
 * `status: "none"` cuando nunca se ha conectado (sin fila en BD).
 * 403 fuera del alcance RBAC; 404 si el atleta no existe.
 */
export async function getStravaConnection(
  athleteId: number,
  options?: { signal?: AbortSignal },
): Promise<StravaConnectionOut> {
  const response = await apiClient.get<StravaConnectionOut>(
    `/api/athletes/${athleteId}/strava/connection`,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * POST /api/athletes/{athlete_id}/strava/connect
 *
 * Inicia el flujo OAuth de Strava. RBAC: admin, coach (club del atleta),
 * padre/acudiente (su hijo). Autorizar la conexión OAuth ES el consentimiento
 * afirmativo — no se exige un consentimiento previo aparte.
 *
 * Si Strava está deshabilitado en el backend → 503.
 *
 * El caller debe redirigir el navegador a `authorize_url` (no es una
 * navegación SPA — es la página de autorización de Strava).
 */
export async function connectStrava(
  athleteId: number,
  options?: { signal?: AbortSignal },
): Promise<StravaConnectResponse> {
  const response = await apiClient.post<StravaConnectResponse>(
    `/api/athletes/${athleteId}/strava/connect`,
    undefined,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * DELETE /api/athletes/{athlete_id}/strava/connection
 *
 * Desconexión iniciada por la familia/coach (FR-014). RBAC: admin, coach
 * (club del atleta), padre/acudiente (su hijo).
 *
 * Las actividades ya sincronizadas se conservan — solo se detiene la
 * sincronización. 204 sin body en éxito; 404 si no hay conexión.
 */
export async function disconnectStrava(
  athleteId: number,
  options?: { signal?: AbortSignal },
): Promise<void> {
  await apiClient.delete(`/api/athletes/${athleteId}/strava/connection`, {
    signal: options?.signal,
  });
}

/**
 * GET /api/athletes/{athlete_id}/activities
 *
 * Lista paginada de actividades Strava del atleta. RBAC: admin, coach
 * (club), padre/acudiente (su hijo — FR-011); 403 si el padre solicita un
 * atleta de otra familia.
 *
 * `params.athlete_id` no aplica aquí (el atleta ya está en la ruta) — se
 * omite del tipo compartido `ActivityListParams` en el request.
 */
export async function getAthleteActivities(
  athleteId: number,
  params?: Omit<ActivityListParams, "athlete_id">,
  options?: { signal?: AbortSignal },
): Promise<ActivityListResponse> {
  const response = await apiClient.get<ActivityListResponse>(
    `/api/athletes/${athleteId}/activities`,
    { params, signal: options?.signal },
  );
  return response.data;
}

/**
 * GET /api/activities
 *
 * Lista paginada de actividades Strava para la revisión del coach (FR-010).
 * RBAC: admin (todos los clubes), coach (solo atletas de sus clubes) — vía
 * `list_activities` en el backend; 403 para roles parent/athlete (su vista
 * de solo lectura vive en `getAthleteActivities`).
 *
 * Filtros: `linked` (`true`/`false`/`all`, default backend `all`),
 * `athlete_id`, `date_from`/`date_to` (sobre `start_date_local`). Con
 * `linked=all` el backend ordena las actividades sin enlazar primero.
 */
export async function getActivities(
  params?: ActivityListParams,
  options?: { signal?: AbortSignal },
): Promise<ActivityListResponse> {
  const response = await apiClient.get<ActivityListResponse>("/api/activities", {
    params,
    signal: options?.signal,
  });
  return response.data;
}

/**
 * GET /api/training-sessions/{session_id}/activities
 *
 * Actividades Strava enlazadas a una sesión de entrenamiento, de todos los
 * atletas asistentes (FR-009). RBAC: reutiliza `can_view_session` (admin,
 * coach del club de la sesión, padre solo si convocó a su hijo — las filas
 * ya llegan acotadas a sus propios hijos para el rol parent).
 */
export async function getSessionActivities(
  sessionId: number,
  options?: { signal?: AbortSignal },
): Promise<SessionActivitiesOut> {
  const response = await apiClient.get<SessionActivitiesOut>(
    `/api/training-sessions/${sessionId}/activities`,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * GET /api/activities/{id}/session-suggestions
 *
 * Sesiones candidatas para vincular una actividad (FR-008). RBAC: admin,
 * coach (club del atleta dueño de la actividad); 403 fuera de alcance.
 *
 * El backend ya ordena `suggestions`: mismo día + asistencia del atleta
 * primero, dentro de una ventana de ±1 día respecto a la actividad.
 */
export async function getSessionSuggestions(
  activityId: number,
  options?: { signal?: AbortSignal },
): Promise<SessionSuggestionListResponse> {
  const response = await apiClient.get<SessionSuggestionListResponse>(
    `/api/activities/${activityId}/session-suggestions`,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * PATCH /api/activities/{id}/link
 *
 * Vincula, re-vincula o desvincula una actividad a una sesión de
 * entrenamiento (FR-007). RBAC: admin, coach (club del atleta) ÚNICAMENTE
 * — 403 para parent/athlete-role.
 *
 * `trainingSessionId` como número enlaza/re-enlaza; `null` desenlaza.
 * `422` cuando la sesión no pertenece al club del atleta.
 */
export async function linkActivity(
  activityId: number,
  trainingSessionId: number | null,
  options?: { signal?: AbortSignal },
): Promise<ActivityOut> {
  const response = await apiClient.patch<ActivityOut>(
    `/api/activities/${activityId}/link`,
    { training_session_id: trainingSessionId },
    { signal: options?.signal },
  );
  return response.data;
}
