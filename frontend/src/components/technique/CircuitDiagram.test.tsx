/**
 * Tests para CircuitDiagram (T012 — feature 019 Phase A, US1).
 *
 * BLOCKED ON T017: CircuitDiagram.tsx does not exist yet.
 * These tests define the SVG contract the implementation must satisfy.
 * They will FAIL until T017 delivers the component.
 *
 * Contract asserted here:
 *  - Renders an <svg> with role="img".
 *  - Each element kind renders a visually distinct SVG primitive identified
 *    by a data-kind attribute on the element group.
 *  - Rotation is applied via a CSS/SVG transform on the element group
 *    (non-zero rotation → transform attribute present and containing the angle).
 *  - Empty layout (zero elements) → renders the SVG shell without crashing.
 *  - Unknown kind values are never present (schema strips them before render).
 *
 * Primitive contract per kind (from spec FR-002 / data-model.md):
 *  cone  → triangle (polygon or path)
 *  line  → path/line; dashed style → stroke-dasharray attribute
 *  gate  → two-post pass-through shape (rect/rect pair or g)
 *  mine  → obstacle marker (circle or X path)
 *  arrow → directional arrow (path with arrowhead / polygon)
 *  beam  → horizontal balance beam (rect wider than tall)
 *  ring  → circle outline (circle element, no fill or light fill)
 */

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { CircuitDiagram } from "./CircuitDiagram";
import type { GymkhanaLayout } from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/** Minimal layout for single-element tests. */
function singleElement(overrides: Partial<GymkhanaLayout["elements"][number]>): GymkhanaLayout {
  return {
    width: 100,
    height: 80,
    elements: [
      { kind: "cone", x: 50, y: 40, ...overrides },
    ],
  };
}

/** Layout with one element of every kind. */
const ALL_KINDS_LAYOUT: GymkhanaLayout = {
  width: 200,
  height: 160,
  elements: [
    { kind: "cone",  x: 10, y: 10 },
    { kind: "line",  x: 30, y: 10, style: "dashed" },
    { kind: "line",  x: 50, y: 10, style: "solid" },
    { kind: "gate",  x: 70, y: 10 },
    { kind: "mine",  x: 90, y: 10 },
    { kind: "arrow", x: 110, y: 10 },
    { kind: "beam",  x: 130, y: 10 },
    { kind: "ring",  x: 150, y: 10 },
  ],
};

const EMPTY_LAYOUT: GymkhanaLayout = {
  width: 100,
  height: 80,
  elements: [],
};

const ALT_TEXT = "Circuito ficticio de gymkhana: cono, slalom, llegada.";

// ---------------------------------------------------------------------------
// Helper: query all elements carrying data-kind inside the container
// ---------------------------------------------------------------------------

function getElementsByKind(container: HTMLElement, kind: string): Element[] {
  return Array.from(container.querySelectorAll(`[data-kind="${kind}"]`));
}

// ---------------------------------------------------------------------------
// Tests — SVG shell
// ---------------------------------------------------------------------------

describe("CircuitDiagram — SVG shell", () => {
  it("renderiza un elemento <svg> con role='img'", () => {
    const { container } = render(
      <CircuitDiagram layout={EMPTY_LAYOUT} altText={ALT_TEXT} />,
    );
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("role", "img");
  });

  it("el <svg> contiene un <title> con el altText proporcionado", () => {
    const { container } = render(
      <CircuitDiagram layout={EMPTY_LAYOUT} altText={ALT_TEXT} />,
    );
    const title = container.querySelector("svg > title, svg title");
    expect(title).not.toBeNull();
    expect(title!.textContent).toBe(ALT_TEXT);
  });

  it("layout vacío (cero elementos) no arroja error y renderiza el SVG", () => {
    expect(() =>
      render(<CircuitDiagram layout={EMPTY_LAYOUT} altText={ALT_TEXT} />),
    ).not.toThrow();
    // no elements expected
  });
});

// ---------------------------------------------------------------------------
// Tests — primitive per kind
// ---------------------------------------------------------------------------

