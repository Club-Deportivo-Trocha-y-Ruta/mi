/**
 * Tests vitest — RosterPanel (convocatoria de una válida).
 *
 * Cubre:
 *  - Render de entradas (nombre, estado)
 *  - Estado vacío
 *  - Estado de error con botón reintentar
 *  - Flujo agregar atleta (mutation crea entrada → invalidación)
 *  - Flujo editar estado de una entrada
 *  - Flujo eliminar entrada (diálogo confirmación)
 *  - Banner de reconciliación con discrepancias
 *  - Modo solo lectura (isReadOnly=true): controles ocultos
 *  - axe: 0 violaciones a11y
 *
 * Privacidad (T029):
 *  - Padre (isReadOnly=true): solo ve su propio hijo; nombre de otro menor ausente.
 *  - axe 0 violaciones en modo padre.
 *
 * Estrategia:
 *  - Mockear los hooks de roster (useRaceRoster, mutations) para aislar
 *    la lógica del componente del transporte HTTP.
 *  - Para el flujo de agregar, también mockeamos useAthletes.
 */
import {
  describe,
  it,
  expect,
  vi,
  beforeEach,
} from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((selector: (s: { accessToken: string; user: null }) => unknown) =>
    selector({ accessToken: "test-token", user: null }),
  ),
}));

const mockUseRaceRoster = vi.fn();
const mockCreateEntry = vi.fn();
const mockUpdateEntry = vi.fn();
const mockDeleteEntry = vi.fn();

vi.mock("@/hooks/race/useRaceRoster", () => ({
  useRaceRoster: (...args: unknown[]) => mockUseRaceRoster(...args),
  useCreateRosterEntry: () => ({
    mutate: mockCreateEntry,
    isPending: false,
    error: null,
  }),
  useUpdateRosterEntry: () => ({
    mutate: mockUpdateEntry,
    isPending: false,
  }),
  useDeleteRosterEntry: () => ({
    mutate: mockDeleteEntry,
    isPending: false,
  }),
  getRosterErrorMessage: (err: unknown) =>
    (err as { message?: string })?.message ?? "Error inesperado.",
}));

const mockUseAthletes = vi.fn();
vi.mock("@/hooks/athletes/useAthletes", () => ({
  useAthletes: (...args: unknown[]) => mockUseAthletes(...args),
}));

import { RosterPanel } from "@/components/competitions/roster/RosterPanel";
import type { RaceRosterResponse } from "@/types/raceRoster.types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ROSTER_WITH_ENTRIES: RaceRosterResponse = {
  race_event_id: 1,
  entries: [
    { id: 1, athlete_id: 10, athlete_name: "Atleta Uno", status: "called_up", note: null },
    { id: 2, athlete_id: 20, athlete_name: "Atleta Dos", status: "confirmed", note: "Inscrito" },
    { id: 3, athlete_id: 30, athlete_name: "Atleta Tres", status: "withdrawn", note: null },
  ],
  reconciliation: { called_up_no_result: [], result_not_called_up: [] },
};

const ROSTER_EMPTY: RaceRosterResponse = {
  race_event_id: 1,
  entries: [],
  reconciliation: { called_up_no_result: [], result_not_called_up: [] },
};

const ROSTER_WITH_DISCREPANCIES: RaceRosterResponse = {
  race_event_id: 1,
  entries: [
    { id: 1, athlete_id: 10, athlete_name: "Atleta Uno", status: "called_up", note: null },
  ],
  reconciliation: {
    called_up_no_result: [10],
    result_not_called_up: [99],
  },
};

