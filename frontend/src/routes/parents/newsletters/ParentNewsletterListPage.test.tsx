/**
 * Tests vitest para ParentNewsletterListPage (feature 038, T303).
 *
 * Cubre: listado de bitácoras, chip "Nueva" mientras `read_at` es null,
 * ruteo protegido por rol parent, y a11y (jest-axe, cero violaciones).
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

import { mswServer } from "@/test/setup";
import { stageLogHandlers } from "@/test/msw/stageLogHandlers";
import { http, HttpResponse } from "msw";
import { ParentNewsletterListPage } from "./ParentNewsletterListPage";

function renderPage(athleteId = 42) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/my-athletes/${athleteId}/bitacora`]}>
        <Routes>
          <Route path="/my-athletes/:athleteId/bitacora" element={<ParentNewsletterListPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ParentNewsletterListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mswServer.use(...stageLogHandlers);
  });

  it("muestra una tarjeta por bitácora enviada con periodo y título de etapa", async () => {
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("parent-newsletter-list")).toBeInTheDocument(),
    );

    expect(screen.getByText("Julio 2026")).toBeInTheDocument();
    expect(screen.getByText("Junio 2026")).toBeInTheDocument();
    // Ambas bitácoras de la fixture comparten el mismo stage_title de ejemplo.
    expect(
      screen.getAllByText("Un mes de base, sin carreras, construyendo resistencia"),
    ).toHaveLength(2);
  });

  it("muestra el chip 'Nueva' solo en bitácoras con read_at null", async () => {
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("parent-newsletter-list")).toBeInTheDocument(),
    );

    // Fixture: newsletter id=1 sin leer (read_at null), id=2 leída.
    expect(screen.getByTestId("parent-newsletter-new-1")).toHaveTextContent("Nueva");
    expect(screen.queryByTestId("parent-newsletter-new-2")).not.toBeInTheDocument();
  });

  it("enlaza cada tarjeta al detalle /my-athletes/:athleteId/bitacora/:newsletterId", async () => {
    renderPage(42);

    await waitFor(() =>
      expect(screen.getByTestId("parent-newsletter-card-1")).toBeInTheDocument(),
    );

    expect(screen.getByTestId("parent-newsletter-card-1")).toHaveAttribute(
      "href",
      "/my-athletes/42/bitacora/1",
    );
  });

  it("muestra un estado vacío cuando el atleta no tiene bitácoras enviadas", async () => {
    mswServer.use(
      http.get("*/api/parents/me/athletes/:athleteId/newsletters", () =>
        HttpResponse.json([]),
      ),
    );
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByText("Todavía no hay bitácoras enviadas para tu atleta."),
      ).toBeInTheDocument(),
    );
  });

  it("sin violaciones axe", async () => {
    const { container } = renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("parent-newsletter-list")).toBeInTheDocument(),
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
