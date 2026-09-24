/**
 * Tests — PendingAnalysesPanel (feature 045, US5, T057).
 *
 * Cubre: estados (cargando / error + reintentar / vacío / lista), enlaces
 * profundos al análisis, RBAC de la acción de abrir (admin no), «Re-ejecutar»
 * (body con temporada derivada del evento + event_id, presupuesto agotado;
 * resúmenes de temporada → `POST …/season-summary` con su `season`),
 * «Descartar aviso» (confirmación, refresco, 409), cambio de modo, objetivos
 * táctiles y jest-axe. Los nombres son ficticios (Ley 1581).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

import { mswServer } from "@/test/setup";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { makeRaceEventRead } from "@/test/msw/raceEventsHandlers";
import {
  defaultPendingByState,
  dismissStaleConflictHandler,
  makePendingAnalysis,
  makeSeasonSummaryPending,
  pendingAnalysesEmptyHandler,
  pendingAnalysesErrorHandler,
  pendingAnalysesHandlers,
} from "@/test/msw/racePendingAnalysesHandlers";
import type { AIStatusResponse } from "@/types/ai.types";
import type { PendingAnalysis } from "@/types/racePendingAnalyses.types";

const mockAuth: { accessToken: string; user: { id: number; role: string } } = {
  accessToken: "test-token",
  user: { id: 1, role: "coach" },
};
vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((selector: (s: unknown) => unknown) => selector(mockAuth)),
}));

let mockAIStatusData: AIStatusResponse | undefined;
vi.mock("@/hooks/ai/useAIStatus", () => ({
  useAIStatus: () => ({ data: mockAIStatusData, isError: false }),
}));

let mockRunFailure: string | null = null;
vi.mock("@/hooks/ai/useAthleteRunOutcome", () => ({
  useAthleteRunOutcome: () => ({ failureMessage: mockRunFailure }),
}));

import {
  PendingAnalysesPanel,
  parsePendingAnalysesMode,
  type PendingAnalysesMode,
} from "@/components/competitions/season/PendingAnalysesPanel";

// Fecha del evento en un año DISTINTO de `season` del fixture (2026): así los
// tests prueban que «Re-ejecutar» usa la temporada del ítem y no el año de la fecha.
const EVENT_DATE = "2025-12-30";
const eventRequests = vi.fn();

beforeEach(() => {
  mockAuth.user.role = "coach";
  mockAIStatusData = undefined;
  mockRunFailure = null;
  eventRequests.mockClear();
  mswServer.use(
    ...pendingAnalysesHandlers,
    http.get("*/api/race-analysis/race-events/:id", ({ params }) => {
      eventRequests(Number(params.id));
      return HttpResponse.json(
        makeRaceEventRead({ id: Number(params.id), event_date: EVENT_DATE }),
      );
    }),
  );
});

function renderPanel(
  mode: PendingAnalysesMode = "desactualizados",
  handlers: { onModeChange?: (m: PendingAnalysesMode) => void; onClose?: () => void } = {},
) {
  return renderWithProviders(
    <PendingAnalysesPanel
      mode={mode}
      onModeChange={handlers.onModeChange ?? vi.fn()}
      onClose={handlers.onClose ?? vi.fn()}
    />,
  );
}

describe("parsePendingAnalysesMode", () => {
  it("reconoce los dos valores del contrato y trata cualquier otro como panel cerrado", () => {
    expect(parsePendingAnalysesMode("por-aprobar")).toBe("por-aprobar");
    expect(parsePendingAnalysesMode("desactualizados")).toBe("desactualizados");
    expect(parsePendingAnalysesMode("otro")).toBeNull();
    expect(parsePendingAnalysesMode(null)).toBeNull();
  });
});

