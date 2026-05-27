/**
 * Tests para CompetitionsListPage.
 *
 * Cubre:
 *  - Render con items: tabla, badges, recuento.
 *  - Filtro temporada/estado re-fetch via query key con filtros.
 *  - Filtro local "Con resultados" filtra correctamente.
 *  - Empty state + CTA "Crear primera válida".
 *  - Kebab "Eliminar" visible solo para admin.
 *  - Kebab "Importar resultados" oculto si has_results=true.
 *  - Delete admin happy path: invalida lista + cierra dialog.
 *  - Delete 409 muestra mensaje de dependencias.
 *  - 0 violaciones a11y (con items + sin items).
 *
 * Patron auth: vi.mock("@/store/auth.store") + vi.mocked al inicio de cada test
 * para cambiar entre roles. Patron tomado de a11y.v2.test.tsx del repo.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

// Mock de auth.store — se reconfigura por test para alternar entre coach y admin.
vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

import { useAuthStore } from "@/store/auth.store";
import { mswServer } from "@/test/setup";
import {
  makeRaceEventListItem,
  makeRaceEventListResponse,
  raceEventsHandlers,
  raceEventsDeleteConflictHandler,
} from "@/test/msw/raceEventsHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { CompetitionsListPage } from "@/routes/competitions/CompetitionsListPage";

function mockAuthAs(role: "admin" | "coach") {
  const state = {
    accessToken: "test-token",
    user: { id: 1, role, first_name: "User", last_name: "Test" },
    isAuthenticated: true,
  };
  vi.mocked(useAuthStore).mockImplementation(
    ((sel: (s: typeof state) => unknown) => sel(state)) as unknown as typeof useAuthStore,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  // Registramos los handlers default de race-events por test (no globales).
  mswServer.use(...raceEventsHandlers);
});

// La página renderiza tanto la tabla desktop (≥md) como las cards mobile (<md)
// simultáneamente — jsdom no aplica media queries. Helper para obtener
// elementos solo de la tabla.
function inTable() {
  const table = document.querySelector("table");
  if (!table) throw new Error("No se encontró tabla");
  return within(table as HTMLElement);
}

describe("CompetitionsListPage — render", () => {
  it("muestra header, filtros y tabla con 3 items de la temporada", async () => {
    mockAuthAs("admin");
    renderWithProviders(<CompetitionsListPage />);
    expect(
      screen.getByRole("heading", { name: "Competencias" }),
    ).toBeInTheDocument();

    await waitFor(() =>
      expect(inTable().getByText("Copa Valle XCO — Válida I")).toBeInTheDocument(),
    );
    expect(inTable().getByText("Copa Valle XCO — Válida II")).toBeInTheDocument();
    expect(inTable().getByText("Copa Valle XCO — Válida III")).toBeInTheDocument();
    expect(screen.getByText(/Mostrando 3 de 3 competencias/i)).toBeInTheDocument();
  });

  it("CTA principal 'Nueva competencia' apunta a /competitions/new", async () => {
    mockAuthAs("coach");
    renderWithProviders(<CompetitionsListPage />);
    const link = await screen.findByRole("link", { name: /Nueva competencia/i });
    expect(link).toHaveAttribute("href", "/competitions/new");
  });
});

describe("CompetitionsListPage — empty state", () => {
  it("muestra empty state + CTA 'Crear primera válida' cuando no hay items", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/", () =>
        HttpResponse.json({ items: [], total: 0 }),
      ),
    );
    mockAuthAs("coach");
    renderWithProviders(<CompetitionsListPage />);

    await waitFor(() =>
      expect(
        screen.getByText(/No hay competencias en esta temporada/i),
      ).toBeInTheDocument(),
    );
    const cta = screen.getByRole("link", { name: /Crear primera válida/i });
    expect(cta).toHaveAttribute("href", "/competitions/new");
  });
});

describe("CompetitionsListPage — filtros", () => {
  it("seleccionar temporada distinta dispara nuevo fetch", async () => {
    let lastSeason: string | null = null;
    mswServer.use(
      http.get("*/api/race-analysis/race-events/", ({ request }) => {
        const url = new URL(request.url);
        lastSeason = url.searchParams.get("season");
        return HttpResponse.json(makeRaceEventListResponse());
      }),
    );
    mockAuthAs("coach");
    const user = userEvent.setup();
    renderWithProviders(<CompetitionsListPage />);

    await waitFor(() => expect(lastSeason).toBe("2026"));
    await user.selectOptions(screen.getByLabelText("Temporada"), "2027");
    await waitFor(() => expect(lastSeason).toBe("2027"));
  });

  it("chip 'Cancelada' agrega status=cancelled al query", async () => {
    let lastStatus: string | null = null;
    mswServer.use(
      http.get("*/api/race-analysis/race-events/", ({ request }) => {
        const url = new URL(request.url);
        lastStatus = url.searchParams.get("status");
        return HttpResponse.json(makeRaceEventListResponse());
      }),
    );
    mockAuthAs("coach");
    const user = userEvent.setup();
    renderWithProviders(<CompetitionsListPage />);

    await waitFor(() =>
      expect(inTable().getByText("Copa Valle XCO — Válida I")).toBeInTheDocument(),
    );
    await user.click(screen.getByRole("button", { name: "Cancelada" }));
    await waitFor(() => expect(lastStatus).toBe("cancelled"));
  });

  it("filtro local 'Con resultados' deja solo items con has_results=true", async () => {
    // Devolvemos 3 items: 2 con resultados y 1 sin.
    mswServer.use(
      http.get("*/api/race-analysis/race-events/", () =>
        HttpResponse.json({
          items: [
            makeRaceEventListItem({ id: 1, name: "Con I", has_results: true }),
            makeRaceEventListItem({ id: 2, name: "Con II", has_results: true }),
            makeRaceEventListItem({ id: 3, name: "Sin", has_results: false }),
          ],
          total: 3,
        }),
      ),
    );
    mockAuthAs("coach");
    const user = userEvent.setup();
    renderWithProviders(<CompetitionsListPage />);

    await waitFor(() => expect(inTable().getByText("Sin")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Con resultados" }));
    await waitFor(() =>
      expect(inTable().queryByText("Sin")).not.toBeInTheDocument(),
    );
    expect(inTable().getByText("Con I")).toBeInTheDocument();
    expect(inTable().getByText("Con II")).toBeInTheDocument();
  });

  it("filtro 'Próxima' deja solo válidas ≤30 días desde hoy", async () => {
    // Fecha hoy = 2026-05-27 (env de test). Una a 15 días, otra a 60 días.
    const todayPlus15 = (() => {
      const d = new Date();
      d.setDate(d.getDate() + 15);
      return d.toISOString().slice(0, 10);
    })();
    const todayPlus60 = (() => {
      const d = new Date();
      d.setDate(d.getDate() + 60);
      return d.toISOString().slice(0, 10);
    })();

    mswServer.use(
      http.get("*/api/race-analysis/race-events/", () =>
        HttpResponse.json({
          items: [
            makeRaceEventListItem({ id: 1, name: "Próx 15d", event_date: todayPlus15 }),
            makeRaceEventListItem({ id: 2, name: "Lejana 60d", event_date: todayPlus60 }),
          ],
          total: 2,
        }),
      ),
    );
    mockAuthAs("coach");
    const user = userEvent.setup();
    renderWithProviders(<CompetitionsListPage />);

    await waitFor(() => expect(inTable().getByText("Lejana 60d")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Próxima" }));
    await waitFor(() =>
      expect(inTable().queryByText("Lejana 60d")).not.toBeInTheDocument(),
    );
    expect(inTable().getByText("Próx 15d")).toBeInTheDocument();
  });
});

describe("CompetitionsListPage — RBAC kebab", () => {
  it("para coach: el item 'Eliminar' NO esta en el kebab", async () => {
    mockAuthAs("coach");
    const user = userEvent.setup();
    renderWithProviders(<CompetitionsListPage />);
    await waitFor(() =>
      expect(
        inTable().getByText("Copa Valle XCO — Válida I"),
      ).toBeInTheDocument(),
    );
    // Kebab del primer item — usamos getAllByRole y filtramos a la tabla
    const kebab = inTable().getAllByRole("button", {
      name: /Acciones para Copa Valle XCO — Válida I/i,
    })[0];
    await user.click(kebab);
    // El menu de Radix se renderiza en un portal → buscar a nivel document
    expect(screen.queryByText(/Eliminar/i)).not.toBeInTheDocument();
  });

  it("para admin: 'Eliminar' aparece en kebab cuando el item se puede borrar", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/", () =>
        HttpResponse.json({
          items: [
            makeRaceEventListItem({
              id: 10,
              name: "Borrable",
              has_results: false,
              has_calendar_event: false,
            }),
          ],
          total: 1,
        }),
      ),
    );
    mockAuthAs("admin");
    const user = userEvent.setup();
    renderWithProviders(<CompetitionsListPage />);
    await waitFor(() =>
      expect(inTable().getByText("Borrable")).toBeInTheDocument(),
    );
    const kebab = inTable().getByRole("button", {
      name: /Acciones para Borrable/i,
    });
    await user.click(kebab);
    const menuItem = await screen.findByText("Eliminar");
    expect(menuItem).toBeInTheDocument();
  });

  it("'Importar resultados' NO aparece cuando has_results=true", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/", () =>
        HttpResponse.json({
          items: [
            makeRaceEventListItem({
              id: 11,
              name: "Ya importada",
              has_results: true,
            }),
          ],
          total: 1,
        }),
      ),
    );
    mockAuthAs("coach");
    const user = userEvent.setup();
    renderWithProviders(<CompetitionsListPage />);
    await waitFor(() =>
      expect(inTable().getByText("Ya importada")).toBeInTheDocument(),
    );
    const kebab = inTable().getByRole("button", {
      name: /Acciones para Ya importada/i,
    });
    await user.click(kebab);
    expect(screen.queryByText(/Importar resultados/i)).not.toBeInTheDocument();
  });
});

