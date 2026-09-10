# Contract — Per-coach activity report, author names and history surfaces

Covers **FR-013**, **FR-031**, **FR-032**, **FR-007** (UI half) and **SC-008**; user story US7.

**Owns**: the `GET /api/clubs/{club_id}/coach-activity` endpoint, the `CoachActivityPage`,
the actor-directory module (`api/users.ts` → `ActorChip`) that replaces every raw numeric
author id, and the *UI* of the two history surfaces (athlete panel, club page).

**Does not own**: the `audit_log` read endpoints, the Spanish sentence templates and the
`AuditEntryOut` payload — those are `contracts/audit-log-api.md`. Attribution columns and
catalogues are `data-model.md` §1–§4. Session co-coaching is `contracts/session-coaches.md`.

---

## 1. Endpoint — `GET /api/clubs/{club_id}/coach-activity`

**Router**: `backend/app/routers/audit.py` (new), mounted next to the club-scoped routers
in `backend/app/main.py:104` (`prefix="/api/clubs"`), so the full path is
`/api/clubs/{club_id}/coach-activity`. The shape mirrors `list_monthly_reports`
(`backend/app/routers/monthly_reports.py:212-241`): path club id, RBAC helper first, one
service call, no ORM leakage into the router.

**Service**: `backend/app/services/coach_activity.py::compute_coach_activity(db, club_id, period_from, period_to, coach_user_id=None)`.

**Schemas**: `backend/app/schemas/audit.py::CoachActivityOut` and its nested models;
mirrored in `frontend/src/schemas/coachActivity.schema.ts` (Zod) and
`frontend/src/types/coachActivity.types.ts`.

### 1.1 Request

| Parameter | In | Type | Required | Notes |
|---|---|---|---|---|
| `club_id` | path | `int` | yes | Scope of the whole response. |
| `from` | query | `date` (`YYYY-MM-DD`) | **yes** | Inclusive lower bound. |
| `to` | query | `date` (`YYYY-MM-DD`) | **yes** | Inclusive upper bound. |
| `coach_user_id` | query | `int` | no | Narrows `coaches[]` to one person. `club_totals` is **never** narrowed. |

Both bounds are mandatory on purpose: an implicit "current month" default makes the
reconciliation test (§9.1, SC-008) depend on the clock, and the UI always has a period
selected. Date-only bounds are expanded server-side to `[from 00:00:00, to+1d 00:00:00)`
for the timestamp-anchored blocks (§3).

Validation: `from <= to` and `to - from <= 366 days`, else `422`.

### 1.2 Response `200`

```json
{
  "club_id": 1,
  "from": "2026-03-01",
  "to": "2026-03-31",
  "computed_at": "2026-04-01T14:22:07.913482",
  "club_totals": {
    "sessions": { "planned": 2, "executed": 10, "cancelled": 1, "total": 13 },
    "attendance_entries_recorded": 154,
    "ai_runs_launched": 6,
    "results_operations": { "imports": 2, "revisions": 5, "competitor_links": 3, "total": 10 },
    "documents": { "reports_approved": 1, "newsletters_approved": 12, "newsletters_sent": 12, "exports": 7 },
    "audit_entries_count": 318
  },
  "coaches": [
    {
      "coach": { "user_id": 7, "display_name": "Ana Coach", "role": "coach", "is_active": true },
      "sessions": { "planned": 1, "executed": 6, "cancelled": 1, "total": 8, "co_led": 2 },
      "attendance_entries_recorded": 92,
      "ai_runs_launched": 4,
      "results_operations": { "imports": 1, "revisions": 3, "competitor_links": 2, "total": 6 },
      "documents": { "reports_approved": 1, "newsletters_approved": 7, "newsletters_sent": 7, "exports": 4 },
      "audit_entries_count": 176
    },
    {
      "coach": { "user_id": 12, "display_name": "Bruno Coach", "role": "coach", "is_active": true },
      "sessions": { "planned": 1, "executed": 4, "cancelled": 0, "total": 5, "co_led": 2 },
      "attendance_entries_recorded": 62,
      "ai_runs_launched": 2,
      "results_operations": { "imports": 1, "revisions": 2, "competitor_links": 1, "total": 4 },
      "documents": { "reports_approved": 0, "newsletters_approved": 5, "newsletters_sent": 5, "exports": 3 },
      "audit_entries_count": 142
    }
  ]
}
```

