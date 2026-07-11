# Tasks: Coach Surface Subtraction

**Input**: Design documents from `/specs/029-coach-surface-subtraction/`

**Prerequisites**: plan.md, spec.md (required for user stories), research.md (R1-R6), data-model.md, contracts/removal-and-redirect-manifest.md, contracts/progreso-tab.md, contracts/anxiety-interpretation-ui.md, quickstart.md. Consumes `specs/028-frontend-design-foundation/contracts/shared-components.md` (`ToggleGroup` primitive, already installed at `frontend/src/components/ui/toggle-group.tsx`) and `currentSeason()` from `frontend/src/lib/datetime.ts` (feature 028 R11 — recommended ship order is 028 before 029 per spec.md Assumptions).

**Tests**: Required, not optional. Constitution Principle II (NON-NEGOTIABLE) mandates every touched surface carry a test disposition (delete/update/add). research.md R5 enumerates the file-level dispositions; each is its own task below, grouped with the removal/change it travels with.

**Organization**: Tasks are grouped by phase, then by user story (US1 P1, US2 P2, US3 P2) per spec.md. Within US1, tasks are further grouped by removal target, in the order fixed by the assignment (insights hub trio → interval templates → session builder → composer → upload widget → npm uninstall → routing-guard tests → validaLabel dedup), matching `contracts/removal-and-redirect-manifest.md`.

**Scope note**: This feature is frontend-only (`frontend/src/`). No backend files, no migrations, no `.specify/feature.json` changes. All paths below are relative to the repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 / US2 / US3 — present only on story-phase tasks (Setup/Foundational/Polish carry no story label)
- Every task names its exact file path(s)

---

## Phase 1: Setup (Safety Nets)

**Purpose**: Land the one safety-critical edit and re-confirm removal preconditions before anything is deleted.

- [ ] T001 Retarget the `/coach/race-analysis` redirect in `frontend/src/App.tsx` (~lines 664-670, the `<Navigate to="/competitions/insights" replace />` element) to `<Navigate to="/competitions" replace />`. This is the single real inbound pointer at the insights hub (research.md R1) — land this BEFORE any hub-trio deletion (Phase 3) so the address never dangles, even momentarily.
- [ ] T002 [P] Pre-removal grep safety net: run `grep -rin "konva" frontend/src` and confirm matches are confined to `frontend/src/components/technique/composer/` (plus the `frontend/src/App.tsx:130` comment); separately run `grep -rn "technique/composer\|technique/sessions/new\|intervals/templates\|components/ai/UploadZone" frontend/src` and confirm zero inbound references outside each target's own directory/tests/`App.tsx`. Re-confirms research.md R1 immediately before deletion begins; no file is edited by this task.

**Checkpoint**: The one live external redirect now points somewhere that survives every deletion in this feature; removal preconditions re-verified fresh.

---

## Phase 2: Foundational (SeasonInsightsPage Relocation) — BLOCKS User Story 1

**Purpose**: Relocate the one non-duplicated view out of `routes/competitions/insights/` before that directory's other three files are bulk-deleted in US1. Skipping this first would delete the surviving page along with the dead ones.

**⚠️ CRITICAL**: US1's directory-level deletion (T012) assumes `SeasonInsightsPage.tsx` and its test are already moved out. Complete this phase first.

