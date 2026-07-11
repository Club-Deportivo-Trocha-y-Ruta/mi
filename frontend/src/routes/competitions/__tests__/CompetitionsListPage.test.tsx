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
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";

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

function mockAuthAs(role: "admin" | "coach" | "parent") {
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
  // Ver nota junto al afterEach de abajo.
  document.body.style.pointerEvents = "";
});

// El AlertDialog de Radix (base de ConfirmDialog) bloquea el body con
// `pointer-events: none` mientras está abierto — a diferencia del antiguo
// ConfirmDeleteDialog (un <div> plano sin overlay modal real). El retiro de
// ese estilo al cerrar no siempre es sincrónico con el desmontaje del
// diálogo (puede quedar pendiente en un timer/efecto que sigue a la
// aserción "ya no está en el documento"), así que un test cuyo diálogo
// queda abierto al terminar (p. ej. error 409, que no cierra el diálogo)
// puede filtrar el bloqueo al siguiente test. Se restaura en beforeEach
// (defensivo, cubre residuos diferidos de un test previo) y en afterEach
// (limpia lo que sí alcanzó a aplicarse de forma sincrónica) para aislar
// cada test sin depender del timing interno de Radix.
afterEach(() => {
  document.body.style.pointerEvents = "";
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

  it("click en la fila navega al detalle de la competencia", async () => {
    mockAuthAs("coach");
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/" element={<CompetitionsListPage />} />
        <Route
          path="/competitions/:id"
          element={<div>DETALLE COMPETENCIA</div>}
        />
      </Routes>,
    );

    await waitFor(() =>
      expect(
        inTable().getByText("Copa Valle XCO — Válida I"),
      ).toBeInTheDocument(),
    );
    const row = inTable()
      .getByText("Copa Valle XCO — Válida I")
      .closest("tr");
    expect(row).not.toBeNull();
    // Click en una celda no interactiva de la fila (no el link de nombre ni el kebab).
    await user.click(row as HTMLElement);
    expect(
      await screen.findByText("DETALLE COMPETENCIA"),
    ).toBeInTheDocument();
  });

  it("kebab de acciones ya no incluye 'Ver detalle' (la fila es clickeable)", async () => {
    mockAuthAs("coach");
    const user = userEvent.setup();
    renderWithProviders(<CompetitionsListPage />);

    await waitFor(() =>
      expect(
        inTable().getByText("Copa Valle XCO — Válida I"),
      ).toBeInTheDocument(),
    );
    const kebab = inTable().getAllByRole("button", {
      name: /Acciones para/i,
    })[0];
    await user.click(kebab);
    expect(screen.queryByText("Ver detalle")).not.toBeInTheDocument();
    // El kebab sigue ofreciendo otras acciones.
    expect(await screen.findByText("Editar metadata")).toBeInTheDocument();
  });
});

