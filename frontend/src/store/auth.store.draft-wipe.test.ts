import { beforeEach, describe, expect, it, vi } from "vitest";

// Feature 046 (privacy-audit F8 recheck): logout() must remove every
// capture draft (e.g. skinfold readings) left on a shared tablet, for any
// user and any target, while leaving unrelated localStorage keys alone.
// Synthetic ids only — drafts never carry names.
vi.mock("@/lib/queryPersister", () => ({
  wipePersistedCache: vi.fn(),
}));

import { useAuthStore } from "@/store/auth.store";

describe("auth.store logout — capture draft wipe (feature 046 F8)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("removes skinfold and session drafts of every user on logout", () => {
    const draft = JSON.stringify({
      version: "v1",
      values: { sites: {} },
      step: 1,
      updatedAt: new Date().toISOString(),
    });
    window.localStorage.setItem("tyr:session-draft:v1:7:skinfolds:101", draft);
    window.localStorage.setItem("tyr:session-draft:v1:8:skinfolds:102", draft);
    window.localStorage.setItem("tyr:session-draft:v1:7:new", draft);
    window.localStorage.setItem("unrelated-key", "keep");

    useAuthStore.getState().logout();

    const remaining = Object.keys(window.localStorage).filter((key) =>
      key.startsWith("tyr:session-draft:"),
    );
    expect(remaining).toEqual([]);
    expect(window.localStorage.getItem("unrelated-key")).toBe("keep");
  });
});
