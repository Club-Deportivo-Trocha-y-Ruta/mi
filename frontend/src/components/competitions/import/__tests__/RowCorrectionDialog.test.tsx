/**
 * Tests para RowCorrectionDialog (feature 044, US1, T022/T023).
 *
 * Cubre:
 *  - Precarga: operación y puesto sugeridos por el hueco detectado.
 *  - Los campos de la fila (nombre, dorsal, ciudad, club, tiempo, puntos)
 *    solo se muestran para agregar/editar — no para eliminar.
 *  - Validación Zod localizada: nombre obligatorio en add/edit.
 *  - Submit exitoso llama a `addRaceImportRowCorrection` con el payload
 *    correcto (`row.position === ordinal`, research R-05 §_build_row) y
 *    propaga la completitud recalculada vía `onCorrected`.
 *  - Cambiar a "Eliminar" oculta los campos de fila y envía `row: null`.
 *  - Estado de error en la mutación: mensaje inline, el diálogo NO se cierra.
 *  - a11y: 0 violaciones jest-axe.
 *
 * Estrategia: mockeamos `@/api/raceImports` (mismo patrón que
 * `DiffConfirm.test.tsx`/`ImportWizard.test.tsx` en esta carpeta) en vez de
 * levantar MSW — este módulo no está en el registro global de handlers.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

expect.extend(toHaveNoViolations);

vi.mock("@/api/raceImports", () => ({
  addRaceImportRowCorrection: vi.fn(),
}));

import * as raceImportsApi from "@/api/raceImports";
import { RowCorrectionDialog } from "@/components/competitions/import/RowCorrectionDialog";
import type { CategoryCompleteness } from "@/types/raceImports.types";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

const OK_COMPLETENESS: CategoryCompleteness = {
  status: "ok",
  missing: [],
  duplicated: [],
};

function renderDialog(
  overrides: Partial<React.ComponentProps<typeof RowCorrectionDialog>> = {},
) {
  const onOpenChange = vi.fn();
  const onCorrected = vi.fn();
  wrap(
    <RowCorrectionDialog
      open
      onOpenChange={onOpenChange}
      parseId="42"
      categoryHeader="INFANTIL A DAMAS"
      initialOp="add"
      initialOrdinal={6}
      initialRow={null}
      onCorrected={onCorrected}
      {...overrides}
    />,
  );
  return { onOpenChange, onCorrected };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RowCorrectionDialog — precarga", () => {
  it("precarga la operación y el puesto sugeridos por el hueco", async () => {
    renderDialog({ initialOp: "add", initialOrdinal: 6 });

    const addRadio = await screen.findByRole("radio", { name: "Agregar" });
    expect(addRadio).toHaveAttribute("aria-checked", "true");
    expect(screen.getByLabelText(/puesto/i)).toHaveValue(6);
  });

  it("muestra los campos de fila para agregar/editar", async () => {
    renderDialog({ initialOp: "edit", initialOrdinal: 20 });

    expect(await screen.findByLabelText(/^nombre$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/dorsal/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/ciudad/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/club/i)).toBeInTheDocument();
  });

  it("oculta los campos de fila y muestra el aviso al elegir Eliminar", async () => {
    const user = userEvent.setup();
    renderDialog({ initialOp: "edit", initialOrdinal: 20 });

    await user.click(screen.getByRole("radio", { name: "Eliminar" }));

    expect(screen.queryByLabelText(/^nombre$/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(/se quita de la categoría solo en esta importación/i),
    ).toBeInTheDocument();
  });
});

describe("RowCorrectionDialog — validación", () => {
  it("exige nombre para agregar/editar y no dispara la mutación", async () => {
    const user = userEvent.setup();
    renderDialog({ initialOp: "add", initialOrdinal: 6 });

    await user.click(screen.getByRole("button", { name: /^Guardar$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /el nombre es obligatorio/i,
    );
    expect(raceImportsApi.addRaceImportRowCorrection).not.toHaveBeenCalled();
  });
});

describe("RowCorrectionDialog — submit", () => {
  it("agrega una fila con position === ordinal y notifica la completitud", async () => {
    vi.mocked(raceImportsApi.addRaceImportRowCorrection).mockResolvedValue({
      category_header: "INFANTIL A DAMAS",
      completeness: OK_COMPLETENESS,
    });

    const user = userEvent.setup();
    const { onOpenChange, onCorrected } = renderDialog({
      initialOp: "add",
      initialOrdinal: 6,
    });

    await user.type(screen.getByLabelText(/^nombre$/i), "Corredora Ficticia");
    await user.click(screen.getByRole("button", { name: /^Guardar$/i }));

    await waitFor(() =>
      expect(raceImportsApi.addRaceImportRowCorrection).toHaveBeenCalledTimes(1),
    );
    const [parseId, body] = vi.mocked(raceImportsApi.addRaceImportRowCorrection).mock
      .calls[0];
    expect(parseId).toBe("42");
    expect(body).toMatchObject({
      op: "add",
      category_header: "INFANTIL A DAMAS",
      ordinal: 6,
      row: expect.objectContaining({
        position: 6,
        name: "Corredora Ficticia",
      }),
    });

    await waitFor(() => expect(onCorrected).toHaveBeenCalledWith(OK_COMPLETENESS));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("elimina una fila enviando row: null", async () => {
    vi.mocked(raceImportsApi.addRaceImportRowCorrection).mockResolvedValue({
      category_header: "INFANTIL A DAMAS",
      completeness: OK_COMPLETENESS,
    });

    const user = userEvent.setup();
    renderDialog({ initialOp: "edit", initialOrdinal: 20 });

    await user.click(screen.getByRole("radio", { name: "Eliminar" }));
    await user.click(screen.getByRole("button", { name: /^Guardar$/i }));

    await waitFor(() =>
      expect(raceImportsApi.addRaceImportRowCorrection).toHaveBeenCalledTimes(1),
    );
    const [, body] = vi.mocked(raceImportsApi.addRaceImportRowCorrection).mock.calls[0];
    expect(body).toMatchObject({ op: "remove", ordinal: 20, row: null });
  });

  it("muestra error inline y NO cierra el diálogo si la mutación falla", async () => {
    vi.mocked(raceImportsApi.addRaceImportRowCorrection).mockRejectedValue(
      new Error("network"),
    );

    const user = userEvent.setup();
    const { onOpenChange } = renderDialog({ initialOp: "add", initialOrdinal: 6 });

    await user.type(screen.getByLabelText(/^nombre$/i), "Corredora Ficticia");
    await user.click(screen.getByRole("button", { name: /^Guardar$/i }));

    await waitFor(() =>
      expect(screen.getByText(/no se pudo guardar la corrección/i)).toBeInTheDocument(),
    );
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});

describe("RowCorrectionDialog — accesibilidad", () => {
  it("0 violaciones axe con el diálogo abierto", async () => {
    renderDialog({ initialOp: "add", initialOrdinal: 6 });
    await screen.findByLabelText(/^nombre$/i);

    const results = await axe(document.body);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
