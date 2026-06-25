/**
 * Tests para FilterBar (US1 / T013):
 *   - Renderiza controles de filtrado (habilidad, edad, dificultad, materiales).
 *   - Aplicar un filtro de select notifica al padre con el valor correcto.
 *   - Activar un material badge lo marca como aria-pressed y llama onChange.
 *   - Limpiar filtros resetea a {} y oculta el botón de limpieza.
 *   - El contador de filtros activos refleja la cantidad correcta.
 *   - a11y: jest-axe sin violaciones (incluyendo carga de materiales y skeletons).
 *
 * Estrategia de mock: MSW via mswServer (setup.ts) + overrideHandlers en suite.
 * Los hooks useSkills y useMaterials se resuelven via MSW — no se hace vi.mock
 * sobre los hooks para mantenerse cerca del comportamiento real.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { FilterBar } from "../FilterBar";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { mswServer } from "@/test/setup";
import { techniqueHandlers } from "@/test/msw/techniqueHandlers";

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

describe("FilterBar", () => {
  beforeEach(() => {
    // Register technique handlers for each test (skills + materials endpoints).
    mswServer.use(...techniqueHandlers);
  });

  it("renderiza los tres selectores y la sección de materiales", async () => {
    renderFilterBar();

    // Age and difficulty selects are present immediately (static, no async data)
    expect(screen.getByLabelText("Franja de edad")).toBeInTheDocument();
    expect(screen.getByLabelText("Dificultad")).toBeInTheDocument();

    // Habilidad select: rendered only once skills load (skeleton replaces it while loading)
    await waitFor(() => {
      expect(screen.getByLabelText("Habilidad")).toBeInTheDocument();
    });

    // Materiales: skeleton while loading → buttons once resolved
    await waitFor(() => {
      expect(screen.getByRole("group", { name: "Filtrar por material" })).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Conos" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sin material" })).toBeInTheDocument();
  });

  it("skill select muestra las opciones cargadas desde la API", async () => {
    renderFilterBar();

    await waitFor(() => {
      // Wait for the skill select to be populated (skeleton removed)
      const select = screen.getByLabelText("Habilidad") as HTMLSelectElement;
      expect(select.options.length).toBeGreaterThan(1);
    });

    const skillSelect = screen.getByLabelText("Habilidad") as HTMLSelectElement;
    const optionValues = Array.from(skillSelect.options).map((o) => o.value);
    expect(optionValues).toContain("equilibrio");
    expect(optionValues).toContain("frenada");
  });

  it("age_band select contiene las tres franjas estáticas", async () => {
    renderFilterBar();

    const ageSelect = screen.getByLabelText("Franja de edad") as HTMLSelectElement;
    const labels = Array.from(ageSelect.options).map((o) => o.text);
    expect(labels).toContain("Todas las franjas");
    expect(labels).toContain("7–9 años");
    expect(labels).toContain("10–12 años");
    expect(labels).toContain("13–15 años");
  });

  it("difficulty select contiene las tres opciones estáticas", () => {
    renderFilterBar();

    const diffSelect = screen.getByLabelText("Dificultad") as HTMLSelectElement;
    const labels = Array.from(diffSelect.options).map((o) => o.text);
    expect(labels).toContain("Todas las dificultades");
    expect(labels).toContain("Fácil");
    expect(labels).toContain("Media");
    expect(labels).toContain("Avanzada");
  });

  it("cambiar franja de edad llama a onChange con age_band correcto", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderFilterBar(onChange);

    const ageSelect = screen.getByLabelText("Franja de edad");
    await user.selectOptions(ageSelect, "10-12");

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ age_band: "10-12" }),
    );
  });

  it("cambiar dificultad llama a onChange con difficulty correcto", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderFilterBar(onChange);

    const diffSelect = screen.getByLabelText("Dificultad");
    await user.selectOptions(diffSelect, "avanzada");

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ difficulty: "avanzada" }),
    );
  });

  it("cambiar habilidad llama a onChange con skill correcto", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderFilterBar(onChange);

    // Wait for skill select to be populated
    await waitFor(() => {
      const select = screen.getByLabelText("Habilidad") as HTMLSelectElement;
      expect(select.options.length).toBeGreaterThan(1);
    });

    const skillSelect = screen.getByLabelText("Habilidad");
    await user.selectOptions(skillSelect, "equilibrio");

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ skill: "equilibrio" }),
    );
  });

  it("activar un badge de material lo marca como aria-pressed=true y llama onChange", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderFilterBar(onChange);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Conos" })).toBeInTheDocument(),
    );

    const conosBtn = screen.getByRole("button", { name: "Conos" });
    expect(conosBtn).toHaveAttribute("aria-pressed", "false");

    await user.click(conosBtn);

    expect(conosBtn).toHaveAttribute("aria-pressed", "true");
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ materials: "conos" }),
    );
  });

  it("desactivar un badge de material lo desmarca y llama onChange sin ese material", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderFilterBar(onChange);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Conos" })).toBeInTheDocument(),
    );

    const conosBtn = screen.getByRole("button", { name: "Conos" });

    // Activate
    await user.click(conosBtn);
    expect(conosBtn).toHaveAttribute("aria-pressed", "true");

    // Deactivate
    await user.click(conosBtn);
    expect(conosBtn).toHaveAttribute("aria-pressed", "false");

    const lastCall = onChange.mock.calls.at(-1)?.[0];
    expect(lastCall?.materials).toBeUndefined();
  });

  it("el botón 'Limpiar filtros' no aparece cuando no hay filtros activos", async () => {
    renderFilterBar();

    // Wait for materials to load so the component is fully rendered
    await waitFor(() =>
      expect(screen.getByRole("group", { name: "Filtrar por material" })).toBeInTheDocument(),
    );

    expect(screen.queryByRole("button", { name: /Limpiar filtros/ })).not.toBeInTheDocument();
  });

  it("el botón 'Limpiar filtros' aparece al activar un filtro y muestra el conteo", async () => {
    const user = userEvent.setup();
    renderFilterBar();

    await waitFor(() =>
      expect(screen.getByRole("group", { name: "Filtrar por material" })).toBeInTheDocument(),
    );

    await user.selectOptions(screen.getByLabelText("Dificultad"), "media");

    expect(screen.getByRole("button", { name: /Limpiar filtros/ })).toBeInTheDocument();
    expect(screen.getByText(/1 filtro activo/)).toBeInTheDocument();
  });

  it("'Limpiar filtros' llama a onChange con {} y oculta el botón", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderFilterBar(onChange);

    await waitFor(() =>
      expect(screen.getByRole("group", { name: "Filtrar por material" })).toBeInTheDocument(),
    );

    // Apply a filter
    await user.selectOptions(screen.getByLabelText("Dificultad"), "media");
    expect(screen.getByRole("button", { name: /Limpiar filtros/ })).toBeInTheDocument();

    // Clear
    await user.click(screen.getByRole("button", { name: /Limpiar filtros/ }));

    expect(onChange).toHaveBeenLastCalledWith({});
    expect(screen.queryByRole("button", { name: /Limpiar filtros/ })).not.toBeInTheDocument();
  });

  it("el contador de filtros activos suma selects y materiales correctamente", async () => {
    const user = userEvent.setup();
    renderFilterBar();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Conos" })).toBeInTheDocument(),
    );

    // 2 selects + 1 material = 3 activos
    await user.selectOptions(screen.getByLabelText("Franja de edad"), "10-12");
    await user.selectOptions(screen.getByLabelText("Dificultad"), "facil");
    await user.click(screen.getByRole("button", { name: "Conos" }));

    expect(screen.getByText(/3 filtros activos/)).toBeInTheDocument();
  });

  it("la sección tiene el aria-label correcto para lectores de pantalla", () => {
    renderFilterBar();

    expect(
      screen.getByRole("region", { name: "Filtros del catálogo" }),
    ).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad con filtros cargados", async () => {
    const { container } = renderFilterBar();

    // Wait for async data to load (materials + skills)
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Conos" })).toBeInTheDocument(),
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de accesibilidad con un filtro activo", async () => {
    const user = userEvent.setup();
    const { container } = renderFilterBar();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Conos" })).toBeInTheDocument(),
    );

    await user.selectOptions(screen.getByLabelText("Dificultad"), "avanzada");

    expect(await axe(container)).toHaveNoViolations();
  });
});
