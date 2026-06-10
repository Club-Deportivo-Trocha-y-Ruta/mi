/**
 * serverWaking.store — tracks in-flight HTTP requests to surface an explicit
 * "el servidor está despertando…" state during a Render Free cold start
 * (~50 s after ~15 min idle). Feature 012, US2.
 *
 * Fed by the axios interceptors in `@/api/client`: every request calls
 * `requestStarted()`/`requestSettled()`. When the oldest in-flight request
 * exceeds the threshold, `isWaking` flips true; it clears automatically once
 * all requests settle. Centralising at the HTTP layer means the guarantee
 * holds for ANY request (queries, mutations, login) without per-hook wiring.
 */
import { create } from "zustand";

/** Delay before showing the waking state (ms). Single source of truth. */
export const SERVER_WAKING_THRESHOLD_MS = 3000;

interface ServerWakingState {
  /** Number of HTTP requests currently in flight. */
  pendingCount: number;
  /** Epoch ms when the oldest in-flight request started (null when idle). */
  oldestPendingSince: number | null;
  /** True once a request has been pending longer than the threshold. */
  isWaking: boolean;
  /** Register that an HTTP request has started. */
  requestStarted: () => void;
  /** Register that an HTTP request has settled (success or error). */
  requestSettled: () => void;
  /** Test-only: reset state and cancel any pending timer. */
  resetForTests: () => void;
}

// Module-level timer so the threshold logic lives in one place (testable with
// fake timers) rather than scattered across components.
let wakeTimer: ReturnType<typeof setTimeout> | null = null;

function clearWakeTimer(): void {
  if (wakeTimer !== null) {
    clearTimeout(wakeTimer);
    wakeTimer = null;
  }
}

export const useServerWakingStore = create<ServerWakingState>((set, get) => ({
  pendingCount: 0,
  oldestPendingSince: null,
  isWaking: false,

  requestStarted: () => {
    const wasIdle = get().pendingCount === 0;
    set((s) => ({ pendingCount: s.pendingCount + 1 }));
    if (wasIdle) {
      set({ oldestPendingSince: Date.now() });
      clearWakeTimer();
      wakeTimer = setTimeout(() => {
        wakeTimer = null;
        // Solo mostramos el aviso si TODAVÍA hay una petición en vuelo.
        if (get().pendingCount > 0) {
          set({ isWaking: true });
        }
      }, SERVER_WAKING_THRESHOLD_MS);
    }
  },

  requestSettled: () => {
    const next = Math.max(0, get().pendingCount - 1);
    if (next === 0) {
      clearWakeTimer();
      set({ pendingCount: 0, oldestPendingSince: null, isWaking: false });
    } else {
      set({ pendingCount: next });
    }
  },

  resetForTests: () => {
    clearWakeTimer();
    set({ pendingCount: 0, oldestPendingSince: null, isWaking: false });
  },
}));
