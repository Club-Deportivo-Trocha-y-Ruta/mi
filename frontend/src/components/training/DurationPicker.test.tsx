import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DurationPicker } from "./DurationPicker";

function renderPicker(value: number | undefined, onChange = vi.fn()) {
  return { onChange, ...render(<DurationPicker value={value} onChange={onChange} />) };
}

describe("DurationPicker — renderizado", () => {
  it("muestra las etiquetas accesibles correctamente", () => {
    renderPicker(60);
    expect(screen.getByRole("group", { name: /Duración/i })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /Duraciones frecuentes/i })).toBeInTheDocument();
  });

  it("descompone 90 minutos en 1 hora y 30 minutos", () => {
    renderPicker(90);
    const horasInput = screen.getByRole("spinbutton", { name: /Horas/i });
    const minutosSelect = screen.getByRole("combobox", { name: /Minutos/i });
    expect(horasInput).toHaveValue(1);
    expect(minutosSelect).toHaveValue("30");
  });

  it("descompone 143 minutos en 2 horas y 23 minutos (snap a 20)", () => {
    renderPicker(143);
    const horasInput = screen.getByRole("spinbutton", { name: /Horas/i });
    const minutosSelect = screen.getByRole("combobox", { name: /Minutos/i });
    expect(horasInput).toHaveValue(2);
    // 143 % 60 = 23 → snap al step de 5 más cercano hacia abajo = 20
    expect(minutosSelect).toHaveValue("20");
  });

  it("descompone 60 minutos (default create) en 1h y 00 min", () => {
    renderPicker(60);
    const horasInput = screen.getByRole("spinbutton", { name: /Horas/i });
    const minutosSelect = screen.getByRole("combobox", { name: /Minutos/i });
    expect(horasInput).toHaveValue(1);
    expect(minutosSelect).toHaveValue("0");
  });

  it("muestra el helper text con el total en minutos", () => {
    renderPicker(90);
    expect(screen.getByText("Total: 90 minutos")).toBeInTheDocument();
  });

  it("muestra mensaje de error cuando se pasa error prop", () => {
    render(
      <DurationPicker value={10} onChange={vi.fn()} error="Mínimo 15 minutos" />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Mínimo 15 minutos");
    // El helper text no debe aparecer cuando hay error
    expect(screen.queryByText(/Total:/)).not.toBeInTheDocument();
  });

  it("aria-invalid es true cuando hay error", () => {
    render(
      <DurationPicker value={10} onChange={vi.fn()} error="Mínimo 15 minutos" />,
    );
    const group = screen.getByRole("group", { name: /Duración/i });
    expect(group).toHaveAttribute("aria-invalid", "true");
  });

  it("aria-invalid es false cuando no hay error", () => {
    renderPicker(60);
    const group = screen.getByRole("group", { name: /Duración/i });
    expect(group).toHaveAttribute("aria-invalid", "false");
  });
});

describe("DurationPicker — interacción", () => {
  it("llama onChange con total correcto al cambiar horas", () => {
    const onChange = vi.fn();
    render(<DurationPicker value={60} onChange={onChange} />);
    const horasInput = screen.getByRole("spinbutton", { name: /Horas/i });
    fireEvent.change(horasInput, { target: { value: "2" } });
    // 2h + 0min = 120
    expect(onChange).toHaveBeenCalledWith(120);
  });

  it("llama onChange con total correcto al cambiar minutos", () => {
    const onChange = vi.fn();
    render(<DurationPicker value={60} onChange={onChange} />);
    const minutosSelect = screen.getByRole("combobox", { name: /Minutos/i });
    fireEvent.change(minutosSelect, { target: { value: "30" } });
    // 1h + 30min = 90
    expect(onChange).toHaveBeenCalledWith(90);
  });

  it("clampa horas a máximo 4", () => {
    const onChange = vi.fn();
    render(<DurationPicker value={60} onChange={onChange} />);
    const horasInput = screen.getByRole("spinbutton", { name: /Horas/i });
    fireEvent.change(horasInput, { target: { value: "9" } });
    // clampa a 4 → 4h + 0min = 240
    expect(onChange).toHaveBeenCalledWith(240);
  });

  it("clampa horas a mínimo 0", () => {
    const onChange = vi.fn();
    render(<DurationPicker value={60} onChange={onChange} />);
    const horasInput = screen.getByRole("spinbutton", { name: /Horas/i });
    fireEvent.change(horasInput, { target: { value: "-2" } });
    // clampa a 0 → 0h + 0min = 0
    expect(onChange).toHaveBeenCalledWith(0);
  });

  it("chip de preset '1 h 30 min' llama onChange con 90", () => {
    const onChange = vi.fn();
    render(<DurationPicker value={60} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "1 h 30 min" }));
    expect(onChange).toHaveBeenCalledWith(90);
  });

  it("chip de preset '2 h' llama onChange con 120", () => {
    const onChange = vi.fn();
    render(<DurationPicker value={60} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "2 h" }));
    expect(onChange).toHaveBeenCalledWith(120);
  });

  it("chip activo tiene aria-pressed=true", () => {
    renderPicker(90);
    const chip = screen.getByRole("button", { name: "1 h 30 min" });
    expect(chip).toHaveAttribute("aria-pressed", "true");
  });

  it("chip inactivo tiene aria-pressed=false", () => {
    renderPicker(60);
    const chip = screen.getByRole("button", { name: "1 h 30 min" });
    expect(chip).toHaveAttribute("aria-pressed", "false");
  });
});

describe("DurationPicker — valores edge", () => {
  it("usa 60 min como fallback cuando value es undefined", () => {
    renderPicker(undefined);
    const horasInput = screen.getByRole("spinbutton", { name: /Horas/i });
    expect(horasInput).toHaveValue(1);
  });

  it("240 minutos = 4 horas 0 minutos", () => {
    renderPicker(240);
    const horasInput = screen.getByRole("spinbutton", { name: /Horas/i });
    const minutosSelect = screen.getByRole("combobox", { name: /Minutos/i });
    expect(horasInput).toHaveValue(4);
    expect(minutosSelect).toHaveValue("0");
  });

  it("15 minutos = 0 horas 15 minutos", () => {
    renderPicker(15);
    const horasInput = screen.getByRole("spinbutton", { name: /Horas/i });
    const minutosSelect = screen.getByRole("combobox", { name: /Minutos/i });
    expect(horasInput).toHaveValue(0);
    expect(minutosSelect).toHaveValue("15");
  });
});

describe("DurationPicker — touch targets (regresión ≥48px)", () => {
  it("el input de horas tiene una clase de min-height >= 48px", () => {
    renderPicker(60);
    const horasInput = screen.getByRole("spinbutton", { name: /Horas/i });
    expect(horasInput.className).toMatch(/min-h-\[48px\]|min-h-12/);
  });

  it("el select de minutos tiene una clase de min-height >= 48px", () => {
    renderPicker(60);
    const minutosSelect = screen.getByRole("combobox", { name: /Minutos/i });
    expect(minutosSelect.className).toMatch(/min-h-\[48px\]|min-h-12/);
  });

  it("cada botón de preset tiene una clase de min-height >= 48px", () => {
    renderPicker(60);
    const presetButtons = screen.getAllByRole("button");
    expect(presetButtons.length).toBeGreaterThan(0);
    for (const button of presetButtons) {
      expect(button.className).toMatch(/min-h-\[48px\]|min-h-12/);
    }
  });
});