describe("CompetitionsListPage — acciones secundarias del header", () => {
  it("acción 'Cargar resultados' apunta a /competitions/import", async () => {
    mockAuthAs("coach");
    renderWithProviders(<CompetitionsListPage />);
    // El nombre accesible viene del aria-label del link.
    const link = await screen.findByRole("link", {
      name: /Cargar resultados de una válida/i,
    });
    expect(link).toHaveAttribute("href", "/competitions/import");
  });

  it("acción 'Sin enlazar' apunta a /competitions/unlinked", async () => {
    mockAuthAs("coach");
    renderWithProviders(<CompetitionsListPage />);
    const link = await screen.findByRole("link", {
      name: /Ver competidores sin enlazar/i,
    });
    expect(link).toHaveAttribute("href", "/competitions/unlinked");
  });

  it("las acciones secundarias mantienen altura táctil ≥44px", async () => {
    mockAuthAs("coach");
    renderWithProviders(<CompetitionsListPage />);
    const importLink = await screen.findByRole("link", {
      name: /Cargar resultados de una válida/i,
    });
    const unlinkedLink = screen.getByRole("link", {
      name: /Ver competidores sin enlazar/i,
    });
    // El patrón del repo usa min-h-[44px] (clase utilitaria de altura mínima).
    expect(importLink.className).toMatch(/min-h-\[44px\]/);
    expect(unlinkedLink.className).toMatch(/min-h-\[44px\]/);
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
    // tone="danger": el foco inicial va a Cancelar, nunca a Eliminar válida.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Cancelar/i })).toHaveFocus(),
    );
    expect(
      screen.getByRole("button", { name: /Eliminar válida/i }),
    ).not.toHaveFocus();
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

describe("CompetitionsListPage — cleanup duplicado (feature 009)", () => {
  it("coach: 'Eliminar duplicado' visible en válida sin resultados → confirma → DELETE /cleanup", async () => {
    let cleanupCalled = false;
    mswServer.use(
      http.get("*/api/race-analysis/race-events/", () =>
        HttpResponse.json({
          items: [
            makeRaceEventListItem({
              id: 77,
              name: "Duplicado Cali",
              has_results: false,
              has_calendar_event: true,
            }),
          ],
          total: 1,
        }),
      ),
      http.delete("*/api/race-analysis/race-events/77/cleanup", () => {
        cleanupCalled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    mockAuthAs("coach");
    const user = userEvent.setup();
    renderWithProviders(<CompetitionsListPage />);
    await waitFor(() =>
      expect(inTable().getByText("Duplicado Cali")).toBeInTheDocument(),
    );
    await user.click(
      inTable().getByRole("button", { name: /Acciones para Duplicado Cali/i }),
    );
    await user.click(
      await screen.findByRole("menuitem", { name: /Eliminar duplicado/i }),
    );
    expect(
      await screen.findByRole("alertdialog", {
        name: /Eliminar competencia duplicada/i,
      }),
    ).toBeInTheDocument();
    // tone="danger": el foco inicial va a Cancelar, nunca a Eliminar duplicado.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Cancelar/i })).toHaveFocus(),
    );
    expect(
      screen.getByRole("button", { name: /Eliminar duplicado/i }),
    ).not.toHaveFocus();
    await user.click(
      screen.getByRole("button", { name: /Eliminar duplicado/i }),
    );
    await waitFor(() => expect(cleanupCalled).toBe(true));
    await waitFor(() =>
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument(),
    );
  });

  it("coach: 'Eliminar duplicado' NO aparece en válida con resultados (protegida)", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/", () =>
        HttpResponse.json({
          items: [
            makeRaceEventListItem({
              id: 78,
              name: "Válida protegida 78",
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
      expect(inTable().getByText("Válida protegida 78")).toBeInTheDocument(),
    );
    await user.click(
      inTable().getByRole("button", { name: /Acciones para Válida protegida 78/i }),
    );
    await screen.findByText("Editar metadata");
    expect(screen.queryByText(/Eliminar duplicado/i)).not.toBeInTheDocument();
  });

  it("parent: nunca ve 'Eliminar duplicado' aunque la válida no tenga resultados", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/", () =>
        HttpResponse.json({
          items: [
            makeRaceEventListItem({
              id: 79,
              name: "Válida parent 79",
              has_results: false,
            }),
          ],
          total: 1,
        }),
      ),
    );
    mockAuthAs("parent");
    const user = userEvent.setup();
    renderWithProviders(<CompetitionsListPage />);
    await waitFor(() =>
      expect(inTable().getByText("Válida parent 79")).toBeInTheDocument(),
    );
    await user.click(
      inTable().getByRole("button", { name: /Acciones para Válida parent 79/i }),
    );
    await screen.findByText("Editar metadata");
    expect(screen.queryByText(/Eliminar duplicado/i)).not.toBeInTheDocument();
  });

  it("0 violaciones jest-axe con el dialog de cleanup abierto", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/", () =>
        HttpResponse.json({
          items: [
            makeRaceEventListItem({
              id: 80,
              name: "Duplicado a11y",
              has_results: false,
              has_calendar_event: true,
            }),
          ],
          total: 1,
        }),
      ),
    );
    mockAuthAs("coach");
    const user = userEvent.setup();
    const { container } = renderWithProviders(<CompetitionsListPage />);
    await waitFor(() =>
      expect(inTable().getByText("Duplicado a11y")).toBeInTheDocument(),
    );
    await user.click(
      inTable().getByRole("button", { name: /Acciones para Duplicado a11y/i }),
    );
    await user.click(
      await screen.findByRole("menuitem", { name: /Eliminar duplicado/i }),
    );
    await screen.findByRole("alertdialog", {
      name: /Eliminar competencia duplicada/i,
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
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
