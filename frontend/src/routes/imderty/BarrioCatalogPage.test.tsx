/**
 * Tests de BarrioCatalogPage (feature 047, US2, T037).
 *
 * Cubre: el filtro de estado, el alta con la hoja compartida, la edición en
 * línea de la tabla (≥768 px) y el manejo del 409 de nombre duplicado tanto
 * en la hoja como en la fila. La página en sí no aplica RBAC — el acceso
 * admin-only vive en `ProtectedRoute` (`App.tsx`, ruta `/imderty/barrios`),
 * fuera del alcance de este archivo de componente.
 *
 * `useBarrios`/`useCreateBarrio`/`useUpdateBarrio` se mockean — mismo patrón
 * que `StaffPage.test.tsx` mockeando `useStaff`/`useSetStaffActive`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import type { Barrio } from "@/schemas/imderty";

// Polyfills de jsdom requeridos por Radix Select/Switch (mismo patrón que
// `ArchivedAthletesPage.test.tsx`/`StaffPage.test.tsx`).
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {};
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

const useBarriosMock = vi.fn();
const createMutate = vi.fn();
const createReset = vi.fn();
const updateMutate = vi.fn();
const updateReset = vi.fn();
const createState = { isPending: false };
const updateState = { isPending: false, variables: undefined as { barrioId: number } | undefined };

vi.mock("@/hooks/useImderty", () => ({
  useBarrios: (includeInactive: boolean) => useBarriosMock(includeInactive),
  useCreateBarrio: () => ({ mutate: createMutate, isPending: createState.isPending, reset: createReset }),
  useUpdateBarrio: () => ({
    mutate: updateMutate,
    isPending: updateState.isPending,
    reset: updateReset,
    variables: updateState.variables,
  }),
}));

import { BarrioCatalogPage } from "@/routes/imderty/BarrioCatalogPage";

function makeBarrio(overrides?: Partial<Barrio>): Barrio {
  return { id: 1, name: "Bello Horizonte", zone: "1", is_active: true, ...overrides };
}

function renderPage() {
  return render(<BarrioCatalogPage />);
}

beforeEach(() => {
  vi.clearAllMocks();
  createState.isPending = false;
  updateState.isPending = false;
  updateState.variables = undefined;
  useBarriosMock.mockReturnValue({
    data: [makeBarrio(), makeBarrio({ id: 2, name: "La Dolores", zone: "ZONA NORTE", is_active: false })],
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  });
});

// ---------------------------------------------------------------------------
// Filtro de estado
// ---------------------------------------------------------------------------

describe("BarrioCatalogPage — filtro de estado", () => {
  it("muestra todos los barrios por defecto", () => {
    renderPage();
    expect(screen.getAllByText("Bello Horizonte").length).toBeGreaterThan(0);
    expect(screen.getAllByText("La Dolores").length).toBeGreaterThan(0);
  });

  it("filtrar por Activos oculta los inactivos", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByTestId("barrio-state-filter"));
    await user.click(await screen.findByRole("option", { name: "Activos" }));

    expect(screen.getAllByText("Bello Horizonte").length).toBeGreaterThan(0);
    expect(screen.queryByText("La Dolores")).not.toBeInTheDocument();
  });

  it("estado vacío por filtro: 'No hay barrios con ese estado.'", async () => {
    useBarriosMock.mockReturnValue({
      data: [makeBarrio({ is_active: true })],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByTestId("barrio-state-filter"));
    await user.click(await screen.findByRole("option", { name: "Inactivos" }));

    expect(await screen.findByText("No hay barrios con ese estado.")).toBeInTheDocument();
  });

  it("estado vacío sin filtrar: 'Aún no hay barrios en el catálogo.'", () => {
    useBarriosMock.mockReturnValue({ data: [], isLoading: false, isError: false, refetch: vi.fn() });
    renderPage();
    expect(screen.getByText("Aún no hay barrios en el catálogo.")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Alta — hoja compartida
// ---------------------------------------------------------------------------

describe("BarrioCatalogPage — agregar barrio", () => {
  it("abre la hoja y valida el nombre requerido", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByTestId("barrio-add-button"));
    expect(await screen.findByTestId("barrio-form-sheet")).toBeInTheDocument();

    await user.click(screen.getByTestId("barrio-form-submit"));

    expect(await screen.findByText("Ingresa el nombre del barrio")).toBeInTheDocument();
    expect(createMutate).not.toHaveBeenCalled();
  });

  it("envía el payload esperado al guardar", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByTestId("barrio-add-button"));
    await screen.findByTestId("barrio-form-sheet");

    await user.type(screen.getByLabelText("Nombre"), "  Nuevo Barrio  ");
    await user.click(screen.getByTestId("barrio-form-submit"));

    await waitFor(() => expect(createMutate).toHaveBeenCalledTimes(1));
    const [payload] = createMutate.mock.calls[0] as [
      { name: string; zone: string; is_active: boolean },
      unknown,
    ];
    expect(payload).toEqual({ name: "Nuevo Barrio", zone: "1", is_active: true });
  });

  it("409 de nombre duplicado se muestra inline en el campo Nombre, sin toast", async () => {
    createMutate.mockImplementation((_payload, opts) => {
      opts.onError({ response: { status: 409 } });
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByTestId("barrio-add-button"));
    await screen.findByTestId("barrio-form-sheet");
    await user.type(screen.getByLabelText("Nombre"), "Bello Horizonte");
    await user.click(screen.getByTestId("barrio-form-submit"));

    expect(await screen.findByText("Ya existe un barrio con ese nombre.")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Edición en línea (tabla desktop)
// ---------------------------------------------------------------------------

describe("BarrioCatalogPage — edición en línea", () => {
  it("editar, cambiar nombre y guardar dispara la mutación con el nuevo valor", async () => {
    const user = userEvent.setup();
    renderPage();

    // El mismo data-testid existe en la tarjeta móvil (abre la hoja) y en la
    // fila de tabla desktop (edición en línea) — se toma la segunda
    // coincidencia para ejercitar el flujo de tabla.
    const editButtons = await screen.findAllByTestId("barrio-edit-1");
    await user.click(editButtons[editButtons.length - 1]);

    const nameInput = screen.getByTestId("barrio-edit-name-1");
    await user.clear(nameInput);
    await user.type(nameInput, "Bello Horizonte Renombrado");
    await user.click(screen.getByTestId("barrio-save-1"));

    await waitFor(() => expect(updateMutate).toHaveBeenCalledTimes(1));
    const [vars] = updateMutate.mock.calls[0] as [{ barrioId: number; payload: unknown }, unknown];
    expect(vars).toEqual({ barrioId: 1, payload: { name: "Bello Horizonte Renombrado", zone: "1" } });
  });

  it("nombre vacío bloquea el guardado con un error inline, sin llamar la mutación", async () => {
    const user = userEvent.setup();
    renderPage();

    const editButtons = await screen.findAllByTestId("barrio-edit-1");
    await user.click(editButtons[editButtons.length - 1]);

    const nameInput = screen.getByTestId("barrio-edit-name-1");
    await user.clear(nameInput);
    await user.click(screen.getByTestId("barrio-save-1"));

    expect(await screen.findByText("Ingresa el nombre del barrio")).toBeInTheDocument();
    expect(updateMutate).not.toHaveBeenCalled();
  });

  it("409 de nombre duplicado se muestra en la fila que se editaba, no como toast", async () => {
    updateMutate.mockImplementation((_vars, opts) => {
      opts?.onError?.({ response: { status: 409 } });
    });
    const user = userEvent.setup();
    renderPage();

    const editButtons = await screen.findAllByTestId("barrio-edit-1");
    await user.click(editButtons[editButtons.length - 1]);
    await user.click(screen.getByTestId("barrio-save-1"));

    expect(await screen.findByText("Ya existe un barrio con ese nombre.")).toBeInTheDocument();
  });

  it("cancelar sale de la edición sin llamar la mutación", async () => {
    const user = userEvent.setup();
    renderPage();

    const editButtons = await screen.findAllByTestId("barrio-edit-1");
    await user.click(editButtons[editButtons.length - 1]);
    await screen.findByTestId("barrio-edit-name-1");

    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByTestId("barrio-edit-name-1")).not.toBeInTheDocument();
    expect(updateMutate).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Activar / desactivar directo
// ---------------------------------------------------------------------------

describe("BarrioCatalogPage — activar/desactivar", () => {
  it("el botón de la fila dispara la mutación con is_active invertido", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByTestId("barrio-toggle-active-1"));

    await waitFor(() => expect(updateMutate).toHaveBeenCalledTimes(1));
    expect(updateMutate).toHaveBeenCalledWith({ barrioId: 1, payload: { is_active: false } });
  });
});

// ---------------------------------------------------------------------------
// Accesibilidad
// ---------------------------------------------------------------------------

describe("BarrioCatalogPage — accesibilidad", () => {
  it("0 violaciones jest-axe en la vista de catálogo", async () => {
    const { container } = renderPage();
    await screen.findByTestId("barrio-catalog-page");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("0 violaciones jest-axe con la hoja de alta abierta", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByTestId("barrio-add-button"));
    await screen.findByTestId("barrio-form-sheet");

    const results = await axe(document.body);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
