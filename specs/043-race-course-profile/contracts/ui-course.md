# Contract — Course UI (coach tab, wizard panel, results columns, parent card)

**Pages**: `frontend/src/routes/competitions/CompetitionDetailPage.tsx` (URL tabs, `TabValue:86`), `CompetitionFormPage.tsx` (success link only), `components/competitions/import/ImportWizard.tsx` (step 3 panel), `routes/parents/competitions/ParentCompetitionResultsPage.tsx`, `routes/parents/calendar/ParentEventDetailPage.tsx`. **Patterns reused**: tri-state card `components/race/RaceConditionsCard.tsx` + sheet `EditConditionsDialog.tsx`; dynamic Leaflet import from `components/training/RouteViewer.tsx`; lazy tabs like `AthletesTab`/`InsightsTab`. Binding: `research.md` R-12, R-13, R-14. Requirements: FR-001, FR-010–FR-013, FR-022–FR-024; SC-001, SC-006; User Stories 1, 3, 5.

## 1. Files

```text
frontend/src/
├── api/raceCourse.ts                       # getCourse, uploadVariant, replaceVariantFile, renameVariant, deleteVariant, putSetups, patchDescription
├── types/raceCourse.types.ts               # CourseRead, Variant, Setup, Description, enums (TerrainType, KeySector)
├── schemas/raceCourse.ts                   # Zod: variantUploadSchema, setupsSchema, descriptionSchema (mirrors backend limits)
├── hooks/race/useRaceCourse.ts             # useRaceCourse(id) [key ["race-course", id]], mutations invalidating it + ["race-results", id]
├── components/race/course/
│   ├── CourseTab.tsx                       # coach composition (variants, setups, description, summary); prop `compact` for the wizard
│   ├── VariantsCard.tsx                    # list + "Agregar variante" (≥48 px) + rename/replace/delete per row
│   ├── VariantUploadDialog.tsx             # Sheet: label, file input (.gpx), optional "vueltas grabadas"; shows detection result for confirmation
│   ├── CategorySetupTable.tsx              # RHF+Zod table: category | laps (1–20) | variant select; prefill banner from suggested_setups
│   ├── CourseDescriptionCard.tsx           # tri-state card (empty/partial/complete) — copy of RaceConditionsCard structure
│   ├── EditCourseDescriptionDialog.tsx     # Sheet with terrain select, difficulty 1–5 radio, sectors checkboxes, notes textarea (counter /1000)
│   ├── CourseSummary.tsx                   # read-only: figures, laps by category, description, <Suspense> map + profile
│   ├── CourseMap.tsx                       # lazy: Leaflet polyline, fitBounds, aria-label, focusable
│   ├── ElevationProfile.tsx                # lazy: Recharts AreaChart, ≤200 samples, role="img" + aria-label
│   └── __tests__/…                         # vitest + jest-axe per component with branching
└── test/msw/raceCourseHandlers.ts          # MSW handlers for the seven endpoints
```

## 2. Coach — "Circuito" tab

- `TabValue` gains `"circuito"`, inserted after `"conditions"`; the trigger label is "Circuito"; lazy-loaded like `AthletesTab`. Visible for every válida (coach/admin only reach this page).
- Empty state (`has_course_data=false`): one card "Sin circuito registrado" with "Agregar variante" and "Describir la pista" buttons (coach/admin); text explains what the circuit data enables.
- **Upload flow** (`VariantUploadDialog`): fields `label` (default "Circuito completo" for the first variant, "Recorrido reducido" for the second), `file` (`accept=".gpx"`), optional `recorded_laps`. On success the dialog shows the detection: "Detectamos {laps_detected} vueltas de {lap_distance_km} km ({elevation_gain_m} m de desnivel). ¿Es correcto?" with "Sí, guardar" (closes) and "No, indicar vueltas" (reveals `recorded_laps` and re-submits via `PUT …/file`). For `method="manual"` without `recorded_laps`: "No detectamos una vuelta cerrada; se tomó toda la grabación como una vuelta ({lap_distance_km} km). Si grabaste varias vueltas, indícalo." Errors map the `code` table of `course-api.md` §6 to inline messages; never raw text.
- **Setups table**: one row per category present in the válida's results **union** categories already in `setups` **union** categories in `suggested_setups`; laps input (numeric, 48 px), variant select. When `setups` is empty and `suggested_setups` is not, a banner "Sugerido desde la válida anterior" pre-fills the rows and the save button reads "Confirmar vueltas". Save = `PUT /course/setups` with the whole table. Category with no laps → row saved only if laps set (blank rows are omitted).
- **Description card**: tri-state like conditions; edit sheet with Zod (`technical_difficulty` 1–5 with labels "1 — Muy fácil, 2 — Fácil, 3 — Media, 4 — Técnico, 5 — Muy técnico", `key_sectors` ≤ 8, notes ≤ 1 000 with live counter, inline errors, no HTML5 validation).
- **Summary** below: `CourseSummary` (same component parents see), one section per variant: figures line, `<Suspense fallback={<Skeleton/>}>` around `CourseMap` and `ElevationProfile`; profile hidden when `has_elevation=false` ("Sin altimetría en la grabación").
- Delete variant with 409 → toast listing the categories; rename inline.

