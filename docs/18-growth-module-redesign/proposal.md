# Growth Module ("Crecimiento" tab) — Audit & Redesign Work Plan

> **Date:** 2026-09-04 · **Status:** Proposal / work plan (no code changed) · **Scope:** the `Crecimiento` tab on the coach athlete detail page (`/athletes/:id?tab=growth`) and its parent-portal twin (`/my-athletes/:id`, tab `growth`), plus the backend growth-reference data that feeds both.
>
> **Purpose:** input for `/speckit-specify` (suggested feature: `040-growth-module-redesign`). Every claim below carries a `file:line` reference. The original design and scientific basis live in `docs/04-percentiles/` (workflow, research); this document does not repeat them.
>
> **Privacy note:** no athlete data is quoted here. Screenshots used during the audit were of local demo seed data and are not stored.

---

## 1. Executive summary

The growth tab was built in April 2026 (feature 04, "WHO/CDC percentiles + curves + decision support") as a **vertical stack of seven independent cards**, then left mostly untouched while the rest of the coach surface went through the 027→035 redesign program. Today it is the screen where the coach reads the most sensitive judgment the app makes about a child (nutritional status, maturation stage, what training is allowed) and it is also the screen that diverges most from the shipped design system.

Three problems, in order of severity:

1. **Two reference standards on one screen.** The backend persists Z-scores and percentiles computed against **CDC** LMS tables (`backend/app/routers/anthropometry.py:142`, seeded only from CDC CSVs by `backend/app/seed_growth_data.py`, backfilled with CDC by `backend/app/scripts/backfill_anthropometry.py:106`). The frontend curves, tooltips and interpretation blocks compute against **WHO 2007** LMS (`frontend/src/data/growth-reference-who.json`, `PercentileCurves.tsx:423`). The classification card prefers the backend (CDC) value when present (`useGrowthMetrics.ts:191-192`) while labeling itself "Res. 2465/2016 / OMS 2007" (`NutritionalClassification.tsx:102,118`). The same measurement can therefore show one Z in the card and another in the chart tooltip, and the regulatory label is inaccurate. Colombian Resolution 2465/2016 mandates WHO.
2. **The layout answers no question first.** The tab opens on three near-empty longitudinal line charts (with the typical 2–4 measurements they render as a flat line on a ±2 cm axis, `GrowthCharts.tsx:224,261`), pushes the only informative visual (the percentile curve) behind a toggle, and buries the coach's real decision inputs — growth velocity, months from PHV, next measurement due — which the backend already computes for the dashboard and for the AI (`services/measurement_alerts.py`, `services/race/ai/athlete_context.py:117-120`) but never shows on this tab.
3. **Design-system drift.** Hand-rolled stat tiles instead of the shared `StatCard`, ~10 hardcoded chart hexes, dashed gridlines the 033 spec explicitly forbids (FR-003), 8-entry legend, fixed 480 px chart, a 371-line rules component with a hardcoded "197 lpm", and a parent view that reuses coach-grade components (raw Z-scores, "Obesidad"/"Delgadez" labels, bibliography) with a latent bug that classifies the **oldest** measurement instead of the latest (`MyAthleteDetailPage.tsx:198,405`).

**Nothing requires a rewrite of the science.** LMS math, Mirwald PHV, the Res. 2465 bands, the PHV/PWV markers and the AI PHV explanation are correct and stay. The redesign is: **fix the reference source once, put the decision first, keep one chart, adopt the shared components, and split the parent view into a family-language variant.**

---

## 2. Current state

### 2.1 What the tab renders today (coach)

`AthleteDetailPage.tsx:841-871`, top to bottom, all full-width white cards:

| # | Card | Component | LOC | Notes |
|---|---|---|---|---|
| 1 | Clasificación nutricional (T/E, IMC/E) | `NutritionalClassification.tsx` | 126 | Backend Z (CDC) when present, else WHO local |
| 2 | Charts card: `Longitudinal` \| `Curvas de percentiles` toggle | `GrowthCharts.tsx` | 342 | Default view = 3 longitudinal charts (talla, peso, maturity offset) |
| 2b | Percentile curve + indicator pills + PNG export | `PercentileCurves.tsx` | 875 | 7 reference lines + athlete line + 4–5 background bands + PHV/PWV marker + bio/chrono toggle + interactive legend + sr-only table + interpretation block |
| 3 | Recomendaciones de entrenamiento (9 rule cards + alerts) | `TrainingReadiness.tsx` | 371 | Static rules by age group × Circa-PHV |
| 4 | Morfología y ajuste de bici | `MorphologyCard.tsx` | 148 | 4 hand-rolled tiles + bike-fit guidance |
| 5 | Explicación PHV (IA) | `components/ai/PHVExplanationCard.tsx` | 401 | Generate/regenerate, cached |
| 6 | Fuentes bibliográficas (collapsed) | `ResearchReferences.tsx` | 95 | 7 links |

