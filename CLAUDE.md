# Club Deportivo Trocha y Ruta — Claude Code Project

## Identity

You are the training assistant for Club Deportivo Trocha y Ruta, specialized in XCO mountain biking for youth riders aged 10 to 15 in Valle del Cauca, Colombia. You support the coach in planning, tracking, communication, and athlete development.

## Reference documents

- `docs/01-marco-teorico.md` — Scientific foundation: LTAD model, windows of trainability, physiology, PMBIA technical progression, nutrition, psychology, injury prevention, technology, federation regulations.

**Non-negotiable rule:** Never contradict the principles in these documents. If the coach asks for something that violates them (e.g., high-intensity intervals for a 10-year-old, supplements for minors), point out the contradiction respectfully and offer the correct alternative.

## Technology stack

- **Backend:** FastAPI modular monolith · SQLAlchemy 2 + aiomysql (async) · Alembic · PyJWT + bcrypt · MySQL 8.4 (Hostinger in prod)
- **Frontend:** React 19 + Vite SPA · shadcn/ui + Tailwind · TanStack Query + Zustand · React Hook Form + Zod
- **External integrations:** Strava Free (GPS tracking hub), Spond (family communication), Google Forms + Sheets (wellness), Kinovea (video analysis)

## Project architecture

```
me/
├── backend/                # FastAPI monolith
│   ├── app/
│   │   ├── main.py         # FastAPI app, CORS, routers
│   │   ├── config.py       # pydantic-settings
│   │   ├── database.py     # SQLAlchemy async engine
│   │   ├── dependencies.py # get_db
│   │   ├── models/         # users, clubs, athletes, anthropometry, ...
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── routers/        # auth, users, clubs, athletes, ...
│   │   └── services/       # auth (JWT), phv (Mirwald), permissions (RBAC), ai, race, intervals, ...
│   ├── alembic/            # Migrations
│   └── tests/
├── frontend/               # React SPA
├── docs/                   # Technical and training documentation
├── specs/                  # Spec Kit feature specs
├── docker-compose.yml
└── .env.example
```

## Data model — core tables

| Table | Purpose |
|---|---|
| `users` | Login (admin, coach, parent). Athletes have user_id but `can_login=false` |
| `clubs` | Sports clubs |
| `club_members` | User↔club relationship with role |
| `athletes` | Sports profile; `age_decimal` and `category` are computed in app |
| `parent_athlete` | Parent/guardian↔athlete relationship |
| `anthropometric_records` | Measurements with full Mirwald PHV calculation |

Feature modules add their own tables (sessions, media, race results, anxiety, technique, strength, Strava, intervals) — see Alembic migrations and `docs/implementation-status.md`.

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

> Full per-module detail lives in **[`docs/implementation-status.md`](docs/implementation-status.md)** — read it (and the relevant `specs/<feature>/`) before working on any of these modules.
> Every module below is ✅ complete and **deploy pending** unless noted.

