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
  - `app/services/ai/` — provider factory (`anthropic` / `openai` / `google` / `fake` / `claude-cli` / `langchain`, default `google`) on `AI_*` env vars. `AI_USE_LANGCHAIN` (**default true**) routes every generation through `providers/langchain_provider.py`, an adapter over the shared factory in `app/services/llm/`; the switch exists to roll **back** to the native SDK providers during the migration window, not to enable the feature. The `AI_ENABLED=false` → `FakeLLMProvider` short-circuit runs first under either value, so the ~40 `fake.last_request` privacy assertions are unaffected. Powers the session assistant, monthly reports, newsletters, and the PHV/anthropometry explainers. `claude-cli` drives the Claude Code CLI via the developer's own subscription — local-only, same restriction as the race stack's `claude-cli`. If the Anthropic provider is selected, it must NOT forward `temperature` (Claude 4.6+ returns 400 on non-default sampling params).
  - `app/services/race/ai/` — the LangGraph agentic pipeline itself: `graph.py`, `nodes/`, `runner.py`, `state.py`, `budget_guard.py`, `run_reconciliation.py`. The sibling `app/services/race/agents/` holds the provider-facing wrappers (`analyst.py`, `critic.py`, `chat.py`); since feature 042 its `_llm.py` and `pricing.py`, plus `race/observability.py`, are **thin shims** over `app/services/llm/` — keep them, ~30 race tests monkeypatch those exact module paths. Prompts live in `race/prompts/*.md` and the eval judge/scorer in `race/eval/`. Own `RACE_AI_*` provider config — `RACE_AI_PROVIDER` defaults to `""` (empty), which **inherits `AI_PROVIDER`** (the `app/services/ai/` stack's own variable, default `google`) so a fresh checkout only needs to set one provider variable; set `RACE_AI_PROVIDER` explicitly only to decouple the two stacks (e.g. race stays on `google` while the other stack runs `claude-cli` locally). `claude-cli` (both stacks) drives the actual Claude Code CLI via `langchain-claude-cli` using the developer's own subscription login — **local-only**, never on Render (Anthropic's consumer terms forbid serving end users off a personal subscription); the package is deliberately absent from `requirements.txt`. Per-role models (feature 037) `RACE_AI_ANALYST_MODEL=gemini-3.8-flash` / `RACE_AI_CRITIC_MODEL=gemini-3.1-flash-lite` (the coach relies on Gemini's free quota in production; `anthropic`/`claude-sonnet-5`, `openai` and `claude-cli` are supported alternatives, not the default; the `chat` role has no dedicated variable and still resolves through legacy `RACE_AI_MODEL`). `RACE_AI_PROMPT_VERSION` (default `race_analyst_v3`) selects the per-válida analysis prompt/pipeline version — set to `race_analyst_v2` for an immediate rollback without a deploy; the season summary always runs the v3 prompt. An empty `RACE_AI_MODEL` resolves to the per-provider default inside `_llm.py`, **not** to `AI_MODEL`; an empty `RACE_AI_API_KEY` falls back to `AI_API_KEY` only when the effective provider (after the inheritance above) matches `AI_PROVIDER`. Sqlite checkpointing (`./data/langgraph_state.sqlite`, ephemeral on Render's free-tier filesystem — a pending HITL decision does not survive a deploy; orphan runs are reconciled at startup). Spend guard: `RACE_AI_BUDGET_USD_30D` (default 20 USD) blocks new runs with `503` once the trailing-30-day cost is exceeded; in-flight runs finish. That overrun path is log-only today (`race_ai_budget_exceeded` at ERROR level, 1-hour cooldown) — the email to coach + admin is a documented TODO in `budget_guard.py`, not wired. The audit trail of record is `athlete_ai_insights` / `agent_runs` / `agent_run_events`; optional local-only Langfuse tracing (`LANGFUSE_ENABLED`/`LANGFUSE_BASE_URL`/`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`, `docker-compose.langfuse.yml`) adds a per-call token/model/latency drill-down for local debugging — forbidden in production (`Settings` fails to start with `LANGFUSE_ENABLED=true` and `APP_ENV=production`), prompt/response content is always redacted (never captured, no opt-in); see `docs/10-race-results/runbook-ops.md` §8. Guarded by a golden eval (`backend/tests/evals/test_race_analyst_eval.py`, run with `pytest -m golden`; dataset and baseline in `backend/evals/race_analyst/`), blocking in CI at composite ≥ 0.75 (`.github/workflows/race-eval.yml`).
- **Race results** (`app/services/race/`): official PDF ingestion (pdfplumber) → fuzzy normalization (rapidfuzz) → transactional, idempotent ingest (SHA256 dedupe in `race_import`) → pandas analytics. Operated through the web Import Wizard (`routers/race_imports.py`: parse → dry-run → commit); there is no CLI path. **Course profile** (feature 043, `race/course/`: `gpx_processing.py`, `service.py`, `derived.py`) is an optional per-válida add-on: seven `/course*` endpoints on `routers/race_events.py` (variant upload/replace-file/rename/delete, `PUT .../setups`, `PATCH .../description`, `GET .../course`) feed derived-at-read distance/speed into results and a `course_block` into the race analyst; see the feature-043 summary below and `docs/10-race-results/course-profile-design.md` for detail.
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
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/044-race-history-backfill/plan.md
<!-- SPECKIT END -->

## Cross-feature invariants

Feature-by-feature history and open items live in `docs/implementation-status.md` and `docs/technical-notes.md`; the rules below are the ones that silently break if forgotten.

- **Shared LLM layer** (`app/services/llm/`, `build_chat_llm(..., role=, stack="app"|"race")`): one-way inheritance — the race stack may read `AI_*`, the app stack must never read `RACE_AI_*`. `race/agents/_llm.py`, `race/agents/pricing.py` and `race/observability.py` are thin shims kept on purpose (~30 race tests monkeypatch those paths).
- **Anthropometry AI** (`app/services/ai/anthro/`): plain async pipeline (context → analyst → critic → guardrails → persist), no graph/checkpointer. Only `critic_verdict` `approved|revised` ever reaches a family; `flagged|fallback|skipped` render as "no analysis yet". `previous_analysis.summary_line` must be scrubbed against the DB forbidden-names list (exact match) **before** the prompt is rendered — post-generation guardrails don't cover carried-forward text.
- **Tracing is redact-always**: no prompt, response, coach note or measurement reaches Langfuse. `LANGFUSE_STRUCTURAL_METADATA` only adds the allow-list in `observability_metadata.py` (never sex, age, category, PHV phase, dates — with ~20 minors those re-identify). Production refuses to start with `LANGFUSE_ENABLED`, `LANGFUSE_STRUCTURAL_METADATA`, or `claude-cli` as the effective provider of either stack.
- **Course profile** (`race/course/`): GPX is reduced to position + elevation in memory (timestamps, author, device extensions stripped; original file never stored; `MAX_RAW_POINTS` pre-check). Distance and average speed are derived at read time (`course/derived.py`), never persisted. `course_notes` is structurally excluded from the analyst's `SELECT` in `race/queries.py::fetch_course_context`.
- **Race identity** (`race/`): `race_competitors.normalized_name` is not unique — identity goes through `race_competitor_signatures` + a coach-reviewed `race_identity_candidates` queue that gates every commit — per import (feature 045): `/commit` and `/commit-pending` are blocked only by pending candidates that involve that import's record keys (matched by the name/club/city triple, ignoring the category discriminator; keys come from the rows that commit ingests, **including GENERAL-sheet triples**; a correction newer than the queue forces a rebuild before the gate), and the 409 body is `{detail:"identity_pending", pending_for_import, review_path}`. Imports can be `discarded` (migration `a76c264449a5`). Cross-válida data for a competitor not linked to a club athlete is blocked by `third_party_guard.py`. Parent access to pre-registration results is gated by `history.py::withhold_before` + `is_policy_version_in_force` (a superseding policy publish must update that setting in the same change).
- **Single race-metrics engine** (`race/field_metrics.py` + `race/audience.py`, feature 045): Parrilla, Percentil, «Brecha vs. mediana/1.ª posición/podio» are computed only here (`compute_field_metrics`, `compute_category_metrics`) — never re-derive them in a router, chart builder, newsletter or prompt. Percentile is time-based; percentile and median gap return `None` below `MIN_FIELD=5` timed finishers. Family payloads omit the winner/podium fields (excluded, not nulled) via `audience.py`; `FAMILY_EXCLUDED_METRIC_FIELDS` is the one list (`gap_pcts` included) and it also feeds family templates and the newsletter prompt context via `redact_for_audience(FAMILY)`; for parents the v3 insight `summary_text`/`recommendations`/top-level `principles_cited` are omitted, `/distribution` is coach-only, and persisted stage logs are scrubbed at read time in `to_parent_dto`. Reference: `docs/10-race-results/competitions-one-place.md`.
- **Alembic**: never trust a head id written in docs — run `alembic heads` and expect exactly one before adding a migration. Migrations must also downgrade cleanly under `pytest -m mysql`.
- **Deferred real-infra checks**: `pytest -m mysql`, `pytest -m golden` and the Playwright specs are routinely left unrun in sessions without MySQL/AI keys; say so explicitly rather than reporting a feature as fully verified.
