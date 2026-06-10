/**
 * usePrefetchOnIntent — prefetch "likely-next" data on user intent
 * (feature 012, US3).
 *
 * Devuelve un callback para disparar `queryClient.prefetchQuery` cuando el
 * usuario muestra intención de abrir un detalle (hover en desktop,
 * touch-start en tablet/móvil). Así el detalle suele renderizar sin estado
 * de carga visible con servidor caliente (SC-006).
 *
 * Dedupe: cada queryKey se prefetcha como máximo UNA vez por carga de la app
 * (Set a nivel de módulo) — los hovers repetidos no generan tráfico extra.
 * Además `prefetchQuery` respeta `staleTime`: si los datos ya están frescos
 * en caché, no dispara red.
 *
 * RBAC sin cambios (FR-013): el prefetch reutiliza exactamente la misma
 * queryKey/queryFn autenticada del hook de detalle correspondiente.
 */
import { useCallback } from "react";
import { hashKey, useQueryClient } from "@tanstack/react-query";
import type { QueryFunction, QueryKey } from "@tanstack/react-query";

const prefetchedKeys = new Set<string>();

export interface PrefetchOnIntentOptions<T> {
  queryKey: QueryKey;
  queryFn: QueryFunction<T>;
  /** Igualar al staleTime del hook de detalle (default 5 min, el global). */
  staleTime?: number;
}

export function usePrefetchOnIntent() {
  const queryClient = useQueryClient();

  return useCallback(
    <T,>({
      queryKey,
      queryFn,
      staleTime = 5 * 60_000,
    }: PrefetchOnIntentOptions<T>): void => {
      const hash = hashKey(queryKey);
      if (prefetchedKeys.has(hash)) return;
      prefetchedKeys.add(hash);
      void queryClient.prefetchQuery({ queryKey, queryFn, staleTime });
    },
    [queryClient],
  );
}

/** Test-only: limpia el dedupe entre tests. */
export function __resetPrefetchOnIntentForTests(): void {
  prefetchedKeys.clear();
}
