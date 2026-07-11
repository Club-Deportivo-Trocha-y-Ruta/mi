# Implementation Plan: Visual Coherence & Polish

**Branch**: `claude/coach-profile-ux-analysis-kaar7d` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/033-visual-coherence-polish/spec.md`

## Summary

Feature 6 of 6 in the coach-experience-redesign program: sweep the whole coach app onto the shared visual system 028–032 established. Four independent passes: (1) collapse **eight** ad hoc status-badge implementations (not six — reading the code surfaced two more, `StaleAnalysisBadge` and `GroupRunRow`'s `StateChip`) onto `StatusBadge`, with race classes A/B/C rendered instead as a validated one-hue ordinal ramp built from the app's own accent teal, never as status colors; (2) restyle `DistributionChart`/`EvolutionChart` per the `dataviz` skill — solid hairline grids, three color roles (own-series = accent, best/worst = status tokens) validated with `scripts/validate_palette.js` rather than eyeballed, an on-point championship marker, capped reference labels above 8 riders, and a mandatory table-view twin (the accent's own contrast ratio against the app's white surface is a documented WARN that the skill says is not dismissable without one); (3) bring técnica, fuerza, intervalos, and ansiedad off `slate-*` and onto the charcoal/mid-gray vocabulary — 295 real occurrences across 32 files once feature 029's approved deletions are accounted for — including the técnica/fuerza `CatalogGrid`/`FilterBar`/`ExerciseCard` structural merge, which `specs/032-session-content-unification/spec.md` explicitly assigns to this feature by name; (4) unify AI identity (noun "Insights IA", verb "Analizar con IA", one icon, one freshness model, one run-progress view) and make cost/latency proactive via one new tiny read-only endpoint, `GET /api/ai/status`, reusing existing budget/concurrency computations verbatim rather than inventing new business logic. Two optional stories (dark appearance, keyboard shortcuts) ship only if capacity allows and only after their hard dependencies (028's shadow/token consolidation; 030's nav groups and quick-create) are in place. Technical approach grounded in `research.md`; contracts in `contracts/`.

## Technical Context

**Language/Version**: TypeScript ~6.0 (frontend); Python 3.13 (backend, one new endpoint — matches `backend/Dockerfile` `FROM python:3.13-slim` and `pyproject.toml requires-python = ">=3.13"`)

**Primary Dependencies**: React 19.2, Vite 8, Tailwind CSS 4.2 (`@theme`, `@custom-variant`), shadcn/ui (new-york), TanStack Query 5.101, React Hook Form 7.72 + Zod 4.3, lucide-react, recharts 3.8.1, react-router-dom 7.14. **Zero new runtime dependencies** — every consumer-facing change reuses primitives already installed: `ui/tabs.tsx` (chart table-view toggle), `ui/dialog.tsx` (keyboard-shortcuts help), the `StatusBadge`/tokens 028 ships, the user menu/quick-create 030 ships. Backend: FastAPI + SQLAlchemy 2 async (existing `athlete_ai_insights` table only, read-only).

**Storage**: N/A — no schema change, no migration. The one new endpoint (`GET /api/ai/status`) reads `athlete_ai_insights.metrics_snapshot_json` via the exact query pattern `check_budget()`/`admin_ai_usage()` already run, plus an in-memory semaphore read (`has_capacity()`); it persists nothing.

**Testing**: vitest + Testing Library + jest-axe (frontend unit/a11y — status adapters, renamed labels, freshness states, chart prop assertions, dark-mode contrast); pytest + httpx.AsyncClient (backend — the one new endpoint, happy + RBAC-negative + the budget/hard-block consistency property test). No new Playwright spec required (this feature does not change tap targets; existing `target-size.spec.ts` from 028 continues to cover any touched interactive control).

**Target Platform**: Existing coach-facing responsive web app (tablet-first field use, desktop planning); backend on Render free tier. Parent-portal surfaces and generated documents (PDF/newsletter/instructivo templates) are explicitly untouched (FR-010).

**Performance Goals**: `GET /api/ai/status` p95 ≤ 500ms (Constitution IV) — trivially met, since it reuses a query already run synchronously on every launch attempt today, plus one in-memory read. No chart re-render regression (prop-level color/shape changes only, no new chart library surface). No frontend bundle growth (zero new deps).

**Constraints**: WCAG 2.1 AA floor maintained (icon+label never color-alone on every status badge; contrast-checked chart/dark tokens); es-CO product copy for every renamed label; no change to any anxiety-module safeguard, wording, or consent gate (Principle V, FR-010); no change to generated documents; dark mode (if shipped) is CSS-only, gated on 028's shadow/token consolidation being merged first.

**Scale/Scope**: 8 status-badge implementations → 1 shared component + adapters; 2 chart files restyled at the prop level; 32 files / 295 real slate-* occurrences remediated (+2 optional stray fixes) across 4 modules, including 1 structural component merge (técnica+fuerza catalog); 7+ AI naming sites unified; 1 new backend endpoint; 2 optional stories (~15 dark-mode token pairs; 8 keyboard bindings) shipped only if capacity allows.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Code Quality & Maintainability | `eslint`/`tsc --noEmit` (frontend), `ruff`/`mypy` (backend endpoint) pass. Duplication removed on the rule-of-three trigger, repeatedly: 8 status-badge systems → 1 (`StatusBadge` + domain adapters); the verbatim-duplicated `confidenceVariant`/`confidenceLabel` (`lib/insights.ts` vs. `AthleteAIAnalysisTab.tsx:75-87`) deleted to one; técnica/fuerza's 259/259-identical `FilterBar.tsx` and near-verbatim `CatalogGrid.tsx`/`ExerciseCard.tsx` merged into shared `components/shared/{CatalogGrid,LibraryFilterBar,LibraryEntityCard}.tsx`. No premature abstraction introduced beyond what the audit already evidenced as a 2nd/3rd copy. | ✅ PASS |
| II. Testing (NON-NEGOTIABLE) | Every renamed label/icon ships with an updated `vitest` assertion (not a silent snapshot bump); every status adapter gets a full-state-table test; the existing chart low-confidence/low-n table fallbacks are asserted **unchanged** (regression test, since this feature could easily touch them incidentally while restyling); a new property test asserts `GET /api/ai/status`'s `budget_status="exhausted"` if-and-only-if a real launch would 503 (prevents the hint and the hard block drifting apart); the AI-status payload is asserted to carry no athlete identifiers (Quality Gates: property tests that real names never appear in AI-adjacent output extend naturally to this new surface); `jest-axe` on every updated badge/chart/dialog component. | ✅ PASS |
| III. UX Consistency | This feature *is* the enforcement of the constitution's own color-semantics clause ("green = success/complete, amber = partial/attention, red = error/blocking, neutral gray = informational... consistent across the app") — closing the gap the constitution already named as non-negotiable. Every chart/status/ordinal color is validated with `scripts/validate_palette.js` (CVD ΔE, lightness band, chroma floor, contrast), not eyeballed; WCAG 2.1 AA maintained (contrast pairs computed for every new token, incl. dark mode); icon+label required on every status render, never color alone (both for the sweep and for the A/B/C ramp, which always ships with the visible letter). Shared components sourced from `components/ui`/`components/shared` per existing convention, no new pattern introduced. | ✅ PASS |
| IV. Performance | Zero new npm/pip dependencies. Chart changes are prop-level only (color/stroke/dot-renderer/label-visibility), no new chart-library surface, no bundle growth. Dark mode (optional) is pure CSS (`@theme`/`@custom-variant`), no JS-computed styling beyond one `data-theme` attribute toggle. `GET /api/ai/status` reuses an already-hot query path (`_sum_cost_last_30d`, already run synchronously on every launch today) plus an in-memory semaphore read — p95 ≤500ms trivially satisfied, no N+1 risk (single aggregate, no per-athlete loop). | ✅ PASS |
| V. Youth Psychological Assessment Safeguards | Ansiedad module changes in this feature are **style-only**: `slate-*` → charcoal/mid-gray token swaps across `components/anxiety/*` and `routes/anxiety/*`. No change to instrument selection, scoring, interpretation wording, baseline anchoring, mastery-climate framing, consent gating, or the human-in-the-loop flow. Explicitly gated by FR-010 and the spec's own edge case ("visual alignment must not alter any Principle V safeguard, wording rule, or consent gate — style only"); quickstart.md's SC-007 check requires reading every touched anxiety-module diff line-by-line and failing the change if any non-className/token edit appears. | ✅ PASS (verified, not just asserted — see quickstart.md SC-007) |
| Quality Gates | `AI_LOG_PROMPTS` stays `false` in production, unaffected by this feature. No PII added anywhere: the new `/api/ai/status` payload carries no athlete identifiers, no names, no dollar figures (dollar figures stay admin-only via the existing `/admin/ai-usage`); this endpoint's logs carry a correlation ID only, per existing observability convention. Stack discipline: zero new runtime dependencies (a real check against this gate, not just a claim — see Technical Context). | ✅ PASS |

**Post-design re-check (after Phase 1)**: `contracts/status-vocabulary-sweep.md`, `contracts/chart-style.md`, `contracts/ai-identity.md`, and `contracts/dark-theme-tokens.md` introduce no data-layer coupling (every sweep target stays presentational, receiving state via props exactly as today); the one backend addition is read-only, RBAC'd via the already-existing `_coach_or_admin` dependency (no new permission logic written); no violation surfaced during Phase 1 design. ✅ PASS

## Project Structure

### Documentation (this feature)

```text
specs/033-visual-coherence-polish/
├── plan.md                          # This file
├── research.md                      # Phase 0 output (R1-R8: StatusBadge sweep, A/B/C ramp,
│                                     #   chart restyle, slate remediation, AI identity,
│                                     #   AI budget/wait, dark mode, keyboard shortcuts)
├── data-model.md                    # Phase 1 output: final status-vocabulary table, ordinal
│                                     #   scale, chart color-role table, dark token map, AIStatus
├── quickstart.md                    # Phase 1 output: validation walkthrough tied to SC-001..007
├── contracts/
│   ├── status-vocabulary-sweep.md   # 8 implementations → StatusBadge, es-CO labels
│   ├── chart-style.md               # Grid/roles/championship-mark/label-cap/table-twin/tooltips
│   ├── ai-identity.md               # Naming/icon/freshness/run-view + GET /api/ai/status contract
│   └── dark-theme-tokens.md         # Optional story: token map + @custom-variant + activation
└── tasks.md                         # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
frontend/
├── src/
│   ├── style.css                              # register --color-success/-warning/-danger consumers
│   │                                           #   (tokens themselves land via 028); optional:
│   │                                           #   @custom-variant dark, dark token values
│   ├── components/
│   │   ├── shared/
│   │   │   ├── StatusBadge.tsx                # (from 028) — this feature adds NO new props,
│   │   │   │                                  #   only new call sites + domain adapters
│   │   │   ├── CatalogGrid.tsx                # NEW — generic, replaces technique+strength copies
│   │   │   ├── LibraryFilterBar.tsx           # NEW — config-driven filter shell
│   │   │   └── LibraryEntityCard.tsx          # NEW — replaces ExerciseCard duplication
│   │   ├── activities/ConnectionStatusBadge.tsx        # → StatusBadge adapter
│   │   ├── competitions/
│   │   │   ├── CompetitionStatusBadges.tsx             # → 3× StatusBadge adapters
│   │   │   └── insights/
│   │   │       ├── AnalyzeAthleteButton.tsx            # icon/label rename; AIStatus hint
│   │   │       ├── StaleAnalysisBadge.tsx              # → StatusBadge(status="warning")
│   │   │       ├── GroupAnalysisPanel.tsx              # AIStatus hint on launch
│   │   │       └── GroupRunRow.tsx                     # StateChip → StatusBadge + compact
│   │   │                                               #   AnalysisRunTimeline
│   │   ├── training/SessionStatusBadge.tsx             # → StatusBadge adapter (was Badge-bypass)
│   │   ├── consent/ConsentStatusPanel.tsx              # → 2× StatusBadge adapters (incl. AI pill)
│   │   ├── athletes/ai/
│   │   │   ├── DistributionChart.tsx                   # grid/roles/labels/table-twin per contract
│   │   │   ├── EvolutionChart.tsx                      # grid/roles/championship-dot/table-twin
│   │   │   └── AthleteAIAnalysisTab.tsx                # rename header + "Lanzar"→"Analizar con IA"
│   │   ├── ai/AnalysisRunTimeline.tsx                  # ADD variant="compact"
│   │   ├── competitions/chat/CompetitionChatPanel.tsx  # add non-persistence caption
│   │   ├── technique/{CatalogGrid,FilterBar,ExerciseCard}.tsx   # re-point at components/shared/*
│   │   └── strength/{CatalogGrid,FilterBar,ExerciseCard}.tsx    # re-point at components/shared/*
│   ├── routes/
│   │   ├── training/{AthleteNewslettersDashboardPage,SessionAssistantPage}.tsx   # rename + StatusBadge
│   │   ├── admin/AIHealthPage.tsx                      # unaffected (different, existing endpoint)
│   │   ├── technique/**, strength/**, intervals/**, anxiety/**   # slate-* → charcoal/mid-gray
│   │   │                                               #   (32 files post-029; see research.md R4)
│   │   ├── ProtectedRoute.tsx                          # optional: stray slate-600 fix
│   │   └── ...
│   ├── components/athletes/MorphologyCard.tsx          # optional: stray slate-100/800 fix
│   ├── lib/insights.ts                                 # confidenceStatus adapter (was confidenceVariant);
│   │                                                    #   CARRERA_TIER "CD" → tier "A" (R2)
│   └── hooks/ai/useAIStatus.ts                         # NEW — GET /api/ai/status
backend/
├── app/
│   ├── routers/ai.py                # ADD: GET /status (coach+admin), reuses check_budget's query
│   │                                 #   + runner.has_capacity()
│   ├── schemas/ai.py                # ADD: AIStatusResponse
│   └── services/race/ai/
│       ├── budget_guard.py          # reused as-is (no behavior change) — new endpoint calls its
│       │                            #   query helper, not check_budget() itself (read, not enforce)
│       └── runner.py                # reused as-is (has_capacity(), get_active_run_count())
└── tests/
    └── routers/test_ai_status.py    # NEW — happy path, RBAC-negative, exhausted-consistency property test
```

**Structure Decision**: Existing web-app monorepo (`frontend/` + `backend/`), unchanged. All new shared frontend components extend `frontend/src/components/shared/` (the location 028 establishes for `StatusBadge` et al.) — no new top-level directory. The one backend addition follows the existing `app/routers/ai.py` + `app/schemas/ai.py` + `app/services/race/ai/` layout exactly, adding one route function that composes two already-existing, already-tested internal helpers rather than new business logic.

## Complexity Tracking

> No constitution violations. No new dependency, no schema change, no new architectural pattern — nothing to justify here.
