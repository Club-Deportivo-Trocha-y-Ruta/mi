/**
 * Tests de la deprecación final de rutas legacy (PR7, D7).
 *
 * Tras un ciclo completo con redirect 301 (PR1-PR6), en PR7 las rutas legacy
 * del módulo IA dejan de redirigir y muestran `GonePage` (equivalente SPA de
 * un HTTP 410 Gone):
 *   - /coach/race-analysis
 *   - /training/races/:raceEventId/club-insights
 *
 * Montamos una réplica mínima de esas rutas (sin el árbol pesado de App /
 * auth) y verificamos que renderizan GonePage con el enlace al nuevo hub.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { GonePage } from "@/routes/GonePage";

function renderAt(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/coach/race-analysis" element={<GonePage />} />
        <Route
          path="/training/races/:raceEventId/club-insights"
          element={<GonePage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Deprecación legacy rutas IA (PR7, D7)", () => {
  it("/coach/race-analysis muestra GonePage (410)", () => {
    renderAt("/coach/race-analysis");
    expect(screen.getByTestId("gone-page")).toBeInTheDocument();
    expect(screen.getByText(/Esta sección se movió/i)).toBeInTheDocument();
  });

  it("/training/races/:id/club-insights muestra GonePage (410)", () => {
    renderAt("/training/races/42/club-insights");
    expect(screen.getByTestId("gone-page")).toBeInTheDocument();
  });

  it("GonePage enlaza al nuevo hub /competitions/insights por default", () => {
    renderAt("/coach/race-analysis");
    const link = screen.getByRole("link", { name: /Análisis IA/i });
    expect(link).toHaveAttribute("href", "/competitions/insights");
  });
});
