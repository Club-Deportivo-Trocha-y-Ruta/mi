/**
 * Tests para CompetitionImportPage — página contenedora de la revisión de
 * una carga (amendment 2026-09-26, `contracts/ui-review-only.md`).
 *
 * Cubre:
 *  - Sin `?import=<id>` → redirige a /competitions/imports?seccion=cargas
 *    (la app ya no sube archivos).
 *  - Con `?import=<id>` y sin :id → breadcrumb "Volver a competencias"
 *    apunta a /competitions.
 *  - Con `?import=<id>` y con :id → breadcrumb "Volver a competencia"
 *    apunta a /competitions/:id.
 *  - El wizard se monta dentro del Suspense (mock para no cargar
 *    dependencias — el wizard tiene su propio test suite).
 *
 * Mockeamos ImportWizard para evitar el peso del bundle y para no requerir
 * handlers de raceImports en cada suite.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/components/competitions/import/ImportWizard", () => ({
  ImportWizard: () => <div data-testid="mock-import-wizard">wizard</div>,
}));

import { CompetitionImportPage } from "@/routes/competitions/CompetitionImportPage";

function renderImport(initialEntry: string) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route
            path="/competitions/import"
            element={<CompetitionImportPage />}
          />
          <Route
            path="/competitions/:id/import"
            element={<CompetitionImportPage />}
          />
          <Route
            path="/competitions/imports"
            element={<div data-testid="board-stub">Tablero</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CompetitionImportPage", () => {
  it("sin ?import → redirige al tablero de cargas", async () => {
    renderImport("/competitions/import");
    expect(await screen.findByTestId("board-stub")).toBeInTheDocument();
    expect(screen.queryByTestId("mock-import-wizard")).not.toBeInTheDocument();
  });

  it("con :id y sin ?import → también redirige al tablero", async () => {
    renderImport("/competitions/42/import");
    expect(await screen.findByTestId("board-stub")).toBeInTheDocument();
  });

  it("con ?import=<id> y sin :id → breadcrumb 'Volver a competencias' apunta a /competitions", async () => {
    renderImport("/competitions/import?import=7");
    const back = await screen.findByTestId("import-back-link");
    expect(back).toHaveAttribute("href", "/competitions");
    expect(back).toHaveTextContent(/Volver a competencias/i);
  });

  it("con ?import=<id> y :id=42 → breadcrumb 'Volver a competencia' apunta a /competitions/42", async () => {
    renderImport("/competitions/42/import?import=7");
    const back = await screen.findByTestId("import-back-link");
    expect(back).toHaveAttribute("href", "/competitions/42");
    expect(back).toHaveTextContent(/Volver a competencia/i);
  });

  it("con ?import=<id> monta el ImportWizard dentro del Suspense", async () => {
    renderImport("/competitions/42/import?import=7");
    expect(await screen.findByTestId("mock-import-wizard")).toBeInTheDocument();
  });

  it("con ?import=<id> muestra el título y subtítulo de revisión", async () => {
    renderImport("/competitions/import?import=7");
    expect(
      await screen.findByRole("heading", { name: "Revisar carga de resultados" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Revisa la lectura, resuelve lo pendiente y confirma."),
    ).toBeInTheDocument();
  });
});
