/**
 * Tests v2 de InsightsTimeline (Task #9, #18 — actualizado en Task #22).
 *
 * Verifica:
 * - Filas con prompt_version === "race_analyst_v2" muestran preview del
 *   bloque "## Qué pasó" parseado (no el summary_text completo).
 * - 5 filas distintas (cada una con summary propio) producen 5 previews
 *   con texto diferente (no replicado).
 * - El detalle v2 renderiza las 4 secciones (qué pasó / recorrido /
 *   hacia dónde va / resumen de temporada).
 *
 * Decisión Task #22: el banner N=1 se condiciona por
 * ``insight.is_first_in_season === true`` (atleta tiene 1 válida en toda la
 * temporada), NO por ``valida_count`` del set lanzado. Insights v1 legacy
 * sin el campo (``is_first_in_season: null``) NO disparan el banner.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Auth mock — coach.
vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Coach", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

// MarkdownReportViewer stub (no react-markdown render).
vi.mock("@/components/ai/MarkdownReportViewer", () => ({
  MarkdownReportViewer: ({ markdown }: { markdown: string }) => (
    <div data-testid="markdown-viewer">{markdown}</div>
  ),
}));

import { http, HttpResponse } from "msw";

import { mswServer } from "@/test/setup";
import {
  fiveDistinctV2InsightsHandler,
  singleV2InsightHandler,
  v2InsightDetailHandler,
} from "@/test/msw/raceAnalysisV2Handlers";
import { mockInsightV2Detail } from "@/test/fixtures/insightV2";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { InsightsTimeline } from "@/components/athletes/ai/InsightsTimeline";

describe("InsightsTimeline — v2 (race_analyst_v2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza preview del bloque 'Qué pasó' para insight v2", async () => {
    mswServer.use(singleV2InsightHandler);
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);

    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1001")).toBeInTheDocument();
    });

    // El preview debería ser la primera línea de "## Qué pasó".
    const card = screen.getByTestId("insight-card-1001");
    expect(within(card).getByText(/avanzó en frenada/i)).toBeInTheDocument();
    // NO debería mostrar el header markdown crudo.
    expect(within(card).queryByText(/## qué pasó/i)).not.toBeInTheDocument();
  });

  it("5 insights v2 distintos producen 5 previews con texto diferente", async () => {
    mswServer.use(fiveDistinctV2InsightsHandler);
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);

    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1001")).toBeInTheDocument();
    });

    // Las 5 cards renderizan.
    for (const valida of [1, 2, 3, 4, 5]) {
      expect(
        screen.getByTestId(`insight-card-${1000 + valida}`),
      ).toBeInTheDocument();
    }

    // Cada preview tiene el texto específico de su válida.
    for (const valida of [1, 2, 3, 4, 5]) {
      const card = screen.getByTestId(`insight-card-${1000 + valida}`);
      expect(
        within(card).getByText(
          new RegExp(`válida ${valida}: foco específico`, "i"),
        ),
      ).toBeInTheDocument();
    }
  });

  it("detalle v2 renderiza las 4 secciones en accordions", async () => {
    mswServer.use(singleV2InsightHandler, v2InsightDetailHandler);
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);

    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1001")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-card-1001"));

    await waitFor(() => {
      expect(screen.getByText(/detalle del análisis/i)).toBeInTheDocument();
    });

    // Las 4 secciones deben mostrarse como bloques navegables. Validamos
    // por el texto del header (tolerante a si es <summary>, <h3> o accordion).
    await waitFor(() => {
      expect(screen.getByText(/qué pasó/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/recorrido hasta aquí/i)).toBeInTheDocument();
    expect(screen.getByText(/hacia dónde va/i)).toBeInTheDocument();
    expect(screen.getByText(/resumen de temporada/i)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Task #18 + #22 — banner N=1 condicional al detalle del insight,
  // gatillado por is_first_in_season (no por valida_count).
  // -------------------------------------------------------------------------

  it("muestra InsightN1Banner cuando insight detail tiene is_first_in_season=true", async () => {
    mswServer.use(
      singleV2InsightHandler,
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
        ({ params }) =>
          HttpResponse.json(
            mockInsightV2Detail({
              id: Number(params.insightId),
              is_first_in_season: true,
              season_validas_count: 1,
            }),
          ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);

    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1001")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-card-1001"));

    await waitFor(() => {
      expect(screen.getByTestId("insight-n1-banner")).toBeInTheDocument();
    });
  });

  it("NO muestra InsightN1Banner cuando is_first_in_season=false (atleta con historial)", async () => {
    mswServer.use(
      singleV2InsightHandler,
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
        ({ params }) =>
          HttpResponse.json(
            mockInsightV2Detail({
              id: Number(params.insightId),
              is_first_in_season: false,
              season_validas_count: 3,
            }),
          ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);

    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1001")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-card-1001"));

    // Espera a que el detalle esté visible (markdown viewer renderizado).
    await waitFor(() => {
      expect(screen.getByText(/detalle del análisis/i)).toBeInTheDocument();
    });
    expect(screen.queryByTestId("insight-n1-banner")).not.toBeInTheDocument();
  });

  it("NO muestra InsightN1Banner cuando is_first_in_season=null (insight v1 legacy)", async () => {
    // Insights generados antes de Task #22 no traen el campo; el banner
    // NO debe aparecer para ellos (compat back-fill).
    mswServer.use(
      singleV2InsightHandler,
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
        ({ params }) =>
          HttpResponse.json(
            mockInsightV2Detail({
              id: Number(params.insightId),
              is_first_in_season: null,
              season_validas_count: null,
            }),
          ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);

    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1001")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-card-1001"));

    await waitFor(() => {
      expect(screen.getByText(/detalle del análisis/i)).toBeInTheDocument();
    });
    expect(screen.queryByTestId("insight-n1-banner")).not.toBeInTheDocument();
  });

  it("propaga mode=parent al banner cuando viewer es padre/madre", async () => {
    mswServer.use(
      singleV2InsightHandler,
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
        ({ params }) =>
          HttpResponse.json(
            mockInsightV2Detail({
              id: Number(params.insightId),
              is_first_in_season: true,
              season_validas_count: 1,
            }),
          ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="parent" />);

    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1001")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-card-1001"));

    await waitFor(() => {
      const banner = screen.getByTestId("insight-n1-banner");
      // Copy parent (Task #22): "Tu hijo/a ha corrido su primera válida..."
      expect(banner).toHaveTextContent(/Tu hijo\/a ha corrido/i);
      expect(banner).toHaveTextContent(/primera válida de la temporada/i);
    });
  });

  it("preview cae al truncado clásico cuando prompt_version es v1 (compat)", async () => {
    // Sin override: handler default emite mock con prompt_version "v1.2" (no v2).
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1")).toBeInTheDocument();
    });
    // El handler default usa "v1.2"; preview muestra el summary_text completo
    // (no busca "Qué pasó"). Sanity check: el preview existe.
    const card = screen.getByTestId("insight-card-1");
    expect(within(card).getByText(/resumen del desempeño/i)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // T017 / T018 — progression badge (FR-007, FR-013)
  // -------------------------------------------------------------------------

  it("muestra progression badge 'Mejorando' cuando metrics_snapshot tiene progression_assessment=improving", async () => {
    mswServer.use(
      singleV2InsightHandler,
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
        ({ params }) =>
          HttpResponse.json(
            mockInsightV2Detail({
              id: Number(params.insightId),
              metrics_snapshot: {
                schema_version: 1,
                season: 2026,
                progression_assessment: "improving",
              } as never,
            }),
          ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);

    await waitFor(() =>
      expect(screen.getByTestId("insight-card-1001")).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("insight-card-1001"));

    await waitFor(() => {
      expect(screen.getByTestId("progression-badge")).toBeInTheDocument();
    });
    expect(screen.getByTestId("progression-badge")).toHaveTextContent(/mejorando/i);
  });

  it("muestra progression badge 'En descenso' cuando assessment=declining", async () => {
    mswServer.use(
      singleV2InsightHandler,
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
        ({ params }) =>
          HttpResponse.json(
            mockInsightV2Detail({
              id: Number(params.insightId),
              metrics_snapshot: {
                schema_version: 1,
                season: 2026,
                progression_assessment: "declining",
              } as never,
            }),
          ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);

    await waitFor(() =>
      expect(screen.getByTestId("insight-card-1001")).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("insight-card-1001"));

    await waitFor(() => {
      expect(screen.getByTestId("progression-badge")).toHaveTextContent(/en descenso/i);
    });
  });

  it("NO muestra progression badge cuando metrics_snapshot no tiene progression_assessment (insight legacy)", async () => {
    mswServer.use(
      singleV2InsightHandler,
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
        ({ params }) =>
          HttpResponse.json(
            mockInsightV2Detail({
              id: Number(params.insightId),
              // metrics_snapshot sin progression_assessment (formato legacy v1)
              metrics_snapshot: {
                schema_version: 1,
                season: 2026,
              } as never,
            }),
          ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);

    await waitFor(() =>
      expect(screen.getByTestId("insight-card-1001")).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("insight-card-1001"));

    await waitFor(() =>
      expect(screen.getByText(/detalle del análisis/i)).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("progression-badge")).not.toBeInTheDocument();
  });

  it("muestra sección 'Contexto de temporada' en detalle v2 cuando está en el summary_text", async () => {
    const summaryWithContext = [
      "## Qué pasó",
      "Avanzó en frenada y curvas cerradas.",
      "",
      "## Recorrido hasta aquí",
      "Progreso técnico consistente.",
      "",
      "## Hacia dónde va",
      "Foco en cadencia sostenida.",
      "",
      "## Resumen de temporada",
      "Temporada de aprendizaje.",
      "",
      "## Contexto de temporada",
      "Lleva 3 válidas disputadas de 7 en la Copa Valle 2026.",
    ].join("\n");

    mswServer.use(
      singleV2InsightHandler,
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
        ({ params }) =>
          HttpResponse.json(
            mockInsightV2Detail({
              id: Number(params.insightId),
              summary_text: summaryWithContext,
            }),
          ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);

    await waitFor(() =>
      expect(screen.getByTestId("insight-card-1001")).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("insight-card-1001"));

    await waitFor(() => {
      expect(screen.getByText(/contexto de temporada/i)).toBeInTheDocument();
    });
  });

  it("NO muestra sección 'Contexto de temporada' para insights sin esa sección (legacy compat)", async () => {
    // El mockInsightV2Detail por defecto usa buildV2Markdown() que NO incluye
    // la sección de contexto de temporada.
    mswServer.use(singleV2InsightHandler, v2InsightDetailHandler);
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);

    await waitFor(() =>
      expect(screen.getByTestId("insight-card-1001")).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("insight-card-1001"));

    await waitFor(() =>
      expect(screen.getByText(/detalle del análisis/i)).toBeInTheDocument(),
    );
    // Las 4 secciones clásicas deben seguir renderizándose.
    expect(screen.getByText(/qué pasó/i)).toBeInTheDocument();
    // La sección nueva NO debe aparecer.
    expect(screen.queryByText(/contexto de temporada/i)).not.toBeInTheDocument();
  });
});
