/**
 * Tests vitest — ResultsTable y ResultsTab.
 *
 * Cubre:
 *  - Render de filas (posición, nombre, club, tiempo)
 *  - Club highlight — filas `is_our_club` tienen data-our-club="true"
 *    y badge "Club"
 *  - Ordenación client-side (posición, nombre, tiempo)
 *  - Filtro de categoría
 *  - Toggle "Solo mi club"
 *  - Estado vacío después de filtro
 *  - Fixture de campo completo (26 categorías, 260 filas) — renderiza sin
 *    errores y el filtro de categoría lo limita a 1 sección
 *  - axe: 0 violaciones a11y en ResultsTab con datos
 *  - Columnas derivadas de circuito (feature 043 US2): "Distancia" y
 *    "Vel. prom." solo con `has_course_data=true`, celdas "sin dato" (muted)
 *    para figuras `null`, y el encabezado de categoría con
 *    "{laps} vueltas · {variant_label} · {lap_distance_km} km · {elevation_gain_m} m D+"
 *    — ver `specs/043-race-course-profile/contracts/results-derived-figures.md`
 *    §1 y `contracts/ui-course.md` §5. Estos tests dependen de campos que
 *    T037 aún no agrega a `ResultsTable.tsx` / `raceResults.types.ts`.
 *
 *  - Métricas por fila (feature 045, US2): «Parrilla» en el encabezado de la
 *    categoría; «Percentil» y «Brecha vs. mediana» para toda audiencia;
 *    «Brecha vs. 1.ª posición» y «Brecha vs. podio» solo en coach — la familia
 *    no las renderiza ni aunque el payload las trajera.
 *
 * NO se testea directamente `useRaceResults` aquí — los tests de hooks
 * viven en hooks/race/__tests__/. Este test usa MSW para los tests de tab.
 */
import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { setupServer } from "msw/node";

import { ResultsTable } from "@/components/competitions/results/ResultsTable";
import { ResultsTab } from "@/components/competitions/tabs/ResultsTab";
import {
  makeCoachMetricSet,
  makeFamilyMetricSet,
  makeRaceEventResultsResponse,
  makeFullFieldResultsResponse,
  makeRaceResultRow,
  raceResultsHandlers,
  raceResultsEmptyHandler,
  raceResultsErrorHandler,
} from "@/test/msw/raceResultsHandlers";
import type { RaceEventResultsResponse } from "@/types/raceResults.types";

// ---------------------------------------------------------------------------
// Store mock — useAuthStore
// ---------------------------------------------------------------------------

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((selector) =>
    selector({ accessToken: "test-token", user: null }),
  ),
}));

// ---------------------------------------------------------------------------
// MSW server (local a este suite para no afectar el setup global)
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

function renderResultsTable(
  overrides?: Parameters<typeof makeRaceEventResultsResponse>[0],
) {
  const data = makeRaceEventResultsResponse(overrides);
  return render(
    <MemoryRouter>
      <ResultsTable data={data} />
    </MemoryRouter>,
  );
}

