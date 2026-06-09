# Implementation Plan: Faithful, Grounded AI Insights for Competitions

**Branch**: `011-ai-insights-grounding` | **Date**: 2026-06-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/011-ai-insights-grounding/spec.md`

## Summary

The competitions AI pipeline (feature 010) fabricates race conditions, analyzes every athlete as Pre-PHV/Bambino, reviews only the first draft of a batch, and persists a hardcoded "medium" confidence. The fix is a grounding pass over the existing LangGraph-style pipeline in `backend/app/services/race/ai/`:

1. **Load real data into the graph state**: `load_race_data` additionally fetches each launched event's recorded conditions (`climate`, `temperature_c`, `surface_condition`, `altitude_msnm`, `weather_notes` — already on `RaceEvent`); the routers inject the athlete's real `ltad_group` and latest `maturation_status` (from anthropometric records) into `initial_state`.
2. **Thread it to the prompts**: `AnalysisInput` gains explicit `race_meta` (per-válida) and `maturation_status` fields (today both are dead reads from `podium_context`); `race_analyst_v2.md` renders conditions only when provided and gains an anti-fabrication veto ("PROHIBIDO mencionar clima/pista si no se proveen datos").
3. **Critic v2**: new `race_critic_v2.md` prompt validating the v2 section structure, receiving the per-draft ground truth (conditions + result rows) to flag contradictions; the critic node iterates over `per_valida_drafts` instead of only `draft_analysis`.
4. **Computed confidence**: a deterministic Python function maps (critic verdict, data completeness) → `InsightConfidence` per draft; `persist_insight` stores the computed value per row instead of the constant default.
5. **Chat grounding**: a new chat tool exposes recorded event conditions; the chat prompt instructs "answer only from recorded data; say 'sin registro' when absent".
6. **Re-generate**: backend replacement already exists (`deprecate_previous_active` deactivates the prior active insight per athlete/season/válida on approved persist); add a "Regenerar" affordance on the insight row in the frontend that re-launches that válida, plus failure-safe messaging.

No new tables, no Alembic migration: per-draft critic verdicts and grounding-input snapshots ride in the existing `metrics_snapshot_json` (additive keys), and `AthleteAiInsight.confidence` already exists.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async (aiomysql), custom LangGraph-style graph (`app/services/race/ai/graph.py`), LangChain tool-calling for chat, Gemini (`AI_PROVIDER=google`, `gemini-2.5-flash-lite`), Jinja2 markdown prompts; frontend: Vite, shadcn/ui, Tailwind, TanStack Query

**Storage**: MySQL 8.4 (Hostinger prod). No schema changes — `race_events` condition columns and `athlete_ai_insights.confidence` already exist; new per-draft data is additive JSON inside `metrics_snapshot_json`

**Testing**: backend `pytest` + `httpx.AsyncClient` + `aiosqlite`; frontend `vitest` + Testing Library + `jest-axe`

**Target Platform**: Render (free tier, Docker, Oregon) backend; web SPA frontend

**Project Type**: Web application (backend + frontend)

**Performance Goals**: No new endpoints; graph runs are async background jobs. Added queries in `load_race_data` reuse the already-loaded events list (no N+1). p95 budgets of existing endpoints unaffected

**Constraints**: `AI_LOG_PROMPTS=false` in prod; anonymization must cover `weather_notes` free text before it reaches the LLM; product copy stays español neutro (Colombia); prompt token growth must stay within `AI_MAX_TOKENS=8192`

**Scale/Scope**: ~6 graph/agent modules, 3 prompt templates (2 edited, 1 new), 2 routers, 1-2 frontend components, plus tests. Single club, dozens of athletes, ≤4 drafts per run

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan satisfies it |
|---|---|
| **I. Code Quality** | No new runtime dependencies. Changes extend existing modules in place (`load_race_data`, `analyst.py`, `critic.py`, `persist_insight.py`); dead reads (`podium_context.get("race_meta")`) are replaced by explicit typed fields on `AnalysisInput`. `ruff` + `mypy` (backend) and `eslint` + `tsc` (frontend) must pass. |
| **II. Testing (NON-NEGOTIABLE)** | This is a bug fix: every defect lands with a regression test that fails on unfixed code — (a) conditions grounding (prompt context contains recorded conditions; absent → no conditions variables), (b) maturation/LTAD no longer default, (c) critic covers N drafts, (d) confidence varies with inputs. Privacy invariants: test that `weather_notes` PII is anonymized before LLM and that real names never appear in output (existing property tests extended). Frontend: vitest for the Regenerar affordance + a11y via jest-axe. |
| **III. UX Consistency** | Product-facing strings (Regenerar button, confidence labels, chat "sin registro" answers) in español neutro. Reuses existing shadcn/ui components and the existing confidence badge semantics (amber=media etc.). Failure of re-generation surfaces an explicit error state, never silent. |
| **IV. Performance** | Conditions come from the events list `load_race_data` already loads (cached `load_events`) — zero extra round-trips in the common path; one extra query for the latest anthropometric record per run (single athlete, indexed FK). No frontend bundle growth beyond a small button/menu item. |
| **Privacy gates** | Maturation status and conditions flow through the existing `anonymize` node; `weather_notes` is scrubbed with the existing guardrails name-redaction before prompt assembly. No PII in logs; `data-privacy-guard` audit applies (athlete-identifiable data is read). |

**Gate result**: PASS — no violations to justify; Complexity Tracking left empty.

## Project Structure

### Documentation (this feature)

```text
specs/011-ai-insights-grounding/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── graph-state.md   # Graph state + AnalysisInput contract changes
│   └── prompt-variables.md  # Jinja2 variable contracts for the 3 prompts
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── routers/
│   │   ├── athlete_race_analysis.py      # inject ltad_group + maturation_status into initial_state
│   │   └── race_analysis.py              # same injection for the legacy/global launch path
│   ├── services/race/
│   │   ├── queries.py                    # fetch_event_conditions (per event set)
│   │   ├── schemas.py                    # AnalysisInput: +race_meta, +maturation_status
│   │   ├── agents/
│   │   │   ├── analyst.py                # _build_v2_context: explicit fields, drop dead podium_context reads
│   │   │   ├── critic.py                 # v2 verdict per draft, ground-truth aware
│   │   │   └── chat.py                   # new tool: obtener_condiciones_evento
│   │   ├── ai/
│   │   │   ├── confidence.py             # NEW: deterministic confidence computation
│   │   │   └── nodes/
│   │   │       ├── load_race_data.py     # + event_conditions per valida_num
│   │   │       ├── anonymize.py          # scrub weather_notes free text
│   │   │       ├── analyst_agent.py      # thread race_meta/maturation per válida
│   │   │       ├── critic_agent.py       # iterate per_valida_drafts → per_valida_verdicts
│   │   │       └── persist_insight.py    # computed confidence + verdicts in snapshot
│   │   └── prompts/
│   │       ├── race_analyst_v2.md        # conditional conditions + anti-fabrication veto
│   │       ├── race_critic_v2.md         # NEW: v2 sections + ground-truth contradiction checks
│   │       └── race_chat_v1.md           # grounding rule for conditions questions
│   └── tests/                            # regression + privacy tests (see Constitution II)
frontend/
└── src/components/athletes/ai/
    ├── InsightsTimeline.tsx              # "Regenerar" affordance on insight row
    └── __tests__/                        # vitest + jest-axe
```

**Structure Decision**: Web application layout already in place (`backend/` + `frontend/`); all changes land inside the existing `services/race` AI pipeline and the athletes AI components — no new top-level modules except `ai/confidence.py`.

## Complexity Tracking

*(empty — Constitution Check passed without violations)*
