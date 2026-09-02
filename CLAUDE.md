# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Coach–athlete management platform for **Club Deportivo Trocha y Ruta** — youth XCO mountain-bike cycling (ages 10–15), Valle del Cauca, Colombia. Monorepo: FastAPI backend (`backend/`), React SPA (`frontend/`), numbered feature docs (`docs/`), Spec Kit features (`specs/`).

Three hard rules color everything:

- **Minors' privacy (Ley 1581)**: no real name, birth date, medical detail, or identifying data of a minor in logs, error messages, commit messages, git-committed fixtures, or AI-provider prompts. AI output about minors runs through guardrails (forbidden-names list from DB, word limits, consent gates); `AI_LOG_PROMPTS=false` in production.
- **Secrets stay out of the transcript**: never read, echo, or paste the contents of `.env`, `.env.production`, or any credential file into chat, commit messages, memory files, or logs — the production MySQL password and the AI-provider keys live there. `.env*` is gitignored; keep it that way. Refer to a variable by name (`MYSQL_PASS`), never by value.
- **Language split**: product end-user copy (frontend strings, email/PDF/DOCX templates, notifications) = español neutro (Colombia) with full diacritics; the AI-instruction corpus (this file, `.claude/agents/*`, `docs/**`) = English.

The project constitution at `.specify/memory/constitution.md` is authoritative — five principles: code quality, testing (NON-NEGOTIABLE), UX consistency, performance budgets, youth psychological-assessment safeguards. Plans and PRs are checked against it.

## Commands

### Backend (`backend/`, Python 3.13, venv at `backend/.venv`)

```bash
source .venv/bin/activate
uvicorn app.main:app --reload            # API on :8000, OpenAPI docs at /docs
pytest                                   # default lane — offline, aiosqlite in-memory
pytest tests/test_foo.py::test_name      # single test
pytest -m mysql                          # opt-in: real MySQL via TEST_DATABASE_URL (mysql+aiomysql://…; DB name MUST end in `_test`)
pytest -m integration                    # opt-in: real external APIs
pytest -m golden                         # opt-in: blocking race-analyst golden eval (needs race AI key)
ruff check                               # lint (default rules; ruff installed globally, not in requirements)
alembic upgrade head                     # apply migrations (needs MySQL up)
alembic revision --autogenerate -m "…"   # new migration
mutmut run                               # mutation testing (scope: pyproject [tool.mutmut])
```

### Frontend (`frontend/`)

```bash
npm run dev                              # Vite on :5173, proxies /api /health /static → :8000
npm run build                            # tsc --noEmit + vite build
npm run typecheck
npm test                                 # vitest run (all)
npx vitest run src/path/File.test.tsx    # single file
npm run test:e2e                         # Playwright (starts its own dev server)
npm run test:mutation                    # Stryker
```

There is no ESLint config — `tsc --noEmit` is the static gate.

### Docker

`docker compose up` — backend + MySQL 8.4 + MailHog (UI on :8025). `backend/entrypoint.sh` auto-runs migrations, the CDC LMS seed, the anthropometry backfill, and (when `APP_ENV=development`) demo seed data.

## Architecture

### Backend — modular monolith

`app/routers/*` (one per domain, all mounted in `app/main.py` under `/api/*`) → `app/services/*` (domain logic) → `app/models/*` (SQLAlchemy 2 async over aiomysql) with `app/schemas/*` (Pydantic v2) at the edges.

