/**
 * Tests para `StructuredInsight` (feature 042, T060/T064, FR-026):
 *   - Colapsado por defecto: "Qué significa" y "Próximas 2–4 semanas" NO
 *     están en el árbol accesible hasta activar el expansor; la línea de
 *     resumen y las señales de aviso SÍ están visibles desde el inicio.
 *   - El expansor es un `<button>` real con `aria-expanded`/`aria-controls`
 *     correctos, alterna ambos y es operable por teclado.
 *   - Confianza y vacíos de información se renderizan.
 *   - Las etiquetas de sección conservan sus tildes/diacríticos.
 *   - jest-axe sin violaciones, colapsado y expandido.
 *
 * Puramente presentacional (sin fetching): recibe `insight` como prop, así
 * que no hay MSW/red que mockear aquí.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { describe, expect, it } from "vitest";

import { StructuredInsight } from "./StructuredInsight";
import type { AnthropometryInsightOut } from "@/types/ai.types";

expect.extend(toHaveNoViolations);

const baseInsight: AnthropometryInsightOut = {
  summary_line: "Talla +1.0 cm en 14 semanas, dentro del rango esperado para su fase Circa-PHV.",
  changes: ["El cambio de talla supera el ruido instrumental y se mantiene en la fase Circa-PHV."],
  meaning: ["La velocidad estimada de 3.7 cm/año está por encima de lo típico para esta fase."],
  next_weeks: ["Esta fase es compatible con fuerza progresiva y mayor estructura de sesión."],
  warning_signs: [],
  confidence: {
    level: "high",
    reason: "Intervalo de 14 semanas confirma un patrón consistente con la medición previa.",
  },
  data_gaps: [],
};

const withWarningsAndGaps: AnthropometryInsightOut = {
  ...baseInsight,
  warning_signs: ["Pérdida de peso inesperada entre mediciones."],
  data_gaps: ["Solo una medición previa registrada."],
};

describe("StructuredInsight — colapsado por defecto", () => {
  it("muestra la línea de resumen desde el inicio", () => {
    render(<StructuredInsight insight={baseInsight} />);
    expect(screen.getByText(baseInsight.summary_line)).toBeInTheDocument();
  });

  it("no muestra 'Qué significa' ni 'Próximas 2–4 semanas' en el árbol accesible antes de expandir", () => {
    render(<StructuredInsight insight={baseInsight} />);

    expect(screen.queryByText("Qué significa")).not.toBeInTheDocument();
    expect(screen.queryByText("Próximas 2–4 semanas")).not.toBeInTheDocument();
    expect(screen.queryByText(baseInsight.meaning[0])).not.toBeInTheDocument();
    expect(screen.queryByText(baseInsight.next_weeks[0])).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("structured-insight-details"),
    ).not.toBeInTheDocument();
  });

  it("no muestra señales de aviso cuando la lista viene vacía", () => {
    render(<StructuredInsight insight={baseInsight} />);
    expect(
      screen.queryByTestId("structured-insight-warning-signs"),
    ).not.toBeInTheDocument();
  });

  it("muestra las señales de aviso desde el inicio cuando existen (sin necesidad de expandir)", () => {
    render(<StructuredInsight insight={withWarningsAndGaps} />);
    const warningBlock = screen.getByTestId("structured-insight-warning-signs");
    expect(warningBlock).toBeInTheDocument();
    expect(warningBlock).toHaveTextContent(withWarningsAndGaps.warning_signs[0]);
    expect(screen.getByText("Señales de aviso")).toBeInTheDocument();
  });
});

describe("StructuredInsight — confianza y vacíos de información", () => {
  it("renderiza el nivel de confianza y su motivo", () => {
    render(<StructuredInsight insight={baseInsight} />);
    const confidence = screen.getByTestId("structured-insight-confidence");
    expect(confidence).toHaveTextContent("Confianza: Alta");
    expect(confidence).toHaveTextContent(baseInsight.confidence.reason);
  });

  it("mapea los tres niveles de confianza a su etiqueta en español", () => {
    const { rerender } = render(
      <StructuredInsight insight={{ ...baseInsight, confidence: { level: "medium", reason: "x" } }} />,
    );
    expect(screen.getByTestId("structured-insight-confidence")).toHaveTextContent(
      "Confianza: Media",
    );

    rerender(
      <StructuredInsight insight={{ ...baseInsight, confidence: { level: "low", reason: "x" } }} />,
    );
    expect(screen.getByTestId("structured-insight-confidence")).toHaveTextContent(
      "Confianza: Baja",
    );
  });

  it("no muestra la sección de vacíos de información cuando la lista viene vacía", () => {
    render(<StructuredInsight insight={baseInsight} />);
    expect(
      screen.queryByTestId("structured-insight-data-gaps"),
    ).not.toBeInTheDocument();
  });

  it("muestra los vacíos de información cuando existen", () => {
    render(<StructuredInsight insight={withWarningsAndGaps} />);
    const gaps = screen.getByTestId("structured-insight-data-gaps");
    expect(gaps).toBeInTheDocument();
    expect(gaps).toHaveTextContent(withWarningsAndGaps.data_gaps[0]);
    expect(screen.getByText("Vacíos de información")).toBeInTheDocument();
  });
});

describe("StructuredInsight — etiquetas con diacríticos", () => {
  it("conserva las tildes de cada etiqueta de sección", () => {
    render(<StructuredInsight insight={baseInsight} />);
    expect(screen.getByText("Qué cambió")).toBeInTheDocument();
    expect(screen.getByText("Ver análisis completo")).toBeInTheDocument();
  });
});

describe("StructuredInsight — expansor", () => {
  it("es un botón real con aria-expanded=false y aria-controls apuntando a un id", () => {
    render(<StructuredInsight insight={baseInsight} />);
    const toggle = screen.getByRole("button", { name: /Ver análisis completo/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle.getAttribute("aria-controls")).toBeTruthy();
  });

  it("al activarlo con clic muestra 'Qué significa' y 'Próximas 2–4 semanas', y alterna el texto/aria-expanded", async () => {
    const user = userEvent.setup();
    render(<StructuredInsight insight={baseInsight} />);

    const toggle = screen.getByRole("button", { name: /Ver análisis completo/i });
    await user.click(toggle);

    expect(screen.getByText("Qué significa")).toBeInTheDocument();
    expect(screen.getByText(baseInsight.meaning[0])).toBeInTheDocument();
    expect(screen.getByText("Próximas 2–4 semanas")).toBeInTheDocument();
    expect(screen.getByText(baseInsight.next_weeks[0])).toBeInTheDocument();

    const toggleAfter = screen.getByRole("button", {
      name: /Ocultar análisis completo/i,
    });
    expect(toggleAfter).toBe(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    // El contenedor de detalles expuesto tiene el mismo id que aria-controls.
    const controlsId = toggle.getAttribute("aria-controls");
    expect(document.getElementById(controlsId as string)).toBe(
      screen.getByTestId("structured-insight-details"),
    );
  });

  it("un segundo clic vuelve a colapsar y saca 'Qué significa'/'Próximas 2–4 semanas' del árbol", async () => {
    const user = userEvent.setup();
    render(<StructuredInsight insight={baseInsight} />);

    const toggle = screen.getByRole("button", { name: /Ver análisis completo/i });
    await user.click(toggle);
    await user.click(
      screen.getByRole("button", { name: /Ocultar análisis completo/i }),
    );

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Qué significa")).not.toBeInTheDocument();
    expect(screen.queryByText("Próximas 2–4 semanas")).not.toBeInTheDocument();
  });

  it("es operable por teclado: foco por Tab + Enter lo expande", async () => {
    const user = userEvent.setup();
    render(<StructuredInsight insight={baseInsight} />);

    await user.tab();
    const toggle = screen.getByRole("button", { name: /Ver análisis completo/i });
    expect(toggle).toHaveFocus();

    await user.keyboard("{Enter}");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Qué significa")).toBeInTheDocument();
  });

  it("es operable por teclado: la barra espaciadora también lo expande", async () => {
    const user = userEvent.setup();
    render(<StructuredInsight insight={baseInsight} />);

    await user.tab();
    const toggle = screen.getByRole("button", { name: /Ver análisis completo/i });
    await user.keyboard(" ");

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Próximas 2–4 semanas")).toBeInTheDocument();
  });
});

describe("StructuredInsight — accesibilidad", () => {
  it("sin violaciones en el estado colapsado", async () => {
    const { container } = render(<StructuredInsight insight={withWarningsAndGaps} />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones en el estado expandido", async () => {
    const user = userEvent.setup();
    const { container } = render(<StructuredInsight insight={withWarningsAndGaps} />);
    await user.click(screen.getByRole("button", { name: /Ver análisis completo/i }));
    expect(await axe(container)).toHaveNoViolations();
  });
});