Figures above are illustrative. `display_name` is `f"{first_name} {last_name}"` of a
**staff account** (an adult); no athlete id, athlete name, birth date, measurement or free
text appears anywhere in this payload (§5).

`coaches[]` is sorted server-side on `(last_name, first_name, user_id)` — a stable order
that does not depend on locale collation, so the same period always renders in the same
sequence.

### 1.3 Membership of `coaches[]`

The list is **not** "coaches who did something". It is:

1. every account with `club_members.role_in_club = coach` in `{club_id}`
   (`backend/app/models/club.py:48`, `role_in_club` at `:58`) that is `is_active = true`
   (`backend/app/models/user.py:38`); **plus**
2. every account that is (or was) a coach member of the club and has a non-zero counter
   in the window — this is how a deactivated coach keeps appearing on the periods they
   worked (FR-013, Edge Case spec.md:169).

Coaches with all-zero counters are still returned, so the reader sees "0" rather than an
absence (spec.md:136 — "A: 4 sessions, 2 runs, 0 approvals; B: 3 sessions, 0 runs, 1 approval").
Administrators are **not** rows here; their actions are visible in the club history.

### 1.4 Variants

| Situation | Response |
|---|---|
| Club has one coach | `coaches[]` has one entry; `club_totals.sessions.total` equals that coach's total when no session is co-led |
| No activity at all in the window | `200`, every counter `0`, `coaches[]` still lists the active coaches |
| `coach_user_id` given | `coaches[]` has exactly one entry; `club_totals` unchanged (full club) |
| Coach deactivated mid-window | included, `coach.is_active: false`, counters unchanged |
| Window covers sessions of an **archived** athlete | those sessions and attendance rows still count — a report reconstructing a past period must not filter `athletes.deleted_at` (`data-model.md` §8.1, "Sites that must **not** filter") |
| Legacy `race_imports` row with `committed_by_user_id IS NULL` | falls back to `imported_by_user_id` / `imported_at` (§3) |

### 1.5 Errors

| Code | When | Body |
|---|---|---|
| `401` | no/invalid token | standard |
| `403` | parent, athlete, or coach without membership in `{club_id}` | `{"detail": "No tienes permisos para ver la actividad de este club."}` |
| `404` | club does not exist | `{"detail": "Club no encontrado"}` |
| `404` | `coach_user_id` is not (and never was) a coach member of the club | `{"detail": "Entrenador no encontrado en este club"}` |
| `422` | `from > to`, or window > 366 days | `{"detail": "El periodo debe empezar antes de terminar y no superar 366 días."}` |

---

## 2. Counting rule (FR-032, SC-008)

Two rules, applied to the **same** rows:

- **Per coach** — a session counts once for *each* of its coaches. A session led by A and
  B adds 1 to A and 1 to B. `co_led` is the subset of that coach's sessions that have
  ≥ 2 rows in `training_session_coaches`; it is **not** a fourth disjoint state:
  `planned + executed + cancelled == total`, and `co_led <= total`.
- **Club total** — a session counts **once**, whatever its number of coaches:
  `COUNT(DISTINCT training_sessions.id)`.

```sql
-- club_totals.sessions (deduped)
SELECT ts.status, COUNT(DISTINCT ts.id)
  FROM training_sessions ts
 WHERE ts.club_id = :club AND ts.scheduled_date BETWEEN :from AND :to
 GROUP BY ts.status;

-- coaches[].sessions (fan-out is intentional)
SELECT c.coach_user_id, ts.status, COUNT(*) AS n
  FROM training_session_coaches c
  JOIN training_sessions ts ON ts.id = c.session_id
 WHERE ts.club_id = :club AND ts.scheduled_date BETWEEN :from AND :to
 GROUP BY c.coach_user_id, ts.status;

-- coaches[].sessions.co_led
SELECT c.coach_user_id, COUNT(*)
  FROM training_session_coaches c
  JOIN training_sessions ts ON ts.id = c.session_id
 WHERE ts.club_id = :club AND ts.scheduled_date BETWEEN :from AND :to
   AND (SELECT COUNT(*) FROM training_session_coaches x WHERE x.session_id = ts.id) > 1
 GROUP BY c.coach_user_id;
```