## 3. Import wizard — step 3 panel

After a successful commit (step 3, "Resultado"), below the summary and above the link to analysis, render `<CourseTab raceEventId={committedEventId} compact />` under a heading "Circuito (opcional)". `STEPS` stays three entries; no new gate; the step-focus effect is untouched. "Continuar sin circuito" is simply leaving the page. The existing wizard tests keep passing; a new test asserts the panel appears only when `race_event_id` is known and the commit succeeded.

## 4. Create/edit form

`CompetitionFormPage` is not extended with uploads. Its success state gains a secondary action "Agregar circuito" linking to `?tab=circuito` of the new válida.

## 5. Results table

`ResultsTable.tsx` (lazy) renders two extra columns, "Distancia" (km, 1 decimal) and "Vel. prom." (km/h, 1 decimal), **only when** `EventResultsRead.has_course_data` is true; cells show "sin dato" (muted) for `null`. Category header shows "{laps} vueltas · {variant_label} · {lap_distance_km} km · {elevation_gain_m} m D+" when the setup exists. The parents' results page uses the same table and therefore inherits the columns for their own rows.

## 6. Parents — `CourseSummary` card

- `ParentCompetitionResultsPage`: `useRaceCourse(raceEventId)` with `retry: false`; on `404` the card is absent (no error state, no toast); on success render `CourseSummary` above the results with the laps of the child's category highlighted per `my_categories` ("{Nombre de la categoría}: 3 vueltas · Recorrido reducido"), labelled by child using the existing child selector context of that page (never a name outside what the page already shows to this parent).
- `ParentEventDetailPage` (calendar): when the calendar event links a válida (`race_event_id` present on the event payload), render the same card so families can prepare before race day; same 404 handling.
- Progressive rendering: figures, laps and description are plain DOM rendered before the lazy chunks resolve; the map and chart load inside Suspense with a skeleton, so on 3G the text is readable first (FR-024, SC-006).
- Mobile: map height 240 px, chart 160 px, both full width; no horizontal scroll.

## 7. Accessibility and consistency

- All targets ≥ 48 px; Sheets trap focus and close on Escape (shared `Sheet`/`Dialog` primitives).
- `CourseMap`: container `role="region"`, `aria-label="Mapa del circuito {label}"`, `tabIndex=0`; Leaflet controls keep their native keyboard handling. `ElevationProfile`: `role="img"`, `aria-label` = "Perfil de altimetría: de {min} a {max} m, {gain} m de desnivel positivo".
- Colours: one neutral series colour for the profile and the polyline (per the `dataviz` skill palette rules); green/amber/red never used for course data.
- jest-axe zero violations on `CourseTab`, `VariantUploadDialog`, `EditCourseDescriptionDialog`, `CourseSummary` (with mocked map), the parents page with the card, and `CompetitionDetailPage` on the new tab.
- Copy in español neutro with diacritics; units "km", "km/h", "m", "D+".

## 8. Tests

vitest: `CourseTab` empty/partial/complete branches by role (coach vs parent read-only); upload dialog detection copy for `closed_loop` / `manual` / `single`; setup table prefill banner and omission of blank rows; description sheet validation (notes 1 001 chars, difficulty out of range); results table columns present only with `has_course_data`; parents page hides the card on 404. Playwright (`frontend/e2e/race-course.spec.ts`, isolated stack, seeded demo válida): upload a synthetic GPX from `e2e/fixtures/course_3laps.gpx`, confirm detection, set laps, save description, open results and see the columns, then log in as the seeded parent and see the card. `VITE_API_BASE_URL` must be set (see the e2e base-URL note in `playwright.config.ts`).
