/**
 * Tests vitest para ComparatorPanel v2.
 *
 * Cubre:
 *   - Header + select temporada + selectores A/B + swap.
 *   - Empty state global (≤1 válida con insight aprobado, o <2 válidas de
 *     la MISMA copa — hotfix multicopa 2026-09-16).
 *   - Feature 045 (T039): las cifras salen de los puntos del historial del
 *     servidor (`GET .../race-analysis/history`, motor único) por `event_id`;
 *     el panel ya no lee el `metrics_snapshot` ni calcula percentiles.
 *   - Guard A===B (mismo valor → banner "elige distintas").
 *   - Tabla unificada Métrica/Antes/Después/Cambio con deltas tipados.
 *   - Triple canal (icono+color+texto) en celdas Δ.
 *   - Banner Circa-PHV cuando hay record antropométrico reciente.
 *   - A11y (jest-axe) sin violaciones en estados clave.
 *
 * Hotfix multicopa (2026-09-16, plans/multicopa-identidad-valida.md):
 *   - Las opciones A/B ahora salen de las carreras reales del atleta
 *     (`GET .../races`) cruzadas con sus insights aprobados, por
 *     `event_id` — no de un calendario fijo `valida_num` 1..7+CD.
 *   - Dos copas con la misma `valida_num` producen etiquetas DISTINTAS
 *     (`raceLabel`), nunca colapsan en una sola opción.
 *   - B se bloquea a la misma copa que A una vez elegido A (y viceversa).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
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

import { mswServer } from "@/test/setup";
import { mockInsight } from "@/test/msw/athleteRaceAnalysisHandlers";
import {
  makeAthleteRaceHistoryRead,
  makeRaceHistoryPoint,
} from "@/test/msw/raceHistoryHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { ComparatorPanel } from "@/components/athletes/ai/ComparatorPanel";
import type { RaceParticipationOption } from "@/types/athleteRaceAnalysis.types";

// ---------------------------------------------------------------------------
// Handlers helper
// ---------------------------------------------------------------------------

/** Carrera de la Copa Valle (series_id=12) para la válida dada. */
function copaValleRace(
  valida: number,
  overrides?: Partial<RaceParticipationOption>,
): RaceParticipationOption {
  return {
    event_id: 90 + valida,
    sequence_number: valida,
    series_kind: "cup",
    event_date: `2026-01-${String(10 + valida).padStart(2, "0")}`,
    event_name: `Copa Valle — Válida ${valida}`,
    location: "Cali",
    label: `Copa Valle · Válida ${valida} — Cali`,
    series_id: 12,
    series_name: "Copa Valle de Ciclomontañismo",
    series_short_name: "Copa Valle",
    series_level: "departmental",
    ...overrides,
  };
}

/** Carrera de la Copa Let's GO (series_id=55) para la válida dada. */
function letsGoRace(
  valida: number,
  overrides?: Partial<RaceParticipationOption>,
): RaceParticipationOption {
  return {
    event_id: 200 + valida,
    sequence_number: valida,
    series_kind: "cup",
    event_date: `2026-02-${String(10 + valida).padStart(2, "0")}`,
    event_name: `Copa Let's GO — Válida ${valida}`,
    location: "Alcalá",
    label: `Let's GO · Válida ${valida} — Alcalá`,
    series_id: 55,
    series_name: "Copa Let's GO",
    series_short_name: "Let's GO",
    series_level: "departmental",
    ...overrides,
  };
}

function racesHandler(items: RaceParticipationOption[]) {
  return http.get(
    "*/api/athletes/:athleteId/race-analysis/races",
    () => HttpResponse.json({ season: 2026, items }),
  );
}

/**
 * Devuelve una lista de insights de temporada (uno por válida de Copa
 * Valle, `event_id` alineado con `copaValleRace`). Por default crea
 * insights aprobados/activos para válidas 1..4 con id = valida*10.
 */
function defaultSeasonListHandler(
  validas: number[] = [1, 3, 4],
  overrides?: (valida: number) => Partial<ReturnType<typeof mockInsight>>,
) {
  return http.get(
    "*/api/athletes/:athleteId/race-analysis/insights",
    () => {
      const items = validas.map((v) =>
        mockInsight({
          id: v * 10,
          valida_num: v,
          season: 2026,
          event_id: 90 + v,
          series_id: 12,
          series_name: "Copa Valle de Ciclomontañismo",
          series_short_name: "Copa Valle",
          ...(overrides?.(v) ?? {}),
        }),
      );
      return HttpResponse.json({
        items,
        total: items.length,
        limit: 50,
        offset: 0,
      });
    },
  );
}

