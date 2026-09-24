/**
 * Rutas de «Competencias» y redirects (feature 045, T048, contracts/ui-routes.md).
 *
 * Renderiza el `App` REAL (la tabla de rutas verdadera, no una copia) con las
 * páginas destino sustituidas por stubs que muestran dónde aterrizó la
 * navegación (pathname + query). Cubre:
 *  - `/competitions/history`          → `/competitions/imports?seccion=cargas`
 *  - `/competitions/identity-review`  → `/competitions/imports?seccion=identidades`
 *  - `/competitions/unlinked`         → `/competitions/imports?seccion=sin-enlazar`
 *  - `/competitions/insights/season/:year` → `/competitions/season/:year`
 *    (conserva `?analisis=…` de un enlace viejo)
 *  - `/competitions/season/:year` y `/competitions/imports` llegan a SU página y
 *    NO son capturadas por `/competitions/:id` (detalle de competencia)
 *  - el asistente retomado (`/competitions/import?import=<id>` y
 *    `/competitions/:id/import?import=<id>`) sigue ruteado.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation, useParams } from "react-router-dom";
import type { ReactNode } from "react";

// ProtectedRoute pasa directo: aquí se prueba la tabla de rutas, no la sesión.
vi.mock("@/routes/ProtectedRoute", () => ({
  ProtectedRoute: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

/** Muestra dónde aterrizó la navegación (pathname + query completos). */
function Landed({ label }: { label: string }) {
  const location = useLocation();
  const params = useParams();
  return (
    <div data-testid="landed" data-label={label}>
      {label}: {location.pathname}
      {location.search}
      {params.year ? ` [year=${params.year}]` : ""}
      {params.id ? ` [id=${params.id}]` : ""}
    </div>
  );
}

vi.mock("@/routes/competitions/CompetitionImportsPage", () => ({
  CompetitionImportsPage: () => <Landed label="cargas-e-identidades" />,
}));
vi.mock("@/routes/competitions/SeasonInsightsPage", () => ({
  default: () => <Landed label="temporada" />,
}));
vi.mock("@/routes/competitions/CompetitionDetailPage", () => ({
  CompetitionDetailPage: () => <Landed label="detalle" />,
}));
vi.mock("@/routes/competitions/CompetitionImportPage", () => ({
  CompetitionImportPage: () => <Landed label="asistente" />,
}));

import App from "@/App";

async function landAt(path: string): Promise<{ label: string; text: string }> {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
  const landed = await screen.findByTestId("landed");
  return {
    label: landed.getAttribute("data-label") ?? "",
    text: landed.textContent ?? "",
  };
}

describe("Competencias — redirects y rutas nuevas (feature 045)", () => {
  it.each([
    ["/competitions/history", "?seccion=cargas"],
    ["/competitions/identity-review", "?seccion=identidades"],
    ["/competitions/unlinked", "?seccion=sin-enlazar"],
  ])("%s redirige a «Cargas e identidades» %s", async (from, search) => {
    const { label, text } = await landAt(from);
    expect(label).toBe("cargas-e-identidades");
    expect(text).toContain(`/competitions/imports${search}`);
  });

  it("/competitions/insights/season/:year redirige a /competitions/season/:year", async () => {
    const { label, text } = await landAt("/competitions/insights/season/2026");
    expect(label).toBe("temporada");
    expect(text).toContain("/competitions/season/2026");
    expect(text).toContain("[year=2026]");
    expect(text).not.toContain("/insights/");
  });

  it("el redirect de temporada conserva ?analisis= de un enlace viejo", async () => {
    const { text } = await landAt(
      "/competitions/insights/season/2026?analisis=por-aprobar",
    );
    expect(text).toContain("/competitions/season/2026?analisis=por-aprobar");
  });

  it("/competitions/season/:year llega a «Temporada», no al detalle de competencia", async () => {
    const { label, text } = await landAt("/competitions/season/2025");
    expect(label).toBe("temporada");
    expect(text).toContain("[year=2025]");
  });

  it("/competitions/imports llega a «Cargas e identidades» con su query (seccion + import)", async () => {
    const { label, text } = await landAt(
      "/competitions/imports?seccion=identidades&import=5",
    );
    expect(label).toBe("cargas-e-identidades");
    expect(text).toContain("?seccion=identidades&import=5");
  });

  it("el asistente retomado sigue ruteado: /competitions/import?import=<id>", async () => {
    const { label, text } = await landAt("/competitions/import?import=9");
    expect(label).toBe("asistente");
    expect(text).toContain("?import=9");
  });

  it("el asistente retomado sigue ruteado: /competitions/:id/import?import=<id>", async () => {
    const { label, text } = await landAt("/competitions/12/import?import=9");
    expect(label).toBe("asistente");
    expect(text).toContain("[id=12]");
    expect(text).toContain("?import=9");
  });

  it("/competitions/:id sigue llegando al detalle", async () => {
    const { label, text } = await landAt("/competitions/12?tab=results");
    expect(label).toBe("detalle");
    expect(text).toContain("[id=12]");
  });
});
