# Implementation Plan: Season evolution charts read cup rounds and championships as separate comparison groups

**Branch**: `039-season-comparison-groups` (spec directory; no git branch created at planning time by owner request — work is on `main`) | **Date**: 2026-09-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/039-season-comparison-groups/spec.md`

## Summary

The three season charts (position per round, gap to the winner, accumulated points) and every consumer of the athlete's season progression mix Copa Valle rounds with the departmental and national championships, which race a different field. The fix introduces a **derived comparison group** (cup = its series; championship = its own single-race group) computed from `race_series.kind` / `id` / `level` with **no schema change**, and makes every consumer read one group at a time: the newsletter renders one evolution block per cup plus a "Campeonatos" card block; the athlete-detail evolution chart gets a "Competencia" selector backed by a `series_id` filter on `GET /evolution`; the AI pipeline receives cup progression and championship readings separately, keys races by `event_id` instead of `valida_num`, and the per-race prompt gains the non-comparability rule the season-summary prompt already has. Multi-cup seasons are supported by construction.

## Technical Context

**Language/Version**: Python 3.13 (backend), TypeScript 5 / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async (aiomysql / aiosqlite), Pydantic v2, pandas, Jinja2 + WeasyPrint (PDF), LangGraph (race AI pipeline), Gemini via `RACE_AI_*`; Vite, TanStack Query, recharts ^3.8.1, shadcn/ui + Tailwind v4, MSW, vitest, jest-axe

**Storage**: MySQL 8.4 (prod, Hostinger) — read-only for this feature; no Alembic migration. `athlete_newsletters.metrics_snapshot` JSON gains new keys inside `email_blocks.race_results` and `pdf_only_blocks.charts_context` (additive, backward compatible for already-stored snapshots).

**Testing**: pytest (offline aiosqlite default lane; `-m mysql` for the raw-SQL dialect test; `-m golden` for the race-analyst eval), vitest + Testing Library + MSW, jest-axe, Playwright (not required here)

**Target Platform**: Render free tier (backend), Cloudflare Pages SPA; coach on tablet, parents on mid-tier Android over 3G/4G

**Project Type**: Web application (backend + frontend monorepo)

**Performance Goals**: `GET /evolution` stays a single SQL round-trip (p95 ≤ 500 ms per constitution IV) — grouping is done in Python over O(tens) rows; newsletter generation adds no extra query beyond the field-metrics computation already loaded for the AI context; frontend selector switch renders from cached query data in < 1 s (SC-007)

**Constraints**: minors' privacy (no names in logs/prompts; championship readings are counts and percentages only); español neutro for all new copy; `race_analyst_v2` must remain a valid rollback; golden eval composite ≥ 0.75 (`RACE_EVAL_THRESHOLD`) is a blocking gate; `EvolutionPoint.valida_num` kept for back-compat

**Scale/Scope**: ~30 athletes, ≤ 10 races per season per athlete, 1 cup + ≤ 2 championships today (design for N cups); 4 backend services, 1 endpoint (additive), 1 PDF template + 1 new Jinja partial, 3 frontend components, 2 prompts, golden dataset +1 case

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan satisfies it | Status |
|---|---|---|
| I. Code Quality | One derivation helper (`comparison_groups.py`) replaces three ad-hoc kind checks (newsletter labels, chart context, AI lookup) — rule of three met. Public services get docstrings. `ruff check` + `tsc --noEmit` gate. | PASS |
| II. Testing (NON-NEGOTIABLE) | Every touched service gets happy + negative tests; router gets a parent-denied test with `series_id`; regression tests for the three latent bugs (valida_num collision in AI lookup, hardcoded "Cto. Dep." dot, date-based dedupe); jest-axe on `EvolutionChart` with the new selector; privacy invariants (no names in championship readings) asserted. Golden eval re-run required before close. | PASS |
| III. UX Consistency | New copy in español neutro with diacritics; selector reuses the exact control pattern already in `EvolutionChart` (48 px targets); loading/empty/error states defined for the selector and card (FR-021); status colors untouched; championship card follows the dataviz stat-tile contract (text in text tokens, mark carries identity). | PASS |
| IV. Performance | No new endpoint; `GET /evolution` remains one query (filter + groups computed in Python). No new heavy frontend module; recharts already lazy-loaded with the Insights tab. PDF adds one small partial per championship. | PASS |
| V. Youth Psych. Safeguards | Not applicable (no psychological instrument). Mastery-climate wording still applies to the AI rule text: it forbids position comparison across fields, it does not add result goals. | N/A |
| Quality gate — Privacy | Championship readings expose position, field size, gap %, percentile of the athlete's own result only; no third-party names; no new PII in logs or prompts. `data-privacy-guard` audit scheduled in tasks. | PASS |
| Quality gate — Stack discipline | No new runtime dependency. | PASS |
| Workflow — Branching | Owner explicitly asked for no branch during spec/plan. Implementation MUST start on `feat/039-season-comparison-groups` (constitution: direct commits to `main` are for emergencies). Recorded here so `/speckit-tasks` includes the branch step. | DEVIATION (documented, owner decision) |

**Post-design re-check (after Phase 1)**: unchanged — no violation introduced by the contracts; the only deviation is the branching timing above.

## Project Structure

### Documentation (this feature)

```text
specs/039-season-comparison-groups/
├── plan.md              # This file
├── spec.md
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── evolution-api.md         # GET /evolution + list_athlete_races additive changes
│   ├── newsletter-context.md    # race_results / charts_context snapshot shape
│   └── ai-context.md            # LangGraph state + prompt inputs
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks output (not created here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── services/race/
│   │   ├── comparison_groups.py        # NEW — pure helpers: build_comparison_group, split_progression, group_label
│   │   ├── analytics.py                # athlete_progression: + event_id, series_id, series_name, comparison_group
│   │   ├── analytics_charts.py         # build_evolution(series_id=None) + groups; list_athlete_races + series fields
│   │   ├── race_labels.py              # unchanged (reused)
│   │   ├── field_metrics.py            # unchanged (reused for championship readings)
│   │   ├── agents/analyst.py           # _progression_to_md: + serie column; season table unchanged
│   │   └── ai/nodes/
│   │       ├── compute_metrics.py      # progression split; _compute_season_comparative by series + event_id; _event_label → build_race_label
│   │       ├── analyst_agent.py        # race_row / field_metrics lookup by event_id (anchored) instead of valida_num
│   │       └── load_race_data.py       # full_season_records: + series_id, series_kind (already has event_id)
│   ├── services/race/prompts/
│   │   ├── race_analyst_v3.md          # + rule: championship not comparable with cup rounds
│   │   └── race_season_summary_v3.md   # already has the rule — verify only
│   ├── services/training/newsletter_builder.py   # _build_race_block: cups[] + championships[]; _build_charts_context per cup
│   ├── schemas/athlete_race_analysis.py           # EvolutionPoint/EvolutionResponse/RaceParticipationOption additive fields
│   └── routers/athlete_race_analysis.py           # get_evolution: + series_id query param
├── templates/documents/pdf/
│   ├── athlete_stage_log.html                     # loop per cup; "Campeonatos" block
│   └── charts/championship_card.html.jinja        # NEW — stat-tile partial
├── evals/race_analyst/golden_v3/case_009.json     # NEW — CD + CN case
└── tests/
    ├── services/race/test_comparison_groups.py    # NEW
    ├── services/race/test_analytics.py, test_analytics_charts.py, test_mysql_dialect.py
    ├── services/race/ai/nodes/test_compute_metrics.py, services/test_compute_metrics_season.py
    ├── services/training/test_newsletter_builder.py, test_newsletter_builder_024.py
    └── routers/test_athlete_race_analysis_evolution_groups.py   # NEW — RBAC + series_id

frontend/src/
├── types/athleteRaceAnalysis.types.ts             # EvolutionPoint/Response/ComparisonGroupOption
├── api/athleteRaceAnalysis.ts                     # getAthleteEvolution(..., seriesId?)
├── hooks/athletes/useAthleteEvolution.ts          # queryKey + seriesId
├── lib/insights.ts                                # validaLabel(series_level)
├── components/athletes/ai/
│   ├── EvolutionChart.tsx                         # "Competencia" selector; ChampionshipReadingCard; level-aware dot
│   ├── ChampionshipReadingCard.tsx                # NEW — stat tile (position / pelotón / gap / percentil)
│   ├── MiniSparkline.tsx                          # first cup only; CD/CN by level
│   └── __tests__/EvolutionChart.test.tsx, MiniSparkline.test.tsx, a11y.v2.test.tsx
└── test/msw/athleteRaceAnalysisHandlers.ts        # mockEvolution with groups + series fields
```

**Structure Decision**: Web application layout already in place (`backend/` + `frontend/`). No new top-level module; one new pure-helper module in `services/race/` and one new presentational component in `components/athletes/ai/`.

## Phase 0 — Research summary

See [research.md](./research.md). All Technical Context items were resolvable from the codebase, Context7 (recharts 3 `DotItemDotProps`), the shadcn registry state of the project, and the dataviz skill (stat-tile form for single-race readings). No `NEEDS CLARIFICATION` remains.

## Phase 1 — Design summary

- **Data model**: [data-model.md](./data-model.md) — `ComparisonGroup` (derived), `ChampionshipReading`, extended `ProgressionRow`, extended `EvolutionPoint` / `EvolutionResponse`.
- **Contracts**: [contracts/evolution-api.md](./contracts/evolution-api.md), [contracts/newsletter-context.md](./contracts/newsletter-context.md), [contracts/ai-context.md](./contracts/ai-context.md).
- **Validation guide**: [quickstart.md](./quickstart.md).
- **Agent context**: `CLAUDE.md` Spec Kit block now points to this plan.

## Delivery phases (input for /speckit-tasks)

1. **Backend source of truth** — `comparison_groups.py`, `athlete_progression` columns, `build_evolution(series_id)` + `groups`, `list_athlete_races` fields, schemas, router param, tests (offline + mysql dialect), RBAC denied-path test. Response stays backward compatible.
2. **Newsletter** — `_build_race_block` split (cups / championships, dedupe by `event_id`), `_build_charts_context` per cup, PDF template loop + `championship_card` partial, copy review, snapshot back-compat test, regeneration with the real dataset (`-m mysql`, reuse the pending SC-1 of feature 038).
3. **Frontend** — types/api/hook, `EvolutionChart` selector + `ChampionshipReadingCard`, level-aware `ChampionshipDot`, `validaLabel` / `MiniSparkline` level fix, MSW mocks, vitest + jest-axe.
4. **AI pipeline** — progression split, `event_id`-keyed lookups, `_compute_season_comparative` by series, `_event_label` removal, `_progression_to_md` serie column, prompt rule, golden case 009, `pytest -m golden` ≥ 0.75.
5. **Close** — `data-privacy-guard` audit, `docs/implementation-status.md` + `docs/technical-notes.md` + `docs/06-parents/003-newsletter-improvements.md`, post-deploy smoke (`/health` + `GET /evolution?series_id=`).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Branching deviation: spec + plan authored on `main` without a feature branch | Explicit owner request during planning ("no crear ramas") | Creating the branch anyway would override an explicit instruction; the deviation is time-boxed — implementation tasks start with the branch step |