describe("PendingAnalysesPanel — estados", () => {
  it("muestra un esqueleto accesible mientras carga", () => {
    renderPanel();
    expect(screen.getByTestId("pending-analyses-loading")).toHaveAttribute("aria-busy", "true");
  });

  it("lista los análisis del estado pedido, con nombre, competencia y fecha", async () => {
    renderPanel("desactualizados");

    const list = await screen.findByTestId("pending-analyses-list");
    expect(within(list).getAllByRole("listitem")).toHaveLength(defaultPendingByState.stale.length);
    expect(within(list).getByText("Ana Ficticia")).toBeInTheDocument();
    expect(within(list).getAllByText(/Copa Valle IV — Cali/)).toHaveLength(2);
    expect(within(list).getAllByText(/Actualizado/).length).toBeGreaterThan(0);
  });

  it("vacío: mensaje propio de cada modo", async () => {
    mswServer.use(pendingAnalysesEmptyHandler);
    const { unmount } = renderPanel("por-aprobar");
    expect(await screen.findByTestId("pending-analyses-empty")).toHaveTextContent(
      "No hay análisis por aprobar.",
    );
    unmount();

    renderPanel("desactualizados");
    expect(await screen.findByTestId("pending-analyses-empty")).toHaveTextContent(
      "No hay análisis desactualizados.",
    );
  });

  it("error: alerta con Reintentar, que vuelve a consultar y muestra la lista", async () => {
    const user = userEvent.setup();
    mswServer.use(pendingAnalysesErrorHandler);
    renderPanel("desactualizados");

    expect(await screen.findByTestId("pending-analyses-error")).toHaveTextContent(
      "No se pudieron cargar los análisis pendientes",
    );

    mswServer.use(...pendingAnalysesHandlers);
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByTestId("pending-analyses-list")).toBeInTheDocument();
    expect(screen.queryByTestId("pending-analyses-error")).not.toBeInTheDocument();
  });
});

describe("PendingAnalysesPanel — abrir el análisis", () => {
  it("por aprobar: «Revisar y aprobar» abre la vista de análisis sin insight (aún no existe)", async () => {
    renderPanel("por-aprobar");

    const link = await screen.findByRole("link", { name: "Revisar el análisis de Beto Imaginario" });
    expect(link).toHaveAttribute("href", "/athletes/145?tab=races&view=analisis");
    expect(link).toHaveTextContent("Revisar y aprobar");
  });

  it("desactualizados: «Abrir análisis» abre ese insight en Carreras › Análisis IA", async () => {
    renderPanel("desactualizados");

    const link = await screen.findByRole("link", { name: "Abrir el análisis de Ana Ficticia" });
    expect(link).toHaveAttribute("href", "/athletes/144?tab=races&view=analisis&insight=501");
  });

  it("admin no ve la acción de abrir (/athletes/:id es coach-only) pero conserva el resto", async () => {
    mockAuth.user.role = "admin";
    renderPanel("desactualizados");

    await screen.findByTestId("pending-analyses-list");
    expect(screen.queryByRole("link", { name: /Abrir el análisis/ })).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Descartar el aviso de análisis desactualizado de Ana Ficticia/ }),
    ).toBeInTheDocument();
  });

  it("solo los desactualizados ofrecen re-ejecutar y descartar", async () => {
    const { unmount } = renderPanel("por-aprobar");
    await screen.findByTestId("pending-analyses-list");
    expect(screen.queryByRole("button", { name: /Re-ejecutar/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Descartar el aviso/ })).not.toBeInTheDocument();
    unmount();

    renderPanel("desactualizados");
    await screen.findByTestId("pending-analyses-list");
    expect(screen.getAllByRole("button", { name: /Re-ejecutar el análisis de/ })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: /Descartar el aviso/ })).toHaveLength(2);
  });

  it("un desactualizado sin competencia ni tipo conocido no se puede re-ejecutar: solo abrir y descartar", async () => {
    const unknown: PendingAnalysis = makePendingAnalysis({
      run_id: "run-stale-unknown",
      event_id: null,
      event_label: "Temporada 2026",
      kind: null,
    });
    mswServer.use(http.get("*/api/race-analysis/pending-analyses", () => HttpResponse.json([unknown])));
    renderPanel("desactualizados");

    await screen.findByTestId("pending-analyses-list");
    expect(screen.queryByRole("button", { name: /Re-ejecutar/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Abrir el análisis de/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Descartar el aviso/ })).toBeInTheDocument();
  });

  it("un backend previo a `kind` (campo ausente) conserva el comportamiento por competencia", async () => {
    const legacy = makePendingAnalysis();
    delete legacy.kind;
    mswServer.use(http.get("*/api/race-analysis/pending-analyses", () => HttpResponse.json([legacy])));
    renderPanel("desactualizados");

    expect(
      await screen.findByRole("button", { name: "Re-ejecutar el análisis de Ana Ficticia" }),
    ).toBeInTheDocument();
  });

  it("un resumen de temporada desactualizado ofrece re-ejecutar el resumen (no el análisis por válida)", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/pending-analyses", () =>
        HttpResponse.json([makeSeasonSummaryPending()]),
      ),
    );
    renderPanel("desactualizados");

    await screen.findByTestId("pending-analyses-list");
    expect(
      screen.getByRole("button", { name: "Re-ejecutar el resumen de temporada de Eli Simulada" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Re-ejecutar el análisis de/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Descartar el aviso/ })).toBeInTheDocument();
  });

  it("un resumen de temporada sin `season` conocida no ofrece re-ejecutar (no se adivina la temporada)", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/pending-analyses", () =>
        HttpResponse.json([makeSeasonSummaryPending({ season: null })]),
      ),
    );
    renderPanel("desactualizados");

    await screen.findByTestId("pending-analyses-list");
    expect(screen.queryByRole("button", { name: /Re-ejecutar/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Descartar el aviso/ })).toBeInTheDocument();
  });

  it("por aprobar nunca ofrece re-ejecutar, ni siquiera para un resumen de temporada", async () => {
    renderPanel("por-aprobar");

    await screen.findByTestId("pending-analyses-list");
    expect(screen.getByText("Cami Supuesta")).toBeInTheDocument(); // kind=season_summary
    expect(screen.queryByRole("button", { name: /Re-ejecutar/ })).not.toBeInTheDocument();
  });
});