Consequence, and the exact wording of the SC-008 assertion:
`SUM(coaches[].sessions.total) >= club_totals.sessions.total`, the excess being the number
of extra coach assignments. The reconciliation test asserts
`club_totals.sessions.total == COUNT(DISTINCT session_id)` over the union of the per-coach
buckets — **never** a naive sum (`data-model.md` §8.3 Q3).

`club_totals.sessions.planned` means `status = 'planned'`, matching
`backend/app/services/training/metrics.py:54-56`. It does **not** mean "planned or
executed" — that other reading exists in the same module for *minutes*
(`backend/app/services/training/metrics.py:62-66`) and must not leak into this report.

The non-session blocks have no fan-out: each row has exactly one actor, so the club total
is the plain sum of the per-coach values **plus** rows attributed to an administrator or
to an automated actor. The response therefore never promises
`SUM(coaches[].x) == club_totals.x` for those blocks either; the UI states the club total
as its own figure (§6.4 copy).

---

## 3. Sources per block

| Block | Table / column | Actor column | Period anchor | Evidence |
|---|---|---|---|---|
| `sessions.{planned,executed,cancelled}` | `training_sessions.status` | `training_session_coaches.coach_user_id` | `training_sessions.scheduled_date` | `backend/app/models/training_session.py:79,84`; bridge in `data-model.md` §3 |
| `sessions.co_led` | `training_session_coaches` row count per session | idem | idem | `data-model.md` §3 |
| `attendance_entries_recorded` | `session_attendance` rows with `archived_at IS NULL` | `session_attendance.recorded_by_user_id` (new) | `training_sessions.scheduled_date` via `session_attendance.session_id` | `backend/app/models/training_session.py:153,179`; new columns in `data-model.md` §4.3 |
| `ai_runs_launched` | `agent_runs` | `agent_runs.requested_by_user_id` | `agent_runs.started_at` | `backend/app/models/agent_run.py:94,105` |
| `results_operations.imports` | `race_imports` with `status = 'committed'` | `committed_by_user_id` (new), falling back to `imported_by_user_id` | `committed_at` (new), falling back to `imported_at` | `backend/app/models/race_import.py:110,121,124`; new columns in `data-model.md` §4.8 |
| `results_operations.revisions` | `race_result_revisions` | `changed_by_user_id` | `changed_at` | `backend/app/models/race_result_revision.py:75,78` |
| `results_operations.competitor_links` | `race_competitor_link_audit` (`link` **and** `unlink`) | `user_id` | `created_at` | `backend/app/models/race_competitor_link_audit.py:107,110` |
| `documents.reports_approved` | `audit_log` `action='approve' AND entity_type='monthly_report'` | `actor_user_id` | `occurred_at` | `data-model.md` §1, §2.1, §2.3 |
| `documents.newsletters_approved` | `audit_log` `action='approve' AND entity_type='athlete_monthly_newsletter'` | idem | idem | idem |
| `documents.newsletters_sent` | `audit_log` `action='send' AND entity_type='athlete_monthly_newsletter'` | idem | idem | idem |
| `documents.exports` | `audit_log` `action='export'`, any `entity_type` | idem | idem | `data-model.md` §2.3 (`meta_json.document_kind`) |
| `audit_entries_count` | `audit_log`, any action, `club_id = :club` | idem | idem | `data-model.md` §1.1 `ix_audit_actor_time` |

Notes that must survive into the implementation:

1. **Two anchor families, on purpose.** Sessions and attendance are anchored on the
   session's own date, so "March" means the same month the monthly report means and the
   two reconcile. Every other block is anchored on the timestamp of the act itself
   (a report approved on 2 April belongs to April). This mirrors the spec's own
   independent test (spec.md:136), which counts sessions led *in* the month and
   approvals performed *in* the month.
2. **Only committed imports count.** A `pending`/`dry_run` parse is work in progress, not
   a results operation; `committed_by_user_id` is precisely the column US6 AS2 demands so
   the commit is attributed to the coach who pressed it while the parse keeps its importer
   (`data-model.md` §4.8).
3. **Archived attendance rows are excluded** (`archived_at IS NULL`), so the count matches
   what the monthly report and the session detail show. The archive event itself remains
   visible in the history.
