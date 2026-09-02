/**
 * Recuperación de runs activos al montar el tab "Análisis IA".
 *
 * Bug que cubre: `activeRunId` era estado puramente local — sólo se
 * poblaba cuando el coach lanzaba el análisis en ESA instancia de React.
 * Un run en `awaiting_hitl` (análisis terminado esperando la aprobación
 * del coach) desaparecía de la vista tras un refresh, un cambio de
 * sub-tab o al volver al día siguiente, y encima seguía bloqueando con
 * 409 cualquier intento de relanzar, sin nada en pantalla que lo
 * explicara.
 *
 * El arreglo replica el patrón del panel grupal
 * (`hooks/ai/useGroupAnalysis.ts`): recovery query + efecto que siembra el
 * run activo más reciente. Aquí se ejercita end-to-end contra MSW, con
 * `AnalysisRunTimeline` y `HITLApprovalCard` REALES (mockearlos escondería
 * justo lo que se quiere probar) y reusando los handlers de
 * `raceRunTestHandlers.ts`.
 *
 * Las requests se observan con `mswServer.events` en vez de handlers
 * espía, para no competir en prioridad con los handlers reutilizados.
 *
 * La sesión mockeada es SIEMPRE de coach: así el caso `mode="parent"`
 * prueba el gate por modo del componente y no el gate por rol que
 * `useAthleteRuns` ya trae de fábrica.
 */
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
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

// Sub-componentes pesados fuera del alcance de esta prueba (tienen sus
// propios specs). `AnalysisRunTimeline` y `HITLApprovalCard` NO se mockean.
vi.mock("@/components/athletes/ai/PanoramaView", () => ({
  PanoramaView: () => <div data-testid="mock-panorama-view">panorama</div>,
}));
vi.mock("@/components/athletes/ai/InsightsTimeline", () => ({
  InsightsTimeline: () => <div data-testid="mock-insights-timeline">timeline</div>,
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
  LaunchAnalysisForm: () => <div data-testid="mock-launch-form">launch</div>,
}));

import { mswServer } from "@/test/setup";
import { mockRun } from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { AthleteAIAnalysisTab } from "@/components/athletes/ai/AthleteAIAnalysisTab";
import type { AthleteOut } from "@/types/athlete.types";
import type { AthleteRunOut } from "@/types/athleteRaceAnalysis.types";
import { Sex } from "@/types/enums";
import {
  cursorAwareRunStatusHandler,
  hitlWaitingRunStatusHandler,
  progressiveRunStatusHandler,
  staleCursorHitlHandler,
} from "./raceRunTestHandlers";

const RECOVERED_RUN_ID = "run-awaiting-hitl-001";

const athlete: AthleteOut = {
  id: 2,
  user_id: 100,
  first_name: "Atleta",
  last_name: "Prueba",
  birth_date: "2012-01-15",
  sex: Sex.M,
  club_join_date: "2024-01-01",
  years_in_club: 2,
  age_decimal: 14.3,
  category: "Sub-15",
  club_id: 1,
  created_at: "2024-01-01T00:00:00Z",
};

/**
 * Listado tal cual lo entrega el backend: ordenado por `started_at DESC`
 * y SIN filtrar por estado (el endpoint sólo acepta `limit`/`offset`). El
 * run terminal va primero a propósito — si el componente tomara el primer
 * item en vez de filtrar en cliente, tomaría el equivocado.
 */
const RUNS_PAGE: AthleteRunOut[] = [
  mockRun({
    run_id: "run-completed-000",
    status: "completed",
    valida_nums: [3],
    started_at: "2026-05-18T09:55:00Z",
    finished_at: "2026-05-18T10:00:00Z",
  }),
  mockRun({
    run_id: RECOVERED_RUN_ID,
    status: "awaiting_hitl",
    valida_nums: [2],
    started_at: "2026-05-17T09:00:00Z",
    finished_at: null,
    has_output: false,
  }),
  mockRun({
    run_id: "run-running-older",
    status: "running",
    valida_nums: [1],
    started_at: "2026-05-16T09:00:00Z",
    finished_at: null,
    has_output: false,
  }),
];

const RUNS_LIST_RE = /\/api\/athletes\/\d+\/race-analysis\/runs(\?|$)/;
const RUN_STATUS_RE = /\/api\/race-analysis\/runs\/([^/?]+)\/status/;

