# Contract — audit recording (`record_audit`, request context, instrumentation matrix)

**Module**: `backend/app/services/audit.py` (new) + `backend/app/services/request_context.py` (new)
**Model**: `backend/app/models/audit_log.py` (new) — columns, enums and indexes are fixed by [`data-model.md`](../data-model.md) §1–§2. Nothing here re-specifies them.
**Callers**: the service layer only (never a router body, so the CLI, the two webhooks, the cron endpoint and the LangGraph completion callbacks obey the same rule — `plan.md` "Structure Decision").
**Related contracts**: `audit-log-api.md` (read side, Spanish sentence templates), `retention-purge.md` (the only remover), `athlete-archive.md`, `session-coaches.md`, `concurrency-and-approvals.md`, `scope-ai-imports.md`.
**Requirements covered**: FR-001, FR-002, FR-003, FR-004 (write half), FR-005, FR-009; Acceptance Scenarios US1-2/3/4/5.

---

## 1. `record_audit` — the single write entry point

### 1.1 Signature

```python
# backend/app/services/audit.py

async def record_audit(
    db: AsyncSession,
    *,
    action: AuditAction,
    entity_type: AuditEntityType,
    entity_id: int,
    actor: User | None,
    actor_kind: AuditActorKind = AuditActorKind.user,
    club_id: int | None,
    athlete_id: int | None = None,
    changed_fields: Sequence[str] | None = None,
    diff: Mapping[str, tuple[Any, Any]] | None = None,
    reason_code: AuditReasonCode | None = None,
    meta: Mapping[str, Any] | None = None,
    request_id: str | None = None,
) -> AuditLog | None:
    """Queue one append-only audit row in the caller's transaction.

    Calls ``db.add()`` and returns. It never flushes, never commits and never
    opens a session of its own, so the row shares fate with the business write
    (FR-001, spec.md:168). Returns ``None`` only for the documented no-op of
    §1.4 rule R7.
    """
```

`club_id` is keyword-**required with no default** on purpose: forgetting it must be a `TypeError` at import/call time, not a silently club-less row invisible to the club history (`data-model.md` §8.4).

### 1.2 What it does, in order

```text
1. validate       action ∈ AuditAction, entity_type ∈ AuditEntityType, entity_id > 0
2. actor coherence
                  actor_kind == user   → actor is not None      (else AuditContractError)
                  actor_kind != user   → actor is None          (else AuditContractError)
                  actor_role = actor.role if actor else None    (snapshot, never re-derived)
3. request_id     request_id or current_request_id()            (else AuditContractError)
4. reason gate    (entity_type, action) ∈ REASON_REQUIRED and reason_code is None
                  → AuditReasonRequired  (router maps to 422, §1.5)
5. no-op gate     action == update and not changed_fields and not diff → return None  (R7)
6. minimise       changed_fields := sorted(set(changed_fields or diff.keys()))
                  diff_json      := {k: {"before": …, "after": …}
                                     for k in diff if k in VALUE_ALLOWLIST[entity_type]}
                  meta_json      := validated against META_ALLOWLIST (§1.6)
7. add            db.add(AuditLog(occurred_at=datetime.now(timezone.utc), …))
8. log            logger.debug("audit_recorded", extra={...counts only...})   (§7)
9. return         the pending AuditLog
```

Step 6 is where FR-003 is enforced *before the row exists*: a value that is not
allow-listed is dropped, never stored and never logged. The dropped keys are
counted, never named-with-value, in the debug line.

### 1.3 Transaction rule — the row must be queued before the *right* commit

`db.add()` only moves the object to *pending*; it reaches MySQL on the caller's
flush/commit (research R-03). The default request session commits once, after the
handler returns (`backend/app/dependencies.py:17-24`), so for a well-behaved
endpoint "somewhere before returning" is enough.

It is not enough for the **56 explicit `await db.commit()` / `await session.commit()`
sites in `backend/app/` outside `dependencies.py`** (measured 2026-09-09; 57 including
`dependencies.py:21`). A `record_audit` call placed after an early commit lands in a
different transaction and can survive a rollback of the business write.

| Hazard | Site | Rule for this feature |
|---|---|---|
| Early commit to release the MySQL connection before SFTP + pdfplumber | `backend/app/routers/race_imports.py:1017` | The `race_import` `execute` row is recorded **inside the ingest transaction** (`backend/app/services/race/ingestor.py:254,449`), never in the router before `:1017`. |
| Service owns its commit | `backend/app/services/training/sessions.py:157,689,745,777`; `backend/app/services/training/attendance.py:58,97`; `backend/app/services/calendar/events.py:158,396,489,562,579`; `backend/app/services/training/reports.py:206,228,823,923`; `backend/app/services/intervals/structures.py:629,772,821`; `backend/app/services/intervals/templates.py:230,369,414` | `record_audit` is called inside the same service function, above its `db.commit()`. |
| Router owns its commit | `backend/app/routers/athlete_monthly_newsletters.py:648,699,832,1087,1230,1267,1476`; `backend/app/routers/training_sessions.py:780,917,986,1037`; `backend/app/routers/monthly_reports.py:783,834`; `backend/app/routers/race_events.py:741`; `backend/app/routers/athlete_race_analysis.py:466`; `backend/app/routers/parent_newsletters.py:234,287` | The service the router calls records; where the router mutates inline, the call goes immediately above that `commit()`. |
| Rollback used as an idempotency path | `backend/app/routers/webhooks_resend.py:188-197` (`IntegrityError` on a Svix replay → `db.rollback()` at `:192`) | `record_audit` is called **after** the successful `db.flush()` at `:189`, so a duplicate delivery discards the audit row with the event. Correct by construction — do not move it earlier. |
| Detached session, no request scope | `backend/app/routers/race_analysis.py:729-742`; `backend/app/routers/athlete_race_analysis.py:895-905`; `backend/app/routers/strava_integration.py:346-374`; `backend/app/services/intervals/match_runner.py:358-396` | These open their own `AsyncSessionLocal` **after** the HTTP response. `actor` and `request_id` are passed explicitly (§3.4); the ContextVar is already out of scope there. |

**Failure policy**: a failed audit fails the request. `record_audit` never swallows an
exception and is never wrapped in `try/except` at the call site. FR-001's "same unit
of work" has no partial mode.

### 1.4 Rules

| # | Rule |
|---|---|
| R1 | One row per (entity instance × action). A request that touches N records writes N rows sharing one `request_id` (FR-002, spec.md:27). |
| R2 | `actor_role` is a snapshot. Never join `users.role` at read time. |
| R3 | `actor_user_id` is `NULL` **iff** `actor_kind != user`. There is no "unknown user" state. |
| R4 | Values reach the DB only through `VALUE_ALLOWLIST[entity_type]` (`data-model.md` §2.5). `changed_fields` still lists every changed name, allow-listed or not. |
| R5 | `reason_code` is a catalogue member; free text is never accepted, at any layer. |
| R6 | `entity_id` is the primary key of the row the action is *about*. For a composite-PK bridge row (`training_session_coaches`) it is the `session_id`, and `meta_json.coach_user_id` carries the other half. |
| R7 | `action=update` with an empty change set writes **nothing** and returns `None`. A no-op PATCH must not manufacture history. Every other action always writes. |
| R8 | Document `export` / `send` rows are attached to the record the document is generated from, with `meta_json.document_kind` (`data-model.md` §2.3). |
| R9 | Plain reads are never recorded (FR-005, spec.md:15). The only GET requests that produce rows are the nine of §4.13. |

### 1.5 Errors

| Exception | Raised when | HTTP mapping | Product copy (es-CO) |
|---|---|---|---|
| `AuditContractError` (subclass of `RuntimeError`) | actor/actor_kind incoherent, unknown `entity_type`, no `request_id` in scope | 500 | generic `"Error interno del servidor"` (existing handler, `backend/app/main.py:68-81`) |
| `AuditReasonRequired` (subclass of `ValueError`) | `(entity_type, action) ∈ REASON_REQUIRED` and `reason_code is None` | 422 | `"Debes seleccionar un motivo para esta acción."` |

`AuditContractError` is a programming error, never a user error — it must be
impossible to reach it from a well-formed request, and the coverage test of §8 is
what proves it.

`REASON_REQUIRED` (from `data-model.md` §2.4, verbatim):

```python
REASON_REQUIRED: frozenset[tuple[AuditEntityType, AuditAction]] = frozenset({
    ("athlete",       AuditAction.archive),
    ("athlete",       AuditAction.restore),
    ("calendar_event", AuditAction.cancel),
    ("training_session", AuditAction.cancel),
    ("user",          AuditAction.deactivate),
    ("user",          AuditAction.delete),
    ("audit_log",     AuditAction.purge),
})
```

The primary guard is the **request layer**, so the 422 comes from FastAPI validation
with the standard body shape. Each request is typed with the sub-enum of its own
group — never with the full `AuditReasonCode` catalogue, which would happily accept a
`cancel_*` code on an athlete archive or an `athlete_*` code on an account
deactivation. The five sub-enums are fixed in `contracts/athlete-archive.md` §3.1 and
served to the pickers by `GET /api/audit/reason-codes`
(`contracts/audit-log-api.md` §14):

| Request | Field type | Required |
|---|---|---|
| `AthleteArchiveIn` (`DELETE /api/athletes/{id}`) | `AthleteArchiveReasonCode` | yes |
| `AthleteRestoreIn` (`POST /api/athletes/{id}/restore`) | `AthleteRestoreReasonCode` | yes |
| `EventCancelIn` (`DELETE /api/calendar/events/{event_id}`) | `CancelReasonCode` | yes |
| `SessionCancelIn` (`DELETE /api/training-sessions/{id}`) | `CancelReasonCode` | yes |
| `UserUpdate` (`PATCH /api/users/{id}`, the `is_active` flip) | `AccountStateReasonCode \| None` | when `is_active` is present |
| `UserDeleteIn` (`DELETE /api/users/{id}`) | `ParentRemovalReasonCode` | yes |

