import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import { NotifyParentsDialog } from "./NotifyParentsDialog";

expect.extend(toHaveNoViolations);

const defaultProps = {
  open: true,
  onSend: vi.fn(),
  onSkip: vi.fn(),
  onCancel: vi.fn(),
};

describe("NotifyParentsDialog", () => {
  it("no renderiza nada cuando open=false", () => {
    const { container } = render(
      <NotifyParentsDialog {...defaultProps} variant="create" open={false} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("variante create muestra tres botones y dispara cada callback", () => {
    const onSend = vi.fn();
    const onSkip = vi.fn();
    const onCancel = vi.fn();

    render(
      <NotifyParentsDialog
        {...defaultProps}
        variant="create"
        parentCount={3}
        onSend={onSend}
        onSkip={onSkip}
        onCancel={onCancel}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Enviar notificación/i }));
    fireEvent.click(screen.getByRole("button", { name: /^No enviar$/i }));
    fireEvent.click(screen.getByRole("button", { name: /^Cancelar$/i }));

    expect(onSend).toHaveBeenCalledOnce();
    expect(onSkip).toHaveBeenCalledOnce();
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("variante update muestra el diff y deshabilita Enviar si no hay cambios", () => {
    const { rerender } = render(
      <NotifyParentsDialog {...defaultProps} variant="update" changes={[]} />,
    );
    expect(
      screen.getByRole("button", { name: /Enviar notificación/i }),
    ).toBeDisabled();

    rerender(
      <NotifyParentsDialog
        {...defaultProps}
        variant="update"
        changes={[
          { field: "location", fieldLabel: "Lugar", oldValue: "A", newValue: "B" },
        ]}
      />,
    );
    expect(screen.getByText("Lugar:")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Enviar notificación/i }),
    ).toBeEnabled();
  });

  it("variante cancel permite escribir motivo y lo pasa al callback onSend", () => {
    const onSend = vi.fn();
    render(
      <NotifyParentsDialog
        {...defaultProps}
        variant="cancel"
        parentCount={2}
        onSend={onSend}
      />,
    );

    fireEvent.change(screen.getByLabelText(/Motivo/i), {
      target: { value: "Lluvia intensa" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Enviar notificación/i }));
    expect(onSend).toHaveBeenCalledWith("Lluvia intensa");
  });

  it("variante attendance lista atletas añadidos y removidos", () => {
    render(
      <NotifyParentsDialog
        {...defaultProps}
        variant="attendance"
        addedAthletes={[
          { id: 1, name: "Andrés Pérez" },
          { id: 2, name: "Luisa Gómez" },
        ]}
        removedAthletes={[{ id: 3, name: "Pedro Salas" }]}
      />,
    );
    expect(screen.getByText("+ Andrés Pérez")).toBeInTheDocument();
    expect(screen.getByText("+ Luisa Gómez")).toBeInTheDocument();
    expect(screen.getByText("− Pedro Salas")).toBeInTheDocument();
  });

  it("deshabilita Enviar en variante attendance si no hay atletas añadidos", () => {
    render(
      <NotifyParentsDialog
        {...defaultProps}
        variant="attendance"
        addedAthletes={[]}
        removedAthletes={[{ id: 3, name: "Pedro" }]}
      />,
    );
    expect(
      screen.getByRole("button", { name: /Enviar notificación/i }),
    ).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Suite: Radix Dialog — foco y cierre (regresión del rebuild sobre
// components/ui/dialog.tsx). El hand-rolled <div role="alertdialog"> previo
// no tenía keydown handler para Escape ni lógica de focus-trap alguna, así
// que estas dos aserciones no podían pasar contra esa versión: Tab llegaba
// sin obstáculo a cualquier elemento de fondo y Escape no invocaba ningún
// callback (no había listener). Con el Dialog de Radix (FocusScope
// trapped+loop, DismissableLayer con onDismiss→onOpenChange) ambas quedan
// cubiertas "gratis".
// ---------------------------------------------------------------------------

describe("NotifyParentsDialog — Radix Dialog (foco y cierre)", () => {
  it("atrapa el foco: Tab repetido nunca llega a un elemento de fondo", async () => {
    const user = userEvent.setup();
    render(
      <>
        <button type="button">Fondo</button>
        <NotifyParentsDialog {...defaultProps} variant="create" parentCount={2} />
      </>,
    );

    // Radix marca el resto de la página como aria-hidden mientras el diálogo
    // está abierto (oculto del árbol de accesibilidad) — `hidden: true` es
    // necesario para poder seguir obteniendo una referencia al nodo.
    const fondoButton = screen.getByRole("button", { name: "Fondo", hidden: true });

    // Más vueltas que botones focosables tiene el diálogo (X, Cancelar,
    // No enviar, Enviar notificación): si el foco no estuviera atrapado,
    // alguna de estas vueltas debería aterrizar en "Fondo".
    for (let i = 0; i < 12; i++) {
      await user.tab();
      expect(document.activeElement).not.toBe(fondoButton);
    }
  });

  it("Escape cierra el diálogo (llama a onCancel)", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(
      <NotifyParentsDialog {...defaultProps} variant="create" onCancel={onCancel} />,
    );

    await user.keyboard("{Escape}");

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("sin violaciones de accesibilidad (jest-axe)", async () => {
    render(
      <NotifyParentsDialog {...defaultProps} variant="create" parentCount={2} />,
    );
    // Radix porta el contenido del diálogo a document.body (fuera del
    // `container` de render()), así que el chequeo corre sobre document.body.
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
