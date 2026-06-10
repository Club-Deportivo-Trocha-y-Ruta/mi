import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildBuster,
  createQueryPersister,
  wipePersistedCache,
  PERSIST_CACHE_KEY,
  PERSIST_MAX_AGE,
} from "@/lib/queryPersister";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("queryPersister — buildBuster", () => {
  it("composes '{appVersion}:{userId}'", () => {
    expect(buildBuster(42, "abc123")).toBe("abc123:42");
  });

  it("uses 'anon' when userId is null/undefined", () => {
    expect(buildBuster(null, "abc123")).toBe("abc123:anon");
    expect(buildBuster(undefined, "abc123")).toBe("abc123:anon");
  });

  it("scopes per user — different users yield different busters", () => {
    expect(buildBuster(1, "v")).not.toBe(buildBuster(2, "v"));
  });

  it("invalidates per version — different versions yield different busters", () => {
    expect(buildBuster(1, "v1")).not.toBe(buildBuster(1, "v2"));
  });
});

describe("queryPersister — constants", () => {
  it("uses the namespaced v1 cache key", () => {
    expect(PERSIST_CACHE_KEY).toBe("tyr:rq-cache:v1");
  });

  it("expires after 24 h", () => {
    expect(PERSIST_MAX_AGE).toBe(24 * 60 * 60 * 1000);
  });
});

describe("queryPersister — wipePersistedCache", () => {
  it("removes the persisted cache key from localStorage", () => {
    window.localStorage.setItem(PERSIST_CACHE_KEY, JSON.stringify({ a: 1 }));
    expect(window.localStorage.getItem(PERSIST_CACHE_KEY)).not.toBeNull();
    wipePersistedCache();
    expect(window.localStorage.getItem(PERSIST_CACHE_KEY)).toBeNull();
  });

  it("does not throw when storage access fails", () => {
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(() => wipePersistedCache()).not.toThrow();
  });
});

describe("queryPersister — createQueryPersister (graceful degradation)", () => {
  it("returns a persister when localStorage works", () => {
    expect(createQueryPersister()).not.toBeNull();
  });

  it("returns null when localStorage.setItem throws (private mode/quota)", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    expect(createQueryPersister()).toBeNull();
  });
});
