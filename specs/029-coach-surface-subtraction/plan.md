# Implementation Plan: Coach Surface Subtraction

**Branch**: `claude/coach-profile-ux-analysis-kaar7d` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/029-coach-surface-subtraction/spec.md`

## Summary

Remove ~3,500 lines of confirmed dead/duplicated coach-facing presentation surface (gymkhana composer + its two drawing dependencies, standalone technique session builder, standalone interval-template screen, and the duplicated cross-race AI hub trio), while relocating the one genuinely unique view in that last group (the season panorama) to a visible entry under Competencias. In parallel, close two known integration gaps rather than deleting them: consolidate technique-skill and strength progress onto one "Progreso" tab on the athlete profile (with a wellbeing pointer into the anxiety module, athlete preselected), and wire the already-built, already-tested on-demand anxiety interpretation into the individual anxiety view. All changes are presentation-only — no schema, migration, or stored-data change (`data-model.md`); every previously-shared external address keeps resolving (`contracts/removal-and-redirect-manifest.md`). Technical approach grounded in `research.md`; consumes the shared component kit and testing approach from `specs/028-frontend-design-foundation`.

## Technical Context

**Language/Version**: TypeScript ~6.0 (frontend only — no backend source changes in this feature)

**Primary Dependencies**: React 19.2, Vite 8, Tailwind CSS 4.2, TanStack Query 5.101, React Router v7.14, shadcn/ui + Radix (`ToggleGroup` for the Técnica/Fuerza toggle, reused from 028), lucide-react. **Removed**: `konva` (`package.json:71`), `react-konva` (`package.json:79`) — no replacement, no new runtime dependency added.

**Storage**: N/A — no migration, no schema change; all removed/relocated/wired screens read and write through existing, unchanged endpoints (`data-model.md`)

**Testing**: vitest + Testing Library + jest-axe (unit/a11y, per-file updates enumerated in `research.md` R5), Playwright (existing `frontend/e2e/`, unaffected by this feature — no new spec required), pytest (backend, regression-only — confirms the untouched `technique`/`strength`/`anxiety` endpoints still pass; no new backend tests because no backend code changes)

**Target Platform**: Mobile-first responsive web; coach tablet (outdoors) + desktop planning — unchanged from 028

**Project Type**: Web application (existing `frontend/` + `backend/` monorepo); this feature is frontend-only

**Performance Goals**: Net bundle size **decreases** (SC-007) — two drawing dependencies dropped, ~3,500 LOC removed; the Progreso tab and interpretation wiring add zero new bundle weight (both reuse already-`React.lazy`-loaded components, `research.md` R3/R4)

**Constraints**: WCAG 2.1 AA floor (unchanged); ≥48×48 px touch targets on any new interactive element (toggle, pointer link); es-CO product copy; Principle V safeguards preserved verbatim on the interpretation wiring (no new interpretation logic, no scoring change, no auto-messaging)

**Scale/Scope**: 8 routes removed, 1 route relocated (file move, same URL), 2 routes added implicitly via 1 new tab value, 1 redirect retargeted, ~3,500 LOC + 2 npm packages removed, ~10 test files touched (`research.md` R5), 0 migrations

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — no new violations surfaced.*

| Principle | Gate | Status |
|---|---|---|
| I. Code Quality | `eslint`/`tsc --noEmit` pass (typecheck is also the removal-mechanics safety net, `research.md` R1); duplication removed on the rule-of-three (`validaLabel`'s true duplicate pair merged, R6); dead code (upload widget, composer, session builder, insights trio) deleted outright rather than left commented-out | ✅ PASS |
| II. Testing (NON-NEGOTIABLE) | Every removal's test file is deleted or updated (never left dangling — `research.md` R5 table); the interpretation wiring lands with a new regression test proving it renders (both `source: "llm"` and `"rule"` cases, `contracts/anxiety-interpretation-ui.md`); the Progreso tab lands with a new `AthleteDetailPage.progreso.test.tsx` (following the existing `.strava.test.tsx` per-tab convention); jest-axe re-run on `AthleteDetailPage` and `IndividualPanel` since both gain new interactive elements | ✅ PASS |
| III. UX Consistency | Surviving screens keep their existing loading/empty/error states unchanged; new elements (Técnica/Fuerza toggle, wellbeing pointer, "Analizar con IA" button) are ≥48 px and keyboard-operable (`ToggleGroup`, plain link/button — no new custom widget); es-CO copy reused verbatim from already-shipped strings; season-panorama entry point makes an already-built capability newly discoverable per FR-002 | ✅ PASS |
| IV. Performance | Bundle **shrinks** (konva + react-konva removed, ~3,500 LOC gone); no static import of >50 KB modules added; Progreso tab / interpretation wiring add 0 new lazy chunks (both compositions of already-lazy components) | ✅ PASS |
| V. Youth Psych. Assessment Safeguards (NON-NEGOTIABLE) | Interpretation wiring is presentation-only (FR-009): no scoring change, no new interpretation logic, coach-only access unchanged (server-enforced), rule-based fallback surfaced as a normal success state not an error (`contracts/anxiety-interpretation-ui.md`), no auto-messaging introduced. **Named, not hidden, limitation**: the guardian-consent gate is enforced server-side only at assessment creation (verified, `research.md` R4) — this feature does not weaken that; it also does not newly close the mid-session-revocation edge case, since doing so would require a server change FR-009 explicitly excludes. Documented as a scoped-out follow-up, not silently assumed solved | ✅ PASS (with documented scope boundary) |
| Quality Gates | Stack discipline: **removes** 2 runtime deps, adds 0 — the opposite of the usual "new dependency needs justification" case, nothing to justify. Privacy: no new logs, no new PII surface; anxiety interpretation payload shape is unchanged (already audited under spec 017). Security/RBAC: unchanged — no route's `allowedRoles` changes. AI features: reuses an existing, already-guardrailed endpoint; no new AI call path | ✅ PASS |

## Project Structure

### Documentation (this feature)

```text
specs/029-coach-surface-subtraction/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output — no new entities
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── removal-and-redirect-manifest.md  # Every removed/relocated route + redirect/tombstone behavior
│   ├── progreso-tab.md                   # New AthleteDetailPage tab contract
│   └── anxiety-interpretation-ui.md      # Wired interpretation UI states + existing endpoint contract
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
frontend/
├── src/
│   ├── App.tsx                                          # EDIT: remove 6 lazy imports + 8 route blocks;
│   │                                                     #   retarget /coach/race-analysis → /competitions;
│   │                                                     #   add 2 relocated-page lazy import (SeasonInsightsPage
│   │                                                     #   new path)
│   ├── routes/technique/ComposerPage.tsx                 # DELETE
│   ├── routes/technique/SessionBuilderPage.tsx            # DELETE
│   ├── components/technique/composer/                     # DELETE (dir: AccessibleControls.tsx, KonvaCanvas.tsx,
│   │                                                       #   piiGuard.ts, Composer.a11y.test.tsx,
│   │                                                       #   Composer.roundtrip.test.tsx)
│   ├── components/technique/SessionAssembler.tsx           # DELETE
│   ├── components/technique/__tests__/SessionAssembler.test.tsx  # DELETE
│   ├── routes/intervals/                                   # DELETE (dir: TemplateLibraryPage.tsx only file)
│   ├── routes/competitions/insights/                        # DELETE (dir) EXCEPT SeasonInsightsPage.tsx, which:
│   ├── routes/competitions/SeasonInsightsPage.tsx            # ADD (relocated from insights/; fix 2 internal links)
│   ├── components/ai/UploadZone.tsx                         # DELETE
│   ├── components/ai/__tests__/UploadZone.test.tsx           # DELETE
│   ├── routes/technique/AthleteProgressPage.tsx               # DELETE
│   ├── routes/strength/AthleteProgressPage.tsx                # DELETE
│   ├── routes/strength/__tests__/AthleteProgressPage.test.tsx # DELETE
│   ├── routes/athletes/AthleteDetailPage.tsx                  # EDIT: +"progreso" tab (contracts/progreso-tab.md)
│   ├── routes/athletes/AthleteDetailPage.progreso.test.tsx    # ADD (new, per-tab test convention)
│   ├── routes/athletes/AthleteDetailPage.test.tsx              # EDIT: tab-count assertion
│   ├── routes/competitions/CompetitionsListPage.tsx            # EDIT: + "Panorama de temporada" header link
│   ├── routes/anxiety/AnxietyDashboardPage.tsx                  # EDIT: read ?athlete=, default tab (contracts/progreso-tab.md)
│   ├── components/anxiety/IndividualPanel.tsx                   # EDIT: mount AnalyzeButton + InterpretationPanel
│   ├── components/anxiety/__tests__/IndividualPanel.test.tsx     # EDIT: +QueryClientProvider, +interpretation test
│   ├── components/athletes/ai/AthleteAIAnalysisTab.tsx           # EDIT: delete private validaLabel, import shared one
│   ├── lib/insights.ts                                           # EDIT: validaLabel docstring (sole survivor note)
│   ├── __tests__/competitions-routing.test.tsx                    # EDIT: retarget redirect stub + T022 path literals
│   ├── __tests__/competitionsRedirects.test.tsx                    # EDIT: retarget redirect stub
│   ├── __tests__/T049-wave-f-cleanup.test.tsx                       # EDIT: retarget stub + extend REMOVED_MODULE_FRAGMENTS
│   ├── routes/competitions/insights/__tests__/*.test.tsx (3 files)   # DELETE (InsightsHubPage/ClubInsightsPage/AthleteInsightsPage)
│   ├── routes/competitions/__tests__/SeasonInsightsPage.test.tsx      # ADD (moved + edited from insights/__tests__/)
│   ├── routes/GonePage.tsx                                            # EDIT (optional, low-priority): default prop target
│   └── package.json                                                   # EDIT: remove konva, react-konva
backend/                                                                 # UNTOUCHED — no files in this feature
```

**Structure Decision**: Existing web-app monorepo; this feature is frontend-only (`frontend/src/`). No new top-level directories — removals collapse existing directories (`components/technique/composer/`, `routes/intervals/`, `routes/competitions/insights/`) and one file relocates one level up (`routes/competitions/insights/SeasonInsightsPage.tsx` → `routes/competitions/SeasonInsightsPage.tsx`). Full per-file disposition and evidence: `research.md`, `contracts/removal-and-redirect-manifest.md`.

## Complexity Tracking

*No constitution violations — table intentionally empty.* This feature is net complexity-**negative**: 8 routes and ~3,500 LOC removed, 2 runtime dependencies (`konva`, `react-konva`) removed from `package.json` with zero new dependencies added, and the two "wiring" changes (Progreso tab, anxiety interpretation) are compositions of already-built, already-tested components rather than new subsystems.