const ATHLETES_LIST = {
  items: [
    { id: 10, first_name: "Atleta", last_name: "Uno", birth_date: "2012-01-01", sex: "M", club_join_date: null, years_in_club: null, age_decimal: 14, category: "JUV", club_id: 1, created_at: "2026-01-01", user_id: 10 },
    { id: 20, first_name: "Atleta", last_name: "Dos", birth_date: "2013-03-15", sex: "F", club_join_date: null, years_in_club: null, age_decimal: 13, category: "JUV", club_id: 1, created_at: "2026-01-01", user_id: 20 },
    { id: 40, first_name: "Atleta", last_name: "Nuevo", birth_date: "2014-06-20", sex: "M", club_join_date: null, years_in_club: null, age_decimal: 12, category: "INF", club_id: 1, created_at: "2026-01-01", user_id: 40 },
  ],
  total: 3,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQC() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
}

function wrap(ui: ReactNode) {
  return render(
    <QueryClientProvider client={makeQC()}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function happyRoster(overrides?: Partial<RaceRosterResponse>) {
  mockUseRaceRoster.mockReturnValue({
    data: { ...ROSTER_WITH_ENTRIES, ...overrides },
    isLoading: false,
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  });
  mockUseAthletes.mockReturnValue({ data: ATHLETES_LIST, isLoading: false });
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Render básico
// ---------------------------------------------------------------------------

describe("RosterPanel — render básico", () => {
  it("muestra las entradas del roster con nombre y estado", () => {
    happyRoster();
    wrap(<RosterPanel raceEventId={1} />);

    expect(screen.getByTestId("roster-entry-1")).toBeInTheDocument();
    expect(screen.getByTestId("roster-entry-2")).toBeInTheDocument();
    expect(screen.getByTestId("roster-entry-3")).toBeInTheDocument();
    expect(screen.getByText("Atleta Uno")).toBeInTheDocument();
    expect(screen.getByText("Atleta Dos")).toBeInTheDocument();
    expect(screen.getByText("Atleta Tres")).toBeInTheDocument();
  });

  it("muestra la nota de una entrada cuando existe", () => {
    happyRoster();
    wrap(<RosterPanel raceEventId={1} />);
    expect(screen.getByText("Inscrito")).toBeInTheDocument();
  });

  it("muestra el badge de contador con el número de atletas", () => {
    happyRoster();
    wrap(<RosterPanel raceEventId={1} />);
    expect(screen.getByTestId("roster-count-badge")).toHaveTextContent("3 atletas");
  });

  it("muestra los controles de edición en modo escritura", () => {
    happyRoster();
    wrap(<RosterPanel raceEventId={1} />);
    expect(screen.getByTestId("roster-add-picker")).toBeInTheDocument();
    expect(screen.getByTestId("roster-add-btn")).toBeInTheDocument();
    // Hay botones de eliminar para cada entrada
    expect(screen.getByTestId("roster-delete-btn-1")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Estado vacío
// ---------------------------------------------------------------------------

describe("RosterPanel — estado vacío", () => {
  it("muestra el estado vacío cuando no hay convocados", () => {
    mockUseRaceRoster.mockReturnValue({
      data: ROSTER_EMPTY,
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    mockUseAthletes.mockReturnValue({ data: ATHLETES_LIST, isLoading: false });

    wrap(<RosterPanel raceEventId={1} />);
    expect(screen.getByTestId("roster-panel-empty")).toBeInTheDocument();
    expect(screen.getByText(/Sin convocados/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Estado de error
// ---------------------------------------------------------------------------

describe("RosterPanel — estado de error", () => {
  it("muestra el banner de error con botón reintentar", () => {
    const mockRefetch = vi.fn();
    mockUseRaceRoster.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      isFetching: false,
      refetch: mockRefetch,
    });
    mockUseAthletes.mockReturnValue({ data: null, isLoading: false });

    wrap(<RosterPanel raceEventId={1} />);
    expect(screen.getByTestId("roster-panel-error")).toBeInTheDocument();
    expect(screen.getByTestId("roster-panel-retry")).toBeInTheDocument();
  });

  it("llama refetch al hacer clic en Reintentar", async () => {
    const user = userEvent.setup();
    const mockRefetch = vi.fn();
    mockUseRaceRoster.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      isFetching: false,
      refetch: mockRefetch,
    });
    mockUseAthletes.mockReturnValue({ data: null, isLoading: false });

    wrap(<RosterPanel raceEventId={1} />);
    await user.click(screen.getByTestId("roster-panel-retry"));
    expect(mockRefetch).toHaveBeenCalled();
  });

  it("muestra el skeleton durante la carga", () => {
    mockUseRaceRoster.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      isFetching: true,
      refetch: vi.fn(),
    });
    mockUseAthletes.mockReturnValue({ data: null, isLoading: true });

    wrap(<RosterPanel raceEventId={1} />);
    expect(screen.getByRole("status", { name: /cargando convocatoria/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Flujo agregar atleta
// ---------------------------------------------------------------------------

describe("RosterPanel — agregar atleta", () => {
  it("muestra el selector de atletas disponibles (excluye ya convocados)", () => {
    happyRoster();
    wrap(<RosterPanel raceEventId={1} />);

    const select = screen.getByTestId("roster-athlete-select") as HTMLSelectElement;
    // Atleta Nuevo (id=40) debería aparecer; Atleta Uno (10) y Dos (20) ya en roster
    expect(within(select).getByText("Atleta Nuevo")).toBeInTheDocument();
    // Los ya convocados no aparecen como opciones disponibles
    expect(
      within(select).queryByText("Atleta Uno"),
    ).not.toBeInTheDocument();
  });

  it("llama a la mutation create al hacer clic en Agregar con atleta seleccionado", async () => {
    const user = userEvent.setup();
    happyRoster();
    wrap(<RosterPanel raceEventId={1} />);

    const select = screen.getByTestId("roster-athlete-select");
    await user.selectOptions(select, "40");

    const addBtn = screen.getByTestId("roster-add-btn");
    await user.click(addBtn);

    expect(mockCreateEntry).toHaveBeenCalledWith(
      expect.objectContaining({
        raceEventId: 1,
        body: expect.objectContaining({ athlete_id: 40, status: "called_up" }),
      }),
      expect.any(Object),
    );
  });

  it("el botón Agregar está deshabilitado sin atleta seleccionado", () => {
    happyRoster();
    wrap(<RosterPanel raceEventId={1} />);
    expect(screen.getByTestId("roster-add-btn")).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Flujo editar estado
// ---------------------------------------------------------------------------

describe("RosterPanel — editar estado", () => {
  it("llama a la mutation update al cambiar el estado del select", async () => {
    const user = userEvent.setup();
    happyRoster();
    wrap(<RosterPanel raceEventId={1} />);

    const statusSelect = screen.getByTestId("roster-status-select-1");
    await user.selectOptions(statusSelect, "confirmed");

    expect(mockUpdateEntry).toHaveBeenCalledWith(
      expect.objectContaining({
        raceEventId: 1,
        entryId: 1,
        body: { status: "confirmed" },
      }),
      expect.any(Object),
    );
  });
});

// ---------------------------------------------------------------------------
// Flujo eliminar entrada
// ---------------------------------------------------------------------------

describe("RosterPanel — eliminar entrada", () => {
  it("abre el diálogo de confirmación al hacer clic en el botón eliminar", async () => {
    const user = userEvent.setup();
    happyRoster();
    wrap(<RosterPanel raceEventId={1} />);

    await user.click(screen.getByTestId("roster-delete-btn-1"));
    const dialog = screen.getByTestId("roster-delete-dialog");
    expect(dialog).toBeInTheDocument();
    // El texto "Retirar de la convocatoria" está en el título del diálogo
    expect(
      within(dialog).getByText(/Retirar de la convocatoria/i),
    ).toBeInTheDocument();
    // Nombre del atleta aparece en el <strong> dentro del cuerpo del diálogo
    expect(
      within(dialog).getByText(/Atleta Uno/i),
    ).toBeInTheDocument();
  });

  it("llama a la mutation delete al confirmar en el diálogo", async () => {
    const user = userEvent.setup();
    happyRoster();
    wrap(<RosterPanel raceEventId={1} />);

    await user.click(screen.getByTestId("roster-delete-btn-1"));
    await user.click(screen.getByTestId("roster-delete-confirm"));

    expect(mockDeleteEntry).toHaveBeenCalledWith(
      expect.objectContaining({ raceEventId: 1, entryId: 1 }),
      expect.any(Object),
    );
  });

  it("no llama delete al cancelar el diálogo", async () => {
    const user = userEvent.setup();
    happyRoster();
    wrap(<RosterPanel raceEventId={1} />);

    await user.click(screen.getByTestId("roster-delete-btn-1"));
    await user.click(screen.getByTestId("roster-delete-cancel"));

    expect(mockDeleteEntry).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Reconciliación
// ---------------------------------------------------------------------------

describe("RosterPanel — reconciliación", () => {
  it("muestra el banner de reconciliación cuando hay discrepancias", () => {
    mockUseRaceRoster.mockReturnValue({
      data: ROSTER_WITH_DISCREPANCIES,
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    mockUseAthletes.mockReturnValue({ data: ATHLETES_LIST, isLoading: false });

    wrap(<RosterPanel raceEventId={1} />);
    expect(screen.getByTestId("roster-reconciliation-banner")).toBeInTheDocument();
  });

  it("muestra la sección de convocados sin resultado", () => {
    mockUseRaceRoster.mockReturnValue({
      data: ROSTER_WITH_DISCREPANCIES,
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    mockUseAthletes.mockReturnValue({ data: ATHLETES_LIST, isLoading: false });

    wrap(<RosterPanel raceEventId={1} />);
    expect(screen.getByTestId("roster-called-up-no-result")).toBeInTheDocument();
    // badge para atleta 10 con nombre del roster
    expect(screen.getByTestId("reconciliation-no-result-10")).toBeInTheDocument();
    expect(screen.getByTestId("reconciliation-no-result-10")).toHaveTextContent("Atleta Uno");
  });

  it("muestra la sección de resultados sin convocar", () => {
    mockUseRaceRoster.mockReturnValue({
      data: ROSTER_WITH_DISCREPANCIES,
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    mockUseAthletes.mockReturnValue({ data: ATHLETES_LIST, isLoading: false });

    wrap(<RosterPanel raceEventId={1} />);
    expect(screen.getByTestId("roster-result-not-called-up")).toBeInTheDocument();
    // atleta 99 no tiene nombre en el roster → se muestra "Atleta #99"
    expect(screen.getByTestId("reconciliation-not-called-up-99")).toHaveTextContent("Atleta #99");
  });

  it("NO muestra el banner cuando no hay discrepancias", () => {
    happyRoster();
    wrap(<RosterPanel raceEventId={1} />);
    expect(
      screen.queryByTestId("roster-reconciliation-banner"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Modo solo lectura
// ---------------------------------------------------------------------------

describe("RosterPanel — modo isReadOnly", () => {
  it("oculta el picker de atletas en modo solo lectura", () => {
    happyRoster();
    wrap(<RosterPanel raceEventId={1} isReadOnly />);
    expect(screen.queryByTestId("roster-add-picker")).not.toBeInTheDocument();
  });

  it("oculta los botones de eliminar en modo solo lectura", () => {
    happyRoster();
    wrap(<RosterPanel raceEventId={1} isReadOnly />);
    expect(screen.queryByTestId("roster-delete-btn-1")).not.toBeInTheDocument();
  });

  it("muestra badges de estado (no selects) en modo solo lectura", () => {
    happyRoster();
    wrap(<RosterPanel raceEventId={1} isReadOnly />);
    // No hay ningún select de estado
    expect(screen.queryByTestId("roster-status-select-1")).not.toBeInTheDocument();
  });

  it("sigue mostrando el banner de reconciliación en modo solo lectura", () => {
    mockUseRaceRoster.mockReturnValue({
      data: ROSTER_WITH_DISCREPANCIES,
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    mockUseAthletes.mockReturnValue({ data: ATHLETES_LIST, isLoading: false });

    wrap(<RosterPanel raceEventId={1} isReadOnly />);
    expect(screen.getByTestId("roster-reconciliation-banner")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Privacidad (T029) — Padre ve solo su propio hijo
// ---------------------------------------------------------------------------

describe("RosterPanel — privacidad (vista padre)", () => {
  const MY_ATHLETE_ID = 55;
  const MY_ATHLETE_NAME = "Mi Hijo Uno";
  const OTHER_ATHLETE_NAME = "Otro Menor Ajeno";

  const PARENT_VIEW_ROSTER: RaceRosterResponse = {
    race_event_id: 1,
    entries: [
      // El backend ya filtró; solo viene el hijo del padre
      { id: 5, athlete_id: MY_ATHLETE_ID, athlete_name: MY_ATHLETE_NAME, status: "confirmed", note: null },
    ],
    reconciliation: { called_up_no_result: [], result_not_called_up: [] },
  };

  it("solo muestra el nombre del propio hijo (no datos de otros menores)", () => {
    mockUseRaceRoster.mockReturnValue({
      data: PARENT_VIEW_ROSTER,
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    mockUseAthletes.mockReturnValue({ data: { items: [], total: 0 }, isLoading: false });

    wrap(<RosterPanel raceEventId={1} isReadOnly />);

    // Nombre propio visible
    expect(screen.getByText(MY_ATHLETE_NAME)).toBeInTheDocument();
    // Nombre de otro menor ausente del DOM
    expect(screen.queryByText(OTHER_ATHLETE_NAME)).not.toBeInTheDocument();
  });

  it("no expone controles de escritura a padres (isReadOnly)", () => {
    mockUseRaceRoster.mockReturnValue({
      data: PARENT_VIEW_ROSTER,
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    mockUseAthletes.mockReturnValue({ data: { items: [], total: 0 }, isLoading: false });

    wrap(<RosterPanel raceEventId={1} isReadOnly />);

    expect(screen.queryByTestId("roster-add-picker")).not.toBeInTheDocument();
    expect(screen.queryByTestId(`roster-delete-btn-5`)).not.toBeInTheDocument();
    expect(screen.queryByTestId(`roster-status-select-5`)).not.toBeInTheDocument();
  });

  it("axe 0 violaciones en vista padre (isReadOnly)", async () => {
    mockUseRaceRoster.mockReturnValue({
      data: PARENT_VIEW_ROSTER,
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    mockUseAthletes.mockReturnValue({ data: { items: [], total: 0 }, isLoading: false });

    const { container } = wrap(
      <RosterPanel raceEventId={1} isReadOnly />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Accesibilidad
// ---------------------------------------------------------------------------

describe("RosterPanel — accesibilidad", () => {
  it("axe 0 violaciones — estado con datos (coach)", async () => {
    happyRoster();
    const { container } = wrap(<RosterPanel raceEventId={1} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("axe 0 violaciones — estado vacío", async () => {
    mockUseRaceRoster.mockReturnValue({
      data: ROSTER_EMPTY,
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    mockUseAthletes.mockReturnValue({ data: ATHLETES_LIST, isLoading: false });

    const { container } = wrap(<RosterPanel raceEventId={1} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("axe 0 violaciones — con reconciliación", async () => {
    mockUseRaceRoster.mockReturnValue({
      data: ROSTER_WITH_DISCREPANCIES,
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    mockUseAthletes.mockReturnValue({ data: ATHLETES_LIST, isLoading: false });

    const { container } = wrap(<RosterPanel raceEventId={1} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
