# Research — Multi-coach governance (041)

**Date**: 2026-09-09 · **Inputs**: `spec.md` (US1–US8, FR-001…FR-034, SC-001…SC-010), the constitution, four code inventories of the running tree (write paths and commit sites; reusable domain patterns; frontend/test/e2e/CI; backend permissions), a web best-practice sweep (audit-log design, GDPR/Ley-1581 data minimisation, soft-delete on MySQL, RFC 9110 optimistic concurrency, staff deactivation), and Context7 documentation (`/websites/sqlalchemy_en_20`, `/websites/fastapi_tiangolo`, `/websites/alembic_sqlalchemy`, `/kludex/uvicorn`, `/tanstack/query`, `/shadcn-ui/ui`, `/remix-run/react-router`, `/react-hook-form/resolvers`, `/react-hook-form/documentation`).

Each entry: **Decision** · **Rationale** · **Alternatives considered** · **Sources**. Every repo claim below was re-verified against the working tree on 2026-09-09; contradictions between the input research and the tree are listed in *Contradictions resolved* at the end.

Naming in this document follows `plan.md`: the table is `audit_log` (not `history_entries`), the helper is `record_audit`, the concurrency token is `edit_version`, the correlation column is `request_id`.

---

## A. Audit log — schema, transaction boundary, minimisation, coverage, presentation

### R-01 One club-wide, append-only, entity-agnostic `audit_log` table

**Decision**: Add a single generic table `audit_log` (`app/models/audit_log.py`) rather than per-entity shadow tables. Columns:

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `BigInteger().with_variant(SQLITE_INTEGER(), "sqlite")` | no | Same idiom as `backend/app/models/race_competitor_link_audit.py:82-86` (needed so SQLite aliases the PK to ROWID in the offline test lane) |
| `occurred_at` | `mysql.DATETIME(fsp=6)` (generic `DateTime` variant for sqlite) | no | FR-002 sub-second precision — see R-02 |
| `request_id` | `String(36)` | no | FR-002 "correlation reference shared by all entries of the same request" — see R-05 |
| `actor_user_id` | FK `users.id` `ondelete="RESTRICT"` | yes | Null only when `actor_kind != person` |
| `actor_kind` | `Enum(AuditActorKind)` | no | `person`, `webhook_resend`, `webhook_strava`, `cron_strava_reconcile`, `startup_backfill`, `startup_seed`, `agent_run`, `purge_job` — see R-05 |
| `actor_role` | `Enum(UserRole)` | yes | Role **at the time** of the action; never re-derived by join |
| `club_id` | FK `clubs.id` `ondelete="RESTRICT"` | no | Scopes FR-006 |
| `action` | `Enum(AuditAction)` | no | FR-001 verb list verbatim: create, update, archive, delete, restore, approve, unapprove, send, export, cancel, execute, link, unlink, role_change, activate, deactivate, purge |
| `entity_type` | `Enum(AuditEntityType)` | no | Closed catalogue, polymorphic discriminator |
| `entity_id` | `BigInteger` | no | Polymorphic — no FK possible |
| `athlete_id` | FK `athletes.id` `ondelete="SET NULL"` | yes | Only when the action concerns an athlete (FR-007) |
| `changed_fields` | `JSON` (array of column names) | no, default `[]` | Names only (FR-003) |
| `diff_json` | `JSON` (object) | yes | Values only for allow-listed fields — see R-04 |
| `reason_code` | `Enum(AuditReasonCode)` | yes | Fixed catalogue (FR-002/FR-015/FR-017) |

Indexes (names fixed by `plan.md`): `ix_audit_club_time (club_id, occurred_at)`, `ix_audit_actor_time (actor_user_id, occurred_at)`, `ix_audit_entity (entity_type, entity_id)`, `ix_audit_athlete_time (athlete_id, occurred_at)`, plus a plain index on `request_id`. Actor display names are **not** denormalised: FR-018 makes staff accounts undeletable (only deactivatable), so a join to `users` always resolves — including for deactivated accounts (FR-013).

> **Superseded (Phase 1)**: `data-model.md` §1 carries the authoritative column list and index names; where it differs from this sketch, it wins. Two differences matter to a reader of this entry: `request_id` is `String(32)` (`uuid4().hex`, not `String(36)`), and `actor_kind` has the four values of `data-model.md` §2.2 (`user`, `system`, `webhook`, `cron`) instead of the eight listed here and in R-05 — the specific job name moves to `meta_json.job`. Recorded in `contracts/audit-recording.md` §10 point 1.

**Rationale**: This is the third instance of a pattern the project has already shipped twice — `RaceResultRevision` (`backend/app/models/race_result_revision.py:36-93`: actor FK RESTRICT, subject FK SET NULL, `Enum(..., values_callable=…)`, `diff_json`, closed `reason` catalogue) and `RaceCompetitorLinkAudit` (`backend/app/models/race_competitor_link_audit.py:1-132`, whose docstring already states the append-only and no-names rules). Generalising the third copy instead of writing a fourth near-duplicate is exactly the constitution's rule of three (Principle I). The generic single-table shape gives one query surface for both read views the spec needs (club-wide FR-006 and per-athlete FR-007); its known weakness (no per-entity type safety) is acceptable because entity-specific detail already lives in the existing domain trails, which the spec's Assumptions explicitly keep as "domain detail" indexed by the new log.

**Alternatives**: (a) per-entity shadow tables — rejected, ~15 near-identical tables for the FR-001 verb/entity matrix; (b) MySQL system-versioned/temporal tables — rejected, not available on this SQLAlchemy stack and cannot carry actor/reason/correlation, only column state; (c) full event sourcing — rejected, an architecture rewrite with no replay requirement; (d) a third-party audit library (SQLAlchemy-Continuum et al.) — rejected, a new runtime dependency (constitution "Stack discipline") for a pattern already hand-rolled twice here.

**Sources**: `backend/app/models/race_result_revision.py:36-93`; `backend/app/models/race_competitor_link_audit.py:1-132`; `backend/app/models/newsletter_delivery_event.py:13-16`; spec FR-001/FR-002; https://www.red-gate.com/blog/database-design-for-audit-logging; https://www.intelligentgraphicandcode.com/development/audit-trails; https://aakashsharan.com/event-sourcing-patterns-pitfalls

### R-02 `occurred_at` is declared `mysql.DATETIME(fsp=6)`

**Decision**: Declare `occurred_at` with explicit fractional-seconds precision (`from sqlalchemy.dialects.mysql import DATETIME`, `DATETIME(fsp=6)`, generic `DateTime` variant for the sqlite lane). Application code keeps writing `datetime.now(timezone.utc)` (naive-UTC-in-a-naive-column, the project convention); do **not** pass `timezone=True` (unused by the MySQL dialect) and do not switch to `TIMESTAMP`.

**Rationale**: MySQL 8.4 defaults `DATETIME` to `fsp=0` — whole seconds — unless the column is declared `DATETIME(fsp)`. The two existing audit tables are affected: `backend/alembic/versions/0edd41998022_agrega_tablas_race_result_revisions_y_.py:84` declares `sa.Column("changed_at", sa.DateTime(), nullable=False)` with no `fsp`, so production silently truncates microseconds that Python computed. FR-002 explicitly requires sub-second precision, and US5's two-coaches-in-the-same-second scenario is the case it exists for. Reaching into `sqlalchemy.dialects.mysql` for a MySQL-only capability that must still compile under aiosqlite has precedent here (`backend/app/models/strava_connection.py:27` `VARBINARY`, `backend/app/models/privacy_policy.py:7` `LONGTEXT`).

**Alternatives**: (a) plain `sa.DateTime` like the two precedent tables — rejected, fails FR-002 by construction; (b) `TIMESTAMP(6)` — rejected, session-timezone conversion and the 2038 bound, and it would break the project's "naive UTC set in Python" convention; (c) rely on autoincrement `id` for ordering — rejected, insert order across concurrent transactions is not wall-clock order and FR-002 asks for the *time*, not just a sort key. A monotonic `seq` tie-breaker (the idiom in `backend/app/services/race/ai/events.py`) is *not* added: `(occurred_at DESC, id DESC)` is a total order and one column cheaper. Verification note: the fsp fallback under the SQLite compiler is asserted by precedent, not by Context7; the migration test in the `mysql` lane must confirm the emitted DDL.

**Sources**: https://dev.mysql.com/doc/refman/8.4/en/date-and-time-type-syntax.html; Context7 `/websites/sqlalchemy_en_20` (dialects/mysql — `DATETIME(fsp)`, "`timezone` not used by the MySQL dialect"); `backend/alembic/versions/0edd41998022_agrega_tablas_race_result_revisions_y_.py:84`; `backend/app/models/strava_connection.py:27`; `backend/app/models/privacy_policy.py:7`

### R-03 One explicit helper, in the caller's transaction — not an outbox, not a flush listener

**Decision**: `app/services/audit.py::record_audit(db: AsyncSession, *, actor, action, entity_type, entity_id, …) -> AuditLog` does `db.add(AuditLog(...))` and returns; it never commits or opens a session of its own. It is called from the service layer (never from routers directly, so CLI, webhook and LangGraph callers obey the same rule), positioned so the row is queued **before the last commit of the logical operation** — not merely "somewhere in the request".

**Rationale**: `Session.add()` only moves an object to *pending*; nothing reaches the DB until the caller's flush/commit, so the audit row shares fate with the business write for free — exactly the spec's edge case "a failed request leaves neither the data change nor the entry" (FR-001). This is already the house pattern: `backend/app/services/race/revision.py:737-801` inserts a revision row inside each branch of its create/update/delete loop and flushes once at the end; `backend/app/services/race/competitor_linking.py:621,709` add the audit row and flush next to the mutation; `backend/app/services/training/attendance.py:58` and `backend/app/services/training/sessions.py:157` add inside helpers and let the outer caller commit. The dual-write problem the transactional-outbox pattern solves does not exist here (one MySQL database, no broker, no separate consumer), and the sources that describe the pattern say to avoid the relay for "a simple monolith with a single database" — which is also the only shape the free tier can host (no workers).

The hazard this decision must respect is *multiple commits per request*: `get_db()` (`backend/app/dependencies.py:16-22`) commits once after the handler, but ~46 explicit `await db.commit()` sites exist in `app/`, several per file (`backend/app/routers/athlete_monthly_newsletters.py` alone has 7; `backend/app/routers/race_imports.py:1017` commits early on purpose to release the MySQL connection before slow SFTP+pdfplumber work, and `backend/app/services/race/ingestor.py:254,449` commit twice more). A `record_audit` call placed after an early commit lands in a *different* transaction and can survive a later rollback. The instrumentation matrix in `contracts/audit-recording.md` must therefore pin the call site per endpoint, not per request.

**Alternatives**: (a) transactional outbox + relay — rejected, solves a cross-service problem this monolith does not have and needs a process the hosting tier cannot run; (b) `before_flush`/`after_flush` session listeners auto-diffing dirty objects — rejected twice over: they never fire for the ~20 Core statements that perform the most audit-worthy mutations (`backend/app/routers/athletes.py:359-366` eight `delete()` statements; `backend/app/routers/users.py:333-346`; `backend/app/services/training/attendance.py:41`; `backend/app/services/calendar/events.py:207,452,484`; `backend/app/services/race/competitor_linking.py:535,956`; `backend/app/routers/ai.py` `mysql_insert(...).on_duplicate_key_update()`; the `agent_runs`/`agent_run_events` raw `text()` layer in `backend/app/routers/race_analysis.py`), and even where they do fire they cannot know the business intent FR-002 requires (which verb, which reason code, which athlete, which `request_id`); (c) `SessionEvents.do_orm_execute()` — closer (it sees ORM-enabled Core DML) but still cannot supply reason/athlete/correlation without smuggling metadata through `execution_options`; (d) DB triggers / CDC — rejected, no authenticated user at that layer, breaks the sqlite lane, and stores raw values (FR-003).

