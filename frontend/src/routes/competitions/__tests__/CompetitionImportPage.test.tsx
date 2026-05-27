/**
 * Tests para CompetitionImportPage — wrapper del ImportWizard.
 *
 * Cubre:
 *  - Sin :id → breadcrumb "Volver a competencias" apunta a /competitions.
 *  - Con :id → breadcrumb "Volver a competencia" apunta a /competitions/:id.
 *  - El wizard se monta dentro del Suspense (mock para no cargar dependencias).
 *
 * Mockeamos ImportWizard para evitar el peso del bundle de upload y para
 * no requerir handlers de raceImports en cada suite — el wizard tiene su
 * propio test suite (ImportWizard.test.tsx).
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
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CompetitionImportPage", () => {
  it("sin :id → breadcrumb 'Volver a competencias' apunta a /competitions", async () => {
    renderImport("/competitions/import");
    const back = await screen.findByTestId("import-back-link");
    expect(back).toHaveAttribute("href", "/competitions");
    expect(back).toHaveTextContent(/Volver a competencias/i);
  });

  it("con :id=42 → breadcrumb 'Volver a competencia' apunta a /competitions/42", async () => {
    renderImport("/competitions/42/import");
    const back = await screen.findByTestId("import-back-link");
    expect(back).toHaveAttribute("href", "/competitions/42");
    expect(back).toHaveTextContent(/Volver a competencia/i);
  });

  it("monta el ImportWizard dentro del Suspense", async () => {
    renderImport("/competitions/42/import");
    expect(await screen.findByTestId("mock-import-wizard")).toBeInTheDocument();
  });
});
