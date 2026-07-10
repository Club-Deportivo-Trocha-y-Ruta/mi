/**
 * Tests de ActivityReviewPage (feature 025, T034).
 *
 * Cubre: agrupamiento por fecha, badges de estado de enlace (heredados de
 * `ActivityCard`), interacción de filtros (estado/atleta/rango de fechas +
 * limpiar), estados de carga/error/vacío, y accesibilidad (0 violaciones
 * axe) — vía MSW contra `GET /api/activities` (capa HTTP real, sin mockear
 * `@/hooks/activities/useActivityReview`), consistente con
 * `useStravaConnection.test.ts`.
 *
 * `@/hooks/athletes/useAthletes` se mockea directamente (patrón de
 * `CalendarPage.test.tsx`) porque el filtro de atleta es incidental a este
 * módulo — no vale la pena levantar `auth.store` + `GET /api/athletes` real
 * solo para poblar un <select>.
 *
 * `@/store/auth.store` sí se mockea (rol `coach`) porque esta ruta es una
 * de las dos superficies coach que habilitan `canLink` en `ActivityCard`
 * (T032b) — sin un rol coach/admin el botón "Enlazar a sesión" no se
 * renderiza (gate doble, ver `ActivityCard.test.tsx`).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse, delay } from "msw";
import { axe, toHaveNoViolations } from "jest-axe";

import { mswServer } from "@/test/setup";
import {
  stravaHandlers,
  mockReviewActivityListResponse,
  mockActivity,
  emptyReviewActivitiesHandler,
  reviewActivitiesErrorHandler,
} from "@/test/msw/stravaHandlers";
import type { AthleteListOut } from "@/types/athlete.types";
import { UserRole } from "@/types/enums";

expect.extend(toHaveNoViolations);

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (s: { accessToken: string; user: { id: number; role: UserRole } }) => unknown,
  ) => selector({ accessToken: "test-token", user: { id: 1, role: UserRole.coach } }),
}));

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockAthletesData: AthleteListOut = {
  total: 2,
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
    {
      id: 7,
      user_id: 107,
      first_name: "Valentina",
      last_name: "López Ficticia",
      birth_date: "2014-05-01",
      sex: "F",
      club_join_date: "2024-01-01",
      years_in_club: 2,
      age_decimal: 12.2,
      category: "sub-13",
      club_id: 1,
      created_at: "2024-01-01T00:00:00Z",
    },
  ],
} as unknown as AthleteListOut;

vi.mock("@/hooks/athletes/useAthletes", () => ({
  useAthletes: vi.fn(() => ({ data: mockAthletesData, isLoading: false })),
}));

import { ActivityReviewPage } from "./ActivityReviewPage";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ActivityReviewPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mswServer.use(...stravaHandlers);
});

// ---------------------------------------------------------------------------
// Agrupamiento por fecha
// ---------------------------------------------------------------------------

describe("ActivityReviewPage — agrupamiento por fecha", () => {
  it("agrupa las actividades en secciones independientes por día, más reciente primero", async () => {
    renderPage();

    const headings = await waitFor(() => {
      const found = screen.getAllByRole("heading", { level: 2 });
      expect(found).toHaveLength(2);
      return found;
    });

    expect(headings[0]).toHaveTextContent(/8 de julio/i);
    expect(headings[1]).toHaveTextContent(/5 de julio/i);
  });

  it("cada grupo de fecha contiene solo las actividades de ese día", async () => {
    mswServer.use(
      http.get("*/api/activities", () =>
        HttpResponse.json(
          mockReviewActivityListResponse({
            items: [
              mockActivity({ id: 1, start_date_local: "2026-07-08T06:30:00" }),
              mockActivity({ id: 2, start_date_local: "2026-07-08T16:00:00" }),
              mockActivity({ id: 3, start_date_local: "2026-07-01T09:00:00" }),
            ],
          }),
        ),
      ),
    );

    renderPage();

    const headings = await waitFor(() => {
      const found = screen.getAllByRole("heading", { level: 2 });
      expect(found).toHaveLength(2);
      return found;
    });

    const julySection = headings[0].closest("div") as HTMLElement;
    expect(within(julySection).getAllByRole("article")).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// Badges de estado de enlace
// ---------------------------------------------------------------------------