describe("PendingAnalysesPanel — descartar aviso", () => {
  it("pide confirmación, llama al endpoint con el run y la fila sale de la lista", async () => {
    const user = userEvent.setup();
    let remaining = [...defaultPendingByState.stale];
    const dismissed: string[] = [];
    mswServer.use(
      http.get("*/api/race-analysis/pending-analyses", () => HttpResponse.json(remaining)),
      http.post("*/api/race-analysis/runs/:runId/dismiss-stale", ({ params }) => {
        dismissed.push(String(params.runId));
        remaining = remaining.filter((i) => i.run_id !== params.runId);
        return HttpResponse.json({ run_id: String(params.runId), stale: false });
      }),
    );
    renderPanel("desactualizados");

    await user.click(
      await screen.findByRole("button", {
        name: "Descartar el aviso de análisis desactualizado de Ana Ficticia",
      }),
    );
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("El análisis se conserva tal como está");
    expect(dismissed).toEqual([]); // nada hasta confirmar

    await user.click(within(dialog).getByRole("button", { name: "Descartar aviso" }));

    await waitFor(() => expect(dismissed).toEqual(["run-stale-001"]));
    await waitFor(() =>
      expect(screen.queryByTestId("pending-analysis-run-stale-001")).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId("pending-analysis-run-stale-002")).toBeInTheDocument();
  });

  it("cancelar no llama al endpoint", async () => {
    const user = userEvent.setup();
    const calls = vi.fn();
    mswServer.use(
      http.post("*/api/race-analysis/runs/:runId/dismiss-stale", () => {
        calls();
        return HttpResponse.json({ run_id: "x", stale: false });
      }),
    );
    renderPanel("desactualizados");

    await user.click(
      await screen.findByRole("button", { name: /Descartar el aviso.*Ana Ficticia/ }),
    );
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Cancelar" }));

    expect(calls).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("409: informa que ya no está desactualizado, sin cerrar el diálogo", async () => {
    const user = userEvent.setup();
    mswServer.use(dismissStaleConflictHandler);
    renderPanel("desactualizados");

    await user.click(
      await screen.findByRole("button", { name: /Descartar el aviso.*Ana Ficticia/ }),
    );
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Descartar aviso" }));

    expect(await within(dialog).findByText("Este análisis ya no está desactualizado.")).toBeInTheDocument();
  });
});

describe("PendingAnalysesPanel — re-ejecutar", () => {
  it("lanza con la temporada del ítem y event_id como ancla, sin consultar el evento, y confirma «Análisis iniciado»", async () => {
    const user = userEvent.setup();
    let body: unknown = null;
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/runs", async ({ request, params }) => {
        body = { athleteId: params.athleteId, ...((await request.json()) as object) };
        return HttpResponse.json(
          {
            run_id: "run-new-777",
            status: "running",
            started_at: "2026-09-23T10:00:00Z",
            status_url: "/api/race-analysis/runs/run-new-777/status",
            estimated_seconds: 45,
          },
          { status: 201 },
        );
      }),
    );
    renderPanel("desactualizados");

    const button = await screen.findByRole("button", { name: "Re-ejecutar el análisis de Ana Ficticia" });
    expect(button).toBeEnabled(); // la temporada ya viene en el ítem
    await user.click(button);

    expect(await screen.findByTestId("pending-rerun-started-144")).toHaveTextContent("Análisis iniciado");
    // season 2026 del ítem (la fecha del evento es de 2025): no se deriva del evento.
    expect(body).toEqual({ athleteId: "144", season: 2026, event_id: 7 });
    expect(eventRequests).not.toHaveBeenCalled();
  });

  it("respaldo: si el ítem no trae season (null), la deriva del año de la fecha del evento", async () => {
    const user = userEvent.setup();
    let body: unknown = null;
    mswServer.use(
      http.get("*/api/race-analysis/pending-analyses", () =>
        HttpResponse.json([makePendingAnalysis({ season: null })]),
      ),
      http.post("*/api/athletes/:athleteId/race-analysis/runs", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          {
            run_id: "run-new-778",
            status: "running",
            started_at: "2026-09-23T10:00:00Z",
            status_url: "/api/race-analysis/runs/run-new-778/status",
            estimated_seconds: 45,
          },
          { status: 201 },
        );
      }),
    );
    renderPanel("desactualizados");

    const button = await screen.findByRole("button", { name: "Re-ejecutar el análisis de Ana Ficticia" });
    // Deshabilitado hasta conocer la temporada (evento por resolver).
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);

    expect(await screen.findByTestId("pending-rerun-started-144")).toBeInTheDocument();
    expect(body).toEqual({ season: 2025, event_id: 7 });
    expect(eventRequests).toHaveBeenCalledWith(7);
  });

  it("con el presupuesto de IA agotado el botón queda deshabilitado", async () => {
    mockAIStatusData = { budget_status: "exhausted" } as AIStatusResponse;
    renderPanel("desactualizados");

    const buttons = await screen.findAllByRole("button", { name: /No se puede re-ejecutar el análisis de/ });
    for (const button of buttons) expect(button).toBeDisabled();
    expect(screen.getByTestId("ai-budget-hint-exhausted")).toBeInTheDocument();
  });

  it("un rechazo del backend (429) se muestra inline, no como un falso «iniciado»", async () => {
    const user = userEvent.setup();
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/runs", () =>
        HttpResponse.json({ detail: "límite" }, { status: 429 }),
      ),
    );
    renderPanel("desactualizados");

    const button = await screen.findByRole("button", { name: "Re-ejecutar el análisis de Ana Ficticia" });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);

    expect(await screen.findByTestId("pending-rerun-error-144")).toHaveTextContent(
      "Límite de análisis simultáneos alcanzado",
    );
    expect(screen.queryByTestId("pending-rerun-started-144")).not.toBeInTheDocument();
  });

  it("si el run termina en fallo, el estado optimista se reemplaza por el error", async () => {
    const user = userEvent.setup();
    renderPanel("desactualizados");

    const button = await screen.findByRole("button", { name: "Re-ejecutar el análisis de Ana Ficticia" });
    await waitFor(() => expect(button).toBeEnabled());
    mockRunFailure = "El análisis de Ana Ficticia falló. Intenta de nuevo.";
    await user.click(button);

    expect(await screen.findByTestId("pending-rerun-error-144")).toHaveTextContent("falló");
  });
});

