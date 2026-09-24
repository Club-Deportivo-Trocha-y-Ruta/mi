/**
 * Handlers MSW de composición corporal por pliegues (feature 046),
 * `contracts/skinfolds-api.md`. Fixtures ficticias — sin datos reales de
 * atletas (Ley 1581: sólo `athlete_id` numérico, sin nombres).
 *
 * Nota: la task list del feature nombra este archivo
 * `frontend/src/mocks/handlers/bodyComposition.ts`, pero el proyecto no
 * tiene ese directorio — el registro real de handlers MSW vive en
 * `frontend/src/test/msw/*Handlers.ts` + `frontend/src/test/setup.ts`
 * (ver `growthSummaryHandlers.ts`, `raceCourseHandlers.ts`). Se sigue esa
 * convención existente en su lugar.
 */
import { http, HttpResponse } from "msw";

import type {
  BodyCompositionOut,
  SkinfoldSetIn,
  SkinfoldSetOut,
  SkinfoldSite,
} from "@/types/bodyComposition.types";
import { SKINFOLD_SITES } from "@/types/bodyComposition.types";

// ---------------------------------------------------------------------------
// Fixture factories
// ---------------------------------------------------------------------------

function emptySite(): SkinfoldSetOut["sites"][SkinfoldSite] {
  return { value_mm: null, readings: null, declined: true, unconfirmed: false };
}

export function makeSkinfoldSetOut(overrides?: Partial<SkinfoldSetOut>): SkinfoldSetOut {
  const sites = Object.fromEntries(
    SKINFOLD_SITES.map((site) => [
      site,
      { value_mm: 8.5, readings: [8.0, 9.0], declined: false, unconfirmed: false },
    ]),
  ) as SkinfoldSetOut["sites"];

  return {
    record_id: 812,
    athlete_id: 17,
    evaluation_date: "2026-09-20",
    caliper_model: "slim_guide",
    protocol_version: "v1",
    sites,
    sum4_mm: 31.8,
    sum6_mm: 51.0,
    body_fat_pct: 16.5,
    fat_mass_kg: 6.9,
    fat_free_mass_kg: 35.0,
    equation_version: "slaughter_tc_1988_v1",
    margin_pct: 4,
    measured_by: 3,
    updated_at: "2026-09-20T15:02:11Z",
    needs_third_reading_unconfirmed: [],
    ...overrides,
  };
}

export function makeBodyCompositionOut(
  overrides?: Partial<BodyCompositionOut>,
): BodyCompositionOut {
  const latest = makeSkinfoldSetOut();
  return {
    athlete_id: latest.athlete_id,
    sets: [latest],
    series: {
      sum4: [{ date: latest.evaluation_date, value: latest.sum4_mm ?? 0 }],
      sum6: [{ date: latest.evaluation_date, value: latest.sum6_mm ?? 0 }],
      per_site: Object.fromEntries(
        SKINFOLD_SITES.map((site) => [site, [] as { date: string; value: number }[]]),
      ) as unknown as Record<SkinfoldSite, { date: string; value: number }[]>,
    },
    reading: {
      sets_count: 1,
      sum4_change_mm: null,
      sum6_change_mm: null,
      sum_change_code: "none",
      weight_change_code: "unavailable",
      height_growth_code: "unavailable",
      velocity_code: "unavailable",
      bmi_z_change_code: "unavailable",
      reference_triceps: { percentile: 50, code: "normal" },
      reference_subscapular: { percentile: 50, code: "normal" },
      ffm_trend_code: "unavailable",
      sites_declined_count: 0,
      band: "verde",
      family_band: "verde",
      latest_attempt_declined: null,
      band_reason_code: "first_set",
      legs_missing: ["previous_set"],
      next_due_date: "2026-12-19",
      days_until_due: 90,
    },
    estimates_latest: {
      body_fat_pct: latest.body_fat_pct,
      fat_mass_kg: latest.fat_mass_kg,
      fat_free_mass_kg: latest.fat_free_mass_kg,
      equation_version: latest.equation_version,
      margin_pct: latest.margin_pct,
    },
    reference: {
      source: "FUPRECOL",
      population: "escolares de Bogotá 2016",
      side: "izquierdo",
      age_range: "9–17.9",
    },
    next_due_date: "2026-12-19",
    ...overrides,
  };
}

function emptySkinfoldSetOut(overrides?: Partial<SkinfoldSetIn>): SkinfoldSetOut {
  return makeSkinfoldSetOut({
    caliper_model: overrides?.caliper_model ?? "slim_guide",
    sites: Object.fromEntries(SKINFOLD_SITES.map((site) => [site, emptySite()])) as SkinfoldSetOut["sites"],
  });
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

export const bodyCompositionHandlers = [
  http.get("*/api/athletes/:athleteId/body-composition", ({ params }) => {
    return HttpResponse.json(
      makeBodyCompositionOut({ athlete_id: Number(params.athleteId) }),
    );
  }),

  http.put(
    "*/api/athletes/:athleteId/anthropometry/:recordId/skinfolds",
    async ({ params, request }) => {
      const body = (await request.json()) as SkinfoldSetIn;
      return HttpResponse.json(
        makeSkinfoldSetOut({
          athlete_id: Number(params.athleteId),
          record_id: Number(params.recordId),
          caliper_model: body.caliper_model,
        }),
      );
    },
  ),

  http.delete("*/api/athletes/:athleteId/anthropometry/:recordId/skinfolds", () => {
    return new HttpResponse(null, { status: 204 });
  }),

  http.get("*/api/athletes/:athleteId/body-composition/referral-note.pdf", () => {
    return new HttpResponse(new Blob(["%PDF-fake"], { type: "application/pdf" }), {
      status: 200,
      headers: { "Content-Type": "application/pdf" },
    });
  }),

  http.get("*/api/body-composition/field-guide.pdf", () => {
    return new HttpResponse(new Blob(["%PDF-fake"], { type: "application/pdf" }), {
      status: 200,
      headers: { "Content-Type": "application/pdf" },
    });
  }),
];

export { emptySkinfoldSetOut };
