# Contract — Athlete archive (soft delete), restore, and user deletion

**Scope**: FR-014, FR-015, FR-018 (US2). Turns `DELETE /api/athletes/{id}` from a
destructive eight-statement cascade into an archiving UPDATE, adds an admin-only restore
and an admin-only archived listing, enumerates **every** read site that must exclude
archived athletes, and closes the two defects on the user-deletion path.

**Out of scope, contracted elsewhere**: the audit row shapes and the `record_audit`
signature (`contracts/audit-recording.md`), the history read endpoints
(`contracts/audit-log-api.md`), the staff screen and staff creation
(`contracts/staff-admin.md`), the session-roster archive of `session_attendance`
(`contracts/session-coaches.md` — only its *read* filter is listed here).

## 0. Naming — `deleted_at`, not `archived_at`

`data-model.md` §4.2 is authoritative: the columns are `athletes.deleted_at`,
`athletes.deleted_by_user_id`, `athletes.deleted_reason_code`, following the existing
soft-delete precedent `race_results.deleted_at` (`backend/app/models/race_result.py:141`)
and its index (`backend/app/models/race_result.py:105`). `research.md` R-09 spells the
same three columns `archived_*` and names an `AthleteArchiveReason` enum; that spelling is
**superseded** — the reason values live in the shared `AuditReasonCode` catalogue
(`data-model.md` §2.4, `athlete_*` and `restore_*` groups). "Archivar" stays the Spanish
UI verb; it is a copy decision, not a column name.

---

## 1. `DELETE /api/athletes/{athlete_id}` — archive

**Router**: `backend/app/routers/athletes.py:329-367` (route unchanged, body replaced).
**Auth**: `require_role([admin, coach])` (unchanged); a coach must own the athlete's club
(`backend/app/routers/athletes.py:350-355`, unchanged).
**Service**: new `app/services/athlete_scope.py::archive_athlete(db, athlete, actor, reason_code)`.

### Request

```http
DELETE /api/athletes/42 HTTP/1.1
Content-Type: application/json

{ "reason_code": "athlete_left_club" }
```

`app/schemas/athlete.py::AthleteArchiveIn`:

```python
class AthleteArchiveIn(BaseModel):
    reason_code: AthleteArchiveReasonCode  # closed sub-enum of AuditReasonCode, see §3.1
```

`reason_code` is **required**. A `DELETE` with no body, an empty body, or a value outside
the catalogue is `422` — this is the FR-003 guarantee that no coach can type a minor's
name into a free-text reason.

> **Client gotcha**: axios drops the payload on `apiClient.delete(url, body)`; it must be
> `apiClient.delete(url, { data: body })`. FastAPI accepts a Pydantic body on `DELETE`,
> and the API is called directly at Render (no proxy strips the body).

### Response `204 No Content`

Writes exactly one UPDATE, on `athletes` only:

```sql
UPDATE athletes
   SET deleted_at = :now,
       deleted_by_user_id = :actor_id,
       deleted_reason_code = :reason_code,
       updated_by_user_id = :actor_id,
       updated_at = :now
 WHERE id = :athlete_id;
```

**No child row is touched.** The eight `delete()` statements at
`backend/app/routers/athletes.py:359-366` are removed — including
`delete(ParentalConsent)` at `:359`, which today destroys the Ley-1581 evidence the club
is required to keep, and `delete(User)` at `:366`, which destroys the athlete stub every
`ClubMember` and `race_insight_dispatcher` lookup joins through
(`backend/app/services/notification/race_insight_dispatcher.py:464-470`).

### Errors

| Code | When | Body |
|---|---|---|
| `401` | no/invalid token | standard |
| `403` | coach whose clubs do not include `athlete.club_id` | `{"detail": "No tienes acceso a este atleta"}` (existing text, `athletes.py:354`) |
| `404` | athlete does not exist, **or** is already archived and the caller is a coach | `{"detail": "Atleta no encontrado"}` |
| `409` | already archived and the caller is an admin | `{"detail": "El atleta ya está archivado"}` |
| `422` | `reason_code` missing or outside the catalogue | Pydantic validation error |

The 404/409 split is deliberate: an admin works from the archived list and deserves the
precise state; a coach must not be able to probe for the existence of an athlete they can
no longer see.

### Audit

One row, `entity_type=athlete`, `action=archive`, `reason_code` = the submitted value,
`athlete_id` = the archived athlete, `club_id` = `athlete.club_id`,
`changed_fields=["deleted_at","deleted_by_user_id","deleted_reason_code"]`,
`diff_json` limited to `deleted_reason_code` (the only allow-listed field of the three —
`data-model.md` §2.5). Written in the same transaction as the UPDATE.

---

## 2. `POST /api/athletes/{athlete_id}/restore` — admin only

**Router**: `backend/app/routers/athletes.py` (new, next to the `DELETE`).
**Auth**: `require_role([UserRole.admin])`. A coach gets `403` even for an athlete in
their own club (FR-015: restoration is an administrator action).
Verb-suffix action endpoint, consistent with `/commit`
(`backend/app/routers/race_imports.py:1004`), `/execute`
(`backend/app/routers/training_sessions.py:429`), `/approve` and `/send`
(`backend/app/routers/athlete_monthly_newsletters.py:1241,1278`).

### Request

```http
POST /api/athletes/42/restore HTTP/1.1
Content-Type: application/json

{ "reason_code": "restore_mistaken_archive" }
```

`reason_code ∈ {restore_mistaken_archive, restore_returned_to_club}` (required).

### Response `200 OK`

