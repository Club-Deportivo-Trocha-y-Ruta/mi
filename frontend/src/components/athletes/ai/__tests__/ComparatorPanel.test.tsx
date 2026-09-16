/**
 * Tests vitest para ComparatorPanel v2.
 *
 * Cubre:
 *   - Header + select temporada + selectores A/B + swap.
 *   - Empty state global (≤1 válida con insight aprobado, o <2 válidas de
 *     la MISMA copa — hotfix multicopa 2026-09-16).
 *   - Empty state legacy snapshot (snapshot sin schema_version=1).
 *   - Guard A===B (mismo valor → banner "elige distintas").
 *   - Tabla unificada Métrica/Antes/Después/Cambio con deltas tipados.
 *   - Triple canal (icono+color+texto) en celdas Δ.
 *   - Banner Circa-PHV cuando hay record antropométrico reciente.
 *   - Vista parent: sin números absolutos, frase educativa visible.
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
import { screen, waitFor } from "@testing-library/react";
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
import {
  mockInsight,
  mockInsightDetail,
  mockMetricsSnapshot,
} from "@/test/msw/athleteRaceAnalysisHandlers";
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

function defaultDetailHandler(
  detailByInsightId?: Record<number, Partial<ReturnType<typeof mockInsightDetail>>>,
) {
  return http.get(
    "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
    ({ params }) => {
      const id = Number(params.insightId);
      // valida_num inferida del id (id = valida*10).
      const valida = Math.floor(id / 10);
      const baseSnapshot = mockMetricsSnapshot({
        event_id: 90 + valida,
        valida_num: valida,
        race_time_ms: 2_500_000 - valida * 50_000, // mejora progresiva
        ranking_in_category: Math.max(1, 8 - valida),
        podium_gap_ms: 120_000 - valida * 25_000,
        category_size: 12,
      });
      return HttpResponse.json(
        mockInsightDetail({
          id,
          valida_num: valida,
          metrics_snapshot: baseSnapshot,
          ...(detailByInsightId?.[id] ?? {}),
        }),
      );
    },
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
      defaultDetailHandler(),
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
      defaultDetailHandler(),
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
      defaultDetailHandler(),
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
      defaultDetailHandler(),
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
    // Filas MVP: posición + gap al podio (sin tiempo total, sin Δ vs mejor).
    await waitFor(() => {
      expect(screen.queryByText("Posición categoría")).toBeInTheDocument();
      expect(screen.queryByText("Gap al podio")).toBeInTheDocument();
    });
    expect(screen.queryByText("Tiempo total")).not.toBeInTheDocument();
    expect(screen.queryByText(/δ vs mejor propia/i)).not.toBeInTheDocument();
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
        defaultDetailHandler(),
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
        defaultDetailHandler(),
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
        defaultDetailHandler(),
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
      defaultDetailHandler(),
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

  it("vista parent: sin tiempos absolutos, frase educativa visible, no muestra fila 'Tiempo total'", async () => {
    renderWithProviders(<ComparatorPanel athleteId={42} viewMode="parent" />);
    // Esperamos a que aparezca tanto la tabla como la frase educativa
    // (ambas pertenecen a ComparisonBody y vienen tras detail queries).
    await waitFor(() => {
      expect(
        screen.getByText(/se mide contra sí mismo, no contra el ganador/i),
      ).toBeInTheDocument();
    });

    // No hay fila "Tiempo total".
    expect(
      screen.queryByRole("rowheader", { name: /tiempo total/i }),
    ).not.toBeInTheDocument();

    // No hay fila "Δ vs mejor propia".
    expect(
      screen.queryByRole("rowheader", { name: /δ vs mejor propia/i }),
    ).not.toBeInTheDocument();

    // Las celdas de gap son cualitativas, no en segundos.
    expect(screen.queryByText(/^\+\d+:\d+/)).not.toBeInTheDocument();
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
        defaultDetailHandler(),
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
        defaultDetailHandler(),
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
        defaultDetailHandler(),
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
      defaultDetailHandler(),
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

    it("error en el detalle de una válida (A o B) muestra ErrorState en la comparación", async () => {
      mswServer.use(
        defaultSeasonListHandler(),
        http.get(
          "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
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
        await screen.findByText(/no se pudo cargar el detalle del análisis/i),
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
