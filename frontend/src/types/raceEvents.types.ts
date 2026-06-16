/**
 * Tipos del módulo race-events.
 *
 * Mirror de los Pydantic schemas en `backend/app/schemas/race_events.py`.
 *
 * Endpoints cubiertos:
 *   - PATCH /api/race-analysis/race-events/{id}/conditions   (F-COND)
 *   - POST  /api/race-analysis/race-events/                  (CF3)
 *   - PATCH /api/race-analysis/race-events/{id}              (CF3)
 *   - DELETE /api/race-analysis/race-events/{id}             (CF3)
 *   - GET   /api/race-analysis/race-events/                  (CF3)
 *
 * Privacidad: este módulo no contiene datos de menores; sólo metadatos
 * logísticos y climáticos de las jornadas.
 */

import type { SurfaceCondition } from "@/types/raceImports.types";

// Re-exportamos SurfaceCondition para que los consumidores de race-events
// no necesiten importar desde raceImports.types.
export type { SurfaceCondition } from "@/types/raceImports.types";

// ---------------------------------------------------------------------------
// Catálogos de UI
// ---------------------------------------------------------------------------

/**
 * Valores válidos de `surface_condition` en orden de "peor a mejor" para
 * uso en selects y toggles de la UI.
 */
export const SURFACE_CONDITIONS: SurfaceCondition[] = [
  "seca",
  "humeda",
  "barro",
  "lluvia",
  "mixta",
];

/**
 * Etiquetas en español para cada condición de superficie.
 * Usar en <Select> o <Badge> del wizard de condiciones.
 */
export const SURFACE_CONDITION_LABELS: Record<SurfaceCondition, string> = {
  seca: "Seca",
  humeda: "Húmeda",
  barro: "Barro",
  lluvia: "Lluvia",
  mixta: "Mixta",
};

/**
 * Altitudes aproximadas (msnm) de las sedes habituales de la Copa Valle XCO.
 * Permite autocompletar el campo `altitude_msnm` al seleccionar ubicación.
 *
 * Fuente: datos topográficos de los municipios del Valle del Cauca.
 */
export const VENUE_ALTITUDES: Record<string, number> = {
  Sevilla: 1620,
  Ginebra: 1080,
  Cali: 1000,
  Palmira: 1001,
  Roldanillo: 950,
  Yumbo: 1021,
  "La Cumbre": 1581,
};

// ---------------------------------------------------------------------------
// Response del PATCH /race-events/{id}/conditions
// ---------------------------------------------------------------------------

/**
 * Cuerpo completo que devuelve el backend tras actualizar condiciones.
 * Incluye los 5 campos de condición + metadatos de auditoría.
 */
export interface RaceEventConditions {
  race_event_id: number;
  climate: string | null;
  /** El backend serializa `Decimal` como string; parsear con `parseFloat` si necesitas número. */
  temperature_c: string | null;
  surface_condition: SurfaceCondition | null;
  altitude_msnm: number | null;
  weather_notes: string | null;
  updated_at: string; // ISO 8601 datetime
}

// ---------------------------------------------------------------------------
// Body del PATCH /race-events/{id}/conditions
// ---------------------------------------------------------------------------

/**
 * Payload parcial para actualizar condiciones de un evento de carrera.
 * Todos los campos son opcionales — el backend aplica merge (PATCH semántico).
 *
 * `temperature_c` acepta string o number para compatibilidad con inputs HTML
 * (type="number" devuelve string en onChange). El API client lo convierte a
 * string antes del envío (JSON serialization).
 */
export interface RaceEventConditionsUpdate {
  climate?: string | null;
  temperature_c?: string | number | null;
  surface_condition?: SurfaceCondition | null;
  altitude_msnm?: number | null;
  weather_notes?: string | null;
}

// ---------------------------------------------------------------------------
// CRUD race-events (CF3) — mirror de schemas backend
// ---------------------------------------------------------------------------

/**
 * Estados posibles de un evento de carrera.
 * Mirror de `RaceEventStatus` enum del backend.
 */
export type RaceEventStatus = "scheduled" | "completed" | "cancelled";

/**
 * Payload de creación de un evento de carrera.
 * Mirror de `RaceEventCreate` del backend.
 *
 * Los campos de condiciones son opcionales al crear; se pueden completar
 * después vía PATCH /{id}/conditions (F-COND).
 */
