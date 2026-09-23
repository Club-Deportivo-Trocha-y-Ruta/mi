# Implementation Plan: Competitions in one place

**Branch**: `main` (owner decision 2026-09-23 — no feature branch; auto-commit hooks skipped) | **Date**: 2026-09-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/045-competitions-one-place/spec.md`

## Summary

The feature condenses every race surface into three places:
- the «Competencias» area, with three sections (competitions, «Temporada», «Cargas e identidades»);
- one athlete tab «Carreras» for coach and family, with the views Progresión, Análisis IA and Comparar;
- one server-side metrics engine.

Technically there are five changes:
1. **Make `field_metrics.py` the only metrics engine.** Percentile becomes time-based, and the gap to the podium and the timed-finisher count are added. The engine applies the gate of at least 5 finishers itself and gains a category batch mode. The evolution, distribution and results reads delegate to it (research R-01..R-04).
2. **Rebuild the athlete tab** from existing components: history, championship cards, insights, HITL, comparator. Each view is its own lazy chunk, the tab address carries `view=` and `insight=`, and the old tab keys stay as aliases (R-07).
3. **Scope the identity gate to the import being committed** (no migration). Make imports resumable and discardable; this needs one enum migration (R-08, R-09).
4. **Extend the coach summary** with three counts. They feed «Pendientes» and the new inbox badge. Stale and awaiting-approval analyses are listed under «Temporada» (R-10, R-11).
5. **Enforce the family safeguards server-side.** Parent payloads never carry winner or podium gaps, and the approval payload carries `family_gap_mentions` (R-05, R-06).

Phase 0 and phase 0b fixes are already in the working tree. This plan builds on them.

## Technical Context

**Language/Version**: Python 3.13 (backend venv currently runs 3.14), TypeScript 5 / React 19

**Primary Dependencies**:
- Backend: FastAPI, SQLAlchemy 2 async, Pydantic v2, Alembic.
- Frontend: TanStack Query, React Router, shadcn/ui + Tailwind v4, RHF + Zod, Recharts (existing charts).
- No new runtime dependency.

**Storage**: MySQL 8.4 (Hostinger). One Alembic migration: the `race_imports.status` enum gains `discarded`.

**Testing**:
- pytest in the default lane (aiosqlite) plus the deferred `-m mysql` and `-m golden` lanes;
- vitest + Testing Library + MSW + jest-axe;
- Playwright (deferred).

**Target Platform**: coach on a tablet (web, field conditions); families on mid-tier Android over 3G/4G; backend on the Render free tier (cold start about 50 s).

**Project Type**: web application (`backend/` + `frontend/`)

**Performance Goals**:
- Family «Carreras» LCP ≤ 3.5 s on simulated 3G (data-dense route).
- First paint fires only the active view's request.
- The engine batch for one category is O(n) per category, with no N+1.
- Read endpoints at p95 ≤ 500 ms.

**Constraints**:
- **Ley 1581**: no minor PII in logs, fixtures or prompts.
- **Parent data filtering**: parent reads are filtered to the parent's own athletes, and family payloads **omit** winner and podium fields.
- **Code sharing**: another session is migrating design tokens across about 240 frontend files at the same time. Edit with targeted replacements, re-read before every edit, and never rewrite whole files.

**Scale/Scope**:
- About 20 club athletes and about 25 cup válidas with full fields across 2024–2026, plus a few championships.
- About 12 backend modules and about 45 frontend files are touched.
- About 40 unit test files and about 7 e2e specs are affected.

## Constitution Check

*Gate before research: PASS with one justified deviation (branching). Re-checked after design: PASS.*

| Principle | How 045 complies |
|---|---|
| **I. Code quality** | Removes three duplicated gap computations and two extra percentile formulas (rule of three) and deletes `raceMetrics.ts`. The public engine functions keep and extend their docstrings. `ruff` and `tsc --noEmit` must be clean on changed files. |
| **II. Testing (NON-NEGOTIABLE)** | Every router change gets happy-path and denied tests (parent 403/omission, other club 404). Every bug fix gets a failing-first regression test: the evolution percentile without the gate (R-01), the parent podium-gap leak and raw statuses (phase 0b), and the whole-queue gate (R-08). Privacy invariants: parent payloads omit winner and podium fields. jest-axe runs on the merged tab, the inbox, «Temporada» and the approval card. |
| **III. UX consistency** | One glossary (`contracts/ui-copy.md`), español neutro with diacritics. Touch targets ≥ 48 px on the named surfaces. Loading, empty and error states for every new async view. Semantic badge colours: amber for pending. |
| **IV. Performance** | One `React.lazy` chunk per view. Queries move into their view. Engine batch mode, with no per-row queries. A query-count test on the results read. |
| **V. Youth safeguards** | Families never see winner or podium gaps (enforced server-side). Median gap is the default. AI text is flagged to the coach before approval. No automatic messages to families: no approval email, and the bitácora notice is inserted by the coach. |
| **Quality gates** | `data-privacy-guard` audit before closing. `data-platform-lead` validation of the identity rule. AI guardrails unchanged. `AI_LOG_PROMPTS` untouched. |
| **Workflow: branching** | ⚠ Deviation: the work happens on `main` without a feature branch (see Complexity Tracking). |

## Project Structure

### Documentation (this feature)

```text
specs/045-competitions-one-place/
├── plan.md
├── research.md          # R-01..R-15 decisions
├── data-model.md        # MetricSet, RaceImport.discarded, summary counts, HITL field
├── quickstart.md        # offline lanes + scenario checks + deferred lanes
├── contracts/
│   ├── api.md           # changed/new endpoints, parent omissions, 409 body
│   ├── ui-routes.md     # addresses, aliases, redirects, menu
│   └── ui-copy.md       # glossary, warnings, bitácora notice (es-CO)
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── app/services/race/field_metrics.py        # THE engine (time percentile, podium gap, timed_finishers, batch)
├── app/services/race/analytics_charts.py     # build_evolution / build_distribution delegate to the engine
├── app/services/race/history.py              # simplified (engine gates)
├── app/services/race/results_read.py         # per-row MetricSet via batch mode
├── app/services/race/identity_review.py      # helper: pending candidates for an import's record keys
├── app/services/race/run_staleness.py        # dismiss-stale wrapper + audit
├── app/services/dashboard_summary.py         # 3 new counts
├── app/services/newsletter/…                 # stage_log_builder / newsletter_builder → median gap (family)
├── app/routers/race_imports.py               # per-import gate, GET one, POST discard
├── app/routers/athlete_race_analysis.py      # parent omissions, family_gap_mentions, metric 403
├── app/routers/race_analysis.py              # POST dismiss-stale
├── app/schemas/{athlete_race_analysis,dashboard,race_import}.py
├── app/models/race_import.py                 # RaceImportStatus.discarded
├── alembic/versions/<new>_race_import_discarded.py
└── tests/…                                   # engine, consistency, gate, imports, summary, redaction, mentions

