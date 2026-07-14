/**
 * LibraryEntityCard — shared component coverage (feature 033 / T043).
 *
 * Generic tests over the T040-extracted card shell: title link (WCAG
 * 48×48 px touch target — Constitution III), cornerContent, summary,
 * chipGroups (default chip rendering + custom renderChip override), and the
 * bottom-pinned footer slot. técnica/fuerza's `ExerciseCard.tsx` wrappers
 * only map their own domain fields onto these same props.
 */
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { LibraryEntityCard } from "../LibraryEntityCard";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";

describe("LibraryEntityCard (shared)", () => {
  it("renderiza el título como enlace apuntando a href", () => {
    renderWithProviders(<LibraryEntityCard href="/catalog/1" title="Ejercicio de prueba" />);

    const link = screen.getByRole("link", { name: "Ejercicio de prueba" });
    expect(link).toHaveAttribute("href", "/catalog/1");
  });

  it("el enlace del título cumple el mínimo de 48×48 px (min-h-12) — Constitution III", () => {
    renderWithProviders(<LibraryEntityCard href="/catalog/1" title="Ejercicio de prueba" />);

    expect(screen.getByRole("link", { name: "Ejercicio de prueba" })).toHaveClass("min-h-12");
  });

  it("renderiza cornerContent junto al título cuando se provee", () => {
    renderWithProviders(
      <LibraryEntityCard
        href="/catalog/1"
        title="Ejercicio de prueba"
        cornerContent={<span data-testid="corner">Badge</span>}
      />,
    );

    expect(screen.getByTestId("corner")).toBeInTheDocument();
  });

  it("no renderiza el summary cuando se omite", () => {
    renderWithProviders(<LibraryEntityCard href="/catalog/1" title="Ejercicio de prueba" />);

    expect(screen.queryByText(/resumen/i)).not.toBeInTheDocument();
  });

  it("renderiza el summary cuando se provee", () => {
    renderWithProviders(
      <LibraryEntityCard href="/catalog/1" title="Ejercicio de prueba" summary="Un resumen breve" />,
    );

    expect(screen.getByText("Un resumen breve")).toBeInTheDocument();
  });

  it("renderiza chips con el estilo por defecto cuando el grupo no define renderChip", () => {
    renderWithProviders(
      <LibraryEntityCard
        href="/catalog/1"
        title="Ejercicio de prueba"
        chipGroups={[
          {
            ariaLabel: "Etiquetas",
            chips: [{ key: "a", label: "Etiqueta A" }],
          },
        ]}
      />,
    );

    expect(screen.getByText("Etiqueta A")).toBeInTheDocument();
    expect(screen.getByLabelText("Etiquetas")).toBeInTheDocument();
  });

  it("usa el renderChip personalizado del grupo cuando se provee", () => {
    renderWithProviders(
      <LibraryEntityCard
        href="/catalog/1"
        title="Ejercicio de prueba"
        chipGroups={[
          {
            ariaLabel: "Etiquetas",
            chips: [{ key: "a", label: "Etiqueta A" }],
            renderChip: (chip) => (
              <em key={chip.key} data-testid="custom-chip">
                {chip.label}
              </em>
            ),
          },
        ]}
      />,
    );

    expect(screen.getByTestId("custom-chip")).toHaveTextContent("Etiqueta A");
  });

  it("no renderiza un grupo de chips vacío", () => {
    renderWithProviders(
      <LibraryEntityCard
        href="/catalog/1"
        title="Ejercicio de prueba"
        chipGroups={[{ ariaLabel: "Etiquetas vacías", chips: [] }]}
      />,
    );

    expect(screen.queryByLabelText("Etiquetas vacías")).not.toBeInTheDocument();
  });

  it("renderiza el footer cuando se provee, sin renderizarlo cuando se omite", () => {
    const { rerender } = renderWithProviders(
      <LibraryEntityCard href="/catalog/1" title="Ejercicio de prueba" footer={<span>Pie de tarjeta</span>} />,
    );

    expect(screen.getByText("Pie de tarjeta")).toBeInTheDocument();

    rerender(<LibraryEntityCard href="/catalog/1" title="Ejercicio de prueba" />);

    expect(screen.queryByText("Pie de tarjeta")).not.toBeInTheDocument();
  });
});
