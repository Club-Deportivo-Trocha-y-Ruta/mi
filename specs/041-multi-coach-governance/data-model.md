# Data model — Multi-coach governance (041)

Only the deltas. Existing entities are referenced by their current names, verified in
the code at planning time (`path:line` citations throughout). Nothing here restates a
column that already exists; every subsection of §4 opens with an explicit
**"already present"** list so the migration author does not re-add one.

**Conventions used by this feature**

| Rule | Value | Why |
|---|---|---|
| Actor FK naming | `<verb>_by_user_id` (`updated_by_user_id`, `deleted_by_user_id`, …) | The dominant convention in the schema (`training_sessions.created_by_user_id`, `backend/app/models/training_session.py:76`; `calendar_events.created_by_user_id`, `backend/app/models/calendar_event.py:135`). The two legacy outliers `users.created_by` (`backend/app/models/user.py:43`), `athletes.created_by` (`backend/app/models/athlete.py:57`) and `anthropometric_records.evaluated_by` (`backend/app/models/anthropometry.py:68`) are **not renamed** — a rename would break every reader for no functional gain. New columns never repeat the short form. |
| Actor FK `ondelete` | `RESTRICT` on the audit actor, `SET NULL` on attribution columns | FR-018 makes staff accounts undeletable, so `RESTRICT` on `audit_log.actor_user_id` is enforceable and keeps the name resolvable forever; attribution columns use `SET NULL` so a parent account deletion (still allowed) never blocks. Mirrors `race_result_revisions.changed_by_user_id` RESTRICT (`backend/app/models/race_result_revision.py:70`) and `race_competitor_link_audit.previous_athlete_id` SET NULL (`backend/app/models/race_competitor_link_audit.py:99`). |
| Enum DDL | `Enum(PyEnum, name="…", values_callable=lambda e: [x.value for x in e])` | The project idiom (`backend/app/models/race_result_revision.py:66-72`, `backend/app/models/race_competitor_link_audit.py:89-96`) — stores the lowercase `.value`, not the member name. |
| Timestamps | naive UTC in a naive column, `default=lambda: datetime.now(timezone.utc)` | Every existing `DateTime` column does this (`backend/app/models/athlete.py:58-64`, `backend/app/models/club.py:31-33`). `audit_log.occurred_at` is the single exception in *precision* (see §1). |
| Catalogue codes | closed Python enums, persisted as their string value, labelled in Spanish in a `*_LABELS` dict | Exactly the shape of `RevisionReasonCode` + `REVISION_REASON_LABELS` (`backend/app/schemas/race_imports.py:38-67`), which exists precisely so a coach cannot type a minor's name into a "reason" field. |

---

## 1. New table `audit_log`

One row per recorded action (FR-001). Append-only (FR-004), privacy-minimised (FR-003),
retained 24 months (FR-030). This is the club-wide **index**; the three existing domain
trails (`race_result_revisions`, `race_competitor_link_audit`, `agent_run_events`) stay
as domain detail and are referenced from it, per spec.md:280.

`backend/app/models/audit_log.py` (new).

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `BigInteger().with_variant(SQLITE_INTEGER(), "sqlite")` | no | autoincrement | PK. The SQLite variant is mandatory: without it the offline test lane fails with `NOT NULL constraint failed` because a plain `BIGINT` PK is not a ROWID alias. Same idiom and same reason as `backend/app/models/race_competitor_link_audit.py:78-86`. |
| `occurred_at` | `DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")` | no | `datetime.now(timezone.utc)` (Python-side) | **fsp=6 is required by FR-002 ("sub-second precision").** MySQL 8.4 defaults `DATETIME` to `fsp=0` and silently truncates (dev.mysql.com/doc/refman/8.4/en/date-and-time-type-syntax.html) — which is already happening to `race_result_revisions.changed_at` (declared as a bare `sa.DateTime()` in `backend/alembic/versions/0edd41998022_agrega_tablas_race_result_revisions_y_.py:84`) and to `race_competitor_link_audit.created_at`. Those are pre-existing gaps, not introduced here; this table must not inherit them because two coaches can act inside the same second (US5). No `timezone=True` — the MySQL dialect ignores it and the project stores naive UTC. |
| `actor_user_id` | `FK users.id ondelete=RESTRICT` | yes | — | `NULL` **only** when `actor_kind != user`. Never denormalise the name: FR-018 guarantees the row survives, so a JOIN always resolves, including for deactivated accounts (FR-013). |
| `actor_kind` | `Enum(AuditActorKind)` | no | — | `user` / `system` / `webhook` / `cron`. Never defaults to `user`; unattended writes must set it explicitly (FR-002, Edge Case spec.md:167). |
| `actor_role` | `Enum(UserRole)` | yes | — | **Snapshot** of the actor's role at write time. Roles change; this column must never be re-derived by joining `users.role` at read time. `NULL` when `actor_kind != user`. |
| `club_id` | `FK clubs.id ondelete=SET NULL` | yes | — | Scopes FR-006. `SET NULL` (not RESTRICT) so a future club deletion can never be blocked by, or silently drop, audit rows. Nullable in DDL; the service layer requires it for every club-scoped entity and leaves it `NULL` only for genuinely club-less actions (e.g. a password-reset consumption). |
| `athlete_id` | `FK athletes.id ondelete=SET NULL` | yes | — | Populated only when the action concerns one athlete (FR-007). Archived athletes are **not** filtered out of history reads (Edge Case spec.md:176), so this FK must survive the soft delete — it does, because §4 archives instead of destroying. |
| `entity_type` | `String(64)` | no | — | Polymorphic discriminator. Closed catalogue **in Python** (`AuditEntityType`), not a DB enum: a DB enum would need an `ALTER TABLE` every time a table becomes auditable, and MySQL enum reordering is a footgun. Validated on write and by the coverage test (FR-009). |
| `entity_id` | `BigInteger` | no | — | Polymorphic; **no FK is possible**. Accepted risk (see §8.4). |
| `action` | `Enum(AuditAction)` | no | — | Closed catalogue matching FR-001's verb list. |
| `changed_fields` | `JSON` | no | `list` (`[]`) | A JSON **array of column-name strings only** — never values. FR-003. |
| `diff_json` | `JSON` | yes | `NULL` | `{"<field>": {"before": …, "after": …}}` **restricted to `VALUE_ALLOWLIST[entity_type]`** (§2.5). Anything not allow-listed is dropped before the row is built, and an automated privacy test re-scans every produced row (FR-003). |
| `reason_code` | `String(40)` | yes | `NULL` | Closed catalogue **in Python** (`AuditReasonCode`) for the same reason as `entity_type`. Mandatory for the actions listed in §2.4; refused (422) when absent. |
| `request_id` | `String(32)` | no | — | `uuid4().hex` (exactly 32 chars). One value per logical operation — per HTTP request, or per invocation for `webhook`/`cron`/`system` actors. This is FR-002's "correlation reference" and what makes Acceptance Scenario 5 (spec.md:27) true for bulk roster saves and batch newsletter generation. |
| `meta_json` | `JSON` | yes | `NULL` | Small, non-PII context for rendering: `{"document_kind": "growth_pdf"}`, `{"removed_count": 143}`, `{"period": "2026-03"}`, `{"recipients_count": 2}`. Never a name, an email address, free text, a measurement or a narrative. Covered by the same privacy scan as `diff_json`. |

### 1.1 Indexes

| Name | Columns | Serves |
|---|---|---|
| `ix_audit_club_time` | `(club_id, occurred_at DESC)` | FR-006 club history, newest-first, the default read. |
| `ix_audit_actor_time` | `(actor_user_id, occurred_at DESC)` | "filter by coach B" (spec.md:19) and the per-coach history link in FR-032. |
| `ix_audit_entity_time` | `(entity_type, entity_id, occurred_at DESC)` | "history of this one record"; also the record-type filter of FR-006 (leftmost-prefix on `entity_type`). |
| `ix_audit_athlete_time` | `(athlete_id, occurred_at DESC)` | FR-007 per-athlete "historial" panel. |
| `ix_audit_request_id` | `(request_id)` | Grouping one logical operation (FR-002 / AS5). Single-column, not composite — the grouping is always "all rows of this request", never time-sliced. |

Descending index parts are real indexes on MySQL 8.0+ (not just parser sugar) and are
ignored/normalised on SQLite, so the same DDL serves both lanes.

`occurred_at` alone is deliberately **not** indexed: the only query that filters on it
without a club is the retention purge (§6.3), which runs monthly on a table of low
thousands of rows. Add `ix_audit_occurred_at` only if the table ever passes ~1 M rows —
a sixth index on a write-hot table is not worth paying for today.

