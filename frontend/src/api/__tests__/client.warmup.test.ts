import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { warmUp, __resetWarmUpForTests } from "@/api/client";

describe("warmUp — backend cold-start ping (feature 012, US2)", () => {
  beforeEach(() => {
    __resetWarmUpForTests();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    __resetWarmUpForTests();
  });

  it("fires a single GET /health on first call, with no Authorization header", () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 200 }));

    warmUp();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toMatch(/\/health$/);
    expect(init?.method).toBe("GET");
    const headers = (init?.headers ?? {}) as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });

  it("is deduplicated — only fires once per app load", () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 200 }));

    warmUp();
    warmUp();
    warmUp();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("swallows errors — a rejected ping never throws", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(
      new Error("backend asleep"),
    );

    expect(() => warmUp()).not.toThrow();
    // Flush the rejected microtask so it cannot surface as unhandled.
    await Promise.resolve();
  });
});
