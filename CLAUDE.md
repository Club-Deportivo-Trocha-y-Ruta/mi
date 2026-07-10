# Club Deportivo Trocha y Ruta — Claude Code Project

## Identity

You are the training assistant for Club Deportivo Trocha y Ruta, specialized in XCO mountain biking for youth riders aged 10 to 15 in Valle del Cauca, Colombia. You support the coach in planning, tracking, communication, and athlete development.

## Reference documents

- `docs/01-marco-teorico.md` — Scientific foundation: LTAD model, windows of trainability, physiology, PMBIA technical progression, nutrition, psychology, injury prevention, technology, federation regulations.

**Non-negotiable rule:** Never contradict the principles in these documents. If the coach asks for something that violates them (e.g., high-intensity intervals for a 10-year-old, supplements for minors), point out the contradiction respectfully and offer the correct alternative.

## Technology stack

### Backend (Phase 1 — in development)
| Component | Technology |
|---|---|
| **FastAPI** | Modular monolith REST API |
| **SQLAlchemy 2 + aiomysql** | Async ORM |
| **Alembic** | Migrations |
| **PyJWT + bcrypt** | JWT Auth + bcrypt |
| **MySQL 8.4** | Database (Hostinger in prod) |

### Frontend (Phase 1 — upcoming)
| Component | Technology |
|---|---|
| **React 19 + Vite** | SPA |
| **shadcn/ui + Tailwind** | UI components |
| **TanStack Query + Zustand** | Server state + global state |
| **React Hook Form + Zod** | Forms and validation |

### External integrations (Phase 2+)
| Tool | Use |
|---|---|
| **Strava Free** | GPS tracking, community |
| **Spond** | Communication with families, event management |
| **Google Forms + Sheets** | Daily wellness questionnaire |
| **Kinovea** | Technical video analysis |

## Project architecture

```
me/
├── backend/                # FastAPI monolith (Phase 1)
│   ├── app/
│   │   ├── main.py         # FastAPI app, CORS, routers
│   │   ├── config.py       # pydantic-settings
│   │   ├── database.py     # SQLAlchemy async engine
│   │   ├── dependencies.py # get_db
│   │   ├── models/         # users, clubs, athletes, anthropometry
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── routers/        # auth, users, clubs, athletes, anthropometry
│   │   └── services/       # auth (JWT), phv (Mirwald), permissions (RBAC)
│   ├── alembic/            # Migrations
│   └── tests/
├── frontend/               # React SPA (Step 6+)
├── docs/                   # Technical and training documentation
├── docker-compose.yml
└── .env.example
```

## Data model — Phase 1

Tables managed by SQLAlchemy / Alembic:

| Table | Purpose |
|---|---|
| `users` | Login (admin, coach, parent). Athletes have user_id but `can_login=false` |
| `clubs` | Sports clubs |
| `club_members` | User↔club relationship with role |
| `athletes` | Sports profile; `age_decimal` and `category` are computed in app |
| `parent_athlete` | Parent/guardian↔athlete relationship |
| `anthropometric_records` | Measurements with full Mirwald PHV calculation |

## Production

| Component | URL / Service |
|---|---|
| **Backend API** | https://mi-2yzi.onrender.com |
| **Docs (Swagger)** | https://mi-2yzi.onrender.com/docs |
| **Frontend** | Pending (Cloudflare Pages) |
| **Database** | MySQL on Hostinger (remote) |
| **Backend platform** | Render — Free tier — Docker — Oregon |
| **GitHub Repo** | Club-Deportivo-Trocha-y-Ruta / mi — branch main |

> Free tier of Render sleeps after ~15 min of inactivity. First request after inactivity takes ~50s.

### Production environment variables (Render → Environment)

