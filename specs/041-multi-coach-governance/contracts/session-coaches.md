# Contract — Co-coached sessions, acting-coach notifications, attendance attribution and calendar-event cancellation

Covers US4 (spec.md:74-91) and FR-011, FR-016, **FR-017**, FR-024, FR-025, FR-026, plus
the "only coach is inactive" edge case (spec.md:169). Schema is fixed by
[data-model.md](../data-model.md) §3 (`training_session_coaches`), §4.3
(`session_attendance`), §4.4 (`calendar_events`), §7.2 and §7.5; decisions by
[research.md](../research.md) R-11, R-17, R-18, R-19.

Product copy in this document is **español neutro (Colombia) with diacritics**; the
document itself is English (constitution III).

---

## 1. Naming reconciliation (read this before implementing)

The brief and `research.md` use working names that differ from the code and from
`data-model.md`. `data-model.md` and the real code win; this table is the mapping so no
one implements a ghost symbol.

| Name used elsewhere | Authoritative name | Source |
|---|---|---|
| `TrainingSessionOut` | `TrainingSessionRead` (coach/admin) and `TrainingSessionReadParent` (family) | `backend/app/schemas/training_session.py:138`, `:167` |
| `SessionCreate` / `SessionUpdate` | `TrainingSessionCreate` / `TrainingSessionUpdate` | `backend/app/schemas/training_session.py:38`, `:75` |
| `AttendanceOut` | `AttendanceRead` / `AttendanceReadParent` | `backend/app/schemas/training_session.py:258`, `:278` |
| bridge column `user_id` (research R-17) | **`coach_user_id`** | data-model.md §3, backfill B1 (data-model.md §6.3) |
| bridge `UniqueConstraint(session_id, user_id)` (R-17) | **composite PK** `(session_id, coach_user_id)` | data-model.md §3 |
| attendance `last_edited_by_user_id` / `last_edited_at` (R-11) | **`updated_by_user_id`** + the existing `updated_at` (`backend/app/models/training_session.py:199`) | data-model.md §4.3 |
| attendance `archived_by_user_id` (R-11) | **not added** — the actor lives in the `audit_log` row of the same `request_id` | data-model.md §4.3 |

The API response field names `recorded_by_display_name` / `last_edited_by_display_name`
are kept from the brief: the *column* is `updated_by_user_id`, the *rendered* concept is
"última edición", and the response name is what the coach reads about.

**No column is added to `training_sessions`.** data-model.md §4 lists attribution columns
for eleven tables and `training_sessions` is not one of them; §5's mixin table does not
apply a mixin to `TrainingSession` either. Who updated / executed / cancelled a session is
therefore answered **only** by `audit_log` (§9 below), and the session response exposes no
`updated_by_user_id`.

That is a **decided narrowing of FR-010**, not an open question for this contract to leave
hanging. `training_sessions` keeps `created_by_user_id`
(`backend/app/models/training_session.py:76`) and `updated_at` (`:104`); only the
last-editor *actor* lives exclusively in the log, written in the same transaction as the
edit (§9; audit-recording.md §4.6). The identical narrowing covers `race_events`,
`race_event_roster`, `interval_structures` and `interval_templates` — editable club records
that data-model.md §4.8 gives no attribution column and whose mutating endpoints are all
instrumented (audit-recording.md §4.10, §4.11). The decision, its accepted cost (the actor
is one indexed `audit_log` query away instead of one column, and it disappears with the
24-month purge of FR-030) and the rejected alternative are recorded as the FR-010 row of
plan.md's **Complexity Tracking** table, where the owner reads it at review time.

Reversing it, if a "última edición por" surface is ever designed for these records, is one
nullable `updated_by_user_id` FK per table (`UpdatedByMixin` already exists, data-model.md
§5) plus `"updated_by_user_id"` in each entity's `VALUE_ALLOWLIST` entry (data-model.md
§2.5) — a data-model.md change first, then this contract and §3.1's response.

---

## 2. Data surface (recap — no new schema decisions here)

| Object | Columns this contract reads/writes | Defined in |
|---|---|---|
| `training_session_coaches` | `session_id`, `coach_user_id`, `added_by_user_id`, `added_at` | data-model.md §3 |
| `session_attendance` | new: `recorded_by_user_id`, `updated_by_user_id`, `archived_at`; existing: `status`, `rpe_omni`, `rubric_*`, `individual_feedback`, `updated_at` | data-model.md §4.3; `backend/app/models/training_session.py:153-216` |
| index `ix_session_attendance_archived_at` | filter support for every active read | data-model.md §6.2 step 4 |
| index `ix_tsc_coach_user_id` | the `coach_user_id` listing filter | data-model.md §3 |

New ORM relationships (declarative only, no DDL beyond §3/§4.3):

```text
TrainingSession.session_coaches -> list[TrainingSessionCoach]
    back_populates="session", cascade="all, delete-orphan",
    order_by="TrainingSessionCoach.added_at"

TrainingSessionCoach.coach     -> User   (foreign_keys=[coach_user_id])
TrainingSessionCoach.session   -> TrainingSession

SessionAttendance.recorded_by  -> User | None (foreign_keys=[recorded_by_user_id])
SessionAttendance.updated_by   -> User | None (foreign_keys=[updated_by_user_id])
```

The relationship is named `session_coaches`, **not** `coaches`, so it never reads as the
API field of the same name. `TrainingSession.attendances`
(`backend/app/models/training_session.py:127-131`) is **not** given a filtered
`primaryjoin`: it carries `cascade="all, delete-orphan"`, and hiding archived rows from
the collection is exactly the kind of subtlety that turns an archive into a delete.
Archived rows are filtered at each consumer instead — the same idiom already used for
soft-deleted media at `backend/app/routers/training_sessions.py:105`. See §6.3.

---

## 3. API — session coaches

### 3.1 Response (`TrainingSessionRead`, coach/admin)

Two additive fields on `backend/app/schemas/training_session.py:138-164`:

```json
{
  "id": 512,
  "club_id": 1,
  "created_by_user_id": 7,
  "status": "planned",
  "scheduled_date": "2026-09-15",
  "coaches": [
    { "user_id": 7, "display_name": "Ana Coach" },
    { "user_id": 9, "display_name": "Bruno Coach" }
  ],
  "has_active_coach": true
}
```

```text
class SessionCoachOut(BaseModel):
    user_id: int
    display_name: str        # resolved by the shared actor-name resolver, contracts/audit-log-api.md

class TrainingSessionRead(BaseModel):
    ...                                       # unchanged fields
    coaches: list[SessionCoachOut] = Field(default_factory=list)
    has_active_coach: bool = True
```

| Field | Semantics |
|---|---|
| `coaches` | Every row of `training_session_coaches` for this session, ordered by `added_at` ascending (creator first for every backfilled and newly created session). Always non-empty after the migration (backfill B1, data-model.md §6.3). |
| `has_active_coach` | `False` when **no** coach of the session has `users.is_active = true`. Derived per read (`any(c.coach.is_active …)`), never stored — data-model.md §7.2. Drives the listing signal of §8. |

`added_by_user_id` and `added_at` are **not** exposed: they exist for provenance and are
already answerable from `audit_log`; putting them in a list payload would add two fields
per coach per session to every listing for no reader.

**`TrainingSessionReadParent` is unchanged.** FR-025 puts the coaches' names in the
family *e-mail*; no family screen shows a coach name today
(`frontend/src/routes/parents/training/ParentSessionDetailPage.tsx` and
`frontend/src/components/parents/ParentSessionCard.tsx` render "el entrenador" as a role,
never a person), and US4 asks for nothing more. Adding the names to the parent payload
would be scope the spec did not ask for. A test asserts their absence (§12, B-14).

### 3.2 Request

