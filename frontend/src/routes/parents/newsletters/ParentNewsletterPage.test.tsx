/**
 * Tests vitest para ParentNewsletterPage (feature 038, T303).
 *
 * Cubre: render de StageLogView(mode="parent"), receipt de lectura
 * disparado UNA sola vez por newsletterId, botón "Descargar PDF", ruteo
 * protegido por rol parent y a11y.
 *
 * NOTA DE DEPENDENCIA: `@/components/newsletter/StageLogView` se construye
 * en paralelo en esta misma oleada — se mockea aquí porque su forma final
 * (props exactas más allá de `mode`/`stageLog`) no está cerrada todavía.
 * Si el import real ya existe cuando corra este archivo, el mock sigue
 * siendo válido (vi.mock reemplaza el módulo real igual).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 5, role: "parent" },
      isAuthenticated: true,
    }),
  ),
}));

vi.mock("@/components/newsletter/StageLogView", () => ({
  StageLogView: ({ mode, stageLog }: { mode: string; stageLog: { stage_title: string } }) => (
    <div data-testid="mock-stage-log-view" data-mode={mode}>
      {stageLog.stage_title}
    </div>
  ),
}));

import { mswServer } from "@/test/setup";
import { stageLogHandlers, parentNewsletterNotFoundHandler } from "@/test/msw/stageLogHandlers";
import { ParentNewsletterPage } from "./ParentNewsletterPage";

function renderPage(athleteId = 42, newsletterId = 1) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/my-athletes/${athleteId}/bitacora/${newsletterId}`]}>
        <Routes>
          <Route
            path="/my-athletes/:athleteId/bitacora/:newsletterId"
            element={<ParentNewsletterPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ParentNewsletterPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mswServer.use(...stageLogHandlers);
  });

  it("renderiza StageLogView con mode='parent' y el stage_log del boletín", async () => {
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("mock-stage-log-view")).toBeInTheDocument(),
    );

    expect(screen.getByTestId("mock-stage-log-view")).toHaveAttribute(
      "data-mode",
      "parent",
    );
  });

  it("muestra el botón 'Descargar PDF' cuando has_pdf es true", async () => {
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("download-bitacora-pdf-btn")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("download-bitacora-pdf-btn")).toHaveTextContent(
      "Descargar PDF",
    );
  });

  it("dispara el receipt de lectura UNA sola vez por newsletterId", async () => {
    const { http, HttpResponse } = await import("msw");
    let callCount = 0;
    mswServer.use(
      http.post(
        "*/api/parents/me/athletes/:athleteId/newsletters/:newsletterId/read",
        () => {
          callCount += 1;
          return new HttpResponse(null, { status: 204 });
        },
      ),
    );

    const { rerender } = renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("mock-stage-log-view")).toBeInTheDocument(),
    );
    await waitFor(() => expect(callCount).toBe(1));

    // Un re-render (p. ej. re-entrar a la misma pestaña sin recargar) no
    // debe repetir el POST — guard local (ref) + guard sessionStorage del
    // hook (data-model.md §6). Debe reenvolverse en QueryClientProvider
    // (mismo requisito que `renderPage`): `useMarkNewsletterRead` usa
    // `useQueryClient()` internamente y explota sin ese contexto.
    const rerenderQueryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
    });
    rerender(
      <QueryClientProvider client={rerenderQueryClient}>
        <MemoryRouter initialEntries={["/my-athletes/42/bitacora/1"]}>
          <Routes>
            <Route
              path="/my-athletes/:athleteId/bitacora/:newsletterId"
              element={<ParentNewsletterPage />}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("mock-stage-log-view")).toBeInTheDocument(),
    );
    expect(callCount).toBe(1);
  });

  it("no repite el receipt si ya se marcó leído en esta sesión (sessionStorage)", async () => {
    sessionStorage.setItem("bitacora-read:1", "1");
    const { http, HttpResponse } = await import("msw");
    let callCount = 0;
    mswServer.use(
      http.post(
        "*/api/parents/me/athletes/:athleteId/newsletters/:newsletterId/read",
        () => {
          callCount += 1;
          return new HttpResponse(null, { status: 204 });
        },
      ),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("mock-stage-log-view")).toBeInTheDocument(),
    );
    expect(callCount).toBe(0);
  });

  it("muestra un estado de error cuando la bitácora no existe o no fue enviada (404)", async () => {
    mswServer.use(parentNewsletterNotFoundHandler);
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("No se pudo cargar esta bitácora.")).toBeInTheDocument(),
    );
  });

  it("sin violaciones axe", async () => {
    const { container } = renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("mock-stage-log-view")).toBeInTheDocument(),
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
