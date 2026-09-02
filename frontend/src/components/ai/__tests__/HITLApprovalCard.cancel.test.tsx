/**
 * Tests de la acción "Descartar análisis" de HITLApprovalCard.
 *
 * Contexto: Aprobar / Editar / Rechazar reanudan el grafo. Si el run se
 * quedó atascado en el gate HITL ninguna de las tres sirve, y el coach
 * quedaba bloqueado — el backend responde 409 a un relanzamiento mientras
 * ese run siga activo y un run pausado en HITL no expira solo. Esta
 * tercera acción llama a `POST /runs/:id/cancel`.
 *
 * Este archivo usa MSW (red real de axios contra handlers) en vez del
 * `vi.mock("@/api/raceAnalysis")` que usa `HITLApprovalCard.test.tsx`:
 * así se ejercita también el wrapper `cancelRun` (URL y verbo reales), no
 * sólo el componente.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

import { mswServer } from "@/test/setup";
import { raceRunKeys } from "@/hooks/ai/useRaceRun";
import { HITLApprovalCard } from "@/components/ai/HITLApprovalCard";

const CANCEL_PATH = "*/api/race-analysis/runs/:runId/cancel";

/** Claves precargadas para comprobar la invalidación posterior. */
const ATHLETE_INSIGHTS_KEY = ["athlete-insights", 144] as const;
const SEASON_PANORAMA_KEY = ["season-panorama", 2026, 1] as const;
/** Fuera del alcance del helper — no debe invalidarse (Strava). */
const ACTIVITIES_KEY = ["athlete-activities", 144] as const;

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      // `gcTime` distinto de 0 a propósito: las queries que sembramos con
      // `setQueryData` no tienen observadores y con gcTime=0 el recolector
      // las borra antes de que podamos leer su `isInvalidated`.
      queries: { retry: false, gcTime: 60_000 },
      mutations: { retry: false },
    },
  });
}

function wrap(ui: ReactNode, qc: QueryClient) {
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

function seedQueries(qc: QueryClient) {
  qc.setQueryData(raceRunKeys.status("r1"), { latest: {}, events: [] });
  qc.setQueryData(ATHLETE_INSIGHTS_KEY, []);
  qc.setQueryData(SEASON_PANORAMA_KEY, []);
  qc.setQueryData(ACTIVITIES_KEY, []);
}

/** Abre el AlertDialog de confirmación y devuelve su nodo. */
async function openDiscardDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTestId("hitl-discard-button"));
  return await screen.findByRole("alertdialog");
}

