/**
 * Singleton handle al QueryClient para módulos que no pueden depender
 * directamente del provider (Zustand stores, código no-React, etc.).
 *
 * Motivación: el store de auth (Zustand) necesita ejecutar
 * `queryClient.clear()` en `logout()` para evitar fugas de cache entre
 * cuentas en máquinas compartidas (R1 del Wave 2 de privacy hardening).
 *
 * Como Zustand stores se evalúan en el load del módulo (antes de que
 * React monte el QueryClientProvider), no podemos importar el client
 * directamente — habría ciclo de dependencias. Este módulo expone un
 * setter que se llama una vez desde `App.tsx` tras crear el client.
 */
import type { QueryClient, QueryKey } from "@tanstack/react-query";

let _queryClient: QueryClient | null = null;

/**
 * Registra el QueryClient singleton. Debe llamarse una sola vez, durante
 * el bootstrap de la app (App.tsx tras `new QueryClient(...)`).
 */
export function setQueryClient(qc: QueryClient): void {
  _queryClient = qc;
}

/**
 * Recupera el QueryClient registrado. Devuelve `null` si todavía no
 * está inicializado (típico en tests sin bootstrap completo).
 *
 * Quien lo consuma debe manejar el caso `null` defensivamente (log
 * warning + no-op).
 */
export function getQueryClient(): QueryClient | null {
  return _queryClient;
}

/**
 * Purga del cache cualquier query asociada a un atleta específico.
 *
 * Pensada para Wave 4: cuando un padre cambia de hijo en el
 * AthleteSwitcher, las queries del hijo anterior deben evacuarse para
 * que el siguiente render no muestre datos cruzados ni siquiera por un
 * frame.
 *
 * Estrategia: examina cada QueryKey buscando:
 *   1) un objeto plano con `athlete_id === athleteId` (filtros)
 *   2) el `athleteId` como elemento numérico directo del array
 *      (patrón actual de keys con userId al inicio y athleteId al final)
 *
 * No se llama todavía desde producción. Queda listo para Wave 4.
 */
export function purgeQueriesForAthlete(athleteId: number): void {
  const qc = _queryClient;
  if (!qc) {
    // En runtime real no debería ocurrir; en tests es esperable.
    // eslint-disable-next-line no-console
    console.warn(
      "[queryClientHandle] purgeQueriesForAthlete llamado sin QueryClient registrado",
    );
    return;
  }
  qc.removeQueries({
    predicate: (q) => keyReferencesAthlete(q.queryKey, athleteId),
  });
}

function keyReferencesAthlete(key: QueryKey, athleteId: number): boolean {
  for (const part of key) {
    if (part === athleteId) return true;
    if (part && typeof part === "object" && !Array.isArray(part)) {
      const obj = part as Record<string, unknown>;
      if ("athlete_id" in obj && obj.athlete_id === athleteId) return true;
      if ("athleteId" in obj && obj.athleteId === athleteId) return true;
    }
  }
  return false;
}

/**
 * Reset interno solo para tests. No usar en código de producción.
 */
export function __resetQueryClientHandleForTests(): void {
  _queryClient = null;
}