describe("AthleteAIAnalysisTab — recuperación de runs activos", () => {
  let requestUrls: string[];

  const runsListRequests = () => requestUrls.filter((u) => RUNS_LIST_RE.test(u));
  const polledRunIds = () =>
    requestUrls
      .map((u) => RUN_STATUS_RE.exec(u)?.[1])
      .filter((id): id is string => !!id);

  /** Listado de runs del atleta con los items indicados. */
  function useRunsHandler(items: AthleteRunOut[]) {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/runs", () =>
        HttpResponse.json({
          items,
          total: items.length,
          limit: 20,
          offset: 0,
        }),
      ),
    );
  }

  beforeEach(() => {
    requestUrls = [];
    mswServer.events.removeAllListeners();
    mswServer.events.on("request:start", ({ request }) => {
      requestUrls.push(request.url);
    });
  });

  afterEach(() => {
    mswServer.events.removeAllListeners();
  });

  it("monta la card de aprobación de un run awaiting_hitl sin haber lanzado nada", async () => {
    useRunsHandler(RUNS_PAGE);
    mswServer.use(hitlWaitingRunStatusHandler());

    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);

    // Sin ningún click previo: el timeline y la card de aprobación aparecen
    // solos, sembrados desde el servidor.
    expect(await screen.findByTestId("analysis-run-timeline")).toBeInTheDocument();
    expect(await screen.findByTestId("hitl-approval-card")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /aprobar/i })).toBeInTheDocument();

    // Se sembró el run ACTIVO más reciente, no el terminal que iba primero
    // ni el activo más viejo.
    await waitFor(() => {
      expect(polledRunIds()).toContain(RECOVERED_RUN_ID);
    });
    expect(polledRunIds()).not.toContain("run-completed-000");
    expect(polledRunIds()).not.toContain("run-running-older");
  });

  it("no envía los params `status`/`season` al listado (el backend los descarta; el filtro es en cliente)", async () => {
    useRunsHandler(RUNS_PAGE);
    mswServer.use(hitlWaitingRunStatusHandler());

    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);

    await waitFor(() => {
      expect(runsListRequests().length).toBeGreaterThan(0);
    });
    for (const url of runsListRequests()) {
      const params = new URL(url).searchParams;
      expect(params.get("status")).toBeNull();
      expect(params.get("season")).toBeNull();
    }
  });

  it("no monta timeline ni card cuando todos los runs son terminales", async () => {
    useRunsHandler([RUNS_PAGE[0]]);
    mswServer.use(hitlWaitingRunStatusHandler());

    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);

    await screen.findByTestId("mock-panorama-view");
    await waitFor(() => {
      expect(runsListRequests().length).toBeGreaterThan(0);
    });
    expect(screen.queryByTestId("analysis-run-timeline")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hitl-approval-card")).not.toBeInTheDocument();
    expect(polledRunIds()).toHaveLength(0);
  });

  it("modo parent NO pide el listado de runs (endpoint coach-only)", async () => {
    useRunsHandler(RUNS_PAGE);
    mswServer.use(hitlWaitingRunStatusHandler());

    renderWithProviders(
      <AthleteAIAnalysisTab athlete={athlete} mode="parent" />,
    );

    await screen.findByTestId("mock-panorama-view");
    // Margen para que cualquier fetch tardío alcance a registrarse.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(runsListRequests()).toHaveLength(0);
    expect(polledRunIds()).toHaveLength(0);
    expect(screen.queryByTestId("analysis-run-timeline")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hitl-approval-card")).not.toBeInTheDocument();
  });

  it("el tab con un run recuperado en HITL no tiene violaciones a11y", async () => {
    useRunsHandler(RUNS_PAGE);
    mswServer.use(hitlWaitingRunStatusHandler());

    const { container } = renderWithProviders(
      <AthleteAIAnalysisTab athlete={athlete} mode="coach" />,
    );

    await screen.findByTestId("hitl-approval-card");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("conserva el borrador del hitl_request cuando el backend deja de reenviarlo", async () => {
    // Reproduce lo que pasa en producción y que `fixedRunStatusHandler`
    // esconde: el backend real sólo devuelve los eventos con `seq > since`.
    // Una vez que el cursor alcanza `last_seq`, el `hitl_request` —el único
    // evento que lleva el `draft_markdown`— no se vuelve a enviar nunca.
    // Si el consumidor no conserva su buffer acumulado, la card de
    // aprobación queda pidiéndole al coach que apruebe algo que no ve.
    useRunsHandler(RUNS_PAGE);
    mswServer.use(
      cursorAwareRunStatusHandler({
        run_id: "placeholder",
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
              step_id: "hitl-step-1",
              draft_markdown: "### Borrador\nContenido de prueba.",
            },
          },
        ],
      }),
    );

    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);

    await screen.findByTestId("hitl-approval-card");
    expect(await screen.findByText(/Contenido de prueba/)).toBeInTheDocument();

    // Tras varios polls con el cursor ya al día, el borrador debe seguir en
    // pantalla y NUNCA aparecer el texto de respaldo.
    await waitFor(
      () => {
        expect(
          polledRunIds().filter((id) => id === RECOVERED_RUN_ID).length,
        ).toBeGreaterThan(1);
      },
      { timeout: 5000 },
    );
    expect(screen.getByText(/Contenido de prueba/)).toBeInTheDocument();
    expect(
      screen.queryByText(/no incluyó el markdown en el evento/i),
    ).not.toBeInTheDocument();
  });

  it("no pierde el hitl_request cuando los eventos llegan repartidos en varios polls", async () => {
    // Regresión del reparto del stream entre observadores: el tab y
    // `AnalysisRunTimeline` observan el MISMO run con la misma queryKey, y
    // cada uno dispara su propio `refetchInterval`. Cuando el cursor y el
    // buffer vivían en refs por instancia, cada observador avanzaba su
    // propio `since` y sólo se quedaba con los eventos que le tocaron: el
    // `hitl_request` (que lleva el `draft_markdown`) caía en el buffer de
    // uno y `data.events` acababa siendo el del otro, sin él.
    //
    // Los eventos llegan de a 2 por poll para forzar la divergencia; el
    // borrador va en el ÚLTIMO, así que sólo aparece si el buffer es
    // compartido y no tiene huecos.
    const events = [
      { seq: 1, ts: "2026-08-20T10:00:01Z", type: "node_start", node: "validate_input", payload: {} },
      { seq: 2, ts: "2026-08-20T10:00:02Z", type: "node_end", node: "validate_input", payload: {} },
      { seq: 3, ts: "2026-08-20T10:00:03Z", type: "node_start", node: "analyst_agent", payload: {} },
      { seq: 4, ts: "2026-08-20T10:00:04Z", type: "node_end", node: "analyst_agent", payload: {} },
      { seq: 5, ts: "2026-08-20T10:00:05Z", type: "node_start", node: "hitl_gate_review", payload: {} },
      {
        seq: 6,
        ts: "2026-08-20T10:00:06Z",
        type: "hitl_request",
        node: "hitl_gate_review",
        payload: {
          step_id: "hitl-step-1",
          draft_markdown: "### Borrador\nContenido de prueba.",
        },
      },
    ] as never;

    useRunsHandler(RUNS_PAGE);
    mswServer.use(
      progressiveRunStatusHandler(events, {
        run_id: "placeholder",
        state: "hitl_waiting",
        progress_pct: 62,
        current_node: "hitl_gate_review",
        started_at: "2026-08-20T10:00:00Z",
        estimated_seconds_remaining: 0,
      }),
    );

    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);

    await screen.findByTestId("hitl-approval-card");
    expect(
      await screen.findByText(/Contenido de prueba/, undefined, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/no incluyó el markdown en el evento/i),
    ).not.toBeInTheDocument();
  });

  it("recupera el borrador cuando el cursor quedó pasado y el backend ya no lo reenvía", async () => {
    // Síntoma reportado: la card decía "Revisión humana requerida" y
    // mostraba el texto de respaldo en vez del borrador. El backend TENÍA
    // el `draft_markdown` en su evento `hitl_request`, pero el cliente
    // nunca lo recibió y, con el cursor `since` ya pasado, no se volvía a
    // pedir nunca. El tab detecta la incoherencia (hitl_waiting sin
    // hitl_request) y reinicia el cursor una vez.
    useRunsHandler(RUNS_PAGE);
    mswServer.use(
      staleCursorHitlHandler(
        {
          seq: 6,
          ts: "2026-08-20T10:00:06Z",
          type: "hitl_request",
          node: "hitl_gate_review",
          payload: {
            step_id: "hitl-step-1",
            draft_markdown: "### Borrador\nContenido de prueba.",
          },
        } as never,
        {
          run_id: "placeholder",
          state: "hitl_waiting",
          progress_pct: 62,
          current_node: "hitl_gate_review",
          started_at: "2026-08-20T10:00:00Z",
          estimated_seconds_remaining: 0,
        },
      ),
    );

    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);

    await screen.findByTestId("hitl-approval-card");
    expect(
      await screen.findByText(/Contenido de prueba/, undefined, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/no incluyó el markdown en el evento/i),
    ).not.toBeInTheDocument();
  });
});
