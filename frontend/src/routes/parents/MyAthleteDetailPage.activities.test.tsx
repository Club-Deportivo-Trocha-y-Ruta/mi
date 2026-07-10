/**
 * MyAthleteDetailPage — sección "Actividades" (Strava) del padre/acudiente
 * (feature 025, T039 / US3 — FR-011, FR-012, SC-006).
 *
 * A diferencia de `MyAthleteDetailPage.test.tsx` (que mockea todos los
 * hooks), este archivo NO mockea `useAthleteActivities`: la sección de
 * actividades ejercita la capa HTTP real (axios) contra handlers MSW
 * (`@/test/msw/stravaHandlers`), mismo criterio que
 * `AthleteDetailPage.strava.test.tsx` (T027) para el lado del coach.
 *
 * Cubre:
 *  - Alcance ("scoping"): la sección consulta
 *    `GET /api/athletes/{athleteId}/activities` con el `athleteId` de la
 *    ruta — el mismo endpoint que el backend acota a "solo mi hijo" vía
 *    `can_view_activity` (FR-011). El test no puede probar el 403 del
 *    backend (ver `backend/tests/routers/test_activities.py`), pero SÍ que
 *    (a) la UI llama al endpoint con el atleta correcto y (b) una
 *    respuesta de acceso denegado (403, ej. "atleta de otra familia") se
 *    degrada con gracia sin filtrar datos.
 *  - Solo lectura: NUNCA se renderiza ningún control de enlace/desenlace de
 *    sesión (exclusivos del coach/admin, FR-007) — `ActivityCard` no los
 *    expone en ningún modo, esto es una garantía estructural que este
 *    archivo verifica como regresión.
 *  - Privacidad (Ley 1581): ningún dato de ubicación/mapa/coordenadas del
 *    menor aparece en el DOM (Acceptance Scenario US3 #3, SC-006).
 *  - 0 violaciones jest-axe en la sección de actividades para los estados
 *    cargando/vacío/con datos/error.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
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

// Sub-componentes pesados ajenos al objeto de este archivo — mismo patrón
// que MyAthleteDetailPage.test.tsx / AthleteDetailPage.strava.test.tsx.
vi.mock("@/components/athletes/AthleteInfoCard", () => ({
  AthleteInfoCard: () => <div data-testid="athlete-info-card">InfoCard</div>,
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
vi.mock("@/components/athletes/ResearchReferences", () => ({
  ResearchReferences: () => <div data-testid="research-references">ResearchReferences</div>,
}));
vi.mock("@/components/ai/PHVExplanationCard", () => ({
  PHVExplanationCard: () => <div data-testid="phv-explanation-card">PHVExplanationCard</div>,
}));
vi.mock("@/components/athletes/ai/AthleteAIAnalysisTab", () => ({
  AthleteAIAnalysisTab: () => <div data-testid="mock-ai-analysis-tab" />,
}));

// ---------------------------------------------------------------------------
// Imports de producción (después de mocks)
// ---------------------------------------------------------------------------

import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { MyAthleteDetailPage } from "./MyAthleteDetailPage";
import { mswServer } from "@/test/setup";
import {
  stravaHandlers,
  emptyActivitiesHandler,
  activitiesErrorHandler,
  mockActivityListResponse,
  mockActivity,
} from "@/test/msw/stravaHandlers";
import type { AthleteDetailOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

// ---------------------------------------------------------------------------
// Fixtures — DATOS FICTICIOS. Nunca datos reales de atletas menores.
// ---------------------------------------------------------------------------

const MY_ATHLETE_ID = 42;

const mockAthlete: AthleteDetailOut = {
  id: MY_ATHLETE_ID,
  user_id: 100,
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

function renderAthletePage(athleteId: number = MY_ATHLETE_ID, tab = "activities") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <MemoryRouter initialEntries={[`/my-athletes/${athleteId}?tab=${tab}`]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/my-athletes/:id" element={<MyAthleteDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

async function openActivitiesTab() {
  const user = userEvent.setup();
  const tab = await screen.findByTestId("parent-tab-activities");
  await user.click(tab);
  return screen.findByText("Actividades sincronizadas");
}

/** Contenedor de la sección de actividades (la tarjeta, no toda la página). */
function getActivitiesSection(): HTMLElement {
  const heading = screen.getByText("Actividades sincronizadas");
  const section = heading.closest("div.rounded-xl");
  if (!section) throw new Error("No se encontró la sección de actividades");
  return section as HTMLElement;
}

// ---------------------------------------------------------------------------
// Suites
// ---------------------------------------------------------------------------

