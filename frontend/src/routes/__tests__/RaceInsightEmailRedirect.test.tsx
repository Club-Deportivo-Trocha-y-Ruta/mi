/**
 * RaceInsightEmailRedirect — tests del redirect por rol (2026-09-23).
 *
 * Contexto: alias para los correos de insight de carrera YA enviados antes
 * de que se eliminara el envío automático al aprobar. La ruta
 * `/athletes/:athleteId/race-analysis/insights/:insightId` nunca existió
 * en el router — sin este alias, cualquier clic en esos correos caía en
 * NotFoundPage. Cubre:
 *  - parent      → /my-athletes/:athleteId?tab=ai-analysis&insight=:id
 *  - coach/admin → /athletes/:athleteId?tab=ai_analysis&insight=:id
 *  - otro rol (athlete) o sin rol resuelto → NotFoundPage (no hay panorama
 *    de atleta para ese caso)
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

import { useAuthStore } from "@/store/auth.store";
import { RaceInsightEmailRedirect } from "@/routes/RaceInsightEmailRedirect";
import { UserRole } from "@/types/enums";

function mockRole(role: UserRole | undefined) {
  vi.mocked(useAuthStore).mockImplementation(
    // @ts-expect-error — firma real de Zustand toma un selector; el mock
    // solo necesita resolver `s.user?.role`.
    (selector) => selector({ user: role ? { role } : null }),
  );
}

/** Muestra a dónde aterrizó el redirect (pathname + query completos). */
function LandedAt({ label }: { label: string }) {
  const location = useLocation();
  return (
    <div data-testid="landed">
      {label}: {location.pathname}
      {location.search}
    </div>
  );
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/athletes/:athleteId/race-analysis/insights/:insightId"
          element={<RaceInsightEmailRedirect />}
        />
        <Route
          path="/my-athletes/:id"
          element={<LandedAt label="padre" />}
        />
        <Route path="/athletes/:id" element={<LandedAt label="coach" />} />
        <Route path="*" element={<div>404</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RaceInsightEmailRedirect", () => {
  it("padre: redirige a /my-athletes/:id?tab=ai-analysis&insight=:id", () => {
    mockRole(UserRole.parent);
    renderAt("/athletes/42/race-analysis/insights/7");
    expect(screen.getByTestId("landed")).toHaveTextContent(
      "padre: /my-athletes/42?tab=ai-analysis&insight=7",
    );
  });

  it("coach: redirige a /athletes/:id?tab=ai_analysis&insight=:id", () => {
    mockRole(UserRole.coach);
    renderAt("/athletes/42/race-analysis/insights/7");
    expect(screen.getByTestId("landed")).toHaveTextContent(
      "coach: /athletes/42?tab=ai_analysis&insight=7",
    );
  });

  it("admin: redirige a /athletes/:id?tab=ai_analysis&insight=:id (mismo destino que coach)", () => {
    mockRole(UserRole.admin);
    renderAt("/athletes/42/race-analysis/insights/7");
    expect(screen.getByTestId("landed")).toHaveTextContent(
      "coach: /athletes/42?tab=ai_analysis&insight=7",
    );
  });

  it("rol sin panorama de atleta (athlete): cae en NotFoundPage", () => {
    mockRole(UserRole.athlete);
    renderAt("/athletes/42/race-analysis/insights/7");
    expect(screen.queryByTestId("landed")).not.toBeInTheDocument();
    expect(screen.getByText("404")).toBeInTheDocument();
    expect(screen.getByText("Ruta no encontrada.")).toBeInTheDocument();
  });

  it("sin rol resuelto: cae en NotFoundPage (defensivo)", () => {
    mockRole(undefined);
    renderAt("/athletes/42/race-analysis/insights/7");
    expect(screen.queryByTestId("landed")).not.toBeInTheDocument();
    expect(screen.getByText("Ruta no encontrada.")).toBeInTheDocument();
  });
});
