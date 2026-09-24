import type { RunEvent } from "@/types/raceAnalysis.types";

/**
 * `hitl_request` vigente de un run, o `undefined` si no hay ninguno o el coach
 * ya respondió. Se recorre hacia atrás y se corta en el primer `hitl_response`
 * para que un request viejo no reviva la tarjeta. No se matchea por
 * `node === "hitl_gate_review"`: ese nodo emite node_start/node_end (sin
 * `draft_markdown`) incluso cuando auto-aprueba.
 */
export function findPendingHitlEvent(
  events: RunEvent[] | undefined,
): RunEvent | undefined {
  if (!events) return undefined;
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const e = events[i];
    if (e.type === "hitl_response") return undefined;
    if (e.type === "hitl_request" || e.type === "hitl_required") return e;
  }
  return undefined;
}

/**
 * Fragmentos del borrador que mencionan la brecha con el líder/podio
 * (`payload.family_gap_mentions` del `hitl_request`, feature 045 T062/FR-022).
 * Devuelve `[]` cuando el evento no existe, no trae la clave (backend previo,
 * `hitl_required` legado) o el valor no es una lista de textos: la tarjeta de
 * aprobación sólo muestra el aviso si hay al menos un fragmento. Se descartan
 * las entradas vacías o no textuales; el backend ya topa en 3 fragmentos.
 */
export function familyGapMentionsFromEvent(
  event: RunEvent | undefined,
): string[] {
  const raw = event?.payload?.family_gap_mentions;
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (item): item is string => typeof item === "string" && item.trim() !== "",
  );
}
