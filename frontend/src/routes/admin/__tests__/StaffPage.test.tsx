/**
 * Tests de StaffPage (feature 041 — gobernanza multi-coach, US3, T057).
 * Contrato: specs/041-multi-coach-governance/contracts/staff-admin.md §8, §14.2.
 *
 * `useStaff`/`useSetStaffActive` se mockean; `useClubs`/`useAuditReasonCodes`
 * corren contra MSW real (`staffHandlers`, `auditHandlers`), mismo patrón
 * que `ArchivedAthletesPage.test.tsx`.
 */
import { Children, isValidElement } from "react";
import type { ReactElement, ReactNode } from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { http, HttpResponse } from "msw";

import { mswServer } from "@/test/setup";
import { auditHandlers } from "@/test/msw/auditHandlers";
import { staffHandlers, makeStaffUser } from "@/test/msw/staffHandlers";
import type { UserOut } from "@/types/user.types";

const accountReasonCodesHandler = http.get("*/api/audit/reason-codes", () =>
  HttpResponse.json({
    items: [
      { code: "account_staff_rotation", group: "account", label: "Cambio de personal" },
      { code: "account_end_of_engagement", group: "account", label: "Fin de vinculación" },
      { code: "account_security", group: "account", label: "Motivo de seguridad" },
    ],
  }),
);

// Polyfills de jsdom requeridos por Radix Select (mismo patrón que
// ArchivedAthletesPage.test.tsx).
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

const useStaffMock = vi.fn();
vi.mock("@/hooks/admin/useStaff", () => ({
  useStaff: (params: unknown) => useStaffMock(params),
}));

const setActiveMutateMock = vi.fn();
vi.mock("@/hooks/admin/useSetStaffActive", () => ({
  useSetStaffActive: () => ({ mutate: setActiveMutateMock, isPending: false }),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { user: { id: number } }) => unknown) =>
    selector({ user: { id: 1 } }),
}));

import { StaffPage } from "@/routes/admin/StaffPage";

const coach: UserOut = makeStaffUser();
const inactiveCoach: UserOut = makeStaffUser({
  id: 12,
  first_name: "Ana",
  last_name: "Rivera",
  is_active: false,
  created_by_display_name: "Laura Méndez",
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <StaffPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mswServer.use(accountReasonCodesHandler, ...staffHandlers, ...auditHandlers);
});

describe("StaffPage", () => {
  it("muestra la tabla con las seis columnas", async () => {
    useStaffMock.mockReturnValue({
      data: { items: [coach, inactiveCoach], total: 2 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderPage();

    expect(await screen.findByTestId("staff-table")).toBeInTheDocument();
    expect(screen.getAllByText("Laura Méndez").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("Entrenador").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Activo")).toBeInTheDocument();
    expect(screen.getByText("Inactivo")).toBeInTheDocument();
  });

  it("estado vacío: 'Aún no hay personal registrado.'", () => {
    useStaffMock.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getByText("Aún no hay personal registrado.")).toBeInTheDocument();
  });

  it("estado vacío filtrado: 'No hay personal con ese estado.'", async () => {
    useStaffMock.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    const user = userEvent.setup();
    renderPage();

    const filterSelect = screen.getByTestId("staff-state-filter");
    await user.selectOptions(filterSelect, "inactive");

    expect(
      await screen.findByText("No hay personal con ese estado."),
    ).toBeInTheDocument();
  });

  it("estado de error: ErrorState con reintentar", () => {
    const refetch = vi.fn();
    useStaffMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("boom"),
      refetch,
    });

    renderPage();

    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("no muestra acción para la propia fila del admin conectado", () => {
    useStaffMock.mockReturnValue({
      data: { items: [{ ...coach, id: 1 }], total: 1 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.queryByTestId("staff-toggle-active-1")).not.toBeInTheDocument();
  });

  it("cambiar el filtro de estado dispara useStaff con el nuevo valor", async () => {
    useStaffMock.mockReturnValue({
      data: { items: [coach], total: 1 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    const user = userEvent.setup();
    renderPage();

    const filterSelect = screen.getByTestId("staff-state-filter");
    await user.selectOptions(filterSelect, "active");

    await waitFor(() => {
      expect(useStaffMock).toHaveBeenCalledWith({ isActive: true });
    });
  });

  it("desactivar: abre el diálogo, requiere motivo y llama a la mutación", async () => {
    useStaffMock.mockReturnValue({
      data: { items: [coach], total: 1 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByTestId(`staff-toggle-active-${coach.id}`));
    await screen.findByTestId("staff-state-dialog");

    await user.click(screen.getByRole("button", { name: "Desactivar" }));
    // No reason picked yet -> validation error, no mutate call.
    expect(setActiveMutateMock).not.toHaveBeenCalled();

    const reasonSelect = await screen.findByTestId("staff-reason-select");
    await user.selectOptions(reasonSelect, "account_staff_rotation");
    await user.click(screen.getByRole("button", { name: "Desactivar" }));

    await waitFor(() => {
      expect(setActiveMutateMock).toHaveBeenCalledWith(
        {
          id: coach.id,
          body: { is_active: false, reason_code: "account_staff_rotation" },
        },
        expect.any(Object),
      );
    });
  });

  it("reactivar: envía 'account_reactivation' sin pedir motivo", async () => {
    useStaffMock.mockReturnValue({
      data: { items: [inactiveCoach], total: 1 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByTestId(`staff-toggle-active-${inactiveCoach.id}`));
    await screen.findByTestId("staff-state-dialog");
    await user.click(screen.getByRole("button", { name: "Reactivar" }));

    await waitFor(() => {
      expect(setActiveMutateMock).toHaveBeenCalledWith(
        {
          id: inactiveCoach.id,
          body: { is_active: true, reason_code: "account_reactivation" },
        },
        expect.any(Object),
      );
    });
  });

  it("abre la hoja de creación al hacer clic en '+ Nuevo entrenador'", async () => {
    useStaffMock.mockReturnValue({
      data: { items: [coach], total: 1 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByTestId("staff-new-button"));
    expect(await screen.findByTestId("staff-create-sheet")).toBeInTheDocument();
  });
});
