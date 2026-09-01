# Implementation Plan: AI Insights Tab — Full-Stack Review

**Branch**: `036-ai-insights-tab-review` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/036-ai-insights-tab-review/spec.md`

## Summary

Seven prioritised stories fixing the athlete AI Insights tab: a missing consent gate (legal, blocking), templated AI output that carries no analytical value, cross-athlete state leakage, error placeholders indistinguishable from real analyses, several false or ambiguous on-screen claims, mobile and accessibility failures, and a test suite whose high coverage hides the flows that actually broke. The work is sequenced so that each wave is independently shippable, with the legal gate first and the test safety net woven through rather than deferred to the end.

## Technical Context

**Language/Version**: Python 3.13 (backend), TypeScript 5 / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async + aiomysql, Pydantic v2, Alembic, LangGraph; React 19, TanStack Query, shadcn/ui + Tailwind v4, recharts, React Hook Form + Zod

**Storage**: MySQL 8.4 (Hostinger). Agentic checkpointing in sqlite.

**Testing**: pytest + httpx.AsyncClient + aiosqlite (backend); vitest + Testing Library + MSW + jest-axe (frontend); Playwright (e2e); `backend/evals/race_analyst/` golden eval, blocking in CI at composite ≥ 0.75

**Target Platform**: Backend on Render free tier (cold start ~50 s); frontend on Cloudflare Pages. Coach on tablet, parent on mid-range Android over 3G/4G.

**Project Type**: Web app — modular monolith backend, React SPA frontend

**Constraints**: No real name, birth date or medical detail of a minor in logs, commits, git-committed fixtures or AI-provider prompts. `AI_LOG_PROMPTS=false` in production. Touch targets ≥ 48×48. Zero jest-axe violations on page- and dialog-level components.

**Scale/Scope**: ~5,400 lines of frontend components under review, 9 query hooks, 8 REST endpoints, one LangGraph pipeline. Club-scale data volumes (tens of athletes, ~7 races per season).

## Constitution Check

| Principle | Status | Note |
|---|---|---|
| I — Code quality | Addressed | US3–US5 remove duplicated helpers and dead contracts; large-component decomposition is deliberately kept as refactor-in-place, not a rewrite |
| II — Testing (NON-NEGOTIABLE) | Addressed | US7 is a first-class story, not a phase; each earlier story ships with the test that would have caught it |
| III — UX consistency | Addressed | US5 and US6 |
| IV — Performance budgets | Watch | Lazy-loading the tab (it pulls `recharts` into every `/athletes/:id` visit today) is in scope; no new runtime dependency is introduced |
| V — Youth psychological safeguards | Watch | US2 acceptance scenario 4 forbids body judgement and diagnostic language. Open Question 2 (parent access to absolute times and podium gaps) must be decided by the club before US2 ships. The missing AI-consent gate is a confirmed critical finding tracked outside this feature, not resolved here — see Evidence base in `spec.md` |

**Verdict**: proceed. The consent-gate work that would otherwise sit in Wave 1 is tracked separately, outside this feature; nothing in Waves 2–6 depends on it.

## Project Structure

### Documentation

```
specs/036-ai-insights-tab-review/
├── spec.md          # this feature's what and why
├── plan.md          # this file
├── research.md      # Phase 0 — budget calibration, Render ephemerality, Langfuse, prompt technique
├── data-model.md    # Phase 1 — entity deltas (is_fallback, run reconciliation, contract fixes)
├── contracts/
│   └── athlete-race-analysis-api.md  # the 8 endpoints + contract changes
├── quickstart.md    # per-wave validation guide
└── tasks.md         # dependency-ordered task list by wave
```

### Source files in scope

```
backend/app/
├── routers/athlete_race_analysis.py       # 8 endpoints; consent gate, ordering, role filtering
├── routers/ai.py                          # reference pattern for the consent gate (do not change)
├── services/privacy.py                    # assert_ai_consent_* helpers
├── services/race/
│   ├── ai/fallback.py                     # US4 — mark fallback rows
│   ├── ai/runner.py                       # US3/US4 — in-memory run registry
│   ├── ai/grounding.py                    # US2 — what context reaches the model
│   ├── agents/analyst.py, critic.py       # US2 — prompt and confidence scoring
│   └── analytics_charts.py                # US5 — display_name exposure
├── models/athlete_ai_insight.py           # US4 — needs a way to mark a failed analysis
└── main.py                                # US3 — orphan run reconciliation on startup

