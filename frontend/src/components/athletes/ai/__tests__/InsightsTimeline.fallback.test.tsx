/**
 * Filas fallback (US4, feature 036): marcado visual, checkbox de boletín
 * suprimido y acción "Reintentar".
 *
 * Un insight con `is_fallback=true` fue persistido por el camino de FALLA de
 * `deterministic_fallback` (`backend/app/services/race/ai/fallback.py`) — el
 * `summary_text` es el placeholder fijo "Análisis IA no disponible…", no un
 * análisis real. Antes de este fix la fila era indistinguible de un análisis
 * real y conservaba el checkbox de boletín: un coach podía adjuntar por error
 * el mensaje de falla al boletín que reciben las familias.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

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
import {
  FALLBACK_SUMMARY_TEXT,
  fallbackInsightDetailHandler,
  fallbackInsightListHandler,
  mockFallbackSeasonSummaryInsight,
} from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { InsightsTimeline } from "@/components/athletes/ai/InsightsTimeline";

/**
 * Detalles literales que arma el backend (`app/routers/athlete_race_analysis.py`)
 * para los 409 que puede recibir "Reintentar": run activo y válida ambigua en
 * el lanzamiento por válida, y colisión de resumen activo en el endpoint de
 * resumen de temporada. La fila fallback por defecto es season 2026,
 * valida_num 3.
 */
const RETRY_ACTIVE_RUN_DETAIL =
  "Ya hay un análisis en curso para este deportista en la válida 3 de la " +
  "temporada 2026. Espera a que termine antes de lanzar uno nuevo.";

const RETRY_AMBIGUOUS_VALIDA_DETAIL =
  "Válida ambigua: #3 → eventos [21, 22]. Hay copa y campeonato con el " +
  "mismo número en esta temporada; lanza el análisis desde la competición " +
  "específica.";

const SEASON_SUMMARY_ACTIVE_RUN_DETAIL =
  "Ya existe un resumen de temporada activo para este deportista y esta " +
  "temporada — probablemente otra solicitud se adelantó. Recarga la vista " +
  "antes de reintentar.";

