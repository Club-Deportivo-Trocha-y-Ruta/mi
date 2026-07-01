/**
 * Composer.roundtrip.test.tsx — data-layer round-trip test for the Phase B
 * composer (T026, SC-006, O-6).
 *
 * jsdom does not implement <canvas>, so react-konva/Konva is never rendered
 * here — KonvaCanvas.tsx is NOT imported. Instead this test exercises the
 * SAME data path the composer actually persists through:
 *
 *   AccessibleControls (non-drag fallback) → ComposedElement[] state
 *     → toGymkhanaLayout() → JSON.stringify (network boundary)
 *     → JSON.parse → fromGymkhanaLayout() → ComposedElement[] state
 *     → toGymkhanaLayout() again
 *
 * and asserts the two GymkhanaLayouts are equivalent (elements, positions,
 * rotations, styles, labels — order preserved), then renders the
 * re-hydrated layout through the read-only <CircuitDiagram> to confirm it
 * accepts the round-tripped data without error (FR-012).
 */

import { useEffect, useState } from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AccessibleControls } from "./AccessibleControls";
import { validatePhaseBLabel } from "./piiGuard";
import type { ComposedElement } from "./KonvaCanvas";
import { CircuitDiagram } from "@/components/technique/CircuitDiagram";
import {
  CANVAS_W,
  CANVAS_H,
  toGymkhanaLayout,
  fromGymkhanaLayout,
} from "@/routes/technique/ComposerPage";
import type { CircuitElementKind, GymkhanaLayout } from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Test harness — mirrors ComposerPage's element-management callbacks without
// pulling in TanStack Query / routing / KonvaCanvas.
// ---------------------------------------------------------------------------

function Harness({
  onLayoutChange,
}: {
  onLayoutChange: (layout: GymkhanaLayout) => void;
}) {
  const [elements, setElements] = useState<ComposedElement[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    onLayoutChange(toGymkhanaLayout(elements));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [elements]);

  function handleAdd(kind: CircuitElementKind) {
    const el: ComposedElement = {
      _id: `${kind}-${elements.length}-${Math.random().toString(36).slice(2)}`,
      kind,
      x: 20,
      y: 15,
      rotation: 0,
      style: kind === "line" ? "dashed" : undefined,
    };
    setElements((prev) => [...prev, el]);
    setSelectedId(el._id);
  }

  function handleChange(
    id: string,
    updates: Partial<Omit<ComposedElement, "_id" | "kind">>,
  ) {
    setElements((prev) =>
      prev.map((el) => (el._id === id ? { ...el, ...updates } : el)),
    );
  }

  function handleRemove(id: string) {
    setElements((prev) => prev.filter((el) => el._id !== id));
    if (selectedId === id) setSelectedId(null);
  }

  return (
    <AccessibleControls
      elements={elements}
      selectedId={selectedId}
      canvasWidth={CANVAS_W}
      canvasHeight={CANVAS_H}
      onSelect={setSelectedId}
      onAdd={handleAdd}
      onChange={handleChange}
      onRemove={handleRemove}
    />
  );
}

// ---------------------------------------------------------------------------

