/**
 * Tests para AthleteNewsletterStudioPage (feature 038, T302).
 *
 * `StageLogView` (T301) es responsabilidad de un desarrollo en paralelo —
 * se mockea aquí para aislar la lógica del estudio (hooks, PATCH,
 * permutaciones) de esa dependencia todavía no disponible.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "tok",
      user: { role: "coach", first_name: "Juan", last_name: "T", club_ids: [1], id: 10 },
    }),
  ),
}));

vi.mock("@/hooks/athletes/useAthlete", () => ({
  useAthlete: vi.fn(() => ({
    data: { id: 42, first_name: "Ana", last_name: "Ruiz" },
    isLoading: false,
  })),
}));

import { mswServer } from "@/test/setup";
import {
  newsletterHandlers,
  patchVersionConflictHandler,
  patchPreconditionRequiredHandler,
} from "@/test/msw/newsletterHandlers";
import { stageLogHandlers, makeV2Newsletter } from "@/test/msw/stageLogHandlers";
import { AthleteNewsletterStudioPage } from "@/routes/training/AthleteNewsletterStudioPage";

function renderStudio(athleteId = 42, newsletterId = 1) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/training/athlete-newsletters/${athleteId}/${newsletterId}`]}>
        <Routes>
          <Route
            path="/training/athlete-newsletters/:athleteId/:newsletterId"
            element={<AthleteNewsletterStudioPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockDesktop(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("768px") ? matches : false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

function useV2DetailHandler(overrides?: Parameters<typeof makeV2Newsletter>[0]) {
  return http.get(
    "*/api/athletes/:athleteId/monthly-newsletters/:id",
    ({ params }) =>
      HttpResponse.json(
        makeV2Newsletter({
          id: Number(params.id),
          athlete_id: Number(params.athleteId),
          status: "draft",
          selected_race_insight_ids: [17],
          ...overrides,
        }),
      ),
  );
}

