/**
 * Tests vitest del SeasonSummaryButton (Task #9).
 *
 * - Disabled si analyzedValidasCount < 3, con tooltip explicativo.
 * - Click dispara mutation y muestra feedback de éxito.
 * - Error path: muestra feedback de error.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Coach", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

import { mswServer } from "@/test/setup";
import {
  seasonSummarySuccessHandler,
  seasonSummaryInsufficientValidasHandler,
} from "@/test/msw/raceAnalysisV2Handlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { SeasonSummaryButton } from "@/components/athletes/ai/SeasonSummaryButton";

describe("SeasonSummaryButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("se muestra disabled si analyzedValidasCount < 3", () => {
    renderWithProviders(
      <SeasonSummaryButton athleteId={42} analyzedValidasCount={2} />,
    );
    const btn = screen.getByTestId("season-summary-btn");
    expect(btn).toBeDisabled();
  });

  it("tooltip explica el mínimo cuando está disabled", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <SeasonSummaryButton athleteId={42} analyzedValidasCount={1} />,
    );
    // Hover dispara el tooltip (Radix renderiza al body).
    const btn = screen.getByTestId("season-summary-btn");
    // El wrapper span contiene tabIndex=0 — la trigger es ese wrapper.
    await user.hover(btn.parentElement ?? btn);
    await waitFor(() => {
      // Texto literal: "Mínimo 3 válidas analizadas (tienes 1)"
      // Radix Tooltip puede renderizar el contenido en múltiples nodos
      // (portal visible + sr-only para a11y). Usamos getAllByText.
      const matches = screen.getAllByText(
        /mínimo 3 válidas analizadas \(tienes 1\)/i,
      );
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("queda habilitado cuando hay 3+ válidas analizadas", () => {
    renderWithProviders(
      <SeasonSummaryButton athleteId={42} analyzedValidasCount={3} />,
    );
    const btn = screen.getByTestId("season-summary-btn");
    expect(btn).not.toBeDisabled();
  });

  it("click dispara mutation y muestra feedback de éxito", async () => {
    mswServer.use(seasonSummarySuccessHandler);
    const user = userEvent.setup();
    renderWithProviders(
      <SeasonSummaryButton athleteId={42} analyzedValidasCount={4} />,
    );

    const btn = screen.getByTestId("season-summary-btn");
    await user.click(btn);

    await waitFor(() => {
      expect(screen.getByTestId("season-summary-success")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/resumen en proceso/i),
    ).toBeInTheDocument();
  });

  it("error del backend muestra feedback de error", async () => {
    mswServer.use(seasonSummaryInsufficientValidasHandler);
    const user = userEvent.setup();
    renderWithProviders(
      <SeasonSummaryButton athleteId={42} analyzedValidasCount={4} />,
    );

    const btn = screen.getByTestId("season-summary-btn");
    await user.click(btn);

    await waitFor(() => {
      expect(screen.getByTestId("season-summary-error")).toBeInTheDocument();
    });
    // Muestra el `detail` real del backend (422 insufficient válidas).
    expect(
      screen.getByText(/m[ií]nimo 3 v[áa]lidas/i),
    ).toBeInTheDocument();
  });

  it("tras éxito el botón vuelve a estar habilitado", async () => {
    mswServer.use(seasonSummarySuccessHandler);
    const user = userEvent.setup();
    renderWithProviders(
      <SeasonSummaryButton athleteId={42} analyzedValidasCount={4} />,
    );
    const btn = screen.getByTestId("season-summary-btn");
    await user.click(btn);

    await waitFor(() => {
      expect(screen.getByTestId("season-summary-success")).toBeInTheDocument();
    });
    // Tras la resolución de la mutation el botón vuelve a estar enabled.
    expect(screen.getByTestId("season-summary-btn")).not.toBeDisabled();
  });
});
