/**
 * Composer.a11y.test.tsx — accessibility test for the keyboard/screen-reader
 * fallback control set (T027, FR-018, WCAG 2.1 AA).
 *
 * AccessibleControls is the DOM-only path mandated by FR-018: drag-and-drop
 * (KonvaCanvas/react-konva, which jsdom cannot render) MUST NOT be the only
 * way to add/position/remove circuit elements. These tests render
 * AccessibleControls in isolation (no Konva, no canvas) and verify:
 *
 *   1. Zero axe WCAG AA violations across the main states (empty, with
 *      elements, with a selection, with the line-style controls visible).
 *   2. Add / select / nudge / rotate / remove are all reachable and
 *      operable via keyboard (real <button>/<select>/<ul role="listbox">
 *      semantics — tab order + Enter/Space activation + arrow-key list
 *      navigation), independent of any pointer drag.
 */

import { useEffect, useState } from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { AccessibleControls } from "./AccessibleControls";
import type { ComposedElement } from "./KonvaCanvas";
import { CANVAS_W, CANVAS_H } from "@/routes/technique/ComposerPage";
import type { CircuitElementKind } from "@/types/technique.types";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Harness — identical shape to the one in Composer.roundtrip.test.tsx, kept
// local/minimal so this file can run standalone against just the a11y path.
// ---------------------------------------------------------------------------

function Harness({
  initialElements = [],
  onElementsChange,
}: {
  initialElements?: ComposedElement[];
  onElementsChange?: (els: ComposedElement[]) => void;
}) {
  const [elements, setElements] = useState<ComposedElement[]>(initialElements);
  const [selectedId, setSelectedId] = useState<string | null>(
    initialElements[0]?._id ?? null,
  );

  useEffect(() => {
    onElementsChange?.(elements);
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

describe("AccessibleControls a11y (T027, FR-018)", () => {
  it("has zero axe violations when empty", async () => {
    const { container } = render(<Harness />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("has zero axe violations with elements and an active selection (incl. line-style + label controls)", async () => {
    const lineEl: ComposedElement = {
      _id: "line-1",
      kind: "line",
      x: 30,
      y: 20,
      rotation: 0,
      style: "dashed",
      label: "Salida",
    };
    const { container } = render(<Harness initialElements={[lineEl]} />);
    // Selected-element panel (nudge/rotate/style/label/remove) is visible.
    expect(screen.getByText(/Elemento seleccionado/)).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("supports the full add → select → nudge → rotate → remove flow via keyboard only", async () => {
    const user = userEvent.setup();
    let lastElements: ComposedElement[] = [];
    render(<Harness onElementsChange={(els) => (lastElements = els)} />);

    // Tab from body into the picker, then activate "+ Agregar" via keyboard.
    await user.tab(); // kind <select>
    expect(screen.getByLabelText("Tipo de elemento")).toHaveFocus();
    await user.tab(); // "+ Agregar" button
    const addButton = screen.getByRole("button", { name: "+ Agregar" });
    expect(addButton).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(lastElements).toHaveLength(1);

    // Nudge via keyboard activation (Space) on the directional buttons.
    const rightBtn = screen.getByRole("button", { name: "Mover a la derecha" });
    rightBtn.focus();
    await user.keyboard(" ");
    expect(lastElements[0].x).toBe(22);

    // Rotate via keyboard.
    const rotateBtn = screen.getByRole("button", { name: "Rotar 15 grados horario" });
    rotateBtn.focus();
    await user.keyboard("{Enter}");
    expect(lastElements[0].rotation).toBe(15);

    // Remove via keyboard.
    const removeBtn = screen.getByRole("button", { name: /Eliminar elemento/ });
    removeBtn.focus();
    await user.keyboard("{Enter}");
    expect(lastElements).toHaveLength(0);
  });

  it("exposes the element list as a keyboard-navigable listbox (arrow keys move selection)", async () => {
    const user = userEvent.setup();
    const els: ComposedElement[] = [
      { _id: "a", kind: "cone", x: 10, y: 10, rotation: 0 },
      { _id: "b", kind: "gate", x: 20, y: 20, rotation: 0 },
    ];
    let selected: string | null = "a";
    function ListHarness() {
      const [elements] = useState(els);
      const [selectedId, setSelectedId] = useState<string | null>("a");
      selected = selectedId;
      return (
        <AccessibleControls
          elements={elements}
          selectedId={selectedId}
          canvasWidth={CANVAS_W}
          canvasHeight={CANVAS_H}
          onSelect={setSelectedId}
          onAdd={() => {}}
          onChange={() => {}}
          onRemove={() => {}}
        />
      );
    }
    render(<ListHarness />);

    const listbox = screen.getByRole("listbox");
    listbox.focus();
    await user.keyboard("{ArrowDown}");
    expect(selected).toBe("b");
    await user.keyboard("{ArrowUp}");
    expect(selected).toBe("a");
  });

  it("never prompts for an athlete's name (no name/DOB field exists in the control set)", () => {
    render(<Harness initialElements={[{ _id: "c", kind: "cone", x: 10, y: 10, rotation: 0 }]} />);
    // The only free-text field is the generic, optional, non-PII "label".
    const textInputs = screen.getAllByRole("textbox");
    expect(textInputs).toHaveLength(1);
    expect(textInputs[0]).toHaveAccessibleName(/Etiqueta del elemento/);
    expect(textInputs[0]).not.toHaveAccessibleName(/nombre del (atleta|deportista)/i);
    expect(screen.queryByLabelText(/fecha de nacimiento/i)).not.toBeInTheDocument();
  });
});
