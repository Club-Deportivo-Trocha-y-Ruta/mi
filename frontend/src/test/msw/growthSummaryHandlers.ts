/**
 * Handlers MSW de `GET /api/athletes/:athleteId/growth-summary` (feature 040,
 * US2). Fixture ficticia — sin datos reales de atletas.
 */
import { http, HttpResponse } from "msw";

import { MaturationStatus } from "@/types/enums";
import type { GrowthSummary } from "@/types/growth.types";

// ---------------------------------------------------------------------------
// Fixture factory
// ---------------------------------------------------------------------------

export function makeGrowthSummary(overrides?: Partial<GrowthSummary>): GrowthSummary {
  return {
    athlete_id: 2,
    computed_at: "2026-09-04",
    records_count: 3,
    latest_evaluation_date: "2026-08-14",
    stage: MaturationStatus.PostPHV,
    maturity_offset: 1.2,
    age_at_phv: 12.9,
    months_from_phv: 16.4,
    velocity: {
      cm_per_month: 0.31,
      cm_per_year: 3.7,
      window_days: 101,
      interval_short: false,
      expected_cm_per_year: [1.0, 4.0],
    },
    measurement: {
      status: "ok",
      interval_days: 120,
      next_due_date: "2026-12-12",
      days_overdue: null,
    },
    alerts: [],
    latest: {
      record_id: 41,
      growth_source: "WHO",
      height: { value: 150.0, z_score: -1.66, percentile: 4.8, band: "riesgo_retraso_talla" },
      bmi: { value: 21.9, z_score: 0.70, percentile: 75.7, band: "adecuado" },
      weight: null,
    },
    ...overrides,
  };
}

/** Variante "sin registros" — `contracts/growth-summary-api.md` fila 1. */
export function makeNeverGrowthSummary(
  overrides?: Partial<GrowthSummary>,
): GrowthSummary {
  return makeGrowthSummary({
    records_count: 0,
    latest_evaluation_date: null,
    stage: null,
    maturity_offset: null,
    age_at_phv: null,
    months_from_phv: null,
    velocity: null,
    measurement: {
      status: "never",
      interval_days: 90,
      next_due_date: null,
      days_overdue: null,
    },
    alerts: [],
    latest: null,
    ...overrides,
  });
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

export const growthSummaryHandlers = [
  http.get("*/api/athletes/:athleteId/growth-summary", ({ params }) => {
    return HttpResponse.json(
      makeGrowthSummary({ athlete_id: Number(params.athleteId) }),
    );
  }),
];
