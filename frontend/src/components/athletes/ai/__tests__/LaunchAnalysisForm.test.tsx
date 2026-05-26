/**
 * Tests vitest para LaunchAnalysisForm (FE-3).
 *
 * Cubre:
 *  - Athlete name read-only.
 *  - onSubmit dispara mutation con body correcto (season + valida_nums + explain_mode).
 *  - Toggle de chips válida (selected → multi-select).
 *  - Disabled durante mutation.
 *  - onStarted callback dispara con run_id.
 *  - Error de servidor expone el mensaje.
 *
 * Nota: el schema Zod permite valida_nums vacío (mapeo a null en el body).
 * El form siempre puede enviarse — no hay error de required en el form layer.
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

import { mswServer } from "@/test/setup";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { LaunchAnalysisForm } from "@/components/athletes/ai/LaunchAnalysisForm";

describe("LaunchAnalysisForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra athlete name read-only y form completo", () => {
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Sebastián García" />,
    );
    expect(screen.getByTestId("launch-analysis-form")).toBeInTheDocument();
    expect(screen.getByText("Sebastián García")).toBeInTheDocument();
    expect(screen.getByTestId("launch-season-select")).toBeInTheDocument();
    expect(screen.getByTestId("launch-explain-switch")).toBeInTheDocument();
    expect(screen.getByTestId("launch-submit")).toBeInTheDocument();
    // Chips de válida visibles
    expect(screen.getByTestId("launch-valida-1")).toBeInTheDocument();
    expect(screen.getByTestId("launch-valida-99")).toBeInTheDocument();
  });

  it("toggle de chips válida actualiza aria-pressed", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );
    const chip = screen.getByTestId("launch-valida-4");
    expect(chip).toHaveAttribute("aria-pressed", "false");
    await user.click(chip);
    await waitFor(() => {
      expect(chip).toHaveAttribute("aria-pressed", "true");
    });
    // Click de nuevo lo deselecciona
    await user.click(chip);
    await waitFor(() => {
      expect(chip).toHaveAttribute("aria-pressed", "false");
    });
  });

  it("submit dispara request con body correcto y llama onStarted con run_id", async () => {
    const bodies: unknown[] = [];
    mswServer.use(
      http.post(
        "*/api/athletes/:athleteId/race-analysis/runs",
        async ({ request }) => {
          const body = await request.json();
          bodies.push(body);
          return HttpResponse.json(
            {
              run_id: "run-xyz-789",
              status: "running",
              started_at: "2026-05-22T10:00:00Z",
              status_url: "/x",
              estimated_seconds: 45,
            },
            { status: 201 },
          );
        },
      ),
    );

    const onStarted = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <LaunchAnalysisForm
        athleteId={42}
        athleteName="Test User"
        onStarted={onStarted}
      />,
    );

    await user.click(screen.getByTestId("launch-valida-3"));
    await user.click(screen.getByTestId("launch-valida-7"));
    await user.click(screen.getByTestId("launch-explain-switch"));
    await user.click(screen.getByTestId("launch-submit"));

    await waitFor(() => {
      expect(onStarted).toHaveBeenCalledWith("run-xyz-789");
    });

    expect(bodies).toHaveLength(1);
    const body = bodies[0] as {
      season: number;
      valida_nums: number[] | null;
      explain_mode: boolean;
    };
    expect(body.season).toBe(new Date().getFullYear());
    expect(body.valida_nums).toEqual([3, 7]);
    expect(body.explain_mode).toBe(true);
  });

  it("submit con sin chips seleccionados envía valida_nums=null", async () => {
    const bodies: unknown[] = [];
    mswServer.use(
      http.post(
        "*/api/athletes/:athleteId/race-analysis/runs",
        async ({ request }) => {
          bodies.push(await request.json());
          return HttpResponse.json(
            {
              run_id: "r1",
              status: "running",
              started_at: "2026-05-22T10:00:00Z",
              status_url: "/x",
              estimated_seconds: 45,
            },
            { status: 201 },
          );
        },
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );
    await user.click(screen.getByTestId("launch-submit"));
    await waitFor(() => {
      expect(bodies).toHaveLength(1);
    });
    expect(
      (bodies[0] as { valida_nums: number[] | null }).valida_nums,
    ).toBeNull();
  });

  it("muestra error de servidor en submit fallido", async () => {
    mswServer.use(
      http.post(
        "*/api/athletes/:athleteId/race-analysis/runs",
        () =>
          new HttpResponse(
            JSON.stringify({ detail: "Sin permisos para lanzar análisis" }),
            { status: 403, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );
    await user.click(screen.getByTestId("launch-submit"));
    await waitFor(() => {
      // Mensaje genérico fallback (axios suele tirar AxiosError con
      // message="Request failed with status code 403").
      const alerts = screen.getAllByRole("alert");
      expect(alerts.length).toBeGreaterThan(0);
    });
  });

  it("botón submit queda disabled durante la mutation", async () => {
    let resolve!: (v: unknown) => void;
    const pending = new Promise((r) => {
      resolve = r;
    });
    mswServer.use(
      http.post(
        "*/api/athletes/:athleteId/race-analysis/runs",
        async () => {
          await pending;
          return HttpResponse.json(
            {
              run_id: "r1",
              status: "running",
              started_at: "2026-05-22T10:00:00Z",
              status_url: "/x",
              estimated_seconds: 45,
            },
            { status: 201 },
          );
        },
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );
    const submit = screen.getByTestId("launch-submit") as HTMLButtonElement;
    expect(submit).not.toBeDisabled();
    await user.click(submit);
    await waitFor(() => {
      expect(submit).toBeDisabled();
    });
    expect(screen.getByText(/lanzando/i)).toBeInTheDocument();

    // Limpia la promesa pendiente
    resolve({});
  });

  it("no tiene violaciones a11y", async () => {
    const { container } = renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  // ---------------------------------------------------------------------------
  // Task #18 — cap de 4 válidas por lanzamiento
  // ---------------------------------------------------------------------------
  //
  // Spec: tras seleccionar 4 válidas, la 5ta debe estar disabled con tooltip
  // "Máximo 4 válidas por lanzamiento". Permite des-seleccionar para liberar
  // slot. La implementación actual del form NO impone este límite todavía —
  // los tests se marcan skip con razón clara para no bloquear la suite.
  describe("cap de 4 válidas por lanzamiento (Task #18)", () => {
    it(`tras seleccionar 4 válidas, la 5ta queda disabled`, async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
      );
      // Selecciona 4 chips primero.
      await user.click(screen.getByTestId("launch-valida-1"));
      await user.click(screen.getByTestId("launch-valida-2"));
      await user.click(screen.getByTestId("launch-valida-3"));
      await user.click(screen.getByTestId("launch-valida-4"));

      const fifth = screen.getByTestId("launch-valida-5") as HTMLButtonElement;
      await waitFor(() => {
        expect(fifth).toBeDisabled();
      });
    });

    it(`tooltip dice "Máximo 4 válidas por lanzamiento"`, async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
      );
      await user.click(screen.getByTestId("launch-valida-1"));
      await user.click(screen.getByTestId("launch-valida-2"));
      await user.click(screen.getByTestId("launch-valida-3"));
      await user.click(screen.getByTestId("launch-valida-4"));

      // El tooltip puede materializarse via title, aria-describedby u overlay.
      // Probamos por texto literal en el DOM (cualquier portal/inline).
      await waitFor(() => {
        expect(
          screen.getByText(/Máximo 4 válidas por lanzamiento/i),
        ).toBeInTheDocument();
      });
    });

    it(`click en 5ta disabled es no-op (no se selecciona)`, async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
      );
      await user.click(screen.getByTestId("launch-valida-1"));
      await user.click(screen.getByTestId("launch-valida-2"));
      await user.click(screen.getByTestId("launch-valida-3"));
      await user.click(screen.getByTestId("launch-valida-4"));

      const fifth = screen.getByTestId("launch-valida-5") as HTMLButtonElement;
      await user.click(fifth);

      expect(fifth).toHaveAttribute("aria-pressed", "false");
    });

    it(`permite des-seleccionar una para liberar slot`, async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
      );
      await user.click(screen.getByTestId("launch-valida-1"));
      await user.click(screen.getByTestId("launch-valida-2"));
      await user.click(screen.getByTestId("launch-valida-3"));
      await user.click(screen.getByTestId("launch-valida-4"));

      // Libera slot des-seleccionando válida 2.
      await user.click(screen.getByTestId("launch-valida-2"));

      const fifth = screen.getByTestId("launch-valida-5") as HTMLButtonElement;
      await waitFor(() => {
        expect(fifth).not.toBeDisabled();
      });
      await user.click(fifth);
      expect(fifth).toHaveAttribute("aria-pressed", "true");
    });
  });
});
