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
  /** Feature 045: cuenta **análisis (runs)** desactualizados, no insights. */
  insights_stale: number | null;
  weekly_load: WeeklyLoadBand[] | null;
  /**
   * Feature 045 (US5) — decisiones de identidad pendientes (cola completa del
   * club, `race_identity_candidates.state == pending`). `null` = ese agregado
   * falló → la fila/insignia se omite, nunca se muestra como cero.
   *
   * Opcional: el frontend (Cloudflare Pages) y el backend (Render) se
   * despliegan por separado, así que una respuesta previa a la 045 no trae la
   * clave. Ausente se trata igual que `null`.
   */
  identity_decisions_pending?: number | null;
  /** Feature 045 — cargas de resultados en curso (`pending` o `dry_run`). Mismas reglas de `null`/ausente. */
  imports_in_progress?: number | null;
  /** Feature 045 — análisis IA esperando aprobación del coach (`awaiting_hitl`). Mismas reglas de `null`/ausente. */
  analyses_awaiting_approval?: number | null;
  /**
   * Feature 045 (FR-033) — competidores de Copa Valle sin enlazar que esperan
   * acción: el `total` de la lista «Sin enlazar» al abrirla (filtro «Solo
   * Trocha y Ruta»). Solo alimenta la insignia de «Cargas e identidades» (no
   * tiene fila en «Pendientes»). Mismas reglas de `null`/ausente.
   */
  unlinked_competitors_pending?: number | null;
}
