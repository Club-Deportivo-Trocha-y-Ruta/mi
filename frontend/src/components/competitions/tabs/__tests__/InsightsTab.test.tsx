/**
 * Tests vitest — InsightsTab (tab "Insights IA" del detalle de la competencia).
 *
 * Tras eliminar el strangler `VITE_INSIGHTS_IN_COMPETITION`, el tab SIEMPRE
 * renderiza el grid scopeado a la válida (`ClubInsightsGrid`) — nunca el hub
 * RaceAnalysisPage. Estos tests fijan ese comportamiento.
 *
 * Cubre:
 *  - Renderiza el grid scopeado (data-testid="insights-tab") con cards.
 *  - Click en una card navega al perfil del atleta scopeado (no al hub).
 *  - Empty state cuando la válida no tiene insights.
 *  - T011 (feature 010): GroupAnalysisPanel visible para coach/admin,
 *    oculto para parent.
 *  - AthleteLink (specs/028): la card con insight enlaza a /athletes/:id
 *    solo para coach; admin ve el mismo contenido sin navegación (evita el
 *    rebote silencioso de ProtectedRoute — `/athletes/:id` es coach-only).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { axe } from "jest-axe";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual =
    await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// `vi.hoisted` corre antes de que los imports se resuelvan — mismo patrón
// que MeasurementAlerts.test.tsx / AthleteLink.test.tsx para alternar el rol
// entre tests del mismo archivo sin remockear el módulo completo. Default
// "coach" porque los tests preexistentes de este archivo asumen que la card
// con insight es navegable (AthleteLink solo habilita el <Link> para coach —
// ver src/components/shared/AthleteLink.tsx).
const authState = vi.hoisted(() => ({
  role: "coach" as string | undefined,
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (s: { user: { id: number; role: string | undefined } | null }) => unknown,
  ) => selector({ user: { id: 1, role: authState.role } }),
}));

const mockUseClubInsightsByRace = vi.fn();
vi.mock("@/hooks/athletes/useClubInsightsByRace", () => ({
  useClubInsightsByRace: (...args: unknown[]) =>
    mockUseClubInsightsByRace(...args),
}));

// GroupAnalysisPanel — mock to isolate from its hook dependencies.
vi.mock(
  "@/components/competitions/insights/GroupAnalysisPanel",
  () => ({
    GroupAnalysisPanel: ({ raceEventId }: { raceEventId: number }) => (
      <div data-testid="group-analysis-panel" data-race-event-id={raceEventId} />
    ),
  }),
);

// CompetitionChatPanel — mock to isolate from its API dependencies.
vi.mock(
  "@/components/competitions/chat/CompetitionChatPanel",
  () => ({
    CompetitionChatPanel: ({ raceEventId }: { raceEventId: number }) => (
      <div data-testid="competition-chat-panel" data-race-event-id={raceEventId} />
    ),
  }),
);

import { InsightsTab } from "@/components/competitions/tabs/InsightsTab";

/**
 * Muestra pathname+search actuales — permite verificar navegación (o su
 * ausencia) tras un click sin depender del contenido de la página. Mismo
 * patrón que AthleteLink.test.tsx.
 */
function LocationDisplay() {
  const location = useLocation();
  return (
    <div data-testid="location-display">
      {location.pathname + location.search}
    </div>
  );
}

function renderTab(
  raceEventId = 5,
  opts: { hasResults?: boolean; isCoachOrAdmin?: boolean } = {},
) {
  return render(
    <MemoryRouter>
      <LocationDisplay />
      <InsightsTab
        raceEventId={raceEventId}
        hasResults={opts.hasResults ?? false}
        isCoachOrAdmin={opts.isCoachOrAdmin ?? false}
      />
    </MemoryRouter>,
  );
}

const INSIGHTS = {
  data: {
    race_event_id: 5,
    race_event_label: "Válida IV — Cali",
    total_athletes: 2,
    items: [
      {
        athlete_id: 145,
        athlete_display_name: "Isabel Quinonez",
        valida_num: 4,
        insight_id: 99,
        summary_excerpt: "Tercer lugar, progreso en frenada.",
        generated_at: "2026-05-25T19:49:00",
        confidence: "medium",
      },
      {
        athlete_id: 201,
        athlete_display_name: "Mateo Perez",
        valida_num: 4,
        insight_id: null,
        summary_excerpt: null,
        generated_at: null,
        confidence: null,
      },
    ],
  },
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
  authState.role = "coach";
});

