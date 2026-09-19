/**
 * Tests para AcknowledgeGapDialog (feature 044, US1, T022/T023).
 *
 * Cubre:
 *  - El catálogo de motivos viene del backend (`getAcknowledgeReasons`), no
 *    de un arreglo hardcodeado en el cliente (research R-05: texto libre
 *    sobre un acta de menores invita a escribir nombres).
 *  - Confirmar sin elegir motivo muestra error inline y no dispara la
 *    mutación.
 *  - Submit exitoso llama a `acknowledgeRaceImportCategory` con el code
 *    elegido y propaga la completitud (`status: "acknowledged"`).
 *  - Estado de error en la mutación: mensaje inline, el diálogo NO se cierra.
 *  - a11y: 0 violaciones jest-axe.
 *
 * jsdom no implementa `hasPointerCapture`/`scrollIntoView` que el `Select`
 * de Radix usa internamente — mismo polyfill que `CancelEventDialog.test.tsx`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

expect.extend(toHaveNoViolations);

if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

vi.mock("@/api/raceImports", () => ({
  acknowledgeRaceImportCategory: vi.fn(),
  getAcknowledgeReasons: vi.fn(),
}));

import * as raceImportsApi from "@/api/raceImports";
import { AcknowledgeGapDialog } from "@/components/competitions/import/AcknowledgeGapDialog";
import type { CategoryCompleteness } from "@/types/raceImports.types";

const REASON_OPTIONS = [
  { code: "source_duplicate_ordinal", label: "El acta oficial repite un puesto" },
  { code: "source_missing_ordinal", label: "El acta oficial salta un puesto" },
  { code: "source_disqualification_gap", label: "El salto corresponde a una descalificación" },
  { code: "verified_against_source", label: "Verificado contra el acta oficial" },
];

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

function renderDialog(
  overrides: Partial<React.ComponentProps<typeof AcknowledgeGapDialog>> = {},
) {
  const onOpenChange = vi.fn();
  const onAcknowledged = vi.fn();
  wrap(
    <AcknowledgeGapDialog
      open
      onOpenChange={onOpenChange}
      parseId="42"
      categoryHeader="INFANTIL A DAMAS"
      onAcknowledged={onAcknowledged}
      {...overrides}
    />,
  );
  return { onOpenChange, onAcknowledged };
}

async function openSelectAndPick(label: string) {
  const user = userEvent.setup();
  await user.click(screen.getByRole("combobox", { name: /motivo/i }));
  await user.click(await screen.findByRole("option", { name: label }));
  return user;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(raceImportsApi.getAcknowledgeReasons).mockResolvedValue({
    options: REASON_OPTIONS,
  });
});

describe("AcknowledgeGapDialog — catálogo cerrado", () => {
  it("lista los motivos servidos por GET /acknowledge-reasons", async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole("combobox", { name: /motivo/i }));

    for (const { label } of REASON_OPTIONS) {
      expect(await screen.findByRole("option", { name: label })).toBeInTheDocument();
    }
  });
});

describe("AcknowledgeGapDialog — validación", () => {
  it("exige un motivo antes de reconocer", async () => {
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(raceImportsApi.getAcknowledgeReasons).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: /^Reconocer$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/selecciona un motivo/i);
    expect(raceImportsApi.acknowledgeRaceImportCategory).not.toHaveBeenCalled();
  });
});

describe("AcknowledgeGapDialog — submit", () => {
  it("reconoce la categoría con el motivo elegido y notifica la completitud", async () => {
    const acknowledgedCompleteness: CategoryCompleteness = {
      status: "acknowledged",
      missing: [6],
      duplicated: [],
    };
    vi.mocked(raceImportsApi.acknowledgeRaceImportCategory).mockResolvedValue({
      category_header: "INFANTIL A DAMAS",
      completeness: acknowledgedCompleteness,
    });

    const { onOpenChange, onAcknowledged } = renderDialog();
    await waitFor(() => expect(raceImportsApi.getAcknowledgeReasons).toHaveBeenCalled());

    const user = await openSelectAndPick("El acta oficial salta un puesto");
    await user.click(screen.getByRole("button", { name: /^Reconocer$/i }));

    await waitFor(() =>
      expect(raceImportsApi.acknowledgeRaceImportCategory).toHaveBeenCalledWith("42", {
        category_header: "INFANTIL A DAMAS",
        reason: "source_missing_ordinal",
      }),
    );
    await waitFor(() =>
      expect(onAcknowledged).toHaveBeenCalledWith(acknowledgedCompleteness),
    );
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("muestra error inline y NO cierra el diálogo si la mutación falla", async () => {
    vi.mocked(raceImportsApi.acknowledgeRaceImportCategory).mockRejectedValue(
      new Error("network"),
    );

    const { onOpenChange } = renderDialog();
    await waitFor(() => expect(raceImportsApi.getAcknowledgeReasons).toHaveBeenCalled());

    const user = await openSelectAndPick("Verificado contra el acta oficial");
    await user.click(screen.getByRole("button", { name: /^Reconocer$/i }));

    await waitFor(() =>
      expect(
        screen.getByText(/no se pudo guardar el reconocimiento/i),
      ).toBeInTheDocument(),
    );
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});

describe("AcknowledgeGapDialog — accesibilidad", () => {
  it("0 violaciones axe con el diálogo abierto", async () => {
    renderDialog();
    await waitFor(() => expect(raceImportsApi.getAcknowledgeReasons).toHaveBeenCalled());

    const results = await axe(document.body);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
