/**
 * Tests de HeaderOverridesForm (feature 047, US3, T045).
 *
 * Cubre: precarga desde la configuración del club, los cambios del coach se
 * emiten hacia el padre (overrides «enviados» vía `onChange`, no hay POST
 * propio — ver el comentario de cabecera del componente), la casilla
 * «Guardar como predeterminado» se respeta, y cero violaciones axe.
 *
 * `getClubImdertySettings` se mockea a nivel de `@/api/imderty` (mismo
 * patrón que `BarrioCombobox.test.tsx`), no vía MSW.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

vi.mock("@/api/imderty", () => ({
  getClubImdertySettings: vi.fn(),
}));

import { getClubImdertySettings } from "@/api/imderty";
import { HeaderOverridesForm } from "@/components/imderty/HeaderOverridesForm";
import type { ClubImdertySettings, ImdertySheetHeaderValues } from "@/schemas/imderty";

const mockGetSettings = vi.mocked(getClubImdertySettings);

const SAVED_SETTINGS: ClubImdertySettings = {
  contractor_name: "Club Trocha y Ruta",
  venue: "Coliseo municipal",
  training_days: "LUNES A VIERNES",
  schedule: "4:00 PM A 6:00 PM",
  programs: ["individual", "competencia"],
};

function renderForm({
  onChange = vi.fn(),
  onSaveAsDefaultChange = vi.fn(),
  saveAsDefault = false,
}: {
  onChange?: (header: ImdertySheetHeaderValues) => void;
  onSaveAsDefaultChange?: (value: boolean) => void;
  saveAsDefault?: boolean;
} = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <HeaderOverridesForm
        clubId={7}
        saveAsDefault={saveAsDefault}
        onSaveAsDefaultChange={onSaveAsDefaultChange}
        onChange={onChange}
      />
    </QueryClientProvider>,
  );
  return { ...utils, onChange, onSaveAsDefaultChange };
}

describe("HeaderOverridesForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("no emite `onChange` mientras la configuración del club sigue cargando", async () => {
    mockGetSettings.mockReturnValue(new Promise(() => {}));
    const onChange = vi.fn();
    renderForm({ onChange });

    expect(
      await screen.findByLabelText("Cargando configuración del encabezado…"),
    ).toBeInTheDocument();
    // Nunca debe emitir el formulario en blanco mientras no se sabe si el
    // club tiene configuración guardada (ver el comentario de `onChange`
    // en el componente): el padre debe poder seguir mandando `header: null`
    // y así heredar la configuración del club en el backend.
    expect(onChange).not.toHaveBeenCalled();
  });

  it("precarga los campos desde la configuración guardada del club", async () => {
    mockGetSettings.mockResolvedValue(SAVED_SETTINGS);
    const onChange = vi.fn();
    renderForm({ onChange });

    expect(await screen.findByDisplayValue("Club Trocha y Ruta")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Coliseo municipal")).toBeInTheDocument();
    expect(screen.getByDisplayValue("LUNES A VIERNES")).toBeInTheDocument();
    expect(screen.getByDisplayValue("4:00 PM A 6:00 PM")).toBeInTheDocument();
    expect(screen.getByLabelText("Individual")).toBeChecked();
    expect(screen.getByLabelText("Competencia")).toBeChecked();
    expect(screen.getByLabelText("Masificación")).not.toBeChecked();

    await waitFor(() =>
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({
          contractor_name: "Club Trocha y Ruta",
          venue: "Coliseo municipal",
          training_days: "LUNES A VIERNES",
          schedule: "4:00 PM A 6:00 PM",
          programs: ["individual", "competencia"],
        }),
      ),
    );
  });

  it("los cambios del coach se envían al padre sin tocar la configuración guardada", async () => {
    mockGetSettings.mockResolvedValue(SAVED_SETTINGS);
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderForm({ onChange });

    const scheduleInput = await screen.findByDisplayValue("4:00 PM A 6:00 PM");
    await user.clear(scheduleInput);
    await user.type(scheduleInput, "5:00 PM A 7:00 PM");

    await waitFor(() =>
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ schedule: "5:00 PM A 7:00 PM" }),
      ),
    );
    // El mock de la API nunca se llama para escribir: no hay PUT propio.
    expect(mockGetSettings).toHaveBeenCalledTimes(1);
  });

  it("agregar un programa lo incluye en el header emitido", async () => {
    mockGetSettings.mockResolvedValue(SAVED_SETTINGS);
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderForm({ onChange });

    await screen.findByDisplayValue("Club Trocha y Ruta");
    await user.click(screen.getByLabelText("Recreación"));

    await waitFor(() =>
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({
          programs: expect.arrayContaining(["individual", "competencia", "recreacion"]),
        }),
      ),
    );
  });

  it("la casilla «Guardar como predeterminado» se respeta", async () => {
    mockGetSettings.mockResolvedValue(SAVED_SETTINGS);
    const onSaveAsDefaultChange = vi.fn();
    const user = userEvent.setup();
    renderForm({ onSaveAsDefaultChange });

    await screen.findByDisplayValue("Club Trocha y Ruta");
    await user.click(screen.getByLabelText("Guardar como predeterminado"));

    expect(onSaveAsDefaultChange).toHaveBeenCalledWith(true);
  });

  it("sin violaciones axe", async () => {
    mockGetSettings.mockResolvedValue(SAVED_SETTINGS);
    const { container } = renderForm();

    await screen.findByDisplayValue("Club Trocha y Ruta");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
