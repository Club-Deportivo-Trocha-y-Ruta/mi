/**
 * Tests para SessionPickerDialog (feature 032, T012) — el selector compartido
 * "¿A qué sesión?" (research.md R6):
 *
 *   - Orden ascendente (R6/R10, la regresión que este test existe para
 *     evitar): `useTrainingSessions` se mockea devolviendo el orden real del
 *     servicio — `scheduled_date DESC` (`backend/app/services/training/
 *     sessions.py:905-910`, la sesión más lejana en el futuro primero). El
 *     componente debe reordenar el resultado ascendente por
 *     `(scheduled_date, scheduled_start_time)` antes de mostrar las próximas
 *     ~5 sesiones — nunca confiar en el orden crudo de la API.
 *   - El buscador de texto encuentra sesiones fuera de las próximas 5
 *     mostradas por defecto (fallback para cualquier sesión más lejana).
 *   - `onSelect` se dispara con el id de la sesión elegida.
 *   - a11y: jest-axe sin violaciones.
 *
 * Estrategia de mock: `useTrainingSessions` se mockea a nivel de módulo
 * (mirror de `TemplatePicker.test.tsx`) — sin MSW, sin red real.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import type { TrainingSession } from "@/types/trainingSession.types";

const mockUseTrainingSessions = vi.fn();

vi.mock("@/api/trainingSessions", () => ({
  useTrainingSessions: (...args: unknown[]) => mockUseTrainingSessions(...args),
}));

import {
  SessionPickerDialog,
  type SessionPickerDialogProps,
} from "../SessionPickerDialog";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Fixtures — datos ficticios, nunca datos reales de atletas TyR
// ---------------------------------------------------------------------------

function makeSession(
  overrides: Partial<TrainingSession> & { id: number },
): TrainingSession {
  return {
    club_id: 1,
    created_by_user_id: 1,
    status: "planned",
    scheduled_date: "2026-07-20",
    scheduled_start_time: "09:00:00",
    duration_min: 90,
    location: "Sevilla",
    technical_focus: "Frenado",
    description: "",
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-01T00:00:00Z",
    ...overrides,
  };
}

// Ascendente: A (más próxima) → B → C → D → E → F (más lejana, fuera del
// límite de "próximas 5").
const SESSION_A = makeSession({
  id: 1,
  scheduled_date: "2026-07-20",
  scheduled_start_time: "09:00:00",
  location: "Sevilla",
});
const SESSION_B = makeSession({
  id: 2,
  scheduled_date: "2026-07-20",
  scheduled_start_time: "16:00:00",
  location: "Cali",
});
const SESSION_C = makeSession({
  id: 3,
  scheduled_date: "2026-07-25",
  scheduled_start_time: "10:00:00",
  location: "Ginebra",
});
const SESSION_D = makeSession({
  id: 4,
  scheduled_date: "2026-08-01",
  scheduled_start_time: "10:00:00",
  location: "Palmira",
});
const SESSION_E = makeSession({
  id: 5,
  scheduled_date: "2026-08-15",
  scheduled_start_time: "10:00:00",
  location: "Roldanillo",
});
const SESSION_F = makeSession({
  id: 6,
  scheduled_date: "2026-09-01",
  scheduled_start_time: "10:00:00",
  location: "Yumbo",
});

/** Orden real devuelto por el servicio: scheduled_date DESC (la más lejana primero). */
const DESC_ORDERED_SESSIONS = [
  SESSION_F,
  SESSION_E,
  SESSION_D,
  SESSION_C,
  SESSION_B,
  SESSION_A,
];

function successResult(items: TrainingSession[]) {
  return {
    data: items,
    isLoading: false,
    isError: false,
    error: null,
  };
}

function renderDialog(overrides: Partial<SessionPickerDialogProps> = {}) {
  const onOpenChange = vi.fn();
  const onSelect = vi.fn();
  const utils = render(
    <SessionPickerDialog
      open
      onOpenChange={onOpenChange}
      onSelect={onSelect}
      {...overrides}
    />,
  );
  return { ...utils, onOpenChange, onSelect };
}

// ---------------------------------------------------------------------------
// Suite: filtrado de sesiones (status=planned) y estado del hook
// ---------------------------------------------------------------------------

