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
    // El hint para coach pide ir a "Analizar con IA".
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
    // Cada card tiene badges (válida 4 + válida 3 del 2do mock) — formato
    // romano, feature 036 T032.
    expect(screen.getAllByText(/válida\s*iv\b/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/válida\s*iii\b/i).length).toBeGreaterThan(0);
  });

  // ---------------------------------------------------------------------------
  // T091 (feature 036, US6) — el checkbox de selección para boletín estaba
  // en h-4 w-4 (16px), muy por debajo del piso de 48×48px que
  // `frontend/e2e/target-size.spec.ts` (MIN_TARGET_SIZE=48) exige. jsdom no
  // mide boundingBox() real (por eso el sweep real vive en Playwright,
  // T091b), pero si el tamaño no está en las clases del propio <input> el
  // e2e nunca podrá pasar — mismo patrón usado por feature 032
  // (`TechniqueAttachPicker.tsx`).
  // ---------------------------------------------------------------------------
  it("T091 — el checkbox de boletín usa clases h-12 w-12 (piso táctil 48×48px)", async () => {
    renderWithProviders(
      <InsightsTimeline athleteId={42} mode="coach" onToggleSelection={vi.fn()} />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("insight-checkbox-1")).toBeInTheDocument();
    });
    const checkbox = screen.getByTestId("insight-checkbox-1");
    expect(checkbox.className).toMatch(/(^|\s)h-12(\s|$)/);
    expect(checkbox.className).toMatch(/(^|\s)w-12(\s|$)/);
  });

  // ---------------------------------------------------------------------------
  // T095 (feature 036, US6) — el listado usaba un `aria-label` en un `div`
  // (sin nombre accesible real, porque un `div` es role="generic") en vez de
  // un heading real, así que la navegación por encabezados saltaba de
  // Panorama al resto sin pasar por "Histórico" — a diferencia de
  // EvolutionChart/DistributionChart/LaunchAnalysisForm, que sí exponen un
  // <h3>. El heading debe existir sin importar el estado de la query
  // (loading/error/empty/lista), igual que en esas 3 sub-vistas.
  // ---------------------------------------------------------------------------
  describe("T095 — heading real 'Histórico'", () => {
    it("expone un <h3> 'Histórico' en el estado de carga", () => {
      renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
      expect(
        screen.getByRole("heading", { level: 3, name: /histórico/i }),
      ).toBeInTheDocument();
    });

    it("expone un <h3> 'Histórico' con la lista cargada", async () => {
      renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
      await waitFor(() => {
        expect(screen.getByTestId("insight-card-1")).toBeInTheDocument();
      });
      expect(
        screen.getByRole("heading", { level: 3, name: /histórico/i }),
      ).toBeInTheDocument();
    });

    it("expone un <h3> 'Histórico' en el empty state", async () => {
      mswServer.use(emptyInsightsHandler);
      renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
      await waitFor(() => {
        expect(
          screen.getByText(/aún no hay análisis aprobados/i),
        ).toBeInTheDocument();
      });
      expect(
        screen.getByRole("heading", { level: 3, name: /histórico/i }),
      ).toBeInTheDocument();
    });

    it("expone un <h3> 'Histórico' en el error state", async () => {
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
      expect(
        screen.getByRole("heading", { level: 3, name: /histórico/i }),
      ).toBeInTheDocument();
    });
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

  it("muestra un error de servidor cuando el listado falla (T039: ErrorState con Reintentar)", async () => {
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
    // ErrorState compartido (T039): role="alert" explícito + botón Reintentar
    // — el párrafo rojo ad hoc de antes no ofrecía ninguna acción.
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /reintentar/i }),
    ).toBeInTheDocument();
    // Nunca el texto crudo de la excepción/detail del backend.
    expect(screen.queryByText(/kaboom/i)).not.toBeInTheDocument();
  });

  it("Reintentar en el error del listado vuelve a pedir los insights (T039)", async () => {
    let calls = 0;
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/insights", () => {
        calls += 1;
        return new HttpResponse(JSON.stringify({ detail: "kaboom" }), {
          status: 500,
        });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);

    await screen.findByText(/no pudimos cargar el histórico/i);
    expect(calls).toBe(1);

    await user.click(screen.getByRole("button", { name: /reintentar/i }));
    await waitFor(() => expect(calls).toBe(2));
  });

  it("un fallo de red (forma cold-start) en el listado muestra la copy calmada, no la de error (T039)", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
        HttpResponse.error(),
      ),
    );
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);

    expect(
      await screen.findByText(/la aplicación está iniciando/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/no pudimos cargar el histórico/i),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("muestra ErrorState con Reintentar cuando el detalle de un insight falla al cargar (T039)", async () => {
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
        () =>
          new HttpResponse(JSON.stringify({ detail: "kaboom" }), {
            status: 500,
          }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-card-1"));

    expect(
      await screen.findByText(/no pudimos cargar el detalle del análisis/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /reintentar/i }),
    ).toBeInTheDocument();
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

  // ---------------------------------------------------------------------------
  // T033 (feature 036) — orden por fecha de carrera + fecha visible por fila.
  // Antes: la lista ordenaba por generated_at, produciendo secuencias como
  // Válida 1 → Resumen → Válida 4 → Válida 3 → Válida 2. El backend ya
  // ordena por event_date DESC (insights_history.list_athlete_insights); el
  // cliente NO debe reordenar, y cada fila debe mostrar la fecha real de la
  // carrera, no la de generación.
  // ---------------------------------------------------------------------------

  describe("T033 — orden y fecha de carrera en el histórico", () => {
    it("muestra la fecha de la carrera (event_date), no la de generación ni con corrimiento de huso horario", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/insights",
          () =>
            HttpResponse.json({
              items: [
                mockInsight({
                  id: 301,
                  valida_num: 4,
                  event_date: "2026-05-17",
                  // Analizada semanas después de la carrera — si el
                  // componente mostrara generated_at en vez de event_date,
                  // o si formateara la fecha con corrimiento de zona
                  // horaria (America/Bogotá es UTC-5), este test lo detecta.
                  generated_at: "2026-06-02T10:00:00Z",
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
        expect(screen.getByTestId("insight-card-301")).toBeInTheDocument();
      });
      const card = screen.getByTestId("insight-card-301");
      expect(card).toHaveTextContent(/17.*may.*2026/i);
      // Regresión específica: "2026-05-17" interpretado como medianoche UTC
      // y proyectado a UTC-5 cae en "16 may" — no debe pasar.
      expect(card).not.toHaveTextContent(/16.*may.*2026/i);
    });

    it("con event_date=null (resumen de temporada, filas legacy) no muestra 'Invalid Date' ni un separador colgando", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/insights",
          () =>
            HttpResponse.json({
              items: [
                mockInsight({
                  id: 302,
                  valida_num: 0,
                  event_id: null,
                  event_date: null,
                  series_kind: null,
                  generated_at: "2026-12-15T10:00:00Z",
                }),
              ],
              total: 1,
              limit: 50,
              offset: 0,
            }),
        ),
      );
      renderWithProviders(
        <InsightsTimeline
          athleteId={42}
          mode="coach"
          onToggleSelection={vi.fn()}
        />,
      );
      await waitFor(() => {
        expect(screen.getByTestId("insight-card-302")).toBeInTheDocument();
      });
      // El aria-label del checkbox es la salida exacta de
      // validaLabelWithDate — sin event_date debe ser solo la etiqueta:
      // nunca "Invalid Date", nunca un " · " sin fecha detrás.
      expect(
        screen.getByLabelText(
          "Seleccionar análisis Resumen de temporada para boletín",
        ),
      ).toBeInTheDocument();
      expect(screen.queryByText(/invalid date/i)).not.toBeInTheDocument();
    });

    it("muestra 'Cto. Nacional' cuando series_level='national' (feature 039)", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/insights",
          () =>
            HttpResponse.json({
              items: [
                mockInsight({
                  id: 303,
                  valida_num: 8,
                  event_id: 200,
                  event_date: "2026-06-12",
                  series_kind: "championship",
                  series_level: "national",
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
        expect(screen.getByTestId("insight-card-303")).toBeInTheDocument();
      });
      const card = screen.getByTestId("insight-card-303");
      expect(card).toHaveTextContent("Cto. Nacional");
      // No debe confundirse con el default departamental ni mostrar ambas.
      expect(card).not.toHaveTextContent("Cto. Departamental");
    });

    it("no reordena el listado del backend — respeta el orden por fecha de carrera del servidor", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/insights",
          () =>
            HttpResponse.json({
              items: [
                // Orden deliberadamente NO monótono en generated_at: si el
                // cliente reordenara por generated_at (o por valida_num)
                // este orden cambiaría. El server ya ordena por event_date
                // DESC (insights_history.list_athlete_insights) — el
                // cliente debe respetarlo tal cual llega.
                mockInsight({
                  id: 401,
                  valida_num: 4,
                  event_date: "2026-05-17",
                  generated_at: "2026-01-10T09:00:00Z",
                }),
                mockInsight({
                  id: 402,
                  valida_num: 3,
                  event_date: "2026-04-19",
                  generated_at: "2026-06-01T09:00:00Z",
                }),
                mockInsight({
                  id: 403,
                  valida_num: 2,
                  event_date: "2026-02-28",
                  generated_at: "2026-02-28T09:00:00Z",
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
        expect(screen.getByTestId("insight-card-401")).toBeInTheDocument();
      });
      const container = screen.getByLabelText(
        /histórico de análisis del deportista/i,
      );
      const ids = Array.from(
        container.querySelectorAll('[data-testid^="insight-card-"]'),
      ).map((el) => el.getAttribute("data-testid"));
      expect(ids).toEqual([
        "insight-card-401",
        "insight-card-402",
        "insight-card-403",
      ]);
    });
  });
});
