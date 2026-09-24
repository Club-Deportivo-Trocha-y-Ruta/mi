/**
 * Tests — FamilyBodyCompositionCard (feature 046, US4, T050).
 *
 * Contrato: `specs/046-body-composition-skinfolds/contracts/skinfolds-api.md`
 * §5 — el bloque familiar de composición corporal expone exactamente
 * `has_data`, `latest_set_date`, `family_band`, `family_label`,
 * `family_sentence` — nunca `body_fat_pct`, `sum4_mm` ni `band` (coach). El
 * tipo `BodyCompositionFamilySummary` ya excluye `rojo` de `family_band`
 * (`types/bodyComposition.types.ts`).
 *
 * Datos: sintéticos, sin nombre ni fecha de nacimiento reales de un menor.
 */
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { FamilyBodyCompositionCard } from "@/components/athletes/body-composition/FamilyBodyCompositionCard";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { BodyCompositionFamilySummary } from "@/types/bodyComposition.types";

// El tooltip informativo requiere un `TooltipProvider` ancestro — en la app
// real lo pone `App.tsx`; acá se envuelve cada render, mismo criterio que
// `FamilyBandCards.test.tsx`.
function renderWithTooltip(ui: ReactElement) {
  return render(<TooltipProvider delayDuration={0}>{ui}</TooltipProvider>);
}

const NO_DATA_MESSAGE = "Aún no hay datos suficientes para mostrar esta medida.";

function makeSummary(
  overrides: Partial<BodyCompositionFamilySummary> = {},
): BodyCompositionFamilySummary {
  return {
    has_data: true,
    latest_set_date: "2026-08-01",
    family_band: "verde",
    family_label: "En su curva esperada",
    family_sentence:
      "La composición corporal de tu hijo/a se mantiene dentro de lo esperado para su etapa de desarrollo. Sigue acompañando el proceso — esto va de la mano de un crecimiento saludable.",
    ...overrides,
  };
}

describe("FamilyBodyCompositionCard", () => {
  it.each<BodyCompositionFamilySummary["family_band"]>(["verde", "ambar"])(
    "muestra la etiqueta y la frase narrativa para family_band=%s",
    (band) => {
      const summary = makeSummary({
        family_band: band,
        family_label: band === "verde" ? "En su curva esperada" : "En observación",
        family_sentence:
          band === "verde"
            ? "La composición corporal de tu hijo/a se mantiene dentro de lo esperado."
            : "Notamos un cambio que vale la pena conversar.",
      });

      renderWithTooltip(<FamilyBodyCompositionCard summary={summary} />);

      expect(screen.getByText(summary.family_label!)).toBeInTheDocument();
      expect(screen.getByText(summary.family_sentence!)).toBeInTheDocument();
    },
  );

  it("con has_data=false muestra el mensaje neutro en vez de la etiqueta/frase", () => {
    renderWithTooltip(
      <FamilyBodyCompositionCard
        summary={makeSummary({
          has_data: false,
          latest_set_date: null,
          family_label: "En su curva esperada",
          family_sentence: "Texto que no debería renderizarse.",
        })}
      />,
    );

    expect(screen.getByText(NO_DATA_MESSAGE)).toBeInTheDocument();
    expect(screen.queryByText("Texto que no debería renderizarse.")).not.toBeInTheDocument();
  });

  it("con summary=null muestra el mensaje neutro sin romper", () => {
    renderWithTooltip(<FamilyBodyCompositionCard summary={null} />);
    expect(screen.getByText(NO_DATA_MESSAGE)).toBeInTheDocument();
  });

  it("el título de la tarjeta es siempre 'Composición corporal'", () => {
    renderWithTooltip(<FamilyBodyCompositionCard summary={makeSummary()} />);
    expect(screen.getByText("Composición corporal")).toBeInTheDocument();
  });

  it("nunca muestra un numeral (%BF ni suma de pliegues) en el DOM", () => {
    const { container } = renderWithTooltip(<FamilyBodyCompositionCard summary={makeSummary()} />);
    const text = container.textContent ?? "";
    // Ninguna cifra decimal ni entero suelto en el cuerpo de la tarjeta —
    // ni %BF, ni Σ4/Σ6 mm, ni fecha numérica cruda (contrato §5).
    expect(text).not.toMatch(/\d/);
  });

  it("sin violaciones de accesibilidad (axe)", async () => {
    const { container } = renderWithTooltip(<FamilyBodyCompositionCard summary={makeSummary()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
