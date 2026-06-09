/**
 * US6 (feature 011): "Regenerar" affordance on insight rows.
 *
 * Coach-only action that re-launches the per-válida analysis scoped to the
 * row's (season, valida_num). Shows error state on failure. a11y via jest-axe.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

vi.mock("@/components/ai/MarkdownReportViewer", () => ({
  MarkdownReportViewer: ({ markdown }: { markdown: string }) => (
    <div data-testid="markdown-viewer">{markdown}</div>
  ),
}));

import { mswServer } from "@/test/setup";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { InsightsTimeline } from "@/components/athletes/ai/InsightsTimeline";

describe("InsightsTimeline — Regenerar (US6)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra el botón Regenerar en filas de válida (coach)", async () => {
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-regenerate-1")).toBeInTheDocument();
    });
  });

  it("NO muestra Regenerar para parent", async () => {
    renderWithProviders(<InsightsTimeline athleteId={42} mode="parent" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-card-1")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("insight-regenerate-1")).not.toBeInTheDocument();
  });

  it("re-lanza el análisis de la válida con (season, valida_num) de la fila", async () => {
    let captured: { season?: number; valida_nums?: number[] } | null = null;
    mswServer.use(
      http.post(
        "*/api/athletes/:athleteId/race-analysis/runs",
        async ({ request }) => {
          captured = (await request.json()) as {
            season?: number;
            valida_nums?: number[];
          };
          return HttpResponse.json(
            {
              run_id: "run-regen-001",
              status: "running",
              started_at: "2026-06-09T10:00:00Z",
              status_url: "/api/race-analysis/runs/run-regen-001/status",
              estimated_seconds: 20,
            },
            { status: 201 },
          );
        },
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-regenerate-1")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-regenerate-1"));

    await waitFor(() => {
      expect(captured).not.toBeNull();
    });
    // mockInsight() default: season 2026, valida_num 4.
    expect(captured!.season).toBe(2026);
    expect(captured!.valida_nums).toEqual([4]);
  });

  it("muestra estado de error si la regeneración falla", async () => {
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/runs", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={42} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("insight-regenerate-1")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("insight-regenerate-1"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/no se pudo regenerar/i);
    });
  });

  it("no tiene violaciones de accesibilidad con el control de regeneración", async () => {
    const { container } = renderWithProviders(
      <InsightsTimeline athleteId={42} mode="coach" />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("insight-regenerate-1")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
