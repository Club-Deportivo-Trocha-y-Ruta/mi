# Contract — club scope for AI runs and imports, spend per coach, budget message

Covers **US6 / FR-028 / FR-029**. One rule replaces creator-lock: *anything of the club
can be acted on by any coach of the club; admin always; another club's coach never.*

**Backend**: `app/routers/race_analysis.py`, `app/routers/race_imports.py`,
`app/services/permissions.py`, `app/services/race/ai/budget_guard.py`,
`app/services/race/ingestor.py`, `app/schemas/race_ai.py`, `app/models/agent_run.py`,
`app/models/race_import.py`.
**Frontend**: `src/routes/admin/AIHealthPage.tsx`, `src/api/raceAnalysis.ts`,
`src/types/raceAnalysis.types.ts`, `src/components/ai/AIBudgetHint.tsx`.

**Not changed by this contract** (verified, do not touch):

| Surface | Why it needs nothing |
|---|---|
| `GET /race-events/{id}/runs` (`race_analysis.py:1891`) | already unfiltered by actor — the spec's "their listings are not filtered" (spec.md:116) |
| `GET /imports/` (`race_imports.py:1197`) | already unfiltered, and already resolves the uploader's name (`:1242-1247`) |
| `app/routers/athlete_race_analysis.py` run endpoints | gated by `verify_athlete_access` (`app/dependencies.py:88-125`), which is club-scoped already |
| The budget itself | stays one club-wide limit (spec.md:282); this contract makes it *visible* per coach, not partitioned |
| The overrun e-mail | still the documented TODO in `budget_guard.py:178-189` |

---

## 1. Club resolution — one helper pair in `permissions.py`

New in `backend/app/services/permissions.py`, next to `coach_club_ids` (`:71`), which
reads `user.club_memberships` — already eager-loaded by `get_current_user`
(`app/dependencies.py:61-64`), so the check costs no extra query for the caller.

```text
async def run_club_ids(db, run: dict[str, Any]) -> set[int]
async def import_club_ids(db, imp: RaceImport) -> set[int]
async def ensure_run_club_access(db, run, user) -> None        # raises 403
async def ensure_import_club_access(db, imp, user) -> None     # raises 403
```

`ensure_*` raise `HTTPException(403)` directly, like `permissions.require_role`
(`:49-55`).

### 1.1 Run → clubs

| Step | Source | Note |
|---|---|---|
| 1 | `agent_runs.athlete_id` (`app/models/agent_run.py:109`) | preferred |
| 2 | `input_json["athlete_id"]` | fallback — **required**, see §1.3 |
| 3 | `athletes.club_id` for that id (`app/models/athlete.py:56`) | `deleted_at` is **not** filtered: a run about an archived athlete stays openable (data-model §8.1) |
| 4 | clubs where `requested_by_user_id` is a `club_members` row with `role_in_club='coach'` | used only when steps 1–3 yield nothing |
| 5 | `set()` | genuinely unresolvable |

### 1.2 Import → clubs

`race_imports`, `race_series` and `race_events` carry **no `club_id`** — verified:
`app/models/race_import.py:81-135`, `app/models/race_series.py:56-110`,
`app/models/race_event.py`. Races are third-party competitions, not club-owned rows, and
`data-model.md` §4.8 deliberately did **not** denormalise one onto `race_imports`.
The only truthful club link is therefore the importer's membership:

| Step | Source |
|---|---|
| 1 | clubs where `race_imports.imported_by_user_id` (`app/models/race_import.py:121`) is a `club_members` row with `role_in_club='coach'` |
| 2 | `set()` |

### 1.3 Gotcha — `agent_runs.athlete_id` is NULL on two of the four insert sites

| Insert site | Sets `athlete_id`? |
|---|---|
| `app/routers/race_analysis.py:635-643` (`POST /runs`) | **no** |
| `app/services/race/group_launch.py:406-414` (group launch) | **no** |
| `app/routers/athlete_race_analysis.py:826-834` | yes |
| `app/routers/athlete_race_analysis.py:1161-1169` | yes |

Three required changes, or step 1 resolves `NULL` for most existing runs and every new
group run:

