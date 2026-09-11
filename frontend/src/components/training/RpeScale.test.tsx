import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { RpeScale } from "./RpeScale";

describe("RpeScale", () => {
  it("no renderiza ningún input de rango (role=slider)", () => {
    render(<RpeScale value={5} onChange={vi.fn()} />);
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
  });

  it("renderiza como ToggleGroup con 11 opciones discretas (0-10)", () => {
    render(<RpeScale value={5} onChange={vi.fn()} />);
    const group = screen.getByRole("group", { name: "RPE OMNI 0-10" });
    expect(within(group).getAllByRole("radio")).toHaveLength(11);
  });

  it("value=null: ninguna opción está marcada y muestra 'Sin registrar'", () => {
    render(<RpeScale value={null} onChange={vi.fn()} />);
    const group = screen.getByRole("group", { name: "RPE OMNI 0-10" });
    expect(within(group).queryAllByRole("radio", { checked: true })).toHaveLength(0);
    expect(screen.getByText("Sin registrar")).toBeInTheDocument();
  });

  it("muestra la carita y la etiqueta cualitativa del valor seleccionado", () => {
    render(<RpeScale value={7} onChange={vi.fn()} />);
    expect(screen.getByText("7 · Duro")).toBeInTheDocument();
    expect(screen.queryByText("Sin registrar")).not.toBeInTheDocument();
  });

  it("muestra los extremos 'Reposo' y 'Máximo'", () => {
    render(<RpeScale value={5} onChange={vi.fn()} />);
    expect(screen.getByText("Reposo")).toBeInTheDocument();
    expect(screen.getByText("Máximo")).toBeInTheDocument();
  });

  it("clickear una opción llama a onChange con el número seleccionado", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<RpeScale value={5} onChange={onChange} />);

    const group = screen.getByRole("group", { name: "RPE OMNI 0-10" });
    await user.click(within(group).getByRole("radio", { name: "RPE OMNI 0-10: 8 — Muy duro" }));

    expect(onChange).toHaveBeenCalledWith(8);
  });

  it("pulsar la opción ya seleccionada la deselecciona (onChange con null)", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<RpeScale value={5} onChange={onChange} />);

    const group = screen.getByRole("group", { name: "RPE OMNI 0-10" });
    await user.click(within(group).getByRole("radio", { name: "RPE OMNI 0-10: 5 — Moderado" }));

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("muestra la etiqueta del campo 'RPE · esfuerzo percibido'", () => {
    render(<RpeScale value={5} onChange={vi.fn()} />);
    expect(screen.getByText("RPE · esfuerzo percibido")).toBeInTheDocument();
  });

  it("sin valor (null) la barra baja de opacidad (no se confunde con 'con valor')", () => {
    render(<RpeScale value={null} onChange={vi.fn()} />);
    const group = screen.getByRole("group", { name: "RPE OMNI 0-10" });
    expect(group).toHaveClass("opacity-60");
    expect(group).not.toHaveClass("opacity-100");
  });

  it("con un valor la barra vuelve a opacidad completa y el segmento activo lleva el marcador (anillo blanco + más alto)", () => {
    render(<RpeScale value={5} onChange={vi.fn()} />);
    const group = screen.getByRole("group", { name: "RPE OMNI 0-10" });
    expect(group).toHaveClass("opacity-100");
    expect(group).not.toHaveClass("opacity-60");

    const selected = within(group).getByRole("radio", {
      name: "RPE OMNI 0-10: 5 — Moderado",
      checked: true,
    });
    expect(selected.className).toContain("data-[state=on]:ring-charcoal");
    expect(selected.className).toContain("data-[state=on]:h-14");
  });

  it("disabled=true deshabilita las 11 opciones y no dispara onChange al pulsarlas", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<RpeScale value={5} onChange={onChange} disabled />);

    const group = screen.getByRole("group", { name: "RPE OMNI 0-10" });
    const options = within(group).getAllByRole("radio");
    options.forEach((o) => expect(o).toBeDisabled());

    await user.click(within(group).getByRole("radio", { name: "RPE OMNI 0-10: 8 — Muy duro" }));
    expect(onChange).not.toHaveBeenCalled();
  });
});