export interface RaceEventCreate {
  series_id: number;
  /**
   * Número de válida en la serie. Requerido para series tipo copa.
   * Omitido para campeonatos — el backend fuerza 1 (spec 014).
   */
  sequence_number?: number;
  name: string;
  /** Fecha ISO YYYY-MM-DD (sin hora). */
  event_date: string;
  location?: string | null;
  is_championship?: boolean;
  status?: RaceEventStatus;
  /**
   * Si es `true` (default del backend), el backend crea un `calendar_event`
   * ligado 1:1 a esta válida en el mismo request. Si es `false`, no se crea
   * ningún calendar_event (el coach puede asociarlo después vía
   * `POST /{id}/calendar-link`).
   *
   * FR-024: "When creating a competition, the system MUST offer a default-on
   * option to create a linked calendar event, with a visible opt-out."
   */
  create_calendar_event?: boolean;
  // Condiciones opcionales — heredan validaciones de _ConditionsFields backend
  climate?: string | null;
  /** El backend almacena Decimal; acepta string o number desde el form. */
  temperature_c?: string | number | null;
  surface_condition?: SurfaceCondition | null;
  altitude_msnm?: number | null;
  weather_notes?: string | null;
}

/**
 * Payload para asociar un `calendar_event` ya existente a una válida.
 * `POST /api/race-analysis/race-events/{id}/calendar-link`
 *
 * 409 si alguna de las dos entidades ya tiene un vínculo activo (1:1 estricto).
 * 404 si el `calendar_event_id` no existe.
 */
export interface RaceEventCalendarLinkBody {
  calendar_event_id: number;
}

/**
 * Respuesta mínima del endpoint calendar-link.
 * El backend retorna el `RaceEventRead` actualizado (con `has_calendar_event=true`).
 */
export type RaceEventCalendarLinkResponse = Pick<
  RaceEventRead,
  "id" | "has_calendar_event"
>;

/**
 * Payload de actualización parcial de un evento de carrera.
 * `extra=forbid` en el backend: no enviar campos de condiciones aquí,
 * usar PATCH /{id}/conditions para eso.
 */
export interface RaceEventUpdate {
  name?: string;
  event_date?: string;
  location?: string | null;
  sequence_number?: number;
  status?: RaceEventStatus;
  is_championship?: boolean;
}

/**
 * Respuesta completa de creación/actualización de un evento de carrera.
 * Mirror de `RaceEventRead` del backend.
 */
export interface RaceEventRead {
  id: number;
  series_id: number;
  sequence_number: number;
  name: string;
  event_date: string;
  location: string | null;
  is_championship: boolean;
  status: RaceEventStatus;
  // Condiciones (pueden ser null si aún no se han registrado)
  climate: string | null;
  /** Serializado como string por el backend (Decimal). */
  temperature_c: string | null;
  surface_condition: SurfaceCondition | null;
  altitude_msnm: number | null;
  weather_notes: string | null;
  // Auditoría
  created_at: string;
  updated_at: string;
  created_by_user_id: number;
  /** true si el evento ya tiene un calendar_event asociado. Backend calcula en GET /{id}. */
  has_calendar_event?: boolean;
}

/**
 * Ítem reducido para la vista de lista de eventos.
 * Mirror de `RaceEventListItem` del backend.
 *
 * `conditions_completeness` resume qué tan completo está el registro de
 * condiciones — útil para mostrar badge visual sin calcular en frontend.
 */
export interface RaceEventListItem {
  id: number;
  series_id: number;
  sequence_number: number;
  name: string;
  event_date: string;
  location: string | null;
  is_championship: boolean;
  status: RaceEventStatus;
  /** true si la válida ya tiene race_results importados. */
  has_results: boolean;
  /** true si tiene un calendar_event asociado. */
  has_calendar_event: boolean;
  conditions_completeness: "complete" | "partial" | "empty";
}

// ---------------------------------------------------------------------------
// Response del POST /race-events/{id}/calendar-event (008-associate-competition-calendar)
// ---------------------------------------------------------------------------

/**
 * Respuesta del endpoint que crea y vincula automáticamente un CalendarEvent
 * de tipo "all-day" a partir de los datos de la propia válida.
 *
 * `POST /api/race-analysis/race-events/{id}/calendar-event`
 * RBAC: coach only (FR-008).
 *
 * 201 → evento creado y vinculado.
 * 409 → la válida ya tiene un calendar_event (1:1 estricto).
 */
export interface CalendarAutoCreateResponse {
  race_event_id: number;
  calendar_event_id: number;
  /** Siempre `true` en la respuesta 201. */
  has_calendar_event: true;
}

/**
 * Response paginado del GET /race-events/.
 */
export interface RaceEventListResponse {
  items: RaceEventListItem[];
  total: number;
}

/**
 * Filtros opcionales para el GET /race-events/.
 * Todos son opcionales — ausencia = sin filtro.
 */
export interface RaceEventListFilters {
  /** Año de temporada (ej. 2026). */
  season?: number;
  status?: RaceEventStatus;
  /** true = solo campeonatos, false = solo válidas regulares. */
  is_championship?: boolean;
  /** Filtro parcial por nombre de ubicación. */
  location?: string;
}
