/**
 * Tests vitest para LaunchAnalysisForm (FE-3).
 *
 * Cubre:
 *  - Athlete name read-only.
 *  - Chips poblados con las carreras reales del atleta (useAthleteRaces).
 *  - onSubmit dispara mutation con body correcto:
 *      · 1 carrera   → { season, event_id }  (desambigua copa vs campeonato)
 *      · >1 carrera  → { season, valida_nums: [...] }
 *      · 0 carreras  → { season, valida_nums: null }
 *  - Toggle de chips + cap de 4.
 *  - Disabled durante mutation.
 *  - onStarted callback dispara con run_id.
 *  - Error de servidor expone el mensaje.
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

const YEAR = new Date().getFullYear();

// Carreras de ejemplo: 5 válidas de copa (event 1..5, seq 1..5) + 1 campeonato
// (event 99, seq 1 — colisiona con la válida 1: por eso event_id importa).
const RACES = {
  season: YEAR,
  items: [
    { event_id: 1, sequence_number: 1, series_kind: "cup", event_date: `${YEAR}-01-31`, event_name: "V1", location: "Sevilla", label: "Válida 1" },
    { event_id: 2, sequence_number: 2, series_kind: "cup", event_date: `${YEAR}-02-28`, event_name: "V2", location: "Ginebra", label: "Válida 2" },
    { event_id: 3, sequence_number: 3, series_kind: "cup", event_date: `${YEAR}-04-19`, event_name: "V3", location: "La Cumbre", label: "Válida 3" },
    { event_id: 4, sequence_number: 4, series_kind: "cup", event_date: `${YEAR}-05-17`, event_name: "V4", location: "Cali", label: "Válida 4" },
    { event_id: 5, sequence_number: 5, series_kind: "cup", event_date: `${YEAR}-08-01`, event_name: "V5", location: "Palmira", label: "Válida 5" },
    { event_id: 99, sequence_number: 1, series_kind: "championship", event_date: `${YEAR}-06-13`, event_name: "Ginebra", location: "Ginebra", label: "Campeonato Departamental" },
  ],
};

function mockRaces(items = RACES) {
  mswServer.use(
    http.get("*/api/athletes/:athleteId/race-analysis/races", () =>
      HttpResponse.json(items),
    ),
  );
}

function mockLaunch(bodies: unknown[]) {
  mswServer.use(
    http.post(
      "*/api/athletes/:athleteId/race-analysis/runs",
      async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(
          {
            run_id: "run-xyz-789",
            status: "running",
            started_at: `${YEAR}-05-22T10:00:00Z`,
            status_url: "/x",
            estimated_seconds: 45,
          },
          { status: 201 },
        );
      },
    ),
  );
}

