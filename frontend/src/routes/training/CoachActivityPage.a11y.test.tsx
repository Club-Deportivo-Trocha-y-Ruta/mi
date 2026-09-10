/**
 * Tests de accesibilidad de CoachActivityPage (feature 041 — gobernanza
 * multi-coach, T084). Contrato:
 * specs/041-multi-coach-governance/contracts/coach-activity-report.md §6.5.
 *
 * jest-axe cero violaciones, cargado y vacío.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";
import { http, HttpResponse } from "msw";

import { mswServer } from "@/test/setup";
import {
  coachActivityHandlers,
  makeEmptyCoachActivityOut,
} from "@/test/msw/coachActivityHandlers";
import { UserRole } from "@/types/enums";
import type { UserListOut } from "@/types/user.types";

expect.extend(toHaveNoViolations);

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (s: {
      accessToken: string;
      user: { id: number; role: UserRole; club_ids: number[] };
    }) => unknown,
  ) =>
    selector({
      accessToken: "test-token",
      user: { id: 1, role: UserRole.coach, club_ids: [1] },
    }),
}));

import { CoachActivityPage } from "./CoachActivityPage";

const listCoachUsersHandler = http.get("*/api/users", () => {
  const body: UserListOut = {
    items: [
      {
        id: 7,
        email: "ana.coach@example.org",
        first_name: "Ana",
        last_name: "Coach",
        phone: null,
        role: UserRole.coach,
        is_active: true,
        can_login: true,
        created_at: "2026-01-01T00:00:00",
        created_by_display_name: null,
      },
    ],
    total: 1,
  };
  return HttpResponse.json(body);
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/training/reports/actividad-entrenadores"]}>
      <QueryClientProvider client={qc}>
        <CoachActivityPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mswServer.use(...coachActivityHandlers, listCoachUsersHandler);
});

describe("CoachActivityPage — accesibilidad", () => {
  it("no tiene violaciones con datos cargados", async () => {
    const { container } = renderPage();
    await screen.findAllByTestId("coach-activity-card");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones con el club sin entrenadores (estado vacío)", async () => {
    mswServer.use(
      http.get("*/api/clubs/:clubId/coach-activity", () =>
        HttpResponse.json(makeEmptyCoachActivityOut()),
      ),
    );

    const { container } = renderPage();
    await screen.findByText("Este club todavía no tiene entrenadores registrados.");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