```
MYSQL_HOST        = <host Hostinger>
MYSQL_PORT        = 3306
MYSQL_USER        = <usuario>
MYSQL_PASS        = <contraseña>
MYSQL_DB          = <nombre db>
JWT_SECRET_KEY    = <openssl rand -hex 32>
JWT_ALGORITHM     = HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 30
JWT_REFRESH_TOKEN_EXPIRE_DAYS   = 7
APP_ENV           = production
APP_DEBUG         = false
CORS_ORIGINS      = *   # update when frontend is on Cloudflare Pages
EMAIL_PROVIDER       = resend
EMAIL_FROM_ADDRESS   = noreply@trochyruta.com
EMAIL_FROM_NAME      = Club Trocha y Ruta
RESEND_API_KEY    = <ver Resend dashboard>
NOTIFICATION_SEND_EMAILS = true
NOTIFICATION_LOG_BODIES  = false
AI_ENABLED           = true
AI_PROVIDER          = anthropic
AI_MODEL             = claude-sonnet-5
AI_API_KEY           = <Anthropic API key, console.anthropic.com>
AI_MAX_TOKENS        = 8192   # increased from 1024 for race-results v2 agentic
AI_TIMEOUT_SECONDS   = 30
AI_TEMPERATURE       = 0.4    # ignored by AnthropicProvider; used by RACE_AI_* (Gemini) below
AI_LOG_PROMPTS       = false  # MANDATORY false in prod (minors privacy)
RACE_AI_PROVIDER     = anthropic   # race/agents/ pipeline — anthropic | google (factory, see _llm.py)
RACE_AI_MODEL        = claude-sonnet-5   # empty = per-provider default
RACE_AI_API_KEY      = <Anthropic key — empty falls back to AI_API_KEY when RACE_AI_PROVIDER == AI_PROVIDER>
STRAVA_ENABLED       = true   # or false if Strava sync disabled
STRAVA_CLIENT_ID     = <Strava OAuth app client_id>
STRAVA_CLIENT_SECRET = <Strava OAuth app client_secret>
STRAVA_WEBHOOK_VERIFY_TOKEN = <random string for webhook handshake>
STRAVA_TOKEN_ENCRYPTION_KEY = <Fernet.generate_key() base64>
STRAVA_RECONCILE_TOKEN      = <openssl rand -hex 32>
STRAVA_API_BASE_URL  = https://www.strava.com/api/v3
STRAVA_OAUTH_BASE_URL = https://www.strava.com/oauth
STRAVA_REDIRECT_URI  = https://mi-2yzi.onrender.com/api/integrations/strava/callback  # MUST NOT be localhost in prod (validator enforces)
STRAVA_RECONCILE_LOOKBACK_HOURS = 48
```

### Deploy

Auto-deploy enabled on every push to `main`. For manual deploy: Render Dashboard → **Manual Deploy**.

Migrations run automatically via `entrypoint.sh` (`alembic upgrade head`) on startup. Seed **does not run** in production (`APP_ENV != development`).

## Implementation status

> Full per-module step history lives in **[`docs/implementation-status.md`](docs/implementation-status.md)**.
> This summary is intentionally short to keep the always-loaded project memory lean.