| Module | Spec | Migration |
|---|---|---|
| Core backend (auth, clubs, users, athletes, PHV) | Phase 1 | — (frontend 6-8 + tests 10 pending) |
| Training Sessions (attendance, rubric, AI monthly report) | Phase 1.5 | — |
| Session Media (photo/video, SFTP, EXIF strip) | Phase 1.6 | — (needs SFTP env vars) |
| Copa Valle Results (PDF ingest, analytics) + Race conditions UI | Phase 1.7/1.7+ | — |
| Competitions Module (`race_events` CRUD, tabs, wizard) | Phase 1.7+/1.8 | — |
| Individual Monthly Newsletter (parent email + PDF) | Phase 1.8 | — |
| Monthly Technical Report (funder-style) | Phase 1.9 | — |
| Password Reset | specs/003 | — |
| User Profile & Account Settings | specs/004 | — |
| AI Session Clarify & Draft | specs/006 | — |
| Unified Competitions Module | specs/007 | — |
| Associate Competition to Calendar (one-click) | specs/008 | — |
| Cleanup Duplicate Competition | specs/009 | — |
| Competitions AI Insights (group launch, chat, per-athlete launch) | specs/010 | — |
| Perceived Performance Cache | specs/012 | — |
| Coach Per-Athlete Race Notes (`coach_note`, fed to AI) | specs/013 | `a3b4c5d6e7f8` |
| Cup vs Championship Series (`race_series.kind` enum) | specs/014 | `b1c2d3e4f5a6` |
| Prefill Import from Competition | specs/015 | — (frontend-only) |
| Race-Analysis Championship Charts Fix (`event_id` identity) | specs/016 | — |
| Competitive Anxiety Assessment (CSAI-2R/SAS-2/CSAI-2, consent gate) | specs/017 | `c2d3e4f5a6b7` |
| Technique & Gymkhana Library (A–H taxonomy, no AI) | specs/018 | `e1f2a3b4c5d6` |
| Strength Training Exercise Library (age-band guardrails) | specs/021 | `a7b8c9d0e1f2` |
| Align Monthly Report to Approved Format (+DOCX export) | specs/022 | — (additive JSON) |
| Newsletter Audit Fixes (A1–A5 + B6–B14) | specs/024 | — |
| Strava Activity Sync (OAuth, webhook, consent-gated) | specs/025 | `a4b5c6d7e8f9` (+webhook + env vars) |
| Structured Interval Training with Strava Correlation | specs/026 | `b5c6d7e8f9a0` |
| Interval Duration Usability (mm:ss, `open_lap`, engine v2) | specs/034 | `c7d8e9f0a1b2` |
| Nav & Coach Dashboard Redesign (grouped sidebar + rail, parent bottom nav, home) | specs/035 | — (frontend-only) |

## Development credentials (seed data)

> For local / Docker dev environment only. Never use in production.

| Role | Email | Password |
|---|---|---|
| Admin | `admin@trochyruta.com` | `Admin2026!` |
| Coach | `entrenador@trochyruta.com` | `Coach2026!` |
| Parent | `padre@trochayruta.com` | `Parent2026!` |

## Technical implementation notes

> Full dated changelog entries live in **[`docs/technical-notes.md`](docs/technical-notes.md)**. Evergreen gotchas:

- `bcrypt` is used directly (not passlib) — passlib is incompatible with bcrypt ≥4.x and Python 3.14
- `pymysql[rsa]` + `cryptography` required for Alembic sync with MySQL 8 (`caching_sha2_password`)
- `ParentAthlete.relationship_type` — Python attribute name (column alias for `relationship`) to avoid collision with `sqlalchemy.orm.relationship`
- `MaturationStatus` uses `values_callable` to store `Pre-PHV`/`Circa-PHV`/`Post-PHV` instead of enum names
- Anthropic models `claude-sonnet-5` / 4.6+ family return 400 on any non-default `temperature`/`top_p`/`top_k` — `AnthropicProvider` and `_build_anthropic_llm` deliberately never send sampling params
- Two AI stacks: `app/services/ai/` (factory `AI_PROVIDER`/`AI_MODEL`, default anthropic) and `race/agents/` LangGraph pipeline (factory `RACE_AI_PROVIDER`/`RACE_AI_MODEL` in `_llm.py`, `RACE_AI_API_KEY` falls back to `AI_API_KEY` when providers match). RAG subsystem was fully removed 2026-07-10 (citations machinery kept, always resolves `[]`)
- `sequence_number=99` convention retired (feature 014) — championships use `race_series.kind='championship'`, `sequence_number` fixed to `1` server-side. Do not use 99 in new code
- Session create/edit is a multi-step wizard (`components/training/session-wizard/`); drafts autosave to `localStorage` `tyr:session-draft:v1:{userId}:{new|<id>}`. See `docs/09-training-planning/session-wizard.md`

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
at specs/034-interval-duration-usability/plan.md
<!-- SPECKIT END -->
