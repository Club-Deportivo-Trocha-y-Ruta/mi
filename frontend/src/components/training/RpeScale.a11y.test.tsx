import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";

import { RpeScale } from "./RpeScale";

expect.extend(toHaveNoViolations);

describe("RpeScale — accesibilidad", () => {
  it("sin violaciones axe con un valor seleccionado", async () => {
    const { container } = render(<RpeScale value={6} onChange={vi.fn()} />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones axe sin ningún valor (null)", async () => {
    const { container } = render(<RpeScale value={null} onChange={vi.fn()} />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones axe deshabilitado", async () => {
    const { container } = render(<RpeScale value={4} onChange={vi.fn()} disabled />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("las 11 opciones exponen aria-label y aria-checked", () => {
    render(<RpeScale value={3} onChange={vi.fn()} />);
    const group = screen.getByRole("group", { name: "RPE OMNI 0-10" });
    const options = within(group).getAllByRole("radio");
    expect(options).toHaveLength(11);
    options.forEach((o) => {
      expect(o.getAttribute("aria-label")?.length).toBeGreaterThan(0);
      expect(o).toHaveAttribute("aria-checked");
    });
  });
});
