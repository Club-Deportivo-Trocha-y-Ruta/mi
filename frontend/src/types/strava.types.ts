/**
 * Tipos del módulo Strava Activity Sync (feature 025).
 *
 * Mirror de los Pydantic schemas en `backend/app/routers/strava_integration.py`
 * y `backend/app/routers/activities.py`. Ver contracts/api.md §A/§C.
 *
 * Privacidad (Ley 1581): NUNCA incluir coordenadas, polyline, mapa o
 * descripción — el backend las excluye por diseño (ver data-model.md §2,
 * "Explicitly ABSENT columns"). No agregar esos campos aquí aunque Strava
 * los exponga en su API pública.
 */

// ---------------------------------------------------------------------------
// A. Connection management
// ---------------------------------------------------------------------------

/**
 * Estado de la conexión Strava de un atleta.
 * Mirror del `status` enum de `strava_connections` + estado sintético `none`
 * (sin fila en BD) que arma el endpoint GET /connection.
 */
export type StravaConnectionStatus = "active" | "disconnected" | "broken" | "none";

/**
 * Respuesta de GET /api/athletes/{athlete_id}/strava/connection.
 */
export interface StravaConnectionOut {
  status: StravaConnectionStatus;
  connected_at: string | null;
  disconnected_at: string | null;
  /** Nombre para mostrar de quien autorizó la conexión (coach o acudiente). */
  authorized_by: string | null;
  last_sync_at: string | null;
}

/**
 * Respuesta de POST /api/athletes/{athlete_id}/strava/connect.
 * `authorize_url` es la URL de OAuth de Strava a la que redirigir al usuario.
 */
export interface StravaConnectResponse {
  authorize_url: string;
}

// ---------------------------------------------------------------------------
// C. Activities & linking
// ---------------------------------------------------------------------------

/**
 * Vínculo de una actividad con una sesión de entrenamiento, si existe.
 * `null` cuando la actividad no está enlazada.
 */
export interface ActivitySessionLink {
  training_session_id: number;
  /** Etiqueta legible de la sesión (fecha/tipo) para mostrar en la UI. */
  session_label: string;
  /** Nombre de quien hizo el enlace (coach/admin). */
  linked_by: string | null;
  linked_at: string | null;
}

/**
 * Estado de la actividad respecto a Strava (¿sigue existiendo upstream?).
 * Mirror del `upstream_state` enum de `strava_activities`.
 */
export type ActivityUpstreamState = "present" | "removed_upstream";

/**
 * Representación de una actividad de Strava sincronizada.
 * Mirror de `ActivityOut` (contracts/api.md §C).
 *
 * NUNCA incluye coordenadas, polyline, mapa ni descripción — ver nota de
 * privacidad al inicio del archivo.
 */
export interface ActivityOut {
  id: number;
  athlete_id: number;
  athlete_name: string;
  name: string;
  sport_type: string;
  start_date_local: string;
  elapsed_time_s: number;
  moving_time_s: number | null;
  distance_m: number | null;
  total_elevation_gain_m: number | null;
  average_heartrate: number | null;
  max_heartrate: number | null;
  is_trainer: boolean;
  upstream_state: ActivityUpstreamState;
  summary_complete: boolean;
  link: ActivitySessionLink | null;
}

/**
 * Filtro de estado de enlace para GET /api/activities y
 * GET /api/athletes/{athlete_id}/activities.
 */
export type ActivityLinkedFilter = "true" | "false" | "all";

/**
 * Parámetros de consulta comunes a los listados de actividades.
 * Todos opcionales — ausencia = sin filtro (o default del backend).
 */
export interface ActivityListParams {
  linked?: ActivityLinkedFilter;
  athlete_id?: number;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}

/**
 * Respuesta paginada de los listados de actividades.
 * Mirror de `ActivityListOut` (backend `schemas/strava.py`).
 */
export interface ActivityListResponse {
  items: ActivityOut[];
  total: number;
  page: number;
  page_size: number;
}

/**
 * Respuesta de GET /api/training-sessions/{session_id}/activities (FR-009).
 * Sin paginación — el volumen por sesión es acotado (asistentes del día).
 */
export interface SessionActivitiesOut {
  items: ActivityOut[];
}

/**
 * Una sesión de entrenamiento candidata para vincular una actividad
 * (FR-008). Mirror de `SessionSuggestionOut` (backend `schemas/strava.py`).
 *
 * `scheduled_date` llega como datetime NAIVE que representa la hora local
 * del club (combina `scheduled_date` + `scheduled_start_time` de
 * `TrainingSession` en el backend) — misma convención que
 * `ActivityOut.start_date_local`. NO tratar como UTC al formatear (ver nota
 * de `formatActivityDateTime` en `ActivityCard.tsx`).
 */
export interface SessionSuggestion {
  training_session_id: number;
  scheduled_date: string;
  session_kind: string | null;
  location: string | null;
  technical_focus: string | null;
  /** true cuando la sesión es del mismo día calendario que la actividad. */
  same_day: boolean;
  /** true cuando el atleta dueño de la actividad fue convocado a la sesión. */
  athlete_in_attendance: boolean;
}

/**
 * Respuesta de GET /api/activities/{id}/session-suggestions.
 * `suggestions` ya viene ordenada por el backend: mismo día + asistencia
 * primero.
 */
export interface SessionSuggestionListResponse {
  suggestions: SessionSuggestion[];
}

/**
 * Body de PATCH /api/activities/{id}/link.
 * `training_session_id` como número enlaza/re-enlaza; `null` desenlaza.
 */
export interface LinkUpdateIn {
  training_session_id: number | null;
}
