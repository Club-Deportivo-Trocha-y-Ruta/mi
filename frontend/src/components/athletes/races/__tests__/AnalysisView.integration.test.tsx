/**
 * T080 (feature 036, US7) — integración real Panorama → detalle → Histórico.
 *
 * Feature 045 (T042): re-alojada desde
 * `AthleteAIAnalysisTab.integration.test.tsx`. `AnalysisView.test.tsx` mockea
 * `PanoramaView` e `InsightsTimeline` por completo, así que la composición
 * real nunca se ejercería allí: click en "Releer último" (dentro de
 * `HeroLastInsightCard`, montado por `PanoramaView`) → `onOpenDetail` →
 * `AnalysisView` fija `selectedInsightId` → `InsightsTimeline` (también real
 * aquí) recibe `selectedInsightId` y su `InsightDetailDrawer` interno abre el
 * análisis correcto. En la vista única ya no hay sub-tab al que saltar: el
 * histórico está en la misma pantalla, debajo del último análisis.
 *
 * Es un archivo aparte porque `vi.mock(...)` se hoistea a nivel de archivo —
 * no hay forma de "des-mockear" `PanoramaView`/`InsightsTimeline` para un solo
 * test dentro de un archivo que ya los mockea globalmente.
 *
 * Sólo se mockean los sub-componentes AJENOS a esta composición
 * (LaunchAnalysisForm, chat, resumen de temporada).
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
// de este test). Sí se mockean los componentes ajenos a la composición.
vi.mock("@/components/athletes/ai/AthleteAnalystChatPanel", () => ({
  AthleteAnalystChatPanel: () => <div data-testid="mock-chat-panel">chat</div>,
}));
vi.mock("@/components/athletes/ai/SeasonSummaryButton", () => ({
  SeasonSummaryButton: () => <div data-testid="mock-season-summary">summary</div>,
}));
vi.mock("@/components/athletes/ai/LaunchAnalysisForm", () => ({
  LaunchAnalysisForm: () => <div data-testid="mock-launch-form">launch</div>,
}));

import { mswServer } from "@/test/setup";
import { mockInsight, mockInsightDetail } from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { AnalysisView } from "@/components/athletes/races/AnalysisView";
import type { AthleteOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

const athlete: AthleteOut = {
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

describe("AnalysisView — T080 integración real Panorama → detalle → Histórico", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDistinguishableInsightHandlers();
  });

  it("coach: click en 'Releer último' del Hero real abre el Histórico real con el insight correcto preseleccionado", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AnalysisView athlete={athlete} audience="coach" />);

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

  it("familia: la misma composición (Panorama real → Histórico real) funciona sin exponer boletín", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AnalysisView athlete={athlete} audience="family" />);

    await screen.findByTestId("hero-btn-reread");
    const hero = screen.getByTestId("hero-last-insight-card");
    await user.click(within(hero).getByTestId("hero-btn-reread"));

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
