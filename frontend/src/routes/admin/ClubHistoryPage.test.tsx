/**
 * Tests de ClubHistoryPage (feature 041 — gobernanza multi-coach, T037).
 * Contrato: specs/041-multi-coach-governance/contracts/coach-activity-report.md §8.2.
 *
 * `@/hooks/athletes/useAthletes` se mockea (patrón de `ActivityReviewPage.test.tsx`)
 * porque el combobox de atleta es incidental a este módulo. `@/store/auth.store`
 * se mockea con rol `coach` y `club_ids: [1]`. El resto —lista de personal y
 * lista de auditoría— corre contra MSW real (`auditHandlers`).
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { axe, toHaveNoViolations } from "jest-axe";

import { mswServer } from "@/test/setup";
import {
  auditHandlers,
  clubAuditLogErrorHandler,
  makeAuditEntry,
  makeAuditListOut,
} from "@/test/msw/auditHandlers";
import type { AthleteListOut } from "@/types/athlete.types";
import { UserRole } from "@/types/enums";

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

const mockAthletesData: AthleteListOut = {
  total: 1,
  items: [
    {
      id: 42,
      user_id: 142,
      first_name: "Sebastián",
      last_name: "García Ficticio",
      birth_date: "2013-03-01",
      sex: "M",
      club_join_date: "2024-01-01",
      years_in_club: 2,
      age_decimal: 13.4,
      category: "sub-15",
      club_id: 1,
      created_at: "2024-01-01T00:00:00Z",
    },
  ],
} as unknown as AthleteListOut;

vi.mock("@/hooks/athletes/useAthletes", () => ({
  useAthletes: vi.fn(() => ({ data: mockAthletesData, isLoading: false })),
}));

import { ClubHistoryPage } from "./ClubHistoryPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/club/historial"]}>
      <QueryClientProvider client={qc}>
        <ClubHistoryPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mswServer.use(...auditHandlers);
});

describe("ClubHistoryPage", () => {
  it("renderiza el título y la lista de registros", async () => {
    renderPage();

    expect(screen.getByText("Historial del club")).toBeInTheDocument();
    expect(await screen.findAllByTestId("club-history-row")).toHaveLength(1);
    expect(
      screen.getByText("Ana Coach actualizó la sesión de entrenamiento."),
    ).toBeInTheDocument();
  });

  it("muestra el estado vacío cuando no hay registros", async () => {
    mswServer.use(
      http.get("*/api/clubs/:clubId/audit-log", () =>
        HttpResponse.json(makeAuditListOut({ items: [], total: 0 })),
      ),
    );

    renderPage();

    expect(
      await screen.findByText("No hay registros para los filtros seleccionados."),
    ).toBeInTheDocument();
  });

  it("muestra el estado de error con botón Reintentar", async () => {
    mswServer.use(clubAuditLogErrorHandler);

    renderPage();

    expect(
      await screen.findByText("No se pudo cargar el historial del club."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reintentar/i })).toBeInTheDocument();
  });

  it("envía el actor_user_id elegido en el filtro de entrenador", async () => {
    const observedActorIds: string[] = [];
    mswServer.use(
      http.get("*/api/users", () =>
        HttpResponse.json({
          items: [
            {
              id: 7,
              email: "ana@example.com",
              first_name: "Ana",
              last_name: "Coach",
              phone: null,
              role: "coach",
              is_active: true,
              can_login: true,
              created_at: "2024-01-01T00:00:00Z",
            },
          ],
          total: 1,
        }),
      ),
      http.get("*/api/clubs/:clubId/audit-log", ({ request }) => {
        observedActorIds.push(
          new URL(request.url).searchParams.get("actor_user_id") ?? "",
        );
        return HttpResponse.json(makeAuditListOut());
      }),
    );

    const user = userEvent.setup();
    renderPage();

    await screen.findAllByTestId("club-history-row");

    await waitFor(() => {
      expect(screen.getByLabelText("Entrenador")).toBeInTheDocument();
    });
    await user.selectOptions(screen.getByLabelText("Entrenador"), "7");

    await waitFor(() => expect(observedActorIds).toContain("7"));
  });

  it("pagina con Anterior/Siguiente usando offset del servidor", async () => {
    const observedOffsets: string[] = [];
    mswServer.use(
      http.get("*/api/clubs/:clubId/audit-log", ({ request }) => {
        const offset = new URL(request.url).searchParams.get("offset") ?? "0";
        observedOffsets.push(offset);
        return HttpResponse.json(
          makeAuditListOut({
            items: [makeAuditEntry({ id: Number(offset) + 1 })],
            total: 40,
            offset: Number(offset),
          }),
        );
      }),
    );

    const user = userEvent.setup();
    renderPage();

    await screen.findAllByTestId("club-history-row");

    const nextButton = screen.getByRole("button", { name: "Siguiente" });
    await user.click(nextButton);

    await waitFor(() => expect(observedOffsets).toContain("20"));
  });

  it("no tiene violaciones de accesibilidad (axe)", async () => {
    const { container } = renderPage();
    await screen.findAllByTestId("club-history-row");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
