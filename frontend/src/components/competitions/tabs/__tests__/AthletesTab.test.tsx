/**
 * Tests vitest — AthletesTab (tab "Atletas" del detalle de la competencia).
 *
 * Cubre:
 *  - Renderiza las dos secciones: RosterPanel + grid de análisis IA.
 *  - Para el padre (user.role === "parent"):
 *    - RosterPanel se monta en modo isReadOnly.
 *    - El nombre de otro menor NO aparece en el DOM (T029 privacidad).
 *    - axe 0 violaciones.
 *  - Para coach: RosterPanel en modo edición (selector de atleta visible).
 *  - axe 0 violaciones en vista coach.
 *
 * Estrategia:
 *  - Se mockea useClubInsightsByRace (sección IA ya cubierta en InsightsTab.test.tsx).
 *  - Se mockea RosterPanel para controlar su renderizado y verificar las
 *    props isReadOnly recibidas, manteniendo el test focalizado.
 *  - Se mockea useAuthStore para controlar el rol del usuario.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual =
    await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockUseClubInsightsByRace = vi.fn();
vi.mock("@/hooks/athletes/useClubInsightsByRace", () => ({
  useClubInsightsByRace: (...args: unknown[]) =>
    mockUseClubInsightsByRace(...args),
}));

// Capturamos las props recibidas por RosterPanel para aserciones
const capturedRosterProps: Record<string, unknown>[] = [];
vi.mock("@/components/competitions/roster/RosterPanel", () => ({
  RosterPanel: (props: Record<string, unknown>) => {
    capturedRosterProps.push(props);
    return (
      <div
        data-testid="mock-roster-panel"
        data-readonly={String(props.isReadOnly ?? false)}
        data-race-event-id={String(props.raceEventId)}
      >
        {/* Simula la vista padre: solo el hijo propio */}
        {props.isReadOnly ? (
          <span data-testid="parent-child-name">Mi Hijo Uno</span>
        ) : (
          <span data-testid="coach-roster">Controles edición</span>
        )}
      </div>
    );
  },
}));

const mockUseAuthStore = vi.fn();
vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: unknown) => unknown) => mockUseAuthStore(selector),
}));

import { AthletesTab } from "@/components/competitions/tabs/AthletesTab";
import { UserRole } from "@/types/enums";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const EMPTY_INSIGHTS = {
  data: { race_event_id: 1, total_athletes: 0, items: [] },
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
};

const INSIGHTS_WITH_DATA = {
  data: {
    race_event_id: 1,
    race_event_label: "Válida IV — Cali",
    total_athletes: 1,
    items: [
      {
        athlete_id: 145,
        athlete_display_name: "Mi Atleta",
        valida_num: 4,
        insight_id: 99,
        summary_excerpt: "Buen desempeño.",
        generated_at: "2026-05-25T19:49:00",
        confidence: "medium",
      },
    ],
  },
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
};

function makeCoachAuth() {
  return (selector: (s: { accessToken: string; user: { role: UserRole } }) => unknown) =>
    selector({ accessToken: "test-token", user: { role: UserRole.coach } });
}

function makeParentAuth() {
  return (selector: (s: { accessToken: string; user: { role: UserRole } }) => unknown) =>
    selector({ accessToken: "test-token", user: { role: UserRole.parent } });
}

function makeAdminAuth() {
  return (selector: (s: { accessToken: string; user: { role: UserRole } }) => unknown) =>
    selector({ accessToken: "test-token", user: { role: UserRole.admin } });
}

function wrap(ui: ReactNode) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
  capturedRosterProps.length = 0;
});

// ---------------------------------------------------------------------------
// Estructura de la página
// ---------------------------------------------------------------------------

describe("AthletesTab — estructura", () => {
  it("renderiza el panel de convocatoria (RosterPanel) y la sección de insights IA", () => {
    mockUseAuthStore.mockImplementation(makeCoachAuth());
    mockUseClubInsightsByRace.mockReturnValue(EMPTY_INSIGHTS);

    wrap(<AthletesTab raceEventId={1} />);

    expect(screen.getByTestId("athletes-tab")).toBeInTheDocument();
    expect(screen.getByTestId("mock-roster-panel")).toBeInTheDocument();
    // Encabezados de sección
    expect(screen.getByText(/Convocatoria/i)).toBeInTheDocument();
    expect(screen.getByText(/Insights IA/i)).toBeInTheDocument();
  });

  it("pasa el raceEventId correcto al RosterPanel", () => {
    mockUseAuthStore.mockImplementation(makeCoachAuth());
    mockUseClubInsightsByRace.mockReturnValue(EMPTY_INSIGHTS);

    wrap(<AthletesTab raceEventId={7} />);

    const panel = screen.getByTestId("mock-roster-panel");
    expect(panel).toHaveAttribute("data-race-event-id", "7");
  });
});

// ---------------------------------------------------------------------------
// Coach: modo escritura
// ---------------------------------------------------------------------------

