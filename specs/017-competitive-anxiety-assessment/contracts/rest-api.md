# Phase 1 Contract: REST API — Competitive Anxiety Assessment

Base path `/api/anxiety`. All coach endpoints require auth + RBAC role `coach`/`admin` (via existing `services/permissions.py`). The token answer endpoint is **unauthenticated** but gated by a valid single-use token. All response/error copy in español neutro. No minor PII in logs.

## Coach — configuration

### POST `/api/anxiety/assessments`
Create one assessment (athlete auto-selects instrument by age; under-13 + CSAI-2/2R requires `override=true` and is recorded).
- Body: `{ athlete_id, event_id?, scheduled_at, instrument_type?, override?: bool }`
- 201 → assessment (status `pending`) + a freshly issued answer token (raw token returned **once**).
- 409 → athlete lacks active `psychological_assessment` guardian consent.
- 422 → under-13 with CSAI-2/2R and `override` not set (warning payload returned).

### POST `/api/anxiety/assessments/batch`
Create assessments for a group in one call (≤ 2-min flow, SC-001).
- Body: `{ athlete_ids: [int], event_id, scheduled_at }`
- 201 → list of created assessments + per-athlete tokens; per-athlete warnings (override needed / consent missing) surfaced without failing the whole batch.

## Athlete — answering (token, no auth)

### GET `/api/anxiety/answer/{token}`
- 200 → instrument items (text from licensed key), age-appropriate intro, 1–4 scale. No interpretations.
- 410 → token consumed/expired.

### POST `/api/anxiety/answer/{token}`
- Body: `{ answers: { "<item_id>": 1..4, ... } }` (missing items allowed → partial)
- 200 → `{ status: "completed"|"partial", short_message }` (short encouraging message only). Consumes token, computes & stores scores, seeds baseline if first.
- 410 → token consumed/expired.

## Coach — scoring & interpretation

### GET `/api/anxiety/assessments/{id}`
- 200 → assessment with scores, baseline deltas, interpretation (if any), flags.

### POST `/api/anxiety/assessments/{id}/recompute`
- 200 → recomputes scores from stored `answers_json` (deterministic).

### POST `/api/anxiety/assessments/{id}/interpret`
On-demand interpretation; caches result (regenerate supersedes).
- 200 → interpretation JSON (`resumen`, `por_dimension`, `estrategias`, `mensaje_para_el_atleta`, `banderas`) + `source: "llm"|"rule"`.
- Always succeeds with `source:"rule"` if LLM unavailable/invalid (FR-016).

### POST `/api/anxiety/assessments/interpret-group`
- Body: `{ assessment_ids: [int] }` → per-athlete cached interpretations (each individual).

## Coach — dashboards

### GET `/api/anxiety/athletes/{athlete_id}/series?instrument_type=`
- 200 → time series of subscale scores + baseline + per-point interpretation/flags (eager-loaded). Series split by instrument family (non-comparable note when mixed).

### GET `/api/anxiety/groups/by-event/{event_id}`
- 200 → group triage: athletes grouped by dominant pattern (`somatic_high` | `cognitive_high` | `confidence_low` | `favorable`) + alert flags surfaced (US5).

## Coach — import & export

### POST `/api/anxiety/import` (multipart CSV)
- Body: CSV with one column per item (`i1..iN`) + metadata (`athlete_ref`, `instrument`, `date`, `event_ref?`).
- 200 → `{ imported, skipped, errors[] }`; scores + interprets retroactively; seeds baselines where data permits.

### GET `/api/anxiety/export?format=csv|json&athlete_id=&season=`
- 200 → assessment data (scores + item answers) for coach analysis.

## Error model

Reuses the project's standard error envelope (localized message, code, no PII). Auth failures 401/403; not-found 404; consent/override conflicts 409/422; token issues 410.
