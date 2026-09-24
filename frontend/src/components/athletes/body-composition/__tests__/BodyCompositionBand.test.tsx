/**
 * Tests — sección de banda de composición corporal dentro de
 * `BodyCompositionCard.tsx` (feature 046, US3, T043).
 *
 * `contracts/body-composition-reading.md` §3/§4: badge + `coach_reason` por
 * cada `band_reason_code`, sugerencia de escalamiento sólo ámbar/rojo, y
 * `ReferralNoteButton` sólo en rojo (nunca lo ve una familia).
 */
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { axe } from "jest-axe";
import type { UseQueryResult } from "@tanstack/react-query";

import { BodyCompositionCard } from "@/components/athletes/body-composition/BodyCompositionCard";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import type {
  BandReasonCode,
  BodyCompositionOut,
  BodyCompositionReading,
  CoachBand,
} from "@/types/bodyComposition.types";

const BASE_SET = {
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
};

const BASE_READING: BodyCompositionReading = {
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
};

// Rojo is only reachable through the combined pattern (contract §3 rule 2):
// Σ4 `down_real` + weight `flat_or_down` + height `growing`, projected to
// ámbar for families. A rojo fixture must never carry a rising Σ4 (US3 gate
// T048), so every rojo reading is built on top of this block.
const ROJO_READING: Partial<BodyCompositionReading> = {
  sum4_change_mm: -8,
  sum6_change_mm: -10,
  sum_change_code: "down_real",
  weight_change_code: "flat_or_down",
  height_growth_code: "growing",
  family_band: "ambar",
};

function makeData(
  band: CoachBand,
  reasonCode: BandReasonCode,
  readingOverrides: Partial<BodyCompositionReading> = {},
): BodyCompositionOut {
  const bandDefaults = band === "rojo" ? ROJO_READING : {};
  return {
    athlete_id: 17,
    sets: [BASE_SET],
    series: {
      sum4: [{ date: "2026-08-01", value: 36 }],
      sum6: [{ date: "2026-08-01", value: 52 }],
      per_site: {
        triceps: [],
        biceps: [],
        subscapular: [],
        medial_calf: [],
        iliac_crest: [],
        supraspinale: [],
      },
    },
    reading: {
      ...BASE_READING,
      ...bandDefaults,
      band,
      band_reason_code: reasonCode,
      ...readingOverrides,
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
  };
}

function makeQuery(data: BodyCompositionOut): UseQueryResult<BodyCompositionOut, Error> {
  return {
    data,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as UseQueryResult<BodyCompositionOut, Error>;
}

// `contracts/body-composition-reading.md` §4 "Coach" — un texto por código.
const COACH_REASON_SNIPPETS: Record<BandReasonCode, string> = {
  no_real_change: /sin cambio real/i.source,
  expected_pubertal_gain: /pico de crecimiento en niñas/i.source,
  pre_spurt_accumulation: /acumulación previa al estirón/i.source,
  post_phv_lean_gain: /ganancia de masa magra esperada/i.source,
  first_set: /primera toma de pliegues/i.source,
  stable: /composición corporal estable/i.source,
  sum_up_unexplained: /sin un patrón de crecimiento que lo explique/i.source,
  sum_up_velocity_low: /velocidad de talla está.*por debajo/i.source,
  sum_down_unexplained: /peso estancado/i.source,
  reference_extreme: /extremo de la referencia poblacional/i.source,
  bmi_z_drop: /comida primero/i.source,
  velocity_low_persistent: /dos ciclos por debajo/i.source,
  energy_availability_pattern: /baja disponibilidad energética/i.source,
};

describe("BodyCompositionCard — banda (T043)", () => {
  it.each(Object.entries(COACH_REASON_SNIPPETS) as [BandReasonCode, string][])(
    "muestra el badge y el motivo de coach para band_reason_code=%s",
    (reasonCode, snippet) => {
      const band: CoachBand = reasonCode === "energy_availability_pattern" ? "rojo" : "verde";
      renderWithProviders(
        <BodyCompositionCard query={makeQuery(makeData(band, reasonCode))} />,
      );
      expect(screen.getByTestId("body-composition-band")).toBeInTheDocument();
      expect(screen.getByText(new RegExp(snippet, "i"))).toBeInTheDocument();
    },
  );

  it("no muestra sugerencia de escalamiento en verde", () => {
    renderWithProviders(
      <BodyCompositionCard query={makeQuery(makeData("verde", "stable"))} />,
    );
    expect(screen.queryByTestId("body-composition-escalation")).not.toBeInTheDocument();
  });

  it("muestra sugerencia de escalamiento en ámbar", () => {
    renderWithProviders(
      <BodyCompositionCard query={makeQuery(makeData("ambar", "sum_up_unexplained"))} />,
    );
    expect(screen.getByTestId("body-composition-escalation")).toHaveTextContent(
      /conversa en privado/i,
    );
  });

  it("muestra sugerencia de escalamiento en rojo (texto de remisión, no un diagnóstico)", () => {
    renderWithProviders(
      <BodyCompositionCard
        query={makeQuery(makeData("rojo", "energy_availability_pattern"))}
      />,
    );
    expect(screen.getByTestId("body-composition-escalation")).toHaveTextContent(
      /esto no es un diagnóstico/i,
    );
  });

  it("no renderiza ReferralNoteButton en verde ni en ámbar", () => {
    renderWithProviders(
      <BodyCompositionCard query={makeQuery(makeData("verde", "stable"))} />,
    );
    expect(
      screen.queryByRole("button", { name: /generar nota de remisión/i }),
    ).not.toBeInTheDocument();

    renderWithProviders(
      <BodyCompositionCard query={makeQuery(makeData("ambar", "bmi_z_drop"))} />,
    );
    expect(
      screen.queryByRole("button", { name: /generar nota de remisión/i }),
    ).not.toBeInTheDocument();
  });

  it("renderiza ReferralNoteButton únicamente en rojo", () => {
    renderWithProviders(
      <BodyCompositionCard
        query={makeQuery(makeData("rojo", "energy_availability_pattern"))}
      />,
    );
    expect(
      screen.getByRole("button", { name: /generar nota de remisión/i }),
    ).toBeInTheDocument();
  });

  it("muestra la línea 'No evaluado: …' cuando hay legs_missing", () => {
    renderWithProviders(
      <BodyCompositionCard
        query={makeQuery(
          makeData("ambar", "sum_down_unexplained", { legs_missing: ["height"] }),
        )}
      />,
    );
    expect(screen.getByText(/No evaluado: talla/i)).toBeInTheDocument();
  });

  it("ningún fixture rojo lleva una suma de pliegues en aumento (contrato §3 regla 2)", () => {
    const rojo = makeData("rojo", "energy_availability_pattern").reading!;
    expect(rojo.sum_change_code).toBe("down_real");
    expect(rojo.sum4_change_mm).toBeLessThan(0);
    expect(rojo.family_band).toBe("ambar");
  });

  it("sin violaciones de accesibilidad (axe) en rojo con escalamiento y nota de remisión", async () => {
    const { container } = renderWithProviders(
      <BodyCompositionCard
        query={makeQuery(makeData("rojo", "energy_availability_pattern"))}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
