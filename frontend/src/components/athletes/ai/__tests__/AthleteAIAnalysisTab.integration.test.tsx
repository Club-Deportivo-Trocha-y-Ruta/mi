/**
 * T080 (feature 036, US7) — integración real Panorama → detalle → Histórico.
 *
 * `AthleteAIAnalysisTab.test.tsx` mockea `PanoramaView` por completo
 * (`vi.mock("@/components/athletes/ai/PanoramaView", ...)`), así que la
 * composición real nunca se ejercía: click en "Releer último" (dentro de
 * `HeroLastInsightCard`, montado por `PanoramaView`) → `onOpenDetail` →
 * `AthleteAIAnalysisTab` fija `selectedInsightId` y salta al sub-tab
 * "Histórico" → `InsightsTimeline` (también real aquí, por la misma razón:
 * el otro archivo lo mockea) recibe `selectedInsightId` y su
 * `InsightDetailDrawer` interno abre el análisis correcto.
 *
 * Este archivo es NUEVO (no extiende AthleteAIAnalysisTab.test.tsx) porque
 * `vi.mock(...)` se hoistea a nivel de archivo — no hay forma de "des-
 * mockear" `PanoramaView`/`InsightsTimeline` para un solo test dentro de un
 * archivo que ya los mockea globalmente para el resto de su suite.
 *
 * Sólo se mockean los sub-componentes AJENOS a esta composición
 * (EvolutionChart, ComparatorPanel, DistributionChart, LaunchAnalysisForm)
 * — mismo criterio que el archivo hermano, pero recortado a lo que este
 * flujo no toca.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

vi.mock("@/api/athleteNewsletters", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/athleteNewsletters")>();
  return {
    ...actual,
    useAttachInsightsToNewsletter: vi.fn(() => ({
      isPending: false,
      isSuccess: false,
      isError: false,
      data: undefined,
      error: null,
      mutate: vi.fn(),
      reset: vi.fn(),
    })),
  };
});

// Deliberadamente NO mockeados: PanoramaView, InsightsTimeline (el objeto
// de este test). Sí se mockean los sub-tabs ajenos a la composición.
vi.mock("@/components/athletes/ai/EvolutionChart", () => ({
  EvolutionChart: () => <div data-testid="mock-evolution-chart">evolution</div>,
}));
vi.mock("@/components/athletes/ai/ComparatorPanel", () => ({
  ComparatorPanel: () => <div data-testid="mock-comparator-panel">compare</div>,
}));
vi.mock("@/components/athletes/ai/DistributionChart", () => ({
  DistributionChart: () => (
    <div data-testid="mock-distribution-chart">distribution</div>
  ),
}));
vi.mock("@/components/athletes/ai/LaunchAnalysisForm", () => ({
  LaunchAnalysisForm: () => <div data-testid="mock-launch-form">launch</div>,
}));

import { mswServer } from "@/test/setup";
import { mockInsight, mockInsightDetail } from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { AthleteAIAnalysisTab } from "@/components/athletes/ai/AthleteAIAnalysisTab";
import type { AthleteOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

const athlete: AthleteOut = {
  id: 42,
  user_id: 100,
  first_name: "Sebastián",
  last_name: "García",
  birth_date: "2012-01-15",
  sex: Sex.M,
  club_join_date: "2024-01-01",
  years_in_club: 2,
  age_decimal: 14.3,
  category: "Sub-15",
  club_id: 1,
  created_at: "2024-01-01T00:00:00Z",
};

// Dos insights con `summary_text` DISTINTO y verificable — así, si el
// detalle abierto tras el click no corresponde al insight que mostraba el
// Hero, el test lo detecta (contenido idéntico entre ambos habría dejado
// pasar un `selectedInsightId` incorrecto sin que ningún assert lo notara).
const HERO_INSIGHT_ID = 501;
const OTHER_INSIGHT_ID = 502;
const HERO_TEXT = "Texto exclusivo del insight A — mostrado por el Hero.";
const OTHER_TEXT = "Texto exclusivo del insight B — NO debería abrirse aquí.";

function useDistinguishableInsightHandlers() {
  mswServer.use(
    http.get("*/api/athletes/:athleteId/race-analysis/insights", () => {
      const items = [
        mockInsight({
          id: HERO_INSIGHT_ID,
          valida_num: 4,
          summary_text: HERO_TEXT,
          generated_at: "2026-05-18T10:00:00Z",
        }),
        mockInsight({
          id: OTHER_INSIGHT_ID,
          valida_num: 3,
          summary_text: OTHER_TEXT,
          generated_at: "2026-04-20T10:00:00Z",
        }),
      ];
      return HttpResponse.json({
        items,
        total: items.length,
        limit: 50,
        offset: 0,
      });
    }),
    http.get(
      "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
      ({ params }) => {
        const id = Number(params.insightId);
        const text = id === HERO_INSIGHT_ID ? HERO_TEXT : OTHER_TEXT;
        return HttpResponse.json(mockInsightDetail({ id, summary_text: text }));
      },
    ),
  );
}

