/**
 * Tests vitest — StandingsTable y StandingsTab.
 *
 * Cubre:
 *  - Render de filas (rank, nombre, club, puntos)
 *  - Club highlight — filas `is_our_club`
 *  - Ordenación client-side (rank, nombre, puntos)
 *  - Filtro de categoría
 *  - Toggle "Solo mi club"
 *  - Estado vacío después de filtro
 *  - Fixture de campo completo (26 categorías)
 *  - StandingsTab: loading, error (cold-start), vacío, con datos
 *  - axe: 0 violaciones a11y
 */
import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { setupServer } from "msw/node";

import { StandingsTable } from "@/components/competitions/results/StandingsTable";
import { StandingsTab } from "@/components/competitions/tabs/StandingsTab";
import {
  makeRaceEventStandingsResponse,
  makeFullFieldStandingsResponse,
  raceResultsHandlers,
  standingsEmptyHandler,
  standingsErrorHandler,
} from "@/test/msw/raceResultsHandlers";

// ---------------------------------------------------------------------------
// Store mock — useAuthStore
// ---------------------------------------------------------------------------

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((selector) =>
    selector({ accessToken: "test-token", user: null }),
  ),
}));

// ---------------------------------------------------------------------------
// MSW server
// ---------------------------------------------------------------------------

const server = setupServer(...raceResultsHandlers);

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  });
}

function renderStandingsTable(
  overrides?: Parameters<typeof makeRaceEventStandingsResponse>[0],
) {
  const data = makeRaceEventStandingsResponse(overrides);
  return render(
    <MemoryRouter>
      <StandingsTable data={data} />
    </MemoryRouter>,
  );
}