Two of those names are not JSON bodies, and the difference is fixed by their owning
contract, not here. Both cancels carry a free-text `reason` query parameter today
(`backend/app/routers/calendar.py:402`, `backend/app/routers/training_sessions.py:465-466`);
`contracts/session-coaches.md` §7.2 promotes the calendar one to a real body schema
(`backend/app/schemas/calendar.py::EventCancelIn`), while §7.1 keeps the session one as a
query parameter, so `SessionCancelIn` names that route's validated parameter rather than a
body. The sub-enum typing and the 422 are identical either way. `UserUpdate` is the
existing schema (`backend/app/schemas/user.py:25-29`) extended per
`contracts/staff-admin.md` §4.1; it is the one field that is `Optional` at the schema
level, because the same PATCH also edits non-state fields — `contracts/athlete-archive.md`
§9 pins the conditional requirement.

The `record_audit` gate is defence in depth for a service called from the CLI or a
script.

### 1.6 `club_id` and `athlete_id` resolution

Ten auditable tables have **no `club_id` column** — verified: `race_events`,
`race_series`, `race_imports`, `race_results`, `race_competitors`, `agent_runs`
(`backend/app/models/agent_run.py:90-112`), `athlete_ai_insights`,
`athlete_ai_explanations`, `interval_structures`, `strava_activities`. (`interval_templates`
does have one, `backend/app/models/interval_structure.py:260`.) The caller resolves
`club_id` with this ladder and the first hit wins:

```text
1. the entity's own club_id column                      (athletes, training_sessions,
                                                         calendar_events, monthly_reports,
                                                         club_project_profiles, interval_templates, …)
2. athletes.club_id of the athlete the action concerns   (anything athlete-scoped)
3. the parent entity's club_id                           (session_attendance → training_sessions,
                                                          session_media → training_sessions,
                                                          interval_structures → training_sessions,
                                                          athlete_monthly_newsletters → athletes)
4. the single club of coach_club_ids(actor)              (backend/app/services/permissions.py:71)
                                                          — only when it has exactly one member
5. None                                                  (CLUB_OPTIONAL only, §1.7)
```

Step 4 is the honest one for the race domain: with one club it is exact, and if a
second club is ever onboarded it degenerates to step 5 rather than guessing. The
coverage test asserts that every audited entity type except the `CLUB_OPTIONAL` set
produces a non-null `club_id` (`data-model.md` §8.4).

`athlete_id` is set **only** when the action concerns exactly one athlete. A club-wide
action (monthly report, club project profile, race event, staff account) leaves it
`NULL`; a batch over N athletes writes N rows, each with its own `athlete_id`. The
per-endpoint expression is the fourth column of every matrix table in §4.

### 1.7 `CLUB_OPTIONAL` and `META_ALLOWLIST`

```python
CLUB_OPTIONAL: frozenset[tuple[AuditEntityType, AuditAction]] = frozenset({
    ("user", AuditAction.update),      # password-reset consumption, profile self-edit
    ("club", AuditAction.create),      # the club does not exist yet
    ("audit_log", AuditAction.purge),  # cross-club by definition
})
```

`meta_json` keys are themselves a closed set — an unbounded dict is a PII channel:

| Key | Type | Used by |
|---|---|---|
| `document_kind` | `AuditDocumentKind` value (`data-model.md` §2.3) | every `export` / `send` row |
| `recipients_count` | int | newsletter/report sends |
| `athlete_count` | int | batch newsletter generation, club-wide runs |
| `convocados_count` | int | session creation roster placeholders (§4.7 note) |
| `removed_count`, `cutoff` | int, ISO date | the retention purge |
| `period` | `"YYYY-MM"` | monthly report / newsletter rows |
| `job` | short slug, closed set: `"strava_reconcile"`, `"orphan_run_reconciliation"`, `"anthropometry_backfill"`, `"lms_seed"`, `"resend_webhook"`, `"strava_webhook"`, `"interval_match"`, `"agent_run_complete"`, `"audit_retention"`, `"duplicate_cleanup"` | every non-`user` actor row, plus the one `user`-actor row that names a sub-operation (`duplicate_cleanup`, §4.10) |
| `rows` | int | the reference-data seeds' one-summary-row-per-invocation shape (§3.3) |
| `event_type` | delivery-event enum value | Resend webhook rows |
| `coach_user_id`, `target_user_id`, `parent_user_id`, `related_entity_id` | int | bridge / link rows |
| `results_count`, `competitors_count` | int | race import commit |
| `previous_status`, `new_status` | enum value | state flips whose entity has no allow-listed `status` |
| `event_date` | ISO date (`"YYYY-MM-DD"`) | `training_session` / `calendar_event` rows; the source of `{fecha}` in `audit-log-api.md` §7.2 |
| `role` | `UserRole` value | staff rows whose role is not in the diff; the source of `{rol}` (`audit-log-api.md` §7.2) |
| `role_in_club` | `ClubRole` value | `club_member` rows; the source of `{rol_club}` |
| `set_password_email` | bool | staff creation (`staff-admin.md` §1.5) |
| `step_id` | HITL step slug | `agent_run` decision rows (`scope-ai-imports.md` §5) |
| `has_edits` | bool | HITL approve — whether the coach edited the proposal before accepting |
| `stale` | bool | run invalidation (`scope-ai-imports.md` §5) |
| `supersedes_run_id` | int | run re-execution |
| `race_event_id` | int | race import commit |
| `is_revision` | bool | race import commit over an already-ingested event |
| `block` | newsletter/report block key, member of the known block-key set — never free text | block regeneration (`concurrency-and-approvals.md` §3) |

Anything else is refused by `record_audit` with `AuditContractError`. There is no
free-text meta key — no `note`, no `message`, no `filename`.

`job` is the one key whose **values** are also a closed set, listed in full above: a slug
is a string an author types by hand, so leaving it open would reintroduce the free-text
channel the key table exists to close. `record_audit` refuses an unlisted slug with the
same `AuditContractError`, and additionally requires the shape `^[a-z_]{3,40}$`, so a new
background job cannot ship its first audit row without an edit to this table — which is
the review gate, not an inconvenience. Every slug here appears in §3.3 or §4.

This table is the **union of every `meta_json` key the nine contracts of this feature
emit**, and it is the only place that union is written down. `audit-log-api.md` §8
re-filters `meta_json` on the way out through this same set rather than a second copy
of it, so a key allowed here is readable and a key added there without landing here is
a defect. The drift is caught mechanically by §9 T1.12: extending one contract's audit
table without extending `META_ALLOWLIST` fails the unit lane, not production.

---

## 2. `compute_changed_fields` — building `changed_fields` and `diff`

### 2.1 Signature

```python
# backend/app/services/audit.py

_UNSET = object()

def snapshot(obj: Any, *fields: str) -> dict[str, Any]:
    """Read the listed attributes off an ORM object into a plain dict.

    Call it BEFORE mutating the object; SQLAlchemy attribute history is not
    used, so the caller keeps full control of what is compared.
    """

def compute_changed_fields(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    allow_list: frozenset[str],
) -> tuple[list[str], dict[str, tuple[Any, Any]]]:
    """Return (changed_fields, diff) for one entity.

    ``changed_fields`` lists EVERY field whose normalised value changed.
    ``diff`` carries the before/after pair ONLY for fields in ``allow_list``.
    """
```

Typical call site:

```python
allow = VALUE_ALLOWLIST[AuditEntityType.training_session]
before = snapshot(session, "status", "session_kind", "scheduled_date",
                  "duration_min", "location", "technical_focus")
...                                   # apply the patch
after = snapshot(session, *before)
changed, diff = compute_changed_fields(before, after, allow)
await record_audit(db, action=AuditAction.update,
                   entity_type=AuditEntityType.training_session,
                   entity_id=session.id, actor=ctx.actor, actor_kind=ctx.actor_kind,
                   club_id=session.club_id, athlete_id=None,
                   changed_fields=changed, diff=diff)
```

`location` and `technical_focus` are deliberately in the snapshot and deliberately
**absent** from `VALUE_ALLOWLIST["training_session"]`: their *names* must appear in
`changed_fields` (the coach needs to know what changed), their *values* must never
be stored.

### 2.2 Normalisation

`_normalise(value)` is applied to both sides before comparison and before storage:

| Input | Stored / compared as |
|---|---|
| `enum.Enum` | `value.value` (the project idiom — enums persist their `.value`, `data-model.md` Conventions) |
| `datetime` | `value.isoformat()` (naive UTC, as stored) |
| `date` | `value.isoformat()` |
| `Decimal` | `str(value)` |
| `set` / `tuple` | `sorted(list(...))` |
| `None` | `None` |
| `str`, `int`, `float`, `bool`, `list`, `dict` | unchanged |
| anything else | `AuditContractError` — an unserialisable value must never reach a JSON column |

Rules:

- A key present in only one mapping is compared against `_UNSET` and therefore
  **skipped**: it means the caller did not snapshot it, not that it changed.
- Comparison is on the normalised value, so `Decimal("45.50")` vs `Decimal("45.5")`
  reports a change. Accepted: no `Decimal` column is allow-listed anywhere
  (`data-model.md` §2.5 bans every `*_cm`/`*_kg` column), so the only consequence
  is a redundant field *name* — never a value.
- `changed_fields` is returned sorted, so two runs of the same edit produce
  byte-identical JSON and the privacy scan is deterministic.
- `diff` is `{field: (before, after)}`; `record_audit` reshapes it into
  `{field: {"before": …, "after": …}}` (the column shape fixed by `data-model.md` §1).