`TrainingSessionCreate` (`backend/app/schemas/training_session.py:38-56`) and
`TrainingSessionUpdate` (`:75-89`) each gain one optional field:

```text
coach_user_ids: list[int] | None = Field(
    default=None,
    min_length=1,
    description="Entrenadores a cargo de la sesión. Si se omite al crear, "
                "queda el creador como único entrenador.",
)
```

Semantics — **full replacement set**, never a patch:

| Payload | Create | Update |
|---|---|---|
| field absent / `null` | coaches = `[current_user.id]` | coaches unchanged |
| `[a, b]` | coaches = `{a, b}` | coaches = `{a, b}` exactly (adds and removals computed by the service) |
| `[]` | 422 (`min_length=1`) | 422 (`min_length=1`) |
| `[a, a, b]` | deduplicated preserving first occurrence, no error | idem |

Replacement (rather than `add_coach` / `remove_coach` sub-resources) is what the wizard
produces: the field is a multi-select whose value is the whole set, and a set write is
idempotent under a double submit.

### 3.3 Validation matrix

Applied in `create_session` / `update_session` before the commit, inside the same
transaction as the write.

| # | Rule | Code | Body `detail` (español neutro) |
|---|---|---|---|
| V1 | `coach_user_ids` is present and empty | `422` | `"Una sesión debe tener al menos un entrenador."` |
| V2 | An id does not exist, or `users.role ∉ {coach, admin}` | `422` | `"Los siguientes usuarios no son entrenadores del club: [9, 14]"` |
| V3 | An id has no `club_members` row in the session's `club_id` | `422` | same message as V2 (the coach must not learn whether the id exists in another club) |
| V4 | An id is **newly added** and `users.is_active = false` | `422` | `"No puedes asignar a un entrenador inactivo: [9]"` |
| V5 | An id is **already assigned** and now inactive, and stays in the set | accepted | — (history is not rewritten, spec.md:169) |
| V6 | The resulting set would be empty after applying adds/removals | `409` | `"Una sesión debe tener al menos un entrenador."` |
| V7 | Caller is not admin and not a coach of the session's club | `403` | existing text `"No tienes permisos para editar esta sesión"` (`backend/app/routers/training_sessions.py:396-400`) |

V4 vs V5 is the load-bearing pair: a coach must be able to save an unrelated edit on a
session whose co-coach was deactivated yesterday, and must not be able to newly assign a
deactivated account. Implement as `new_ids - current_ids` for the `is_active` check.

V2 accepts `admin` as well as `coach` because the router already lets an administrator
create and edit sessions (`backend/app/routers/training_sessions.py:271`, `:392`) and the
migration backfills `coach_user_id = created_by_user_id` (data-model.md §6.3, B1), which
may be an administrator on pre-041 rows. The *picker* (§10.1) still lists `role=coach`
only, per FR-024. See §13, open point 1.

V6 is the `SELECT … FOR UPDATE` guard of data-model.md §3 and research R-18:

```text
SELECT coach_user_id FROM training_session_coaches
 WHERE session_id = :id
   FOR UPDATE                      -- same transaction as the write
→ apply removals / additions
→ if final count == 0: raise → 409
```

With replacement semantics a non-empty payload can never reach zero on its own; the lock
exists so two concurrent replacements serialise into one coherent set instead of
interleaving, and the count check is defence in depth. Both codes are reachable and both
are tested (§12, B-04 and B-05).

### 3.4 Endpoints touched

| Method + path | Router site | Change |
|---|---|---|
| `POST /api/training-sessions` | `backend/app/routers/training_sessions.py:262-312` | accepts `coach_user_ids`; response carries `coaches` |
| `PATCH /api/training-sessions/{id}` | `backend/app/routers/training_sessions.py:386-421` | accepts `coach_user_ids`; passes `actor=current_user` |
| `POST /api/training-sessions/{id}/execute` | `backend/app/routers/training_sessions.py:429-453` | passes `actor=current_user` |
| `DELETE /api/training-sessions/{id}` | `backend/app/routers/training_sessions.py:461-514` | `reason` → `reason_code`; passes `actor=current_user` (§7) |
| `GET /api/training-sessions` | `backend/app/routers/training_sessions.py:322-350` | new `coach_user_id` filter (§8) |
| `GET /api/training-sessions/{id}` | `backend/app/routers/training_sessions.py:359-384` | response carries `coaches` |
| `PUT /api/training-sessions/{id}/attendance` | `backend/app/routers/training_sessions.py:572-626` | passes `actor=current_user`; archives instead of deleting (§6) |
| `PATCH /api/training-sessions/{id}/attendance/{athlete_id}` | `backend/app/routers/training_sessions.py:636-667` | passes `actor=current_user` |
| `GET /api/training-sessions/{id}/attendance` | `backend/app/routers/training_sessions.py:517-570` | filters `archived_at IS NULL`; new admin-only `include_archived` (§6.4) |
| `GET /api/calendar/events` | `backend/app/routers/calendar.py:210-277` | new `coach_user_id` filter (§8.2) |
| `DELETE /api/calendar/events/{id}` | `backend/app/routers/calendar.py:399-439` | `reason` query parameter → `reason_code` body; passes `ctx` (§7.2) |
| `DELETE /api/calendar/events/{id}/permanent` | `backend/app/routers/calendar.py:447-467` | passes `ctx`; hard delete becomes soft delete (§7.3) |

---

## 4. Service signatures — the acting user is threaded, never re-derived

`_load_session_coach` (`backend/app/services/training/sessions.py:853-864`) selects
`User` by `session.created_by_user_id` and is passed as the notification `coach` at
`:715`, `:787` and `:839`. That single function is the US4 bug: a cancellation by coach B
tells families coach A cancelled it. It is **deleted**, not patched.

| Function | Today | 041 |
|---|---|---|
| `create_session` | `(db, payload, coach, club_id, notification_service, dispatcher)` — `backend/app/services/training/sessions.py:105-112` | signature unchanged; `coach` becomes `added_by_user_id` and the default sole session coach; `payload.coach_user_ids` overrides the membership |
| `update_session` | `(db, session_id, payload, *, notification_service, dispatcher)` — `:661-668` | `+ actor: User` (keyword-only, required) |
| `execute_session` | `(db, session_id)` — `:730` | `(db, session_id, *, actor: User)` |
| `cancel_session` | `(db, session_id, *, send_notification, reason: str \| None, …)` — `:751-758` | `reason: str \| None` → `reason_code: CancelReasonCode`; `+ actor: User` |
| `update_convocatoria` | `(db, session_id, athlete_ids, *, send_notification, …)` — `:802-809` | `+ actor: User` |
| `bulk_upsert_convocatoria` | `(db, session_id, athlete_ids)` — `backend/app/services/training/attendance.py:15-19` | `+ actor: User` |
| `update_attendance` | `(db, session_id, athlete_id, payload)` — `backend/app/services/training/attendance.py:68-72` | `+ actor: User` |
| `_load_session_coach` | `:853-864` | **removed** |
| — | — | **new** `_load_session_coaches(db, session) -> list[User]` — one query over the bridge, ordered by `added_at` |
| `list_sessions` | `:868-878` | `+ coach_user_id: int \| None = None` |

`actor` is keyword-only and has **no default**: a default would let a future call site
silently record the wrong person, which is the failure this whole feature exists to
remove. Every router call site already has `current_user` in scope; the precedent for
threading it down is `session_media.uploaded_by_user_id` at
`backend/app/routers/training_sessions.py:913` (research R-19).

Commit boundaries (audit rows go in **before** these calls, FR-001):
`create_session` commits at `backend/app/services/training/sessions.py:157`,
`update_session` at `:689`, `execute_session` at `:745`, `cancel_session` at `:777`,
`bulk_upsert_convocatoria` at `backend/app/services/training/attendance.py:58`,
`update_attendance` at `backend/app/services/training/attendance.py:97`.