`changed_fields`, `diff_json` and `meta_json` are **never indexed**. MySQL cannot index a
`JSON` column directly; it would require a stored generated column plus its own index,
and no read path in this feature filters on JSON content.

### 1.2 Append-only invariants (FR-004)

1. The model has **no** `updated_at` / `updated_by` column, by construction.
2. All ORM relationships on `AuditLog` (`actor`, `club`, `athlete`) are declared
   `viewonly=True`, so no cascade can ever write through them.
3. The application MUST NOT issue `update(AuditLog)`, `delete(AuditLog)` or
   `session.delete(<AuditLog>)` anywhere. The single exception is
   `app/services/retention.py`, which implements FR-030.
4. Enforcement: a static test (`backend/tests/test_audit_append_only.py`) greps
   `backend/app/` for `AuditLog` appearing inside an `update(` / `delete(` construct and
   fails on any hit outside `app/services/retention.py`; plus a behavioural test that
   runs a realistic multi-action scenario and asserts no row's `id`, `occurred_at` or
   `diff_json` changed.
5. DB-level hardening (a `BEFORE UPDATE` / `BEFORE DELETE` trigger raising `SIGNAL`, or
   a grant without `UPDATE`/`DELETE` on this table) is **explicitly deferred**: this
   codebase has zero triggers today (no `CREATE TRIGGER` anywhere in
   `backend/alembic/versions/`) and Hostinger gives the app a single DB user. Documented
   as a follow-up in the runbook, not implemented here.

### 1.3 Retention (FR-030)

- Horizon: **24 months** on `occurred_at`.
- The cutoff timestamp is computed **once** in the preview step and passed verbatim to
  the confirm step — never recomputed from a second `now()`, or rows could cross the
  boundary between the count the administrator approved and the delete that ran.
- The purge writes one new row per affected `club_id` (`action=purge`,
  `actor_kind=cron` when the scheduled workflow runs it or `system` when an operator runs
  the CLI by hand — **never `user`**: a CLI has no authenticated session, so attributing
  the row to a person would fabricate an attribution nobody verified,
  `entity_type=audit_log`, `entity_id=0`, `reason_code=retention_24m`,
  `meta_json={"removed_count": N, "cutoff": "<iso>", "job": "audit_retention"}`). This is
  additive — one INSERT per club — and therefore not a violation of §1.2, which forbids
  UPDATE/DELETE *of existing rows* by the app. On today's single-club deployment (§9) that
  is exactly one row; `contracts/retention-purge.md` §0 and §1.4 own the details.

---

## 2. Catalogues

`backend/app/models/audit_log.py` for the enums that reach the DDL; the two
Python-only catalogues and the allow-list live in `backend/app/services/audit.py`.

### 2.1 `AuditAction` (DB enum, closed)

Mirrors FR-001's verb list one-for-one.

| Value | Used for |
|---|---|
| `create` | any new row |
| `update` | any field change |
| `archive` | soft delete (athlete, session-attendance entry, template) |
| `delete` | permanent delete (parent account, calendar event, roster entry) |
| `restore` | un-archive (FR-015) |
| `approve` | newsletter / monthly report approval |
| `unapprove` | approval cleared by a later edit (US5 AS3) |
| `send` | family newsletter e-mail, report e-mail (FR-005) |
| `export` | PDF/DOCX download of a document containing a minor's data (FR-005) |
| `cancel` | calendar event, training session, AI run |
| `execute` | session executed, AI run launched, import committed, interval recompute |
| `link` | competitor↔athlete, calendar↔race event, Strava connect, parent↔athlete |
| `unlink` | the inverse of `link` |
| `role_change` | `users.role` or `club_members.role_in_club` changed |
| `activate` / `deactivate` | `users.is_active` flipped (FR-020) |
| `purge` | the retention job itself (FR-030), the only writer allowed to remove rows |

### 2.2 `AuditActorKind` (DB enum, closed)

| Value | Concrete callers in this codebase |
|---|---|
| `user` | any request carrying a `current_user`; `actor_user_id` and `actor_role` MUST be set |
| `webhook` | `POST /api/webhooks/resend` (`backend/app/routers/webhooks_resend.py:112`), `POST /api/integrations/strava/webhook` (`backend/app/routers/strava_integration.py:376`) |
| `cron` | `POST /api/integrations/strava/reconcile` (`backend/app/routers/strava_integration.py:409`, driven by `.github/workflows/strava-reconcile.yml`) and the scheduled retention purge |
| `system` | in-process, no request: the lifespan orphan-run reconciliation (`backend/app/main.py:24-40` → `app/services/race/ai/run_reconciliation.py`), the boot scripts (`app/seed_growth_data.py`, `app/scripts/backfill_anthropometry.py`, both wired in `backend/entrypoint.sh`), and the detached LangGraph completion callbacks that write from their own session (`backend/app/routers/race_analysis.py:730-742`, `backend/app/routers/athlete_race_analysis.py:895-905`) |

Four values, not six: `backfill`, `purge_job` and `reconciliation` all collapse into
`system`/`cron` without losing anything a reader needs, and `meta_json.job` carries the
specific job name when it matters.

### 2.3 `AuditEntityType` (Python catalogue, one per auditable table)

`String(64)` in the DB; validated against this frozen set on write.

| Value | Table | Model |
|---|---|---|
| `user` | `users` | `backend/app/models/user.py:24` |
| `club` | `clubs` | `backend/app/models/club.py:24` |
| `club_member` | `club_members` | `backend/app/models/club.py:48` |
| `athlete` | `athletes` | `backend/app/models/athlete.py:42` |
| `parent_athlete` | `parent_athlete` | `backend/app/models/athlete.py:140` |
| `parent_invite` | `parent_invites` | `backend/app/models/parent_invite.py` |
| `parental_consent` | `parental_consents` | `backend/app/models/parental_consent.py:18` |
| `anthropometric_record` | `anthropometric_records` | `backend/app/models/anthropometry.py:47` |
| `training_session` | `training_sessions` | `backend/app/models/training_session.py:60` |
| `training_session_coach` | `training_session_coaches` | new, §3 |
| `session_attendance` | `session_attendance` | `backend/app/models/training_session.py:153` |
| `session_media` | `session_media` | `backend/app/models/session_media.py:32` |
| `calendar_event` | `calendar_events` | `backend/app/models/calendar_event.py:72` |
| `event_attendance` | `event_attendances` | `backend/app/models/calendar_event.py:216` |
| `monthly_report` | `monthly_reports` | `backend/app/models/training_session.py:218` |
| `club_project_profile` | `club_project_profiles` | `backend/app/models/club_project_profile.py:23` |
| `athlete_monthly_newsletter` | `athlete_monthly_newsletters` | `backend/app/models/athlete_newsletter.py:39` |
| `athlete_ai_insight` | `athlete_ai_insights` | `backend/app/models/athlete_ai_insight.py:100` |
| `agent_run` | `agent_runs` | `backend/app/models/agent_run.py:72` |
| `race_import` | `race_imports` | `backend/app/models/race_import.py:81` |
| `race_series` | `race_series` | `backend/app/models/race_series.py:56` |
| `race_event` | `race_events` | `backend/app/models/race_event.py` |
| `race_event_roster` | `race_event_roster` | `backend/app/models/race_event_roster.py` |
| `race_result` | `race_results` | `backend/app/models/race_result.py` |
| `race_competitor` | `race_competitors` | `backend/app/models/race_competitor.py` |
| `interval_structure` | `interval_structures` | `backend/app/models/interval_structure.py` |
| `interval_template` | `interval_templates` | `backend/app/models/interval_structure.py` |
| `strava_connection` | `strava_connections` | `backend/app/models/strava_connection.py` |
| `strava_activity` | `strava_activities` | `backend/app/models/strava_activity.py` |
| `athlete_ai_explanation` | `athlete_ai_explanations` | `backend/app/models/ai_explanation.py:34` |
| `audit_log` | `audit_log` | itself — only for `action=purge` |

Document exports and sends (FR-005) do **not** get their own `entity_type`. They are
recorded against the record the document is generated from — `athlete` for the
anthropometry/growth PDF and the medical-authorisation DOCX, `monthly_report` for the
club report, `athlete_monthly_newsletter` for the family bitácora, `agent_run` for the
race-analysis PDF — with `action=export|send` and
`meta_json.document_kind ∈ AuditDocumentKind`:
`growth_pdf`, `clearance_docx`, `monthly_report_pdf`, `monthly_report_docx`,
`newsletter_pdf`, `newsletter_email`, `race_analysis_pdf`, `session_instructivo_pdf`.
This keeps "one entity type per table" true and still answers "which document".

