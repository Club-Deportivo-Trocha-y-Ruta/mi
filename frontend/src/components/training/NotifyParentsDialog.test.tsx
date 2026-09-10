import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { NotifyParentsDialog } from "./NotifyParentsDialog";
import { getAuditReasonCodes } from "@/api/audit";

expect.extend(toHaveNoViolations);

// jsdom no implementa estas APIs de puntero/scroll que Radix Select usa
// internamente (PointerEvent completo, hasPointerCapture, scrollIntoView).
// Sin este polyfill, abrir el Select revienta con un TypeError en jsdom.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// El catálogo cerrado de motivos de cancelación solo se consulta en
// variante "cancel" (ver `NotifyParentsDialog`). Se mockea la llamada al
// API en vez de levantar MSW: mantiene el test enfocado en el componente.
vi.mock("@/api/audit", () => ({
  getAuditReasonCodes: vi.fn(),
}));

const CANCEL_REASON_CODES = [
  { code: "cancel_weather", label: "Clima adverso", group: "cancel" as const },
  { code: "cancel_rescheduled", label: "Reprogramada", group: "cancel" as const },
];

const defaultProps = {
  open: true,
  onSend: vi.fn(),
  onSkip: vi.fn(),
  onCancel: vi.fn(),
};

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

async function selectCancelReason() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("combobox", { name: /Motivo de la cancelación/i }));
  await user.click(await screen.findByRole("option", { name: "Reprogramada" }));
}

describe("NotifyParentsDialog", () => {
  it("no renderiza nada cuando open=false", () => {
    const { container } = renderWithClient(
      <NotifyParentsDialog {...defaultProps} variant="create" open={false} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("variante create muestra tres botones y dispara cada callback", () => {
    const onSend = vi.fn();
    const onSkip = vi.fn();
    const onCancel = vi.fn();

    renderWithClient(
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
    const { rerender } = renderWithClient(
      <NotifyParentsDialog {...defaultProps} variant="update" changes={[]} />,
    );
    expect(
      screen.getByRole("button", { name: /Enviar notificación/i }),
    ).toBeDisabled();

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <NotifyParentsDialog
          {...defaultProps}
          variant="update"
          changes={[
            { field: "location", fieldLabel: "Lugar", oldValue: "A", newValue: "B" },
          ]}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText("Lugar:")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Enviar notificación/i }),
    ).toBeEnabled();
  });

  it("variante cancel exige elegir motivo del catálogo antes de habilitar Enviar/No enviar", async () => {
    vi.mocked(getAuditReasonCodes).mockResolvedValue({ items: CANCEL_REASON_CODES });
    const onSend = vi.fn();
    const onSkip = vi.fn();
    renderWithClient(
      <NotifyParentsDialog
        {...defaultProps}
        variant="cancel"
        parentCount={2}
        onSend={onSend}
        onSkip={onSkip}
      />,
    );

    expect(
      screen.getByRole("button", { name: /Enviar notificación/i }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: /^No enviar$/i })).toBeDisabled();

    await selectCancelReason();

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Enviar notificación/i }),
      ).toBeEnabled(),
    );

    fireEvent.change(screen.getByLabelText(/Mensaje para las familias/i), {
      target: { value: "Lluvia intensa" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Enviar notificación/i }));
    expect(onSend).toHaveBeenCalledWith("Lluvia intensa", "cancel_rescheduled");
  });

  it("variante cancel pasa el reasonCode elegido a 'No enviar'", async () => {
    vi.mocked(getAuditReasonCodes).mockResolvedValue({ items: CANCEL_REASON_CODES });
    const onSkip = vi.fn();
    renderWithClient(
      <NotifyParentsDialog
        {...defaultProps}
        variant="cancel"
        parentCount={2}
        onSkip={onSkip}
      />,
    );

    await selectCancelReason();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^No enviar$/i })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: /^No enviar$/i }));
    expect(onSkip).toHaveBeenCalledWith("cancel_rescheduled");
  });

  it("variante attendance lista atletas añadidos y removidos", () => {
    renderWithClient(
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
    renderWithClient(
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
    renderWithClient(
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
    renderWithClient(
      <NotifyParentsDialog {...defaultProps} variant="create" onCancel={onCancel} />,
    );

    await user.keyboard("{Escape}");

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("sin violaciones de accesibilidad (jest-axe)", async () => {
    renderWithClient(
      <NotifyParentsDialog {...defaultProps} variant="create" parentCount={2} />,
    );
    // Radix porta el contenido del diálogo a document.body (fuera del
    // `container` de render()), así que el chequeo corre sobre document.body.
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