1. Add `athlete_id` to both INSERT column lists (one parameter each, mirroring
   `athlete_race_analysis.py:829`).
2. Keep the `input_json` fallback of §1.1 step 2 permanently — the historical rows keep
   their `NULL`.
3. **Delta vs `data-model.md` §6.3** — add backfill **B7** to the same revision:
   `UPDATE agent_runs SET athlete_id = CAST(JSON_UNQUOTE(JSON_EXTRACT(input_json, '$.athlete_id')) AS UNSIGNED) WHERE athlete_id IS NULL AND JSON_EXTRACT(input_json, '$.athlete_id') IS NOT NULL`
   (SQLite branch: `json_extract(input_json, '$.athlete_id')`). Idempotent via the
   `IS NULL` guard; dialect-branched like `c4d5e6f7a8b9_seed_race_categories.py:75-145`.
   `athlete_id` is FK `SET NULL` to `athletes.id`, so add
   `AND EXISTS (SELECT 1 FROM athletes a WHERE a.id = <extracted>)`.

### 1.4 Decision matrix

`club_ids` = the set from §1.1/§1.2; `coach_clubs` = `coach_club_ids(user)`.

| Caller | `club_ids` | Outcome |
|---|---|---|
| admin | anything | **allow** (unchanged bypass) |
| parent / other role | anything | **403** — already blocked upstream by `_coach_or_admin` (`race_analysis.py:121`) / `require_role([admin, coach])` (`race_imports.py:855`, `:1009`) |
| coach, `coach_clubs ∩ club_ids ≠ ∅` | non-empty | **allow** — this is the change |
| coach, `coach_clubs ∩ club_ids = ∅` | non-empty | **403** |
| coach, `user.id == requested_by_user_id` / `imported_by_user_id` | empty | **allow** (legacy owner fallback: never widens, only keeps a club-less record reachable by its author) |
| coach, any other | empty | **403** |

---

## 2. `_ensure_run_owner` is deleted; seven call sites move to the club check

Delete `_ensure_run_owner` (`app/routers/race_analysis.py:542-550` — verbatim today:
admin bypass, then `run.get("requested_by_user_id") != user.id → 403`). Replace each call
with `await ensure_run_club_access(db, run, current_user)`.

| # | Line today | Endpoint | Action | Audit row (§5) |
|---|---|---|---|---|
| 1 | `:803` | `GET /runs/{run_id}/status` | read | none (plain read, FR-005) |
| 2 | `:895` | `POST /runs/{run_id}/hitl/{step_id}` | decide | `agent_run` / `approve` \| `unapprove` |
| 3 | `:1037` | `GET /runs/{run_id}/result` | read | none |
| 4 | `:1095` | `GET /runs/{run_id}/pdf` | export | `agent_run` / `export`, `meta_json.document_kind="race_analysis_pdf"` |
| 5 | `:1622` | `POST /runs/{run_id}/invalidate` | update | `agent_run` / `update` |
| 6 | `:1657` | `POST /runs/{run_id}/cancel` | cancel | `agent_run` / `cancel` |
| 7 | `:1739` | `POST /runs/{run_id}/re-execute` | execute | `agent_run` / `execute` |

The helper becomes `async` (it queries `athletes` / `club_members`), so every call site
gains `await` and passes `db`. The six OpenAPI `403` descriptions still saying "owner"
(`:780`, `:870`, `:1020`, `:1609`, `:1643`, `:1725`) become **"Coach de otro club."**, and
the three `description=` strings that end in "RBAC coach/admin + owner" (`:1605`, `:1639`,
`:1721`) become "RBAC coach/admin del club". The 403 body text stays
`"No tienes acceso a este run"` — unchanged on purpose, so no existing assertion churns on
wording.

---

## 3. Persisting who decided — `agent_runs.decided_by_user_id` + `decided_at`

Today the deciding user only exists in the in-memory `resume_value`
(`race_analysis.py:919`) and is dropped from the persisted `payload_json`
(`:940-947`), so "who decided" (FR-028) is unrecoverable.