### 2.4 `AuditReasonCode` (Python catalogue, closed) + Spanish labels

Persisted as its string value in `audit_log.reason_code` and, where the domain keeps its
own column, in `athletes.deleted_reason_code` / `calendar_events.cancellation_reason_code`.
`AUDIT_REASON_LABELS: dict[AuditReasonCode, str]` holds the español-neutro label — the
backend never persists the label, exactly like `REVISION_REASON_LABELS`
(`backend/app/schemas/race_imports.py:57-67`).

| Group | Value | Label (es-CO) |
|---|---|---|
| Athlete archive (FR-015) | `athlete_left_club` | "Se retiró del club" |
| | `athlete_transferred` | "Traslado a otro club" |
| | `athlete_season_inactive` | "Inactivo esta temporada" |
| | `athlete_family_request` | "Solicitud de la familia" |
| | `athlete_duplicate_record` | "Registro duplicado" |
| | `athlete_data_correction` | "Corrección de datos" |
| Athlete restore | `restore_mistaken_archive` | "Archivado por error" |
| | `restore_returned_to_club` | "Regresó al club" |
| Event / session cancellation (FR-017) | `cancel_weather` | "Clima adverso" |
| | `cancel_venue_unavailable` | "Sede no disponible" |
| | `cancel_insufficient_athletes` | "Convocatoria insuficiente" |
| | `cancel_coach_unavailable` | "Entrenador no disponible" |
| | `cancel_rescheduled` | "Reprogramado" |
| | `cancel_organizer_cancelled` | "Cancelado por el organizador" |
| Account state (FR-020) | `account_staff_rotation` | "Cambio de personal" |
| | `account_end_of_engagement` | "Fin de vinculación" |
| | `account_security` | "Motivo de seguridad" |
| | `account_reactivation` | "Reincorporación" |
| Parent account removal (FR-018) | `parent_family_request` | "Solicitud de la familia" |
| | `parent_duplicate_account` | "Cuenta duplicada" |
| Retention (FR-030) | `retention_24m` | "Retención: 24 meses cumplidos" |

**`reason_code` is mandatory** (422 when missing) for: `archive` and `restore` on
`athlete`; `cancel` on `calendar_event` and `training_session`; `deactivate` on `user`;
`delete` on `user`; `purge` on `audit_log`. It is optional elsewhere. Free text is never
accepted anywhere — this is the whole point of the catalogue (FR-003).

### 2.5 `VALUE_ALLOWLIST` — the only fields whose values may reach `diff_json`

`backend/app/services/audit.py::VALUE_ALLOWLIST: dict[str, frozenset[str]]`, keyed by
`entity_type`. Default for every entity not listed and every field not listed: **names
only in `changed_fields`, no value anywhere**.

Admissible categories, and nothing else: enum states, booleans/flags, dates of events
(never a birth date), foreign-key identifiers, small counters/versions.

| `entity_type` | Allow-listed fields |
|---|---|
| `athlete` | `club_id`, `club_join_date`, `parental_consent_obtained`, `deleted_reason_code` |
| `user` | `role`, `is_active`, `can_login` |
| `club_member` | `club_id`, `role_in_club` |
| `training_session` | `status`, `session_kind`, `scheduled_date`, `duration_min`, `calendar_event_id` |
| `training_session_coach` | `coach_user_id` |
| `session_attendance` | `status`, `archived_at` |
| `calendar_event` | `status`, `event_type`, `start_at`, `end_at`, `all_day`, `race_event_id`, `cancellation_reason_code` |
| `event_attendance` | `rsvp_status`, `actual_status` |
| `monthly_report` | `status`, `year`, `month`, `approved_by_user_id` |
| `athlete_monthly_newsletter` | `status`, `year`, `month`, `edit_version`, `hidden_blocks` *(key names only — see below)* |
| `athlete_ai_insight` | `coach_approved`, `confidence`, `is_fallback`, `prompt_version`, `season`, `valida_num` |
| `agent_run` | `status`, `prompt_version`, `graph_name` |
| `race_import` | `status`, `kind`, `event_id`, `series_id` |
| `race_result` | `deleted_at`, `category_id`, `competitor_id` |
| `race_competitor` | `athlete_id` |
| `strava_connection` | `athlete_id` |
| `anthropometric_record` | `evaluation_date`, `growth_source` |

Explicitly **never** allow-listed, in any entity: `first_name`, `last_name`, `email`,
`phone`, `birth_date`, `sex`, every `*_cm` / `*_kg` / `*_z_score` / `*_percentile`
column, `maturation_status`, `nutritional_status`, `training_implications`,
`individual_feedback`, `excuse_reason`, `coach_note`, `coach_notes`,
`coach_observations`, `coach_answer_text`, `notes`, `description`, `objectives`,
`summary_text`, `ai_summary`, `ai_narrative`, `narrative_blocks`, `stage_log_json`,
`stage_overrides`, `structured_json`, `recommendations_json`, `metrics_snapshot`,
`consent_*`, `ip_address`, `user_agent`, `sent_to`, `error_message`, `storage_url`,
`storage_path`, `filename_original`, `caption`.

`hidden_blocks` stores the *list of block keys* the coach hid; block keys are static
identifiers (`"resumen"`, `"carrera"`, …), never content — this is the one JSON column
whose value is admissible, and the privacy test asserts each element is a member of the
known key set rather than free text.

**Automated privacy test** (`backend/tests/test_audit_privacy.py`, modelled on
`backend/tests/test_privacy.py:31`): run a realistic multi-action scenario against the
offline app, then scan **every** produced `audit_log` row for (a) any key in `diff_json`
or `meta_json` not present in the allow-list for its `entity_type`, and (b) forbidden
substrings — the fixture's synthetic names, ISO date-of-birth patterns, and numeric
strings in measurement ranges. Zero tolerance; this is SC-001's second half.

---

## 3. New bridge table `training_session_coaches`

`TrainingSession` has no multi-coach concept today — a single
`created_by_user_id` (`backend/app/models/training_session.py:76`), and every family
notification resolves the coach through `_load_session_coach`
(`backend/app/services/training/sessions.py:853`), which always returns the *creator*
(called at `:715`, `:787`, `:839`). That is the bug behind US4.

`backend/app/models/training_session.py` (new class `TrainingSessionCoach`).

| Column | Type | Null | Notes |
|---|---|---|---|
| `session_id` | `FK training_sessions.id ondelete=CASCADE` | no | Part of the PK. |
| `coach_user_id` | `FK users.id ondelete=RESTRICT` | no | Part of the PK. `RESTRICT` because FR-018 forbids deleting a staff account anyway; a deactivated coach keeps their row (Edge Case spec.md:169). |
| `added_by_user_id` | `FK users.id ondelete=SET NULL` | yes | Who added this coach to this session. `NULL` for the migration backfill. |
| `added_at` | `DateTime` | no | `datetime.now(timezone.utc)`. `NULL`-free; the backfill copies `training_sessions.created_at`. |

```text
PrimaryKeyConstraint("session_id", "coach_user_id")
Index("ix_tsc_coach_user_id", "coach_user_id")          # "sessions where X is a coach" (FR-026, FR-032)
```

Composite PK (no surrogate `id`): the pair *is* the identity, it gives the uniqueness
constraint for free, and InnoDB clusters on it so "all coaches of this session" is a
single range read. The secondary index on `coach_user_id` is what makes the per-coach
direction cheap — without it FR-026's coach filter would be a full scan.

Why a bridge table and not a JSON `coach_ids` column on `training_sessions`: every other
N:M relation in this schema is a junction table (`ParentAthlete`,
`backend/app/models/athlete.py:140`; `ClubMember`, `backend/app/models/club.py:48`), a
JSON array cannot be indexed for FR-026 without a generated column, and it would have
nowhere to put `added_by_user_id` / `added_at`.

**Minimum-one invariant (FR-024, Edge Case spec.md:172).** Enforced in the service
layer, inside the same transaction as the removal:

```text
SELECT COUNT(*) FROM training_session_coaches
 WHERE session_id = :id FOR UPDATE          -- row lock, same transaction
→ if count would drop to 0: 409 "Una sesión debe tener al menos un entrenador."
→ DELETE
```

