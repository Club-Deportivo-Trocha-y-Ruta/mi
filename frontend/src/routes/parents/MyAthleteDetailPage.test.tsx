/**
 * MyAthleteDetailPage — pestaña única «Carreras» de la familia (feature 045,
 * US4 / T044 / T045; FR-010, FR-014, FR-015, FR-016, FR-018).
 *
 * Reemplaza a la cobertura anterior de las pestañas «Análisis IA» y «Carreras»
 * por separado. A diferencia de `AthleteDetailPage.test.tsx` (que sonda
 * `CarrerasTab`), aquí `CarrerasTab` corre REAL contra handlers MSW — las
 * aserciones de contenido (sin brechas contra líder/podio, etiqueta de IA
 * revisada por el entrenador, cero violaciones a11y) solo tienen sentido con
 * la pestaña real. Solo se mockea la gráfica (`HistoryChart`, recharts) — ya
 * cubierta en su propio spec.
 *
 * Cubre:
 *  - UNA sola pestaña «Carreras»; ya no existe «Análisis IA» como pestaña de
 *    página (los alias se resuelven por URL);
 *  - alias `?tab=ai-analysis[&insight=<id>]` → `?tab=races&view=analisis[&insight=<id>]`;
 *  - `view=comparar` (solo-coach) cae en «Progresión», nunca es un error;
 *  - ninguna cadena «Brecha vs. 1.ª posición» / «Brecha vs. podio» en ninguna vista;
 *  - la etiqueta «Análisis generado con IA y revisado por el entrenador.» en cada
 *    análisis mostrado a la familia;
 *  - jest-axe: cero violaciones en «Progresión» y en «Análisis IA».
 *
 * Privacidad Ley 1581: fixtures 100% sintéticas, ningún menor real.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { axe } from "jest-axe";

// ---------------------------------------------------------------------------
// Mocks — declarados antes de imports de producción
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

// Stand-in liviano de la gráfica (recharts) — cubierta en HistoryChart.test.tsx.
vi.mock("@/components/race/history/HistoryChart", () => ({
  HistoryChart: ({ points }: { points: unknown[] }) => (
    <div data-testid="mock-history-chart" data-count={points.length} />
  ),
}));

// Componentes secundarios ajenos al objeto de este archivo.
vi.mock("@/components/athletes/AthleteInfoCard", () => ({
  AthleteInfoCard: () => <div data-testid="athlete-info-card">InfoCard</div>,
}));

import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useAnthropometry } from "@/hooks/athletes/useAnthropometry";
import { mswServer } from "@/test/setup";
import { raceHistoryFamilyHandler } from "@/test/msw/raceHistoryHandlers";
import { seasonPanoramaHandler } from "@/test/msw/athleteRaceAnalysisHandlers";
import { MyAthleteDetailPage } from "./MyAthleteDetailPage";
import { Sex } from "@/types/enums";
import type { AthleteDetailOut } from "@/types/athlete.types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const AI_REVIEWED_LABEL = "Análisis generado con IA y revisado por el entrenador.";

const mockAthlete: AthleteDetailOut = {
  id: 42,
  user_id: 100,
  first_name: "Atleta",
  last_name: "Ficticio",
  birth_date: "2012-01-15",
  sex: Sex.M,
  club_join_date: "2024-01-01",
  years_in_club: 2,
  age_decimal: 14.3,
  category: "Sub-15",
  club_id: 1,
  created_at: "2024-01-01T00:00:00Z",
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

/** Expone `location.search` para verificar la sincronización con la URL. */
function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-search">{location.search}</div>;
}

function currentSearchParams(): URLSearchParams {
  return new URLSearchParams(screen.getByTestId("location-search").textContent ?? "");
}

