# Phase 0 Research: Prefill results import from an existing competition

Date: 2026-06-16 · Branch: `015-prefill-import-from-competition`

Method: codebase mapping (Explore agent) + sequential reasoning (sequential-thinking MCP) + library docs (Context7) + web best-practices search.

## R0 — Why the wizard re-asks data today (root cause)

**Decision**: The container passes no competition context to the wizard.

**Evidence**:
- `frontend/src/routes/competitions/CompetitionImportPage.tsx` reads `id` via `useParams` and uses it only for the back-link and the post-commit redirect, then renders `<ImportWizard onCompleted={handleCompleted} />` — `id` is never handed to the wizard (`ImportWizardProps` = `{ onCompleted? }`, line 312).
- `ImportWizard.tsx` initializes RHF with `defaultValues: { series_kind: "cup", … }` (line 386) → step 1 is always blank and "Tipo de competencia" always defaults to **Copa**, even for a championship (event id 15 = `is_championship` Campeonato).
- Spec 014 anticipated this (US3/FR-008: "import must not assume Copa Valle; flow derives the series") but the "derive from parent event" half was never built.

**Implication**: A small wiring + view-model change closes the gap; no backend gap exists.

## R1 — Backend already exposes everything needed (no API change)

**Decision**: Reuse existing read endpoints; **no new endpoint, no migration**.

**Evidence** (backend, verbatim fields):
- `GET /api/race-analysis/race-events/{id}` → `RaceEventRead` (`schemas/race_event.py:167`) returns `id, series_id, sequence_number, name, event_date, location, is_championship, status, climate, temperature_c, surface_condition, altitude_msnm, weather_notes, created_by_user_id, created_at, updated_at, has_calendar_event`.
- `GET /api/race-analysis/race-series` → `RaceSeriesListResponse { items: RaceSeriesRead[], total }`; `RaceSeriesRead` = `id, name, season_year, organizer, kind (cup|championship), event_count` (`schemas/race_series.py:65`). There is **no** single `GET /race-series/{id}`; resolve by filtering the list on `series_id`.
- Import `POST /api/race-analysis/imports/parse` accepts form fields `series_name, season, valida_num, event_name, event_date, location, series_kind (cup|championship, default cup), kind, conditions…, resultados_pdf, general_pdf`. It resolves/creates the series by `(series_name, season)` and links to an existing event through its revision / `parent_event_id` path.

**Derivation map for prefill** (event + series → wizard fields):
- `series_kind` ← `series.kind` (by `event.series_id`)
- `series_name` ← `series.name`
- `season` ← `series.season_year`
- `valida_num` ← `event.sequence_number` (cup only; hidden for championship)
- `event_name` ← `event.name`; `event_date` ← `event.event_date`; `location` ← `event.location`
- conditions (`climate, temperature_c, surface_condition, altitude_msnm, weather_notes`) ← event (optional; remain editable as today)

## R2 — Linking to the *exact* competition (FR-003 / SC-003)

**Decision**: Rely on the existing header-matching with prefilled-exact values; do **not** add an explicit `race_event_id` param to `/parse`.

**Rationale**: `/parse` resolves the series from `(series_name, season)` and the event from `(series_id, valida_num)`. Spec 014 made `(series_id, sequence_number)` effectively unique per event (championships are standalone series with `sequence_number=1`; cup rounds have a unique válida per series). Prefilling the **stored** values reproduces exactly that key → the existing revision/`parent_event_id` path links results to the same competition, with no coach re-selection. This keeps the change within FR-011 ("MUST NOT change how results are parsed/ingested/validated").

**Alternatives considered**:
- *Option B — backend `race_event_id` param + `GET /race-events/{id}/import-prefill` endpoint*: stronger "exact" guarantee and server-side FR-009 block, but changes parse behavior (against FR-011 spirit), adds endpoint + tests + RBAC surface. **Rejected** as out of scope; recorded here as a future hardening if header-matching ever proves insufficient.
- *Read-only on the whole step 1*: rejected — conditions and file upload must stay interactive.

## R3 — Locked / read-only fields: accessibility (Constitution III, WCAG 2.1 AA)