- [ ] T003 Move `frontend/src/routes/competitions/insights/SeasonInsightsPage.tsx` to `frontend/src/routes/competitions/SeasonInsightsPage.tsx` (`git mv`; content unchanged). The route path stays `/competitions/insights/season/:year` — it is a literal string to React Router, not a nested hierarchy, so no redirect is needed (research.md R2).
- [ ] T004 In the relocated `frontend/src/routes/competitions/SeasonInsightsPage.tsx`, fix the back-link inside `HeaderBar` (`<Link to="/competitions/insights">`, ~line 30) to `to="/competitions"`. The old target is deleted later in US1 (T009-T012); without this fix the surviving page would self-break on its own back-link (research.md R2). Depends on T003 (same file).
- [ ] T005 In the relocated `frontend/src/routes/competitions/SeasonInsightsPage.tsx`, fix the row-click handler (~line 157, `` navigate(`/competitions/insights/athletes/${it.athlete_id}`) ``) to `` navigate(`/athletes/${it.athlete_id}?tab=ai_analysis`) ``, the surviving per-athlete analysis home (`AthleteAIAnalysisTab`, reached via `AthleteDetailPage`'s existing `ai_analysis` tab). Depends on T003 (same file as T004 — sequential, not parallel).
- [ ] T006 [P] Update the `SeasonInsightsPage` lazy import in `frontend/src/App.tsx` (~lines 49-51) from `import("@/routes/competitions/insights/SeasonInsightsPage")` to `import("@/routes/competitions/SeasonInsightsPage")`. The route element usage (~lines 632-646) is otherwise unchanged. Depends on T003; different file than T004/T005 so parallel with them.
- [ ] T007 [P] Add a "Panorama de temporada" secondary-action link to `frontend/src/routes/competitions/CompetitionsListPage.tsx`'s header action row (~lines 192-211, alongside the existing "Cargar resultados"/"Sin enlazar" links), pointing to `` `/competitions/insights/season/${currentSeason()}` `` using the `currentSeason()` helper from `frontend/src/lib/datetime.ts` (feature 028 R11 — do not hardcode a year; add a minimal `currentSeason(): number` there if 028 hasn't landed yet). Unlike its 44px-tall neighbors in this same row, size this new link ≥48×48 px per this feature's own touch-target constraint (plan.md Constraints). No dependency on T003-T006 — different file.
- [ ] T008 Move `frontend/src/routes/competitions/insights/__tests__/SeasonInsightsPage.test.tsx` to `frontend/src/routes/competitions/__tests__/SeasonInsightsPage.test.tsx`; update its import (~line 22) from `@/routes/competitions/insights/SeasonInsightsPage` to `@/routes/competitions/SeasonInsightsPage`; update the row-click assertion (~lines 66-69) from `expect(mockNavigate).toHaveBeenCalledWith("/competitions/insights/athletes/144")` to `expect(mockNavigate).toHaveBeenCalledWith("/athletes/144?tab=ai_analysis")`. Depends on T003-T005 (asserts the behavior they establish).

**Checkpoint**: `SeasonInsightsPage` now lives at its permanent path with both internal links fixed and a working entry point from Competencias. `frontend/src/routes/competitions/insights/` now contains only the three dead pages (`InsightsHubPage.tsx`, `ClubInsightsPage.tsx`, `AthleteInsightsPage.tsx`) plus their tests — safe to bulk-remove in US1.

---

## Phase 3: User Story 1 - Remove What Nobody Can Reach (Priority: P1) 🎯 MVP

**Goal**: Delete ~3,500 lines of confirmed-unreachable/duplicated presentation surface (gymkhana composer + its drawing dependencies, standalone technique session builder, standalone interval-template screen, duplicated cross-race AI hub trio, superseded upload widget) with zero coach-visible capability loss beyond the two explicitly-approved ones (composer; standalone technique-session-assembly path pending feature 032).

**Independent Test**: No coach screen is unreachable; the removed screens 404 via the catch-all; the season panorama opens from Competencias; `/coach/race-analysis` still resolves; `npm run build` shows no `konva` chunk and a smaller technique-area bundle.

### Insights hub trio (InsightsHubPage, ClubInsightsPage, AthleteInsightsPage)

