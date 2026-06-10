/**
 * queryPersister — device-storage persister for the TanStack Query cache
 * (feature 012, US1).
 *
 * Persists an allow-listed slice of the query cache to `localStorage` so return
 * visits render instantly while the Render Free backend wakes (~50 s cold
 * start). Degrades gracefully to in-memory-only behaviour when storage is
 * unavailable (private mode, quota, SSR): all helpers no-op / return null
 * instead of throwing.
 *
 * Privacy: WHAT gets persisted is governed by `persistAllowList.ts`. This module
 * only handles WHERE (key, medium) and the lifecycle controls (buster, wipe).
 */
import { createAsyncStoragePersister } from "@tanstack/query-async-storage-persister";

/** Persister instance type, derived from the factory's return type. */
type QueryPersister = ReturnType<typeof createAsyncStoragePersister>;

/** Single localStorage key holding the dehydrated cache envelope. */
export const PERSIST_CACHE_KEY = "tyr:rq-cache:v1";

/** Max age of a restored snapshot before it is silently discarded (24 h). */
export const PERSIST_MAX_AGE = 24 * 60 * 60 * 1000;

/**
 * Build-time app version injected by Vite `define`. Changes per deploy so a new
 * release invalidates older persisted snapshots. Falls back to "dev" if the
 * define is somehow absent (e.g. an unusual test transform).
 */
const APP_VERSION: string =
  typeof __APP_VERSION__ !== "undefined" ? __APP_VERSION__ : "dev";

/**
 * Compose the cache-buster string `"{appVersion}:{userId}"`. A mismatch makes
 * the persister discard the snapshot on restore, which simultaneously enforces
 * account scoping (different user ⇒ different buster) and version invalidation
 * (new deploy ⇒ different version). `userId` null/undefined ⇒ "anon".
 */
export function buildBuster(
  userId: number | string | null | undefined,
  appVersion: string = APP_VERSION,
): string {
  return `${appVersion}:${userId ?? "anon"}`;
}

/**
 * Return `window.localStorage` only if it is actually usable. Probes with a
 * write because private/locked-down modes expose the object but throw on use.
 */
function getSafeLocalStorage(): Storage | undefined {
  try {
    if (typeof window === "undefined" || !window.localStorage) return undefined;
    const probe = "__tyr_probe__";
    window.localStorage.setItem(probe, "1");
    window.localStorage.removeItem(probe);
    return window.localStorage;
  } catch {
    return undefined;
  }
}

/**
 * Create the async-storage persister, or `null` when storage is unavailable so
 * the caller can fall back to a plain (in-memory) provider (FR-007).
 */
export function createQueryPersister(): QueryPersister | null {
  const storage = getSafeLocalStorage();
  if (!storage) return null;
  return createAsyncStoragePersister({
    storage,
    key: PERSIST_CACHE_KEY,
    throttleTime: 1000,
  });
}

/**
 * Remove the persisted cache from device storage. Called on logout (alongside
 * the in-memory `queryClient.clear()`) so account data never persists at rest
 * on a shared device. Safe to call when storage is unavailable.
 */
export function wipePersistedCache(): void {
  try {
    if (typeof window === "undefined" || !window.localStorage) return;
    window.localStorage.removeItem(PERSIST_CACHE_KEY);
  } catch {
    // Storage unavailable — nothing to wipe.
  }
}