function renderPage(search = "") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <MemoryRouter initialEntries={[`/my-athletes/42${search}`]}>
      <QueryClientProvider client={queryClient}>
        <LocationProbe />
        <Routes>
          <Route path="/my-athletes/:id" element={<MyAthleteDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/** Espera a que no quede ningún esqueleto de carga (chunks lazy + consultas). */
async function waitUntilSettled() {
  await screen.findByTestId("carreras-tab");
  await waitFor(() => {
    expect(document.querySelector('[aria-busy="true"]')).toBeNull();
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("MyAthleteDetailPage — pestaña única «Carreras» (feature 045, US4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHooks();
    // Lo que recibe un padre: historial sin brechas contra líder/podio.
    mswServer.use(raceHistoryFamilyHandler, seasonPanoramaHandler);
  });

  describe("estructura de pestañas", () => {
    it("hay UNA sola pestaña «Carreras» y ninguna «Análisis IA» ni «Insights IA» a nivel de página (FR-010)", async () => {
      renderPage();
      expect(await screen.findByTestId("parent-tab-races")).toHaveTextContent(/^Carreras$/);

      expect(screen.getAllByRole("button", { name: /^Carreras$/i })).toHaveLength(1);
      expect(screen.queryByRole("button", { name: /Análisis IA/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Insights IA/i })).not.toBeInTheDocument();
      expect(screen.queryByTestId("parent-tab-ai-analysis")).not.toBeInTheDocument();
    });

    it("en la pestaña por defecto (Datos) NO monta CarrerasTab", async () => {
      renderPage();
      await screen.findByTestId("parent-tab-races");
      expect(screen.queryByTestId("carreras-tab")).not.toBeInTheDocument();
      expect(screen.getByText("Datos del atleta")).toBeInTheDocument();
    });

    it("la familia llega a Carreras con UN toque desde la ficha del hijo (FR-018: ≤ 2 desde el inicio)", async () => {
      const user = userEvent.setup();
      renderPage();

      await user.click(await screen.findByTestId("parent-tab-races"));

      expect(await screen.findByTestId("carreras-tab")).toBeInTheDocument();
      expect(currentSearchParams().get("tab")).toBe("races");
    });

    it("?tab=races abre Carreras directamente en Progresión", async () => {
      renderPage("?tab=races");
      await screen.findByTestId("carreras-tab");
      expect(screen.getByTestId("carreras-view-progresion")).toHaveAttribute(
        "aria-selected",
        "true",
      );
    });

    it("?tab= con un valor que no es ninguna pestaña cae en la pestaña por defecto", async () => {
      renderPage("?tab=algo-que-no-existe");
      await screen.findByTestId("parent-tab-races");
      expect(screen.queryByTestId("carreras-tab")).not.toBeInTheDocument();
      expect(screen.getByText("Datos del atleta")).toBeInTheDocument();
    });

    it("salir de Carreras suelta view e insight de la URL", async () => {
      const user = userEvent.setup();
      renderPage("?tab=races&view=analisis&insight=7");
      await screen.findByTestId("carreras-tab");

      await user.click(screen.getByRole("button", { name: /^Datos$/i }));

      expect(screen.queryByTestId("carreras-tab")).not.toBeInTheDocument();
      expect(screen.getByTestId("location-search").textContent).toBe("");
    });
  });

  describe("alias de URL (correos ya enviados y enlaces internos)", () => {
    it("?tab=ai-analysis → ?tab=races&view=analisis", async () => {
      renderPage("?tab=ai-analysis");

      await screen.findByTestId("carreras-tab");
      const params = currentSearchParams();
      expect(params.get("tab")).toBe("races");
      expect(params.get("view")).toBe("analisis");
      expect(params.has("insight")).toBe(false);
      expect(screen.getByTestId("carreras-view-analisis")).toHaveAttribute(
        "aria-selected",
        "true",
      );
    });

    it("?tab=ai-analysis&insight=7 conserva insight y abre Análisis IA", async () => {
      renderPage("?tab=ai-analysis&insight=7");

      await screen.findByTestId("carreras-tab");
      const params = currentSearchParams();
      expect(params.get("tab")).toBe("races");
      expect(params.get("view")).toBe("analisis");
      expect(params.get("insight")).toBe("7");
      expect(screen.getByTestId("carreras-view-analisis")).toHaveAttribute(
        "aria-selected",
        "true",
      );
    });
  });

  describe("«Comparar» es solo-coach (FR-015)", () => {
    it("view=comparar cae en Progresión — sin error y sin pestaña Comparar", async () => {
      renderPage("?tab=races&view=comparar");

      await screen.findByTestId("carreras-tab");
      expect(screen.getByTestId("carreras-view-progresion")).toHaveAttribute(
        "aria-selected",
        "true",
      );
      expect(screen.queryByTestId("carreras-view-comparar")).not.toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: /Comparar/i })).not.toBeInTheDocument();
    });
  });

  describe("privacidad familiar (FR-014, spec US4)", () => {
    it("ninguna vista muestra «Brecha vs. 1.ª posición» ni «Brecha vs. podio»", async () => {
      const user = userEvent.setup();
      renderPage("?tab=races");
      await waitUntilSettled();

      const forbidden = [/Brecha vs\.? 1\.?ª posición/i, /Brecha vs\.? podio/i];
      const assertClean = () => {
        const text = document.body.textContent ?? "";
        forbidden.forEach((pattern) => expect(text).not.toMatch(pattern));
      };

      assertClean();

      await user.click(screen.getByTestId("carreras-view-analisis"));
      await waitUntilSettled();
      assertClean();
    });

    it("cada análisis mostrado a la familia lleva la etiqueta de IA revisada por el entrenador", async () => {
      renderPage("?tab=races&view=analisis");
      await waitUntilSettled();

      const labels = await screen.findAllByText(AI_REVIEWED_LABEL);
      expect(labels.length).toBeGreaterThanOrEqual(1);
    });

    it("no expone metadatos operativos de IA (confianza, tokens, modelo, prompt)", async () => {
      renderPage("?tab=races&view=analisis");
      await waitUntilSettled();
      await screen.findAllByText(AI_REVIEWED_LABEL);

      const tree = document.body.textContent ?? "";
      [/confidence/i, /\$\d/, /tokens?/i, /\bprompt\b/i, /\bmodel\b/i, /gemini/i].forEach(
        (pattern) => expect(tree).not.toMatch(pattern),
      );
    });
  });

  describe("accesibilidad", () => {
    it("jest-axe: cero violaciones en Progresión", async () => {
      const { container } = renderPage("?tab=races");
      await waitUntilSettled();
      expect(await axe(container)).toHaveNoViolations();
    });

    it("jest-axe: cero violaciones en Análisis IA", async () => {
      const { container } = renderPage("?tab=races&view=analisis");
      await waitUntilSettled();
      await screen.findAllByText(AI_REVIEWED_LABEL);
      expect(await axe(container)).toHaveNoViolations();
    });
  });
});