4. **AI runs are club-scoped through the athlete**: `agent_runs.athlete_id`
   (`backend/app/models/agent_run.py:109`) → `athletes.club_id`
   (`backend/app/models/athlete.py:56`). Runs with `athlete_id IS NULL` are attributed to
   the club when their `requested_by_user_id` is a coach member of that club.
5. **Race tables carry no `club_id`** — verified: neither `race_series` nor `race_event`
   has one. The three results counters are therefore scoped by *the actor being a member
   of `{club_id}`*, which is exact for a single-club deployment. Accepted limitation, with
   an explicit trigger: **when a second club is onboarded, this scoping must change**
   before the report can be trusted. Recorded here rather than silently.

---

## 4. RBAC

Helper: `backend/app/services/permissions.py::can_view_coach_activity(db, user, club_id)`,
written in the shape of `can_view_monthly_report`
(`backend/app/services/permissions.py:205-225`) and reusing `user_club_role`
(`backend/app/services/permissions.py:76`).

| Caller | `GET /clubs/{id}/coach-activity` | `GET /clubs/{id}/audit-log` (see `audit-log-api.md`) | `/training/reports/actividad-entrenadores` | `/club/historial` |
|---|---|---|---|---|
| `admin` | 200, any club | 200 | visible | visible |
| `coach`, member of the club | 200 | 200 | visible | visible |
| `coach`, not a member | 403 | 403 | route guard redirects | route guard redirects |
| `parent` | **403** | **403** | not routed | not routed |
| `athlete` | 403 | 403 | not routed | not routed |
| anonymous | 401 | 401 | redirect to login | redirect to login |

The per-coach view is an internal management surface: it is never rendered under
`routes/parents/`, never included in any family email, PDF or newsletter, and its query
keys are **not** added to `PERSIST_ALLOWLIST_PREFIXES`
(`frontend/src/lib/persistAllowList.ts:49-64` — default-deny, so doing nothing is correct
and the PR must say so explicitly).

---

## 5. Non-functional

- **Queries**: one query per block, six in total, all `GROUP BY <actor>` — never one query
  per coach. A query-count test pins the number so a future "loop over coaches" refactor
  fails. Indexes already in place or added by this feature:
  `idx_training_session_club_date` (`backend/app/models/training_session.py:69`),
  `ix_tsc_coach_user_id` (`data-model.md` §3),
  `ix_agent_runs_user_started` (`backend/app/models/agent_run.py:86`),
  `ix_race_result_revisions_changed_by` (`backend/app/models/race_result_revision.py:59`),
  `ix_link_audit_user_id` (`backend/app/models/race_competitor_link_audit.py:74`),
  `ix_audit_actor_time` (`data-model.md` §1.1).
- **Budget**: p95 ≤ 500 ms (read). Bounded by the 366-day window and the club's volume
  (≈ 8 000 audit rows/year, `data-model.md` §9).
- **Privacy (Ley 1581)**: the payload contains staff names and integers only. No
  `athlete_id`, no athlete name, no birth date, no measurement, no free text, no document
  file name. A schema-level test asserts the response key set is exactly the closed set of
  §1.2 (§9.1, test 15).
- **Logging**: errors log `club_id` and the window only, never a name (constitution,
  Observability gate).

---

## 6. Frontend — `CoachActivityPage`

### 6.1 Route and wiring

| Item | Value |
|---|---|
| Path | `/training/reports/actividad-entrenadores` |
| File | `frontend/src/routes/training/CoachActivityPage.tsx` |
| Registration | `React.lazy(...)` + `<Route>` wrapped in `<ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>`, immediately after the `/training/reports/project-profile` block at `frontend/src/App.tsx:507-516` |
| Suspense label | `<RouteFallback label="Cargando actividad por entrenador…" />` |
| Nav | **No** `navigation.ts` entry. It is a sub-page of "Informes del club", exactly like `/training/reports/project-profile`, and `/training/reports` is already a `matchPrefixes` entry of the `families` area (`frontend/src/lib/navigation.ts:175-179`), so the active state is inherited. |
| Entry point | A `<Link>` in the `ReportsListPage` header actions row, cloned from the "Datos del proyecto" link at `frontend/src/routes/training/ReportsListPage.tsx:398-404`, `data-testid="coach-activity-link"`, label **"Actividad por entrenador"** |

A tab inside `ReportsListPage` was the alternative offered in the brief; a sibling route is
chosen because `ReportsListPage` already owns a generate-report dialog and a download flow
(`frontend/src/routes/training/ReportsListPage.tsx:1-485`) and FR-031 requires that page's
content to stay byte-identical (SC-009).

