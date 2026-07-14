/**
 * Tests para CatalogGrid (US1 / T014):
 *   - Estado loading → skeletons con role="status" + aria-busy.
 *   - Estado error genérico → mensaje en role="alert".
 *   - Estado error timeout/network → copy "servidor iniciando".
 *   - Estado vacío con hasActiveFilters=false → "El catálogo está vacío".
 *   - Estado vacío con hasActiveFilters=true → "Sin resultados para estos filtros".
 *   - Estado success → grid con tarjetas de ejercicios.
 *   - onEdit undefined → no renderiza botón de edición.
 *   - onEdit definido → renderiza botón de edición por tarjeta.
 *   - isFetching + !isLoading → muestra "Actualizando…".
 *   - a11y: jest-axe sin violaciones en todos los estados principales.
 */
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { CatalogGrid } from "../CatalogGrid";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { makeExerciseListItem } from "@/test/msw/techniqueHandlers";
import type { ExerciseListItem } from "@/types/technique.types";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const EXERCISES: ExerciseListItem[] = [
  makeExerciseListItem({ id: 1, name: "Slalom con conos" }),
  makeExerciseListItem({
    id: 2,
    slug: "gymkhana-basica",
    name: "Gymkhana básica",
    difficulty: "media",
    is_gymkhana: true,
    age_bands: ["13-15"],
  }),
];

// ---------------------------------------------------------------------------
// Default props
// ---------------------------------------------------------------------------

const BASE_PROPS = {
  items: EXERCISES,
  total: EXERCISES.length,
  isLoading: false,
  isFetching: false,
  isError: false,
  error: null,
  hasActiveFilters: false,
} as const;

