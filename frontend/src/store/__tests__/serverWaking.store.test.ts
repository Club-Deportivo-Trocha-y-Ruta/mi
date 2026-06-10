import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  useServerWakingStore,
  SERVER_WAKING_THRESHOLD_MS,
} from "@/store/serverWaking.store";

function state() {
  return useServerWakingStore.getState();
}

describe("serverWaking.store", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    state().resetForTests();
  });

  afterEach(() => {
    state().resetForTests();
    vi.useRealTimers();
  });

  it("starts idle", () => {
    expect(state().pendingCount).toBe(0);
    expect(state().isWaking).toBe(false);
    expect(state().oldestPendingSince).toBeNull();
  });

  it("flips isWaking only after the threshold while a request is pending", () => {
    state().requestStarted();
    expect(state().pendingCount).toBe(1);
    expect(state().isWaking).toBe(false);

    vi.advanceTimersByTime(SERVER_WAKING_THRESHOLD_MS - 1);
    expect(state().isWaking).toBe(false);

    vi.advanceTimersByTime(1);
    expect(state().isWaking).toBe(true);
  });

  it("does NOT flip isWaking if the request settles before the threshold", () => {
    state().requestStarted();
    vi.advanceTimersByTime(SERVER_WAKING_THRESHOLD_MS - 100);
    state().requestSettled();
    vi.advanceTimersByTime(500);
    expect(state().isWaking).toBe(false);
    expect(state().pendingCount).toBe(0);
  });

  it("clears isWaking automatically once all requests settle", () => {
    state().requestStarted();
    vi.advanceTimersByTime(SERVER_WAKING_THRESHOLD_MS);
    expect(state().isWaking).toBe(true);

    state().requestSettled();
    expect(state().isWaking).toBe(false);
    expect(state().oldestPendingSince).toBeNull();
  });

  it("stays waking until the LAST of several overlapping requests settles", () => {
    state().requestStarted();
    state().requestStarted();
    expect(state().pendingCount).toBe(2);

    vi.advanceTimersByTime(SERVER_WAKING_THRESHOLD_MS);
    expect(state().isWaking).toBe(true);

    state().requestSettled();
    expect(state().pendingCount).toBe(1);
    expect(state().isWaking).toBe(true);

    state().requestSettled();
    expect(state().pendingCount).toBe(0);
    expect(state().isWaking).toBe(false);
  });

  it("never drops below zero pending on an extra settle", () => {
    state().requestSettled();
    expect(state().pendingCount).toBe(0);
    expect(state().isWaking).toBe(false);
  });
});
