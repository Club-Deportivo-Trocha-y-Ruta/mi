import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { CancelEventDialog } from "./CancelEventDialog";
import { getAuditReasonCodes } from "@/api/audit";

expect.extend(toHaveNoViolations);

// jsdom no implementa estas APIs de puntero/scroll que Radix Select usa
// internamente (mismo polyfill que NotifyParentsDialog.test.tsx).
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// El catálogo cerrado de motivos de cancelación se consulta vía
// useAuditReasonCodes("cancel") — se mockea la llamada al API en vez de
// levantar MSW, mismo patrón que NotifyParentsDialog.test.tsx.
vi.mock("@/api/audit", () => ({
  getAuditReasonCodes: vi.fn(),
}));

// Catálogo real de motivos de cancelación (backend/app/services/audit.py,
// clase CancelReasonCode) — exactamente 6 códigos, grupo "cancel".
const CANCEL_REASON_CODES = [
  { code: "cancel_weather", label: "Clima adverso", group: "cancel" as const },
  { code: "cancel_venue_unavailable", label: "Sede no disponible", group: "cancel" as const },
  {
    code: "cancel_insufficient_athletes",
    label: "Convocatoria insuficiente",
    group: "cancel" as const,
  },
  {
    code: "cancel_coach_unavailable",
    label: "Entrenador no disponible",
    group: "cancel" as const,
  },
  { code: "cancel_rescheduled", label: "Reprogramado", group: "cancel" as const },
  {
    code: "cancel_organizer_cancelled",
    label: "Cancelado por el organizador",
    group: "cancel" as const,
  },
];

function renderDialog(props: Partial<React.ComponentProps<typeof CancelEventDialog>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={qc}>
      <CancelEventDialog
        open
        eventTitle="Copa Valle II — Ginebra"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        {...props}
      />
    </QueryClientProvider>,
  );
}

async function openSelectAndPick(label: string) {
  const user = userEvent.setup();
  await user.click(screen.getByRole("combobox", { name: /Motivo de la cancelación/i }));
  await user.click(await screen.findByRole("option", { name: label }));
  return user;
}

describe("CancelEventDialog", () => {
  beforeEach(() => {
    vi.mocked(getAuditReasonCodes).mockResolvedValue({ items: CANCEL_REASON_CODES });
  });

  it("renderiza las seis etiquetas del catálogo servido por la API, no de un arreglo local", async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole("combobox", { name: /Motivo de la cancelación/i }));

    for (const { label } of CANCEL_REASON_CODES) {
      expect(await screen.findByRole("option", { name: label })).toBeInTheDocument();
    }
  });

  it("mantiene deshabilitado Confirmar mientras no se elija un motivo y muestra el error al forzar", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    renderDialog({ onConfirm });

    await waitFor(() => expect(getAuditReasonCodes).toHaveBeenCalled());

    await user.click(screen.getByTestId("cancel-event-confirm-button"));

    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByText("Selecciona un motivo de cancelación.")).toBeInTheDocument();
  });

  it("llama a onConfirm con el reasonCode elegido", async () => {
    const onConfirm = vi.fn();
    renderDialog({ onConfirm });

    const user = await openSelectAndPick("Reprogramado");
    await user.click(screen.getByTestId("cancel-event-confirm-button"));

    expect(onConfirm).toHaveBeenCalledWith("cancel_rescheduled");
  });

  it("muestra 'Este evento ya está cancelado.' en línea sin cerrar el diálogo ante un 409", async () => {
    const onCancel = vi.fn();
    renderDialog({ errorMessage: "Este evento ya está cancelado.", onCancel });

    expect(screen.getByText("Este evento ya está cancelado.")).toBeInTheDocument();
    expect(screen.getByTestId("cancel-event-dialog")).toBeInTheDocument();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("no tiene violaciones de accesibilidad con el diálogo abierto (jest-axe)", async () => {
    const { container } = renderDialog();
    await waitFor(() => expect(getAuditReasonCodes).toHaveBeenCalled());
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