describe("SessionPickerDialog", () => {
  beforeEach(() => {
    mockUseTrainingSessions.mockReturnValue(successResult(DESC_ORDERED_SESSIONS));
  });

  it("consulta useTrainingSessions filtrando por status=planned", () => {
    renderDialog();
    expect(mockUseTrainingSessions).toHaveBeenCalledWith({ status: "planned" });
  });

  it("no renderiza el diálogo cuando open=false", () => {
    renderDialog({ open: false });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Regresión R6/R10: la API responde scheduled_date DESC — el componente
  // debe reordenar ascendente antes de mostrar las próximas 5.
  // -------------------------------------------------------------------------

  it("reordena la lista ascendente por (scheduled_date, scheduled_start_time) pese al orden DESC de la API", () => {
    renderDialog();

    const dialog = screen.getByRole("dialog");
    const list = within(dialog).getByRole("list");
    const items = within(list).getAllByRole("listitem");

    // Próximas 5 en orden ascendente: A, B, C, D, E — F queda fuera del límite.
    const locations = items.map((li) => within(li).getByRole("button").textContent);
    expect(locations[0]).toContain("Sevilla");
    expect(locations[1]).toContain("Cali");
    expect(locations[2]).toContain("Ginebra");
    expect(locations[3]).toContain("Palmira");
    expect(locations[4]).toContain("Roldanillo");
    expect(items).toHaveLength(5);
    expect(within(dialog).queryByText(/Yumbo/)).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Buscador de texto — fallback para sesiones fuera de las próximas 5
  // -------------------------------------------------------------------------

  it("el buscador de texto encuentra una sesión fuera de las próximas 5", async () => {
    const user = userEvent.setup();
    renderDialog();

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByText(/Yumbo/)).not.toBeInTheDocument();

    const search = within(dialog).getByRole("searchbox", { name: "Buscar sesión" });
    await user.type(search, "Yumbo");

    expect(within(dialog).getByText(/Yumbo/)).toBeInTheDocument();
    // El resto de la lista queda filtrado.
    expect(within(dialog).queryByText(/Sevilla/)).not.toBeInTheDocument();
  });

  it("el buscador de texto filtra la lista mostrada por defecto", async () => {
    const user = userEvent.setup();
    renderDialog();

    const dialog = screen.getByRole("dialog");
    const search = within(dialog).getByRole("searchbox", { name: "Buscar sesión" });
    await user.type(search, "Cali");

    const list = within(dialog).getByRole("list");
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(1);
    expect(within(items[0]).getByRole("button").textContent).toContain("Cali");
  });

  it("muestra un mensaje cuando el buscador no encuentra resultados", async () => {
    const user = userEvent.setup();
    renderDialog();

    const dialog = screen.getByRole("dialog");
    const search = within(dialog).getByRole("searchbox", { name: "Buscar sesión" });
    await user.type(search, "Popayán");

    expect(
      within(dialog).getByText(/No se encontraron sesiones/i),
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // onSelect
  // -------------------------------------------------------------------------

  it("onSelect se dispara con el id de la sesión elegida", async () => {
    const user = userEvent.setup();
    const { onSelect } = renderDialog();

    const dialog = screen.getByRole("dialog");
    const cardButton = within(dialog)
      .getAllByRole("button")
      .find((btn) => btn.textContent?.includes("Cali"));
    expect(cardButton).toBeDefined();
    await user.click(cardButton!);

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(2);
  });

  // -------------------------------------------------------------------------
  // Estados de carga / error / vacío
  // -------------------------------------------------------------------------

  it("muestra un estado de carga mientras useTrainingSessions está pendiente", () => {
    mockUseTrainingSessions.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    });
    renderDialog();

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("muestra un mensaje cuando no hay sesiones planificadas", () => {
    mockUseTrainingSessions.mockReturnValue(successResult([]));
    renderDialog();

    expect(
      screen.getByText(/No hay sesiones planificadas/i),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("SessionPickerDialog — accesibilidad", () => {
  beforeEach(() => {
    mockUseTrainingSessions.mockReturnValue(successResult(DESC_ORDERED_SESSIONS));
  });

  it("no tiene violaciones de a11y con la lista de sesiones", async () => {
    const { container } = renderDialog();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y en el estado vacío", async () => {
    mockUseTrainingSessions.mockReturnValue(successResult([]));
    const { container } = renderDialog();
    expect(await axe(container)).toHaveNoViolations();
  });
});