Columns per `data-model.md` §4.8 (`decided_by_user_id` FK `users` `SET NULL`,
`decided_at` `DateTime`, both nullable, no backfill). Written in
`submit_hitl_decision`, **before** the event INSERT and **outside** its swallow-all
`try/except` (`:926`, `:950-951`) — that guard exists for the raw-SQL event enum, and a
lost attribution must fail loudly, not silently:

```sql
UPDATE agent_runs
   SET decided_by_user_id = :uid, decided_at = :ts
 WHERE external_run_id = :rid
```

Last decision wins when a graph has several HITL gates; the full sequence stays in
`agent_run_events` and in the audit log. `POST /runs/{id}/cancel` does **not** write
these columns — cancelling is not a decision; "who cancelled" is the `cancel` audit row
of §5.

---

## 4. Response contract — who launched it, who decided

### 4.1 `_load_run` gains three columns and two names

`_load_run` (`race_analysis.py:147-197`) currently selects ten columns and maps them
through `_g(name, idx)`, which falls back to **positional** access for tuple rows. New
columns are therefore **appended**, never inserted, so indices 0–9 stay valid:

```sql
SELECT r.id, r.external_run_id, r.status, r.started_at, r.finished_at,
       r.input_json, r.final_output_json, r.error_message,
       r.requested_by_user_id, r.explain_mode,
       r.athlete_id, r.decided_by_user_id, r.decided_at,
       TRIM(CONCAT(COALESCE(u_req.first_name, ''), ' ', COALESCE(u_req.last_name, ''))) AS requested_by_display_name,
       TRIM(CONCAT(COALESCE(u_dec.first_name, ''), ' ', COALESCE(u_dec.last_name, ''))) AS decided_by_display_name
  FROM agent_runs r
  LEFT JOIN users u_req ON u_req.id = r.requested_by_user_id
  LEFT JOIN users u_dec ON u_dec.id = r.decided_by_user_id
 WHERE r.external_run_id = :rid
 LIMIT 1
```

Two `LEFT JOIN`s on the PK of a table with a handful of rows: one round-trip, no extra
query on the 2-second poll. Aliases are `u_req` / `u_dec` — `dec` is a MySQL type
keyword. `TRIM`/`CONCAT`/`COALESCE` behave identically on SQLite (offline lane).

Display-name rule — the **shared resolver** of `contracts/audit-log-api.md` §6.2, *not* the
`f"user#{id}"` fallback still hardcoded at `race_imports.py:1244-1247`:

| Case | Value |
|---|---|
| the join resolves a user | the trimmed `"{first_name} {last_name}"` — including for a deactivated coach (FR-013) |
| the FK is set but the join yields no usable name (deleted or hand-edited row) | **`"Usuario no disponible"`** |
| the FK itself is `NULL` (no requester / not decided yet) | `null` |

The SQL above returns the empty string in *both* of the last two cases — `COALESCE(…, '')`
collapses a missing join row and a `NULL` name alike — so the mapper distinguishes them on
`requested_by_user_id` / `decided_by_user_id` being `NULL`, never on the string. `user#7` is
**never** a legal value of these fields: FR-013 forbids a raw identifier reaching the reader,
exactly as `contracts/audit-log-api.md` §6.2 and `contracts/coach-activity-report.md` §7.2
state for the audit rows and for `ActorChip`. These are **staff** names (adults) — no minor's
name ever enters this payload.

### 4.2 `RunStatusResponse` (`app/schemas/race_ai.py:180-196`), additive

```json
{
  "run_id": "9f2c…",
  "state": "hitl_waiting",
  "progress_pct": 62,
  "current_node": "hitl_gate_review",
  "started_at": "2026-09-09T14:02:11Z",
  "estimated_seconds_remaining": 0,
  "new_events": [],
  "last_seq": 17,
  "requested_by_user_id": 3,
  "requested_by_display_name": "Ana Coach",
  "decided_by_user_id": null,
  "decided_by_display_name": null
}
```

