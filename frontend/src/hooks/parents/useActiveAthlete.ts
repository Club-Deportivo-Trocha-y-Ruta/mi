/**
 * useActiveAthlete — Hook helper que combina la lista de atletas del padre
 * autenticado con el id "activo" persistido en `useParentContextStore`.
 *
 * Reglas:
 *   1. Si el padre tiene UN solo atleta y no hay id elegido → ese atleta
 *      es el "activo" implícito (no obligamos selección con un solo hijo).
 *   2. Si el id persistido ya no existe en la lista (atleta removido del
 *      padre, fallback de seguridad) → reseteamos a null automáticamente.
 *   3. Retornamos también la lista completa y el setter por conveniencia
 *      para que los componentes que consumen el hook no tengan que hacer
 *      el doble import.
 *
 * Patrón inspirado en useMyAthletes (Wave 2 R2): el hook NO dispara su
 * propia query; reutiliza `useMyAthletes` que ya está cacheada con
 * `userId` en el queryKey.
 */
import { useEffect, useMemo } from "react";

import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useParentContextStore } from "@/store/parentContext.store";
import type { MyAthleteOut } from "@/types/parent.types";

export interface UseActiveAthleteResult {
  /** Atleta efectivo (id seleccionado, o único hijo si solo hay uno). null si multi-hijo sin selección. */
  athlete: MyAthleteOut | null;
  /** Lista completa de atletas vinculados al padre. */
  athletes: MyAthleteOut[];
  /** Loading state de la lista subyacente. */
  isLoading: boolean;
  /** Setter para cambiar de atleta activo (o pasar null para "todos"). */
  setActiveAthlete: (id: number | null) => void;
  /** Id seleccionado (state crudo del store — null si nada seleccionado). */
  activeAthleteId: number | null;
}

export function useActiveAthlete(): UseActiveAthleteResult {
  const { data: athletes, isLoading } = useMyAthletes();
  const activeAthleteId = useParentContextStore((s) => s.activeAthleteId);
  const setActiveAthlete = useParentContextStore((s) => s.setActiveAthlete);

  const list = athletes ?? [];

  // Defensa: si el id persistido en localStorage ya no corresponde a un
  // atleta vinculado (el coach removió la vinculación, o un padre cambió
  // de cuenta en la misma máquina), reseteamos a null. El efecto corre
  // solo cuando cambia la composición de la lista o el id seleccionado.
  useEffect(() => {
    if (
      activeAthleteId !== null &&
      list.length > 0 &&
      !list.some((a) => a.athlete_id === activeAthleteId)
    ) {
      setActiveAthlete(null);
    }
  }, [activeAthleteId, list, setActiveAthlete]);

  // Atleta efectivo: respeta selección explícita; si no hay y el padre
  // tiene un solo hijo, ese hijo es el "implícito". Si multi-hijo y sin
  // selección → null (los consumidores deciden si mostrar todos apilados
  // o pedir selección).
  const athlete = useMemo<MyAthleteOut | null>(() => {
    if (activeAthleteId !== null) {
      return list.find((a) => a.athlete_id === activeAthleteId) ?? null;
    }
    if (list.length === 1) {
      return list[0];
    }
    return null;
  }, [activeAthleteId, list]);

  return {
    athlete,
    athletes: list,
    isLoading,
    setActiveAthlete,
    activeAthleteId,
  };
}
