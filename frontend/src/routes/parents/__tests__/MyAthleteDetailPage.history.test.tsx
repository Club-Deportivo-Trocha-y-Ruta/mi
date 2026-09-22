/**
 * MyAthleteDetailPage — tab "Carreras" del padre/acudiente (feature 044,
 * US7, T082/T079).
 *
 * Reutiliza `HistoryProgressionCard` (misma tarjeta que el coach ve en
 * `AthleteDetailPage.tsx`, tab "Carreras") con `audience="family"` — este
 * archivo NO repite la cobertura de estados carga/error/vacío ya cubierta en
 * `components/race/history/__tests__/HistoryProgressionCard.test.tsx`; se
 * enfoca en lo específico de esta página:
 *
 *  - el tab existe y monta la tarjeta con `audience="family"` (nunca
 *    "coach"), scopeada al atleta de la ruta;
 *  - la redacción familiar del cambio de categoría es la NEUTRAL decidida en
 *    la revisión UX (`HistoryTable.tsx`'s "Cambió de categoría…"), nunca la
 *    de `tasks.md` ("Subió de categoría… deportistas mayores… el puesto
 *    baje" — ver el override documentado ahí en T082);
 *  - ningún dato de un tercero (otro atleta/competidor) aparece en el DOM —
 *    la tarjeta solo consume los puntos propios del atleta de la ruta;
 *  - "texto primero": chips de temporada + últimos resultados están en el
 *    DOM antes de que el chunk lazy de la gráfica termine de montar;
 *  - jest-axe sin violaciones.
 *
 * `HistoryChart` se mockea como stand-in liviano — igual que
 * `HistoryProgressionCard.test.tsx` — para no arrastrar recharts real acá
 * (ya cubierto en `HistoryChart.test.tsx`).
 *
 * Privacidad Ley 1581: fixtures 100% sintéticas, ningún atleta real.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";
import { http, HttpResponse } from "msw";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Mocks — deben declararse antes de los imports de producción
// ---------------------------------------------------------------------------

vi.mock("@/hooks/athletes/useAthlete", () => ({
  useAthlete: vi.fn(),
}));

vi.mock("@/hooks/athletes/useAnthropometry", () => ({
  useAnthropometry: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 20, role: "parent", first_name: "Padre", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

// `HistoryChart` es el único subcomponente mockeado (stand-in liviano, igual
// que `HistoryProgressionCard.test.tsx`) — todo lo demás de la tarjeta
// (chips, tabla, nota de cambio de categoría, caveats) corre real.
vi.mock("@/components/race/history/HistoryChart", () => ({
  HistoryChart: ({ points }: { points: unknown[] }) => (
    <div data-testid="mock-history-chart" data-count={points.length} />
  ),
}));

// Sub-componentes pesados ajenos al objeto de este archivo — mismo criterio
// que `MyAthleteDetailPage.test.tsx` / `MyAthleteDetailPage.activities.test.tsx`.
vi.mock("@/components/athletes/AthleteInfoCard", () => ({
  AthleteInfoCard: () => <div data-testid="athlete-info-card">InfoCard</div>,
}));
vi.mock("@/components/athletes/ai/AthleteAIAnalysisTab", () => ({
  AthleteAIAnalysisTab: () => <div data-testid="mock-ai-analysis-tab" />,
}));

// ---------------------------------------------------------------------------
// Imports de producción (después de los mocks)
// ---------------------------------------------------------------------------

import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { MyAthleteDetailPage } from "../MyAthleteDetailPage";
import { mswServer } from "@/test/setup";
import {
  raceHistoryHandlers,
  raceHistoryEmptyHandler,
  makeAthleteRaceHistoryRead,
  makeRaceHistoryPoint,
} from "@/test/msw/raceHistoryHandlers";
import { growthSummaryHandlers } from "@/test/msw/growthSummaryHandlers";
import { Sex } from "@/types/enums";
import type { AthleteDetailOut } from "@/types/athlete.types";

// ---------------------------------------------------------------------------
// Fixtures — DATOS FICTICIOS. Nunca datos reales de atletas menores.
// ---------------------------------------------------------------------------

const MY_ATHLETE_ID = 42;

const mockAthlete: AthleteDetailOut = {
  id: MY_ATHLETE_ID,
  user_id: 100,
  first_name: "Valentina",
  last_name: "Ficticia",
  birth_date: "2012-06-15",
  sex: Sex.M,
  club_join_date: "2023-01-01",
  years_in_club: 2.3,
  age_decimal: 13.5,
  category: "Sub-15",
  club_id: 1,
  created_at: "2023-01-01T00:00:00Z",
  latest_anthropometry: null,
};

function mockHooks() {
  vi.mocked(useAthlete).mockReturnValue({
    data: mockAthlete,
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useAthlete>);

  vi.mocked(useAnthropometry).mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useAnthropometry>);
}

// ---------------------------------------------------------------------------
// Helpers de render
// ---------------------------------------------------------------------------

function renderAthletePage(athleteId: number = MY_ATHLETE_ID) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <MemoryRouter initialEntries={[`/my-athletes/${athleteId}`]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/my-athletes/:id" element={<MyAthleteDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

async function openRacesTab() {
  const user = userEvent.setup();
  const tab = await screen.findByTestId("parent-tab-races");
  await user.click(tab);
  return screen.findByTestId("history-progression-card");
}

// ---------------------------------------------------------------------------
// Suites
// ---------------------------------------------------------------------------

describe("MyAthleteDetailPage — tab Carreras (padre, feature 044, US7)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHooks();
    mswServer.use(...raceHistoryHandlers, ...growthSummaryHandlers);
  });

  it("renderiza el botón de tab 'Carreras' para el padre", async () => {
    renderAthletePage();
    expect(await screen.findByTestId("parent-tab-races")).toHaveTextContent(/carreras/i);
  });

  it("click en 'Carreras' monta HistoryProgressionCard con audience='family', scopeada al atleta de la ruta", async () => {
    renderAthletePage();
    await openRacesTab();

    // La tarjeta pide el historial del atleta de la ruta, no un id fijo.
    await screen.findByTestId("season-completion-chips");
    expect(screen.getByTestId("history-latest-three")).toBeInTheDocument();

    // audience="family": la nota de cambio de categoría usa la redacción
    // NEUTRAL decidida en la revisión UX (override T082) — nunca "coach".
    // T083: desde la vista mobile de tarjetas, la misma nota vive dos veces
    // en el DOM (desktop + mobile, toggle puramente CSS) — se escopea al
    // testid desktop (sin sufijo "mobile") para un único match.
    const note = await screen.findByTestId(
      /^history-family-category-note-(?!mobile-)/,
    );
    expect(note).toHaveTextContent(
      /Cambió de categoría \(de INFANTIL B a PREJUVENIL A\)\. En la nueva categoría compite con otro grupo, así que el puesto no se compara directamente con el anterior\./,
    );
  });

  it("NO usa la redacción descartada por la revisión UX ('Subió de categoría', 'deportistas mayores', 'el puesto baje')", async () => {
    renderAthletePage();
    const card = await openRacesTab();

    const text = card.textContent ?? "";
    expect(text).not.toMatch(/subió de categoría/i);
    expect(text).not.toMatch(/deportistas mayores/i);
    expect(text).not.toMatch(/el puesto baje/i);
    // Tampoco lenguaje comparativo sobre el hijo/a (mejor/peor que, rankings
    // entre atletas del club) — contrato `ui-history.md` §1, variante family.
    expect(text).not.toMatch(/mejor que|peor que|más rápido que|más lento que/i);
  });

  it("no expone ningún dato de un tercero (otro atleta o competidor) — solo los puntos propios del atleta de la ruta", async () => {
    renderAthletePage();
    const card = await openRacesTab();

    await waitFor(() =>
      expect(screen.getByTestId("mock-history-chart")).toBeInTheDocument(),
    );

    // El fixture de `raceHistoryHandlers` solo trae puntos del propio
    // atleta (contrato: el endpoint es `.../athletes/{athleteId}/...`, sin
    // `competitor_id` en la respuesta) — la tarjeta no agrega nombres de
    // otros deportistas ni de otro club a lo que el backend devuelve.
    const text = card.textContent ?? "";
    expect(text).not.toMatch(/competitor_id/i);
    expect(text).not.toMatch(/club rival|otro club|otro atleta/i);
  });

  it("texto primero: chips y últimos resultados están en el DOM antes de que el chunk lazy de la gráfica termine de montar", async () => {
    renderAthletePage();
    await openRacesTab();

    // No esperamos a la gráfica: el bloque de texto ya debe estar presente.
    expect(screen.getByTestId("season-completion-chips")).toBeInTheDocument();
    expect(screen.getByTestId("history-latest-three").querySelectorAll("li")).toHaveLength(3);

    await waitFor(() =>
      expect(screen.getByTestId("mock-history-chart")).toBeInTheDocument(),
    );
  });

  it("estado vacío: mensaje dedicado, sin chips/tabla/gráfica", async () => {
    mswServer.use(raceHistoryEmptyHandler);
    renderAthletePage();
    await openRacesTab();

    expect(await screen.findByTestId("history-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("season-completion-chips")).not.toBeInTheDocument();
    expect(screen.queryByTestId("history-table")).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad (jest-axe) con datos cargados", async () => {
    const { container } = renderAthletePage();
    await openRacesTab();
    await screen.findByTestId("season-completion-chips");
    await waitFor(() =>
      expect(screen.getByTestId("mock-history-chart")).toBeInTheDocument(),
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("consulta el historial del atleta de la ruta (propio hijo), no un id fijo", async () => {
    let requestedAthleteId: string | undefined;
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/history",
        ({ params }) => {
          requestedAthleteId = params.athleteId as string;
          return HttpResponse.json(makeAthleteRaceHistoryRead());
        },
      ),
    );

    renderAthletePage(MY_ATHLETE_ID);
    await openRacesTab();

    expect(requestedAthleteId).toBe(String(MY_ATHLETE_ID));
  });

  // ---------------------------------------------------------------------
  // T083 (ux-review.md) — tono cálido, explicador de métricas y la
  // bifurcación de FR-042 por `category_change_kind`.
  // ---------------------------------------------------------------------

  it("tono cálido: dice 'tu hijo o hija' en el subtítulo, nunca 'el atleta' (T083 MINOR) — sin enhebrar el nombre real", async () => {
    renderAthletePage();
    const card = await openRacesTab();

    expect(card).toHaveTextContent(/tu hijo o hija/i);
    expect(card.textContent).not.toMatch(/el atleta/i);
    // El nombre real del menor (fixture: "Valentina") nunca se enhebra acá.
    expect(card.textContent).not.toMatch(/valentina/i);
  });

  it("explicador familiar de Percentil/Brecha a la mediana está presente (T083 MAJOR)", async () => {
    renderAthletePage();
    const card = await openRacesTab();

    const explainer = within(card).getByTestId("history-family-metrics-explainer");
    expect(explainer).toHaveTextContent(/percentil/i);
    expect(explainer).toHaveTextContent(/brecha a la mediana/i);
  });

  it("no muestra el tag corto de cambio de categoría — es exclusivo de la vista coach", async () => {
    renderAthletePage();
    const card = await openRacesTab();

    expect(
      within(card).queryByTestId(/history-category-change-tag-/),
    ).not.toBeInTheDocument();
  });

  it("category_change_kind='promotion': explica el ascenso con la redacción exacta acordada con el líder", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/history", () =>
        HttpResponse.json(
          makeAthleteRaceHistoryRead({
            points: [
              makeRaceHistoryPoint({
                event_id: 41,
                event_date: "2025-02-09",
                season: 2025,
                category_label: "PREJUVENIL A",
                category_changed: true,
                previous_category_label: "INFANTIL B",
                category_change_kind: "promotion",
              }),
            ],
            seasons: [{ season: 2025, started: 1, finished: 1 }],
          }),
        ),
      ),
    );

    renderAthletePage();
    const card = await openRacesTab();

    const note = await within(card).findByTestId(
      /^history-family-category-note-(?!mobile-)/,
    );
    expect(note).toHaveTextContent(
      "Subió de categoría: ahora corre con deportistas mayores. Es normal que el puesto baje al comienzo.",
    );
  });
});
