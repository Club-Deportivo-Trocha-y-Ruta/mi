/**
 * Tests vitest para InsightsTimeline (FE-3).
 *
 * Cubre estados (loading/empty/list), apertura del modal de detalle
 * con MarkdownReportViewer mockeado (jsdom no rinde markdown), badges
 * de confianza/válida, y la sección "Versiones anteriores" cuando
 * el insight tiene cadena ``supersedes``.
 *
 * Mockeamos ``MarkdownReportViewer`` para aislar el test del parser
 * de markdown (react-markdown puede ser lento o tener side-effects en
 * jsdom). Auth se mockea como coach con token.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

// Auth mock — token presente, role coach.
vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Coach", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

// Mock MarkdownReportViewer (react-markdown es pesado/innecesario para
// estos tests). Mantiene el texto plano para asserts.
vi.mock("@/components/ai/MarkdownReportViewer", () => ({
  MarkdownReportViewer: ({ markdown }: { markdown: string }) => (
    <div data-testid="markdown-viewer">{markdown}</div>
  ),
}));

import { mswServer } from "@/test/setup";
import {
  emptyInsightsHandler,
  insightsWithSupersedesHandler,
  mockInsight,
} from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { InsightsTimeline } from "@/components/athletes/ai/InsightsTimeline";

describe("InsightsTimeline", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza loading skeleton inicial", () => {
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    expect(
      screen.getByRole("status", { name: /cargando histórico/i }),
    ).toBeInTheDocument();
  });

  it("renderiza empty state cuando no hay insights — modo coach", async () => {
    mswServer.use(emptyInsightsHandler);
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(
        screen.getByText(/aún no hay análisis aprobados/i),
      ).toBeInTheDocument();
    });
    // El hint para coach pide ir a "Lanzar".
    expect(screen.getByText(/lanza un análisis desde/i)).toBeInTheDocument();
  });

  it("renderiza empty state con copy adaptado a parent", async () => {
    mswServer.use(emptyInsightsHandler);
    renderWithProviders(<InsightsTimeline athleteId={42} mode="parent" />);
    await waitFor(() => {
      expect(
        screen.getByText(/cuando tu entrenador apruebe/i),
      ).toBeInTheDocument();
    });
  });

  it("renderiza N cards cuando hay insights", async () => {
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1")).toBeInTheDocument();
    });
    expect(screen.getByTestId("insight-card-2")).toBeInTheDocument();
    // Cada card tiene badges (válida 4 + válida 3 del 2do mock)
    expect(screen.getAllByText(/válida\s*4/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/válida\s*3/i).length).toBeGreaterThan(0);
  });

  it("abre el detalle al hacer click en una card", async () => {
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-card-1"));

    // Dialog/Sheet expone título "Detalle del análisis"
    await waitFor(() => {
      expect(screen.getByText(/detalle del análisis/i)).toBeInTheDocument();
    });

    // El summary_text se renderiza via mocked MarkdownReportViewer.
    await waitFor(() => {
      expect(screen.getByTestId("markdown-viewer")).toBeInTheDocument();
    });

    // Recomendaciones (mock detail tiene 2)
    expect(screen.getByText(/recomendaciones/i)).toBeInTheDocument();
    expect(
      screen.getByText(/mantener trabajo de cadencia/i),
    ).toBeInTheDocument();
  });

  it("muestra sección 'Versiones anteriores' cuando supersedes.length > 0", async () => {
    mswServer.use(insightsWithSupersedesHandler);
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-card-1"));

    await waitFor(() => {
      expect(screen.getByTestId("insight-supersedes")).toBeInTheDocument();
    });
    expect(screen.getByText(/versiones anteriores \(2\)/i)).toBeInTheDocument();
  });

  it("oculta el badge de versión prompt para parents (no aparece v1.2)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="parent" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-card-1"));
    await waitFor(() => {
      expect(screen.getByText(/detalle del análisis/i)).toBeInTheDocument();
    });
    // El badge "v{prompt_version}" sólo lo vemos en mode=coach.
    expect(screen.queryByText("v1.2")).not.toBeInTheDocument();
  });

  it("oculta el badge de confianza en el drawer detalle para parents (Ley 1581)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="parent" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-card-1"));
    await waitFor(() => {
      expect(screen.getByText(/detalle del análisis/i)).toBeInTheDocument();
    });
    expect(
      screen.queryByText(/confianza (alta|media|baja)/i),
    ).not.toBeInTheDocument();
  });

  it("muestra un error de servidor cuando el listado falla", async () => {
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights",
        () =>
          new HttpResponse(JSON.stringify({ detail: "kaboom" }), {
            status: 500,
          }),
      ),
    );
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(
        screen.getByText(/no pudimos cargar el histórico/i),
      ).toBeInTheDocument();
    });
  });

  it("aplica line-clamp-2 sobre summaries largos (truncado por CSS, no por JS)", async () => {
    // Sprint 1 — el truncate JS con "…" fue reemplazado por CSS line-clamp-2.
    // El texto completo se mantiene en el DOM (mejor a11y para lectores de
    // pantalla) y el navegador lo recorta visualmente con dos líneas + "…".
    const longText = "Lorem ipsum ".repeat(40);
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights",
        () =>
          HttpResponse.json({
            items: [mockInsight({ summary_text: longText })],
            total: 1,
            limit: 50,
            offset: 0,
          }),
      ),
    );
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1")).toBeInTheDocument();
    });
    // 1) El texto COMPLETO está en el DOM (sin recorte JS, sin "…").
    const preview = screen.getByText((_content, node) => {
      if (!node) return false;
      return (
        node.tagName.toLowerCase() === "p" &&
        node.className.includes("line-clamp-2") &&
        (node.textContent ?? "").trim() === longText.trim()
      );
    });
    expect(preview).toBeInTheDocument();
    // 2) El recorte es responsabilidad de CSS — verificamos la clase Tailwind.
    expect(preview).toHaveClass("line-clamp-2");
    // 3) Sanidad: ningún "…" insertado por JS al final del nodo.
    expect((preview.textContent ?? "").trim().endsWith("…")).toBe(false);
  });

  it("no tiene violaciones a11y en el listado", async () => {
    const { container } = renderWithProviders(
      <InsightsTimeline athleteId={42} mode="coach" />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones a11y en empty state", async () => {
    mswServer.use(emptyInsightsHandler);
    const { container } = renderWithProviders(
      <InsightsTimeline athleteId={42} mode="parent" />,
    );
    await waitFor(() => {
      expect(
        screen.getByText(/aún no hay análisis aprobados/i),
      ).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