/**
 * Historial del servidor (motor único) con un punto por válida de Copa Valle
 * (`event_id` alineado con `copaValleRace`: 90 + válida). Mejora progresiva:
 * mejor posición, percentil y brechas a medida que avanza la temporada.
 */
function historyPoint(valida: number, overrides?: Parameters<typeof makeRaceHistoryPoint>[0]) {
  return makeRaceHistoryPoint({
    event_id: 90 + valida,
    event_date: `2026-01-${String(10 + valida).padStart(2, "0")}`,
    season: 2026,
    label: `Válida ${valida} — Cali`,
    series_id: 12,
    position: Math.max(1, 8 - valida),
    field_size: 12,
    timed_finishers: 12,
    percentile: 40 + valida * 10,
    gap_to_median_pct: 2 - valida * 1.5,
    gap_to_winner_pct: 12 - valida * 2,
    gap_to_podium_pct: 8 - valida * 1.5,
    ...overrides,
  });
}

function defaultHistoryHandler(
  overridesByValida?: Record<number, Parameters<typeof makeRaceHistoryPoint>[0]>,
) {
  return http.get("*/api/athletes/:athleteId/race-analysis/history", () =>
    HttpResponse.json(
      makeAthleteRaceHistoryRead({
        points: [1, 2, 3, 4].map((v) => historyPoint(v, overridesByValida?.[v])),
      }),
    ),
  );
}

/** Mock vacío de anthropometry — sin record reciente Circa-PHV. */
function anthropometryEmptyHandler() {
  return http.get("*/api/athletes/:athleteId/anthropometry", () => {
    return HttpResponse.json([]);
  });
}

/** Mock anthropometry con un record Circa-PHV dentro de los últimos 90 días. */
function anthropometryCircaPHVHandler() {
  return http.get("*/api/athletes/:athleteId/anthropometry", () => {
    const recentDate = new Date();
    recentDate.setDate(recentDate.getDate() - 30); // hace 30 días
    return HttpResponse.json([
      {
        id: 1,
        athlete_id: 42,
        evaluation_date: recentDate.toISOString().slice(0, 10),
        weight_kg: 45,
        standing_height_cm: 160,
        sitting_height_cm: 80,
        arm_span_cm: null,
        leg_length_cm: 80,
        leg_sitting_ratio: 1.0,
        maturity_offset: 0.2,
        age_at_phv: 13.5,
        maturation_status: "Circa-PHV",
        training_implications: null,
        evaluated_by: 1,
        created_at: new Date().toISOString(),
        notes: null,
      },
    ]);
  });
}