Above the tabs the page already shows a hero (name, PHV badge, age, category, talla, peso — `AthleteInfoCard.tsx`) and four stat tiles (Edad, Offset PHV, Talla+P, Última medición) built with a **page-local** `StatCard` (`AthleteDetailPage.tsx:86-108`) instead of `components/shared/StatCard.tsx`. Talla appears four times on one screen (hero chip, stat tile, morphology tile, classification row).

### 2.2 Parent view

`MyAthleteDetailPage.tsx:402-432` renders, in this order: `NutritionalClassification` → `AnthropometryHistory` (mode `parent`) → `GrowthCharts` (identical to coach, minus the role-gated bio-age toggle) → `PHVExplanationCard readOnly` → `ResearchReferences`. There is no family-language variant of the classification or the curve, although `PercentileInterpretationBlock` already has a `hideAdvanced` prop (`PercentileInterpretationBlock.tsx:28`) that **no caller uses**, and `docs/06-parents/workflow.md:26` lists a "clinical/family toggle mode in percentiles" that was never built.

### 2.3 Data flow

```
POST /athletes/{id}/anthropometry  ──► Mirwald PHV (services/phv.py)
                                    ──► LMS Z/percentiles, source=CDC (services/growth.py)  ──► persisted columns
GET  /athletes/{id}/anthropometry  ──► list, newest first (routers/anthropometry.py:249)
GET  /growth-reference             ──► CDC curves from DB (routers/growth.py) — NOT used by the SPA
GET  /alerts                       ──► per-athlete velocity, next due, growth alerts — dashboard only
frontend/src/data/growth-reference-who.json (106 KB, WHO 2007) ──► curves, tooltips, local Z fallback
```

The SPA never calls `/growth-reference`; it ships its own WHO JSON. The backend endpoint is effectively dead for the UI (it is still used conceptually by the newsletter PDF chart builder, which reads the CDC table directly: `services/training/growth_chart_builder.py`).

### 2.4 Test and bundle footprint

- Unit tests over the six components: 73 (`GrowthCharts` 23, `TrainingReadiness` 11, `NutritionalClassification` 11, `PercentileCurves` 10 + a11y file, `PercentileInterpretationBlock` 10, `MorphologyCard` 8). Backend: `tests/test_growth_service.py` and the seed/backfill suites.
- E2E: `frontend/e2e/history.spec.ts:34,90-93` depends on the tab auto-selecting `growth` and on the `growth-charts` test id. No e2e opens the percentile view.
- Bundle: `App.tsx:54` imports `AthleteDetailPage` statically, which imports `GrowthCharts` statically (`AthleteDetailPage.tsx:29`), which pulls **recharts + the 106 KB WHO JSON + html-to-image (lazy)** into the main bundle for every user, including parents who never open the tab. The Insights IA tab was lazy-loaded for exactly this reason (feature 036 T096, `AthleteDetailPage.tsx:52-57`); the growth tab undoes that saving.

---

## 3. Findings (fix regardless of the redesign)

Severity: **C** correctness · **P** privacy/safeguard · **U** usability · **D** design-system · **F** performance.

