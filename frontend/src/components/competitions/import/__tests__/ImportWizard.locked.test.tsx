/**
 * Tests de protección del link prefill: campos bloqueados + escape hatch +
 * estado bloqueado + a11y (US2, feature 015).
 *
 * Cubre:
 *  - Identidad render como texto read-only, no inputs editables (T012, FR-004).
 *  - Sin control para editar tipo/serie in-flow (T012, FR-005).
 *  - Link "Editar metadata" presente → /competitions/{id}/edit (T012, FR-006).
 *  - Estado bloqueado cuando la serie es irresoluble (FR-009).
 *  - jest-axe: cero violaciones en el paso 1 prefill (T014, WCAG 2.1 AA).
 *
 * Privacidad: fixtures solo con metadata de competencia (FR-013).
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
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
  prefillUnresolvableSeriesEventHandler,
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

describe("ImportWizard — link protegido (US2)", () => {
  it("identidad bloqueada: texto read-only, sin inputs editables (FR-004)", async () => {
    mswServer.use(...raceSeriesHandlers, prefillCupEventHandler);
    wrap(<ImportWizard raceEventId={2} />);

    await screen.findByTestId("prefill-locked-summary");
    // No existe el selector de tipo ni los inputs de serie/evento.
    expect(screen.queryByTestId("wizard-series-kind")).not.toBeInTheDocument();
    expect(screen.queryByTestId("wizard-series-name")).not.toBeInTheDocument();
    expect(screen.queryByTestId("wizard-valida-num")).not.toBeInTheDocument();
    expect(screen.queryByTestId("wizard-event-date")).not.toBeInTheDocument();
  });

  it("sin control para editar tipo/serie in-flow (FR-005)", async () => {
    mswServer.use(...raceSeriesHandlers, prefillCupEventHandler);
    wrap(<ImportWizard raceEventId={2} />);
    await screen.findByTestId("prefill-locked-summary");

    // No hay ningún combobox/select de tipo de competencia.
    expect(
      screen.queryByRole("combobox", { name: /tipo de competencia/i }),
    ).not.toBeInTheDocument();
  });

  it("escape hatch 'Editar metadata' → /competitions/{id}/edit (FR-006)", async () => {
    mswServer.use(...raceSeriesHandlers, prefillCupEventHandler);
    wrap(<ImportWizard raceEventId={2} />);

    const link = await screen.findByTestId("prefill-edit-metadata");
    expect(link).toHaveAttribute("href", "/competitions/2/edit");
  });

  it("estado bloqueado: serie irresoluble muestra bloqueo + escape hatch (FR-009)", async () => {
    mswServer.use(...raceSeriesHandlers, prefillUnresolvableSeriesEventHandler);
    wrap(<ImportWizard raceEventId={777} />);

    const blocked = await screen.findByTestId("prefill-blocked");
    expect(blocked).toBeInTheDocument();
    // El formulario de paso 1 NO se renderiza (la importación no puede proceder).
    expect(screen.queryByTestId("wizard-step1-submit")).not.toBeInTheDocument();
    expect(
      screen.getByTestId("prefill-blocked-edit-metadata"),
    ).toHaveAttribute("href", "/competitions/777/edit");
  });

  it("a11y: cero violaciones en el paso 1 prefill (WCAG 2.1 AA, T014)", async () => {
    mswServer.use(...raceSeriesHandlers, prefillCupEventHandler);
    const { container } = wrap(<ImportWizard raceEventId={2} />);
    await screen.findByTestId("prefill-locked-summary");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