After coach B decides, the same endpoint returns `"decided_by_user_id": 7`,
`"decided_by_display_name": "Beto Coach"`. The ETag
(`f'W/"{run_id}:{last_seq}:{status}"'`, `:812`) already changes, because the decision
inserts an event and bumps `last_seq` — a stale `304` cannot hide the new fields.

### 4.3 `HITLDecisionResponse` (`:218-224`), additive

```json
{
  "accepted": true,
  "run_id": "9f2c…",
  "step_id": "gate_review",
  "next_state": "running",
  "decided_by_user_id": 7,
  "decided_by_display_name": "Beto Coach"
}
```

### 4.4 Frontend

`RunStatusResponse` / `HITLDecisionResponse` in
`frontend/src/types/raceAnalysis.types.ts:67-76` and `:88+` gain the four optional
fields (`?: string | null`), so existing consumers keep compiling. The run header renders
**"Lanzado por Ana Coach"** and, once decided, **"· Decidido por Beto Coach"**. It renders
the string verbatim — including the `"Usuario no disponible"` of §4.1 — and renders nothing
at all when the field is `null`. No raw id ever reaches the reader (FR-013), which is why
§4.1 removes the `user#{id}` fallback rather than leaving the frontend to filter it out.

---

## 5. Audit rows for these operations

Written through `record_audit(...)` in the caller's transaction, per
`contracts/audit-recording.md`; catalogues from `data-model.md` §2.

| Operation | `entity_type` | `action` | `entity_id` | `meta_json` |
|---|---|---|---|---|
| HITL approve / edit | `agent_run` | `approve` | `agent_runs.id` | `{"step_id": …, "has_edits": bool}` |
| HITL reject | `agent_run` | `unapprove` | `agent_runs.id` | `{"step_id": …}` |
| Cancel run | `agent_run` | `cancel` | `agent_runs.id` | `{"previous_status": …}` |
| Invalidate run | `agent_run` | `update` | `agent_runs.id` | `{"stale": true}` |
| Re-execute | `agent_run` | `execute` | `agent_runs.id` | `{"supersedes_run_id": <old id>}` |
| Run PDF download | `agent_run` | `export` | `agent_runs.id` | `{"document_kind": "race_analysis_pdf"}` |

**Import commit is deliberately not a row of this table.** Its tuple, `changed_fields` and
`meta` keys live in `contracts/audit-recording.md` §4.10, which is the single source of truth
for every `(entity_type, action)` pair; duplicating it here is how the two contracts drifted
apart. §6.2 below governs only what the commit writes on the `race_imports` row itself
(`committed_by_user_id` / `committed_at`), not what it writes to `audit_log`.

`club_id` = the resolved club of §1 (first element, or `NULL` when unresolvable);
`athlete_id` = the run's athlete when known. `agent_run_events` has **no ORM model**
(`app/models/agent_run.py` maps only `AgentRun`), so these hooks go at the router call
sites, not on any ORM event — consistent with research R-03/R-23.

---

## 6. Imports — club check, and who committed

### 6.1 `_load_pending_import`

Replace the ownership branch (`app/routers/race_imports.py:713-721`, whose own comment
says "ownership cross-coach") with `await ensure_import_club_access(db, imp, current_user)`.
The 404 branches above it (`:698-712`: unknown id, non-`pending` status) are unchanged
and still evaluated first. New 403 copy:

> **"No tienes acceso a este cargue de resultados: pertenece a otro club."**

All three call sites are unchanged in shape — `dry_run_import` (`:858`) and
`commit_import` (`:1012`, plus the re-locking reload at `:1065`).

### 6.2 `committed_by_user_id` / `committed_at`

`data-model.md` §4.8 adds `updated_at`, `committed_at` and `committed_by_user_id` to
`race_imports`, because US6 AS2 (spec.md:123) requires "the commit records coach B while
the parse keeps coach A as importer" — which `imported_by_user_id` alone cannot express.
Two sites promote a parse to `committed` and both must set them in lock-step:

| Site | Actor in scope |
|---|---|
| `app/services/race/ingestor.py:415-416` (live path) | `ingested_by_user_id` (`:177`) |
| `app/services/race/revision.py:786` (no caller today — keep consistent) | `changed_by_user_id` (`:698`) |