describe("InsightsTab (siempre grid scopeado, sin flag)", () => {
  it("scopea la query a la válida recibida por props", () => {
    mockUseClubInsightsByRace.mockReturnValue(INSIGHTS);
    renderTab(5);
    // Primer argumento del hook = raceEventId scopeado.
    expect(mockUseClubInsightsByRace).toHaveBeenCalledWith(
      5,
      expect.objectContaining({ latestOnly: true }),
    );
  });

  it("renderiza el grid scopeado con las cards de la válida", () => {
    mockUseClubInsightsByRace.mockReturnValue(INSIGHTS);
    renderTab(5);
    expect(screen.getByTestId("insights-tab")).toBeInTheDocument();
    expect(screen.getByTestId("insights-tab-card-145")).toBeInTheDocument();
    expect(screen.getByText(/1 de 2 atletas con análisis IA/i)).toBeInTheDocument();
    // NO debe montar el hub viejo (no hay tabs "Nuevo análisis"/"Cargar resultados").
    expect(screen.queryByText(/nuevo análisis/i)).not.toBeInTheDocument();
  });

  it("click en una card navega al perfil del atleta (scopeado, no al hub)", async () => {
    // Rol coach (default del beforeEach) — AthleteLink habilita el <Link>.
    mockUseClubInsightsByRace.mockReturnValue(INSIGHTS);
    const user = userEvent.setup();
    renderTab(5);
    // Patrón "stretched link" (T-insights-redesign): el <a> de AthleteLink
    // envuelve solo el nombre (no toda la card) y su `after:inset-0` es lo
    // que estira el área clickable en el navegador real; en jsdom no hay
    // hit-testing por CSS, así que el test apunta directo al link.
    const card = screen.getByTestId("insights-tab-card-145");
    const link = within(card).getByRole("link", { name: "Isabel Quinonez" });
    expect(link).toHaveAttribute("href", "/athletes/145?tab=ai_analysis");
    await user.click(link);
    expect(screen.getByTestId("location-display")).toHaveTextContent(
      "/athletes/145?tab=ai_analysis",
    );
  });

  it("muestra empty state cuando la válida no tiene insights", () => {
    mockUseClubInsightsByRace.mockReturnValue({
      data: { race_event_id: 5, total_athletes: 0, items: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab(5);
    expect(screen.getByTestId("insights-tab")).toBeInTheDocument();
    expect(
      screen.getByText(/No hay insights generados para esta válida/i),
    ).toBeInTheDocument();
  });

  it("un error 503 (cold start) muestra la copy calmada, no el tono de error", () => {
    mockUseClubInsightsByRace.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("Request failed with status code 503"),
      refetch: vi.fn(),
    });
    renderTab(5);
    expect(screen.getByTestId("insights-tab")).toBeInTheDocument();
    expect(
      screen.getByText(/la aplicación está iniciando/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No se pudieron cargar los insights. Intenta de nuevo."),
    ).not.toBeInTheDocument();
  });

  it("un error real (no cold start) muestra la copy de error con 'Intenta de nuevo'", () => {
    mockUseClubInsightsByRace.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("Error de validación"),
      refetch: vi.fn(),
    });
    renderTab(5);
    expect(
      screen.getByText("No se pudieron cargar los insights. Intenta de nuevo."),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// T011 (feature 010) — GroupAnalysisPanel visibility by role
// ---------------------------------------------------------------------------

describe("InsightsTab — GroupAnalysisPanel visibilidad por rol (T011)", () => {
  beforeEach(() => {
    // Use a non-empty response so the grid renders without errors.
    mockUseClubInsightsByRace.mockReturnValue({
      data: { race_event_id: 5, total_athletes: 0, items: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
  });

  it("coach ve el GroupAnalysisPanel", () => {
    renderTab(5, { isCoachOrAdmin: true, hasResults: true });
    expect(screen.getByTestId("group-analysis-panel")).toBeInTheDocument();
  });

  it("admin ve el GroupAnalysisPanel", () => {
    renderTab(5, { isCoachOrAdmin: true, hasResults: false });
    expect(screen.getByTestId("group-analysis-panel")).toBeInTheDocument();
  });

  it("parent NO ve el GroupAnalysisPanel", () => {
    renderTab(5, { isCoachOrAdmin: false });
    expect(
      screen.queryByTestId("group-analysis-panel"),
    ).not.toBeInTheDocument();
  });

  it("GroupAnalysisPanel recibe el raceEventId correcto", () => {
    renderTab(42, { isCoachOrAdmin: true, hasResults: true });
    const panel = screen.getByTestId("group-analysis-panel");
    expect(panel).toHaveAttribute("data-race-event-id", "42");
  });
});

// ---------------------------------------------------------------------------
// AthleteLink (specs/028) — enlace al detalle del atleta según rol.
//
// `/athletes/:id` está restringido a UserRole.coach (ver App.tsx); antes de
// adoptar AthleteLink, la card completa navegaba ahí vía un div
// role="button" + onClick sin mirar el rol, y ProtectedRoute rebotaba a
// admin en silencio de vuelta al dashboard. Mismo patrón de aserciones que
// MeasurementAlerts.test.tsx / AthleteLink.test.tsx.
// ---------------------------------------------------------------------------

describe("InsightsTab — enlace al detalle del atleta según rol (AthleteLink)", () => {
  it("coach: la card de un atleta con insight es un link funcional a /athletes/{id}", () => {
    authState.role = "coach";
    mockUseClubInsightsByRace.mockReturnValue(INSIGHTS);
    renderTab(5);

    const card = screen.getByTestId("insights-tab-card-145");
    const link = within(card).getByRole("link", { name: "Isabel Quinonez" });
    expect(link).toHaveAttribute("href", "/athletes/145?tab=ai_analysis");
  });

  it('admin: la card de un atleta con insight NO es un link (evita rebote de ProtectedRoute en "/athletes/:id")', async () => {
    authState.role = "admin";
    mockUseClubInsightsByRace.mockReturnValue(INSIGHTS);
    const user = userEvent.setup();
    renderTab(5);

    // Ningún link en todo el grid (ni la card con insight, ni la de "sin análisis").
    expect(screen.queryAllByRole("link")).toHaveLength(0);

    const card = screen.getByTestId("insights-tab-card-145");
    expect(card.closest("a")).toBeNull();
    // El contenido sigue visible como texto plano, solo que no navegable.
    expect(screen.getByText("Isabel Quinonez")).toBeInTheDocument();

    // Click no navega (sin href, sin cambio de ruta).
    await user.click(card);
    expect(screen.getByTestId("location-display")).toHaveTextContent("/");
  });

  it("admin: el resto de la card (badges, resumen) sigue visible sin navegación", () => {
    authState.role = "admin";
    mockUseClubInsightsByRace.mockReturnValue(INSIGHTS);
    renderTab(5);

    expect(
      screen.getByText(/Tercer lugar, progreso en frenada\./),
    ).toBeInTheDocument();
  });

  it("card sin insight aún (sin análisis) nunca es un link, ni para coach ni para admin", () => {
    authState.role = "coach";
    mockUseClubInsightsByRace.mockReturnValue(INSIGHTS);
    renderTab(5);

    // Atleta 201 no tiene insight_id → no es clickable independientemente del rol.
    const card = screen.getByTestId("insights-tab-card-201");
    expect(card.closest("a")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Rediseño del grid (excerpt en texto plano, orden, a11y) — ver
// src/lib/markdownExcerpt.ts para la limpieza de markdown.
// ---------------------------------------------------------------------------

const MIXED_ORDER = {
  data: {
    race_event_id: 5,
    race_event_label: "Válida IV — Cali",
    total_athletes: 2,
    items: [
      // Pendiente primero en el orden del backend — debe renderizar
      // DESPUÉS del analizado (orden: analizados primero).
      {
        athlete_id: 301,
        athlete_display_name: "Pendiente Uno",
        valida_num: 4,
        insight_id: null,
        summary_excerpt: null,
        generated_at: null,
        confidence: null,
      },
      {
        athlete_id: 145,
        athlete_display_name: "Isabel Quinonez",
        valida_num: 4,
        insight_id: 99,
        summary_excerpt: "## Hallazgo principal\nEl bajón **táctico** del cierre.",
        generated_at: "2026-05-25T19:49:00",
        confidence: "medium",
      },
    ],
  },
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
};

describe("InsightsTab — excerpt en texto plano (markdown crudo limpio)", () => {
  it("no renderiza el markdown crudo del excerpt (sin '##', sin '**', sin el título del header)", () => {
    mockUseClubInsightsByRace.mockReturnValue(MIXED_ORDER);
    renderTab(5);
    const card = screen.getByTestId("insights-tab-card-145");
    expect(card).toHaveTextContent("El bajón táctico del cierre.");
    expect(card.textContent).not.toContain("##");
    expect(card.textContent).not.toContain("**");
    expect(card.textContent).not.toContain("Hallazgo principal");
  });
});

describe("InsightsTab — orden de cards (analizados primero)", () => {
  it("ordena las cards con análisis antes que las pendientes, sin importar el orden del backend", () => {
    mockUseClubInsightsByRace.mockReturnValue(MIXED_ORDER);
    renderTab(5);
    const cards = screen.getAllByRole("article");
    expect(cards.map((el) => el.getAttribute("data-testid"))).toEqual([
      "insights-tab-card-145",
      "insights-tab-card-301",
    ]);
  });
});

describe("InsightsTab — accesibilidad (T-insights-redesign)", () => {
  it("jest-axe: 0 violaciones con una mezcla de cards pendientes y analizadas", async () => {
    mockUseClubInsightsByRace.mockReturnValue(MIXED_ORDER);
    const { container } = renderTab(5);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
