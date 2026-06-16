/**
 * "Válida #" según el tipo de competencia en el prefill — US4, feature 015.
 *
 * - Campeonato: el concepto "Válida #" NO aparece (FR-008, SC-006).
 * - Copa: la válida aparece como dato bloqueado.
 *
 * Privacidad: fixtures solo con metadata de competencia (FR-013).
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { createElement, type ReactNode } from "react";

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
import {
  prefillCupEventHandler,
  prefillChampionshipEventHandler,
} from "@/test/msw/raceEventsHandlers";
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

describe("ImportWizard — válida según tipo (US4)", () => {
  it("campeonato: no muestra 'Válida #' (FR-008)", async () => {
    mswServer.use(...raceSeriesHandlers, prefillChampionshipEventHandler);
    wrap(<ImportWizard raceEventId={15} />);

    const summary = await screen.findByTestId("prefill-locked-summary");
    expect(summary).toHaveTextContent("Campeonato");
    expect(within(summary).queryByText(/Válida #/i)).not.toBeInTheDocument();
  });

  it("copa: muestra la válida bloqueada (FR-008)", async () => {
    mswServer.use(...raceSeriesHandlers, prefillCupEventHandler);
    wrap(<ImportWizard raceEventId={2} />);

    const summary = await screen.findByTestId("prefill-locked-summary");
    expect(within(summary).getByText(/Válida #/i)).toBeInTheDocument();
    expect(summary).toHaveTextContent("4");
  });
});