### 2.3 Worked example

```python
before = {"status": SessionStatus.PLANNED, "duration_min": 90, "location": "Pance"}
after  = {"status": SessionStatus.EXECUTED, "duration_min": 90, "location": "Cerro"}
allow  = frozenset({"status", "session_kind", "scheduled_date",
                    "duration_min", "calendar_event_id"})

compute_changed_fields(before, after, allow)
# → (["location", "status"],
#    {"status": ("planned", "executed")})
```

`location` changed, so its **name** is in `changed_fields`; it is not allow-listed,
so no value is stored. `duration_min` did not change, so it appears nowhere.

---

## 3. Request context

### 3.1 `app/services/request_context.py`

```python
_request_id: ContextVar[str | None] = ContextVar("audit_request_id", default=None)

def new_request_id() -> str:            # uuid4().hex — exactly 32 chars (data-model.md §1)
def current_request_id() -> str | None: # None outside any scope

@contextmanager
def request_id_scope(value: str | None = None) -> Iterator[str]:
    """Bind a request_id for a non-HTTP unit of work (CLI, cron, webhook,
    detached callback). Always resets the token on exit."""

class RequestIdMiddleware:
    """Pure ASGI (Starlette), not BaseHTTPMiddleware."""
    def __init__(self, app: ASGIApp) -> None: ...
    async def __call__(self, scope, receive, send) -> None: ...
```

Middleware behaviour:

- `scope["type"] != "http"` → pass through untouched.
- Binds `new_request_id()`, resets the ContextVar token in a `finally`.
- Wraps `send` and appends `x-request-id` to the `http.response.start` headers.
- An inbound `X-Request-Id` is honoured **only** for the two machine endpoints
  (`POST /api/webhooks/resend`, `POST /api/integrations/strava/reconcile`) and only
  when it matches `^[0-9a-f]{32}$`. Everywhere else it is ignored — a browser must
  not be able to choose its own correlation id.

`BaseHTTPMiddleware` is rejected: it re-wraps every response in a `StreamingResponse`,
and this feature must audit byte responses from WeasyPrint/docxtpl (§4.13) without
changing how they are delivered (research R-05).

**Registration** — `backend/app/main.py`, immediately **after** the existing
`app.add_middleware(CORSMiddleware, …)` block at `backend/app/main.py:59-64`.

This is the **single authoritative CORS block for feature 041**. Feature 041 makes
two independent header changes to the same call — `If-Match` for optimistic
concurrency (research R-15) and the two exposed response headers — and they are
written once, here. `concurrency-and-approvals.md` §1.3 and `audit-log-api.md` §9
point at this block and deliberately restate nothing: three partial snippets is how an
implementer applies the last one they read and silently drops the other feature's
header.

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Accept", "If-Match"],  # ← + If-Match (R-15)
    expose_headers=["ETag", "X-Request-Id"],                               # ← new, both values
)
app.add_middleware(RequestIdMiddleware)                                    # ← last = outermost
```

Starlette prepends each `add_middleware` call to the user stack, so the **last**
registration is the outermost layer. Registering `RequestIdMiddleware` last means
the id exists for CORS-rejected and 500 responses too, and its header survives.

Verified 2026-09-09: `backend/app/main.py:59-64` has **neither** value —
`allow_headers=["Authorization", "Content-Type", "Accept"]` and no `expose_headers`
at all. Each omission breaks a different half of the feature, silently and without an
error anywhere: without `If-Match` in `allow_headers` the browser never sends the
precondition and optimistic concurrency degrades to no conflict detection
(`concurrency-and-approvals.md` §1.3); without `expose_headers` the browser cannot
read `ETag` (the reason `frontend/src/api/raceAnalysis.ts:44-47` is dead code today)
nor `X-Request-Id` (`audit-log-api.md` §9).

One test covers both, because one edit produces both: `backend/tests/test_cors_etag.py`
(`concurrency-and-approvals.md` §9 T21) asserts a preflight `OPTIONS` with
`Access-Control-Request-Headers: if-match` is allowed **and** that
`access-control-expose-headers` on a `GET` lists `ETag` *and* `X-Request-Id`.
`audit-log-api.md` §13 T11 asserts the header is present and well-formed and defers
the cross-origin readability assertion to that test.

### 3.2 `AuditContext` and the `get_request_context` dependency

```python
@dataclass(frozen=True, slots=True)
class AuditContext:
    request_id: str
    actor: User | None
    actor_kind: AuditActorKind
    actor_role: UserRole | None

    @classmethod
    def for_user(cls, user: User, request_id: str | None = None) -> "AuditContext": ...

    @classmethod
    def for_job(cls, kind: AuditActorKind, job: str,
                request_id: str | None = None) -> "AuditContext": ...
        # kind must be system / cron / webhook; actor and actor_role stay None


async def get_request_context(
    current_user: User = Depends(get_current_user),
) -> AuditContext:
    """Dependency for every authenticated mutating endpoint."""
    return AuditContext.for_user(
        current_user,
        request_id=current_request_id() or new_request_id(),
    )


async def get_public_request_context() -> AuditContext:
    """For the two unauthenticated writers (parent-register, password-reset
    confirm): actor is resolved by the handler itself, kind stays `user`."""