describe("AthleteAIAnalysisTab — T080 integración real Panorama → detalle → Histórico", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDistinguishableInsightHandlers();
  });

  it("coach: click en 'Releer último' del Hero real abre el Histórico real con el insight correcto preseleccionado", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);

    // El Hero (PanoramaView real, no mockeado) muestra el insight "más
    // reciente" — su propio texto, sin truncar. `hero-last-insight-card`
    // es el mismo testid del skeleton de carga, así que esperamos a que
    // aparezca el botón (sólo se renderiza con datos ya cargados) en vez
    // de resolver sobre el esqueleto todavía vacío.
    await screen.findByTestId("hero-btn-reread");
    const hero = screen.getByTestId("hero-last-insight-card");
    expect(within(hero).getByText(HERO_TEXT)).toBeInTheDocument();
    expect(within(hero).queryByText(OTHER_TEXT)).not.toBeInTheDocument();

    await user.click(within(hero).getByTestId("hero-btn-reread"));

    // El sub-tab salta a Histórico.
    await waitFor(() => {
      expect(screen.getByTestId("ai-subtab-history")).toHaveAttribute(
        "data-state",
        "active",
      );
    });

    // InsightsTimeline real (no mockeado): ambas cards de la lista están
    // presentes — confirma que esta prueba monta el componente real, no un
    // doble vacío.
    await waitFor(() => {
      expect(
        screen.getByTestId(`insight-card-${HERO_INSIGHT_ID}`),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByTestId(`insight-card-${OTHER_INSIGHT_ID}`),
    ).toBeInTheDocument();

    // El detalle correcto (el del Hero, HERO_INSIGHT_ID) se abrió SOLO —
    // no el del otro insight de la lista. Esto es lo que este test existe
    // para probar: `selectedInsightId` viajó del Hero al drawer intacto.
    await waitFor(() => {
      expect(screen.getByText("Detalle del análisis")).toBeInTheDocument();
    });
    const dialog = screen.getByText("Detalle del análisis").closest(
      '[role="dialog"]',
    ) as HTMLElement;
    expect(dialog).not.toBeNull();
    expect(within(dialog).getByText(HERO_TEXT)).toBeInTheDocument();
    expect(within(dialog).queryByText(OTHER_TEXT)).not.toBeInTheDocument();
  });

  it("parent: la misma composición (Panorama real → Histórico real) funciona sin exponer boletín ni distribución", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="parent" />);

    await screen.findByTestId("hero-btn-reread");
    const hero = screen.getByTestId("hero-last-insight-card");
    await user.click(within(hero).getByTestId("hero-btn-reread"));

    await waitFor(() => {
      expect(screen.getByTestId("ai-subtab-history")).toHaveAttribute(
        "data-state",
        "active",
      );
    });
    await waitFor(() => {
      expect(screen.getByText("Detalle del análisis")).toBeInTheDocument();
    });
    const dialog = screen.getByText("Detalle del análisis").closest(
      '[role="dialog"]',
    ) as HTMLElement;
    expect(within(dialog).getByText(HERO_TEXT)).toBeInTheDocument();

    // Privacidad: el padre no tiene checkbox de boletín en la card abierta.
    expect(
      screen.queryByTestId(`insight-checkbox-${HERO_INSIGHT_ID}`),
    ).not.toBeInTheDocument();
  });
});
