import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { axe } from "jest-axe";
import type { UseQueryResult } from "@tanstack/react-query";

import { BodyCompositionCard, changeReadingCopy } from "@/components/athletes/body-composition/BodyCompositionCard";
import type { BodyCompositionOut } from "@/types/bodyComposition.types";

function makeSet(overrides: Partial<BodyCompositionOut["sets"][number]> = {}) {
  return {
    record_id: 1,
    athlete_id: 17,
    evaluation_date: "2026-08-01",
    caliper_model: "slim_guide",
    protocol_version: "v1",
    sites: {
      triceps: { value_mm: 12, readings: [12, 12], declined: false, unconfirmed: false },
      biceps: { value_mm: 6, readings: [6, 6], declined: false, unconfirmed: false },
      subscapular: { value_mm: 8, readings: [8, 8], declined: false, unconfirmed: false },
      medial_calf: { value_mm: 10, readings: [10, 10], declined: false, unconfirmed: false },
      iliac_crest: { value_mm: 9, readings: [9, 9], declined: false, unconfirmed: false },
      supraspinale: { value_mm: 7, readings: [7, 7], declined: false, unconfirmed: false },
    },
    sum4_mm: 36,
    sum6_mm: 52,
    body_fat_pct: 18.2,
    fat_mass_kg: 8.1,
    fat_free_mass_kg: 34.9,
    equation_version: "slaughter_1988",
    margin_pct: 4,
    measured_by: 1,
    updated_at: "2026-08-01T12:00:00Z",
    needs_third_reading_unconfirmed: [],
    ...overrides,
  };
}

function makeData(overrides: Partial<BodyCompositionOut> = {}): BodyCompositionOut {
  return {
    athlete_id: 17,
    sets: [makeSet()],
    series: {
      sum4: [
        { date: "2026-05-01", value: 29 },
        { date: "2026-08-01", value: 36 },
      ],
      sum6: [
        { date: "2026-05-01", value: 45 },
        { date: "2026-08-01", value: 52 },
      ],
      per_site: {
        triceps: [], biceps: [], subscapular: [], medial_calf: [], iliac_crest: [], supraspinale: [],
      },
    },
    reading: {
      sets_count: 2,
      sum4_change_mm: 7,
      sum6_change_mm: 7,
      sum_change_code: "up_real",
      weight_change_code: "up",
      height_growth_code: "growing",
      velocity_code: "within_or_above",
      bmi_z_change_code: "ok",
      reference_triceps: { percentile: 60, code: "normal" },
      reference_subscapular: { percentile: 55, code: "normal" },
      ffm_trend_code: "up",
      sites_declined_count: 0,
      band: "verde",
      family_band: "verde",
      latest_attempt_declined: null,
      band_reason_code: "expected_pubertal_gain",
      legs_missing: [],
      next_due_date: "2026-11-01",
      days_until_due: 60,
    },
    estimates_latest: {
      body_fat_pct: 18.2,
      fat_mass_kg: 8.1,
      fat_free_mass_kg: 34.9,
      equation_version: "slaughter_1988",
      margin_pct: 4,
    },
    reference: {
      source: "FUPRECOL",
      population: "escolares de Bogotá 2016",
      side: "izquierdo",
      age_range: "9–17.9",
    },
    next_due_date: "2026-11-01",
    ...overrides,
  };
}

function makeQuery(
  overrides: Partial<UseQueryResult<BodyCompositionOut, Error>> = {},
): UseQueryResult<BodyCompositionOut, Error> {
  return {
    data: makeData(),
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  } as unknown as UseQueryResult<BodyCompositionOut, Error>;
}

describe("changeReadingCopy", () => {
  it("dentro del margen (neutral)", () => {
    const result = changeReadingCopy("within_noise", 6.9);
    expect(result.label).toBe("Dentro del margen de medición (+6.9 mm; umbral 7.0 mm)");
    expect(result.tone).toBe("neutral");
  });

  it("cambio real hacia arriba (coloreado)", () => {
    const result = changeReadingCopy("up_real", 8.0);
    expect(result.label).toBe("Cambio real (+8.0 mm; umbral 7.0 mm)");
    expect(result.tone).toBe("warning");
  });

  it("sin toma anterior comparable", () => {
    const result = changeReadingCopy("none", null);
    expect(result.label).toBe("Sin toma anterior comparable");
    expect(result.tone).toBe("neutral");
  });
});