---

## 5. Family notifications — the acting coach is named, the session coaches are listed

### 5.1 Context keys

`coach_name` is **removed** from all three templates and from their
`required_context_keys` and replaced by three keys. Reusing `coach_name` with a new
meaning would repeat the `content_version` mistake documented in data-model.md §4.6.

| Key | Type | Value |
|---|---|---|
| `acting_coach_name` | `str` | display name of the coach who performed *this* action (creator on invite, editor on update, canceller on cancel, inviter on convocatoria growth) |
| `coach_names` | `list[str]` | display names of the session coaches, `added_at` order — used only for pluralisation (`\|length`) |
| `coaches_text` | `str` | `coach_names` joined in Spanish: `"Ana Coach"` / `"Ana Coach y Bruno Coach"` / `"Ana, Bruno y Carla"`, built by a private `_join_names_es(names)` helper in `backend/app/services/training/sessions.py` |

Registry edits — `backend/app/services/notification/template_registry.py:140-151`
(invite), `:162-175` (updated), `:185-197` (cancelled): drop `"coach_name"`, add
`"acting_coach_name"`, `"coach_names"`, `"coaches_text"`. Extra context keys are allowed
(`_assert_required_keys` only checks for missing ones,
`backend/app/services/notification/template_registry.py:671-682`), missing ones raise
`ValueError` — so the registry and the services must land in the same commit.

The three dispatch helpers build the context: `_dispatch_invitation`
(`backend/app/services/training/sessions.py:259-317`, `coach_name` at `:302`),
`_dispatch_update` (`:392-453`, `coach_name` at `:437`), `_dispatch_cancel`
(`:528-587`, `coach_name` at `:571`). The `coach_name` local computed at `:205`, `:336`
and `:472` becomes `acting_coach_name` from the threaded `actor`, and `coach_names` /
`coaches_text` come from `_load_session_coaches`.

### 5.2 Exact copy (español neutro, with diacritics)

**`backend/templates/email/training_session_invite.html:16-19`** — replaces the current
`El entrenador <strong>{{ coach_name }}</strong> …`:

```jinja
<p>
  El entrenador <strong>{{ acting_coach_name }}</strong> del <strong>{{ club_name }}</strong>
  ha planificado una sesión de entrenamiento para <strong>{{ athlete_name }}</strong>.
</p>
```

New row inside the `highlight-box` table of the same file (after "Foco técnico"):

```jinja
<tr>
  <td style="font-size: 13px; color: #898989; padding: 5px 0; width: 160px;">
    <strong style="color: #2f2f2f;">{% if coach_names|length > 1 %}Entrenadores a cargo:{% else %}Entrenador a cargo:{% endif %}</strong>
  </td>
  <td style="font-size: 13px; color: #333333; padding: 5px 0;">{{ coaches_text }}</td>
</tr>
```

**`backend/templates/email/training_session_updated.html:17-20`**:

```jinja
<p>
  El entrenador <strong>{{ acting_coach_name }}</strong> del <strong>{{ club_name }}</strong>
  ha modificado la sesión a la que <strong>{{ athlete_name }}</strong> está convocado/a.
</p>
{% if coach_names|length > 1 %}
<p>La sesión está a cargo de <strong>{{ coaches_text }}</strong>.</p>
{% endif %}
```

**`backend/templates/email/training_session_cancelled.html:16-20`**:

```jinja
<p>
  El entrenador <strong>{{ acting_coach_name }}</strong> del <strong>{{ club_name }}</strong>
  ha <strong>cancelado</strong> la sesión a la que <strong>{{ athlete_name }}</strong>
  estaba convocado/a.
</p>
{% if coach_names|length > 1 %}
<p>La sesión estaba a cargo de <strong>{{ coaches_text }}</strong>.</p>
{% endif %}
```

**Signature block**, identical in all three
(`training_session_invite.html:81`, `training_session_updated.html:109`,
`training_session_cancelled.html:74`):

```jinja
<p>
  Saludos,<br>
  <strong>{{ coaches_text }} — {{ club_name }}</strong>
</p>
```

The body names **who acted**; the signature names **who leads**. That split is FR-025
read literally and is what makes the US4 independent test pass.

### 5.3 Plain-text twins

`backend/templates/email/training_session_invite.txt:5,24`,
`training_session_updated.txt:5,30` and `training_session_cancelled.txt:5,23` carry the
same `{{ coach_name }}` wording. Nothing renders them today — the registry only declares
`body_path` (`.html`) and `NotificationService` renders that single path
(`backend/app/services/notification/service.py:115`). They must still be updated in the
same commit with the wording above, or deleted; leaving three stale files that say the
wrong coach cancelled the session is not an option a reviewer should have to catch twice.

---

## 6. Attendance — attribution and archiving

### 6.1 Response

`AttendanceRead` (`backend/app/schemas/training_session.py:258-275`) gains two fields:

```json
{
  "id": 8891,
  "session_id": 512,
  "athlete_id": 31,
  "athlete_name": "…",
  "status": "presente",
  "rpe_omni": 6,
  "rubric_effort": 4,
  "recorded_by_display_name": "Ana Coach",
  "last_edited_by_display_name": "Bruno Coach",
  "updated_at": "2026-09-15T18:04:11"
}
```

```text
recorded_by_display_name: str | None = None      # <- recorded_by_user_id
last_edited_by_display_name: str | None = None   # <- updated_by_user_id
```

Both are `None` for rows written before this feature (data-model.md §6.3: the actor
columns are deliberately **not** backfilled — `NULL` means "we have no record"). The UI
renders nothing rather than guessing (§10.4).

`AttendanceReadParent` (`backend/app/schemas/training_session.py:278-300`) is
**unchanged**. `_attendance_to_read_parent`
(`backend/app/routers/training_sessions.py:70-78`) builds a dict from `AttendanceRead`
and revalidates it into the parent model, so the two new keys are dropped by Pydantic —
a test asserts it explicitly rather than relying on that (§12, B-14).

Name resolution uses the shared actor-name resolver introduced by
`contracts/audit-log-api.md` (FR-013); do not add a second `f"{first} {last}"` helper.
Loading is `selectinload(SessionAttendance.recorded_by)` +
`selectinload(SessionAttendance.updated_by)` wherever attendance is read for
coach/admin, so a 20-row roster stays at a constant query count.

### 6.2 Write rules

| Operation | `recorded_by_user_id` | `updated_by_user_id` | `updated_at` |
|---|---|---|---|
| Placeholder row created by the convocatoria (`status = AUSENTE`, no rating) — `backend/app/services/training/sessions.py:146-152`, `backend/app/services/training/attendance.py:50-56` | `NULL` | `NULL` | model default |
| First `update_attendance` that sets any of `status ≠ AUSENTE`, `rpe_omni`, `rubric_*`, `individual_feedback` | `actor.id` **if currently `NULL`** | `actor.id` | `onupdate` |
| Any later `update_attendance` | untouched | `actor.id` | `onupdate` |

