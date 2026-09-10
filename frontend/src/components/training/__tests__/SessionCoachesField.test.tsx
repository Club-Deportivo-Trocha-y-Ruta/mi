/**
 * Tests de SessionCoachesField (feature 041 — gobernanza multi-coach, T066).
 * contracts/session-coaches.md §10.1, §12 (F-01).
 *
 * Nombres inventados de personas adultas (entrenadores) únicamente — ningún
 * dato de un menor aparece en este archivo.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { axe, toHaveNoViolations } from "jest-axe";

import { mswServer } from "@/test/setup";
import { makeStaffListOut, makeStaffUser } from "@/test/msw/staffHandlers";
import { SessionCoachesField } from "@/components/training/SessionCoachesField";

expect.extend(toHaveNoViolations);

const CURRENT_USER = {
  id: 3,
  email: "laura.mendez@example.org",
  first_name: "Laura",
  last_name: "Méndez",
};

// Dos entrenadores ACTIVOS del club (el picker excluye inactivos — V4/§10.1,
// copy "No hay otros entrenadores activos en el club."). `staffHandlers` trae
// un segundo coach inactivo por defecto, así que aquí lo sobreescribimos con
// uno activo para poder ejercer el flujo de "agregar".
const listActiveCoachesHandler = http.get("*/api/users", () =>
  HttpResponse.json(
    makeStaffListOut({
      items: [
        makeStaffUser({ id: 3, first_name: "Laura", last_name: "Méndez" }),
        makeStaffUser({ id: 12, first_name: "Ana", last_name: "Rivera", is_active: true }),
      ],
    }),
  ),
);

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { user: typeof CURRENT_USER; accessToken: string }) => unknown) =>
    selector({ user: CURRENT_USER, accessToken: "test-token" }),
}));

function renderField(props: {
  value: number[];
  onChange: (ids: number[]) => void;
  error?: string;
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SessionCoachesField {...props} />
    </QueryClientProvider>,
  );
}

describe("SessionCoachesField", () => {
  beforeEach(() => {
    mswServer.use(listActiveCoachesHandler);
  });

  it("se prellena con el entrenador autenticado cuando el valor llega vacío", async () => {
    const onChange = vi.fn();
    renderField({ value: [], onChange });

    await waitFor(() => expect(onChange).toHaveBeenCalledWith([3]));
  });

  it("agregar un segundo entrenador renderiza dos chips", async () => {
    const onChange = vi.fn();
    const { rerender } = renderField({ value: [3], onChange });

    await waitFor(() => expect(screen.getByText("Laura Méndez")).toBeInTheDocument());

    const checkbox = await screen.findByRole("checkbox", { name: /Agregar a Ana Rivera/i });
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith([3, 12]);

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    rerender(
      <QueryClientProvider client={queryClient}>
        <SessionCoachesField value={[3, 12]} onChange={onChange} />
      </QueryClientProvider>,
    );

    const chipList = await screen.findByTestId("selected-coach-chips");
    const chips = within(chipList).getAllByRole("listitem");
    expect(chips).toHaveLength(2);
    expect(within(chipList).getByText("Laura Méndez")).toBeInTheDocument();
    expect(within(chipList).getByText("Ana Rivera")).toBeInTheDocument();
  });

  it("el botón de quitar del único chip restante está deshabilitado con el hint", async () => {
    const onChange = vi.fn();
    renderField({ value: [3], onChange });

    const removeButton = await screen.findByRole("button", { name: /Quitar a Laura Méndez/i });
    expect(removeButton).toBeDisabled();
    expect(screen.getByText("Una sesión debe tener al menos un entrenador.")).toBeInTheDocument();
  });

  it("el botón de quitar SÍ está habilitado cuando hay más de un entrenador", async () => {
    const onChange = vi.fn();
    renderField({ value: [3, 12], onChange });

    const removeButton = await screen.findByRole("button", { name: /Quitar a Laura Méndez/i });
    expect(removeButton).not.toBeDisabled();
  });

  it("quitar un entrenador no-último invoca onChange sin él", async () => {
    const onChange = vi.fn();
    renderField({ value: [3, 12], onChange });

    const removeButton = await screen.findByRole("button", { name: /Quitar a Ana Rivera/i });
    fireEvent.click(removeButton);
    expect(onChange).toHaveBeenCalledWith([3]);
  });

  it("muestra el mensaje de error cuando se pasa", async () => {
    renderField({ value: [3], onChange: vi.fn(), error: "Selecciona al menos un entrenador" });
    expect(await screen.findByText("Selecciona al menos un entrenador")).toBeInTheDocument();
  });

  it("muestra skeleton mientras carga", () => {
    const { container } = renderField({ value: [3], onChange: vi.fn() });
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("muestra estado de error con reintentar cuando la carga falla", async () => {
    mswServer.use(
      http.get("*/api/users", () => HttpResponse.json({ detail: "error" }, { status: 500 })),
    );
    renderField({ value: [3], onChange: vi.fn() });
    expect(
      await screen.findByText(/No se pudo cargar la lista de entrenadores/i),
    ).toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad", async () => {
    const { container } = renderField({ value: [3, 12], onChange: vi.fn() });
    await screen.findByTestId("selected-coach-chips");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
