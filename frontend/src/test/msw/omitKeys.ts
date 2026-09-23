/**
 * Helper de fixtures para las variantes de familia (feature 045).
 *
 * El backend **elimina** del payload de una familia las brechas contra el
 * líder/podio (`LEADER_GAP_METRIC_KEYS`, `gap_pct` en evolución) — no las
 * envía como `null`. Los fixtures de familia deben reproducir exactamente
 * eso (claves ausentes), o un test no detectaría un componente que las lea.
 */
export function omitKeys<T extends object, K extends PropertyKey>(
  value: T,
  keys: readonly K[],
): Omit<T, K> {
  const copy = { ...value } as Record<PropertyKey, unknown>;
  for (const key of keys) delete copy[key];
  return copy as Omit<T, K>;
}
