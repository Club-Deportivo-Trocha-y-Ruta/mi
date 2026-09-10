/**
 * Tests de StaffStateDialog (feature 041 — gobernanza multi-coach, US3,
 * T057). contracts/staff-admin.md §10, §14.2.
 */
import { Children, isValidElement } from "react";
import type { ComponentProps, ReactElement, ReactNode } from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { http, HttpResponse } from "msw";

import { mswServer } from "@/test/setup";

const accountReasonCodesHandler = http.get("*/api/audit/reason-codes", () =>
  HttpResponse.json({
    items: [
      { code: "account_staff_rotation", group: "account", label: "Cambio de personal" },
      { code: "account_end_of_engagement", group: "account", label: "Fin de vinculación" },
      { code: "account_security", group: "account", label: "Motivo de seguridad" },
    ],
  }),
);

if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {};
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

vi.mock("@/components/ui/select", () => {
  const SelectTrigger = ({
    children,
  }: {
    children: ReactNode;
    id?: string;
    "data-testid"?: string;
  }) => <>{children}</>;

  const SelectContent = ({ children }: { children: ReactNode }) => <>{children}</>;

  const Select = ({
    value,
    onValueChange,
    children,
  }: {
    value: string;
    onValueChange: (v: string) => void;
    children: ReactNode;
  }) => {
    const childArray = Children.toArray(children) as ReactElement[];
    const trigger = childArray.find(
      (c) => isValidElement(c) && c.type === SelectTrigger,
    ) as ReactElement<{ id?: string; "data-testid"?: string }> | undefined;
    const content = childArray.find(
      (c) => isValidElement(c) && c.type === SelectContent,
    ) as ReactElement<{ children?: ReactNode }> | undefined;
    return (
      <select
        id={trigger?.props.id}
        data-testid={trigger?.props["data-testid"]}
        value={value}
        onChange={(e) => onValueChange(e.target.value)}
      >
        {content?.props.children}
      </select>
    );
  };

  return {
    Select,
    SelectTrigger,
    SelectValue: () => null,
    SelectContent,
    SelectItem: ({ value, children }: { value: string; children: ReactNode }) => (
      <option value={value}>{children}</option>
    ),
  };
});

import { StaffStateDialog } from "@/components/admin/StaffStateDialog";

function renderDialog(
  props: Partial<ComponentProps<typeof StaffStateDialog>> = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onConfirm = props.onConfirm ?? vi.fn();
  const onCancel = props.onCancel ?? vi.fn();
  return {
    onConfirm,
    onCancel,
    ...render(
      <QueryClientProvider client={qc}>
        <StaffStateDialog
          open
          action="deactivate"
          staffFullName="Laura Méndez"
          onConfirm={onConfirm}
          onCancel={onCancel}
          {...props}
        />
      </QueryClientProvider>,
    ),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mswServer.use(accountReasonCodesHandler);
});

describe("StaffStateDialog", () => {
  it("desactivar: confirmar deshabilitado sin motivo elegido, habilitado tras elegirlo", async () => {
    const user = userEvent.setup();
    const { onConfirm } = renderDialog({ action: "deactivate" });

    await screen.findByTestId("staff-state-dialog");
    const confirmButton = screen.getByRole("button", { name: "Desactivar" });

    await user.click(confirmButton);
    expect(onConfirm).not.toHaveBeenCalled();

    const reasonSelect = await screen.findByTestId("staff-reason-select");
    await user.selectOptions(reasonSelect, "account_staff_rotation");
    await user.click(confirmButton);

    expect(onConfirm).toHaveBeenCalledWith("account_staff_rotation");
  });

  it("reactivar: no muestra selector de motivo y envía 'account_reactivation'", async () => {
    const user = userEvent.setup();
    const { onConfirm } = renderDialog({ action: "reactivate" });

    await screen.findByTestId("staff-state-dialog");
    expect(screen.queryByTestId("staff-reason-select")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reactivar" }));
    expect(onConfirm).toHaveBeenCalledWith("account_reactivation");
  });

  it("error: mantiene el diálogo abierto y muestra el mensaje", async () => {
    renderDialog({ action: "deactivate", errorMessage: "No se pudo desactivar." });

    expect(await screen.findByText("No se pudo desactivar.")).toBeInTheDocument();
    expect(screen.getByTestId("staff-state-dialog")).toBeInTheDocument();
  });
});