Data: `frontend/src/api/coachActivity.ts::getCoachActivity(clubId, params)` +
`frontend/src/hooks/governance/useCoachActivity.ts`, following the filtered-list hook
convention of `frontend/src/hooks/activities/useActivityReview.ts`
(`useQuery({ queryKey: ["coach-activity", clubId, filters], enabled: !!accessToken && !!clubId, placeholderData: keepPreviousData })`).
`clubId` comes from `useAuthStore(...).user?.club_ids?.[0]`, the established idiom at
`frontend/src/routes/training/ReportsListPage.tsx:323`.

> Placement note: `plan.md` lists the hooks flat (`hooks/useCoachActivity.ts`). They go in
> `hooks/governance/` to follow the per-domain subfolder convention already in the tree
> (`hooks/activities/`, `hooks/training/`, `hooks/race/`); same module, same name.

### 6.2 Component tree

```text
CoachActivityPage
├── PageHeader                     ← título + subtítulo + Link "Informes del club"
├── CoachActivityFilters           ← presets de periodo · Desde/Hasta · selector de entrenador
├── ClubTotalsRow                  ← 4 × shared/StatCard con el total del club
├── CoachActivityCard[]            ← una tarjeta por entrenador
│   ├── ActorChip                  ← nombre + insignia "Inactivo" cuando aplica
│   ├── 5 × StatCard/tile          ← Sesiones · Asistencias · Análisis IA · Resultados · Documentos
│   └── Link "Ver historial"       ← /club/historial?actor={id}&from={from}&to={to}
└── EmptyState / ErrorState        ← shared/EmptyState.tsx, shared/ErrorState.tsx
```

Filter controls clone `ActivityReviewPage`'s panel
(`frontend/src/routes/activities/ActivityReviewPage.tsx:167-245`): the same
`inputSelectClass` token, native `<select>` + `<input type="date">` with a visible
`<label htmlFor>`, and a "Limpiar filtros" reset. The coach picker is a Radix/native
`Select` (R-29) — no combobox at this cardinality.

Period presets (buttons that set `from`/`to`): **"Mes actual"**, **"Mes anterior"**,
**"Últimos 30 días"**, **"Temporada"**. The custom `Desde`/`Hasta` inputs stay visible and
authoritative; picking a preset just fills them.

### 6.3 States

| Surface | Loading | Empty | Error |
|---|---|---|---|
| Club totals | `StatCard isLoading` skeletons | all-zero counters render as "0", never as an empty state | `ErrorState` with "Reintentar" (refetch) |
| Coach cards | 2 skeleton cards | "Este club todavía no tiene entrenadores registrados." | same `ErrorState`, one per page (not per card) |
| Period with no activity | — | "No hay actividad registrada en el periodo seleccionado." + hint "Prueba con otro rango de fechas." | — |
| Server cold start | existing `ServerWakingBanner` behaviour, unchanged | | |

### 6.4 Copy (español neutro, con tildes)

- Title **"Actividad por entrenador"**; subtitle **"Resumen interno de gestión del club. No se comparte con las familias."**
- Filters: "Periodo", "Desde", "Hasta", "Entrenador", "Todos los entrenadores", "Limpiar filtros".
- Club totals card labels: "Sesiones del club", "Registros de asistencia", "Análisis de IA", "Documentos".
  Footnote under the row: **"Cada sesión se cuenta una sola vez en el total del club. Una sesión con dos entrenadores cuenta para ambos en sus tarjetas."**
- Per-coach tiles:
  - "Sesiones" → value `total`, hint "{planned} planificadas · {executed} ejecutadas · {cancelled} canceladas"; extra line "{co_led} en co-dirección" only when `co_led > 0`.
  - "Registros de asistencia" → value `attendance_entries_recorded`.
  - "Análisis de IA lanzados" → value `ai_runs_launched`.
  - "Operaciones de resultados" → value `results_operations.total`, hint "{imports} importaciones · {revisions} revisiones · {competitor_links} enlaces".
  - "Documentos" → hint "{reports_approved} informes aprobados · {newsletters_approved} boletines aprobados · {newsletters_sent} enviados · {exports} descargas".