function renderStandingsTab(raceEventId = 1) {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <StandingsTab raceEventId={raceEventId} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// StandingsTable — render básico
// ---------------------------------------------------------------------------

describe("StandingsTable — render básico", () => {
  it("muestra las filas de corredores", () => {
    renderStandingsTable();
    // 2 categorías con 3 y 2 corredores
    expect(screen.getAllByTestId(/^standings-row-/)).toHaveLength(5);
  });

  it("muestra rank, nombre y puntos de las filas", () => {
    renderStandingsTable();
    const rowA = screen.getByTestId("standings-row-101");
    // Rank "1" aparece dos veces en la fila (rank + best_position), usamos getAllByText
    expect(within(rowA).getAllByText("1").length).toBeGreaterThanOrEqual(1);
    expect(within(rowA).getByText("Corredor A")).toBeInTheDocument();
    expect(within(rowA).getByText("75")).toBeInTheDocument();
  });

  it("renderiza el selector de categoría con las opciones", () => {
    renderStandingsTable();
    const select = screen.getByTestId("standings-category-select");
    expect(select).toBeInTheDocument();
    expect(within(select as HTMLSelectElement).getByText("Todas")).toBeInTheDocument();
    expect(within(select as HTMLSelectElement).getByText("Infantil Masculino")).toBeInTheDocument();
    expect(within(select as HTMLSelectElement).getByText("Infantil Femenino")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Club highlight
// ---------------------------------------------------------------------------

describe("StandingsTable — club highlight", () => {
  it("las filas is_our_club tienen data-our-club=true", () => {
    renderStandingsTable();
    const rowOurClub = screen.getByTestId("standings-row-101");
    expect(rowOurClub).toHaveAttribute("data-our-club", "true");
  });

  it("las filas rivales NO tienen data-our-club", () => {
    renderStandingsTable();
    const rowRival = screen.getByTestId("standings-row-202");
    expect(rowRival).not.toHaveAttribute("data-our-club");
  });

  it("las filas del club tienen aria-label que indica pertenencia", () => {
    renderStandingsTable();
    const rowOurClub = screen.getByTestId("standings-row-101");
    expect(rowOurClub).toHaveAttribute(
      "aria-label",
      "Corredor A — corredor de nuestro club",
    );
  });

  it("las filas del club muestran el badge 'Club'", () => {
    renderStandingsTable();
    const rowOurClub = screen.getByTestId("standings-row-101");
    expect(within(rowOurClub).getAllByText("Club").length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Filtro de categoría
// ---------------------------------------------------------------------------

describe("StandingsTable — filtro de categoría", () => {
  it("muestra todas las filas cuando no hay filtro", () => {
    renderStandingsTable();
    expect(screen.getAllByTestId(/^standings-row-/)).toHaveLength(5);
  });

  it("filtra a la categoría seleccionada", async () => {
    const user = userEvent.setup();
    renderStandingsTable();

    const select = screen.getByTestId("standings-category-select");
    await user.selectOptions(select, "2");

    expect(screen.getAllByTestId(/^standings-row-/)).toHaveLength(2);
    expect(screen.queryByTestId("standings-category-section-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("standings-category-section-2")).toBeInTheDocument();
  });

  it("vuelve a mostrar todas al seleccionar 'Todas'", async () => {
    const user = userEvent.setup();
    renderStandingsTable();

    const select = screen.getByTestId("standings-category-select");
    await user.selectOptions(select, "2");
    await user.selectOptions(select, "all");

    expect(screen.getAllByTestId(/^standings-row-/)).toHaveLength(5);
  });
});

// ---------------------------------------------------------------------------
// Toggle "Solo mi club"
// ---------------------------------------------------------------------------

describe("StandingsTable — toggle solo mi club", () => {
  it("muestra solo filas is_our_club al activar el toggle", async () => {
    const user = userEvent.setup();
    renderStandingsTable();

    const toggle = screen.getByTestId("standings-club-only-toggle");
    await user.click(toggle);

    const rows = screen.getAllByTestId(/^standings-row-/);
    // Solo 2 corredores del club (101 en INF_M, 401 en INF_F)
    expect(rows).toHaveLength(2);
    rows.forEach((row) => {
      expect(row).toHaveAttribute("data-our-club", "true");
    });
  });

  it("muestra estado vacío cuando solo hay rivales y se filtra por club", async () => {
    const user = userEvent.setup();
    const data = makeRaceEventStandingsResponse({
      categories: [
        {
          category_id: 1,
          code: "INF_M",
          label: "Infantil Masculino",
          rows: [
            {
              rank: 1,
              competitor_id: 999,
              display_name: "Solo Rival",
              club_text: "Club Rival",
              athlete_id: null,
              is_our_club: false,
              total_points: 50,
              races_run: 2,
              podiums: 0,
              best_position: 1,
            },
          ],
        },
      ],
    });

    render(
      <MemoryRouter>
        <StandingsTable data={data} />
      </MemoryRouter>,
    );

    const toggle = screen.getByTestId("standings-club-only-toggle");
    await user.click(toggle);

    expect(screen.getByTestId("standings-empty-after-filter")).toBeInTheDocument();
    expect(screen.queryByTestId(/^standings-row-/)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// hideClubFilter prop
// ---------------------------------------------------------------------------

describe("StandingsTable — hideClubFilter", () => {
  it("el toggle 'Solo mi club' NO se renderiza cuando hideClubFilter=true", () => {
    const data = makeRaceEventStandingsResponse();
    render(
      <MemoryRouter>
        <StandingsTable data={data} hideClubFilter />
      </MemoryRouter>,
    );
    expect(
      screen.queryByTestId("standings-club-only-toggle"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("standings-club-only-label"),
    ).not.toBeInTheDocument();
  });

  it("el toggle 'Solo mi club' SÍ se renderiza cuando hideClubFilter=false (default)", () => {
    renderStandingsTable();
    expect(
      screen.getByTestId("standings-club-only-toggle"),
    ).toBeInTheDocument();
  });

  it("el selector de categoría sigue presente con hideClubFilter=true", () => {
    const data = makeRaceEventStandingsResponse();
    render(
      <MemoryRouter>
        <StandingsTable data={data} hideClubFilter />
      </MemoryRouter>,
    );
    expect(
      screen.getByTestId("standings-category-select"),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Ordenación
// ---------------------------------------------------------------------------

describe("StandingsTable — ordenación", () => {
  it("ordena por rank por defecto (ascendente)", () => {
    renderStandingsTable();
    const select = screen.getByTestId("standings-category-select");
    // Filtrar a INF_M para verificar ordenación
    // El order visual por defecto es rank asc: 101 (rank=1) primero
    const section = screen.getByTestId("standings-category-section-1");
    const rows = within(section).getAllByTestId(/^standings-row-/);
    expect(rows[0]).toHaveAttribute("data-testid", "standings-row-101");
    void select; // evitar warning lint
  });

  it("ordena por nombre al hacer click en el botón Corredor", async () => {
    const user = userEvent.setup();
    renderStandingsTable();

    const select = screen.getByTestId("standings-category-select");
    await user.selectOptions(select, "1");

    const sortBtn = screen.getByRole("button", { name: /ordenar por corredor/i });
    await user.click(sortBtn);

    const rows = screen.getAllByTestId(/^standings-row-/);
    expect(rows[0]).toHaveAttribute("data-testid", "standings-row-101");
    expect(rows[1]).toHaveAttribute("data-testid", "standings-row-202");
  });

  it("ordena por puntos al hacer click en el botón Puntos", async () => {
    const user = userEvent.setup();
    renderStandingsTable();

    const select = screen.getByTestId("standings-category-select");
    await user.selectOptions(select, "1");

    const sortBtn = screen.getByRole("button", { name: /ordenar por puntos/i });
    await user.click(sortBtn);

    // El sort de puntos es asc → 48, 60, 75 → 303, 202, 101
    const rows = screen.getAllByTestId(/^standings-row-/);
    expect(rows[0]).toHaveAttribute("data-testid", "standings-row-303");
  });
});

// ---------------------------------------------------------------------------
// Fixture campo completo (26 categorías)
// ---------------------------------------------------------------------------

describe("StandingsTable — campo completo 26 categorías", () => {
  it("renderiza sin errores con 260 filas", () => {
    const fullData = makeFullFieldStandingsResponse();
    render(
      <MemoryRouter>
        <StandingsTable data={fullData} />
      </MemoryRouter>,
    );

    expect(
      screen.getAllByTestId(/^standings-category-section-/).length,
    ).toBe(26);
    expect(screen.getByTestId("standings-count-badge")).toHaveTextContent(
      "260 corredores",
    );
  });

  it("filtrar a una categoría del campo completo muestra solo 1 sección", async () => {
    const user = userEvent.setup();
    const fullData = makeFullFieldStandingsResponse();
    render(
      <MemoryRouter>
        <StandingsTable data={fullData} />
      </MemoryRouter>,
    );

    const select = screen.getByTestId("standings-category-select");
    await user.selectOptions(select, "3");

    expect(screen.getAllByTestId(/^standings-category-section-/)).toHaveLength(1);
    expect(screen.getAllByTestId(/^standings-row-/)).toHaveLength(10);
  });

  it("'Solo mi club' con 26 categorías filtra a 26 corredores (1 por categoría)", async () => {
    const user = userEvent.setup();
    const fullData = makeFullFieldStandingsResponse();
    render(
      <MemoryRouter>
        <StandingsTable data={fullData} />
      </MemoryRouter>,
    );

    const toggle = screen.getByTestId("standings-club-only-toggle");
    await user.click(toggle);

    expect(screen.getAllByTestId(/^standings-row-/)).toHaveLength(26);
    expect(screen.getByTestId("standings-count-badge")).toHaveTextContent(
      "26 corredores",
    );
  });
});

// ---------------------------------------------------------------------------
// StandingsTab — estados
// ---------------------------------------------------------------------------

describe("StandingsTab — estado vacío (backend vacío)", () => {
  it("muestra estado vacío cuando el backend retorna categorías vacías", async () => {
    server.use(standingsEmptyHandler);
    renderStandingsTab(1);

    await screen.findByTestId("standings-tab-empty", {}, { timeout: 3000 });
    expect(
      screen.getByText(/sin clasificación disponible/i),
    ).toBeInTheDocument();
  });
});

describe("StandingsTab — estado error", () => {
  it("muestra banner de error cuando el endpoint falla (503)", async () => {
    server.use(standingsErrorHandler);
    renderStandingsTab(1);

    const errorBanner = await screen.findByTestId("standings-tab-error", {}, { timeout: 3000 });
    expect(errorBanner).toBeInTheDocument();
  });

  it("muestra mensaje de cold-start para error 503", async () => {
    server.use(standingsErrorHandler);
    renderStandingsTab(1);

    await screen.findByTestId("standings-tab-error", {}, { timeout: 3000 });
    // 503 es un cold-start simulado
    // El handler retorna 503 → el componente NO detecta cold-start desde status codes
    // en el branch actual (solo ECONNABORTED/ERR_NETWORK/502/503/504)
    // 503 SÍ activa cold-start
    expect(
      screen.getByText(/el servidor está iniciando/i),
    ).toBeInTheDocument();
  });

  it("muestra botón de reintentar en el estado de error", async () => {
    server.use(standingsErrorHandler);
    renderStandingsTab(1);

    await screen.findByTestId("standings-tab-error", {}, { timeout: 3000 });
    expect(screen.getByTestId("standings-tab-retry")).toBeInTheDocument();
  });
});

describe("StandingsTab — con datos (via MSW)", () => {
  it("renderiza la tabla cuando hay datos", async () => {
    renderStandingsTab(1);

    await screen.findByTestId("standings-table-root", {}, { timeout: 3000 });
    expect(screen.getAllByTestId(/^standings-row-/).length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Accessibility (axe)
// ---------------------------------------------------------------------------

describe("StandingsTab — accesibilidad", () => {
  it("no tiene violaciones axe con datos cargados", async () => {
    const { container } = renderStandingsTab(1);

    await screen.findByTestId("standings-table-root", {}, { timeout: 5000 });

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones axe en estado vacío", async () => {
    server.use(standingsEmptyHandler);
    const { container } = renderStandingsTab(1);

    await screen.findByTestId("standings-tab-empty", {}, { timeout: 3000 });

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
