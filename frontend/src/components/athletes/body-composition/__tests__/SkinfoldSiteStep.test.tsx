/**
 * Tests — SkinfoldSiteStep (feature 046, US1, T019/T026).
 *
 * Reglas cubiertas (contracts/skinfolds-api.md, data-model.md §4,
 * lib/bodyComposition/readings.ts): la tercera lectura aparece sólo cuando
 * la diferencia entre las dos primeras supera `max(5 %, 1.0 mm)`
 * (estrictamente mayor, nunca en el límite exacto); el "Valor del sitio" es
 * el promedio de dos lecturas o la mediana de tres; "Omitir este sitio"
 * marca `{declined: true}` sin pedir motivo; la advertencia de rango
 * plausible es `role="status"` (informativa, nunca `alert` ni bloqueante).
 *
 * Datos: sintéticos, sin nombre de ningún deportista real.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { SkinfoldSiteStep } from "@/components/athletes/body-composition/SkinfoldSiteStep";
import type { SkinfoldSiteStepValue } from "@/components/athletes/body-composition/SkinfoldSiteStep";
import { SKINFOLD_SITE_ORDER, getSkinfoldSiteDiagram } from "@/lib/bodyComposition/siteDiagrams";
import { getSiteIllustration } from "@/lib/bodyComposition/siteIllustrations";

// Ilustración simulada: no depende de que los `.webp` existan en el repo.
vi.mock("@/lib/bodyComposition/siteIllustrations", () => ({
  SITE_ILLUSTRATION_SIZE: 768,
  getSiteIllustration: vi.fn(),
}));

const mockIllustration = vi.mocked(getSiteIllustration);

const EMPTY_VALUE: SkinfoldSiteStepValue = { declined: false, readings: [] };

function renderStep(overrides: Partial<Parameters<typeof SkinfoldSiteStep>[0]> = {}) {
  const onChange = vi.fn();
  const onSkip = vi.fn();
  const utils = render(
    <SkinfoldSiteStep
      site="triceps"
      ageYears={12}
      value={EMPTY_VALUE}
      onChange={onChange}
      onSkip={onSkip}
      {...overrides}
    />,
  );
  return { ...utils, onChange, onSkip };
}

async function typeReadings(user: ReturnType<typeof userEvent.setup>, r1: string, r2: string) {
  await user.type(screen.getByLabelText("Primera lectura (mm)"), r1);
  await user.type(screen.getByLabelText("Segunda lectura (mm)"), r2);
}

describe("SkinfoldSiteStep", () => {
  it("no muestra el prompt de tercera lectura con 8.0 y 9.0 (diferencia en el límite, no lo supera)", async () => {
    const user = userEvent.setup();
    renderStep();
    await typeReadings(user, "8.0", "9.0");
    expect(
      screen.queryByText("Diferencia mayor a lo esperado: toma una tercera lectura"),
    ).not.toBeInTheDocument();
  });

  it("no muestra el prompt de tercera lectura con 20.0 y 21.0 (diferencia bajo el 5 %)", async () => {
    const user = userEvent.setup();
    renderStep();
    await typeReadings(user, "20.0", "21.0");
    expect(
      screen.queryByText("Diferencia mayor a lo esperado: toma una tercera lectura"),
    ).not.toBeInTheDocument();
  });

  it("muestra el prompt de tercera lectura con 8.0 y 9.5 (diferencia supera la tolerancia)", async () => {
    const user = userEvent.setup();
    renderStep();
    await typeReadings(user, "8.0", "9.5");

    const prompt = screen.getByText("Diferencia mayor a lo esperado: toma una tercera lectura");
    expect(prompt).toBeInTheDocument();
    expect(prompt).toHaveAttribute("role", "status");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Tercera lectura (mm)")).toBeInTheDocument();
  });

  it("muestra el valor del sitio como promedio de dos lecturas", async () => {
    const user = userEvent.setup();
    renderStep();
    await typeReadings(user, "8.0", "9.0");
    expect(screen.getByText("8.5 mm")).toBeInTheDocument();
  });

  it("muestra el valor del sitio como mediana de tres lecturas", async () => {
    const user = userEvent.setup();
    renderStep();
    await typeReadings(user, "8.0", "9.5");
    await user.type(screen.getByLabelText("Tercera lectura (mm)"), "9.0");
    // mediana de [8.0, 9.5, 9.0] = 9.0
    expect(screen.getByText("9.0 mm")).toBeInTheDocument();
  });

  it("notifica onChange con las lecturas una vez hay al menos dos válidas", async () => {
    const user = userEvent.setup();
    const { onChange } = renderStep();
    await typeReadings(user, "8.0", "9.0");
    expect(onChange).toHaveBeenLastCalledWith({ declined: false, readings: [8, 9] });
  });

  it("al borrar una lectura notifica la lista reducida (no conserva el par anterior)", async () => {
    const user = userEvent.setup();
    const { onChange } = renderStep();
    await typeReadings(user, "8.0", "9.0");
    expect(onChange).toHaveBeenLastCalledWith({ declined: false, readings: [8, 9] });

    await user.clear(screen.getByLabelText("Segunda lectura (mm)"));
    expect(onChange).toHaveBeenLastCalledWith({ declined: false, readings: [8] });
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("descarta la tercera lectura cuando la corrección de la primera ya no la exige", async () => {
    const user = userEvent.setup();
    const { onChange } = renderStep();
    await typeReadings(user, "8.0", "9.5");
    await user.type(screen.getByLabelText("Tercera lectura (mm)"), "9.0");
    expect(onChange).toHaveBeenLastCalledWith({ declined: false, readings: [8, 9.5, 9] });

    const first = screen.getByLabelText("Primera lectura (mm)");
    await user.clear(first);
    await user.type(first, "9.0");
    expect(
      screen.queryByText("Diferencia mayor a lo esperado: toma una tercera lectura"),
    ).not.toBeInTheDocument();
    expect(onChange).toHaveBeenLastCalledWith({ declined: false, readings: [9, 9.5] });
  });

  it("'Omitir este sitio' marca {declined: true} sin pedir motivo y notifica onSkip", async () => {
    const user = userEvent.setup();
    const { onChange, onSkip } = renderStep();

    const skipButton = screen.getByRole("button", { name: "Omitir este sitio" });
    await user.click(skipButton);

    expect(screen.queryByRole("textbox", { name: /motivo/i })).not.toBeInTheDocument();
    expect(onChange).toHaveBeenCalledWith({ declined: true });
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it("el botón 'Omitir este sitio' cumple el mínimo de 48 px de alto (touch target)", () => {
    renderStep();
    const skipButton = screen.getByRole("button", { name: "Omitir este sitio" });
    expect(skipButton.className).toMatch(/min-h-12|h-12/);
  });

  it("los inputs numéricos usan step=0.5 (mediomilímetro)", () => {
    renderStep();
    expect(screen.getByLabelText("Primera lectura (mm)")).toHaveAttribute("step", "0.5");
    expect(screen.getByLabelText("Segunda lectura (mm)")).toHaveAttribute("step", "0.5");
  });

  it("muestra la advertencia suave de rango plausible sin bloquear, como role=status", async () => {
    const user = userEvent.setup();
    renderStep();
    // Para tríceps, 9-12 años, rango plausible es [4, 30] mm — 45/46 está fuera.
    await typeReadings(user, "45.0", "46.0");

    const warning = screen.getByText(/¿Seguro\? Ese valor es alto\/bajo para este pliegue\./);
    expect(warning).toHaveAttribute("role", "status");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    // No bloquea: el botón de omitir sigue disponible y no aparece ningún estado deshabilitado forzado.
    expect(screen.getByRole("button", { name: "Omitir este sitio" })).toBeEnabled();
  });

  it("muestra la sección 'Dónde' y 'Cómo' del sitio", () => {
    renderStep();
    expect(screen.getByText("Dónde")).toBeInTheDocument();
    expect(screen.getByText("Cómo")).toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad (axe)", async () => {
    const { container } = renderStep();
    expect(await axe(container)).toHaveNoViolations();
  });

  describe("ilustración del sitio", () => {
    beforeEach(() => {
      mockIllustration.mockImplementation((site) => `/assets/${site}.webp`);
    });

    it.each(SKINFOLD_SITE_ORDER)("muestra la ilustración de %s con su texto alternativo", (site) => {
      renderStep({ site });
      const img = screen.getByRole("img", { name: getSkinfoldSiteDiagram(site).alt });
      expect(img.tagName).toBe("IMG");
      expect(img).toHaveAttribute("src", `/assets/${site}.webp`);
    });

    it("no se abre el diálogo de ampliación hasta tocar la ilustración", () => {
      renderStep();
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("al tocar la ilustración abre el diálogo ampliado con el nombre del sitio como título", async () => {
      const user = userEvent.setup();
      renderStep({ site: "medial_calf" });

      await user.click(screen.getByRole("button", { name: "Ampliar la ilustración de Pantorrilla medial" }));

      const dialog = screen.getByRole("dialog", { name: "Pantorrilla medial" });
      const enlarged = within(dialog).getByRole("img", { name: getSkinfoldSiteDiagram("medial_calf").alt });
      expect(enlarged).toHaveAttribute("src", "/assets/medial_calf.webp");
      expect(within(dialog).getByRole("img", { name: "Lado derecho" })).toBeInTheDocument();
    });

    it("el botón 'Cerrar' cierra el diálogo ampliado", async () => {
      const user = userEvent.setup();
      renderStep();

      await user.click(screen.getByRole("button", { name: "Ampliar la ilustración de Tríceps" }));
      await user.click(screen.getByRole("button", { name: "Cerrar" }));

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("Escape cierra el diálogo ampliado", async () => {
      const user = userEvent.setup();
      renderStep();

      await user.click(screen.getByRole("button", { name: "Ampliar la ilustración de Tríceps" }));
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      await user.keyboard("{Escape}");

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("ampliar la ilustración no altera las lecturas ni dispara callbacks", async () => {
      const user = userEvent.setup();
      const { onChange, onSkip } = renderStep();

      await user.click(screen.getByRole("button", { name: "Ampliar la ilustración de Tríceps" }));
      await user.click(screen.getByRole("button", { name: "Cerrar" }));

      expect(onChange).not.toHaveBeenCalled();
      expect(onSkip).not.toHaveBeenCalled();
    });

    it("sin violaciones de accesibilidad (axe) con el paso y el diálogo abierto", async () => {
      const user = userEvent.setup();
      const { container } = renderStep();
      expect(await axe(container)).toHaveNoViolations();

      await user.click(screen.getByRole("button", { name: "Ampliar la ilustración de Tríceps" }));

      expect(await axe(document.body)).toHaveNoViolations();
    });
  });
});
