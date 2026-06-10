import { beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// Keep the real apiClient/registerAuthHandlers (auth.store depends on them);
// only replace warmUp so we can assert LoginPage fires it on mount.
vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return { ...actual, warmUp: vi.fn() };
});

import { warmUp } from "@/api/client";
import { LoginPage } from "@/routes/auth/LoginPage";

describe("LoginPage — backend warm-up on mount (feature 012, US2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fires the backend warm-up ping on mount", () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    expect(warmUp).toHaveBeenCalledTimes(1);
  });
});