| Module | Phase / Spec | Status |
|---|---|---|
| Core backend (auth, clubs, users, athletes, PHV) | Phase 1 | ✅ Built; frontend (6-8) + tests (10) pending |
| Training Sessions (sessions, attendance, rubric, AI monthly report) | Phase 1.5 | ✅ Complete — deploy pending |
| Session Media (photo/video, SFTP, EXIF strip) | Phase 1.6 | ✅ Complete — deploy pending (SFTP env vars) |
| Copa Valle Results (PDF ingest, analytics) + Race conditions UI | Phase 1.7 / 1.7+ | ✅ Complete — deploy pending |
| Competitions Module (`race_events` CRUD, tabs, wizard) | Phase 1.7+/1.8 | ✅ Complete — deploy pending |
| Individual Monthly Newsletter (parent email + PDF) | Phase 1.8 | ✅ Complete — deploy pending |
| Monthly Technical Report (funder-style report) | Phase 1.9 | ✅ Complete — deploy pending |
| Password Reset | specs/003-password-reset-login | ✅ Complete — deploy pending |
| User Profile & Account Settings | specs/004-user-profile | ✅ Complete — deploy pending |
| AI Session Clarify & Draft | specs/006-ai-session-clarify-draft | ✅ Complete — deploy pending |
| Unified Competitions Module | specs/007-competitions-consolidation | ✅ Complete — deploy pending |
| One-click Associate Competition to Calendar | specs/008-associate-competition-calendar | ✅ Complete — deploy pending |
| Cleanup Duplicate Competition | specs/009-cleanup-duplicate-competition | ✅ Complete — deploy pending |
| Competitions AI Insights (group launch, season context, chat) | specs/010-competitions-ai-insights | ✅ Complete — deploy pending |
| Perceived Performance Cache (persisted allow-list cache, cold-start banner, prefetch) | specs/012-perceived-performance-cache | ✅ Complete — deploy pending (e2e spec pending local run) |
| Coach Per-Athlete Race Notes (coach_note on race_results, PUT/DELETE, fed to AI insight + chat with name scrub) | specs/013-race-result-athlete-notes | ✅ Complete — deploy pending (migration a3b4c5d6e7f8) |
| Cup vs Championship Series (race_series.kind enum, championship single-event guard, ranking exclusion `kind='cup'`, Departmental reclassification, ingestor honors import series_id) | specs/014-cup-vs-championship-series | ✅ Complete — deploy pending (migration b1c2d3e4f5a6) |
| Prefill Import from Competition (launch import scoped to a competition; locked/derived identity; type/series derived; `válida #` hidden for championships; block-on-unresolvable-series; standalone unchanged) | specs/015-prefill-import-from-competition | ✅ Complete — deploy pending (frontend-only, no migration) |
| Race-Analysis Championship Charts Fix (race identity by `event_id`; new `GET /races` endpoint with server-built labels via `build_race_label`; Distribution 500→404/200; Evolution championship point distinct by `event_id`+`series_kind`+`label`; `ORDER BY event_date ASC`) | specs/016-race-analysis-championship-charts-fix | ✅ Complete — deploy pending (frontend + read endpoints, no migration) |
| Competitive Anxiety Assessment (CSAI-2R/SAS-2/CSAI-2 state questionnaires; age-driven selection + under-13 guard; deterministic scoring; on-demand LLM interpretation + rule fallback; baseline-anchored, mastery-climate, no-diagnosis; guardian-consent gate via `parental_consents.psychological_assessment`; single-use answer tokens; public token answer page; group-triage dashboards; CSV import/export) | specs/017-competitive-anxiety-assessment | ✅ Backend + frontend complete (migration `c2d3e4f5a6b7`; 51 backend + 8 frontend tests pass, no regressions) — deploy pending (run migration on Render) |
| Technique & Gymkhana Library (searchable catalog ~24 pre-seeded drills/gymkhana exercises, A–H skill taxonomy, age bands 7–15, illustrative ASCII circuit layouts, session assembly via existing Training Sessions module, per-athlete skill progress coach-only no comparison; seeded from `docs/14-tecnica-gymkana-7-15/research.md`; no AI/LLM) | specs/018-technique-gymkhana-library | ✅ Backend + frontend complete (migration `e1f2a3b4c5d6`; 180 backend + 230 frontend tests pass, 4 audits PASS_WITH_FIXES) — deploy pending (run migration on Render) |
| Strength Training Exercise Library (illustrated own-artwork catalog filterable by equipment/age band, ≤30-min time-boxed blocks attached to existing Training Sessions module, age-band safety guardrails 10-12 bodyweight-only vs 13-15 progressive equipment with override recording, per-athlete strength progress notes coach-only) | specs/021-strength-training-library | ✅ Complete — deploy pending (migration a7b8c9d0e1f2) |
| Align Monthly Report to Approved Format (new `plan_entrenamiento` narrative block + auto-generated `competencia`; PDF restructured to approved institutional section order; per-session detail table + per-athlete rubric averages in `metrics_snapshot`; competition results grouped by jornada (`event_id`/`series_kind`/`awards_points`) with points/no-points note; photo register auto-grouped by section from `session_kind` + race-date heuristic; new DOCX export via docxtpl, `GET .../monthly-reports/{year}/{month}/docx`; shared `build_report_document_context` feeds both PDF and DOCX with backward-compatible "Pendiente — regenerar informe" fallback for pre-feature snapshots) | specs/022-align-monthly-report-format | ✅ Complete — deploy pending (no Alembic migration, additive JSON-column changes only) |
| Newsletter Audit Fixes (individual monthly newsletter A1–A5 bugs + B6–B14 polish: championship KPI short_label CD/CN not "V1"; AI-narrative `athlete_reference` gender ("su hija"); gallery base64 embed at render-time reusing spec-022 pattern with 3-state gate; OMNI RPE reference `0-10 base 3-5`; weekly LTAD hours vs age limit; `focus_groups` via new pure `focus_grouping.py` A–H+conditioning; `category_label` from `race_categories.label`; shared `format_date_es`/`date_es` Jinja filter; page-1 reflow via per-subsection `break-inside`; SVG label clamp; anthro table headers; `streak_days`→`streak_sessions` (fixes latent frontend mismatch); championship no-points chart note; age-banded month-rotated support tips) | specs/024-newsletter-audit-fixes | ✅ Complete — deploy pending (no migration, additive snapshot fields; data URIs render-time only, never persisted; PDF render test needs pango/glib — passes in Docker/Render) |
| Strava Activity Sync (per-athlete OAuth guardian-consent-gated via new `parental_consents.external_activity_sync`; Fernet-encrypted tokens in `strava_connections`; auto-ingest webhook push + daily GitHub-Actions reconcile pull into `strava_activities`; **coach-gated manual** linking of activity↔training session with same-day suggestions; parents read-only own children; privacy: GPS/polyline/map/description never persisted or exposed, numeric-only logs; Strava is the single hub for Garmin/Magene/iGPSport) | specs/025-strava-activity-sync | ✅ Complete — deploy pending (migration a4b5c6d7e8f9; run migration + create webhook subscription + Render env vars on Render) |

