import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { CoachFilter } from "@/components/audit/CoachFilter";

expect.extend(toHaveNoViolations);

const COACHES = [
  { id: 10, displayName: "Ana Coach" },
  { id: 11, displayName: "Beto Coach" },
];

describe("CoachFilter", () => {
  it('incluye la opción "Todos los entrenadores" seleccionada por defecto', () => {
    render(<CoachFilter coaches={COACHES} value={null} onChange={vi.fn()} />);
    expect(
      screen.getByRole("option", { name: "Todos los entrenadores" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Entrenador")).toHaveValue("");
  });

  it("lista una opción por cada entrenador del club", () => {
    render(<CoachFilter coaches={COACHES} value={null} onChange={vi.fn()} />);
    expect(screen.getByRole("option", { name: "Ana Coach" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Beto Coach" })).toBeInTheDocument();
  });

  it("dispara onChange con el id numérico al elegir un entrenador", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<CoachFilter coaches={COACHES} value={null} onChange={onChange} />);

    await user.selectOptions(screen.getByLabelText("Entrenador"), "11");
    expect(onChange).toHaveBeenCalledWith(11);
  });

  it('dispara onChange con null al volver a "Todos los entrenadores"', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<CoachFilter coaches={COACHES} value={10} onChange={onChange} />);

    await user.selectOptions(screen.getByLabelText("Entrenador"), "");
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('no muestra "Limpiar filtros" cuando showClear es false', () => {
    render(<CoachFilter coaches={COACHES} value={10} onChange={vi.fn()} />);
    expect(screen.queryByText("Limpiar filtros")).not.toBeInTheDocument();
  });

  it('muestra "Limpiar filtros" y dispara onClear cuando showClear es true', async () => {
    const user = userEvent.setup();
    const onClear = vi.fn();
    render(
      <CoachFilter
        coaches={COACHES}
        value={10}
        onChange={vi.fn()}
        showClear
        onClear={onClear}
      />,
    );

    const clearButton = screen.getByText("Limpiar filtros");
    expect(clearButton).toBeInTheDocument();
    await user.click(clearButton);
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("deshabilita el select cuando disabled es true", () => {
    render(<CoachFilter coaches={COACHES} value={null} onChange={vi.fn()} disabled />);
    expect(screen.getByLabelText("Entrenador")).toBeDisabled();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(
      <CoachFilter coaches={COACHES} value={null} onChange={vi.fn()} showClear onClear={vi.fn()} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
