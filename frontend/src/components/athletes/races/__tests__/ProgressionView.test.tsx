/**
 * Tests de ProgressionView (feature 045, T037 — US1/US4).
 *
 * Cubre:
 *  - pide el historial con `series_kind=all`;
 *  - las copas van a la línea (`HistoryChart`), los campeonatos a tarjetas de
 *    lectura — un campeonato nunca entra a la línea;
 *  - selector de métrica por audiencia (la familia jamás ve líder/podio);
 *  - filtro de competencia (una serie por copa/campeonato);
 *  - «texto primero», tabla debajo, estados de carga / vacío / error;
 *  - familia: ningún texto de «Brecha vs. 1.ª posición» / «Brecha vs. podio»;
 *  - jest-axe.
 *
 * `HistoryChart` se mockea (recharts) — se prueba qué puntos y qué métrica
 * recibe; su render está cubierto en `HistoryChart.test.tsx`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

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
  HistoryChart: ({
    points,
    metric,
    audience,
  }: {
    points: Array<{ series_id: number; event_id: number }>;
    metric?: string;
    audience?: string;
  }) => (
    <div
      data-testid="mock-history-chart"
      data-metric={metric}
      data-audience={audience}
      data-event-ids={points.map((p) => p.event_id).join(",")}
      data-series-ids={Array.from(new Set(points.map((p) => p.series_id))).join(",")}
    />
  ),
}));

import { ProgressionView } from "@/components/athletes/races/ProgressionView";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import {
  makeAthleteRaceHistoryRead,
  makeFamilyRaceHistoryPoint,
  makeRaceHistoryPoint,
  raceHistoryEmptyHandler,
  raceHistoryErrorHandler,
} from "@/test/msw/raceHistoryHandlers";
import { mswServer } from "@/test/setup";
import type { RaceHistoryPoint } from "@/types/raceHistory.types";

const HISTORY_PATH = "/api/athletes/42/race-analysis/history";

/** Dos copas (ids 7 y 8) y un campeonato (id 9). */
const CUP_A_1 = { event_id: 41, event_date: "2025-02-09", label: "Válida 1 — Ginebra", series_id: 7, series_name: "Copa Valle" };
const CUP_A_2 = { event_id: 42, event_date: "2025-03-09", label: "Válida 2 — Buga", series_id: 7, series_name: "Copa Valle" };
const CUP_B_1 = { event_id: 51, event_date: "2025-04-06", label: "Válida 1 — Alcalá", series_id: 8, series_name: "Copa Let's GO" };
const CHAMP = {
  event_id: 60,
  event_date: "2025-06-15",
  label: "Campeonato Departamental",
  series_id: 9,
  series_name: "Campeonato Departamental",
  series_kind: "championship" as const,
  position: 4,
  field_size: 15,
  percentile: 79,
  gap_to_median_pct: -6.1,
  gap_to_winner_pct: 9.4,
  gap_to_podium_pct: 4.2,
};

function coachPoints(): RaceHistoryPoint[] {
  return [
    makeRaceHistoryPoint(CUP_A_1),
    makeRaceHistoryPoint(CUP_A_2),
    makeRaceHistoryPoint(CUP_B_1),
    makeRaceHistoryPoint(CHAMP),
  ];
}

function familyPoints(): RaceHistoryPoint[] {
  return [
    makeFamilyRaceHistoryPoint(CUP_A_1),
    makeFamilyRaceHistoryPoint(CUP_A_2),
    makeFamilyRaceHistoryPoint(CUP_B_1),
    makeFamilyRaceHistoryPoint(CHAMP),
  ];
}

function useHistory(points: RaceHistoryPoint[]) {
  mswServer.use(
    http.get("*/api/athletes/:athleteId/race-analysis/history", () =>
      HttpResponse.json(
        makeAthleteRaceHistoryRead({
          points,
          seasons: [{ season: 2025, started: points.length, finished: points.length }],
        }),
      ),
    ),
  );
}

