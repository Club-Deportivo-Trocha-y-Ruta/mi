/**
 * applyOverrides — fusión pura de un `StageLog` con un `StageOverrides` de
 * estudio, feature 038 (data-model.md §6).
 *
 * Usado para el preview optimista en `AthleteNewsletterStudioPage`: el
 * draft local de overrides (`stage_overrides`) se aplica sobre el
 * `stage_log` que vino de la query, sin mutar ninguno de los dos.
 * `clearOverrideBlock` es el inverso: limpia el override de un bloque tras
 * "Regenerar" (el backend ya lo hizo, pero el draft local en memoria
 * también debe olvidarlo para no re-enviarlo en el próximo PATCH).
 */
import type {
  RegenerableBlock,
  StageLog,
  StageOverrides,
} from "@/types/stageLog.types";

/** Claves de `StageOverrides` — usado por `clearOverrideBlock`. */
const OVERRIDE_KEYS: readonly RegenerableBlock[] = [
  "stage_title",
  "summit_caption",
  "observations",
  "next_segment_text",
  "family_compass",
  "analyst_reading",
];

/**
 * Fusiona `overrides` sobre `stageLog` sin mutar ninguno de los dos
 * argumentos. Campos ausentes en `overrides` dejan el valor original de
 * `stageLog` intacto; un override solo reemplaza el bloque que nombra.
 */
export function applyOverrides(
  stageLog: StageLog,
  overrides: StageOverrides | null | undefined,
): StageLog {
  if (!overrides) return stageLog;

  const merged: StageLog = { ...stageLog };

  if (overrides.stage_title !== undefined) {
    merged.stage_title = overrides.stage_title;
  }

  if (overrides.summit_caption !== undefined && stageLog.summit) {
    merged.summit = { ...stageLog.summit, caption: overrides.summit_caption };
  }

  if (overrides.observations !== undefined) {
    merged.observations = overrides.observations;
  }

  if (overrides.analyst_reading !== undefined && stageLog.analyst_reading) {
    merged.analyst_reading = {
      ...stageLog.analyst_reading,
      headline_family: overrides.analyst_reading.headline_family,
      action_family: overrides.analyst_reading.action_family,
    };
  }

  if (overrides.next_segment_text !== undefined && stageLog.next_segment) {
    merged.next_segment = {
      ...stageLog.next_segment,
      text: overrides.next_segment_text,
    };
  }

  if (overrides.family_compass !== undefined) {
    merged.family_compass = overrides.family_compass;
  }

  return merged;
}

/**
 * Devuelve un nuevo `StageOverrides` sin la clave de `block` — el inverso
 * de aplicar un override, para usar tras un "Regenerar" exitoso (el
 * backend ya limpió el override de ese bloque y puso `block_states[block]
 * = "ai""`; el draft local del estudio debe reflejarlo).
 */
export function clearOverrideBlock(
  overrides: StageOverrides | null | undefined,
  block: RegenerableBlock,
): StageOverrides {
  if (!overrides) return {};
  const next = { ...overrides };
  delete next[block];
  return next;
}

/** Lista de bloques regenerables — reexportada para consumo de UI/tests. */
export const REGENERABLE_OVERRIDE_KEYS = OVERRIDE_KEYS;
