# API Contract: `/api/athletes/{athlete_id}/race-analysis/*`

**Feature**: `036-ai-insights-tab-review` | Router: `backend/app/routers/athlete_race_analysis.py` | Schemas: `backend/app/schemas/athlete_race_analysis.py`

The 8 existing endpoints, with the contract changes this feature introduces. RBAC baseline: parent access is always filtered to their own athletes; every endpoint requires a denied-path test, and this feature adds the missing admin-role tests (T076) and parent-denial tests for `/distribution` and `/evolution` (T077).

## Endpoints

| # | Method + Path | Roles | Contract change in 036 |
|---|---|---|---|
| 1 | `GET .../insights` | coach, admin, parent (own child) | Ordering anchored to **race date** (T033); items gain `event_id`, race date, `series_kind` (T030); items gain `is_fallback` (T024). |
| 2 | `GET .../insights/{insight_id}` | coach, admin, parent (own child) | Gains `is_fallback`. Open Question 2 pending: whether `metrics_snapshot` must be role-filtered server-side (`race_time_ms`, `podium_gap_ms` currently reach parents via API). |
| 3 | `GET .../runs` | coach, admin | Unchanged shape. Admin-role test added. |
| 4 | `POST .../runs` | coach, admin | New **409 guard**: reject launch when a run is already active for the same athlete+válida (T043). Consent gate is tracked **outside** this feature. |
| 5 | `GET .../distribution` | coach, admin, parent (own child) | No shape change yet; `display_name` policy for other clubs' minors is Open Question 1 (T037 — blocked on club decision). Subtitle/docstring corrected meanwhile (T036). |
| 6 | `GET .../evolution` | coach, admin, parent (own child) | Unchanged shape. Parent-denial test added. |
| 7 | `GET .../races` | coach, admin | Race picker items become uniquely identifiable: `event_id`, date, `series_kind` replace the `valida_num===99` convention (T030/T031). |
| 8 | `POST .../season-summary` | coach, admin | Dedup lock acquired **before** LLM invocation; double submit returns **409** (`IntegrityError` caught), not 500 (T044). Response schema unchanged — see below. |

## Response schemas — corrections

### `SeasonSummaryResponse` (endpoint 8)

Backend (`schemas/athlete_race_analysis.py:571`) is already correct and is the source of truth:

```
insight_id: int ≥ 1
season: int
summary_text: str (≤ 5000 chars)
prompt_version: str  # "race_analyst_v2"
validas_analyzed: int ≥ 3
generated_at: datetime
```

**Frontend must conform** (T040): `frontend/src/api/athleteRaceAnalysis.ts:111-125` declares phantom `run_id`/`status`/`started_at`. The call is synchronous — no "Resumen en proceso" state exists.

### Insight items (endpoints 1–2)

Additions:

```
is_fallback: bool            # T024 — TRUE only for the failure-path fallback
event_id: int | null         # authoritative race identity (column already exists)
event_date: date | null      # enables race-date ordering + labels client-side
series_kind: str | null      # replaces valida_num===99 branching
```

`valida_num` stays for backward compatibility (`0` = season aggregate) but is no longer a label source.

### `ClubInsightByRaceItem`

`stale_run_id` is declared but never populated; T041 resolves it one way (populate) or the other (delete field + frontend badge). Not both.

## Cross-cutting server rules added

- **Newsletter attach guard** (in `routers/athlete_monthly_newsletters.py`, T026): attaching an insight with `is_fallback=TRUE` → **422**; client-side suppression is not the enforcement point.
- **Orphan reconciliation** (T016): on startup, `running`/`awaiting_hitl` runs older than the threshold → `failed` + `error_message`. Clients polling `GET .../runs` then see a terminal state instead of polling forever; `useRaceRun.ts` adds its own ceiling (T017).
- **Error detail**: 4xx responses carry a specific Spanish `detail`; the frontend must render it instead of the Axios status line (T045).
