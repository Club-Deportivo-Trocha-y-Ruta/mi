/**
 * Tests para CaveatsNote (feature 044, US6 — T076).
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { CaveatsNote } from "@/components/race/history/CaveatsNote";

describe("CaveatsNote", () => {
  it("siempre está presente con role=note aunque la lista esté vacía", () => {
    render(<CaveatsNote caveats={[]} />);
    const note = screen.getByTestId("history-caveats-note");
    expect(note).toHaveAttribute("role", "note");
    expect(note).toHaveTextContent(/compara con cautela/i);
  });

  it("muestra una oración por código reconocido", () => {
    render(
      <CaveatsNote
        caveats={["different_courses", "small_fields"]}
      />,
    );
    expect(screen.getByText(/circuito distinto/i)).toBeInTheDocument();
    expect(screen.getByText(/muy pocos corredores/i)).toBeInTheDocument();
  });

  it("omite un código desconocido en vez de romper", () => {
    render(
      // @ts-expect-error — código fuera del catálogo cerrado, a propósito.
      <CaveatsNote caveats={["different_courses", "unknown_code"]} />,
    );
    expect(screen.getByText(/circuito distinto/i)).toBeInTheDocument();
    expect(screen.queryByText(/unknown_code/i)).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(
      <CaveatsNote caveats={["different_courses"]} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
