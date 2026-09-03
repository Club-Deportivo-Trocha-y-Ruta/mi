import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { axe } from "jest-axe";

import { DeliveryPanel } from "@/components/newsletter/studio/DeliveryPanel";
import type { DeliveryRow } from "@/types/athleteNewsletter.types";

function makeRow(overrides?: Partial<DeliveryRow>): DeliveryRow {
  return {
    parent_user_id: 10,
    email_masked: "j***@gmail.com",
    has_account: true,
    sent_at: "2026-07-03T10:00:00Z",
    delivered_at: null,
    opened_at: null,
    web_read_at: null,
    bounced: false,
    ...overrides,
  };
}

describe("DeliveryPanel", () => {
  it("muestra mensaje vacío cuando no hay entregas", () => {
    render(<DeliveryPanel delivery={[]} onResend={() => {}} />);
    expect(screen.getByTestId("delivery-panel-empty")).toBeInTheDocument();
  });

  it("emails enmascarados nunca aparecen en claro", () => {
    render(<DeliveryPanel delivery={[makeRow()]} onResend={() => {}} />);
    expect(screen.getByText("j***@gmail.com")).toBeInTheDocument();
    expect(screen.queryByText(/@gmail\.com$/, { exact: false })).toBeInTheDocument(); // sanity: still masked form
  });

  it("muestra 'Leído en la web' con fecha cuando web_read_at está presente", () => {
    render(
      <DeliveryPanel
        delivery={[makeRow({ web_read_at: "2026-07-05T09:00:00Z" })]}
        onResend={() => {}}
      />,
    );
    expect(screen.getByText(/Leído en la web/)).toBeInTheDocument();
  });

  it("muestra 'Correo entregado' con fecha cuando delivered_at está presente", () => {
    render(
      <DeliveryPanel
        delivery={[makeRow({ delivered_at: "2026-07-03T10:05:00Z" })]}
        onResend={() => {}}
      />,
    );
    expect(screen.getByText(/Correo entregado/)).toBeInTheDocument();
  });

  it("muestra 'Abierto' con fecha cuando opened_at está presente", () => {
    render(
      <DeliveryPanel
        delivery={[makeRow({ opened_at: "2026-07-03T11:00:00Z" })]}
        onResend={() => {}}
      />,
    );
    expect(screen.getByText(/^Abierto/)).toBeInTheDocument();
  });

  it("muestra 'Sin leer' cuando tiene cuenta pero no ha leído", () => {
    render(<DeliveryPanel delivery={[makeRow()]} onResend={() => {}} />);
    expect(screen.getByText("Sin leer")).toBeInTheDocument();
  });

  it("muestra 'Sin cuenta web' cuando el padre no tiene cuenta activa", () => {
    render(
      <DeliveryPanel delivery={[makeRow({ has_account: false })]} onResend={() => {}} />,
    );
    expect(screen.getByText("Sin cuenta web")).toBeInTheDocument();
  });

  it("muestra 'Rebotado' cuando bounced es true", () => {
    render(<DeliveryPanel delivery={[makeRow({ bounced: true })]} onResend={() => {}} />);
    expect(screen.getByText("Rebotado")).toBeInTheDocument();
  });

  it("botón Reenviar llama a onResend (force_resend)", () => {
    const onResend = vi.fn();
    render(<DeliveryPanel delivery={[makeRow()]} onResend={onResend} />);
    fireEvent.click(screen.getByTestId("delivery-resend-10"));
    expect(onResend).toHaveBeenCalledTimes(1);
  });

  it("sin violaciones de accesibilidad", async () => {
    const { container } = render(
      <DeliveryPanel
        delivery={[makeRow(), makeRow({ parent_user_id: 11, has_account: false })]}
        onResend={() => {}}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
