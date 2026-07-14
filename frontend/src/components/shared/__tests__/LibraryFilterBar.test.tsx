/**
 * LibraryFilterBar — shared component coverage (feature 033 / T043).
 *
 * Generic tests over the T040-extracted config-driven filter shell: text /
 * select / multiSelect field types, active-filter serialization, "Limpiar
 * filtros", and loading-skeleton placeholders for async option lists.
 * técnica/fuerza's own `FilterBar.tsx` wrappers (tested in
 * `components/technique/__tests__/FilterBar.test.tsx` and
 * `components/strength/__tests__/FilterBar.test.tsx`) only add field config
 * and domain serialization on top of this shell.
 */
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { LibraryFilterBar, type LibraryFilterField } from "../LibraryFilterBar";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";

const TEXT_FIELD: LibraryFilterField = {
  type: "text",
  name: "q",
  label: "Buscar",
  placeholder: "Nombre…",
};

const SELECT_FIELD: LibraryFilterField = {
  type: "select",
  name: "category",
  label: "Categoría",
  placeholder: "Todas las categorías",
  options: [
    { value: "a", label: "Categoría A" },
    { value: "b", label: "Categoría B" },
  ],
};

const MULTI_SELECT_FIELD: LibraryFilterField = {
  type: "multiSelect",
  name: "tags",
  label: "Etiquetas",
  options: [
    { value: "x", label: "Etiqueta X" },
    { value: "y", label: "Etiqueta Y" },
  ],
};

function renderBar(fields: LibraryFilterField[], onChange = vi.fn()) {
  const utils = renderWithProviders(
    <LibraryFilterBar ariaLabel="Filtros de prueba" fields={fields} onChange={onChange} />,
  );
  return { onChange, ...utils };
}

describe("LibraryFilterBar (shared) — renderizado por tipo de campo", () => {
  it("renderiza un input de texto para un campo 'text'", () => {
    renderBar([TEXT_FIELD]);

    expect(screen.getByLabelText("Buscar")).toBeInTheDocument();
  });

  it("renderiza un <select> con la opción 'Todos/as' al inicio para un campo 'select'", () => {
    renderBar([SELECT_FIELD]);

    const select = screen.getByLabelText("Categoría") as HTMLSelectElement;
    expect(select.options[0]).toHaveTextContent("Todas las categorías");
    expect(select.options[1]).toHaveTextContent("Categoría A");
  });

  it("muestra un skeleton en vez del <select> cuando isLoading=true", () => {
    renderBar([{ ...SELECT_FIELD, isLoading: true } as LibraryFilterField]);

    expect(screen.queryByLabelText("Categoría")).not.toBeInTheDocument();
  });

  it("renderiza pills toggle para un campo 'multiSelect'", () => {
    renderBar([MULTI_SELECT_FIELD]);

    expect(screen.getByRole("group", { name: "Etiquetas" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Etiqueta X" })).toHaveAttribute("aria-pressed", "false");
  });

  it("muestra skeletons de pills cuando el multiSelect está cargando", () => {
    renderBar([{ ...MULTI_SELECT_FIELD, isLoading: true } as LibraryFilterField]);

    expect(screen.queryByRole("group", { name: "Etiquetas" })).not.toBeInTheDocument();
    expect(screen.getByRole("status", { name: /Cargando etiquetas…/i })).toBeInTheDocument();
  });

  it("no renderiza la fila de grid cuando todos los campos son multiSelect", () => {
    renderBar([MULTI_SELECT_FIELD]);

    expect(screen.queryByLabelText("Buscar")).not.toBeInTheDocument();
  });
});

describe("LibraryFilterBar (shared) — serialización de filtros activos", () => {
  it("notifica onChange con el valor de texto recortado", async () => {
    const user = userEvent.setup();
    const { onChange } = renderBar([TEXT_FIELD]);

    await user.type(screen.getByLabelText("Buscar"), "abc");

    expect(onChange).toHaveBeenLastCalledWith({ q: "abc" });
  });

  it("notifica onChange con el valor seleccionado de un 'select'", async () => {
    const user = userEvent.setup();
    const { onChange } = renderBar([SELECT_FIELD]);

    await user.selectOptions(screen.getByLabelText("Categoría"), "b");

    expect(onChange).toHaveBeenLastCalledWith({ category: "b" });
  });

  it("serializa los valores de 'multiSelect' unidos con coma bajo el nombre del campo", async () => {
    const user = userEvent.setup();
    const { onChange } = renderBar([MULTI_SELECT_FIELD]);

    await user.click(screen.getByRole("button", { name: "Etiqueta X" }));
    await user.click(screen.getByRole("button", { name: "Etiqueta Y" }));

    expect(onChange).toHaveBeenLastCalledWith({ tags: "x,y" });
  });

  it("marca aria-pressed=true en una pill de multiSelect activa", async () => {
    const user = userEvent.setup();
    renderBar([MULTI_SELECT_FIELD]);

    const pill = screen.getByRole("button", { name: "Etiqueta X" });
    await user.click(pill);

    expect(pill).toHaveAttribute("aria-pressed", "true");
  });

  it("no incluye campos vacíos en el objeto de filtros activos", async () => {
    const user = userEvent.setup();
    const { onChange } = renderBar([TEXT_FIELD, SELECT_FIELD]);

    await user.selectOptions(screen.getByLabelText("Categoría"), "a");

    expect(onChange).toHaveBeenLastCalledWith({ category: "a" });
  });
});

describe("LibraryFilterBar (shared) — 'Limpiar filtros'", () => {
  it("no muestra el botón 'Limpiar filtros' ni el conteo cuando no hay filtros activos", () => {
    renderBar([TEXT_FIELD]);

    expect(screen.queryByRole("button", { name: "Limpiar filtros" })).not.toBeInTheDocument();
  });

  it("muestra el botón y el conteo de filtros activos cuando hay al menos uno activo", async () => {
    const user = userEvent.setup();
    renderBar([TEXT_FIELD]);

    await user.type(screen.getByLabelText("Buscar"), "abc");

    expect(screen.getByRole("button", { name: "Limpiar filtros" })).toBeInTheDocument();
    expect(screen.getByText("1 filtro activo")).toBeInTheDocument();
  });

  it("pluraliza el conteo cuando hay más de un filtro activo", async () => {
    const user = userEvent.setup();
    renderBar([TEXT_FIELD, SELECT_FIELD]);

    await user.type(screen.getByLabelText("Buscar"), "abc");
    await user.selectOptions(screen.getByLabelText("Categoría"), "a");

    expect(screen.getByText("2 filtros activos")).toBeInTheDocument();
  });

  it("al hacer clic en 'Limpiar filtros' resetea los campos y notifica onChange({})", async () => {
    const user = userEvent.setup();
    const { onChange } = renderBar([TEXT_FIELD]);

    await user.type(screen.getByLabelText("Buscar"), "abc");
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));

    expect(onChange).toHaveBeenLastCalledWith({});
    expect(screen.getByLabelText("Buscar")).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Limpiar filtros" })).not.toBeInTheDocument();
  });
});