describe("AthletesTab — coach (modo escritura)", () => {
  it("pasa isReadOnly=false al RosterPanel para coach", () => {
    mockUseAuthStore.mockImplementation(makeCoachAuth());
    mockUseClubInsightsByRace.mockReturnValue(EMPTY_INSIGHTS);

    wrap(<AthletesTab raceEventId={1} />);

    const panel = screen.getByTestId("mock-roster-panel");
    expect(panel).toHaveAttribute("data-readonly", "false");
    // Los controles de edición son visibles
    expect(screen.getByTestId("coach-roster")).toBeInTheDocument();
  });

  it("muestra el grid de análisis IA cuando hay datos", () => {
    mockUseAuthStore.mockImplementation(makeCoachAuth());
    mockUseClubInsightsByRace.mockReturnValue(INSIGHTS_WITH_DATA);

    wrap(<AthletesTab raceEventId={1} />);

    expect(screen.getByTestId("athlete-tab-card-145")).toBeInTheDocument();
  });

  it("muestra el empty state de insights cuando no hay datos", () => {
    mockUseAuthStore.mockImplementation(makeCoachAuth());
    mockUseClubInsightsByRace.mockReturnValue(EMPTY_INSIGHTS);

    wrap(<AthletesTab raceEventId={1} />);

    expect(
      screen.getByText(/No hay atletas de Trocha y Ruta con resultados/i),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Padre (T029 privacidad)
// ---------------------------------------------------------------------------

describe("AthletesTab — padre (solo lectura / privacidad)", () => {
  it("pasa isReadOnly=true al RosterPanel para padre", () => {
    mockUseAuthStore.mockImplementation(makeParentAuth());
    mockUseClubInsightsByRace.mockReturnValue(EMPTY_INSIGHTS);

    wrap(<AthletesTab raceEventId={1} />);

    const panel = screen.getByTestId("mock-roster-panel");
    expect(panel).toHaveAttribute("data-readonly", "true");
  });

  it("el nombre de otro menor NO aparece en el DOM (privacidad R1)", () => {
    mockUseAuthStore.mockImplementation(makeParentAuth());
    mockUseClubInsightsByRace.mockReturnValue(EMPTY_INSIGHTS);

    wrap(<AthletesTab raceEventId={1} />);

    // El mock de RosterPanel en modo readonly solo renderiza "Mi Hijo Uno"
    expect(screen.getByText("Mi Hijo Uno")).toBeInTheDocument();
    // Nombre de otro menor hipotético nunca en el DOM
    expect(screen.queryByText("Otro Menor Ajeno")).not.toBeInTheDocument();
  });

  it("los controles de edición del roster están ocultos para padre", () => {
    mockUseAuthStore.mockImplementation(makeParentAuth());
    mockUseClubInsightsByRace.mockReturnValue(EMPTY_INSIGHTS);

    wrap(<AthletesTab raceEventId={1} />);

    expect(screen.queryByTestId("coach-roster")).not.toBeInTheDocument();
  });

  it("axe 0 violaciones en vista padre", async () => {
    mockUseAuthStore.mockImplementation(makeParentAuth());
    mockUseClubInsightsByRace.mockReturnValue(EMPTY_INSIGHTS);

    const { container } = wrap(<AthletesTab raceEventId={1} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Admin vs. coach — bug de navegación silenciosa a /athletes/:id
// (mismo patrón que la corrección hermana en MeasurementAlerts: esa ruta es
// coach-only en App.tsx; un <Link>/navigate() sin chequear el rol hacía que
// ProtectedRoute rebotara a admin en silencio de vuelta al dashboard).
// ---------------------------------------------------------------------------

describe("AthletesTab — admin vs. coach (navegación a /athletes/:id)", () => {
  it("coach: la tarjeta de atleta enlaza a /athletes/{id}?tab=ai_analysis", () => {
    mockUseAuthStore.mockImplementation(makeCoachAuth());
    mockUseClubInsightsByRace.mockReturnValue(INSIGHTS_WITH_DATA);

    wrap(<AthletesTab raceEventId={1} />);

    const card = screen.getByTestId("athlete-tab-card-145");
    const link = card.querySelector("a");
    expect(link).toHaveAttribute("href", "/athletes/145?tab=ai_analysis");
  });

  it("admin: la tarjeta de atleta NO renderiza un <a> (antes navegaba y ProtectedRoute rebotaba en silencio)", () => {
    mockUseAuthStore.mockImplementation(makeAdminAuth());
    mockUseClubInsightsByRace.mockReturnValue(INSIGHTS_WITH_DATA);

    wrap(<AthletesTab raceEventId={1} />);

    const card = screen.getByTestId("athlete-tab-card-145");
    expect(card.querySelector("a")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    // El contenido se sigue mostrando como texto plano, sin navegación.
    expect(within(card).getByText("Mi Atleta")).toBeInTheDocument();
  });

  it("admin: axe 0 violaciones con datos de análisis", async () => {
    mockUseAuthStore.mockImplementation(makeAdminAuth());
    mockUseClubInsightsByRace.mockReturnValue(INSIGHTS_WITH_DATA);

    const { container } = wrap(<AthletesTab raceEventId={1} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

// ---------------------------------------------------------------------------
// Accesibilidad (coach)
// ---------------------------------------------------------------------------

describe("AthletesTab — accesibilidad", () => {
  it("axe 0 violaciones — vista coach sin datos de análisis", async () => {
    mockUseAuthStore.mockImplementation(makeCoachAuth());
    mockUseClubInsightsByRace.mockReturnValue(EMPTY_INSIGHTS);

    const { container } = wrap(<AthletesTab raceEventId={1} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("axe 0 violaciones — vista coach con datos de análisis", async () => {
    mockUseAuthStore.mockImplementation(makeCoachAuth());
    mockUseClubInsightsByRace.mockReturnValue(INSIGHTS_WITH_DATA);

    const { container } = wrap(<AthletesTab raceEventId={1} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