describe("LaunchAnalysisForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra athlete name read-only y chips de carreras reales", async () => {
    mockRaces();
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Sebastián García" />,
    );
    expect(screen.getByTestId("launch-analysis-form")).toBeInTheDocument();
    expect(screen.getByText("Sebastián García")).toBeInTheDocument();
    expect(screen.getByTestId("launch-season-select")).toBeInTheDocument();
    expect(screen.getByTestId("launch-submit")).toBeInTheDocument();
    // Chips poblados desde el endpoint de carreras (incluye el campeonato).
    await waitFor(() => {
      expect(screen.getByTestId("launch-event-1")).toBeInTheDocument();
    });
    expect(screen.getByTestId("launch-event-99")).toBeInTheDocument();
    // El campeonato se rotula "CD".
    expect(screen.getByTestId("launch-event-99")).toHaveTextContent("CD");
  });

  it("toggle de chip actualiza aria-pressed", async () => {
    mockRaces();
    const user = userEvent.setup();
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );
    const chip = await screen.findByTestId("launch-event-4");
    expect(chip).toHaveAttribute("aria-pressed", "false");
    await user.click(chip);
    await waitFor(() => expect(chip).toHaveAttribute("aria-pressed", "true"));
    await user.click(chip);
    await waitFor(() => expect(chip).toHaveAttribute("aria-pressed", "false"));
  });

  it("una sola carrera → body con event_id (desambigua campeonato)", async () => {
    mockRaces();
    const bodies: unknown[] = [];
    mockLaunch(bodies);
    const onStarted = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <LaunchAnalysisForm
        athleteId={42}
        athleteName="Test User"
        onStarted={onStarted}
      />,
    );
    // Selecciona SOLO el campeonato (event 99, seq 1).
    await user.click(await screen.findByTestId("launch-event-99"));
    await user.click(screen.getByTestId("launch-explain-switch"));
    await user.click(screen.getByTestId("launch-submit"));

    await waitFor(() =>
      expect(onStarted).toHaveBeenCalledWith("run-xyz-789"),
    );
    expect(bodies).toHaveLength(1);
    const body = bodies[0] as {
      season: number;
      event_id?: number;
      valida_nums?: number[] | null;
      explain_mode: boolean;
    };
    expect(body.season).toBe(YEAR);
    expect(body.event_id).toBe(99);
    expect(body.valida_nums).toBeUndefined();
    expect(body.explain_mode).toBe(true);
  });

  it("varias carreras → body con valida_nums (sequence_number)", async () => {
    mockRaces();
    const bodies: unknown[] = [];
    mockLaunch(bodies);
    const user = userEvent.setup();
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );
    await user.click(await screen.findByTestId("launch-event-3"));
    await user.click(screen.getByTestId("launch-event-5"));
    await user.click(screen.getByTestId("launch-submit"));

    await waitFor(() => expect(bodies).toHaveLength(1));
    const body = bodies[0] as { valida_nums?: number[] | null; event_id?: number };
    expect(body.valida_nums).toEqual([3, 5]);
    expect(body.event_id).toBeUndefined();
  });

  it("sin selección → valida_nums=null", async () => {
    mockRaces();
    const bodies: unknown[] = [];
    mockLaunch(bodies);
    const user = userEvent.setup();
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );
    await screen.findByTestId("launch-event-1");
    await user.click(screen.getByTestId("launch-submit"));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(
      (bodies[0] as { valida_nums: number[] | null }).valida_nums,
    ).toBeNull();
  });

  it("temporada sin carreras muestra mensaje vacío", async () => {
    mockRaces({ season: YEAR, items: [] });
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );
    expect(await screen.findByTestId("launch-races-empty")).toBeInTheDocument();
  });

  it("muestra error de servidor en submit fallido", async () => {
    mockRaces();
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
    await screen.findByTestId("launch-event-1");
    await user.click(screen.getByTestId("launch-submit"));
    await waitFor(() => {
      const alerts = screen.getAllByRole("alert");
      expect(alerts.length).toBeGreaterThan(0);
    });
  });

  it("botón submit queda disabled durante la mutation", async () => {
    mockRaces();
    let resolve!: (v: unknown) => void;
    const pending = new Promise((r) => {
      resolve = r;
    });
    mswServer.use(
      http.post("*/api/athletes/:athleteId/race-analysis/runs", async () => {
        await pending;
        return HttpResponse.json(
          {
            run_id: "r1",
            status: "running",
            started_at: `${YEAR}-05-22T10:00:00Z`,
            status_url: "/x",
            estimated_seconds: 45,
          },
          { status: 201 },
        );
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );
    await screen.findByTestId("launch-event-1");
    const submit = screen.getByTestId("launch-submit") as HTMLButtonElement;
    expect(submit).not.toBeDisabled();
    await user.click(submit);
    await waitFor(() => expect(submit).toBeDisabled());
    expect(screen.getByText(/lanzando/i)).toBeInTheDocument();
    resolve({});
  });

  it("no tiene violaciones a11y", async () => {
    mockRaces();
    const { container } = renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );
    await screen.findByTestId("launch-event-1");
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  // ---------------------------------------------------------------------------
  // Cap de 4 carreras por lanzamiento
  // ---------------------------------------------------------------------------
  describe("cap de 4 carreras por lanzamiento", () => {
    it("tras seleccionar 4, la 5ta queda disabled y su click es no-op", async () => {
      mockRaces();
      const user = userEvent.setup();
      renderWithProviders(
        <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
      );
      await user.click(await screen.findByTestId("launch-event-1"));
      await user.click(screen.getByTestId("launch-event-2"));
      await user.click(screen.getByTestId("launch-event-3"));
      await user.click(screen.getByTestId("launch-event-4"));

      const fifth = screen.getByTestId("launch-event-5") as HTMLButtonElement;
      await waitFor(() => expect(fifth).toBeDisabled());
      await user.click(fifth);
      expect(fifth).toHaveAttribute("aria-pressed", "false");
    });

    it("des-seleccionar libera slot", async () => {
      mockRaces();
      const user = userEvent.setup();
      renderWithProviders(
        <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
      );
      await user.click(await screen.findByTestId("launch-event-1"));
      await user.click(screen.getByTestId("launch-event-2"));
      await user.click(screen.getByTestId("launch-event-3"));
      await user.click(screen.getByTestId("launch-event-4"));

      await user.click(screen.getByTestId("launch-event-2"));

      const fifth = screen.getByTestId("launch-event-5") as HTMLButtonElement;
      await waitFor(() => expect(fifth).not.toBeDisabled());
      await user.click(fifth);
      expect(fifth).toHaveAttribute("aria-pressed", "true");
    });
  });
});