- [ ] T009 [US1] Remove the 3 insights-hub-trio route blocks from `frontend/src/App.tsx`: `/competitions/insights` (~lines 578-593, `InsightsHubPage`), `/competitions/insights/club` (~lines 615-630, `ClubInsightsPage`), `/competitions/insights/athletes/:id` (~lines 647-662, `AthleteInsightsPage`); and their 3 lazy imports (~lines 37-41, ~lines 52-57). Leave the `/competitions/insights/season/:year` route (already retargeted to the relocated `SeasonInsightsPage` in T006) untouched.
- [ ] T010 [P] [US1] Delete the 3 now-orphaned page files: `frontend/src/routes/competitions/insights/InsightsHubPage.tsx`, `frontend/src/routes/competitions/insights/ClubInsightsPage.tsx`, `frontend/src/routes/competitions/insights/AthleteInsightsPage.tsx`. Depends on T009 (route/import removed first so `tsc` fails loudly on any missed reference, research.md R1).
- [ ] T011 [P] [US1] Delete their 3 test files: `frontend/src/routes/competitions/insights/__tests__/InsightsHubPage.test.tsx`, `ClubInsightsPage.test.tsx`, `AthleteInsightsPage.test.tsx` (travel with their source, research.md R5). Depends on T009; parallel with T010 — different files.
- [ ] T012 [US1] Remove the now-empty `frontend/src/routes/competitions/insights/` directory and its `__tests__/` subdirectory. Depends on T010, T011 (and on Foundational's T003/T008, which already moved the only survivors out).

### Interval template library

- [ ] T013 [US1] Remove the `/intervals/templates` route block (~lines 856-871) and its lazy import (~lines 173-177, `TemplateLibraryPage`) from `frontend/src/App.tsx`.
- [ ] T014 [P] [US1] Delete `frontend/src/routes/intervals/TemplateLibraryPage.tsx` and remove the now-empty `frontend/src/routes/intervals/` directory. Depends on T013. No dedicated test file exists for this page (research.md R5) — template browsing/attaching remains covered by `components/intervals/TemplatePicker.tsx`'s own tests, untouched by this feature.

### Technique session builder

- [ ] T015 [US1] Remove the `/technique/sessions/new` route block (~lines 705-720) and its lazy import (~lines 120-124, `SessionBuilderPage`) from `frontend/src/App.tsx`.
- [ ] T016 [P] [US1] Delete `frontend/src/routes/technique/SessionBuilderPage.tsx` and `frontend/src/components/technique/SessionAssembler.tsx`. Depends on T015.
- [ ] T017 [P] [US1] Delete test `frontend/src/components/technique/__tests__/SessionAssembler.test.tsx`. Depends on T015; parallel with T016 — different files.

### Gymkhana composer + drawing dependencies

- [ ] T018 [US1] Remove the `/technique/composer` route block (~lines 738-753) and its lazy import (~lines 131-135, `ComposerPage`) from `frontend/src/App.tsx`.
- [ ] T019 [P] [US1] Delete `frontend/src/routes/technique/ComposerPage.tsx`. Depends on T018.
- [ ] T020 [P] [US1] Delete the composer support files: `frontend/src/components/technique/composer/AccessibleControls.tsx`, `frontend/src/components/technique/composer/KonvaCanvas.tsx`, `frontend/src/components/technique/composer/piiGuard.ts`. Depends on T018; parallel with T019/T021 — different files.
- [ ] T021 [P] [US1] Delete the composer test files: `frontend/src/components/technique/composer/Composer.a11y.test.tsx`, `frontend/src/components/technique/composer/Composer.roundtrip.test.tsx`. Depends on T018; parallel with T019/T020.
- [ ] T022 [US1] Remove the now-empty `frontend/src/components/technique/composer/` directory. Depends on T019, T020, T021.

### Superseded upload widget

- [ ] T023 [P] [US1] Delete `frontend/src/components/ai/UploadZone.tsx` and its test `frontend/src/components/ai/__tests__/UploadZone.test.tsx`. Not routed; its only importer was its own test (research.md R1). Fully independent of every `App.tsx` edit above — no dependency.

### npm uninstall (konva, react-konva)

- [ ] T024 [US1] Run `npm uninstall konva react-konva` in `frontend/` (removes both lines from `frontend/package.json`'s `dependencies`). Depends on T020 and T022 — the only consumer (`KonvaCanvas.tsx`) and its directory must be gone first.
- [ ] T025 [US1] Verify the uninstall: `grep -rin "konva" frontend/src` returns zero hits; `grep -n "konva" frontend/package.json` returns zero hits. Depends on T024.

### Routing-guard test updates

- [ ] T026 [P] [US1] Update `frontend/src/__tests__/competitions-routing.test.tsx`: retarget the replica route-tree stub and assertions (~lines 90-93, 100-102, 177-181) that currently chase `/coach/race-analysis` → `/competitions/insights` → an `insights-hub` stand-in testid, so they chase `/coach/race-analysis` → `/competitions` instead. Depends on T009-T024 (asserts post-removal state); different file than T028/T029/T030 so parallel with them.
- [ ] T027 [US1] In the same `frontend/src/__tests__/competitions-routing.test.tsx`, update its existing "parent blocked" RBAC test block (labeled `T022` inside that file from a prior feature — unrelated to this tasks.md's own numbering — ~lines 230-343): swap its `/competitions/insights*` path literals (stubbed against its own `InsightsGuard`, not the real `ProtectedRoute`) for still-existing coach/admin-only paths (e.g. `/competitions`, `/technique`), so the RBAC-redirect coverage no longer references a dead route. Depends on T026 (same file — sequential).
- [ ] T028 [P] [US1] Update `frontend/src/__tests__/competitionsRedirects.test.tsx`: retarget its replica stub and assertions (~lines 31-34, 40-43, 54-58) from `/competitions/insights` to `/competitions`. Depends on T009-T024; parallel with T026/T029/T030 — different files.
- [ ] T029 [P] [US1] Update `frontend/src/__tests__/T049-wave-f-cleanup.test.tsx`: retarget its replica stub and assertions (~lines 108-111, 118-120, 136-144) from `/competitions/insights` to `/competitions`, and extend `REMOVED_MODULE_FRAGMENTS` (~lines 47-50) with `InsightsHubPage`, `ClubInsightsPage`, `AthleteInsightsPage`, `ComposerPage`, `SessionBuilderPage`, `SessionAssembler`, `TemplateLibraryPage`. Depends on T009-T024; parallel with T026/T028/T030.
- [ ] T030 [P] [US1] Verify `frontend/src/components/layout/__tests__/AppShell.test.tsx` still passes with zero source changes — its sidebar-link-absence assertions (~lines 118-146) already assert the insights link is NOT present, which remains true after removal (research.md R5: no change expected; this is a confirmation run, not an edit). Parallel with T026/T028/T029.

### validaLabel consolidation (research.md R6)

- [ ] T031 [P] [US1] Remove the private `validaLabel` helper (~lines 89-94) from `frontend/src/components/athletes/ai/AthleteAIAnalysisTab.tsx` and import the shared `validaLabel` from `frontend/src/lib/insights.ts` instead; update its one call site (~line 277, `validaLabel(latest.valida_num)`) to use the import, matching the shared version's fallback casing (`"—"` / `"Resumen de temporada"`) per data-model.md. No dependency on T009-T030 — different files entirely.
- [ ] T032 [P] [US1] Update the shared `validaLabel` docstring in `frontend/src/lib/insights.ts` (~line 107) to document it as the sole surviving implementation plus the legacy `=== 99` sentinel exception, per data-model.md's consolidated docstring. Self-contained prose change, independent of T031.
- [ ] T033 [US1] Update `frontend/src/components/athletes/ai/__tests__/AthleteAIAnalysisTab.test.tsx`'s valida-label assertions to expect the shared helper's fallback casing. Depends on T031 (same component's behavior change).

### Optional cosmetic + US1 checkpoint

- [ ] T034 [P] [US1] (Optional, low-priority) Update the default `to` prop in `frontend/src/routes/GonePage.tsx` (~line 14) from `/competitions/insights` to `/competitions`. Cosmetic — `GonePage` is wired into zero routes today either way (research.md R1). Independent of every other US1 task.
- [ ] T035 [US1] Run `npm run typecheck` and `npm run build` in `frontend/`; confirm zero "Cannot find module" errors for any path in `contracts/removal-and-redirect-manifest.md`'s removed-routes table, and confirm no `konva` chunk in the build (`grep -ril "konva" dist/assets` → no hits). Depends on T009-T034 — this is the US1 completion gate.

**Checkpoint**: User Story 1 is fully functional and independently testable. This is the MVP — ~3,500 LOC and 2 runtime dependencies removed, 0 unreachable screens remain, every previously-shared address still resolves.

---

## Phase 4: User Story 2 - The Athlete Profile Is the One Place for Athlete Information (Priority: P2)

**Goal**: Consolidate technique-skill and strength progress under one "Progreso" tab on the athlete profile (internal Técnica/Fuerza toggle, profile stays at 7 top-level sections), with a wellbeing pointer into the anxiety module that preselects the athlete.

**Independent Test**: From an athlete's profile, open technique progress, strength progress, and the anxiety view (athlete preselected) without typing a URL; the profile does not exceed 7 sections.

**Note on dependencies**: This story touches `AthleteDetailPage.tsx`, `AnxietyDashboardPage.tsx`, and the two `AthleteProgressPage.tsx` files/routes — none of which overlap with Foundational's relocated files (`SeasonInsightsPage.tsx`, `CompetitionsListPage.tsx`) or with US1's removal targets (different `App.tsx` route blocks, different directories). It can start immediately after Setup and run in parallel with Foundational/US1 if staffed separately; a solo executor simply follows the numbering below.

- [ ] T036 [US2] Add `"progreso"` to the `Tab` union type (~line 53) and `VALID_TABS` array (~lines 55-62) in `frontend/src/routes/athletes/AthleteDetailPage.tsx`, per `contracts/progreso-tab.md`'s tab registration (6 values become 7 — the SC-005 ceiling).
- [ ] T037 [US2] Add a "Progreso" tab button to the tab row in `frontend/src/routes/athletes/AthleteDetailPage.tsx` (appended after "Actividades", near the ~line 628 `updateTab("activities")` button), always rendered (unlike the conditional "Crecimiento" tab). Depends on T036 (same file).
- [ ] T038 [US2] Implement `ProgresoTabPanel` in `frontend/src/routes/athletes/AthleteDetailPage.tsx` (or a co-located component file): a `ToggleGroup`/`ToggleGroupItem` (from `frontend/src/components/ui/toggle-group.tsx`) with "Técnica" (default)/"Fuerza" options, backed by local `useState<"tecnica" | "fuerza">("tecnica")`, NOT URL-synced, per `contracts/progreso-tab.md`. Depends on T036 (same file).
- [ ] T039 [US2] Wire the two boards into `ProgresoTabPanel`: lazy-load `SkillProgressBoard` (`frontend/src/components/technique/SkillProgressBoard.tsx`, via `useAthleteSkillProgress(athleteId)`) under "Técnica", and `ProgressNotesBoard` (`frontend/src/components/strength/ProgressNotesBoard.tsx`, via `useAthleteStrengthProgress(athleteId)`) under "Fuerza", each wrapped in `Suspense` with a `BoardSkeleton` fallback — reuse the exact lazy-import pattern currently in `frontend/src/routes/technique/AthleteProgressPage.tsx` / `frontend/src/routes/strength/AthleteProgressPage.tsx` (both deleted in T043) before it disappears. Depends on T038 (same file).
- [ ] T040 [US2] Add the wellbeing pointer inside `ProgresoTabPanel`: `<Link to={`/anxiety?athlete=${athleteId}`}>Ver ansiedad competitiva</Link>`, always rendered per `contracts/progreso-tab.md`. Depends on T038/T039 (same file).
- [ ] T041 [US2] Remove the `/technique/athletes/:athleteId/progress` route block (`App.tsx:721-736`, research.md R3) and its `AthleteProgressPage` lazy import (~lines 125-129) from `frontend/src/App.tsx`. Depends on T040 — the Progreso tab must be the new home before the old one is removed.
- [ ] T042 [US2] Remove the `/strength/athletes/:athleteId/progress` route block (`App.tsx:820-835`, research.md R3) and its `StrengthAthleteProgressPage` lazy import (~lines 153-157) from `frontend/src/App.tsx`. Same file as T041 — sequential.
- [ ] T043 [P] [US2] Delete `frontend/src/routes/technique/AthleteProgressPage.tsx` and `frontend/src/routes/strength/AthleteProgressPage.tsx`. Depends on T041, T042.
- [ ] T044 [P] [US2] Delete test `frontend/src/routes/strength/__tests__/AthleteProgressPage.test.tsx` — its meaningful assertions are already covered by the untouched `frontend/src/components/strength/__tests__/ProgressNotesBoard.test.tsx` (research.md R5); no dedicated test exists for the technique page. Depends on T042; parallel with T043 — different files.
- [ ] T045 [P] [US2] Add `useSearchParams` (`react-router-dom`) to `frontend/src/routes/anxiety/AnxietyDashboardPage.tsx`: read `?athlete=`, and default `tab` (~line 25, `useState<Tab>("crear")`) to `"individual"` when the parsed athlete id is > 0, else keep `"crear"`, per `contracts/progreso-tab.md`'s `AnxietyDashboardPage` receiving-end contract. Independent of the `AthleteDetailPage.tsx` thread (T036-T040) — different file.
- [ ] T046 [US2] Seed `IndividualTab`'s (~line 68) local `athleteId`/`submittedId` state from the URL `athlete` param on mount, so `useAthleteSeries` (~lines 69-72) fires without the coach re-selecting from the dropdown. Depends on T045 (same file).
- [ ] T047 [P] [US2] Update `frontend/src/routes/athletes/AthleteDetailPage.test.tsx`: add/adjust the tab-count assertion (now 7 tabs) and a tab-button assertion for "Progreso". Depends on T036-T040.
- [ ] T048 [P] [US2] Add new test file `frontend/src/routes/athletes/AthleteDetailPage.progreso.test.tsx`, following the existing `AthleteDetailPage.strava.test.tsx` per-tab convention: covers the Técnica default view, switching to Fuerza, the wellbeing pointer's `href`, and a `jest-axe` check scoped to the Progreso tab panel (satisfies plan.md's Constitution Check row II, "jest-axe re-run on AthleteDetailPage"). Depends on T036-T040; parallel with T047/T049 — different files.
- [ ] T049 [P] [US2] Add new test file `frontend/src/routes/anxiety/__tests__/AnxietyDashboardPage.test.tsx` (new `__tests__/` directory — none exists today): covers default tab `"crear"` with no query param, default tab `"individual"` with `?athlete=42`, `IndividualTab` pre-seeding its athlete selection from the URL, and a `jest-axe` check. Depends on T045-T046; parallel with T047/T048.

**Checkpoint**: User Story 2 is fully functional and independently testable. Technique and strength progress are reachable from the athlete profile's Progreso tab in 2 interactions (profile → Progreso tab → toggle); the two standalone progress screens are gone; the wellbeing pointer preselects the athlete in the anxiety view.

---

## Phase 5: User Story 3 - Finish the Half-Built Anxiety Interpretation (Priority: P2)

**Goal**: Wire the already-built, already-tested on-demand interpretation (`AnalyzeButton` + `InterpretationPanel`) into `IndividualPanel.tsx`, gated on `latest.cognitive !== null`. No backend change.

**Independent Test**: As coach, open a consented athlete's completed assessment in the individual anxiety view, request the interpretation, and verify baseline-anchored wording, no diagnostic labels, coach-only visibility, and a graceful rule-based fallback when the AI service is unavailable.

**Known, named scope boundary (carried into this phase, not silently assumed away)**: guardian consent for `psychological_assessment` is enforced by the backend only at assessment creation; nothing in the read/interpret path re-checks it today, and FR-009 explicitly forbids this feature from adding a server-side re-check. The "Consent-blocked" test below (T058) exercises the existing, already-written `mapAnxietyError` 409 mapping defensively/forward-compatibly — it does not close the mid-session-revocation gap, which remains an explicitly out-of-scope fast-follow per `contracts/anxiety-interpretation-ui.md`.

**Note on dependencies**: This story touches exactly `components/anxiety/IndividualPanel.tsx` and its test — no file overlap with Foundational, US1, or US2. Fully independent; can start immediately after Setup.

- [ ] T050 [US3] In `frontend/src/components/anxiety/IndividualPanel.tsx`, import `AnalyzeButton` (`./AnalyzeButton`) and `InterpretationPanel` (`./InterpretationPanel`), add `useState` to the existing `react` import (~line 1), and add local state `const [result, setResult] = useState<InterpretationResponse | null>(null)` (import `InterpretationResponse` from `@/types/anxiety.types`).
- [ ] T051 [US3] Render `<AnalyzeButton assessmentId={latest.assessment_id} onAnalyzed={setResult} />` in `frontend/src/components/anxiety/IndividualPanel.tsx`, gated on `latest !== null && latest.cognitive !== null` (the "Not interpretable" gate from `contracts/anxiety-interpretation-ui.md` — the button must not render at all, not merely be disabled), mounted beneath the flags block (~line 83, after the `{flags.length > 0 && (...)}` block, before the closing `</section>`). Depends on T050 (same file).
- [ ] T052 [US3] Render `{result && <InterpretationPanel interpretation={result.interpretation} source={result.source} />}` beneath `AnalyzeButton` in `frontend/src/components/anxiety/IndividualPanel.tsx`, covering both `source: "llm"` ("IA" badge) and `source: "rule"` ("Reglas" badge — the graceful-degradation success state, never rendered as an error). Depends on T051 (same file).
- [ ] T053 [US3] Update `frontend/src/components/anxiety/__tests__/IndividualPanel.test.tsx`: replace all 5 existing `render(<IndividualPanel series={SERIES} />)` calls (~lines 71, 81, 88, 97, 102) with `renderWithProviders(<IndividualPanel series={SERIES} />)` (import from `@/test/helpers/renderWithProviders`, the same helper already used by the sibling `SeasonInsightsPage.test.tsx`) — required now that `AnalyzeButton`'s `useInterpretation` calls `useMutation` and needs a `QueryClientProvider` in the tree. Depends on T050-T052.
- [ ] T054 [US3] Add a test to `frontend/src/components/anxiety/__tests__/IndividualPanel.test.tsx`: `AnalyzeButton` ("Analizar con IA") renders when `latest.cognitive !== null`, and does NOT render (not merely disabled) when `series.points` is empty or the latest point's `cognitive` is `null` — the "Not interpretable" state. Depends on T053 (same file — sequential with T055-T059).
- [ ] T055 [US3] Add a test to the same file: clicking `AnalyzeButton` shows the loading state (button disabled, label "Analizando… (puede tardar)", cold-start helper text visible) before the mocked `POST .../interpret` call resolves. Mock `interpretAssessment` from `@/api/anxiety` (or MSW) with a controllable/delayed promise. Depends on T054.
- [ ] T056 [US3] Add a test to the same file: a successful interpretation with `source: "llm"` renders `InterpretationPanel` with the "IA" badge and its `resumen`/`por_dimension`/`estrategias`/`mensaje_para_el_atleta` content, per the Success (LLM) row of `contracts/anxiety-interpretation-ui.md`. Depends on T055.
- [ ] T057 [US3] Add a test to the same file: a successful interpretation with `source: "rule"` renders `InterpretationPanel` with the "Reglas" badge (`title="Generada por reglas (respaldo)"`) — asserted as a normal success render, not an error banner. Depends on T056.
- [ ] T058 [US3] Add a test to the same file: a rejected mutation mocking a 409 response renders the existing `COPY.consent_missing` text via `AnalyzeButton`'s `role="alert"` error path — forward-compatible "Consent-blocked" coverage per `contracts/anxiety-interpretation-ui.md`'s Known Limitation (the backend does not return 409 from `/interpret` today; this proves the frontend already handles it correctly for when it does). Depends on T057.
- [ ] T059 [US3] Extend the existing `jest-axe` check (or add a new one) in the same file, confirming zero violations with `AnalyzeButton` and a rendered `InterpretationPanel` both mounted — satisfies plan.md's Constitution Check row II, "jest-axe re-run on ... IndividualPanel". Depends on T058.

**Checkpoint**: User Story 3 is fully functional and independently testable. The on-demand anxiety interpretation is reachable for any consented athlete with a completed assessment; every Principle V safeguard (coach-only, no diagnostic labels, baseline-anchored, mastery climate, rule-based fallback, human-in-the-loop) is preserved verbatim since no server code changed.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify the feature's measurable outcomes (SC-001 through SC-007) holistically, across all three stories.

- [ ] T060 [P] Run `npm run build` in `frontend/`; compare the built bundle against a pre-feature baseline and confirm: no `konva`/`react-konva` chunk (`grep -ril "konva" dist/assets` → no hits), the technique-area chunk shrinks (composer + session-builder removed), and no route's initial chunk grows (SC-001, SC-007).
- [ ] T061 [P] Run the full frontend suite (`cd frontend && npm test`) and the backend regression suite (`cd backend && pytest`) — both must be green. The backend run is regression-only, confirming the untouched `technique`/`strength`/`anxiety` endpoints still pass (no backend code changed by this feature).
- [ ] T062 Execute quickstart.md's 5 manual scenarios end-to-end: (1) old bookmarks/shared links still resolve (`/coach/race-analysis` → `/competitions`; each removed route → `NotFoundPage`); (2) season panorama reachable from Competencias with both internal links fixed; (3) Progreso tab shows exactly 7 top-level tabs with a working Técnica/Fuerza toggle and wellbeing pointer; (4) anxiety interpretation renders for both `source: "llm"` and `source: "rule"`, under 60 seconds end-to-end, and the not-interpretable gate holds; (5) no-capability-loss sweep (interval templates from session detail, per-válida AI insights from `CompetitionDetailPage`'s Insights IA tab, per-athlete AI analysis from the profile's Análisis IA tab, season panorama from Competencias, session-planning/exercise-catalog flows unaffected).
- [ ] T063 Capability-loss audit: walk `contracts/removal-and-redirect-manifest.md`'s removed-routes table and its "Capability-loss check (FR-010)" section row by row, confirming each row's stated surviving home is genuinely reachable, and that the only two capability losses are the explicitly-approved ones (gymkhana composer's drawing capability, decision D1; the standalone technique-session-assembly path pending feature 032, decision D4). Record this sweep as the final SC-002/SC-003/FR-010 sign-off.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001-T002)**: No dependencies — start immediately.
- **Foundational (T003-T008)**: Depends on Setup. **BLOCKS User Story 1** — `routes/competitions/insights/` cannot be bulk-deleted (T012) until `SeasonInsightsPage` and its test are relocated out (T003, T008); deleting the directory first would take the sole surviving view down with the dead ones.
- **User Story 1 (T009-T035)**: Depends on Foundational completing.
- **User Story 2 (T036-T049)**: Depends only on Setup. Does **not** depend on Foundational's relocation (`AthleteDetailPage.tsx`, `AnxietyDashboardPage.tsx`, the two `AthleteProgressPage.tsx` files never reference `SeasonInsightsPage.tsx`/`CompetitionsListPage.tsx`) and does not depend on US1's deletions (different `App.tsx` route blocks, different directories). Parallelizable with Foundational and US1 if staffed separately.
- **User Story 3 (T050-T059)**: Depends only on Setup. Touches exactly `components/anxiety/IndividualPanel.tsx` and its test — zero file overlap with Foundational, US1, or US2. Fully independent.
- **Polish (T060-T063)**: Depends on every story being shipped that the team wants verified — at minimum Setup+Foundational+US1 for the bundle checks (T060); T062's manual sweep exercises US2/US3 acceptance scenarios too, so a full Polish pass presumes all three stories are done.

### Within-Phase Notes

- All `frontend/src/App.tsx` edits within a phase are mutually sequential (same file): T009/T013/T015/T018 in US1; T041/T042 in US2. This is a file-sharing constraint, not a functional-ordering one — the four US1 route removals are independent of each other in principle.
- Test-file edits that land on the same file are sequential with each other even when marked otherwise-parallel-eligible: T026→T027 (`competitions-routing.test.tsx`), and the whole T053→T054→T055→T056→T057→T058→T059 chain (`IndividualPanel.test.tsx`).
- Cross-target file deletions (e.g., composer files vs. session-builder files) are parallel once each target's own preceding `App.tsx` edit has landed.

### Parallel Examples (real task IDs)

```bash
# Foundational — different files, both depend only on T003:
Task: "T006 [P] Update SeasonInsightsPage lazy import path in frontend/src/App.tsx"
Task: "T007 [P] Add 'Panorama de temporada' link to frontend/src/routes/competitions/CompetitionsListPage.tsx"

# US1 — composer support files vs. composer test files, both depend only on T018:
Task: "T020 [P] Delete AccessibleControls.tsx, KonvaCanvas.tsx, piiGuard.ts"
Task: "T021 [P] Delete Composer.a11y.test.tsx, Composer.roundtrip.test.tsx"

# US1 — four independent routing-guard/dedup files:
Task: "T026 [P] Update competitions-routing.test.tsx main redirect stub"
Task: "T028 [P] Update competitionsRedirects.test.tsx"
Task: "T029 [P] Update T049-wave-f-cleanup.test.tsx"
Task: "T031 [P] Remove private validaLabel from AthleteAIAnalysisTab.tsx"

# US2 — three independent new/updated test files:
Task: "T047 [P] Update AthleteDetailPage.test.tsx tab-count assertions"
Task: "T048 [P] Add AthleteDetailPage.progreso.test.tsx"
Task: "T049 [P] Add AnxietyDashboardPage.test.tsx"

# Cross-story — US2 and US3 touch entirely disjoint files; either can run alongside US1 after Foundational/Setup respectively:
Task: "T036 [US2] Add progreso to Tab union in AthleteDetailPage.tsx"
Task: "T050 [US3] Import AnalyzeButton/InterpretationPanel in IndividualPanel.tsx"
```

---

## Implementation Strategy

### MVP First (Setup + Foundational + US1)

1. Complete Setup (T001-T002) — redirect safety net + grep audit.
2. Complete Foundational (T003-T008) — relocate the one survivor.
3. Complete US1 (T009-T035) — the subtraction itself: ~3,500 LOC and 2 dependencies removed, 0 unreachable screens remain among what's left.
4. **STOP and VALIDATE**: T035's typecheck/build gate, plus quickstart.md scenarios 1, 2, and 5.
5. This is the MVP. It is independently shippable and delivers SC-001, SC-002, SC-003, and SC-007 on its own.

### Incremental Delivery

6. Add US2 (T036-T049) — Progreso tab consolidation. Validate independently via quickstart.md scenario 3. Ships SC-004/SC-005.
7. Add US3 (T050-T059) — anxiety interpretation wiring. Validate independently via quickstart.md scenario 4. Ships SC-006.
8. Finish with Polish (T060-T063) — bundle verification, full quickstart sweep, capability-loss sign-off.

### Parallel Team Strategy

With multiple developers, after Setup completes:

- **Developer A**: Foundational → US1 (the critical path; US1 needs Foundational first).
- **Developer B**: US2 — independent of Foundational/US1 per the file-overlap analysis above.
- **Developer C**: US3 — fully independent of every other phase.
- All three converge at Polish.

---

## Notes

- `[P]` tasks touch different files and have no dependency on an incomplete task — verified individually above, not assumed.
- `[Story]` labels map every Phase 3-5 task to US1/US2/US3 for traceability; Setup, Foundational, and Polish carry no story label by design.
- No task in this feature touches `backend/`, any Alembic migration, or `.specify/feature.json`.
- Every deletion task is preceded by the `App.tsx` route/import removal that makes it safe (research.md R1's "fail loudly" ordering) — do not reorder within a target's own cluster.
- Stop at any checkpoint to validate a story independently before continuing.