| ID | Sev | Finding | Evidence |
|---|---|---|---|
| G-01 | C | Backend Z/percentiles are CDC, frontend curves/tooltips/interpretation are WHO; the classification card shows CDC values under an "OMS / Res. 2465" label. Same record → two different Z on one screen. | `routers/anthropometry.py:142`, `seed_growth_data.py` (CDC only), `backfill_anthropometry.py:106`, `useGrowthMetrics.ts:191-192`, `PercentileCurves.tsx:423`, `NutritionalClassification.tsx:102,118` |
| G-02 | C | Parent view classifies and computes `phvAgeMonths` from `records[records.length - 1]`, but the API returns newest-first → parents see the **oldest** measurement's status. | `MyAthleteDetailPage.tsx:195-198,405` vs `routers/anthropometry.py:249` (`.desc()`) and `AthleteDetailPage.tsx:486-487` |
| G-03 | C | Height band cut-offs differ between layers: frontend `classifyBand` labels 1 < Z ≤ 2 "Talla alta" (blue) while the backend classifies Z ≤ 2 as `talla_adecuada` (Res. 2465 defines no upper cut-off for 5–17). The band vocabulary must be one. | `useGrowthMetrics.ts:71-77`, `lib/growth/bands.ts:44-56`, `services/growth.py:117-134` |
| G-04 | C | "Test FC máxima … estimada: 197 lpm" is a hardcoded literal, not derived from age. | `TrainingReadiness.tsx:156,163` |
| G-05 | U | Default view is three longitudinal charts on a `dataMin − 2 / dataMax + 2` axis; with 2–4 measurements they read as noise, and "Maturity Offset vs Tiempo" plots a derived index most coaches cannot interpret as a trend. The informative visual (percentile curve) is one click away and off by default. | `GrowthCharts.tsx:189,224,261,287-290` |
| G-06 | U | Growth velocity (cm/month), next measurement due, "approaching Circa-PHV" and "phase changed" alerts exist in the backend and on the dashboard, but not on the athlete's growth tab — the coach must leave the athlete to see them. The AI receives `growth_velocity_cm_per_year` and `months_from_phv` the coach never sees. | `services/measurement_alerts.py`, `routers/alerts.py:108-148`, `race/ai/athlete_context.py:117-120,159-160` |
| G-07 | U | Weight-for-age is hidden from the percentile view above age 10 (WHO has no reference) but "Peso vs Tiempo" is always drawn in the longitudinal view → inconsistent story about weight. Weight/BMI framing for adolescent athletes also needs the RED-S-aware wording from `docs/01-marco-teorico.md` §7–8, not a bare line. | `GrowthCharts.tsx:54` vs `GrowthCharts.tsx:250-285` |
| G-08 | P | Parents see raw Z-scores/percentiles, the labels "Delgadez"/"Obesidad"/"Sobrepeso", the Mirwald offset chart and a scientific bibliography. `hideAdvanced` exists but is unused; the family-mode toggle scoped in `docs/06-parents/workflow.md:26` was never built. | `MyAthleteDetailPage.tsx:402-432`, `PercentileInterpretationBlock.tsx:28` |
| G-09 | D | Page-local `StatCard` duplicates `components/shared/StatCard.tsx`; morphology tiles are hand-rolled; PHV badge colors are re-declared in three places (`PHVBadge.tsx`, `TrainingReadiness.tsx:280-284`, `AthleteDetailPage.tsx:110-115`) with raw Tailwind `blue/amber/green` instead of the status vocabulary. | listed |
| G-10 | D | Charts violate 033 FR-003: dashed gridlines, ~10 hardcoded hexes (`#dc2626`, `#ca8a04`, `#16a34a`, `#2563eb`, `#ea580c`, `#242424`, `#898989`), athlete series in charcoal instead of the accent, 8-item legend, fixed 480 px height. | `PercentileCurves.tsx:340-360,399-403,660,665,718…`, `GrowthCharts.tsx:212-334` |
| G-11 | D | `PercentileCurves.tsx` (875 LOC) re-implements `classifyBand` and `ageMonthsFromDates` that already live in `useGrowthMetrics.ts` / `lib/growth/lms.ts`. | `PercentileCurves.tsx:203,247` |
| G-12 | F | recharts + WHO JSON enter the main bundle through the static import chain; the growth tab defeats the lazy-load the Insights tab introduced. Constitution IV budget: route bundle ≤ 250 KB gzipped. | `App.tsx:54` → `AthleteDetailPage.tsx:29` |
| G-13 | U | The tab auto-switches to `growth` whenever measurements exist and the URL has no `tab` (surprising navigation; e2e depends on it). With the redesign the growth tab should be a deliberate destination, and the summary the coach needs on arrival should live in the hero/tiles. | `AthleteDetailPage.tsx:492-497`, `e2e/history.spec.ts:34,90` |
| G-14 | U | `TrainingReadiness` shows the athlete's full name in a chip on a page whose hero already shows it, and its 9 rule cards duplicate `training_implications` shown on the Info tab and in the AI prompt catalog — three places to maintain one rule set. | `TrainingReadiness.tsx:316`, `AthleteDetailPage.tsx:748-777` |
| G-15 | U | The percentile chart spans the whole WHO range (5.1–19 y on the x-axis, `domain={["dataMin","dataMax"]}`), so an athlete's 2–4 measurements occupy ~2 % of the plot width and the trajectory is unreadable; the full-height `band_low`/`band_high` fills (red/blue) dominate the picture and read as an alarm. Y ticks are non-round (97/122/147/172/179). Observed live on 2026-09-04. | `PercentileCurves.tsx:668-672` (x domain), `:316-360` (band fills), `:680-686` (y ticks) |
| G-16 | U | The AI PHV explanation shown on the **coach** tab is written for the family ("Su hija se encuentra…") and is the only place the coach can read the growth velocity — as prose, not as a number. The card has no title in coach mode, only badges. | `components/ai/PHVExplanationCard.tsx`, `services/ai/use_cases/phv_explainer.py`, `services/ai/prompts/registry.py` |