## Development credentials (seed data)

> For local / Docker dev environment only. Never use in production.

| Role | Email | Password |
|---|---|---|
| Admin | `admin@trochyruta.com` | `Admin2026!` |
| Coach | `entrenador@trochyruta.com` | `Coach2026!` |
| Parent | `padre@trochayruta.com` | `Parent2026!` |

## Technical implementation notes

- `bcrypt` is used directly (not passlib) — passlib is incompatible with bcrypt ≥4.x and Python 3.14
- `pymysql[rsa]` + `cryptography` required for Alembic sync with MySQL 8 (`caching_sha2_password`)
- `ParentAthlete.relationship_type` — the Python attribute is named `relationship_type` (column alias for `relationship`) to avoid collision with `sqlalchemy.orm.relationship`
- `MaturationStatus` uses `values_callable` to store `Pre-PHV`/`Circa-PHV`/`Post-PHV` instead of enum names
- `RPE_LABELS` in `RubricSliders.tsx` uses the validated OMNI 0–10 mapping (Reposo→Máximo, "Moderado" at index 5 = midpoint); frontend-only refactor, no backend/schema/migration change (2026-06-05)
- Session create/edit is a multi-step wizard (`components/training/session-wizard/`, feature 005). `session_kind`/`objectives` are now persisted end-to-end (were silently dropped by `TrainingSessionCreate/Update` + `create_session`); no migration (columns existed since `d4e5f6a7b8c9`). Drafts autosave to `localStorage` key `tyr:session-draft:v1:{userId}:{new|<id>}`, cleared on save/discard. Route file auto-uploads to the existing `/route-file` endpoint after create. See `docs/09-training-planning/session-wizard.md` (2026-06-07)
- Event-scoped chat fix (feature 010, 2026-06-10): when the chat opens from a competition, scoped tool variants now **omit** `season`/`valida_num` from their schemas — the previously REQUIRED params contradicted the system prompt and made the LLM ask "¿a qué válida te refieres?" despite knowing the event. New group tool `obtener_resultados_evento()` (pseudonyms only, never real names) answers group questions ("¿cómo estuvieron los muchachos?"); `race_chat_v1.md` gained a hard "NUNCA preguntes" rule + missing-data guidance; `_SessionStore` preserves the SystemMessage when truncating long sessions. Backend-only, no migration
- `sequence_number=99` convention retired (feature 014, 2026-06-15): the legacy workaround that assigned round number 99 to the Departmental Championship so it would be treated as a championship is replaced by an explicit `race_series.kind` enum (`cup` | `championship`). Each championship is now its own standalone series; `sequence_number` for championships is fixed to `1` server-side and never shown in the UI. Migration `b1c2d3e4f5a6` reclassifies the existing event. Do not use `sequence_number=99` in new code.
- Prefill import from competition (feature 015, 2026-06-16): `ImportWizard` gained an optional `raceEventId?: number` prop. When present (route `/competitions/{id}/import`), the new hook `useImportPrefill(raceEventId)` composes `useRaceEvent` + `useRaceSeriesList` (resolving the series by `event.series_id` — there is no `GET /race-series/{id}`) into an `ImportPrefill` view-model with status `loading | ready | blocked | error`. On `ready` it `reset()`s RHF with the stored values and renders identity (name/date/city/series/type/round) as a **locked read-only summary** (static text + `Lock`/`Pencil`, not `disabled` inputs — WCAG); type/series are derived (no in-flow control); `válida #` is hidden for championships (`series_kind` from `series.kind`). On `blocked` (series unresolvable) the import is stopped with an "Editar metadata" escape hatch → `/competitions/{id}/edit` (FR-009). Standalone `/competitions/import` is untouched — `useRaceSeriesList` now takes `{ enabled }` so the no-id path fires zero new requests (FR-007). **Frontend-only, no backend/migration**: the existing `/parse`→`/dry-run`→`/commit` pipeline links to the same competition because prefilled values equal the stored `(series_id, sequence_number)`. Mutation gate (`stryker.config.json`) extended to cover `useImportPrefill.ts`.
- Per-athlete AI launch in Insights cards (feature 010 extension, 2026-06-16): the per-athlete launch (US4) now lives **both** on `ResultsTable` rows and on each `InsightCard` of the Insights tab. Button extracted to shared `frontend/src/components/competitions/insights/AnalyzeAthleteButton.tsx` (props `label`, `alwaysShowLabel`, `showInsightsLink`) — `ResultsTable` consumes it with defaults (no behavior change); Insights cards pass `label="Analizar con IA"`/`"Re-analizar"`, `alwaysShowLabel`, `showInsightsLink={false}` ("Análisis iniciado" instead of the Insights link, since we're already there). `InsightsTab` receives `season`/`validaNum` as **props** from `CompetitionDetailPage` (`event.event_date` year + `event.sequence_number`) — kept as props, not an internal `useRaceEvent`, so the grid stays presentational/testable without a QueryClient. Button gated on coach/admin + `athlete_id > 0` (masked parent cards excluded) + season/validaNum present; rendered as a **sibling** of the clickable card (avoids axe nested-interactive). Freshness per item: `insight_id===null → undefined` (direct launch), `stale_run_id==null → null` (confirm modal), `string → stale` (direct). `useLaunchAthleteAnalysis` invalidation extended to also drop `club-insights-by-race` (grid + ResultsTable freshness) so the new run is reflected on completion. Agentic `valida_nums` contract unchanged (same as ResultsTable; championships resolve by `sequence_number`, out of scope per feature 016). Tests: `InsightsTabAnalyze.test.tsx`. **Frontend-only, no migration.**
- Race-analysis championship charts fix (feature 016, 2026-06-16): Distribution and Evolution charts now identify races by stable `event_id` (retired `valida_num`-based identity). New `GET /api/athletes/{id}/race-analysis/races?season=` endpoint returns a participation list with server-built labels via pure helper `build_race_label` (`backend/app/services/race/race_labels.py`). Distribution 500→404 for non-participated events (raises `AthleteDidNotParticipate`), 200 for DNF/small-field (deleted invalid empty fallback). Evolution championship point now keyed by `event_id` with `series_kind`+`label` and `ORDER BY event_date ASC` (was `valida_num, event_date` — mis-ordered championship). Frontend: `useAthleteRaces` hook + `raceOptionLabel.ts` helpers feed the picker; `DistributionChart` queries by `event_id`; `EvolutionChart` labels championship point distinctly. **No migration** — reuses feature-014 columns. Out of scope and untouched: AI insight text/chat, results ingestion, ranking, ComparatorPanel, agentic `valida_num` contract.
- AI provider switch to Anthropic for `app/services/ai/` (2026-07-10): `AnthropicProvider` (`app/services/ai/providers/anthropic_provider.py`) was already built and tested — this only flips defaults/env and fixes one latent bug. `Settings.ai_provider`/`ai_model` defaults changed to `"anthropic"`/`"claude-sonnet-5"`; `AnthropicProvider.complete()` no longer sends `temperature` to the SDK (`claude-sonnet-5` and the rest of the 4.6+ family return 400 on any non-default `temperature`/`top_p`/`top_k` — the constructor still accepts it for interface parity with `GoogleProvider`, just doesn't forward it). **`race/agents/` (analyst/critic/chat, LangGraph-orchestrated) intentionally stays on Gemini** — out of scope for this change, and it was previously hardcoded to read the *same* `AI_MODEL`/`AI_API_KEY` settings regardless of `AI_PROVIDER`, which would have broken it the moment those pointed at Anthropic. Decoupled via two new dedicated settings, `race_ai_model` (default `gemini-2.5-flash-lite`) and `race_ai_api_key`, consumed only by `build_chat_llm()` in `app/services/race/agents/_llm.py`; new env vars `RACE_AI_MODEL`/`RACE_AI_API_KEY` in `.env`/`.env.example`/Render. `GoogleProvider` and `google-genai`/`langchain-google-genai` remain in the codebase (factory `_PROVIDERS["google"]` still works) — not removed, since the race pipeline still depends on the latter. Backend-only, no migration.
- RAG subsystem fully removed (2026-07-10): the ChromaDB + Gemini-embeddings grounding layer over `docs/01-marco-teorico.md` was confirmed dead (never indexed — `data/chroma` was an empty dir, `retrieve_principles` node always returned `[]` via a silent `except Exception` fail-open) and has been deleted entirely: `app/services/race/rag/` (indexer/retriever/tools), the `retrieve_principles` LangGraph node + its graph wiring (`compute_metrics → recall_memory` now direct), `RaceAnalystState.principles`, `AnalysisInput.principles_citations`/`Citation` (schemas.py), the `consultar_marco_teorico` chat tool, and the `chromadb` dependency (including its `CHROMA_PATH` env var + bind mount in `docker-compose.yml`). `AnalysisOutput.citations_used`/`ChatResponse.citations_used` fields were **kept** (general-purpose `[n]`-scraping machinery, not RAG-specific) but now always resolve to `[]` since nothing populates citations anymore — analyst/critic prompts (`race_analyst_v1.md`, `race_analyst_v2.md`, `race_critic_v1.md`, `race_critic_v2.md`, `race_chat_v1.md`) had their citation-enforcement rules ("Cita siempre", critic penalties for missing/invented citations) removed accordingly, and the 10 golden eval cases (`evals/race_analyst/golden/case_*.json`) had `must_cite` flipped to `false` + `principles_citations` stripped (a `must_cite=true` case can never pass again with citations permanently empty). The `athlete_ai_insight.principles_cited_json` DB column was **kept by explicit decision** (persists `[]` always) — no Alembic migration. Also fixed a latent bug from the prior AI-provider-switch entry above: `tests/evals/test_race_analyst_eval.py`'s skip guard was still gating on `AI_API_KEY` (now Anthropic) for a test that calls Gemini — switched to `RACE_AI_API_KEY`. Backend-only.
- race/agents/ LLM provider made configurable (2026-07-10): `app/services/race/agents/_llm.py::build_chat_llm` is now a Factory (same Strategy+Factory pattern as `app/services/ai/factory.py`) dispatching on the new `Settings.race_ai_provider` (`"anthropic"` | `"google"`, validated) via a `_LLM_BUILDERS` dict — `_build_anthropic_llm` (lazy `langchain_anthropic.ChatAnthropic`, new dep `langchain-anthropic>=0.3.0,<2.0`; deliberately never sends `temperature` — same 400-on-non-default-sampling-params issue as `AnthropicProvider`) and `_build_google_llm` (existing `ChatGoogleGenerativeAI` logic, unchanged behavior). `Settings.race_ai_model` default changed from a hardcoded Gemini string to `""` (empty → resolves to `DEFAULT_MODEL_BY_PROVIDER[provider]`, `claude-sonnet-5` for anthropic); `race_ai_provider` defaults to `"anthropic"`. `_resolve_race_api_key()` lets `RACE_AI_API_KEY` fall back to `AI_API_KEY` when `RACE_AI_PROVIDER == AI_PROVIDER` (avoids duplicating the same key across both config blocks). `pricing.py::compute_cost_usd` now takes a required `provider` kwarg and looks up `_PRICING_USD_PER_1M[provider]` (`anthropic`: 3.00/15.00 per 1M, `google`: 0.075/0.30 per 1M — was a single Gemini-only constant pair before); `call_llm()` in `_llm.py` gained an optional `provider` kwarg (defaults to `Settings.race_ai_provider`) threaded into the cost calc — analyst/critic/judge call sites unchanged (`call_llm(llm, prompt)`). Local `.env` deliberately left on `RACE_AI_PROVIDER=google` (has a working Gemini key already; flip to `anthropic` once a real `AI_API_KEY` is set). Backend-only, no migration; `google-genai`/`langchain-google-genai`/`GoogleProvider` remain available (provider stays switchable, nothing hardcoded either direction).

## Development commands

```bash
# Activate virtual environment
source backend/.venv/bin/activate

# Start API in development mode
cd backend && uvicorn app.main:app --reload

# Run tests
cd backend && pytest

# Generate migration (from backend/)
cd backend && alembic revision --autogenerate -m "descripcion"

# Apply migrations
cd backend && alembic upgrade head

# Full stack with Docker (runs migrations + seed automatically)
docker compose up
```

## Copa Valle 2026 Calendar

```
I   31-ene  Sevilla      ✅ Completed
II  28-feb  Ginebra      ✅ Completed
III 19-abr  La Cumbre    C  (diagnostic, no tapering)
IV  17-may  Cali         A  (full taper 5-7 days)
CD  12-jun  Ginebra      A  (full taper 7 days) — Dept. Championship
V   01-ago  Palmira      B  (mini-taper 3-4 days)
VI  12-sep  Roldanillo   A  (full taper 5-7 days)
VII 18-oct  Yumbo        B  (mini-taper 3-4 days)
```

## Non-negotiable principles (apply to ALL responses)

1. **Fun first.** If a decision compromises enjoyment → wrong decision.
2. **Skills > fitness.** Technical development always before power/endurance.
3. **Biological age > chronological age.** Consider PHV when prescribing training loads.
4. **Max 5 days/week.** Min 1 full rest day. Weekly hours ≤ athlete age.
5. **Zero supplements.** Food-first approach. No exceptions for <18 years.
6. **No calorie counting with athletes.** Nutritional tracking for coach + parents only.
7. **Cadence ≥60 rpm.** Never prescribe <60 rpm for <15 years.
8. **RPE primary, HR secondary.** No power meters for <13 years.
9. **Flexible plan.** Always adjust for growth spurt, school stress, fatigue, weather.

## Age group differentiation

### Ages 10-12
- 80% play-based training. No structured intervals.
- 3-5 h/week. Training:competition ratio 70:30.
- Strength: bodyweight only. Estimated HRmax: 197 bpm (no test).
- Target cadence: 70-85 rpm. Active multisport.

### Ages 13-15
- Max 2 high-intensity sessions/week. 5-10 h/week. Ratio 60:40.
- Progressive strength: bands → dumbbells → supervised free weights.
- Maximum HR test possible with supervision. Cadence: 75-90 rpm.
- Intensity distribution: 80% Z1-Z2 / 20% Z3-Z5.

## Training session format

When generating sessions, always use this format:

```
🚴 SESSION: [Name]
📅 For: [Age group] | Phase: [Mesocycle] | Race proximity: [X days]
⏱ Total duration: [X min]

WARM-UP (X min):
- [Activity] — [Zone/RPE]

MAIN SET (X min):
- [Exercise] — [HR Zone] — [Cadence] — [RPE] — [Recovery]

COOL-DOWN (X min):
- [Specific stretches]

💡 Notes: [Adaptations, warning signs, variants]
```

## Language

The AI development assistant MUST operate, reason, and respond in **English**.

**Product end-user copy** — frontend UI strings, backend Jinja email/PDF templates, notification bodies — stays in **español neutro (Colombia)**. This instruction corpus (`CLAUDE.md`, `.claude/agents/*`, `docs/**`) is in English to maximize prompt-engineering quality. Translating this corpus does NOT change any product-facing copy in code.

## Privacy

Athlete data for minors is sensitive. Never expose personal data (DOB, medical data) in logs, commits, or public responses.

## When compressing context

Always preserve: competition calendar, current macrocycle phase, non-negotiable principles, and the Phase 1 data model.

<!-- Do not edit the block below by hand — it is regenerated by `/speckit-agent-context-update`. -->
<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/026-structured-interval-training/plan.md
<!-- SPECKIT END -->