let requestedUrls: string[] = [];
const onRequestStart = ({ request }: { request: Request }) => {
  requestedUrls.push(request.url);
};

function optionLabels(select: HTMLElement): string[] {
  return within(select)
    .getAllByRole("option")
    .map((o) => o.textContent ?? "");
}

describe("ProgressionView", () => {
  beforeEach(() => {
    requestedUrls = [];
    mswServer.events.on("request:start", onRequestStart);
  });
  afterEach(() => {
    mswServer.events.removeListener("request:start", onRequestStart);
  });

  it("pide el historial con series_kind=all", async () => {
    useHistory(coachPoints());
    renderWithProviders(<ProgressionView athleteId={42} audience="coach" />);

    await screen.findByTestId("mock-history-chart");
    const historyUrl = requestedUrls.find((u) => new URL(u).pathname === HISTORY_PATH);
    expect(historyUrl).toBeDefined();
    expect(new URL(historyUrl as string).searchParams.get("series_kind")).toBe("all");
  });

  it("muestra el estado de carga y luego el contenido", async () => {
    useHistory(coachPoints());
    renderWithProviders(<ProgressionView athleteId={42} audience="coach" />);

    expect(
      screen.getByRole("status", { name: /cargando progresión histórica/i }),
    ).toBeInTheDocument();
    await screen.findByTestId("mock-history-chart");
    expect(screen.queryByRole("status", { name: /cargando/i })).not.toBeInTheDocument();
  });

  it("las copas van a la línea y el campeonato a una tarjeta de lectura, nunca a la línea", async () => {
    useHistory(coachPoints());
    renderWithProviders(<ProgressionView athleteId={42} audience="coach" />);

    const chart = await screen.findByTestId("mock-history-chart");
    // Solo las 3 válidas de copa (41, 42, 51) — el campeonato (60) no.
    expect(chart).toHaveAttribute("data-event-ids", "41,42,51");

    const champs = screen.getByTestId("progression-championships");
    const card = within(champs).getByTestId("championship-reading-card");
    expect(within(card).getByText("Campeonato Departamental")).toBeInTheDocument();
    expect(within(card).getByText("P4")).toBeInTheDocument();
    expect(within(card).getByText("15 corredores")).toBeInTheDocument();
    // Coach: la tarjeta trae la brecha vs. 1.ª posición.
    expect(within(card).getByText("Brecha vs. 1.ª posición")).toBeInTheDocument();
    expect(within(card).getByText("+9.4 %")).toBeInTheDocument();
  });

  it("la tarjeta de campeonato enlaza al detalle de la competencia (coach, FR-017)", async () => {
    useHistory(coachPoints());
    renderWithProviders(<ProgressionView athleteId={42} audience="coach" />);

    const card = await screen.findByTestId("championship-reading-card");
    expect(
      within(card).getByRole("link", { name: /ver competencia/i }),
    ).toHaveAttribute("href", "/competitions/60");
  });

  it("un DNF en un campeonato se lee «No completó la prueba»", async () => {
    useHistory([
      makeRaceHistoryPoint(CUP_A_1),
      makeRaceHistoryPoint({
        ...CHAMP,
        status: "dnf",
        position: null,
        percentile: null,
        gap_to_median_pct: null,
        gap_to_winner_pct: null,
        gap_to_podium_pct: null,
      }),
    ]);
    renderWithProviders(<ProgressionView athleteId={42} audience="coach" />);

    const card = await screen.findByTestId("championship-reading-card");
    expect(within(card).getByText(/no completó la prueba/i)).toBeInTheDocument();
  });

  it("sin válidas de copa (solo campeonato) no monta la línea ni el selector de métrica", async () => {
    useHistory([makeRaceHistoryPoint(CHAMP)]);
    renderWithProviders(<ProgressionView athleteId={42} audience="coach" />);

    await screen.findByTestId("championship-reading-card");
    expect(screen.queryByTestId("mock-history-chart")).not.toBeInTheDocument();
    expect(screen.queryByTestId("progression-metric-select")).not.toBeInTheDocument();
  });

  it("texto primero: chips de temporada, últimos resultados y tabla debajo", async () => {
    useHistory(coachPoints());
    renderWithProviders(<ProgressionView athleteId={42} audience="coach" />);

    await screen.findByTestId("mock-history-chart");
    expect(screen.getByTestId("season-completion-chips")).toBeInTheDocument();
    const latest = screen.getByTestId("history-latest-three");
    expect(within(latest).getAllByRole("listitem")).toHaveLength(3);
    // El campeonato (15 jun) es el resultado más reciente.
    expect(within(latest).getAllByRole("listitem")[0]).toHaveTextContent(
      "Campeonato Departamental",
    );
    expect(screen.getByTestId("history-table")).toBeInTheDocument();
  });

  describe("selector de métrica", () => {
    it("coach: mediana por defecto y todas las métricas, incluidas líder y podio", async () => {
      useHistory(coachPoints());
      renderWithProviders(<ProgressionView athleteId={42} audience="coach" />);

      const select = await screen.findByTestId("progression-metric-select");
      expect(select).toHaveValue("gap_to_median_pct");
      expect(optionLabels(select)).toEqual([
        "Brecha vs. mediana",
        "Percentil",
        "Posición",
        "Brecha vs. 1.ª posición",
        "Brecha vs. podio",
      ]);
      expect(screen.getByTestId("mock-history-chart")).toHaveAttribute(
        "data-metric",
        "gap_to_median_pct",
      );
    });

    it("cambiar la métrica se la pasa a la gráfica", async () => {
      const user = userEvent.setup();
      useHistory(coachPoints());
      renderWithProviders(<ProgressionView athleteId={42} audience="coach" />);

      const select = await screen.findByTestId("progression-metric-select");
      await user.selectOptions(select, "gap_to_podium_pct");
      expect(screen.getByTestId("mock-history-chart")).toHaveAttribute(
        "data-metric",
        "gap_to_podium_pct",
      );
    });

    it("familia: solo mediana, percentil y posición — nunca líder ni podio", async () => {
      useHistory(familyPoints());
      renderWithProviders(<ProgressionView athleteId={42} audience="family" />);

      const select = await screen.findByTestId("progression-metric-select");
      expect(optionLabels(select)).toEqual([
        "Brecha vs. mediana",
        "Percentil",
        "Posición",
      ]);
      expect(screen.getByTestId("mock-history-chart")).toHaveAttribute(
        "data-audience",
        "family",
      );
    });
  });

  describe("filtro de competencia (grupos de comparación)", () => {
    it("aparece con más de una serie y lista copas primero, luego campeonatos", async () => {
      useHistory(coachPoints());
      renderWithProviders(<ProgressionView athleteId={42} audience="coach" />);

      const select = await screen.findByTestId("progression-group-select");
      expect(select).toHaveValue("all");
      expect(optionLabels(select)).toEqual([
        "Todas las competencias",
        "Copa Let's GO",
        "Copa Valle",
        "Campeonato Departamental",
      ]);
    });

    it("no aparece con una sola serie", async () => {
      useHistory([makeRaceHistoryPoint(CUP_A_1), makeRaceHistoryPoint(CUP_A_2)]);
      renderWithProviders(<ProgressionView athleteId={42} audience="coach" />);

      await screen.findByTestId("mock-history-chart");
      expect(screen.queryByTestId("progression-group-select")).not.toBeInTheDocument();
    });

    it("elegir una copa filtra la línea, las tarjetas y la tabla a esa serie", async () => {
      const user = userEvent.setup();
      useHistory(coachPoints());
      renderWithProviders(<ProgressionView athleteId={42} audience="coach" />);

      const select = await screen.findByTestId("progression-group-select");
      await user.selectOptions(select, "7"); // Copa Valle

      expect(screen.getByTestId("mock-history-chart")).toHaveAttribute(
        "data-event-ids",
        "41,42",
      );
      expect(screen.queryByTestId("progression-championships")).not.toBeInTheDocument();
    });

    it("elegir el campeonato deja solo su tarjeta (sin línea)", async () => {
      const user = userEvent.setup();
      useHistory(coachPoints());
      renderWithProviders(<ProgressionView athleteId={42} audience="coach" />);

      const select = await screen.findByTestId("progression-group-select");
      await user.selectOptions(select, "9");

      expect(screen.queryByTestId("mock-history-chart")).not.toBeInTheDocument();
      expect(screen.getByTestId("championship-reading-card")).toBeInTheDocument();
    });
  });

  describe("audiencia familia", () => {
    it("nunca muestra «Brecha vs. 1.ª posición» ni «Brecha vs. podio»", async () => {
      useHistory(familyPoints());
      const { container } = renderWithProviders(
        <ProgressionView athleteId={42} audience="family" />,
      );

      await screen.findByTestId("championship-reading-card");
      expect(container).not.toHaveTextContent(/brecha vs\. 1\.ª posición/i);
      expect(container).not.toHaveTextContent(/brecha vs\. podio/i);
      // La brecha vs. mediana sí es comparable y se muestra.
      expect(within(screen.getByTestId("championship-reading-card")).getByText("Brecha vs. mediana")).toBeInTheDocument();
    });

    it("la tarjeta de campeonato enlaza a la vista de resultados de la familia (FR-017)", async () => {
      useHistory(familyPoints());
      renderWithProviders(<ProgressionView athleteId={42} audience="family" />);

      const card = await screen.findByTestId("championship-reading-card");
      expect(
        within(card).getByRole("link", { name: /ver competencia/i }),
      ).toHaveAttribute("href", "/parents/competitions/60");
    });

    it("usa el subtítulo familiar", async () => {
      useHistory(familyPoints());
      renderWithProviders(<ProgressionView athleteId={42} audience="family" />);

      expect(
        await screen.findByText(/cómo ha cambiado tu hijo o hija/i),
      ).toBeInTheDocument();
    });
  });

  describe("estados", () => {
    it("vacío: mensaje claro y sin gráfica", async () => {
      mswServer.use(raceHistoryEmptyHandler);
      renderWithProviders(<ProgressionView athleteId={42} audience="coach" />);

      expect(await screen.findByTestId("history-empty")).toHaveTextContent(
        /todavía no hay carreras históricas/i,
      );
      expect(screen.queryByTestId("mock-history-chart")).not.toBeInTheDocument();
    });

    it("error: role=alert, sin contenido parcial", async () => {
      mswServer.use(raceHistoryErrorHandler);
      renderWithProviders(<ProgressionView athleteId={42} audience="coach" />);

      expect(await screen.findByRole("alert")).toHaveTextContent(
        /no pudimos cargar la progresión histórica/i,
      );
      expect(screen.queryByTestId("history-table")).not.toBeInTheDocument();
    });
  });

  describe("accesibilidad", () => {
    it("coach: sin violaciones jest-axe con copas, campeonato y selectores", async () => {
      useHistory(coachPoints());
      const { container } = renderWithProviders(
        <ProgressionView athleteId={42} audience="coach" />,
      );
      await screen.findByTestId("championship-reading-card");
      await waitFor(() =>
        expect(screen.queryByRole("status", { name: /cargando/i })).toBeNull(),
      );

      expect(await axe(container)).toHaveNoViolations();
    });

    it("familia: sin violaciones jest-axe", async () => {
      useHistory(familyPoints());
      const { container } = renderWithProviders(
        <ProgressionView athleteId={42} audience="family" />,
      );
      await screen.findByTestId("championship-reading-card");

      expect(await axe(container)).toHaveNoViolations();
    });
  });
});
