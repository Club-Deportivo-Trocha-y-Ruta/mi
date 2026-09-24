/**
 * Tests de CarrerasTab (feature 045, T033 — US1/US4).
 *
 * Cubre:
 *  - abre en «Progresión» por defecto;
 *  - la primera pintura solo dispara la petición del historial (registro
 *    de peticiones de MSW) — nada de insights, runs ni distribución;
 *  - cambiar a «Análisis IA» dispara insights y runs;
 *  - `view=` se sincroniza con la URL (y `insight=` fuerza «Análisis IA»);
 *  - familia: sin «Comparar», `view=comparar` cae en «Progresión»;
 *  - jest-axe: cero violaciones.
 *
 * Los componentes hijos pesados (gráfica, timeline, hero, chat, formulario)
 * se mockean — están probados en sus propios specs; aquí se prueba el
 * cascarón (vistas, URL, carga diferida).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { useLocation } from "react-router-dom";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Coach", last_name: "Prueba" },
      isAuthenticated: true,
    }),
  ),
}));

vi.mock("@/components/race/history/HistoryChart", () => ({
  HistoryChart: () => <div data-testid="mock-history-chart">chart</div>,
}));
vi.mock("@/components/athletes/ai/PanoramaView", () => ({
  PanoramaView: () => <div data-testid="mock-panorama-view" />,
}));
vi.mock("@/components/athletes/ai/HeroLastInsightCard", () => ({
  HeroLastInsightCard: () => <div data-testid="mock-hero-last-insight" />,
}));
vi.mock("@/components/athletes/ai/InsightsTimeline", () => ({
  InsightsTimeline: ({
    selectedInsightId,
    onSelectInsight,
  }: {
    selectedInsightId?: number | null;
    onSelectInsight?: (id: number | null) => void;
  }) => (
    <div data-testid="mock-insights-timeline">
      selected-{selectedInsightId ?? "none"}
      <button type="button" onClick={() => onSelectInsight?.(9)}>
        abrir-9
      </button>
      <button type="button" onClick={() => onSelectInsight?.(null)}>
        cerrar-insight
      </button>
    </div>
  ),
}));
vi.mock("@/components/athletes/ai/LaunchAnalysisForm", () => ({
  LaunchAnalysisForm: () => <div data-testid="mock-launch-form" />,
}));
vi.mock("@/components/athletes/ai/AthleteAnalystChatPanel", () => ({
  AthleteAnalystChatPanel: () => <div data-testid="mock-chat-panel" />,
}));
vi.mock("@/components/athletes/ai/SeasonSummaryButton", () => ({
  SeasonSummaryButton: () => <div data-testid="mock-season-summary" />,
}));
vi.mock("@/components/athletes/ai/DistributionChart", () => ({
  DistributionChart: () => <div data-testid="mock-distribution-chart" />,
}));
vi.mock("@/components/athletes/ai/ComparatorPanel", () => ({
  ComparatorPanel: () => <div data-testid="mock-comparator-panel" />,
}));

import { CarrerasTab } from "@/components/athletes/races/CarrerasTab";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { mswServer } from "@/test/setup";
import { Sex } from "@/types/enums";
import type { AthleteOut } from "@/types/athlete.types";

const athlete: AthleteOut = {
  id: 42,
  user_id: 100,
  first_name: "Atleta",
  last_name: "Prueba",
  birth_date: "2012-01-15",
  sex: Sex.M,
  club_join_date: "2024-01-01",
  years_in_club: 2,
  age_decimal: 14.3,
  category: "Sub-15",
  club_id: 1,
  created_at: "2024-01-01T00:00:00Z",
};

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-search">{location.search}</div>;
}

function renderTab(
  audience: "coach" | "family",
  search = "?tab=races",
) {
  return renderWithProviders(
    <>
      <CarrerasTab athlete={athlete} audience={audience} />
      <LocationProbe />
    </>,
    { initialEntries: [`/athletes/42${search}`] },
  );
}

/** Registro de las peticiones salientes — solo `pathname`, sin cuerpo. */
let requestedPaths: string[] = [];
const onRequestStart = ({ request }: { request: Request }) => {
  requestedPaths.push(new URL(request.url).pathname);
};