Not a DB `CHECK` (MySQL 8.4 `CHECK` cannot reference sibling rows) and not a trigger
(this codebase has zero triggers; introducing the first one for a single cardinality
rule fails the constitution's stack-discipline test). The `FOR UPDATE` read is the part
that closes the race where two coaches each remove "the other" simultaneously —
omitting it reintroduces exactly the concurrency hole this feature exists to close.

**Backfill**: one row per existing session, `coach_user_id = created_by_user_id`,
`added_by_user_id = NULL`, `added_at = training_sessions.created_at` (spec.md:285).

`created_by_user_id` is **kept** on `training_sessions` and keeps its current meaning
("who planned it"); the bridge answers a different question ("who leads it now").

---

## 4. Attribution columns on existing tables

Additive, nullable, no `server_default` (so MySQL 8.4 can use INSTANT `ADD COLUMN`).
Each subsection lists what is **already present** first — those columns must not be re-added.

### 4.1 `users` — `backend/app/models/user.py:24`

**Already present** (do not re-add): `id`, `email`, `hashed_password`, `first_name`, `last_name`, `phone`, `role`, `is_active` (`:38`), `can_login` (`:39`), `created_at` (`:40`), `created_by` (`:43`, legacy short name)

| New column | Type | Null | Notes |
|---|---|---|---|
| `updated_at` | `DateTime` | yes | `onupdate=now(utc)`. Backfilled to `created_at`. |
| `updated_by_user_id` | `FK users.id ondelete=SET NULL` | yes | Self-referential, like the existing `created_by`. |

FR-018 needs **no new column**: `DELETE /api/users/{id}` already refuses admin/coach
targets unconditionally (`backend/app/routers/users.py:317-320`) and login already
refuses inactive accounts (`backend/app/routers/auth.py:68-71`). What 041 changes there
is copy and audit instrumentation, not schema. It must also stop the
`UPDATE users SET created_by = NULL WHERE created_by = :user_id` statement at
`backend/app/routers/users.py:343-345` from firing on a parent deletion — that is the
literal violation of US2 AS7 ("no other record loses its created by attribution").

### 4.2 `athletes` — `backend/app/models/athlete.py:42`

**Already present** (do not re-add): `created_by` (`:57`, legacy short name), `created_at` (`:58`), `updated_at` (`:61`)

| New column | Type | Null | Notes |
|---|---|---|---|
| `updated_by_user_id` | `FK users.id ondelete=SET NULL` | yes | FR-010. |
| `deleted_at` | `DateTime` | yes | `NULL` = active. The soft-delete discriminator for FR-014. Indexed (see §9). |
| `deleted_by_user_id` | `FK users.id ondelete=SET NULL` | yes | FR-015. |
| `deleted_reason_code` | `String(40)` | yes | `AuditReasonCode` value from the `athlete_*` group. Mandatory when `deleted_at` is set (service-level check, since MySQL cannot express a two-column conditional `CHECK` portably here). |

Column names follow `race_results.deleted_at` (`backend/app/models/race_result.py:141`),
the existing soft-delete precedent, rather than the `archived_at` spelling used by
`athlete_ai_insights` (`backend/app/models/athlete_ai_insight.py:205`) — both exist in
the schema; `deleted_at` is chosen because it is the one paired with an index
(`ix_race_results_deleted_at`, `backend/app/models/race_result.py:105`) and the UI word
"archivar" is a copy decision, not a column name.

`DELETE /api/athletes/{athlete_id}` (`backend/app/routers/athletes.py:330-367`) currently
issues **eight** Core `delete()` statements including
`delete(ParentalConsent)` at `:359` — the Ley 1581 evidence. In 041 that whole body is
replaced by an UPDATE of the four columns above; **no child row is touched**. This is
also what fixes US2 AS4: three FKs to `athletes.id` are `ondelete=RESTRICT`
(`event_attendances.athlete_id`, `backend/app/models/calendar_event.py:237`;
`race_event_roster.athlete_id`, `backend/app/models/race_event_roster.py:76`;
`session_attendance.athlete_id`, `backend/app/models/training_session.py:183`), so today
the cascade raises an `IntegrityError` half-way for any athlete with real history.

No `SoftDeleteMixin` is introduced: `athletes` and `calendar_events` make two
occurrences (`session_media.deleted_at` already exists and only gains an actor). The
constitution's rule of three says wait for the third.

### 4.3 `session_attendance` — `backend/app/models/training_session.py:153`

**Already present** (do not re-add): `status` (`:185`), `rpe_omni`/`rubric_*`/`individual_feedback` (`:191-195`), `created_at` (`:196`), `updated_at` (`:199`)

| New column | Type | Null | Notes |
|---|---|---|---|
| `recorded_by_user_id` | `FK users.id ondelete=SET NULL` | yes | FR-011 — the coach who first entered the rating/feedback. |
| `updated_by_user_id` | `FK users.id ondelete=SET NULL` | yes | FR-011 — last editor. Together they render "registrado por A, editado por B". |
| `archived_at` | `DateTime` | yes | FR-016. Rows removed from a roster that already carry data are archived, not deleted. |

No `archived_by_user_id`: an attendance row is only ever archived as part of a roster
save, so the actor is already in `audit_log` for that same `request_id`. Adding a fifth
actor column here would be the redundant copy the constitution warns about.

`bulk_upsert_convocatoria` currently hard-deletes the removed rows
(`delete(SessionAttendance)`, `backend/app/services/training/attendance.py:40-45`). 041
splits that: rows where all of `rpe_omni`, `rubric_effort`, `rubric_attitude`,
`rubric_technique`, `individual_feedback` are `NULL` (untouched placeholders) are still
hard-deleted; any row carrying data gets `archived_at` set instead, and every read path
filters `archived_at IS NULL`.

### 4.4 `calendar_events` — `backend/app/models/calendar_event.py:72`

**Already present** (do not re-add): `status` (`:108`), `created_by_user_id` (`:135`), `created_at` (`:140`), `updated_at` (`:143`)

| New column | Type | Null | Notes |
|---|---|---|---|
| `updated_by_user_id` | `FK users.id ondelete=SET NULL` | yes | FR-010. |
| `cancelled_by_user_id` | `FK users.id ondelete=SET NULL` | yes | FR-017. |
| `cancelled_at` | `DateTime` | yes | FR-017. |
| `cancellation_reason_code` | `String(40)` | yes | `AuditReasonCode` `cancel_*` group. Replaces the free-text `reason` that `cancel_event` receives today and never persists. |
| `deleted_at` | `DateTime` | yes | Permanent delete becomes a soft delete so the audit row's `entity_id` still resolves. |
| `deleted_by_user_id` | `FK users.id ondelete=SET NULL` | yes | FR-017. |

`cancel_event(..., reason: str, user: "User")` already **accepts** the actor
(`backend/app/services/calendar/events.py:463`) and never reads it — `reason` only reaches
the outbound notification. `delete_event_permanent`
(`backend/app/services/calendar/events.py:541`) does not even accept a user, so the
router must start passing `current_user` into both.

### 4.5 `monthly_reports` — `backend/app/models/training_session.py:218`

**Already present** (do not re-add): `status` (`:236`, `MonthlyReportStatus` = `draft`/`approved`), `generated_by_user_id` (`:242`), `generated_at` (`:245`)

| New column | Type | Null | Notes |
|---|---|---|---|
| `updated_at` | `DateTime` | yes | `onupdate`. Missing today. |
| `updated_by_user_id` | `FK users.id ondelete=SET NULL` | yes | FR-010. |
| `approved_by_user_id` | `FK users.id ondelete=SET NULL` | yes | **New capability** — there is no approval attribution at all today; `update_report_blocks` only flips `status` (`backend/app/services/training/reports.py:818`). |
| `approved_at` | `DateTime` | yes | idem. |
| `previous_approved_by_user_id` | `FK users.id ondelete=SET NULL` | yes | FR-010's "previously approved by", survives regeneration. |
| `previous_approved_at` | `DateTime` | yes | idem. |

The regeneration branch at `backend/app/services/training/reports.py:194-200` currently
overwrites `generated_by_user_id`/`generated_at` and resets
`status = MonthlyReportStatus.DRAFT` with nothing preserved. 041 changes it to: copy
`approved_by_user_id`/`approved_at` into the `previous_*` pair **before** clearing them,
then reset the status. See §7.4.

### 4.6 `athlete_monthly_newsletters` — `backend/app/models/athlete_newsletter.py:39`

**Already present** (do not re-add): `status` (`:72`, `draft`/`approved`/`sent`/`failed`/`outdated`), `generated_by_user_id` (`:100`), `approved_by_user_id` (`:103`), `approved_at` (`:106`), `sent_at` (`:107`), `coach_note` (`:140`), `read_by_user_id` (`:144`), `created_at` (`:148`), `updated_at` (`:153`)

| New column | Type | Null | Notes |
|---|---|---|---|
| `coach_note_author_id` | `FK users.id ondelete=SET NULL` | yes | FR-012. Mirrors `race_results.coach_note_author_id` (`backend/app/models/race_result.py:137`) exactly — same pattern, second occurrence. |
| `coach_note_updated_at` | `DateTime` | yes | FR-012. Mirrors `race_results.coach_note_updated_at` (`:140`). |
| `last_edited_by_user_id` | `FK users.id ondelete=SET NULL` | yes | FR-010 — the studio's "última edición por". |
| **`edit_version`** | `Integer` | no (`default=1`) | Optimistic-concurrency counter for FR-027. **Not named `content_version`** — see below. |

Both `coach_note_*` columns are exposed **only** on the coach/admin response schema and
are absent from the parent schema, the family PDF template
(`backend/templates/documents/pdf/athlete_stage_log.html`) and the family e-mail
template (`backend/templates/email/athlete_stage_log.html`), per FR-012.

#### Why the optimistic-lock counter is `edit_version`, not `content_version`

Migration `8b5ac1f24f61` ("drop newsletter content_version", down-revision
`d0e1f2a3b4c5`) removed `content_version SMALLINT NOT NULL DEFAULT 1` when the legacy v1
newsletter pipeline was retired
(`backend/alembic/versions/8b5ac1f24f61_drop_newsletter_content_version.py:52-64`), after
first `DELETE`ing every row where `content_version = 1`.

Re-introducing the *same name* with new semantics (a version counter instead of a
pipeline switch) is **not safe enough to be worth it**, for three reasons of decreasing
strength:

1. **It breaks two live tests immediately, and correctly so.**
   `backend/tests/models/test_newsletter_stage_log_migration.py:110` asserts
   `"content_version" not in cols` against a schema built from the ORM metadata
   (`Base.metadata.create_all`), so simply adding the attribute to the model turns that
   test red; `backend/tests/models/test_newsletter_content_version_removal_migration.py:84`
   makes the same assertion against the migration. Both assertions are *about the v1
   pipeline being gone*, not about optimistic locking — "fixing" them by relaxing the
   assertion would delete the guard that keeps the retired pipeline retired.
2. **The downgrade path collides.** `8b5ac1f24f61.downgrade()` re-adds
   `content_version SMALLINT NOT NULL DEFAULT 1`
   (`…/8b5ac1f24f61_drop_newsletter_content_version.py:71-79`). A strictly sequential
   downgrade through 041 first drops 041's column and is fine — but any out-of-order or
   `alembic stamp`-assisted recovery (the realistic shape of a manual rollback on
   Hostinger) hits `Duplicate column name 'content_version'`.
3. **It re-poisons the vocabulary.** `content_version` still means "v1 vs v2 bitácora" in
   the templates (`backend/templates/documents/pdf/athlete_stage_log.html:4-7`,
   `backend/templates/email/athlete_stage_log.html:10`) and the docs
   (`docs/06-parents/038-bitacora.md:15`, `docs/implementation-status.md:685`). A reader
   grepping the name would get two unrelated meanings.

`edit_version` is unambiguous, collides with nothing, and matches plan.md. Semantics:
`NOT NULL DEFAULT 1`; every successful mutating write does
`UPDATE … SET edit_version = edit_version + 1 … WHERE id = :id AND edit_version = :expected`
and treats `rowcount == 0` as the conflict. See §7.3 and §8.2.

### 4.7 `athlete_ai_insights` — `backend/app/models/athlete_ai_insight.py:100`

**Already present** (do not re-add): `generated_by_user_id` (`:160`), `coach_approved` (`:201`), `approved_at` (`:204`), `archived_at` (`:205`), `deprecated_at` (`:208`), `coach_answer_text` (`:223`), `coach_answer_at` (`:224`)

| New column | Type | Null | Notes |
|---|---|---|---|
| `approved_by_user_id` | `FK users.id ondelete=SET NULL` | yes | Pairs with the existing `approved_at`. |
| `archived_by_user_id` | `FK users.id ondelete=SET NULL` | yes | Pairs with the existing `archived_at`. |
| `coach_answer_by_user_id` | `FK users.id ondelete=SET NULL` | yes | Pairs with the existing `coach_answer_at`; FR-011-adjacent (the coach's answer is authored content). |

Named with the `_user_id` suffix rather than the brief's shorthand
(`approved_by`/`archived_by`/`coach_answer_by`) to stay on the dominant convention and
not create a fourth naming style in a table that already uses `generated_by_user_id`.

### 4.8 Remaining tables

| Table (model) | Already present (do not re-add) | New columns |
|---|---|---|
| `session_media` (`backend/app/models/session_media.py:32`) | `uploaded_by_user_id` (`:64`), `uploaded_at` (`:67`), `deleted_at` (`:70`) | `deleted_by_user_id` `FK users SET NULL` |
| `anthropometric_records` (`backend/app/models/anthropometry.py:47`) | `evaluated_by` (`:68`, legacy short name), `created_at` (`:69`) | `updated_at` `DateTime` **+** `updated_by_user_id` `FK users SET NULL` — the brief lists only the actor, but FR-010 says "who last edited it **and when**", and this table has no `updated_at` at all |
| `race_imports` (`backend/app/models/race_import.py:81`) | `imported_by_user_id` (`:121`), `imported_at` (`:124`), `status` (`:110`, `pending`/`dry_run`/`committed`/`failed`) | `updated_at` `DateTime`, `committed_at` `DateTime`, **`committed_by_user_id`** `FK users SET NULL` — the third is beyond the brief but required verbatim by US6 AS2 (spec.md:123): "the commit records coach B while the parse keeps coach A as importer", which `imported_by_user_id` alone cannot express |
| `race_series` (`backend/app/models/race_series.py:56`) | `created_at` (`:98`), `updated_at` (`:101`) | `created_by_user_id` `FK users SET NULL` |
| `club_project_profiles` (`backend/app/models/club_project_profile.py:23`) | `created_at` (`:50`), `updated_at` (`:53`) | `created_by_user_id`, `updated_by_user_id`, both `FK users SET NULL` |
| `club_members` (`backend/app/models/club.py:48`) | `role_in_club` (`:58`), `joined_at` (`:59`), `UniqueConstraint(club_id, user_id)` (`:51`) | `added_by_user_id` `FK users SET NULL` |
| `agent_runs` (`backend/app/models/agent_run.py:72`) | `requested_by_user_id` (`:105`), `status` (`:96`), `started_at`/`finished_at` (`:94-95`) | `decided_by_user_id` `FK users SET NULL` **+** `decided_at` `DateTime` — FR-028 requires the run to *show* "who decided"; today the deciding user's id only exists inside the in-memory `resume_value` passed to LangGraph (`backend/app/routers/race_analysis.py:916-921`) and is dropped from the persisted `agent_run_events.payload_json` (`backend/app/routers/race_analysis.py:927-949`). `decided_at` is added with it so the run header renders in one query instead of a join to a table that has no ORM model |

Not touched by this feature: `race_results` (already has
`coach_note_author_id`/`coach_note_updated_at`/`deleted_at`, `backend/app/models/race_result.py:137-141`
and its own `race_result_revisions` trail), `race_competitors` (own
`race_competitor_link_audit` trail), `parental_consents`, `newsletter_delivery_events`
(append-only by construction).

---

## 5. `ActorTimestampMixin` — `backend/app/models/mixins.py` (new file)

`backend/app/models/base.py` today is `class Base(DeclarativeBase): pass` — three lines,
no mixins anywhere in `backend/app/models/`. **`Base` is not touched.**

```text
backend/app/models/mixins.py

class UpdatedByMixin:
    """Actor-only. For tables that already declare their own `updated_at`."""
    @declared_attr
    def updated_by_user_id(cls) -> Mapped[int | None]:
        return mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

class ActorTimestampMixin(UpdatedByMixin):
    """Actor + time. For tables that have neither."""
    @declared_attr
    def updated_at(cls) -> Mapped[datetime | None]:
        return mapped_column(
            DateTime,
            default=lambda: datetime.now(timezone.utc),
            onupdate=lambda: datetime.now(timezone.utc),
            nullable=True,
        )
```

`@declared_attr` is required for `updated_by_user_id`: a plain class-level
`mapped_column(ForeignKey(...))` would be a single shared `Column` object aliased across
every mapped class, which SQLAlchemy explicitly forbids. `updated_at` carries no
`ForeignKey` and would work as a plain attribute, but is declared the same way so the two
read identically.

Two classes, one public entry point: a single mixin cannot serve both groups, because
the tables that need only the actor (`athletes`, `calendar_events`,
`athlete_monthly_newsletters`, `session_attendance`, `race_series`,
`club_project_profiles`) already declare `updated_at` and a mixin cannot be partially
suppressed.

| Mixin | Applied to
| `ActorTimestampMixin` (actor + `updated_at`) | `User`, `MonthlyReport`, `AnthropometricRecord`, `RaceImport` |
| `UpdatedByMixin` (actor only) | `Athlete`, `CalendarEvent`, `SessionAttendance`, `ClubProjectProfile` |
| neither (explicit columns) | `AthleteMonthlyNewsletter` (`last_edited_by_user_id`, a different name), `AthleteAiInsight`, `SessionMedia`, `RaceSeries`, `ClubMember`, `AgentRun`, `TrainingSessionCoach` |

The mixins are declarative sugar only — Alembic still emits every column explicitly in
§6, because `batch_alter_table` operates on table names, not mixins.

---

## 6. Alembic migration

### 6.1 Single head confirmed

`2a8baa967cc6` is the **only** head. Verified two ways at planning time:

- `cd backend && alembic heads` → `2a8baa967cc6 (head)`.
- Static check over `backend/alembic/versions/` (50 files): every other revision id
  appears as somebody's `down_revision`, including the three that a naive grep misses
  because they are consumed by tuple-valued merge revisions —
  `11aaea26e2ba_merge_newsletter_and_ai_insights_heads.py:16`
  (`down_revision = ('8c1d2e3f4a5b', 'a1b2c3d4e5f7')`) and
  `b4c5d6e7f8a9_email_change_requests_and_merge_heads.py:36`
  (`('8c1d2e3f4a5b', 'a1b2c3d4e5f7', 'a1b2c3d4e5f8')`).

This closes the open question in spec.md:278. **No `alembic merge` is needed.**

```text
backend/alembic/versions/<rev>_multi_coach_governance.py

revision      = "<generated>"
down_revision = "2a8baa967cc6"
branch_labels = None
depends_on    = None
```

One revision for the whole feature: the backfills depend on the columns and the bridge
table created in the same step, so splitting them would create an intermediate state
where `training_session_coaches` exists and is empty — i.e. every session momentarily has
zero coaches, violating §3's invariant.

### 6.2 `upgrade()` order

1. `op.create_table("audit_log", …)` + the five indexes of §1.1.
2. `op.create_table("training_session_coaches", …)` with the composite PK, the two FKs
   and `ix_tsc_coach_user_id`.
3. Attribution columns, one `with op.batch_alter_table("<table>") as batch_op:` block per
   table, `add_column` then `create_foreign_key` inside the same block.
4. `op.create_index("ix_athletes_deleted_at", "athletes", ["deleted_at"])` and
   `op.create_index("ix_calendar_events_deleted_at", "calendar_events", ["deleted_at"])`
   and `op.create_index("ix_session_attendance_archived_at", "session_attendance", ["archived_at"])`
   — every listing now filters on these (§8.1).
5. Backfills (§6.3).

`downgrade()` reverses in the exact inverse order. The backfilled data is not restored
(same honest posture as `8b5ac1f24f61`'s docstring); the schema shape is.

### 6.3 Backfills (idempotent, dialect-aware)

All written with `op.execute(sa.text(...))` and a `dialect = op.get_bind().dialect.name`
branch where the SQL differs — the established pattern in
`backend/alembic/versions/c4d5e6f7a8b9_seed_race_categories.py:75-145` (MySQL
`ON DUPLICATE KEY UPDATE` vs SQLite `INSERT OR IGNORE`) and
`backend/alembic/versions/8c1d2e3f4a5b_athlete_ai_insights_history_and_calendar_link.py:126-142`.
No app model is ever imported into the migration.

| # | Backfill | Statement (shape) | Idempotent because |
|---|---|---|---|
| B1 | Session coaches = creator (spec.md:285) | `INSERT INTO training_session_coaches (session_id, coach_user_id, added_by_user_id, added_at) SELECT ts.id, ts.created_by_user_id, NULL, ts.created_at FROM training_sessions ts WHERE NOT EXISTS (SELECT 1 FROM training_session_coaches c WHERE c.session_id = ts.id)` | the `NOT EXISTS` guard; re-running is a no-op |
| B2 | Approved reports get an approval time | `UPDATE monthly_reports SET approved_at = generated_at WHERE status = 'approved' AND approved_at IS NULL` | the `IS NULL` guard |
| B3 | Newsletter lock counter | `UPDATE athlete_monthly_newsletters SET edit_version = 1 WHERE edit_version IS NULL` — only needed if the column is added nullable-then-tightened; with `server_default='1'` on the ADD and a follow-up `alter_column(server_default=None)` it is unnecessary | value already 1 |
| B4 | `users.updated_at` | `UPDATE users SET updated_at = created_at WHERE updated_at IS NULL` | `IS NULL` guard |
| B5 | `anthropometric_records.updated_at` | `UPDATE anthropometric_records SET updated_at = created_at WHERE updated_at IS NULL` | `IS NULL` guard |
| B6 | `race_imports` timeline | `UPDATE race_imports SET updated_at = imported_at WHERE updated_at IS NULL` and `UPDATE race_imports SET committed_at = imported_at WHERE status = 'committed' AND committed_at IS NULL` | `IS NULL` guards |

**B2 deliberately does not set `approved_by_user_id`.** Copying `generated_by_user_id`
into it would fabricate an attribution the system never recorded — exactly the kind of
false evidence FR-010 exists to prevent. Historical approved reports therefore render as
"Aprobado antes del registro de autoría" (a UI copy decision, contract
`concurrency-and-approvals.md`), and `approved_by_user_id` stays `NULL` until someone
approves again. `previous_approved_*` stays `NULL` for all pre-041 rows for the same
reason.

`athletes.deleted_at`, `session_attendance.archived_at`, `calendar_events.cancelled_*`
and every `*_by_user_id` column are **not** backfilled: `NULL` correctly means "we have
no record of who did this", which is the truth for everything that happened before this
feature.

### 6.4 MySQL 8.4 notes

- **`batch_alter_table` everywhere.** On SQLite (the default `pytest` lane) it is the
  only way to add an FK-bearing column, because SQLite cannot
  `ALTER TABLE … ADD COLUMN … REFERENCES … ON DELETE`; it recreates the table. On MySQL
  it is a thin wrapper that emits the plain `ALTER TABLE`. Both styles already coexist in
  this repo — the dialect branch of
  `backend/alembic/versions/8c1d2e3f4a5b_…py:112-127` ("SQLite no soporta ADD COLUMN con
  FK + ON DELETE; usar batch") and the unconditional style of
  `backend/alembic/versions/2a8baa967cc6_growth_source_on_anthropometry.py:44-50`. This
  migration uses the unconditional style for readability, since **every** new column here
  is nullable.
- **`fsp=6`.** `audit_log.occurred_at` must be declared
  `sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")` (import from
  `sqlalchemy.dialects.mysql`, the same way `strava_connection.py:27` imports `VARBINARY`
  and `privacy_policy.py:7` imports `LONGTEXT`). A bare `sa.DateTime()` compiles to
  `DATETIME` with `fsp=0` on MySQL 8.4 and silently truncates the microseconds Python
  computes — the pre-existing defect in `race_result_revisions.changed_at`. **Verify in
  the `mysql` lane** (`pytest -m mysql`) that the generated DDL contains `DATETIME(6)`
  and that a round-trip preserves microseconds; the SQLite fallback for a MySQL dialect
  type is by-precedent, not by documentation.
- **`JSON` columns are never indexed** (`changed_fields`, `diff_json`, `meta_json`).
  MySQL requires a stored generated column + an index on it; no read path needs it.
- **INSTANT DDL.** Every new column is nullable with no `server_default` and is appended
  at the end of the table, so MySQL 8.0+ performs `ADD COLUMN` in-place/instant (brief
  metadata lock, no table rewrite). The only exception is
  `athlete_monthly_newsletters.edit_version` (`NOT NULL DEFAULT 1`), which is also
  INSTANT-eligible on 8.0.12+ but on a table of a few hundred rows either way.
- **Adding the FKs is the slow part.** `ALTER TABLE … ADD CONSTRAINT … FOREIGN KEY`
  requires a validating pass. On this dataset (≈20 athletes, low hundreds of sessions)
  it is milliseconds, but it is still prod DDL on Hostinger — coordinate before running,
  per repo policy (same warning as
  `backend/alembic/versions/2a8baa967cc6_growth_source_on_anthropometry.py` docstring).
- **Enums are inline per column** in MySQL, so the new `Enum(AuditAction)`,
  `Enum(AuditActorKind)` and the reuse of `Enum(UserRole)` for `actor_role` create no
  shared DB type and cannot collide with existing ones.

### 6.5 Required migration tests

- SQLite lane: `upgrade()` then `downgrade()` round-trip; assert every new column and
  index exists after upgrade and is gone after downgrade; assert B1 produces exactly one
  bridge row per pre-existing session and is a no-op on a second run.
- `mysql` lane (`pytest -m mysql`, DB name ending in `_test`): assert
  `SHOW CREATE TABLE audit_log` contains `datetime(6)`; assert a written row keeps its
  microseconds; assert the five audit indexes exist with the expected column order.

---

## 7. State transitions

### 7.1 Athlete: active → archived → restored (FR-014, FR-015)

```text
                 archive(actor, reason ∈ athlete_*)
   ┌──────────┐ ───────────────────────────────────► ┌───────────┐
   │  active  │                                      │ archived  │
   │ deleted_ │ ◄─────────────────────────────────── │ deleted_* │
   │ at NULL  │      restore(admin, reason ∈         │ set       │
   └──────────┘        restore_*)                    └───────────┘
```

| Transition | Who | Writes | Audit row |
|---|---|---|---|
| active → archived | admin or coach of the club | `deleted_at=now`, `deleted_by_user_id`, `deleted_reason_code` | `action=archive`, `entity_type=athlete`, `reason_code` required |
| archived → active | **admin only** (FR-015) | the three columns back to `NULL` | `action=restore`, `reason_code` required |
| archived → archived | — | refused (409, "El atleta ya está archivado") | none |

Invariants:

- **No child row is ever touched.** Consent, measurements, attendance, results, calendar
  audiences and race rosters keep pointing at the athlete (US2 AS2/AS8). This is what
  makes the three `RESTRICT` FKs harmless.
- The athlete is excluded from **every** active surface (§8.1) but **not** from history
  reads (Edge Case spec.md:176) and **not** from historical counts already produced.
- The cycle may repeat any number of times; each archive and each restore is its own
  audit row, so the timeline stays continuous (Edge Case spec.md:175).
- A parent whose only linked athlete is archived gets an empty list, never a 404
  (US2 AS5) — enforced by filtering inside `parent_athlete_ids`
  (`backend/app/services/permissions.py:63`), the single choke point used by 7+ routers.

### 7.2 Session coaches (FR-024)

```text
create session ──► {creator}                    (1 coach, from the wizard default)
add coach      ──► {creator, other}             (any active coach of the club)
remove coach   ──► allowed while count > 1
remove coach   ──► 409 when it is the last one  (§3, FOR UPDATE guard)
deactivate coach ─► set unchanged; the session list flags
                    "único entrenador inactivo"  (Edge Case spec.md:169)
```

Deactivating a user never rewrites `training_session_coaches` — history is not rewritten.
The flag is a derived read (`EXISTS (coaches of this session where users.is_active)` is
false), not a stored column.

### 7.3 Newsletter: draft / approved / sent, with `edit_version` (FR-027, US5)

`NewsletterStatus` (`backend/app/models/athlete_newsletter.py:29-36`) is unchanged:
`draft`, `approved`, `sent`, `failed`, `outdated`.

```text
        edit (If-Match ok)          approve
draft ──────────────────► draft ───────────► approved
  ▲                                             │
  │            edit (clears approval)           │
  └─────────────────────────────────────────────┘
                                                │ send
                                                ▼
                                              sent   ── edit ──► 409 (immutable, unchanged today)
```

`edit_version` semantics:

| Situation | Result |
|---|---|
| client sends the `edit_version` it loaded, and it matches | write applies; `edit_version += 1`; `last_edited_by_user_id`, `updated_at` set |
| client sends a stale `edit_version` (`rowcount == 0`) | **409 Conflict** — the body carries `current_version` (the stored `edit_version`, read in the same transaction) so the UI can offer "Recargar". |
| client sends no version at all | **428 Precondition Required** — fails loudly instead of silently reverting to last-write-wins |
| the write is refused for a *state* reason (already `sent`) | **409 Conflict** — the existing behaviour and the existing status code used across this router (`backend/app/routers/athlete_monthly_newsletters.py`, 6+ sites). The body carries **no** `current_version` key. |

**412 is never emitted.** RFC 9110 §13.1.2 does make 412 the literal code for a failed
client-declared precondition, and that reading is recorded as the rejected alternative in
`research.md` R-14; the wire status is 409 because it is this codebase's uniform conflict
idiom and the frontend error helper already branches on it.

Both refusals are therefore `409`, and the discriminator is the **body, not the status**:
the stale-precondition response is the only 409 in this router that carries
`current_version`. That key is what lets the client tell "recarga y reintenta" (silent,
recoverable) apart from "esta acción no es posible ahora" (terminal), exactly as specified
in `contracts/concurrency-and-approvals.md` §2.5. `edit_version` is incremented on
**every** mutating write, including `approve`, `regenerate-block` and `attach-insights`,
so an approval by coach B invalidates coach A's stale draft too.

Editing an `approved` newsletter clears the approval **as it does today** (US5 AS3) and
produces two audit rows sharing one `request_id`: `action=update` and
`action=unapprove`.

### 7.4 Monthly report: approval evidence survives regeneration (FR-010, US5 AS4)

`MonthlyReportStatus` stays `draft` / `approved`.

```text
generate ──► draft ── approve ──► approved
                ▲                    │
                │   regenerate(force_regenerate=True)
                │                    │
                └────────────────────┘
                     before clearing:
                       previous_approved_by_user_id ← approved_by_user_id
                       previous_approved_at         ← approved_at
                     then:
                       approved_by_user_id ← NULL
                       approved_at         ← NULL
                       generated_by_user_id ← the regenerating coach
                       generated_at         ← now
                       status               ← draft
```

`previous_approved_*` is only overwritten when a **new** approval is later cleared —
i.e. it always holds the most recent *superseded* approval, never `NULL`-ed by a
regeneration of an already-draft report. The UI renders "Aprobado anteriormente por
{nombre} el {fecha}". Two audit rows, one `request_id`: `action=update`
(`entity_type=monthly_report`) and `action=unapprove`.

Regression test (must fail on today's code): approve as coach A, regenerate as coach B,
assert `previous_approved_by_user_id == A` and `generated_by_user_id == B`. Today
`backend/app/services/training/reports.py:194-200` loses A entirely.

### 7.5 Session attendance archive (FR-016)

```text
roster save removes athlete X:
  row has no rating and no feedback  ──► hard DELETE (untouched placeholder)
  row has any of rpe_omni / rubric_* / individual_feedback
                                     ──► archived_at = now  (row kept, audit action=archive)
  athlete re-added later             ──► archived_at = NULL (audit action=restore)
```

---

## 8. Validation rules and key queries

### 8.1 `deleted_at IS NULL` must be applied at every active-athlete read site

This is the highest-risk part of FR-014: one missed filter leaks an archived athlete into
a family-facing surface. There is no ORM-level default scope in this codebase (every read
is an explicit `select(...)`), and a global `with_loader_criteria` listener is
**rejected** — administrators must still see archived athletes (US2 AS2), so the filter
would have to be selectively bypassed anyway, and it would be invisible to a reviewer
reading a router.

Instead: one shared helper `app/services/athlete_scope.py::active_athletes_stmt()` plus a
CI check. Sites that must filter:

| Surface | Site |
|---|---|
| Coach athlete list (also backs the AI athlete picker via `useAthletes`) | `backend/app/routers/athletes.py:161-227` |
| Parent "my athletes" | `backend/app/routers/parent_athletes.py:171-220` |
| Parent scope choke point (7+ routers: activities, athletes, club insights, calendar ×2, monthly reports, parent newsletters, training sessions ×3) | `backend/app/services/permissions.py:63` |
| Admin/coach parent-link list | `backend/app/routers/parent_athletes.py:380-411` |
| Dashboard counts (consents, insights, weekly load) | `backend/app/services/dashboard_summary.py:84-99,145,196-200` |
| Newsletter athlete resolution (single + club batch) | `backend/app/routers/athlete_monthly_newsletters.py:192,242,594` |
| AI run athlete resolution | `backend/app/routers/race_analysis.py:672` |
| Monthly report roster | `backend/app/services/training/reports.py` |
| Session wizard convocatoria candidates | `backend/app/services/training/sessions.py` |
| Calendar audience expansion | `backend/app/services/calendar/audiences.py` |

Sites that must **not** filter: the admin archive view, the club history and per-athlete
history endpoints, and any query reconstructing a past period.

Automated gate: a test that walks `backend/app/` for `select(Athlete)` / `Athlete.id.in_(`
occurrences and fails on any file:line not either calling the scope helper, applying
`Athlete.deleted_at.is_(None)`, or listed in an explicit reviewed `ARCHIVE_SCOPE_EXEMPT`
set. This is a **separate** gate from FR-009's audit-coverage check — same spirit,
different omission; implementing one and assuming it covers the other leaves a real hole.

### 8.2 Other validation rules

| Rule | Where | Failure |
|---|---|---|
| `club_id` required when the **created account's** role is `coach` — not only when the *caller* is a coach | `backend/app/routers/users.py:53-58` only checks `current_user.role == coach`, so an admin can create a clubless coach today (`backend/tests/test_users.py:32-57` proves it, and asserts 201) | 422 |
| `club_members.role_in_club` must match `users.role` (FR-022) | `backend/app/routers/clubs.py:119-158` (`add_member`) has no such check; reuse the `role_in_club_map` already inline at `backend/app/routers/users.py:112-116` | 422 |
| A session always has ≥ 1 coach | §3, `SELECT … FOR UPDATE` in the same transaction | 409 |
| `deleted_reason_code` required whenever `deleted_at` is set | service layer (`archive_athlete`) | 422 |
| `reason_code` required for the actions in §2.4 | `record_audit` | 422 |
| `diff_json` keys ⊆ `VALUE_ALLOWLIST[entity_type]` | `record_audit`, before the row is built | silently dropped **and** asserted by the privacy test |
| `edit_version` must be supplied on newsletter writes | `backend/app/routers/athlete_monthly_newsletters.py:1006-1089` (`patch_newsletter`) applies fields unconditionally today | 428 (missing) / 409 (stale) |
| `audit_log` never UPDATEd or DELETEd outside `services/retention.py` | §1.2 | static test failure |

### 8.3 Key queries

**Q1 — club history (FR-006, FR-008).** One indexed query plus one join for names, never
N+1:

```text
SELECT a.*, u.first_name, u.last_name
  FROM audit_log a
  LEFT JOIN users u ON u.id = a.actor_user_id
 WHERE a.club_id = :club
   [AND a.actor_user_id = :actor]
   [AND a.entity_type   = :entity_type]
   [AND a.athlete_id    = :athlete]
   [AND a.occurred_at  >= :from AND a.occurred_at < :to]
 ORDER BY a.occurred_at DESC, a.id DESC
 LIMIT :limit OFFSET :offset            -- limit ≤ 50, offset/limit like every other list
```

`ix_audit_club_time` covers the unfiltered default; the optional predicates fall back to
`ix_audit_actor_time` / `ix_audit_entity_time` / `ix_audit_athlete_time` when they are the
selective one. `(occurred_at DESC, id DESC)` is the total order — `id` breaks ties
deterministically even at microsecond resolution. Query-count test asserts exactly 2
queries (rows + total).

**Q2 — per-athlete history (FR-007).** Same shape, `WHERE a.athlete_id = :id`, no club
predicate needed (the athlete determines the club); RBAC is checked before the query.

**Q3 — per-coach activity, no double counting (FR-032, SC-008).**

```text
-- club total for the period: session grain, deduped
SELECT COUNT(DISTINCT ts.id)
  FROM training_sessions ts
  JOIN training_session_coaches c ON c.session_id = ts.id
 WHERE ts.club_id = :club AND ts.scheduled_date BETWEEN :from AND :to;

-- per coach: a co-coached session legitimately counts once for EACH of its coaches
SELECT c.coach_user_id, ts.status, COUNT(*) AS n
  FROM training_session_coaches c
  JOIN training_sessions ts ON ts.id = c.session_id
 WHERE ts.club_id = :club AND ts.scheduled_date BETWEEN :from AND :to
 GROUP BY c.coach_user_id, ts.status;
```

`COUNT(DISTINCT ts.id)` for the club total, plain `COUNT(*)` per coach. SC-008's
reconciliation rule is therefore: *the number of distinct sessions* equals the club
total, while `SUM(per-coach counts) ≥ club total`, with the excess exactly equal to the
number of extra coach assignments. The reconciliation test asserts
`club_total == COUNT(DISTINCT session_id across all per-coach buckets)`, **not** a naive
sum — spec.md:271 states the rule as "sum of per-coach sessions counted once per session".

The other per-coach counters read the attribution columns directly, each an indexed
equality on `<actor>_user_id` + a date range: attendance/feedback entries
(`session_attendance.recorded_by_user_id`), AI runs (`agent_runs.requested_by_user_id`),
results operations (`race_imports.imported_by_user_id`,
`race_result_revisions.changed_by_user_id`, `race_competitor_link_audit.user_id`),
documents approved/sent (`audit_log` where `action IN ('approve','send','export')`).

**Q4 — coach filter on listings (FR-026).**
`… JOIN training_session_coaches c ON c.session_id = ts.id AND c.coach_user_id = :coach`
for sessions (served by `ix_tsc_coach_user_id`);
`calendar_events.created_by_user_id = :coach` for other events. `list_sessions`
(`backend/app/services/training/sessions.py:868`) accepts only
`status/date_from/date_to/athlete_id/limit/offset` today.

### 8.4 Accepted risks

- **`entity_type`/`entity_id` carry no FK**, so a genuine hard delete elsewhere leaves a
  dangling reference. Acceptable because FR-014/FR-017/FR-018 push the app toward
  archive-instead-of-destroy; worth a code-review note whenever a future feature adds a
  hard-deletable entity.
- **Append-only is enforced in code and tests, not by the database** (§1.2 item 5).
- **`club_id` is nullable in DDL** but required by the service for club-scoped entities;
  a `NULL` `club_id` row is invisible to FR-006's club history by construction. The
  privacy/coverage test asserts every audited entity type produces a non-null `club_id`.

---

## 9. Volume, indexes and growth

Club scale: 1 club, ~20 athletes, 2 coaches + 1 admin, ~40 parents.

| Source | Rows/year (estimate) | Note |
|---|---|---|
| Session attendance saves | ~3 000 | the dominant term: ~150 sessions × ~20 roster rows, one audit row per athlete row, all sharing one `request_id` |
| Training sessions (create/update/execute/cancel) | ~450 | |
| Calendar events + RSVPs | ~800 | |
| Newsletters (generate/edit/approve/send/export) | ~1 200 | ~20 athletes × 10 months × ~6 actions |
| Monthly reports + project profile | ~150 | |
| Anthropometry | ~120 | ~6 measurements/athlete/year |
| AI runs, insights, HITL decisions | ~600 | |
| Race imports, revisions, competitor links | ~400 | |
| Document exports/sends (FR-005) | ~500 | |
| Staff/account/consent/parent-link changes | ~100 | |
| Automated actors (Resend + Strava webhooks, daily reconcile) | ~700 | |
| **Total** | **≈ 8 000 / year** | ≈ **16 000 rows** at the 24-month steady state |

Storage: ~250 B of fixed columns plus a small JSON payload → ~1 KB/row average, so
≈ 16 MB at steady state plus ≈ 8 MB of index — negligible on Hostinger and well inside
the free tier's working set. The five indexes cost ~5 index writes per INSERT; at ~8 000
INSERTs/year that is irrelevant to the p95 ≤ 1500 ms write budget, and the audit INSERT
rides inside the transaction the write already opened (no extra round trip to commit).

Read budget: every history/activity query above is a single indexed range scan with
`LIMIT ≤ 50` and one `LEFT JOIN users` (a handful of rows) — comfortably inside p95 ≤
500 ms, and covered by a query-count assertion rather than a timing assertion so the test
stays deterministic.

Growth triggers to watch:

| If … | Then … |
|---|---|
| the table passes ~1 M rows | add `ix_audit_occurred_at` so the retention purge stops full-scanning |
| a second club is onboarded | nothing changes — `club_id` is already the leading column of the default index |
| roster saves become far more frequent | consider collapsing a bulk roster save into one audit row with `meta_json.athlete_count`, at the cost of losing per-athlete granularity in Q2; **not** done now because FR-007 wants per-athlete entries |
| MySQL row-size or JSON growth becomes visible | `diff_json`/`meta_json` are already bounded by the allow-list; add an explicit size assertion in the privacy test |

New indexes introduced by this feature outside `audit_log`:
`ix_tsc_coach_user_id`, `ix_athletes_deleted_at`, `ix_calendar_events_deleted_at`,
`ix_session_attendance_archived_at`.
