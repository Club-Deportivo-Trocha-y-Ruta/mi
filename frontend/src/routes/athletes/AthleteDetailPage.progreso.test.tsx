/**
 * AthleteDetailPage — tab Progreso (Técnica/Fuerza) (specs/028, ProgresoTabPanel).
 *
 * Cubre el toggle interno Técnica/Fuerza (Técnica por defecto, monta
 * SkillProgressBoard/ProgressNotesBoard vía lazy+Suspense), el enlace
 * puntual a ansiedad competitiva (`/anxiety?athlete={id}`), y 0
 * violaciones axe en el panel de la pestaña.
 *
 * A semejanza de `AthleteDetailPage.strava.test.tsx`, este archivo mockea
 * `@/store/auth.store` como coach y mockea los sub-componentes pesados que
 * no son objeto de este archivo — incluyendo, adicionalmente,
 * `SkillProgressBoard`/`ProgressNotesBoard` (lazy-loaded vía `lazy()` en
 * AthleteDetailPage, ya cubiertos por sus propios tests).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";

import { UserRole } from "@/types/enums";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Mocks — deben declararse antes de los imports de producción
// ---------------------------------------------------------------------------

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (s: { accessToken: string; user: { id: number; role: UserRole } }) => unknown,
  ) => selector({ accessToken: "test-token", user: { id: 1, role: UserRole.coach } }),
}));

vi.mock("@/api/athletes", () => ({
  getAthlete: vi.fn(),
  getAnthropometry: vi.fn(),
  createAnthropometry: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    interceptors: { request: { use: vi.fn() } },
  },
  registerAuthHandlers: vi.fn(),
}));

vi.mock("@/api/parents", () => ({
  getParentAthletes: vi.fn().mockResolvedValue([]),
  getParentInvites: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/api/ai", () => ({
  getPHVExplanation: vi.fn(),
  getPHVExplanationCached: vi.fn().mockResolvedValue(null),
}));

// Sub-componentes pesados que no son objeto de este archivo — mismo patrón
// que AthleteDetailPage.test.tsx / AthleteDetailPage.strava.test.tsx.
vi.mock("@/components/athletes/AnthropometryForm", () => ({
  AnthropometryForm: () => <div data-testid="anthropometry-form">AnthropometryForm</div>,
}));
vi.mock("@/components/athletes/AnthropometryHistory", () => ({
  AnthropometryHistory: () => <div data-testid="anthropometry-history">AnthropometryHistory</div>,
}));
vi.mock("@/components/athletes/GrowthCharts", () => ({
  GrowthCharts: () => <div data-testid="growth-charts">GrowthCharts</div>,
}));
vi.mock("@/components/athletes/NutritionalClassification", () => ({
  NutritionalClassification: () => (
    <div data-testid="nutritional-classification">NutritionalClassification</div>
  ),
}));
vi.mock("@/components/athletes/TrainingReadiness", () => ({
  TrainingReadiness: () => <div data-testid="training-readiness">TrainingReadiness</div>,
}));
vi.mock("@/components/athletes/ResearchReferences", () => ({
  ResearchReferences: () => <div data-testid="research-references">ResearchReferences</div>,
}));
vi.mock("@/components/athletes/AthleteInfoCard", () => ({
  AthleteInfoCard: ({ athlete }: { athlete: { first_name: string; last_name: string } }) => (
    <div data-testid="athlete-info-card">
      {athlete.first_name} {athlete.last_name}
    </div>
  ),
}));
vi.mock("@/components/athletes/LinkedParentsCard", () => ({
  LinkedParentsCard: () => <div data-testid="linked-parents-card">LinkedParentsCard</div>,
}));
vi.mock("@/components/ai/PHVExplanationCard", () => ({
  PHVExplanationCard: () => <div data-testid="phv-explanation-card">PHVExplanationCard</div>,
}));
vi.mock("@/components/training/AthleteNewslettersTabPanel", () => ({
  AthleteNewslettersTabPanel: () => (
    <div data-testid="newsletters-tab-panel">AthleteNewslettersTabPanel</div>
  ),
}));

// Tableros pesados de la pestaña Progreso — lazy-loaded en AthleteDetailPage
// vía `lazy(() => import(...))`; ya cubiertos por sus propios tests.
vi.mock("@/components/technique/SkillProgressBoard", () => ({
  SkillProgressBoard: () => <div data-testid="skill-progress-board">SkillProgressBoard</div>,
}));
vi.mock("@/components/strength/ProgressNotesBoard", () => ({
  ProgressNotesBoard: () => <div data-testid="progress-notes-board">ProgressNotesBoard</div>,
}));

// ---------------------------------------------------------------------------
// Imports de producción (después de mocks)
// ---------------------------------------------------------------------------

import * as athletesApi from "@/api/athletes";
import { AthleteDetailPage } from "./AthleteDetailPage";
import type { AthleteDetailOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

// ---------------------------------------------------------------------------
// Fixtures — DATOS FICTICIOS. Nunca usar datos reales de atletas menores.
// ---------------------------------------------------------------------------

const TEST_ATHLETE_ID = 42;

const mockAthlete: AthleteDetailOut = {
  id: TEST_ATHLETE_ID,
  user_id: 10,
  first_name: "Sebastián",
  last_name: "García Ficticio",
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

// ---------------------------------------------------------------------------
// Helper de render
// ---------------------------------------------------------------------------

function renderPage(athleteId = String(TEST_ATHLETE_ID)) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <MemoryRouter initialEntries={[`/athletes/${athleteId}`]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/athletes/:id" element={<AthleteDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

async function goToProgresoTab() {
  const tabButton = await screen.findByTestId("athlete-tab-progreso");
  await act(async () => {
    await userEvent.click(tabButton);
  });
}

// ---------------------------------------------------------------------------
// Suites
// ---------------------------------------------------------------------------

describe("AthleteDetailPage — tab Progreso", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthlete);
    vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([]);
  });

  it("renderiza el tablero Técnica (SkillProgressBoard) por defecto", async () => {
    renderPage();
    await goToProgresoTab();

    expect(await screen.findByTestId("skill-progress-board")).toBeInTheDocument();
    expect(screen.queryByTestId("progress-notes-board")).not.toBeInTheDocument();
  });

  it("el toggle Técnica está activo por defecto", async () => {
    renderPage();
    await goToProgresoTab();
    await screen.findByTestId("skill-progress-board");

    expect(screen.getByRole("radio", { name: "Técnica" })).toHaveAttribute(
      "data-state",
      "on",
    );
    expect(screen.getByRole("radio", { name: "Fuerza" })).toHaveAttribute(
      "data-state",
      "off",
    );
  });

  it("cambiar a Fuerza renderiza ProgressNotesBoard en lugar de SkillProgressBoard", async () => {
    renderPage();
    await goToProgresoTab();
    await screen.findByTestId("skill-progress-board");

    await act(async () => {
      await userEvent.click(screen.getByRole("radio", { name: "Fuerza" }));
    });

    expect(await screen.findByTestId("progress-notes-board")).toBeInTheDocument();
    expect(screen.queryByTestId("skill-progress-board")).not.toBeInTheDocument();
  });

  it("expone el enlace 'Ver ansiedad competitiva' con el href del atleta activo", async () => {
    renderPage();
    await goToProgresoTab();
    await screen.findByTestId("skill-progress-board");

    const link = screen.getByRole("link", { name: /Ver ansiedad competitiva/i });
    expect(link).toHaveAttribute("href", `/anxiety?athlete=${TEST_ATHLETE_ID}`);
  });

  it("no tiene violaciones de accesibilidad en el panel Progreso", async () => {
    const { container } = renderPage();
    await goToProgresoTab();
    await screen.findByTestId("skill-progress-board");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
