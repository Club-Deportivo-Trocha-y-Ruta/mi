import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { NotifyParentsDialog } from "./NotifyParentsDialog";

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
