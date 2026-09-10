/**
 * Tests de CoachActivityPage (feature 041 — gobernanza multi-coach, T084).
 * Contrato: specs/041-multi-coach-governance/contracts/coach-activity-report.md §6.
 *
 * `@/store/auth.store` se mockea con rol `coach` y `club_ids: [1]` (mismo
 * patrón de `ClubHistoryPage.test.tsx`). El resto —informe de actividad y
 * directorio de personal— corre contra MSW real
 * (`coachActivityHandlers`, `staffHandlers`).
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

import { mswServer } from "@/test/setup";
import {
  coachActivityHandlers,
  makeCoachActivityOut,
  makeEmptyCoachActivityOut,
} from "@/test/msw/coachActivityHandlers";
import { UserRole } from "@/types/enums";
import type { UserListOut } from "@/types/user.types";

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

// `/api/users?role=coach` (para `useClubStaff`, el selector "Entrenador")
// y `/api/users?role=coach&role=admin` (para `useStaff`, dentro de
// `ActorChip`) — mismos dos entrenadores del fixture de
// `coachActivityHandlers` (ids 7 y 12), para que elegir uno del selector
// coincida con una fila real del informe.
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
      {
        id: 12,
        email: "bruno.coach@example.org",
        first_name: "Bruno",
        last_name: "Coach",
        phone: null,
        role: UserRole.coach,
        is_active: true,
        can_login: true,
        created_at: "2026-01-01T00:00:00",
        created_by_display_name: null,
      },
    ],
    total: 2,
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

describe("CoachActivityPage", () => {
  it("renderiza una tarjeta por entrenador desde MSW", async () => {
    renderPage();

    const cards = await screen.findAllByTestId("coach-activity-card");
    expect(cards).toHaveLength(2);
    // `within(card)` porque "Ana Coach"/"Bruno Coach" también son las
    // opciones del selector "Entrenador" — sin scoping, getByText fallaría
    // por ambigüedad.
    expect(within(cards[0]).getByText("Ana Coach")).toBeInTheDocument();
    expect(within(cards[1]).getByText("Bruno Coach")).toBeInTheDocument();
  });

  it("muestra los totales del club", async () => {
    renderPage();

    await screen.findAllByTestId("coach-activity-card");
    const totals = screen.getByTestId("coach-activity-club-totals");
    // club_totals.sessions.total = 13 en el fixture por defecto.
    expect(within(totals).getByText("13")).toBeInTheDocument();
  });

  it("los presets de periodo actualizan Desde/Hasta", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findAllByTestId("coach-activity-card");

    const fromInput = screen.getByLabelText("Desde") as HTMLInputElement;
    const initialFrom = fromInput.value;

    await user.click(screen.getByRole("button", { name: "Mes anterior" }));

    await waitFor(() => {
      expect((screen.getByLabelText("Desde") as HTMLInputElement).value).not.toBe(
        initialFrom,
      );
    });
  });

  it("el selector de entrenador recorta a una tarjeta y los totales del club siguen completos", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findAllByTestId("coach-activity-card");

    await user.selectOptions(
      screen.getByLabelText("Entrenador"),
      screen.getByRole("option", { name: "Bruno Coach" }),
    );

    await waitFor(() => {
      expect(screen.getAllByTestId("coach-activity-card")).toHaveLength(1);
    });
    const card = screen.getByTestId("coach-activity-card");
    expect(within(card).getByText("Bruno Coach")).toBeInTheDocument();

    const totals = screen.getByTestId("coach-activity-club-totals");
    expect(within(totals).getByText("13")).toBeInTheDocument();
  });

  it("el enlace de historial apunta a /club/historial con el actor y el periodo del informe", async () => {
    renderPage();
    await screen.findAllByTestId("coach-activity-card");

    const links = screen.getAllByTestId("coach-activity-history-link");
    expect(links[0]).toHaveAttribute(
      "href",
      "/club/historial?actor=7&from=2026-03-01&to=2026-03-31",
    );
  });

  it("muestra el estado vacío cuando el club no tiene entrenadores", async () => {
    mswServer.use(
      http.get("*/api/clubs/:clubId/coach-activity", () =>
        HttpResponse.json(makeEmptyCoachActivityOut()),
      ),
    );

    renderPage();

    expect(
      await screen.findByText("Este club todavía no tiene entrenadores registrados."),
    ).toBeInTheDocument();
  });

  it("muestra la nota de periodo sin actividad cuando audit_entries_count es 0", async () => {
    mswServer.use(
      http.get("*/api/clubs/:clubId/coach-activity", () =>
        HttpResponse.json(
          makeCoachActivityOut({
            club_totals: {
              sessions: { planned: 0, executed: 0, cancelled: 0, total: 0 },
              attendance_entries_recorded: 0,
              ai_runs_launched: 0,
              results_operations: { imports: 0, revisions: 0, competitor_links: 0, total: 0 },
              documents: {
                reports_approved: 0,
                newsletters_approved: 0,
                newsletters_sent: 0,
                exports: 0,
              },
              audit_entries_count: 0,
            },
          }),
        ),
      ),
    );

    renderPage();

    expect(
      await screen.findByText(
        "No hay actividad registrada en el periodo seleccionado. Prueba con otro rango de fechas.",
      ),
    ).toBeInTheDocument();
  });

  it("muestra el estado de error con botón Reintentar", async () => {
    mswServer.use(
      http.get("*/api/clubs/:clubId/coach-activity", () =>
        HttpResponse.json(
          { detail: "No se pudo cargar la actividad por entrenador." },
          { status: 500 },
        ),
      ),
    );

    renderPage();

    expect(
      await screen.findByText("No se pudo cargar la actividad por entrenador."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reintentar/i })).toBeInTheDocument();
  });

  it("no muestra las tarjetas de entrenador mientras carga", () => {
    renderPage();

    expect(screen.queryByTestId("coach-activity-card")).not.toBeInTheDocument();
    expect(
      screen.getByTestId("coach-activity-club-totals"),
    ).toHaveAttribute("aria-busy", "true");
  });
});
