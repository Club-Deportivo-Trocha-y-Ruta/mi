import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { todayISODate } from "@/lib/datetime";
import type { SessionStatus } from "@/types/trainingSession.types";

function currentMonthRange(): { from_date: string; to_date: string } {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const from = new Date(year, month, 1);
  const to = new Date(year, month + 1, 0);
  return {
    from_date: from.toISOString().slice(0, 10),
    to_date: to.toISOString().slice(0, 10),
  };
}

interface TrainingFiltersState {
  from_date: string;
  to_date: string;
  status: SessionStatus | "";
  setFromDate: (from_date: string) => void;
  setToDate: (to_date: string) => void;
  setStatus: (status: SessionStatus | "") => void;
  resetToCurrentMonth: () => void;
  setToday: () => void;
}

const defaults = currentMonthRange();

export const useTrainingFiltersStore = create<TrainingFiltersState>()(
  persist(
    (set) => ({
      from_date: defaults.from_date,
      to_date: defaults.to_date,
      status: "",
      setFromDate: (from_date) => set({ from_date }),
      setToDate: (to_date) => set({ to_date }),
      setStatus: (status) => set({ status }),
      resetToCurrentMonth: () => set({ ...currentMonthRange(), status: "" }),
      // Feature 032, US3: atajo "Hoy" — reusa el shape from_date/to_date/status
      // persistido existente, sin campos nuevos.
      setToday: () => {
        const today = todayISODate();
        set({ from_date: today, to_date: today });
      },
    }),
    {
      name: "training-filters",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
