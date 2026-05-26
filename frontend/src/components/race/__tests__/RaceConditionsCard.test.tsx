/**
 * Tests para RaceConditionsCard (F-COND F4 — tarjeta tri-estado).
 *
 * Cubre:
 *  - Estado vacio (0 campos): coach ve botón "Agregar", parent no ve nada.
 *  - Estado parcial (1-3 campos): grilla con placeholder "— sin registro —"
 *    + botón "Completar".
 *  - Estado completo (>=4 campos): grilla con valores + botón "Editar".
 *  - Formato: `°C`, `msnm`, etiquetas humanas de surface ("Húmeda").
 *  - RBAC: parent NO ve ningún botón de edición.
 *  - a11y: 0 violaciones jest-axe.
 *
 * Estrategia de mock:
 *  - useAuthStore mockeado via vi.mock devolviendo role configurable por test.
 *  - EditConditionsDialog mockeado para evitar render del Sheet/Radix que mete
 *    portales fuera del container y rompe los asserts.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { createElement, type ReactNode } from "react";

// ----------------------------------------------------------------------------
// Mock de auth.store — el role se configura por test via setMockRole().
// Patrón: el mock vive a nivel de módulo y un helper actualiza la variable
// local antes de cada render. Coincide con el patrón de InsightsTimeline.test.
// ----------------------------------------------------------------------------
let mockRole: "coach" | "admin" | "parent" | "athlete" = "coach";
function setMockRole(r: typeof mockRole) {
  mockRole = r;
}

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: unknown) => unknown) =>
    selector({
      accessToken: "test-token",
      user: { id: 1, role: mockRole, first_name: "Test", last_name: "User" },
      isAuthenticated: true,
    }),
}));

// Mock del EditConditionsDialog para aislar el card de la pesadez del Sheet.
// Renderiza solo un sentinel que confirme que el card intentó abrirlo.
vi.mock("@/components/race/EditConditionsDialog", () => ({
  EditConditionsDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="edit-conditions-dialog-mock" /> : null,
}));

import { RaceConditionsCard } from "@/components/race/RaceConditionsCard";
import type { RaceEventConditions } from "@/types/raceEvents.types";

function wrap(ui: ReactNode) {
  // El card NO usa TanStack Query directamente (esa responsabilidad vive en
  // EditConditionsDialog → useUpdateRaceEventConditions, y ya está mockeado).
  // Solo necesitamos un render mínimo.
  return render(createElement("div", null, ui));
}

const COMPLETE_CONDITIONS: Partial<RaceEventConditions> = {
  climate: "Soleado",
  temperature_c: "22.5",
  surface_condition: "humeda",
  altitude_msnm: 1000,
  weather_notes: "Pista en buen estado tras drenaje matutino.",
};

const PARTIAL_CONDITIONS: Partial<RaceEventConditions> = {
  // Solo 2 de los 5 campos llenos → estado "partial".
  temperature_c: "18",
  altitude_msnm: 1340,
};

beforeEach(() => {
  vi.clearAllMocks();
  setMockRole("coach");
});

// ---------------------------------------------------------------------------
// Estado vacío (test #7)
// ---------------------------------------------------------------------------

describe("RaceConditionsCard — estado vacío", () => {
  it("muestra 'no registradas' + botón 'Agregar' visible solo para coach", () => {
    setMockRole("coach");
    wrap(<RaceConditionsCard raceEventId={42} conditions={null} />);

    expect(screen.getByTestId("race-conditions-card-empty")).toBeInTheDocument();
    expect(
      screen.getByText(/Condiciones de carrera no registradas/i),
    ).toBeInTheDocument();
    expect(screen.getByTestId("race-conditions-add-btn")).toBeInTheDocument();
    expect(screen.getByTestId("race-conditions-add-btn")).toHaveTextContent(
      /Agregar/i,
    );
  });

  it("parent NO ve el botón 'Agregar' en estado vacío", () => {
    setMockRole("parent");
    wrap(<RaceConditionsCard raceEventId={42} conditions={null} />);

    expect(screen.getByTestId("race-conditions-card-empty")).toBeInTheDocument();
    // Texto informativo sigue visible (puede leerlo)
    expect(
      screen.getByText(/Condiciones de carrera no registradas/i),
    ).toBeInTheDocument();
    // El CTA de edición NO debe existir
    expect(
      screen.queryByTestId("race-conditions-add-btn"),
    ).not.toBeInTheDocument();
  });

  it("acepta `conditions` undefined sin romper (defensive default)", () => {
    setMockRole("coach");
    wrap(<RaceConditionsCard raceEventId={42} conditions={undefined} />);
    expect(screen.getByTestId("race-conditions-card-empty")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Estado parcial (test #8)
// ---------------------------------------------------------------------------

describe("RaceConditionsCard — estado parcial", () => {
  it("renderiza grilla con placeholders '— sin registro —' + botón 'Completar'", () => {
    setMockRole("coach");
    wrap(
      <RaceConditionsCard raceEventId={42} conditions={PARTIAL_CONDITIONS} />,
    );

    const card = screen.getByTestId("race-conditions-card-partial");
    expect(card).toBeInTheDocument();

    // Botón Completar (no "Agregar" porque hay algún campo lleno).
    const editBtn = screen.getByTestId("race-conditions-edit-btn");
    expect(editBtn).toHaveTextContent(/Completar/i);

    // Valores llenos visibles
    expect(within(card).getByText("18 °C")).toBeInTheDocument();
    expect(within(card).getByText("1340 msnm")).toBeInTheDocument();

    // Placeholders para los faltantes (terreno, clima, notas → 3 ocurrencias).
    const placeholders = within(card).getAllByText(/— sin registro —/);
    expect(placeholders.length).toBeGreaterThanOrEqual(3);
  });

  it("parent NO ve botón en estado parcial", () => {
    setMockRole("parent");
    wrap(
      <RaceConditionsCard raceEventId={42} conditions={PARTIAL_CONDITIONS} />,
    );
    expect(screen.getByTestId("race-conditions-card-partial")).toBeInTheDocument();
    expect(
      screen.queryByTestId("race-conditions-edit-btn"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Estado completo (test #9)
// ---------------------------------------------------------------------------

describe("RaceConditionsCard — estado completo", () => {
  it("renderiza valores formateados y botón 'Editar' para coach", () => {
    setMockRole("coach");
    wrap(
      <RaceConditionsCard raceEventId={42} conditions={COMPLETE_CONDITIONS} />,
    );

    const card = screen.getByTestId("race-conditions-card-complete");
    expect(card).toBeInTheDocument();

    // Botón Editar (no "Agregar"/"Completar" en este estado).
    const editBtn = screen.getByTestId("race-conditions-edit-btn");
    expect(editBtn).toHaveTextContent(/Editar/i);

    // Formato: temperatura con sufijo °C
    expect(within(card).getByText("22.5 °C")).toBeInTheDocument();
    // Formato: altitud con sufijo msnm
    expect(within(card).getByText("1000 msnm")).toBeInTheDocument();
    // Surface mapeado a etiqueta humana: "humeda" → "Húmeda"
    expect(within(card).getByText("Húmeda")).toBeInTheDocument();
    expect(within(card).queryByText("humeda")).not.toBeInTheDocument();
    // Clima literal
    expect(within(card).getByText("Soleado")).toBeInTheDocument();
    // Notas
    expect(
      within(card).getByText(/Pista en buen estado tras drenaje matutino/i),
    ).toBeInTheDocument();
  });

  it("admin también ve el botón 'Editar' (RBAC: coach + admin)", () => {
    setMockRole("admin");
    wrap(
      <RaceConditionsCard raceEventId={42} conditions={COMPLETE_CONDITIONS} />,
    );
    expect(
      screen.getByTestId("race-conditions-edit-btn"),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// RBAC parent — refuerzo del test #10
// ---------------------------------------------------------------------------

describe("RaceConditionsCard — RBAC parent", () => {
  it("parent NO ve ningún botón de edición en NINGÚN estado", () => {
    setMockRole("parent");

    // Estado vacío
    const { unmount: u1 } = wrap(
      <RaceConditionsCard raceEventId={42} conditions={null} />,
    );
    expect(
      screen.queryByTestId("race-conditions-add-btn"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("race-conditions-edit-btn"),
    ).not.toBeInTheDocument();
    u1();

    // Estado parcial
    const { unmount: u2 } = wrap(
      <RaceConditionsCard raceEventId={42} conditions={PARTIAL_CONDITIONS} />,
    );
    expect(
      screen.queryByTestId("race-conditions-edit-btn"),
    ).not.toBeInTheDocument();
    u2();

    // Estado completo
    wrap(
      <RaceConditionsCard raceEventId={42} conditions={COMPLETE_CONDITIONS} />,
    );
    expect(
      screen.queryByTestId("race-conditions-edit-btn"),
    ).not.toBeInTheDocument();
  });

  it("athlete (rol futuro) tampoco ve botones de edición", () => {
    setMockRole("athlete");
    wrap(
      <RaceConditionsCard raceEventId={42} conditions={COMPLETE_CONDITIONS} />,
    );
    expect(
      screen.queryByTestId("race-conditions-edit-btn"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// A11y (test #15)
// ---------------------------------------------------------------------------

describe("RaceConditionsCard — accesibilidad", () => {
  it("estado vacío: 0 violaciones serias/críticas", async () => {
    setMockRole("coach");
    const { container } = wrap(
      <RaceConditionsCard raceEventId={42} conditions={null} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("estado parcial: 0 violaciones serias/críticas", async () => {
    setMockRole("coach");
    const { container } = wrap(
      <RaceConditionsCard raceEventId={42} conditions={PARTIAL_CONDITIONS} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);

  it("estado completo: 0 violaciones serias/críticas", async () => {
    setMockRole("coach");
    const { container } = wrap(
      <RaceConditionsCard raceEventId={42} conditions={COMPLETE_CONDITIONS} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 15_000);
});
