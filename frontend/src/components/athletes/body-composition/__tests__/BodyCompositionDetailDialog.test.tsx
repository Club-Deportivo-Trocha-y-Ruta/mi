import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { BodyCompositionDetailDialog } from "@/components/athletes/body-composition/BodyCompositionDetailDialog";
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
      sum4: [{ date: "2026-05-01", value: 29 }, { date: "2026-08-01", value: 36 }],
      sum6: [{ date: "2026-05-01", value: 45 }, { date: "2026-08-01", value: 52 }],
      per_site: {
        triceps: [{ date: "2026-05-01", value: 11 }, { date: "2026-08-01", value: 12 }],
        biceps: [],
        subscapular: [],
        medial_calf: [],
        iliac_crest: [],
        supraspinale: [],
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
      reference_subscapular: { percentile: null, code: "unavailable" },
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

describe("BodyCompositionDetailDialog", () => {
  it("no renderiza contenido cuando open=false", () => {
    render(
      <BodyCompositionDetailDialog open={false} onOpenChange={vi.fn()} data={makeData()} />,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("muestra el título, sparklines por sitio y el historial de tomas", () => {
    render(<BodyCompositionDetailDialog open onOpenChange={vi.fn()} data={makeData()} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Composición corporal — detalle por sitio")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Evolución del pliegue de Tríceps, últimas 2 tomas" }),
    ).toBeInTheDocument();
    expect(screen.getByText("1 ago 2026")).toBeInTheDocument();
  });

  it("marca 'Omitido' cuando el último set declinó ese sitio", () => {
    const data = makeData({
      sets: [
        makeSet({
          sites: {
            ...makeSet().sites,
            biceps: { value_mm: null, readings: null, declined: true, unconfirmed: false },
          },
        }),
      ],
    });
    render(<BodyCompositionDetailDialog open onOpenChange={vi.fn()} data={data} />);
    expect(screen.getByText("Omitido")).toBeInTheDocument();
  });

  it("muestra 'Suma incompleta' cuando sum4_mm es null en un set", () => {
    const data = makeData({ sets: [makeSet({ sum4_mm: null })] });
    render(<BodyCompositionDetailDialog open onOpenChange={vi.fn()} data={data} />);
    expect(screen.getByText("Suma incompleta")).toBeInTheDocument();
  });

  it("muestra 'Falta tríceps' en el historial cuando el estimado es null por ese motivo", () => {
    const data = makeData({
      sets: [
        makeSet({
          body_fat_pct: null,
          sites: {
            ...makeSet().sites,
            triceps: { value_mm: null, readings: null, declined: true, unconfirmed: false },
          },
        }),
      ],
    });
    render(<BodyCompositionDetailDialog open onOpenChange={vi.fn()} data={data} />);
    expect(screen.getByText("Falta tríceps")).toBeInTheDocument();
  });

  it("muestra 'sin referencia para esta edad' cuando el código de referencia es unavailable", () => {
    render(<BodyCompositionDetailDialog open onOpenChange={vi.fn()} data={makeData()} />);
    expect(screen.getByText(/Subescapular: sin referencia para esta edad/)).toBeInTheDocument();
  });

  it("muestra la leyenda de referencia poblacional (contexto, no veredicto)", () => {
    render(<BodyCompositionDetailDialog open onOpenChange={vi.fn()} data={makeData()} />);
    expect(
      screen.getByText(
        "Referencia: escolares de Bogotá 2016, medida en lado izquierdo; contexto, no veredicto.",
      ),
    ).toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad (axe)", async () => {
    const { container } = render(
      <BodyCompositionDetailDialog open onOpenChange={vi.fn()} data={makeData()} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