**Sources**: Context7 `/websites/sqlalchemy_en_20` (`Session.add` semantics; asyncio "register ORM event listeners on `AsyncSession`"; Mapper events do not intercept bulk ORM DML); `backend/app/dependencies.py:16-22`; `backend/app/routers/athletes.py:359-366`; `backend/app/routers/race_imports.py:1017`; `backend/app/services/race/revision.py:737-801`; https://gaevoy.com/2021/03/18/audit-log-via-transactional-outbox.html; https://singhajit.com/transactional-outbox-pattern

### R-04 Field names by default; values only through a reviewed allow-list, guarded by a privacy test

**Decision**: `changed_fields` stores column **names** only. Values may additionally be written to `diff_json` **only** for fields listed in `app/services/audit.py::VALUE_ALLOWLIST: dict[AuditEntityType, frozenset[str]]` — restricted to states/enums, booleans, dates of events and other record identifiers, never a minor's name, birth date, sex, measurement, medical detail, consent text, feedback, coach note, narrative or AI output (FR-003). The allow-list is covered by an automated privacy test in the style of `backend/tests/test_privacy.py`: run a realistic multi-action scenario against the app, then scan every `audit_log` row for (a) any key outside the allow-list and (b) forbidden substrings — a synthetic forbidden-names fixture, ISO date-of-birth patterns, and measurement-shaped numerics.

**Rationale**: Matches both external guidance ("log deltas, not full rows"; GDPR minimisation: avoid logging full names, prefer identifiers) and the project's own written rule — `backend/app/models/race_competitor_link_audit.py:14-16` already states "Sin nombres. El audit guarda únicamente IDs + timestamp + acción", and `backend/app/models/newsletter_delivery_event.py:13-16` repeats it for delivery events. Because the actor here is club staff (not the protected data subject), storing `actor_user_id`/`actor_role` is fine; the minor appears only as `athlete_id`, which is exactly what FR-003 permits. Asserting on the *emitted rows* rather than trusting the call sites is the same technique the repo already uses for log scanning and that PHI-safe FastAPI audit middlewares recommend.

**Alternatives**: (a) hash/pseudonymise sensitive values with a per-tenant salt so correlation survives — rejected, adds key management for a capability nobody asked for; the stricter "never store the value" rule is simpler and satisfies FR-003 outright; (b) store full before/after JSON like `race_result_revisions.diff_json` — rejected for this table (FR-003); that trail is grandfathered because its diff content is non-identifying numeric race data, and its practice must not be copied here.

**Sources**: `backend/app/models/race_competitor_link_audit.py:14-16`; `backend/tests/test_privacy.py:31`; `.claude/agents/data-privacy-guard.md:17-30`; https://nxlog.co/news-and-blog/posts/gdpr-compliance; https://www.konfirmity.com/blog/gdpr-logging-and-monitoring; https://github.com/bh-healthcare/bh-fastapi-audit

### R-05 Request context: pure-ASGI `request_id` in a ContextVar, actor passed explicitly, closed actor-kind enum

**Decision**: (1) A pure-ASGI middleware (`app/services/request_context.py` + registration in `backend/app/main.py` before `CORSMiddleware`) sets a `ContextVar[str]` with a UUID4 per request (honouring an inbound `X-Request-Id` only for server-to-server callers) and echoes it as a response header; `record_audit` reads it as the default `request_id`. (2) The **actor** is passed explicitly through service signatures — never inferred from the ContextVar. (3) Non-HTTP callers generate one `request_id` per invocation and pass it explicitly, tagged with an `AuditActorKind` constant, never `person`.

> **Superseded (Phase 1)**: the enum shipped with four values, not eight — `user` / `system` / `webhook` / `cron` (`data-model.md` §2.2), with `meta_json.job` naming the specific job; the human kind is spelled `user`, not `person`, and `request_id` is `String(32)` (`uuid4().hex`, `data-model.md` §1). Recorded in `contracts/audit-recording.md` §10 point 1. The mechanism decided here is unchanged: one correlation id per logical operation in a ContextVar, the actor always passed explicitly, and a non-`user` kind for every automated writer.

**Rationale**: FR-002 and Acceptance Scenario 5 require every row of one logical operation to share a correlation reference — a per-`record_audit` UUID would fail the roster-update and batch-newsletter cases outright, and a JWT `jti` would falsely correlate a whole login session. The repo has no request-id middleware today (`backend/app/main.py:59-64` registers only `CORSMiddleware`) and the sole correlation precedent is a locally generated uuid4 threaded as a function argument (`backend/app/services/strava/ingest.py:91`) — so this is greenfield, and the constitution's Observability gate already asks for correlation IDs. The ContextVar must not be the *actor* channel because the six confirmed non-HTTP writers have no `Request` and no `current_user`: the Resend webhook (`backend/app/routers/webhooks_resend.py:112`, Svix HMAC), the Strava webhook (`backend/app/routers/strava_integration.py:376`, deferred into its own session at `:362`), the daily reconcile (`:409`, `X-Reconcile-Token`, driven by `.github/workflows/strava-reconcile.yml`), the two boot scripts in `backend/entrypoint.sh`, and `reconcile_orphan_runs()` from the lifespan (`backend/app/main.py:24-40`). The LangGraph `_on_complete` closures are the sharpest case: they open a **fresh** `AsyncSessionLocal` after the HTTP response has already been sent (`backend/app/routers/race_analysis.py:730-742`, `backend/app/routers/athlete_race_analysis.py:895-905`), so a request-scoped ContextVar is already out of scope there by the time the run finishes — those call sites must pass both actor and `request_id` explicitly.

**Alternatives**: (a) `@app.middleware("http")` / `BaseHTTPMiddleware` — rejected: it wraps every response in a `StreamingResponse`, which is a real risk for the WeasyPrint/docxtpl byte responses this very feature must audit (FR-005), and pure ASGI avoids the `call_next` indirection; (b) derive the actor from `Depends(get_current_user)` inside `record_audit` — rejected, it would silently attribute the six automated writers to a person, the exact failure Acceptance Scenario 4 forbids; (c) a module-level global instead of a ContextVar — rejected, ids would leak across concurrent requests.

**Sources**: Context7 `/websites/fastapi_tiangolo` ("manage context variables across yield dependency"; middleware reference — wrapping ASGI `send`); `backend/app/main.py:24-40,59-64`; `backend/app/services/strava/ingest.py:91`; `backend/app/routers/race_analysis.py:730-742`; `backend/app/routers/webhooks_resend.py:112`; `backend/app/routers/strava_integration.py:305-450`; `backend/entrypoint.sh`; `.github/workflows/strava-reconcile.yml`

### R-06 FR-009 coverage is enforced by three layers, not one

**Decision**: (1) **Static registry** — `app/services/audit.py::AUDITED_ROUTES: dict[tuple[str, str], AuditPolicy]` keyed by `(method, path_template)`, with an explicit, reviewed `EXEMPT(reason=…)` for the few genuinely non-club writes (token refresh, password-reset claim, RSVP-by-parent if excluded). A pytest meta-test walks `app.routes` (FastAPI exposes `route.methods`/`route.path`; no server needed) and fails when any route whose methods intersect `{POST, PUT, PATCH, DELETE}` lacks an entry — so a new mutating router cannot merge unregistered. (2) **Dynamic smoke per router** — call the endpoint against the offline aiosqlite app and assert exactly the expected number of `audit_log` rows land sharing one `request_id`. (3) **Test-only strict flush detector** (`AUDIT_STRICT=true` in the test lane, per `plan.md` Complexity Tracking) — a session-level hook that fails a test when a flush mutates an audited table without a pending `AuditLog` in the same session.

**Rationale**: The spec's edge case ("a record type is added in the future without being wired to the history: an automated check fails so the omission cannot ship unnoticed") is a *merge-time* requirement, which only the static registry satisfies. But a registry entry is a promise, not proof: the dynamic smoke tests prove the service actually calls `record_audit`, and the strict detector catches the residual case a registry cannot see — a service that mutates a *second* table without recording it. The three layers have complementary blind spots, and the constitution's human-review + compliance-statement step is the backstop against a dishonest registry entry.

**Alternatives**: (a) dynamic coverage only — rejected, protects only endpoints someone remembered to test, which is precisely the gap FR-009 exists to close; (b) a production runtime assertion that raises if a mutating request completes unaudited — kept as a possible defence-in-depth follow-up (log-only in prod), not the primary gate, since it fires after merge; (c) code-coverage tooling on the `record_audit` call site — rejected, it measures "exercised in tests", not "present in the route set".

**Sources**: Context7 `/websites/fastapi_tiangolo` (routing/`app.routes`); `backend/tests/test_privacy.py:31`; https://github.com/bh-healthcare/bh-fastapi-audit; spec FR-009 and Edge Cases

### R-07 Append-only is enforced in code and by test; the purge is the single, additive exception

