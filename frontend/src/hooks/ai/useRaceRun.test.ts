/**
 * Tests para los hooks race-analysis v2 (F6.1-6.3).
 *
 * - useStartRun: dispara POST y devuelve run_id.
 * - useRunStatus: polling, acumula eventos, se detiene en terminal.
 * - useApproveStep: POST con decision.
 *
 * Mockea `@/api/raceAnalysis` con vi.mock para evitar requests reales.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor, act } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/raceAnalysis", () => ({
  startRun: vi.fn(),
  getRunStatus: vi.fn(),
  submitHITLDecision: vi.fn(),
  // T082 (feature 036): `useRunResult` se eliminó de useRaceRun.ts (sin
  // consumidores) — este mock ya no necesita stubbear `getRunResult`.
  reExecuteRun: vi.fn(),
  cancelRun: vi.fn(),
}));

import * as raceApi from "@/api/raceAnalysis";

import {
  RUN_NOT_RESPONDING_MESSAGE,
  isTerminalState,
  useApproveStep,
  useRunStatus,
  useStartRun,
} from "./useRaceRun";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("isTerminalState", () => {
  it("detecta estados terminales", () => {
    expect(isTerminalState("done")).toBe(true);
    expect(isTerminalState("failed")).toBe(true);
    expect(isTerminalState("cancelled")).toBe(true);
    expect(isTerminalState("error")).toBe(true);
  });
  it("detecta estados activos", () => {
    expect(isTerminalState("running")).toBe(false);
    expect(isTerminalState("hitl_waiting")).toBe(false);
    expect(isTerminalState(undefined)).toBe(false);
    expect(isTerminalState(null)).toBe(false);
  });
});

describe("useStartRun", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POST /runs y devuelve run_id", async () => {
    vi.mocked(raceApi.startRun).mockResolvedValue({
      run_id: "abc123",
      status: "running",
      started_at: "2026-05-20T10:00:00Z",
      status_url: "/api/race-analysis/runs/abc123/status",
      estimated_seconds: 25,
    });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useStartRun(), { wrapper });

    let mutateResult: { run_id: string } | undefined;
    await act(async () => {
      mutateResult = await result.current.mutateAsync({
        athlete_id: 1,
        season: 2026,
        valida_nums: [1, 2],
      });
    });

    expect(raceApi.startRun).toHaveBeenCalledWith({
      athlete_id: 1,
      season: 2026,
      valida_nums: [1, 2],
    });
    // mutateAsync resolve devuelve los datos directamente.
    expect(mutateResult?.run_id).toBe("abc123");
    await waitFor(() => expect(result.current.data?.run_id).toBe("abc123"));
  });

  it("propaga errores del backend", async () => {
    vi.mocked(raceApi.startRun).mockRejectedValue(
      new Error("503 AI disabled"),
    );
    const wrapper = createWrapper();
    const { result } = renderHook(() => useStartRun(), { wrapper });

    await expect(
      act(async () => {
        await result.current.mutateAsync({
          athlete_id: 1,
          season: 2026,
        });
      }),
    ).rejects.toThrow();
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useRunStatus", () => {
  beforeEach(() => vi.clearAllMocks());

  it("hace primer fetch y devuelve evento accumulado", async () => {
    vi.mocked(raceApi.getRunStatus).mockResolvedValueOnce({
      run_id: "r1",
      state: "running",
      progress_pct: 25,
      current_node: "anonymize",
      started_at: "2026-05-20T10:00:00Z",
      estimated_seconds_remaining: 20,
      last_seq: 2,
      new_events: [
        {
          seq: 1,
          ts: "2026-05-20T10:00:01Z",
          type: "node_start",
          node: "validate_input",
          payload: {},
        },
        {
          seq: 2,
          ts: "2026-05-20T10:00:02Z",
          type: "node_end",
          node: "validate_input",
          payload: {},
        },
      ],
    });

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useRunStatus("r1", { pollIntervalMs: 100000 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.events).toHaveLength(2);
    expect(result.current.data?.latest.state).toBe("running");
  });

  it("se detiene cuando state es terminal", async () => {
    vi.mocked(raceApi.getRunStatus).mockResolvedValueOnce({
      run_id: "r2",
      state: "done",
      progress_pct: 100,
      current_node: null,
      started_at: "2026-05-20T10:00:00Z",
      estimated_seconds_remaining: 0,
      last_seq: 5,
      new_events: [],
    });

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useRunStatus("r2", { pollIntervalMs: 50 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.latest.state).toBe("done");

    // Espera para asegurar que no hay re-pollings (mock fue llamado 1 vez).
    await new Promise((r) => setTimeout(r, 250));
    expect(raceApi.getRunStatus).toHaveBeenCalledTimes(1);
  });

  it("no se dispara cuando runId es null", () => {
    const wrapper = createWrapper();
    renderHook(() => useRunStatus(null), { wrapper });
    expect(raceApi.getRunStatus).not.toHaveBeenCalled();
  });

  it("respeta enabled=false", () => {
    const wrapper = createWrapper();
    renderHook(() => useRunStatus("r3", { enabled: false }), { wrapper });
    expect(raceApi.getRunStatus).not.toHaveBeenCalled();
  });
});

describe("useApproveStep", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POST decision approve y propaga response", async () => {
    vi.mocked(raceApi.submitHITLDecision).mockResolvedValue({
      accepted: true,
      run_id: "r1",
      step_id: "hitl_review_1",
      next_state: "running",
    });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useApproveStep("r1"), { wrapper });

    let res: { accepted: boolean } | undefined;
    await act(async () => {
      res = await result.current.mutateAsync({
        stepId: "hitl_review_1",
        decision: { decision: "approve" },
      });
    });

    expect(raceApi.submitHITLDecision).toHaveBeenCalledWith(
      "r1",
      "hitl_review_1",
      { decision: "approve" },
    );
    expect(res?.accepted).toBe(true);
    await waitFor(() => expect(result.current.data?.accepted).toBe(true));
  });

  it("propaga errores HTTP", async () => {
    vi.mocked(raceApi.submitHITLDecision).mockRejectedValue(
      new Error("409 Conflict"),
    );

    const wrapper = createWrapper();
    const { result } = renderHook(() => useApproveStep("r1"), { wrapper });

    await expect(
      act(async () => {
        await result.current.mutateAsync({
          stepId: "x",
          decision: { decision: "reject" },
        });
      }),
    ).rejects.toThrow();
  });

  // T042 (feature 036, US5): antes de este fix, onSuccess invalidaba con
  // un predicate ad-hoc `startsWith("athlete-")` — matcheaba de rebote
  // `athlete-activities`/`athlete-newsletter(s)` y NUNCA invalidaba
  // `club-insights-by-race` ni `season-panorama`. Revertir el fix (volver
  // a llamar `queryClient.invalidateQueries` con ese predicate inline en
  // vez de `invalidateAthleteAiQueries`) hace fallar este test.
  it("T042 — onSuccess delega en invalidateAthleteAiQueries: invalida club-insights-by-race, season-panorama y claves de CUALQUIER atleta, pero no Strava/boletín", async () => {
    vi.mocked(raceApi.submitHITLDecision).mockResolvedValue({
      accepted: true,
      run_id: "r1",
      step_id: "s1",
      next_state: "running",
    });

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
        mutations: { retry: false },
      },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children);

    const { result } = renderHook(() => useApproveStep("r1"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        stepId: "s1",
        decision: { decision: "approve" },
      });
    });

    // Dos invalidaciones ocurren en onSuccess: la del status del propio
    // run (queryKey directa) y la del helper compartido (con predicate).
    // Tomamos la que trae un predicate.
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

    expect(predicate({ queryKey: ["club-insights-by-race", 5] })).toBe(true);
    expect(predicate({ queryKey: ["season-panorama", 2026, 1] })).toBe(true);
    // Sin athleteId conocido: cualquier atleta matchea.
    expect(predicate({ queryKey: ["athlete-insights", 999, {}] })).toBe(true);
    // Dominios sin relación con un run de IA — no deben invalidarse.
    expect(predicate({ queryKey: ["athlete-activities", 42] })).toBe(false);
    expect(predicate({ queryKey: ["athlete-newsletters", 1, 42] })).toBe(
      false,
    );
  });
});

// ---------------------------------------------------------------------------
// T017/T018 — techo duro de polling
//
// El techo se mide con un reloj LOCAL a este hook (cuánto lleva
// pollingueando SIN llegar a un estado terminal), no contra el
// `started_at` que manda el servidor — por eso los fixtures de estas
// pruebas usan fechas fijas de sobra (mismo estilo que el resto del
// archivo) sin que afecten el resultado.
//
// Los fixtures de este bloque usan `running`: es el único estado al que
// el techo aplica. `hitl_waiting` está exceptuado (un run pausado espera
// al coach por diseño) y tiene su propio bloque más abajo.
// ---------------------------------------------------------------------------

describe("useRunStatus — T017 techo duro de polling", () => {
  beforeEach(() => vi.clearAllMocks());

  it(
    "si el run no llega a un estado terminal dentro de maxPollingMs, la " +
      "query pasa a error con RUN_NOT_RESPONDING_MESSAGE y deja de pollear",
    async () => {
      vi.mocked(raceApi.getRunStatus).mockResolvedValue({
        run_id: "stuck-1",
        state: "running",
        progress_pct: 70,
        current_node: "analyst_agent",
        started_at: "2026-05-20T10:00:00Z",
        estimated_seconds_remaining: 0,
        last_seq: 1,
        new_events: [],
      });

      const wrapper = createWrapper();
      const { result } = renderHook(
        () => useRunStatus("stuck-1", { pollIntervalMs: 20, maxPollingMs: 80 }),
        { wrapper },
      );

      await waitFor(() => expect(result.current.isError).toBe(true), {
        timeout: 3000,
      });
      expect(result.current.error).toBeInstanceOf(Error);
      expect((result.current.error as Error).message).toBe(
        RUN_NOT_RESPONDING_MESSAGE,
      );

      // El polling se detiene de verdad (refetchInterval → false): no debe
      // haber más llamadas a getRunStatus pasado un rato.
      const callsAtError = vi.mocked(raceApi.getRunStatus).mock.calls.length;
      await new Promise((resolve) => setTimeout(resolve, 200));
      expect(vi.mocked(raceApi.getRunStatus).mock.calls.length).toBe(
        callsAtError,
      );
    },
  );

  it("mientras esté dentro del techo, sigue pollingueando con normalidad", async () => {
    vi.mocked(raceApi.getRunStatus).mockResolvedValue({
      run_id: "fresh-1",
      state: "running",
      progress_pct: 10,
      current_node: "analyst_agent",
      started_at: "2026-05-20T10:00:00Z",
      estimated_seconds_remaining: 20,
      last_seq: 0,
      new_events: [],
    });

    const wrapper = createWrapper();
    const { result } = renderHook(
      () =>
        useRunStatus("fresh-1", { pollIntervalMs: 100000, maxPollingMs: 10_000 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.isError).toBe(false);
    expect(result.current.data?.latest.state).toBe("running");
  });

  it(
    "un run que sí llega a estado terminal después de acercarse al techo " +
      "no se marca como 'no responde'",
    async () => {
      const runningFixture = {
        run_id: "slow-1",
        state: "running" as const,
        progress_pct: 60,
        current_node: "analyst_agent",
        started_at: "2026-05-20T10:00:00Z",
        estimated_seconds_remaining: 5,
        new_events: [],
      };
      vi.mocked(raceApi.getRunStatus)
        .mockResolvedValueOnce({ ...runningFixture, last_seq: 1 })
        .mockResolvedValueOnce({ ...runningFixture, last_seq: 2 })
        .mockResolvedValueOnce({ ...runningFixture, last_seq: 3 })
        .mockResolvedValue({
          ...runningFixture,
          state: "done",
          progress_pct: 100,
          estimated_seconds_remaining: 0,
          last_seq: 4,
        });

      const wrapper = createWrapper();
      const { result } = renderHook(
        () => useRunStatus("slow-1", { pollIntervalMs: 20, maxPollingMs: 50 }),
        { wrapper },
      );

      await waitFor(
        () => expect(result.current.data?.latest.state).toBe("done"),
        { timeout: 3000 },
      );
      expect(result.current.isError).toBe(false);
    },
  );

  it(
    "el techo también se detecta en la rama 304 (run huérfano que dejó de " +
      "emitir eventos nuevos)",
    async () => {
      vi.mocked(raceApi.getRunStatus)
        .mockResolvedValueOnce({
          run_id: "orphan-304",
          state: "running",
          progress_pct: 70,
          current_node: "analyst_agent",
          started_at: "2026-05-20T10:00:00Z",
          estimated_seconds_remaining: 0,
          last_seq: 1,
          new_events: [],
        })
        // 304 para siempre — igual que un run huérfano cuyo backend nunca
        // vuelve a mover last_seq.
        .mockResolvedValue(null);

      const wrapper = createWrapper();
      const { result } = renderHook(
        () =>
          useRunStatus("orphan-304", { pollIntervalMs: 20, maxPollingMs: 80 }),
        { wrapper },
      );

      await waitFor(() => expect(result.current.isError).toBe(true), {
        timeout: 3000,
      });
      expect((result.current.error as Error).message).toBe(
        RUN_NOT_RESPONDING_MESSAGE,
      );
    },
  );
});

// ---------------------------------------------------------------------------
// P0 — el techo de polling NO aplica a un run pausado en `hitl_waiting`.
//
// Un run detenido en un gate HITL espera al coach por diseño: no emite
// eventos y el backend responde 304 mientras nadie decida. Antes de este
// fix, al cruzar el techo la query pasaba a error con
// RUN_NOT_RESPONDING_MESSAGE ("Vuelve a lanzarlo"), lo que borraba de
// pantalla la card de aprobación y dejaba al coach con una instrucción
// imposible: el guard 409 del backend rechaza relanzar mientras ese run
// siga vivo.
//
// Estas pruebas usan timers falsos para cruzar los 15 minutos reales del
// techo por defecto (`DEFAULT_MAX_POLLING_MS`) sin overrides, y avanzan
// el reloj con `advanceTimersByTimeAsync` dentro de `act` (no con
// `waitFor`, que no coopera bien con timers falsos).
// ---------------------------------------------------------------------------

describe("useRunStatus — P0 excepción HITL al techo de polling", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.useRealTimers());

  const hitlWaitingFixture = {
    run_id: "hitl-paused",
    state: "hitl_waiting" as const,
    progress_pct: 70,
    current_node: "hitl_gate_review",
    started_at: "2026-05-20T10:00:00Z",
    estimated_seconds_remaining: 0,
    last_seq: 1,
    new_events: [
      {
        seq: 1,
        ts: "2026-05-20T10:00:30Z",
        type: "hitl_request",
        node: "hitl_gate_review",
        payload: { step_id: "hitl-step-1" },
      },
    ],
  };

  it(
    "(a) run en hitl_waiting con 304 sostenido más de 15 min: la query NO " +
      "entra en error y el estado sigue siendo hitl_waiting",
    async () => {
      vi.useFakeTimers();
      vi.mocked(raceApi.getRunStatus)
        .mockResolvedValueOnce(hitlWaitingFixture)
        // 304 para siempre: el coach todavía no decide.
        .mockResolvedValue(null);

      const wrapper = createWrapper();
      const { result } = renderHook(() => useRunStatus("hitl-paused"), {
        wrapper,
      });

      // Primer poll (fuera de timer: se dispara al montar).
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10);
      });
      expect(result.current.data?.latest.state).toBe("hitl_waiting");

      // Cruza con holgura el techo por defecto (15 min).
      await act(async () => {
        await vi.advanceTimersByTimeAsync(16 * 60 * 1000);
      });

      expect(result.current.isError).toBe(false);
      expect(result.current.error).toBeNull();
      expect(result.current.data?.latest.state).toBe("hitl_waiting");
      // El evento hitl_request acumulado sigue disponible: es lo que
      // alimenta la card de aprobación del coach.
      expect(result.current.data?.events).toHaveLength(1);

      // Sigue escuchando, pero a ritmo lento (~15 s, no ~2 s): en 60 s
      // más deben caber unas pocas llamadas, no treinta.
      const callsAfterCeiling = vi.mocked(raceApi.getRunStatus).mock.calls
        .length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60 * 1000);
      });
      const delta =
        vi.mocked(raceApi.getRunStatus).mock.calls.length - callsAfterCeiling;
      expect(delta).toBeGreaterThanOrEqual(1);
      expect(delta).toBeLessThanOrEqual(6);
    },
  );

  it(
    "(b) contraste — run en running con 304 sostenido más de 15 min: sigue " +
      "lanzando RUN_NOT_RESPONDING_MESSAGE",
    async () => {
      vi.useFakeTimers();
      vi.mocked(raceApi.getRunStatus)
        .mockResolvedValueOnce({
          ...hitlWaitingFixture,
          run_id: "orphan-running",
          state: "running" as const,
          current_node: "analyst_agent",
          new_events: [],
        })
        .mockResolvedValue(null);

      const wrapper = createWrapper();
      const { result } = renderHook(() => useRunStatus("orphan-running"), {
        wrapper,
      });

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10);
      });
      expect(result.current.data?.latest.state).toBe("running");

      await act(async () => {
        await vi.advanceTimersByTimeAsync(16 * 60 * 1000);
      });

      expect(result.current.isError).toBe(true);
      expect((result.current.error as Error).message).toBe(
        RUN_NOT_RESPONDING_MESSAGE,
      );

      // Y el polling se detiene de verdad.
      const callsAtError = vi.mocked(raceApi.getRunStatus).mock.calls.length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60 * 1000);
      });
      expect(vi.mocked(raceApi.getRunStatus).mock.calls.length).toBe(
        callsAtError,
      );
    },
  );
});

// ---------------------------------------------------------------------------
// T078 (feature 036, US7) — tres ramas de useRunStatus sin cobertura:
// 304-Not-Modified (caso normal, sin techo alcanzado), dedupe de eventos
// por `seq`, y `resetEvents`.
// ---------------------------------------------------------------------------

describe("useRunStatus — T078 rama 304 Not-Modified", () => {
  beforeEach(() => vi.clearAllMocks());

  it("con dato previo y sin alcanzar el techo, reutiliza el snapshot acumulado sin error ni cambios", async () => {
    vi.mocked(raceApi.getRunStatus)
      .mockResolvedValueOnce({
        run_id: "r304",
        state: "running",
        progress_pct: 40,
        current_node: "critic_agent",
        started_at: "2026-05-20T10:00:00Z",
        estimated_seconds_remaining: 15,
        last_seq: 3,
        new_events: [
          { seq: 1, ts: "t1", type: "node_start", node: "x", payload: {} },
          { seq: 2, ts: "t2", type: "node_end", node: "x", payload: {} },
          { seq: 3, ts: "t3", type: "node_start", node: "y", payload: {} },
        ],
      })
      // Segundo (y siguientes) poll(s): 304 — sin cambios en el servidor.
      .mockResolvedValue(null);

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useRunStatus("r304", { pollIntervalMs: 30, maxPollingMs: 10_000 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.data?.events).toHaveLength(3));

    // Deja correr al menos un poll más (304) y confirma que el snapshot
    // acumulado no se pierde ni se vacía, y que la query no entra en error.
    await waitFor(() =>
      expect(vi.mocked(raceApi.getRunStatus).mock.calls.length).toBeGreaterThanOrEqual(2),
    );
    expect(result.current.isError).toBe(false);
    expect(result.current.data?.events).toHaveLength(3);
    expect(result.current.data?.latest.last_seq).toBe(3);
    expect(result.current.data?.latest.state).toBe("running");
  });

  it("en el primer poll, sin dato previo en cache, sintetiza un snapshot placeholder 'running' vacío", async () => {
    vi.mocked(raceApi.getRunStatus).mockResolvedValue(null);

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useRunStatus("r304-first", { pollIntervalMs: 100000 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.isError).toBe(false);
    expect(result.current.data?.latest.run_id).toBe("r304-first");
    expect(result.current.data?.latest.state).toBe("running");
    expect(result.current.data?.events).toEqual([]);
  });
});

describe("useRunStatus — T078 dedupe de eventos por seq", () => {
  beforeEach(() => vi.clearAllMocks());

  it("no duplica un evento cuyo seq ya fue visto en un poll anterior, y preserva el orden", async () => {
    vi.mocked(raceApi.getRunStatus)
      .mockResolvedValueOnce({
        run_id: "r-dedupe",
        state: "running",
        progress_pct: 30,
        current_node: "a",
        started_at: "2026-05-20T10:00:00Z",
        estimated_seconds_remaining: 20,
        last_seq: 2,
        new_events: [
          { seq: 1, ts: "t1", type: "node_start", node: "a", payload: {} },
          { seq: 2, ts: "t2-original", type: "node_end", node: "a", payload: {} },
        ],
      })
      // El backend repite defensivamente seq=2 (ya visto) y agrega seq=3.
      .mockResolvedValueOnce({
        run_id: "r-dedupe",
        state: "running",
        progress_pct: 60,
        current_node: "b",
        started_at: "2026-05-20T10:00:00Z",
        estimated_seconds_remaining: 10,
        last_seq: 3,
        new_events: [
          { seq: 2, ts: "t2-repetido", type: "node_end", node: "a", payload: {} },
          { seq: 3, ts: "t3", type: "node_start", node: "b", payload: {} },
        ],
      })
      .mockResolvedValue(null);

    const wrapper = createWrapper();
    const { result } = renderHook(
      () =>
        useRunStatus("r-dedupe", { pollIntervalMs: 30, maxPollingMs: 10_000 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.data?.latest.last_seq).toBe(3));

    // 3 eventos únicos (seq 1,2,3) — NO 4, aunque seq=2 llegó dos veces.
    const events = result.current.data?.events ?? [];
    expect(events).toHaveLength(3);
    expect(events.map((e) => e.seq)).toEqual([1, 2, 3]);
    // El evento seq=2 conserva el payload de la PRIMERA vez que se vio: la
    // repetición defensiva del segundo poll no lo sobreescribe.
    expect(events.find((e) => e.seq === 2)?.ts).toBe("t2-original");
  });
});

describe("useRunStatus — T078 resetEvents", () => {
  beforeEach(() => vi.clearAllMocks());

  it("limpia el buffer de eventos acumulados y reinicia el cursor `since` a 0", async () => {
    vi.mocked(raceApi.getRunStatus)
      .mockResolvedValueOnce({
        run_id: "r-reset",
        state: "running",
        progress_pct: 40,
        current_node: "a",
        started_at: "2026-05-20T10:00:00Z",
        estimated_seconds_remaining: 20,
        last_seq: 2,
        new_events: [
          { seq: 1, ts: "t1", type: "node_start", node: "a", payload: {} },
          { seq: 2, ts: "t2", type: "node_end", node: "a", payload: {} },
        ],
      })
      .mockResolvedValueOnce({
        run_id: "r-reset",
        state: "running",
        progress_pct: 45,
        current_node: "a",
        started_at: "2026-05-20T10:00:00Z",
        estimated_seconds_remaining: 15,
        last_seq: 9,
        new_events: [
          { seq: 9, ts: "t9", type: "node_start", node: "b", payload: {} },
        ],
      });

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useRunStatus("r-reset", { pollIntervalMs: 100000 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.data?.events).toHaveLength(2));

    act(() => {
      result.current.resetEvents();
    });

    // Forzamos el siguiente poll manualmente (pollIntervalMs es gigante a
    // propósito para que el único refetch posible sea este).
    await act(async () => {
      await result.current.refetch();
    });

    await waitFor(() => expect(result.current.data?.latest.last_seq).toBe(9));

    // El buffer se limpió de verdad: si no se hubiera limpiado, el segundo
    // poll habría acumulado 3 eventos (los 2 viejos + el nuevo), no 1.
    const events = result.current.data?.events ?? [];
    expect(events).toHaveLength(1);
    expect(events[0].seq).toBe(9);

    // El cursor `since` enviado en el segundo fetch fue 0 (reset), no 2.
    expect(raceApi.getRunStatus).toHaveBeenNthCalledWith(
      2,
      "r-reset",
      0,
      expect.anything(),
    );
  });
});