`imported_by_user_id` is never overwritten.

### 6.3 Listing stays as it is

`GET /imports/` (`:1197-1264`) is untouched: no owner filter today, and its
`UploadUserRef.full_name` (`app/schemas/race_imports.py:337-343`) is already the shape
`ActorChip` consumes.

---

## 7. Spend per coach

### 7.1 `spend_by_user_last_30d` in `budget_guard.py`

`app/services/race/ai/budget_guard.py` is already the shared source of truth for spend —
`app/routers/ai.py:73` imports its private `_sum_cost_last_30d` and calls it at `:251`. Add, next to it:

```text
@dataclass(frozen=True)
class UserSpend:
    user_id: int | None          # None = unattributed bucket
    display_name: str
    cost_usd_total: float
    run_count: int

async def spend_by_user_last_30d(db: AsyncSession, *, days: int = 30) -> list[UserSpend]
```

A plain dataclass, not a Pydantic model — a service module must not import
`app.schemas`. Same window and the same `JSON_EXTRACT` path as
`_QUERY_SUM_COST_30D` (`:106-114`); if that extraction is ever migrated to a dedicated
`cost_usd` column, all three places move together (the module's own note at `:103-105`).

```sql
SELECT COALESCE(ar.requested_by_user_id, i.generated_by_user_id) AS uid,
       COUNT(*)                                                  AS run_count,
       COALESCE(SUM(JSON_EXTRACT(i.metrics_snapshot_json,
                                 '$.aggregate.cost_usd_total')), 0) AS cost
  FROM athlete_ai_insights i
  LEFT JOIN agent_runs ar ON ar.id = i.agent_run_id
 WHERE i.generated_at >= :cutoff
 GROUP BY uid
 ORDER BY cost DESC
```

`agent_runs.requested_by_user_id` is the attribution key (research R-24). The
`COALESCE` to `athlete_ai_insights.generated_by_user_id`
(`app/models/athlete_ai_insight.py:160`) is a **refinement of R-24**: `agent_run_id` is
nullable (`:155-159`), so a plain `JOIN` would silently drop rows and break the
reconciliation invariant below. Names are resolved with a second batched
`SELECT id, first_name, last_name FROM users WHERE id IN (…)`, same formatting rule as
§4.1; the `NULL` bucket is labelled **"Sin atribuir"**.

**Reconciliation invariant (FR-029, US6 AC4)**:
`sum(s.cost_usd_total for s in spend_by_user_last_30d(db)) == _sum_cost_last_30d(db)`,
within `1e-6`. This is a required test, not a comment.

### 7.2 `GET /api/race-analysis/admin/ai-usage` — additive `by_coach`

The endpoint (`race_analysis.py:1314-1470`) keeps every existing field.

```json
{
  "window_days": 30,
  "run_count": 12,
  "cost_usd_total": 3.4712,
  "latency_ms_p50": 42000,
  "latency_ms_p95": 91000,
  "fail_rate": 0.0833,
  "by_prompt_version": [
    { "prompt_version": "race_analyst_v3", "run_count": 10, "cost_usd_total": 3.1012 },
    { "prompt_version": "race_analyst_v2", "run_count": 2,  "cost_usd_total": 0.3700 }
  ],
  "by_coach": [
    { "user_id": 3,    "display_name": "Ana Coach",   "run_count": 8, "cost_usd_total": 2.4012 },
    { "user_id": 7,    "display_name": "Beto Coach",  "run_count": 3, "cost_usd_total": 1.0700 },
    { "user_id": null, "display_name": "Sin atribuir","run_count": 1, "cost_usd_total": 0.0000 }
  ]
}
```

New schema `AIUsageByCoach` in `app/schemas/race_ai.py`, next to `AIUsageByPromptVersion`
(`:263-270`). Field names follow that sibling (`cost_usd_total`, `run_count`) rather than
the brief's shorthand `usd`, so one response never carries two naming styles;
`run_count` comes free from the same `GROUP BY` and the page's table wants it.

**RBAC widens**: `_admin: User = Depends(_admin_only)` (`:1325`) →
`current_user: User = Depends(_coach_or_admin)` (`_coach_or_admin` at `:121`). Spec US6
AC4 says "an administrator **or coach** views it". This deliberately reverses the
"coach-safe = sin montos en dólares" stance of `GET /api/ai/status`
(`app/routers/ai.py:244-248`): the coach now sees dollars, because they need to know who
is consuming the shared budget. No minors' data is involved — only staff names and money.

### 7.3 Admin AI page

`frontend/src/routes/admin/AIHealthPage.tsx` today renders only provider/model/enabled
from `GET /api/ai/health` (`useAIHealth`). It gains a second query to
`GET /api/race-analysis/admin/ai-usage?days=30` (new `getAIUsage` in
`src/api/raceAnalysis.ts` + `useAIUsage` hook) and a plain shadcn `Table` (research R-28,
no new dependency):

| UI element | Copy (español neutro) |
|---|---|
| Section title | "Gasto de IA por entrenador (últimos 30 días)" |
| Columns | "Entrenador" · "Análisis" · "Gasto (USD)" |
| Total row | "Total del club" |
| Empty state | "Aún no hay gasto registrado en esta ventana." |
| Error state | "No se pudo cargar el gasto de IA. Intenta de nuevo." |
| Unattributed row | "Sin atribuir" |

#### States (per async surface)

Same four-state shape as `contracts/staff-admin.md` §8 — the page is read-only, so it has a
loading, an empty, an error and a cold-start branch, and no mutation branch:

| State | Rendering |
|---|---|
| Loading | 3 skeleton rows inside the `Table` shell (same shape as `frontend/src/routes/athletes/AthletesListPage.tsx:122-129`), wrapped in `role="status" aria-live="polite"` with an `sr-only` label; the existing health card keeps its own `isLoading` branch (`frontend/src/routes/admin/AIHealthPage.tsx:55-63`), unchanged |
| Empty (`by_coach` is `[]`) | `EmptyState title="Aún no hay gasto registrado en esta ventana."`, no CTA — never an empty table body |
| Error | `ErrorState message="No se pudo cargar el gasto de IA. Intenta de nuevo." onRetry={() => void usageQuery.refetch()}` (`frontend/src/components/shared/ErrorState.tsx:14-21`) |
| Cold start | `ErrorState isColdStart` when `isColdStartError(err)` (`frontend/src/components/shared/ErrorState.tsx:101`), never a bare spinner — `/admin/ai` becomes a coach entry point on Render's free tier, so the ~50 s wake MUST be named (Constitution IV) |
| Mutation error | not applicable — the page issues no mutation |

The two queries fail independently: a failing `useAIUsage` never blanks the provider/model
card that `useAIHealth` already renders, and vice versa.

Touch targets: the `ErrorState` "Reintentar" button and any window/period control added to
this section are `min-h-12` (48 px, Constitution III); the table rows themselves are not
interactive.

The route guard in `src/App.tsx:427-436` (`allowedRoles` at `:430`) widens from
`allowedRoles={[UserRole.admin]}` to `{[UserRole.admin, UserRole.coach]}`, and the nav
entry becomes visible to coaches. `jest-axe` with zero violations is required on the page
(Constitution II).

---

## 8. Budget refusal — one formatter, four call sites

Four copies of the same `f`-string exist today: `race_analysis.py:608-615` (start run),
`race_analysis.py:1823-1830` (group launch), `athlete_race_analysis.py:803-809`
(per-válida run), `athlete_race_analysis.py:1107-1113` (season summary). Past the rule of
three (Constitution I), they collapse into one property on the existing error:

```text
class BudgetExceededError(RuntimeError):          # budget_guard.py:56
    @property
    def user_message(self) -> str: ...
```

Every site becomes `detail=exc.user_message`.

**Copy (español neutro, tildes completas)** — states the period and that in-flight runs
finish, per FR-029:

> "Presupuesto de IA del club agotado para los últimos 30 días: $0.0050 de $0.0010 USD.
> Los análisis en curso terminan normalmente; los nuevos se habilitan cuando el gasto
> salga de la ventana de 30 días o cuando el administrador aumente el presupuesto."

It keeps the leading word "Presupuesto" and the two amounts, so the existing assertions in
`tests/routers/test_race_analysis.py:610-612` keep passing on the new text. The ERROR log
line (`budget_guard.py:169-176`) already says the right thing and is unchanged.

**Frontend constant** `AI_BUDGET_EXHAUSTED_MESSAGE`
(`src/components/ai/AIBudgetHint.tsx:31-32`) — the current text says "mensual" and "el
próximo ciclo", both wrong for a trailing 30-day window:

> "Presupuesto de IA del club agotado para los últimos 30 días. Los análisis en curso
> terminan; los nuevos se habilitan cuando el gasto salga de la ventana."

`src/components/competitions/import/ImportWizard.tsx:266` hardcodes a fifth copy of the
old string — it must import the constant instead.

---

## 9. Error matrix

| Code | Runs (`/api/race-analysis/runs/{run_id}/*`) | Imports (`/api/race-analysis/imports/{parse_id}/*`) |
|---|---|---|
| `401` | no/invalid token | idem |
| `403` | parent (role gate); coach whose clubs do not intersect the run's — `{"detail": "No tienes acceso a este run"}` | parent; coach of another club — `{"detail": "No tienes acceso a este cargue de resultados: pertenece a otro club."}` |
| `404` | run does not exist | `parse_id` unknown, or no longer `pending` (unchanged, evaluated before the club check) |
| `409` | terminal run on HITL/cancel (unchanged) | concurrent commit (unchanged) |
| `422` | `edit` without `edits`; re-execute without `athlete_id`/`season` (unchanged) | incomplete `resolved_matches` (unchanged) |
| `429` | backpressure (unchanged) | — |
| `503` | AI disabled; budget exhausted → §8 copy | — |

---

## 10. Non-functional

- One extra round-trip at most per gated request: the club resolution needs `athletes`
  (PK lookup) and, only on the fallback path, `club_members`. `coach_club_ids(user)` is
  pure Python over an eager-loaded relationship. Budget: p95 ≤ 500 ms reads / 1500 ms
  writes (Constitution IV).
- `GET /runs/{id}/status` keeps exactly one query for the run (§4.1) plus the existing
  event/seq queries — the poll must not grow a second round-trip.
- `by_coach` is two queries (aggregate + batched name resolution), never N+1.
- Privacy: nothing added here carries a minor's name, birth date or measurement. The new
  fields carry staff display names and integer ids only; logs keep using ids
  (`race_import_commit parse_id=… event_id=…`, `race_imports.py:1173-1182`).

---

## 11. Required tests

### 11.1 New — backend

`tests/routers/test_race_analysis_club_scope.py` (fixture: coach A `id=10` and coach B
`id=11` both `club_id=1`; coach C `id=12` in `club_id=2`; `make_user` in
`tests/routers/conftest.py:39-48` gains a `club_memberships` argument — today it is
hardcoded `[]`):

1. Coach B opens `GET /runs/{id}/status` of a run launched by coach A → **200**.
2. Coach B posts the HITL decision on that run → **200**, and `agent_runs` now has
   `decided_by_user_id = 11` and a non-null `decided_at`.
3. Same response shows `requested_by_display_name` = coach A and
   `decided_by_display_name` = coach B.
4. **No raw identifier reaches the reader (FR-013)**: across the responses of the seven
   endpoints of §2, no string value anywhere in the body matches `^user#\d+$`. A run whose
   `requested_by_user_id` points at a row that no longer resolves returns
   `"Usuario no disponible"`; a `NULL` FK returns `null` (§4.1). This is the backend mirror
   of the `ActorChip` regression test in `contracts/coach-activity-report.md` §9.3.
5. Coach C (other club) → **403** on all seven endpoints, parametrised.
6. Parent → **403** (role gate, unchanged).
7. Admin → allowed on all seven (unchanged bypass).
8. Run whose `agent_runs.athlete_id` is `NULL` but whose `input_json.athlete_id` resolves
   → coach B still allowed (the §1.3 fallback).
9. Run with no resolvable athlete and no coach membership for its requester → only its
   author and admin pass (the empty-set fallback of §1.4).
10. Cancel by coach B writes the `cancel` audit row with actor B and leaves
    `decided_by_user_id` untouched.

`tests/routers/test_race_imports_club_scope.py`:

11. Parse created by coach A (`imported_by_user_id=10`), committed by coach B → **200**;
    afterwards `imported_by_user_id == 10` **and** `committed_by_user_id == 11`, with
    `committed_at` set.
12. Coach C dry-runs coach A's parse → **403** with the new Spanish detail.
13. Admin still bypasses (existing `test_dry_run_admin_bypasses_ownership` behaviour).
14. `GET /imports/` is unchanged for all three coaches (regression guard on "listings
    unchanged").

`tests/services/race/ai/test_spend_by_user.py`:

15. Three insights across two coaches → two `by_coach` rows with the right split.
16. **Reconciliation**: `sum(by_coach.cost_usd_total) == _sum_cost_last_30d()` within
    `1e-6`, including a row whose `agent_run_id IS NULL` (falls back to
    `generated_by_user_id`) and a row whose actor no longer resolves (`"Sin atribuir"`).
17. Empty window → `[]`, and the endpoint still returns `cost_usd_total: 0.0`.

`tests/routers/test_race_analysis.py::TestAdminMetrics` additions:

18. Coach → **200** on `/admin/ai-usage` (the RBAC widening).
19. `503` detail contains "últimos 30 días" and "en curso terminan".

`tests/scripts/` or the migration test module (`data-model.md` §6.5): B7 backfill fills
`athlete_id` from `input_json`, is a no-op on a second run, and never invents an id that
has no `athletes` row.

### 11.2 Updated — backend

| File:line | Today | After |
|---|---|---|
| `tests/routers/test_race_analysis_cancel.py:226-234` (`test_coach_no_owner_403`) | coach 99 with no memberships | rename to `test_coach_otro_club_403`; give coach 99 an explicit `club_id=2` membership so the 403 proves the club rule, not an empty set |
| `tests/routers/test_run_staleness_endpoints.py:102-111`, `:143-151` (`*_run_ajeno_403`) | same shape | same fix; add the mirror case "coach del mismo club → 200" |
| `tests/routers/test_race_imports.py:691-712` (`test_dry_run_403_cross_coach_ownership`) | coach 20 vs coach 10 → 403 | split in two: same club → **200**; `club_members` row in another club → **403** (the fixture's SQLite engine already creates `clubs` and `club_members`, `:94-112`) |
| `tests/routers/test_race_analysis.py:57-61`, `:524-526` | coach → 403 on `/admin/ai-usage` | coach → **200** |
| `tests/routers/test_race_analysis.py:553-570` (`test_admin_shape_completo`) | `set(body.keys()) == expected_keys` | add `"by_coach"`, and assert each entry's keys are `{user_id, display_name, run_count, cost_usd_total}` |
| `tests/routers/test_race_imports.py:11` (module docstring) | "403 ownership cross-coach" | "403 coach de otro club" |

### 11.3 Frontend

20. `AIHealthPage.test.tsx`: renders the per-coach table, the total row equals the sum of
    the rows, and each of the four states of §7.3 renders — loading skeleton rows, empty,
    error with a working "Reintentar", and the cold-start variant on an unanswered request;
    `jest-axe` reports zero violations (loaded and empty).
21. Run header test: `requested_by_display_name` and `decided_by_display_name` render as
    "Lanzado por … · Decidido por …", `"Usuario no disponible"` renders when the name did
    not resolve, and nothing renders when they are `null` (never a raw id).
22. Copy updates for the new budget message in
    `src/components/competitions/insights/__tests__/AnalyzeAthleteButton.test.tsx:253`,
    `.../GroupAnalysisPanel.test.tsx:194,393`,
    `src/components/competitions/results/__tests__/ResultsTableLaunch.test.tsx:373`,
    `src/components/competitions/import/__tests__/ImportWizard.postimport.test.tsx:294`,
    `src/routes/training/SessionAssistantPage.test.tsx:112`.
