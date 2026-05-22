/**
 * parentContext.store — Estado client-side del padre activo en la SPA.
 *
 * Wave 4: cuando un padre tiene varios atletas, queremos que la "home"
 * (feed de últimas/próximas sesiones, alertas, resumen semanal) y otras
 * vistas portal puedan filtrar por un atleta concreto sin re-pedir al
 * usuario seleccionar en cada página. Persistimos el id en localStorage
 * bajo la key `parent-context` para que la elección sobreviva a recargas.
 *
 * Privacy R4 (Wave 4): cuando el padre cambia de hijo, también purgamos
 * del cache de TanStack Query las queries asociadas al hijo previo. Sin
 * esto, datos del hijo A podrían quedar visibles por un frame al pintar
 * la home con foco en hijo B (mismo padre, pero misma tablet/sesión, así
 * que la regla R1 de logout no aplica — necesitamos limpieza específica
 * por atleta). Ver `purgeQueriesForAthlete` en `lib/queryClientHandle.ts`.
 */
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { purgeQueriesForAthlete } from "@/lib/queryClientHandle";

interface ParentContextState {
  activeAthleteId: number | null;
  setActiveAthlete: (id: number | null) => void;
  /** Reset interno — útil para tests que comparten el store singleton. */
  reset: () => void;
}

export const useParentContextStore = create<ParentContextState>()(
  persist(
    (set, get) => ({
      activeAthleteId: null,

      setActiveAthlete: (id) => {
        const prevId = get().activeAthleteId;
        // Si cambiamos a otro hijo (o a "todos"), purga del cache las queries
        // del hijo previo. No-op si prevId === null o si prevId === id.
        if (prevId !== null && prevId !== id) {
          purgeQueriesForAthlete(prevId);
        }
        set({ activeAthleteId: id });
      },

      reset: () => set({ activeAthleteId: null }),
    }),
    {
      name: "parent-context",
      storage: createJSONStorage(() => localStorage),
      // Solo persistimos el id — todo lo demás (acciones, derivados) se
      // reconstruye al hidratar.
      partialize: (state) => ({ activeAthleteId: state.activeAthleteId }),
      // Hidratación client-only: en SSR no leemos del storage (no aplica
      // hoy — la SPA es CSR puro — pero queda como defensa).
      skipHydration: typeof window === "undefined",
    },
  ),
);
