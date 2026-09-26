# Contract — Web app: review and commit only (amendment 2026-09-26 · FR-044 · FR-048 · SC-014)

The web app keeps every review screen and loses the upload step. Loads are prepared outside the app by the results skill and appear on the board (*Competencias › Cargas*), where the coach reviews and commits them. Research: R-26, R-27, R-31. The line numbers below are from the frontend sweep at `ebbb786` and are only a guide.

## Routes (`src/App.tsx`)

| Route | Before | After |
|---|---|---|
| `/competitions/import?import=<id>`, `/competitions/:id/import?import=<id>` | wizard resumes at step 2 | **review of the staged import** (unchanged entry, the wizard without step 1) |
| `/competitions/import` (no `?import`) | step 1 upload form | redirect to `/competitions/imports?seccion=cargas` |
| `/competitions/:id/import` (no `?import`) | step 1 with calendar prefill | redirect to `/competitions/imports?seccion=cargas` |
| `/competitions/imports`, `/competitions/history` redirect | board | unchanged |

## Wizard (`ImportWizard.tsx`, `CompetitionImportPage.tsx`)

- **Steps.** `STEPS` becomes `["Revisar carga", "Resultado"]`, and the review opens directly on the staged import.
- **Deleted, step 1 only:**
  - `step1Schema` and its `useForm`;
  - venue-altitude autofill, prefill reset and the prefill blocks (`PrefillLockedSummary`, `PrefillLoadingState`, `PrefillBlockedState`, `PrefillErrorState`);
  - metadata fields, the conditions section, the upload zones, the step-1 error box and *Continuar*;
  - `submitStep1`, the `resultadosPdf` / `generalPdf` state, `raceEventId` prefill wiring and the "not ready" branch.
- **Changed.** *Volver* on step 2 goes back to the board, not to step 1. `reset()`, *Empezar una carga nueva*, *Cargar otro* and a successful discard all navigate to the board.
- **Unchanged.** Dry-run (including the revision branch, now reachable: `revision-via-skill.md`), `CategoryMappingTable`, `RowCorrectionDialog`, `AcknowledgeGapDialog`, match resolution, commit, discard, and step 3 (the AI button, `RaceConditionsCard`, `CourseTab`). `CompetitionImportPage.handleCompleted` still navigates to the válida.
- `resumeFromDetail.ts` stays the entry point.
- **Legacy imports.** When the detail says the import was staged by the old upload (any review route answers `409 restage_required`), `ResumeStatusNotice` shows the legacy message below, and only *Descartar* is offered.

## Removed

| Item | Path |
|---|---|
| Dropzone | `components/competitions/import/RaceUploadZone.tsx` and its test |
| Upload call | `api/raceImports.ts` `parseRaceImport` |
| Hook | `hooks/ai/useRaceImports.ts` `useImportParse`, `UseImportParseVariables` |
| Types | `ImportParseRequestFields`, `ImportPrefill*` (`types/raceImports.types.ts`); `ImportParseResponse` stays, because the resume path uses it |
| Prefill hook | `hooks/race/useImportPrefill.ts` |
| Env | `VITE_RACE_MAX_PDF_MB` (`vite-env.d.ts`, `.env.example` if present) |

## Entry points

| Location | Before | After |
|---|---|---|
| `CompetitionsListPage` header | «Cargar resultados» → wizard | removed; «Carga histórica» / board link stays |
| `CompetitionsListPage` row menu | «Importar resultados» | removed |
| `CompetitionDetailPage` primary CTA | «Importar resultados» | removed |
| `tabs/ResultsTab` empty state | CTA «Importar resultados» | copy below plus link «Ir a Cargas» |
| `imports/LoadsSection` header and empty state | «Cargar archivo» | removed; new description and empty-state copy below |
| `imports/LoadsSection` «Retomar» and `matches_unresolved` link | «Retomar en el asistente de importación» | «Revisar la carga» (same href) |
| `imports/IdentitySection` «Volver a la carga» | unchanged href | unchanged |
| `calendar/EventForm` hint | «…Crea una desde el módulo de importación» | copy below |
| `dashboard/PendingInbox` «Resultados por importar» | list filter | unchanged (it lists válidas still without results) |

## Copy (español neutro; reviewed by `ux-researcher`)