frontend/src/
├── routes/athletes/AthleteDetailPage.tsx       # «Carreras» tab, view/insight params, aliases
├── routes/parents/MyAthleteDetailPage.tsx      # family «Carreras», aliases
├── components/athletes/races/                  # NEW: CarrerasTab (shell), ProgressionView, AnalysisView, CompareView (lazy)
├── components/race/history/*                   # HistoryChart gains metric selector; HistoryProgressionCard → Progresión
├── components/athletes/ai/*                    # re-homed into AnalysisView / CompareView; EvolutionChart retired from the tab
├── components/ai/HITLApprovalCard.tsx          # gap warning, 48 px targets, copy
├── routes/competitions/CompetitionImportsPage.tsx  # NEW «Cargas e identidades» (sections)
├── routes/competitions/SeasonInsightsPage.tsx  # «Temporada» + analyses list (por aprobar / desactualizados)
├── routes/competitions/CompetitionDetailPage.tsx   # «Circuito y condiciones» tab, alias
├── components/competitions/import/ImportWizard.tsx # resume from ?import=<id>, discard
├── components/competitions/results/ResultsTable.tsx # per-row metrics (role-aware)
├── components/dashboard/PendingInbox.tsx       # 2 new rows, fixed destinations
├── config/navigation.ts + hooks/useNavBadges.ts # «Competencias» items + badge
├── App.tsx                                     # new routes + redirects
└── lib/raceMetrics.ts                          # DELETED (ComparatorPanel reads server points)
```

**Structure Decision**: the existing web-app layout (`backend/`, `frontend/`). The only new frontend folder is `components/athletes/races/`, for the merged tab's shell and views. Everything else is modified in place.

## Delivery waves

Waves follow the dynamic-workflow convention. Each wave has disjoint file ownership per agent and a gate run between waves (pytest + ruff + typecheck + vitest).

1. **W1 · Engine** (backend only): engine extensions, delegation from evolution, distribution, history and results, family omissions in the API, the consistency test (SC-002), and the metric 403 for parents.
2. **W2 · Loads and pending** (backend): the per-import gate plus its 409 body, `GET` and discard of imports, the migration, the three summary counts, the dismiss-stale endpoint, and `family_gap_mentions`. Then the data-platform-lead review of R-08.
3. **W3 · Athlete «Carreras»** (frontend): the shell, the three lazy views, the params and aliases, retiring `EvolutionChart` from the tab, deleting `raceMetrics.ts`, and the family variant.
4. **W4 · Competencias area** (frontend): navigation and badge, the «Cargas e identidades» page and redirects, the resumable wizard, «Temporada» with the analyses list, the «Circuito y condiciones» tab, «Pendientes» rows, per-row results metrics, and the vocabulary sweep plus 48 px targets.
5. **W5 · Family copy and closing**: bitácora and newsletter median gap, the notice insertion, and the approval warning UI. Then e2e spec updates, the `data-privacy-guard` audit, docs (`implementation-status.md`, `technical-notes.md`, a `docs/NN-*` note) and the deferred-lane report.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Work on `main` without a feature branch (Development Workflow: branching) | Explicit owner decision on 2026-09-23 ("Todo en main, sin ramas"). Feature 044 set the same precedent. Phase-0 fixes that 045 builds on already live uncommitted on `main` | A `feat/045-…` branch was offered and declined by the owner. Mitigation: commits stay atomic per wave and use Conventional Commits; nothing is pushed without the owner's instruction; the owner reviews before the Render auto-deploy |
| One new enum value plus migration (`discarded`) | FR-032 needs an explicit discard that the inbox must not show as an error | Reusing `failed` conflates abandoned imports with broken ones (research R-09) |