---

## 4. Design principles for the redesign

1. **Decision first, evidence second.** The first screen must answer, without scrolling: *What stage is this athlete in? Is growth on track? What does that change in training this month? When do I measure again?* Curves and tables are supporting evidence.
2. **One reference standard.** WHO 2007 for height-for-age and BMI-for-age (regulatory, Res. 2465/2016). Weight-for-age only where a reference exists (WHO ≤ 10 y; CDC 10–20 y is an explicit, labeled exception or is dropped — decision D1).
3. **One chart, done right.** The percentile curve is the chart. Longitudinal talla/peso become sparklines inside stat tiles (dataviz rule: a single current value + trend = stat tile, not a chart). The maturity-offset line chart is retired in favour of a **maturation timeline** (Pre → Circa → Post with the estimated PHV age and today's position).
4. **Velocity is the signal.** PHV is a velocity concept; show cm/year (annualized from the last two measurements, with the interval) against the expected range for the stage (`docs/01-marco-teorico.md` §1: 7–9 cm/y girls, 8–10 cm/y boys at peak), reusing `measurement_alerts.calculate_growth_velocity`.
5. **Two audiences, one data source.** Coach mode = clinical vocabulary + numbers. Parent mode = the narratives in `lib/growth/bands.ts`, band label + colour + icon, no Z/percentile, no bibliography, no maturity-offset index, softened BMI wording (never "obesidad" as a headline to a family; the band narrative already says "requiere evaluación").
6. **Shared components only.** `StatCard`, `StatusBadge`, `EmptyState`, `ErrorState`, shadcn `Tabs`/`ToggleGroup`/`Collapsible`/`Tooltip`; tokens `--color-primary`, `--color-success/-warning/-danger`, `--color-border-gray`; no raw hexes; grid = solid hairline; athlete series = accent; reference bands = status tokens at low alpha.
7. **Lazy by default.** The whole growth tab is one lazy chunk (recharts + WHO JSON + html-to-image) like the Insights tab.
8. **Safeguards unchanged.** No new PII surfaces; AI explanation stays consent-gated; nothing here feeds talent selection (keep the morphology disclaimer verbatim).

---

## 5. Proposed layout

### 5.1 Coach — `Crecimiento` tab (desktop ≥ lg; stacks to one column on tablet)

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ ROW A · Estado de crecimiento                                       [Nueva medición] │
│ ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌────────────────┐        │
│ │ Etapa          │ │ Velocidad talla│ │ Talla / edad   │ │ IMC / edad     │        │
│ │ Post-PHV  ●    │ │ 4.2 cm/año ▁▃▅ │ │ P5 · Z −1.66   │ │ P76 · Z +0.70  │        │
│ │ PHV est. 12.9 a│ │ últimos 3 meses│ │ ⚠ En vigilancia│ │ ✓ Adecuado     │        │
│ │ hace 16 meses  │ │ esperado 1–3   │ │ (OMS 2007)     │ │ (OMS 2007)     │        │
│ └────────────────┘ └────────────────┘ └────────────────┘ └────────────────┘        │
│ ┌──────────────────────────────────────────────────────────────────────────┐        │
│ │ Próxima medición: 12 dic 2026 (cada 120 días en Post-PHV) · ✓ al día      │        │
│ └──────────────────────────────────────────────────────────────────────────┘        │
├───────────────────────────────────────────────────────────────────────────────┤
│ ROW B · Qué cambia en el entrenamiento                     (collapsible, open) │
│  ⚠ Alerta si aplica (Circa-PHV / P<3 / velocidad ≥ 0.6 cm/mes)                 │
│  ✓ Fuerza peso corporal · ⚠ Intervalos máx 2/sem · ✗ Peso externo · … (compact │
│    chips, 3–5 rules that actually differ from the default, "Ver todas")        │
├───────────────────────────────────────────────────────────────────────────────┤
│ ROW C · Curva de crecimiento                                                    │
│  [Talla] [IMC] [Peso ≤10 a]        Eje: (Cronológica | Biológica)   [Tabla] [PNG] │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  percentile curve, P3/P50/P97 lines + P10–P90 band, athlete in accent,   │  │
│  │  PHV/PWV marker, solid hairline grid, height = clamp(280px, 55vw, 440px)  │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│  Interpretación: ● En vigilancia — "La estatura está un poco por debajo…"      │
│  Nota PHV (indicator-specific)                                                 │
├───────────────────────────────────────────────────────────────────────────────┤
│ ROW D · Maduración (timeline)   Pre ──────●────── Circa ──────── Post           │
│         offset +1.2 · PHV estimado a los 12.9 años · ventana fuerza abierta     │
├───────────────────────────────────────────────────────────────────────────────┤
│ ROW E · Morfología y ajuste de bici  (StatCard × 4 + bike-fit + disclaimer)     │
│ ROW F · Explicación PHV (IA)  — unchanged                                       │
│ ROW G · Historial de mediciones (compact table, link to Antropometría tab)      │
│ ROW H · Fuentes (collapsed)                                                     │
└───────────────────────────────────────────────────────────────────────────────┘
```

Row A replaces the four page-level tiles for this tab (the page hero keeps name, badge, talla/peso chips). Row B is the surviving `TrainingReadiness`, reduced to the rules that differ from the age-group default, computed from one shared rule table. Row C is `PercentileCurves` restyled. Row D replaces the maturity-offset chart. Row G reuses `AnthropometryHistory` in a compact mode so the coach does not have to switch tabs to see the numbers behind the curve.

### 5.2 Parent — `Crecimiento` tab

```
┌───────────────────────────────────────────────────────────────────────┐
│ Etapa de desarrollo: "El crecimiento de tu hija se está estabilizando" │
│ ┌──────────────────────┐ ┌──────────────────────┐                       │
│ │ Estatura para su edad│ │ Peso para su estatura │   (band icon+label, │
│ │ ● En vigilancia      │ │ ✓ Adecuado            │    narrative, NO Z/P)│
│ │ narrative sentence   │ │ narrative sentence    │                       │
│ └──────────────────────┘ └──────────────────────┘                       │
│ Curva de crecimiento (same chart, family mode: P50 + P3–P97 band only,  │
│   no bio-age toggle, no offset, no legend clutter, table view available)│
│ Explicación PHV (IA, read-only) — unchanged                              │
│ Historial (talla, peso, fecha) — existing parent-mode table              │
└───────────────────────────────────────────────────────────────────────┘
```

Removed for parents: `ResearchReferences`, maturity-offset chart, Z-score/percentile numerals, "IMC" wording as a headline (Res. 2465 uses BMI-for-age; the family label reads "Peso para su estatura" with the technical name in a tooltip — decision D3).

---

## 6. Component plan

| Action | Component / file | What changes |
|---|---|---|
| **New** | `components/athletes/growth/GrowthTab.tsx` (lazy) | Container for rows A–H; `mode: "coach" \| "parent"`; owns the indicator/axis state; `key={athlete.id}` remount like the AI tab |
| **New** | `components/athletes/growth/GrowthStatusRow.tsx` | Row A: four `shared/StatCard` with `tone` + `badge` (`StatusBadge`), sparkline slot (tiny inline SVG, no recharts) |
| **New** | `components/athletes/growth/NextMeasurementCard.tsx` | Reads the new growth summary (§7); `StatusBadge` with the same `STATUS_META` as `dashboard/MeasurementAlerts.tsx` (extract that map to `lib/measurementStatus.ts`) |
| **New** | `components/athletes/growth/MaturationTimeline.tsx` | Row D; pure SVG/CSS, no chart lib; a11y text alternative |
| **New** | `lib/growth/rules.ts` | Single LTAD rule table (age group × stage) consumed by `TrainingReadiness` and exported for the AI catalog docs; FC max derived (`208 − 0.7·age`, Tanaka — or "no estimar" per decision D4) |
| **Refactor** | `PercentileCurves.tsx` | Split into `PercentileChart.tsx` (chart only, ≤ 300 LOC, tokens, solid grid, accent athlete line, 3 lines + 1 band by default, "Detalle" toggle for P10/P25/P75/P90, **x-axis windowed to [first measurement − 2 y, last measurement + 3 y] with a "Ver 5–19 años" toggle**, round y ticks, no full-height alarm fills), `PercentileToolbar.tsx` (indicator `ToggleGroup`, axis toggle, table/PNG actions), `PercentileTable.tsx` (visible table view, replaces sr-only-only); delete local `classifyBand` / `ageMonthsFromDates` in favour of the hook/lib |
| **Refactor** | `GrowthCharts.tsx` | Retire the longitudinal view and the offset chart; becomes the Row C wrapper or is deleted (its 23 tests move to the new components) |
| **Refactor** | `NutritionalClassification.tsx` | Becomes two `StatCard`s in Row A (coach) / two narrative cards (parent); single source = `useGrowthMetrics` on the **latest** record with WHO only (§7) |
| **Refactor** | `TrainingReadiness.tsx` | Consumes `lib/growth/rules.ts`; compact chip list, "Ver todas" collapsible; drop the name chip; alerts via `StatusBadge`/`Alert` |
| **Refactor** | `MorphologyCard.tsx` | Tiles → `shared/StatCard`; copy unchanged |
| **Refactor** | `PHVBadge.tsx` | Map stage → `Status` (Pre = neutral, Circa = warning, Post = success) and render through `StatusBadge`; delete the two other colour maps |
| **Refactor** | `AthleteDetailPage.tsx`, `MyAthleteDetailPage.tsx` | Delete the local `StatCard`; `growth` tab renders `<Suspense><GrowthTab mode=… /></Suspense>`; remove the auto-select-growth effect (D5); fix G-02 by construction (`GrowthTab` picks `records[0]`) |
| **Keep** | `PHVExplanationCard`, `AnthropometryHistory`, `ResearchReferences` (coach only), `lib/growth/lms.ts`, `lib/growth/bands.ts`, `useGrowthMetrics` | Bands file gains parent-mode headline labels (D3). `PHVExplanationCard` gets a title and an `audience: "coach" \| "family"` prompt variant (G-16) — coach text addresses the coach, family text stays as today; both remain consent-gated and guardrail-scrubbed |
| **Delete** | Longitudinal charts in `GrowthCharts.tsx:184-338`, page-local `StatCard`, duplicated helpers, three PHV colour maps | — |

---

## 7. Backend plan

| # | Change | Why | Files |
|---|---|---|---|
| B-1 | **Seed WHO 2007 LMS** into `growth_reference_lms` (`source=WHO`) from vendored XLSX/CSV under `backend/app/data/who_lms/` (height-for-age, bmi-for-age 61–228 mo; weight-for-age 61–120 mo). Keep CDC rows. Offline, idempotent, same upsert as the CDC seed. | G-01; the frontend JSON already proves the data is available and licence-free | `seed_growth_data.py`, `app/data/who_lms/README.md`, `entrypoint.sh` (no change if the seed module loops over both sources) |
| B-2 | **Switch the calculation source to WHO** for height/BMI in `create_anthropometry`; weight-for-age: WHO ≤ 120 mo, else CDC *only if* D1 keeps weight, stored with an explicit `growth_source` column (new nullable enum column, additive migration) so the UI can label it. | G-01, regulatory | `routers/anthropometry.py:128-160`, `models/anthropometry.py`, Alembic revision |
| B-3 | **Backfill v2**: recompute `*_z_score`, `*_percentile`, `nutritional_status` for every row (not only NULLs) when `growth_source` is NULL or CDC; raw columns untouched; aggregate-only logs. | historical rows are CDC today | `scripts/backfill_anthropometry.py` (add `--recompute-source` flag) |
| B-4 | **`GET /api/athletes/{id}/growth-summary`** (coach/admin + the athlete's own parent; parent-denied test for other athletes): `{ stage, maturity_offset, age_at_phv, months_from_phv, growth_velocity_cm_month, growth_velocity_cm_year, velocity_window_days, expected_velocity_range, next_due_date, measurement_status, days_overdue, growth_alerts[], latest: {height_band, bmi_band, weight_band?, source} }`. Pure reuse of `measurement_alerts.py` + `growth.py`; one query for the last two records. | G-06; single source of truth shared with dashboard and AI; avoids re-implementing intervals in the SPA | new `routers/growth.py` route, `schemas/growth.py`, `services/growth_summary.py`, tests |
| B-5 | Align `classify_nutritional_status_height` upper band with the frontend (decision D2) and expose the band enum → label map once (frontend mirrors it in `bands.ts`). | G-03 | `services/growth.py:117-134`, `lib/growth/bands.ts` |
| B-6 | Newsletter PDF chart (`growth_chart_builder.py`) reads `source=WHO` after B-1 so the family PDF and the app agree. Regenerate one real-dataset PDF to check (same SC-1 gate as feature 038). | consistency | `services/training/growth_chart_builder.py` |
| B-7 | Retire or keep `GET /growth-reference`? It is unused by the SPA. Recommendation: keep (cheap, cached) but document it as "PDF/analytics only". | dead surface | `routers/growth.py` docstring |

No change to `POST /anthropometry` inputs, to PHV/Mirwald, to RBAC filters, or to the AI stacks. The AI context already receives `growth_velocity_cm_per_year`/`months_from_phv`; B-4 makes the same numbers visible to the coach.

---

## 8. Privacy, safeguards, accessibility

- `data-privacy-guard` audit is **mandatory** (athlete-identifiable data). Checklist: no birth date on screen (already removed in feature 04 step 15 — keep), no name inside the growth components (drop the `TrainingReadiness` chip), month-year date obfuscation in tooltips/tables preserved (`PercentileCurves.tsx:213-220`), PNG export file name without name/id (today: indicator + timestamp — keep), no PII in `growth-summary` logs.
- Parent mode never shows Z-score, percentile numerals, the Mirwald offset, "obesidad"/"delgadez" headlines, or bibliography. Band narratives from `bands.ts` are the parent copy; review them with `parent-communicator` for tone.
- Constitution III: every status carries icon + label (`StatusBadge`); colour is never the only channel in bands (keep line dash patterns + labels in the chart).
- WCAG AA: keep the `role="img"` + text alternative; **promote the sr-only table to a visible table view** (033 FR-003 "table view available"); 48 px targets for toggles (the 033 F-6 fix set `min-h-12` on selects — apply to the indicator/axis `ToggleGroup`); `prefers-reduced-motion` respected (animations already off in recharts).
- Language: all new copy in español neutro with diacritics (note: `PercentileCurves.tsx` ships "Cronologica"/"Biologica"/"Interpretacion"/"Detalles tecnicos" without accents — fix in the restyle).

---

## 9. Phased roadmap

Each phase is independently shippable; 0 and 1 must land before 2. Sizes assume the Sonnet/Opus wave workflow used for 036–039.

| Phase | Scope | Agents | Size | Gate |
|---|---|---|---|---|
| **0. Correctness (no visual change)** | G-02 parent latest-record fix; G-04 FC max (D4); G-03 band alignment (D2); e2e `history.spec.ts` decoupled from auto-select (keep behaviour for now) | `react-ui-engineer`, `qa-engineer` | 0.5 d | vitest + e2e green |
| **1. One reference standard** | B-1 seed WHO; B-2 source switch + `growth_source` column; B-3 recompute backfill; B-5 band map; B-6 PDF chart on WHO; frontend `useGrowthMetrics` stops preferring backend Z unless `source === "WHO"` (transitional) | `database-architect`, `fastapi-architect`, `qa-engineer`, `data-privacy-guard` | 2 d | `pytest` (default + `-m mysql` for the migration/backfill on a `_test` DB); Z parity test: backend WHO Z vs `lib/growth/lms.ts` on 6 fixture points ±0.02; one real PDF regenerated |
| **2. Growth summary endpoint** | B-4 route + schema + service + tests (happy, parent-own, parent-other 403, admin, no-records, single-record velocity = null); frontend `useGrowthSummary` hook + MSW handler + Zod schema | `fastapi-architect`, `react-ui-engineer`, `qa-engineer` | 1.5 d | p95 ≤ 500 ms (one query); denied-path test |
| **3. Coach tab redesign** | `GrowthTab` lazy container; Row A/B/D new components; `PercentileCurves` split + restyle (tokens, solid grid, accent, table view, responsive height); `TrainingReadiness` on `lib/growth/rules.ts`; `MorphologyCard` on `StatCard`; `PHVBadge` → `StatusBadge`; delete longitudinal charts + local `StatCard` + colour maps; remove auto-select (D5); jest-axe zero violations on `GrowthTab` | `react-ui-engineer` ×2 (parallel: rows A/B/D vs chart split), `ux-researcher` (review), `qa-engineer` | 4 d | `npm run build` route chunk report (recharts + WHO JSON out of the main chunk, growth chunk ≤ 120 KB gz); vitest ≥ current 73 tests re-homed; e2e `growth.spec.ts` (open tab → curve → indicator switch → table view → PNG) |
| **4. Parent (family) mode** | `GrowthTab mode="parent"`: narrative cards, family chart preset, no Z/P/offset/bibliography; parent copy pass; `MyAthleteDetailPage` wiring; e2e parent spec | `react-ui-engineer`, `parent-communicator`, `data-privacy-guard`, `qa-engineer` | 1.5 d | privacy audit PASS; jest-axe; e2e `ai-insights-parent.spec.ts`-style parent run |
| **5. Close-out** | `docs/implementation-status.md` + `docs/technical-notes.md` entries; `docs/04-percentiles/workflow.md` "superseded by 18" banner; `docs/06-parents/workflow.md:26` marked done; CLAUDE.md active-feature block via `/speckit-agent-context-update`; post-deploy smoke: `/health` + `GET /growth-summary` on one athlete; prod backfill run once (`entrypoint.sh` already runs it) | `technical-writer`, `release-manager` | 0.5 d | smoke OK |

Total ≈ **10 working days**; phases 3 and 4 are where the wave workflow pays off (two UI workers in parallel).

### Dependency graph

```
0 ──► 1 ──► 2 ──► 3 ──► 4 ──► 5
      │           ▲
      └───────────┘  (3 can start its component work on mocks while 2 finishes; wiring waits)
```

---

## 10. Decisions required from the coach (before `/speckit-specify`)

| ID | Question | Recommendation |
|---|---|---|
| **D1** | Weight-for-age above 10 years: keep it via CDC (labeled "CDC 2000") or drop it and keep only BMI-for-age (WHO)? | **Drop.** Res. 2465 does not use weight-for-age at 5–17; BMI-for-age plus the velocity tile carry the information, and one standard is simpler to explain to families. Keep the raw weight sparkline in Row A. |
| **D2** | Upper height band: keep the frontend's "Talla alta" (Z > 1 / Z > 2, blue) or follow Res. 2465 literally (no upper cut-off → "Adecuada" up to Z ≤ 2, "Talla alta" only > 2)? | **Follow the resolution** (backend behaviour); blue "Talla alta" only above +2, informational not a status. |
| **D3** | Parent headline wording for BMI-for-age and its bands ("Sobrepeso"/"Obesidad" vs the band narrative only). | Show band **narrative + neutral label** ("Por encima del rango esperado — revisaremos la tendencia") in parent mode; clinical label only in coach mode. |
| **D4** | Estimated max HR in the rules: derive by formula (Tanaka `208 − 0.7·age`), or remove the number and keep "sin test" only? | **Remove the number.** `docs/01-marco-teorico.md` §9 says HR is unreliable as a training driver at this age; a printed estimate invites zone training the same rules forbid. |
| **D5** | Keep the auto-switch to `Crecimiento` when measurements exist? | **Remove.** Land on `Info general` with the new Row A summary lifted into the page tiles; `Crecimiento` is a deliberate tap. |
| **D6** | Keep the PNG export? | **Keep** (coach uses it for families/medical referrals) but move it into the chart toolbar and export the table as well. |
| **D7** | Should Row B (training rules) stay on this tab, move to the session planner, or become an AI-only input? | **Stay, compact** — it is the bridge between growth data and the coach's decision; the full table lives in one place (`lib/growth/rules.ts`) so the planner and AI can consume the same rules later. |

---

## 11. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| WHO recomputation changes stored classifications for existing athletes (some children move band) | Families already received PDFs with CDC values | Backfill logs aggregate counts of band changes; coach reviews the list before the next newsletter cycle; note in `technical-notes.md` |
| Render free tier: backfill at startup over all rows | Cold-start time | Backfill is idempotent and skips rows already marked `WHO`; first run only |
| `PercentileCurves` split regresses the interactive legend / bio-age toggle behaviour | Coach loses a feature they use | Behaviour-level tests written before the split (characterization tests on the current component), then moved |
| Parent-mode copy drifts from the coach's reading of the same data | Trust | Both modes read the same `useGrowthMetrics` band; only the label layer differs; snapshot test asserts band equality |
| Golden eval / AI prompts reference "growth_velocity" already — no change expected | — | Run `pytest -m golden` once after phase 2 as a no-regression check (quota permitting) |

---

## 12. Success criteria

- SC-1 A given measurement shows **one** Z/percentile everywhere (card, tooltip, table, PDF); source label reads "OMS 2007 / Res. 2465/2016" and is true.
- SC-2 On opening `Crecimiento`, stage, velocity, both bands and next-due date are visible without scrolling on a 1024 px tablet and on a 390 px phone (stacked).
- SC-3 Parent view shows zero Z-score/percentile numerals, zero clinical headline labels, and the **latest** measurement.
- SC-4 Main bundle no longer contains recharts or the WHO JSON; growth chunk ≤ 120 KB gzipped; LCP budget unchanged (Constitution IV).
- SC-5 jest-axe zero violations on `GrowthTab` in both modes; visible table view for the curve; all toggles ≥ 48 px.
- SC-6 No raw hexes in `components/athletes/growth/**`; grid solid; athlete series in `--color-primary`.
- SC-7 `data-privacy-guard` audit PASS; e2e coach + parent growth specs green; unit test count ≥ 73 re-homed.

---

## 13. Suggested next step

1. Answer D1–D7 (defaults above are safe).
2. Run `/speckit-specify` with this document as the description source → `specs/040-growth-module-redesign/spec.md`; then `/speckit-plan` and `/speckit-tasks`.
3. Branch `feat/040-growth-module-redesign` after 039 is committed.
