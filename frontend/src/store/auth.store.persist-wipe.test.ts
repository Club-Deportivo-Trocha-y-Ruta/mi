import { beforeEach, describe, expect, it, vi } from "vitest";

// Mock the persister module so we can assert logout() wipes the persisted
// cache without touching real localStorage.
vi.mock("@/lib/queryPersister", () => ({
  wipePersistedCache: vi.fn(),
}));

import { wipePersistedCache } from "@/lib/queryPersister";
import { useAuthStore } from "@/store/auth.store";

describe("auth.store logout — persisted cache wipe (feature 012)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("wipes the persisted device cache on logout", () => {
    useAuthStore.getState().logout();
    expect(wipePersistedCache).toHaveBeenCalledTimes(1);
  });

  it("leaves the user logged out after logout", () => {
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().user).toBeNull();
  });
});
