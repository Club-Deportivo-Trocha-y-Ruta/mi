/**
 * Tests vitest para AnalysisView — la vista «Análisis IA» de «Carreras»
 * (feature 045, T038 / T042).
 *
 * Re-alojada desde `athletes/ai/__tests__/AthleteAIAnalysisTab.test.tsx`
 * cuando se retiró `AthleteAIAnalysisTab` (T042). Se conserva la cobertura de
 * la lógica que se movió tal cual a `AnalysisView`:
 *
 *  - orden de la vista: pendiente → último análisis → histórico → herramientas
 *    del coach (ya no hay sub-tabs);
 *  - audiencia familiar: etiqueta de IA revisada por el entrenador, sin
 *    lanzador, chat, resumen de temporada ni casillas de boletín;
 *  - `insightId` (de `insight=` en la URL) llega al histórico;
 *  - resumen de temporada → mismo timeline/HITL que las válidas (T302, T012b);
 *  - BB4 multi-select para boletín + barra fija (`NewsletterSelectionBar`),
 *    incluida la mutación real de Sprint 4 y el timer de T013;
 *  - T012/T014/T042/T301: run en vivo, HITL, invalidación y `InsightV3Card`;
 *  - a11y (axe) coach y familia.
 *
 * Lo que NO se re-aloja acá (cambió de dueño):
 *  - header de «último análisis» + badge de confianza → `PanoramaView` /
 *    `HeroLastInsightCard` (sus propios specs);
 *  - Sheet del Comparador (BB3) y Distribución → `CompareView`;
 *  - Evolución → `ProgressionView`.
 *
 * Se mockean los sub-componentes pesados (PanoramaView, InsightsTimeline,
 * LaunchAnalysisForm, chat) — están testeados en sus propios specs. Excepción
 * (T015, feature 036): `AnalysisRunTimeline`, `HITLApprovalCard` y
 * `SeasonSummaryButton` NO se mockean — mockear el propio timeline es justo lo
 * que dejaría sin probar la lógica de activeRunId/HITL que vive en la vista.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
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
// Mock de useAttachInsightsToNewsletter para controlar el estado de la
// mutación en los tests de la barra fija (Sprint 4). Variable mutable que cada
// test puede sobreescribir.
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
// poder probar la barra BB4 sin depender del componente real, y el insight
// seleccionado (`selectedInsightId`) para probar el `insight=` de la URL.
vi.mock("@/components/athletes/ai/InsightsTimeline", () => ({
  InsightsTimeline: ({
    mode,
    selectedInsightId,
    newsletterSelection,
    onToggleSelection,
  }: {
    mode: string;
    selectedInsightId?: number | null;
    newsletterSelection?: Set<number>;
    onToggleSelection?: (id: number) => void;
  }) => (
    <div
      data-testid="mock-insights-timeline"
      data-selected={selectedInsightId ?? ""}
    >
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
vi.mock("@/components/athletes/ai/AthleteAnalystChatPanel", () => ({
  AthleteAnalystChatPanel: () => <div data-testid="mock-chat-panel">chat</div>,
}));
// LaunchAnalysisForm mock: expone un botón que dispara onStarted directamente
// (T015), sin reproducir el formulario real (carreras, season, useAIStatus) —
// eso ya está cubierto en LaunchAnalysisForm.test.tsx. Las pruebas T012-T014
// (activeRunId / HITL) sólo necesitan poder simular "un run acaba de arrancar".
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

import { mswServer } from "@/test/setup";
import { mockInsight } from "@/test/msw/athleteRaceAnalysisHandlers";
import { seasonSummarySuccessHandler } from "@/test/msw/raceAnalysisV2Handlers";
import {
  createTestQueryClient,
  renderWithProviders,
} from "@/test/helpers/renderWithProviders";
import { AnalysisView } from "@/components/athletes/races/AnalysisView";
import type { AthleteOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";
import {
  doneRunStatusHandler,
  hitlWaitingRunStatusHandler,
} from "./raceRunTestHandlers";
import { buildInsightV3 } from "@/test/fixtures/insightV3";

const athlete: AthleteOut = {
  id: 42,
  user_id: 100,
  first_name: "Atleta",
  last_name: "Ficticio",
  birth_date: "2012-01-15",
  sex: Sex.M,
  club_join_date: "2024-01-01",
  years_in_club: 2,
  age_decimal: 14.3,
  category: "Sub-15",
  club_id: 1,
  created_at: "2024-01-01T00:00:00Z",
};

const FAMILY_LABEL = "Análisis generado con IA y revisado por el entrenador.";

function resetAttachState() {
  mockAttachState = {
    isPending: false,
    isSuccess: false,
    isError: false,
    data: undefined,
    error: null,
    mutate: mockAttachMutate,
    reset: mockAttachReset,
  };
}

/** Listado con >= 3 válidas analizadas: habilita `SeasonSummaryButton`. */
function enoughInsightsHandler() {
  return http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
    HttpResponse.json({
      items: [mockInsight({ valida_num: 4 })],
      total: 4,
      limit: 50,
      offset: 0,
    }),
  );
}

