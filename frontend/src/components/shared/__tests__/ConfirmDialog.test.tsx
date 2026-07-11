/**
 * Tests para ConfirmDialog (specs/028-frontend-design-foundation, T011):
 *   - Contenido: title, description, etiquetas por defecto/personalizadas.
 *   - Foco inicial: tone="danger" enfoca Cancelar (no Confirmar) al abrir —
 *     es la regresión que corrige el autoFocus fijo en Confirmar de
 *     ConfirmModal/ConfirmDeleteDialog (common/ConfirmModal.tsx:66).
 *   - Cierre: Escape y clic en Cancelar llaman a onCancel.
 *   - Confirmar: clic llama a onConfirm y NO a onCancel (AlertDialogAction es
 *     un Close de Radix por construcción — sin preventDefault se dispararían
 *     ambos callbacks en el mismo clic).
 *   - isPending: spinner en Confirmar, ambos botones deshabilitados.
 *   - errorMessage: se renderiza inline (role="alert") sin cerrar el diálogo.
 *   - a11y: jest-axe sin violaciones en cada estado.
 *
 * Nota: AlertDialog de Radix monta su contenido en un portal directamente
 * bajo document.body (fuera del `container` que devuelve render()), así que
 * los checks de axe corren sobre document.body, no sobre `container`.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { ConfirmDialog, type ConfirmDialogProps } from "../ConfirmDialog";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderDialog(overrides: Partial<ConfirmDialogProps> = {}) {
  const onConfirm = overrides.onConfirm ?? vi.fn();
  const onCancel = overrides.onCancel ?? vi.fn();
  const props: ConfirmDialogProps = {
    open: true,
    title: "Eliminar atleta",
    ...overrides,
    onConfirm,
    onCancel,
  };
  return {
    ...render(<ConfirmDialog {...props} />),
    props,
    onConfirm,
    onCancel,
  };
}

// ---------------------------------------------------------------------------
// Suite: contenido
// ---------------------------------------------------------------------------

describe("ConfirmDialog — contenido", () => {
  it("renderiza el title como heading", () => {
    renderDialog({ title: "¿Eliminar este registro?" });
    expect(
      screen.getByRole("heading", { name: "¿Eliminar este registro?" }),
    ).toBeInTheDocument();
  });

  it("usa las etiquetas por defecto 'Confirmar'/'Cancelar' cuando no se pasan", () => {
    renderDialog();
    expect(screen.getByRole("button", { name: "Confirmar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeInTheDocument();
  });

  it("usa confirmLabel/cancelLabel personalizados", () => {
    renderDialog({ confirmLabel: "Eliminar", cancelLabel: "Volver" });
    expect(screen.getByRole("button", { name: "Eliminar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Volver" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirmar" })).not.toBeInTheDocument();
  });

  it("renderiza description cuando se pasa", () => {
    renderDialog({ description: "Esta acción no se puede deshacer." });
    expect(
      screen.getByText("Esta acción no se puede deshacer."),
    ).toBeInTheDocument();
  });

  it("mantiene un elemento describedby oculto (sr-only) cuando no se pasa description", () => {
    renderDialog();

    const dialog = screen.getByRole("alertdialog");
    const describedById = dialog.getAttribute("aria-describedby");
    expect(describedById).toBeTruthy();

    // El elemento debe existir de verdad (no dejar aria-describedby "colgado"
    // apuntando a un id sin elemento) pero sin texto visible.
    const descriptionEl = document.getElementById(describedById as string);
    expect(descriptionEl).not.toBeNull();
    expect(descriptionEl).toHaveTextContent("");
    expect(descriptionEl?.className).toContain("sr-only");
  });
});

// ---------------------------------------------------------------------------
// Suite: foco inicial según tone
// ---------------------------------------------------------------------------

describe("ConfirmDialog — foco inicial (tone)", () => {
  it("tone='danger' enfoca Cancelar (no Confirmar) al abrir — regresión del autoFocus previo", async () => {
    renderDialog({ tone: "danger" });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Cancelar" })).toHaveFocus();
    });
    expect(screen.getByRole("button", { name: "Confirmar" })).not.toHaveFocus();
  });

  it("tone='default' (o sin especificar) conserva el autofocus por defecto de Radix en Cancelar", async () => {
    renderDialog();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Cancelar" })).toHaveFocus();
    });
  });
});

// ---------------------------------------------------------------------------
// Suite: cierre (Escape / Cancelar)
// ---------------------------------------------------------------------------

describe("ConfirmDialog — cierre", () => {
  it("Escape llama a onCancel", async () => {
    const user = userEvent.setup();
    const { onCancel, onConfirm } = renderDialog();

    await user.keyboard("{Escape}");

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("clic en Cancelar llama a onCancel y no a onConfirm", async () => {
    const user = userEvent.setup();
    const { onCancel, onConfirm } = renderDialog();

    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Suite: confirmar
// ---------------------------------------------------------------------------

describe("ConfirmDialog — confirmar", () => {
  it("clic en Confirmar llama a onConfirm y NO a onCancel", async () => {
    const user = userEvent.setup();
    const { onConfirm, onCancel } = renderDialog();

    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Suite: isPending
// ---------------------------------------------------------------------------

describe("ConfirmDialog — isPending", () => {
  it("muestra un spinner en Confirmar y deshabilita ambos botones", () => {
    renderDialog({ isPending: true });

    const confirmBtn = screen.getByRole("button", { name: "Confirmar" });
    const cancelBtn = screen.getByRole("button", { name: "Cancelar" });

    expect(confirmBtn).toBeDisabled();
    expect(cancelBtn).toBeDisabled();
    expect(confirmBtn.querySelector("svg.animate-spin")).toBeInTheDocument();
  });

  it("no muestra spinner cuando isPending es false", () => {
    renderDialog({ isPending: false });
    const confirmBtn = screen.getByRole("button", { name: "Confirmar" });
    expect(confirmBtn.querySelector("svg.animate-spin")).not.toBeInTheDocument();
    expect(confirmBtn).not.toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Suite: errorMessage
// ---------------------------------------------------------------------------

describe("ConfirmDialog — errorMessage", () => {
  it("se renderiza inline con role=alert y el diálogo permanece abierto", () => {
    const { rerender, props } = renderDialog();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    rerender(
      <ConfirmDialog
        {...props}
        errorMessage="No se pudo completar la acción. Intenta de nuevo."
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "No se pudo completar la acción. Intenta de nuevo.",
    );
    // El diálogo (título + botones) sigue presente — no se cerró por el error.
    expect(screen.getByRole("heading", { name: "Eliminar atleta" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirmar" })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("ConfirmDialog — accesibilidad", () => {
  it("sin violaciones en el estado por defecto", async () => {
    renderDialog();
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("sin violaciones con tone='danger'", async () => {
    renderDialog({ tone: "danger" });
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("sin violaciones con isPending=true", async () => {
    renderDialog({ isPending: true });
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("sin violaciones con errorMessage presente", async () => {
    renderDialog({ errorMessage: "No se pudo completar la acción." });
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("sin violaciones con description presente", async () => {
    renderDialog({ description: "Esta acción no se puede deshacer." });
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