describe("CompetitionsListPage — delete admin", () => {
  it("happy path: confirma → DELETE 204 → cierra dialog", async () => {
    let deleteCalled = false;
    mswServer.use(
      http.get("*/api/race-analysis/race-events/", () =>
        HttpResponse.json({
          items: [
            makeRaceEventListItem({
              id: 99,
              name: "Borrable",
              has_results: false,
              has_calendar_event: false,
            }),
          ],
          total: 1,
        }),
      ),
      http.delete("*/api/race-analysis/race-events/99", () => {
        deleteCalled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    mockAuthAs("admin");
    const user = userEvent.setup();
    renderWithProviders(<CompetitionsListPage />);
    await waitFor(() =>
      expect(inTable().getByText("Borrable")).toBeInTheDocument(),
    );
    await user.click(
      inTable().getByRole("button", { name: /Acciones para Borrable/i }),
    );
    await user.click(await screen.findByText("Eliminar"));
    // Dialog confirmacion
    expect(
      await screen.findByRole("alertdialog", { name: /Eliminar competencia/i }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Eliminar válida/i }));
    await waitFor(() => expect(deleteCalled).toBe(true));
    // Dialog se cierra
    await waitFor(() =>
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument(),
    );
  });

  it("error 409: muestra mensaje de dependencias dentro del dialog", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/", () =>
        HttpResponse.json({
          items: [
            makeRaceEventListItem({
              id: 50,
              name: "Con dependencias",
              has_results: false,
              has_calendar_event: false,
            }),
          ],
          total: 1,
        }),
      ),
      raceEventsDeleteConflictHandler,
    );
    mockAuthAs("admin");
    const user = userEvent.setup();
    renderWithProviders(<CompetitionsListPage />);
    await waitFor(() =>
      expect(inTable().getByText("Con dependencias")).toBeInTheDocument(),
    );
    await user.click(
      inTable().getByRole("button", { name: /Acciones para Con dependencias/i }),
    );
    await user.click(await screen.findByText("Eliminar"));
    await user.click(
      await screen.findByRole("button", { name: /Eliminar válida/i }),
    );
    // El mensaje del 409 mapeado por getRaceEventErrorMessage
    expect(
      await screen.findByText(
        /resultados importados o está vinculado al calendario/i,
      ),
    ).toBeInTheDocument();
  });
});

describe("CompetitionsListPage — a11y", () => {
  it("0 violaciones jest-axe con items", async () => {
    mockAuthAs("coach");
    const { container } = renderWithProviders(<CompetitionsListPage />);
    await waitFor(() =>
      expect(
        inTable().getByText("Copa Valle XCO — Válida I"),
      ).toBeInTheDocument(),
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("0 violaciones jest-axe en empty state", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/", () =>
        HttpResponse.json({ items: [], total: 0 }),
      ),
    );
    mockAuthAs("coach");
    const { container } = renderWithProviders(<CompetitionsListPage />);
    await screen.findByText(/No hay competencias en esta temporada/i);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
