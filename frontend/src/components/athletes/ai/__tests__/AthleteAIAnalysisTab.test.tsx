/**
 * Tests vitest para AthleteAIAnalysisTab (FE-3, Sprint 2 BB3+BB4).
 *
 * Cubre:
 *  - 5 sub-tabs renderizados en mode=coach (Panorama, Histórico,
 *    Evolución, Distribución, Lanzar). El tab "Comparador" fue
 *    eliminado en Sprint 2 BB3 — ahora es un Sheet dentro de
 *    Distribución.
 *  - mode=parent oculta "Lanzar" + "Distribución" (privacidad).
 *  - Header del tab muestra última fecha/válida cuando hay insights.
 *  - Loading state mientras espera datos.
 *  - Click en tab cambia el contenido renderizado.
 *  - BB3: botón "open-comparator-sheet" dentro de Distribución abre
 *    Sheet con ComparatorPanel montado.
 *  - BB4: multi-select para boletín — checkboxes solo coach,
 *    action bar aparece con copy correcto, "Limpiar" la cierra.
 *
 * Mockeamos los sub-componentes pesados (InsightsTimeline,
 * EvolutionChart, ComparatorPanel, DistributionChart, LaunchAnalysisForm,
 * PanoramaView) — están testeados en sus propios specs.
 *
 * Excepción (T015, feature 036): `AnalysisRunTimeline` y
 * `HITLApprovalCard` NO se mockean — la suite "T012/T013/T014" al final
 * de este archivo los monta reales contra MSW, porque mockear el propio
 * timeline es justo lo que dejó sin probar la lógica de activeRunId/HITL
 * que vive en este componente.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, screen, waitFor } from "@testing-library/react";
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

// ---------------------------------------------------------------------------
// Mocks de useAttachInsightsToNewsletter para controlar el estado de la mutación
// en los tests de la sticky action bar (Sprint 4).
// Usamos una variable mutable que cada test puede sobreescribir.
// ---------------------------------------------------------------------------
const mockAttachMutate = vi.fn();
const mockAttachReset = vi.fn();
let mockAttachState: {
  isPending: boolean;
  isSuccess: boolean;
  isError: boolean;
  data: unknown;
  error: unknown;
  mutate: typeof mockAttachMutate;
  reset: typeof mockAttachReset;
} = {
  isPending: false,
  isSuccess: false,
  isError: false,
  data: undefined,
  error: null,
  mutate: mockAttachMutate,
  reset: mockAttachReset,
};

vi.mock("@/api/athleteNewsletters", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/athleteNewsletters")>();
  return {
    ...actual,
    useAttachInsightsToNewsletter: vi.fn(() => mockAttachState),
  };
});

vi.mock("@/components/athletes/ai/PanoramaView", () => ({
  PanoramaView: ({ mode }: { mode: string }) => (
    <div data-testid="mock-panorama-view">panorama-{mode}</div>
  ),
}));
// InsightsTimeline mock: expone toggleSelection vía botones-checkbox para
// poder probar la action bar BB4 sin depender del componente real.
vi.mock("@/components/athletes/ai/InsightsTimeline", () => ({
  InsightsTimeline: ({
    mode,
    newsletterSelection,
    onToggleSelection,
  }: {
    mode: string;
    newsletterSelection?: Set<number>;
    onToggleSelection?: (id: number) => void;
  }) => (
    <div data-testid="mock-insights-timeline">
      timeline-{mode}
      {onToggleSelection && (
        <div>
          {[101, 102, 103].map((id) => (
            <button
              key={id}
              type="button"
              data-testid={`insight-checkbox-${id}`}
              aria-pressed={newsletterSelection?.has(id) ?? false}
              onClick={() => onToggleSelection(id)}
            >
              toggle-{id}
            </button>
          ))}
        </div>
      )}
    </div>
  ),
}));
vi.mock("@/components/athletes/ai/EvolutionChart", () => ({
  EvolutionChart: () => <div data-testid="mock-evolution-chart">evolution</div>,
}));
vi.mock("@/components/athletes/ai/ComparatorPanel", () => ({
  ComparatorPanel: () => <div data-testid="mock-comparator-panel">compare</div>,
}));
vi.mock("@/components/athletes/ai/DistributionChart", () => ({
  DistributionChart: () => (
    <div data-testid="mock-distribution-chart">distribution</div>
  ),
}));
// LaunchAnalysisForm mock: expone un botón que dispara onStarted
// directamente (T015), sin reproducir el formulario real (carreras,
// season, useAIStatus) — eso ya está cubierto en LaunchAnalysisForm.test.tsx.
// Las pruebas T012-T014 (activeRunId / HITL) sólo necesitan poder
// simular "un run acaba de arrancar".
vi.mock("@/components/athletes/ai/LaunchAnalysisForm", () => ({
  LaunchAnalysisForm: ({
    athleteName,
    onStarted,
  }: {
    athleteName: string;
    onStarted?: (runId: string) => void;
  }) => (
    <div data-testid="mock-launch-form">
      launch-{athleteName}
      <button
        type="button"
        data-testid="mock-launch-trigger"
        onClick={() => onStarted?.("run-mock-001")}
      >
        simular inicio de run
      </button>
    </div>
  ),
}));
// AnalysisRunTimeline y HITLApprovalCard ya NO se mockean (T015): las
// pruebas T012-T014 más abajo montan el árbol real contra MSW — mockear
// el propio timeline es justo lo que dejaba sin probar la lógica de
// activeRunId/HITL de este archivo.

import { mswServer } from "@/test/setup";
import { emptyInsightsHandler, mockInsight } from "@/test/msw/athleteRaceAnalysisHandlers";
import { seasonSummarySuccessHandler } from "@/test/msw/raceAnalysisV2Handlers";
import {
  createTestQueryClient,
  renderWithProviders,
} from "@/test/helpers/renderWithProviders";
import { AthleteAIAnalysisTab } from "@/components/athletes/ai/AthleteAIAnalysisTab";
import type { AthleteOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";
import { doneRunStatusHandler } from "./raceRunTestHandlers";

const athlete: AthleteOut = {
  id: 42,
  user_id: 100,
  first_name: "Sebastián",
  last_name: "García",
  birth_date: "2012-01-15",
  sex: Sex.M,
  club_join_date: "2024-01-01",
  years_in_club: 2,
  age_decimal: 14.3,
  category: "Sub-15",
  club_id: 1,
  created_at: "2024-01-01T00:00:00Z",
};

describe("AthleteAIAnalysisTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Resetear el estado de la mutación al estado idle por defecto
    mockAttachState = {
      isPending: false,
      isSuccess: false,
      isError: false,
      data: undefined,
      error: null,
      mutate: mockAttachMutate,
      reset: mockAttachReset,
    };
  });

  it("renderiza los 5 sub-tabs en mode=coach (Panorama, Histórico, Evolución, Distribución, Lanzar) — Comparador eliminado en Sprint 2 BB3", async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("ai-subtab-panorama")).toBeInTheDocument();
    });
    expect(screen.getByTestId("ai-subtab-history")).toBeInTheDocument();
    expect(screen.getByTestId("ai-subtab-evolution")).toBeInTheDocument();
    expect(screen.getByTestId("ai-subtab-distribution")).toBeInTheDocument();
    expect(screen.getByTestId("ai-subtab-launch")).toBeInTheDocument();
    // BB3: Comparador ya no es un tab. Vive dentro de Distribución como Sheet.
    expect(screen.queryByTestId("ai-subtab-compare")).not.toBeInTheDocument();
    // Sanidad: exactamente 5 tabs en coach.
    const tabsList = screen.getByRole("tablist");
    expect(tabsList.querySelectorAll('[role="tab"]').length).toBe(5);
  });

  // -------------------------------------------------------------------------
  // T090 (feature 036, US6) — el strip de sub-tabs ya no oculta overflow con
  // scroll horizontal invisible (scrollbar-width:none): a 360–400px eso
  // dejaba "Analizar con IA" — el último sub-tab y la acción principal del
  // módulo — inalcanzable salvo que el usuario adivinara que podía
  // deslizar. jsdom no calcula layout real (no hay forma de medir overflow
  // horizontal aquí — ver target-size.spec.ts para la comprobación con
  // layout real a 360px), así que esta prueba confirma el fix estructural:
  // ya no existe la clase que ocultaba el scroll, y el strip permite wrap.
  // -------------------------------------------------------------------------
  it("T090 — el strip de sub-tabs ya no oculta el overflow con scroll invisible (permite wrap)", async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("ai-subtab-panorama")).toBeInTheDocument();
    });
    const tabsList = screen.getByRole("tablist");
    expect(tabsList.className).toContain("flex-wrap");
    expect(tabsList.className).not.toContain("overflow-x-auto");
    expect(tabsList.className).not.toContain("scrollbar");
  });

  it("default activo en mode=coach es 'panorama'", async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("ai-subtab-panorama")).toBeInTheDocument();
    });
    // Radix Tabs marca el trigger activo con data-state="active" y
    // aria-selected="true".
    const panoramaTrigger = screen.getByTestId("ai-subtab-panorama");
    expect(panoramaTrigger).toHaveAttribute("data-state", "active");
    expect(panoramaTrigger).toHaveAttribute("aria-selected", "true");
    // Y el contenido inicial es el de Panorama (no Histórico).
    expect(screen.getByTestId("mock-panorama-view")).toBeInTheDocument();
    expect(
      screen.queryByTestId("mock-insights-timeline"),
    ).not.toBeInTheDocument();
  });

  it("oculta 'Lanzar' en mode=parent", async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="parent" />);
    await waitFor(() => {
      expect(screen.getByTestId("ai-subtab-panorama")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("ai-subtab-launch")).not.toBeInTheDocument();
  });

  it("muestra Skeleton mientras espera el header de último análisis", () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    // Skeleton del header (initial loading): no estamos buscando getByRole
    // porque Skeleton no tiene role, pero ai-header-summary aún no aparece.
    expect(screen.queryByTestId("ai-header-summary")).not.toBeInTheDocument();
  });

  it("muestra header con última fecha y badge de válida cuando hay insights", async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("ai-header-summary")).toBeInTheDocument();
    });
    // El header expone "Total aprobados: 2" del MSW handler default
    expect(screen.getByText(/total aprobados:\s*2/i)).toBeInTheDocument();
    // Badge "Válida IV" (header) — formato romano, feature 036 T032.
    expect(
      screen.getAllByText(/válida\s*iv\b/i).length,
    ).toBeGreaterThanOrEqual(1);
  });

  // T019: confidenceStatus() canónico de lib/insights.ts (contract
  // status-vocabulary-sweep.md §4) — el header renderiza el badge de
  // confianza vía <StatusBadge>, ya no el par local
  // confidenceBadgeVariant/confidenceText eliminado de este archivo.
  it("badge de confianza del header usa el StatusBadge compartido (confidenceStatus canónico)", async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("ai-header-summary")).toBeInTheDocument();
    });
    // El insight más reciente del handler default trae confidence="high"
    // → confidenceStatus() mapea a status="success", label="Confianza alta".
    const badge = screen.getByText("Confianza alta");
    expect(badge).toBeInTheDocument();
    expect(badge.closest("span")).toHaveClass("bg-success/10");
  });

  // -------------------------------------------------------------------------
  // T034 (feature 036, US5) — el header ancla "Último análisis" a la fecha
  // de LA CARRERA, no a cuándo se generó el análisis. Antes, "Válida 1"
  // (una carrera vieja) aparecía junto a la fecha de HOY (generated_at),
  // dando la falsa impresión de que la válida 1 acababa de correrse — el
  // coach no podía distinguir "el módulo está roto" de "simplemente hay
  // válidas más nuevas sin analizar todavía".
  // -------------------------------------------------------------------------

  it("T034 — el header ancla 'Último análisis' a la fecha de la carrera (event_date), no a la fecha de generación", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
        HttpResponse.json({
          items: [
            mockInsight({
              valida_num: 1,
              event_date: "2026-03-15",
              generated_at: "2026-08-30T10:00:00Z",
              season: 2026,
            }),
          ],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
    );
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("ai-header-summary")).toBeInTheDocument();
    });

    // La fecha prominente es la de LA CARRERA (15 mar 2026) — antes de
    // T034 esta línea mostraba la fecha de generación (30 ago 2026).
    const raceDate = screen.getByTestId("ai-header-race-date");
    expect(raceDate).toHaveTextContent("15 mar 2026");
    expect(raceDate).not.toHaveTextContent(/30 ago/);
    // La fecha de generación se conserva, pero marcada explícitamente
    // como tal ("Generado ..."), en una línea aparte — no se pierde
    // información, sólo se deja de confundir con la fecha de la carrera.
    // No fijamos el formato exacto de `formatDateTimeCompact` (varía con
    // la data ICU del runtime) — sólo que la etiqueta "Generado" está
    // presente y que trae el año/mes de generación (agosto), distinto al
    // de la carrera (marzo).
    const summary = screen.getByTestId("ai-header-summary");
    expect(summary).toHaveTextContent(/generado/i);
    expect(summary).toHaveTextContent(/ago/i);
  });

  it("T034 — resumen de temporada (sin evento vinculado): el header cae a 'Temporada {season}' en vez de mostrar la fecha de generación", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
        HttpResponse.json({
          items: [
            mockInsight({
              valida_num: 0,
              event_id: null,
              event_date: null,
              series_kind: null,
              season: 2026,
              use_case: "season_summary_v2",
            }),
          ],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
    );
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("ai-header-summary")).toBeInTheDocument();
    });

    expect(screen.getByTestId("ai-header-race-date")).toHaveTextContent(
      "Temporada 2026",
    );
  });

  it("T040 — al generar el resumen de temporada, el botón deep-linkea al insight recién creado (salta a Histórico)", async () => {
    // `SeasonSummaryButton` requiere >= 3 válidas analizadas para habilitarse.
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
        HttpResponse.json({
          items: [mockInsight({ valida_num: 4 })],
          total: 4,
          limit: 50,
          offset: 0,
        }),
      ),
      seasonSummarySuccessHandler,
    );
    const user = userEvent.setup();
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);

    await waitFor(() => {
      expect(screen.getByTestId("season-summary-btn")).toBeEnabled();
    });
    // Antes de este fix, `onGenerated` nunca se pasaba desde este
    // componente — el link "Ver resumen" de `SeasonSummaryButton` ni
    // siquiera se renderizaba, y generar el resumen dejaba al coach en el
    // mismo sub-tab sin ninguna forma de ver el insight recién creado.
    await user.click(screen.getByTestId("season-summary-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("ai-subtab-history")).toHaveAttribute(
        "data-state",
        "active",
      );
    });
  });

  it("muestra placeholder 'Sin análisis' cuando no hay insights", async () => {
    mswServer.use(emptyInsightsHandler);
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    await waitFor(() => {
      expect(
        screen.getByText(/sin análisis aprobados aún/i),
      ).toBeInTheDocument();
    });
  });

  it("cambia el contenido al hacer click en otro tab", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    // Sprint 1: default tab es Panorama. Histórico ahora requiere click.
    await waitFor(() => {
      expect(screen.getByTestId("mock-panorama-view")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("ai-subtab-history"));
    await waitFor(() => {
      expect(screen.getByTestId("mock-insights-timeline")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("ai-subtab-evolution"));
    await waitFor(() => {
      expect(screen.getByTestId("mock-evolution-chart")).toBeInTheDocument();
    });

    // BB3: el tab Comparador fue reemplazado por Distribución + Sheet.
    // Verificamos que al entrar a Distribución, además del chart
    // aparezca el botón "open-comparator-sheet" (sin abrirlo aquí).
    await user.click(screen.getByTestId("ai-subtab-distribution"));
    await waitFor(() => {
      expect(screen.getByTestId("mock-distribution-chart")).toBeInTheDocument();
    });
    expect(screen.getByTestId("open-comparator-sheet")).toBeInTheDocument();

    await user.click(screen.getByTestId("ai-subtab-launch"));
    await waitFor(() => {
      expect(screen.getByTestId("mock-launch-form")).toBeInTheDocument();
    });
    // LaunchAnalysisForm recibe el athleteName concatenado
    expect(
      screen.getByText(/launch-Sebastián\s+García/i),
    ).toBeInTheDocument();
  });

  it("no tiene violaciones a11y (modo coach, lista no vacía)", async () => {
    const { container } = renderWithProviders(
      <AthleteAIAnalysisTab athlete={athlete} mode="coach" />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("ai-header-summary")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones a11y (modo parent, lista vacía)", async () => {
    mswServer.use(emptyInsightsHandler);
    const { container } = renderWithProviders(
      <AthleteAIAnalysisTab athlete={athlete} mode="parent" />,
    );
    await waitFor(() => {
      expect(
        screen.getByText(/sin análisis aprobados aún/i),
      ).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  // -------------------------------------------------------------------------
  // Sprint 2 BB3 — Comparador como Sheet on-demand dentro de Distribución
  // -------------------------------------------------------------------------

  describe("Sprint 2 BB3 — Comparator Sheet", () => {
    it("click en 'open-comparator-sheet' abre Sheet con ComparatorPanel montado", async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <AthleteAIAnalysisTab athlete={athlete} mode="coach" />,
      );
      await waitFor(() => {
        expect(screen.getByTestId("ai-subtab-panorama")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("ai-subtab-distribution"));
      await waitFor(() => {
        expect(screen.getByTestId("open-comparator-sheet")).toBeInTheDocument();
      });
      // ComparatorPanel mock NO debe estar montado antes de abrir el Sheet.
      expect(
        screen.queryByTestId("mock-comparator-panel"),
      ).not.toBeInTheDocument();

      await user.click(screen.getByTestId("open-comparator-sheet"));

      // Sheet abierto → SheetTitle visible + ComparatorPanel montado.
      await waitFor(() => {
        expect(
          screen.getByText(/comparador de progreso/i),
        ).toBeInTheDocument();
      });
      expect(screen.getByTestId("mock-comparator-panel")).toBeInTheDocument();
    });

    it("parent NO tiene acceso al botón 'open-comparator-sheet' (Distribución oculta)", async () => {
      renderWithProviders(
        <AthleteAIAnalysisTab athlete={athlete} mode="parent" />,
      );
      await waitFor(() => {
        expect(screen.getByTestId("ai-subtab-panorama")).toBeInTheDocument();
      });
      // Distribución no se renderiza para parent → botón no existe.
      expect(
        screen.queryByTestId("open-comparator-sheet"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByTestId("ai-subtab-distribution"),
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Sprint 2 BB4 — Multi-select bulk para boletín (sticky action bar)
  // -------------------------------------------------------------------------

  describe("Sprint 2 BB4 — Multi-select boletín", () => {
    it("coach: cada insight tiene checkbox accesible; click activa la action bar con copy en singular", async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <AthleteAIAnalysisTab athlete={athlete} mode="coach" />,
      );
      // Cambiamos a Histórico para que se monten los checkboxes del mock.
      await waitFor(() => {
        expect(screen.getByTestId("ai-subtab-history")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("ai-subtab-history"));
      await waitFor(() => {
        expect(
          screen.getByTestId("mock-insights-timeline"),
        ).toBeInTheDocument();
      });
      // Checkboxes del mock presentes.
      expect(screen.getByTestId("insight-checkbox-101")).toBeInTheDocument();
      // Action bar aún no visible (sin selección).
      expect(
        screen.queryByTestId("newsletter-action-bar"),
      ).not.toBeInTheDocument();

      await user.click(screen.getByTestId("insight-checkbox-101"));
      await waitFor(() => {
        expect(
          screen.getByTestId("newsletter-action-bar"),
        ).toBeInTheDocument();
      });
      const bar = screen.getByTestId("newsletter-action-bar");
      expect(bar).toHaveTextContent(/1\s+insight\s+seleccionado/i);
    });

    // -----------------------------------------------------------------------
    // T093 (feature 036, US6) — la barra sticky cambia de estado (conteo de
    // selección, éxito, error) sin anunciar nada a un lector de pantalla.
    // -----------------------------------------------------------------------
    it("T093 — la action bar expone role='status' y aria-live='polite' (no 'assertive': la acción es reintentable)", async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <AthleteAIAnalysisTab athlete={athlete} mode="coach" />,
      );
      await waitFor(() => {
        expect(screen.getByTestId("ai-subtab-history")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("ai-subtab-history"));
      await waitFor(() => {
        expect(
          screen.getByTestId("mock-insights-timeline"),
        ).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("insight-checkbox-101"));

      const bar = await screen.findByTestId("newsletter-action-bar");
      expect(bar).toHaveAttribute("role", "status");
      expect(bar).toHaveAttribute("aria-live", "polite");
    });

    it("coach: dos checks → copy en plural; 'Limpiar' colapsa la action bar", async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <AthleteAIAnalysisTab athlete={athlete} mode="coach" />,
      );
      await waitFor(() => {
        expect(screen.getByTestId("ai-subtab-history")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("ai-subtab-history"));
      await waitFor(() => {
        expect(
          screen.getByTestId("mock-insights-timeline"),
        ).toBeInTheDocument();
      });

      await user.click(screen.getByTestId("insight-checkbox-101"));
      await user.click(screen.getByTestId("insight-checkbox-102"));
      await waitFor(() => {
        const bar = screen.getByTestId("newsletter-action-bar");
        expect(bar).toHaveTextContent(/2\s+insights\s+seleccionados/i);
      });

      // Botón "Limpiar" → action bar desaparece.
      await user.click(screen.getByRole("button", { name: /limpiar/i }));
      await waitFor(() => {
        expect(
          screen.queryByTestId("newsletter-action-bar"),
        ).not.toBeInTheDocument();
      });
    });

    it("parent: NO se renderizan checkboxes ni la action bar nunca aparece", async () => {
      renderWithProviders(
        <AthleteAIAnalysisTab athlete={athlete} mode="parent" />,
      );
      await waitFor(() => {
        expect(screen.getByTestId("ai-subtab-history")).toBeInTheDocument();
      });
      // No es necesario clicar histórico — el contrato es que onToggleSelection
      // sólo se pasa al mock cuando mode==="coach". Aún así verificamos que
      // tras navegar a Histórico no aparezcan checkboxes.
      const user = userEvent.setup();
      await user.click(screen.getByTestId("ai-subtab-history"));
      await waitFor(() => {
        expect(
          screen.getByTestId("mock-insights-timeline"),
        ).toBeInTheDocument();
      });
      // Privacidad Ley 1581: el rol parent no maneja flujo de boletín.
      expect(
        screen.queryByTestId("insight-checkbox-101"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByTestId("insight-checkbox-102"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByTestId("insight-checkbox-103"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByTestId("newsletter-action-bar"),
      ).not.toBeInTheDocument();
    });

    it("coach: a11y con action bar visible (estado seleccionado) no introduce violaciones", async () => {
      const user = userEvent.setup();
      const { container } = renderWithProviders(
        <AthleteAIAnalysisTab athlete={athlete} mode="coach" />,
      );
      await waitFor(() => {
        expect(screen.getByTestId("ai-subtab-history")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("ai-subtab-history"));
      await waitFor(() => {
        expect(
          screen.getByTestId("mock-insights-timeline"),
        ).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("insight-checkbox-101"));
      await waitFor(() => {
        expect(
          screen.getByTestId("newsletter-action-bar"),
        ).toBeInTheDocument();
      });
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  // -------------------------------------------------------------------------
  // Sprint 4 — attach-insights: mutation real vs action bar feedback
  // -------------------------------------------------------------------------

  describe("Sprint 4 — attach-insights mutation", () => {
    async function setupHistoryWithSelection(user: ReturnType<typeof userEvent.setup>) {
      renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
      await waitFor(() => {
        expect(screen.getByTestId("ai-subtab-history")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("ai-subtab-history"));
      await waitFor(() => {
        expect(screen.getByTestId("mock-insights-timeline")).toBeInTheDocument();
      });
      // Seleccionar 2 insights
      await user.click(screen.getByTestId("insight-checkbox-101"));
      await user.click(screen.getByTestId("insight-checkbox-102"));
      await waitFor(() => {
        expect(screen.getByTestId("newsletter-action-bar")).toBeInTheDocument();
      });
    }

    it("click 'Enviar a boletín' dispara la mutación con los insight_ids seleccionados", async () => {
      const user = userEvent.setup();
      await setupHistoryWithSelection(user);

      await user.click(screen.getByTestId("newsletter-action-bar-submit"));

      await waitFor(() => {
        expect(mockAttachMutate).toHaveBeenCalledOnce();
      });
      const [payload] = mockAttachMutate.mock.calls[0] as [{ insight_ids: number[] }];
      expect(payload.insight_ids).toContain(101);
      expect(payload.insight_ids).toContain(102);
    });

    it("isPending → label 'Enviando…' y botón disabled", async () => {
      mockAttachState = { ...mockAttachState, isPending: true };
      const user = userEvent.setup();
      renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
      await waitFor(() => {
        expect(screen.getByTestId("ai-subtab-history")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("ai-subtab-history"));
      await waitFor(() => {
        expect(screen.getByTestId("mock-insights-timeline")).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("insight-checkbox-101"));
      await waitFor(() => {
        expect(screen.getByTestId("newsletter-action-bar")).toBeInTheDocument();
      });

      const submitBtn = screen.getByTestId("newsletter-action-bar-submit");
      expect(submitBtn).toHaveTextContent(/enviando/i);
      expect(submitBtn).toBeDisabled();
    });

    it("isSuccess con selección vacía → mensaje de confirmación visible", async () => {
      // isSuccess = true, selección vacía (ya fue limpiada por onSuccess)
      mockAttachState = { ...mockAttachState, isSuccess: true };
      renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
      await waitFor(() => {
        expect(screen.getByTestId("newsletter-action-bar")).toBeInTheDocument();
      });
      expect(screen.getByTestId("newsletter-action-bar-success")).toBeInTheDocument();
      expect(screen.getByTestId("newsletter-action-bar-success")).toHaveTextContent(
        /agregados al boletín del mes/i,
      );
    });

    it("isError → mensaje de error + botón Reintentar visibles; sin exponer datos PII", async () => {
      mockAttachState = {
        ...mockAttachState,
        isError: true,
        error: { response: { status: 400 } },
      };
      renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
      await waitFor(() => {
        expect(screen.getByTestId("newsletter-action-bar")).toBeInTheDocument();
      });

      const errorMsg = screen.getByTestId("newsletter-action-bar-error");
      expect(errorMsg).toBeInTheDocument();
      // El mensaje no expone IDs ni datos del atleta
      expect(errorMsg.textContent).not.toMatch(/\d{3,}/);
      expect(errorMsg).toHaveTextContent(/no pudimos agregar al boletín/i);

      // Botón Reintentar presente
      expect(screen.getByRole("button", { name: /reintentar/i })).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Rename table (feature 033 / T054, T046) — contracts/ai-identity.md §1
// ---------------------------------------------------------------------------

describe("AthleteAIAnalysisTab — rename table (T054, regresión T046)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAttachState = {
      isPending: false,
      isSuccess: false,
      isError: false,
      data: undefined,
      error: null,
      mutate: mockAttachMutate,
      reset: mockAttachReset,
    };
  });

  it('mode=coach: el header es "Insights IA" (h2), no "Análisis IA del deportista"', async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    const heading = await screen.findByRole("heading", {
      level: 2,
      name: "Insights IA",
    });
    expect(heading).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { level: 2, name: "Análisis IA del deportista" }),
    ).not.toBeInTheDocument();
  });

  it('mode=parent: el header sigue siendo "Insights IA" (h2), no "Análisis del coach"', async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="parent" />);
    const heading = await screen.findByRole("heading", {
      level: 2,
      name: "Insights IA",
    });
    expect(heading).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { level: 2, name: "Análisis del coach" }),
    ).not.toBeInTheDocument();
  });

  it('el sub-tab de lanzamiento se llama "Analizar con IA" con ícono Sparkles, no "Lanzar" con Play', async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    const subtab = await screen.findByTestId("ai-subtab-launch");
    expect(subtab).toHaveTextContent("Analizar con IA");
    expect(subtab).not.toHaveTextContent("Lanzar");
    expect(subtab.querySelector("svg.lucide-sparkles")).toBeInTheDocument();
    expect(subtab.querySelector("svg.lucide-play")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// T015 (feature 036, US3) — T012/T013/T014 con el árbol REAL montado.
//
// `AnalysisRunTimeline` y `HITLApprovalCard` ya no se mockean (ver el
// bloque de mocks arriba). `LaunchAnalysisForm` sigue mockeado, pero
// ahora expone `mock-launch-trigger`, que dispara `onStarted` igual que
// lo haría un submit real — así estas pruebas no dependen de carreras,
// season ni useAIStatus, que son responsabilidad de
// LaunchAnalysisForm.test.tsx.
// ---------------------------------------------------------------------------

describe("AthleteAIAnalysisTab — T012/T013/T014 (árbol real de run+HITL)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAttachState = {
      isPending: false,
      isSuccess: false,
      isError: false,
      data: undefined,
      error: null,
      mutate: mockAttachMutate,
      reset: mockAttachReset,
    };
  });

  async function startMockRun(user: ReturnType<typeof userEvent.setup>) {
    await waitFor(() => {
      expect(screen.getByTestId("ai-subtab-launch")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("ai-subtab-launch"));
    await user.click(await screen.findByTestId("mock-launch-trigger"));
    // handleStarted setea activeRunId + cambia el sub-tab a Histórico de
    // forma síncrona — confirma que sí arrancamos "un run" antes de
    // esperar cualquier efecto de la query real.
    await waitFor(() => {
      expect(screen.getByTestId("ai-subtab-history")).toHaveAttribute(
        "data-state",
        "active",
      );
    });
  }

  it("T012 — al llegar a estado terminal (done), activeRunId se limpia y el timeline deja de estar montado", async () => {
    mswServer.use(doneRunStatusHandler());
    const user = userEvent.setup();
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    await startMockRun(user);

    // Antes de T012 este timeline (real, sin mock) quedaba pegado para
    // siempre porque handleRunComplete nunca volvía a poner activeRunId
    // en null.
    await waitFor(() => {
      expect(screen.queryByTestId("analysis-run-timeline")).not.toBeInTheDocument();
    });
  });

  // T042 (feature 036, US5): antes de este fix, `handleRunComplete`
  // invalidaba con un predicate ad-hoc `startsWith("athlete-")` — perdía
  // `club-insights-by-race` y `season-panorama`. Revertir el fix (volver
  // al predicate inline en vez de `invalidateAthleteAiQueries`) hace
  // fallar este test.
  it("T042 — al completar el run, invalidateAthleteAiQueries cubre club-insights-by-race, season-panorama y las claves del atleta correcto", async () => {
    mswServer.use(doneRunStatusHandler());
    const queryClient = createTestQueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const user = userEvent.setup();
    renderWithProviders(
      <AthleteAIAnalysisTab athlete={athlete} mode="coach" />,
      { queryClient },
    );
    await startMockRun(user);

    await waitFor(() => {
      expect(
        screen.queryByTestId("analysis-run-timeline"),
      ).not.toBeInTheDocument();
    });

    const predicateCall = invalidateSpy.mock.calls.find(
      (call) =>
        typeof (call[0] as { predicate?: unknown } | undefined)
          ?.predicate === "function",
    );
    expect(predicateCall).toBeDefined();
    const predicate = (
      predicateCall![0] as {
        predicate: (q: { queryKey: unknown }) => boolean;
      }
    ).predicate;

    expect(
      predicate({ queryKey: ["athlete-insights", athlete.id, {}] }),
    ).toBe(true);
    // Otro atleta — no debe invalidarse.
    expect(predicate({ queryKey: ["athlete-insights", 999, {}] })).toBe(
      false,
    );
    expect(predicate({ queryKey: ["club-insights-by-race", 3] })).toBe(true);
    expect(predicate({ queryKey: ["season-panorama", 2026, 1] })).toBe(true);
    // Dominios sin relación con un run de IA.
    expect(
      predicate({ queryKey: ["athlete-activities", athlete.id] }),
    ).toBe(false);
    expect(
      predicate({ queryKey: ["athlete-newsletters", 1, athlete.id] }),
    ).toBe(false);
  });

  it("T013 — el timer de confirmación (3s) no se reinicia aunque attachMutation cambie de referencia entre renders", async () => {
    vi.useFakeTimers();
    try {
      mockAttachState = {
        isPending: false,
        isSuccess: true,
        isError: false,
        data: undefined,
        error: null,
        mutate: mockAttachMutate,
        reset: mockAttachReset,
      };
      const { rerender } = renderWithProviders(
        <AthleteAIAnalysisTab athlete={athlete} mode="coach" />,
      );
      expect(
        screen.getByTestId("newsletter-action-bar-success"),
      ).toBeInTheDocument();

      // Simula 4 "poll ticks": cada uno entrega un `attachMutation` con
      // una referencia NUEVA (igual que TanStack Query v5 en cada
      // render), pero el mismo `isSuccess` y la misma función `reset` —
      // justo lo que el fix de T013 debe tolerar sin reiniciar el timer.
      for (let i = 0; i < 4; i += 1) {
        await act(async () => {
          vi.advanceTimersByTime(700);
        });
        mockAttachState = { ...mockAttachState };
        rerender(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
      }
      // 2800 ms repartidos en 4 renders con referencia nueva cada vez.
      // Si el efecto dependiera del objeto completo (bug pre-T013), cada
      // rerender reiniciaría el timer y reset() nunca llegaría a
      // dispararse acá.
      expect(mockAttachReset).not.toHaveBeenCalled();

      await act(async () => {
        vi.advanceTimersByTime(300); // total 3100 ms desde el montaje inicial
      });
      expect(mockAttachReset).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("T014 — la card HITL renderiza el draft real y desaparece apenas el coach decide (no queda pegada al hitl_request viejo)", async () => {
    let decided = false;
    const hitlRequestEvent = {
      seq: 1,
      ts: "2026-08-20T10:00:01Z",
      type: "hitl_request",
      node: "hitl_gate_review",
      payload: {
        step_id: "hitl-step-1",
        draft_markdown: "### Borrador real\nContenido de prueba T014.",
      },
    };
    mswServer.use(
      http.get("*/api/race-analysis/runs/:runId/status", ({ params }) =>
        HttpResponse.json(
          decided
            ? {
                run_id: String(params.runId),
                state: "running",
                progress_pct: 90,
                current_node: "persist_insight",
                started_at: "2026-08-20T10:00:00Z",
                estimated_seconds_remaining: 5,
                last_seq: 2,
                new_events: [
                  hitlRequestEvent,
                  {
                    seq: 2,
                    ts: "2026-08-20T10:00:05Z",
                    type: "hitl_response",
                    node: "hitl_gate_review",
                    payload: {
                      decision: "approve",
                      step_id: "hitl-step-1",
                      has_edits: false,
                    },
                  },
                ],
              }
            : {
                run_id: String(params.runId),
                state: "hitl_waiting",
                progress_pct: 70,
                current_node: "hitl_gate_review",
                started_at: "2026-08-20T10:00:00Z",
                estimated_seconds_remaining: 0,
                last_seq: 1,
                new_events: [hitlRequestEvent],
              },
        ),
      ),
      http.post(
        "*/api/race-analysis/runs/:runId/hitl/:stepId",
        ({ params }) => {
          decided = true;
          return HttpResponse.json({
            accepted: true,
            run_id: String(params.runId),
            step_id: String(params.stepId),
            next_state: "running",
          });
        },
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    await startMockRun(user);

    const card = await screen.findByTestId("hitl-approval-card");
    expect(card).toHaveTextContent(/Borrador real/);

    await user.click(screen.getByTestId("hitl-approve-button"));

    // Antes de T014, el hitl_request viejo seguía "matcheando" para
    // siempre (vía node===hitl_gate_review) y la card no se soltaba
    // aunque ya hubiera un hitl_response más reciente.
    await waitFor(() => {
      expect(screen.queryByTestId("hitl-approval-card")).not.toBeInTheDocument();
    });
  });
});