- History link: **"Ver historial de {nombre}"**.
- Inactive badge: **"Inactivo"** (neutral gray `StatusBadge`, icon + text — never colour alone).
- Errors: "No se pudo cargar la actividad por entrenador." + "Reintentar".

### 6.5 Accessibility

- Every tile is a `shared/StatCard` (`frontend/src/components/shared/StatCard.tsx`); the
  numbers are text, never colour-coded alone.
- Each coach card is a `<section>` with `aria-labelledby` pointing at the coach name
  heading, so a screen reader announces "Ana Coach, sección" before the counters.
- Filter controls: every `<select>`/`<input>` has a visible `<label htmlFor>`; the preset
  buttons are a `role="group"` with `aria-label="Periodo"`; all interactive targets
  `min-h-12` (48 px, constitution III).
- Loading regions carry `role="status" aria-live="polite"` with an `sr-only` label, as in
  `frontend/src/routes/activities/ActivityReviewPage.tsx:247-254`.
- jest-axe: zero violations, loaded and empty.

### 6.6 Stable test ids

`coach-activity-page`, `coach-activity-filters`, `coach-activity-club-totals`,
`coach-activity-card` (one per coach, with `data-coach-id`), `coach-activity-history-link`,
`coach-activity-link` (the entry point on `ReportsListPage`), `actor-chip`.

---

## 7. Author names everywhere — `api/users.ts` + `ActorChip` (FR-013)

### 7.1 New API module — `frontend/src/api/users.ts`

The backend endpoint already exists and needs **no change**: `GET /api/users`
(`backend/app/routers/users.py:140-217`) accepts `role` and `club_id`
(`backend/app/routers/users.py:142-143`), is gated to `admin`/`coach`
(`:145`), scopes a coach to their own clubs (`:181-209`), returns
`UserListOut { items: UserOut[], total }` (`backend/app/schemas/user.py:32-48`), and does
**not** filter by `is_active` — which is exactly what FR-013 needs for deactivated names to
keep resolving.

```ts
// frontend/src/api/users.ts
export async function getUsers(params?: {
  role?: "admin" | "coach" | "parent";
  club_id?: number;
}): Promise<UserListOut>;

/** Sugar for the coach picker and the per-coach report. */
export async function getCoachUsers(params: { club_id: number }): Promise<UserListOut>;
```

`frontend/src/api/parents.ts:15-22` already calls `/api/users?role=parent`; that function
stays where it is (parents domain) and is **not** moved — this module is additive, not a
refactor.

Hook: `frontend/src/hooks/governance/useClubStaff.ts`

```ts
useClubStaff(clubId?: number, role?: "coach")   // ["club-staff", clubId, role]
useActorDirectory(clubId?: number)              // Map<number, UserOut>, built from useClubStaff(clubId)
```

Neither key is persisted (`persistAllowList` default-deny).

### 7.2 `ActorChip` — `frontend/src/components/audit/ActorChip.tsx`

```ts
interface ActorChipProps {
  userId: number | null;
  /** Already-resolved name (audit rows carry it; InfoTab does not). */
  displayName?: string | null;
  /** From the audit row when the writer was not a person. */
  actorKind?: "user" | "system" | "webhook" | "cron";
  isActive?: boolean;
  className?: string;
}
```

Resolution order and copy:

| Case | Renders |
|---|---|
| `displayName` provided | the name |
| `userId` resolves in the directory | the name; plus a neutral "Inactivo" badge when `is_active === false` |
| `actorKind !== "user"` (or `userId === null`) | **"Proceso automático"** |
| id not in the directory (deleted parent, other club) | **"Usuario no disponible"** |
| directory still loading | `Skeleton`, never the raw number |

The raw numeric id is **never** rendered — that is the whole point of FR-013.

### 7.3 The one existing violation

`frontend/src/components/competitions/tabs/InfoTab.tsx:152-155` is the only surface in the
whole frontend that prints a raw author id (verified: a repo-wide grep for `"Creado por"`
returns this file plus Playwright snapshot artefacts). Replace:

```tsx
// before — InfoTab.tsx:152-155
<InfoRow label="Creado por usuario ID">
  <span className="font-mono text-xs text-mid-gray">{event.created_by_user_id}</span>
</InfoRow>

// after
<InfoRow label="Creado por">
  <ActorChip userId={event.created_by_user_id} />
</InfoRow>
```

