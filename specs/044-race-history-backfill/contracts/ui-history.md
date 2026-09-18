# Contract — UI (US1, US4, US5, US6, US7)

All copy in español neutro (Colombia) with full diacritics. Forms: React Hook Form + Zod, inline errors, no HTML5 validation. jest-axe zero violations on every surface listed.

## 1. `HistoryProgressionCard` (`components/race/history/`, lazy)

- Data: `useAthleteRaceHistory(athleteId)` (TanStack Query, key `["athlete-race-history", id]`).
- Text first: season completion chips ("2025 · 6 de 7") and the latest three results render as plain DOM before the chart chunk loads (3G budget).
- Chart (Recharts `ComposedChart`, time-scale x): metric toggle **Brecha a la mediana** (default) / **Velocidad media**; never two y-axes. Gap axis inverted so up = faster; zero line labelled "Mediana de su categoría". `ReferenceLine` per `category_changed` point, label "Infantil B → Prejuvenil A". Dashed connector across missing válidas/seasons; DNF/DSQ/DNS drawn as a hollow marker on the baseline with its status in the tooltip and no value. Tooltip always shows "Parrilla: 23". One neutral series colour; status colours untouched. Chart has a text alternative (the table below) and `aria-describedby` to the caveats.
- Table grouped by season → category: fecha, válida, puesto, percentil, parrilla, brecha, velocidad. No row or line joins two groups. "sin dato" wherever the API sends `null`.
- Caveats block, always visible, `role="note"`: one sentence per `caveats` code.
- Family variant (`audience="family"`): at each category change, "Subió de categoría: ahora corre con deportistas mayores. Es normal que el puesto baje al comienzo." No comparative wording about the child.
- Mounted on the coach's athlete race-analysis surface and on `routes/parents/MyAthleteDetailPage.tsx`.

## 2. Import preview extensions (`components/competitions/import/`)

- `CategoryMappingTable`: encabezado impreso · categoría · tipo (exacta / renombrada / propia de esa temporada / sin reconocer) · filas · estado.
- Completeness badge per category; inconsistent rows list "Falta el puesto 6" / "El puesto 20 está repetido".
- `RowCorrectionDialog` (add/edit/remove one row) and `AcknowledgeGapDialog` (reason from the closed catalogue).
- Commit button: disabled with the reason when identity review is pending; otherwise "Confirmar categorías completas (21 de 23)".

## 3. `HistoricalLoadPage` (`routes/competitions/history/`)

Board of staged imports by season: archivo leído → categorías por revisar → identidad por revisar → listo → cargado. Shows pending-category counters and the identity-review banner with its count. Coach/admin only.

## 4. `IdentityReviewPage`

One candidate at a time or list; two cards side by side (nombre impreso, club, ciudad, temporadas, categorías) with the signals in words ("Mismo nombre en dos categorías de la misma válida"); two ≥ 48 px buttons "Es la misma persona" / "Son personas distintas"; keyboard shortcuts; progress "12 de 57"; filter by state; "Deshacer" on decided items with confirmation. Warning chip when a linked athlete is involved.

## 5. Standings label

Historical and current standings tables show "Clasificación calculada por la plataforma".

## Tests

vitest + Testing Library + MSW per component (states: loading skeleton, empty, error, gate-closed family view, all-null metrics); role branches; jest-axe on the card (both audiences), both pages and both dialogs; Playwright `race-history.spec.ts` on the isolated stack (stage two synthetic files → correct a gap → decide identity → commit → coach series with marker → parent view without third parties).
