/**
 * Tests vitest del SeasonSummaryButton (Task #9).
 *
 * - Disabled si analyzedValidasCount < 3, con tooltip explicativo.
 * - Click lanza el run (202 {run_id}) y muestra feedback "en proceso".
 * - Error path: muestra feedback de error.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
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

  it("click lanza el run y muestra feedback 'en proceso' (feature 037: asíncrono)", async () => {
    mswServer.use(seasonSummarySuccessHandler);
    const user = userEvent.setup();
    renderWithProviders(
      <SeasonSummaryButton athleteId={42} analyzedValidasCount={4} />,
    );

    await user.click(screen.getByTestId("season-summary-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("season-summary-success")).toBeInTheDocument();
    });
    expect(screen.getByText(/en proceso/i)).toBeInTheDocument();
    expect(screen.queryByText(/resumen de temporada generado/i)).not.toBeInTheDocument();
  });

  it("expone run_id via onRunStarted", async () => {
    mswServer.use(seasonSummarySuccessHandler);
    const onRunStarted = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <SeasonSummaryButton
        athleteId={42}
        analyzedValidasCount={4}
        onRunStarted={onRunStarted}
      />,
    );

    await user.click(screen.getByTestId("season-summary-btn"));

    await waitFor(() => {
      // run_id="run-season-9001" en seasonSummarySuccessHandler.
      expect(onRunStarted).toHaveBeenCalledWith("run-season-9001");
    });
    expect(onRunStarted).toHaveBeenCalledTimes(1);
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
