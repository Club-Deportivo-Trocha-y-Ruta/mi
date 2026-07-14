/**
 * CatalogGrid — shared component coverage (feature 033 / T043).
 *
 * Generic tests over the T040-extracted `CatalogGrid<T>` itself (domain
 * agnostic — uses a throwaway `FakeItem` shape), covering the four states
 * it owns: loading skeletons, error (generic + cold-start via
 * `isColdStartError`), empty, and success (grid + total/fetching copy +
 * `renderCard`/`getItemKey` contract). técnica/fuerza's own wrapper tests
 * (`components/technique/__tests__/CatalogGrid.test.tsx`,
 * `components/strength/__tests__/CatalogPage.test.tsx`) already cover the
 * domain-specific copy through this same shell — this file is the
 * shell's own contract, independent of either domain.
 */
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CatalogGrid } from "../CatalogGrid";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";

interface FakeItem {
  id: number;
  label: string;
}

const ITEMS: FakeItem[] = [
  { id: 1, label: "Primer elemento" },
  { id: 2, label: "Segundo elemento" },
];

const BASE_PROPS = {
  items: ITEMS,
  total: ITEMS.length,
  isLoading: false,
  isFetching: false,
  isError: false,
  error: null,
  renderCard: (item: FakeItem) => <div data-testid={`card-${item.id}`}>{item.label}</div>,
  getItemKey: (item: FakeItem) => item.id,
  emptyState: { title: "Vacío", description: "Nada por aquí" },
} as const;

function renderGrid(overrides: Partial<Parameters<typeof CatalogGrid<FakeItem>>[0]> = {}) {
  return renderWithProviders(<CatalogGrid<FakeItem> {...BASE_PROPS} {...overrides} />);
}

describe("CatalogGrid (shared) — estado de carga", () => {
  it("muestra skeletons con role=status, aria-busy y el label por defecto", () => {
    renderGrid({ isLoading: true, items: undefined, total: undefined });

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(status).toHaveAttribute("aria-label", "Cargando catálogo de ejercicios…");
  });

  it("respeta un loadingLabel personalizado", () => {
    renderGrid({
      isLoading: true,
      items: undefined,
      total: undefined,
      loadingLabel: "Cargando catálogo de fuerza…",
    });

    expect(screen.getByRole("status")).toHaveAttribute("aria-label", "Cargando catálogo de fuerza…");
  });

  it("respeta un skeletonCount personalizado", () => {
    const { container } = renderGrid({
      isLoading: true,
      items: undefined,
      total: undefined,
      skeletonCount: 3,
    });

    // Each skeleton card renders its own <Skeleton> pieces; count the
    // top-level skeleton wrapper divs instead of relying on internals.
    const status = screen.getByRole("status");
    expect(container.querySelectorAll('[role="status"] > div')).toHaveLength(3);
    expect(status).toBeInTheDocument();
  });

  it("no renderiza tarjetas durante la carga", () => {
    renderGrid({ isLoading: true, items: undefined, total: undefined });

    expect(screen.queryByText("Primer elemento")).not.toBeInTheDocument();
  });
});

describe("CatalogGrid (shared) — estado de error", () => {
  it("renderiza role=alert con el errorMessage provisto para errores genéricos", () => {
    renderGrid({
      isError: true,
      error: new Error("boom"),
      items: undefined,
      total: undefined,
      errorMessage: "No se pudo cargar el catálogo compartido.",
    });

    expect(screen.getByRole("alert")).toHaveTextContent("No se pudo cargar el catálogo compartido.");
  });

  it("detecta cold-start (timeout/network/503) vía isColdStartError y cambia a role=status", () => {
    renderGrid({
      isError: true,
      error: new Error("Network Error"),
      items: undefined,
      total: undefined,
      errorMessage: "genérico",
    });

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("invoca onRetry al hacer clic en 'Reintentar'", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    renderGrid({
      isError: true,
      error: new Error("boom"),
      items: undefined,
      total: undefined,
      onRetry,
    });

    await user.click(screen.getByRole("button", { name: /Reintentar/i }));

    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("CatalogGrid (shared) — estado vacío", () => {
  it("usa el emptyState.title/description provisto por el llamador cuando items está vacío", () => {
    renderGrid({ items: [], total: 0 });

    expect(screen.getByText("Vacío")).toBeInTheDocument();
    expect(screen.getByText("Nada por aquí")).toBeInTheDocument();
  });

  it("usa el emptyState cuando items es undefined", () => {
    renderGrid({ items: undefined, total: undefined });

    expect(screen.getByText("Vacío")).toBeInTheDocument();
  });
});

describe("CatalogGrid (shared) — estado exitoso", () => {
  it("renderiza cada item vía renderCard, usando getItemKey para la key", () => {
    renderGrid();

    expect(screen.getByTestId("card-1")).toHaveTextContent("Primer elemento");
    expect(screen.getByTestId("card-2")).toHaveTextContent("Segundo elemento");
  });

  it("muestra el total por defecto ('N ejercicios')", () => {
    renderGrid();

    expect(screen.getByText("2 ejercicios")).toBeInTheDocument();
  });

  it("respeta un totalLabel personalizado", () => {
    renderGrid({ totalLabel: (t) => `${t} resultados compartidos` });

    expect(screen.getByText("2 resultados compartidos")).toBeInTheDocument();
  });

  it("respeta un gridAriaLabel personalizado", () => {
    renderGrid({ gridAriaLabel: (count) => `Grid compartido: ${count}` });

    expect(screen.getByLabelText("Grid compartido: 2")).toBeInTheDocument();
  });

  it("muestra 'Actualizando…' cuando isFetching=true y no está en loading inicial", () => {
    renderGrid({ isFetching: true });

    expect(screen.getByText(/Actualizando…/)).toBeInTheDocument();
  });

  it("no muestra 'Actualizando…' cuando isFetching=false", () => {
    renderGrid({ isFetching: false });

    expect(screen.queryByText(/Actualizando…/)).not.toBeInTheDocument();
  });

  it("aplica un gridClassName personalizado al contenedor de la grid", () => {
    const { container } = renderGrid({ gridClassName: "grid gap-2 custom-shared-grid" });

    expect(container.querySelector(".custom-shared-grid")).toBeInTheDocument();
  });
});