describe("CircuitDiagram — primitiva SVG por kind", () => {
  it("kind='cone' renderiza un elemento con data-kind='cone'", () => {
    const { container } = render(
      <CircuitDiagram layout={singleElement({ kind: "cone" })} altText={ALT_TEXT} />,
    );
    expect(getElementsByKind(container, "cone").length).toBeGreaterThanOrEqual(1);
  });

  it("kind='line' con style='dashed' renderiza data-kind='line' con stroke-dasharray", () => {
    const { container } = render(
      <CircuitDiagram
        layout={singleElement({ kind: "line", style: "dashed" })}
        altText={ALT_TEXT}
      />,
    );
    const lineEls = getElementsByKind(container, "line");
    expect(lineEls.length).toBeGreaterThanOrEqual(1);
    // The dashed path or a descendant must have a stroke-dasharray attribute
    const hasDashArray = lineEls.some((el) => {
      // Check element itself or its SVG children
      if (el.hasAttribute("stroke-dasharray")) return true;
      return el.querySelector("[stroke-dasharray]") !== null;
    });
    expect(hasDashArray).toBe(true);
  });

  it("kind='line' con style='solid' renderiza data-kind='line' sin stroke-dasharray", () => {
    const { container } = render(
      <CircuitDiagram
        layout={singleElement({ kind: "line", style: "solid" })}
        altText={ALT_TEXT}
      />,
    );
    const lineEls = getElementsByKind(container, "line");
    expect(lineEls.length).toBeGreaterThanOrEqual(1);
    // Solid lines must NOT have a dashed stroke
    const hasDashArray = lineEls.some((el) => {
      if (el.getAttribute("stroke-dasharray")) return true;
      return el.querySelector("[stroke-dasharray]") !== null;
    });
    expect(hasDashArray).toBe(false);
  });

  it("kind='gate' renderiza un elemento con data-kind='gate'", () => {
    const { container } = render(
      <CircuitDiagram layout={singleElement({ kind: "gate" })} altText={ALT_TEXT} />,
    );
    expect(getElementsByKind(container, "gate").length).toBeGreaterThanOrEqual(1);
  });

  it("kind='mine' renderiza un elemento con data-kind='mine'", () => {
    const { container } = render(
      <CircuitDiagram layout={singleElement({ kind: "mine" })} altText={ALT_TEXT} />,
    );
    expect(getElementsByKind(container, "mine").length).toBeGreaterThanOrEqual(1);
  });

  it("kind='arrow' renderiza un elemento con data-kind='arrow'", () => {
    const { container } = render(
      <CircuitDiagram layout={singleElement({ kind: "arrow" })} altText={ALT_TEXT} />,
    );
    expect(getElementsByKind(container, "arrow").length).toBeGreaterThanOrEqual(1);
  });

  it("kind='beam' renderiza un elemento con data-kind='beam'", () => {
    const { container } = render(
      <CircuitDiagram layout={singleElement({ kind: "beam" })} altText={ALT_TEXT} />,
    );
    expect(getElementsByKind(container, "beam").length).toBeGreaterThanOrEqual(1);
  });

  it("kind='ring' renderiza un elemento con data-kind='ring'", () => {
    const { container } = render(
      <CircuitDiagram layout={singleElement({ kind: "ring" })} altText={ALT_TEXT} />,
    );
    expect(getElementsByKind(container, "ring").length).toBeGreaterThanOrEqual(1);
  });

  it("layout con todos los kinds renderiza exactamente un data-kind por instancia", () => {
    const { container } = render(
      <CircuitDiagram layout={ALL_KINDS_LAYOUT} altText={ALT_TEXT} />,
    );
    // cone × 1, line × 2, gate × 1, mine × 1, arrow × 1, beam × 1, ring × 1
    expect(getElementsByKind(container, "cone").length).toBe(1);
    expect(getElementsByKind(container, "line").length).toBe(2);
    expect(getElementsByKind(container, "gate").length).toBe(1);
    expect(getElementsByKind(container, "mine").length).toBe(1);
    expect(getElementsByKind(container, "arrow").length).toBe(1);
    expect(getElementsByKind(container, "beam").length).toBe(1);
    expect(getElementsByKind(container, "ring").length).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// Tests — rotación
// ---------------------------------------------------------------------------

describe("CircuitDiagram — rotación aplicada", () => {
  it("rotation=0 → el elemento no tiene transform de rotación significativo", () => {
    const { container } = render(
      <CircuitDiagram
        layout={singleElement({ kind: "cone", rotation: 0 })}
        altText={ALT_TEXT}
      />,
    );
    const coneGroup = getElementsByKind(container, "cone")[0];
    expect(coneGroup).toBeDefined();
    // transform may be absent or contain rotate(0) — both are acceptable
    const transform = coneGroup?.getAttribute("transform") ?? "";
    // If it has rotate, it must be rotate(0 ...) — no non-trivial rotation
    if (transform.includes("rotate")) {
      expect(transform).toMatch(/rotate\(\s*0/);
    }
  });

  it("rotation=45 → el elemento lleva transform con rotate(45)", () => {
    const { container } = render(
      <CircuitDiagram
        layout={singleElement({ kind: "cone", rotation: 45 })}
        altText={ALT_TEXT}
      />,
    );
    const coneGroup = getElementsByKind(container, "cone")[0];
    expect(coneGroup).toBeDefined();
    const transform = coneGroup?.getAttribute("transform") ?? "";
    // The transform must encode a 45-degree rotation
    expect(transform).toMatch(/rotate\(\s*45/);
  });

  it("rotation=90 → el elemento lleva transform con rotate(90)", () => {
    const { container } = render(
      <CircuitDiagram
        layout={singleElement({ kind: "arrow", rotation: 90 })}
        altText={ALT_TEXT}
      />,
    );
    const arrowGroup = getElementsByKind(container, "arrow")[0];
    expect(arrowGroup).toBeDefined();
    const transform = arrowGroup?.getAttribute("transform") ?? "";
    expect(transform).toMatch(/rotate\(\s*90/);
  });

  it("rotation=180 → el elemento lleva transform con rotate(180)", () => {
    const { container } = render(
      <CircuitDiagram
        layout={singleElement({ kind: "gate", rotation: 180 })}
        altText={ALT_TEXT}
      />,
    );
    const gateGroup = getElementsByKind(container, "gate")[0];
    expect(gateGroup).toBeDefined();
    const transform = gateGroup?.getAttribute("transform") ?? "";
    expect(transform).toMatch(/rotate\(\s*180/);
  });

  it("rotation ausente → se aplica la misma lógica que rotation=0", () => {
    // rotation is optional (default 0); should not crash
    const { container } = render(
      <CircuitDiagram
        layout={singleElement({ kind: "cone" })} // no rotation key
        altText={ALT_TEXT}
      />,
    );
    expect(getElementsByKind(container, "cone").length).toBeGreaterThanOrEqual(1);
  });
});