const HISTORY_PATH = "/api/athletes/42/race-analysis/history";
const INSIGHTS_PATH = "/api/athletes/42/race-analysis/insights";
const RUNS_PATH = "/api/athletes/42/race-analysis/runs";

function searchOf(): URLSearchParams {
  return new URLSearchParams(screen.getByTestId("location-search").textContent ?? "");
}

describe("CarrerasTab", () => {
  beforeEach(() => {
    requestedPaths = [];
    mswServer.events.on("request:start", onRequestStart);
  });

  afterEach(() => {
    mswServer.events.removeListener("request:start", onRequestStart);
  });

  it("abre en Progresión por defecto", async () => {
    renderTab("coach");

    const tab = await screen.findByRole("tab", { name: /progresión/i });
    expect(tab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /análisis ia/i })).toHaveAttribute(
      "aria-selected",
      "false",
    );
    expect(await screen.findByTestId("progression-view")).toBeInTheDocument();
    expect(screen.queryByTestId("analysis-view")).not.toBeInTheDocument();
  });

  it("en la primera pintura solo dispara la petición del historial", async () => {
    renderTab("coach");

    await waitFor(() => expect(requestedPaths).toContain(HISTORY_PATH));
    // Deja pasar un ciclo de efectos por si alguna vista oculta consulta.
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(requestedPaths).not.toContain(INSIGHTS_PATH);
    expect(requestedPaths).not.toContain(RUNS_PATH);
    expect(
      requestedPaths.filter((p) => p.includes("/race-analysis/distribution")),
    ).toEqual([]);
  });

  it("al pasar a Análisis IA dispara insights y runs", async () => {
    const user = userEvent.setup();
    renderTab("coach");
    await screen.findByTestId("progression-view");

    await user.click(screen.getByRole("tab", { name: /análisis ia/i }));

    await waitFor(() => expect(requestedPaths).toContain(INSIGHTS_PATH));
    await waitFor(() => expect(requestedPaths).toContain(RUNS_PATH));
    expect(await screen.findByTestId("analysis-view")).toBeInTheDocument();
  });

  it("sincroniza `view=` con la URL al cambiar de vista", async () => {
    const user = userEvent.setup();
    renderTab("coach");
    await screen.findByTestId("progression-view");

    await user.click(screen.getByRole("tab", { name: /análisis ia/i }));
    await waitFor(() => expect(searchOf().get("view")).toBe("analisis"));
    // No pisa `tab` (lo posee la página).
    expect(searchOf().get("tab")).toBe("races");

    await user.click(screen.getByRole("tab", { name: /comparar/i }));
    await waitFor(() => expect(searchOf().get("view")).toBe("comparar"));

    await user.click(screen.getByRole("tab", { name: /progresión/i }));
    await waitFor(() => expect(searchOf().get("view")).toBe("progresion"));
  });

  it("lee `view=` de la URL al montar", async () => {
    renderTab("coach", "?tab=races&view=comparar");

    expect(
      await screen.findByRole("tab", { name: /comparar/i }),
    ).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByTestId("compare-view")).toBeInTheDocument();
  });

  it("`insight=` fuerza Análisis IA y se conserva en la URL", async () => {
    renderTab("coach", "?tab=races&view=progresion&insight=7");

    expect(
      await screen.findByRole("tab", { name: /análisis ia/i }),
    ).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByTestId("analysis-view")).toBeInTheDocument();
    expect(searchOf().get("insight")).toBe("7");
  });

  it("abrir un análisis lo refleja en `insight=` y cerrarlo NO vuelve a Progresión", async () => {
    const user = userEvent.setup();
    renderTab("coach", "?tab=races&view=analisis");
    await screen.findByTestId("analysis-view");

    await user.click(await screen.findByRole("button", { name: "abrir-9" }));
    await waitFor(() => expect(searchOf().get("insight")).toBe("9"));
    expect(searchOf().get("view")).toBe("analisis");
    expect(screen.getByTestId("mock-insights-timeline")).toHaveTextContent("selected-9");

    await user.click(screen.getByRole("button", { name: "cerrar-insight" }));
    await waitFor(() => expect(searchOf().has("insight")).toBe(false));
    // Sigue en «Análisis IA» aunque `insight` ya no fuerce la vista.
    expect(searchOf().get("view")).toBe("analisis");
    expect(screen.getByRole("tab", { name: /análisis ia/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("cambiar de vista suelta el `insight` expandido", async () => {
    const user = userEvent.setup();
    renderTab("coach", "?tab=races&view=analisis&insight=7");
    await screen.findByTestId("analysis-view");

    await user.click(screen.getByRole("tab", { name: /progresión/i }));

    await waitFor(() => expect(searchOf().get("view")).toBe("progresion"));
    expect(searchOf().has("insight")).toBe(false);
  });

  it("un `view` desconocido cae en Progresión", async () => {
    renderTab("coach", "?tab=races&view=otra-cosa");

    expect(
      await screen.findByRole("tab", { name: /progresión/i }),
    ).toHaveAttribute("aria-selected", "true");
  });

  describe("audiencia familia", () => {
    it("no ofrece la vista Comparar", async () => {
      renderTab("family");

      await screen.findByRole("tab", { name: /progresión/i });
      expect(screen.getByRole("tab", { name: /análisis ia/i })).toBeInTheDocument();
      expect(
        screen.queryByRole("tab", { name: /comparar/i }),
      ).not.toBeInTheDocument();
    });

    it("`view=comparar` cae en Progresión sin error", async () => {
      renderTab("family", "?tab=races&view=comparar");

      expect(
        await screen.findByRole("tab", { name: /progresión/i }),
      ).toHaveAttribute("aria-selected", "true");
      expect(await screen.findByTestId("progression-view")).toBeInTheDocument();
      expect(screen.queryByTestId("compare-view")).not.toBeInTheDocument();
      // Ni el comparador ni la distribución llegan a montarse (FR-015).
      expect(screen.queryByTestId("mock-comparator-panel")).not.toBeInTheDocument();
      expect(screen.queryByTestId("mock-distribution-chart")).not.toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("no consulta la distribución ni el comparador", async () => {
      const user = userEvent.setup();
      renderTab("family");
      await screen.findByTestId("progression-view");

      await user.click(screen.getByRole("tab", { name: /análisis ia/i }));
      await screen.findByTestId("analysis-view");

      expect(
        requestedPaths.filter((p) => p.includes("/race-analysis/distribution")),
      ).toEqual([]);
    });
  });

  describe("accesibilidad", () => {
    it("Progresión (coach) no tiene violaciones jest-axe", async () => {
      const { container } = renderTab("coach");
      await screen.findByTestId("progression-view");
      await waitFor(() =>
        expect(screen.queryByRole("status", { name: /cargando/i })).toBeNull(),
      );

      expect(await axe(container)).toHaveNoViolations();
    });

    it("Análisis IA (coach) no tiene violaciones jest-axe", async () => {
      const { container } = renderTab("coach", "?tab=races&view=analisis");
      await screen.findByTestId("analysis-view");

      expect(await axe(container)).toHaveNoViolations();
    });

    it("Comparar (coach) no tiene violaciones jest-axe", async () => {
      const { container } = renderTab("coach", "?tab=races&view=comparar");
      await screen.findByTestId("compare-view");

      expect(await axe(container)).toHaveNoViolations();
    });

    it("Progresión (familia) no tiene violaciones jest-axe", async () => {
      const { container } = renderTab("family");
      await screen.findByTestId("progression-view");
      await waitFor(() =>
        expect(screen.queryByRole("status", { name: /cargando/i })).toBeNull(),
      );

      expect(await axe(container)).toHaveNoViolations();
    });
  });
});