const DEFAULT_RACES = [1, 2, 3, 4].map((v) => copaValleRace(v));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ComparatorPanel v2", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mswServer.use(
      defaultSeasonListHandler(),
      defaultHistoryHandler(),
      anthropometryEmptyHandler(),
      racesHandler(DEFAULT_RACES),
    );
  });

  it("renderiza header con título + select temporada + selectores A/B + swap", async () => {
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    expect(screen.getByTestId("comparator-panel")).toBeInTheDocument();
    expect(screen.getByTestId("comparator-season-select")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("comparator-col-a")).toBeInTheDocument();
      expect(screen.getByTestId("comparator-col-b")).toBeInTheDocument();
      expect(screen.getByTestId("comparator-swap")).toBeInTheDocument();
    });
  });

  it("muestra empty state cuando hay menos de 2 válidas con insight aprobado", async () => {
    mswServer.use(
      defaultSeasonListHandler([4]),
      defaultHistoryHandler(),
      anthropometryEmptyHandler(),
      racesHandler(DEFAULT_RACES),
    );
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByTestId("comparator-empty-pair")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/al menos 2 válidas de la misma copa/i),
    ).toBeInTheDocument();
  });

  it("muestra empty state distinto cuando no hay ningún insight aprobado", async () => {
    mswServer.use(
      defaultSeasonListHandler([]),
      defaultHistoryHandler(),
      anthropometryEmptyHandler(),
      racesHandler(DEFAULT_RACES),
    );
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByTestId("comparator-empty-pair")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/aún no hay análisis aprobados/i),
    ).toBeInTheDocument();
  });

  it("muestra empty state cuando hay 2+ válidas pero de copas DISTINTAS (hotfix multicopa)", async () => {
    // Una válida de Copa Valle + una de Copa Let's GO — 2 insights en total,
    // pero ninguna copa individual llega a 2, así que no hay par válido.
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights",
        () =>
          HttpResponse.json({
            items: [
              mockInsight({
                id: 40,
                valida_num: 4,
                event_id: 94,
                series_id: 12,
                series_name: "Copa Valle de Ciclomontañismo",
                series_short_name: "Copa Valle",
              }),
              mockInsight({
                id: 240,
                valida_num: 4,
                event_id: 204,
                series_id: 55,
                series_name: "Copa Let's GO",
                series_short_name: "Let's GO",
              }),
            ],
            total: 2,
            limit: 50,
            offset: 0,
          }),
      ),
      defaultHistoryHandler(),
      anthropometryEmptyHandler(),
      racesHandler([copaValleRace(4), letsGoRace(4)]),
    );
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByTestId("comparator-empty-pair")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/al menos 2 válidas de la misma copa/i),
    ).toBeInTheDocument();
  });

  it("renderiza tabla unificada Métrica/Antes/Después/Cambio con deltas válidos", async () => {
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    // Filas del motor: posición, brecha vs. mediana, brecha vs. podio y
    // percentil (sin tiempo total, sin Δ vs mejor).
    await waitFor(() => {
      expect(screen.getByRole("rowheader", { name: "Posición" })).toBeInTheDocument();
    });
    for (const metric of ["Brecha vs. mediana", "Brecha vs. podio", "Percentil"]) {
      expect(screen.getByRole("rowheader", { name: metric })).toBeInTheDocument();
    }
    expect(screen.queryByText("Tiempo total")).not.toBeInTheDocument();
    expect(screen.queryByText(/δ vs mejor propia/i)).not.toBeInTheDocument();
  });

  it("lee las cifras de los puntos del servidor: valores A/B y delta por métrica", async () => {
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    // Par por defecto = primera y última válida de la copa: válida 1 → 4.
    const table = await screen.findByTestId("comparator-diff-table");
    const row = (name: string) =>
      within(table).getByRole("rowheader", { name }).closest("tr") as HTMLElement;

    // Posición: P7 de 12 → P4 de 12 (subió 3 puestos).
    expect(within(row("Posición")).getByText("P7 de 12")).toBeInTheDocument();
    expect(within(row("Posición")).getByText("P4 de 12")).toBeInTheDocument();
    expect(within(row("Posición")).getByText("−3 puestos")).toBeInTheDocument();
    // Brecha vs. mediana: +0.5 % → −4.0 % (−4.5 pp, mejora).
    expect(within(row("Brecha vs. mediana")).getByText("+0.5 %")).toBeInTheDocument();
    expect(within(row("Brecha vs. mediana")).getByText("-4.0 %")).toBeInTheDocument();
    expect(within(row("Brecha vs. mediana")).getByText("−4.5 pp")).toBeInTheDocument();
    // Percentil: 50 → 80 (+30 pp, mayor es mejor).
    expect(within(row("Percentil")).getByText("50")).toBeInTheDocument();
    expect(within(row("Percentil")).getByText("80")).toBeInTheDocument();
    expect(within(row("Percentil")).getByText("+30.0 pp")).toBeInTheDocument();
    // Todas las métricas mejoraron.
    expect(screen.getByTestId("comparator-improvement-summary")).toHaveTextContent(
      /mejoró 4 de 4 métricas/i,
    );
  });

  it("un percentil `null` del motor (campo chico) deja la fila sin datos, no inventa un valor", async () => {
    mswServer.use(
      defaultHistoryHandler({
        1: { percentile: null, gap_to_median_pct: null },
        4: { percentile: null, gap_to_median_pct: null },
      }),
    );
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    const table = await screen.findByTestId("comparator-diff-table");
    const pctRow = within(table)
      .getByRole("rowheader", { name: "Percentil" })
      .closest("tr") as HTMLElement;

    expect(within(pctRow).getAllByText("sin dato")).toHaveLength(2);
    expect(within(pctRow).getByLabelText("sin datos para comparar")).toBeInTheDocument();
    // Solo cuentan las métricas con delta: posición y brecha vs. podio.
    expect(screen.getByTestId("comparator-improvement-summary")).toHaveTextContent(
      /mejoró 2 de 2 métricas/i,
    );
  });

  it("una carrera sin punto en el historial avisa en la tabla en vez de romperse", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/history", () =>
        HttpResponse.json(
          makeAthleteRaceHistoryRead({ points: [historyPoint(1)] }),
        ),
      ),
    );
    renderWithProviders(<ComparatorPanel athleteId={42} />);

    expect(
      await screen.findByText(/aún no tiene resultados en el historial/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("comparator-improvement-summary")).not.toBeInTheDocument();
  });

  it("la familia no tiene vista alterna: el panel ya no acepta `viewMode`", async () => {
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    await screen.findByTestId("comparator-diff-table");
    expect(
      screen.queryByText(/se mide contra sí mismo, no contra el ganador/i),
    ).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Wave 3 (hotfix multicopa) — banner tapering-mismatch sobre `priority`
  // real por evento, restaurado tras retirar el calendario Copa Valle.
  // -------------------------------------------------------------------------
  describe("banner tapering-mismatch (Wave 3)", () => {
    it("muestra el banner cuando A y B tienen priority distinto (A vs C)", async () => {
      mswServer.use(
        defaultSeasonListHandler([1, 4], (v) => ({
          priority: v === 1 ? "C" : "A",
        })),
        defaultHistoryHandler(),
        anthropometryEmptyHandler(),
        racesHandler([
          copaValleRace(1, { priority: "C" }),
          copaValleRace(4, { priority: "A" }),
        ]),
      );
      renderWithProviders(<ComparatorPanel athleteId={42} />);
      await waitFor(() => {
        expect(screen.getByTestId("comparator-tapering-banner")).toBeInTheDocument();
      });
      expect(screen.getByText(/carreras de distinto tipo/i)).toBeInTheDocument();
      expect(screen.getByText(/\(C vs A\)/)).toBeInTheDocument();
    });

    it("NO muestra el banner cuando A y B tienen el mismo priority", async () => {
      mswServer.use(
        defaultSeasonListHandler([1, 2], () => ({ priority: "C" })),
        defaultHistoryHandler(),
        anthropometryEmptyHandler(),
        racesHandler([
          copaValleRace(1, { priority: "C" }),
          copaValleRace(2, { priority: "C" }),
        ]),
      );
      renderWithProviders(<ComparatorPanel athleteId={42} />);
      await waitFor(() => {
        expect(screen.getByTestId("comparator-diff-table")).toBeInTheDocument();
      });
      expect(
        screen.queryByTestId("comparator-tapering-banner"),
      ).not.toBeInTheDocument();
    });

    it("NO muestra el banner cuando alguno de los dos lados tiene priority null (UNKNOWN)", async () => {
      mswServer.use(
        defaultSeasonListHandler([1, 4], (v) => ({
          priority: v === 1 ? null : "A",
        })),
        defaultHistoryHandler(),
        anthropometryEmptyHandler(),
        racesHandler([
          copaValleRace(1, { priority: null }),
          copaValleRace(4, { priority: "A" }),
        ]),
      );
      renderWithProviders(<ComparatorPanel athleteId={42} />);
      await waitFor(() => {
        expect(screen.getByTestId("comparator-diff-table")).toBeInTheDocument();
      });
      expect(
        screen.queryByTestId("comparator-tapering-banner"),
      ).not.toBeInTheDocument();
    });
  });

  it("muestra banner Circa-PHV cuando hay record antropométrico reciente", async () => {
    mswServer.use(
      defaultSeasonListHandler(),
      defaultHistoryHandler(),
      anthropometryCircaPHVHandler(),
      racesHandler(DEFAULT_RACES),
    );
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByTestId("comparator-phv-banner")).toBeInTheDocument();
    });
    expect(screen.getByText(/atleta en estirón/i)).toBeInTheDocument();
  });

  it("NO muestra banner Circa-PHV cuando no hay record reciente", async () => {
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByTestId("comparator-diff-table")).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId("comparator-phv-banner"),
    ).not.toBeInTheDocument();
  });

  it("guard A===B: muestra mensaje 'selecciona dos válidas distintas'", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByTestId("comparator-col-a")).toBeInTheDocument();
    });

    // Cambia el selector B al mismo valor que A.
    const selectA = screen.getByLabelText(
      /Válida A — seleccionar válida/i,
    ) as HTMLSelectElement;
    const valueA = selectA.value;
    const selectB = screen.getByLabelText(
      /Válida B — seleccionar válida/i,
    ) as HTMLSelectElement;
    await user.selectOptions(selectB, valueA);

    await waitFor(() => {
      expect(
        screen.getByText(/selecciona dos válidas distintas/i),
      ).toBeInTheDocument();
    });
    // Tabla NO renderiza en estado guard.
    expect(
      screen.queryByTestId("comparator-diff-table"),
    ).not.toBeInTheDocument();
  });

  it("botón swap intercambia los selectores A y B", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByTestId("comparator-swap")).toBeInTheDocument();
    });

    const selectA = screen.getByLabelText(
      /Válida A — seleccionar válida/i,
    ) as HTMLSelectElement;
    const selectB = screen.getByLabelText(
      /Válida B — seleccionar válida/i,
    ) as HTMLSelectElement;
    const initialA = selectA.value;
    const initialB = selectB.value;

    await user.click(screen.getByTestId("comparator-swap"));

    await waitFor(() => {
      expect(selectA.value).toBe(initialB);
      expect(selectB.value).toBe(initialA);
    });
  });

  it("muestra resumen 'Mejoró X de Y métricas — Confianza Z'", async () => {
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    await waitFor(() => {
      expect(
        screen.getByTestId("comparator-improvement-summary"),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByText(/mejoró \d+ de \d+ métricas/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/confianza/i)).toBeInTheDocument();
  });

  it("cambiar el selector A actualiza la comparación con la nueva carrera", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComparatorPanel athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByTestId("comparator-col-a")).toBeInTheDocument();
    });

    const selectA = screen.getByLabelText(
      /Válida A — seleccionar válida/i,
    ) as HTMLSelectElement;
    // event_id de la válida 3 = 93 (ver copaValleRace).
    await user.selectOptions(selectA, "93");

    await waitFor(() => {
      expect(selectA.value).toBe("93");
    });
  });

  // -------------------------------------------------------------------------
  // Hotfix multicopa (2026-09-16) — identidad de copa en las opciones A/B.
  // -------------------------------------------------------------------------
  describe("identidad de copa (hotfix multicopa)", () => {
    it("dos copas comparten valida_num=4 pero aparecen como opciones DISTINTAS, nunca colapsadas", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/insights",
          () =>
            HttpResponse.json({
              items: [
                mockInsight({
                  id: 40,
                  valida_num: 4,
                  event_id: 94,
                  series_id: 12,
                  series_name: "Copa Valle de Ciclomontañismo",
                  series_short_name: "Copa Valle",
                }),
                mockInsight({
                  id: 50,
                  valida_num: 5,
                  event_id: 95,
                  series_id: 12,
                  series_name: "Copa Valle de Ciclomontañismo",
                  series_short_name: "Copa Valle",
                }),
                mockInsight({
                  id: 240,
                  valida_num: 4,
                  event_id: 204,
                  series_id: 55,
                  series_name: "Copa Let's GO",
                  series_short_name: "Let's GO",
                }),
                mockInsight({
                  id: 260,
                  valida_num: 6,
                  event_id: 206,
                  series_id: 55,
                  series_name: "Copa Let's GO",
                  series_short_name: "Let's GO",
                }),
              ],
              total: 4,
              limit: 50,
              offset: 0,
            }),
        ),
        defaultHistoryHandler(),
        anthropometryEmptyHandler(),
        racesHandler([
          copaValleRace(4),
          copaValleRace(5),
          letsGoRace(4),
          letsGoRace(6),
        ]),
      );
      renderWithProviders(<ComparatorPanel athleteId={42} />);
      await waitFor(() => {
        expect(screen.getByTestId("comparator-col-a")).toBeInTheDocument();
      });

      const selectA = screen.getByLabelText(
        /Válida A — seleccionar válida/i,
      ) as HTMLSelectElement;
      const optionTexts = Array.from(selectA.options).map((o) => o.textContent);
      const copaValleV4 = optionTexts.find((t) => t?.includes("Copa Valle · V4"));
      const letsGoV4 = optionTexts.find((t) => t?.includes("Let's GO · V4"));
      expect(copaValleV4).toBeDefined();
      expect(letsGoV4).toBeDefined();
      expect(copaValleV4).not.toBe(letsGoV4);
    });

    it("bloquea seleccionar una carrera de otra copa una vez A está fijado", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/insights",
          () =>
            HttpResponse.json({
              items: [
                mockInsight({
                  id: 40,
                  valida_num: 4,
                  event_id: 94,
                  series_id: 12,
                  series_name: "Copa Valle de Ciclomontañismo",
                  series_short_name: "Copa Valle",
                }),
                mockInsight({
                  id: 50,
                  valida_num: 5,
                  event_id: 95,
                  series_id: 12,
                  series_name: "Copa Valle de Ciclomontañismo",
                  series_short_name: "Copa Valle",
                }),
                mockInsight({
                  id: 240,
                  valida_num: 4,
                  event_id: 204,
                  series_id: 55,
                  series_name: "Copa Let's GO",
                  series_short_name: "Let's GO",
                }),
              ],
              total: 3,
              limit: 50,
              offset: 0,
            }),
        ),
        defaultHistoryHandler(),
        anthropometryEmptyHandler(),
        racesHandler([copaValleRace(4), copaValleRace(5), letsGoRace(4)]),
      );
      renderWithProviders(<ComparatorPanel athleteId={42} />);
      await waitFor(() => {
        expect(screen.getByTestId("comparator-col-a")).toBeInTheDocument();
      });

      // Defaults: única copa con >=2 carreras es Copa Valle (94/95) — A/B
      // arrancan ahí. La opción de Copa Let's GO en el select B debe estar
      // deshabilitada, con la explicación accesible visible.
      const selectB = screen.getByLabelText(
        /Válida B — seleccionar válida/i,
      ) as HTMLSelectElement;
      const letsGoOption = Array.from(selectB.options).find((o) =>
        o.textContent?.includes("Let's GO"),
      );
      expect(letsGoOption).toBeDefined();
      expect(letsGoOption?.disabled).toBe(true);
      expect(
        screen.getAllByText(/solo se pueden comparar válidas de la misma copa/i)
          .length,
      ).toBeGreaterThan(0);
    });

    it("insight legacy sin series_name/series_short_name (null) no inventa una copa — cae a 'Válida N'", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/insights",
          () =>
            HttpResponse.json({
              items: [
                mockInsight({
                  id: 40,
                  valida_num: 4,
                  event_id: 94,
                  series_id: null,
                  series_name: null,
                  series_short_name: null,
                }),
                mockInsight({
                  id: 50,
                  valida_num: 5,
                  event_id: 95,
                  series_id: null,
                  series_name: null,
                  series_short_name: null,
                }),
              ],
              total: 2,
              limit: 50,
              offset: 0,
            }),
        ),
        defaultHistoryHandler(),
        anthropometryEmptyHandler(),
        racesHandler([
          copaValleRace(4, { series_id: undefined, series_name: undefined, series_short_name: null }),
          copaValleRace(5, { series_id: undefined, series_name: undefined, series_short_name: null }),
        ]),
      );
      renderWithProviders(<ComparatorPanel athleteId={42} />);
      await waitFor(() => {
        expect(screen.getByTestId("comparator-col-a")).toBeInTheDocument();
      });

      const selectA = screen.getByLabelText(
        /Válida A — seleccionar válida/i,
      ) as HTMLSelectElement;
      const optionTexts = Array.from(selectA.options).map((o) => o.textContent ?? "");
      expect(optionTexts.some((t) => /^Válida IV/.test(t))).toBe(true);
      expect(optionTexts.some((t) => t.includes("Copa"))).toBe(false);
    });
  });

  it("a11y: sin violaciones en estado nominal con deltas", async () => {
    const { container } = renderWithProviders(
      <ComparatorPanel athleteId={42} />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("comparator-diff-table")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("a11y: sin violaciones en estado guard A===B", async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(
      <ComparatorPanel athleteId={42} />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("comparator-col-a")).toBeInTheDocument();
    });
    const selectA = screen.getByLabelText(
      /Válida A — seleccionar válida/i,
    ) as HTMLSelectElement;
    const valueA = selectA.value;
    const selectB = screen.getByLabelText(
      /Válida B — seleccionar válida/i,
    ) as HTMLSelectElement;
    await user.selectOptions(selectB, valueA);
    await waitFor(() => {
      expect(
        screen.getByText(/selecciona dos válidas distintas/i),
      ).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("a11y: sin violaciones en empty state global", async () => {
    mswServer.use(
      defaultSeasonListHandler([4]),
      defaultHistoryHandler(),
      anthropometryEmptyHandler(),
      racesHandler(DEFAULT_RACES),
    );
    const { container } = renderWithProviders(
      <ComparatorPanel athleteId={42} />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("comparator-empty-pair")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  // ---------------------------------------------------------------------------
  // T038 — antes de este fix, un query fallido no mostraba NADA: el coach
  // veía el panel en blanco sin ninguna indicación de que algo falló.
  // ---------------------------------------------------------------------------
  describe("manejo de errores (T038)", () => {
    it("error en la lista de insights de temporada muestra ErrorState, no un panel en blanco", async () => {
      mswServer.use(
        http.get(
          "*/api/athletes/:athleteId/race-analysis/insights",
          () =>
            new HttpResponse(
              JSON.stringify({ detail: "Error interno" }),
              { status: 500, headers: { "Content-Type": "application/json" } },
            ),
        ),
        anthropometryEmptyHandler(),
        racesHandler(DEFAULT_RACES),
      );
      renderWithProviders(<ComparatorPanel athleteId={42} />);

      expect(
        await screen.findByText(/no se pudieron cargar los análisis de la temporada/i),
      ).toBeInTheDocument();
      // El panel no queda en blanco: hay un role="alert" explícito, y ni el
      // empty state ni la tabla se confunden con "sin datos".
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.queryByTestId("comparator-empty-pair")).not.toBeInTheDocument();
      expect(screen.queryByTestId("comparator-diff-table")).not.toBeInTheDocument();
    });

    it("Reintentar en el error de temporada vuelve a pedir la lista de insights", async () => {
      let calls = 0;
      mswServer.use(
        http.get("*/api/athletes/:athleteId/race-analysis/insights", () => {
          calls += 1;
          return new HttpResponse(
            JSON.stringify({ detail: "Error interno" }),
            { status: 500, headers: { "Content-Type": "application/json" } },
          );
        }),
        anthropometryEmptyHandler(),
        racesHandler(DEFAULT_RACES),
      );
      const user = userEvent.setup();
      renderWithProviders(<ComparatorPanel athleteId={42} />);

      await screen.findByText(/no se pudieron cargar los análisis de la temporada/i);
      expect(calls).toBe(1);

      await user.click(screen.getByRole("button", { name: /reintentar/i }));
      await waitFor(() => expect(calls).toBe(2));
    });

    it("error en el historial muestra ErrorState en la comparación", async () => {
      mswServer.use(
        defaultSeasonListHandler(),
        http.get(
          "*/api/athletes/:athleteId/race-analysis/history",
          () =>
            new HttpResponse(
              JSON.stringify({ detail: "Error interno" }),
              { status: 500, headers: { "Content-Type": "application/json" } },
            ),
        ),
        anthropometryEmptyHandler(),
        racesHandler(DEFAULT_RACES),
      );
      renderWithProviders(<ComparatorPanel athleteId={42} />);

      await waitFor(() => {
        expect(screen.getByTestId("comparator-col-a")).toBeInTheDocument();
      });
      expect(
        await screen.findByText(/no se pudieron cargar las métricas de las carreras/i),
      ).toBeInTheDocument();
      expect(screen.queryByTestId("comparator-diff-table")).not.toBeInTheDocument();
    });

    it("un fallo de red (forma cold-start) en la lista de temporada muestra la copy calmada", async () => {
      mswServer.use(
        http.get("*/api/athletes/:athleteId/race-analysis/insights", () =>
          HttpResponse.error(),
        ),
        anthropometryEmptyHandler(),
        racesHandler(DEFAULT_RACES),
      );
      renderWithProviders(<ComparatorPanel athleteId={42} />);

      expect(
        await screen.findByText(/la aplicación está iniciando/i),
      ).toBeInTheDocument();
      expect(
        screen.queryByText(/no se pudieron cargar los análisis de la temporada/i),
      ).not.toBeInTheDocument();
    });
  });
});
