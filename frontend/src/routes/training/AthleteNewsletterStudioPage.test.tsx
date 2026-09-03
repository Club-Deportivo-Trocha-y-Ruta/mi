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
import { newsletterHandlers } from "@/test/msw/newsletterHandlers";
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
});
