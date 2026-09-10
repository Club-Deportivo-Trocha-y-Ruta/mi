/**
 * Tests de StaffCreateSheet (feature 041 — gobernanza multi-coach, US3,
 * T057). contracts/staff-admin.md §9, §14.2.
 */
import { Children, isValidElement } from "react";
import type { ReactElement, ReactNode } from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

import { mswServer } from "@/test/setup";
import { staffHandlers, makeClub } from "@/test/msw/staffHandlers";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

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

import { StaffCreateSheet } from "@/components/admin/StaffCreateSheet";

function renderSheet(onOpenChange = vi.fn(), onCreated = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    onOpenChange,
    onCreated,
    ...render(
      <QueryClientProvider client={qc}>
        <StaffCreateSheet open onOpenChange={onOpenChange} onCreated={onCreated} />
      </QueryClientProvider>,
    ),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mswServer.use(...staffHandlers);
});

async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Nombres"), "Ana");
  await user.type(screen.getByLabelText("Apellidos"), "Rivera");
  await user.type(screen.getByLabelText("Correo electrónico"), "ana.rivera@example.org");
}

describe("StaffCreateSheet", () => {
  it("enviar sin club: error inline y no dispara la petición", async () => {
    let requestFired = false;
    mswServer.use(
      http.post("*/api/users", () => {
        requestFired = true;
        return HttpResponse.json({}, { status: 201 });
      }),
    );

    const user = userEvent.setup();
    renderSheet();

    await fillRequiredFields(user);
    await user.click(screen.getByTestId("staff-create-submit"));

    expect(
      await screen.findByText("El club es obligatorio para un entrenador"),
    ).toBeInTheDocument();
    expect(requestFired).toBe(false);
  });

  it("camino feliz: crea sin password y con role coach", async () => {
    let capturedBody: Record<string, unknown> | null = null;
    mswServer.use(
      http.post("*/api/users", async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 99 }, { status: 201 });
      }),
      http.get("*/api/clubs/", () => HttpResponse.json([makeClub()])),
    );

    const user = userEvent.setup();
    const { onOpenChange, onCreated } = renderSheet();

    await fillRequiredFields(user);
    await screen.findByRole("option", { name: "Trocha y Ruta" });
    await user.selectOptions(screen.getByTestId("staff-club-select"), "1");
    await user.click(screen.getByTestId("staff-create-submit"));

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalled();
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });

    expect(capturedBody).toMatchObject({
      first_name: "Ana",
      last_name: "Rivera",
      email: "ana.rivera@example.org",
      role: "coach",
      club_id: 1,
    });
    expect(capturedBody).not.toHaveProperty("password");
  });

  it("409 duplicado: mapea el error al campo de correo", async () => {
    mswServer.use(
      http.post("*/api/users", () =>
        HttpResponse.json(
          { detail: "Ya existe un usuario con ese correo electrónico" },
          { status: 409 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderSheet();

    await fillRequiredFields(user);
    await screen.findByRole("option", { name: "Trocha y Ruta" });
    await user.selectOptions(screen.getByTestId("staff-club-select"), "1");
    await user.click(screen.getByTestId("staff-create-submit"));

    expect(
      await screen.findByText("Ya existe un usuario con ese correo electrónico"),
    ).toBeInTheDocument();
  });

  it("Escape cierra la hoja (onOpenChange(false))", async () => {
    const user = userEvent.setup();
    const { onOpenChange } = renderSheet();

    await screen.findByTestId("staff-create-sheet");
    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it("422 de club_id: mapea el error al campo club", async () => {
    mswServer.use(
      http.post("*/api/users", () =>
        HttpResponse.json(
          { detail: "El club es obligatorio para las cuentas de entrenador y administrador" },
          { status: 422 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderSheet();

    await fillRequiredFields(user);
    await screen.findByRole("option", { name: "Trocha y Ruta" });
    await user.selectOptions(screen.getByTestId("staff-club-select"), "1");
    await user.click(screen.getByTestId("staff-create-submit"));

    expect(
      await screen.findByText(
        "El club es obligatorio para las cuentas de entrenador y administrador",
      ),
    ).toBeInTheDocument();
  });
});