describe("PendingAnalysesPanel — re-ejecutar resumen de temporada", () => {
  const seasonRerunName = "Re-ejecutar el resumen de temporada de Eli Simulada";

  function useSeasonSummaryItem(overrides?: Partial<PendingAnalysis>) {
    mswServer.use(
      http.get("*/api/race-analysis/pending-analyses", () =>
        HttpResponse.json([makeSeasonSummaryPending(overrides)]),
      ),
    );
  }

  it("llama a season-summary del atleta con la temporada del ítem (no la actual ni la de un evento) y confirma", async () => {
    const user = userEvent.setup();
    let call: { athleteId: unknown; body: unknown } | null = null;
    const validaLaunches = vi.fn();
    useSeasonSummaryItem(); // season 2025 ≠ año en curso
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/season-summary", async ({ request, params }) => {
        call = { athleteId: params.athleteId, body: await request.json() };
        return HttpResponse.json({ run_id: "run-season-901", status: "running" }, { status: 202 });
      }),
      http.post("*/api/athletes/:athleteId/race-analysis/runs", () => {
        validaLaunches();
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    renderPanel("desactualizados");

    await user.click(await screen.findByRole("button", { name: seasonRerunName }));

    expect(await screen.findByTestId("pending-rerun-season-started-148")).toHaveTextContent(
      "Resumen de temporada iniciado",
    );
    expect(call).toEqual({ athleteId: "148", body: { season: 2025 } });
    expect(validaLaunches).not.toHaveBeenCalled();
    expect(eventRequests).not.toHaveBeenCalled();
  });

  it("con el presupuesto de IA agotado el botón queda deshabilitado", async () => {
    mockAIStatusData = { budget_status: "exhausted" } as AIStatusResponse;
    useSeasonSummaryItem();
    renderPanel("desactualizados");

    const button = await screen.findByRole("button", {
      name: /No se puede re-ejecutar el resumen de temporada de Eli Simulada/,
    });
    expect(button).toBeDisabled();
  });

  it("un rechazo del backend (422: faltan válidas aprobadas) se muestra inline con su mensaje", async () => {
    const user = userEvent.setup();
    useSeasonSummaryItem();
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/season-summary", () =>
        HttpResponse.json(
          { detail: "Se requieren ≥3 válidas con análisis aprobados para generar el resumen de temporada. Válidas encontradas: 2." },
          { status: 422 },
        ),
      ),
    );
    renderPanel("desactualizados");

    await user.click(await screen.findByRole("button", { name: seasonRerunName }));

    expect(await screen.findByTestId("pending-rerun-season-error-148")).toHaveTextContent(
      "Se requieren ≥3 válidas",
    );
    expect(screen.queryByTestId("pending-rerun-season-started-148")).not.toBeInTheDocument();
  });

  it("un fallo sin detalle usa un mensaje genérico en español", async () => {
    const user = userEvent.setup();
    useSeasonSummaryItem();
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/season-summary", () =>
        HttpResponse.json({}, { status: 500 }),
      ),
    );
    renderPanel("desactualizados");

    await user.click(await screen.findByRole("button", { name: seasonRerunName }));

    expect(await screen.findByTestId("pending-rerun-season-error-148")).toBeInTheDocument();
    expect(screen.queryByTestId("pending-rerun-season-started-148")).not.toBeInTheDocument();
  });

  it("si el run termina en fallo, el estado optimista se reemplaza por el error", async () => {
    const user = userEvent.setup();
    useSeasonSummaryItem();
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/season-summary", () =>
        HttpResponse.json({ run_id: "run-season-902", status: "running" }, { status: 202 }),
      ),
    );
    renderPanel("desactualizados");

    const button = await screen.findByRole("button", { name: seasonRerunName });
    mockRunFailure = "El análisis de Eli Simulada falló. Intenta de nuevo.";
    await user.click(button);

    expect(await screen.findByTestId("pending-rerun-season-error-148")).toHaveTextContent("falló");
  });

  it("válida y resumen del mismo atleta conviven sin colisionar sus data-testid", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/pending-analyses", () =>
        HttpResponse.json([
          makePendingAnalysis({ athlete_id: 148, athlete_ref: "Eli Simulada" }),
          makeSeasonSummaryPending(),
        ]),
      ),
    );
    renderPanel("desactualizados");

    await screen.findByTestId("pending-analyses-list");
    expect(screen.getByTestId("pending-rerun-btn-148")).toBeInTheDocument();
    expect(screen.getByTestId("pending-rerun-season-btn-148")).toBeInTheDocument();
  });
});