Returns the restored athlete in the standard `AthleteOut` shape, so the client can
navigate straight to the athlete page:

```json
{
  "id": 42,
  "user_id": 118,
  "club_id": 1,
  "deleted_at": null,
  "deleted_reason_code": null,
  "deleted_by": null,
  "…": "remaining AthleteOut fields unchanged"
}
```

Writes `deleted_at = NULL`, `deleted_by_user_id = NULL`, `deleted_reason_code = NULL`,
plus `updated_by_user_id` / `updated_at`.

### Errors

| Code | When | Body |
|---|---|---|
| `403` | caller is coach or parent | `{"detail": "Solo un administrador puede restaurar atletas"}` |
| `404` | athlete does not exist | `{"detail": "Atleta no encontrado"}` |
| `409` | athlete is not archived | `{"detail": "El atleta no está archivado"}` |
| `422` | `reason_code` missing or outside the `restore_*` group | Pydantic validation error |

### Audit

One row, `action=restore`, `entity_type=athlete`, `reason_code` required. Archive and
restore may alternate any number of times; each is its own row, so the athlete's timeline
stays continuous (spec.md:175).

---

## 3. Reason catalogue

Values come from `AuditReasonCode` (`data-model.md` §2.4). Five request-level Python
sub-enums keep each endpoint's request closed to its own group, and one shared
`AUDIT_REASON_LABELS` dict holds the Spanish label. **The backend never persists the
label** — same discipline as `REVISION_REASON_LABELS`
(`backend/app/schemas/race_imports.py:57-67`).

### 3.1 The five sub-enums

Each is a `StrEnum` whose members are a strict subset of `AuditReasonCode`, and each member is
written as `AuditReasonCode.<member>.value` rather than re-typed as a literal, so a code is
spelled in exactly one place. They are declared in the **same module as `AuditReasonCode`
itself** — `backend/app/models/audit_log.py` per `plan.md:87`; `data-model.md` §2 opens by
placing the Python-only catalogues in `backend/app/services/audit.py`, and wherever
`AuditReasonCode` finally lands its sub-enums land with it — never in the per-domain schema
modules, because both the request schemas and the catalogue endpoint of
`contracts/audit-log-api.md` §14 import them.

| Sub-enum | `group` key | Members (`data-model.md` §2.4) | Typed on |
|---|---|---|---|
| `AthleteArchiveReasonCode` | `athlete_archive` | the six `athlete_*` codes | `AthleteArchiveIn.reason_code` (§1) |
| `AthleteRestoreReasonCode` | `athlete_restore` | `restore_mistaken_archive`, `restore_returned_to_club` | `AthleteRestoreIn.reason_code` — the `POST /athletes/{id}/restore` body of §2 |
| `CancelReasonCode` | `cancel` | the six `cancel_*` codes | `SessionCancelIn.reason_code` for `DELETE /api/training-sessions/{id}` (`contracts/session-coaches.md` §7.1) and `EventCancelIn.reason_code` for `DELETE /api/calendar/events/{event_id}` (§7.2 there) |
| `AccountStateReasonCode` | `account` | the four `account_*` codes | `UserUpdate.reason_code` (§9 here; `contracts/staff-admin.md` §4.1) |
| `ParentRemovalReasonCode` | `parent_removal` | `parent_family_request`, `parent_duplicate_account` | `UserDeleteIn.reason_code` (§8.4) |

`AuditReasonGroup` — a `StrEnum` of exactly those five `group` keys — and
`AUDIT_REASON_GROUPS: dict[AuditReasonGroup, type[StrEnum]]` live in the same module; they are
what `GET /api/audit/reason-codes` iterates and what the group test of
`contracts/audit-log-api.md` §13 T19 walks.

`retention_24m` (`data-model.md` §2.4, Retention group) deliberately has **no** sub-enum and
**no** group key: it is written by the purge CLI (`contracts/retention-purge.md`) and is never
offered in a picker.

Typing a request with the full `AuditReasonCode` instead would let `cancel_weather` reach an
athlete archive and `athlete_left_club` reach an account deactivation. Nothing downstream would
notice — both are valid catalogue members and both are persisted verbatim — so the closed
sub-enum is the only place that `422` can come from.

### 3.2 What the endpoints of this contract accept

| Endpoint | Allowed `reason_code` | Label shown in the picker (es-CO) |
|---|---|---|
| `DELETE /athletes/{id}` | `athlete_left_club` | "Se retiró del club" |
| | `athlete_transferred` | "Traslado a otro club" |
| | `athlete_season_inactive` | "Inactivo esta temporada" |
| | `athlete_family_request` | "Solicitud de la familia" |
| | `athlete_duplicate_record` | "Registro duplicado" |
| | `athlete_data_correction` | "Corrección de datos" |
| `POST /athletes/{id}/restore` | `restore_mistaken_archive` | "Archivado por error" |
| | `restore_returned_to_club` | "Regresó al club" |

Labels reach the frontend through `GET /api/audit/reason-codes?group=athlete_archive`
(specified in `contracts/audit-log-api.md` §14) so the catalogue has one source of truth; the
frontend must not hardcode a second copy of the list.

---

## 4. `GET /api/athletes?include_archived=true` — admin only

**Router**: `backend/app/routers/athletes.py:160-227`.

```http
GET /api/athletes?include_archived=true&club_id=1
```

| Parameter | Type | Default | Rules |
|---|---|---|---|
| `include_archived` | `bool` | `false` | `true` is admin-only. Coach → `403`. |
| `club_id`, `sort` | unchanged | | |