frontend/src/
├── routes/athletes/AthleteDetailPage.tsx  # US3 — key={athlete.id}; US6 — lazy import
├── components/athletes/ai/                # the tab and its five sub-views
├── components/ai/                          # run timeline, HITL card, markdown viewer
├── hooks/ai/useRaceRun.ts                 # polling, 304 branch, invalidation predicate
├── hooks/athletes/                        # 9 query hooks
├── lib/insights.ts, lib/raceCalendar.ts   # US5 — the two válida label functions
└── api/athleteRaceAnalysis.ts             # US5 — SeasonSummaryResponse contract
```

## Design decisions

### US2 — Analysis quality

Root cause is established, not hypothesised. The pipeline audit found three compounding causes, all verified:

**(a) The prompt asks for a checklist, not an analysis.** `backend/app/services/race/prompts/race_analyst_v2.md:44` literally instructs the model to include five fields — "posición final, tiempo de carrera (formato hh:mm:ss), gap al líder, número de vueltas completadas, si hubo abandono". Line 46 then requires citing the time in `hh:mm:ss` "en la narrativa", which the model satisfies by restating a figure already given. Line 47 permits exactly five verbs. Neither prompt version contains a single few-shot example. The result is the only safe combinatorial output left: subject + permitted verb + raw datum, once per field. The prompt is an excellent *compliance* artefact and a poor *analysis* artefact — it specifies exhaustively what not to say and never models how to connect anything.

**(b) The lap sentence is a fabrication forced by the prompt.** Line 44 demands "número de vueltas completadas", but no lap field exists anywhere in `backend/app/services/race/schemas.py` — a grep for `lap` returns nothing. The model cannot decline a required field, so it emits the safest sentence that satisfies the instruction without inventing a number: "Alcanzó el número máximo de vueltas previsto para la categoría." It is a mandated hallucination, and no guardrail catches it because there is no ground truth to check it against.

**(c) The N=1 rule suppresses all comparison.** `race_analyst_v2.md:220-245` forbids every cross-race comparison when `is_first_in_season=True`. If the coach analyses one válida at a time — which the generation timestamps of the inspected athlete suggest — each launch may see itself as the first reference and the season history never reaches the prompt, even though feature 010 already computes `season_comparative` and `progression_assessment` and persists them. **Verify how `is_first_in_season` is computed for single-válida launches before touching the prompt**: if that flag is wrong, no prompt change will produce comparison.

Ruled out: the fallback (the observed text matches neither fallback constant) and the critic (it validates factual contradiction and club rules, and has no rule about narrative quality either way).

**The eval is blind, and that comes first.** `backend/tests/evals/test_race_analyst_eval.py:173` calls `agent.invoke` — the **v1** method with the five-section `race_analyst_v1.md` prompt — while production runs `invoke_per_valida` against **v2**. The CI workflow pins `AI_PROVIDER: google` / `AI_MODEL: gemini-2.5-flash-lite` (`.github/workflows/race-eval.yml:53-54`), while production defaults to `anthropic` / `claude-sonnet-5` (`config.py:112`, `_llm.py:33`). The gate that blocks CI at composite ≥ 0.75 has never once exercised the prompt, the method or the model that serve coaches. That is why nothing caught this. Fixing the eval precedes every prompt change.

### US3 — State isolation

`key={athlete.id}` on the tab mount is the minimal correct fix and forces a clean remount. Prefer it over a `useEffect` reset chain, which would need to enumerate every piece of state and would silently rot as state is added. Separately, the backend needs orphan-run reconciliation at startup (`main.py` lifespan), because the run registry is in-memory and Render redeploys on every push to `main`, leaving runs stuck in `running` forever with the client polling indefinitely.

### US4 — Fallback marking

Requires a way to distinguish a fallback row at the data layer. Cheapest honest option is a nullable discriminator on the insight model rather than sniffing the markdown string, which would be brittle. Existing rows can be classified by a one-off backfill matching the known fallback text — acceptable because the string is a compile-time constant in `fallback.py`, not user input. The UI then keys its badge, its checkbox suppression and its retry affordance off that field.

### US5 — Truth on screen

Four independent fixes with one shared root: `validaLabel` still branches on the retired `valida_num === 99`. Migrate the AI payload to `event_id` + `race_series.kind` as features 014/016 did elsewhere, collapse the two label helpers into one (adopt the roman formatting already used by `MiniSparkline`), order history by race date, and change the Distribution selector default to the most recent race. The `display_name` question is a product decision (Open Question 2); until it is made, at minimum correct the subtitle and the docstring so they stop asserting a protection that is not in place.

### US6 — Devices and accessibility

Make the sub-tab overflow visible rather than hidden; enlarge the checkboxes to the 48×48 floor using the pattern feature 032 already proved; add `role="status"`/`aria-live` to the sticky bar; add `axe()` coverage for `HITLApprovalCard` in both resting and dialog-open states. Lazy-load the tab from `AthleteDetailPage` following the pattern the same file already uses for the Progreso tab, which keeps `recharts` out of the initial bundle for every athlete profile visit.

### US7 — Test safety net

The rule for this feature: **each story ships with the test that would have caught its bug**, rather than batching testing into a final wave. The structural gap is that `AthleteAIAnalysisTab.test.tsx` mocks its own subcomponents, so composition logic is untested by construction. New integration tests must mount the real tree and mock only the network via MSW.

## Sequencing

**Wave 1 — Correctness.** US3 and US4. Both are data-integrity bugs with a plausible path to a family-visible incident. Independent of each other; can run in parallel.

**Wave 2 — Truth and trust.** US5. Mostly mechanical once the `valida_num` migration lands; the `display_name` decision may split off if the club needs time.

**Wave 3 — Analysis quality.** US2. Sequenced after the eval is extended (within US2 itself, see the design decision above). This is the largest and least predictable piece of work in this feature.

**Wave 4 — Devices.** US6. Independent of everything above; can be pulled earlier if a UX-focused contributor is available.

US7's tasks are distributed across waves 1–4 rather than forming their own wave, except for the e2e specs, which land last because they need the fixed behaviour to assert against.

## Complexity Tracking

| Item | Why it is not simpler |
|---|---|
| Discriminator column for fallback insights (US4) | String-matching the markdown would be brittle and would break the moment the fallback wording changes. A nullable column plus a one-off backfill is cheaper to reason about and to test. |
| Orphan run reconciliation at startup (US3) | The alternative — a client-side polling timeout only — leaves corrupt rows in the database and hides the problem instead of fixing it. Both are needed; the server-side half is the real fix. |
| Extending the golden eval before touching the prompt (US2) | Iterating the prompt against an eval that already passes on bad output would produce unmeasurable churn. |

## Deferred pending audit

The UX audit returned partially. Its information-architecture conclusion is incorporated (five sub-tabs collapse to three: **Resumen** merging Panorama and Histórico, **Rendimiento** merging Evolución and Distribución with the comparator as a control rather than a separate sheet, and **Analizar con IA**). On review this reverts nothing: BB3 moved the comparator out of the tab list and into a sheet, and it stays in a sheet — it simply hangs off Rendimiento instead of Distribución. The Evolución/Distribución merge was never decided either way in any spec. The merge also dissolves the 400 px sub-tab clipping without a separate cosmetic fix, since three tabs fit without horizontal scroll. Its microcopy table, WCAG target-size findings and flow measurements are still outstanding and will extend wave 5's task list without changing the plan's shape.

One correction from that audit, worth recording because it was reported as a defect and is not one: the turquoise of "Releer último" and "Regenerar" is the product's primary brand colour (`frontend/src/style.css:36`, documented at `frontend/src/components/ui/button.tsx:11`), not an off-palette accent. The real issue there is hierarchy — two primary-weight buttons competing in one card — not colour.