const RUN_STATUS_RE = /\/api\/race-analysis\/runs\/([^/?]+)\/status/;

/**
 * Cuenta las peticiones de estado de un run (`GET .../runs/:id/status`). Con
 * un run que termina de inmediato (`done`) el bloque pendiente se monta y se
 * desmonta antes de que un `findBy*` lo alcance a ver: el poll es la prueba
 * de que el run SÍ arrancó y el timeline se montó, para que la aserción
 * posterior "ya no está montado" no pase de forma vacía.
 */
function observeRunStatusPolls() {
  const urls: string[] = [];
  mswServer.events.removeAllListeners();
  mswServer.events.on("request:start", ({ request }) => {
    if (RUN_STATUS_RE.test(request.url)) urls.push(request.url);
  });
  return () => urls.length;
}

/** Espera a que el histórico (mock) esté montado. */
async function waitForTimeline() {
  await waitFor(() => {
    expect(screen.getByTestId("mock-insights-timeline")).toBeInTheDocument();
  });
}

describe("AnalysisView — estructura", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetAttachState();
  });

  it("coach: muestra panorama, histórico y las herramientas (lanzador, chat, resumen) en UNA sola vista, sin sub-tabs", async () => {
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);

    expect(await screen.findByTestId("mock-panorama-view")).toHaveTextContent(
      "panorama-coach",
    );
    expect(screen.getByTestId("mock-insights-timeline")).toHaveTextContent(
      "timeline-coach",
    );
    expect(screen.getByTestId("analysis-coach-tools")).toBeInTheDocument();
    expect(screen.getByTestId("mock-launch-form")).toBeInTheDocument();
    // LaunchAnalysisForm recibe el athleteName concatenado.
    expect(screen.getByText(/launch-Atleta\s+Ficticio/i)).toBeInTheDocument();
    expect(screen.getByTestId("mock-chat-panel")).toBeInTheDocument();
    expect(screen.getByTestId("season-summary-btn")).toBeInTheDocument();
    // Ya no existen los sub-tabs de la antigua AthleteAIAnalysisTab.
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-subtab-launch")).not.toBeInTheDocument();
  });

  it("sin run vivo NO se monta el bloque pendiente (timeline/HITL)", async () => {
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);
    await waitForTimeline();
    expect(screen.queryByTestId("analysis-pending")).not.toBeInTheDocument();
    expect(screen.queryByTestId("analysis-run-timeline")).not.toBeInTheDocument();
  });

  it("identidad de IA (feature 033): la sección del coach se llama «Analizar con IA» con ícono Sparkles, no «Lanzar»", async () => {
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);
    const heading = await screen.findByRole("heading", {
      level: 3,
      name: "Analizar con IA",
    });
    expect(heading.querySelector("svg.lucide-sparkles")).toBeInTheDocument();
    expect(screen.queryByText(/^Lanzar$/)).not.toBeInTheDocument();
    expect(heading.querySelector("svg.lucide-play")).not.toBeInTheDocument();
  });

  it("coach: la etiqueta de la vista describe la IA sin afirmar revisión del entrenador", async () => {
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);
    await waitForTimeline();
    expect(screen.getByTestId("analysis-ai-label")).toHaveTextContent(
      /generado con IA a partir de los resultados oficiales/i,
    );
    expect(screen.queryByText(FAMILY_LABEL)).not.toBeInTheDocument();
  });

  it("familia: muestra la etiqueta «Análisis generado con IA y revisado por el entrenador.» (FR-014)", async () => {
    renderWithProviders(<AnalysisView athlete={athlete} audience="family" />);
    await waitForTimeline();
    expect(screen.getByTestId("analysis-ai-label")).toHaveTextContent(FAMILY_LABEL);
  });

  it("familia: sin lanzador, chat, resumen de temporada ni bloque pendiente", async () => {
    renderWithProviders(<AnalysisView athlete={athlete} audience="family" />);
    await waitForTimeline();
    expect(screen.getByTestId("mock-panorama-view")).toHaveTextContent(
      "panorama-parent",
    );
    expect(screen.queryByTestId("analysis-coach-tools")).not.toBeInTheDocument();
    expect(screen.queryByTestId("mock-launch-form")).not.toBeInTheDocument();
    expect(screen.queryByTestId("mock-chat-panel")).not.toBeInTheDocument();
    expect(screen.queryByTestId("season-summary-btn")).not.toBeInTheDocument();
    expect(screen.queryByTestId("analysis-pending")).not.toBeInTheDocument();
  });

  it("insightId (insight= de la URL) llega al histórico como análisis abierto", async () => {
    renderWithProviders(
      <AnalysisView athlete={athlete} audience="coach" insightId={7} />,
    );
    await waitForTimeline();
    expect(screen.getByTestId("mock-insights-timeline")).toHaveAttribute(
      "data-selected",
      "7",
    );
  });

  it("no tiene violaciones a11y (coach, con herramientas)", async () => {
    const { container } = renderWithProviders(
      <AnalysisView athlete={athlete} audience="coach" />,
    );
    await waitForTimeline();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones a11y (familia)", async () => {
    const { container } = renderWithProviders(
      <AnalysisView athlete={athlete} audience="family" />,
    );
    await waitForTimeline();
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("AnalysisView — resumen de temporada → run en vivo (T302, T012b)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetAttachState();
  });

  afterEach(() => {
    mswServer.events.removeAllListeners();
  });

  it("T302 — al generar el resumen de temporada, el run_id se conecta al mismo timeline/HITL que las válidas", async () => {
    // `SeasonSummaryButton` requiere >= 3 válidas analizadas para habilitarse.
    mswServer.use(
      enoughInsightsHandler(),
      seasonSummarySuccessHandler,
      hitlWaitingRunStatusHandler(),
    );
    const user = userEvent.setup();
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);

    await waitFor(() => {
      expect(screen.getByTestId("season-summary-btn")).toBeEnabled();
    });
    await user.click(screen.getByTestId("season-summary-btn"));

    // El mismo `AnalysisRunTimeline` real (no mockeado) que usan los runs por
    // válida debe montarse para el run del resumen de temporada, dentro del
    // bloque «pendiente» (ya no hay sub-tab de Histórico al que saltar), y al
    // quedar pausado en `hitl_waiting` también debe aparecer la misma
    // `HITLApprovalCard`.
    await waitFor(() => {
      expect(screen.getByTestId("analysis-pending")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId("analysis-run-timeline")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId("hitl-approval-card")).toBeInTheDocument();
    });
  });

  it("T012b — el run del resumen de temporada también se desmonta al llegar a estado terminal", async () => {
    mswServer.use(
      enoughInsightsHandler(),
      seasonSummarySuccessHandler,
      doneRunStatusHandler(),
    );
    const statusPolls = observeRunStatusPolls();
    const user = userEvent.setup();
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);

    await waitFor(() => {
      expect(screen.getByTestId("season-summary-btn")).toBeEnabled();
    });
    await user.click(screen.getByTestId("season-summary-btn"));

    // El run arrancó (el timeline se montó y consultó su estado)…
    await waitFor(() => expect(statusPolls()).toBeGreaterThan(0));
    // …y al llegar a `done` el bloque pendiente se suelta.
    await waitFor(() => {
      expect(screen.queryByTestId("analysis-pending")).not.toBeInTheDocument();
    });
    expect(screen.queryByTestId("analysis-run-timeline")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Sprint 2 BB4 — Multi-select bulk para boletín (barra fija)
// ---------------------------------------------------------------------------

describe("AnalysisView — BB4 multi-select boletín", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetAttachState();
  });

  it("coach: cada insight tiene checkbox accesible; click activa la barra con copy en singular", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);
    await waitForTimeline();
    // Checkboxes del mock presentes.
    expect(screen.getByTestId("insight-checkbox-101")).toBeInTheDocument();
    // Barra aún no visible (sin selección).
    expect(screen.queryByTestId("newsletter-action-bar")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("insight-checkbox-101"));
    const bar = await screen.findByTestId("newsletter-action-bar");
    expect(bar).toHaveTextContent(/1\s+insight\s+seleccionado/i);
  });

  // T093 (feature 036, US6) — la barra cambia de estado (conteo, éxito, error)
  // sin anunciar nada a un lector de pantalla.
  it("T093 — la barra expone role='status' y aria-live='polite' (no 'assertive': la acción es reintentable)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);
    await waitForTimeline();
    await user.click(screen.getByTestId("insight-checkbox-101"));

    const bar = await screen.findByTestId("newsletter-action-bar");
    expect(bar).toHaveAttribute("role", "status");
    expect(bar).toHaveAttribute("aria-live", "polite");
  });

  it("coach: dos checks → copy en plural; 'Limpiar' colapsa la barra", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);
    await waitForTimeline();

    await user.click(screen.getByTestId("insight-checkbox-101"));
    await user.click(screen.getByTestId("insight-checkbox-102"));
    await waitFor(() => {
      expect(screen.getByTestId("newsletter-action-bar")).toHaveTextContent(
        /2\s+insights\s+seleccionados/i,
      );
    });

    await user.click(screen.getByRole("button", { name: /limpiar/i }));
    await waitFor(() => {
      expect(screen.queryByTestId("newsletter-action-bar")).not.toBeInTheDocument();
    });
  });

  it("familia: NO se renderizan checkboxes ni la barra (Ley 1581: la familia no maneja el flujo de boletín)", async () => {
    renderWithProviders(<AnalysisView athlete={athlete} audience="family" />);
    await waitForTimeline();

    [101, 102, 103].forEach((id) => {
      expect(screen.queryByTestId(`insight-checkbox-${id}`)).not.toBeInTheDocument();
    });
    expect(screen.queryByTestId("newsletter-action-bar")).not.toBeInTheDocument();
  });

  it("coach: a11y con la barra visible (estado seleccionado) no introduce violaciones", async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(
      <AnalysisView athlete={athlete} audience="coach" />,
    );
    await waitForTimeline();
    await user.click(screen.getByTestId("insight-checkbox-101"));
    await screen.findByTestId("newsletter-action-bar");
    expect(await axe(container)).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Sprint 4 — attach-insights: mutación vs feedback de la barra
// ---------------------------------------------------------------------------

describe("AnalysisView — Sprint 4 attach-insights mutation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetAttachState();
  });

  async function setupWithSelection(user: ReturnType<typeof userEvent.setup>) {
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);
    await waitForTimeline();
    // Seleccionar 2 insights
    await user.click(screen.getByTestId("insight-checkbox-101"));
    await user.click(screen.getByTestId("insight-checkbox-102"));
    await screen.findByTestId("newsletter-action-bar");
  }

  it("click 'Enviar a boletín' dispara la mutación con los insight_ids seleccionados", async () => {
    const user = userEvent.setup();
    await setupWithSelection(user);

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
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);
    await waitForTimeline();
    await user.click(screen.getByTestId("insight-checkbox-101"));
    await screen.findByTestId("newsletter-action-bar");

    const submitBtn = screen.getByTestId("newsletter-action-bar-submit");
    expect(submitBtn).toHaveTextContent(/enviando/i);
    expect(submitBtn).toBeDisabled();
  });

  it("isSuccess con selección vacía → mensaje de confirmación visible", async () => {
    // isSuccess = true, selección vacía (ya fue limpiada por onSuccess)
    mockAttachState = { ...mockAttachState, isSuccess: true };
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);
    await screen.findByTestId("newsletter-action-bar");
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
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);
    await screen.findByTestId("newsletter-action-bar");

    const errorMsg = screen.getByTestId("newsletter-action-bar-error");
    // El mensaje no expone IDs ni datos del atleta
    expect(errorMsg.textContent).not.toMatch(/\d{3,}/);
    expect(errorMsg).toHaveTextContent(/no pudimos agregar al boletín/i);
    expect(screen.getByRole("button", { name: /reintentar/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// T015 (feature 036, US3) — T012/T013/T014 con el árbol REAL montado.
//
// `AnalysisRunTimeline` y `HITLApprovalCard` no se mockean.
// `LaunchAnalysisForm` sigue mockeado, pero expone `mock-launch-trigger`, que
// dispara `onStarted` igual que lo haría un submit real — así estas pruebas no
// dependen de carreras, season ni useAIStatus (responsabilidad de
// LaunchAnalysisForm.test.tsx).
// ---------------------------------------------------------------------------

describe("AnalysisView — T012/T013/T014 (árbol real de run+HITL)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetAttachState();
  });

  afterEach(() => {
    mswServer.events.removeAllListeners();
  });

  /** Dispara `onStarted` y devuelve el contador de polls de estado. */
  async function startMockRun(user: ReturnType<typeof userEvent.setup>) {
    const statusPolls = observeRunStatusPolls();
    await user.click(await screen.findByTestId("mock-launch-trigger"));
    // handleStarted setea activeRunId de forma síncrona y monta el bloque
    // pendiente; el poll confirma que el timeline real arrancó (ver
    // `observeRunStatusPolls`) antes de esperar cualquier efecto posterior.
    await waitFor(() => expect(statusPolls()).toBeGreaterThan(0));
    return statusPolls;
  }

  it("T012 — al llegar a estado terminal (done), activeRunId se limpia y el timeline deja de estar montado", async () => {
    mswServer.use(doneRunStatusHandler());
    const user = userEvent.setup();
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);
    await startMockRun(user);

    // Antes de T012 este timeline (real, sin mock) quedaba pegado para
    // siempre porque handleRunComplete nunca volvía a poner activeRunId en
    // null.
    await waitFor(() => {
      expect(screen.queryByTestId("analysis-run-timeline")).not.toBeInTheDocument();
    });
    expect(screen.queryByTestId("analysis-pending")).not.toBeInTheDocument();
  });

  // T042 (feature 036, US5): antes de este fix, `handleRunComplete` invalidaba
  // con un predicate ad-hoc `startsWith("athlete-")` — perdía
  // `club-insights-by-race` y `season-panorama`. Revertir el fix (volver al
  // predicate inline en vez de `invalidateAthleteAiQueries`) hace fallar este
  // test.
  it("T042 — al completar el run, invalidateAthleteAiQueries cubre club-insights-by-race, season-panorama y las claves del atleta correcto", async () => {
    mswServer.use(doneRunStatusHandler());
    const queryClient = createTestQueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const user = userEvent.setup();
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />, {
      queryClient,
    });
    await startMockRun(user);

    await waitFor(() => {
      expect(screen.queryByTestId("analysis-run-timeline")).not.toBeInTheDocument();
    });

    const predicateCall = invalidateSpy.mock.calls.find(
      (call) =>
        typeof (call[0] as { predicate?: unknown } | undefined)?.predicate ===
        "function",
    );
    expect(predicateCall).toBeDefined();
    const predicate = (
      predicateCall![0] as {
        predicate: (q: { queryKey: unknown }) => boolean;
      }
    ).predicate;

    expect(predicate({ queryKey: ["athlete-insights", athlete.id, {}] })).toBe(true);
    // Otro atleta — no debe invalidarse.
    expect(predicate({ queryKey: ["athlete-insights", 999, {}] })).toBe(false);
    expect(predicate({ queryKey: ["club-insights-by-race", 3] })).toBe(true);
    expect(predicate({ queryKey: ["season-panorama", 2026, 1] })).toBe(true);
    // Dominios sin relación con un run de IA.
    expect(predicate({ queryKey: ["athlete-activities", athlete.id] })).toBe(false);
    expect(predicate({ queryKey: ["athlete-newsletters", 1, athlete.id] })).toBe(false);
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
        <AnalysisView athlete={athlete} audience="coach" />,
      );
      expect(screen.getByTestId("newsletter-action-bar-success")).toBeInTheDocument();

      // Simula 4 "poll ticks": cada uno entrega un `attachMutation` con una
      // referencia NUEVA (igual que TanStack Query v5 en cada render), pero el
      // mismo `isSuccess` y la misma función `reset` — justo lo que el fix de
      // T013 debe tolerar sin reiniciar el timer.
      for (let i = 0; i < 4; i += 1) {
        await act(async () => {
          vi.advanceTimersByTime(700);
        });
        mockAttachState = { ...mockAttachState };
        rerender(<AnalysisView athlete={athlete} audience="coach" />);
      }
      // 2800 ms repartidos en 4 renders con referencia nueva cada vez. Si el
      // efecto dependiera del objeto completo (bug pre-T013), cada rerender
      // reiniciaría el timer y reset() nunca llegaría a dispararse acá.
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
      http.post("*/api/race-analysis/runs/:runId/hitl/:stepId", ({ params }) => {
        decided = true;
        return HttpResponse.json({
          accepted: true,
          run_id: String(params.runId),
          step_id: String(params.stepId),
          next_state: "running",
        });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);
    await startMockRun(user);

    const card = await screen.findByTestId("hitl-approval-card");
    expect(card).toHaveTextContent(/Borrador real/);

    await user.click(screen.getByTestId("hitl-approve-button"));

    // Antes de T014, el hitl_request viejo seguía "matcheando" para siempre
    // (vía node===hitl_gate_review) y la card no se soltaba aunque ya
    // hubiera un hitl_response más reciente.
    await waitFor(() => {
      expect(screen.queryByTestId("hitl-approval-card")).not.toBeInTheDocument();
    });
  });

  it("T301 (feature 037) — la card HITL renderiza InsightV3Card cuando el evento hitl_request trae payload.structured_draft", async () => {
    const structured = buildInsightV3();
    mswServer.use(
      http.get("*/api/race-analysis/runs/:runId/status", ({ params }) =>
        HttpResponse.json({
          run_id: String(params.runId),
          state: "hitl_waiting",
          progress_pct: 70,
          current_node: "hitl_gate_review",
          started_at: "2026-08-20T10:00:00Z",
          estimated_seconds_remaining: 0,
          last_seq: 1,
          new_events: [
            {
              seq: 1,
              ts: "2026-08-20T10:00:01Z",
              type: "hitl_request",
              node: "hitl_gate_review",
              payload: {
                step_id: "hitl-step-v3",
                draft_markdown: "### Borrador v2 (no debería verse)",
                structured_draft: structured,
              },
            },
          ],
        }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);
    await startMockRun(user);

    expect(await screen.findByTestId("hitl-approval-card")).toBeInTheDocument();
    expect(screen.getByTestId("insight-v3-card")).toBeInTheDocument();
    expect(screen.getByTestId("insight-v3-headline")).toHaveTextContent(
      structured.headline,
    );
  });

  // Feature 045 (T062): `payload.family_gap_mentions` del `hitl_request` llega
  // hasta la tarjeta de aprobación como aviso (coach únicamente).
  describe("T062 — aviso de brecha con el podio en la card HITL", () => {
    function hitlStatusWith(payloadExtra: Record<string, unknown>) {
      return http.get("*/api/race-analysis/runs/:runId/status", ({ params }) =>
        HttpResponse.json({
          run_id: String(params.runId),
          state: "hitl_waiting",
          progress_pct: 70,
          current_node: "hitl_gate_review",
          started_at: "2026-08-20T10:00:00Z",
          estimated_seconds_remaining: 0,
          last_seq: 1,
          new_events: [
            {
              seq: 1,
              ts: "2026-08-20T10:00:01Z",
              type: "hitl_request",
              node: "hitl_gate_review",
              payload: {
                step_id: "hitl-step-gap",
                draft_markdown: "### Borrador\nContenido de prueba.",
                ...payloadExtra,
              },
            },
          ],
        }),
      );
    }

    it("con family_gap_mentions no vacío la card muestra el aviso y los fragmentos; Aprobar y Rechazar siguen ahí", async () => {
      mswServer.use(
        hitlStatusWith({
          family_gap_mentions: ["terminó a 40 s del ganador", "lejos del podio"],
        }),
      );
      const user = userEvent.setup();
      renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);
      await startMockRun(user);

      expect(await screen.findByTestId("hitl-approval-card")).toBeInTheDocument();
      expect(screen.getByTestId("hitl-family-gap-warning")).toHaveTextContent(
        "Este análisis menciona la brecha con el primer lugar o el podio",
      );
      expect(screen.getByTestId("hitl-family-gap-snippets")).toHaveTextContent(
        "«terminó a 40 s del ganador»",
      );
      expect(screen.getByTestId("hitl-approve-button")).toBeEnabled();
      expect(screen.getByTestId("hitl-reject-button")).toBeEnabled();
    });

    it.each([
      ["family_gap_mentions vacío", { family_gap_mentions: [] }],
      ["sin la clave (backend previo a la 045)", {}],
    ])("%s: la card no muestra aviso", async (_label, extra) => {
      mswServer.use(hitlStatusWith(extra));
      const user = userEvent.setup();
      renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);
      await startMockRun(user);

      expect(await screen.findByTestId("hitl-approval-card")).toBeInTheDocument();
      expect(screen.queryByTestId("hitl-family-gap-warning")).not.toBeInTheDocument();
    });
  });
});
