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
 * AnalysisRunTimeline, PanoramaView) — están testeados en sus propios specs.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

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
vi.mock("@/components/athletes/ai/LaunchAnalysisForm", () => ({
  LaunchAnalysisForm: ({ athleteName }: { athleteName: string }) => (
    <div data-testid="mock-launch-form">launch-{athleteName}</div>
  ),
}));
vi.mock("@/components/ai/AnalysisRunTimeline", () => ({
  AnalysisRunTimeline: ({ runId }: { runId: string }) => (
    <div data-testid="mock-run-timeline">run-{runId}</div>
  ),
}));

import { mswServer } from "@/test/setup";
import { emptyInsightsHandler } from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { AthleteAIAnalysisTab } from "@/components/athletes/ai/AthleteAIAnalysisTab";
import type { AthleteOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

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
    // Badge "Válida 4" (header)
    expect(
      screen.getAllByText(/válida\s*4/i).length,
    ).toBeGreaterThanOrEqual(1);
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
