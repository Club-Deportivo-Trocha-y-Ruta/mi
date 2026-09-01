/**
 * Tests Sprint 2 BB1 — agrupación temporal del Histórico.
 *
 * Cubre:
 *  - Items de meses distintos → headers de grupo separados aparecen.
 *  - Mes con tier conocido (Carrera A en mayo 2026) → badge "Carrera A".
 *  - Resumen de temporada (valida_num===0) → borde primary + ícono Trophy.
 *  - Cto. Departamental (valida_num===99) → borde amber + ícono Medal.
 *  - Carrera normal (válida 1..7) → card compacta sin borde de color ni Trophy/Medal.
 *
 * Privacidad: este componente no expone PII de menores; los snapshots de
 * fechas usan los valores del calendario Copa Valle 2026 (público).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

// Auth mock — coach por default.
vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Coach", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

vi.mock("@/components/ai/MarkdownReportViewer", () => ({
  MarkdownReportViewer: ({ markdown }: { markdown: string }) => (
    <div data-testid="markdown-viewer">{markdown}</div>
  ),
}));

import { mswServer } from "@/test/setup";
import { mockInsight } from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { InsightsTimeline } from "@/components/athletes/ai/InsightsTimeline";

describe("InsightsTimeline — agrupación temporal (Sprint 2 BB1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("items de meses distintos → muestra headers separados por mes-año", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
        HttpResponse.json({
          items: [
            // Mayo 2026 — Válida IV (Carrera A)
            mockInsight({
              id: 10,
              valida_num: 4,
              generated_at: "2026-05-18T10:00:00Z",
            }),
            // Abril 2026 — Válida III (Carrera C)
            mockInsight({
              id: 11,
              valida_num: 3,
              generated_at: "2026-04-20T10:00:00Z",
            }),
            // Febrero 2026 — Válida II (Carrera C)
            mockInsight({
              id: 12,
              valida_num: 2,
              generated_at: "2026-02-28T10:00:00Z",
            }),
          ],
          total: 3,
          limit: 50,
          offset: 0,
        }),
      ),
    );

    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-10")).toBeInTheDocument();
    });

    // Intl.DateTimeFormat("es-CO", { month: "long", year: "numeric" }) →
    // típicamente "mayo de 2026" / "abril de 2026" / "febrero de 2026".
    // El header sticky contiene al menos el nombre del mes en su grupo.
    expect(screen.getByText(/mayo.*2026/i)).toBeInTheDocument();
    expect(screen.getByText(/abril.*2026/i)).toBeInTheDocument();
    expect(screen.getByText(/febrero.*2026/i)).toBeInTheDocument();

    // Sanidad: las 3 cards montadas, una por grupo.
    expect(screen.getByTestId("insight-card-11")).toBeInTheDocument();
    expect(screen.getByTestId("insight-card-12")).toBeInTheDocument();
  });

  it("mes con tier 'Carrera A' (mayo 2026) → badge 'Carrera A' presente en el header del grupo", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
        HttpResponse.json({
          items: [
            mockInsight({
              id: 20,
              valida_num: 4,
              generated_at: "2026-05-17T10:00:00Z",
            }),
          ],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
    );
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-20")).toBeInTheDocument();
    });
    // Badge del tier — el helper getCarreraTier mapea 2026-05 → "A".
    expect(screen.getByText(/Carrera\s*A/i)).toBeInTheDocument();
  });

  it("mes sin tier (sin válida en el calendario, ej. marzo 2026) → NO renderiza badge de tier", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
        HttpResponse.json({
          items: [
            mockInsight({
              id: 21,
              valida_num: 1,
              generated_at: "2026-03-10T10:00:00Z",
            }),
          ],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
    );
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-21")).toBeInTheDocument();
    });
    // No hay tier para 2026-03 → no debe renderizar "Carrera A/B/C/CD".
    expect(screen.queryByText(/Carrera\s*[ABC]/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Carrera\s*CD/i)).not.toBeInTheDocument();
  });

  it("resumen de temporada (valida_num===0) → card con borde primary + ícono Trophy", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
        HttpResponse.json({
          items: [
            mockInsight({
              id: 30,
              valida_num: 0,
              generated_at: "2026-12-15T10:00:00Z",
            }),
          ],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
    );
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-30")).toBeInTheDocument();
    });
    const card = screen.getByTestId("insight-card-30");
    // Clase de borde aplicada (Tailwind: border-l-4 border-primary).
    expect(card.className).toMatch(/border-l-4/);
    expect(card.className).toMatch(/border-primary/);
    // Ícono Trophy (lucide-react) montado como svg dentro del botón.
    const svgs = card.querySelectorAll("svg");
    expect(svgs.length).toBeGreaterThan(0);
    // Lucide trophy renders class "lucide-trophy"
    const hasTrophy = Array.from(svgs).some((s) =>
      (s.getAttribute("class") ?? "").toLowerCase().includes("trophy"),
    );
    expect(hasTrophy).toBe(true);
    // Si está en un grupo donde TODO es resumen-temporada, no debe haber
    // badge de tier (la lógica del componente lo suprime).
    const monthGroup = card.closest("section");
    if (monthGroup) {
      expect(
        within(monthGroup as HTMLElement).queryByText(/^Carrera\s+/i),
      ).not.toBeInTheDocument();
    }
  });

  it("Cto. Departamental (valida_num===99) → card con borde amber + ícono Medal", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
        HttpResponse.json({
          items: [
            mockInsight({
              id: 40,
              valida_num: 99,
              generated_at: "2026-06-26T10:00:00Z",
            }),
          ],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
    );
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-40")).toBeInTheDocument();
    });
    const card = screen.getByTestId("insight-card-40");
    expect(card.className).toMatch(/border-l-4/);
    // Borde amber (Tailwind: border-amber-400).
    expect(card.className).toMatch(/border-amber/);
    const svgs = card.querySelectorAll("svg");
    const hasMedal = Array.from(svgs).some((s) =>
      (s.getAttribute("class") ?? "").toLowerCase().includes("medal"),
    );
    expect(hasMedal).toBe(true);
  });

  it("Cto. Departamental moderno (series_kind='championship', valida_num NO es 99) → borde amber + ícono Medal", async () => {
    // Feature 036 (US5): un campeonato post features 014/016 puede traer su
    // propio valida_num de secuencia (no literalmente 99) — el shape debe
    // decidirse por `series_kind`, no por el número mágico retirado.
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
        HttpResponse.json({
          items: [
            mockInsight({
              id: 41,
              valida_num: 1,
              series_kind: "championship",
              generated_at: "2026-06-26T10:00:00Z",
            }),
          ],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
    );
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-41")).toBeInTheDocument();
    });
    const card = screen.getByTestId("insight-card-41");
    expect(card.className).toMatch(/border-l-4/);
    expect(card.className).toMatch(/border-amber/);
    const svgs = card.querySelectorAll("svg");
    const hasMedal = Array.from(svgs).some((s) =>
      (s.getAttribute("class") ?? "").toLowerCase().includes("medal"),
    );
    expect(hasMedal).toBe(true);
  });

  it("a11y — Timeline agrupado (3 meses con tiers mixtos) no introduce violaciones", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
        HttpResponse.json({
          items: [
            mockInsight({
              id: 901,
              valida_num: 4,
              generated_at: "2026-05-17T10:00:00Z",
            }),
            mockInsight({
              id: 902,
              valida_num: 3,
              generated_at: "2026-04-19T10:00:00Z",
            }),
            mockInsight({
              id: 903,
              valida_num: 99,
              generated_at: "2026-06-26T10:00:00Z",
            }),
          ],
          total: 3,
          limit: 50,
          offset: 0,
        }),
      ),
    );
    const { container } = renderWithProviders(
      <InsightsTimeline athleteId={42} mode="coach" />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-901")).toBeInTheDocument();
    });
    // Sanidad mínima: badge(s) de tier y agrupación renderizadas. El grupo
    // de junio (Cto. Departamental, valida_num=99) también resuelve a tier
    // "A" desde feature 033/T015 (getCarreraTier ya no distingue "CD"), así
    // que hay 2 badges "Carrera A" (mayo + junio) — no 1.
    expect(screen.getAllByText(/Carrera\s*A/i).length).toBe(2);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("válida normal (1..7) → card compacta sin border-l-4, sin Trophy ni Medal", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
        HttpResponse.json({
          items: [
            mockInsight({
              id: 50,
              valida_num: 2,
              generated_at: "2026-02-28T10:00:00Z",
            }),
          ],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
    );
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-50")).toBeInTheDocument();
    });
    const card = screen.getByTestId("insight-card-50");
    // Sin borde de color
    expect(card.className).not.toMatch(/border-l-4/);
    // Sin íconos Trophy/Medal dentro del card.
    const svgs = card.querySelectorAll("svg");
    const hasTrophyOrMedal = Array.from(svgs).some((s) => {
      const cls = (s.getAttribute("class") ?? "").toLowerCase();
      return cls.includes("trophy") || cls.includes("medal");
    });
    expect(hasTrophyOrMedal).toBe(false);
  });
});