| Where | Old | New |
|---|---|---|
| Board description | «…Retoma una carga en curso donde la dejaste, sin volver a subir el archivo.» | «Aquí revisas y confirmas las cargas de resultados. Las cargas nuevas se preparan fuera de la app y aparecen aquí cuando están listas.» |
| Board empty state | «Todavía no hay cargues históricos» / «Sube el primer archivo…» | «Todavía no hay cargas por revisar» / «Cuando se prepare la carga de una válida, aparecerá aquí para que la revises y la confirmes.» |
| Results tab, no results | «Importa el PDF oficial de la Copa Valle…» | «Esta válida todavía no tiene resultados. Cuando su carga esté lista, la encontrarás en Cargas para revisarla.» |
| Review page title and subtitle | «Importar resultados» / «Carga el PDF oficial…» | «Revisar carga de resultados» / «Revisa la lectura, resuelve lo pendiente y confirma.» |
| Legacy notice | «Esta carga no se pudo leer. Sube el archivo de nuevo.» | «Esta carga se preparó con el método anterior y ya no se puede revisar. Descártala y pide que se prepare de nuevo.» |
| Discard dialog | «…El archivo no se borra: si lo necesitas, puedes subirlo de nuevo.» | «El archivo original queda guardado como respaldo. Si descartas la carga, habrá que prepararla de nuevo.» |
| Diff table aria-label | «Diferencias entre el PDF nuevo y los resultados ya importados» | «Diferencias entre la lectura nueva y los resultados ya cargados» |
| 409 message | «Este PDF ya fue ingestado previamente.» (any 409) | per code: `already_committed` → «Esta carga ya fue confirmada.»; `restage_required` → legacy notice; others keep their current handling |
| Commit button | «Confirmar e ingestar» | «Confirmar carga» |
| Success title | «Ingesta completada» | «Carga confirmada» |
| Calendar hint | «Crea una desde el módulo de importación» | «La válida se crea cuando se confirma su carga de resultados.» |
| Loading fallbacks | «Cargando wizard…» / «Cargando importación...» | «Abriendo la carga…» |

Also removed: every string that only existed in step 1 or `RaceUploadZone` (the list is in the sweep: size and format errors, dropzone labels, «Debes adjuntar el archivo de resultados.»).

## Tests

**Deleted** (they test removed code):
- `RaceUploadZone.test.tsx`
- `api/__tests__/raceImports.conditions.test.ts`
- the `useImportParse` cases in `useRaceImports.test.tsx`
- `ImportWizard.prefill`, `.locked`, `.championship` and `.standalone` `.test.tsx` (step 1 only)
- the step-1 parts of `ImportWizard.014.test.tsx`
- `ImportWizard.conditions.test.tsx`: conditions left the wizard; `RaceConditionsCard` keeps its own tests

**Ported** to start from `?import=<id>` with MSW, following the `ImportWizard.resume.test.tsx` pattern:
- `ImportWizard.test.tsx` (steps 2–3, matches, errors per 409 code)
- `ImportWizard.categories.test.tsx`
- `ImportWizard.postimport.test.tsx`
- `DiffConfirm.test.tsx`, now through the real revision dry-run shape
- the upload-only regression case of `ImportWizard.resume.test.tsx`

**Updated:**
- entry-point assertions in `CompetitionsListPage.test.tsx`, `ResultsTable.test.tsx`, `EventForm.race-event-id.test.tsx`, `CompetitionImportPage.test.tsx` and `navigation.test.ts`;
- the redirects in `competitionsRedirects.test.tsx` (no `?import` → board; `?import` still routes);
- the resume hrefs and copy in `LoadsSection.test.tsx` and `CompetitionImportsPage.test.tsx`.

**Added:**
- `noResultsUpload.test.tsx`: render the review page, the board, the competitions list, the competition detail and the results tab, and assert there is no `input[type=file]` and no «Cargar resultados», «Importar resultados» or «Cargar archivo» text.
- A legacy notice test (409 `restage_required` → notice plus discard only).
- jest-axe with zero violations on the review page and the legacy notice.

**Playwright:**
- `race-history.spec.ts` stages its synthetic files with `python -m scripts.race_results stage --target local` against the e2e stack's database (after `mask`/`apply` with a test profile), instead of `setInputFiles`. Everything after staging stays as is.
- `prefill-import-from-competition.spec.ts` is deleted: the feature is retired, and `race_event_id` in the manifest replaces it.
- `cup-vs-championship.spec.ts` E2E-014-006 now asserts that the level staged in the manifest shows in the review header.
- `race-course.spec.ts` is untouched.
