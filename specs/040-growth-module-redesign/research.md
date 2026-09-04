# Research — Growth module redesign (040)

**Date**: 2026-09-04 · **Inputs**: `spec.md`, `docs/18-growth-module-redesign/proposal.md` (audit, §3 findings G-01…G-16), `docs/04-percentiles/research.md`, `docs/01-marco-teorico.md`, constitution, live audit of the running app, Context7 (recharts 3), dataviz skill, a production build of the current frontend.

Each entry: **Decision** · **Rationale** · **Alternatives considered**.

---

## R-01 Reference standard on the server: WHO 2007, vendored from the reviewed client dataset

**Decision**: Seed `growth_reference_lms` with `source=WHO` rows for `height_for_age` and `bmi_for_age` (61.5–228.5 months, monthly, both sexes, 168 rows each) and `weight_for_age` (61.5–120.5 months, 60 rows each). The seed reads vendored CSVs under `backend/app/data/who_lms/` generated **from the existing, already-reviewed** `frontend/src/data/growth-reference-who.json` (fields `age`, `L`, `M`, `S`) by a one-off, committed script (`backend/scripts/export_who_lms_csv.py`). The README cites the WHO source tables (https://www.who.int/tools/growth-reference-data-for-5to19-years/indicators) and records the JSON's `generated: 2026-05-06` provenance.

**Rationale**: The client JSON has been the visual source of truth since May 2026 and is what the coach has been looking at; deriving the server table from it guarantees server/client parity by construction (a parity test asserts every (indicator, sex, age) L/M/S triple matches to 6 decimals). WHO data is publicly downloadable and already redistributed in the repo; no licence change. Offline, deterministic seeding is the same property the CDC seed already has (`docs/04-percentiles/003-lms-seed-and-backfill.md`).

**Alternatives**: (a) download WHO XLSX at seed time — rejected (network at cold start on Render, same reason CDC was vendored); (b) switch the client to CDC instead — rejected (Res. 2465/2016 mandates WHO; CDC has no regulatory standing in Colombia); (c) keep both and label — rejected by spec FR-003 (one standard everywhere).

## R-02 Weight-for-age above 10 years is dropped (owner default D1)

**Decision**: The app computes/stores/plots weight-for-age only when a WHO row exists (age ≤ 120.5 months). For older athletes `weight_z_score`/`weight_percentile` are set to NULL by the recompute and never displayed; weight stays visible as a raw value with a trend sparkline. The CDC rows already in `growth_reference_lms` remain in the table (harmless, ~1,446 rows) but no runtime path selects `GrowthSource.CDC` after this feature.

**Rationale**: Res. 2465/2016 does not use weight-for-age at 5–17; BMI-for-age carries the information; one standard is simpler to explain to families. Removing the CDC path also removes the last mixed-source surface (`growth_chart_builder.py:272`).

**Alternatives**: keep CDC weight-for-age labeled "CDC 2000" — rejected (adds a second standard back for a metric the regulation does not use).

## R-03 Store the reference used with each record: additive `growth_source` column

**Decision**: Alembic migration adds `anthropometric_records.growth_source` (`Enum(GrowthSource)`, nullable, indexed not needed). New records get `WHO`; the recompute sets `WHO` after refreshing derived values. `AnthropometryOut` gains `growth_source: str | None` (additive).

**Rationale**: FR-001/FR-004 require the surface to label the source truthfully and the recompute to be idempotent ("skip rows already `WHO`"). A nullable column keeps backward compatibility for rows and clients that ignore it.

**Alternatives**: infer the source from the presence of derived values — rejected (CDC-computed rows are indistinguishable from WHO-computed rows by value alone).

## R-04 Growth summary is a new read endpoint, fetched in parallel with the athlete detail

**Decision**: `GET /api/athletes/{athlete_id}/growth-summary` guarded by the existing `verify_athlete_access` dependency (admin / coach-of-club / linked parent). It loads the two most recent records in one query and derives everything with existing pure helpers (`measurement_alerts.calculate_growth_velocity`, `calculate_next_due`, `detect_approaching_circa`, `get_measurement_interval`) plus a new `services/growth_summary.py`. The frontend calls it with `useGrowthSummary(athleteId)` from the athlete page (top tiles) and the growth tab, as a **parallel** TanStack query alongside `useAthlete`/`useAnthropometry` (no waterfall). Query key `["growth-summary", athleteId]` is **not** added to `persistAllowList` (athlete-identifiable, default deny).

**Rationale**: Single source of truth for intervals/thresholds shared with the dashboard `/alerts` and the AI context (G-06); parent RBAC comes for free; one small query keeps p95 ≤ 500 ms (Constitution IV). Extending `AthleteDetailOut` was the alternative but would force the detail query to load two anthropometry rows on every tab and couple two schemas.

**Alternatives**: derive velocity/next-due in the frontend from the records already fetched — rejected (duplicates interval/threshold constants across backend and frontend; the project already carries two such mirrors — Mirwald and LMS — and the constitution's rule of three says stop).

## R-05 Expected growth-velocity ranges by stage are backend constants returned with the summary

**Decision**: `services/growth_summary.py` holds `EXPECTED_VELOCITY_CM_YEAR = {"Pre-PHV": (4.0, 6.0), "Circa-PHV": {"M": (8.0, 10.0), "F": (7.0, 9.0)}, "Post-PHV": (1.0, 4.0)}` and returns the applicable `(min, max)` as `expected_velocity_cm_year`. Copy shown to the coach: "esperado N–M cm/año en esta etapa (orientativo)". Velocity is `calculate_growth_velocity` (cm/month over a 30.44-day month) × 12, rounded to 1 decimal; `velocity_window_days` accompanies it; `interval_short = window < 30 days` suppresses the rapid-growth alert and adds the caveat (spec FR-007).

**Rationale**: Peak ranges come from `docs/01-marco-teorico.md` §1 (girls 7–9 cm/y at ~11.5 y; boys 8–10 cm/y at ~13.5 y). Pre-peak (~5 cm/y childhood plateau, 4–6) and post-peak deceleration (falling below ~4 within a year of PHV and toward 1–2 by two years) follow the standard Tanner/Preece–Baines description used in pediatric growth references; the ranges are deliberately wide and labeled orientative — they inform the coach, they do not diagnose (Constitution V spirit, not letter). Keeping them server-side avoids a third client/server mirror (see R-04) and lets the AI context (`athlete_context.py`) reuse them later.

**Alternatives**: WHO height-velocity percentile tables — not published for 5–19 as LMS; Tanner–Davies velocity charts — copyrighted and US-population; both rejected as data sources for now (out of scope; noted for a future feature).

## R-06 Chart theming with CSS variables directly on recharts, no new dependency

**Decision**: Recharts 3.8.1 (installed) is kept; the athlete series uses `stroke="var(--color-primary)"`, reference lines `var(--color-mid-gray)` with the P50 in `var(--color-charcoal)`, grid `var(--color-border-gray)` **solid** 1 px, the P3–P97 envelope an `Area` with a two-value dataKey filled with `var(--color-light-gray)` at 0.6 opacity — no status-coloured full-height fills. Hover dots carry a 2 px surface ring. No shadcn `chart` block is added (`components.json` has no registries configured and the block only wraps the same recharts primitives with a config object we do not need).

**Rationale**: Presentation attributes in SVG resolve `var()` in all supported browsers (the pattern shadcn's own chart examples rely on); it satisfies 033 FR-003 (accent for self series, solid hairline grids) and the dataviz rules (thin marks, recessive grid, status colours only for status, text never in series colour) with zero bundle cost. Context7 confirmed for recharts 3: numeric `XAxis` honours `domain={[min,max]}` only with `allowDataOverflow` (R-07), and `ResponsiveContainer` uses ResizeObserver (fine for our targets).

**Alternatives**: shadcn `chart` (adds `ChartContainer`/`ChartConfig` + CSS-var plumbing) — not needed; `visx`/`d3` rewrite — rejected (new dependency, no gain).

## R-07 Age-axis window and ticks

**Decision**: Numeric `XAxis dataKey="age_months"` with `domain={[windowMin, windowMax]}` and `allowDataOverflow`, where `windowMin = max(61.5, firstMeasurementMonths − 24)` and `windowMax = min(228.5, lastMeasurementMonths + 36)`; the reference rows are filtered to the window before rendering so the Y domain (P3 min … P97 max of the *visible* rows, 5 % margin) is tight; `ticks` are whole years inside the window; a "Ver 5–19 años" toggle sets the full range. Y ticks come from a `niceTicks(min, max, step ∈ {1, 2, 5, 10})` helper.

**Rationale**: Spec FR-011/SC-008 (measurements must span ≥ 60 % of the plot width). Filtering rows also shrinks the recharts data array from 168 to ~60 points.

**Alternatives**: recharts `Brush` — rejected (poor on touch, adds chrome); zoom by wheel — rejected (no discoverability on tablet).

## R-08 Growth-tab code is one lazy chunk; recharts leaves the first paint

**Decision**: `GrowthTab` (and everything under `components/athletes/growth/`) is loaded with `React.lazy` + `Suspense` from both `AthleteDetailPage` and `MyAthleteDetailPage`, with `key={athlete.id}`; the WHO JSON moves behind a dynamic `import()` inside the chart module so it lives in the same lazy chunk. After the change the plan includes a build-report gate: the main chunk must not statically import the chunk containing `recharts-wrapper`.

**Rationale (measured today)**: `npm run build` on the current tree: `index-*.js` = 1,292.02 kB raw / **336.68 kB gzip** (already above the 250 kB constitution budget) and it **statically imports** `useAthleteInsights-*.js` = 367.65 kB / **107.39 kB gzip**, the chunk Vite hoisted recharts into; `index.html` module-preloads it. So the AI-tab lazy load introduced in feature 036 is currently defeated by the static `GrowthCharts` import: every first visit, including parents', downloads recharts and the 106 kB WHO JSON. Cutting the static path removes ≈ 107 + ~25 kB gzip from the first paint — this is what makes spec SC-005 (≥ 100 kB) achievable. Other static recharts importers (`newsletter/EffortProfile.tsx` via `StageLogView`, `athletes/ai/MiniSparkline.tsx` via `PanoramaView`) must be re-checked after the change; if any remains reachable from the entry chunk, it is wrapped the same way (task with a build gate).

**Alternatives**: Vite `manualChunks` for recharts — does not fix a static import (the chunk would still be preloaded); keep as is — violates Constitution IV ("static imports of > 50 KB modules into shared layouts are a violation").

## R-09 Sparklines in the summary tiles are inline SVG, not recharts

**Decision**: `Sparkline` (≤ 40 LOC) renders a 12-point polyline in `var(--color-mid-gray)` with the last point in the accent, inside `shared/StatCard`'s `badge`/hint area (dataviz stat-tile contract).

**Rationale**: Row A must render before the chart chunk arrives and must never pull recharts into the page. Trend arrows alone would hide the *shape* the coach cares about (spurt onset).

## R-10 One rule table for training implications

**Decision**: `frontend/src/lib/growth/rules.ts` exports `TRAINING_RULES: TrainingRule[]` (`{ id, topic, ageGroup, stage | "any", status, text }`) and `rulesFor(ageGroup, stage)` + `differsFromDefault(rule, ageGroup)`; `TrainingReadiness` renders the differing rules as `StatusBadge` chips and the full list in a `Collapsible`. The "Test FC máxima" rule loses its numeric estimate (D4) and reads "Sin test de FC máxima — no se estima ni se usa para zonas". The alert list (Circa-PHV, P < 3 height, P < 3 BMI, rapid growth) is fed from the growth summary, not recomputed locally.

**Rationale**: G-04/G-14; the same table is the seed for a later backend catalog if the AI prompts ever need it (out of scope here).

## R-11 Band vocabulary: backend enum is the source of the *band*, frontend owns the *labels*

**Decision**: Backend already emits `nutritional_status_height` / `nutritional_status_bmi` (`NutritionalStatus` enum) per record; the growth summary repeats the latest two. The frontend maps enum → `{ coachLabel, familyLabel, narrative, tone }` in `lib/growth/bands.ts` (extended with `familyLabel`, `familyTitle`, and the D2 alignment: for height, `1 < z ≤ 2` is `talla_adecuada` → "Adecuada"; `talla_alta` only above +2, tone neutral/informational). `useGrowthMetrics` stops recomputing Z when the record carries stored values and `growth_source === "WHO"`; local LMS computation remains only for the reference *curves* and as a labeled fallback for rows not yet recomputed ("referencia anterior").

**Rationale**: FR-003/FR-005 (one definition of cut-offs — backend `classify_nutritional_status_*`), G-03 (front/back divergence), spec US4 (family labels without clinical terms).

## R-12 AI PHV explanation gets an audience

**Decision**: `AthleteAIExplanation.use_case` (existing string column, part of the cache key together with `anthropometric_record_id`) takes a second value `phv_explanation_coach`; `PHVExplainer.run(audience="family"|"coach")` selects `phv_explanation_coach_v1.md` (new prompt: addresses the coach, must state velocity in cm/año and months from PHV, ≤ 120 words, same guardrails). The parent path is untouched. Frontend `PHVExplanationCard` gains a title ("Explicación PHV") and passes `audience` by mode.

**Rationale**: G-16 with no migration (`use_case` already discriminates cache rows).

## R-13 Recompute (backfill v2)

**Decision**: `app/scripts/backfill_anthropometry.py` gains a second pass `recompute_to_source(session, target=GrowthSource.WHO)`: select rows where `growth_source IS NULL OR growth_source != 'WHO'`; recompute BMI (unchanged), height/BMI Z + percentile + status with WHO; weight Z/percentile with WHO if age ≤ 120.5 months else NULL; set `growth_source='WHO'`; collect `(athlete_id, indicator, old_status, new_status)` where the status changed; print an aggregate summary and write `band_changes_<date>.json` (athlete ids only) to `./data/`; never touch raw columns; second run is a no-op. `entrypoint.sh` already runs the module; no wiring change.

**Rationale**: FR-004, SC-007. Athlete ids are not PII under the project's privacy rules (names/birth dates are).

## R-14 Family newsletter PDF chart follows the switch

**Decision**: `growth_chart_builder.py` requests `GrowthSource.WHO`; weight chart omitted above 10 y; one real-dataset PDF regenerated locally as the SC-1-style gate (WeasyPrint + Pango env note from `technical-notes.md`).

## R-15 Tab navigation

**Decision**: Remove the `records.length > 0 → setActiveTab("growth")` effect (D5); the page top tiles read the growth summary (stage, latest height + P, velocity, next-measurement status via `StatusBadge`) using `shared/StatCard`; delete the page-local `StatCard`. `e2e/history.spec.ts` is updated to click the tab explicitly.

## R-16 Testing strategy

**Decision**: (1) Characterization tests on today's `PercentileCurves` behaviours that must survive (legend toggle, bio-age toggle, PHV/PWV marker, sr-only table, PNG export) written *before* the split and re-homed after; (2) parity test backend WHO LMS vs `lms.ts` on 6 fixture points (Z within ±0.02) — fixtures are synthetic, no minors; (3) router tests for `growth-summary`: coach happy path, admin, own-parent 200, other-parent 403, unknown athlete 404, no records → `stage=null`, one record → `velocity=null`, short interval → `interval_short=true` and no rapid-growth alert; (4) vitest + MSW handler `growthSummaryHandlers.ts`; jest-axe on `GrowthTab` in both modes; (5) Playwright `growth.spec.ts` (coach: open tab → tiles → switch indicator → table view → export; parent: latest record, no numerals) using the existing `loginAsCoach` pattern; (6) build gate script `scripts/check-chart-chunk.sh` (greps `dist/index.html` modulepreloads and the entry chunk for the recharts chunk name).

## R-17 Copy and privacy

**Decision**: All new strings in español neutro with diacritics; existing "Cronologica/Biologica/Interpretacion/Detalles tecnicos" fixed. No names in growth components (drop the `TrainingReadiness` chip); export file name `crecimiento-<indicador>-<timestamp>.png` unchanged; logs and the band-change report use athlete ids only. `data-privacy-guard` audit is a task with a checklist file.

---

## Resolved unknowns from Technical Context

| Unknown | Resolution |
|---|---|
| WHO LMS availability for server seeding | R-01 — derive from the reviewed client JSON; parity test |
| Weight-for-age > 10 y | R-02 — dropped |
| Where velocity/next-due live | R-04 — backend summary endpoint |
| Expected velocity ranges | R-05 — backend constants, orientative |
| Chart tokens on recharts 3 | R-06 — CSS variables, no new dep |
| Bundle feasibility of SC-005 | R-08 — measured; ≈ 130 kB gzip removable |
| AI explanation for coach without migration | R-12 — `use_case` discriminator |
