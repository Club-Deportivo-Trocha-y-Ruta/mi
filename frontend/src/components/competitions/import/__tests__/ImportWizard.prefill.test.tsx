/**
 * Tests del prefill del ImportWizard lanzado desde una competencia (US1, feature 015).
 *
 * Cubre:
 *  - El wizard con `raceEventId` precarga nombre/fecha/ciudad/serie/tipo (T007/US1).
 *  - El coach NO re-teclea metadata: los inputs editables de identidad no existen.
 *  - El "Válida #" de la copa aparece como dato bloqueado.
 *
 * Privacidad: los fixtures solo contienen metadata de competencia (FR-013).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { createElement, type ReactNode } from "react";

// raceImports API se mockea (no se ejercita el parse/dry-run en render); el
// prefill usa raceEvents + raceSeries reales contra MSW.
vi.mock("@/api/raceImports", () => ({
  parseRaceImport: vi.fn(),
  dryRunRaceImport: vi.fn(),
  commitRaceImport: vi.fn(),
  listRaceImports: vi.fn(),
  getRevisionReasons: vi.fn(),
  getRaceEventDiff: vi.fn(),
}));
vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

import { mswServer } from "@/test/setup";
import { raceSeriesHandlers } from "@/test/msw/raceSeriesHandlers";
import { prefillCupEventHandler } from "@/test/msw/raceEventsHandlers";
import { ImportWizard } from "@/components/competitions/import/ImportWizard";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(MemoryRouter, null, ui),
    ),
  );
}

describe("ImportWizard — prefill desde competencia (US1)", () => {
  beforeEach(() => {
    mswServer.use(...raceSeriesHandlers, prefillCupEventHandler);
  });

  it("precarga identidad (nombre/fecha/ciudad/serie/tipo) sin re-tecleo", async () => {
    wrap(<ImportWizard raceEventId={2} />);

    const summary = await screen.findByTestId("prefill-locked-summary");
    expect(summary).toBeInTheDocument();

    // Valores derivados del evento + serie (copa).
    expect(summary).toHaveTextContent("Copa");
    expect(summary).toHaveTextContent("Copa Valle de Ciclomontañismo");
    expect(summary).toHaveTextContent("2026");
    expect(summary).toHaveTextContent("Copa Valle XCO — Válida IV");
    expect(summary).toHaveTextContent("2026-05-17");
    expect(summary).toHaveTextContent("Cali");
    // La copa muestra su válida bloqueada.
    expect(summary).toHaveTextContent("Válida #");
    expect(summary).toHaveTextContent("4");
  });

  it("no hay inputs editables de identidad (cero re-tecleo)", async () => {
    wrap(<ImportWizard raceEventId={2} />);
    await screen.findByTestId("prefill-locked-summary");

    // En modo prefill no se renderiza el selector de tipo ni el input de serie.
    expect(screen.queryByTestId("wizard-series-kind")).not.toBeInTheDocument();
    expect(screen.queryByTestId("wizard-series-name")).not.toBeInTheDocument();
    expect(screen.queryByTestId("wizard-event-name")).not.toBeInTheDocument();

    // Los uploads y "Continuar" siguen presentes (el coach solo aporta el PDF).
    expect(screen.getByTestId("wizard-step1-submit")).toBeInTheDocument();
  });
});
