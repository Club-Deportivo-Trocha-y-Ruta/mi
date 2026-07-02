/**
 * Tests para AgeBandGuardrailDialog (US3 / T032):
 *   - Renderiza el mensaje de explicación con el nombre del ejercicio y las
 *     franjas de edad involucradas.
 *   - "Cancelar" llama a onOpenChange(false) y NO llama a onConfirmOverride.
 *   - "Confirmar anulación" llama a onConfirmOverride con la nota capturada
 *     (o null si se deja vacía).
 *   - isPending=true deshabilita ambos botones y el textarea.
 *   - a11y: jest-axe sin violaciones.
 *
 * Mirror de `components/technique/__tests__/ExerciseFormDialog.test.tsx` (feature 018)
 * para el uso del API de Dialog de shadcn/ui en tests.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { AgeBandGuardrailDialog } from "../AgeBandGuardrailDialog";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface OverrideProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  exerciseName?: string;
  exerciseAgeBands?: ("10-12" | "13-15")[];
  targetAgeBand?: "10-12" | "13-15";
  onConfirmOverride?: (overrideNote: string | null) => void;
  isPending?: boolean;
}

function renderDialog(overrides: OverrideProps = {}) {
  const props = {
    open: true,
    onOpenChange: vi.fn(),
    exerciseName: "Press Ficticio",
    exerciseAgeBands: ["13-15"] as ("10-12" | "13-15")[],
    targetAgeBand: "10-12" as const,
    onConfirmOverride: vi.fn(),
    isPending: false,
    ...overrides,
  };
  return {
    ...render(<AgeBandGuardrailDialog {...props} />),
    onOpenChange: props.onOpenChange,
    onConfirmOverride: props.onConfirmOverride,
  };
}

// ---------------------------------------------------------------------------
// Suite: contenido
// ---------------------------------------------------------------------------

describe("AgeBandGuardrailDialog — contenido", () => {
  it("muestra el título y el nombre del ejercicio en la descripción", () => {
    renderDialog();
    expect(
      screen.getByRole("heading", { name: "Ejercicio fuera de la franja de edad" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Press Ficticio")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: Cancelar
// ---------------------------------------------------------------------------

describe("AgeBandGuardrailDialog — cancelar", () => {
  it("clicar 'Cancelar' llama a onOpenChange(false) y no a onConfirmOverride", async () => {
    const user = userEvent.setup();
    const { onOpenChange, onConfirmOverride } = renderDialog();

    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onConfirmOverride).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Suite: Confirmar anulación
// ---------------------------------------------------------------------------

describe("AgeBandGuardrailDialog — confirmar anulación", () => {
  it("clicar 'Confirmar anulación' sin nota llama a onConfirmOverride(null)", async () => {
    const user = userEvent.setup();
    const { onConfirmOverride } = renderDialog();

    await user.click(screen.getByRole("button", { name: "Confirmar anulación" }));

    expect(onConfirmOverride).toHaveBeenCalledWith(null);
  });

  it("clicar 'Confirmar anulación' con nota capturada la pasa recortada", async () => {
    const user = userEvent.setup();
    const { onConfirmOverride } = renderDialog();

    await user.type(
      screen.getByLabelText("Nota de anulación (opcional)"),
      "  Atleta con buen dominio técnico  ",
    );
    await user.click(screen.getByRole("button", { name: "Confirmar anulación" }));

    expect(onConfirmOverride).toHaveBeenCalledWith("Atleta con buen dominio técnico");
  });
});

// ---------------------------------------------------------------------------
// Suite: isPending
// ---------------------------------------------------------------------------

describe("AgeBandGuardrailDialog — isPending", () => {
  it("deshabilita 'Cancelar', 'Confirmar anulación' y el textarea cuando isPending=true", () => {
    renderDialog({ isPending: true });

    expect(screen.getByRole("button", { name: "Cancelar" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Confirmar anulación" }),
    ).toBeDisabled();
    expect(
      screen.getByLabelText("Nota de anulación (opcional)"),
    ).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("AgeBandGuardrailDialog — accesibilidad", () => {
  it("no tiene violaciones de a11y", async () => {
    const { container } = renderDialog();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y con isPending=true", async () => {
    const { container } = renderDialog({ isPending: true });
    expect(await axe(container)).toHaveNoViolations();
  });
});
