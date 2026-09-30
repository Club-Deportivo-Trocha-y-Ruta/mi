/**
 * Tests de SensitiveDataCard (feature 047, US2, T037).
 *
 * Cubre: el bloque bloqueado vs. desbloqueado según autorización activa, el
 * diálogo de registro, la validación de `conflict_victim` sin default antes
 * de guardar, y el flujo de retiro (ConfirmDialog, no `window.confirm`). Los
 * cuatro hooks de datos sensibles se mockean — mismo patrón que
 * `ImdertyProfileForm.test.tsx`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import type { ImdertyGuardian, SensitiveAuthorization, SensitiveData } from "@/schemas/imderty";

// Polyfills de jsdom requeridos por Radix Select/AlertDialog (mismo patrón
// que `ArchivedAthletesPage.test.tsx`/`StaffPage.test.tsx`).
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

const createAuthorizationMutate = vi.fn();
const withdrawMutate = vi.fn();
const updateSensitiveDataMutate = vi.fn();
const sensitiveDataState: { data: SensitiveData | undefined; isLoading: boolean; isError: boolean } = {
  data: undefined,
  isLoading: false,
  isError: false,
};
const withdrawState = { isPending: false, isError: false, error: undefined as unknown };

vi.mock("@/hooks/useImderty", () => ({
  useCreateSensitiveAuthorization: () => ({ mutate: createAuthorizationMutate, isPending: false }),
  useWithdrawSensitiveAuthorization: () => ({
    mutate: withdrawMutate,
    isPending: withdrawState.isPending,
    isError: withdrawState.isError,
    error: withdrawState.error,
  }),
  useSensitiveData: () => sensitiveDataState,
  useUpdateSensitiveData: () => ({ mutate: updateSensitiveDataMutate, isPending: false }),
}));

import { SensitiveDataCard } from "@/components/imderty/SensitiveDataCard";

const guardians: ImdertyGuardian[] = [
  { user_id: 1, display_name: "Acudiente Ficticio Uno", has_phone: true, is_primary_contact: true },
  { user_id: 2, display_name: "Acudiente Ficticio Dos", has_phone: false, is_primary_contact: false },
];

const activeAuthorization: SensitiveAuthorization = {
  id: 9,
  guardian_user_id: 1,
  authorized_on: "2026-01-15",
  active: true,
};

function renderCard(props?: {
  guardians?: ImdertyGuardian[];
  authorization?: SensitiveAuthorization | null;
}) {
  return render(
    <SensitiveDataCard
      athleteId={7}
      guardians={props?.guardians ?? guardians}
      authorization={props?.authorization ?? null}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sensitiveDataState.data = undefined;
  sensitiveDataState.isLoading = false;
  sensitiveDataState.isError = false;
  withdrawState.isPending = false;
  withdrawState.isError = false;
  withdrawState.error = undefined;
});

// ---------------------------------------------------------------------------
// Bloqueado vs. desbloqueado
// ---------------------------------------------------------------------------

describe("SensitiveDataCard — bloqueado sin autorización", () => {
  it("muestra la alerta de bloqueo y no expone los tres campos", () => {
    renderCard({ authorization: null });

    expect(screen.getByText("Bloqueado sin autorización")).toBeInTheDocument();
    expect(screen.queryByLabelText("Etnia")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Discapacidad")).not.toBeInTheDocument();
  });

  it("deshabilita 'Registrar autorización' sin acudientes vinculados", () => {
    renderCard({ guardians: [], authorization: null });

    expect(screen.getByRole("button", { name: "Registrar autorización" })).toBeDisabled();
    expect(
      screen.getByText(/no tiene un acudiente vinculado todavía/i),
    ).toBeInTheDocument();
  });

  it("habilita 'Registrar autorización' con al menos un acudiente", () => {
    renderCard({ authorization: null });
    expect(screen.getByRole("button", { name: "Registrar autorización" })).toBeEnabled();
  });
});

describe("SensitiveDataCard — desbloqueado con autorización activa", () => {
  it("muestra el indicador 'Autorizado' y el editor de los tres campos", async () => {
    sensitiveDataState.data = { ethnicity: "MESTIZO", disability: "N/A", conflict_victim: "no" };
    renderCard({ authorization: activeAuthorization });

    expect(screen.getByText("Autorizado")).toBeInTheDocument();
    expect(await screen.findByText("Etnia")).toBeInTheDocument();
    expect(screen.getByText("Discapacidad")).toBeInTheDocument();
    expect(screen.getByText("Víctima del conflicto armado")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retirar autorización" })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Diálogo: registrar autorización
// ---------------------------------------------------------------------------

describe("SensitiveDataCard — registrar autorización", () => {
  it("abre el diálogo (no window.confirm) y envía el acudiente + fecha elegidos", async () => {
    const confirmSpy = vi.spyOn(window, "confirm");
    const user = userEvent.setup();
    renderCard({ authorization: null });

    await user.click(screen.getByRole("button", { name: "Registrar autorización" }));
    expect(await screen.findByRole("dialog", { name: "Registrar autorización" })).toBeInTheDocument();
    expect(confirmSpy).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Registrar" }));

    await waitFor(() => expect(createAuthorizationMutate).toHaveBeenCalledTimes(1));
    const [payload] = createAuthorizationMutate.mock.calls[0] as [
      { guardian_user_id: number; authorized_on: string },
      unknown,
    ];
    expect(payload.guardian_user_id).toBe(1);
    expect(payload.authorized_on).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

// ---------------------------------------------------------------------------
// Edición — conflict_victim sin default
// ---------------------------------------------------------------------------

describe("SensitiveDataCard — edición de los tres campos", () => {
  it("bloquea el guardado si víctima del conflicto no se elige explícitamente", async () => {
    sensitiveDataState.data = undefined; // sin fila previa: usa los defaults del formulario
    const user = userEvent.setup();
    renderCard({ authorization: activeAuthorization });

    await screen.findByText("Etnia");
    await user.click(screen.getByRole("button", { name: "Guardar datos sensibles" }));

    // El placeholder del combobox y el mensaje de error de Zod comparten el
    // mismo texto ("Selecciona SI o NO"); se acota al `role="alert"` del
    // `FormMessage` para no ambigüar con el placeholder siempre visible.
    expect(await screen.findByRole("alert")).toHaveTextContent("Selecciona SI o NO");
    expect(updateSensitiveDataMutate).not.toHaveBeenCalled();
  });

  it("guarda con los defaults NO SABE NO RESPONDE / N/A una vez elegido SI/NO", async () => {
    sensitiveDataState.data = undefined;
    const user = userEvent.setup();
    renderCard({ authorization: activeAuthorization });

    await screen.findByText("Etnia");
    await user.click(screen.getByRole("combobox", { name: /Víctima del conflicto armado/i }));
    await user.click(await screen.findByRole("option", { name: "SI" }));
    await user.click(screen.getByRole("button", { name: "Guardar datos sensibles" }));

    await waitFor(() => expect(updateSensitiveDataMutate).toHaveBeenCalledTimes(1));
    const [payload] = updateSensitiveDataMutate.mock.calls[0] as [
      { ethnicity: string; disability: string; conflict_victim: string },
      unknown,
    ];
    expect(payload).toEqual({
      ethnicity: "NO SABE NO RESPONDE",
      disability: "N/A",
      conflict_victim: "si",
    });
  });
});

// ---------------------------------------------------------------------------
// Retirar autorización
// ---------------------------------------------------------------------------

describe("SensitiveDataCard — retirar autorización", () => {
  it("abre un ConfirmDialog (no window.confirm) que explica el borrado, y confirma la baja", async () => {
    sensitiveDataState.data = { ethnicity: "MESTIZO", disability: "N/A", conflict_victim: "no" };
    const confirmSpy = vi.spyOn(window, "confirm");
    const user = userEvent.setup();
    renderCard({ authorization: activeAuthorization });

    await screen.findByText("Etnia");
    await user.click(screen.getByRole("button", { name: "Retirar autorización" }));

    const dialog = await screen.findByRole("alertdialog", { name: "Retirar autorización" });
    expect(dialog).toHaveTextContent(/se borrarán de inmediato/i);
    expect(confirmSpy).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Retirar autorización" }));

    await waitFor(() => expect(withdrawMutate).toHaveBeenCalledTimes(1));
  });

  it("cancelar cierra el diálogo sin llamar a la mutación", async () => {
    sensitiveDataState.data = { ethnicity: "MESTIZO", disability: "N/A", conflict_victim: "no" };
    const user = userEvent.setup();
    renderCard({ authorization: activeAuthorization });

    await screen.findByText("Etnia");
    await user.click(screen.getByRole("button", { name: "Retirar autorización" }));
    await screen.findByRole("alertdialog", { name: "Retirar autorización" });

    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(withdrawMutate).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument(),
    );
  });
});

// ---------------------------------------------------------------------------
// Accesibilidad
// ---------------------------------------------------------------------------

describe("SensitiveDataCard — accesibilidad", () => {
  it("0 violaciones jest-axe bloqueado", async () => {
    const { container } = renderCard({ authorization: null });
    // Todas las reglas activas, heading-order incluida: `LockedState` ya no
    // usa `AlertTitle` (h5) bajo el `CardTitle` (h3).
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("0 violaciones jest-axe bloqueado bajo un h2 de página (heading-order)", async () => {
    // Contexto real: la tarjeta vive bajo la ficha del atleta (h1/h2). La
    // tarjeta no debe introducir ningún encabezado por debajo de su h3.
    const { container } = render(
      <main>
        <h1>Ficha del atleta</h1>
        <h2>Datos IMDERTY</h2>
        <SensitiveDataCard athleteId={7} guardians={[]} authorization={null} />
      </main>,
    );
    const headings = Array.from(container.querySelectorAll("h1, h2, h3, h4, h5, h6")).map(
      (h) => h.tagName,
    );
    expect(headings).not.toContain("H5");
    expect(headings).not.toContain("H6");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("0 violaciones jest-axe con el error de carga (sin h5)", async () => {
    sensitiveDataState.isError = true;
    const { container } = renderCard({ authorization: activeAuthorization });
    await screen.findByText("No se pudieron cargar los datos sensibles");
    expect(container.querySelector("h5")).toBeNull();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("0 violaciones jest-axe desbloqueado", async () => {
    sensitiveDataState.data = { ethnicity: "MESTIZO", disability: "N/A", conflict_victim: "no" };
    const { container } = renderCard({ authorization: activeAuthorization });
    await screen.findByText("Etnia");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("0 violaciones jest-axe con el diálogo de retiro abierto", async () => {
    sensitiveDataState.data = { ethnicity: "MESTIZO", disability: "N/A", conflict_victim: "no" };
    const user = userEvent.setup();
    renderCard({ authorization: activeAuthorization });
    await screen.findByText("Etnia");
    await user.click(screen.getByRole("button", { name: "Retirar autorización" }));
    await screen.findByRole("alertdialog", { name: "Retirar autorización" });

    const results = await axe(document.body);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
