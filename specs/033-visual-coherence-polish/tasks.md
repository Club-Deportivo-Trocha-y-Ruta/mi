---

description: "Task list template for feature implementation"
---

# Tasks: Visual Coherence & Polish

**Input**: Design documents from `/home/user/mi/specs/033-visual-coherence-polish/`

**Prerequisites**: plan.md (required, read), spec.md (required, read), research.md (R1–R8, read), data-model.md (read), contracts/status-vocabulary-sweep.md, contracts/chart-style.md, contracts/ai-identity.md, contracts/dark-theme-tokens.md (all read), quickstart.md (read), `.specify/memory/constitution.md` (read). **Hard cross-feature prerequisite**: `specs/028-frontend-design-foundation` (`StatusBadge.tsx`, `PageHeader`/shared-component kit, `--color-success/-warning/-danger` tokens, shadow/token consolidation) MUST already be merged — as of this writing neither exists in `frontend/src/components/shared/` or `frontend/src/style.css`, and every task below that consumes them assumes they have landed first. See **Dependencies & Execution Order** for the full cross-feature map (029/030/032).

**Tests**: INCLUDED. Constitution II (NON-NEGOTIABLE) and this feature's `plan.md`/`quickstart.md` mandate `vitest`/`jest-axe`/`pytest` coverage for every renamed label, every status adapter, the chart regression set, the new endpoint, and dark-mode contrast (if US5 ships). Test tasks are woven into each implementation task where 1:1 (e.g. "extract adapter + test"), plus dedicated cross-cutting test tasks where a check spans multiple files (regression grep, jest-axe sweeps, palette validation).

**Organization**: Tasks are grouped by user story (spec.md priorities: US1=P1, US2=P2, US3=P2, US4=P2, US5=P3 optional) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1–US5); Setup/Foundational/Polish carry no story label
- Every task names its exact file path(s) — this is a presentation-only sweep over existing files, no new top-level directories

## Path Conventions

Existing web-app monorepo, unchanged by this feature (`plan.md` Structure Decision):

- **Backend**: `backend/app/routers/`, `backend/app/schemas/`, `backend/app/services/race/ai/`, `backend/tests/routers/`
- **Frontend**: `frontend/src/components/`, `frontend/src/routes/`, `frontend/src/lib/`, `frontend/src/hooks/`, `frontend/src/api/`; tests are co-located either as `Component.test.tsx` beside the component or under a sibling `__tests__/` directory — each task below follows whichever convention the target file already uses
- **Docs**: `docs/05-design-system/design.md` (Polish only)
- Zero new runtime dependencies anywhere (chart table-toggle reuses `ui/tabs.tsx`; shortcuts help reuses `ui/dialog.tsx`; dark mode is CSS-only)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Register the new design tokens this feature introduces, and stand up the backend scaffold for the one new endpoint.

