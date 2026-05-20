/**
 * Store global del toggle "Modo aprendizaje" (race-analysis v2 §10.2).
 *
 * Estado simple persistido en localStorage bajo la key
 * `race-explain-mode`. Cuando está activo, el agente narra cada paso
 * del grafo y pausa en gates HITL siempre (no sólo en los críticos).
 *
 * Se mantiene como zustand store en vez de useState para que toda la
 * SPA pueda reaccionar al cambio sin prop drilling.
 */
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

interface ExplainModeState {
  enabled: boolean;
  toggle: () => void;
  setEnabled: (enabled: boolean) => void;
}

export const useExplainModeStore = create<ExplainModeState>()(
  persist(
    (set) => ({
      enabled: false,
      toggle: () => set((state) => ({ enabled: !state.enabled })),
      setEnabled: (enabled) => set({ enabled }),
    }),
    {
      name: "race-explain-mode",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
