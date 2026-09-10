/**
 * Tipos del informe de actividad por entrenador (feature 041 — gobernanza
 * multi-coach, US7). Contrato:
 * specs/041-multi-coach-governance/contracts/coach-activity-report.md §1.2.
 *
 * Mirror de `backend/app/schemas/coach_activity.py::CoachActivityOut` y sus
 * modelos anidados — confirmado leyendo ese archivo y
 * `backend/app/routers/audit.py::get_coach_activity` (endpoint ya en el
 * árbol al momento de escribir este módulo). `role` usa los mismos cuatro
 * valores que `UserRole` (`@/types/enums`).
 *
 * Privacidad (Ley 1581): este payload solo contiene nombres de personal
 * adulto y enteros — ningún dato identificable de un deportista viaja acá
 * (§5 del contrato). `CoachRef.display_name` es siempre de un adulto.
 */
import type { UserRole } from "@/types/enums";

/** Referencia mínima a un entrenador del informe. */
export interface CoachRef {
  user_id: number;
  display_name: string;
  role: UserRole;
  /**
   * `false` cuando la cuenta fue desactivada — un entrenador desactivado
   * sigue apareciendo en los períodos que trabajó (FR-013), nunca
   * desaparece del histórico.
   */
  is_active: boolean;
}

export interface ClubSessionCounters {
  planned: number;
  executed: number;
  cancelled: number;
  /** Deduplicado: una sesión codirigida cuenta una sola vez acá. */
  total: number;
}

export interface CoachSessionCounters extends ClubSessionCounters {
  /**
   * Subconjunto de `total` cuyas sesiones tienen 2+ entrenadores asignados.
   * No es un quinto estado disjunto: `planned + executed + cancelled === total`
   * y `co_led <= total` (§2 del contrato).
   */
  co_led: number;
}

export interface ResultsOperationsCounters {
  imports: number;
  revisions: number;
  competitor_links: number;
  total: number;
}

export interface DocumentCounters {
  reports_approved: number;
  newsletters_approved: number;
  newsletters_sent: number;
  exports: number;
}

/**
 * Totales del club. Incluyen lo hecho por administradores y por actores
 * automáticos, así que `sum(coaches[].x)` no tiene por qué coincidir con
 * estos números salvo en `sessions` (§2, último párrafo del contrato).
 */
export interface ClubTotals {
  sessions: ClubSessionCounters;
  attendance_entries_recorded: number;
  ai_runs_launched: number;
  results_operations: ResultsOperationsCounters;
  documents: DocumentCounters;
  audit_entries_count: number;
}

/** Una fila del informe: un entrenador y sus contadores del período. */
export interface CoachActivityRow {
  coach: CoachRef;
  sessions: CoachSessionCounters;
  attendance_entries_recorded: number;
  ai_runs_launched: number;
  results_operations: ResultsOperationsCounters;
  documents: DocumentCounters;
  audit_entries_count: number;
}

/** Respuesta de `GET /api/clubs/{club_id}/coach-activity` (§1.2). */
export interface CoachActivityOut {
  club_id: number;
  /** `YYYY-MM-DD`, límite inferior inclusive. */
  from: string;
  /** `YYYY-MM-DD`, límite superior inclusive. */
  to: string;
  computed_at: string;
  club_totals: ClubTotals;
  coaches: CoachActivityRow[];
}

/** Query params de `GET /clubs/{club_id}/coach-activity` (§1.1). */
export interface CoachActivityParams {
  from: string;
  to: string;
  coach_user_id?: number;
}
