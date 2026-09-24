/**
 * Elegibilidad de captura de pliegues cutáneos (feature 046, US1).
 *
 * Compuertas de UX compartidas por `SkinfoldCapturePage`,
 * `AnthropometryForm` («Guardar y agregar pliegues») y
 * `AnthropometryHistory` («Agregar pliegues»). El backend es la autoridad
 * (`check_min_age` → 409 `athlete_too_young`, `check_interval` → 409
 * `skinfold_interval_too_short`); aquí sólo se evita ofrecer una salida que
 * el servidor rechazaría.
 */
import type { AnthropometricRecord } from "@/types/anthropometry.types";

/** Mirror de `BODY_COMP_MIN_AGE_YEARS` (backend `Settings`, research R4). */
export const SKINFOLD_MIN_AGE_YEARS = 9;

const MILLIS_PER_YEAR = 1000 * 60 * 60 * 24 * 365.25;

/** Ruta del asistente de captura para una evaluación. */
export function skinfoldCapturePath(athleteId: number, recordId: number): string {
  return `/athletes/${athleteId}/anthropometry/${recordId}/skinfolds`;
}

/**
 * Edad decimal en la fecha de la evaluación derivada del propio registro:
 * Mirwald guarda `age_at_phv = edad − maturity_offset` (`services/phv.py`),
 * así que `edad = age_at_phv + maturity_offset` sin necesitar la fecha de
 * nacimiento del menor.
 */
export function ageAtEvaluation(record: AnthropometricRecord): number | null {
  const ageAtPhv = Number(record.age_at_phv);
  const offset = Number(record.maturity_offset);
  if (!Number.isFinite(ageAtPhv) || !Number.isFinite(offset)) return null;
  return ageAtPhv + offset;
}

/** Edad decimal (sin redondear) entre dos fechas ISO `YYYY-MM-DD`, o `null`. */
export function ageFromBirthDate(birthDateIso: string, evaluationDateIso: string): number | null {
  const birth = new Date(`${birthDateIso.slice(0, 10)}T00:00:00Z`).getTime();
  const evaluation = new Date(`${evaluationDateIso.slice(0, 10)}T00:00:00Z`).getTime();
  if (Number.isNaN(birth) || Number.isNaN(evaluation)) return null;
  return (evaluation - birth) / MILLIS_PER_YEAR;
}

/**
 * `true` cuando el intervalo mínimo entre sets bloquea una evaluación de
 * esa fecha (`evaluationDate < nextDueDate`). Comparación lexicográfica de
 * fechas ISO — ambas son `YYYY-MM-DD`.
 */
export function isIntervalBlocked(
  evaluationDateIso: string,
  nextDueDateIso: string | null | undefined,
): boolean {
  if (!nextDueDateIso) return false;
  return evaluationDateIso.slice(0, 10) < nextDueDateIso.slice(0, 10);
}
