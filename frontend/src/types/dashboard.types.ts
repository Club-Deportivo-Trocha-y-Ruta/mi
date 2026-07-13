/**
 * Types for the coach-home mission-control aggregate (feature 031).
 *
 * Backs `GET /api/dashboard/coach-summary` — see
 * `specs/031-coach-home-mission-control/contracts/coach-summary-endpoint.md`
 * and `data-model.md` §1 for the full field-by-field contract.
 *
 * Every field is a counts-only / minutes-only read-model — no athlete ids,
 * names, or session content (Constitution Quality Gates; FR-010).
 */

/** Age band tracked by the weekly-load meter. Never a third value. */
export type WeeklyLoadAgeBand = "10-12" | "13-15";

export interface WeeklyLoadBand {
  age_band: WeeklyLoadAgeBand;
  planned_minutes: number;
  cap_minutes: number;
  athlete_count: number;
}

export interface CoachSummary {
  generated_at: string;
  consents_pending: number | null;
  insights_stale: number | null;
  weekly_load: WeeklyLoadBand[] | null;
}
