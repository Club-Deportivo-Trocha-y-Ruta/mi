/**
 * jest-axe zero-violations pass de StaffPage (feature 041 — gobernanza
 * multi-coach, US3, T057). contracts/staff-admin.md §12.
 */
import { Children, isValidElement } from "react";
import type { ReactElement, ReactNode } from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";

import { mswServer } from "@/test/setup";
import { auditHandlers } from "@/test/msw/auditHandlers";
import { staffHandlers, makeStaffUser } from "@/test/msw/staffHandlers";
import type { UserOut } from "@/types/user.types";

expect.extend(toHaveNoViolations);

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
  useStaff: () => useStaffMock(),
}));

vi.mock("@/hooks/admin/useSetStaffActive", () => ({
  useSetStaffActive: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { user: { id: number } }) => unknown) =>
    selector({ user: { id: 1 } }),
}));

import { StaffPage } from "@/routes/admin/StaffPage";

const coach: UserOut = makeStaffUser();

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
  mswServer.use(...staffHandlers, ...auditHandlers);
});

describe("StaffPage — accesibilidad", () => {
  it("sin violaciones: cargado, poblado", async () => {
    useStaffMock.mockReturnValue({
      data: { items: [coach], total: 1 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    const { container } = renderPage();
    await screen.findByTestId("staff-table");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones: vacío", async () => {
    useStaffMock.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    const { container } = renderPage();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones: error", async () => {
    useStaffMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("boom"),
      refetch: vi.fn(),
    });
    const { container } = renderPage();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones: hoja de creación abierta", async () => {
    useStaffMock.mockReturnValue({
      data: { items: [coach], total: 1 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    const user = userEvent.setup();
    const { container } = renderPage();

    await user.click(screen.getByTestId("staff-new-button"));
    await screen.findByTestId("staff-create-sheet");

    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones: diálogo de desactivar abierto", async () => {
    useStaffMock.mockReturnValue({
      data: { items: [coach], total: 1 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    const user = userEvent.setup();
    const { container } = renderPage();

    await user.click(await screen.findByTestId(`staff-toggle-active-${coach.id}`));
    await screen.findByTestId("staff-state-dialog");

    expect(await axe(container)).toHaveNoViolations();
  });
});
