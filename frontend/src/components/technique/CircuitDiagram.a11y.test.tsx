/**
 * Tests de accesibilidad WCAG 2.1 AA para CircuitDiagram (T013 — feature 019 Phase A, US1).
 *
 * BLOCKED ON T017: CircuitDiagram.tsx does not exist yet.
 * These tests define the accessibility contract the implementation must satisfy.
 * They will FAIL until T017 delivers the component.
 *
 * Verifica:
 *  1. role="img" está presente en el elemento <svg> raíz.
 *  2. <title> está presente y no es vacío (derivado de layout_alt / altText prop).
 *  3. <desc> está presente y no es vacío (FR-017 — text alternative).
 *  4. Cero violaciones de axe WCAG AA en todos los estados principales.
 *  5. Color no es el único canal diferenciador de kinds (FR-017):
 *     cada kind tiene un atributo SVG estructural distinto además del color
 *     (data-kind, shape, stroke-dasharray) — la leyenda en español refuerza.
 */

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { CircuitDiagram } from "./CircuitDiagram";
import type { GymkhanaLayout } from "@/types/technique.types";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Fixtures — datos ficticios (nunca PII de menores reales)
// ---------------------------------------------------------------------------

const EMPTY_LAYOUT: GymkhanaLayout = {
  width: 100,
  height: 80,
  elements: [],
};

const SINGLE_CONE_LAYOUT: GymkhanaLayout = {
  width: 100,
  height: 80,
  elements: [{ kind: "cone", x: 50, y: 40 }],
};

/** Layout with every kind — tests that all kinds coexist without a11y violations. */
const ALL_KINDS_LAYOUT: GymkhanaLayout = {
  width: 200,
  height: 160,
  elements: [
    { kind: "cone",  x: 10,  y: 10 },
    { kind: "line",  x: 30,  y: 10, style: "dashed" },
    { kind: "line",  x: 50,  y: 10, style: "solid" },
    { kind: "gate",  x: 70,  y: 10 },
    { kind: "mine",  x: 90,  y: 10 },
    { kind: "arrow", x: 110, y: 10, rotation: 45 },
    { kind: "beam",  x: 130, y: 10, rotation: 90 },
    { kind: "ring",  x: 150, y: 10 },
  ],
};

const ALT_TEXT = "Circuito ficticio de gymkhana: cono, slalom, llegada.";
const ALT_TEXT_FULL = "Circuito gymkhana ficticio completo: cono, trayecto libre, trayecto técnico, puerta, mina, flecha, equilibrio, círculo de la muerte.";

// ---------------------------------------------------------------------------
// Tests — atributos de accesibilidad estructurales
// ---------------------------------------------------------------------------

describe("CircuitDiagram — estructura accesible (role / title / desc)", () => {
  it("el <svg> raíz tiene role='img'", () => {
    const { container } = render(
      <CircuitDiagram layout={EMPTY_LAYOUT} altText={ALT_TEXT} />,
    );
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("role", "img");
  });

  it("contiene un <title> no vacío con el altText", () => {
    const { container } = render(
      <CircuitDiagram layout={SINGLE_CONE_LAYOUT} altText={ALT_TEXT} />,
    );
    const title = container.querySelector("svg title");
    expect(title).not.toBeNull();
    expect(title!.textContent?.trim().length).toBeGreaterThan(0);
    expect(title!.textContent).toContain(ALT_TEXT);
  });

  it("contiene un <desc> no vacío (alternativa textual completa, FR-017)", () => {
    const { container } = render(
      <CircuitDiagram layout={SINGLE_CONE_LAYOUT} altText={ALT_TEXT} />,
    );
    const desc = container.querySelector("svg desc");
    expect(desc).not.toBeNull();
    expect(desc!.textContent?.trim().length).toBeGreaterThan(0);
  });

  it("altText vacío → <title> contiene texto de fallback no vacío", () => {
    const { container } = render(
      <CircuitDiagram layout={SINGLE_CONE_LAYOUT} altText="" />,
    );
    const title = container.querySelector("svg title");
    expect(title).not.toBeNull();
    expect(title!.textContent?.trim().length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Tests — color NO es el único canal (FR-017)
// ---------------------------------------------------------------------------

describe("CircuitDiagram — diferenciación sin depender solo del color", () => {
  it("line dashed y line solid tienen stroke-dasharray solo en la variante guía", () => {
    const layout: GymkhanaLayout = {
      width: 100,
      height: 80,
      elements: [
        { kind: "line", x: 20, y: 40, style: "dashed" },
        { kind: "line", x: 60, y: 40, style: "solid" },
      ],
    };
    const { container } = render(
      <CircuitDiagram layout={layout} altText={ALT_TEXT} />,
    );
    // There must be at least one SVG element with stroke-dasharray (dashed line)
    const dashedEl = container.querySelector("[stroke-dasharray]");
    expect(dashedEl).not.toBeNull();
  });

  it("cada kind tiene un data-kind distinto (canal estructural, no solo color)", () => {
    const { container } = render(
      <CircuitDiagram layout={ALL_KINDS_LAYOUT} altText={ALT_TEXT_FULL} />,
    );
    const kinds = ["cone", "line", "gate", "mine", "arrow", "beam", "ring"];
    for (const kind of kinds) {
      const els = container.querySelectorAll(`[data-kind="${kind}"]`);
      expect(els.length, `kind="${kind}" debe tener al menos un elemento`).toBeGreaterThanOrEqual(1);
    }
  });
});

// ---------------------------------------------------------------------------
// Tests — axe WCAG 2.1 AA (sin violaciones)
// ---------------------------------------------------------------------------

describe("CircuitDiagram — cero violaciones axe WCAG 2.1 AA", () => {
  it("layout vacío → sin violaciones de accesibilidad", async () => {
    const { container } = render(
      <CircuitDiagram layout={EMPTY_LAYOUT} altText={ALT_TEXT} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("layout con cono único → sin violaciones", async () => {
    const { container } = render(
      <CircuitDiagram layout={SINGLE_CONE_LAYOUT} altText={ALT_TEXT} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("layout con todos los kinds → sin violaciones", async () => {
    const { container } = render(
      <CircuitDiagram layout={ALL_KINDS_LAYOUT} altText={ALT_TEXT_FULL} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("layout con rotaciones → sin violaciones", async () => {
    const rotatedLayout: GymkhanaLayout = {
      width: 100,
      height: 80,
      elements: [
        { kind: "arrow", x: 30, y: 30, rotation: 45 },
        { kind: "gate",  x: 60, y: 30, rotation: 90 },
        { kind: "cone",  x: 80, y: 60, rotation: 180 },
      ],
    };
    const { container } = render(
      <CircuitDiagram layout={rotatedLayout} altText={ALT_TEXT} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