```

The ContextVar is **set by the middleware** so it exists for every request, including
those that never declare the dependency; `get_request_context` only *reads* it, and
falls back to `new_request_id()` so a router-level unit test that mounts the app
without the middleware still works.

The **actor is never read from the ContextVar**. It travels as an explicit
`ctx: AuditContext` parameter through service signatures, because the eleven
non-HTTP writers of §3.3 have no `current_user` and attributing their writes to the
last logged-in person is exactly what Acceptance Scenario 4 forbids (spec.md:26).

### 3.3 Non-HTTP callers

| Caller | Site | `actor_kind` | `request_id` | `meta_json.job` |
|---|---|---|---|---|
| Resend delivery webhook | `backend/app/routers/webhooks_resend.py:112` | `webhook` | inbound `X-Request-Id` if valid, else generated per delivery | `resend_webhook` |
| Strava webhook, deferred worker | `backend/app/routers/strava_integration.py:346-374` (own `AsyncSessionLocal`, runs after the ACK at `:376-404`) | `webhook` | generated in `receive_strava_webhook_event` and passed into the deferred coroutine | `strava_webhook` |
| Daily Strava reconcile | `backend/app/routers/strava_integration.py:409-427` (driven by `.github/workflows/strava-reconcile.yml`) | `cron` | inbound `X-Request-Id` if valid, else generated | `strava_reconcile` |
| Orphan-run reconciliation at start-up | `backend/app/main.py:24-49` → `app/services/race/ai/run_reconciliation.py` | `system` | one per lifespan invocation | `orphan_run_reconciliation` |
| LangGraph run completion (club runs) | `backend/app/routers/race_analysis.py:729-742` | `system` | the launching request's id, captured in the closure | `agent_run_complete` |
| LangGraph run completion (athlete runs) | `backend/app/routers/athlete_race_analysis.py:895-905` | `system` | idem | `agent_run_complete` |
| Deferred interval matching | `backend/app/services/intervals/match_runner.py:358-396` (own session, commits at `:396`) | `system` | the triggering request's id, passed as an argument | `interval_match` |
| LMS reference seed | `backend/app/seed_growth_data.py` (wired in `backend/entrypoint.sh`) | `system` | one per invocation | `lms_seed` |
| Anthropometry backfill | `backend/app/scripts/backfill_anthropometry.py` (wired in `backend/entrypoint.sh`) | `system` | one per invocation | `anthropometry_backfill` |
| Retention purge, scheduled | `backend/scripts/retention_audit_log.py` (contract `retention-purge.md`) | `cron` | one per invocation | `audit_retention` |
| Retention purge, run by hand | same script, interactive | `system` — **not `user`**: a CLI has no authenticated session, and `--actor-kind` only accepts `system\|cron` (`retention-purge.md` §0, §2.1) | one per invocation | `audit_retention` |

Reference data (LMS tables, race categories) carries no club and no athlete: those
seeds write **one summary row** per invocation (`entity_type` of the seeded table,
`action=execute`, `club_id=None`, `meta_json={"job": …, "rows": N}`), not one row per
seeded constant.

**Tuples written by the Strava deferred worker.** This is the one caller in the table
whose HTTP entry point is *exempt* (§4.14: `POST /api/integrations/strava/webhook`
only ACKs, `routers/strava_integration.py:376`), so the tuples live here and appear in
no route row: `strava_activity`·`create` for a new activity, `strava_activity`·`update`
for an update or a delete event, and `strava_connection`·`update` for a
deauthorisation. `athlete_id` = the connection's athlete; `club_id` resolves through
step 2 of the §1.6 ladder. A registry entry cannot be both `Audited(...)` and
`Exempt(...)`, and the deferred worker has no route of its own — recording the tuple
in two places is what §9 T4.1/T4.3 would have failed on.

### 3.4 Threading the context through services

Four service functions already accept the acting user and ignore it, or do not accept
it at all. This feature makes them use it — this is the same thread that fixes US4's
misattributed emails, so the two changes land together:

| Function | Today | After |
|---|---|---|
| `cancel_event(db, event, reason: str, user: "User", …)` | `backend/app/services/calendar/events.py:463-470` — `user` is accepted and never read; `reason` only reaches the outbound notification and is never persisted | `user` becomes the audit actor; `reason` becomes `reason_code: CancelReasonCode` (`contracts/athlete-archive.md` §3.1) and is persisted in `calendar_events.cancellation_reason_code` |
| `delete_event_permanent(db, event)` | `backend/app/services/calendar/events.py:541-562` — no actor at all | gains `ctx: AuditContext` |
| `execute_session(db, session_id)` | `backend/app/services/training/sessions.py:730` — no actor | gains `ctx: AuditContext` (US4 AS6) |
| `_load_session_coach(db, session)` | `backend/app/services/training/sessions.py:853`, called at `:715`, `:787`, `:839` — always returns the **creator** | replaced by the session-coach set + the acting coach from `ctx` (contract `session-coaches.md`) |

---

## 4. Instrumentation matrix (complete)

Every route of the mounted app whose methods intersect `{POST, PUT, PATCH, DELETE}`
— **99 endpoints**, enumerated from `app.routes` on 2026-09-09 — plus the **9
mutating or exporting GETs** of §4.13 and the **2 adjudicated read GETs** of §4.14,
for 110 registry keys in total. Each row is either audited (with its exact tuple) or
exempt with a written reason. No route appears in both states: an entry is
`Audited(...)` or `Exempt(...)`, never one in a matrix table and the other in §4.14.

**How to read a row**: *Endpoint* is the mounted path (router prefix from
`backend/app/main.py:82-133` + route path). *Site* is where `record_audit` is called
— the service function when one exists, otherwise the router. *athlete_id* is the
expression that fills the column, `—` meaning `NULL`. *reason* is the `reason_code`
requirement.

### 4.1 Auth and profile — `/api/auth`, `/api/profile`

| Endpoint | Site | entity_type · action | athlete_id | reason |
|---|---|---|---|---|
| `POST /api/auth/login` | `routers/auth.py:53` | **EXEMPT** — read-only credential check, no write | — | — |
| `POST /api/auth/refresh` | `routers/auth.py:89` | **EXEMPT** — token exchange, no DB write | — | — |
| `POST /api/auth/parent-register` | `routers/auth.py:245-260` (`consume_invite`) | `user`·`create` + `parent_athlete`·`link` + `parent_invite`·`update` | `invite.athlete_id` on the link row | — |
| `POST /api/auth/password-reset/request` | `routers/auth.py:299` | **EXEMPT** — writes only a reset token; recording it would build an account-enumeration oracle | — | — |
| `POST /api/auth/password-reset/confirm` | `routers/auth.py:349` (`consume_token`) | `user`·`update`, `changed_fields=["hashed_password"]`, `club_id=None` | — | — |
| `PATCH /api/profile/basic` | `services/profile.py::update_basic_info` | `user`·`update` (names/phone: names only) | — | — |
| `POST /api/profile/change-password` | `services/profile.py::change_password` | `user`·`update`, `["hashed_password"]` | — | — |
| `POST /api/profile/change-email/request` | `routers/profile.py:94` | **EXEMPT** — writes a pending-verification token only; the neutral response is an anti-enumeration requirement and the account is unchanged | — | — |
| `POST /api/profile/change-email/confirm` | `services/profile.py::confirm_email_change` | `user`·`update`, `["email"]` (never the address) | — | — |

`club_id=None` on the four self-service `user` rows is intentional and matches
`data-model.md` §1: they are invisible in the club history (FR-006) and visible in
the per-user trail.

### 4.2 Staff and clubs — `/api/users`, `/api/clubs`

| Endpoint | Site | entity_type · action | athlete_id | reason |
|---|---|---|---|---|
| `POST /api/users` | `routers/users.py:36` | `user`·`create` **+** `club_member`·`create` (same `request_id`) | — | — |
| `PATCH /api/users/{user_id}` | `routers/users.py:223` | `user`·`update`; `is_active` flip → `activate` / `deactivate`; `role` change → `role_change` | — | required for `deactivate` (`account_*`) |
| `DELETE /api/users/{user_id}` | `routers/users.py:280-347` | `user`·`delete` **+** one `parent_athlete`·`unlink` per removed link **+** `parental_consent`·`delete` **+** `club_member`·`delete` | per-link rows carry `ParentAthlete.athlete_id` | required (`parent_*`) |
| `POST /api/clubs/` | `routers/clubs.py:25` | `club`·`create` (`club_id` = the new club) | — | — |
| `PATCH /api/clubs/{club_id}` | `routers/clubs.py:88` | `club`·`update` | — | — |
| `POST /api/clubs/{club_id}/members` | `routers/clubs.py:114-158` | `club_member`·`create` | — | — |

Two pre-existing defects must be fixed in the same commits, because auditing them as
they stand would record a lie:

- `backend/app/routers/users.py:344-345` runs
  `UPDATE users SET created_by = NULL WHERE created_by = :user_id` on a parent
  deletion. It **must be removed** — it is the literal violation of US2 AS7
  (spec.md:50) and would silently erase attribution the audit row claims to preserve.
- `backend/app/routers/users.py:53-58` gates the "club is required" check on
  `current_user.role == coach`, so an admin can still create a club-less coach
  (`backend/tests/test_users.py:32-57` asserts 201 today). Contract `staff-admin.md`
  moves the check to the created account's role.

### 4.3 Athletes and their records — `/api/athletes`

| Endpoint | Site | entity_type · action | athlete_id | reason |
|---|---|---|---|---|
| `POST /api/athletes` | `routers/athletes.py:67` | `athlete`·`create` | new `athlete.id` | — |
| `PATCH /api/athletes/{athlete_id}` | `routers/athletes.py:285` | `athlete`·`update` | path | — |
| `DELETE /api/athletes/{athlete_id}` | `routers/athletes.py:329-367` | `athlete`·`archive` | path | **required** (`athlete_*`) |
| `POST /api/athletes/{athlete_id}/restore` *(new, admin-only)* | contract `athlete-archive.md` | `athlete`·`restore` | path | **required** (`restore_*`) |
| `POST /api/athletes/{athlete_id}/anthropometry` | `routers/anthropometry.py:112` | `anthropometric_record`·`create` | path | — |
| `POST /api/ai/athletes/{athlete_id}/phv-explanation` | `routers/ai.py:428` (`mysql_insert … on_duplicate_key_update`) | `athlete_ai_explanation`·`create` when the pre-SELECT at `:333-336` found nothing, else `update` | path | — |
| `POST /api/ai/athletes/{athlete_id}/measurements/{record_id}/explanation` | `routers/ai.py:584` (pre-SELECT at `:489-492`) | `athlete_ai_explanation`·`create` \| `update` | path | — |

`DELETE /api/athletes/{athlete_id}` keeps its route and status code; its body loses
the eight Core `delete()` statements at `backend/app/routers/athletes.py:359-366`
— including `delete(ParentalConsent)` at `:359`, the Ley 1581 evidence — and becomes
an UPDATE of the four archive columns plus one `record_audit`
(`data-model.md` §4.2, contract `athlete-archive.md`).

### 4.4 Parent links and consent — `/api/parent-athletes`, `/api/me/consent`

| Endpoint | Site | entity_type · action | athlete_id | reason |
|---|---|---|---|---|
| `POST /api/parent-athletes` | `routers/parent_athletes.py:73` | `parent_athlete`·`link` | `body.athlete_id` | — |
| `POST /api/parent-athletes/invite` | `routers/parent_athletes.py:239` | `parent_invite`·`create` | `body.athlete_id` | — |
| `DELETE /api/parent-athletes/{relation_id}` | `routers/parent_athletes.py:419` | `parent_athlete`·`unlink` | the relation's `athlete_id` | — |
| `POST /api/me/consent/renew` | `routers/consent.py:82` | `parental_consent`·`create` (+ `update` on the superseded row) | `body.athlete_id` | — |
| `POST /api/me/consent/withdraw` | `routers/consent.py:121` | `parental_consent`·`update` | `body.athlete_id` | — |

Consent rows are written by the **parent**: `actor_kind=user`, `actor_role=parent`.
Parents cannot read the history (FR-006); that does not exempt their writes.
Consent text, IP and user-agent are on the permanent ban list of
`data-model.md` §2.5 — only `athlete_id`, the policy version identifier and the
action reach the row.

### 4.5 Calendar — `/api/calendar/events`

| Endpoint | Site | entity_type · action | athlete_id | reason |
|---|---|---|---|---|
| `POST /api/calendar/events` | `services/calendar/events.py:101-158` | `calendar_event`·`create` | — (audience is a set) | — |
| `PATCH /api/calendar/events/{event_id}` | `services/calendar/events.py:355-396` | `calendar_event`·`update` | — | — |
| `DELETE /api/calendar/events/{event_id}` | `services/calendar/events.py:463-489` | `calendar_event`·`cancel` | — | **required** (`cancel_*`) |
| `DELETE /api/calendar/events/{event_id}/permanent` | `services/calendar/events.py:541-562` | `calendar_event`·`delete` **+** `training_session`·`delete` when the linked session is removed at `:552-559` | — | — |
| `POST /api/calendar/events/{event_id}/rsvp` | `services/calendar/attendances.py:27-70` | `event_attendance`·`create` \| `update` | `body.athlete_id` | — |

`create_event` also creates a parallel `TrainingSession` for
`event_type=TRAINING_SESSION` (`services/calendar/events.py:184-253`); that row gets
its own `training_session`·`create` entry under the same `request_id`.

### 4.6 Training sessions — `/api/training-sessions`

| Endpoint | Site | entity_type · action | athlete_id | reason |
|---|---|---|---|---|
| `POST /api/training-sessions` | `services/training/sessions.py:105-157` | `training_session`·`create` (`meta.convocados_count`) **+** `training_session_coach`·`create` per coach **+** `calendar_event`·`create` from `:588` | — | — |
| `PATCH /api/training-sessions/{session_id}` | `services/training/sessions.py:661-689` | `training_session`·`update`; roster edits → `training_session_coach`·`create` / `delete` | — | — |
| `POST /api/training-sessions/{session_id}/execute` | `services/training/sessions.py:730-745` | `training_session`·`execute` | — | — |
| `DELETE /api/training-sessions/{session_id}` | `services/training/sessions.py:751-777` | `training_session`·`cancel` | — | **required** (`cancel_*`) |
| `PUT /api/training-sessions/{session_id}/attendance` | `services/training/attendance.py:15-58` | one row per changed roster entry: `session_attendance`·`create` \| `archive` \| `restore` \| `delete` | each row's own `athlete_id` | — |
| `PATCH /api/training-sessions/{session_id}/attendance/{athlete_id}` | `services/training/attendance.py:68-97` | `session_attendance`·`update` | path | — |
| `POST /api/training-sessions/{session_id}/route-file` | `routers/training_sessions.py:690-780` | `training_session`·`update` (`changed_fields` names only) | — | — |
| `POST /api/training-sessions/{session_id}/media` | `routers/training_sessions.py:835-917` | `session_media`·`create` | — | — |
| `DELETE /api/training-sessions/{session_id}/media/{media_id}` | `routers/training_sessions.py:953-986` | `session_media`·`archive` (the model already has `deleted_at`, `models/session_media.py:70`) | — | — |
| `PATCH /api/training-sessions/{session_id}/media/{media_id}` | `routers/training_sessions.py:996-1037` | `session_media`·`update` | — | — |

**Roster-row granularity rule.** At session creation the roster rows are untouched
placeholders (`AttendanceStatus.AUSENTE`, `services/training/sessions.py:144-152`),
so they are summarised in `meta_json.convocados_count` on the single
`training_session`·`create` row. Per-athlete `session_attendance` rows start at the
first roster save. This is what keeps the volume estimate of `data-model.md` §9
(~3 000 attendance rows/year) exact and still satisfies FR-007.

`bulk_upsert_convocatoria` currently hard-deletes removed rows
(`delete(SessionAttendance)`, `services/training/attendance.py:40-45`). FR-016 splits
that: rows where all of `rpe_omni`, `rubric_effort`, `rubric_attitude`,
`rubric_technique`, `individual_feedback` are `NULL` are still deleted (`action=delete`);
any row carrying data gets `archived_at` and `action=archive`.

### 4.7 Monthly reports and the club project profile — `/api/clubs`

| Endpoint | Site | entity_type · action | athlete_id | reason |
|---|---|---|---|---|
| `POST /api/clubs/{club_id}/monthly-reports` | `services/training/reports.py:60-228` | `monthly_report`·`create`; on `force_regenerate` over an approved report → `update` **+** `unapprove` (same `request_id`, `data-model.md` §7.4) | — | — |
| `PATCH /api/clubs/{club_id}/monthly-reports/{year}/{month}/blocks` | `services/training/reports.py:758-823` | `monthly_report`·`update`; `status` → `approved` → also `approve`; cleared → also `unapprove` | — | — |
| `POST /api/clubs/{club_id}/monthly-reports/{year}/{month}/blocks/{block_key}/regenerate` | `services/training/reports.py:838-923` | `monthly_report`·`update` (`meta.period`) | — | — |
| `PUT /api/clubs/{club_id}/project-profile` | `routers/monthly_reports.py:748-783` | `club_project_profile`·`create` \| `update` | — | — |
| `PATCH /api/clubs/{club_id}/project-profile` | `routers/monthly_reports.py:796-834` | `club_project_profile`·`update` | — | — |
| `GET /api/parents/training/monthly-summary/{year}/{month}` | `routers/monthly_reports.py:850` | *not registered* — plain read, no document produced (FR-005) | — | — |

The regeneration branch at `backend/app/services/training/reports.py:194-200`
overwrites `generated_by_user_id`/`generated_at` and resets the status with nothing
preserved. It must first copy the approval pair into `previous_approved_*`
(`data-model.md` §7.4) — the audit rows describe that transition, they do not
substitute for it.

### 4.8 Family newsletters — `/api/athletes`, `/api/clubs`, `/api/training`

| Endpoint | Site | entity_type · action | athlete_id | reason |
|---|---|---|---|---|
| `POST /api/clubs/{club_id}/monthly-newsletters/batch` | `routers/athlete_monthly_newsletters.py:564-699` | one `athlete_monthly_newsletter`·`create` per athlete, **one shared `request_id`** (AS5), `meta.athlete_count` | each row's athlete | — |
| `POST /api/athletes/{athlete_id}/monthly-newsletters` | `routers/athlete_monthly_newsletters.py:670` | `athlete_monthly_newsletter`·`create` | path | — |
| `PATCH /api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}` | `routers/athlete_monthly_newsletters.py:1001-1087` | `athlete_monthly_newsletter`·`update`; when the edit clears an approval → also `unapprove` (US5 AS3) | path | — |
| `POST /api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}/regenerate-block` | `routers/athlete_monthly_newsletters.py:1097-1230` | `athlete_monthly_newsletter`·`update` | path | — |
| `POST /api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}/approve` | `routers/athlete_monthly_newsletters.py:1240-1267` | `athlete_monthly_newsletter`·`approve` | path | — |
| `POST /api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}/send` | `services/notification/newsletter_dispatcher.py:396-401` (before the commit at `:142`) | `athlete_monthly_newsletter`·`send`, `meta={"document_kind": "newsletter_email", "recipients_count": N}` | the newsletter's athlete | — |
| `POST /api/athletes/{athlete_id}/monthly-newsletters/attach-insights` | `routers/athlete_monthly_newsletters.py:1359-1476` | `athlete_monthly_newsletter`·`update` \| `link` | path | — |
| `POST /api/parents/me/athletes/{athlete_id}/newsletters/{newsletter_id}/read` | `routers/parent_newsletters.py:251-287` | `athlete_monthly_newsletter`·`update`, `changed_fields=["read_by_user_id","read_at"]`, `actor_role=parent` | path | — |

The dispatcher's row is written **per newsletter**, inside
`dispatch_newsletters`'s transaction, so a batch send of N newsletters produces N
`send` rows under one `request_id`. `coach_note`, `stage_log_json`,
`narrative_blocks` and `metrics_snapshot` are on the permanent ban list — a
newsletter row never carries content, only `status`, `year`, `month`, `edit_version`
and `hidden_blocks` keys (`data-model.md` §2.5).

### 4.9 AI runs and insights — `/api/race-analysis`, `/api/athletes`

| Endpoint | Site | entity_type · action | athlete_id | reason |
|---|---|---|---|---|
| `POST /api/race-analysis/runs` | `routers/race_analysis.py:558`, at the raw `INSERT INTO agent_runs` (`:635`) | `agent_run`·`create` | `body.athlete_id` when set | — |
| `POST /api/race-analysis/runs/{run_id}/hitl/{step_id}` | `routers/race_analysis.py:865-949` | `agent_run`·`approve` on accept/edit (`meta={"step_id":…, "has_edits": bool}`) \| `agent_run`·`unapprove` on reject (`meta={"step_id":…}`); both with `changed_fields=["decided_by_user_id","decided_at"]` and `meta.previous_status` | the run's athlete | — |
| `POST /api/race-analysis/runs/{run_id}/invalidate` | `routers/race_analysis.py:1598` | `agent_run`·`update`, `meta={"stale": true}` | the run's athlete | — |
| `POST /api/race-analysis/runs/{run_id}/cancel` | `routers/race_analysis.py:1627` | `agent_run`·`cancel`, `meta.previous_status` | the run's athlete | — |
| `POST /api/race-analysis/runs/{run_id}/re-execute` | `routers/race_analysis.py:1714` | `agent_run`·`execute`, `meta={"supersedes_run_id": <old id>}` | the run's athlete | — |
| `POST /api/race-analysis/race-events/{race_event_id}/runs` | `services/race/group_launch.py` | one `agent_run`·`create` per launched run, one shared `request_id`, `meta.athlete_count` | each run's athlete | — |
| `POST /api/race-analysis/chat` | `routers/race_analysis.py:1192` | **EXEMPT** — sessions are in-memory with a 1 h TTL (docstring `:1209-1210`); no DB write | — | — |
| `POST /api/clubs/{club_id}/session-assistant/clarify` | `routers/session_assistant.py:106-165` | **EXEMPT** — builds an aggregate context and calls the LLM; no DB write | — | — |
| `POST /api/clubs/{club_id}/session-assistant/draft` | `routers/session_assistant.py:173` | **EXEMPT** — same, no DB write | — | — |
| `POST /api/athletes/{athlete_id}/race-analysis/runs` | `routers/athlete_race_analysis.py:679` | `agent_run`·`create` | path | — |
| `POST /api/athletes/{athlete_id}/race-analysis/season-summary` | `routers/athlete_race_analysis.py:1056` | `agent_run`·`create` | path | — |
| `POST /api/athletes/{athlete_id}/race-analysis/insights/{insight_id}/answer` | `routers/athlete_race_analysis.py:413-466` | `athlete_ai_insight`·`update`, `changed_fields=["coach_answer_text","coach_answer_at","coach_answer_by_user_id"]` | path | — |
| *(no route)* run completion | `routers/race_analysis.py:729-742`, `routers/athlete_race_analysis.py:895-905` | `agent_run`·`update`, `actor_kind=system` | the run's athlete | — |

**`create` vs `execute` vs `approve` on `agent_run`.** The three verbs are not
interchangeable and the sentence catalogue (`audit-log-api.md` §7.5) is what fixes
their meaning: `create` = "lanzó un análisis de carrera" (a *new* run, whatever the
entry point — club, athlete or season summary), `execute` = "volvió a ejecutar un
análisis de carrera" (reserved for `/re-execute`, which supersedes an existing run),
`approve` / `unapprove` = "resolvió la decisión pendiente" (the HITL step). This
matches `scope-ai-imports.md` §5 and `quickstart.md` step 18 (`agent_run/create`)
exactly; an earlier draft of this table mapped the launch to `execute` and the HITL
decision to `update`, which rendered as "volvió a ejecutar" for a first run and
"actualizó el análisis de carrera" for a decision — both misleading, and both
invisible to a one-directional catalogue test. `audit-log-api.md` §13 T7 now asserts
the mapping in **both** directions, so a tuple with no template and a template with no
tuple each fail.

`coach_answer_text` is a name in `changed_fields` and a value **nowhere**. The
deciding user (`by_user_id`, `routers/race_analysis.py:920`) is currently built into
`resume_value` and dropped from the persisted payload at `:938-947`; FR-028 requires
it, so it lands in `agent_runs.decided_by_user_id` (`data-model.md` §4.8) *and* in the
audit row.

### 4.10 Race results domain — `/api/race-analysis/*`, `/api/race-competitors`

| Endpoint | Site | entity_type · action | athlete_id | reason |
|---|---|---|---|---|
| `POST /api/race-analysis/race-series/` | `routers/race_series.py:126` | `race_series`·`create` | — | — |
| `POST /api/race-analysis/imports/parse` | `routers/race_imports.py:328-499` | `race_import`·`create` | — | — |
| `POST /api/race-analysis/imports/{parse_id}/dry-run` | `routers/race_imports.py:851-863` | `race_import`·`update` (`status` → `dry_run`) | — | — |
| `POST /api/race-analysis/imports/{parse_id}/commit` | `services/race/ingestor.py:254,449` — **after** the early commit at `routers/race_imports.py:1017` | `race_import`·`execute`, `changed_fields=["status","committed_by_user_id","committed_at"]`, `meta={"results_count":…, "competitors_count":…, "race_event_id":…, "is_revision": bool}` | — | — |
| `POST /api/race-analysis/race-events/` | `routers/race_events.py:446` | `race_event`·`create` | — | — |
| `PATCH /api/race-analysis/race-events/{race_event_id}` | `routers/race_events.py:531` | `race_event`·`update` | — | — |
| `DELETE /api/race-analysis/race-events/{race_event_id}` | `routers/race_events.py:568` | `race_event`·`delete` | — | — |
| `DELETE /api/race-analysis/race-events/{race_event_id}/cleanup` | `routers/race_events.py:601` | `race_event`·`delete`, `meta.job="duplicate_cleanup"` | — | — |
| `POST /api/race-analysis/race-events/{race_event_id}/roster` | `routers/race_events.py:279` | `race_event_roster`·`create` | `body.athlete_id` | — |
| `PATCH /api/race-analysis/race-events/{race_event_id}/roster/{entry_id}` | `routers/race_events.py:323` | `race_event_roster`·`update` | the entry's athlete | — |
| `DELETE /api/race-analysis/race-events/{race_event_id}/roster/{entry_id}` | `routers/race_events.py:366` | `race_event_roster`·`delete` | the entry's athlete | — |
| `POST /api/race-analysis/race-events/{race_event_id}/calendar-link` | `routers/race_events.py:637` | `race_event`·`link`, `meta.related_entity_id=<calendar_event_id>` | — | — |
| `POST /api/race-analysis/race-events/{race_event_id}/calendar-event` | `routers/race_events.py:694-741` | `calendar_event`·`create` **+** `race_event`·`link` | — | — |
| `PATCH /api/race-analysis/race-events/{race_event_id}/conditions` | `routers/race_events.py:761` | `race_event`·`update` | — | — |
| `PUT /api/race-analysis/race-events/race-results/{result_id}/coach-note` | `routers/race_events.py:870` | `race_result`·`update`, `["coach_note","coach_note_author_id","coach_note_updated_at"]` | the result's athlete | — |
| `DELETE /api/race-analysis/race-events/race-results/{result_id}/coach-note` | `routers/race_events.py:940` | `race_result`·`update` | the result's athlete | — |
| `POST /api/race-competitors/{competitor_id}/link` | `services/race/competitor_linking.py:612-621` (next to the existing `RaceCompetitorLinkAudit` insert) | `race_competitor`·`link`, `meta.results_count=<propagated>` | the linked athlete | — |
| `DELETE /api/race-competitors/{competitor_id}/link` | `services/race/competitor_linking.py:700-709` | `race_competitor`·`unlink` | the previously linked athlete | — |

The two domain trails are **kept, not replaced**: `race_result_revisions`
(`backend/app/services/race/revision.py:737-801`) and `race_competitor_link_audit`
(`backend/app/models/race_competitor_link_audit.py`) stay as the per-result detail,
and the `audit_log` row is the club-wide index that points at them
(spec.md:280). A committed import therefore produces **one** `race_import` row here,
not one row per result.

`DELETE /race-events/{id}/cleanup` and `POST /race-events/{id}/calendar-event` are
coach-only today and 403 an admin (`routers/race_events.py:606-609,700-703`),
inconsistent with every other mutation in that module. Out of scope for this
contract; flagged for the owner (research "Contradictions resolved").

### 4.11 Interval training — `/api/intervals`

| Endpoint | Site | entity_type · action | athlete_id | reason |
|---|---|---|---|---|
| `POST /api/intervals/structures` | `services/intervals/structures.py:554-629` | `interval_structure`·`create` | — | — |
| `PUT /api/intervals/structures/{structure_id}` | `services/intervals/structures.py:701-772` | `interval_structure`·`update` | — | — |
| `DELETE /api/intervals/structures/{structure_id}` | `services/intervals/structures.py:785-821` | `interval_structure`·`delete` | — | — |
| `POST /api/intervals/structures/{structure_id}/recalculate` | `routers/intervals.py:760` (dispatch) + `services/intervals/match_runner.py:358-396` (deferred, own session) | `interval_structure`·`execute` (dispatch, `actor_kind=user`) **+** `interval_structure`·`execute` (completion, `actor_kind=system`, `meta.job="interval_match"`) | the activity's athlete on the deferred row | — |
| `POST /api/intervals/templates` | `services/intervals/templates.py:170-230` | `interval_template`·`create` | — | — |
| `PUT /api/intervals/templates/{template_id}` | `services/intervals/templates.py:305-369` | `interval_template`·`update` | — | — |
| `PATCH /api/intervals/templates/{template_id}/archive` | `services/intervals/templates.py:381-414` | `interval_template`·`archive` | — | — |
| `POST /api/intervals/templates/{template_id}/attach` | `services/intervals/templates.py:431` | `interval_template`·`link`, `meta.related_entity_id=<training_session_id>` | — | — |

### 4.12 Strava, activities and webhooks — `/api`, `/api/webhooks`

Mounted only when `settings.strava_enabled` (`backend/app/main.py:120-133`). The
route-registry test iterates the mounted app, so both states are valid; the registry
entries are declared unconditionally and the test skips the missing routes when the
flag is off.

| Endpoint | Site | entity_type · action | athlete_id | reason |
|---|---|---|---|---|
| `POST /api/athletes/{athlete_id}/strava/connect` | `routers/strava_integration.py:126` | **EXEMPT** — builds the OAuth redirect, no DB write | — | — |
| `DELETE /api/athletes/{athlete_id}/strava/connection` | `routers/strava_integration.py:156` | `strava_connection`·`unlink` | path | — |
| `POST /api/integrations/strava/webhook` | ACK at `routers/strava_integration.py:376` | **EXEMPT** — ACK only; the rows are written by `_process_webhook_event_deferred` (`:346-374`), which runs after the response on its own session and is covered by the §3.3 non-HTTP caller table | — | — |
| `POST /api/integrations/strava/reconcile` | `routers/strava_integration.py:409-427` → `services/strava/*::reconcile_all` | one row per created/updated `strava_activity`, `actor_kind=cron`, `meta.job="strava_reconcile"` | each activity's athlete | — |
| `PATCH /api/activities/{activity_id}/link` | `routers/activities.py:368` | `strava_activity`·`link` (or `unlink` when `training_session_id is None`), `meta.related_entity_id` | the activity's athlete | — |
| `POST /api/webhooks/resend` | `routers/webhooks_resend.py:199-201`, after the successful `flush()` at `:189` | `athlete_monthly_newsletter`·`update`, `actor_kind=webhook`, `meta={"job":"resend_webhook","event_type":"<delivered\|opened\|bounced\|…>"}` | the newsletter's athlete | — |

The existing correlation idiom in this domain — a locally generated
`uuid.uuid4().hex[:12]` threaded as an argument
(`backend/app/services/strava/ingest.py:91-97`) — is superseded by the 32-char
`request_id`; the shorter id may remain in the log lines, but the audit row carries
the canonical one.

### 4.13 Mutating and exporting GETs

FR-005 records exports; FR-005 also forbids recording plain reads. These nine GETs
are the entire intersection, and they must be listed **explicitly** in the coverage
registry, because the route walk of §7 (test T4.1) only scans
`{POST, PUT, PATCH, DELETE}` and would miss every one of them.

| Endpoint | Site | entity_type · action | `meta.document_kind` | athlete_id |
|---|---|---|---|---|
| `GET /api/athletes/{athlete_id}/report/pdf` | `routers/reports.py:75-136` | `athlete`·`export` | `growth_pdf` | path |
| `GET /api/athletes/{athlete_id}/clearance/docx` | `routers/reports.py:143-194` | `athlete`·`export` | `clearance_docx` | path |
| `POST /api/athletes/{athlete_id}/report/email` *(POST, listed here for symmetry)* | `routers/reports.py:200-284` | `athlete`·`send` | `growth_pdf` | path |
| `GET /api/clubs/{club_id}/monthly-reports/{year}/{month}/pdf` | `routers/monthly_reports.py:424-557` | `monthly_report`·`export` | `monthly_report_pdf` | — |
| `GET /api/clubs/{club_id}/monthly-reports/{year}/{month}/docx` | `routers/monthly_reports.py:564-706` | `monthly_report`·`export` | `monthly_report_docx` | — |
| `GET /api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}/pdf` | `routers/athlete_monthly_newsletters.py:778-841` | `athlete_monthly_newsletter`·`export` | `newsletter_pdf` | path |
| `GET /api/parents/me/athletes/{athlete_id}/newsletters/{newsletter_id}/pdf` | `routers/parent_newsletters.py:184-243` | `athlete_monthly_newsletter`·`export`, `actor_role=parent` | `newsletter_pdf` | path |
| `GET /api/intervals/sessions/{training_session_id}/instructivo` | `routers/intervals.py:842-898` | `training_session`·`export` | `session_instructivo_pdf` | — |
| `GET /api/race-analysis/runs/{run_id}/pdf` | `routers/race_analysis.py:1075-1184` | `agent_run`·`export` | `race_analysis_pdf` | the run's athlete |
| `GET /api/integrations/strava/callback` | `routers/strava_integration.py:201-313` (writes the connection at `:283-307`) | `strava_connection`·`link` | — | resolved from the OAuth state |

Two call-site hazards, both real in today's code:

1. `routers/athlete_monthly_newsletters.py:828-832` and
   `routers/parent_newsletters.py:230-234` commit **only** when the PDF hash changed
   (`if nl.pdf_sha256 != sha256:`). The export row must be recorded on **every**
   download, outside that branch; it is committed by `get_db` at
   `backend/app/dependencies.py:21` after the handler returns.
2. The export row is queued **after** the document has been generated successfully,
   so a WeasyPrint/docxtpl failure produces no "export" that never happened.

`GET /api/integrations/strava/callback` is the only *mutating* GET: it is not an
export, it links an account, and it is precisely the route a POST-only registry walk
would let ship unaudited.

Two further coach-facing GETs serve a document or media containing a minor's data and
sit close enough to FR-005's "exports … of documents containing a minor's data" to
need an explicit verdict. Both were examined and both are **not** exports; they are
recorded as exemptions in §4.14 rather than left invisible, so the judgement is
reviewable instead of implicit.

### 4.14 Exempt-with-reason registry (complete)

Every exemption above, in one place. The registry entry carries the reason string
verbatim, and the coverage test prints it on failure.

| Endpoint | Reason |
|---|---|
| `POST /api/auth/login` | Read-only credential check; no row is written. |
| `POST /api/auth/refresh` | Token exchange in memory; no row is written. |
| `POST /api/auth/password-reset/request` | Writes only a single-use reset token. Recording it (success or failure) would turn the history into an account-enumeration oracle. |
| `POST /api/profile/change-email/request` | Writes only a pending-verification token; the account is unchanged and the response is deliberately neutral against enumeration. The applied change is audited at `/change-email/confirm`. |
| `POST /api/clubs/{club_id}/session-assistant/clarify` | Stateless LLM call; no DB write (`routers/session_assistant.py:106-165`). |
| `POST /api/clubs/{club_id}/session-assistant/draft` | Stateless LLM call; no DB write (`routers/session_assistant.py:173`). |
| `POST /api/race-analysis/chat` | In-memory sessions with a 1 h TTL; no DB write (`routers/race_analysis.py:1209-1210`). |
| `POST /api/athletes/{athlete_id}/strava/connect` | Builds the OAuth redirect URL only; the write happens in the audited callback. |
| `POST /api/integrations/strava/webhook` | The handler itself only ACKs (`routers/strava_integration.py:376`) and writes nothing. The rows are written after the response by `_process_webhook_event_deferred` (`:346-374`), which has no route of its own and is specified in the §3.3 non-HTTP caller table. |
| `GET /api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}/render` | In-app preview of the family e-mail surface (`?surface=email`, the only accepted value), admin/coach only (`routers/athlete_monthly_newsletters.py:849-858`). The registry key is the mounted path template, without the query string, so it resolves under T4.2. It renders HTML into the coach's own screen; nothing is produced, stored or sent, so it is a read under FR-005, not an export. The download that *is* an export is the audited `/pdf` route of §4.13, and the send is the audited `/send` route of §4.8. |
| `GET /api/training-sessions/{session_id}/media` | Media listing for one session (`routers/training_sessions.py:929-950`): stored metadata, already narrowed per role (a parent sees only their own athletes' media, `:945-948`). No file leaves the system and no document is generated, so FR-005's "plain page reads MUST NOT be recorded" governs. The audited events on this media are `create` / `update` / `archive` (§4.6). |

**Eleven exemptions out of 110 registered routes** — 99 mutating routes (§4.1–§4.12),
the 9 mutating or exporting GETs of §4.13, and the 2 GETs above, which are registry
keys only. Any twelfth requires a written reason in this table and a reviewer's
approval — the registry is not a place to park work.

The last two entries are the only registry keys the coverage walk of §9 T4.1 does not
reach on its own: they are neither in `{POST, PUT, PATCH, DELETE}` nor in
`MUTATING_GETS`. They are declared anyway, precisely so that "is this an export?" is a
decision someone wrote down and a reviewer can overturn, rather than a route nobody
looked at. T4.2 (no stale entries) and T4.3 (exempt set equals this table) still cover
them; T4.1 does not need to.

---

## 5. Append-only invariants on the write side (FR-004)

`data-model.md` §1.2 states the invariants; this contract states what the *code* may
contain:

1. `AuditLog` is constructed in exactly one place — `record_audit`. No other module
   imports the class to instantiate it.
2. No module may issue `update(AuditLog)`, `delete(AuditLog)` or
   `session.delete(<AuditLog instance>)`. The single exception is
   `backend/app/services/retention.py` (contract `retention-purge.md`).
3. `record_audit` never mutates a returned row; the caller must not either. The
   returned object exists so a test can assert on it, not so a service can amend it.
4. The purge is **additive** at this layer: it writes one `purge` row and is the only
   code path allowed to remove others.

Enforced by `backend/tests/test_audit_append_only.py` (§9, T5).

---

## 6. Structured logging with `request_id`

Verified 2026-09-09: nothing under `backend/app/` calls `logging.dictConfig` or
`logging.basicConfig`, and `backend/entrypoint.sh` launches a bare
`uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1` with no `--log-config`.
Uvicorn's default `LOGGING_CONFIG` configures only `uvicorn`, `uvicorn.error` and
`uvicorn.access`, each with `propagate: False`, and never touches root — so every
`logger.info(...)` in `app/services/**` is discarded in production today, and
`logger.error` surfaces only through Python's `lastResort` handler with no timestamp.

Minimum configuration, applied at the top of `backend/app/main.py` **before** the
`FastAPI(...)` instantiation at `backend/app/main.py:52-57`:

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,          # never drop uvicorn's own loggers
    "filters": {
        "request_id": {"()": "app.services.request_context.RequestIdFilter"},
    },
    "formatters": {
        "app": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(levelprefix)s %(asctime)s [%(request_id)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "app": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "app",
            "filters": ["request_id"],
        },
    },
    "loggers": {
        "app": {"handlers": ["app"], "level": "INFO", "propagate": False},
    },
}
logging.config.dictConfig(LOGGING)
```

Rules:

- `RequestIdFilter.filter()` sets `record.request_id = current_request_id() or "-"`.
  It never raises, and it never reads anything else from the context.
- Scope is the `app` logger tree only. `uvicorn.access` is left exactly as uvicorn
  configured it; `disable_existing_loggers: False` is what keeps it alive, and a
  missing `False` here silences the whole server (research R-27).
- `level` comes from `settings.app_debug` (`backend/app/config.py:22`): `DEBUG` when
  true, `INFO` otherwise.
- **Never log a request or response body**, an e-mail address, a name, a measurement
  or an AI output (Constitution — Observability; `AI_LOG_PROMPTS` stays `false`).
  `record_audit`'s own line is counts only:
  `logger.debug("audit_recorded", extra={"entity_type": …, "action": …, "fields": len(changed_fields), "dropped": n_dropped})`.
- The existing unhandled-exception handler (`backend/app/main.py:68-81`) already logs
  method, path and exception type without the body; it gains the `request_id` for
  free through the filter.

---

## 7. Coverage registry (FR-009)

```python
# backend/app/services/audit.py

@dataclass(frozen=True, slots=True)
class Audited:
    entities: frozenset[AuditEntityType]   # every type this route may write
    min_rows: int = 1                      # rows expected for one successful call

@dataclass(frozen=True, slots=True)
class Exempt:
    reason: str                            # verbatim from the §4.14 table

AuditPolicy = Audited | Exempt

AUDITED_ROUTES: dict[tuple[str, str], AuditPolicy] = { ... }   # (method, path_template)

MUTATING_GETS: frozenset[tuple[str, str]] = frozenset({        # §4.13
    ("GET", "/api/athletes/{athlete_id}/report/pdf"),
    ...
})
```

Keys are `(method, route.path)` using the **mounted** path template exactly as
FastAPI exposes it on `app.routes`, so the test needs no server and no HTTP call to
detect a missing entry.

Three layers, with complementary blind spots (research R-06):

| Layer | Catches | Misses |
|---|---|---|
| Static registry meta-test | a new mutating route merged without a decision | a registry entry that lies |
| Dynamic per-router smoke | a service that says it audits and does not | routes nobody wrote a smoke for |
| `AUDIT_STRICT=true` flush detector (test lane only) | a service that mutates a *second* table without recording it | nothing outside a test run |

The strict detector is a session-level `before_flush` hook, active only when
`AUDIT_STRICT=true` (test lane, `plan.md` Complexity Tracking). It inspects
`session.new | session.dirty | session.deleted` for instances of an audited model and
fails the test when no pending `AuditLog` shares the flush. It is a **detector**, never
the recording mechanism: flush events are blind to the ~20 Core statements that carry
the most audit-worthy mutations (`routers/athletes.py:359-366`,
`routers/users.py:333-346`, `services/training/attendance.py:41`,
`services/calendar/events.py:207,452,484`, `routers/ai.py:428,584`, and the raw
`text()` `agent_runs` layer at `routers/race_analysis.py:635,930,1679`).

---

## 8. Test-lane prerequisite — `audit_log` in the subset harnesses

**77 test files** call `Base.metadata.create_all(..., tables=[...])` with an explicit
subset of tables (measured 2026-09-09; the idiom is visible at
`backend/tests/test_race_series_router.py:48-100`). Any of them that exercises an
audited write will now fail with `no such table: audit_log`.

Required, once, as part of Setup:

- A shared helper `backend/tests/helpers/audit_tables.py::AUDIT_TABLES`
  (`["audit_log", "training_session_coaches"]`) that every subset harness appends to
  its `_TABLES` list, instead of 77 hand-edited literals.
- The dependency override used by those harnesses already mirrors `get_db`'s commit
  (`backend/tests/test_race_series_router.py:106-116`), so audit rows are visible to
  the assertions without further change.

---

## 9. Required tests

Offline `aiosqlite` lane unless stated. Every test name below is a deliverable.

**T1 — `tests/services/test_audit_helper.py` (unit, `record_audit`)**
1. Happy path: `db.add` called, nothing flushed, nothing committed (assert
   `session.new` contains the row and the DB is still empty).
2. `actor_kind=user` with `actor=None` → `AuditContractError`.
3. `actor_kind=cron` with an `actor` → `AuditContractError`.
4. `actor_role` equals the actor's role at call time and does **not** change when the
   user's role is later updated in the same session.
5. Unknown `entity_type` → `AuditContractError`.
6. No `request_id` in scope and none passed → `AuditContractError`.
7. `REASON_REQUIRED` pair without `reason_code` → `AuditReasonRequired`.
8. `action=update` with empty `changed_fields` and empty `diff` → returns `None`,
   nothing added (R7).
9. Non-allow-listed key in `diff` → dropped from `diff_json`, still present in
   `changed_fields`.
10. Unknown `meta_json` key → `AuditContractError`.
11. `occurred_at` carries microseconds (`.microsecond != 0` over 50 constructions).
12. **`META_ALLOWLIST` drift guard.** Parse the nine contract files under
    `specs/041-multi-coach-governance/contracts/`, collect every `meta_json` key
    literal they emit — the keys of every inline `meta_json={...}` / `meta={...}`
    mapping, plus every `meta_json.<key>` / `meta.<key>` dotted reference in an audit
    table — and assert the collected set is a **subset** of `META_ALLOWLIST`. The
    failure message names the offending key and the contract file, so the fix is
    obvious: extend §1.7 or stop emitting the key. This is the test that would have
    caught `event_date`, `role`, `set_password_email`, `step_id`, `has_edits`,
    `stale`, `supersedes_run_id`, `race_event_id`, `is_revision`, `block` and `rows`
    being emitted by six contracts while §1.7 refused all eleven.

**T2 — `tests/services/test_compute_changed_fields.py` (unit)**
1. The §2.3 worked example, exactly.
2. Enum, `datetime`, `date`, `Decimal`, `set` normalisation, one case each.
3. A key present in only one mapping is skipped, not reported as a change.
4. Identical mappings → `([], {})`.
5. `changed_fields` is sorted and stable across two runs.
6. A value the normaliser cannot serialise → `AuditContractError`.

**T3 — `tests/services/test_request_context.py` (unit + ASGI)**
1. The middleware sets a 32-hex `request_id` and echoes `X-Request-Id`.
2. Two concurrent requests get different ids and neither leaks into the other
   (`asyncio.gather` over two handlers that read `current_request_id()`).
3. The ContextVar is reset after the response (`current_request_id() is None`).
4. An inbound `X-Request-Id` is ignored on a normal route and honoured on
   `POST /api/integrations/strava/reconcile` when it matches `^[0-9a-f]{32}$`.
5. A malformed inbound id is ignored, not echoed.
6. `request_id_scope()` binds and resets for a non-HTTP unit of work.
7. `AuditContext.for_job(AuditActorKind.user, …)` → `AuditContractError`.

**T4 — `tests/test_audit_coverage.py` (FR-009, the gate)**
1. **Registry completeness**: walk `app.routes`; every `APIRoute` whose `methods`
   intersect `{POST, PUT, PATCH, DELETE}`, plus every member of `MUTATING_GETS`, has
   an `AUDITED_ROUTES` entry. Failure message names the missing `(method, path)` and
   points at this contract.
2. **No stale entries**: every registry key resolves to a mounted route (with the
   `strava_enabled` skip).
3. **Exemptions are justified**: every `Exempt` has a non-empty reason ≥ 20
   characters, and the set of exempt keys equals the §4.14 table exactly.
4. **Dynamic smoke**, parametrised over the `Audited` entries that declare a factory:
   call the endpoint against the offline app as a coach of the club and assert
   (a) `SELECT COUNT(*) FROM audit_log` increased by at least `min_rows`,
   (b) all new rows share one `request_id`,
   (c) every new row's `entity_type` is in the entry's `entities`,
   (d) `club_id` is non-null unless the pair is in `CLUB_OPTIONAL`.
5. **Multi-row correlation** (AS5): a roster save over 5 athletes writes 5 rows with
   one `request_id`; the batch newsletter endpoint over 3 athletes writes 3.
6. **Failed request writes nothing** (spec.md:168): force an error after the business
   write inside one endpoint and assert `audit_log` is empty and the data change was
   rolled back.
7. **Automated actor** (AS4): drive `POST /api/webhooks/resend` with a valid Svix
   signature and assert the row has `actor_kind=webhook`, `actor_user_id IS NULL`,
   `actor_role IS NULL` — and specifically **not** the id of a user who logged in
   earlier in the same test.
8. **Svix replay** writes no second row (the `rollback()` path at
   `routers/webhooks_resend.py:190-197`).
9. **Export is recorded, read is not**: `GET …/report/pdf` writes one `export` row;
   `GET /api/athletes/{id}` and `GET …/monthly-newsletters/{id}` write none.
10. **Export is recorded even when the PDF hash is unchanged** (the branch at
    `routers/athlete_monthly_newsletters.py:828-832`): download twice, assert two
    `export` rows.

**T5 — `tests/test_audit_append_only.py` (FR-004)**
1. Static: AST-walk `backend/app/**/*.py`; fail on `update(AuditLog)`,
   `delete(AuditLog)`, `session.delete(<AuditLog>)` or an attribute assignment on an
   `AuditLog` instance outside `app/services/audit.py` and `app/services/retention.py`.
2. Static: `AuditLog(` is constructed only inside `app/services/audit.py`.
3. Behavioural: run a 20-action scenario (SC-001), snapshot every row's
   `(id, occurred_at, action, diff_json)`, run 20 more actions, assert no snapshot
   changed and the count never decreased.

**T6 — `tests/test_audit_privacy.py` (FR-003, second half of SC-001)**
Modelled on `backend/tests/test_privacy.py:31`. Run the same 20-action scenario with
a synthetic two-coach / two-athlete fixture, then scan **every** produced row:
1. No key in `diff_json` outside `VALUE_ALLOWLIST[entity_type]`.
2. No key in `meta_json` outside `META_ALLOWLIST`.
3. Zero occurrences of the fixture's synthetic first/last names in any column.
4. Zero ISO date-of-birth-shaped strings.
5. Zero measurement-shaped numerics (`\d{2,3}\.\d` in a `*_cm`/`*_kg` context).
6. `hidden_blocks` values, when present, are members of the known block-key set —
   never free text.
7. Captured `app.*` log records over the scenario contain no name, no e-mail address
   and no birth date, and every record carries a `request_id`.

**T7 — `tests/test_audit_actors.py` (FR-002, FR-013)**
1. Two coaches of one club act on the same session; each row names the right actor
   (0 misattributions, SC-001).
2. A deactivated coach's `actor_user_id` still resolves to a display name (FR-013).
3. `actor_role` on a historical row is unchanged after the actor's role changes.
4. `DELETE /api/users/{parent_id}` no longer nulls `users.created_by` — regression
   test for `routers/users.py:344-345`; it must fail on today's code (US2 AS7).

**T8 — `mysql` lane, `tests/test_audit_mysql.py` (`pytest -m mysql`)**
1. `SHOW CREATE TABLE audit_log` contains `datetime(6)`.
2. A written row round-trips its microseconds.
3. Two rows written inside the same second are ordered deterministically by
   `(occurred_at DESC, id DESC)`.

**T9 — query budget, `tests/test_audit_query_count.py`**
Using `backend/tests/helpers/query_counting.py`: one audited write adds exactly **one**
INSERT and **zero** extra SELECTs beyond what the endpoint already issued (the actor
and club are already loaded). Guards the p95 ≤ 1500 ms write budget (Constitution IV).

---

## 10. Open points for the implementer

1. `research.md` R-01/R-05 describe `request_id String(36)` and an eight-value
   `AuditActorKind` (`person`, `webhook_resend`, …). `data-model.md` §1/§2.2 supersedes
   both with `String(32)` (`uuid4().hex`) and four values (`user`, `system`, `webhook`,
   `cron`), with the specific job in `meta_json.job`. **This contract follows
   `data-model.md`.**
2. Registering `RequestIdMiddleware` *after* the `CORSMiddleware` call makes it the
   outermost layer (Starlette prepends); `research.md` R-05's phrasing ("before
   `CORSMiddleware`") reads the other way. Verify the emitted order once with
   `app.user_middleware` in the middleware test.