`include_archived=true` returns active **and** archived athletes in one page; the client
filters on `deleted_at !== null` for the "Archivados" view. One query for a roster of
tens of athletes is cheaper than a second endpoint and keeps the p95 ≤ 500 ms budget
(Principle IV); revisit only if the club's roster passes a few hundred rows.

`AthleteOut` gains three fields, populated **only** for admins (absent/`null` for coach
and parent responses, so no new information reaches a family surface):

```json
{
  "deleted_at": "2026-09-09T14:22:03",
  "deleted_reason_code": "athlete_left_club",
  "deleted_by": { "user_id": 3, "display_name": "Ana Coach" }
}
```

`deleted_by` is the resolved display name (FR-013 — never a raw numeric id), joined from
`users`; it resolves for deactivated accounts too because FR-018 guarantees the row
survives.

| Code | When | Body |
|---|---|---|
| `403` | coach sends `include_archived=true` | `{"detail": "Solo un administrador puede ver atletas archivados"}` |

---

## 5. Exhaustive filter matrix — where `deleted_at IS NULL` must be applied

This is the highest-risk part of the feature: one missed filter leaks an archived minor
into a family-facing surface. Per `data-model.md` §8.1 and `research.md` R-10 there is
**no** global loader criterion — administrators must still see archived athletes, so any
global filter would need selective bypassing at exactly the sensitive sites.

### 5.1 Three choke points (fix these first)

| # | Choke point | Site | What it covers |
|---|---|---|---|
| C1 | `parent_athlete_ids` | `backend/app/services/permissions.py:63-68` | the whole parent surface — 7 internal `permissions.py` callers (`:42, :112, :161, :199, :254, :318, :360`) plus `activities.py:520`, `calendar.py:232,538`, `club_race_insights.py:281`, `monthly_reports.py:863`, `parent_newsletters.py:71`, `training_sessions.py:188,375,550,946`, `calendar/events.py:305`, `training/reports.py:248` |
| C2 | `list_athletes` | `backend/app/routers/athletes.py:186,204,214-215` | the coach athlete list **and**, through `useAthletes`, eight frontend pickers: `components/ai/AthleteCombobox.tsx:32`, `components/training/AthletesMultiSelect.tsx`, `components/calendar/AudienceSelector.tsx`, `components/parents/ParentAthleteAssignment.tsx`, `components/competitions/roster/RosterPanel.tsx`, `routes/athletes/AthletesListPage.tsx`, `routes/training/AthleteNewslettersDashboardPage.tsx`, `routes/training/SessionAssistantPage.tsx` |
| C3 | `verify_athlete_access` | `backend/app/dependencies.py:103` and `:129-136` | every per-athlete route: growth (`routers/growth.py:107`), anthropometry (`routers/anthropometry.py:121,262`), Strava (`routers/strava_integration.py:95,131,161`), athlete race analysis (`routers/athlete_race_analysis.py:326,365,422,518,691,957,1003,1033,1065`) |