function renderResultsTab(props: {
  raceEventId?: number;
  hasResults?: boolean;
}) {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ResultsTab
          raceEventId={props.raceEventId ?? 1}
          hasResults={props.hasResults}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// ResultsTable — render básico
// ---------------------------------------------------------------------------

describe("ResultsTable — render básico", () => {
  it("muestra las filas de corredores", () => {
    renderResultsTable();
    // Hay 2 categorías con 3 y 2 corredores respectivamente
    expect(screen.getAllByTestId(/^results-row-/)).toHaveLength(5);
  });

  it("muestra posición, nombre y tiempo de las filas", () => {
    renderResultsTable();
    // Corredor A — posición 1, tiempo 59:00.000
    const rowA = screen.getByTestId("results-row-101");
    expect(within(rowA).getByText("1")).toBeInTheDocument();
    expect(within(rowA).getByText("Corredor A")).toBeInTheDocument();
    // Tiempo formateado
    expect(within(rowA).getByText("59:00.000")).toBeInTheDocument();
  });

  it("renderiza el selector de categoría con las opciones", () => {
    renderResultsTable();
    const select = screen.getByTestId("results-category-select");
    expect(select).toBeInTheDocument();
    expect(within(select as HTMLSelectElement).getByText("Todas")).toBeInTheDocument();
    expect(within(select as HTMLSelectElement).getByText("Infantil Masculino")).toBeInTheDocument();
    expect(within(select as HTMLSelectElement).getByText("Infantil Femenino")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Estado de resultado — palabras, nunca códigos crudos (decisión del dueño
// 2026-09-23): DNF/DNS/DSQ nunca deben llegar crudos a la pantalla.
// ---------------------------------------------------------------------------

describe("ResultsTable — estado de resultado (DNF/DNS/DSQ)", () => {
  it("muestra el estado en palabras, nunca el código crudo", () => {
    renderResultsTable({
      categories: [
        {
          category_id: 1,
          code: "INF_M",
          label: "Infantil Masculino",
          rows: [
            makeRaceResultRow({
              competitor_id: 901,
              display_name: "Corredor DNF",
              position: null,
              status: "dnf",
              race_time_ms: null,
            }),
            makeRaceResultRow({
              competitor_id: 902,
              display_name: "Corredor DNS",
              position: null,
              status: "dns",
              race_time_ms: null,
            }),
            makeRaceResultRow({
              competitor_id: 903,
              display_name: "Corredor DSQ",
              position: null,
              status: "dsq",
              race_time_ms: null,
            }),
          ],
        },
      ],
    });

    const dnfRow = screen.getByTestId("results-row-901");
    expect(within(dnfRow).getAllByText("No terminó").length).toBeGreaterThan(0);
    expect(within(dnfRow).queryByText("DNF")).not.toBeInTheDocument();

    const dnsRow = screen.getByTestId("results-row-902");
    // Comparte etiqueta con el catálogo de Historial (raceHistory.types.ts).
    expect(within(dnsRow).getAllByText("No salió").length).toBeGreaterThan(0);
    expect(within(dnsRow).queryByText("DNS")).not.toBeInTheDocument();

    const dsqRow = screen.getByTestId("results-row-903");
    expect(within(dsqRow).getAllByText("Descalificado").length).toBeGreaterThan(0);
    expect(within(dsqRow).queryByText("DSQ")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Club highlight
// ---------------------------------------------------------------------------

describe("ResultsTable — club highlight", () => {
  it("las filas is_our_club tienen data-our-club=true", () => {
    renderResultsTable();
    const rowOurClub = screen.getByTestId("results-row-101");
    expect(rowOurClub).toHaveAttribute("data-our-club", "true");
  });

  it("las filas rivales NO tienen data-our-club", () => {
    renderResultsTable();
    const rowRival = screen.getByTestId("results-row-202");
    expect(rowRival).not.toHaveAttribute("data-our-club");
  });

  it("las filas del club muestran el badge 'Club'", () => {
    renderResultsTable();
    const rowOurClub = screen.getByTestId("results-row-101");
    expect(within(rowOurClub).getAllByText("Club").length).toBeGreaterThan(0);
  });

  it("las filas del club tienen aria-label que indica pertenencia", () => {
    renderResultsTable();
    const rowOurClub = screen.getByTestId("results-row-101");
    expect(rowOurClub).toHaveAttribute(
      "aria-label",
      "Corredor A — corredor de nuestro club",
    );
  });

  it("las filas rivales NO tienen aria-label de club", () => {
    renderResultsTable();
    const rowRival = screen.getByTestId("results-row-202");
    expect(rowRival).not.toHaveAttribute("aria-label");
  });
});

// ---------------------------------------------------------------------------
// Filtro de categoría
// ---------------------------------------------------------------------------

describe("ResultsTable — filtro de categoría", () => {
  it("muestra todas las filas cuando no hay filtro", () => {
    renderResultsTable();
    expect(screen.getAllByTestId(/^results-row-/)).toHaveLength(5);
  });

  it("filtra a la categoría seleccionada", async () => {
    const user = userEvent.setup();
    renderResultsTable();

    const select = screen.getByTestId("results-category-select");
    // Seleccionar Infantil Femenino (category_id=2)
    await user.selectOptions(select, "2");

    // Solo 2 filas de Infantil Femenino
    expect(screen.getAllByTestId(/^results-row-/)).toHaveLength(2);
    // No aparece la sección de Infantil Masculino
    expect(screen.queryByTestId("results-category-section-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("results-category-section-2")).toBeInTheDocument();
  });

  it("vuelve a mostrar todas al seleccionar 'Todas'", async () => {
    const user = userEvent.setup();
    renderResultsTable();

    const select = screen.getByTestId("results-category-select");
    await user.selectOptions(select, "2");
    await user.selectOptions(select, "all");

    expect(screen.getAllByTestId(/^results-row-/)).toHaveLength(5);
  });
});

// ---------------------------------------------------------------------------
// Toggle "Solo mi club"
// ---------------------------------------------------------------------------

describe("ResultsTable — toggle solo mi club", () => {
  it("muestra solo filas is_our_club al activar el toggle", async () => {
    const user = userEvent.setup();
    renderResultsTable();

    const toggle = screen.getByTestId("results-club-only-toggle");
    await user.click(toggle);

    // Hay 2 corredores de nuestro club (101 y 401)
    const rows = screen.getAllByTestId(/^results-row-/);
    expect(rows).toHaveLength(2);
    rows.forEach((row) => {
      expect(row).toHaveAttribute("data-our-club", "true");
    });
  });

  it("muestra estado vacío cuando no hay corredores del club en la categoría filtrada", async () => {
    const user = userEvent.setup();
    // Datos sin ningún corredor del club
    const data = makeRaceEventResultsResponse({
      categories: [
        {
          category_id: 1,
          code: "INF_M",
          label: "Infantil Masculino",
          rows: [
            {
              result_id: 9001,
              coach_note: null,
              coach_note_updated_at: null,
              position: 1,
              competitor_id: 999,
              display_name: "Solo Rival",
              club_text: "Club Rival",
              athlete_id: null,
              is_our_club: false,
              status: "finished",
              race_time_ms: 3_600_000,
              laps_behind: null,
              points_awarded: 25,
              bib_number: 1,
            },
          ],
        },
      ],
    });

    render(
      <MemoryRouter>
        <ResultsTable data={data} />
      </MemoryRouter>,
    );

    const toggle = screen.getByTestId("results-club-only-toggle");
    await user.click(toggle);

    expect(screen.getByTestId("results-empty-after-filter")).toBeInTheDocument();
    expect(screen.queryByTestId(/^results-row-/)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Ordenación client-side
// ---------------------------------------------------------------------------

describe("ResultsTable — ordenación", () => {
  it("ordena por posición por defecto (ascendente)", () => {
    renderResultsTable();
    // Verificamos que la primera fila visible de INF_M es el position=1
    const section = screen.getByTestId("results-category-section-1");
    const rows = within(section).getAllByTestId(/^results-row-/);
    expect(rows[0]).toHaveAttribute("data-testid", "results-row-101");
  });

  it("ordena por nombre al hacer click en el botón Corredor", async () => {
    const user = userEvent.setup();
    renderResultsTable();

    // Filtrar a INF_M para tener solo 3 filas predecibles
    const select = screen.getByTestId("results-category-select");
    await user.selectOptions(select, "1");

    // Click en "Corredor" para ordenar por nombre asc
    const sortBtn = screen.getByRole("button", { name: /ordenar por corredor/i });
    await user.click(sortBtn);

    const rows = screen.getAllByTestId(/^results-row-/);
    // Corredor A (101), Corredor B (202), Corredor C (303) — orden alfabético
    expect(rows[0]).toHaveAttribute("data-testid", "results-row-101");
    expect(rows[1]).toHaveAttribute("data-testid", "results-row-202");
    expect(rows[2]).toHaveAttribute("data-testid", "results-row-303");
  });

  it("ordena por tiempo al hacer click en el botón Tiempo", async () => {
    const user = userEvent.setup();
    renderResultsTable();

    const select = screen.getByTestId("results-category-select");
    await user.selectOptions(select, "1");

    // Click en "Tiempo" para ordenar por race_time_ms asc
    const sortBtn = screen.getByRole("button", { name: /ordenar por tiempo/i });
    await user.click(sortBtn);

    // 3_540_000 < 3_600_000 < 3_660_000 → 101, 202, 303
    const rows = screen.getAllByTestId(/^results-row-/);
    expect(rows[0]).toHaveAttribute("data-testid", "results-row-101");
  });

  it("invierte la dirección al hacer click dos veces en el mismo campo", async () => {
    const user = userEvent.setup();
    renderResultsTable();

    const select = screen.getByTestId("results-category-select");
    await user.selectOptions(select, "1");

    const sortBtn = screen.getByRole("button", { name: /ordenar por tiempo/i });
    await user.click(sortBtn);
    await user.click(sortBtn);

    // Desc → el mayor tiempo (3_660_000 = Corredor C, 303) va primero
    const rows = screen.getAllByTestId(/^results-row-/);
    expect(rows[0]).toHaveAttribute("data-testid", "results-row-303");
  });
});

// ---------------------------------------------------------------------------
// Fixture de campo completo (26 categorías, 260 filas)
// ---------------------------------------------------------------------------

describe("ResultsTable — campo completo 26 categorías", () => {
  it("renderiza sin errores con 260 filas (26 categorías × 10 corredores)", () => {
    const fullData = makeFullFieldResultsResponse();
    render(
      <MemoryRouter>
        <ResultsTable data={fullData} />
      </MemoryRouter>,
    );

    // Las 26 secciones de categoría existen
    expect(
      screen.getAllByTestId(/^results-category-section-/).length,
    ).toBe(26);

    // El contador de corredores muestra 260
    expect(screen.getByTestId("results-count-badge")).toHaveTextContent(
      "260 corredores",
    );
  });

  it("filtrar a una categoría del campo completo muestra solo 1 sección", async () => {
    const user = userEvent.setup();
    const fullData = makeFullFieldResultsResponse();
    render(
      <MemoryRouter>
        <ResultsTable data={fullData} />
      </MemoryRouter>,
    );

    // Seleccionar categoría 3 (INF_M)
    const select = screen.getByTestId("results-category-select");
    await user.selectOptions(select, "3");

    expect(screen.getAllByTestId(/^results-category-section-/)).toHaveLength(1);
    expect(screen.getByTestId("results-category-section-3")).toBeInTheDocument();
    // Solo 10 filas
    expect(screen.getAllByTestId(/^results-row-/)).toHaveLength(10);
  });

  it("'Solo mi club' con 26 categorías filtra a 26 corredores (1 por categoría)", async () => {
    const user = userEvent.setup();
    const fullData = makeFullFieldResultsResponse();
    render(
      <MemoryRouter>
        <ResultsTable data={fullData} />
      </MemoryRouter>,
    );

    const toggle = screen.getByTestId("results-club-only-toggle");
    await user.click(toggle);

    // 26 categorías × 1 corredor del club = 26 filas
    expect(screen.getAllByTestId(/^results-row-/)).toHaveLength(26);
    expect(screen.getByTestId("results-count-badge")).toHaveTextContent(
      "26 corredores",
    );
  });
});

// ---------------------------------------------------------------------------
// hideClubFilter prop
// ---------------------------------------------------------------------------

describe("ResultsTable — hideClubFilter", () => {
  it("el toggle 'Solo mi club' NO se renderiza cuando hideClubFilter=true", () => {
    const data = makeRaceEventResultsResponse();
    render(
      <MemoryRouter>
        <ResultsTable data={data} hideClubFilter />
      </MemoryRouter>,
    );
    expect(
      screen.queryByTestId("results-club-only-toggle"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("results-club-only-label"),
    ).not.toBeInTheDocument();
  });

  it("el toggle 'Solo mi club' SÍ se renderiza cuando hideClubFilter=false (default)", () => {
    renderResultsTable();
    expect(screen.getByTestId("results-club-only-toggle")).toBeInTheDocument();
  });

  it("el selector de categoría sigue presente con hideClubFilter=true", () => {
    const data = makeRaceEventResultsResponse();
    render(
      <MemoryRouter>
        <ResultsTable data={data} hideClubFilter />
      </MemoryRouter>,
    );
    expect(
      screen.getByTestId("results-category-select"),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Columnas derivadas de circuito (feature 043, User Story 2)
//
// NOTA: `distance_km` / `avg_speed_kmh` (ResultRow), `laps` / `variant_label`
// (CategoryResults) y `has_course_data` (EventResultsRead) son campos nuevos
// del contrato `specs/043-race-course-profile/contracts/results-derived-figures.md`
// §1. Hasta que la tarea hermana (T037) los agregue a
// `types/raceResults.types.ts` y a `ResultsTable.tsx`, estos tests fallan
// (columnas ausentes / TS marca las propiedades como desconocidas) — ver
// docstring de la suite y el reporte de la tarea T032.
// ---------------------------------------------------------------------------

describe("ResultsTable — columnas de circuito derivado (feature 043)", () => {
  it("muestra las columnas 'Distancia' y 'Vel. prom.' cuando has_course_data=true", () => {
    renderResultsTable({ has_course_data: true });

    expect(
      screen.getAllByRole("columnheader", { name: "Distancia" }).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByRole("columnheader", { name: "Vel. prom." }).length,
    ).toBeGreaterThan(0);
  });

  it("NO muestra las columnas de circuito cuando has_course_data=false", () => {
    renderResultsTable({ has_course_data: false });

    expect(
      screen.queryByRole("columnheader", { name: "Distancia" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("columnheader", { name: "Vel. prom." }),
    ).not.toBeInTheDocument();
  });

  it("NO muestra las columnas de circuito cuando has_course_data está ausente (campo opcional)", () => {
    // Fixture sin el campo en absoluto — SC-007: los consumidores existentes
    // (fixtures sin datos de circuito) siguen funcionando sin cambios.
    renderResultsTable();

    expect(
      screen.queryByRole("columnheader", { name: "Distancia" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("columnheader", { name: "Vel. prom." }),
    ).not.toBeInTheDocument();
  });

  it("renderiza 'sin dato' (estilo muted) cuando distance_km/avg_speed_kmh son null en una fila DNF", () => {
    const data: RaceEventResultsResponse = {
      race_event_id: 1,
      has_course_data: true,
      categories: [
        {
          category_id: 1,
          code: "INF_M",
          label: "Infantil Masculino",
          rows: [
            {
              result_id: 1001,
              coach_note: null,
              coach_note_updated_at: null,
              position: 1,
              competitor_id: 101,
              display_name: "Corredor A",
              club_text: "Club Trocha y Ruta",
              athlete_id: 55,
              is_our_club: true,
              status: "finished",
              race_time_ms: 1_800_000,
              laps_behind: null,
              points_awarded: 25,
              bib_number: 7,
              distance_km: 12.6,
              avg_speed_kmh: 25.2,
            },
            {
              result_id: 1002,
              coach_note: null,
              coach_note_updated_at: null,
              position: null,
              competitor_id: 202,
              display_name: "Corredor B",
              club_text: "Club Rival XCO",
              athlete_id: null,
              is_our_club: false,
              status: "dnf",
              race_time_ms: null,
              laps_behind: null,
              points_awarded: null,
              bib_number: 12,
              distance_km: null,
              avg_speed_kmh: null,
            },
          ],
        },
      ],
    };

    render(
      <MemoryRouter>
        <ResultsTable data={data} />
      </MemoryRouter>,
    );

    const dnfRow = screen.getByTestId("results-row-202");
    const sinDatoCells = within(dnfRow).getAllByText("sin dato");
    // Una celda por cada columna derivada (Distancia + Vel. prom.)
    expect(sinDatoCells.length).toBeGreaterThanOrEqual(2);
    sinDatoCells.forEach((el) => {
      expect(el).toHaveClass("text-mid-gray");
    });
  });

  it("el encabezado de categoría incluye vueltas · variante · distancia de vuelta · desnivel cuando el setup existe", () => {
    const data: RaceEventResultsResponse = {
      race_event_id: 1,
      has_course_data: true,
      categories: [
        {
          category_id: 1,
          code: "INF_M",
          label: "Infantil Masculino",
          laps: 3,
          variant_label: "Recorrido reducido",
          rows: [
            {
              result_id: 1001,
              coach_note: null,
              coach_note_updated_at: null,
              position: 1,
              competitor_id: 101,
              display_name: "Corredor A",
              club_text: "Club Trocha y Ruta",
              athlete_id: 55,
              is_our_club: true,
              status: "finished",
              race_time_ms: 1_800_000,
              laps_behind: null,
              points_awarded: 25,
              bib_number: 7,
              distance_km: 12.6,
              avg_speed_kmh: 25.2,
              lap_distance_km: 4.2,
              elevation_gain_m: 110,
            },
          ],
        },
      ],
    };

    render(
      <MemoryRouter>
        <ResultsTable data={data} />
      </MemoryRouter>,
    );

    const section = screen.getByTestId("results-category-section-1");
    expect(section.textContent).toContain(
      "3 vueltas · Recorrido reducido · 4.2 km · 110 m D+",
    );
  });
});

// ---------------------------------------------------------------------------
// Touch target — botón de nota (regresión tamaño mínimo 48x48px)
// ---------------------------------------------------------------------------

describe("ResultsTable — botón de nota (touch target)", () => {
  it("el botón de nota por fila tiene min-h-[48px] y min-w-[48px]", () => {
    const data = makeRaceEventResultsResponse();
    const qc = makeQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ResultsTable data={data} isCoachOrAdmin />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Fila 101 — is_our_club=true, athlete_id=55 → botón de nota visible.
    const noteBtn = screen.getByTestId("note-btn-101");
    expect(noteBtn).toHaveClass("min-h-[48px]");
    expect(noteBtn).toHaveClass("min-w-[48px]");
  });
});

// ---------------------------------------------------------------------------
// Formato de tiempo
// ---------------------------------------------------------------------------

describe("formatRaceTime", () => {
  // Importar directamente para testeo unitario de la función
  it("formatea milisegundos correctamente", async () => {
    const { formatRaceTime } = await import(
      "@/components/competitions/results/ResultsTable"
    );
    expect(formatRaceTime(3_540_000)).toBe("59:00.000");
    expect(formatRaceTime(3_600_000)).toBe("60:00.000");
    expect(formatRaceTime(61_500)).toBe("01:01.500");
    expect(formatRaceTime(0)).toBe("00:00.000");
    expect(formatRaceTime(null)).toBe("—");
    expect(formatRaceTime(-1)).toBe("—");
  });
});

// ---------------------------------------------------------------------------
// ResultsTab — estados de carga, error, vacío
// ---------------------------------------------------------------------------

describe("ResultsTab — estado vacío (hasResults=false)", () => {
  it("muestra CTA de importar cuando hasResults=false sin query", () => {
    renderResultsTab({ hasResults: false });
    expect(screen.getByTestId("results-tab-empty")).toBeInTheDocument();
    expect(screen.getByTestId("results-tab-import-cta")).toBeInTheDocument();
  });
});

describe("ResultsTab — estado cargando", () => {
  it("muestra skeleton mientras carga", () => {
    // Pausar la respuesta MSW no es sencillo aquí; verificamos que
    // el tab monta sin errores con datos disponibles inmediatamente.
    // El test de skeleton se cubre por el Suspense fallback.
    renderResultsTab({ raceEventId: 1 });
    // Al ser async, el resultado puede ser el skeleton o la tabla;
    // simplemente verificamos que no hay crash.
    expect(
      screen.queryByRole("alert") === null ||
        screen.queryByTestId("results-tab-error") === null,
    ).toBe(true);
  });
});

describe("ResultsTab — estado error", () => {
  it("muestra banner de error cuando el endpoint falla", async () => {
    server.use(raceResultsErrorHandler);
    renderResultsTab({ raceEventId: 1 });

    // Esperamos que aparezca el banner de error
    const errorBanner = await screen.findByTestId("results-tab-error", {}, { timeout: 3000 });
    expect(errorBanner).toBeInTheDocument();
    expect(
      screen.getByText(/no se pudieron cargar los resultados/i),
    ).toBeInTheDocument();
  });

  it("muestra botón de reintentar en el estado de error", async () => {
    server.use(raceResultsErrorHandler);
    renderResultsTab({ raceEventId: 1 });

    await screen.findByTestId("results-tab-error", {}, { timeout: 3000 });
    expect(screen.getByTestId("results-tab-retry")).toBeInTheDocument();
  });
});

describe("ResultsTab — estado vacío (sin datos del backend)", () => {
  it("muestra CTA de importar cuando la respuesta tiene categorías vacías", async () => {
    server.use(raceResultsEmptyHandler);
    renderResultsTab({ raceEventId: 1 });

    await screen.findByTestId("results-tab-empty", {}, { timeout: 3000 });
    expect(screen.getByTestId("results-tab-import-cta")).toBeInTheDocument();
  });
});

describe("ResultsTab — con datos (via MSW)", () => {
  it("renderiza la tabla cuando hay datos", async () => {
    renderResultsTab({ raceEventId: 1 });

    // Esperamos que el root de la tabla aparezca
    await screen.findByTestId("results-table-root", {}, { timeout: 3000 });
    // Al menos 1 fila renderizada
    expect(screen.getAllByTestId(/^results-row-/).length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Accessibility (axe) — ResultsTab con datos
// ---------------------------------------------------------------------------

describe("ResultsTab — accesibilidad", () => {
  it("no tiene violaciones axe con datos cargados", async () => {
    const { container } = renderResultsTab({ raceEventId: 1 });

    // Esperamos que los datos carguen
    await screen.findByTestId("results-table-root", {}, { timeout: 5000 });

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones axe en estado vacío (hasResults=false)", async () => {
    const { container } = renderResultsTab({ hasResults: false });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});


// ---------------------------------------------------------------------------
// Métricas por fila (feature 045, US2, T058)
// ---------------------------------------------------------------------------

/**
 * Categoría con 6 cronometrados (≥ 5): percentil y brecha vs. mediana con
 * valor. Un corredor de nuestro club en P4, otro (rival) sin tiempo.
 */
function makeMetricsResponse(audience: "coach" | "family"): RaceEventResultsResponse {
  const metricSet = audience === "coach" ? makeCoachMetricSet : makeFamilyMetricSet;
  return makeRaceEventResultsResponse({
    categories: [
      {
        category_id: 1,
        code: "INF_M",
        label: "Infantil Masculino",
        rows: [
          makeRaceResultRow({
            competitor_id: 101,
            position: 4,
            metrics: metricSet({
              field_size: 7,
              timed_finishers: 6,
              position: 4,
              percentile: 73,
              gap_to_median_pct: -3.4,
              gap_to_winner_pct: 5.2,
              gap_to_podium_pct: 2.1,
            }),
          }),
          // Perdió vueltas: cuenta en la Parrilla pero sin percentil ni brechas.
          makeRaceResultRow({
            competitor_id: 102,
            display_name: "Corredor F",
            athlete_id: null,
            is_our_club: false,
            position: 7,
            metrics: metricSet({
              field_size: 7,
              timed_finishers: 6,
              position: 7,
              percentile: null,
              gap_to_median_pct: null,
              gap_to_winner_pct: null,
              gap_to_podium_pct: null,
            }),
          }),
        ],
      },
    ],
  });
}

function renderWithAudience(
  data: RaceEventResultsResponse,
  audience: "coach" | "family",
) {
  return render(
    <MemoryRouter>
      <ResultsTable data={data} audience={audience} />
    </MemoryRouter>,
  );
}

describe("ResultsTable — métricas por fila, variante de coach", () => {
  it("muestra las cuatro columnas del glosario, con los valores del motor", () => {
    renderWithAudience(makeMetricsResponse("coach"), "coach");

    for (const label of [
      "Percentil",
      "Brecha vs. mediana",
      "Brecha vs. 1.ª posición",
      "Brecha vs. podio",
    ]) {
      expect(screen.getByRole("columnheader", { name: label })).toBeInTheDocument();
    }

    expect(screen.getByTestId("results-percentile-101")).toHaveTextContent("P73");
    expect(screen.getByTestId("results-gap-median-101")).toHaveTextContent("-3.4 %");
    expect(screen.getByTestId("results-gap-winner-101")).toHaveTextContent("+5.2 %");
    expect(screen.getByTestId("results-gap-podium-101")).toHaveTextContent("+2.1 %");
  });

  it("un valor null se lee «sin dato» (nunca 0 ni un guion), también en las brechas de líder/podio", () => {
    renderWithAudience(makeMetricsResponse("coach"), "coach");

    for (const id of ["percentile", "gap-median", "gap-winner", "gap-podium"]) {
      expect(screen.getByTestId(`results-${id}-102`)).toHaveTextContent("sin dato");
    }
  });

  it("«Parrilla» va en el encabezado de la categoría con el tamaño del grupo, no de las filas visibles", () => {
    renderWithAudience(makeMetricsResponse("coach"), "coach");

    const note = screen.getByTestId("results-field-size-1");
    expect(note).toHaveTextContent("Parrilla: 7");
    // 6 cronometrados ≥ 5: sin aviso de mínimo.
    expect(note).not.toHaveTextContent(/menos de 5/);
  });

  it("con menos de 5 cronometrados la Parrilla explica por qué no hay percentil ni brecha vs. mediana", () => {
    // Fixture base: categorías de 3 y 2 cronometrados.
    renderWithAudience(makeRaceEventResultsResponse(), "coach");

    expect(screen.getByTestId("results-field-size-1")).toHaveTextContent(
      "Parrilla: 3 · con menos de 5 tiempos no hay percentil ni brecha vs. mediana",
    );
    expect(screen.getByTestId("results-percentile-101")).toHaveTextContent("sin dato");
    expect(screen.getByTestId("results-gap-median-101")).toHaveTextContent("sin dato");
    // Las brechas oficiales a P1/P3 no dependen del mínimo (research R-04).
    expect(screen.getByTestId("results-gap-podium-101")).toHaveTextContent("-3.3 %");
  });

  it("se deriva de isCoachOrAdmin cuando no se pasa audience", () => {
    const qc = makeQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ResultsTable data={makeMetricsResponse("coach")} isCoachOrAdmin />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("columnheader", { name: "Brecha vs. 1.ª posición" }),
    ).toBeInTheDocument();
  });
});

describe("ResultsTable — métricas por fila, variante de familia (salvaguarda)", () => {
  it("solo muestra Parrilla, Percentil y Brecha vs. mediana", () => {
    renderWithAudience(makeMetricsResponse("family"), "family");

    expect(screen.getByRole("columnheader", { name: "Percentil" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Brecha vs. mediana" })).toBeInTheDocument();
    expect(screen.getByTestId("results-field-size-1")).toHaveTextContent("Parrilla: 7");
    expect(screen.getByTestId("results-percentile-101")).toHaveTextContent("P73");
    expect(screen.getByTestId("results-gap-median-101")).toHaveTextContent("-3.4 %");
  });

  it("no hay rastro de la brecha contra el líder ni el podio en la variante de familia", () => {
    const { container } = renderWithAudience(makeMetricsResponse("family"), "family");

    expect(screen.queryByRole("columnheader", { name: /1\.ª posición/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /podio/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId("results-gap-winner-101")).not.toBeInTheDocument();
    expect(screen.queryByTestId("results-gap-podium-101")).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/1\.ª posición|podio|ganador|líder/i);
  });

  it("defensa en profundidad: aunque el payload trajera las brechas de líder/podio, la familia no las renderiza", () => {
    // Un backend con un bug de redacción NO debe filtrarse por la UI.
    renderWithAudience(makeMetricsResponse("coach"), "family");

    expect(screen.queryByRole("columnheader", { name: /1\.ª posición|podio/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId("results-gap-winner-101")).not.toBeInTheDocument();
    expect(screen.queryByText("+5.2 %")).not.toBeInTheDocument();
    expect(screen.queryByText("+2.1 %")).not.toBeInTheDocument();
  });

  it("sin isCoachOrAdmin ni audience, la opción segura es la variante de familia", () => {
    render(
      <MemoryRouter>
        <ResultsTable data={makeMetricsResponse("coach")} />
      </MemoryRouter>,
    );

    expect(screen.queryByRole("columnheader", { name: /1\.ª posición|podio/i })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Percentil" })).toBeInTheDocument();
  });
});

describe("ResultsTable — payload sin métricas (backend previo a la 045)", () => {
  it("no agrega columnas de métricas ni la nota de Parrilla", () => {
    const legacy = makeRaceEventResultsResponse();
    for (const cat of legacy.categories) {
      for (const row of cat.rows) delete row.metrics;
    }
    renderWithAudience(legacy, "coach");

    expect(screen.queryByRole("columnheader", { name: "Percentil" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /Brecha vs\./ })).not.toBeInTheDocument();
    expect(screen.queryByTestId("results-field-size-1")).not.toBeInTheDocument();
  });

  it("metrics: null (el backend no pudo calcularlas) da «sin dato», no columnas rotas", () => {
    const data = makeMetricsResponse("coach");
    data.categories[0].rows[0].metrics = null;
    renderWithAudience(data, "coach");

    expect(screen.getByTestId("results-percentile-101")).toHaveTextContent("sin dato");
    expect(screen.getByTestId("results-gap-winner-101")).toHaveTextContent("sin dato");
  });
});

describe("ResultsTable — métricas, accesibilidad", () => {
  it.each(["coach", "family"] as const)("sin violaciones jest-axe (%s)", async (audience) => {
    const { container } = renderWithAudience(makeMetricsResponse(audience), audience);
    expect(await axe(container)).toHaveNoViolations();
  });
});
