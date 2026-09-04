/**
 * Tests — FamilyBandCards (feature 040, US4, T058).
 *
 * Contrato: `specs/040-growth-module-redesign/contracts/growth-tab-ui.md`
 * y `contracts/band-vocabulary.md` — dos tarjetas narrativas ("Estatura
 * para su edad", "Peso para su estatura") con ícono + etiqueta familiar
 * (`StatusBadge`) y la frase narrativa, **sin** Z-score, percentil ni la
 * etiqueta clínica del coach (FR-016).
 *
 * Datos: sintéticos, sin nombre ni fecha de nacimiento reales de un menor.
 */
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { FamilyBandCards } from "@/components/athletes/growth/FamilyBandCards";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { BandReading, LatestBands } from "@/types/growth.types";

// El tooltip de la tarjeta de IMC (`@/components/ui/tooltip`) requiere un
// `TooltipProvider` ancestro — en la app real lo pone `App.tsx`; acá se
// envuelve cada render, mismo criterio que `ParentSessionCard.test.tsx`.
function renderWithTooltip(ui: ReactElement) {
  return render(<TooltipProvider delayDuration={0}>{ui}</TooltipProvider>);
}

function makeLatest(overrides: Partial<LatestBands> = {}): LatestBands {
  return {
    record_id: 41,
    growth_source: "WHO",
    height: { value: 150.0, z_score: -1.66, percentile: 4.8, band: "riesgo_retraso_talla" },
    bmi: { value: 21.9, z_score: 0.7, percentile: 75.7, band: "adecuado" },
    weight: null,
    ...overrides,
  };
}

function makeReading(overrides: Partial<BandReading> = {}): BandReading {
  return { value: 150.0, z_score: -1.66, percentile: 4.8, band: "riesgo_retraso_talla", ...overrides };
}

describe("FamilyBandCards", () => {
  it("expone data-testid=family-band-cards en la raíz", () => {
    renderWithTooltip(<FamilyBandCards latest={makeLatest()} />);
    expect(screen.getByTestId("family-band-cards")).toBeInTheDocument();
  });

  it('muestra los dos títulos fijos del contrato: "Estatura para su edad" y "Peso para su estatura"', () => {
    renderWithTooltip(<FamilyBandCards latest={makeLatest()} />);
    expect(screen.getByText("Estatura para su edad")).toBeInTheDocument();
    expect(screen.getByText("Peso para su estatura")).toBeInTheDocument();
    // Res. 2465 usa "IMC"/"BMI" como nombre técnico — nunca como titular
    // familiar (decisión D3).
    expect(screen.queryByText(/^IMC$/)).not.toBeInTheDocument();
  });

  it("muestra la etiqueta familiar (icono + texto) de cada banda, nunca la etiqueta clínica del coach", () => {
    renderWithTooltip(
      <FamilyBandCards
        latest={makeLatest({
          height: makeReading({ band: "riesgo_retraso_talla" }),
          bmi: makeReading({ band: "adecuado" }),
        })}
      />,
    );
    expect(screen.getByText("Un poco por debajo del promedio")).toBeInTheDocument();
    expect(screen.getByText("Dentro del rango esperado")).toBeInTheDocument();
    // Etiquetas clínicas del coach para las mismas bandas — no deben aparecer.
    expect(screen.queryByText("En vigilancia")).not.toBeInTheDocument();
  });

  it("muestra la frase narrativa de cada banda debajo de la insignia", () => {
    renderWithTooltip(
      <FamilyBandCards
        latest={makeLatest({ height: makeReading({ band: "retraso_talla" }) })}
      />,
    );
    expect(
      screen.getByText(/La estatura está por debajo del rango esperado/),
    ).toBeInTheDocument();
  });

  it("nunca muestra Z-score ni percentil (FR-016)", () => {
    const { container } = renderWithTooltip(
      <FamilyBandCards
        latest={makeLatest({
          height: makeReading({ z_score: -1.66, percentile: 4.8 }),
        })}
      />,
    );
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/Z=/i);
    expect(text).not.toMatch(/-1[.,]66/);
    expect(text).not.toMatch(/P\d{1,2}\b/);
  });

  it("cada banda va acompañada de un ícono (nunca solo color)", () => {
    const { container } = renderWithTooltip(<FamilyBandCards latest={makeLatest()} />);
    expect(container.querySelectorAll("svg").length).toBeGreaterThanOrEqual(2);
  });

  it("con reading=null en un indicador muestra un mensaje neutro en vez de romper", () => {
    renderWithTooltip(<FamilyBandCards latest={makeLatest({ height: null })} />);
    expect(
      screen.getByText("Aún no hay datos suficientes para mostrar esta medida."),
    ).toBeInTheDocument();
  });

  it("con latest=null no revienta y muestra el mensaje neutro en ambas tarjetas", () => {
    renderWithTooltip(<FamilyBandCards latest={null} />);
    expect(
      screen.getAllByText("Aún no hay datos suficientes para mostrar esta medida."),
    ).toHaveLength(2);
  });

  // -------------------------------------------------------------------------
  // Tooltip de la tarjeta de IMC (decisión D3) — solo esa tarjeta lo lleva.
  // -------------------------------------------------------------------------

  it('la tarjeta de IMC lleva un disparador de tooltip con el nombre técnico', async () => {
    const user = userEvent.setup();
    renderWithTooltip(<FamilyBandCards latest={makeLatest()} />);

    const bmiCard = screen.getByTestId("family-band-card-bmi");
    const trigger = within(bmiCard).getByRole("button", {
      name: /Más información sobre Peso para su estatura/i,
    });
    // Radix abre el tooltip con hover/focus, no con click.
    await user.hover(trigger);

    // Radix duplica el texto: un nodo visible + un `span` accesible
    // (`role="tooltip"`) visualmente oculto — de ahí `findAllByText` en vez
    // de `findByText`, que fallaría por "múltiples coincidencias".
    expect(
      await screen.findAllByText("Índice de masa corporal para la edad, OMS 2007"),
    ).not.toHaveLength(0);
  });

  it("la tarjeta de estatura NO lleva disparador de tooltip", () => {
    renderWithTooltip(<FamilyBandCards latest={makeLatest()} />);
    const heightCard = screen.getByTestId("family-band-card-height");
    expect(within(heightCard).queryByRole("button")).not.toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad (axe)", async () => {
    const { container } = renderWithTooltip(<FamilyBandCards latest={makeLatest()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
