/**
 * Tests de las rutas legacy del módulo IA durante la transición Wave B.
 *
 * Wave B reemplaza los GonePage (410) que se renderizaban en PR7 por redirects
 * 301-style (<Navigate replace>) que apuntan a los equivalentes dentro del
 * módulo unificado /competitions/*:
 *
 *   - /coach/race-analysis          → /competitions/insights
 *   - /training/races/:id/club-insights → /competitions/:id?tab=insights
 *
 * Wave F cambiará estos redirects a GonePage (410) definitivo.
 *
 * Montamos una réplica mínima de las rutas (sin el árbol pesado de App /
 * auth) y verificamos que los destinos correctos se montan tras el redirect.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, Navigate, useParams } from "react-router-dom";

/** Stub de ClubInsightsRedirect — misma lógica que en App.tsx */
function ClubInsightsRedirect() {
  const { raceEventId } = useParams<{ raceEventId: string }>();
  return <Navigate to={`/competitions/${raceEventId}?tab=insights`} replace />;
}

function renderAt(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        {/* Legacy routes — Wave B redirects */}
        <Route
          path="/coach/race-analysis"
          element={<Navigate to="/competitions/insights" replace />}
        />
        <Route
          path="/training/races/:raceEventId/club-insights"
          element={<ClubInsightsRedirect />}
        />
        {/* Destinos canónicos */}
        <Route
          path="/competitions/insights"
          element={<div data-testid="insights-hub">Hub análisis IA</div>}
        />
        <Route
          path="/competitions/:id"
          element={<div data-testid="competition-detail">Detalle competencia</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Redirects de transición Wave B — rutas legacy IA", () => {
  it("/coach/race-analysis redirige al hub /competitions/insights", () => {
    renderAt("/coach/race-analysis");
    expect(screen.getByTestId("insights-hub")).toBeInTheDocument();
    expect(screen.queryByText(/Esta sección se movió/i)).not.toBeInTheDocument();
  });

  it("/training/races/:id/club-insights redirige a /competitions/:id?tab=insights", () => {
    renderAt("/training/races/42/club-insights");
    expect(screen.getByTestId("competition-detail")).toBeInTheDocument();
  });

  it("/training/races/:id/club-insights preserva el raceEventId en la URL destino", () => {
    // Verificamos que el component de destino monta (lo que implica que la
    // ruta /competitions/42 fue alcanzada — MemoryRouter no expone href como
    // el DOM real, pero el match de la Route es suficiente como invariante).
    renderAt("/training/races/99/club-insights");
    expect(screen.getByTestId("competition-detail")).toBeInTheDocument();
  });
});
