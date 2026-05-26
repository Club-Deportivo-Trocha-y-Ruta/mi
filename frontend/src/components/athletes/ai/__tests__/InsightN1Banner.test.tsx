/**
 * Tests para InsightN1Banner (Task #18, copy actualizado en Task #22).
 *
 * Banner informativo que se muestra arriba del summary en el detalle del
 * insight cuando ``is_first_in_season === true``. Refuerza al lector que la
 * lectura es descriptiva y no constituye proyección de tendencia.
 *
 * Decisión Task #22: el banner se condiciona por ``is_first_in_season``
 * (atleta tiene 1 válida en toda la temporada), NO por el tamaño del set
 * lanzado. Copy actualizado a "primera válida de la temporada".
 *
 * Verifica:
 *   - Copy específico por rol (coach vs parent) usando la frase nueva.
 *   - role="note" y data-testid estables.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { InsightN1Banner } from "../InsightN1Banner";

describe("InsightN1Banner", () => {
  it("renderiza copy coach con frase 'primera válida de la temporada' + 'proyección de tendencia'", () => {
    render(<InsightN1Banner mode="coach" />);
    const banner = screen.getByTestId("insight-n1-banner");
    expect(banner).toHaveTextContent(/primera válida de la temporada/i);
    expect(banner).toHaveTextContent(/proyección de tendencia/i);
  });

  it("renderiza copy parent con frase 'primera válida de la temporada' + 'aún es pronto'", () => {
    render(<InsightN1Banner mode="parent" />);
    const banner = screen.getByTestId("insight-n1-banner");
    expect(banner).toHaveTextContent(/primera válida de la temporada/i);
    expect(banner).toHaveTextContent(/aún es pronto/i);
  });

  it("tiene role note y aria limpio", () => {
    render(<InsightN1Banner mode="coach" />);
    expect(screen.getByRole("note")).toBeInTheDocument();
  });
});