describe("HITLApprovalCard — descartar análisis", () => {
  beforeEach(() => vi.clearAllMocks());

  it("muestra la acción junto a Aprobar/Editar/Rechazar", () => {
    wrap(
      <HITLApprovalCard runId="r1" stepId="hitl_1" draftMarkdown="t" />,
      makeQueryClient(),
    );
    expect(
      screen.getByRole("button", { name: /descartar análisis/i }),
    ).toBeInTheDocument();
  });

  it("no llama al backend hasta que se confirma en el diálogo", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    mswServer.use(
      http.post(CANCEL_PATH, () => {
        onCancel();
        return HttpResponse.json({ run_id: "r1", state: "cancelled" });
      }),
    );

    wrap(
      <HITLApprovalCard runId="r1" stepId="hitl_1" draftMarkdown="t" />,
      makeQueryClient(),
    );

    const dialog = await openDiscardDialog(user);
    expect(
      within(dialog).getByText("Descartar análisis pendiente"),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        "Se cancelará este análisis sin guardar nada. Podrás volver a lanzarlo.",
      ),
    ).toBeInTheDocument();

    // Cerrar con "Conservar" no dispara nada.
    await user.click(within(dialog).getByRole("button", { name: "Conservar" }));
    await waitFor(() =>
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument(),
    );
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("al confirmar hace POST /runs/:id/cancel, cierra el diálogo y avisa al padre", async () => {
    const user = userEvent.setup();
    const seen: { url: string; runId: string }[] = [];
    mswServer.use(
      http.post(CANCEL_PATH, ({ request, params }) => {
        seen.push({ url: request.url, runId: String(params.runId) });
        return HttpResponse.json({ run_id: "r1", state: "cancelled" });
      }),
    );
    const onCancelled = vi.fn();

    wrap(
      <HITLApprovalCard
        runId="r1"
        stepId="hitl_1"
        draftMarkdown="t"
        onCancelled={onCancelled}
      />,
      makeQueryClient(),
    );

    const dialog = await openDiscardDialog(user);
    await user.click(
      within(dialog).getByRole("button", { name: /descartar análisis/i }),
    );

    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].runId).toBe("r1");
    expect(seen[0].url).toContain("/api/race-analysis/runs/r1/cancel");
    await waitFor(() => expect(onCancelled).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument(),
    );
  });

  it("invalida el status del run y las queries de IA del atleta, y no toca las ajenas", async () => {
    const user = userEvent.setup();
    mswServer.use(
      http.post(CANCEL_PATH, () =>
        HttpResponse.json({ run_id: "r1", state: "cancelled" }),
      ),
    );
    const qc = makeQueryClient();
    seedQueries(qc);

    wrap(<HITLApprovalCard runId="r1" stepId="hitl_1" draftMarkdown="t" />, qc);

    const dialog = await openDiscardDialog(user);
    await user.click(
      within(dialog).getByRole("button", { name: /descartar análisis/i }),
    );

    await waitFor(() => {
      expect(
        qc.getQueryState(raceRunKeys.status("r1"))?.isInvalidated,
      ).toBe(true);
    });
    expect(qc.getQueryState(ATHLETE_INSIGHTS_KEY)?.isInvalidated).toBe(true);
    expect(qc.getQueryState(SEASON_PANORAMA_KEY)?.isInvalidated).toBe(true);
    // `athlete-activities` (Strava) queda fuera del helper compartido.
    expect(qc.getQueryState(ACTIVITIES_KEY)?.isInvalidated).toBe(false);
  });

  it("si el backend responde 409 el diálogo sigue abierto y muestra el error", async () => {
    const user = userEvent.setup();
    mswServer.use(
      http.post(CANCEL_PATH, () =>
        HttpResponse.json(
          { detail: "Run en estado terminal 'failed', no se puede descartar" },
          { status: 409 },
        ),
      ),
    );
    const onCancelled = vi.fn();

    wrap(
      <HITLApprovalCard
        runId="r1"
        stepId="hitl_1"
        draftMarkdown="t"
        onCancelled={onCancelled}
      />,
      makeQueryClient(),
    );

    const dialog = await openDiscardDialog(user);
    await user.click(
      within(dialog).getByRole("button", { name: /descartar análisis/i }),
    );

    expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(onCancelled).not.toHaveBeenCalled();
  });

  it("el botón cumple el tamaño táctil mínimo (48px de alto)", () => {
    wrap(
      <HITLApprovalCard runId="r1" stepId="hitl_1" draftMarkdown="t" />,
      makeQueryClient(),
    );
    // jsdom no calcula layout: verificamos la utilidad Tailwind que fija
    // el alto mínimo (min-h-12 = 3rem = 48px), igual que ConfirmDialog.
    expect(screen.getByTestId("hitl-discard-button").className).toContain(
      "min-h-12",
    );
  });

  it("sin violaciones a11y con el AlertDialog de confirmación abierto", async () => {
    const user = userEvent.setup();
    wrap(
      <HITLApprovalCard
        runId="r1"
        stepId="hitl_1"
        draftMarkdown="# Draft de prueba"
      />,
      makeQueryClient(),
    );

    await openDiscardDialog(user);

    // `axe(document.body)`: Radix renderiza el AlertDialog en un portal
    // fuera del container de `render()` (mismo patrón que ConfirmDialog).
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