C3's rule: **coach and parent get `404` for an archived athlete; admin gets the row.**
That single branch is what makes US2 AS2 ("an administrator views the archive, evidence
intact") and FR-014 ("disappears from every coach and parent surface") both true without
duplicating the dependency.

### 5.2 Remaining sites, one row per query

| Surface | Site | Note |
|---|---|---|
| Athlete PATCH | `backend/app/routers/athletes.py:292` | archived → `404`; an archived athlete is not editable |
| Athlete attendance history (coach branch) | `backend/app/routers/athletes.py:401` | |
| Parent "mis atletas" | `backend/app/routers/parent_athletes.py:177-181` | US2 AS5 |
| Parent-link create (both paths) | `backend/app/routers/parent_athletes.py:99`, `:249` | cannot link a family to an archived athlete |
| Parent-link detail | `backend/app/routers/parent_athletes.py:352` | |
| Admin/coach parent-link list | `backend/app/routers/parent_athletes.py:390-407` | |
| Parent consent panel + renewal modal | `backend/app/services/privacy.py:152-158` | **not in `data-model.md` §8.1** — without this, a family is asked to renew consent for an archived athlete |
| Parent invite acceptance | `backend/app/routers/auth.py:179-183` | an invite for an archived athlete must not be accepted |
| Dashboard: consent counts | `backend/app/services/dashboard_summary.py:84,87,96-101` | |
| Dashboard: stale AI insights | `backend/app/services/dashboard_summary.py:143-147` | |
| Dashboard: weekly load bands | `backend/app/services/dashboard_summary.py:194-202` | |
| Growth / measurement alerts | `backend/app/routers/alerts.py:42-69` | the "growth" surface of the coach dashboard |
| Newsletter athlete resolution (single) | `backend/app/routers/athlete_monthly_newsletters.py:191-193` | |
| Newsletter club batch generation | `backend/app/routers/athlete_monthly_newsletters.py:593-596` | comment already says "atletas activos"; today it is not true |
| Newsletter status summary grid | `backend/app/routers/athlete_monthly_newsletters.py:1545,1547-1555` | |
| Newsletter builder | `backend/app/services/training/newsletter_builder.py:172` | |
| Newsletter e-mail dispatcher | `backend/app/services/notification/newsletter_dispatcher.py:278-283` | last gate before a family e-mail leaves |
| Monthly report rosters and metrics | `backend/app/routers/monthly_reports.py:198,292,352,410,474,619` | six queries, same shape |
| Monthly report per-athlete section | `backend/app/services/training/reports.py:258` | |
| Monthly report competition block | `backend/app/services/training/reports.py:356-358`; `backend/app/services/training/competition_results.py:95-98` | |
| AI run athlete resolution | `backend/app/routers/race_analysis.py:670-674` | cannot launch a run for an archived athlete |
| AI club race insights | `backend/app/services/race/club_insights.py:99-107` | |
| AI season comparison groups (039) | `backend/app/services/race/group_launch.py:210-223`, `:508` | |
| AI graph node club lookup | `backend/app/services/race/ai/nodes/load_athlete_context.py:96` | |
| Session assistant selected athletes | `backend/app/services/training/session_assistant_context.py:224-228` | |
| Calendar audience expansion (4 audience types) | `backend/app/services/calendar/audiences.py:76-117` | also covers `calendar/notifications.py:92-105`, which resolves recipients through it |
| Calendar birthday events | `backend/app/services/calendar/birthdays.py:143-147`, `:180` | an archived athlete must stop generating birthday events |
| Session convocatoria validation | `backend/app/routers/training_sessions.py:601-607` | archived id → the existing "no pertenecen al club" `400` |
| Session media tagging | `backend/app/routers/training_sessions.py:829-832` | |
| Session attendance reads | `contracts/session-coaches.md` | `SessionAttendance.archived_at IS NULL` — a **separate** discriminator; do not conflate it with `Athlete.deleted_at` |
| Race roster add | `backend/app/services/race/roster.py:245-253` | archived → the existing `422` |
| Race competitor link | `backend/app/routers/race_competitors.py:116`; `backend/app/services/race/competitor_linking.py:184`, `:218-222` | archived athletes leave the matcher's candidate pool |
| Race import matching candidates | `backend/app/routers/race_imports.py:917-920` | |
| Strava activities list | `backend/app/routers/activities.py:216,231-244` | |
| Strava activity detail scope | `backend/app/services/permissions.py:386` | |
| Strava daily reconcile cron | `backend/app/services/strava/reconcile.py:267-272` | **not in `data-model.md` §8.1** — without this, the club keeps pulling a third-party activity feed for a minor who left. Filter by joining `athletes` on `deleted_at IS NULL` |
| Badge evaluation | `backend/app/services/training/badge_evaluator.py:253-258` | |

### 5.3 Sites that must **NOT** filter

Filtering these would *reduce* privacy or erase history. Each belongs in the reviewed
`ARCHIVE_SCOPE_EXEMPT` set with the reason recorded next to it.

| Site | Why it must keep archived athletes |
|---|---|
| `backend/app/routers/athlete_monthly_newsletters.py:241-244` | builds `forbidden_names` for the newsletter guardrail. An archived teammate can still be named in a coach note; dropping the name drops the redaction |
| `backend/app/services/training/reports.py:118-122` and `:882-887` | same, for the monthly report |
| `backend/app/services/training/session_assistant_context.py:146-150` | same, for the session assistant |
| `backend/app/services/race/ai/athlete_context.py:368-374` | same, for the race-analysis scrubbing pass ("NUNCA se pasa al LLM — solo alimenta scrubbing/guardrails") |
| Club history and per-athlete history endpoints | spec.md:176 — filtering by an archived athlete must still return entries |
| `GET /api/athletes?include_archived=true` (§4) and the admin archived view | US2 AS2 |
| Any query reconstructing a closed period (an already-generated report, a sent newsletter) | historical counts must not change retroactively |

### 5.4 Automated gate

A test walks `backend/app/` for `select(Athlete)`, `Athlete.id.in_(`, `join(Athlete` and
`Athlete.club_id` and fails on any `file:line` that neither applies
`Athlete.deleted_at.is_(None)` (directly or through `active_athletes_stmt()`) nor appears
in `ARCHIVE_SCOPE_EXEMPT`. This is a **different gate** from FR-009's audit-coverage
check (`contracts/audit-recording.md`): same spirit, different omission. Implementing one
and assuming it covers the other leaves a real hole.

The gate is the cheap lint; the *guarantee* is the enumeration test of §12.2.

---

## 6. What archiving preserves

Nothing below is deleted, nulled, or rewritten by the archive. This is the whole point of
FR-014, and it is also what fixes US2 AS4: three foreign keys to `athletes.id` are
`ondelete=RESTRICT` — `event_attendances.athlete_id`
(`backend/app/models/calendar_event.py:237`), `race_event_roster.athlete_id`
(`backend/app/models/race_event_roster.py:76`), `session_attendance.athlete_id`
(`backend/app/models/training_session.py:183`) — so today's cascade raises an opaque
`IntegrityError` half-way for any athlete who has actually trained or raced.

| Data | Table | Today (`athletes.py:359-366`) | After 041 |
|---|---|---|---|
| Parental consent evidence | `parental_consents` | **deleted** (`:359`) | kept, readable by admin |
| Anthropometric records | `anthropometric_records` | **deleted** (`:362`) | kept |
| AI explanations | `ai_explanations` | **deleted** (`:360`) | kept |
| Parent invites | `parent_invites` | **deleted** (`:361`) | kept |
| Parent↔athlete links | `parent_athlete` | **deleted** (`:363`) | kept — the link is what makes a restore return the athlete to the right family |
| Club membership of the athlete stub | `club_members` | **deleted** (`:364`) | kept |
| Athlete stub user | `users` (`role=athlete`) | **deleted** (`:366`) | kept — several joins resolve the club through it |
| Attendance, ratings, feedback | `session_attendance` | `RESTRICT` → the cascade fails | kept; roster-level archiving is `contracts/session-coaches.md` |
| Race results, roster entries, calendar audiences | `race_results`, `race_event_roster`, `event_attendances` | `RESTRICT` → the cascade fails | kept, references intact (spec.md:174) |
| Change history | `audit_log` | n/a | kept; `athlete_id` survives the soft delete by construction |

---

## 7. A parent whose only athlete is archived

US2 AS5 / spec.md:173. With C1 filtering inside `parent_athlete_ids`, every parent surface
returns an empty collection instead of a row or a `404`:

| Surface | Result |
|---|---|
| `GET /api/parent-athletes/my-athletes` | `200 []` |
| Parent dashboard | the existing calm empty state, unchanged copy: "No tienes atletas vinculados aún. Contacta a tu entrenador." (`frontend/src/routes/parents/ParentDashboardPage.tsx:184-190`) |
| Consent panel / renewal modal | `consents_per_athlete: []` → the blocking renewal modal never opens (`backend/app/services/privacy.py:152-158`) |
| Parent calendar, training, newsletters, activities, club insights | empty lists, `200`, no error |
| `GET /api/athletes/{archived_id}` as that parent | `403` from `verify_athlete_access` (unchanged text: "No tienes acceso a este atleta") |

No new copy is written for this case — reusing the existing empty state is the requirement,
not an improvement opportunity.

---

## 8. `DELETE /api/users/{user_id}` — refuse when the account has recorded activity

**Router**: `backend/app/routers/users.py:280-347`.

### Rules, in evaluation order

The activity check is **role-agnostic**. FR-018 words it for staff, but the same rule is
what makes the deletion path safe for a parent too, and it is the only reading compatible
with the `RESTRICT` foreign keys the data model puts on attribution (see below).

| # | Condition | Result | Site today |
|---|---|---|---|
| 1 | `user_id == current_user.id` | `403` "No puedes eliminarte a ti mismo" | `users.py:292-296`, unchanged |
| 2 | target not found | `404` "Usuario no encontrado" | `users.py:305-309`, unchanged |
| 3 | `target.role == athlete` | `400`, points at `DELETE /api/athletes/{id}` | `users.py:311-315`, unchanged |
| 4 | caller is a coach and the target is outside their clubs | `403`, unchanged | `users.py:323-330` (moved earlier so a coach cannot probe activity outside their clubs) |
| 5 | caller is a coach and `target.role ∈ {admin, coach}` | `403` "No tienes permisos para eliminar este usuario" | `users.py:317-321` today refuses this for *every* caller |
| 6 | **the account has recorded activity** (§8.1) | **`409`** with the deactivation guidance | new; today `403` for staff, and parents are deleted regardless |
| 7 | otherwise (an account that never acted) | `204`, cascade per §8.2 | `users.py:332-347` |

Rule 6 replaces the unconditional `403` for staff. In practice it refuses the same accounts
— a coach who has signed in once has an audit row — which is why `research.md` R-21 judged
the unconditional refusal good enough; the difference is that a staff account created by
mistake and never used stays deletable (FR-018 says "with recorded activity", not "always"),
and that parents now get the same protection. The probes below make the literal reading
affordable: three indexed existence checks, not a cross-table scan.

Consequence to state plainly: **US2 AS7's "a parent account is removed by an administrator"
now applies only to parents with no recorded activity** — a duplicate account, or a family
that never used the app. A parent who granted consent, RSVP'd to an event or read a
bitácora is deactivated instead. The alternative (delete anyway) would destroy the
Ley-1581 consent evidence at `users.py:333`, i.e. exactly the defect this feature removes
on the athlete path, and would be blocked at the DB layer anyway by
`audit_log.actor_user_id ondelete=RESTRICT` (`data-model.md` §Conventions).

### 8.1 The activity probes

```sql
-- 1. any recorded action by this account (post-041; audit_log is the club-wide
--    index of every write, so this covers all new attribution in one query)
SELECT 1 FROM audit_log WHERE actor_user_id = :user_id LIMIT 1;   -- ix_audit_actor_time

-- 2. any account this person created (pre-041 attribution, legacy short column)
SELECT 1 FROM users WHERE created_by = :user_id LIMIT 1;

-- 3. any parental consent granted by this person (pre-041 Ley-1581 evidence)
SELECT 1 FROM parental_consents WHERE parent_user_id = :user_id LIMIT 1;
                                        -- ix_parental_consents_parent_athlete, leftmost prefix
```

Probes 2 and 3 exist because `audit_log` starts empty at deploy: activity that predates
041 leaves no audit row, and the two things worth protecting from it are attribution
(`users.created_by`) and consent evidence (`parental_consents`). Anything else pre-041 is
caught by the database itself — the `created_by_user_id` foreign keys on
`training_sessions` (`backend/app/models/training_session.py:76-78`) and `race_results`
(`backend/app/models/race_result.py:151-153`) are `ondelete=RESTRICT`. The service maps
that `IntegrityError` to the same `409` body instead of letting it surface as a `500`.

### 8.2 What rule 7 deletes, and what it no longer touches

Because rule 6 already refuses every account with activity, two statements in today's
cascade become unreachable and are **removed**:

```python
# backend/app/routers/users.py:333 — unreachable after probe 3
await db.execute(delete(ParentalConsent).where(ParentalConsent.parent_user_id == user_id))

# backend/app/routers/users.py:343-345 — unreachable after probe 2.
# This is the literal violation of US2 AS7 ("no other record loses its
# 'created by' attribution as a side effect").
await db.execute(update(User).where(User.created_by == user_id).values(created_by=None))
```

Note that `users.created_by` is `ForeignKey("users.id")` with **no** `ondelete`
(`backend/app/models/user.py:43`), i.e. MySQL's default `RESTRICT`. The nulling statement
was never a policy choice — it existed only so the FK would not block the delete. Probe 2
now refuses the delete instead of erasing the attribution, which is what the requirement
actually asks for, and adding `ON DELETE SET NULL` in the migration would reintroduce the
same loss and is therefore explicitly **not** done.

The remaining statements stay: `delete(ParentAthlete)` (`:334`), `delete(ClubMember)`
(`:335`) and the two `ParentInvite` nullings (`:336-342`) — relationship rows, not
evidence.

### 8.3 `409` body

```json
{ "detail": "Este usuario tiene actividad registrada y no se puede eliminar. Desactívalo para impedir que inicie sesión; su nombre seguirá visible en el historial." }
```

### 8.4 Request body and audit

`DELETE /api/users/{id}` gains a required body, symmetrical with §1:

```http
DELETE /api/users/57 HTTP/1.1
Content-Type: application/json

{ "reason_code": "parent_duplicate_account" }
```

`reason_code ∈ {parent_family_request, parent_duplicate_account}` (`data-model.md` §2.4);
`delete` on `user` is on that section's mandatory-reason list, so a missing value is `422`.

One audit row: `action=delete`, `entity_type=user`, `entity_id` = the deleted account,
`club_id` = the club the account belonged to, `athlete_id` = `NULL`, `diff_json = NULL` —
no name and no e-mail address, both on the never-allow-list (`data-model.md` §2.5). The
row is written **before** the `users` row disappears, in the same transaction, and its
`actor_user_id` is the administrator, not the deleted account, so the `RESTRICT` FK on
`audit_log.actor_user_id` is unaffected.

---

## 9. `PATCH /api/users/{user_id}` with `is_active` — deactivate / activate

No new endpoint (`research.md` R-21). `backend/app/routers/users.py:223-274` keeps its
role guards; login already refuses inactive accounts with "Usuario desactivado"
(`backend/app/routers/auth.py:68-71`), which US3 AC6 says to reuse.

Two changes:

1. `UserUpdate` accepts an optional `reason_code` (from the `account_*` group:
   `account_staff_rotation`, `account_end_of_engagement`, `account_security`,
   `account_reactivation`). It is **required** when `is_active` is present, `422`
   otherwise, and is never persisted on `users` — only on the audit row.
2. The service emits `action=deactivate` when `is_active` flips `true → false` and
   `action=activate` on `false → true`, `entity_type=user`,
   `changed_fields=["is_active"]`, `diff_json={"is_active": {"before": true, "after": false}}`
   (`is_active` is allow-listed for `user`, `data-model.md` §2.5). A PATCH that changes
   other fields without touching `is_active` emits a plain `action=update`.

`update_user` currently applies `body.model_dump(exclude_none=True)` in a bare `setattr`
loop (`users.py:268-270`), so `is_active=False` **is** applied (it is not `None`) — the
before/after value must be captured before the loop runs.

Deactivating a coach never rewrites `training_session_coaches`; history is not rewritten
(`data-model.md` §7.2).

---

## 10. Frontend — archive dialog

**File**: `frontend/src/routes/athletes/AthleteFormPage.tsx` (existing; the delete flow at
`:34-45`, `:132-144` and `:157-175` is replaced).

### Trigger

The `Trash2` button labelled "Eliminar atleta" (`:141-142`) becomes an `Archive` (lucide)
button labelled **"Archivar atleta"**, same placement and same 48 px minimum touch target.

### Dialog

`ConfirmDialog` (`frontend/src/components/shared/ConfirmDialog.tsx`) accepts only
`description: ReactNode` and has no slot for a control that gates the confirm button, so
this flow uses a dedicated `ArchiveAthleteDialog` built on the same `AlertDialog`
primitives, keeping `ConfirmDialog`'s two behaviours: `tone="danger"` focuses Cancel on
open, and the error renders inline without closing.

```text
ArchiveAthleteDialog { open, athleteFullName, isPending, errorMessage, onCancel, onConfirm(reasonCode) }
├── AlertDialogTitle        "Archivar atleta"
├── AlertDialogDescription  <nombre> + explanatory paragraph
├── Select (Radix, components/ui/select.tsx)   label "Motivo del archivado"
├── inline error            when submitted with no reason
└── AlertDialogFooter       "Cancelar" (focused) · "Sí, archivar atleta"
```

The confirm button is disabled until a reason is chosen; the reason list comes from the
API catalogue of §3, never from a hardcoded array.

### Copy (español neutro, full diacritics)

| Element | Text |
|---|---|
| Button | "Archivar atleta" |
| Dialog title | "Archivar atleta" |
| Dialog body | "El deportista dejará de aparecer en listas, informes, boletines y en la vista de su familia. Se conservan sus mediciones, asistencias, consentimientos e historial. Un administrador puede restaurarlo." |
| Select label | "Motivo del archivado" |
| Select placeholder | "Selecciona un motivo" |
| Validation error | "Selecciona un motivo para archivar." |
| Confirm | "Sí, archivar atleta" |
| Cancel | "Cancelar" |
| Success toast | "Atleta archivado." |
| Error (generic) | "No se pudo archivar el atleta. Intenta de nuevo." |
| Error (409) | "Este atleta ya está archivado." |

On success: invalidate `["athletes"]`, `["athlete", id]` and `["dashboard-summary"]`, then
`navigate("/athletes")`. Error text is resolved with `extractErrorDetail`
(`frontend/src/lib/apiError.ts:33`) so the backend's Spanish `detail` wins over the axios
message — the current handler hardcodes a generic string (`AthleteFormPage.tsx:41-43`).

---

## 11. Frontend — admin "Atletas archivados" view

**File**: `frontend/src/routes/admin/ArchivedAthletesPage.tsx` (new, lazy).
**Route**: `/admin/atletas-archivados`, `<ProtectedRoute allowedRoles={[UserRole.admin]}>`,
mirroring `/admin/ai` (`frontend/src/App.tsx:427-436`). A dedicated admin route is required
because every `/athletes/*` route is coach-only today (`frontend/src/App.tsx:330,340,350,360`),
so an admin cannot reach the athlete surface at all.
**Nav**: a new `NavItem` in `navigation.ts` with `roles: ["admin"]`, under the existing
`club` group, alongside the staff entry from `contracts/staff-admin.md`.

### Content

Plain shadcn `Table` (`components/ui/table.tsx`), server-side filtered — no
`@tanstack/react-table` (`research.md` R-28).

| Column | Source |
|---|---|
| "Deportista" | `first_name` + `last_name` |
| "Club" | `club_id` resolved to the club name |
| "Motivo" | `deleted_reason_code` → its Spanish label |
| "Archivado por" | `deleted_by.display_name` (`ActorChip`) |
| "Fecha" | `deleted_at`, `dd MMM yyyy` |
| — | "Restaurar" button per row |

### Copy

| Element | Text |
|---|---|
| Page title | "Atletas archivados" |
| Subtitle | "Deportistas retirados del club. Su información se conserva y puede restaurarse." |
| Empty state | "No hay atletas archivados." |
| Row action | "Restaurar" |
| Restore dialog title | "Restaurar atleta" |
| Restore dialog body | "El deportista volverá a aparecer en listas, informes, boletines y en la vista de su familia." |
| Restore select label | "Motivo de la restauración" |
| Restore confirm | "Sí, restaurar atleta" |
| Restore success toast | "Atleta restaurado." |
| Restore error | "No se pudo restaurar el atleta. Intenta de nuevo." |

### States

| Surface | Loading | Empty | Error |
|---|---|---|---|
| Table | row skeletons | `EmptyState` "No hay atletas archivados." | `ErrorState` with retry |
| Cold start | existing `ServerWakingBanner` / `isColdStartError` path, unchanged | | |

### API and hooks

- `api/athletes.ts`: `archiveAthlete(id, reasonCode)` replaces `deleteAthlete`
  (`frontend/src/api/athletes.ts:40-42`) — `apiClient.delete(url, { data: { reason_code } })`;
  `restoreAthlete(id, reasonCode)`; `getAthletes` gains `include_archived?: boolean`.
- `hooks/athletes/useArchiveAthlete.ts` replaces `useDeleteAthlete.ts`;
  `hooks/athletes/useRestoreAthlete.ts` (new); `useAthletes` (`hooks/athletes/useAthletes.ts:6-9`)
  gains `include_archived` in `AthleteFilters`, which flows into the query key automatically.
- Query keys carrying archived rows are **not** added to `persistAllowList`
  (`frontend/src/lib/persistAllowList.ts`) beyond the existing `["athletes", …]` entry;
  the admin view relies on the same key with a different filter object.

### Accessibility

Radix `Select` for the reason (keyboard-operable, labelled), `min-h-12` on every control,
`AlertDialog` focus trap with Cancel focused first, jest-axe zero violations on
`AthleteFormPage` (dialog open and closed) and on `ArchivedAthletesPage` (empty, populated,
restore dialog open).

### Test ids (stable)

`archive-athlete-button`, `archive-athlete-dialog`, `archive-reason-select`,
`archive-confirm-button`, `archived-athletes-table`, `restore-athlete-button`,
`restore-athlete-dialog`, `restore-reason-select`.

---

## 12. Required tests

### 12.1 Backend — archive and restore (`backend/tests/routers/test_athlete_archive.py`, new)

There is **no** test today for `DELETE /api/athletes/{id}` or `DELETE /api/users/{id}` —
no test file issues either request — so every case below is new coverage, and cases 3, 4
and 14 are regression tests that must fail on today's code.

1. coach of the club archives with a valid reason → `204`; `deleted_at`, `deleted_by_user_id`, `deleted_reason_code` set.
2. admin archives → `204`.
3. **regression**: after the archive, `parental_consents`, `anthropometric_records`, `parent_athlete`, `ai_explanations`, `parent_invites`, the athlete stub `users` row and its `club_members` row all still exist (today all seven are destroyed).
4. **regression**: an athlete with `session_attendance`, `event_attendances` and `race_event_roster` rows archives cleanly (today the `RESTRICT` FKs raise `IntegrityError` half-way — US2 AS4).
5. archive without `reason_code` → `422`; with a `restore_*` or free-text value → `422`.
6. coach outside the athlete's club → `403`.
7. archive an already-archived athlete: coach → `404`, admin → `409`.
8. admin restores → `200`, the three columns back to `NULL`.
9. coach attempts restore → `403`.
10. restore a non-archived athlete → `409`.
11. restore without `reason_code` → `422`.
12. archive → restore → archive again: three audit rows, correct order, athlete usable throughout.
13. audit rows: `archive` and `restore` each carry actor, actor role, club, `athlete_id`, reason code and a `request_id`; `diff_json` contains only `deleted_reason_code`.
14. **privacy invariant**: no audit row produced by the archive/restore/user-delete flows contains the fixture's synthetic names, an ISO birth date, or any measurement-range numeric string.

### 12.2 Backend — the enumeration test (`backend/tests/test_archived_athlete_absent.py`, new)

The single test that carries FR-014. One archived athlete plus one active athlete in the
same club; assert the archived athlete's id is **absent** from every response below, and
the active one present:

`GET /api/athletes` · `GET /api/athletes?include_archived=true` as coach (`403`) ·
`GET /api/parent-athletes/my-athletes` · `GET /api/parent-athletes` ·
consent status · dashboard summary (all three counters) · `GET /api/alerts` ·
newsletter status summary · newsletter club batch generation · monthly-report roster and
metrics · AI run launch (`404`) · club race insights · season comparison groups ·
calendar audience expansion (all four audience types) · calendar birthdays ·
session convocatoria validation (`400`) · race roster add (`422`) ·
race competitor candidates · race import candidates · Strava activity list ·
Strava reconcile · badge evaluation · `GET /api/athletes/{id}` as coach (`404`) and as
the linked parent (`403`) · `GET /api/athletes/{id}/growth-summary` (`404`).

Plus the inverse: `GET /api/athletes?include_archived=true` as **admin** returns the
archived athlete with `deleted_at`, `deleted_reason_code` and a resolved `deleted_by`
display name; and the four guardrail loaders of §5.3 still return the archived athlete's
name.

### 12.3 Backend — parent with only an archived athlete (`backend/tests/test_parent_archived_only.py`, new)

1. `my-athletes` → `200 []`, never `404`.
2. consent status → `consents_per_athlete: []`, so the blocking renewal modal never opens.
3. parent calendar, training sessions, newsletters, activities and club insights → `200` with empty collections.
4. `GET /api/athletes/{archived_id}` as that parent → `403`.

### 12.4 Backend — user deletion and state (`backend/tests/test_users_delete_deactivate.py`, new)

1. delete a coach who has audit rows → `409` with the deactivation guidance text (probe 1).
2. delete a coach with no activity of any kind → `204`.
3. delete an account that created another account → `409` (probe 2), and **regression**: the created account keeps its `created_by` (today `users.py:343-345` nulls it — US2 AS7).
4. delete a parent who granted a parental consent → `409` (probe 3), and **regression**: the `parental_consents` row still exists (today `users.py:333` destroys it).
5. delete a coach whose `training_sessions.created_by_user_id` rows exist but who has no audit row → `409`, not `500` (the `RESTRICT` `IntegrityError` is mapped).
6. delete a parent with only `parent_athlete` and `club_members` rows and no activity → `204`; those rows are gone, the athlete is untouched.
7. self-delete → `403`; athlete target → `400`; unknown → `404`; coach caller outside the target's clubs → `403`; coach caller targeting a peer coach → `403`.
8. the successful deletion emits one audit row, `action=delete`, `entity_type=user`, a `parent_*` reason code, `diff_json` null, `actor_user_id` = the administrator; deleting without `reason_code` → `422`.
9. `PATCH {"is_active": false, "reason_code": "account_staff_rotation"}` → audit `action=deactivate` with `diff_json={"is_active": {"before": true, "after": false}}`; the account can no longer sign in ("Usuario desactivado").
10. `PATCH {"is_active": true, "reason_code": "account_reactivation"}` → `action=activate`.
11. `PATCH {"is_active": false}` without `reason_code` → `422`; a PATCH of other fields without `is_active` → plain `action=update`, no `activate`/`deactivate` row.
12. a deactivated coach's display name still resolves on their past audit rows and on `deleted_by` of an athlete they archived (FR-013).

### 12.5 Backend — the scope gate (`backend/tests/test_archive_scope_gate.py`, new)

Walks `backend/app/` per §5.4 and fails on any `Athlete` query that neither filters nor is
in `ARCHIVE_SCOPE_EXEMPT`. Asserts additionally that `ARCHIVE_SCOPE_EXEMPT` contains
exactly the §5.3 entries — so adding an exemption is a reviewed edit, not a silent one.

### 12.6 Frontend

`frontend/src/routes/athletes/__tests__/AthleteFormPage.archive.test.tsx` (new):

1. the button reads "Archivar atleta", not "Eliminar atleta".
2. confirm is disabled until a reason is chosen; submitting without one shows "Selecciona un motivo para archivar."
3. a successful archive sends `{ reason_code }` in the request body and navigates to `/athletes`.
4. a `409` renders "Este atleta ya está archivado." inline and keeps the dialog open.
5. `tone="danger"` behaviour preserved: Cancel holds focus on open, Enter does not archive.
6. jest-axe: zero violations, dialog open and closed.

`frontend/src/routes/admin/__tests__/ArchivedAthletesPage.test.tsx` (new):

1. an admin sees the table with reason label, actor name and date; a coach is redirected by `ProtectedRoute`.
2. empty state renders "No hay atletas archivados."
3. restore asks for a reason, calls `POST /athletes/{id}/restore`, and removes the row on success.
4. error state renders `ErrorState` with retry; the cold-start branch shows the calm copy.
5. jest-axe: zero violations, empty and populated.

`frontend/src/routes/parents/ParentDashboardPage.test.tsx` (existing, `:145-158`): extend
to assert the calm empty state when the parent's only athlete is archived — the copy must
be unchanged.

### 12.7 e2e (Playwright)

One spec: coach archives an athlete with a reason → the athlete disappears from the athlete
list, the session wizard picker and the newsletter dashboard; the linked parent sees the
calm empty state; an admin restores the athlete and the coach sees them again. Blocked on
the same pre-existing migration bug documented in
`specs/040-growth-module-redesign/checklists/integration-review.md` §4; carry it as a
deferred task rather than a silent skip (Principle II forbids silent skips).