"Registrado por" is therefore the coach who first put data on the row, not whoever
created the empty placeholder — which is what US4 AS4 asks for ("a coach records
attendance, ratings or feedback … it records that coach as the recorder"). Implemented in
`update_attendance` (`backend/app/services/training/attendance.py:94-97`), which today is
a bare `setattr` loop with no author fields at all.

### 6.3 Roster shrink archives instead of deleting (FR-016)

`bulk_upsert_convocatoria` currently issues an unconditional
`delete(SessionAttendance)` for the removed athletes
(`backend/app/services/training/attendance.py:40-45`). Replace with:

```text
carries_data(row) := any of (rpe_omni, rubric_effort, rubric_attitude,
                             rubric_technique, individual_feedback) IS NOT NULL

to_remove = existing_ids - new_ids
    carries_data      -> UPDATE archived_at = now()          audit: archive
    untouched         -> DELETE  (hard, placeholder only)    audit: delete

to_add = new_ids - existing_ids                              audit: create
re_added = new_ids ∩ {rows where archived_at IS NOT NULL}
                    -> UPDATE archived_at = NULL             audit: restore
```

`re_added` is not optional. `existing` is built from an unfiltered
`select(SessionAttendance)` (`backend/app/services/training/attendance.py:27-32`), so an
archived row is already "existing" and never re-inserted; without the explicit
un-archive, re-adding an athlete would leave them invisible forever. Re-inserting instead
would violate `uq_session_attendance` (`backend/app/models/training_session.py:174`) —
the soft-delete/unique-constraint trap of research R-12, here for real.

`archived_at` is set/cleared; `recorded_by_user_id`, the ratings and
`individual_feedback` are never touched, which is what makes US4 AS5 ("an administrator
can still read the archived entry") true.

### 6.4 Every read of `session_attendance` must filter `archived_at IS NULL`

No global loader criterion (research R-10's reasoning applies verbatim: admins must still
read archived rows). Explicit filter at each site, mirroring the soft-deleted-media
comprehension at `backend/app/routers/training_sessions.py:105`.

| Site | What it feeds | Filter |
|---|---|---|
| `backend/app/services/training/attendance.py:60-64` | return value of `bulk_upsert_convocatoria` | `WHERE archived_at IS NULL` |
| `backend/app/services/training/attendance.py:78-86` | `update_attendance` row lookup | `WHERE archived_at IS NULL` → archived row ⇒ `404` |
| `backend/app/services/training/attendance.py:114-119` | `athlete_attendance_history` | `WHERE archived_at IS NULL` |
| `backend/app/routers/training_sessions.py:104` | `attendance_summary` (coach) | comprehension |
| `backend/app/routers/training_sessions.py:118` | `kid_attendances` (parent) | comprehension |
| `backend/app/routers/training_sessions.py:536,546,552` | `GET …/attendance` (admin/coach and parent branches) | comprehension, unless `include_archived` (below) |
| `backend/app/routers/training_sessions.py:810-816` | `_validate_athlete_ids_for_session` (media tagging) | `AND archived_at IS NULL` |
| `backend/app/routers/calendar.py:547-556` | training-session attendances surfaced as event attendances | `AND archived_at IS NULL` |
| `backend/app/routers/activities.py:328-334` | "attended sessions" for activity matching | `AND archived_at IS NULL` |
| `backend/app/routers/athletes.py:190-201` | `sort=recent_attendance` counter | `AND archived_at IS NULL` |
| `backend/app/services/training/sessions.py:714` | convocados for the update e-mail | comprehension |
| `backend/app/services/training/sessions.py:774` | convocados snapshot for the cancel e-mail | comprehension |
| `backend/app/services/training/sessions.py:820` | `previous_ids` for the convocatoria diff | comprehension |
| `backend/app/services/training/newsletter_builder.py:364,437,503,1011,1059` | family bitácora metrics | `AND archived_at IS NULL` |
| `backend/app/services/training/reports.py:290-293` | monthly report roster metrics | `AND archived_at IS NULL` |
| `backend/app/services/race/ai/athlete_context.py:198-207` | AI athlete context | `AND archived_at IS NULL` |

Sites that must **not** filter: the admin `include_archived` branch below, and any
`audit_log` read.

**`GET /api/training-sessions/{id}/attendance?include_archived=true`** — admin only.
Coach or parent sending it → `403 {"detail": "Solo un administrador puede ver los
registros archivados."}`. Archived rows come back with `archived_at` populated (added to
`AttendanceRead` as `archived_at: datetime | None = None`, `None` for every active row),
so an administrator can serve US4's "still readable" requirement without a second
endpoint.

---

## 7. Cancellation gains a reason code — sessions and calendar events

The training-session half (§7.1) and the calendar-event half (§7.2, §7.3) share one
catalogue group (`CancelReasonCode`), one Spanish refusal sentence and one label-resolution
rule, so they are specified together. §7.2 and §7.3 are what this contract owns for
**FR-017** (spec.md:208); their schema is [data-model.md](../data-model.md) §4.4.

### 7.1 Training sessions

data-model.md §2.4 makes `reason_code` **mandatory** for `action=cancel` on
`entity_type=training_session` (422 when absent). The current endpoint takes free text:

```text
DELETE /api/training-sessions/{id}?notify=true&reason=<free text, max 300>
        backend/app/routers/training_sessions.py:465-466
```

becomes

```text
DELETE /api/training-sessions/{id}?notify=true&reason_code=cancel_weather
```

`reason_code` is required and typed `CancelReasonCode` — the `cancel_*` sub-enum of
`AuditReasonCode` fixed in `contracts/athlete-archive.md` §3.1 (data-model.md §2.4:
`cancel_weather`, `cancel_venue_unavailable`, `cancel_insufficient_athletes`,
`cancel_coach_unavailable`, `cancel_rescheduled`, `cancel_organizer_cancelled`). Typing it
with the full catalogue would let `athlete_left_club` cancel a session. Missing or
out-of-group → `422 {"detail": "Selecciona un motivo de cancelación."}`.

The `reason` key the cancelled template requires
(`backend/app/services/notification/template_registry.py:190`) is filled with
`AUDIT_REASON_LABELS[reason_code]` — the Spanish label, resolved at dispatch time and
never persisted (same pattern as `REVISION_REASON_LABELS`,
`backend/app/schemas/race_imports.py:57-67`). Free text stops reaching families and stops
being a place a coach could type a minor's name (FR-003).

Frontend: `cancelTrainingSession` (`frontend/src/api/trainingSessions.ts:64-78`) swaps
`reason` for `reason_code`, and the cancel flow shows a required `<select>` of the six
labels before confirming.

### 7.2 Calendar events — `DELETE /api/calendar/events/{event_id}` (FR-017)

The same rule, on the other surface. `REASON_REQUIRED` already contains
`("calendar_event", AuditAction.cancel)` and already names `EventCancelIn` as the primary
guard (`contracts/audit-recording.md` §1.5); this section is that schema.

Today the motive is a free-text query parameter that is never persisted:

```text
DELETE /api/calendar/events/{event_id}?reason=<free text>
        backend/app/routers/calendar.py:402   reason: str = Query(default="")
```

It becomes a request **body** — not a query parameter as in §7.1 — because the athlete
archive endpoint of `contracts/athlete-archive.md` §2 already established the body idiom
for a `DELETE` that carries a reason, and `EventCancelIn` is named as a body schema:

```python
# backend/app/schemas/calendar.py
class EventCancelIn(BaseModel):
    """Motivo obligatorio para cancelar un evento del calendario."""

    reason_code: CancelReasonCode
```

```text
DELETE /api/calendar/events/{event_id}
Content-Type: application/json

{ "reason_code": "cancel_venue_unavailable" }
```

`CancelReasonCode` is **not new**: it is the shared `cancel` sub-enum already fixed by
`contracts/athlete-archive.md` §3.1, holding exactly the `cancel_*` group of `AuditReasonCode`
(data-model.md §2.4) — `cancel_weather`, `cancel_venue_unavailable`,
`cancel_insufficient_athletes`, `cancel_coach_unavailable`, `cancel_rescheduled`,
`cancel_organizer_cancelled`. `SessionCancelIn` (§7.1) types its `reason_code` on the same
enum, which is why the two surfaces cannot drift. There is no seventh value and no free-text
escape hatch (FR-003).

| Case | Response |
|---|---|
| valid `reason_code` | `204`, no body (unchanged) |
| no body, empty body, `null`, or a value outside the `cancel_*` group | `422 {"detail": "Selecciona un motivo de cancelación."}` |
| event already cancelled | `409` (unchanged, `backend/app/routers/calendar.py:435-439`) |
| `event_type == BIRTHDAY` | `400` (unchanged, `:410-414`) — birthdays are virtual and are refused before the body is read |
| caller fails `can_edit_calendar_event` | `403` (unchanged, `:416-420`) |

The 422 sentence is the one §7.1 already fixes for the session endpoint, so the two cancel
dialogs surface identical copy. Its **body shape** is decided (plan ruling 2026-09-09, closing §13.2): a flat
`{"detail": "Selecciona un motivo de cancelación."}` raised as `HTTPException(422)` from the
router for **both** endpoints — matching the repo's existing 422 style and keeping
`EventCancelIn` and `SessionCancelIn` in agreement; FastAPI's list-shaped validation body is
not used for this case. `record_audit`'s
`AuditReasonRequired` (`contracts/audit-recording.md` §1.5) sits behind the schema either way,
as defence in depth for a service called from a script.

**What the cancellation persists** (data-model.md §4.4 — all four columns, in the same
unit of work as the audit row):

```sql
UPDATE calendar_events
   SET status                   = 'cancelled',
       cancelled_by_user_id     = :actor,
       cancelled_at             = :now,
       cancellation_reason_code = :reason_code
 WHERE id = :event_id
```

`cancel_event` (`backend/app/services/calendar/events.py:463-470`) accepts `user` today and
never reads it (`contracts/audit-recording.md` §3.4). Its signature becomes:

```python
async def cancel_event(
    db: AsyncSession,
    event: CalendarEvent,
    reason_code: CancelReasonCode,
    ctx: "AuditContext",
    notification_service: "NotificationService | None" = None,
    dispatcher: "TaskDispatcher | None" = None,
) -> CalendarEvent
```

`reason: str` disappears and `user: "User"` is replaced by `ctx`, whose `actor` fills
`cancelled_by_user_id` and the audit row — the actor is threaded, never re-derived (§4).
The router passes `ctx` at `backend/app/routers/calendar.py:427-434`.

**Families still read a Spanish label, never a code.** `notify_event_cancelled`
(`backend/app/services/calendar/notifications.py:268-274`) keeps its `reason: str`
parameter; the caller fills it with `AUDIT_REASON_LABELS[reason_code]`, resolved at dispatch
time and never persisted. The template context key `reason`
(`backend/app/services/calendar/notifications.py:314`) and the
`required_context_keys` of `CALENDAR_EVENT_CANCELLED`
(`backend/app/services/notification/template_registry.py:243-252`) are therefore
**unchanged**. The `"Sin motivo especificado"` fallback at `:314` becomes unreachable —
`reason_code` is mandatory — and is removed.

**Propagation.** When the event is a `TRAINING_SESSION` the service already flips the linked
`TrainingSession` to `CANCELLED` (`backend/app/services/calendar/events.py:477-487`). That
write gets its own `training_session`·`cancel` audit row carrying the same `reason_code`
under the same `request_id`, so the reviewer sees one operation (FR-002, US1 AS5).

**Frontend.** `cancelCalendarEvent(id, reason?)`
(`frontend/src/api/calendar.ts:82-91`) becomes `cancelCalendarEvent(id, reasonCode)` and
sends the body with `apiClient.delete(url, { data: { reason_code } })` — the shape
`contracts/athlete-archive.md` §11 already uses (`frontend/src/api/athletes.ts:40-42`).
`useCancelCalendarEvent` (`frontend/src/api/calendar.ts:197-207`) takes
`{ id, reasonCode }`.

`ConfirmDialog` (`frontend/src/components/shared/ConfirmDialog.tsx:23-33`) accepts only
`description: ReactNode` and has no slot for a control that gates the confirm button — the
same limitation `contracts/athlete-archive.md` §10 hit — so the cancel flow at
`frontend/src/components/calendar/EventDrawer.tsx:488-498` moves to a dedicated
`CancelEventDialog` built on the same `AlertDialog` primitives, keeping `tone="danger"`'s
focus-on-Cancel behaviour and its inline, non-closing error:

```text
CancelEventDialog { open, eventTitle, isPending, errorMessage, onCancel, onConfirm(reasonCode) }
├── AlertDialogTitle        "Cancelar evento"
├── AlertDialogDescription  the existing sentence, unchanged
├── Select (Radix, components/ui/select.tsx)   label "Motivo de la cancelación"
├── inline error            when confirmed with no reason
└── AlertDialogFooter       "No, volver" (focused) · "Cancelar evento"
```

Copy (español neutro, full diacritics):

| Element | Text |
|---|---|
| Trigger button | "Cancelar evento" (unchanged, `EventDrawer.tsx:472`) |
| Dialog title | "Cancelar evento" |
| Dialog body | "El evento pasará al estado 'cancelado'. Los participantes serán notificados." (unchanged, `EventDrawer.tsx:491`) |
| Select label | "Motivo de la cancelación" |
| Select placeholder | "Selecciona un motivo" |
| Options | "Clima adverso" · "Sede no disponible" · "Convocatoria insuficiente" · "Entrenador no disponible" · "Reprogramado" · "Cancelado por el organizador" |
| Validation error | "Selecciona un motivo de cancelación." |
| Confirm | "Cancelar evento" |
| Cancel | "No, volver" |
| Error (409) | "Este evento ya está cancelado." |

The confirm button is disabled until a reason is chosen, every control keeps the 48 px
minimum touch target, and the dialog traps focus and closes on Escape (constitution III).

### 7.3 Permanent deletion — `DELETE /api/calendar/events/{event_id}/permanent` (FR-017)

`delete_event_permanent(db, event)`
(`backend/app/services/calendar/events.py:541-544`) takes no actor at all, so today there
is nothing to attribute the deletion to. It becomes:

```python
async def delete_event_permanent(
    db: AsyncSession,
    event: CalendarEvent,
    ctx: "AuditContext",
) -> None
```

and the router passes it (`backend/app/routers/calendar.py:467`), matching
`contracts/audit-recording.md` §3.4.

Per data-model.md §4.4 the hard `await db.delete(event)`
(`backend/app/services/calendar/events.py:561`) becomes a soft delete — `deleted_at = now`,
`deleted_by_user_id = ctx.actor.id` — so the audit row's `entity_id` still resolves to a
readable row. The linked `TrainingSession` removed at `:552-559` is soft-deleted the same
way and gets its own `training_session`·`delete` row under the same `request_id`
(`contracts/audit-recording.md` §4.5).

Because the row survives, **every calendar read path must filter `deleted_at IS NULL`**:
`get_event` (`backend/app/services/calendar/events.py:46`), `list_events_in_range`
(`:254`) and the router's `_get_event_or_404` (`backend/app/routers/calendar.py:163`),
which is what makes the event vanish from the coach calendar, the parent calendar and the
event drawer exactly as a hard delete used to. `event_audiences` and `event_attendances`
are no longer removed by `ON DELETE CASCADE`; they simply stop being reachable through the
filtered reads.

**No reason code here.** `("calendar_event", AuditAction.delete)` is *not* in
`REASON_REQUIRED` (`contracts/audit-recording.md` §1.5), so the existing `ConfirmDialog`
at `frontend/src/components/calendar/EventDrawer.tsx:500-510` is unchanged — title, body,
"Sí, eliminar" and "No, volver" all stay. The only change is on the backend: the actor is
now recorded.

### 7.4 One catalogue, one source of truth

The six labels reach both dialogs through `GET /api/audit/reason-codes?group=cancel`, the
shared catalogue endpoint of `contracts/audit-log-api.md` §14 (`AuditReasonGroup` member
`cancel`, `AUDIT_REASON_GROUPS["cancel"] is CancelReasonCode`). Neither the session cancel flow
of §7.1 nor the event cancel dialog of §7.2 declares its own array of codes or labels; both
consume it through `useAuditReasonCodes("cancel")` (`contracts/audit-log-api.md` §14.5), which
also fixes the two UI rules they share — the `Select` stays disabled with the picker's own
loading state until the catalogue resolves (never a bare spinner, constitution III), and the
confirm button stays disabled until a code is chosen. The backend persists only the code, never
the label, exactly like `REVISION_REASON_LABELS`
(`backend/app/schemas/race_imports.py:57-67`).

---

## 8. Coach filter on listings (FR-026)

### 8.1 `GET /api/training-sessions?coach_user_id={id}`

New query param on `backend/app/routers/training_sessions.py:323-331`, forwarded through
`_list_for_clubs` (`:226-260`) into `list_sessions`
(`backend/app/services/training/sessions.py:868-921`):

```sql
JOIN training_session_coaches c
  ON c.session_id = training_sessions.id
 AND c.coach_user_id = :coach_user_id
```

served by `ix_tsc_coach_user_id` (data-model.md §3). Filters compose with the existing
`status` / `from` / `to` / `athlete_id`.

Parents sending `coach_user_id` → `403 {"detail": "No tienes permisos para filtrar por
entrenador."}`. Which coach leads a session is internal management information (FR-032
keeps the per-coach view away from families); silently ignoring the parameter would hide
that decision from the reader of the code.

### 8.2 `GET /api/calendar/events?coach_user_id={id}`

`coach_user_id: int | None` added to `EventListQuery`
(`backend/app/schemas/calendar.py:383-399`), the router
(`backend/app/routers/calendar.py:211-220`, forwarded at `:265-272`) and
`list_events_in_range` (`backend/app/services/calendar/events.py:254-347`):

```sql
WHERE (
      calendar_events.created_by_user_id = :coach
   OR EXISTS (SELECT 1
                FROM training_sessions ts
                JOIN training_session_coaches c ON c.session_id = ts.id
               WHERE ts.calendar_event_id = calendar_events.id
                 AND c.coach_user_id = :coach)
)
```

FR-026 says "session coaches for sessions; creator for other events" — a calendar event
of type `training_session` mirrors a session, so it must answer through the bridge, not
through the creator. The `EXISTS` is cheap: `training_sessions.calendar_event_id` is
unique (`backend/app/models/training_session.py:111-118`).

**Virtual birthdays are excluded when the filter is set.** They are synthesised in memory
by `list_birthday_events_in_range`
(`backend/app/services/calendar/events.py:330-346`) and have no creator; returning them
under a coach filter would make the calendar count disagree with the per-coach view
(SC-008). Parents: same `403` as §8.1.

---

## 9. Audit rows owned by this contract

Recorded through `record_audit` (`contracts/audit-recording.md`), called from the
services — never from the routers (plan.md, Structure Decision) — inside the transaction
that performs the write, so every row of one request shares its `request_id` (FR-002,
AS5).

| Trigger | `entity_type` | `entity_id` | `action` | `reason_code` | `changed_fields` / `diff_json` |
|---|---|---|---|---|---|
| `create_session` | `training_session` | session id | `create` | — | allow-listed keys of data-model.md §2.5 |
| coach added on create/update | `training_session_coach` | session id | `create` | — | `{"coach_user_id": {"before": null, "after": 9}}` |
| coach removed on update | `training_session_coach` | session id | `delete` | — | `{"coach_user_id": {"before": 9, "after": null}}` |
| `update_session` | `training_session` | session id | `update` | — | changed field names; values only for `status`, `session_kind`, `scheduled_date`, `duration_min`, `calendar_event_id` |
| `execute_session` | `training_session` | session id | `execute` | — | `{"status": {"before": "planned", "after": "executed"}}` |
| `cancel_session` | `training_session` | session id | `cancel` | **required** (§7) | `{"status": …}` |
| roster add | `session_attendance` | attendance row id | `create` | — | `{"status": …}` |
| roster shrink, row carries data | `session_attendance` | attendance row id | `archive` | — | `{"archived_at": …}` |
| roster shrink, empty placeholder | `session_attendance` | attendance row id | `delete` | — | — |
| roster re-add of an archived row | `session_attendance` | attendance row id | `restore` | — | `{"archived_at": {"before": "…", "after": null}}` |
| `update_attendance` | `session_attendance` | attendance row id | `update` | — | field **names** only for `rpe_omni`, `rubric_*`, `individual_feedback`; value only for `status` |
| `cancel_event` (§7.2) | `calendar_event` | event id | `cancel` | **required** (`cancel_*`) | names `["status","cancelled_at","cancelled_by_user_id","cancellation_reason_code"]`; `diff_json` limited to `status` and `cancellation_reason_code` — the only two allow-listed for this entity (data-model.md §2.5) |
| `cancel_event`, linked training session (`events.py:477-487`) | `training_session` | session id | `cancel` | same code, same `request_id` | `{"status": {"before": "planned", "after": "cancelled"}}` |
| `delete_event_permanent` (§7.3) | `calendar_event` | event id | `delete` | — | names `["deleted_at","deleted_by_user_id"]` only; **no `diff_json`** — neither field is allow-listed |
| `delete_event_permanent`, linked training session (`events.py:552-559`) | `training_session` | session id | `delete` | — | names only, same `request_id` |

`athlete_id` is set on every `session_attendance` row (FR-007 per-athlete history);
`club_id` is the session's club on all of them. The four `calendar_event` rows carry
`club_id = calendar_events.club_id` and `athlete_id = NULL` — the audience is a set, not one
athlete (`contracts/audit-recording.md` §4.5). `event_title` is never recorded: it is
free text a coach could type a name into (FR-003).

Hard privacy line: `individual_feedback` and `excuse_reason` appear **only** as names in
`changed_fields`, never in `diff_json` — data-model.md §2.5's never-list. The audit
privacy scan (data-model.md §2.5) covers the rows produced here.

Volume sanity check: a 20-athlete roster save produces up to 20 `session_attendance` rows
plus one `training_session` row, all under one `request_id` — the ~3 000 rows/year term
of data-model.md §9.

---

## 10. Frontend

### 10.1 `SessionCoachesField` — multi-select with chips

New `frontend/src/components/training/SessionCoachesField.tsx`, rendered in
`StepGeneral` (`frontend/src/components/training/session-wizard/StepGeneral.tsx`, after
the "Foco técnico" block at `:128-147`).

- Visual idiom copied from `AthletesMultiSelect`
  (`frontend/src/components/training/AthletesMultiSelect.tsx:1-70`): a `<fieldset>` with
  an `sr-only` `<legend>`, a selected-first list of toggle rows, and removable chips.
  Radix `Select` is not used for a ≤3-item multi-select (research R-29 reserves `Select`
  for single-value pickers).
- Data: `useClubCoaches()` → `GET /api/users?role=coach` in create mode,
  `GET /api/users?role=coach&club_id={session.club_id}` in edit mode. The endpoint exists
  and already scopes a coach to their own clubs
  (`backend/app/routers/users.py:140-210`). New `frontend/src/api/users.ts` — the **same**
  module `contracts/staff-admin.md` introduces; do not create a second one.
- Prefill: create mode → `[currentUser.id]` from `useAuthStore`; edit mode →
  `session.coaches.map(c => c.user_id)`.
- Removing the last chip is blocked in the UI (the remove button of the sole remaining
  chip is `disabled` with `aria-describedby` pointing at the hint) *and* by Zod (below)
  *and* by the server (V1/V6). Three layers, because the wizard is the only place a coach
  ever sees the rule.

Copy (español neutro):

| Element | Text |
|---|---|
| Label | `Entrenadores a cargo` |
| Hint | `Por defecto quedas tú. Puedes agregar a otro entrenador del club.` |
| Chip remove `aria-label` | `Quitar a {nombre}` |
| Disabled remove tooltip / hint | `Una sesión debe tener al menos un entrenador.` |
| Zod error | `Selecciona al menos un entrenador` |
| Empty coach list | `No hay otros entrenadores activos en el club.` |
| Loading | 2 skeleton rows (`h-12 animate-pulse rounded-lg bg-light-gray`, the `AthletesMultiSelect` idiom) |
| Error | shared `ErrorState` with retry |

### 10.2 Schema and wizard wiring

- `frontend/src/schemas/trainingSession.schema.ts:8-59` gains
  `coach_user_ids: z.array(z.number()).min(1, "Selecciona al menos un entrenador")`.
- `STEP_GENERAL_FIELDS` (`frontend/src/schemas/trainingSession.schema.ts:63-72`) gains
  `"coach_user_ids"` so "Siguiente" stays blocked while the set is empty.
- `ERROR_TARGET_ID` (`frontend/src/components/training/session-wizard/SessionWizard.tsx:57-69`)
  gains `coach_user_ids: "session-coaches-field"` so the error summary can focus it.
- `buildCreatePayload` / the update payload builder
  (`frontend/src/components/training/session-wizard/SessionWizard.tsx:90+`) send
  `coach_user_ids`.
- Types (`frontend/src/types/trainingSession.types.ts:9-32`, `:106+`):
  `SessionCoach { user_id: number; display_name: string }`,
  `TrainingSession.coaches: SessionCoach[]`, `TrainingSession.has_active_coach: boolean`,
  `TrainingSessionCreate.coach_user_ids?: number[]`,
  `TrainingSessionUpdate.coach_user_ids?: number[]`,
  `Attendance.recorded_by_display_name?: string | null`,
  `Attendance.last_edited_by_display_name?: string | null`.

### 10.3 Listings

- `SessionFiltersBar` (`frontend/src/components/training/SessionFiltersBar.tsx:7-60`)
  gains a `<select id="filter-coach">` labelled `Entrenador`, first option `Todos`,
  populated from `useClubCoaches()`, wired to a new `coach_user_id: number | null` in
  `useTrainingFiltersStore` (`frontend/src/store/trainingFiltersStore.ts:19-27`). The
  store is `persist`ed under `training-filters`; a new optional key rehydrates as
  `undefined`, so no version bump is needed.
- `fetchTrainingSessions` (`frontend/src/api/trainingSessions.ts:27-37`) forwards
  `coach_user_id`; the filter object is already part of the query key
  (`:87`), so caching is correct without further change.
- Calendar: `CalendarFilters` (`frontend/src/types/calendar.types.ts:208-214`) gains
  `coach_user_id?: number | null`, forwarded by `fetchCalendarEvents`
  (`frontend/src/api/calendar.ts:29-59`).

### 10.4 Signals and attribution surfaces

| Surface | Rendering |
|---|---|
| `SessionsTable` (`frontend/src/components/training/SessionsTable.tsx:43-70`, both the mobile card and the desktop row) | when `has_active_coach === false`: an amber icon+text marker built exactly like `TodayMarker` (`:33-40`) — `<AlertTriangle size={12} aria-hidden="true" />` + `Entrenador inactivo`. Icon **and** text, never colour alone (constitution III). |
| `SessionDetailPage` "Detalles" block (`frontend/src/routes/training/SessionDetailPage.tsx:393`) | new row `Entrenadores` listing one `ActorChip` per `session.coaches` entry |
| `AttendanceTable` row (`frontend/src/components/training/AttendanceTable.tsx:104`) | a `text-xs text-mid-gray` line under the athlete name: `Registrado por {A} · Editado por {B}`. Only `Registrado por {A}` when the two are the same person or `last_edited_by_display_name` is `null`; the whole line is omitted when both are `null` (pre-041 rows). Coach/admin surface only — the parent card renders nothing new. |
| Inactive-coach hint on the detail page | `Esta sesión no tiene entrenadores activos. Asigna un entrenador para poder gestionarla.` in a shared `Alert` (amber), shown when `has_active_coach === false` |

Accessibility: chips and their remove buttons are ≥ 48 px touch targets with visible
focus rings; the field is a `fieldset`/`legend` group with `aria-describedby` on the
hint and the error; jest-axe zero violations on the wizard step and on `SessionsTable`
with a flagged row.

Stable test ids: `session-coaches-field`, `session-coach-chip-{userId}`,
`session-coach-remove-{userId}`, `session-coaches-error`, `filter-coach`,
`session-inactive-coach-flag`, `attendance-attribution-{athleteId}`,
`session-detail-coaches`.

---

## 11. Non-functional

- **Query count.** `list_sessions` eager-loads
  `selectinload(TrainingSession.session_coaches).selectinload(TrainingSessionCoach.coach)`
  alongside the existing `attendances` / `media` options
  (`backend/app/services/training/sessions.py:913-916`); `get_session` does the same
  (`:930-935`). A 50-session page must stay at a constant number of queries — asserted
  (§12, B-13). Same rule for `selectinload(SessionAttendance.recorded_by / .updated_by)`
  on the attendance endpoints.
- **Budgets.** All endpoints here are existing ones; writes stay within p95 ≤ 1500 ms
  (one extra INSERT per audit row in the same transaction), reads within p95 ≤ 500 ms.
  The new frontend component is a few KB inside the already-lazy session-wizard chunk;
  no new route, no new dependency.
- **Privacy.** No response, log line or audit row introduced here carries an athlete
  name, birth date, measurement, `individual_feedback` or `excuse_reason`. The e-mail
  templates keep the athlete's first+last name they already carry (they are addressed to
  that athlete's own guardian). The existing hashed-id logging idiom
  (`backend/app/services/training/sessions.py:55-74`) is untouched and must be used for
  any new log line.

---

## 12. Required tests

Fixture: the two-coaches-same-club fixture of research R-32 (coach A and coach B in club
1, a third coach in club 2, one parent), SQLite-in-memory +
`app.dependency_overrides`.

### Backend (`backend/tests/`)

| # | Test | Asserts |
|---|---|---|
| B-01 | coach A creates a session without `coach_user_ids` | `coaches == [A]`, one `training_session_coaches` row, `added_by_user_id == A` |
| B-02 | coach A creates with `coach_user_ids=[A, B]` (**the two-coaches happy path**) | `coaches` has both, `added_at` order preserved, two bridge rows, two `training_session_coach` audit rows sharing one `request_id` |
| B-03 | coach B replaces the set with `[B]` | A's row deleted, B's kept, `delete` audit row present |
| B-04 | `coach_user_ids: []` on create and on update | `422`, body `"Una sesión debe tener al menos un entrenador."` |
| B-05 | service-level removal that would empty the set | `409`, same message (the V6 guard) |
| B-06 | `coach_user_ids` contains a coach of club 2 | `422`, message lists the id, nothing written |
| B-07 | newly adding a deactivated coach | `422` (V4); **and** an update that keeps an already-assigned, now-deactivated coach | `200` (V5) |
| B-08 | **regression, must fail on today's code**: coach A creates + notifies, coach B cancels with `notify=true` | the cancelled e-mail context has `acting_coach_name == "B…"` and `coaches_text` contains both names; today `_load_session_coach` (`backend/app/services/training/sessions.py:853`) yields A |
| B-09 | same shape for `update_session` and for the convocatoria-growth invite | `acting_coach_name` is the editor / inviter |
| B-10 | **archive**: roster save removing an athlete whose row has `rubric_effort` set | row survives with `archived_at` set, ratings and `individual_feedback` intact, `archive` audit row; a second athlete with an untouched `AUSENTE` placeholder is hard-deleted |
| B-11 | re-adding the archived athlete | `archived_at IS NULL` again, no `IntegrityError` on `uq_session_attendance`, `restore` audit row |
| B-12 | attribution: A records, B edits | `recorded_by_display_name == A`, `last_edited_by_display_name == B`, `recorded_by_user_id` unchanged by B's edit |
| B-13 | `GET /api/training-sessions?coach_user_id=B` and `GET /api/calendar/events?coach_user_id=B` | only B's sessions / events; birthdays absent; query count constant across a 20-session page |
| B-14 | **privacy**: parent reads a session and its attendance | payload has no `coaches`, no `recorded_by_display_name`, no `last_edited_by_display_name`; parent sending `coach_user_id` → `403`; parent/coach sending `include_archived=true` → `403`, admin → `200` with the archived row |
| B-15 | `has_active_coach` | `false` after the session's only coach is deactivated; `true` again once a second, active coach is assigned |
| B-16 | `DELETE …?reason_code=` missing / out of group | `422` `"Selecciona un motivo de cancelación."`; valid code → cancelled e-mail `reason` equals the Spanish label, and the audit row carries `reason_code` |
| B-17 | template registry | the three specs no longer require `coach_name` and do require `acting_coach_name`, `coach_names`, `coaches_text`; rendering each `.html` with the new context raises nothing |
| B-18 | audit privacy on this domain | no produced `audit_log` row contains `individual_feedback`, `excuse_reason` or any athlete name (extends the scan of data-model.md §2.5) |
| B-19 | **FR-017**: `DELETE /api/calendar/events/{id}` with no body, an empty body, `null`, and a value outside the `cancel_*` group (a `restore_*` code and a free-text string) | `422` `"Selecciona un motivo de cancelación."` in all four cases; the event stays `scheduled`; no `audit_log` row and no e-mail dispatched |
| B-20 | **FR-017**: valid `reason_code` from coach B on an event created by coach A | `204`; `status='cancelled'`, `cancelled_by_user_id == B`, `cancelled_at` set, `cancellation_reason_code` persisted; one `calendar_event`·`cancel` audit row with actor B and that code; the cancelled e-mail's `reason` context key equals the **Spanish label**, never the code; on a `TRAINING_SESSION` event a `training_session`·`cancel` row shares the same `request_id` |
| B-21 | **FR-017**: `DELETE /api/calendar/events/{id}/permanent` | `204`; the row still exists with `deleted_at` and `deleted_by_user_id == actor`; one `calendar_event`·`delete` audit row naming the actor; the event is absent from `GET /api/calendar/events` and `GET /api/calendar/events/{id}` → `404`; the linked session is soft-deleted with its own row under the same `request_id` |

Files: extend `backend/tests/test_training_session_service.py`,
`backend/tests/test_training_session_notifications.py` (B-08/B-09 next to the existing
`test_cancel_session_with_flag_dispatches_cancelled_template`, `:542`),
`backend/tests/test_attendance_validation.py`,
`backend/tests/test_training_session_router.py`,
`backend/tests/test_training_session_privacy.py`; new
`backend/tests/test_session_coaches.py` for B-01…B-07 and B-15. B-19…B-21 extend
`backend/tests/test_calendar_router.py` (the 422/403/404 shapes) and
`backend/tests/test_calendar_events_service.py` (the persisted columns and the audit rows),
with the label assertion of B-20 next to the existing cancellation cases in
`backend/tests/test_calendar_notifications.py`.
Migration/backfill B1 coverage is data-model.md §6.5, not repeated here.

### Frontend (`frontend/src/`)

| # | Test | Asserts |
|---|---|---|
| F-01 | `SessionCoachesField.test.tsx` | prefilled with the current user; adding a second coach renders two chips; the sole remaining chip's remove button is disabled with the hint text |
| F-02 | `SessionWizard` submit | payload carries `coach_user_ids`; clearing the field blocks "Siguiente" and surfaces `Selecciona al menos un entrenador` in the error summary, focusing `session-coaches-field` |
| F-03 | `SessionsTable.test.tsx` | `has_active_coach: false` renders `session-inactive-coach-flag` with the text `Entrenador inactivo`; `true` renders nothing |
| F-04 | `AttendanceTable.test.tsx` | renders `Registrado por Ana Coach · Editado por Bruno Coach`; renders only "Registrado por" when the editor is `null`; renders nothing when both are `null` |
| F-05 | `SessionFiltersBar` | selecting a coach updates the store and the query key; "Todos" clears it |
| F-06 | jest-axe | zero violations on the wizard General step with the new field and on `SessionsTable` with a flagged row |
| F-07 | `CancelEventDialog.test.tsx` (new) + `EventDrawer.test.tsx` | the six labels render from the catalogue response, not from a local array; confirm is disabled until a reason is chosen and shows `Selecciona un motivo de cancelación.` when forced; confirming calls the mutation with `{ id, reasonCode }`; a `409` renders "Este evento ya está cancelado." inline without closing; jest-axe zero violations on the open dialog |

MSW handlers for `GET /api/users?role=coach` go in a new
`frontend/src/test/msw/staffHandlers.ts` with synthetic coach names, in the style of
`frontend/src/test/msw/growthSummaryHandlers.ts` (research R-33). F-07 adds a handler for
`GET /api/audit/reason-codes?group=cancel` alongside it.

### e2e (`frontend/e2e/`)

One spec: coach A creates a co-coached session, coach B cancels it, MailHog shows the
cancellation naming B. Blocked until the second seed coach exists
(`frontend/e2e/helpers/session.ts:17-23` has a single `coach` identity; `SeedRole` gains
`coach2`, with the account added to `backend/scripts/seed.py`) **and** until the
pre-existing migration bug that stops the isolated stack booting on a fresh volume is
fixed (research R-34). Track it there, not here.

---

## 13. Open points for the owner

The FR-010 attribution narrowing that used to sit here is **decided**, not open: see §1 and
the FR-010 row of plan.md's Complexity Tracking table.

1. **May an administrator be a session coach?** V2 accepts `role ∈ {coach, admin}` so that
   an admin-created session and the B1 backfill of admin-created historic sessions stay
   representable, while the picker offers `role=coach` only. If the owner wants sessions
   led strictly by coaches, V2 tightens to `role == coach` and the admin-creator path must
   then send `coach_user_ids` explicitly (422 otherwise).
2. **The 422 body shape for a missing `reason_code` is stated two ways across the contracts.**
   §7.1 and §7.2 quote a flat `{"detail": "Selecciona un motivo de cancelación."}`, while
   `contracts/audit-recording.md` §1.5 says the 422 "comes from FastAPI validation with the
   standard body shape" and `contracts/athlete-archive.md` §3.1 makes the closed sub-enum "the
   only place that `422` can come from" — which yields the list-shaped body. Both are
   defensible; the two cancel endpoints disagreeing is not. The flat shape costs one explicit
   body check plus `HTTPException(422, detail=…)` per endpoint and lets the dialogs render
   `extractErrorDetail` unchanged; the list shape costs one mapping helper in the frontend error
   path. Pick one and apply it to `AthleteArchiveIn`, `AthleteRestoreIn`, `SessionCancelIn`,
   `EventCancelIn`, `UserDeactivateIn` and `UserDeleteIn` together.
3. **"El entrenador {nombre}" is gendered.** The wording is inherited from the current
   templates and is fixed by the spec's own example (spec.md:85) and FR-025, so it is kept
   verbatim. A club with a female coach will read "El entrenador Ana Coach". A neutral
   rewrite ("{nombre}, del club {club}, ha cancelado…") is a one-line copy change in three
   templates and is worth deciding before the second coach is onboarded.
