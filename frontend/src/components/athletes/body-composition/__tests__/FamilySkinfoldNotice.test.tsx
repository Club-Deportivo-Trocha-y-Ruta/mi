/**
 * Tests — FamilySkinfoldNotice (feature 046, US4, T050).
 *
 * Contrato: `docs/21-body-composition/research-safeguards-referral.md` §5 —
 * addendum informativo para familias, colapsable, mostrado para deportistas
 * de 9 años o más sin importar si ya hay mediciones (`has_data`).
 *
 * Datos: sintéticos, sin nombre ni fecha de nacimiento reales de un menor.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { FamilySkinfoldNotice } from "@/components/athletes/body-composition/FamilySkinfoldNotice";

const ADDENDUM_SNIPPET = /Además de talla y peso, el club también podría tomar pliegues cutáneos/;

describe("FamilySkinfoldNotice", () => {
  it("muestra el disparador '¿Qué es la medición de pliegues?' para un atleta de 9 años", () => {
    render(<FamilySkinfoldNotice athleteAgeDecimal={9.0} />);
    expect(
      screen.getByRole("button", { name: "¿Qué es la medición de pliegues?" }),
    ).toBeInTheDocument();
  });

  it("no renderiza nada para un atleta menor de 9 años", () => {
    const { container } = render(<FamilySkinfoldNotice athleteAgeDecimal={8.9} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("no renderiza nada cuando la edad es desconocida (null)", () => {
    const { container } = render(<FamilySkinfoldNotice athleteAgeDecimal={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("está colapsado por defecto (aria-expanded=false)", () => {
    render(<FamilySkinfoldNotice athleteAgeDecimal={12} />);
    const trigger = screen.getByRole("button", { name: "¿Qué es la medición de pliegues?" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("al hacer click expande y muestra el párrafo del addendum verbatim", async () => {
    const user = userEvent.setup();
    render(<FamilySkinfoldNotice athleteAgeDecimal={12} />);
    const trigger = screen.getByRole("button", { name: "¿Qué es la medición de pliegues?" });

    await user.click(trigger);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(ADDENDUM_SNIPPET)).toBeInTheDocument();
  });

  it("se muestra sin importar has_data (no depende de si ya hay mediciones)", () => {
    render(<FamilySkinfoldNotice athleteAgeDecimal={13} />);
    expect(
      screen.getByRole("button", { name: "¿Qué es la medición de pliegues?" }),
    ).toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad (axe)", async () => {
    const { container } = render(<FamilySkinfoldNotice athleteAgeDecimal={12} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