describe("BodyCompositionCard", () => {
  it("expone data-testid=body-composition-card cuando hay datos", () => {
    renderWithProviders(<BodyCompositionCard query={makeQuery()} />);
    expect(screen.getByTestId("body-composition-card")).toBeInTheDocument();
  });

  it("muestra Σ4, Σ6 y el sparkline con aria-label descriptivo", () => {
    renderWithProviders(<BodyCompositionCard query={makeQuery()} />);
    expect(screen.getByText("36.0 mm")).toBeInTheDocument();
    expect(screen.getByText("Σ6: 52.0 mm")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Evolución de la suma de 4 pliegues, últimas 2 tomas" }),
    ).toBeInTheDocument();
  });

  it("muestra el cambio real como StatusBadge con el umbral", () => {
    renderWithProviders(<BodyCompositionCard query={makeQuery()} />);
    expect(screen.getByText("Cambio real (+7.0 mm; umbral 7.0 mm)")).toBeInTheDocument();
  });

  it("muestra el % de grasa con la etiqueta 'estimado (±4 puntos)'", () => {
    renderWithProviders(<BodyCompositionCard query={makeQuery()} />);
    expect(screen.getByText(/% grasa \(est\.\) 18\.2% — estimado \(±4 puntos\)/)).toBeInTheDocument();
  });

  it("muestra 'Falta tríceps' cuando el estimado no está disponible por ese motivo", () => {
    const data = makeData({
      sets: [
        makeSet({
          body_fat_pct: null,
          fat_mass_kg: null,
          fat_free_mass_kg: null,
          sites: {
            ...makeSet().sites,
            triceps: { value_mm: null, readings: null, declined: true, unconfirmed: false },
          },
        }),
      ],
      estimates_latest: {
        body_fat_pct: null,
        fat_mass_kg: null,
        fat_free_mass_kg: null,
        equation_version: null,
        margin_pct: 4,
      },
    });
    renderWithProviders(<BodyCompositionCard query={makeQuery({ data })} />);
    expect(screen.getByText(/falta tríceps/i)).toBeInTheDocument();
  });

  it("muestra la próxima toma de pliegues con la fecha formateada", () => {
    renderWithProviders(<BodyCompositionCard query={makeQuery()} />);
    expect(screen.getByTestId("body-composition-next-due")).toHaveTextContent(
      "Próxima toma de pliegues: 1 nov 2026",
    );
  });

  it("dispara onViewDetail al hacer clic en 'Ver detalle por sitio'", () => {
    const onViewDetail = vi.fn();
    renderWithProviders(<BodyCompositionCard query={makeQuery()} onViewDetail={onViewDetail} />);
    screen.getByRole("button", { name: "Ver detalle por sitio" }).click();
    expect(onViewDetail).toHaveBeenCalledTimes(1);
  });

  it("muestra EmptyState 'Aún no hay pliegues registrados' cuando has_data=false", () => {
    renderWithProviders(<BodyCompositionCard query={makeQuery({ data: makeData({ sets: [] }) })} />);
    expect(screen.getByText("Aún no hay pliegues registrados")).toBeInTheDocument();
  });

  it("muestra ErrorState con reintentar cuando la query falla", () => {
    const refetch = vi.fn();
    renderWithProviders(
      <BodyCompositionCard
        query={makeQuery({ isError: true, isLoading: false, data: undefined, refetch })}
      />,
    );
    expect(screen.getByText("No se pudo cargar la composición corporal.")).toBeInTheDocument();
    screen.getByRole("button", { name: /Reintentar/ }).click();
    expect(refetch).toHaveBeenCalled();
  });

  it("sin violaciones de accesibilidad (axe)", async () => {
    const { container } = renderWithProviders(<BodyCompositionCard query={makeQuery()} onViewDetail={vi.fn()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
