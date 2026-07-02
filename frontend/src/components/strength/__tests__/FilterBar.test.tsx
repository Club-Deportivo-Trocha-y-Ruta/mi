/**
 * Tests para FilterBar del catálogo de Fuerza y Acondicionamiento (US1 / T018):
 *   - Renderiza los controles de filtrado (búsqueda, equipo, edad, categoría).
 *   - Cambiar un campo notifica al padre con el valor correcto.
 *   - Limpiar filtros resetea a {} y oculta el botón de limpieza.
 *   - El contador de filtros activos refleja la cantidad correcta.
 *   - a11y: jest-axe sin violaciones.
 *
 * A diferencia de `components/technique/__tests__/FilterBar.test.tsx`, todos
 * los selects son estáticos (sin fetch a skills/materials) — no se necesita
 * MSW ni `waitFor` para que los controles aparezcan.
 */
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { FilterBar } from "../FilterBar";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderFilterBar(onChange = vi.fn()) {
  return renderWithProviders(<FilterBar onChange={onChange} />);
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------

describe("FilterBar (strength)", () => {
  it("renderiza el campo de búsqueda y los tres selectores estáticos", () => {
    renderFilterBar();

    expect(screen.getByLabelText("Buscar")).toBeInTheDocument();
    expect(screen.getByLabelText("Equipo")).toBeInTheDocument();
    expect(screen.getByLabelText("Franja de edad")).toBeInTheDocument();
    expect(screen.getByLabelText("Categoría de movimiento")).toBeInTheDocument();
  });

  it("equipment select contiene las opciones estáticas", () => {
    renderFilterBar();

    const select = screen.getByLabelText("Equipo") as HTMLSelectElement;
    const labels = Array.from(select.options).map((o) => o.text);
    expect(labels).toContain("Todos los equipos");
    expect(labels).toContain("Sin equipo");
    expect(labels).toContain("Equipo de gimnasio");
  });

  it("age_band select contiene las dos franjas estáticas", () => {
    renderFilterBar();

    const select = screen.getByLabelText("Franja de edad") as HTMLSelectElement;
    const labels = Array.from(select.options).map((o) => o.text);
    expect(labels).toContain("Todas las franjas");
    expect(labels).toContain("10–12 años");
    expect(labels).toContain("13–15 años");
  });

  it("movement_category select contiene las cinco categorías estáticas", () => {
    renderFilterBar();

    const select = screen.getByLabelText(
      "Categoría de movimiento",
    ) as HTMLSelectElement;
    const labels = Array.from(select.options).map((o) => o.text);
    expect(labels).toContain("Todas las categorías");
    expect(labels).toContain("Empuje superior");
    expect(labels).toContain("Tracción superior");
    expect(labels).toContain("Inferior bilateral");
    expect(labels).toContain("Inferior unilateral");
    expect(labels).toContain("Core y estabilidad");
  });

  it("escribir en el campo de búsqueda llama a onChange con q correcto", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderFilterBar(onChange);

    await user.type(screen.getByLabelText("Buscar"), "sentadilla");

    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: "sentadilla" }),
    );
  });

  it("cambiar equipo llama a onChange con equipment correcto", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderFilterBar(onChange);

    await user.selectOptions(screen.getByLabelText("Equipo"), "sin_equipo");

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ equipment: "sin_equipo" }),
    );
  });

  it("cambiar franja de edad llama a onChange con age_band correcto", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderFilterBar(onChange);

    await user.selectOptions(screen.getByLabelText("Franja de edad"), "10-12");

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ age_band: "10-12" }),
    );
  });

  it("cambiar categoría de movimiento llama a onChange con movement_category correcto", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderFilterBar(onChange);

    await user.selectOptions(
      screen.getByLabelText("Categoría de movimiento"),
      "core_estabilidad",
    );

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ movement_category: "core_estabilidad" }),
    );
  });

  it("el botón 'Limpiar filtros' no aparece cuando no hay filtros activos", () => {
    renderFilterBar();

    expect(screen.queryByRole("button", { name: /Limpiar filtros/ })).not.toBeInTheDocument();
  });

  it("el botón 'Limpiar filtros' aparece al activar un filtro y muestra el conteo", async () => {
    const user = userEvent.setup();
    renderFilterBar();

    await user.selectOptions(screen.getByLabelText("Equipo"), "equipo_gym");

    expect(screen.getByRole("button", { name: /Limpiar filtros/ })).toBeInTheDocument();
    expect(screen.getByText(/1 filtro activo/)).toBeInTheDocument();
  });

  it("'Limpiar filtros' llama a onChange con {} y oculta el botón", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderFilterBar(onChange);

    await user.selectOptions(screen.getByLabelText("Equipo"), "equipo_gym");
    expect(screen.getByRole("button", { name: /Limpiar filtros/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Limpiar filtros/ }));

    expect(onChange).toHaveBeenLastCalledWith({});
    expect(screen.queryByRole("button", { name: /Limpiar filtros/ })).not.toBeInTheDocument();
  });

  it("el contador de filtros activos suma búsqueda, selects y categoría correctamente", async () => {
    const user = userEvent.setup();
    renderFilterBar();

    await user.selectOptions(screen.getByLabelText("Equipo"), "sin_equipo");
    await user.selectOptions(screen.getByLabelText("Franja de edad"), "13-15");
    await user.selectOptions(
      screen.getByLabelText("Categoría de movimiento"),
      "empuje_superior",
    );

    expect(screen.getByText(/3 filtros activos/)).toBeInTheDocument();
  });

  it("la sección tiene el aria-label correcto para lectores de pantalla", () => {
    renderFilterBar();

    expect(
      screen.getByRole("region", { name: "Filtros del catálogo de fuerza" }),
    ).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad sin filtros activos", async () => {
    const { container } = renderFilterBar();

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de accesibilidad con un filtro activo", async () => {
    const user = userEvent.setup();
    const { container } = renderFilterBar();

    await user.selectOptions(screen.getByLabelText("Equipo"), "equipo_gym");

    expect(await axe(container)).toHaveNoViolations();
  });
});
