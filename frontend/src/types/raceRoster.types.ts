/**
 * Tipos del módulo de convocatoria (roster) para eventos de carrera.
 *
 * Mirror de los schemas Pydantic del backend para:
 *   - GET    /api/race-analysis/race-events/{id}/roster
 *   - POST   /api/race-analysis/race-events/{id}/roster
 *   - PATCH  /api/race-analysis/race-events/{id}/roster/{entry_id}
 *   - DELETE /api/race-analysis/race-events/{id}/roster/{entry_id}
 *
 * Privacidad: los campos de nombre de atleta son display-only y están
 * bajo RBAC en el backend. Para padres, el backend filtra a solo el
 * hijo propio antes de responder.
 */

// ---------------------------------------------------------------------------
// Catálogos
// ---------------------------------------------------------------------------

/**
 * Estados posibles de una entrada de convocatoria.
 *   - called_up  → convocado (estado inicial tras agregar al roster)
 *   - confirmed  → confirmó participación / inscripción oficial
 *   - withdrawn  → retirado de la convocatoria (lesión, viaje, etc.)
 */
export type RosterEntryStatus = "called_up" | "confirmed" | "withdrawn";

export const ROSTER_STATUS_LABELS: Record<RosterEntryStatus, string> = {
  called_up: "Convocado",
  confirmed: "Confirmado",
  withdrawn: "Retirado",
};

// ---------------------------------------------------------------------------
// Entrada del roster
// ---------------------------------------------------------------------------

/**
 * Una entrada individual en el roster de convocados.
 */
export interface RosterEntry {
  /** ID de la entrada en la tabla race_roster. */
  id: number;
  /** ID del atleta del club. */
  athlete_id: number;
  /** Nombre para mostrar (calculado en backend). */
  athlete_name: string;
  /** Estado actual de la convocatoria. */
  status: RosterEntryStatus;
  /** Nota libre del entrenador (lesión, condición especial, etc.). */
  note: string | null;
}

// ---------------------------------------------------------------------------
// Reconciliación
// ---------------------------------------------------------------------------

/**
 * Resumen de discrepancias entre la convocatoria y los resultados importados.
 *
 * - called_up_no_result:  athlete_ids convocados que no aparecen en los resultados
 *                          (pueden haber llegado tarde o no corrido).
 * - result_not_called_up: athlete_ids con resultado importado que no estaban
 *                          en la convocatoria (atleta "sorpresa").
 */
export interface RosterReconciliation {
  called_up_no_result: number[];
  result_not_called_up: number[];
}

// ---------------------------------------------------------------------------
// Respuesta GET /roster
// ---------------------------------------------------------------------------

export interface RaceRosterResponse {
  race_event_id: number;
  entries: RosterEntry[];
  reconciliation: RosterReconciliation;
}

// ---------------------------------------------------------------------------
// Payloads de mutación
// ---------------------------------------------------------------------------

/** POST /roster — agregar atleta al roster. */
export interface RosterEntryCreate {
  athlete_id: number;
  status?: RosterEntryStatus;
  note?: string | null;
}

/** PATCH /roster/{entry_id} — actualizar estado o nota. */
export interface RosterEntryUpdate {
  status?: RosterEntryStatus;
  note?: string | null;
}