describe("InsightsTimeline — filas fallback (US4, feature 036)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mswServer.use(fallbackInsightListHandler, fallbackInsightDetailHandler);
  });

  it("marca la fila fallback con el badge 'Análisis no disponible'", async () => {
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-77")).toBeInTheDocument();
    });
    expect(screen.getByTestId("insight-fallback-badge-77")).toHaveTextContent(
      /análisis no disponible/i,
    );
    // El estado también viaja en el aria-label del card (a11y).
    expect(
      screen.getByRole("button", { name: /análisis no disponible/i }),
    ).toBeInTheDocument();
  });

  it("muestra el texto exacto del placeholder persistido por el backend", async () => {
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-77")).toBeInTheDocument();
    });
    expect(screen.getByText(FALLBACK_SUMMARY_TEXT)).toBeInTheDocument();
  });

  it("NO muestra el checkbox de boletín en una fila fallback (coach)", async () => {
    renderWithProviders(
      <InsightsTimeline
        athleteId={42}
        mode="coach"
        newsletterSelection={new Set()}
        onToggleSelection={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-77")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("insight-checkbox-77")).not.toBeInTheDocument();
  });

  it("NO muestra el botón Regenerar en una fila fallback (usa Reintentar en su lugar)", async () => {
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-77")).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId("insight-regenerate-77"),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("insight-retry-77")).toBeInTheDocument();
  });

  it("el botón Reintentar re-lanza el análisis de la misma válida", async () => {
    let captured: { season?: number; valida_nums?: number[] } | null = null;
    mswServer.use(
      http.post(
        "*/api/athletes/:athleteId/race-analysis/runs",
        async ({ request }) => {
          captured = (await request.json()) as {
            season?: number;
            valida_nums?: number[];
          };
          return HttpResponse.json(
            {
              run_id: "run-retry-001",
              status: "running",
              started_at: "2026-06-09T10:00:00Z",
              status_url: "/api/race-analysis/runs/run-retry-001/status",
              estimated_seconds: 20,
            },
            { status: 201 },
          );
        },
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-retry-77")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-retry-77"));

    await waitFor(() => {
      expect(captured).not.toBeNull();
    });
    // mockFallbackInsight() default: season 2026, valida_num 3.
    expect(captured!.season).toBe(2026);
    expect(captured!.valida_nums).toEqual([3]);
  });

  it("el Reintentar de un resumen de temporada fallback llama a /season-summary", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
        HttpResponse.json({
          items: [mockFallbackSeasonSummaryInsight()],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
    );
    let called = false;
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/season-summary", () => {
        called = true;
        return HttpResponse.json({
          run_id: "season-summary-retry-001",
          status: "running",
          started_at: "2026-06-09T10:00:00Z",
        });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-retry-78")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-retry-78"));

    await waitFor(() => {
      expect(called).toBe(true);
    });
  });

  it("muestra el detail del backend cuando el reintento choca con un 409 de run activo", async () => {
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/runs", () =>
        HttpResponse.json({ detail: RETRY_ACTIVE_RUN_DETAIL }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-retry-77")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-retry-77"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        RETRY_ACTIVE_RUN_DETAIL,
      );
    });
    expect(
      screen.queryByText(/no se pudo reintentar\. intenta de nuevo\./i),
    ).not.toBeInTheDocument();
  });

  it("muestra el detail del backend cuando el reintento choca con un 409 de válida ambigua", async () => {
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/runs", () =>
        HttpResponse.json(
          { detail: RETRY_AMBIGUOUS_VALIDA_DETAIL },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-retry-77")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-retry-77"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        /lanza el análisis desde la competición específica\./i,
      );
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      RETRY_AMBIGUOUS_VALIDA_DETAIL,
    );
  });

  // Ver nota equivalente en `InsightsTimeline.regenerate.test.tsx`: sin
  // `detail`, `extractErrorDetail` usa el `message` de axios; lo verificable
  // aquí es que el bloque de error exista y no quede vacío.
  it("sigue mostrando un mensaje no vacío cuando el fallo del reintento no trae detail", async () => {
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/runs", () =>
        HttpResponse.json({}, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-retry-77")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-retry-77"));

    await waitFor(() => {
      expect(screen.getByTestId("insight-retry-error-77")).toBeInTheDocument();
    });
    expect(
      screen.getByTestId("insight-retry-error-77"),
    ).not.toBeEmptyDOMElement();
  });

  it("el Reintentar del resumen de temporada muestra el detail de SU endpoint", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
        HttpResponse.json({
          items: [mockFallbackSeasonSummaryInsight()],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
      http.post("*/api/athletes/:athleteId/race-analysis/season-summary", () =>
        HttpResponse.json(
          { detail: SEASON_SUMMARY_ACTIVE_RUN_DETAIL },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-retry-78")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-retry-78"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        SEASON_SUMMARY_ACTIVE_RUN_DETAIL,
      );
    });
  });

  it("NO muestra Reintentar ni checkbox para parent, pero sí conserva el marcado", async () => {
    renderWithProviders(<InsightsTimeline athleteId={42} mode="parent" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-77")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("insight-retry-77")).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("insight-checkbox-77"),
    ).not.toBeInTheDocument();
    // El marcado sí se ve para parent — pudo haber sido aprobado por error.
    expect(screen.getByTestId("insight-fallback-badge-77")).toBeInTheDocument();
  });

  it("el detalle muestra el aviso 'Análisis no disponible' en vez de secciones vacías", async () => {
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-77")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-card-77"));

    await waitFor(() => {
      expect(screen.getByTestId("insight-fallback-notice")).toBeInTheDocument();
    });
    expect(
      screen.queryByText(/no se encontraron secciones/i),
    ).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad con filas fallback", async () => {
    const { container } = renderWithProviders(
      <InsightsTimeline
        athleteId={42}
        mode="coach"
        newsletterSelection={new Set()}
        onToggleSelection={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-77")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