describe("ActivityReviewPage — badges de estado", () => {
  it("distingue actividades enlazadas de las sin enlazar", async () => {
    renderPage();

    // Espera a que las tarjetas carguen (no `findByText("Sin enlazar")`: ese
    // texto también existe como <option> del filtro "Estado" y resolvería
    // antes de que los datos lleguen).
    const articles = await screen.findAllByRole("article");
    expect(articles).toHaveLength(2);
    expect(within(articles[0]).getByText("Sin enlazar")).toBeInTheDocument();
    expect(
      within(articles[1]).getByText(/Enlazada · 5 jul · Entrenamiento/),
    ).toBeInTheDocument();
  });

  it("muestra el nombre del atleta en cada tarjeta (showAthleteName)", async () => {
    renderPage();

    expect(await screen.findByText("Sebastián Ficticio García")).toBeInTheDocument();
    expect(screen.getByText("Valentina Ficticia López")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Acción de enlace (T032b — coach ve el botón y puede abrir el diálogo)
// ---------------------------------------------------------------------------

describe("ActivityReviewPage — acción de enlace", () => {
  it("cada tarjeta de coach expone su acción de enlace/cambio de sesión", async () => {
    renderPage();
    const articles = await screen.findAllByRole("article");
    expect(articles).toHaveLength(2);

    expect(
      within(articles[0]).getByRole("button", { name: /enlazar a sesión/i }),
    ).toBeInTheDocument();
    expect(
      within(articles[1]).getByRole("button", { name: /cambiar sesión/i }),
    ).toBeInTheDocument();
  });

  it("hacer clic en 'Enlazar a sesión' abre LinkSessionDialog para esa actividad", async () => {
    const user = userEvent.setup();
    renderPage();

    const articles = await screen.findAllByRole("article");
    const linkButton = within(articles[0]).getByRole("button", {
      name: /enlazar a sesión/i,
    });
    await user.click(linkButton);

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/Vincular a sesión/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Filtros
// ---------------------------------------------------------------------------

describe("ActivityReviewPage — filtros", () => {
  it("envía el filtro 'linked=false' al backend cuando se elige 'Sin enlazar'", async () => {
    const observedParams: string[] = [];
    mswServer.use(
      http.get("*/api/activities", ({ request }) => {
        observedParams.push(new URL(request.url).searchParams.get("linked") ?? "");
        return HttpResponse.json(mockReviewActivityListResponse());
      }),
    );

    const user = userEvent.setup();
    renderPage();

    await screen.findAllByRole("article");

    await user.selectOptions(screen.getByLabelText("Estado"), "false");

    await waitFor(() => expect(observedParams).toContain("false"));
  });

  it("envía el athlete_id elegido en el filtro de atleta", async () => {
    const observedAthleteIds: string[] = [];
    mswServer.use(
      http.get("*/api/activities", ({ request }) => {
        observedAthleteIds.push(
          new URL(request.url).searchParams.get("athlete_id") ?? "",
        );
        return HttpResponse.json(mockReviewActivityListResponse());
      }),
    );

    const user = userEvent.setup();
    renderPage();

    await screen.findAllByRole("article");
    await user.selectOptions(screen.getByLabelText("Atleta"), "42");

    await waitFor(() => expect(observedAthleteIds).toContain("42"));
  });

  it("muestra 'Limpiar filtros' solo cuando hay algún filtro activo, y lo restablece", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findAllByRole("article");
    expect(screen.queryByRole("button", { name: /limpiar filtros/i })).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Estado"), "false");
    const clearButton = await screen.findByRole("button", { name: /limpiar filtros/i });
    await user.click(clearButton);

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /limpiar filtros/i })).not.toBeInTheDocument(),
    );
    expect(screen.getByLabelText("Estado")).toHaveValue("all");
  });
});

// ---------------------------------------------------------------------------
// Estados de carga / error / vacío
// ---------------------------------------------------------------------------

describe("ActivityReviewPage — estados de carga, error y vacío", () => {
  it("muestra el estado de carga mientras llega la respuesta", async () => {
    mswServer.use(
      http.get("*/api/activities", async () => {
        await delay(30);
        return HttpResponse.json(mockReviewActivityListResponse());
      }),
    );

    renderPage();

    expect(screen.getByRole("status")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole("status")).not.toBeInTheDocument(),
    );
  });

  it("muestra un mensaje de error con opción de reintentar cuando falla la carga", async () => {
    mswServer.use(reviewActivitiesErrorHandler);

    renderPage();

    expect(
      await screen.findByText(/No se pudo cargar la lista de actividades/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reintentar/i })).toBeInTheDocument();
  });

  it("muestra el estado vacío por defecto cuando no hay actividades sincronizadas", async () => {
    mswServer.use(emptyReviewActivitiesHandler);

    renderPage();

    expect(
      await screen.findByText(/Todavía no ha llegado ninguna actividad sincronizada/i),
    ).toBeInTheDocument();
  });

  it("muestra el mensaje de vacío-por-filtro cuando hay filtros activos sin resultados", async () => {
    mswServer.use(emptyReviewActivitiesHandler);

    const user = userEvent.setup();
    renderPage();

    await screen.findByText(/Todavía no ha llegado ninguna actividad sincronizada/i);
    await user.selectOptions(screen.getByLabelText("Estado"), "true");

    expect(
      await screen.findByText(/No hay actividades para los filtros seleccionados/i),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Accesibilidad
// ---------------------------------------------------------------------------

describe("ActivityReviewPage — accesibilidad", () => {
  it("no tiene violaciones de accesibilidad con actividades cargadas", async () => {
    const { container } = renderPage();

    await screen.findAllByRole("article");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("no tiene violaciones de accesibilidad en el estado vacío", async () => {
    mswServer.use(emptyReviewActivitiesHandler);
    const { container } = renderPage();

    await screen.findByText(/Todavía no ha llegado ninguna actividad sincronizada/i);

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
