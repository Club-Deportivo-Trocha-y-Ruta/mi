/**
 * Tests para AgeGateDialog (feature 026, T014):
 *   - Modo "confirmation" (`age_gate_confirmation_required`, FR-007): título +
 *     mensaje por defecto con la franja de edad, CTA "Confirmar estructura" y
 *     "Cancelar". "Cancelar" cierra sin confirmar; "Confirmar estructura"
 *     llama a onConfirm.
 *   - Modo "blocked" (`age_gate_z3_blocked`, FR-006): título + mensaje de
 *     bloqueo duro, lista las posiciones afectadas (singular/plural), un único
 *     botón "Entendido" que cierra — nunca hay CTA de anulación.
 *   - `message` del backend sobreescribe el mensaje por defecto en ambos modos.
 *   - `isPending`: deshabilita los botones de "confirmation" y evita el cierre
 *     mientras el reintento está en curso (el botón "Cerrar" de Radix no debe
 *     disparar onOpenChange).
 *   - a11y: jest-axe sin violaciones en ambos modos y con isPending=true.
 *
 * Mirror de `components/strength/__tests__/AgeBandGuardrailDialog.test.tsx`.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { AgeGateDialog, type AgeGateDialogProps } from "../AgeGateDialog";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderDialog(overrides: Partial<AgeGateDialogProps> = {}) {
  const props: AgeGateDialogProps = {
    open: true,
    onOpenChange: vi.fn(),
    mode: "confirmation",
    targetAgeBand: "10-12",
    onConfirm: vi.fn(),
    isPending: false,
    ...overrides,
  };
  return {
    ...render(<AgeGateDialog {...props} />),
    onOpenChange: props.onOpenChange,
    onConfirm: props.onConfirm,
  };
}

// ---------------------------------------------------------------------------
// Suite: modo "confirmation" (FR-007)
// ---------------------------------------------------------------------------

describe("AgeGateDialog — modo confirmation", () => {
  it("muestra el título y el mensaje por defecto con la franja de edad", () => {
    renderDialog({ targetAgeBand: "10-12" });

    expect(
      screen.getByRole("heading", {
        name: "Confirmá la estructura para esta categoría",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Esta estructura es para la categoría 10 a 12 años. Confirmá explícitamente antes de guardarla.",
      ),
    ).toBeInTheDocument();
  });

  it("el mensaje del backend sobreescribe el mensaje por defecto", () => {
    renderDialog({ message: "Mensaje personalizado del servidor." });

    expect(
      screen.getByText("Mensaje personalizado del servidor."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        /Confirmá explícitamente antes de guardarla/,
      ),
    ).not.toBeInTheDocument();
  });

  it("muestra los botones 'Cancelar' y 'Confirmar estructura'", () => {
    renderDialog();

    expect(screen.getByRole("button", { name: "Cancelar" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Confirmar estructura" }),
    ).toBeInTheDocument();
  });

  it("'Cancelar' llama a onOpenChange(false) y no a onConfirm", async () => {
    const user = userEvent.setup();
    const { onOpenChange, onConfirm } = renderDialog();

    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("'Confirmar estructura' llama a onConfirm", async () => {
    const user = userEvent.setup();
    const { onConfirm } = renderDialog();

    await user.click(screen.getByRole("button", { name: "Confirmar estructura" }));

    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("isPending=true deshabilita 'Cancelar' y 'Confirmar estructura'", () => {
    renderDialog({ isPending: true });

    expect(screen.getByRole("button", { name: "Cancelar" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Confirmar estructura" }),
    ).toBeDisabled();
  });

  it("isPending=true evita el cierre vía el botón 'Cerrar' de Radix", async () => {
    const user = userEvent.setup();
    const { onOpenChange } = renderDialog({ isPending: true });

    await user.click(screen.getByRole("button", { name: "Cerrar" }));

    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it("sin isPending, el botón 'Cerrar' de Radix sí llama a onOpenChange(false)", async () => {
    const user = userEvent.setup();
    const { onOpenChange } = renderDialog({ isPending: false });

    await user.click(screen.getByRole("button", { name: "Cerrar" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("con targetAgeBand '13-15' usa la etiqueta correspondiente", () => {
    renderDialog({ targetAgeBand: "13-15" });

    expect(
      screen.getByText(
        "Esta estructura es para la categoría 13 a 15 años. Confirmá explícitamente antes de guardarla.",
      ),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: modo "blocked" (FR-006, bloqueo duro sin override)
// ---------------------------------------------------------------------------

describe("AgeGateDialog — modo blocked", () => {
  it("muestra el título y el mensaje de bloqueo duro por defecto", () => {
    renderDialog({ mode: "blocked", targetAgeBand: "10-12" });

    expect(
      screen.getByRole("heading", {
        name: "Intensidad no permitida para esta categoría",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Intensidad Z3 o superior no está disponible para la categoría 10 a 12 años.",
      ),
    ).toBeInTheDocument();
  });

  it("solo muestra el botón 'Entendido' — sin CTA de anulación", () => {
    renderDialog({ mode: "blocked" });

    expect(screen.getByRole("button", { name: "Entendido" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Confirmar/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Cancelar" }),
    ).not.toBeInTheDocument();
  });

  it("'Entendido' llama a onOpenChange(false)", async () => {
    const user = userEvent.setup();
    const { onOpenChange } = renderDialog({ mode: "blocked" });

    await user.click(screen.getByRole("button", { name: "Entendido" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("sin posiciones, no muestra el párrafo de bloques a ajustar", () => {
    renderDialog({ mode: "blocked" });

    expect(screen.queryByText(/Ajustá la zona/)).not.toBeInTheDocument();
  });

  it("con una posición, usa singular 'el bloque'", () => {
    renderDialog({ mode: "blocked", positions: [2] });

    const paragraph = screen.getByText(/Ajustá la zona de/).closest("p")!;
    expect(paragraph.textContent).toContain("el bloque");
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("con varias posiciones, usa plural 'los bloques' y las une con coma", () => {
    renderDialog({ mode: "blocked", positions: [2, 4] });

    const paragraph = screen.getByText(/Ajustá la zona de/).closest("p")!;
    expect(paragraph.textContent).toContain("los bloques");
    expect(screen.getByText("2, 4")).toBeInTheDocument();
  });

  it("el mensaje del backend sobreescribe el mensaje de bloqueo por defecto", () => {
    renderDialog({
      mode: "blocked",
      message: "Zona Z4 detectada en el bloque 3.",
    });

    expect(
      screen.getByText("Zona Z4 detectada en el bloque 3."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Intensidad Z3 o superior no está disponible/),
    ).not.toBeInTheDocument();
  });

  it("isPending no afecta al modo blocked: 'Entendido' sigue habilitado", () => {
    renderDialog({ mode: "blocked", isPending: true });

    expect(screen.getByRole("button", { name: "Entendido" })).not.toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("AgeGateDialog — accesibilidad", () => {
  it("no tiene violaciones de a11y en modo confirmation", async () => {
    const { container } = renderDialog({ mode: "confirmation" });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y en modo confirmation con isPending=true", async () => {
    const { container } = renderDialog({ mode: "confirmation", isPending: true });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y en modo blocked", async () => {
    const { container } = renderDialog({ mode: "blocked", positions: [1, 3] });
    expect(await axe(container)).toHaveNoViolations();
  });
});
