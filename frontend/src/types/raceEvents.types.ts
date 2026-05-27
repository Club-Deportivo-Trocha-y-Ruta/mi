/**
 * Tipos del módulo race-events — condiciones de carrera (F-COND).
 *
 * Mirror de los Pydantic schemas en `backend/app/schemas/race_events.py`.
 * Endpoint: PATCH /api/race-analysis/race-events/{id}/conditions
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