All *new* author surfaces (history rows, coach cards, session coaches, "aprobado por",
"generado por", "importado por", "registrado por A, editado por B") use the same component
so there is exactly one place where an unresolvable actor is worded.

---

## 8. History surfaces (UI only)

Payload, filters and sentence templates: `contracts/audit-log-api.md`. This contract fixes
where they live and how they are reached.

### 8.1 Athlete panel — `AthleteHistoryPanel` (FR-007, US7 AS6)

| Item | Value |
|---|---|
| File | `frontend/src/components/athletes/AthleteHistoryPanel.tsx` |
| Host | `frontend/src/routes/athletes/AthleteDetailPage.tsx` — new `"history"` member of `Tab` / `VALID_TABS` (`:68-83`), new tab button in the tab row (`:598-701`), rendered `{activeTab === "history" && …}` |
| Visibility | `{!isParent && …}`, the same guard the "Boletines" tab uses at `frontend/src/routes/athletes/AthleteDetailPage.tsx:636-645`. A parent never sees the tab **and** the endpoint refuses them (defence in depth). |
| Deep link | `?tab=history`, handled for free by `parseTabParam` (`frontend/src/routes/athletes/AthleteDetailPage.tsx:85-91`) once `"history"` is in `VALID_TABS` |
| Loading | lazy chunk like `GrowthTab` (`frontend/src/routes/athletes/AthleteDetailPage.tsx:62-66`) — the panel is not on the default tab |
| Copy | tab label **"Historial"**; empty **"Todavía no hay cambios registrados para este deportista."** |
| Test id | `athlete-tab-history`, `athlete-history-panel` |

### 8.2 Club page — `ClubHistoryPage` (FR-006)

