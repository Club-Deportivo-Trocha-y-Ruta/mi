/**
 * Regression test — CompetitionFormPage discard-changes guard.
 *
 * `handleCancel` used to call `window.confirm(...)` imperatively when the
 * form had unsaved changes. It was converted to the declarative
 * `ConfirmDialog` (tone="default") pattern: a local `showDiscardConfirm`
 * state gates the dialog, and `onConfirm` performs the actual
 * navigation-away/discard action (`discardAndLeave`) — same
 * imperative-to-declarative conversion as `MediaGallery`.
 *
 * Covers:
 *  - `window.confirm` is never called, in any flow (imperative API fully
 *    removed — a spy stays at zero calls throughout).
 *  - Sin cambios sin guardar (isDirty=false) → Cancelar navega directo,
 *    sin mostrar ConfirmDialog.
 *  - Con cambios sin guardar → Cancelar abre ConfirmDialog en vez de
 *    navegar inmediatamente.
 *  - ConfirmDialog "Seguir editando" (cancelar) → cierra el diálogo y NO
 *    navega.
 *  - ConfirmDialog "Salir sin guardar" (confirmar) → navega (descarta).
 *  - 0 violaciones a11y con el diálogo abierto.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "C", last_name: "T" },
      isAuthenticated: true,
    }),
  ),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

import { mswServer } from "@/test/setup";
import { raceEventsHandlers } from "@/test/msw/raceEventsHandlers";
import { raceSeriesHandlers } from "@/test/msw/raceSeriesHandlers";
import { CompetitionFormPage } from "@/routes/competitions/CompetitionFormPage";

function renderForm() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/competitions/new"]}>
        <Routes>
          <Route
            path="/competitions/new"
            element={<CompetitionFormPage mode="create" />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Ensucia el form (isDirty=true) escribiendo en el campo Nombre. */
async function dirtyTheForm(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByLabelText("Nombre");
  await user.type(screen.getByLabelText("Nombre"), "Válida 4 · Cali");
}

/** Ambos botones "Cancelar" (header + footer del form) llaman a handleCancel. */
function clickCancelButton(user: ReturnType<typeof userEvent.setup>) {
  return user.click(screen.getAllByRole("button", { name: "Cancelar" })[0]);
}

describe("CompetitionFormPage — discard-changes guard (ConfirmDialog, not window.confirm)", () => {
  let confirmSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    mswServer.use(...raceEventsHandlers, ...raceSeriesHandlers);
    // Si el componente todavía llamara a window.confirm, esto lo detecta
    // (además de dejar en evidencia la llamada vía confirmSpy).
    confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    confirmSpy.mockRestore();
  });

  it("[regresión] nunca llama a window.confirm — abre ConfirmDialog en su lugar", async () => {
    const user = userEvent.setup();
    renderForm();

    await dirtyTheForm(user);
    await clickCancelButton(user);

    // ConfirmDialog renderiza (AlertDialog de Radix -> role="alertdialog").
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toBeInTheDocument();
    expect(confirmSpy).not.toHaveBeenCalled();

    // Confirmar dentro del diálogo tampoco pasa por window.confirm.
    await user.click(
      within(dialog).getByRole("button", { name: "Salir sin guardar" }),
    );
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it("sin cambios sin guardar → Cancelar navega directo, sin mostrar ConfirmDialog", async () => {
    const user = userEvent.setup();
    renderForm();

    await screen.findByLabelText("Nombre");
    await clickCancelButton(user);

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/competitions"),
    );
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it("con cambios sin guardar → Cancelar abre ConfirmDialog y NO navega todavía", async () => {
    const user = userEvent.setup();
    renderForm();

    await dirtyTheForm(user);
    await clickCancelButton(user);

    const dialog = await screen.findByRole("alertdialog");
    expect(
      within(dialog).getByRole("heading", { name: "¿Salir sin guardar?" }),
    ).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("ConfirmDialog → 'Seguir editando' cierra el diálogo y NO navega", async () => {
    const user = userEvent.setup();
    renderForm();

    await dirtyTheForm(user);
    await clickCancelButton(user);
    const dialog = await screen.findByRole("alertdialog");

    await user.click(
      within(dialog).getByRole("button", { name: "Seguir editando" }),
    );

    await waitFor(() =>
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument(),
    );
    expect(mockNavigate).not.toHaveBeenCalled();
    // El formulario sigue montado (no se descartó nada).
    expect(screen.getByLabelText("Nombre")).toBeInTheDocument();
  });

  it("ConfirmDialog → 'Salir sin guardar' descarta y navega a /competitions", async () => {
    const user = userEvent.setup();
    renderForm();

    await dirtyTheForm(user);
    await clickCancelButton(user);
    const dialog = await screen.findByRole("alertdialog");

    await user.click(
      within(dialog).getByRole("button", { name: "Salir sin guardar" }),
    );

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/competitions"),
    );
  });

  it("0 violaciones a11y con el ConfirmDialog de descarte abierto", async () => {
    const user = userEvent.setup();
    renderForm();

    await dirtyTheForm(user);
    await clickCancelButton(user);
    await screen.findByRole("alertdialog");

    // AlertDialog de Radix monta su contenido en un portal bajo
    // document.body (fuera del `container` de render()), igual que en
    // components/shared/__tests__/ConfirmDialog.test.tsx y
    // components/training/MediaGallery.test.tsx.
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