describe("AthleteNewsletterStudioPage", () => {
  beforeEach(() => {
    mockDesktop(true);
    mswServer.use(...newsletterHandlers, ...stageLogHandlers);
  });

  it("renderiza el estudio con el panel de descarga de PDF", async () => {
    mswServer.use(useV2DetailHandler());
    renderStudio();
    await waitFor(() => expect(screen.getByTestId("newsletter-studio-page")).toBeInTheDocument());
    expect(screen.getByTestId("pdf-preview-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("device-preview")).not.toBeInTheDocument();
  });

  it("editar un bloque actualiza el preview de forma optimista y dispara el PATCH", async () => {
    mswServer.use(useV2DetailHandler());
    let patchBody: unknown = null;
    mswServer.use(
      http.patch(
        "*/api/athletes/:athleteId/monthly-newsletters/:id",
        async ({ request, params }) => {
          patchBody = await request.json();
          return HttpResponse.json(
            makeV2Newsletter({
              id: Number(params.id),
              athlete_id: Number(params.athleteId),
              status: "draft",
              stage_overrides: (patchBody as { stage_overrides?: unknown }).stage_overrides ?? null,
            }),
          );
        },
      ),
    );
    renderStudio();
    await waitFor(() => expect(screen.getByTestId("block-card-header")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("block-edit-header"));
    fireEvent.change(screen.getByLabelText("Editar Título de la etapa"), {
      target: { value: "Un título editado por el coach" },
    });
    fireEvent.click(screen.getByTestId("block-save-header"));

    // Preview optimista: la tarjeta del bloque muestra el valor fusionado
    // (draft local `overridesDraft`) apenas se guarda, antes de que
    // resuelva el PATCH.
    await waitFor(() =>
      expect(screen.getByTestId("block-card-header")).toHaveTextContent(
        "Un título editado por el coach",
      ),
    );

    await waitFor(() =>
      expect(patchBody).toEqual({
        stage_overrides: { stage_title: "Un título editado por el coach" },
      }),
    );
  });

  it("regenerar un bloque llama al endpoint con la instrucción", async () => {
    mswServer.use(useV2DetailHandler());
    let regenerateBody: unknown = null;
    mswServer.use(
      http.post(
        "*/api/athletes/:athleteId/monthly-newsletters/:id/regenerate-block",
        async ({ request, params }) => {
          regenerateBody = await request.json();
          return HttpResponse.json(
            makeV2Newsletter({ id: Number(params.id), athlete_id: Number(params.athleteId), status: "draft" }),
          );
        },
      ),
    );
    renderStudio();
    await waitFor(() => expect(screen.getByTestId("block-card-header")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("block-regenerate-header"));
    fireEvent.change(screen.getByLabelText("Indicación para la regeneración"), {
      target: { value: "más corto" },
    });
    fireEvent.click(screen.getByTestId("regenerate-dialog-confirm"));

    await waitFor(() =>
      expect(regenerateBody).toEqual({ block: "stage_title", instruction: "más corto" }),
    );
  });

  it("ocultar un bloque opcional envía el hidden_blocks actualizado", async () => {
    mswServer.use(useV2DetailHandler());
    let patchBody: unknown = null;
    mswServer.use(
      http.patch(
        "*/api/athletes/:athleteId/monthly-newsletters/:id",
        async ({ request, params }) => {
          patchBody = await request.json();
          return HttpResponse.json(
            makeV2Newsletter({ id: Number(params.id), athlete_id: Number(params.athleteId), status: "draft" }),
          );
        },
      ),
    );
    renderStudio();
    await waitFor(() => expect(screen.getByTestId("block-hide-toggle-photos")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("block-hide-toggle-photos"));

    await waitFor(() => expect(patchBody).toEqual({ hidden_blocks: ["photos"] }));
  });

  it("el picker de analista envía una permutación válida al reordenar", async () => {
    mswServer.use(useV2DetailHandler({ selected_race_insight_ids: [17, 42] }));
    let patchBody: unknown = null;
    mswServer.use(
      http.patch(
        "*/api/athletes/:athleteId/monthly-newsletters/:id",
        async ({ request, params }) => {
          patchBody = await request.json();
          return HttpResponse.json(
            makeV2Newsletter({ id: Number(params.id), athlete_id: Number(params.athleteId), status: "draft" }),
          );
        },
      ),
    );
    renderStudio();
    await waitFor(() => expect(screen.getByTestId("analyst-picker")).toBeInTheDocument());

    const secondItem = screen.getByTestId("analyst-picker-item-42");
    fireEvent.click(within(secondItem).getByRole("button", { name: /^Subir/ }));

    await waitFor(() => expect(patchBody).toEqual({ selected_race_insight_ids: [42, 17] }));
  });

  it("el stepper muestra Leído cuando el boletín está enviado y leído", async () => {
    mswServer.use(
      useV2DetailHandler({ status: "sent", read_at: "2026-07-05T09:00:00Z", sent_at: "2026-07-03T10:00:00Z" }),
    );
    renderStudio();
    await waitFor(() => expect(screen.getByTestId("status-stepper")).toBeInTheDocument());
    expect(screen.getByTestId("stepper-step-read")).toHaveAttribute("aria-current", "step");
  });

  it("layout de dos columnas en ≥768px", async () => {
    mockDesktop(true);
    mswServer.use(useV2DetailHandler());
    renderStudio();
    await waitFor(() => expect(screen.getByTestId("studio-layout-desktop")).toBeInTheDocument());
    expect(screen.queryByTestId("studio-layout-mobile")).not.toBeInTheDocument();
  });

  it("layout de tabs en <768px", async () => {
    mockDesktop(false);
    mswServer.use(useV2DetailHandler());
    renderStudio();
    await waitFor(() => expect(screen.getByTestId("studio-layout-mobile")).toBeInTheDocument());
    expect(screen.getByText("Vista previa")).toBeInTheDocument();
    expect(screen.getByText("Bloques")).toBeInTheDocument();
    expect(screen.getByText("Entrega")).toBeInTheDocument();
    expect(screen.queryByTestId("studio-layout-desktop")).not.toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad", async () => {
    mswServer.use(useV2DetailHandler());
    const { container } = renderStudio();
    await waitFor(() => expect(screen.getByTestId("newsletter-studio-page")).toBeInTheDocument());
    const results = await axe(container, { iframes: false });
    expect(results).toHaveNoViolations();
  });

  // -------------------------------------------------------------------------
  // Concurrencia optimista (041 §2/§6, T073)
  // -------------------------------------------------------------------------

  /** Abre la edición del bloque "header" y escribe `value`, sin guardar aún. */
  async function typeHeaderEdit(value: string) {
    await waitFor(() => expect(screen.getByTestId("block-card-header")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("block-edit-header"));
    fireEvent.change(screen.getByLabelText("Editar Título de la etapa"), {
      target: { value },
    });
  }

  it("guardar envía la precondición de versión cargada como header If-Match (regresión T073)", async () => {
    mswServer.use(useV2DetailHandler({ edit_version: 4 }));
    let ifMatch: string | null = null;
    mswServer.use(
      http.patch(
        "*/api/athletes/:athleteId/monthly-newsletters/:id",
        async ({ request, params }) => {
          ifMatch = request.headers.get("If-Match");
          const body = (await request.json()) as { stage_overrides?: unknown };
          return HttpResponse.json(
            makeV2Newsletter({
              id: Number(params.id),
              athlete_id: Number(params.athleteId),
              edit_version: 5,
              stage_overrides: body.stage_overrides ?? null,
            }),
          );
        },
      ),
    );
    renderStudio();
    await typeHeaderEdit("Un título editado por el coach");
    fireEvent.click(screen.getByTestId("block-save-header"));

    await waitFor(() => expect(ifMatch).toBe('W/"4"'));
  });

  it("409 con current_version abre el diálogo de conflicto con la copia exacta", async () => {
    mswServer.use(useV2DetailHandler({ edit_version: 4 }));
    renderStudio();
    await typeHeaderEdit("Texto que no se debe perder");
    mswServer.use(patchVersionConflictHandler(6));
    fireEvent.click(screen.getByTestId("block-save-header"));

    const dialog = await screen.findByTestId("newsletter-conflict-dialog");
    expect(
      within(dialog).getByText("Otro entrenador guardó cambios"),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        "Otro entrenador guardó cambios en este boletín mientras lo editabas. Tu texto sigue acá: cópialo si lo necesitas y luego recarga para trabajar sobre la última versión.",
      ),
    ).toBeInTheDocument();
    expect(within(dialog).getByTestId("newsletter-conflict-reload")).toBeInTheDocument();
    expect(within(dialog).getByTestId("newsletter-conflict-keep-editing")).toBeInTheDocument();
  });

  it("el draft no se pierde tras el 409: el texto sigue en el textarea, sin refetch", async () => {
    mswServer.use(useV2DetailHandler({ edit_version: 4 }));
    let getCallCount = 0;
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/monthly-newsletters/:id",
        ({ params }) => {
          getCallCount += 1;
          return HttpResponse.json(
            makeV2Newsletter({
              id: Number(params.id),
              athlete_id: Number(params.athleteId),
              edit_version: 4,
              selected_race_insight_ids: [17],
            }),
          );
        },
      ),
    );
    renderStudio();
    await typeHeaderEdit("Texto que no se debe perder");
    const getCallsBeforeSave = getCallCount;
    mswServer.use(patchVersionConflictHandler(6));
    fireEvent.click(screen.getByTestId("block-save-header"));

    await screen.findByTestId("newsletter-conflict-dialog");
    // BlockCard cierra el modo edición al guardar (optimista, feature 038);
    // lo que "no se pierde" es overridesDraft — el preview sigue mostrando
    // el texto del coach, nunca revertido por el 409.
    expect(screen.getByTestId("block-card-header")).toHaveTextContent(
      "Texto que no se debe perder",
    );
    // Ningún GET adicional: el conflicto no dispara un refetch en segundo plano.
    expect(getCallCount).toBe(getCallsBeforeSave);
  });

  it("'Seguir editando' cierra el diálogo, mantiene el banner y el draft", async () => {
    mswServer.use(useV2DetailHandler({ edit_version: 4 }));
    renderStudio();
    await typeHeaderEdit("Texto que no se debe perder");
    mswServer.use(patchVersionConflictHandler(6));
    fireEvent.click(screen.getByTestId("block-save-header"));

    await screen.findByTestId("newsletter-conflict-dialog");
    fireEvent.click(screen.getByTestId("newsletter-conflict-keep-editing"));

    await waitFor(() =>
      expect(screen.queryByTestId("newsletter-conflict-dialog")).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId("newsletter-conflict-banner")).toBeInTheDocument();
    expect(screen.getByTestId("block-card-header")).toHaveTextContent(
      "Texto que no se debe perder",
    );
  });

  it("'Recargar' invalida la query una sola vez, limpia el banner y resiembra el draft del servidor", async () => {
    mswServer.use(useV2DetailHandler({ edit_version: 4 }));
    let getCallCount = 0;
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/monthly-newsletters/:id",
        ({ params }) => {
          getCallCount += 1;
          return HttpResponse.json(
            makeV2Newsletter({
              id: Number(params.id),
              athlete_id: Number(params.athleteId),
              edit_version: getCallCount === 1 ? 4 : 6,
              // updated_at debe cambiar entre llamadas: el efecto de
              // resiembra del draft (AthleteNewsletterStudioPage:131-140)
              // dispara con [newsletter.id, newsletter.updated_at] — sin un
              // updated_at distinto el refetch no resiembra overridesDraft.
              updated_at:
                getCallCount === 1 ? "2026-05-01T00:00:00Z" : "2026-05-02T09:00:00Z",
              stage_overrides:
                getCallCount === 1 ? null : { stage_title: "Título de otro entrenador" },
            }),
          );
        },
      ),
    );
    renderStudio();
    await typeHeaderEdit("Texto que no se debe perder");
    const getCallsBeforeSave = getCallCount;
    mswServer.use(patchVersionConflictHandler(6));
    fireEvent.click(screen.getByTestId("block-save-header"));
    await screen.findByTestId("newsletter-conflict-dialog");

    fireEvent.click(screen.getByTestId("newsletter-conflict-reload"));

    await waitFor(() =>
      expect(screen.queryByTestId("newsletter-conflict-dialog")).not.toBeInTheDocument(),
    );
    expect(screen.queryByTestId("newsletter-conflict-banner")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("block-card-header")).toHaveTextContent(
        "Título de otro entrenador",
      ),
    );
    // Exactamente un GET adicional (el refetch disparado por invalidateQueries).
    expect(getCallCount).toBe(getCallsBeforeSave + 1);
  });

  it("428 muestra el toast de versión faltante, no el diálogo de conflicto", async () => {
    mswServer.use(useV2DetailHandler({ edit_version: 4 }));
    renderStudio();
    await typeHeaderEdit("Un título");
    mswServer.use(patchPreconditionRequiredHandler);
    fireEvent.click(screen.getByTestId("block-save-header"));

    await waitFor(() => expect(screen.getByTestId("toast-error")).toBeInTheDocument());
    expect(screen.queryByTestId("newsletter-conflict-dialog")).not.toBeInTheDocument();
  });

  it("no reintenta el PATCH tras un 409 de versión vencida (R-16): una sola llamada de red", async () => {
    mswServer.use(useV2DetailHandler({ edit_version: 4 }));
    let patchCallCount = 0;
    mswServer.use(
      http.patch(
        "*/api/athletes/:athleteId/monthly-newsletters/:id",
        () => {
          patchCallCount += 1;
          return HttpResponse.json(
            { detail: "Otro entrenador guardó cambios.", current_version: 6 },
            { status: 409 },
          );
        },
      ),
    );
    renderStudio();
    await typeHeaderEdit("Un título");
    fireEvent.click(screen.getByTestId("block-save-header"));

    await screen.findByTestId("newsletter-conflict-dialog");
    expect(patchCallCount).toBe(1);
  });

  it("coach-note-byline muestra autor y fecha, y está ausente sin nota", async () => {
    mswServer.use(
      useV2DetailHandler({
        coach_note: "Nos vemos en la próxima válida.",
        coach_note_author: { user_id: 7, display_name: "Ana Coach" },
        coach_note_updated_at: "2026-09-02T15:41:08Z",
      }),
    );
    renderStudio();
    await waitFor(() => expect(screen.getByTestId("coach-note-byline")).toBeInTheDocument());
    expect(screen.getByTestId("coach-note-byline")).toHaveTextContent("Nota escrita por Ana Coach");
  });

  it("coach-note-byline está ausente cuando no hay nota del entrenador", async () => {
    mswServer.use(useV2DetailHandler({ coach_note: null, coach_note_author: null }));
    renderStudio();
    await waitFor(() => expect(screen.getByTestId("newsletter-studio-page")).toBeInTheDocument());
    expect(screen.queryByTestId("coach-note-byline")).not.toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad con el diálogo de conflicto abierto y cerrado", async () => {
    mswServer.use(useV2DetailHandler({ edit_version: 4 }));
    const { container } = renderStudio();
    await typeHeaderEdit("Un título");
    mswServer.use(patchVersionConflictHandler(6));
    fireEvent.click(screen.getByTestId("block-save-header"));
    await screen.findByTestId("newsletter-conflict-dialog");

    let results = await axe(container, { iframes: false });
    expect(results).toHaveNoViolations();

    fireEvent.click(screen.getByTestId("newsletter-conflict-keep-editing"));
    await waitFor(() =>
      expect(screen.queryByTestId("newsletter-conflict-dialog")).not.toBeInTheDocument(),
    );

    results = await axe(container, { iframes: false });
    expect(results).toHaveNoViolations();
  });
});
