/**
 * Tests de CompareView (feature 045, T039) — vista «Comparar», solo coach.
 *
 * Distribución y comparador se mockean (tienen sus propios specs); aquí se
 * prueba la composición de la vista y su a11y.
 */
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { axe } from "jest-axe";

vi.mock("@/components/athletes/ai/DistributionChart", () => ({
  DistributionChart: ({ athleteId }: { athleteId: number }) => (
    <div data-testid="mock-distribution-chart">distribution-{athleteId}</div>
  ),
}));
vi.mock("@/components/athletes/ai/ComparatorPanel", () => ({
  ComparatorPanel: ({ athleteId }: { athleteId: number }) => (
    <div data-testid="mock-comparator-panel">comparator-{athleteId}</div>
  ),
}));

import { CompareView } from "@/components/athletes/races/CompareView";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";

describe("CompareView", () => {
  it("compone la distribución y el comparador del mismo atleta, en línea (sin Sheet ni botón intermedio)", () => {
    renderWithProviders(<CompareView athleteId={42} />);

    expect(screen.getByTestId("mock-distribution-chart")).toHaveTextContent("distribution-42");
    expect(screen.getByTestId("mock-comparator-panel")).toHaveTextContent("comparator-42");
    expect(screen.queryByTestId("open-comparator-sheet")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("cada bloque tiene un encabezado que lo nombra", () => {
    renderWithProviders(<CompareView athleteId={42} />);

    expect(
      screen.getByRole("region", { name: /distribución del campo/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: /comparador de progreso/i }),
    ).toBeInTheDocument();
  });

  it("no tiene violaciones jest-axe", async () => {
    const { container } = renderWithProviders(<CompareView athleteId={42} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