describe("PendingAnalysesPanel — controles", () => {
  it("el selector de modo marca el activo (aria-pressed) y avisa al padre", async () => {
    const user = userEvent.setup();
    const onModeChange = vi.fn();
    renderPanel("desactualizados", { onModeChange });

    expect(screen.getByTestId("pending-mode-desactualizados")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("pending-mode-por-aprobar")).toHaveAttribute("aria-pressed", "false");

    await user.click(screen.getByTestId("pending-mode-por-aprobar"));
    expect(onModeChange).toHaveBeenCalledWith("por-aprobar");
  });

  it("«Ocultar» cierra el panel", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderPanel("por-aprobar", { onClose });

    await user.click(screen.getByTestId("pending-analyses-close"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("todos los controles interactivos miden ≥48 px (min-h-12)", async () => {
    renderPanel("desactualizados");
    await screen.findByTestId("pending-analyses-list");

    const controls = [
      screen.getByTestId("pending-analyses-close"),
      screen.getByTestId("pending-mode-por-aprobar"),
      screen.getByTestId("pending-mode-desactualizados"),
      screen.getByTestId("pending-dismiss-btn-run-stale-001"),
      screen.getByRole("link", { name: "Abrir el análisis de Ana Ficticia" }),
      screen.getByRole("button", { name: "Re-ejecutar el análisis de Ana Ficticia" }),
    ];
    for (const control of controls) expect(control.className).toMatch(/min-h-12/);
  });
});

describe("PendingAnalysesPanel — accesibilidad", () => {
  it("sin violaciones jest-axe con la lista de desactualizados", async () => {
    const { container } = renderPanel("desactualizados");
    await screen.findByTestId("pending-analyses-list");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones jest-axe con un resumen de temporada desactualizado (re-ejecutar + descartar)", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/pending-analyses", () =>
        HttpResponse.json([makeSeasonSummaryPending()]),
      ),
    );
    const { container } = renderPanel("desactualizados");
    await screen.findByRole("button", { name: /Re-ejecutar el resumen de temporada de/ });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones jest-axe con la lista por aprobar", async () => {
    const { container } = renderPanel("por-aprobar");
    await screen.findByTestId("pending-analyses-list");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones jest-axe en los estados vacío y de error", async () => {
    mswServer.use(pendingAnalysesEmptyHandler);
    const empty = renderPanel("desactualizados");
    await screen.findByTestId("pending-analyses-empty");
    expect(await axe(empty.container)).toHaveNoViolations();
    empty.unmount();

    mswServer.use(pendingAnalysesErrorHandler);
    const error = renderPanel("desactualizados");
    await screen.findByTestId("pending-analyses-error");
    expect(await axe(error.container)).toHaveNoViolations();
  });

  it("sin violaciones jest-axe con el diálogo de confirmación abierto", async () => {
    const user = userEvent.setup();
    renderPanel("desactualizados");
    await user.click(
      await screen.findByRole("button", { name: /Descartar el aviso.*Ana Ficticia/ }),
    );
    await screen.findByRole("alertdialog");
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
