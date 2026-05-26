/**
 * Tests vitest — PanoramaView + HeroLastInsightCard (Sprint 1).
 *
 * El sub-tab "Panorama" es el default ahora en AthleteAIAnalysisTab.
 * En Sprint 1 solo envuelve HeroLastInsightCard, así que probamos:
 *  - Render del último insight con datos del handler MSW default.
 *  - Empty state con copy diferenciado coach vs parent.
 *  - Privacidad mode=parent: sin badge "Confianza", sin botón "Agregar al boletín".
 *  - Callback onOpenDetail invocado con el insight.id al clickear "Releer último".
 *  - 0 violaciones jest-axe en coach y parent.
 *  - `BookmarkPlus` icon tiene `aria-hidden="true"` y el botón un accessible name.
 *
 * Privacidad Ley 1581: este componente nunca expone datos operativos
 * (model, prompt, tokens) ni el badge de confianza al rol parent.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

// Auth mock — coach por default, override por test si hace falta.
vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Coach", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

import { mswServer } from "@/test/setup";
import {
  emptyInsightsHandler,
  mockInsight,
} from "@/test/msw/athleteRaceAnalysisHandlers";
import { http, HttpResponse } from "msw";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { PanoramaView } from "@/components/athletes/ai/PanoramaView";
import { HeroLastInsightCard } from "@/components/athletes/ai/HeroLastInsightCard";
import type { AthleteOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

const athlete: AthleteOut = {
  id: 42,
  user_id: 100,
  first_name: "Juan Pérez",
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

describe("PanoramaView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza HeroLastInsightCard con el último insight", async () => {
    const onOpenDetail = vi.fn();
    const onAddToNewsletter = vi.fn();
    renderWithProviders(
      <PanoramaView
        athlete={athlete}
        mode="coach"
        onOpenDetail={onOpenDetail}
        onAddToNewsletter={onAddToNewsletter}
      />,
    );
    // Esperamos a que termine el loading: el botón "Releer último" sólo
    // aparece cuando ya hay datos (testId del card también lo usa loading).
    await waitFor(() => {
      expect(screen.getByTestId("hero-btn-reread")).toBeInTheDocument();
    });
    // Wrapper Panorama presente
    expect(screen.getByTestId("panorama-view")).toBeInTheDocument();
    // El contenido del summary_text del mock aparece sin truncar.
    expect(
      screen.getByText(/Resumen del desempeño del deportista/i),
    ).toBeInTheDocument();
  });

  it("coach ve badge de confianza y botón 'Agregar al boletín'", async () => {
    renderWithProviders(
      <PanoramaView
        athlete={athlete}
        mode="coach"
        onOpenDetail={vi.fn()}
        onAddToNewsletter={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hero-btn-reread")).toBeInTheDocument();
    });
    // Badge confianza visible para coach
    expect(screen.getByText(/Confianza alta/i)).toBeInTheDocument();
    // Botón "Agregar al boletín" visible para coach
    expect(
      screen.getByTestId("hero-btn-add-newsletter"),
    ).toBeInTheDocument();
  });

  it("parent NO ve badge de confianza ni botón 'Agregar al boletín'", async () => {
    renderWithProviders(
      <PanoramaView
        athlete={athlete}
        mode="parent"
        onOpenDetail={vi.fn()}
        onAddToNewsletter={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hero-btn-reread")).toBeInTheDocument();
    });
    // Privacidad Ley 1581: padre no ve metadatos operativos.
    expect(screen.queryByText(/Confianza/i)).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("hero-btn-add-newsletter"),
    ).not.toBeInTheDocument();
  });

  it("click en 'Releer último' invoca onOpenDetail con el insight.id", async () => {
    const onOpenDetail = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <PanoramaView
        athlete={athlete}
        mode="coach"
        onOpenDetail={onOpenDetail}
        onAddToNewsletter={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hero-btn-reread")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("hero-btn-reread"));
    // El mock por default tiene id=1
    expect(onOpenDetail).toHaveBeenCalledTimes(1);
    expect(onOpenDetail).toHaveBeenCalledWith(1);
  });

  it("click en 'Agregar al boletín' (coach) invoca onAddToNewsletter con el insight.id", async () => {
    const onAddToNewsletter = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <PanoramaView
        athlete={athlete}
        mode="coach"
        onOpenDetail={vi.fn()}
        onAddToNewsletter={onAddToNewsletter}
      />,
    );
    await waitFor(() => {
      expect(
        screen.getByTestId("hero-btn-add-newsletter"),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("hero-btn-add-newsletter"));
    expect(onAddToNewsletter).toHaveBeenCalledTimes(1);
    expect(onAddToNewsletter).toHaveBeenCalledWith(1);
  });

  it("empty state — copy distinto para coach vs parent", async () => {
    // Coach
    mswServer.use(emptyInsightsHandler);
    const { unmount } = renderWithProviders(
      <PanoramaView
        athlete={athlete}
        mode="coach"
        onOpenDetail={vi.fn()}
        onAddToNewsletter={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(
        screen.getByText(/aún no hay análisis aprobados/i),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/lanza el primero/i)).toBeInTheDocument();
    unmount();

    // Parent
    mswServer.use(emptyInsightsHandler);
    renderWithProviders(
      <PanoramaView
        athlete={athlete}
        mode="parent"
        onOpenDetail={vi.fn()}
        onAddToNewsletter={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(
        screen.getByText(/cuando se aprueben análisis de tu hijo/i),
      ).toBeInTheDocument();
    });
    // No botón add-to-newsletter en empty parent.
    expect(
      screen.queryByTestId("hero-btn-add-newsletter"),
    ).not.toBeInTheDocument();
  });

  it("HeroLastInsightCard preview de v2 extrae sección 'Qué pasó'", async () => {
    // Cuando el insight es v2, el hero muestra el bloque "Qué pasó" en
    // lugar del summary completo.
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights",
        () =>
          HttpResponse.json({
            items: [
              mockInsight({
                prompt_version: "race_analyst_v2",
                summary_text:
                  "## Qué pasó\nProgresó en frenada en curva 3.\n\n## Recorrido hasta aquí\nDesde V-I, mejora constante.",
              }),
            ],
            total: 1,
            limit: 50,
            offset: 0,
          }),
      ),
    );
    renderWithProviders(
      <PanoramaView
        athlete={athlete}
        mode="coach"
        onOpenDetail={vi.fn()}
        onAddToNewsletter={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hero-btn-reread")).toBeInTheDocument();
    });
    // Texto extraído (sin header markdown crudo).
    expect(
      screen.getByText(/Progresó en frenada en curva 3/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^##\s/)).not.toBeInTheDocument();
    // Las otras secciones NO aparecen en el hero (sólo "Qué pasó").
    expect(
      screen.queryByText(/Desde V-I, mejora constante/i),
    ).not.toBeInTheDocument();
  });

  // ---------- a11y ----------
  it("no tiene violaciones a11y en mode=coach (con datos)", async () => {
    const { container } = renderWithProviders(
      <PanoramaView
        athlete={athlete}
        mode="coach"
        onOpenDetail={vi.fn()}
        onAddToNewsletter={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hero-btn-reread")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones a11y en mode=parent (con datos)", async () => {
    const { container } = renderWithProviders(
      <PanoramaView
        athlete={athlete}
        mode="parent"
        onOpenDetail={vi.fn()}
        onAddToNewsletter={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hero-btn-reread")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones a11y en empty state (parent)", async () => {
    mswServer.use(emptyInsightsHandler);
    const { container } = renderWithProviders(
      <PanoramaView
        athlete={athlete}
        mode="parent"
        onOpenDetail={vi.fn()}
        onAddToNewsletter={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(
        screen.getByText(/cuando se aprueben análisis de tu hijo/i),
      ).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  // ---------- HeroLastInsightCard atómico ----------
  describe("HeroLastInsightCard — accesibilidad del botón con ícono", () => {
    it("'Agregar al boletín' tiene icono BookmarkPlus con aria-hidden y accessible name", async () => {
      renderWithProviders(
        <HeroLastInsightCard
          athlete={athlete}
          mode="coach"
          onOpenDetail={vi.fn()}
          onAddToNewsletter={vi.fn()}
        />,
      );
      await waitFor(() => {
        expect(
          screen.getByTestId("hero-btn-add-newsletter"),
        ).toBeInTheDocument();
      });
      const btn = screen.getByTestId("hero-btn-add-newsletter");
      // accessible name por texto visible
      expect(btn).toHaveAccessibleName(/Agregar al boletín/i);
      // ícono interno no expuesto a SR
      const svg = btn.querySelector("svg");
      expect(svg).toBeTruthy();
      expect(svg).toHaveAttribute("aria-hidden", "true");
    });

    // ---------------------------------------------------------------------
    // Sprint 2 BB4 — el botón Hero refleja estado de multi-select.
    // ---------------------------------------------------------------------

    it("con newsletterSelection vacío muestra 'Agregar al boletín'; al ya estar seleccionado muestra 'Quitar del boletín'", async () => {
      const onToggle = vi.fn();
      const { rerender } = renderWithProviders(
        <HeroLastInsightCard
          athlete={athlete}
          mode="coach"
          onOpenDetail={vi.fn()}
          onAddToNewsletter={vi.fn()}
          newsletterSelection={new Set<number>()}
          onToggleSelection={onToggle}
        />,
      );
      await waitFor(() => {
        const btn = screen.getByTestId("hero-btn-add-newsletter");
        expect(btn).toHaveAccessibleName(/Agregar al boletín/i);
      });

      // Insight default tiene id=1 (mockInsight).
      rerender(
        <HeroLastInsightCard
          athlete={athlete}
          mode="coach"
          onOpenDetail={vi.fn()}
          onAddToNewsletter={vi.fn()}
          newsletterSelection={new Set<number>([1])}
          onToggleSelection={onToggle}
        />,
      );
      await waitFor(() => {
        const btn = screen.getByTestId("hero-btn-add-newsletter");
        expect(btn).toHaveAccessibleName(/Quitar del boletín/i);
      });
    });

    it("con onToggleSelection definido, click invoca toggle (no onAddToNewsletter)", async () => {
      const onAdd = vi.fn();
      const onToggle = vi.fn();
      const user = userEvent.setup();
      renderWithProviders(
        <HeroLastInsightCard
          athlete={athlete}
          mode="coach"
          onOpenDetail={vi.fn()}
          onAddToNewsletter={onAdd}
          newsletterSelection={new Set<number>()}
          onToggleSelection={onToggle}
        />,
      );
      await waitFor(() => {
        expect(
          screen.getByTestId("hero-btn-add-newsletter"),
        ).toBeInTheDocument();
      });
      await user.click(screen.getByTestId("hero-btn-add-newsletter"));
      expect(onToggle).toHaveBeenCalledTimes(1);
      expect(onToggle).toHaveBeenCalledWith(1);
      expect(onAdd).not.toHaveBeenCalled();
    });
  });

  // ---------------------------------------------------------------------------
  // Sprint 2 BB2 — MiniSparkline + KPI cards en PanoramaView
  // ---------------------------------------------------------------------------

  describe("PanoramaView — MiniSparkline + KPIs (BB2)", () => {
    it("renderiza el contenedor 'mini-evolution-sparkline' cuando hay evolución (≥2 puntos)", async () => {
      // Handler default de evolution devuelve 4 puntos no-nulos.
      renderWithProviders(
        <PanoramaView
          athlete={athlete}
          mode="coach"
          onOpenDetail={vi.fn()}
          onAddToNewsletter={vi.fn()}
        />,
      );
      await waitFor(() => {
        expect(
          screen.getByTestId("mini-evolution-sparkline"),
        ).toBeInTheDocument();
      });
      // No debe mostrar el empty state.
      expect(
        screen.queryByText(/al menos 2 análisis/i),
      ).not.toBeInTheDocument();
    });

    it("muestra empty state cuando hay <2 puntos en la serie", async () => {
      // Override: serie con un solo punto.
      mswServer.use(
        http.get("*/api/athletes/:athleteId/race-analysis/evolution", () =>
          HttpResponse.json({
            season: 2026,
            metric: "ranking",
            confidence: "low",
            series: [
              {
                valida_num: 1,
                event_id: 91,
                event_date: "2026-01-31",
                value: 5,
                unit: null,
              },
            ],
          }),
        ),
      );
      renderWithProviders(
        <PanoramaView
          athlete={athlete}
          mode="coach"
          onOpenDetail={vi.fn()}
          onAddToNewsletter={vi.fn()}
        />,
      );
      await waitFor(() => {
        expect(
          screen.getByText(/al menos 2 análisis/i),
        ).toBeInTheDocument();
      });
      // El testid del wrapper se mantiene aunque sea empty.
      expect(
        screen.getByTestId("mini-evolution-sparkline"),
      ).toBeInTheDocument();
    });

    it("renderiza las 3 KPI cards con sus testids esperados", async () => {
      renderWithProviders(
        <PanoramaView
          athlete={athlete}
          mode="coach"
          onOpenDetail={vi.fn()}
          onAddToNewsletter={vi.fn()}
        />,
      );
      await waitFor(() => {
        expect(screen.getByTestId("panorama-kpi-total")).toBeInTheDocument();
      });
      expect(
        screen.getByTestId("panorama-kpi-best-position"),
      ).toBeInTheDocument();
      // NOTA: el ingeniero usó 'panorama-kpi-races' (no 'panorama-kpi-validas')
      // porque la KPI fue renombrada a "Válidas completadas" (TODO Sprint 3
      // para "Podios"). Cubrimos el testid real.
      expect(screen.getByTestId("panorama-kpi-races")).toBeInTheDocument();
      // Labels visibles para sanidad de copy — esperamos a que el loading
      // de evolution/insights termine (skeleton → contenido con label).
      await waitFor(() => {
        expect(screen.getByText(/análisis aprobados/i)).toBeInTheDocument();
      });
      expect(screen.getByText(/mejor posición/i)).toBeInTheDocument();
      expect(screen.getByText(/válidas completadas/i)).toBeInTheDocument();
    });
  });
});
