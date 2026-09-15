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
  - `app/services/ai/` — provider factory (`anthropic` / `openai` / `google` / `fake` / `claude-cli` / `langchain`, default `google`) on `AI_*` env vars. `AI_USE_LANGCHAIN` (**default true**) routes every generation through `providers/langchain_provider.py`, an adapter over the shared factory in `app/services/llm/`; the switch exists to roll **back** to the native SDK providers during the migration window, not to enable the feature. The `AI_ENABLED=false` → `FakeLLMProvider` short-circuit runs first under either value, so the ~40 `fake.last_request` privacy assertions are unaffected. Powers the session assistant, monthly reports, newsletters, and the PHV/anthropometry explainers. `AI_ENABLED=false` yields `FakeLLMProvider`. `claude-cli` drives the Claude Code CLI via the developer's own subscription — local-only, same restriction as the race stack's `claude-cli`. If the Anthropic provider is selected, it must NOT forward `temperature` (Claude 4.6+ returns 400 on non-default sampling params).
  - `app/services/race/ai/` — the LangGraph agentic pipeline itself: `graph.py`, `nodes/`, `runner.py`, `state.py`, `budget_guard.py`, `run_reconciliation.py`. The sibling `app/services/race/agents/` holds the provider-facing wrappers (`analyst.py`, `critic.py`, `chat.py`); since feature 042 its `_llm.py` and `pricing.py`, plus `race/observability.py`, are **thin shims** over `app/services/llm/` — keep them, ~30 race tests monkeypatch those exact module paths. Prompts live in `race/prompts/*.md` and the eval judge/scorer in `race/eval/`. Own `RACE_AI_*` provider config — `RACE_AI_PROVIDER` defaults to `""` (empty), which **inherits `AI_PROVIDER`** (the `app/services/ai/` stack's own variable, default `google`) so a fresh checkout only needs to set one provider variable; set `RACE_AI_PROVIDER` explicitly only to decouple the two stacks (e.g. race stays on `google` while the other stack runs `claude-cli` locally). `claude-cli` (both stacks) drives the actual Claude Code CLI via `langchain-claude-cli` using the developer's own subscription login — **local-only**, never on Render (Anthropic's consumer terms forbid serving end users off a personal subscription); the package is deliberately absent from `requirements.txt`. Per-role models (feature 037) `RACE_AI_ANALYST_MODEL=gemini-3.8-flash` / `RACE_AI_CRITIC_MODEL=gemini-3.1-flash-lite` (the coach relies on Gemini's free quota in production; `anthropic`/`claude-sonnet-5`, `openai` and `claude-cli` are supported alternatives, not the default; the `chat` role has no dedicated variable and still resolves through legacy `RACE_AI_MODEL`). `RACE_AI_PROMPT_VERSION` (default `race_analyst_v3`) selects the per-válida analysis prompt/pipeline version — set to `race_analyst_v2` for an immediate rollback without a deploy; the season summary always runs the v3 prompt. An empty `RACE_AI_MODEL` resolves to the per-provider default inside `_llm.py`, **not** to `AI_MODEL`; an empty `RACE_AI_API_KEY` falls back to `AI_API_KEY` only when the effective provider (after the inheritance above) matches `AI_PROVIDER`. Sqlite checkpointing (`./data/langgraph_state.sqlite`, ephemeral on Render's free-tier filesystem — a pending HITL decision does not survive a deploy; orphan runs are reconciled at startup). Spend guard: `RACE_AI_BUDGET_USD_30D` (default 20 USD) blocks new runs with `503` once the trailing-30-day cost is exceeded; in-flight runs finish. That overrun path is log-only today (`race_ai_budget_exceeded` at ERROR level, 1-hour cooldown) — the email to coach + admin is a documented TODO in `budget_guard.py`, not wired. The audit trail of record is `athlete_ai_insights` / `agent_runs` / `agent_run_events`; optional local-only Langfuse tracing (`LANGFUSE_ENABLED`/`LANGFUSE_BASE_URL`/`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`, `docker-compose.langfuse.yml`) adds a per-call token/model/latency drill-down for local debugging — forbidden in production (`Settings` fails to start with `LANGFUSE_ENABLED=true` and `APP_ENV=production`), prompt/response content is always redacted (never captured, no opt-in); see `docs/10-race-results/runbook-ops.md` §8. Guarded by a golden eval (`backend/tests/evals/test_race_analyst_eval.py`, run with `pytest -m golden`; dataset and baseline in `backend/evals/race_analyst/`), blocking in CI at composite ≥ 0.75 (`.github/workflows/race-eval.yml`).
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
**Feature 043 (race course profile) — in planning.** Plan: `specs/043-race-course-profile/plan.md` (spec, research R-01…R-16, data-model, five contracts, quickstart). Optional per-válida course: route variants extracted server-side from a coach-recorded GPX (one lap, position+elevation only, nothing else persisted — the recording is the coach's personal data), laps per category with prefill from the previous válida, structured track description; derived distance/speed at read time (never stored, "sin dato" when any input is missing); a `course_block` for the race analyst under the same "present / SIN DATO" veto as conditions (`course_notes` structurally excluded); reconnaissance card for coach and registered families. GPX only (FIT deferred), no new dependency, storage in DB because Render's disk is ephemeral. Tasks: `specs/043-race-course-profile/tasks.md` (69 tasks, agents assigned). Next: `/speckit-implement`.

**Feature 042 (traceable growth AI) — shipped.** Every AI text generation of `app/services/ai/` runs through one LangChain transport behind `AI_USE_LANGCHAIN` (default true), over a shared, stack-neutral chat-model factory at **`app/services/llm/`** (`factory.py` with `build_chat_llm(..., role=, stack="app"|"race")`, `calls.py`, `pricing.py`, `observability.py`, `observability_metadata.py`). `race/agents/_llm.py`, `race/agents/pricing.py` and `race/observability.py` are now **thin shims** over it — kept because ~30 race tests monkeypatch those exact module paths; removing them is a later feature, not a cleanup to do casually. **One-way inheritance holds: race may read `AI_*`; the app stack must never read any `RACE_AI_*`.**

The anthropometric analysis lives in **`app/services/ai/anthro/`** — a plain async five-step pipeline (context → analyst `AI_ANALYST_MODEL` → critic `AI_CRITIC_MODEL` → guardrails → persist) with LangGraph-compatible `(state, config)` steps but **no graph, no checkpointer, no HITL**. It produces `AnthropometryInsightV1` (summary ≤140 chars; `changes` / `meaning` / `next_weeks` / `warning_signs` — the Spanish section labels are rendered UI copy, not schema keys; confidence, data gaps) from full longitudinal context. Velocity keeps the 8-week **computation** floor but is only labelled `reliable` at ≥26 weeks; phase crossings need corroboration; twelve deterministic prechecks (R01–R12, categories fixed by `contracts/golden-eval-case.md` §3) plus a cheap critic, one bounded revision and a deterministic fallback that is itself a valid insight. Persisted `critic_verdict` is one of `approved | revised | flagged | fallback | skipped`; **only `approved|revised` reach a family**, and the other three render to a family exactly like "no analysis yet". Nine nullable columns on `athlete_ai_explanations` carry the accounting; `text` stays `NOT NULL` and is populated even for v2 rows, which is what lets every existing reader work with no backfill. **Current Alembic head: `d5b125474e2b`** (single head, `down_revision=686ce1d873f3`; corrected 2026-09-15 — the 042 text previously said `686ce1d873f3`).

Tracing is **redact-always in every configuration**: no prompt, response, coach note or measurement ever reaches Langfuse. `LANGFUSE_STRUCTURAL_METADATA` (default false) adds only the closed operational allow-list in `observability_metadata.py` — never sex, age, category, PHV phase, deltas, dates or coach text; in a club of ~20 minors those fields form equivalence classes below k=2, so exclusion is the only safe option. Session ids are an HMAC keyed from the server secret, stable across restarts and domain-separated (the race chat trace uses the same helper). All **seven** entry points trace: the anthropometry pipeline opens its own span per step, and `LangChainProvider.complete()` opens one per generation for the five bridged use cases — those callers have no Langfuse scope of their own, so the adapter must open it or FR-017 fails silently while everything stays green. `LLMRequest.use_case` (set by `BaseUseCase._ask`) names the trace; two tests in `tests/test_langchain_provider.py` pin it. **Three production startup failures, each naming the offending variable**: `LANGFUSE_ENABLED`, `LANGFUSE_STRUCTURAL_METADATA`, and `claude-cli` as the effective provider of *either* stack (remember `RACE_AI_PROVIDER` inherits `AI_PROVIDER` when empty). New settings: `AI_USE_LANGCHAIN`, `AI_ANALYST_MODEL`, `AI_CRITIC_MODEL`, `AI_ANTHRO_PROMPT_VERSION` (prompt rollback without a deploy; `prompt_version` is stored per row so a rollback never relabels old rows), `RACE_AI_TEMPERATURE` (the race stack stopped borrowing `AI_TEMPERATURE`), `LANGFUSE_STRUCTURAL_METADATA`.

**One privacy rule this feature had to learn the hard way**: `previous_analysis.summary_line` is the only free-text field the context allow-list admits into a prompt. The rendered-text guardrails (R06) only screen the *new* draft after generation, so anything carried forward must be scrubbed against the club's forbidden-names list **before** the prompt is rendered — by exact match, since a "Nombre Apellido" regex does not catch an arbitrarily shaped name. `pipeline.run_analysis` loads that list before building the context for exactly this reason; a wiring test guards the ordering.

No spending cap for this stack and no change to `RACE_AI_BUDGET_USD_30D` (owner decision): its cost appears in `GET /admin/ai-usage` under `by_coach` labelled `stack="app"`, listed beside the race series but never summed into it. Docs live in `docs/20-traceable-growth-ai/`. Owner decisions of 2026-09-11 are in the spec's Assumptions and must not be re-asked.

**Open after 042** (updated 2026-09-14 — see `docs/technical-notes.md` for the full detail): `pytest -m mysql` and the golden eval have now run for real locally — 21/21 mysql tests pass, golden eval composite `0.781` ≥ 0.75, `baseline.json` is `status: REAL`, T047 done. Two test-infra bugs those runs surfaced are fixed (`conftest.py` wasn't resetting `AI_MODEL` alongside its `AI_PROVIDER=google` override; a fixture/loop-scope + stale-read bug in the mysql column test). `.github/workflows/anthropometry-eval.yml` still needs a new `AI_API_KEY` repo secret (distinct from `RACE_AI_API_KEY`) before CI can run it. `frontend/e2e/growth-analysis.spec.ts` still fails — root-caused, not an infra bug: it needs the **main** `docker compose up` stack with a real AI provider (the isolated Playwright stack is deliberately `fake`), and even there the seeded demo measurement resolves in ~4s instead of the assumed 20-40s because the analyst trips a `must_block` precheck and falls back on the first attempt — the same fallback-heavy behavior the golden eval shows dominating 10/12 cases. That precheck-trip rate is a prompt-quality question needing product judgment, not a bug fix — left open. SC-005's moderated check is unrecorded. Feature 041 (multi-coach governance) is verified locally; feature 040's deferred items (T027/T028 MySQL `_test` recompute, Playwright specs, T077–T079) remain open and are now written against the traced path.
<!-- SPECKIT END -->
