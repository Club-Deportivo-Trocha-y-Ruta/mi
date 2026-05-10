import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { EventType } from "@/types/calendar.types";

function currentMonthRange(): { from: string; to: string } {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const from = new Date(year, month, 1);
  const to = new Date(year, month + 1, 0);
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  };
}

interface CalendarFiltersState {
  from: string;
  to: string;
  eventTypes: EventType[];
  athleteId: number | null;
  category: string | null;
  setFrom: (from: string) => void;
  setTo: (to: string) => void;
  setEventTypes: (types: EventType[]) => void;
  setAthleteId: (id: number | null) => void;
  setCategory: (category: string | null) => void;
  reset: () => void;
}

const defaults = currentMonthRange();

export const useCalendarFiltersStore = create<CalendarFiltersState>()(
  persist(
    (set) => ({
      from: defaults.from,
      to: defaults.to,
      eventTypes: [],
      athleteId: null,
      category: null,
      setFrom: (from) => set({ from }),
      setTo: (to) => set({ to }),
      setEventTypes: (eventTypes) => set({ eventTypes }),
      setAthleteId: (athleteId) => set({ athleteId }),
      setCategory: (category) => set({ category }),
      reset: () =>
        set({
          ...currentMonthRange(),
          eventTypes: [],
          athleteId: null,
          category: null,
        }),
    }),
    {
      name: "calendar-filters",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