**Decision**: No application path issues `UPDATE` or `DELETE` against `audit_log`. The model docstring states the rule (as `race_competitor_link_audit.py` already does), a test asserts it over a full scenario run (row count never decreases, no row's `id`/`occurred_at`/`action` ever changes), and the only removal path is the retention CLI (R-25), whose own effect is *additive*: it writes one new row (`action=purge`, `actor_kind=purge_job`, count in `diff_json`) in addition to the deletion it performs.

**Rationale**: FR-004 is a hard requirement and the two precedent tables already encode it as a docstring convention that has held. A DB-level guard is attractive but out of scope: the project's Alembic history contains **zero** `CREATE TRIGGER`, and introducing the first trigger in a trigger-free codebase for one invariant is the kind of new pattern the constitution asks to justify in writing.

**Alternatives**: (a) MySQL `BEFORE UPDATE`/`BEFORE DELETE` triggers raising via `SIGNAL`, or a dedicated DB user without `UPDATE`/`DELETE` grants on the table — both viable hardening; recorded here as a documented follow-up (they also cannot be exercised in the sqlite lane, so they would create a test-environment divergence); (b) treating the purge as an "update" of an archive table — rejected, moving rows is a second storage surface with the same retention question.

**Sources**: `backend/app/models/race_competitor_link_audit.py:11-13`; `backend/app/models/race_result_revision.py:39`; `backend/alembic/versions/` (no trigger precedent); spec FR-004/FR-030

### R-08 Spanish sentences are composed at render time, never stored

**Decision**: The backend stores machine facts only. `ClubHistoryPage` and `AthleteHistoryPanel` build the FR-008 sentence client-side from a phrase-template map keyed by `(action, entity_type)` in `frontend/src/components/audit/` — e.g. `"{actor} aprobó el informe mensual de {periodo}"` → "Ana Coach aprobó el informe mensual de marzo". Placeholders are limited to the resolved actor display name plus non-identifying context already on the row (period label, record-type label). Raw `entity_id`, `changed_fields` and `diff_json` appear only inside an expandable "Ver detalle" (`Collapsible`, the pattern established by feature 040's training-rules component). No i18n library.

> **Superseded (Phase 1)**: `contracts/audit-log-api.md` §7.1 moves the composition from the client to the response builder (`backend/app/services/audit.py::render_sentence`), so the API returns a ready-made `sentence_es` and the phrase-template map lives in Python, not in `frontend/src/components/audit/`. Reasons: the FR-003 privacy scan can then assert on the *rendered* sentence, and the `(entity_type, action)` map can be checked against the Python action catalogue by the coverage test. The invariant this entry protects — the sentence is composed at read time and **never stored** — is unchanged, as is the client-side `Collapsible` "Ver detalle".

**Rationale**: FR-008 asks for a sentence "never exposing raw identifiers or field names to the reader except in an expandable detail", and the vendor audit-log UIs converge on the same split (store `{actor, action, subject, time}`, render one short sentence). Composing at render time also keeps storage minimisation-clean (R-04): a hand-built sentence is exactly the vector by which a name could reach a stored row. A plain TypeScript template map is right-sized for a single-locale product (constitution language policy) and avoids a runtime dependency.

**Alternatives**: (a) store the rendered sentence at write time — rejected, couples storage to copy (a relabelled action cannot fix historical rows) and weakens minimisation; (b) adopt react-i18next / ICU MessageFormat now — rejected, over-engineering for one locale; noted as the upgrade path if a second language ever appears.

**Sources**: https://docs.cassidyai.com/settings/audit-logs; https://ona.com/docs/ona/audit-logs/overview; spec FR-008/FR-013; `.specify/memory/constitution.md` (III — language policy; Stack discipline)

---

## B. Archiving instead of destroying

### R-09 Athlete archive columns replace the destructive cascade in place

**Decision**: `Athlete` gains `archived_at: DateTime|None`, `archived_by_user_id: FK(users.id, ondelete="SET NULL")|None` and `archive_reason: Enum(AthleteArchiveReason)|None`. `DELETE /api/athletes/{athlete_id}` (`backend/app/routers/athletes.py:329-367`) keeps its route but its body becomes a single archiving UPDATE plus a `record_audit(action=archive, reason_code=…)`; **every child row is left untouched** and the eight `delete()` statements are removed. Restore is a dedicated admin-only action endpoint `POST /api/athletes/{athlete_id}/restore`.

> **Superseded (Phase 1)**: the columns are spelled `deleted_at` / `deleted_by_user_id` / `deleted_reason_code` (`data-model.md` §4.2, `contracts/athlete-archive.md` §0), matching the existing `race_results.deleted_at` precedent, and there is no `AthleteArchiveReason` enum: the reason values come from the shared `AuditReasonCode` catalogue (`data-model.md` §2.4, `athlete_*` and `restore_*` groups), exposed on the request body as the `AthleteArchiveReasonCode` sub-enum. "Archivar" remains the Spanish UI verb — a copy decision, not a column name. Everything else decided here stands: archive in place, keep every child row, same `DELETE` route, `POST …/restore`.

**Rationale**: The verified handler today deletes `ParentalConsent`, `AthleteAIExplanation`, `ParentInvite`, `AnthropometricRecord`, `ParentAthlete`, `ClubMember`, the `Athlete` row and the `User` stub (`backend/app/routers/athletes.py:359-366`) — destroying the very Ley-1581 consent evidence FR-014 requires the club to keep, with no record of who did it. Nothing in that cascade is forced by a foreign key; it is purely applicative, so archiving means *deleting code*, not adding a parallel path. Three FKs to `athletes.id` are `ondelete="RESTRICT"` — `backend/app/models/calendar_event.py:237`, `backend/app/models/race_event_roster.py:76`, `backend/app/models/training_session.py:183` — which is precisely why the cascade fails half-way with an opaque `IntegrityError` for any athlete with attendance, roster or event history (spec AC4). Column naming follows the two existing soft-delete precedents (`backend/app/models/race_result.py:141` `deleted_at`; `backend/app/models/athlete_ai_insight.py:205` `archived_at`), choosing the `archived_*` spelling so the column matches the Spanish UI verb ("Archivar atleta") and the spec's own vocabulary. The action-verb `POST …/restore` matches this codebase's uniform idiom for state transitions (`backend/app/routers/race_imports.py:1004` `/commit`, `backend/app/routers/training_sessions.py:429` `/execute`, `backend/app/routers/athlete_monthly_newsletters.py:1241,1278` `/approve`, `/send`, `backend/app/routers/race_analysis.py:1628` `/cancel`).

**Alternatives**: (a) a generic `status` enum column — rejected, collapses timestamp/actor/reason into one field and has no precedent here; (b) a separate `archived_athletes` table — rejected, every FK already treats `athletes` as the single source of truth; (c) keep hard delete for "empty" athletes and archive only those with history — rejected, adds a judgement call FR-014 does not make; (d) REST-purist `PATCH {"status": "active"}` for restore — rejected, no precedent for PATCH-as-action-trigger in this codebase.

**Sources**: `backend/app/routers/athletes.py:329-367`; `backend/app/models/athlete.py:42-90`; `backend/app/models/calendar_event.py:237`; `backend/app/models/race_event_roster.py:76`; `backend/app/models/training_session.py:183`; `backend/app/models/race_result.py:141`; `backend/app/models/athlete_ai_insight.py:205`; https://oneuptime.com/blog/post/2026-01-21-postgresql-soft-deletes/view; https://philsturgeon.com/restful-deletions-restorations-and-revisions

### R-10 Explicit per-site filtering through the existing choke points, proven by one integration test

**Decision**: No global loader criterion. Every active-surface query adds `Athlete.archived_at.is_(None)`, concentrated first on the two choke points that already exist — `backend/app/services/permissions.py:63-68` (`parent_athlete_ids`, imported by activities, athletes, club race insights, calendar, monthly reports, parent newsletters and training sessions) and `backend/app/routers/athletes.py:161-227` (`list_athletes`, which also backs the dashboard and the AI athlete picker through `useAthletes`) — then the remaining sites: `backend/app/services/dashboard_summary.py:84-99,145,196-200`, `backend/app/routers/parent_athletes.py:171-220,380-411`, `backend/app/routers/athlete_monthly_newsletters.py:192,242,594`, `backend/app/routers/race_analysis.py:672`. The guarantee is an integration test ("an archived athlete is absent from every active surface") enumerating those surfaces, not a lint rule.

**Rationale**: The ecosystems that do offer transparent global filters (EF Core, Ecto/TypeORM plugins) document the same failure mode: raw query builders, reports and admin tools silently bypass the filter — which here would mean an archived minor reappearing in a family newsletter. And an invisible filter is the wrong default anyway for this feature, because FR-014 explicitly requires administrators to still *see* archived athletes and their evidence, so any global criterion would need selective bypassing at exactly the sensitive sites. Concentrating on the two shared choke points means most surfaces are fixed once.

**Alternatives**: (a) SQLAlchemy `with_loader_criteria` event listener — rejected as above (invisible to reviewers, bypassed by Core statements, must be disabled for the admin archive view); (b) a repo-wide grep/AST rule that fails CI when a `select(Athlete)` omits the filter — rejected as the *guarantee*: it is brittle against joins and subqueries, and duplicates intent with FR-009's registry check while proving less than a behavioural test; it may still be added later as a cheap lint, but the surface-enumeration test is what closes the requirement.

**Sources**: `backend/app/services/permissions.py:63-68`; `backend/app/routers/athletes.py:161-227`; `backend/app/services/dashboard_summary.py:84-200`; `backend/app/routers/parent_athletes.py:171-220`; `frontend/src/components/ai/AthleteCombobox.tsx:1-34`; https://barretblake.dev/posts/development/2026/03/ef-core-global-query-filters; https://codewithmukesh.com/blog/soft-deletes-efcore

### R-11 Roster shrink archives the entries that carry data; attendance gains attribution

**Decision**: `bulk_upsert_convocatoria` (`backend/app/services/training/attendance.py:15-65`) stops issuing an unconditional `delete(SessionAttendance)` for `to_remove` (`:40-45`). Rows carrying any coach-entered data (`rpe_omni`, `rubric_effort`, `rubric_attitude`, `rubric_technique`, `individual_feedback` non-null) are archived (`archived_at`, `archived_by_user_id`) and excluded from active reads; untouched `AUSENTE` placeholders may still be hard-deleted. `SessionAttendance` also gains `recorded_by_user_id`, `last_edited_by_user_id`, `last_edited_at` (FR-011), set in `update_attendance` (`:68-99`), which today is a bare `setattr` loop with no author fields on the model (`backend/app/models/training_session.py:153-216` — confirmed: `status`, `excuse_reason`, `rpe_omni`, `rubric_*`, `individual_feedback`, `created_at`, `updated_at`, nothing else).

**Rationale**: FR-016 targets exactly this delete; AC5 scopes it to entries where "ratings or feedback were entered", so the conditional keeps the table from filling with archived placeholders while preserving every entry that documents a minor. FR-011's "recorded by / last edited by" pair has a working precedent to copy in `session_media.uploaded_by_user_id`, set from the router at `backend/app/routers/training_sessions.py:913`.

**Alternatives**: archive every removed row unconditionally — rejected as noise with no requirement behind it; keep hard delete and rely on the audit entry alone — rejected, the audit row stores no feedback text (R-04), so the evidence AC5 asks an admin to read would be gone.

**Sources**: `backend/app/services/training/attendance.py:15-99`; `backend/app/models/training_session.py:153-216`; `backend/app/routers/training_sessions.py:913`; spec FR-011/FR-016

### R-12 Unique constraints under soft-delete need MySQL's generated-column trick — and none is required by this feature

**Decision**: Where a natural-key `UniqueConstraint` must ignore archived rows, use a stored generated column (`active_key GENERATED ALWAYS AS (IF(archived_at IS NULL, <expr>, NULL)) STORED` + `UNIQUE`), exploiting MySQL's multiple-NULLs-allowed unique index. For 041 as scoped this is **not** needed: `athletes` has no natural-key uniqueness that archiving would collide with, and club memberships are still hard-removed. Recorded so the data-model does not invent a Postgres-style partial index.

**Rationale**: MySQL 8.4 has no partial/filtered index syntax, so the `CREATE UNIQUE INDEX … WHERE deleted_at IS NULL` recipe most soft-delete tutorials show is not portable here. The repo already contains one latent instance of the trap: `backend/app/models/race_result.py:84-87` declares `UniqueConstraint("event_id", "category_id", "competitor_id")` that does **not** account for `deleted_at` (`:141`), so a soft-deleted result plus a re-import of the same rider/event/category would violate it. That is pre-existing and out of scope for 041 — cited only as the cautionary precedent.

**Alternatives**: (a) add `archived_at` into the constraint tuple — rejected, MySQL treats each distinct non-NULL timestamp as distinct, so it permits duplicate archived rows and only appears to fix the problem; (b) application-level uniqueness only — rejected, inconsistent with the schema's DB-level convention and race-prone under two concurrent coaches.

**Sources**: `backend/app/models/race_result.py:84-87,141`; https://www.phparch.com/2026/02/advanced-unique-index-patterns-for-soft-deletes-mysql-and-postgresql; https://sqlfordevs.com/unique-index-ignore-some-rows

---

## C. Optimistic concurrency on the newsletter draft

### R-13 Integer `edit_version`, not `content_version` and not `updated_at`

**Decision**: `AthleteMonthlyNewsletter` gains `edit_version: int` (`Integer, nullable=False, server_default="1"`). Every accepted mutation bumps it in the same UPDATE, guarded by `WHERE id = :id AND edit_version = :expected` (0 rows affected ⇒ conflict). The value is exposed as a weak ETag on the read (`ETag: W/"<edit_version>"`) and required as `If-Match` on the studio PATCH. Scope is deliberately narrow: **only** the newsletter draft PATCH (`backend/app/routers/athlete_monthly_newsletters.py:1001-1089`), which is the single documented two-coach race in the spec.

**Rationale**: Three name candidates were on the table and two are disqualified by evidence. `content_version` is a **retired column name in this exact table**: feature 038 added it as the v1/v2 template discriminator and migration `backend/alembic/versions/8b5ac1f24f61_drop_newsletter_content_version.py` dropped it, with `backend/tests/models/test_newsletter_stage_log_migration.py:108-110` asserting `"content_version" not in cols`. Reusing that name weeks later for an unrelated optimistic-lock semantic would mislead every reader who remembers the 038 meaning and would collide with the 038 test vocabulary — hence `plan.md`'s "the retired `content_version` name is not reused". `updated_at` (which does exist, `backend/app/models/athlete_newsletter.py:153`, with `onupdate`) was the cheapest token but is a `DATETIME` with `fsp=0` on MySQL (see R-02), so two saves inside the same second are indistinguishable — the very scenario US5 is about. A monotonic integer answers "has anyone saved since I loaded?" atomically in one statement, needs no canonicalisation, and is what the API-guideline sources recommend ("the ETag MAY be implemented as a version number… refreshed after each modification").

**Alternatives**: (a) content-hash ETag over canonical JSON — rejected, fragile canonicalisation over JSON columns (`stage_overrides`, `hidden_blocks`) that changed shape across features 037/038, with no behavioural gain; (b) `updated_at` / `If-Unmodified-Since` — rejected as above (fsp=0); (c) extend the guard to race-result coach notes and monthly-report regeneration in the same pass — rejected as premature generalisation (constitution rule of three): those already have their own trails and no observed concurrent-edit case; easy to add per entity once the newsletter proves the pattern.

**Sources**: `backend/alembic/versions/8b5ac1f24f61_drop_newsletter_content_version.py`; `backend/tests/models/test_newsletter_stage_log_migration.py:108-110`; `specs/038-newsletter-bitacora-redesign/data-model.md:113`; `backend/app/models/athlete_newsletter.py:148-158`; `backend/app/routers/athlete_monthly_newsletters.py:1001-1089`; https://docs.ed-fi.org/reference/data-exchange/api-guidelines/design-and-implementation-guidelines/api-implementation-guidelines/handling-optimistic-concurrency-with-etags

### R-14 Stale precondition → 409; missing precondition → 428; 412 deliberately not used

**Decision**: A PATCH whose `If-Match` does not match the current `edit_version` is refused with **409 Conflict** and a Spanish body ("Otro entrenador guardó cambios en este boletín. Recarga para ver la última versión."). A PATCH that omits `If-Match` on the guarded endpoint is refused with **428 Precondition Required**, so "forgot the header" fails loudly instead of silently reverting to last-write-wins. **412** is not used.

**Rationale**: RFC 9110 does make 412 the literal code for a failed client-declared precondition, and that reading is correct in the abstract. It is not adopted here for three concrete reasons: (1) `plan.md` and the contract file already fix the wire status at 409; (2) 409 is this codebase's uniform conflict idiom — `backend/app/routers/athlete_monthly_newsletters.py` alone raises `HTTP_409_CONFLICT` at six sites, plus `backend/app/routers/calendar.py:437`, `backend/app/routers/clubs.py:41,154`, `backend/app/routers/intervals.py:806`, `backend/app/routers/athlete_race_analysis.py:763,792` — and the frontend already branches on `e.response?.status === 409` in `frontend/src/components/competitions/import/ImportWizard.tsx:232`; (3) the client needs exactly one "stale, reload" branch, and splitting it across 409/412 would buy no different UI while adding a status the existing error helper does not recognise. The one distinction worth keeping is the *missing-header* case, which is a client bug rather than a data race — hence 428 (400 is the documented fallback if wiring 428 proves awkward).

**Alternatives**: (a) 412 for stale + 428 for missing (RFC-purist) — rejected as above; recorded because it is the correct reading of RFC 9110 §13.1.2 and should be revisited if a second, non-newsletter guarded endpoint ever needs to distinguish "precondition failed" from "business-state conflict"; (b) allow a missing `If-Match` to pass through — rejected, reintroduces the exact bug US5 exists to fix; (c) carry the token as a body field (`expected_version`) instead of headers — kept as the documented fallback if the CORS work in R-15 proves disruptive; the same 409/428 semantics would apply.

**Sources**: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/412; https://pulsetic.com/errors/409-conflict; Context7 `/websites/fastapi_tiangolo` (`HTTPException` custom headers; `Response` parameter for dynamic response headers); `backend/app/routers/athlete_monthly_newsletters.py` (six 409 sites); `frontend/src/components/competitions/import/ImportWizard.tsx:217-243`

### R-15 CORS must expose `ETag` and accept `If-Match` — a dead ETag path already proves it

**Decision**: In `backend/app/main.py:59-64`, add `"If-Match"` to `allow_headers` (currently `["Authorization", "Content-Type", "Accept"]`) and add `expose_headers=["ETag"]` (currently unset, so Starlette defaults to `[]`). A regression test asserts the browser-side client can actually read `response.headers.get("etag")` and round-trip it.

**Rationale**: This is not hypothetical. The backend already emits an `ETag` for race-run status polling and the frontend API layer already accepts an `etag` option and sends `If-None-Match` (`frontend/src/api/raceAnalysis.ts:44,47`), yet **no caller ever passes it** — `useRaceRun` calls `getRunStatus(runId, since, { signal })` with no etag. The most plausible cause is exactly this: without `expose_headers`, browser JS cannot read a non-simple response header, so the capability was built and silently never used. Shipping 041's If-Match without fixing CORS would repeat the same class of failure, and it would degrade *silently* to no conflict detection — the worst possible outcome for FR-027.

**Alternatives**: skip headers and use a body field (R-14 alternative c) — viable, and the safer choice if exposing `ETag` turns out to affect other endpoints; either way the CORS gap is worth fixing on its own merits since it currently makes an existing feature dead code.

**Sources**: `backend/app/main.py:59-64`; `backend/app/routers/race_analysis.py:779-814`; `frontend/src/api/raceAnalysis.ts:36-58`; `frontend/src/hooks/ai/useRaceRun.ts:282`

### R-16 TanStack Query: blocking conflict dialog, never an automatic retry or refetch

**Decision**: The studio mutation's `onError` inspects `error.response?.status`; on 409 it sets a `conflict` state that renders a blocking `AlertDialog` ("Otro entrenador guardó cambios…") with a single "Recargar" action. Only that explicit action calls `queryClient.invalidateQueries({ queryKey: ["newsletter", athleteId, period] })` and refetches, which is also what discards the coach's unsaved diff — FR-027 is satisfied by *refusing* the save, not by merging. `useMutation` sets `retry: (count, error) => ![409, 412, 428].includes(error.response?.status)` so the library never re-POSTs a stale precondition.

**Rationale**: TanStack Query has no optimistic-concurrency primitive; this is an application pattern its own docs sketch (`onError` + `invalidateQueries`), and its retry guidance is explicitly for transient classes (408/504), never conflicts — retrying with the same stale `If-Match` fails identically forever. A blocking dialog rather than a toast is required because the spec asks for "a conflict message and a reload action". Optimistic updates (`onMutate` + rollback) are wrong here for a human reason: they show the coach their edit as saved, and a rollback flash on a whole draft another human is co-editing is exactly the "did my work survive?" ambiguity US5 exists to remove.

**Alternatives**: (a) auto-invalidate on 409 without user action — rejected, silently discards the coach's typing; (b) optimistic update with rollback — rejected as above; (c) three-way field merge — rejected, the backend replaces `stage_overrides` wholesale today (documented in `frontend/src/routes/training/AthleteNewsletterStudioPage.tsx:20`), so merging would be a far bigger behavioural change than the spec asks for.

**Sources**: Context7 `/tanstack/query` (mutations guide; query retries; `invalidateQueries` on mutation success); `frontend/src/hooks/training/useUpdateStageLog.ts:1-43`; `frontend/src/routes/training/AthleteNewsletterStudioPage.tsx:20,126-172`; spec US5/FR-027

---

## D. Co-coached sessions

### R-17 Bridge table `training_session_coaches`, backfilled from the creator

**Decision**: New junction table `training_session_coaches (session_id FK→training_sessions.id ondelete=CASCADE, user_id FK→users.id ondelete=RESTRICT, added_at, added_by_user_id)` with `UniqueConstraint("session_id", "user_id")` and an index on `user_id`. `training_sessions.created_by_user_id` stays as "who created it"; the bridge answers "who leads it" (a distinct concept, per US4). The migration backfills one row per existing session from `created_by_user_id` (spec Assumption).

**Rationale**: `TrainingSession` has no multi-coach concept today (`backend/app/models/training_session.py:60-150` — a single `created_by_user_id` with `ondelete="RESTRICT"`), and every other N:M relation in this schema is a proper junction table (`ParentAthlete` at `backend/app/models/athlete.py:140-165`, `ClubMember` at `backend/app/models/club.py:48-73`). A bridge is also the only shape that can be indexed for FR-026's "sessions where coach X leads", and it carries `added_at`/`added_by_user_id` provenance.

**Alternatives**: a JSON `coach_ids` array column on `training_sessions` — rejected, inconsistent with every relationship in this schema, unindexable for the coach filter without a generated-column workaround, and it loses provenance.

**Sources**: `backend/app/models/training_session.py:60-150`; `backend/app/models/athlete.py:140-165`; `backend/app/models/club.py:48-73`; spec FR-024/FR-026 and Assumptions

### R-18 "At least one coach" is a service-layer invariant with a locking read

**Decision**: Enforce the minimum in the service layer inside the same transaction as the removal: `SELECT COUNT(*) … WHERE session_id = :id FOR UPDATE`, refuse with 409 when the count would reach 0. No `CHECK` constraint, no trigger.

**Rationale**: MySQL 8.4 `CHECK` constraints validate a single row's own columns; "at least one row per `session_id`" is structurally inexpressible. The only DB-level option is a trigger, and this codebase has no trigger precedent (see R-07). The `FOR UPDATE` read is what closes the real race — two coaches each removing a different "last but one" coach simultaneously — which a plain count would not.

**Alternatives**: a `BEFORE DELETE` trigger raising via `SIGNAL` — technically correct and more defensive, rejected as the first trigger in a trigger-free codebase without a second use case; revisit if the app-layer check proves insufficient under real load.

**Sources**: https://dev.mysql.com/doc/refman/8.2/en/create-table-check-constraints.html; https://stackoverflow.com/questions/59559480/mysql-possible-to-add-constraint-that-prevents-a-one-to-many-relation-from-havi; `backend/alembic/versions/` (no `CREATE TRIGGER`)

### R-19 The acting coach is threaded into the services; two distinct names in the templates; two distinct counting rules

**Decision**: (1) `update_session`, `execute_session`, `cancel_session` and `update_convocatoria` (`backend/app/services/training/sessions.py:661-843`) take the acting `User` explicitly, and the notification helpers stop calling `_load_session_coach` (`:853-864`) to name the sender. (2) The three family templates gain a second variable: `coach_names` (the session coaches, FR-025 "lists the session coaches") **and** `acting_coach_name` (the coach who performed the change) — today all three carry only `{{ coach_name }}` (`backend/templates/email/training_session_invite.html:17,81`; `training_session_updated.html:18,109`; `training_session_cancelled.html:17,74`). (3) Counting for FR-032/SC-008: club-wide totals use `COUNT(DISTINCT training_sessions.id)` after joining the bridge; per-coach totals use a plain filtered count, so a co-coached session legitimately counts once for each of its coaches.

**Rationale**: `_load_session_coach` unconditionally selects `User` by `session.created_by_user_id` and is the coach passed into `_notify_parents_update` (`:715`), `_notify_parents_cancel` (`:787`) and the convocatoria growth notification (`:839`) — so today a cancellation by coach B tells families coach A cancelled it, the exact bug US4 names. Every router call site already has `current_user` in scope; the precedent for threading it down is `session_media.uploaded_by_user_id` (`backend/app/routers/training_sessions.py:913`). Two template variables are required because "who leads" and "who acted" are different facts and the spec's own example names only the actor ("El entrenador B ha cancelado…"). The DISTINCT/plain split is the standard join fan-out remedy and is exactly how SC-008 defines reconciliation ("sum of per-coach sessions counted once per session equals the club's session count").

**Alternatives**: (a) reuse `coach_name` as a comma-joined list and drop the acting-coach sentence — rejected, contradicts FR-025 and AC2; (b) derive "who acted" at render time from the audit log — rejected, the email is dispatched synchronously inside the same request, long before any audit read API exists; (c) pre-aggregate with a CTE before the join — a fine implementation detail for wide date ranges, orthogonal to the DISTINCT decision.

**Sources**: `backend/app/services/training/sessions.py:661-864`; `backend/app/routers/training_sessions.py:386-517,913`; `backend/templates/email/training_session_{invite,updated,cancelled}.html`; spec US4/FR-025, SC-008; https://www.varsitytutors.com/practice/subjects/sql/lessons/join-duplication-issues

---

## E. Staff administration

### R-20 The club-required check moves from "who is calling" to "what is being created"

**Decision**: In `create_user` (`backend/app/routers/users.py:36-133`), require `club_id` whenever `body.role == UserRole.coach`, independently of the caller's role, and create the `ClubMember` row in the same operation (FR-019). Additionally, `add_member` (`backend/app/routers/clubs.py:114-158`) must reject a `role_in_club` that contradicts the target account's `User.role`, reusing the `role_in_club_map` already defined inline in `create_user` (`backend/app/routers/users.py:112-117`), extracted to a shared helper (FR-022).

**Rationale**: Verified: the club-required validation lives inside `if current_user.role == UserRole.coach:` (`backend/app/routers/users.py:53-59`), so when an **admin** creates a **coach**, `body.club_id` is optional and the membership block (`:109-131`, guarded by `if body.club_id is not None`) is skipped entirely — the new coach signs in with no membership and every club-scoped list returns empty. This is the spec's readiness-audit bug, and a currently-green test encodes it: `backend/tests/test_users.py:31-58` (`test_admin_creates_coach`) posts a coach with no `club_id` and asserts 201. The fix and that test's update must land together, with a regression test for the refusal. `add_member` today only checks `is_active` (`backend/app/routers/clubs.py:132-137`), never role coherence, so a parent-role user can be added with `role_in_club=coach`.

**Alternatives**: (a) enforce at the Pydantic layer on `UserCreate` — cleaner in isolation, but the rule depends on both `body.role` and (for the club-membership check) the caller's clubs, so the router-level branch is the minimal correct diff; (b) a DB-level cross-table CHECK for role coherence — rejected, not portable on MySQL and against this project's app-level-validation convention.

**Sources**: `backend/app/routers/users.py:36-133`; `backend/app/routers/clubs.py:114-158`; `backend/app/schemas/club.py:32-42`; `backend/tests/test_users.py:31-58,194-230`

### R-21 Deactivation reuses the existing PATCH; the delete refusal already exists and only needs better copy

**Decision**: Deactivate/reactivate = `PATCH /api/users/{user_id}` with `{"is_active": …}` — no new action endpoint. `DELETE /api/users/{user_id}` keeps its existing unconditional refusal for admin/coach targets; only the message changes to point at deactivation (FR-018: "refused with guidance to deactivate"). The parent-delete path must stop clearing attribution.

**Rationale**: The machinery exists and is already guarded: `UserUpdate.is_active` (`backend/app/schemas/user.py:25-29`), `update_user` blocks a coach from editing a peer coach/admin and blocks self-deactivation (`backend/app/routers/users.py:223-273`), and login already refuses with `"Usuario desactivado"` (`backend/app/routers/auth.py:68-71`) — the exact message US3 AC6 says to reuse. `delete_user` already raises 403 for `target.role in (admin, coach)` **unconditionally** (`backend/app/routers/users.py:317-321`), i.e. stricter than FR-018's "with recorded activity" wording; keeping the simpler unconditional rule avoids an expensive cross-table "is this user referenced anywhere" scan for a case no acceptance scenario asks for, and `ondelete="RESTRICT"` on `created_by_user_id` (`backend/app/models/race_result.py:151-153`, `backend/app/models/training_session.py:76-78`) would block it at the DB layer anyway. The one genuine defect on that path is the parent cascade: `backend/app/routers/users.py:333-346` sets `User.created_by = NULL` for rows the deleted parent created — the literal side effect US2 AC7 forbids.

**Alternatives**: (a) new `POST /users/{id}/deactivate` + `/reactivate` action endpoints (matching the archive/restore verb idiom of R-09) — rejected here specifically because, unlike archive/restore, a tested, role-guarded PATCH path already exists; parallel endpoints would be duplication; (b) implement "deletable only if no recorded activity" — rejected, no scenario requires it and it reintroduces the fragile manual-cascade thinking this feature removes.

**Sources**: `backend/app/routers/users.py:223-347`; `backend/app/schemas/user.py:25-29`; `backend/app/routers/auth.py:68-71`; `backend/app/models/race_result.py:151-153`; `backend/app/models/training_session.py:76-78`

### R-22 The set-password email reuses the password-reset token, with one guard to relax

**Decision**: On staff creation the API does **not** accept a password. It creates the account with an unusable placeholder hash and issues the existing reset flow (`backend/app/services/password_reset.py::request_reset` + the `PASSWORD_RESET` template), so the coach receives the standard "set your password" link (FR-023). The one adaptation: `request_reset` early-returns without sending when `not user.hashed_password` (`backend/app/services/password_reset.py:76-83`), so either the placeholder hash or an explicit `allow_unset_password` branch is required. `UserOut` (`backend/app/schemas/user.py:32-43`) additionally gains `created_by` with the creator's resolved display name, and `list_users` (`backend/app/routers/users.py:140-217`) gains an `is_active` filter (FR-020).

**Rationale**: `create_user` sends no email at all today and *requires* a cleartext `password` in the body for `role=coach` (`backend/app/routers/users.py:67-73`) — directly contradicting FR-023. Every needed piece already exists (token issuance, template, `frontend_base_url + /restablecer-contrasena?token=…` at `password_reset.py:116`); no `welcome_coach` template exists in `template_registry.py` and none is needed. `User.created_by` is already populated (`backend/app/routers/users.py:97`) but never surfaced — so FR-020 is a schema/endpoint gap, not a data-model gap.

**Alternatives**: (a) a separate `welcome_coach` template with its own token mechanism — rejected, duplicates the token machinery for a subject-line difference; if different copy is wanted, it is a template-context variant on the same flow; (b) generate a random password server-side and email it — rejected outright by FR-023 ("no password is ever shown or sent in clear").

**Sources**: `backend/app/routers/users.py:36-134,140-217`; `backend/app/services/password_reset.py:57-118`; `backend/app/schemas/notification.py:17-41`; `backend/app/schemas/user.py:32-43`

---

## F. One scope rule for AI runs and imports; spend per coach

### R-23 Replace creator-lock with club scope, and persist who decided

**Decision**: `_ensure_run_owner` (`backend/app/routers/race_analysis.py:542-550`) and the ownership branch of the import loader (`backend/app/routers/race_imports.py:714-720`) become club-scoped checks built on the existing `permissions.coach_club_ids()` (`backend/app/services/permissions.py:71`), resolving the record's club (run → `agent_runs.athlete_id` → `athletes.club_id`; parse → series/event → club). Cross-club coaches and parents keep getting 403. Separately, the HITL decision event must persist the deciding user: `submit_hitl_decision` today threads `by_user_id` into the in-memory `resume_value` but the persisted `payload_json` INSERT stores only `decision`, `step_id`, `has_edits` (`backend/app/routers/race_analysis.py:895-947`), so "who decided" (FR-028) is currently unrecoverable.

**Rationale**: Verified verbatim — `_ensure_run_owner` is `if user.role == admin: return; if run["requested_by_user_id"] != user.id: raise 403`, with no club awareness, and it gates seven endpoints (status, HITL decision, result, PDF, invalidate, cancel, re-execute). The import loader's own comment already names the behaviour ("ownership cross-coach"), i.e. it was a deliberate single-owner decision that the spec now reverses. Note `agent_run_events` has **no ORM model** (`backend/app/models/agent_run.py` maps only `AgentRun`); it is written by raw `text()` INSERTs in the routers, so the audit hook for run actions must be added at those same call sites rather than via any ORM path (consistent with R-03). `RaceImport` carries no `club_id`, so the club must be resolved through `series_id` — a denormalised `club_id` is worth weighing in `data-model.md`.

**Alternatives**: (a) keep owner-only plus an explicit "transfer ownership" action — rejected, US6's independent test expects coach B to just open and act; (b) log only `requested_by` and skip the decision actor — rejected, contradicts AC1 ("the decision records coach B").

**Sources**: `backend/app/routers/race_analysis.py:542-550,895-947`; `backend/app/routers/race_imports.py:710-722`; `backend/app/services/permissions.py:71`; `backend/app/models/agent_run.py`; `backend/tests/routers/test_race_imports.py:691-748`

### R-24 Spend per coach needs no new column, and the budget message needs new words

**Decision**: `GET /admin/ai-usage` gains a `by_coach` breakdown by joining `athlete_ai_insights.agent_run_id → agent_runs.requested_by_user_id → users`, alongside the existing total, and its RBAC widens from admin-only to admin **or** coach (FR-029 says "an administrator or coach views it"). The 503 refusal text changes to state the trailing-30-day window explicitly and that in-flight runs finish. The budget itself stays a single club-wide limit (spec Assumption).

**Rationale**: The actor columns already exist (`athlete_ai_insight.generated_by_user_id`; `agent_runs.requested_by_user_id`), so this is a `GROUP BY` next to the existing `by_prompt_version` aggregation — zero migration. The endpoint is gated `_admin: User = Depends(_admin_only)` today (`backend/app/routers/race_analysis.py:1315-1325`, `_admin_only = require_role([UserRole.admin])` at `:122`) and has **no frontend consumer at all** (no api wrapper, no hook, no page reads it — `AIHealthPage.tsx` shows provider/model/enabled, not spend), so FR-029's "AI administration page" is a new page, not a tweak — worth flagging in task sizing. The refusal wording says "Presupuesto mensual" although the window is a trailing 30 days, and never mentions in-flight runs (`backend/app/services/race/ai/budget_guard.py`); the overrun email remains a documented TODO, matching the spec's Assumption exactly.

**Alternatives**: denormalise `cost_usd`/`requested_by_user_id` onto `athlete_ai_insights` — rejected, `backend/app/models/agent_run.py`'s own docstring already argues for keeping that surface small, and the FK join is free of write-time coupling; partition the budget per coach — explicitly out of scope per the spec.

**Sources**: `backend/app/routers/race_analysis.py:122,1310-1400`; `backend/app/services/race/ai/budget_guard.py`; `backend/app/models/athlete_ai_insight.py:145-164`; `backend/app/models/agent_run.py:90-131`; `frontend/src/routes/admin/AIHealthPage.tsx`

---

## G. Retention and purge

### R-25 Typer CLI, dry-run by default, one shared cutoff, self-audited

**Decision**: `backend/scripts/retention_audit_log.py` — a Typer app mirroring `backend/scripts/retention_ai_insights.py`: `--days` (default 730) and `--apply` (default `False`, so **dry-run is what happens when you type nothing**), timestamped `_emit()` lines for cron-log grepping, a per-`entity_type` breakdown printed before any mutation, `typer.Exit` codes (0 ok / 1 error). The preview and the deletion share **one pre-computed cutoff timestamp** rather than each calling `now()`. The purge writes exactly one new `audit_log` row (`action=purge`, `actor_kind=purge_job`, count in `diff_json`) — the single permitted, additive exception to R-07. Any in-app preview surface for US8 calls the same service function (`app/services/retention.py`) and is restricted to administrators.

> **Superseded (Phase 1)**: `contracts/retention-purge.md` §0 states the horizon in the same unit as FR-030 and `data-model.md` §1.3 — the flag is `--months` with default `24`, not `--days 730` (730 days is not 24 calendar months) — and the purge row's `actor_kind` is `system` by default, `cron` when the scheduled workflow passes `--actor-kind cron`; `purge_job` is not a member of the four-value enum (`data-model.md` §2.2). The purge also writes one row **per distinct `club_id`** in the deleted set, which is exactly one row on today's single-club deployment. Dry-run-by-default via `--apply`, the single shared cutoff and the additive self-audit are unchanged.

**Rationale**: `retention_ai_insights.py` is a near-exact precedent (Typer app at `:55`, `_emit` at `:62-65`, `--days`/`--apply` options at `:130-144`, per-entity breakdown before the action). Its flag polarity is the important detail: safety comes from *dry-run being the default*, not from remembering to type `--dry-run`. GDPR/ICO guidance separates "low-risk data → automated deletion" from higher-risk data that warrants review before deletion, and explicitly asks for particular care where children's data is involved — which is why the spec's preview-then-confirm shape (FR-030) is right here rather than silent automation. Sharing the cutoff prevents rows crossing the boundary between preview and confirmation and producing a count the admin never approved.

**Alternatives**: (a) a `--dry-run` flag with destructive default — rejected, inverts the safe default and contradicts the repo precedent; (b) automatic scheduled deletion with no preview — rejected by FR-030; (c) an in-process scheduler/worker — impossible on the free tier (no persistent workers), the same constraint documented for the AI-budget email.

**Sources**: `backend/scripts/retention_ai_insights.py:52-161`; spec US8/FR-030; https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/individual-rights/individual-rights/right-to-erasure; https://www.cookieyes.com/blog/gdpr-logging-and-monitoring

### R-26 Monthly scheduling from GitHub Actions, mirroring `strava-reconcile.yml`

**Decision**: `.github/workflows/audit-retention.yml` — `on: schedule` (monthly cron) + `workflow_dispatch`, running the preview by default and leaving `--apply` to a manual dispatch input, so the count is visible in the run log before anyone confirms. If the purge is exposed over HTTP instead of via a shell on the host, it follows the existing shape: one `curl -X POST` with a shared-secret header, `--max-time`/`--retry`, a 10-minute job timeout.

**Rationale**: `.github/workflows/strava-reconcile.yml` is the project's only "hit prod on a schedule" precedent and already encodes every needed element (daily cron + `workflow_dispatch`, `X-Reconcile-Token` secret, `--max-time 300 --retry 2`, `timeout-minutes: 10`). Reusing it keeps one operational pattern and gives the admin a visible run log, which manual shell invocation would not.

**Alternatives**: CLI-only, run by hand — simpler (no new secret or endpoint to secure) but loses the "one click, visible log" operability; recorded as the acceptable fallback if exposing a purge endpoint is judged too risky.

**Sources**: `.github/workflows/strava-reconcile.yml:1-25`; spec FR-030

---

## H. Logging and request-id under uvicorn

### R-27 `app.*` INFO logs are currently dropped; add `dictConfig` alongside the request-id middleware

**Decision**: Call `logging.config.dictConfig(...)` at the top of `backend/app/main.py` (before the `FastAPI()` instantiation) configuring the root (or an `"app"` logger with `propagate: True`) with a `StreamHandler` at INFO, reusing `uvicorn.logging.DefaultFormatter` for consistent console output, `disable_existing_loggers: False`, and a filter that injects the `request_id` from R-05's ContextVar. Never log request/response bodies.

**Rationale**: Verified: nothing in `backend/app` ever calls `dictConfig`/`basicConfig`, and `backend/entrypoint.sh` runs a bare `uvicorn app.main:app` with no `--log-config`. Uvicorn's default `LOGGING_CONFIG` defines handlers and levels only for `uvicorn`, `uvicorn.error` and `uvicorn.access`, each with `propagate: False`; it never touches root. So `app.*` loggers resolve their effective level up to root (`WARNING`, no handler) — meaning every `logger.info(...)` across `app/services/**` is silently discarded in production, while `logger.error`/`logger.exception` surface only through Python's `lastResort` handler with no timestamp and no formatting. That is a real, observable inconsistency and it matters here because the audit feature's operational story (correlating a support question to a request) depends on business logs existing at all.

**Alternatives**: (a) `--log-config` file passed to the uvicorn CLI — a second artifact to maintain outside `app/main.py`; (b) `logging.basicConfig(...)` — a one-liner, but it is a no-op once root already has handlers, and the import ordering between `app.main` and uvicorn's own `configure_logging()` is easy to get backwards; `dictConfig` with an explicit `root`/`app` entry is order-robust; (c) set levels per module — does not add the missing handler. Risk: a malformed `dictConfig` that omits `disable_existing_loggers: False` can silence *all* logs including `uvicorn.access` — test in a non-production environment first.

**Sources**: Context7 `/kludex/uvicorn` (default `LOGGING_CONFIG`; programmatic `dictConfig`); `backend/app/main.py` (no `dictConfig`); `backend/entrypoint.sh`; `.specify/memory/constitution.md` (Observability — correlation IDs, no PII in logs)

---

## I. Frontend surfaces

### R-28 Plain shadcn `Table` with server-side filters — `@tanstack/react-table` is not added

**Decision**: `ClubHistoryPage`, `StaffPage` and `CoachActivityPage` render the installed shadcn `Table` primitive with a `.map()` over rows the query already paginated server-side (`offset`/`limit`, bounded default page size, mirroring `backend/app/routers/activities.py:123-167`), with filter controls above the table and a small Prev/Next + "Página N de M" control — the same shape as `AthletesTable`/`AthletesListPage` and the filter panel of `ActivityReviewPage` (`frontend/src/routes/activities/ActivityReviewPage.tsx:107-334`), preferring the shared `EmptyState`/`ErrorState` components over that page's inline blocks. Hooks follow the existing filtered-list convention: `useQuery({ queryKey: [domain, "list", filters], queryFn, placeholderData: keepPreviousData, enabled: !!accessToken })` (`frontend/src/hooks/race/useUnlinkedCompetitors.ts:42-56`).

**Rationale**: `@tanstack/react-table` is not a dependency (`frontend/package.json` has no `react-table` entry), so adopting it needs the constitution's written justification — for one club, three staff members and pages of ≤50 server-filtered rows it buys nothing over the existing pattern. Note also that shadcn's currently published Data Table example targets react-table v9's new `tableFeatures()`/`useTable()` API from the `base`/`v4` registry, while `frontend/components.json` is on the default `new-york` (Radix) registry with no `registries` block — so the documented example is not even installable without a registry migration. `keepPreviousData` avoids a flash-to-empty on every filter change, which matters on the cold-start/3G profile the constitution targets.

**Alternatives**: react-table v8 (`useReactTable`) — a new dependency with no functional gain at this scale; react-table v9 — additionally requires a registry migration and is the least battle-tested; cursor pagination — rejected, offset/limit composes with arbitrary filters and is what every existing paginated endpoint uses (cursors are used only for the append-only race-run event stream).

**Sources**: Context7 `/shadcn-ui/ui` ("Configure Table Features", data-table docs); `frontend/components.json`; `frontend/package.json`; `frontend/src/routes/athletes/AthletesListPage.tsx:59-158`; `frontend/src/routes/activities/ActivityReviewPage.tsx:107-334`; `frontend/src/hooks/race/useUnlinkedCompetitors.ts:42-56`; Context7 `/tanstack/query` (`placeholderData`/`keepPreviousData`, query keys)

### R-29 Person pickers use the installed Radix `Select`; no Combobox is added

**Decision**: The actor filter on the club history, the coach picker on the per-coach view and the co-coach field in the session wizard (`SessionCoachesField`) use the installed `ui/select.tsx` (the pattern of `frontend/src/components/calendar/AudienceSelector.tsx`), or a plain styled `<select>` where the form layout makes Radix composition awkward. The **athlete** filter reuses the existing accessible `AthleteCombobox` (`frontend/src/components/ai/AthleteCombobox.tsx`), which already implements `role="combobox"` + `aria-expanded`/`aria-controls`/`aria-activedescendant` and diacritic-insensitive search. Modal surfaces: the staff-creation form is a `Sheet` with a mandatory (possibly `sr-only`) `SheetTitle`; the newsletter conflict prompt is an `AlertDialog` (not `Dialog`), because it must not dismiss on overlay click.

**Rationale**: No `cmdk` package and no `command.tsx` exist, and shadcn's Combobox examples come from the `aria`/`base` registries this project does not use — so a searchable combobox would be a new dependency plus a registry migration to choose among ≤3 coaches. `Dialog`/`Sheet` both wrap Radix `DialogPrimitive.Content`, which already provides the focus trap, Escape dismissal and scroll lock the constitution requires, at zero extra code.

**Alternatives**: shadcn Combobox for the coach picker — unjustified at this cardinality; a bespoke picker — duplicates `AthleteCombobox` for no gain.

**Sources**: Context7 `/shadcn-ui/ui` (Combobox usage; "Dialog, Sheet and Drawer always need a Title"; Radix-managed focus and scroll); `frontend/package.json` (no `cmdk`); `frontend/src/components/ai/AthleteCombobox.tsx`; `frontend/src/components/calendar/AudienceSelector.tsx`; `.specify/memory/constitution.md` (III)

### R-30 Lazy routes with `ProtectedRoute`, nav entries declared in `navigation.ts`

**Decision**: The three new pages are declared exactly like every existing route in `frontend/src/App.tsx` — `React.lazy(() => import(...).then(m => ({ default: m.X })))` inside `<Routes>/<Route>` wrapped in `ProtectedRoute allowedRoles={…}` (`[UserRole.admin]` for `StaffPage`; `[UserRole.admin, UserRole.coach]` for `ClubHistoryPage` and `CoachActivityPage`). The per-athlete "historial" is a panel inside `AthleteDetailPage`, not a route. Nav entries are added to the config-driven model in `frontend/src/lib/navigation.ts` (which already declares `NavRole = "coach" | "admin"`, a reserved `club` group, and per-item `roles`), **not** as ad-hoc JSX. New query keys are deliberately **not** added to `PERSIST_ALLOWLIST_PREFIXES` — the default-deny persister must keep history/staff data off the device.

**Rationale**: This app uses the classic declarative router (`react-router-dom` v7 imported as `Navigate, Route, Routes`), not `createBrowserRouter`, so React Router 7's `route.lazy`/loader/middleware guard APIs do not apply without a router-architecture migration far outside this feature. `ProtectedRoute` (`frontend/src/routes/ProtectedRoute.tsx:14-57`) already implements per-role redirect fallbacks and is the only guard mechanism in the codebase; hiding the nav entry for coaches (the second half of FR-021) is the separate config layer. The `navigation.ts` route matters because there is an existing counter-example to avoid: `/admin/ai` has **no** entry in `NAV_AREAS` and is reachable only through hand-written `role === "admin"` blocks duplicated in `UserMenu.tsx:232-241` and `MoreSheet.tsx:76-83` — extending that pattern to a second admin page would compound the smell. `persistAllowList.ts` is an explicit allow-list, so "do nothing" is already correct — but the PR should say so, so a reviewer does not read it as an oversight.

**Alternatives**: migrate to a data router for loader-based guards — rejected, touches every route; per-page role checks inside each page body — rejected, duplicates `ProtectedRoute`; a narrow allow-list entry for aggregate counts — rejected as unnecessary scope (feature 040 excluded its growth summary for the same reason).

**Sources**: Context7 `/remix-run/react-router` (data-router `lazy`, loader `redirect`, middleware — all data-router-only); `frontend/src/App.tsx`; `frontend/src/routes/ProtectedRoute.tsx:14-57`; `frontend/src/lib/navigation.ts:12,20,31,46-72`; `frontend/src/components/layout/UserMenu.tsx:232-241`; `frontend/src/components/layout/MoreSheet.tsx:76-83`; `frontend/src/lib/persistAllowList.ts:41-64`

### R-31 Conditional Zod validation with `superRefine`; hardcoded Spanish messages; `ActorChip` replaces the one raw id

**Decision**: `staffCreateSchema` requires `club_id` only when `role === "coach"`, via `.superRefine((val, ctx) => { if (val.role === "coach" && !val.club_id) ctx.addIssue({ code: z.ZodIssueCode.custom, message: "El club es obligatorio para un entrenador", path: ["club_id"] }); })`, wired through `useForm({ resolver: zodResolver(staffCreateSchema) })`. All messages are hardcoded español-neutro strings (no `z.setErrorMap`, no i18n package). Separately, `frontend/src/components/competitions/tabs/InfoTab.tsx:152-155` — the only surface in the whole frontend that prints a raw numeric author id ("Creado por usuario ID") — is replaced by the shared `ActorChip` (FR-013).

**Rationale**: The conditional-required idiom already exists in this codebase (`frontend/src/schemas/calendar.schema.ts:110-165`: `start_time` required unless `all_day`; `race_event_id` required only for competitions), so reusing it keeps one pattern. Native HTML5 `required` is explicitly forbidden from competing with Zod on the same field (constitution III). A grep across `frontend/src` for `*_by_user_id` rendering confirms `InfoTab` is the single pre-existing FR-013 violation, so FR-013 elsewhere is about *new* surfaces.

**Alternatives**: `z.discriminatedUnion("role", …)` — more type-safe but heavier for one conditional field and inconsistent with every other conditional-required field here; a locale map / `zod-i18n-map` — no second locale exists.

**Sources**: Context7 `/react-hook-form/resolvers` (`zodResolver`, conditional validation), `/react-hook-form/documentation` (`Resolver` errors shape); `frontend/src/schemas/calendar.schema.ts:110-165`; `frontend/src/components/competitions/tabs/InfoTab.tsx:152-155`; `.specify/memory/constitution.md` (III)

---

## J. Testing

### R-32 One two-coach fixture, in the most isolated of the three existing idioms

**Decision**: Add the FR-034 fixture (coach A and coach B **in the same club**, plus a third coach in a *different* club and a parent) using the SQLite-in-memory + `app.dependency_overrides` idiom of `backend/tests/routers/test_race_imports.py:59-108,283-407` (role-specific httpx client fixtures), promoted into a shared module under `backend/tests/fixtures/` and registered as a pytest plugin — the mechanism already used for `fixtures/race_groups.py`. Tests that must exercise the real `users.py` router end-to-end (staff creation, club validation, set-password email) may keep the seeded-DB idiom of `backend/tests/test_users.py`.

**Rationale**: The root `backend/tests/conftest.py` provides only a bare `client` plus the opt-in MySQL fixtures (with the `_test` database-name safety check) — there is no shared user/club factory, and three divergent idioms coexist today (SQLite-in-memory + overrides; the `FakeSession` SQL-substring dispatcher in `backend/tests/routers/conftest.py`; the seeded-dev-DB login flow in `test_users.py`). 041 must pick one rather than add a fourth, and the SQLite-in-memory idiom is the newest, fastest and most isolated. Concretely, the fixture must **invert an existing green test**: `test_dry_run_403_cross_coach_ownership` (`backend/tests/routers/test_race_imports.py:691-748`) asserts coach B is refused coach A's parse — under FR-028 that becomes 200 when both share a club, and a new test must cover the still-refused other-club coach (today both fixtures are built with `club_memberships=[]`, so club scoping is not exercised at all).

**Alternatives**: extend the seeded-DB pattern with a second seeded coach for everything — rejected as the default (slower, coupled to seed data), but appropriate for the few real-router tests; a brand-new fourth fixture style — rejected by the constitution's duplication rule.

**Sources**: `backend/tests/conftest.py:1-90`; `backend/tests/routers/test_race_imports.py:59-108,283-407,691-748`; `backend/tests/routers/conftest.py`; `backend/tests/test_users.py:1-58,194-230`; spec FR-034

### R-33 The three tests that carry this feature's guarantees

**Decision**: Beyond the per-contract happy/denied pairs, three tests are load-bearing and must be written as such: (1) **audit coverage** — the route-registry meta-test plus per-router dynamic smoke plus the strict flush detector (R-06); (2) **audit privacy scan** — run a multi-action scenario, then assert no `audit_log` row contains a value outside `VALUE_ALLOWLIST` and no forbidden substring (synthetic names, ISO birth dates, measurement-shaped numerics), the direct executable form of SC-001 (R-04); (3) **"archived athlete is invisible everywhere"** — one integration test enumerating the surfaces of R-10 (athlete list, dashboard, monthly report, newsletter list, AI picker, parent portal) plus admin-still-sees-evidence, the executable form of SC-003. Each behavioural bug this feature fixes also needs a regression test that fails on the unfixed code: the misattributed cancellation email (R-19), the lost newsletter edit (R-13/R-14), the approval evidence destroyed on report regeneration, and the `created_by` nulling on parent delete (R-21). The negative-path idiom to copy is the established "coach de otro club → 403" style already present in `backend/tests/test_users.py:194-230` and `backend/tests/routers/test_club_insights_by_race.py:1-10`.

**Rationale**: Constitution II makes regression tests for bug fixes non-negotiable and requires explicit privacy invariants for minors' data; these three tests are also the only mechanical proof of SC-001, SC-003 and FR-009. Frontend side: jest-axe on the three new pages and on the archive/conflict dialogs (component-level precedent `frontend/src/components/athletes/growth/__tests__/GrowthTab.a11y.test.tsx`, page-level `frontend/src/routes/parents/training/ParentSessionDetailPage.a11y.test.tsx`; `toHaveNoViolations` is already extended globally in `frontend/src/test/setup.ts`), and new MSW handler modules under `frontend/src/test/msw/` exporting synthetic fixture factories in the style of `growthSummaryHandlers.ts`, registered in the shared `setupServer`.

**Sources**: `backend/tests/test_privacy.py:31`; `backend/tests/test_users.py:194-230`; `backend/tests/routers/test_club_insights_by_race.py:1-10`; `frontend/src/test/setup.ts:1-29`; `frontend/src/test/msw/growthSummaryHandlers.ts:14-47`; `.specify/memory/constitution.md` (II)

### R-34 e2e needs a second seed coach — and the isolated stack is blocked by a pre-existing migration bug

**Decision**: Add a `coach2` identity to `frontend/e2e/helpers/session.ts` (`SeedRole` is `'coach' | 'admin' | 'parent'` today, one coach only, `:17-23`) and to `frontend/e2e/helpers/demo-athlete.ts` (single hardcoded `COACH_EMAIL`), plus the matching account in `backend/scripts/seed.py`. **Before** any 041 Playwright spec can run green, the pre-existing migration bug that prevents the isolated e2e stack from booting on a fresh MySQL volume must be fixed as its own small task: three migrations import modules that no longer exist — `backend/alembic/versions/e1f2a3b4c5d6_technique_gymkhana_library.py:276` and `backend/alembic/versions/f1a2b3c4d5e6_add_layout_json_to_technique_exercises.py:60` import `app.data.technique_catalog`, `backend/alembic/versions/a7b8c9d0e1f2_strength_training_library.py:284` imports `app.data.strength_catalog`, while `backend/app/data/` contains only `cdc_lms/` and `who_lms/`. `frontend/playwright.config.ts` itself needs no change (its `E2E_APP_PORT`/`E2E_API_BASE_URL` scheme already generalises).

**Rationale**: Verified live, still broken. This is the same blocker that deferred five Playwright specs in feature 040 (`specs/040-growth-module-redesign/checklists/integration-review.md` §4). A later migration drops those tables, so the seed data has no downstream consumer and the cheapest fix is to make the three imports tolerant of the missing module (try/except `ImportError`) or inline the orphaned constants. Every US1–US8 independent test is two-coach by construction, so both the seed identity and a bootable stack are prerequisites, not polish.

**Alternatives**: run 041's e2e only against the long-lived dev stack — works around the blocker but defeats the disposable-state purpose and leaves CI/fresh-clone e2e broken indefinitely; skip e2e for 041 — rejected, US4/US5/US6 are inherently two-browser scenarios. The second seed coach must use synthetic staff data only (no real person's data in fixtures).

**Sources**: `frontend/e2e/helpers/session.ts:17-23`; `frontend/e2e/helpers/demo-athlete.ts`; `frontend/playwright.config.ts`; `backend/alembic/versions/e1f2a3b4c5d6_technique_gymkhana_library.py:276`; `backend/alembic/versions/f1a2b3c4d5e6_add_layout_json_to_technique_exercises.py:60`; `backend/alembic/versions/a7b8c9d0e1f2_strength_training_library.py:284`; `backend/app/data/`; `specs/040-growth-module-redesign/checklists/integration-review.md` §4

---

## K. Migration mechanics

### R-35 One Alembic revision on the single head, dialect-branched DDL, set-based backfills

**Decision**: One revision for the whole feature, `down_revision = "2a8baa967cc6"` (verified single head — see *Contradictions resolved*). FK-bearing columns follow the repo's existing dialect branch: `if dialect == "sqlite": op.batch_alter_table(...)` with `add_column` + `create_foreign_key` inside the block (SQLite cannot `ALTER TABLE … ADD COLUMN` with an FK/`ON DELETE`), `else:` plain `op.add_column(...)` + `op.create_foreign_key(...)` on MySQL, then `op.create_index(...)`. Backfills are set-based `op.execute(...)` statements written against migration-local `sa.table()`/`sa.column()` objects — never an import of the live ORM models — and must be idempotent: the session-coach backfill is `INSERT INTO training_session_coaches (session_id, coach_user_id, added_by_user_id, added_at) SELECT ts.id, ts.created_by_user_id, NULL, ts.created_at FROM training_sessions ts WHERE NOT EXISTS (SELECT 1 FROM training_session_coaches c WHERE c.session_id = ts.id)` — the bridge column is `coach_user_id`, not `user_id` (`data-model.md` §3); the authoritative statement is backfill B1 in `data-model.md` §6.3.

**Rationale**: Both idioms already exist here. `backend/alembic/versions/8c1d2e3f4a5b_athlete_ai_insights_history_and_calendar_link.py:112-127` adds a nullable FK + composite index with exactly the `if dialect == "sqlite": batch_alter_table … else: add_column + create_foreign_key` branch, with a comment explaining why; `backend/alembic/versions/2a8baa967cc6_growth_source_on_anthropometry.py:44-50` uses `batch_alter_table` unconditionally (documented as safe because Alembic recreates only on SQLite and emits a plain `ALTER TABLE` elsewhere) — both styles coexist, and the explicit branch is preferred for 041 because its columns carry FKs, where the two `create_foreign_key` call signatures differ enough that the branch reads more clearly in review. Migration-local table objects are the documented Alembic idiom precisely so a migration never drifts with the ORM; the repo already does this in `backend/alembic/versions/c4d5e6f7a8b9_seed_race_categories.py:75-145` (MySQL `ON DUPLICATE KEY UPDATE` vs SQLite `INSERT OR IGNORE`) and `8c1d2e3f4a5b` (`JSON_EXTRACT` vs `json_extract`).

**Alternatives**: (a) `batch_alter_table` unconditionally — equally valid per the docs, rejected only for readability on FK-heavy DDL; (b) run the session-coach backfill from `backend/entrypoint.sh` as a startup script (the pattern used for the LMS seed and the anthropometry recompute) instead of inside the migration — a placement choice rather than a technical one; it needs the same idempotency guard either way, and keeping it in the revision means a fresh database is correct without a second step; (c) `op.bulk_insert()` with Python-computed rows — the right tool for static catalogues, not for a one-row-per-session `INSERT … SELECT`; (d) skip DB-level FKs on `audit_log` to avoid lock contention on a hot table — worth a line in `data-model.md`'s complexity discussion given `audit_log` takes a write on every club action, but the expected volume (low thousands of rows per year, per `plan.md`) does not justify weakening referential integrity.

**Sources**: Context7 `/websites/alembic_sqlalchemy` (`batch_alter_table` — recreate only on SQLite; `execute`/`bulk_insert`; conditional data operations); `backend/alembic/versions/8c1d2e3f4a5b_athlete_ai_insights_history_and_calendar_link.py:112-142`; `backend/alembic/versions/2a8baa967cc6_growth_source_on_anthropometry.py:44-50`; `backend/alembic/versions/c4d5e6f7a8b9_seed_race_categories.py:75-145`; `backend/entrypoint.sh`

---

## Contradictions resolved

| Claim from the input research | Verdict | Why |
|---|---|---|
| Table named `history_entries`, helper `record_history_entry`, script `purge_history.py` | **Discarded** (renamed) | `plan.md` fixes `audit_log`, `record_audit`, `scripts/retention_audit_log.py` and the contract filenames; two vocabularies across Phase 0 and Phase 1 would break `/speckit-analyze` consistency. Semantics are unchanged. |
| Concurrency token named `content_version` | **Discarded** | The name is a *retired column of this very table*: feature 038 added it and `backend/alembic/versions/8b5ac1f24f61_drop_newsletter_content_version.py` dropped it (`backend/tests/models/test_newsletter_stage_log_migration.py:108-110` asserts its absence). Reusing it with a different meaning would mislead. → `edit_version` (R-13). |
| `updated_at` is a good enough concurrency token | **Discarded** | It exists (`backend/app/models/athlete_newsletter.py:153`) but is `DATETIME` with `fsp=0` on MySQL, so two saves in the same second are indistinguishable — the exact US5 case (R-02, R-13). |
| 412 Precondition Failed for a stale `If-Match` (RFC-purist) | **Discarded for this feature** | Correct per RFC 9110, but `plan.md`, ~10 existing 409 sites and the frontend's existing 409 branch make one conflict status the cheaper, more consistent choice; documented as the alternative in R-14 so the reasoning is not lost. |
| `alembic heads` shows one head / an earlier claim of two heads | **Confirmed single head** | Re-verified by walking `down_revision` chains over all 49 revisions, including the multi-parent merge `b4c5d6e7f8a9_email_change_requests_and_merge_heads.py` (which consumes `8c1d2e3f4a5b`, `a1b2c3d4e5f7`, `a1b2c3d4e5f8`). Sole head: `2a8baa967cc6` — the `down_revision` `plan.md` assumes. A naïve scan that misses that merge reports two heads; that reading is wrong. |
| Newsletters have no approval attribution | **Partly wrong** | `AthleteMonthlyNewsletter` already has `approved_by_user_id`/`approved_at` (`backend/app/models/athlete_newsletter.py:103-106`). What is genuinely missing there is the **coach-note** author/time (FR-012) and `edit_version`. The missing approval evidence is on `MonthlyReport`, which has `generated_by_user_id`/`generated_at` but **no** `approved_by`/`approved_at` at all (`backend/app/models/training_session.py:218-258`) — so FR-010's "previously approved by" needs both a new column pair and a regeneration path that preserves it. |
| A global ORM filter / an AST lint should enforce the archived-athlete exclusion | **Discarded** | A global criterion must be selectively bypassed for the admin archive view FR-014 requires, and both mechanisms are blind to Core statements; the guarantee is the surface-enumeration test (R-10). |
| Flush events (`before_flush`/`after_flush`) can carry the audit | **Discarded as the mechanism** | Blind to ~20 Core `delete()/update()/text()/mysql_insert()` sites, including the athlete cascade and the whole `agent_runs` layer, and unable to express action/reason/correlation (R-03). Retained only as a *test-only* detector (R-06). |
| A request-scoped ContextVar suffices for actor + correlation | **Partly discarded** | Fine for `request_id` on the HTTP path, wrong for the actor and for the LangGraph `_on_complete` closures, the webhooks and the boot scripts, which run outside the request scope entirely (R-05). |
| Retention CLI takes a `--dry-run` flag | **Adjusted** | The repo precedent (`retention_ai_insights.py`) is the safer inverse: dry-run is the default and `--apply` opts in (R-25). |
| `agent_run_events` can be audited through an ORM model | **Discarded** | No ORM model exists for that table; it is written via raw `text()` INSERTs in the routers, so the audit hook goes at those call sites (R-23). |
| Two race-events endpoints are coach-only, excluding admins | **Out of scope, flagged** | `backend/app/routers/race_events.py:606-609,700-703` require `coach` and 403 an admin, inconsistent with every other mutation in that module. Not an audit requirement; raise with the owner as a one-line decision rather than carrying it silently. |

---

## Resolved unknowns from Technical Context

| Unknown | Resolution |
|---|---|
| One generic audit table vs per-entity trails | R-01 — one `audit_log`, third instance of an existing pattern; domain trails kept as detail |
| Sub-second timestamp on MySQL 8.4 (FR-002) | R-02 — `mysql.DATETIME(fsp=6)`; the two precedent tables truncate to whole seconds today |
| Same-transaction write vs outbox/async | R-03 — explicit `record_audit` in the caller's session; outbox rejected (single DB, no workers); multi-commit endpoints pin the call site |
| How FR-003 minimisation is guaranteed | R-04 — field names by default, per-entity `VALUE_ALLOWLIST`, row-scanning privacy test |
| Correlation reference + automated actors (FR-002, AC4) | R-05 — pure-ASGI `request_id` ContextVar; actor always explicit; closed `AuditActorKind` for the six verified non-human writers |
| FR-009 "cannot ship unaudited" mechanism | R-06 — route registry meta-test + dynamic smoke + test-only strict flush detector |
| FR-004 append-only enforcement | R-07 — code + test; DB trigger/grant hardening deferred; purge is additive |
| Where the Spanish history sentence lives | R-08 — composed at read time from a template map, never stored; Phase 1 moved the renderer server-side (`contracts/audit-log-api.md` §7.1) |
| Athlete removal semantics and endpoint shape | R-09 — soft-delete columns (`deleted_*`, `data-model.md` §4.2), same `DELETE` route rewritten, `POST /restore`; the RESTRICT FKs explain today's half-way failure |
| Keeping archived athletes out of active surfaces | R-10 — explicit filters through two choke points + one enumeration test; no global criterion |
| Roster removal with ratings/feedback (FR-016) | R-11 — conditional archive + attendance attribution columns |
| Unique constraints under soft-delete on MySQL | R-12 — generated-column trick if ever needed; not needed for 041; `race_results` cited as the cautionary precedent |
| Concurrency token name and type | R-13 — integer `edit_version`; `content_version` is a retired 038 name, `updated_at` lacks precision |
| Conflict status codes | R-14 — 409 stale / 428 missing; 412 documented and rejected |
| Can the browser read the ETag today? | R-15 — no: `expose_headers` is unset and `If-Match` is not allow-listed; an existing ETag path is dead code because of it |
| Client behaviour on conflict | R-16 — blocking `AlertDialog` + explicit reload; no retry on 409/412/428 |
| Co-coach data shape and backfill | R-17 — bridge table, creator backfill |
| "At least one coach" invariant | R-18 — service layer + `SELECT … FOR UPDATE`; no CHECK/trigger possible |
| Truthful notifications + SC-008 counting | R-19 — acting user threaded into services, two template variables, DISTINCT club total vs per-coach count |
| Why a coach created by an admin sees an empty app | R-20 — the club check is gated on the *caller's* role; a green test encodes the bug |
| Deactivate vs delete for staff | R-21 — reuse `PATCH is_active`; delete already refused; fix the parent-delete `created_by` nulling |
| Set-password email for a new coach | R-22 — reuse `request_reset`; relax its "no password yet" guard; drop the cleartext password field |
| Creator-locked runs and imports | R-23 — club-scoped checks via `coach_club_ids`; persist the HITL decider (dropped today) |
| Per-coach AI spend | R-24 — join through `agent_runs.requested_by_user_id`, no migration; widen RBAC; new page (endpoint has no consumer today) |
| Purge procedure shape | R-25 — Typer CLI, dry-run default via `--apply`, shared cutoff, self-audited |
| Monthly scheduling without workers | R-26 — GitHub Actions mirroring `strava-reconcile.yml` |
| Why business logs are missing in production | R-27 — no `dictConfig`; uvicorn configures only its own loggers; add root/`app` config with a `request_id` filter |
| Table component for the new list pages | R-28 — shadcn `Table` + server-side offset/limit; `@tanstack/react-table` not added |
| Person picker component | R-29 — Radix `Select`; reuse `AthleteCombobox` for athletes; no `cmdk` |
| Routing/guard/nav mechanism | R-30 — `React.lazy` + `ProtectedRoute` + `navigation.ts`; no data-router migration; no persistence allow-list entries |
| Conditional "club required" validation | R-31 — `superRefine`, Spanish messages; `ActorChip` replaces the one raw id in `InfoTab` |
| Two-coach fixture placement | R-32 — SQLite-in-memory + `dependency_overrides` idiom, shared fixture module; invert the existing cross-coach 403 test |
| Which tests carry the guarantees | R-33 — coverage, privacy scan, archived-invisibility, plus four regression tests |
| Can Playwright specs run at all? | R-34 — not on a fresh volume until the three migrations importing deleted `app.data.*` modules are fixed; a `coach2` seed identity is also required |
| Migration shape, head and backfills | R-35 — one revision on `2a8baa967cc6`, sqlite/MySQL dialect branch for FK columns, idempotent set-based backfills with migration-local tables |

---

## Superseded by Phase 1

Phase 1 (`data-model.md`, `contracts/*.md`) refined the entries below. The decisions
themselves stand; what changed is a name, a unit or the layer that runs them. **Where this
document and Phase 1 disagree, Phase 1 wins** — it is what reaches the DDL, the routers and
the tests.

| Entry | What this document says | Authoritative now |
|---|---|---|
| R-01, R-05 | `request_id String(36)`; eight-value `AuditActorKind` (`person`, `webhook_resend`, `webhook_strava`, `cron_strava_reconcile`, `startup_backfill`, `startup_seed`, `agent_run`, `purge_job`) | `String(32)` (`uuid4().hex`) and four values — `user`, `system`, `webhook`, `cron` — with the specific job in `meta_json.job`: `data-model.md` §1, §2.2; `contracts/audit-recording.md` §10 point 1 |
| R-08 | The FR-008 sentence is composed **client-side** from a TypeScript template map | Composed **server-side** at read time (`render_sentence`) and returned as `sentence_es`; still never stored, and the client keeps the "Ver detalle" `Collapsible`: `contracts/audit-log-api.md` §7.1 |
| R-09 | `archived_at` / `archived_by_user_id` / `archive_reason`; `AthleteArchiveReason` enum | `deleted_at` / `deleted_by_user_id` / `deleted_reason_code`; reason values from the shared `AuditReasonCode` catalogue: `data-model.md` §4.2, §2.4; `contracts/athlete-archive.md` §0 |
| R-11 | attendance `last_edited_by_user_id` + `last_edited_at`; `archived_by_user_id` | `updated_by_user_id` plus the existing `updated_at`; no `archived_by_user_id` — the archiving actor is the `audit_log` row sharing the same `request_id`: `data-model.md` §4.3; `contracts/session-coaches.md` §1 |
| R-17 | bridge column `user_id`; `UniqueConstraint("session_id", "user_id")` | `coach_user_id`; composite PK `(session_id, coach_user_id)` and index `ix_tsc_coach_user_id`: `data-model.md` §3; `contracts/session-coaches.md` §1 |
| R-25 | `--days`, default `730`; purge row `actor_kind=purge_job`; exactly one purge row | `--months`, default `24`; `actor_kind=system` (`cron` when scheduled); one purge row per distinct `club_id` in the deleted set: `contracts/retention-purge.md` §0 |
| R-35 | backfill INSERT named the bridge column `user_id` | **Corrected in place** to `coach_user_id`; the authoritative statement is backfill B1, `data-model.md` §6.3 |

R-01, R-05, R-08, R-09, R-25 and R-35 also carry the note next to the entry itself; R-11
and R-17 are recorded only here, because the naming that superseded them is already
tabulated in `contracts/session-coaches.md` §1.
