import { create } from "zustand";

/**
 * Jornada de medición grupal (feature 048, US3, T044).
 *
 * Estado SOLO en memoria: sin `persist`, a propósito (clarificación 1 —
 * recargar la página pierde la jornada). No guarda nombres ni valores de
 * medición, solo ids numéricos, estados y si el registro quedó con avisos;
 * aun así nada de esto toca `localStorage`/`sessionStorage` (Ley 1581).
 * `auth.store.logout()` llama a `reset()` para que una tablet compartida no
 * herede la jornada de la cuenta anterior.
 */

export type SessionAthleteStatus = "pending" | "measured" | "skipped";

interface MeasurementSessionData {
  /** Fecha de la jornada (YYYY-MM-DD); `null` = no hay jornada activa. */
  date: string | null;
  /** Orden de la cola. */
  athleteIds: number[];
  statusById: Record<number, SessionAthleteStatus>;
  recordIdById: Record<number, number>;
  /** `true` si la medición guardada quedó con avisos de plausibilidad. */
  warningsById: Record<number, boolean>;
  /** Deportista en captura; `null` cuando no queda ninguno pendiente. */
  currentId: number | null;
}

interface MeasurementSessionActions {
  start: (date: string, ids: number[]) => void;
  markMeasured: (id: number, recordId: number, hasWarnings: boolean) => void;
  skip: (id: number) => void;
  /** Devuelve un omitido a pendiente y lo pone en captura. */
  reopen: (id: number) => void;
  /** Salta a un pendiente u omitido (un omitido vuelve a pendiente). */
  goTo: (id: number) => void;
  /** Avanza al siguiente pendiente (en orden circular) o a `null`. */
  next: () => void;
  reset: () => void;
}

export type MeasurementSessionState = MeasurementSessionData & MeasurementSessionActions;

const INITIAL: MeasurementSessionData = {
  date: null,
  athleteIds: [],
  statusById: {},
  recordIdById: {},
  warningsById: {},
  currentId: null,
};

/** Siguiente pendiente después de `fromId` (circular), o `null`. */
export function nextPendingId(
  athleteIds: readonly number[],
  statusById: Record<number, SessionAthleteStatus>,
  fromId: number | null,
): number | null {
  if (athleteIds.length === 0) return null;
  const start = fromId === null ? -1 : athleteIds.indexOf(fromId);
  for (let step = 1; step <= athleteIds.length; step += 1) {
    const id = athleteIds[(start + step + athleteIds.length) % athleteIds.length];
    if (statusById[id] === "pending") return id;
  }
  return null;
}

export const useMeasurementSessionStore = create<MeasurementSessionState>()((set, get) => ({
  ...INITIAL,

  start: (date, ids) => {
    const athleteIds = Array.from(new Set(ids));
    const statusById: Record<number, SessionAthleteStatus> = {};
    for (const id of athleteIds) statusById[id] = "pending";
    set({
      ...INITIAL,
      date,
      athleteIds,
      statusById,
      currentId: athleteIds[0] ?? null,
    });
  },

  markMeasured: (id, recordId, hasWarnings) => {
    const state = get();
    if (!(id in state.statusById)) return;
    const statusById = { ...state.statusById, [id]: "measured" as const };
    set({
      statusById,
      recordIdById: { ...state.recordIdById, [id]: recordId },
      warningsById: { ...state.warningsById, [id]: hasWarnings },
      currentId:
        state.currentId === id || state.currentId === null
          ? nextPendingId(state.athleteIds, statusById, id)
          : state.currentId,
    });
  },

  skip: (id) => {
    const state = get();
    if (state.statusById[id] !== "pending") return;
    const statusById = { ...state.statusById, [id]: "skipped" as const };
    set({
      statusById,
      currentId:
        state.currentId === id || state.currentId === null
          ? nextPendingId(state.athleteIds, statusById, id)
          : state.currentId,
    });
  },

  reopen: (id) => {
    const state = get();
    if (state.statusById[id] !== "skipped") return;
    set({ statusById: { ...state.statusById, [id]: "pending" }, currentId: id });
  },

  goTo: (id) => {
    const state = get();
    const status = state.statusById[id];
    if (status === "pending") {
      set({ currentId: id });
    } else if (status === "skipped") {
      state.reopen(id);
    }
  },

  next: () => {
    const state = get();
    set({ currentId: nextPendingId(state.athleteIds, state.statusById, state.currentId) });
  },

  reset: () => set({ ...INITIAL }),
}));
