/**
 * US6 (feature 011): "Regenerar" affordance on insight rows.
 *
 * Coach-only action that re-launches the per-válida analysis scoped to the
 * row's (season, valida_num). Shows error state on failure. a11y via jest-axe.
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
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { InsightsTimeline } from "@/components/athletes/ai/InsightsTimeline";

/**
 * Detalles literales que arma el backend en
 * `app/routers/athlete_race_analysis.py` (409 de run activo y 409 de válida
 * ambigua) para la fila por defecto de `mockInsight()` — season 2026,
 * valida_num 4. Son los mensajes que el coach debe leer tal cual: le dicen
 * qué hacer, a diferencia de la copy genérica "Intenta de nuevo".
 */
const ACTIVE_RUN_DETAIL =
  "Ya hay un análisis en curso para este deportista en la válida 4 de la " +
  "temporada 2026. Espera a que termine antes de lanzar uno nuevo.";

const AMBIGUOUS_VALIDA_DETAIL =
  "Válida ambigua: #4 → eventos [11, 12]. Hay copa y campeonato con el " +
  "mismo número en esta temporada; lanza el análisis desde la competición " +
  "específica.";

describe("InsightsTimeline — Regenerar (US6)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra el botón Regenerar en filas de válida (coach)", async () => {
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-regenerate-1")).toBeInTheDocument();
    });
  });

  it("NO muestra Regenerar para parent", async () => {
    renderWithProviders(<InsightsTimeline athleteId={42} mode="parent" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("insight-regenerate-1")).not.toBeInTheDocument();
  });

  it("re-lanza el análisis de la válida con (season, valida_num) de la fila", async () => {
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
              run_id: "run-regen-001",
              status: "running",
              started_at: "2026-06-09T10:00:00Z",
              status_url: "/api/race-analysis/runs/run-regen-001/status",
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
      expect(screen.getByTestId("insight-regenerate-1")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-regenerate-1"));

    await waitFor(() => {
      expect(captured).not.toBeNull();
    });
    // mockInsight() default: season 2026, valida_num 4.
    expect(captured!.season).toBe(2026);
    expect(captured!.valida_nums).toEqual([4]);
  });

  it("muestra el detail del backend cuando el 409 es por run activo", async () => {
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/runs", () =>
        HttpResponse.json({ detail: ACTIVE_RUN_DETAIL }, { status: 409 }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-regenerate-1")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-regenerate-1"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(ACTIVE_RUN_DETAIL);
    });
    // La copy genérica ya no puede tapar la instrucción real del backend:
    // pedía "Intenta de nuevo" justo cuando reintentar es lo que falla.
    expect(
      screen.queryByText(/no se pudo regenerar\. intenta de nuevo\./i),
    ).not.toBeInTheDocument();
  });

  it("muestra el detail del backend cuando el 409 es por válida ambigua", async () => {
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/runs", () =>
        HttpResponse.json({ detail: AMBIGUOUS_VALIDA_DETAIL }, { status: 409 }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-regenerate-1")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-regenerate-1"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        /lanza el análisis desde la competición específica\./i,
      );
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      AMBIGUOUS_VALIDA_DETAIL,
    );
  });

  // Sin `detail` el helper canónico (`extractErrorDetail`) cae al
  // `err.message` de axios antes que a la copy de respaldo — mismo
  // comportamiento que ya tienen `LaunchAnalysisForm` y `SeasonSummaryButton`.
  // Lo que se verifica aquí es que el bloque de error siga apareciendo y
  // nunca quede vacío.
  it("sigue mostrando un mensaje no vacío cuando el error no trae detail", async () => {
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/runs", () =>
        HttpResponse.json({}, { status: 500 }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-regenerate-1")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-regenerate-1"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    // Sin `detail`, axios deja su propio mensaje técnico; lo que importa es
    // que el bloque de error siga existiendo y sea legible.
    expect(screen.getByRole("alert")).not.toBeEmptyDOMElement();
  });

  it("el alert del error es legible: no queda encajado en la columna del botón", async () => {
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/runs", () =>
        HttpResponse.json({ detail: ACTIVE_RUN_DETAIL }, { status: 409 }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-regenerate-1")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-regenerate-1"));

    const alert = await screen.findByTestId("insight-regenerate-error-1");
    // El alert es hermano de la fila (card + botón), no hijo de la columna
    // estrecha del botón — ahí un detail de ~140 caracteres era ilegible.
    expect(alert).not.toContainElement(screen.getByTestId("insight-regenerate-1"));
    expect(
      screen.getByTestId("insight-regenerate-1").parentElement,
    ).not.toContainElement(alert);
  });

  it("no tiene violaciones de accesibilidad con el control de regeneración", async () => {
    const { container } = renderWithProviders(
      <InsightsTimeline athleteId={42} mode="coach" />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("insight-regenerate-1")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
