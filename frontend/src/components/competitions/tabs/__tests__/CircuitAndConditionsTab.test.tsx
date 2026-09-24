/**
 * CircuitAndConditionsTab — pestaña «Circuito y condiciones» (feature 045,
 * US6, T049).
 *
 * Cubre:
 *  - Compone `CourseTab` (circuito) y `ConditionsTab` (condiciones) reales en
 *    un solo panel, circuito primero.
 *  - Cada bloque lleva su `<h2>` y su `<section>` nombrada (orden de
 *    encabezados válido bajo el h1 de la página).
 *  - Las condiciones del evento llegan a la tarjeta (`RaceConditionsCard`).
 *  - 0 violaciones jest-axe.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

import { useAuthStore } from "@/store/auth.store";
import { makeRaceEventRead } from "@/test/msw/raceEventsHandlers";
import { CircuitAndConditionsTab } from "@/components/competitions/tabs/CircuitAndConditionsTab";

function mockAuthAs(role: "admin" | "coach") {
  const state = {
    accessToken: "test-token",
    user: { id: 1, role, first_name: "U", last_name: "T" },
    isAuthenticated: true,
  };
  vi.mocked(useAuthStore).mockImplementation(
    ((sel: (s: typeof state) => unknown) => sel(state)) as unknown as typeof useAuthStore,
  );
}

function renderTab(event = makeRaceEventRead({ id: 1 })) {
  // Fixture por defecto: condiciones completas (clima, temperatura, superficie
  // y altitud) → `RaceConditionsCard` en estado «complete».
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        {/* h1 de la página: el componente vive bajo el encabezado del detalle. */}
        <h1>Copa Valle XCO — Válida I</h1>
        <CircuitAndConditionsTab raceEventId={event.id} event={event} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAuthAs("coach");
});

describe("CircuitAndConditionsTab", () => {
  it("monta el circuito y las condiciones en un mismo panel, circuito primero", async () => {
    renderTab();

    const panel = screen.getByTestId("circuit-conditions-tab");
    const circuit = within(panel).getByRole("region", { name: "Circuito" });
    const conditions = within(panel).getByRole("region", { name: "Condiciones" });

    // `CourseTab` (perezoso) resuelve con el fixture feliz global.
    expect(await within(circuit).findByTestId("course-tab")).toBeInTheDocument();
    expect(
      within(conditions).getByTestId("race-conditions-card-complete"),
    ).toBeInTheDocument();

    // Orden en el DOM: circuito antes que condiciones.
    expect(
      circuit.compareDocumentPosition(conditions) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("cada bloque tiene su <h2> bajo el h1 de la página", async () => {
    renderTab();
    await screen.findByTestId("course-tab");

    expect(
      screen.getByRole("heading", { level: 2, name: "Circuito" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "Condiciones" }),
    ).toBeInTheDocument();
  });

  it("evento sin condiciones: la tarjeta queda en estado vacío y el circuito sigue montado", async () => {
    renderTab(
      makeRaceEventRead({
        id: 2,
        climate: null,
        temperature_c: null,
        surface_condition: null,
        altitude_msnm: null,
        weather_notes: null,
      }),
    );
    expect(await screen.findByTestId("course-tab")).toBeInTheDocument();
    expect(screen.getByTestId("race-conditions-card-empty")).toBeInTheDocument();
  });

  it("0 violaciones jest-axe", async () => {
    const { container } = renderTab();
    await screen.findByTestId("course-variants-card");
    expect(await axe(container)).toHaveNoViolations();
  }, 15_000);
});