**Decision**: Render the derived identity fields (name, date, city, series, type, round) as a **read-only summary block** (static text, styled like the detail "Información" card), not as `disabled` inputs. Keep the actual values in RHF state (so they submit). Provide an explicit **"Editar metadata"** link (to `/competitions/{id}/edit`) as the escape hatch (FR-006).

**Rationale** (web best-practice search): `disabled` removes elements from the tab order **and** omits them from form submission; `aria-disabled` keeps focus but does not block editing. For values that are purely informational-and-locked, the cleanest accessible pattern is non-interactive read-only text with a clear label (not placeholder-only), preserving keyboard navigability and screen-reader clarity. Where an actual input must remain visible (none required here), prefer `readOnly` over `disabled`.

**Sources**:
- [aria-disabled vs disabled — when to use each (DhiWise)](https://www.dhiwise.com/post/aria-disabled-vs-disabled-when-to-use-each)
- [Accessible Form Validation: Best Practices (UXPin)](https://www.uxpin.com/studio/blog/accessible-form-validation-best-practices/)
- [How to use aria-required correctly — 2026 guide (Greadme)](https://www.greadme.com/blog/accessibility/how-to-use-aria-required-correctly-complete-guide)

## R4 — FR-009: competition with no determinable series/type

**Decision (from /speckit-clarify, Session 2026-06-16)**: **Block** the prefilled import and direct the coach to "Editar metadata" to assign a series/type; never offer an in-flow series/type selector (preserves FR-005).

**Implementation**: client-side. `event.series_id` is a non-null FK, so the normal case always resolves. The block path triggers when the series cannot be resolved from `GET /race-series` (missing/empty/fetch failure). Render a designed blocked state (not a raw error) with a link to `/competitions/{id}/edit`.

## R5 — Mutation testing with Stryker (user request)

**Decision**: Add `frontend/stryker.config.json` using the Vitest runner, **scoped** to the new prefill logic only (keep runtime sane), and a `test:mutation` script.

**Config** (validated against Context7 StrykerJS docs):
```json
{
  "$schema": "./node_modules/@stryker-mutator/core/schema/stryker-schema.json",
  "packageManager": "npm",
  "testRunner": "vitest",
  "plugins": ["@stryker-mutator/vitest-runner"],
  "coverageAnalysis": "perTest",
  "concurrency": 2,
  "timeoutMS": 60000,
  "reporters": ["html", "progress"],
  "mutate": [
    "src/hooks/race/useImportPrefill.ts",
    "src/components/competitions/import/ImportWizard.tsx",
    "!src/**/*.test.ts",
    "!src/**/*.test.tsx"
  ],
  "thresholds": { "high": 85, "low": 70, "break": 60 }
}
```
**Rationale**: deps `@stryker-mutator/core` + `@stryker-mutator/vitest-runner` (9.6) are already installed but unconfigured. Scoping `mutate` to the prefill surface keeps mutation runs fast and focused on the logic this feature introduces (derive/lock/hide/block), surfacing weak assertions the line-coverage tests might miss. `break: 60` fails CI below 60% mutation score.

**Sources** (Context7 `/stryker-mutator/stryker-js`): vitest-runner config, `mutate` globbing, thresholds.

## R6 — E2E with Playwright (user request)

**Decision**: Add `frontend/e2e/prefill-import-from-competition.spec.ts`, following the established pattern in `e2e/cup-vs-championship.spec.ts` and `e2e/competitions-unification.spec.ts` (Playwright config + suite already exist; `test:e2e` script present).

**Scenarios**:
1. From a completed **cup** competition → launch import → step 1 shows name/date/city/series/type as locked read-only, `válida #` shown locked, type = Copa (never defaults wrong); reach the upload step with **zero** re-typed metadata fields.
2. From a completed **championship** → `válida #` concept absent; type = Campeonato.
3. **Standalone** `/competitions/import` → unchanged (empty, editable, no locking).
4. **Block** path → competition with unresolvable series shows the blocked state + "Editar metadata" link; import cannot proceed.
5. **Privacy** → prefilled step carries only competition metadata; no athlete name appears before the dry-run match step.

## Open questions

None. FR-009 resolved via clarify. All Technical Context items resolved (no NEEDS CLARIFICATION remain).
