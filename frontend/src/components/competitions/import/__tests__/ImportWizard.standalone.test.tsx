/**
 * Regresión del flujo standalone (sin competencia) — US3, feature 015.
 *
 * El wizard sin `raceEventId` debe comportarse exactamente como hoy: vacío,
 * editable, `series_kind` por defecto "cup", sin bloqueo ni resumen prefill
 * (FR-007, SC-005).
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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

describe("ImportWizard — standalone sin cambios (US3)", () => {
  it("sin raceEventId: form editable, tipo default 'cup', sin locking", async () => {
    wrap(<ImportWizard />);

    // El selector de tipo editable existe y default a copa.
    const kind = await screen.findByTestId("wizard-series-kind");
    expect(kind).toBeInTheDocument();
    expect(kind).toHaveValue("cup");

    // Inputs editables de identidad presentes.
    expect(screen.getByTestId("wizard-series-name")).toBeInTheDocument();
    expect(screen.getByTestId("wizard-event-name")).toBeInTheDocument();
    expect(screen.getByTestId("wizard-valida-num")).toBeInTheDocument();

    // Nada del prefill: ni resumen bloqueado ni estado bloqueado.
    expect(
      screen.queryByTestId("prefill-locked-summary"),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("prefill-blocked")).not.toBeInTheDocument();
    expect(screen.queryByTestId("prefill-edit-metadata")).not.toBeInTheDocument();
  });
});
