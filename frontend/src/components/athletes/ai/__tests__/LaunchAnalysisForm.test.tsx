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
 *  - Identidad IA (contracts/ai-identity.md §1, §4): botón usa el verbo
 *    compartido "Analizar con IA" (regresión contra "Analizar deportista",
 *    hallado en QA de spec 033 — este control no estaba en el rename table
 *    original pero es un launch control real); se deshabilita y muestra
 *    AIBudgetHint cuando budget_status="exhausted".
 *  - T091 (036/US6): chips y checkbox de revisión paso a paso miden ≥48×48.
 *  - T092 (036/US6): el checkbox queda junto a su etiqueta, no en el borde.
 *  - T096b (036/US6): microcopy "Revisión paso a paso" / "Máximo 4 a la vez".
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

// useAIStatus (contracts/ai-identity.md §4) — sin datos por defecto:
// degradación reactiva-only, igual que en AnalyzeAthleteButton.test.tsx.
let mockAIStatusData:
  | { budget_status: "ok" | "warning" | "exhausted"; budget_remaining_pct: number; concurrency_available: boolean; est_wait_seconds: number }
  | undefined;

vi.mock("@/hooks/ai/useAIStatus", () => ({
  useAIStatus: () => ({ data: mockAIStatusData }),
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
    mockAIStatusData = undefined;
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

  // ---------------------------------------------------------------------------
  // T031 (feature 036) — dos carreras del mismo series_kind deben ser
  // identificables sin ambigüedad. RaceParticipationOption documenta que
  // "para campeonatos siempre es 1" el sequence_number, así que dos
  // Campeonatos Departamentales en la misma temporada chocan exactamente
  // en el dato que antes distinguía los chips ("CD" a secas, sin fecha).
  // ---------------------------------------------------------------------------
  it("dos Campeonatos Departamentales en la misma temporada se distinguen por fecha", async () => {
    mockRaces({
      season: YEAR,
      items: [
        {
          event_id: 1,
          sequence_number: 1,
          series_kind: "cup",
          event_date: `${YEAR}-01-31`,
          event_name: "V1",
          location: "Sevilla",
          label: "Válida 1",
        },
        {
          // Primer Cto. Departamental — mismo sequence_number=1 que el segundo.
          event_id: 99,
          sequence_number: 1,
          series_kind: "championship",
          event_date: `${YEAR}-06-12`,
          event_name: "Campeonato Departamental — Ginebra",
          location: "Ginebra",
          label: "Cto. Dep. — Ginebra",
        },
        {
          // Segundo Cto. Departamental de la misma temporada (reprogramado
          // o de otra subcategoría) — el bug reportado: sin fecha, ambos
          // chips se ven idénticos ("CD") y el coach no puede diferenciarlos.
          event_id: 150,
          sequence_number: 1,
          series_kind: "championship",
          event_date: `${YEAR}-11-20`,
          event_name: "Campeonato Departamental — Palmira",
          location: "Palmira",
          label: "Cto. Dep. — Palmira",
        },
      ],
    });
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );

    const firstChampionship = await screen.findByTestId("launch-event-99");
    const secondChampionship = await screen.findByTestId("launch-event-150");

    // Ambos siguen rotulados "CD" (mismo series_kind)…
    expect(firstChampionship).toHaveTextContent("CD");
    expect(secondChampionship).toHaveTextContent("CD");
    // …pero el texto visible completo ya no es idéntico: cada uno lleva su
    // propia fecha, así el coach puede distinguirlos sin depender del title.
    expect(firstChampionship.textContent).not.toBe(
      secondChampionship.textContent,
    );
    expect(firstChampionship).toHaveTextContent("12 jun");
    expect(secondChampionship).toHaveTextContent("20 nov");
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

  it("muestra error de servidor en submit fallido (detail verbatim, no el status genérico)", async () => {
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
    // T045: el detail del backend, no "Request failed with status code 403".
    expect(
      await screen.findByText("Sin permisos para lanzar análisis"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/request failed with status code/i),
    ).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // T045 — AxiosError extiende Error, así que la rama genérica
  // `err instanceof Error` atrapaba el 409 antes de llegar al `detail` real.
  // Los dos 409 nuevos de Wave 2/Foundation (run activo, dedup resumen de
  // temporada) dependen de que este mensaje SÍ llegue al coach.
  // ---------------------------------------------------------------------------
  it("T045: un 409 con detail JSON expone el detail verbatim, no el status genérico", async () => {
    mockRaces();
    mswServer.use(
      http.post(
        "*/api/athletes/:athleteId/race-analysis/runs",
        () =>
          new HttpResponse(
            JSON.stringify({
              detail: "Ya hay un análisis en curso para esta válida.",
            }),
            { status: 409, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );
    await screen.findByTestId("launch-event-1");
    await user.click(screen.getByTestId("launch-submit"));

    expect(
      await screen.findByText("Ya hay un análisis en curso para esta válida."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/request failed with status code 409/i),
    ).not.toBeInTheDocument();
  });

  it("carreras: error 500 muestra ErrorState en vez de 'sin carreras registradas'", async () => {
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/races",
        () =>
          new HttpResponse(
            JSON.stringify({ detail: "Error interno" }),
            { status: 500, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );
    // No debe afirmar falsamente que no hay carreras registradas: el fetch
    // falló, no es que la temporada esté vacía (US5 — truth on screen).
    expect(
      await screen.findByText(/no se pudieron cargar las carreras/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("launch-races-empty")).not.toBeInTheDocument();
  });

  it("carreras: un fallo de red (forma cold-start) muestra la copy calmada, no un error alarmante", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/races", () =>
        HttpResponse.error(),
      ),
    );
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );
    // Una petición sin respuesta (Render Free despertando o red caída) es
    // indistinguible desde el cliente — ErrorState usa `role="status"` y
    // tono calmado en vez de la alarma roja genérica de "carreras".
    expect(
      await screen.findByText(/la aplicación está iniciando/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/no se pudieron cargar las carreras/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("launch-races-empty")).not.toBeInTheDocument();
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
  // Identidad IA (contracts/ai-identity.md §1, §4)
  // ---------------------------------------------------------------------------
  describe("identidad IA compartida", () => {
    it('el botón usa el verbo compartido "Analizar con IA", no "Analizar deportista"', async () => {
      mockRaces();
      renderWithProviders(
        <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
      );
      await screen.findByTestId("launch-event-1");
      const submit = screen.getByTestId("launch-submit");
      expect(submit).toHaveTextContent("Analizar con IA");
      expect(submit).not.toHaveTextContent("Analizar deportista");
    });

    it("presupuesto agotado deshabilita el submit y muestra AIBudgetHint", async () => {
      mockAIStatusData = {
        budget_status: "exhausted",
        budget_remaining_pct: 0,
        concurrency_available: true,
        est_wait_seconds: 0,
      };
      mockRaces();
      renderWithProviders(
        <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
      );
      await screen.findByTestId("launch-event-1");
      expect(screen.getByTestId("launch-submit")).toBeDisabled();
      expect(
        screen.getByTestId("ai-budget-hint-exhausted"),
      ).toBeInTheDocument();
    });

    it("presupuesto ok no muestra hint bloqueante y deja el submit habilitado", async () => {
      mockAIStatusData = {
        budget_status: "ok",
        budget_remaining_pct: 90,
        concurrency_available: true,
        est_wait_seconds: 0,
      };
      mockRaces();
      renderWithProviders(
        <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
      );
      await screen.findByTestId("launch-event-1");
      expect(screen.getByTestId("launch-submit")).not.toBeDisabled();
      expect(
        screen.queryByTestId("ai-budget-hint-exhausted"),
      ).not.toBeInTheDocument();
    });
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

    it("no tiene violaciones a11y con un chip en estado cap-reached (disabled)", async () => {
      mockRaces();
      const user = userEvent.setup();
      const { container } = renderWithProviders(
        <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
      );
      await user.click(await screen.findByTestId("launch-event-1"));
      await user.click(screen.getByTestId("launch-event-2"));
      await user.click(screen.getByTestId("launch-event-3"));
      await user.click(screen.getByTestId("launch-event-4"));
      await waitFor(() =>
        expect(screen.getByTestId("launch-event-5")).toBeDisabled(),
      );
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  // ---------------------------------------------------------------------------
  // T091 [US6] — piso táctil de 48×48px (frontend/e2e/target-size.spec.ts:44).
  // jsdom no calcula layout real (sin motor de render), así que se afirma
  // sobre las clases Tailwind que fijan el tamaño mínimo — mismo patrón que
  // `session-plan/TechniqueAttachPicker.tsx` (feature 032) ya probó en real:
  // el propio elemento interactivo mide 48×48, no solo un envoltorio.
  // ---------------------------------------------------------------------------
  describe("piso táctil 48×48 (T091)", () => {
    it("los chips de carreras miden al menos 48×48 (antes: min-h-9 = 36px)", async () => {
      mockRaces();
      renderWithProviders(
        <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
      );
      const chip = await screen.findByTestId("launch-event-1");
      expect(chip).toHaveClass("min-h-12");
      expect(chip).toHaveClass("min-w-12");
      expect(chip).not.toHaveClass("min-h-9");
    });

    it("el checkbox de revisión paso a paso mide al menos 48×48 (antes: h-5 w-5 = 20px)", async () => {
      mockRaces();
      renderWithProviders(
        <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
      );
      await screen.findByTestId("launch-event-1");
      const checkbox = screen.getByTestId("launch-explain-switch");
      expect(checkbox).toHaveClass("h-12");
      expect(checkbox).toHaveClass("w-12");
      expect(checkbox).not.toHaveClass("h-5");
    });
  });

  // ---------------------------------------------------------------------------
  // T092 [US6] — el checkbox debe quedar junto al texto que gobierna, no
  // empujado al borde derecho por un `justify-between` a lo ancho del card.
  // ---------------------------------------------------------------------------
  it("T092: el checkbox de revisión paso a paso está junto a su etiqueta, no en el borde", async () => {
    mockRaces();
    renderWithProviders(
      <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
    );
    await screen.findByTestId("launch-event-1");
    const checkbox = screen.getByTestId("launch-explain-switch");
    // La fila que envuelve al checkbox comparte contenedor con el título
    // corto ("Revisión paso a paso") y NO con la descripción larga, que
    // vive en un bloque aparte debajo — así el checkbox queda pegado al
    // texto que gobierna en vez de separado por todo el ancho del card.
    const row = checkbox.closest("span");
    expect(row).not.toBeNull();
    expect(row).toHaveTextContent("Revisión paso a paso");
    expect(row).not.toHaveTextContent("El análisis se detendrá");
  });

  // ---------------------------------------------------------------------------
  // T096b [US6] — microcopy: "Modo explicativo" → "Revisión paso a paso";
  // "Máximo 4 por lanzamiento" → "Máximo 4 a la vez".
  // ---------------------------------------------------------------------------
  describe("microcopy T096b", () => {
    it('usa "Revisión paso a paso" y retira "Modo explicativo"', async () => {
      mockRaces();
      renderWithProviders(
        <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
      );
      await screen.findByTestId("launch-event-1");
      expect(screen.getByText("Revisión paso a paso")).toBeInTheDocument();
      expect(
        screen.getByText(
          "El análisis se detendrá en cada etapa para que lo apruebes antes de continuar.",
        ),
      ).toBeInTheDocument();
      expect(screen.queryByText("Modo explicativo")).not.toBeInTheDocument();
      expect(
        screen.queryByText(/el agente pausará/i),
      ).not.toBeInTheDocument();
    });

    it('usa "Máximo 4 a la vez" y retira "Máximo 4 por lanzamiento"', async () => {
      mockRaces();
      renderWithProviders(
        <LaunchAnalysisForm athleteId={42} athleteName="Test User" />,
      );
      await screen.findByTestId("launch-event-1");
      expect(screen.getByText(/máximo 4 a la vez/i)).toBeInTheDocument();
      expect(
        screen.queryByText(/máximo 4 por lanzamiento/i),
      ).not.toBeInTheDocument();
    });
  });
});