- **RBAC** is centralized in `app/services/permissions.py` (roles: admin, coach, parent, athlete). Router changes need at least one denied-path test; parent-facing reads are filtered so a parent only ever sees their own athletes' data.
- **Two separate AI stacks** — do not conflate their config:
  - `app/services/ai/` — provider factory (`anthropic` / `openai` / `google` / `fake`, default `google`) on `AI_*` env vars. Powers the session assistant, monthly reports, and newsletters. `AI_ENABLED=false` yields `FakeLLMProvider`. If the Anthropic provider is selected, it must NOT forward `temperature` (Claude 4.6+ returns 400 on non-default sampling params).
  - `app/services/race/ai/` — the LangGraph agentic pipeline itself: `graph.py`, `nodes/`, `runner.py`, `state.py`, `budget_guard.py`, `run_reconciliation.py`. The sibling `app/services/race/agents/` holds only the LLM factory and the provider-facing wrappers (`_llm.py::build_chat_llm`, `analyst.py`, `critic.py`, `chat.py`, `pricing.py`); prompts live in `race/prompts/*.md` and the eval judge/scorer in `race/eval/`. Own `RACE_AI_*` provider config, default `google`, per-role models (feature 037) `RACE_AI_ANALYST_MODEL=gemini-3.8-flash` / `RACE_AI_CRITIC_MODEL=gemini-3.1-flash-lite` (the coach relies on Gemini's free quota; `anthropic`/`claude-sonnet-5` and `openai` are supported alternatives, not the default; the `chat` role has no dedicated variable and still resolves through legacy `RACE_AI_MODEL`). `RACE_AI_PROMPT_VERSION` (default `race_analyst_v3`) selects the per-válida analysis prompt/pipeline version — set to `race_analyst_v2` for an immediate rollback without a deploy; the season summary always runs the v3 prompt. An empty `RACE_AI_MODEL` resolves to the per-provider default inside `_llm.py`, **not** to `AI_MODEL`; an empty `RACE_AI_API_KEY` falls back to `AI_API_KEY` only when both stacks name the same provider. Sqlite checkpointing (`./data/langgraph_state.sqlite`, ephemeral on Render's free-tier filesystem — a pending HITL decision does not survive a deploy; orphan runs are reconciled at startup). Spend guard: `RACE_AI_BUDGET_USD_30D` (default 20 USD) blocks new runs with `503` once the trailing-30-day cost is exceeded; in-flight runs finish. That overrun path is log-only today (`race_ai_budget_exceeded` at ERROR level, 1-hour cooldown) — the email to coach + admin is a documented TODO in `budget_guard.py`, not wired. No observability tool is wired in — the audit trail is `athlete_ai_insights` / `agent_runs` / `agent_run_events`; self-hosted Langfuse was scoped as an optional future add-on and was never implemented. Guarded by a golden eval (`backend/tests/evals/test_race_analyst_eval.py`, run with `pytest -m golden`; dataset and baseline in `backend/evals/race_analyst/`), blocking in CI at composite ≥ 0.75 (`.github/workflows/race-eval.yml`).
- **Race results** (`app/services/race/`): official PDF ingestion (pdfplumber) → fuzzy normalization (rapidfuzz) → transactional, idempotent ingest (SHA256 dedupe in `race_import`) → pandas analytics. Operated through the web Import Wizard (`routers/race_imports.py`: parse → dry-run → commit); there is no CLI path.
- **Documents & email**: Jinja email templates in `templates/email/` (MailHog in dev, Resend in prod), PDF via WeasyPrint, DOCX via docxtpl (`templates/documents/`; regenerate the monthly-report DOCX with `scripts/generate_docx_template_monthly_report.py`). Media uploads validate magic bytes, strip EXIF, and store on Hostinger SFTP with local fallback.
- **Strava sync** (feature flag `STRAVA_ENABLED`): webhook plus a daily reconcile cron (`.github/workflows/strava-reconcile.yml` hits prod). GPS/route data is never persisted or displayed.
- **Training sessions**: the session wizard only creates `session_kind=entrenamiento`; outings and joint activities are calendar events (`club_event`, `group_training`), and the monthly report unions both sources.

### Frontend — React 19 SPA

`src/routes/*` (pages per domain; coach surface vs `routes/parents/`) + `src/components/*` (shadcn/ui + Tailwind v4) + `src/api/*` (axios) + `src/hooks/*` (TanStack Query; persisted cache is busted per deploy via `__APP_VERSION__`) + `src/store/` (Zustand auth) + `src/schemas/` (Zod, mirroring backend schemas). Forms are always React Hook Form + Zod. Tests: vitest + Testing Library + MSW; jest-axe with zero violations required on page- and dialog-level components.

### Deploy topology

Backend auto-deploys to Render free tier from `main` (`https://mi-2yzi.onrender.com`, cold start ~50 s — the frontend must show a "starting server" state, never a bare spinner); MySQL lives on Hostinger; frontend on Cloudflare Pages. Post-deploy: smoke-check `/health` plus one authenticated endpoint.

## Workflow conventions

- **Spec Kit**: features are developed in `specs/NNN-slug/` via the `/speckit-*` skills (specify → plan → tasks → implement). Long-form feature docs live in `docs/NN-topic/` (numbered, with `workflow.md` / `design.md` / `qa.md` / `runbook.md` inside).
- **History lives outside this file**: update `docs/implementation-status.md` (per-module step tables) and `docs/technical-notes.md` (dated technical changelog) when finishing work — not this file.
- **Branches**: `<type>/<short-slug>` (e.g. `feat/season-panorama`). Commits: Conventional Commits — type in English, description in español latino, never mentioning AI tooling.
- **Subagents**: project agents in `.claude/agents/` follow the tiering/team policy documented in `.claude/agents/README.md` (leads = opus, workers = sonnet). The `data-privacy-guard` audit is mandatory for any feature touching athlete-identifiable data.

<!-- SPECKIT START -->
Most recent feature: `specs/036-ai-insights-tab-review/plan.md` (spec, research, data-model, contracts and quickstart live alongside it). Implementation is complete per `docs/implementation-status.md`, with follow-up still uncommitted in the working tree. No feature is active right now — regenerate this block with `/speckit-agent-context-update` when the next one starts.
<!-- SPECKIT END -->