- [ ] T001 [P] Add the validated A/B/C ordinal ramp tokens (`--color-tier-c: #5bc6d5`, `--color-tier-b: #1cb5c7`, `--color-tier-a: #008492`, one hue/monotone lightness per `research.md` R2 and `data-model.md` §2) to both token blocks (`:root` and `@theme`) in `frontend/src/style.css`; also add `--color-success`/`--color-warning`/`--color-danger` (`#0ca30c`/`#fab219`/`#d03b3b`) to the same two blocks **only if not already present** from `specs/028-frontend-design-foundation` (defensive — this feature consumes these tokens but does not own them long-term)
- [ ] T002 [P] Vendor the `dataviz` skill's `validate_palette.js` `validate()`/`validateOrdinal()` logic into the repo as a CI-runnable module (e.g. `frontend/scripts/validate-palette.mjs`, importable from both a Node CLI invocation and a `vitest` test) so the chart palette and A/B/C ramp can be re-validated automatically instead of eyeballed, per `research.md` R2/R3
- [ ] T003 [P] Scaffold `GET /api/ai/status`: add the `AIStatusResponse` schema (`budget_status: Literal["ok","warning","exhausted"]`, `budget_remaining_pct: int`, `concurrency_available: bool`, `est_wait_seconds: int`) to `backend/app/schemas/ai.py`, and register the route in `backend/app/routers/ai.py` gated on the existing `_coach_or_admin` dependency pattern (mirrors `ai_health`'s `@router.get("/health", ...)` shape), returning a placeholder body — full computation lands in Foundational (T004)

**Checkpoint**: Tokens exist; the new endpoint's shape and RBAC are wired but not yet computing real values.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure every user story either directly needs (AI status endpoint/hook) or is blocked on (the `StatusBadge` domain-adapter layer). No US1/US2/US3/US4 rendering task may start before this phase completes.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete. This phase itself assumes `specs/028-frontend-design-foundation`'s `StatusBadge.tsx` and design tokens are already merged (see header note) — the adapters below produce `{status, label, icon?}` values for a component that must already exist.

- [ ] T004 Implement the real `GET /api/ai/status` computation in `backend/app/routers/ai.py` (completes the `AIStatusResponse` scaffold from T003): `budget_remaining_pct = round(max(0, 1 - current_usd_30d/race_ai_budget_usd_30d) * 100)` reusing `_sum_cost_last_30d()` and `settings.race_ai_budget_usd_30d` from `backend/app/services/race/ai/budget_guard.py`; `budget_status` = `"exhausted"` iff `budget_remaining_pct <= 0` (identical trigger to `check_budget()`'s `BudgetExceededError`), `"warning"` iff `< 20`, else `"ok"`; `concurrency_available` = direct read of `has_capacity()` from `backend/app/services/race/ai/runner.py`; `est_wait_seconds` = the same `latency_ms_p50` computation `admin_ai_usage()` performs in `backend/app/routers/race_analysis.py` (~line 1431), scoped to a short recent window, `ms → s`, rounded
- [ ] T005 [P] Add `backend/tests/routers/test_ai_status.py`: happy path asserting `ok`/`warning`/`exhausted` from seeded 30-day cost sums; RBAC-negative (parent role → 403, admin/coach → 200); a property test asserting `budget_status == "exhausted"` if-and-only-if a subsequent real launch attempt would 503 (keeps the hint and the hard block from drifting apart — the load-bearing regression test for SC-004); assert the response body carries no athlete identifiers
- [ ] T006 [P] Add `getAIStatus()` to `frontend/src/api/ai.ts` and `frontend/src/hooks/ai/useAIStatus.ts` (TanStack Query, key `["ai-status"]`, `staleTime` 30s, mirrors the existing `frontend/src/hooks/ai/useAIHealth.ts` pattern) plus `frontend/src/hooks/ai/useAIStatus.test.ts` (happy path + graceful degradation when the fetch fails — must never block the launch button it feeds)
- [ ] T007 [P] Status adapter 1/8 — `frontend/src/components/activities/ConnectionStatusBadge.tsx`: extract a pure `connectionStatus(state)` adapter (`none→neutral "Sin conectar"`, `active→success "Conectado"`, `broken→warning "Conexión rota"`, `disconnected→neutral "Desconectado"`) alongside the component, keeping its existing icon choices; add a full-state-table `vitest` test in `frontend/src/components/activities/ConnectionStatusBadge.test.tsx`
- [ ] T008 [P] Status adapter 2/8 — `frontend/src/components/competitions/CompetitionStatusBadges.tsx`: extract 3 pure adapters — `resultadosStatus(has_results)`, `calendarioStatus(has_calendar_event)`, `condicionesStatus(state)` (`none/partial/complete`) per `contracts/status-vocabulary-sweep.md` §2 — alongside the component; add/extend the `vitest` table test in `frontend/src/components/competitions/__tests__/CompetitionStatusBadges.test.tsx`
- [ ] T009 [P] Status adapter 3/8 — `frontend/src/components/training/SessionStatusBadge.tsx`: extract a pure `sessionStatus(state)` adapter (`planned→neutral`, `executed→success`, `cancelled→danger`) alongside the still-unchanged hand-rolled component body (body rewrite happens in US1/T018); add the table test in `frontend/src/components/training/SessionStatusBadge.test.tsx`
- [ ] T010 [P] Status adapter 4/8 — `frontend/src/lib/insights.ts`: rename `confidenceVariant`/`confidenceLabel` into a single canonical `confidenceStatus(confidence)` adapter returning `{status, label}` for `high/medium/low` per `contracts/status-vocabulary-sweep.md` §4; update/extend `frontend/src/lib/__tests__/insights.test.ts` — this is the canonical version; `AthleteAIAnalysisTab.tsx`'s verbatim duplicate is deleted in US1 (T019), not here
- [ ] T011 [P] Status adapter 5/8 — `frontend/src/routes/training/AthleteNewslettersDashboardPage.tsx`: extract a pure `newsletterStatus(status)` adapter (`none/draft/approved/sent/failed`, `approved`+`sent` both `success`, differentiated only by label) alongside the still-unchanged `STATUS_CONFIG`/span rendering (rewrite happens in US1/T020); add/extend the test in `frontend/src/routes/training/AthleteNewslettersDashboardPage.test.tsx`
- [ ] T012 [P] Status adapter 6/8 — `frontend/src/components/consent/ConsentStatusPanel.tsx`: extract two pure adapters — `consentStatus(state)` (`never/outdated/revoked/current`) and `aiConsentStatus(isActive)` (`not authorized→neutral`, `authorized→success`) per `contracts/status-vocabulary-sweep.md` §6; add/extend the test in `frontend/src/components/consent/ConsentStatusPanel.test.tsx`
- [ ] T013 [P] Status adapter 7/8 — `frontend/src/components/competitions/insights/StaleAnalysisBadge.tsx`: extract a pure `staleAnalysisStatus()` adapter (`stale→warning "Análisis desactualizado"`) alongside the still-unchanged hand-colored badge (rewrite happens in US1/T022); add/extend the test in `frontend/src/components/competitions/insights/__tests__/StaleAnalysisBadge.test.tsx`
- [ ] T014 [P] Status adapter 8/8 — `frontend/src/components/competitions/insights/GroupRunRow.tsx`: extract a pure `groupRunStatus(runState, outcome)` adapter covering every terminal state (`already_running→neutral`, `backpressure→warning`, `error/no_results/budget_exceeded→danger`, `hitl_waiting→warning`, `done→success`, `failed→danger`, `cancelled→neutral`) per `contracts/status-vocabulary-sweep.md` §8, alongside the still-unchanged `StateChip` (deletion happens in US1/T023); add/extend the test in `frontend/src/components/competitions/insights/__tests__/GroupAnalysisPanel.test.tsx`

**Checkpoint**: Foundation ready — the AI-status read model and every status-domain adapter exist and are unit-tested; US1/US2/US3 rendering work can now begin in parallel, and US4 has the hook it needs.

---

## Phase 3: User Story 1 - One meaning per color, everywhere (Priority: P1) 🎯 MVP

**Goal**: Every status presentation in the coach app — sync, session, consent, analysis freshness, newsletter, group-run, chart reference — uses the shared `success/warning/danger/neutral` vocabulary with icon+label, never color alone; A/B/C race classes read as an ordered intensity scale, never as status colors.

**Independent Test**: Inventory every status presentation across coach modules: each maps to the shared vocabulary, pairs color with icon/label, and no color is used with a conflicting meaning anywhere; A/B/C badges read as an ordered ramp; the same state shown in two modules (e.g. "outdated" vs "stale") renders identically in color/shape/icon placement.

### Implementation for User Story 1

- [ ] T015 [P] [US1] Fix the race-class ordinal presentation in `frontend/src/lib/insights.ts`: `CARRERA_TIER`/`getCarreraTier` must map `"CD"` (Campeonato Departamental) to tier `"A"` instead of a 4th distinct value (its real tapering intensity per the Copa Valle calendar); render the A/B/C badge using the ordinal ramp tokens from T001 (`--color-tier-a/-b/-c`) with the visible `A`/`B`/`C` letter always as text, never a bare colored dot; verify `frontend/src/routes/competitions/CompetitionDetailPage.tsx`'s separate trophy badge (~line 452-460, amber "CD" pill + `Trophy` icon) is unaffected; update `frontend/src/lib/__tests__/insights.test.ts`
- [ ] T016 [P] [US1] Migrate `frontend/src/components/activities/ConnectionStatusBadge.tsx` to render `<StatusBadge>` via `connectionStatus()` (T007); remove the local `STATUS_CONFIG` map and `<Badge variant>` plumbing; update `ConnectionStatusBadge.test.tsx`
- [ ] T017 [P] [US1] Migrate `frontend/src/components/competitions/CompetitionStatusBadges.tsx`'s three sub-badges (resultados/calendario/condiciones) to `<StatusBadge>` via the adapters from T008; keep the existing `Tooltip` wrapper around each badge unchanged; update `frontend/src/components/competitions/__tests__/CompetitionStatusBadges.test.tsx`
- [ ] T018 [P] [US1] Rewrite `frontend/src/components/training/SessionStatusBadge.tsx` to render `<StatusBadge>` via `sessionStatus()` (T009), deleting the hand-rolled `<span className=...>`; add a regression assertion in `SessionStatusBadge.test.tsx` that no raw status `<span>` renders
- [ ] T019 [P] [US1] Delete the duplicate `confidenceBadgeVariant`/`confidenceText` block in `frontend/src/components/athletes/ai/AthleteAIAnalysisTab.tsx` (~lines 75-87); import the canonical `confidenceStatus()` from `frontend/src/lib/insights.ts` (T010) at every call site in the file; update `frontend/src/components/athletes/ai/__tests__/AthleteAIAnalysisTab.test.tsx`
- [ ] T020 [P] [US1] Replace the hand-rolled `badgeClass`/raw `<span>` (~lines 162-167) in `frontend/src/routes/training/AthleteNewslettersDashboardPage.tsx` with `<StatusBadge>` via `newsletterStatus()` (T011); add a regression assertion that no raw status span renders; update `AthleteNewslettersDashboardPage.test.tsx`
- [ ] T021 [P] [US1] Migrate `frontend/src/components/consent/ConsentStatusPanel.tsx`'s `STATE_CONFIG` block (~52-76) and the embedded `AiConsentRow` pill (~187-250) to `<StatusBadge>` via `consentStatus()`/`aiConsentStatus()` (T012); no behavior change to the renew/revoke/toggle actions themselves; update `ConsentStatusPanel.test.tsx`
- [ ] T022 [P] [US1] Replace the hand-colored `<Badge variant="secondary" className="bg-amber-100 text-amber-800">` in `frontend/src/components/competitions/insights/StaleAnalysisBadge.tsx` (~43-49) with `<StatusBadge status="warning">` via `staleAnalysisStatus()` (T013); keep the adjacent "Re-ejecutar" `Button` unchanged; update `frontend/src/components/competitions/insights/__tests__/StaleAnalysisBadge.test.tsx`
- [ ] T023 [P] [US1] Delete the `StateChip` implementation (~34-149) in `frontend/src/components/competitions/insights/GroupRunRow.tsx`; render `<StatusBadge>` via `groupRunStatus()` (T014) for every terminal state (`already_running/backpressure/error/no_results/budget_exceeded/done/failed/hitl_waiting/cancelled`); leave the "in progress" branches (`running`, launch outcome `started`/`recovered`) exactly as they render today — they are replaced by the compact `AnalysisRunTimeline` in US4/T050, not here; update `frontend/src/components/competitions/insights/__tests__/GroupAnalysisPanel.test.tsx`
- [ ] T024 [US1] Add a `jest-axe` pass across all 8 migrated badge components (T016–T023) confirming zero violations and that icon+label pairing is present on every status render (never color-alone)
- [ ] T025 [US1] Add a cross-module consistency regression test asserting the "outdated" (`ConsentStatusPanel`, T021) and "stale" (`StaleAnalysisBadge`, T022) states render `StatusBadge` with identical color/shape/icon-placement, differing only in label text (spec.md acceptance scenario 3)

**Checkpoint**: At this point, one color vocabulary applies everywhere in the coach app — User Story 1 is fully functional and independently testable. This is the MVP.

---

## Phase 4: User Story 2 - Charts that read correctly (Priority: P2)

**Goal**: `DistributionChart`/`EvolutionChart` use solid hairline grids, the accent for the athlete's own series, shared status colors for best/worst, an on-point championship marker, capped reference labels, the preserved small-sample table fallback, and a table view for the main chart data.

**Independent Test**: Render both charts across data shapes (normal field, 10-15-rider field, small sample, championship present): verify grid style, color roles, on-point championship marking, label capping, table fallback, and the new table view.

### Implementation for User Story 2

- [ ] T026 [P] [US2] Restyle `frontend/src/components/athletes/ai/DistributionChart.tsx` per `contracts/chart-style.md`: remove `strokeDasharray="3 3"` on `<CartesianGrid>` (~line 304); replace the one-off axis-ink `#5a6172` with `--color-mid-gray` on every `XAxis`/`YAxis` tick/label (~309,315,320,327); replace the self/best/worst/other-rider colors with `--color-primary`/`--color-success`/`--color-danger`/`--color-mid-gray`, collapsing the two existing "self" blues (curve `#131316` + "Tú" line `#0ea5e9`/`#0369a1`) into the one accent
- [ ] T027 [US2] Add reference-label capping to `RiderReferenceLines` in `frontend/src/components/athletes/ai/DistributionChart.tsx` (~482-519, depends on T026): when `points.length > 8`, only self/best/worst keep a visible text label — every other rider's `ReferenceLine` still renders at the correct position without a label; unchanged (all riders labeled, alternating top/bottom) at `points.length <= 8`
- [ ] T028 [US2] Add a "Gráfica"/"Tabla" toggle (built on `frontend/src/components/ui/tabs.tsx`) to `frontend/src/components/athletes/ai/DistributionChart.tsx` (depends on T026/T027) generalizing the existing `LowConfidenceTable` (~399-463: position/name/time, self-row highlighted) into the table-view twin for the n≥5 path; preserve the existing `n<5` fallback exactly as-is, rendered unconditionally and never alongside the toggle
- [ ] T029 [P] [US2] Restyle `frontend/src/components/athletes/ai/EvolutionChart.tsx` per `contracts/chart-style.md`: remove `strokeDasharray="3 3"` on `<CartesianGrid>` (~line 213); replace the axis-ink `#5a6172` with `--color-mid-gray` (~216,224,228); replace the self line/dot color `#131316` (~244,246) with `--color-primary`
- [ ] T030 [US2] Add an on-point championship marker to `frontend/src/components/athletes/ai/EvolutionChart.tsx` (depends on T029): a custom `dot` render for the point where `series_kind === "championship"` — rotated-square diamond shape, `--color-primary` fill (same as self), radius ~6, 2px surface-color ring, direct "Cto. Dep." label anchored at/above the point — in addition to, not replacing, the existing `<ol>` legend entry (~263-267)
- [ ] T031 [US2] Add an equivalent table-view twin + "Gráfica"/"Tabla" toggle to `frontend/src/components/athletes/ai/EvolutionChart.tsx` (depends on T029/T030): columns mirror the existing tooltip's fields (label/event date/value, ~321-341), championship row flagged the same way the `<ol>` legend already flags it; preserve the existing `n<3` fallback exactly as-is
- [ ] T032 [P] [US2] Add `vitest` chart regression tests in `frontend/src/components/athletes/ai/__tests__/DistributionChart.test.tsx` and `EvolutionChart.test.tsx`: zero `strokeDasharray` prop on either `<CartesianGrid>`; championship diamond dot renders iff fixture data has `series_kind==="championship"`; reference-line label present at `points.length<=8`, absent (position preserved) at `>8`; existing `n<5`/`n<3` low-confidence fallbacks render unchanged
- [ ] T033 [P] [US2] Add `jest-axe` coverage for both charts' table-view twins (T028, T031) — this is the point of the twin: it must be the WCAG-clean equivalent of the chart, not merely "also present"
- [ ] T034 [P] [US2] Add a palette-validation `vitest` check calling the validator from T002 to assert the chart role palette (`#20b7c9,#0ca30c,#d03b3b`, `pairs:"all"`) and the A/B/C ordinal ramp (T001/T015) both still pass their lightness-band/chroma-floor/CVD/contrast checks — guards against a future color edit silently breaking the validated set

**Checkpoint**: Charts are honest, legible, and table-accessible — independently testable alongside US1.

---

## Phase 5: User Story 3 - The newer modules stop looking bolted-on (Priority: P2)

**Goal**: Técnica, fuerza, intervalos, and ansiedad look and feel like the same product as the rest — same text colors, headings, shared components — with técnica and fuerza additionally presenting one consistent library experience.

**Independent Test**: Side-by-side visual audit of a screen from each of the four modules against a Competitions screen: typography, text colors, headers, empty/error states, and status labels are indistinguishable in style; técnica and fuerza share the same filtering/cards/detail layout, differing only in domain content.

### Implementation for User Story 3

- [ ] T035 [P] [US3] Remediate slate-* usage — técnica module, **excluding** `CatalogGrid.tsx`/`FilterBar.tsx`/`ExerciseCard.tsx` (handled by the shared-component merge, T040-T041): `frontend/src/routes/technique/**` and the remaining `frontend/src/components/technique/**` files (~80 occurrences across técnica per `research.md` R4, minus the 3 merge-target files). Remap convention: `slate-900/700/800`→`text-charcoal`, `slate-500/600`→`text-mid-gray` (or `text-text-disclaimer` for sub-12px fine print), `slate-100/200`→`bg-light-gray`, `slate-300` borders→`border-border-gray`
- [ ] T036 [P] [US3] Remediate slate-* usage — fuerza module, **excluding** `CatalogGrid.tsx`/`FilterBar.tsx`/`ExerciseCard.tsx` (handled by T040/T042): `frontend/src/routes/strength/**` and the remaining `frontend/src/components/strength/**` files (~95 occurrences per `research.md` R4, minus the 3 merge-target files), same remap convention as T035
- [ ] T037 [P] [US3] Remediate slate-* usage — intervalos module: `frontend/src/components/intervals/**` (`StructureEditor.tsx`, `TemplatePicker.tsx`, `BlockRow.tsx`, etc.) and any `frontend/src/routes/intervals/**` remnants post-029 (~43 occurrences per `research.md` R4), same remap convention
- [ ] T038 [P] [US3] Remediate slate-* usage — ansiedad module: `frontend/src/routes/anxiety/**` and `frontend/src/components/anxiety/**` (~75 occurrences per `research.md` R4), same remap convention. **Style-only**: zero change to instrument selection, scoring, interpretation wording, baseline anchoring, mastery-climate framing, consent gating, or the human-in-the-loop flow (Principle V) — only className/token edits are permitted in this task's diff
- [ ] T039 [P] [US3] Stray fixes outside the four named modules: `frontend/src/routes/ProtectedRoute.tsx` (~line 35, `text-slate-600` on the "Cargando sesión..." loading screen) and `frontend/src/components/athletes/MorphologyCard.tsx` (~line 24, `bg-slate-100 text-slate-800` tag variant)
- [ ] T040 [P] [US3] Extract shared `frontend/src/components/shared/CatalogGrid.tsx`, `frontend/src/components/shared/LibraryFilterBar.tsx`, and `frontend/src/components/shared/LibraryEntityCard.tsx` from the near-identical técnica/fuerza implementations (`FilterBar.tsx` is 259/259 lines identical; `strength/CatalogGrid.tsx` is already documented as a mirror of `technique/CatalogGrid.tsx`; `ExerciseCard.tsx` shares the same WCAG-48×48 link-on-name layout), config-driven via props for domain-specific fields (skill taxonomy vs. equipment/age-band); charcoal/mid-gray tokens from the start (no slate)
- [ ] T041 [P] [US3] Re-point `frontend/src/components/technique/CatalogGrid.tsx`, `FilterBar.tsx`, `ExerciseCard.tsx` at the shared components from T040, passing técnica's skill-taxonomy field config (depends on T040)
- [ ] T042 [P] [US3] Re-point `frontend/src/components/strength/CatalogGrid.tsx`, `FilterBar.tsx`, `ExerciseCard.tsx` at the shared components from T040, passing fuerza's equipment/age-band field config (depends on T040)
- [ ] T043 [US3] Add `vitest` coverage for the new shared `CatalogGrid`/`LibraryFilterBar`/`LibraryEntityCard` (T040) plus an assertion that técnica and fuerza both render through the same shared components, not two parallel implementations (depends on T040-T042)
- [ ] T044 [US3] Add a CI-runnable grep regression test asserting `\bslate-\d` returns zero matches under `routes/technique`, `routes/strength`, `routes/intervals`, `routes/anxiety`, `components/technique`, `components/strength`, `components/intervals`, `components/anxiety` (depends on T035-T042 all complete)

**Checkpoint**: The four newer modules are visually indistinguishable from the rest of the app; técnica/fuerza share one library experience — independently testable.

---

## Phase 6: User Story 4 - AI that presents one identity (Priority: P2)

**Goal**: Every AI entry point presents one identity — noun "Insights IA", verb "Analizar con IA", one icon (`Sparkles`), one freshness vocabulary, the same run-progress view (full or compact), and a pre-launch wait/budget hint instead of only a post-click failure.

**Independent Test**: Visit every AI entry point (session assistant, per-competition insights, per-athlete analysis, race chat, group launch): one name, one verb, one icon, one freshness presentation, the same run-progress view, and a pre-launch wait/budget hint; exhaust the budget in a test environment and verify the state is communicated before launch.

**Note**: This phase depends on Foundational's `useAIStatus` hook (T006) and reuses US1's `GroupRunRow` terminal-state migration (T023).

### Implementation for User Story 4

- [ ] T045 [P] [US4] Rename the h1 "Asistente IA" → "Insights IA" in `frontend/src/routes/training/SessionAssistantPage.tsx` (~88-92); keep a session-specific subtitle if it reads better, but the noun is "Insights IA"
- [ ] T046 [P] [US4] In `frontend/src/components/athletes/ai/AthleteAIAnalysisTab.tsx`: rename the h2 "Análisis IA del deportista"/"Análisis del coach" (mode-dependent, ~230-231) → "Insights IA" in both modes, keeping the mode-specific description text (~233-236) unchanged; rename the "Lanzar" sub-tab (~340-343) → "Analizar con IA", icon `Play`→`Sparkles`
- [ ] T047 [P] [US4] In `frontend/src/components/competitions/insights/AnalyzeAthleteButton.tsx`: icon `BrainCircuit`→`Sparkles` (~line 23); default label `"Analizar"`→`"Analizar con IA"` (~line 90); confirm-modal title `"Re-ejecutar análisis"`→`"Re-ejecutar análisis con IA"` (~line 202)
- [ ] T048 [P] [US4] Add a one-line non-persistence caption ("Esta conversación no se guarda — se pierde al cerrar o recargar la página.") to `frontend/src/components/competitions/chat/CompetitionChatPanel.tsx`, near the header (~230-236); keep the `MessageSquare` icon — the one deliberate, documented exception to "one icon everywhere" (chat is conversational, not a launched/tracked run)
- [ ] T049 [P] [US4] Add a `variant="compact"` to `frontend/src/components/ai/AnalysisRunTimeline.tsx`: header-only rendering (state label + progress bar + ETA, ~310-357), no per-node `<ol>`; the full variant stays unchanged at its existing mount point in `AthleteAIAnalysisTab.tsx` (~296-298)
- [ ] T050 [US4] Wire the compact `AnalysisRunTimeline` (T049) into `frontend/src/components/competitions/insights/GroupRunRow.tsx` for the "in progress" branches (`running`, launch outcome `started`/`recovered`) — the branches US1/T023 deliberately left untouched; one run-view implementation, two densities, not two implementations
- [ ] T051 [US4] Wire the pre-launch AI budget/wait hint into `frontend/src/components/competitions/insights/AnalyzeAthleteButton.tsx` using `useAIStatus()` (T006), depends on T047: `ok`→no visible hint beyond the button; `warning`→amber inline hint ("Presupuesto de IA: N% restante"), launch still enabled; `exhausted`→button disabled, plain-language explanation shown before any click (reuses the existing 503 copy); `concurrency_available=false`→"Alta demanda — espera ≈Ns", launch stays enabled; otherwise an "≈Ns" duration hint; a fetch failure degrades to today's reactive-only behavior, never blocking the button
- [ ] T052 [P] [US4] Wire the same pre-launch AI budget/wait hint pattern (T051) into `frontend/src/components/competitions/insights/GroupAnalysisPanel.tsx`'s launch button
- [ ] T053 [US4] Wire the same pre-launch AI budget/wait hint pattern (T051) into the session-assistant entry point in `frontend/src/routes/training/SessionAssistantPage.tsx` (depends on T045, same file)
- [ ] T054 [P] [US4] Add `vitest` rename-table assertions for T045-T047 plus a lock-in regression test that `frontend/src/routes/competitions/CompetitionDetailPage.tsx`'s Insights tab label stays "Insights IA" (~line 110, already correct — regression guard only); add a repo-wide grep-based test asserting `BrainCircuit` and the "Lanzar" label no longer appear in any AI-related component (`MessageSquare` allowlisted for `CompetitionChatPanel.tsx` only)
- [ ] T055 [P] [US4] Add `vitest` coverage for `AnalyzeAthleteButton`/`GroupAnalysisPanel` (depends on T051-T053): all three budget-status presentations, the concurrency wait hint, and graceful degradation when `GET /api/ai/status` fails to fetch
- [ ] T056 [P] [US4] Add `jest-axe` coverage for `AnalysisRunTimeline` (both variants, T049), `AnalyzeAthleteButton`, and `GroupAnalysisPanel` after T045-T053

**Checkpoint**: AI presents one name, one verb, one icon, one freshness model, and a proactive budget/wait hint everywhere — independently testable.

---

## Phase 7: User Story 5 - Comfort polish (Priority: P3 — optional, capacity permitting)

**Goal**: A dark appearance following device preference at the same contrast bars as light mode, and keyboard shortcuts for desktop planning. No command palette (program decision D5).

**Independent Test**: Switch the device to dark appearance and audit coach screens for legibility/contrast; on desktop, navigate between main areas and trigger quick-create via documented shortcuts.

**Ships only if capacity allows.** Hard dependencies: `specs/028-frontend-design-foundation`'s shadow/token consolidation (inline `boxShadow`/colors cannot respond to a CSS variant) for dark mode; `specs/030-coach-navigation-redesign`'s `frontend/src/components/layout/UserMenu.tsx`, `QuickCreate.tsx`, and `NavArea[]` config for both sub-features.

### Implementation for User Story 5

- [ ] T057 [P] [US5] Add `@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *))` and the dark token values (page-plane `#0d0d0d`, card/chart surface `#1a1a1a`, primary/secondary/disclaimer text, subtle-panel fill, border, and a 1px ring replacing `--shadow-card`, per `contracts/dark-theme-tokens.md`) to `frontend/src/style.css`, scoped to coach surfaces only; also add the dark variants of the A/B/C ordinal ramp (`#6dd6e6`/`#2fbfd1`/`#0d97a7`); accent and status tokens are unchanged between modes (already clear contrast on `#1a1a1a`)
- [ ] T058 [US5] Implement theme activation (depends on T057): `localStorage` key `tyr:theme-preference:v1`; an inline pre-hydration `<script>` in `frontend/index.html` that reads the stored preference and applies `data-theme` before first paint (no flash-of-wrong-theme); `"system"` leaves the attribute unset and falls back to the `prefers-color-scheme` media query
- [ ] T059 [US5] Add a Sistema/Claro/Oscuro 3-state toggle to `frontend/src/components/layout/UserMenu.tsx` (depends on T058), wired to the activation logic; confirm parent-portal routes stay light-only regardless of the coach's stored preference (a shared layout component must read a "surface scope" flag rather than blindly honoring `data-theme`)
- [ ] T060 [P] [US5] Add an automated contrast-audit test re-running the T002 validator against every dark token pair from T057, for both `data-theme="light"` and `data-theme="dark"`
- [ ] T061 [P] [US5] Add `jest-axe` coverage with `data-theme="dark"` forced for every page-level/dialog-level coach component touched by this feature, and sweep for dark-on-dark invisible marks (charts, badges, photos/illustrations)
- [ ] T062 [P] [US5] Implement the keyboard-shortcuts hook: `g` then `i/e/c/a/f/b` jumps to the six 030 `NavArea`s (Inicio/Entrenamiento/Competencias/Atletas/Familias/Biblioteca), `n` opens the existing `QuickCreate` control, `?` opens the shortcuts help dialog; guardrails disable all shortcuts while `document.activeElement` is an `<input>`/`<textarea>`/`contenteditable`, or a modal/sheet is open
- [ ] T063 [US5] Add an "Atajos de teclado" help dialog (`frontend/src/components/ui/dialog.tsx`) listing the shortcut table from T062, with a discoverable entry point in `frontend/src/components/layout/UserMenu.tsx` (depends on T059, same file; and T062)
- [ ] T064 [P] [US5] Add `vitest` coverage for the keyboard-shortcut guardrails (inactive in input/textarea/contenteditable/open-modal) and for each area-jump/quick-create binding from T062/T063

**Checkpoint**: Dark appearance and keyboard shortcuts ship only if all prior phases are complete and capacity allows — independently testable, cleanly deferrable.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation against every Success Criterion, and closing the loop on the spec's own design-system-currency assumption.

- [ ] T065 [P] Run the full `quickstart.md` SC-001…SC-007 manual/visual audit checklists across every touched surface and record results (screenshots or a written pass/fail per checklist item)
- [ ] T066 [P] Perform the US3 side-by-side style-parity sweep: a técnica, fuerza, intervalos, and ansiedad screen each compared against a Competitions screen (typography, text colors, headers, empty/error/loading states, status labels)
- [ ] T067 [P] Update `docs/05-design-system/design.md` to match shipped reality: formalize the single accent (`#20b7c9`, one name — the doc currently references an unrelated `#0099ff`/`#242424` Cal.com-inspired palette), retire the unused secondary brand color (`--color-accent`/`#8be000`, confirmed unconsumed anywhere in `frontend/src`) from the documented app palette, and document the final status vocabulary, A/B/C ordinal ramp, and (if shipped) dark tokens
- [ ] T068 [P] Line-by-line review of every touched `frontend/src/components/anxiety/*` and `frontend/src/routes/anxiety/*` diff (T038) confirming only className/token changes — any changed copy, threshold, scoring, or consent-gate edit is a regression, not an intended change (SC-007, Principle V)
- [ ] T069 [P] Regenerate one report/newsletter/instructivo before and after this feature's changes and byte-diff (or visual-diff) the output to confirm zero regression; confirm the existing PDF/newsletter/instructivo render tests still pass unmodified (SC-007, FR-010)
- [ ] T070 Run the full constitution re-check: `eslint`/`tsc --noEmit` (frontend), `ruff`/`mypy` (backend), the complete `pytest` and `vitest` suites, and confirm `AI_LOG_PROMPTS` stays `false` in production config with no PII in the new `/api/ai/status` payload or its logs

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No internal dependencies — can start immediately once the cross-feature prerequisite below is satisfied.
- **Foundational (Phase 2)**: Depends on Setup (T001-T003) completing. **BLOCKS all user stories.**
- **User Stories (Phase 3-7)**: All depend on Foundational (Phase 2) completing.
  - US1, US2, US3 touch disjoint file sets and can proceed **in parallel** once Foundational is done.
  - US4 additionally needs `useAIStatus` (T006, Foundational) and reuses US1's `GroupRunRow` terminal-state migration (T023) — start US4 after Foundational, ideally after US1's T023 lands to avoid a `GroupRunRow.tsx` merge conflict.
  - US5 is last and optional (P3) — start only after US1-US4 and capacity allows.
- **Polish (Phase 8)**: Depends on all shipped user stories being complete.

### Cross-Feature Dependencies (program sequencing, specs 028-032)

- **Hard blocker**: `specs/028-frontend-design-foundation` — `StatusBadge.tsx`, the shared-component kit, `--color-success/-warning/-danger` tokens, and the shadow/token consolidation. Neither exists in this repository as of this writing; Foundational (T004-T014) and every user-story task that renders `<StatusBadge>` or depends on inline-style-free shadows (US5's dark mode, T057-T059) cannot be verified until 028 merges.
- **Soft/scope-reducing**: `specs/029-coach-surface-subtraction` — its approved deletions (gymkhana composer, standalone technique builder, standalone interval-template screen, two athlete-progress wrapper routes) reduce US3's slate-remediation surface (T035-T038) from 40 files/361 occurrences to 32 files/295 occurrences. Not blocking — if 029 hasn't shipped yet, T035-T038 simply do transient extra work on files that will later be deleted.
- **Recommended, not blocking**: `specs/030-coach-navigation-redesign` (`UserMenu.tsx`, `QuickCreate.tsx`, `NavArea[]`) is a **hard** dependency specifically for US5 (T059, T062, T063) — everything else in this feature is independent of it. `specs/032-session-content-unification` explicitly assigns the técnica/fuerza catalog consolidation (T040-T043) to this feature by name (`specs/032-session-content-unification/spec.md:109`) — no ordering dependency, just confirmation of scope ownership.

### Within Each User Story

- Same-file edits are sequential even when both belong to the same story (e.g. US2's grid/color pass before its own label-capping/table-twin pass on the same chart file; US5's dark-mode and shortcuts sub-features both eventually touch `UserMenu.tsx`).
- Cross-story same-file touches are called out inline: `AthleteAIAnalysisTab.tsx` is touched by US1 (T019) and US4 (T046) — sequence those two if working the stories fully in parallel; `GroupRunRow.tsx` is touched by US1 (T023) and US4 (T050) similarly; `SessionAssistantPage.tsx` is touched by US4 twice (T045 then T053).
- Every adapter-consuming task in US1/US4 depends on its corresponding Foundational adapter/hook task, never the other way around.

### Parallel Opportunities

- All Setup tasks (T001-T003) in parallel.
- All Foundational tasks except T004 (T005-T014) in parallel — 10 of 11.
- US1: 9 of 11 tasks in parallel (T015-T023); T024 (jest-axe) and T025 (cross-module test) run after.
- US2: the two per-chart restyle entry points (T026, T029) in parallel with each other; each chart's own label-cap/marker/table-twin follow-ons are sequential within that file; the three cross-cutting test tasks (T032-T034) in parallel once implementation lands.
- US3: all four module remediations plus the stray-fix task plus the shared-component extraction (T035-T040) in parallel; the two re-point tasks (T041-T042) in parallel with each other once T040 lands; the two validation tasks (T043-T044) run last.
- US4: five independent rename/caption/variant tasks (T045-T049) in parallel; T052 (GroupAnalysisPanel hint) in parallel with T051's sibling work; the three test tasks (T054-T056) in parallel once implementation lands.
- US5: the dark-mode token task (T057) and the keyboard-shortcuts hook (T062) are independent chain starts and run in parallel; their respective test tasks (T060-T061, T064) run in parallel once implementation lands.
- Polish: T065-T069 in parallel; T070 (full suite run) is the final gate.

---

## Parallel Example: User Story 1

```bash
# Launch every legacy badge migration together (each a different file, each already
# has its Foundational adapter from T007-T014):
Task: "Migrate ConnectionStatusBadge.tsx to StatusBadge via connectionStatus() — T016"
Task: "Migrate CompetitionStatusBadges.tsx's 3 sub-badges to StatusBadge — T017"
Task: "Rewrite SessionStatusBadge.tsx to render StatusBadge via sessionStatus() — T018"
Task: "Delete AthleteAIAnalysisTab.tsx's duplicate confidence adapter, import the canonical one — T019"
Task: "Replace AthleteNewslettersDashboardPage.tsx's hand-rolled span with StatusBadge — T020"
Task: "Migrate ConsentStatusPanel.tsx's STATE_CONFIG + AI pill to StatusBadge — T021"
Task: "Replace StaleAnalysisBadge.tsx's hand-colored Badge with StatusBadge — T022"
Task: "Delete GroupRunRow.tsx's StateChip, render StatusBadge for terminal states — T023"

# Plus, independently, the ordinal-ramp fix (different file entirely):
Task: "Fix CARRERA_TIER/getCarreraTier 'CD'→tier 'A' in lib/insights.ts — T015"
```

## Parallel Example: User Story 3

```bash
# Launch all four module remediations, the stray fixes, and the shared-component
# extraction together (eight disjoint file sets):
Task: "slate-* remediation — técnica (excl. merge-target files) — T035"
Task: "slate-* remediation — fuerza (excl. merge-target files) — T036"
Task: "slate-* remediation — intervalos — T037"
Task: "slate-* remediation — ansiedad (style-only, Principle V) — T038"
Task: "Stray fixes — ProtectedRoute.tsx + MorphologyCard.tsx — T039"
Task: "Extract shared CatalogGrid/LibraryFilterBar/LibraryEntityCard — T040"

# Then, once T040 lands, both re-point tasks in parallel:
Task: "Re-point técnica's CatalogGrid/FilterBar/ExerciseCard at shared components — T041"
Task: "Re-point fuerza's CatalogGrid/FilterBar/ExerciseCard at shared components — T042"
```

## Parallel Example: User Story 4

```bash
# Launch the five independent rename/caption/variant tasks together:
Task: "Rename SessionAssistantPage.tsx h1 to Insights IA — T045"
Task: "Rename AthleteAIAnalysisTab.tsx h2 + Lanzar sub-tab — T046"
Task: "Rename AnalyzeAthleteButton.tsx icon + labels — T047"
Task: "Add non-persistence caption to CompetitionChatPanel.tsx — T048"
Task: "Add variant='compact' to AnalysisRunTimeline.tsx — T049"
```

---

## Implementation Strategy

### MVP First (Setup + Foundational + User Story 1 only)

1. Complete Phase 1: Setup (tokens, palette validator, endpoint scaffold).
2. Complete Phase 2: Foundational (real endpoint + hook + all 8 status adapters) — **CRITICAL, blocks every story**.
3. Complete Phase 3: User Story 1 (the badge sweep + A/B/C ordinal fix).
4. **STOP and VALIDATE**: run the SC-001 checklist in `quickstart.md` independently — one color vocabulary, everywhere.
5. Ship/demo if ready — this alone closes the constitution's own long-standing color-semantics gap.

### Incremental Delivery

1. Setup + Foundational → foundation ready (endpoint, hook, adapters all unit-tested).
2. Add User Story 1 → validate independently → ship (MVP).
3. Add User Story 2 (charts) → validate independently (SC-005) → ship.
4. Add User Story 3 (newer-module parity + técnica/fuerza merge) → validate independently (SC-002) → ship.
5. Add User Story 4 (AI identity + proactive budget hint) → validate independently (SC-003, SC-004) → ship.
6. Add User Story 5 (dark mode + shortcuts) **only if capacity allows** → validate independently (SC-006) → ship.
7. Polish: run every remaining Success Criterion check, update the design-system doc, confirm zero regressions in generated documents and the anxiety module (SC-007).

### Parallel Team Strategy

With multiple developers/agents, once Foundational is done:

- Developer/Agent A: User Story 1 (badge sweep)
- Developer/Agent B: User Story 2 (charts)
- Developer/Agent C: User Story 3 (module parity + técnica/fuerza merge)
- User Story 4 starts once A finishes `GroupRunRow`'s terminal-state migration (T023) to avoid a merge conflict on that file
- User Story 5 starts last, capacity permitting, once 030 has also landed

---

## Notes

- [P] tasks = different files, no dependency on an incomplete task; 54 of the 70 tasks below are marked [P].
- [Story] label maps every story-phase task to US1-US5 for traceability; Setup/Foundational/Polish carry no story label per the strict task format.
- This is a presentation-only feature (FR-010): no schema change, no migration, no change to any AI pipeline/prompt/scoring/budget logic itself, no change to generated documents, no change to any Principle V (anxiety module) safeguard, wording, or consent gate — only how existing state is rendered.
- Every renamed label/icon and every status adapter ships with its own test update, not a silent snapshot bump (Constitution II).
- Verify tests fail (or are meaningfully new) before considering an implementation task done; stop at any checkpoint to validate a story independently before moving to the next.
- Avoid: vague tasks, unnecessary same-file conflicts, cross-story dependencies that break independence beyond the two explicitly noted shared files (`AthleteAIAnalysisTab.tsx`, `GroupRunRow.tsx`, `SessionAssistantPage.tsx`, `UserMenu.tsx`).