function renderGrid(overrides: Partial<Parameters<typeof CatalogGrid>[0]> = {}) {
  return renderWithProviders(
    <CatalogGrid {...BASE_PROPS} {...overrides} />,
  );
}

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe("CatalogGrid — estado de carga", () => {
  it("muestra skeletons con role=status y aria-busy cuando isLoading=true", () => {
    renderGrid({ isLoading: true, items: undefined, total: undefined });

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(status).toHaveAttribute("aria-label", "Cargando catálogo de ejercicios…");
  });

  it("no renderiza tarjetas de ejercicios durante la carga", () => {
    renderGrid({ isLoading: true, items: undefined, total: undefined });

    expect(screen.queryByText("Slalom con conos")).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad en el estado de carga", async () => {
    const { container } = renderGrid({
      isLoading: true,
      items: undefined,
      total: undefined,
    });
    expect(await axe(container)).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Error state
// ---------------------------------------------------------------------------

describe("CatalogGrid — estado de error", () => {
  it("muestra role=alert con mensaje genérico en error desconocido", () => {
    renderGrid({
      isError: true,
      error: new Error("Algo salió mal"),
      items: undefined,
      total: undefined,
    });

    const alert = screen.getByRole("alert");
    expect(alert).toBeInTheDocument();
    expect(alert).toHaveTextContent("No se pudo cargar el catálogo. Intenta de nuevo.");
  });

  it("muestra copy de servidor iniciando cuando el error contiene 'timeout'", () => {
    renderGrid({
      isError: true,
      error: new Error("timeout: request exceeded 30s"),
      items: undefined,
      total: undefined,
    });

    // Cold-start errors render as role="status" (reassuring tone), not
    // role="alert" — shared `ErrorState` contract (feature 033 / T041).
    expect(screen.getByRole("status")).toHaveTextContent(
      "El servidor está iniciando",
    );
  });

  it("muestra copy de servidor iniciando cuando el error contiene 'network'", () => {
    renderGrid({
      isError: true,
      error: new Error("Network Error"),
      items: undefined,
      total: undefined,
    });

    expect(screen.getByRole("status")).toHaveTextContent(
      "El servidor está iniciando",
    );
  });

  it("muestra copy de servidor iniciando para errores 503", () => {
    renderGrid({
      isError: true,
      error: new Error("Request failed with status code 503"),
      items: undefined,
      total: undefined,
    });

    expect(screen.getByRole("status")).toHaveTextContent(
      "El servidor está iniciando",
    );
  });

  it("no tiene violaciones de accesibilidad en el estado de error", async () => {
    const { container } = renderGrid({
      isError: true,
      error: new Error("Error genérico"),
      items: undefined,
      total: undefined,
    });
    expect(await axe(container)).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

describe("CatalogGrid — estado vacío", () => {
  it("muestra 'El catálogo está vacío' cuando no hay filtros activos", () => {
    renderGrid({ items: [], total: 0, hasActiveFilters: false });

    expect(screen.getByText("El catálogo está vacío")).toBeInTheDocument();
    expect(
      screen.getByText("Aún no hay ejercicios registrados en esta biblioteca."),
    ).toBeInTheDocument();
  });

  it("muestra 'Sin resultados para estos filtros' cuando hay filtros activos", () => {
    renderGrid({ items: [], total: 0, hasActiveFilters: true });

    expect(screen.getByText("Sin resultados para estos filtros")).toBeInTheDocument();
    expect(
      screen.getByText("Ajusta o limpia los filtros para ver más ejercicios."),
    ).toBeInTheDocument();
  });

  it("no muestra el texto del catálogo vacío cuando hay filtros activos", () => {
    renderGrid({ items: [], total: 0, hasActiveFilters: true });

    expect(screen.queryByText("El catálogo está vacío")).not.toBeInTheDocument();
  });

  it("no muestra 'Sin resultados' cuando no hay filtros activos", () => {
    renderGrid({ items: [], total: 0, hasActiveFilters: false });

    expect(
      screen.queryByText("Sin resultados para estos filtros"),
    ).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad con catálogo vacío sin filtros", async () => {
    const { container } = renderGrid({
      items: [],
      total: 0,
      hasActiveFilters: false,
    });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de accesibilidad con catálogo vacío con filtros activos", async () => {
    const { container } = renderGrid({
      items: [],
      total: 0,
      hasActiveFilters: true,
    });
    expect(await axe(container)).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Success state
// ---------------------------------------------------------------------------

describe("CatalogGrid — estado exitoso", () => {
  it("renderiza todos los ejercicios recibidos", () => {
    renderGrid();

    expect(screen.getByText("Slalom con conos")).toBeInTheDocument();
    expect(screen.getByText("Gymkhana básica")).toBeInTheDocument();
  });

  it("muestra el total de ejercicios", () => {
    renderGrid();

    expect(screen.getByText(/2 ejercicios/)).toBeInTheDocument();
  });

  it("muestra 'Actualizando…' cuando isFetching=true y no está en loading inicial", () => {
    renderGrid({ isFetching: true });

    expect(screen.getByText(/Actualizando…/)).toBeInTheDocument();
  });

  it("no muestra 'Actualizando…' cuando isFetching=false", () => {
    renderGrid({ isFetching: false });

    expect(screen.queryByText(/Actualizando…/)).not.toBeInTheDocument();
  });

  it("no renderiza botones de edición cuando onEdit no está definido", () => {
    renderGrid({ onEdit: undefined });

    expect(
      screen.queryByRole("button", { name: /Editar ejercicio/ }),
    ).not.toBeInTheDocument();
  });

  it("renderiza un botón de edición por tarjeta cuando onEdit está definido", () => {
    const onEdit = vi.fn();
    renderGrid({ onEdit });

    const editButtons = screen.getAllByRole("button", { name: /Editar ejercicio/ });
    expect(editButtons).toHaveLength(EXERCISES.length);
  });

  it("llama a onEdit con el ejercicio correcto al hacer clic en editar", async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    renderGrid({ onEdit });

    const editButtons = screen.getAllByRole("button", { name: /Editar ejercicio/ });
    await user.click(editButtons[0]);

    expect(onEdit).toHaveBeenCalledOnce();
    expect(onEdit).toHaveBeenCalledWith(
      expect.objectContaining({ id: 1, name: "Slalom con conos" }),
    );
  });

  it("no tiene violaciones de accesibilidad en el estado exitoso sin onEdit", async () => {
    const { container } = renderGrid({ onEdit: undefined });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de accesibilidad en el estado exitoso con onEdit", async () => {
    const { container } = renderGrid({ onEdit: vi.fn() });
    expect(await axe(container)).toHaveNoViolations();
  });
});