| Item | Value |
|---|---|
| Path | `/club/historial` |
| File | `frontend/src/routes/admin/ClubHistoryPage.tsx` (per `plan.md`'s structure block) |
| Guard | `<ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>` — coach **and** admin, so it does not live under `/admin/*` |
| Nav | new `NavArea` `{ id: "gobierno", label: "Gobierno", icon: History, group: "club", roles: ["coach","admin"], matchPrefixes: ["/club"] }` in `frontend/src/lib/navigation.ts:169-200`, with item `gobierno.history` → "Historial del club" (coach + admin). The staff item (`/admin/usuarios`, admin only) is added to this same area by `contracts/staff-admin.md` — one area, two contracts, no duplicate declaration. |
| Filters | actor (`Select`, fed by `useClubStaff`), record type (`Select`), athlete (existing `AthleteCombobox`, `frontend/src/components/ai/AthleteCombobox.tsx`), `Desde`/`Hasta`; all mirrored in the query string so `?actor=7&from=…&to=…` from the activity report lands pre-filtered |
| Table | shared `Table` primitive (`frontend/src/components/ui/table.tsx`) + server-side `offset`/`limit` and a Prev/Next control (R-28); no `@tanstack/react-table` |
| Copy | title **"Historial del club"**; subtitle **"Quién hizo qué y cuándo. Visible solo para el equipo del club."**; empty **"No hay registros para los filtros seleccionados."**; detail toggle **"Ver detalle"** |
| Test ids | `club-history-page`, `club-history-filters`, `club-history-row`, `club-history-pagination` |

The "Ver historial de {nombre}" link on each coach card (§6.2) targets
`/club/historial?actor={user_id}&from={from}&to={to}`, so the report and the log always
agree on the period being read.

---

## 9. Required tests

### 9.1 Backend — `backend/tests/test_coach_activity.py`

Fixture: the two-coaches-same-club module of R-32 (coach A and coach B in club 1, coach C
in club 2, one parent). All athlete data in fixtures is synthetic.

1. coach A (member) → `200`, both coaches present.
2. admin → `200`.
3. parent → `403`.
4. athlete → `403`.
5. coach C (other club) → `403`.
6. unknown `club_id` → `404`.
7. `coach_user_id` of a non-member → `404`; of coach B → `200` with a single entry and
   **unnarrowed** `club_totals`.
8. `from > to` → `422`; 400-day window → `422`.
9. **Co-led counting**: 1 session led by A+B, 2 by A alone, 1 by B alone →
   `A.sessions.total == 3`, `B.sessions.total == 2`, `A.co_led == B.co_led == 1`,
   `club_totals.sessions.total == 4`.
10. **SC-008 reconciliation**: for a seeded month, assert
    `club_totals.sessions.{planned,executed,cancelled}` equals
    `compute_monthly_metrics(...)`'s `total_sessions_{planned,executed,cancelled}`
    (`backend/app/services/training/metrics.py:25-56`), and that
    `club_totals.sessions.total == len({session ids across all per-coach buckets})` —
    not the naive sum.
11. A coach with zero activity is present with every counter `0`.
12. A **deactivated** coach with activity in the window is present, `is_active: false`,
    name resolved (FR-013).
13. A session whose athlete was archived mid-window still counts, and its non-archived
    attendance rows still count (`data-model.md` §8.1 "must not filter").
14. Attendance rows with `archived_at IS NOT NULL` are excluded.
15. **Privacy invariant**: the serialised response contains no `first_name`/`last_name`
    of an athlete, no `athlete_id`, no `birth_date`, no free-text key; its key set equals
    the closed set of §1.2. Modelled on `backend/tests/test_privacy.py:31`.
16. **Query count**: the number of SQL statements is constant when the club has 2 coaches
    vs 5 coaches (no N+1).
17. Legacy `race_imports` row with `committed_by_user_id IS NULL` is attributed to
    `imported_by_user_id` and anchored on `imported_at`.
18. Only `status='committed'` imports count; a `dry_run` parse in the window does not.

### 9.2 Backend — regression guard for FR-031 / SC-009

`backend/tests/test_monthly_report_unchanged.py` (or an added case in the existing monthly
report test module): a snapshot of the club-wide monthly report payload — sections, figures
and signature — taken from seeded data must be identical before and after this feature. The
per-coach report must not alter `compute_monthly_metrics` in any way.

### 9.3 Frontend

| File | Asserts |
|---|---|
| `frontend/src/routes/training/CoachActivityPage.test.tsx` | renders one card per coach from MSW; period presets update `from`/`to` and refetch; the coach `Select` narrows to one card while the club totals stay whole; the history link href is `/club/historial?actor=7&from=…&to=…`; loading / empty / error+retry states |
| `frontend/src/routes/training/CoachActivityPage.a11y.test.tsx` | jest-axe zero violations, loaded **and** empty |
| `frontend/src/routes/training/ReportsListPage.test.tsx` (existing) | the new "Actividad por entrenador" link is present and points at the route; **no other change** to this page's assertions (SC-009) |
| `frontend/src/components/audit/__tests__/ActorChip.test.tsx` | resolves a name; renders "Inactivo" for a deactivated account; renders "Usuario no disponible" for an unknown id; renders "Proceso automático" for `actorKind !== "user"`; **never** renders the numeric id (regression for FR-013) |
| `frontend/src/components/competitions/tabs/InfoTab.test.tsx` (existing) | "Creado por usuario ID" is gone; the resolved name is shown |
| `frontend/src/components/athletes/__tests__/AthleteHistoryPanel.test.tsx` + `.a11y.test.tsx` | renders entries newest-first; empty state; jest-axe clean |
| `frontend/src/routes/admin/ClubHistoryPage.test.tsx` + `.a11y.test.tsx` | filters are reflected in the query string and in the request; pagination; jest-axe clean |
| `frontend/src/lib/__tests__/navigation.test.ts` (existing) | the `gobierno` area is visible to coach and admin; `isAreaActive` matches `/club/historial` |
| `frontend/src/lib/__tests__/persistAllowList.test.ts` (existing) | `["coach-activity", …]` and `["club-staff", …]` are **not** persistable |
| `frontend/src/test/msw/coachActivityHandlers.ts`, `.../usersHandlers.ts` | new synthetic handler modules in the style of `frontend/src/test/msw/growthSummaryHandlers.ts`, registered in `frontend/src/test/setup.ts:18-25`; staff names are synthetic, no minor data |

### 9.4 e2e (Playwright, blocked — see R-34)

One spec, `frontend/e2e/coach-activity.spec.ts`: sign in as `coach2`, open
`/training/reports/actividad-entrenadores`, assert both coach cards render and that the
co-led session appears in both, then follow "Ver historial" and assert the club history
loads pre-filtered by that actor. Cannot run until the three migrations importing deleted
`app.data.*` modules are fixed (R-34); tracked as a prerequisite task, not as polish.