describe("Composer round-trip (T026, SC-006)", () => {
  let latestLayout: GymkhanaLayout = { width: CANVAS_W, height: CANVAS_H, elements: [] };

  beforeEach(() => {
    latestLayout = { width: CANVAS_W, height: CANVAS_H, elements: [] };
  });

  it("preserves elements/positions/rotations/labels through a full save→reload cycle", async () => {
    const user = userEvent.setup();
    render(<Harness onLayoutChange={(l) => (latestLayout = l)} />);

    // ── Add a cone (default kind) ──
    await user.click(screen.getByRole("button", { name: "+ Agregar" }));

    // Nudge it twice right, once down (2-unit steps).
    await user.click(screen.getByRole("button", { name: "Mover a la derecha" }));
    await user.click(screen.getByRole("button", { name: "Mover a la derecha" }));
    await user.click(screen.getByRole("button", { name: "Mover abajo" }));

    // Rotate it.
    await user.click(screen.getByRole("button", { name: "Rotar 15 grados horario" }));
    await user.click(screen.getByRole("button", { name: "Rotar 15 grados horario" }));

    // Give it a safe (non-PII) label.
    await user.type(screen.getByLabelText(/Etiqueta del elemento/), "Salida");

    // ── Add a second element: a line, switch it to the "solid" style ──
    await user.selectOptions(screen.getByLabelText("Tipo de elemento"), "line");
    await user.click(screen.getByRole("button", { name: "+ Agregar" }));
    await user.click(screen.getByRole("button", { name: "Técnico (────)" }));

    // Sanity: two elements are listed.
    expect(screen.getByText(/Elementos en el circuito \(2\)/)).toBeInTheDocument();

    const layoutBeforeSave = latestLayout;
    expect(layoutBeforeSave.elements).toHaveLength(2);

    // ── Simulate the save→network→reload boundary ──
    const serialized = JSON.stringify(layoutBeforeSave);
    const parsed = JSON.parse(serialized) as GymkhanaLayout;
    const reHydratedElements = fromGymkhanaLayout(parsed);
    const layoutAfterReload = toGymkhanaLayout(reHydratedElements);

    // Equivalent in content (order, kind, x, y, rotation, style, label) —
    // only the internal _id differs (re-generated on reload), which
    // toGymkhanaLayout strips out, so the comparison is on layout shape only.
    expect(layoutAfterReload).toEqual(layoutBeforeSave);
    expect(layoutAfterReload.width).toBe(CANVAS_W);
    expect(layoutAfterReload.height).toBe(CANVAS_H);

    const [cone, line] = layoutAfterReload.elements;
    expect(cone).toMatchObject({ kind: "cone", x: 24, y: 17, rotation: 30, label: "Salida" });
    expect(line).toMatchObject({ kind: "line", style: "solid" });

    // ── The re-hydrated layout renders cleanly through the read-only renderer ──
    const { container } = render(
      <CircuitDiagram
        layout={layoutAfterReload}
        altText="Circuito combinado ficticio de prueba"
      />,
    );
    const svg = container.querySelector('svg[role="img"]');
    expect(svg).not.toBeNull();
    expect(within(container).getByText("Circuito combinado ficticio de prueba")).toBeInTheDocument();
  });

  it("round-trips an empty layout (no elements) without error", () => {
    const layout: GymkhanaLayout = { width: CANVAS_W, height: CANVAS_H, elements: [] };
    const reHydrated = toGymkhanaLayout(fromGymkhanaLayout(JSON.parse(JSON.stringify(layout))));
    expect(reHydrated).toEqual(layout);
  });

  it("removing an element before save is reflected in the persisted layout (no ghost elements)", async () => {
    const user = userEvent.setup();
    render(<Harness onLayoutChange={(l) => (latestLayout = l)} />);

    await user.click(screen.getByRole("button", { name: "+ Agregar" })); // cone #1
    await user.click(screen.getByRole("button", { name: "+ Agregar" })); // cone #2 (auto-selected)

    expect(latestLayout.elements).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: /Eliminar elemento/ }));

    expect(latestLayout.elements).toHaveLength(1);

    const roundTripped = toGymkhanaLayout(
      fromGymkhanaLayout(JSON.parse(JSON.stringify(latestLayout))),
    );
    expect(roundTripped.elements).toHaveLength(1);
  });

  it("rejects a PII-looking label client-side and never lets the full name reach the layout", async () => {
    const user = userEvent.setup();
    render(<Harness onLayoutChange={(l) => (latestLayout = l)} />);

    await user.click(screen.getByRole("button", { name: "+ Agregar" }));
    const labelInput = screen.getByLabelText(/Etiqueta del elemento/);
    await user.type(labelInput, "Juan Perez");

    // The guard runs on every keystroke: a two-capitalized-word value is
    // never committed to layout state, so the full "Juan Perez" name can
    // never round-trip into a saved diagram (FR-019).
    expect(screen.getByRole("alert")).toHaveTextContent(/nombre/i);
    expect(latestLayout.elements[0].label).not.toBe("Juan Perez");
    // validatePhaseBLabel itself confirms the committed value is still safe
    // (no two-capitalized-word person-name pattern slipped through).
    expect(validatePhaseBLabel(latestLayout.elements[0].label ?? "")).toBeNull();
  });
});