describe("MyAthleteDetailPage — sección Actividades (padre, T039)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHooks();
    mswServer.use(...stravaHandlers);
  });

  // -------------------------------------------------------------------------
  // Alcance ("scoping") — FR-011
  // -------------------------------------------------------------------------

  describe("alcance por atleta (FR-011)", () => {
    it("consulta las actividades del atleta de la ruta (propio hijo), no un id fijo", async () => {
      let requestedAthleteId: string | undefined;
      mswServer.use(
        http.get("*/api/athletes/:athleteId/activities", ({ params }) => {
          requestedAthleteId = params.athleteId as string;
          return HttpResponse.json(mockActivityListResponse());
        }),
      );

      renderAthletePage(MY_ATHLETE_ID);
      await openActivitiesTab();

      expect(requestedAthleteId).toBe(String(MY_ATHLETE_ID));
    });

    it("renderiza las actividades sincronizadas del propio hijo", async () => {
      renderAthletePage();
      await openActivitiesTab();

      expect(await screen.findByText("Rodada matutina")).toBeInTheDocument();
      expect(screen.getByText("Salida familiar")).toBeInTheDocument();
    });

    it("degrada con gracia (sin filtrar datos) cuando el acceso es denegado — ej. atleta de otra familia", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/activities",
          () =>
            new HttpResponse(
              JSON.stringify({ detail: "No tiene permiso para ver las actividades de este atleta" }),
              { status: 403 },
            ),
        ),
      );

      renderAthletePage();
      await openActivitiesTab();

      expect(
        await screen.findByText("No se pudieron cargar las actividades."),
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Reintentar/i })).toBeInTheDocument();
      // El detalle del error del backend (403) NUNCA se filtra al DOM.
      expect(screen.queryByText(/permiso/i)).not.toBeInTheDocument();
      expect(screen.queryByText("Rodada matutina")).not.toBeInTheDocument();
    });

    it("degrada con gracia ante un error de servidor genérico", async () => {
      mswServer.use(activitiesErrorHandler);

      renderAthletePage();
      await openActivitiesTab();

      expect(
        await screen.findByText("No se pudieron cargar las actividades."),
      ).toBeInTheDocument();
    });

    it("muestra el estado vacío cuando el atleta todavía no tiene actividades", async () => {
      mswServer.use(emptyActivitiesHandler);

      renderAthletePage();
      await openActivitiesTab();

      expect(
        await screen.findByText(
          /Todavía no hay actividades sincronizadas de Strava para tu atleta/i,
        ),
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Solo lectura — FR-007 (link/unlink es exclusivo coach/admin)
  // -------------------------------------------------------------------------

  describe("solo lectura (FR-007)", () => {
    it("NO renderiza ningún control de enlace/desenlace a sesión", async () => {
      renderAthletePage();
      await openActivitiesTab();
      await screen.findByText("Rodada matutina");

      const section = getActivitiesSection();
      // El único botón permitido en la sección es "Reintentar", que solo
      // aparece en el estado de error — acá no debe existir ningún botón.
      expect(within(section).queryAllByRole("button")).toHaveLength(0);
      expect(within(section).queryByText(/Vincular|Desvincular|Enlazar a sesión/i)).not.toBeInTheDocument();
    });

    it("muestra el estado de enlace como información pasiva (badge), no como acción", async () => {
      mswServer.use(
        http.get("*/api/athletes/:athleteId/activities", () =>
          HttpResponse.json(
            mockActivityListResponse({
              items: [
                mockActivity({
                  id: 5,
                  name: "Rodada con el grupo",
                  link: {
                    training_session_id: 10,
                    session_label: "5 jul · Entrenamiento",
                    linked_by: "Entrenador Ficticio",
                    linked_at: "2026-07-05T12:00:00Z",
                  },
                }),
              ],
            }),
          ),
        ),
      );

      renderAthletePage();
      await openActivitiesTab();

      expect(await screen.findByText(/Enlazada · 5 jul · Entrenamiento/)).toBeInTheDocument();
      const section = getActivitiesSection();
      expect(within(section).queryAllByRole("button")).toHaveLength(0);
    });
  });

  // -------------------------------------------------------------------------
  // Privacidad (Ley 1581) — Acceptance Scenario US3 #3, SC-006
  // -------------------------------------------------------------------------

  describe("privacidad de menores (Ley 1581)", () => {
    it("no expone ubicación, mapa ni coordenadas de las actividades", async () => {
      renderAthletePage();
      await openActivitiesTab();
      await screen.findByText("Rodada matutina");

      const section = getActivitiesSection();
      const text = section.textContent ?? "";
      const forbidden = [/\blat(itude)?\b/i, /\blng|longitude\b/i, /polyline/i, /\bmapa\b/i, /ubicaci[oó]n/i, /\bgps\b/i];
      forbidden.forEach((pattern) => {
        expect(text).not.toMatch(pattern);
      });
      // La sección no contiene ningún <img>/<canvas>/<svg data-map> — solo
      // texto (fecha, duración, distancia, FC). Garantía estructural: no
      // hay ningún elemento de mapa en el DOM de la sección.
      expect(section.querySelector('[data-map], canvas, [class*="map"]')).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Accesibilidad — jest-axe, 0 violaciones
  // -------------------------------------------------------------------------

  describe("accesibilidad (jest-axe)", () => {
    it("sin violaciones con actividades cargadas", async () => {
      renderAthletePage();
      await openActivitiesTab();
      await screen.findByText("Rodada matutina");

      const results = await axe(getActivitiesSection());
      expect(results).toHaveNoViolations();
    });

    it("sin violaciones en el estado vacío", async () => {
      mswServer.use(emptyActivitiesHandler);
      renderAthletePage();
      await openActivitiesTab();
      await screen.findByText(/Todavía no hay actividades sincronizadas/i);

      const results = await axe(getActivitiesSection());
      expect(results).toHaveNoViolations();
    });

    it("sin violaciones en el estado de error con acción de reintentar", async () => {
      mswServer.use(activitiesErrorHandler);
      renderAthletePage();
      await openActivitiesTab();
      await screen.findByText("No se pudieron cargar las actividades.");

      const results = await axe(getActivitiesSection());
      expect(results).toHaveNoViolations();
    });
  });
});
