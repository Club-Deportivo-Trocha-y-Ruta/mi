# Contract — Concurrency and approval evidence

**Covers**: FR-010 (approval evidence survives regeneration), FR-012 (coach-note author, coach-only),
FR-013 (author display names), FR-027 (no silent overwrite), US5 (AS1–AS5), SC-006, SC-009.

**Surfaces**:

| Layer | File |
|---|---|
| Newsletter model | `backend/app/models/athlete_newsletter.py:39` |
| Newsletter schemas | `backend/app/schemas/athlete_newsletter.py:79` (`Patch`), `:210` (`Read`) |
| Newsletter router | `backend/app/routers/athlete_monthly_newsletters.py:755` (GET), `:1001` (PATCH), `:1097` (regenerate-block), `:1240` (approve), `:1277` (send), `:1359` (attach-insights) |
| Parent projection | `backend/app/services/training/stage_log.py:382-437`, `backend/app/schemas/parent_newsletter.py:37`, `backend/app/routers/parent_newsletters.py:119,214` |
| Family templates | `backend/templates/documents/pdf/athlete_stage_log.html:254-257`, `backend/templates/email/athlete_stage_log.html:212-213` |
| Monthly report model | `backend/app/models/training_session.py:218` |
| Monthly report service | `backend/app/services/training/reports.py:194-209` (regenerate), `:758-834` (`update_report_blocks`) |
| Monthly report router | `backend/app/routers/monthly_reports.py:129` (create/regenerate), `:307` (patch blocks) |
| CORS | `backend/app/main.py:58-64` |
| Studio page | `frontend/src/routes/training/AthleteNewsletterStudioPage.tsx` |
| Studio mutation | `frontend/src/hooks/training/useUpdateStageLog.ts:27-43`, `frontend/src/api/athleteNewsletters.ts:81-90` |
| Report detail page | `frontend/src/routes/training/ReportDetailPage.tsx:430-520` |

**Related contracts**: `audit-recording.md` (every row emitted here goes through `record_audit`),
`coach-activity-report.md` (`ActorRef` / `ActorChip` are shared), `audit-log-api.md` (Spanish sentences).

Column names, enums and reason codes come from `data-model.md` §4.5, §4.6, §7.3, §7.4.
Status-code decision is `research.md` R-14. Client behaviour is R-16. CORS is R-15.

> **Status-code note.** `research.md` R-14 and the "Contradictions resolved" table fix the wire
> status for a stale precondition at **409**, matching `plan.md:68,145,166`. `data-model.md` §7.3
> has been corrected to the same semantics. **409 stale (body carries `current_version`),
> 428 missing, 409 terminal state (no `current_version`); 412 is never emitted.**

---

## 1. The version token on the wire

### 1.1 Column

`athlete_monthly_newsletters.edit_version INT NOT NULL DEFAULT 1` (`data-model.md` §4.6).
The retired name `content_version` is **not** reused — `backend/alembic/versions/8b5ac1f24f61_drop_newsletter_content_version.py:52-79`
dropped it and `backend/tests/models/test_newsletter_stage_log_migration.py:110` asserts its absence.

`updated_at` is **not** a valid token: it is a bare `DateTime` (`backend/app/models/athlete_newsletter.py:153`)
and MySQL 8.4 stores it with `fsp=0`, so two saves inside the same second are indistinguishable —
exactly the US5 case.

### 1.2 Exposure on reads

`GET /api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}`
(`backend/app/routers/athlete_monthly_newsletters.py:755-771`) gains one body field and one header.

```json
{
  "id": 812,
  "athlete_id": 2,
  "year": 2026,
  "month": 8,
  "status": "draft",
  "edit_version": 4,
  "coach_note": "Este mes sostuviste el ritmo en las subidas largas.",
  "coach_note_author": { "user_id": 7, "display_name": "Ana Coach" },
  "coach_note_updated_at": "2026-09-02T15:41:08",
  "last_edited_by": { "user_id": 9, "display_name": "Bruno Coach" },
  "generated_by": { "user_id": 7, "display_name": "Ana Coach" },
  "approved_by": null,
  "approved_at": null,
  "updated_at": "2026-09-02T15:41:08"
}
```

```http
ETag: W/"4"
```

- `edit_version` is also returned by the list endpoint (`:721`) so the dashboard can pass it straight
  into a PATCH without a second fetch.
- `ActorRef` = `{ "user_id": int, "display_name": str }`, defined once in `app/schemas/audit.py`
  and reused by `audit-log-api.md` and `coach-activity-report.md`. `display_name` is
  `f"{user.first_name} {user.last_name}"` and **must resolve for deactivated accounts** (FR-013);
  it is `null` only when the FK itself is `NULL`.
- The pre-existing raw integer fields `generated_by_user_id` / `approved_by_user_id`
  (`backend/app/schemas/athlete_newsletter.py:289-291`, mirrored in
  `frontend/src/types/athleteNewsletter.types.ts:46-47`) stay for backward compatibility.
  New UI reads the `ActorRef` objects; no surface renders a bare id.
- Resolution is a single `selectinload`/join on the newsletter query — never one query per actor.

### 1.3 CORS prerequisite (R-15)

`backend/app/main.py:59-64` currently sets `allow_headers=["Authorization", "Content-Type", "Accept"]`
and no `expose_headers`, so browser JS cannot read `ETag` at all. This is not hypothetical: the race-run
ETag path (`backend/app/routers/race_analysis.py:779-814`, `frontend/src/api/raceAnalysis.ts:44-47`)
is dead code for this exact reason.

This contract needs `If-Match` in `allow_headers` and `ETag` in `expose_headers`. It does **not**
restate the block: feature 041 also adds `X-Request-Id` to the same call, and the authoritative
version — with both features' values in one snippet — lives in
**`contracts/audit-recording.md` §3.1**, which also owns the middleware ordering. Apply it from
there, once.

Shipping the precondition without that change degrades **silently** to no conflict detection —
no error, no warning, just every `PATCH` accepted. The guard is `backend/tests/test_cors_etag.py`
(§9 T21), which asserts both features' headers in a single test.

---

## 2. `PATCH /api/athletes/{athlete_id}/monthly-newsletters/{newsletter_id}`

`backend/app/routers/athlete_monthly_newsletters.py:1001-1089`. Today the handler applies every
supplied field unconditionally and commits — last write wins, which is the bug US5 exists to fix.

### 2.1 Request

```http
PATCH /api/athletes/2/monthly-newsletters/812
Authorization: Bearer <jwt>
If-Match: "4"
Content-Type: application/json

{
  "stage_overrides": { "observations": ["Sostuvo el ritmo en las subidas largas."] },
  "coach_note": "Nos vemos en la próxima válida."
}
```

Body fallback (identical semantics, R-14 alternative c) — used when the header path is unavailable:

```json
{ "expected_version": 4, "coach_note": "Nos vemos en la próxima válida." }
```

`AthleteNewsletterPatch` (`backend/app/schemas/athlete_newsletter.py:79-146`) gains:

```python
expected_version: int | None = Field(
    default=None,
    ge=1,
    description=(
        "Versión que el cliente cargó (athlete_monthly_newsletters.edit_version). "
        "Alternativa al header If-Match; exactamente uno de los dos es obligatorio."
    ),
)
```

`expected_version` is a **precondition, never a payload field**: it is stripped before the field loop
at `:1045-1074` and never written to a column.

### 2.2 Precondition resolution

| `If-Match` | `expected_version` | Result |
|---|---|---|
| absent | absent | `428` — precondition required |
| `W/"4"` or `"4"` | absent | token = `4` |
| absent | `4` | token = `4` |
| `"4"` | `4` | token = `4` |
| `"4"` | `5` | `400` — contradictory preconditions |
| `*` | any | `428` — the wildcard is refused; this endpoint has no "create if absent" mode |
| malformed (`"abc"`, `W/""`) | — | `400` |

Weak (`W/"4"`) and strong (`"4"`) forms are both accepted and compared on the numeric value only.

### 2.3 Applying the write

The whole handler body runs in one transaction. The guarded UPDATE replaces the current
implicit ORM flush at `:1085-1087`:

```sql
UPDATE athlete_monthly_newsletters
   SET <changed columns>,
       edit_version = edit_version + 1,
       last_edited_by_user_id = :actor,
       updated_at = :now
 WHERE id = :id
   AND edit_version = :expected;
```

`rowcount == 0` ⇒ conflict (§2.5). Re-reading and comparing in Python is **not** acceptable: it
reintroduces the race between the read and the write.

Order of operations, preserving today's behaviour:

1. `_verify_coach_athlete_access` (`:185`) then `_get_newsletter_or_404` (`:214`).
2. State guard — `status ∉ {draft, approved}` ⇒ `409` with the existing message (`:1035-1043`).
   This runs **before** the version check: a `sent` newsletter is terminally immutable (US5 AS5)
   and reloading would not help.
3. Field application (`:1047-1075`), including `_redact_names` on `coach_note` (`:1055-1060`).
4. When `coach_note` was in the body: set `coach_note_author_id = current_user.id` and
   `coach_note_updated_at = now` (§3).
5. When the newsletter was `approved` and content changed: clear the approval as today
   (`:1076-1079`) and emit the extra `unapprove` audit row (§5).
6. `pdf_sha256 = None` and `_rederive_stage_log` (`:1081-1083`) — unchanged.
7. The guarded UPDATE above, then `record_audit`, then one commit.

### 2.4 Success `200`

Full `AthleteNewsletterRead` with `edit_version` already incremented, plus the refreshed header:

```json
{ "id": 812, "edit_version": 5, "last_edited_by": { "user_id": 9, "display_name": "Bruno Coach" }, "status": "draft" }
```

```http
ETag: W/"5"
```

### 2.5 Errors

| Code | When | Body |
|---|---|---|
| `409` | the token does not match the stored `edit_version` (`rowcount == 0`) | `{"detail": "Otro entrenador guardó cambios en este boletín. Recarga para ver la última versión.", "current_version": 6}` |
| `409` | `status ∈ {sent, failed, outdated}` — terminal, unchanged (`:1035-1043`) | `{"detail": "Solo se puede editar un boletín en estado 'draft' o 'approved'. Estado actual: 'sent'."}` |
| `428` | neither `If-Match` nor `expected_version` supplied | `{"detail": "Falta la versión del boletín (If-Match). Recarga la bitácora antes de guardar."}` |
| `400` | malformed token, `If-Match: *`, or header/body disagreement | `{"detail": "Precondición inválida."}` |
| `422` | `coach_note` > 60 words, unknown `hidden_blocks`, `selected_race_insight_ids` not a permutation (`:1064-1072`) | unchanged |
| `403` / `404` | RBAC and existence, unchanged (`:185-231`) | unchanged |

The stale-conflict body is the **only** 409 in this router that carries `current_version`; that key is
what lets the client tell "recarga y reintenta" apart from the terminal state conflicts. 428 responses
also carry `ETag` so a client that forgot the header can recover without a second GET.

`current_version` is read in the same transaction after the failed UPDATE. It is a small integer —
no minor's data, nothing that needs redaction.

### 2.6 Which writes move `edit_version`

| Endpoint | Bumps `edit_version` | Requires the precondition |
|---|---|---|
| `PATCH .../{id}` (`:1001`) | yes | **yes** |
| `POST .../{id}/regenerate-block` (`:1097`) | yes | no |
| `POST .../{id}/approve` (`:1240`) | yes | no |
| `POST .../attach-insights` (`:1359`) | yes (when it updates an existing row) | no |
| `POST .../{id}/send` (`:1277`) | yes | no |
| `POST .../{id}/read` (parent) | no | no |
| `GET .../{id}/pdf` (`:778`) | no — read-only for the coach even when it regenerates the file | no |

Every mutating write bumps the counter (`data-model.md` §7.3), so an approval or a block regeneration
by coach B correctly invalidates coach A's stale draft. Only the free-form PATCH *demands* the
precondition: R-13 keeps the guard deliberately narrow, and the other endpoints are single explicit
actions already protected by their own state guards.

---

## 3. Coach-note authorship (FR-012)

### 3.1 Columns

`data-model.md` §4.6 — both mirror `race_results.coach_note_author_id` / `coach_note_updated_at`
(`backend/app/models/race_result.py:137-140`), the second occurrence of an existing pattern:

| Column | Type | Written by |
|---|---|---|
| `coach_note_author_id` | `FK users.id ondelete=SET NULL`, nullable | the PATCH branch at `:1055-1060`, whenever `body.coach_note is not None` |
| `coach_note_updated_at` | `DateTime`, nullable | idem |

Setting `coach_note` to `null` (the coach clears the note) **also** rewrites both columns —
the author of the deletion is the last person who touched it. It does not blank them, so
"quién la borró" stays answerable together with the `audit_log` row.

### 3.2 Exposure matrix

| Surface | `coach_note` text | `coach_note_author` | `coach_note_updated_at` |
|---|---|---|---|
| `AthleteNewsletterRead` — coach/admin (`backend/app/schemas/athlete_newsletter.py:210`) | yes | **yes** | **yes** |
| `ParentNewsletterOut` (`backend/app/schemas/parent_newsletter.py:37`) | yes | **never** | **never** |
| `to_parent_dto` allow-list (`backend/app/services/training/stage_log.py:382-401`) | `coach_note` stays in `_PARENT_DTO_KEYS:399` | **never added** | **never added** |
| Family PDF (`backend/templates/documents/pdf/athlete_stage_log.html:254-257`) | yes, under the generic heading "Nota del entrenador" | **never** | **never** |
| Family e-mail (`backend/templates/email/athlete_stage_log.html`) | yes | **never** | **never** |
| `StageLog` model (`backend/app/services/training/stage_log.py:319`) | yes | **never** — the author does not enter `stage_log_json` at all | **never** |

The note *text* is the club's institutional voice and families already read it; only the **name of the
person who wrote it** is coach-only. The family footer keeps its institutional wording
("Esta bitácora fue preparada por el entrenador de {{ club_name }}",
`backend/templates/email/athlete_stage_log.html:212`) — never a personal name.

`_PARENT_DTO_KEYS` is an explicit allow-list by design; the two new columns live on the ORM row and
never enter `StageLog`, so there are two independent barriers between them and a family surface.

### 3.3 Coach-facing copy (español neutro)

Rendered under the "Nota del entrenador" card in `BlockPanel`
(`frontend/src/components/newsletter/studio/BlockPanel.tsx:168-181`), as a `<p className="text-xs text-mid-gray">`:

- With an author: `Nota escrita por Ana Coach · 2 sep 2026`
- Edited by someone else since: `Nota escrita por Ana Coach · editada por Bruno Coach · 2 sep 2026`
- No note yet: the line is not rendered.

Dates use `formatDateMedium` (`frontend/src/lib/datetime.ts:84`, `es-CO`, `America/Bogota`).

---

## 4. Newsletter approve / unapprove actor

`approved_by_user_id` and `approved_at` already exist (`backend/app/models/athlete_newsletter.py:103-106`)
and `approve_newsletter` already writes them (`:1263-1265`). What 041 adds:

| Event | Column writes | Audit row |
|---|---|---|
| approve (`:1240-1270`) | `approved_by_user_id`, `approved_at`, `edit_version += 1` | `action=approve`, `entity_type=athlete_monthly_newsletter` |
| unapprove via content PATCH (`:1076-1079`) | `approved_by_user_id = NULL`, `approved_at = NULL`, `last_edited_by_user_id`, `edit_version += 1` | **two** rows sharing one `request_id`: `action=update` + `action=unapprove` |
| unapprove via regenerate-block (`:1221-1224`) | same | same pair, `meta_json={"block": "<block_key>"}` |
| send (`:1277`) | `sent_at`, `edit_version += 1` | `action=send`, `meta_json={"document_kind": "newsletter_email", "recipients_count": N}` |

Because the columns are cleared on unapprove, the identity of the person who *revoked* the approval
lives only in `audit_log` (`actor_user_id` on the `unapprove` row) plus `last_edited_by_user_id`.
The newsletter does **not** get `previous_approved_*` — unlike the monthly report (§5), a newsletter
is never regenerated in place after approval, and the spec asks for the surviving evidence only there.

---

## 5. Monthly report — approval evidence survives regeneration (FR-010, US5 AS4)

### 5.1 Today's defect

`monthly_reports` has `generated_by_user_id` / `generated_at`
(`backend/app/models/training_session.py:242-245`) and **no approval attribution at all**:
`update_report_blocks` only flips `status` (`backend/app/services/training/reports.py:818-819`).
The regeneration branch (`:194-209`) then overwrites `generated_by_user_id` and resets
`status = DRAFT`, so approving as coach A and regenerating as coach B erases every trace of A.

### 5.2 New columns

`data-model.md` §4.5:

| Column | Type |
|---|---|
| `updated_at` | `DateTime`, nullable, `onupdate` |
| `updated_by_user_id` | `FK users.id ondelete=SET NULL` |
| `approved_by_user_id` | `FK users.id ondelete=SET NULL` |
| `approved_at` | `DateTime`, nullable |
| `previous_approved_by_user_id` | `FK users.id ondelete=SET NULL` |
| `previous_approved_at` | `DateTime`, nullable |

### 5.3 Approve

`PATCH /api/clubs/{club_id}/monthly-reports/{year}/{month}/blocks`
(`backend/app/routers/monthly_reports.py:307-360`) with `{"status": "approved"}`.

`update_report_blocks` (`backend/app/services/training/reports.py:758`) must, when
`new_status == APPROVED` and the report was `draft`:

```python
report.status = MonthlyReportStatus.APPROVED
report.approved_by_user_id = editor_user.id
report.approved_at = now
report.updated_by_user_id = editor_user.id
report.updated_at = now
```

The existing draft→approved-only guard at `:802-806` is unchanged. `editor_user` is already a
parameter of the service (`:822-834` logs it) — it is simply never persisted today.

Audit: `action=approve`, `entity_type=monthly_report`, `meta_json={"period": "2026-03"}`.

### 5.4 Regenerate (`force_regenerate=true`)

`generate_monthly_report` (`backend/app/services/training/reports.py:60`), branch at `:194-209`.
**Copy before clearing** — the order is the contract:

```python
if existing is not None and force_regenerate:
    if existing.approved_by_user_id is not None:          # 1. preserve
        existing.previous_approved_by_user_id = existing.approved_by_user_id
        existing.previous_approved_at = existing.approved_at
    existing.approved_by_user_id = None                   # 2. clear
    existing.approved_at = None
    existing.generated_by_user_id = generator_user.id     # 3. new generator
    existing.generated_at = now
    existing.updated_by_user_id = generator_user.id
    existing.updated_at = now
    existing.status = MonthlyReportStatus.DRAFT
    ...                                                   # existing content writes, unchanged
```

Invariants:

- The `if` guard is required. Regenerating an already-`draft` report must **not** blank
  `previous_approved_*` — the pair always holds the most recent *superseded* approval
  (`data-model.md` §7.4).
- `previous_approved_*` is never exposed to parents: `monthly_reports` parent responses already strip
  `narrative_blocks` / `competition_results` / `athlete_names`
  (`backend/app/schemas/training_session.py:372-383`); the two new fields join that list.

Audit rows, one shared `request_id`: `action=update` (`entity_type=monthly_report`,
`changed_fields` including `generated_by_user_id`, `status`) **and** `action=unapprove`.
Per `VALUE_ALLOWLIST` (`data-model.md` §2.5) only `status`, `year`, `month` and
`approved_by_user_id` may carry values into `diff_json`.

### 5.5 Response

`MonthlyReportRead` (`backend/app/schemas/training_session.py:372`) gains:

```json
{
  "id": 44,
  "club_id": 1,
  "year": 2026,
  "month": 3,
  "status": "draft",
  "generated_by": { "user_id": 9, "display_name": "Bruno Coach" },
  "generated_at": "2026-09-09T14:02:11",
  "approved_by": null,
  "approved_at": null,
  "previous_approved_by": { "user_id": 7, "display_name": "Ana Coach" },
  "previous_approved_at": "2026-04-03T10:12:00",
  "updated_by": { "user_id": 9, "display_name": "Bruno Coach" },
  "updated_at": "2026-09-09T14:02:11"
}
```

The existing `generated_by_user_id: int` field (`:392`, mirrored in
`frontend/src/types/trainingSession.types.ts:262`) is kept; the `ActorRef` objects are additive.

---

## 6. Frontend — `AthleteNewsletterStudioPage` conflict UX

`frontend/src/routes/training/AthleteNewsletterStudioPage.tsx`.

### 6.1 Version plumbing

- `frontend/src/types/athleteNewsletter.types.ts:72-79` — `AthleteNewsletterPatch` gains
  `expected_version?: number`; `AthleteNewsletter` (`:30-63`) gains `edit_version: number`,
  `coach_note_author`, `coach_note_updated_at`, `last_edited_by`, and the `ActorRef` variants of
  `generated_by` / `approved_by`.
- `patchAthleteNewsletter` (`frontend/src/api/athleteNewsletters.ts:81-90`) sends
  `headers: { "If-Match": `W/"${expectedVersion}"` }`. If the R-15 CORS work is deferred, it sends
  `expected_version` in the body instead — same backend, no schema change.
- `useUpdateStageLog` (`frontend/src/hooks/training/useUpdateStageLog.ts:27-43`) takes the version
  from the cached newsletter and adds
  `retry: (_c, err) => ![400, 409, 428].includes(err.response?.status)`. Retrying a stale
  precondition fails identically forever (R-16).
- `parseApiError` (`frontend/src/api/athleteNewsletters.ts:30-43`) already surfaces `detail` on 409;
  it gains a 428 branch returning the server `detail`.

### 6.2 State

`AthleteNewsletterStudioPage` gains one state slot next to `overridesDraft` (`:111`):

```ts
const [conflict, setConflict] = useState<{ currentVersion: number | null } | null>(null);
```

`onError` on every `updateStageLog.mutate` call site (`:154`, `:164`, `:179`, `:188`) branches:
status `409` **with** a `current_version` key ⇒ `setConflict({ currentVersion: detail.current_version })`;
anything else ⇒ the existing `showToast("error", …)`.

**The local draft is never discarded on conflict.** `overridesDraft` keeps the coach's typing, and the
sync effect at `:131-140` must not fire while `conflict !== null` (add `if (conflict) return;`) — otherwise
a background refetch would silently replace what the coach is looking at. Only the explicit
"Recargar" action clears the draft.

### 6.3 Surfaces

Two surfaces, both required:

1. **Blocking `AlertDialog`** (`frontend/src/components/ui/alert-dialog.tsx`), opened when
   `conflict !== null` — R-16's "conflict message and a reload action".
   - Title: `Otro entrenador guardó cambios`
   - Body: `Otro entrenador guardó cambios en este boletín mientras lo editabas. Tu texto sigue acá: cópialo si lo necesitas y luego recarga para trabajar sobre la última versión.`
   - `AlertDialogAction` — `Recargar`: `queryClient.invalidateQueries({ queryKey: ["athlete-newsletter", userId, athleteId, newsletterId] })`, then `setConflict(null)` and let the sync effect reseed `overridesDraft` from the server.
   - `AlertDialogCancel` — `Seguir editando`: closes the dialog, leaves `conflict` set (so the banner stays) and leaves the draft untouched.
2. **Pinned `Alert variant="warning"`** (`frontend/src/components/ui/alert.tsx`), rendered above the
   header block (`:364`) for as long as `conflict !== null`, so the coach who chose "Seguir editando"
   still sees the state and can copy their text:
   - `Este boletín cambió en el servidor. Guardar volverá a fallar hasta que recargues.` + a `Recargar` button.

There is **no** automatic refetch, no optimistic update and no three-way merge: the backend replaces
`stage_overrides` wholesale (documented at `AthleteNewsletterStudioPage.tsx:18-22`), so merging would
be a far larger behavioural change than the spec asks for, and a rollback flash on a draft another
human is co-editing is exactly the ambiguity US5 removes.

### 6.4 Coach-note author line

Rendered by `BlockCard` for the "Nota del entrenador" card
(`frontend/src/components/newsletter/studio/BlockPanel.tsx:168-181`) — `BlockCardProps`
(`BlockCard.tsx:34-54`) gains `byline?: string`. Copy per §3.3.

### 6.5 Copy, a11y and test ids

| Item | Value |
|---|---|
| Dialog title | `Otro entrenador guardó cambios` |
| Dialog body | `Otro entrenador guardó cambios en este boletín mientras lo editabas. Tu texto sigue acá: cópialo si lo necesitas y luego recarga para trabajar sobre la última versión.` |
| Primary action | `Recargar` |
| Secondary action | `Seguir editando` |
| Banner | `Este boletín cambió en el servidor. Guardar volverá a fallar hasta que recargues.` |
| 428 toast | `Falta la versión del boletín. Recarga la bitácora antes de guardar.` |
| Report evidence line | `Aprobado anteriormente por {nombre} el {fecha}` |
| Report current approval | `Aprobado por {nombre} el {fecha}` |

- Both actions are `min-h-12` (48 px, Constitution III), keyboard-operable, with visible focus rings.
- The `AlertDialog` traps focus, is dismissible by Escape (equivalent to "Seguir editando") and by the
  explicit cancel affordance.
- The banner is `role="alert"`; the dialog carries `role="alertdialog"` from the primitive.
- `jest-axe`: zero violations for the studio page with `conflict` set and cleared.
- Stable test ids: `newsletter-conflict-dialog`, `newsletter-conflict-reload`,
  `newsletter-conflict-keep-editing`, `newsletter-conflict-banner`, `coach-note-byline`,
  `report-previous-approval`.

---

## 7. Frontend — report approval evidence

`frontend/src/routes/training/ReportDetailPage.tsx:445-520` (coach editor header).

- Under the `StatusBadge` (`:100-110`): when `report.approved_by` is set, render
  `Aprobado por {nombre} el {fecha}`.
- When `report.previous_approved_by` is set **and** `report.status === "draft"`, render
  `Aprobado anteriormente por {nombre} el {fecha}` as `text-xs text-mid-gray`,
  `data-testid="report-previous-approval"`. Both lines can be present at once after a
  re-approval following a regeneration.
- Dates via `formatDateMedium` (`frontend/src/lib/datetime.ts:84`).
- Parents never reach this page; the parent branch of `MonthlyReportRead` never carries the fields.

---

## 8. Non-functional

- One extra guarded UPDATE per PATCH; no extra round trip. Well inside the p95 ≤ 1500 ms write budget.
- Actor names come from joins already loaded by the endpoint's own query — no N+1 (Constitution IV).
- No new runtime dependency, no new component pattern: `Alert`, `AlertDialog` and `Table` are already
  installed under `frontend/src/components/ui/`.
- No response field added here carries a minor's name, birth date, measurement or narrative:
  `edit_version` and `current_version` are integers, `ActorRef.display_name` is an **adult staff**
  name, and the `audit_log` rows emitted carry only the allow-listed keys of `data-model.md` §2.5.

---

## 9. Required tests

### Backend — `backend/tests/routers/test_newsletter_concurrency.py` (new)

Uses the two-coaches-same-club fixture of `research.md` R-32.

1. **Race → 409 (regression; fails on today's code).** Coach A and coach B both `GET` the newsletter
   at `edit_version = 4`. A PATCHes a `coach_note` → `200`, `edit_version = 5`. B PATCHes
   `stage_overrides` with `If-Match: "4"` → `409`, body `detail` + `current_version: 5`, and a re-read
   proves A's note survived untouched. This is SC-006 in executable form.
2. Happy path: `If-Match` matching → `200`, `edit_version` incremented by exactly 1,
   `last_edited_by_user_id == actor.id`, `ETag: W/"5"`.
3. `expected_version` body fallback behaves identically to the header.
4. Missing precondition → `428`; response still carries `ETag`.
5. `If-Match: *`, malformed token, and header≠body → `400`.
6. Terminal state wins over the version check: `status = sent` + a **valid** `If-Match` → `409` with
   the state message and **no** `current_version` key.
7. `edit_version` bumps on `approve`, `regenerate-block`, `attach-insights` and `send`, and a PATCH
   holding the pre-approval token is then refused.
8. Concurrency under the real dialect: same as (1) but marked `@pytest.mark.mysql`, two sessions,
   asserting exactly one UPDATE takes effect.

### Backend — `backend/tests/routers/test_newsletter_coach_note_author.py` (new)

9. Saving `coach_note` writes `coach_note_author_id` and `coach_note_updated_at`; coach B editing it
   rewrites both to B.
10. **Author visible to coach only.** `AthleteNewsletterRead` for coach and admin contains
    `coach_note_author`; `ParentNewsletterOut` for the linked parent
    (`backend/app/routers/parent_newsletters.py:167-183`) contains the note text and **no** key
    matching `coach_note_author*`, and no staff surname anywhere in the serialized body.
11. `to_parent_dto` output keys are exactly `_PARENT_DTO_KEYS`
    (`backend/app/services/training/stage_log.py:382-401`) — an author key added to `StageLog` in the
    future does not leak.
12. **Family PDF carries no coach name.** Render `athlete_stage_log.html` with a note authored by a
    coach whose synthetic surname is a distinctive token; assert the extracted PDF text contains the
    note text and the generic heading "Nota del entrenador", and contains the coach's surname
    **zero** times. Same assertion against the family e-mail body.
    Idiom: `backend/tests/test_newsletter_privacy.py`.
13. Clearing the note (`coach_note: null`) still records the actor and time.

### Backend — `backend/tests/test_monthly_report_approval_evidence.py` (new)

14. **Regenerate preserves evidence (regression; fails on today's code).** Approve as coach A
    (`approved_by_user_id == A`), regenerate as coach B with `force_regenerate=true`; assert
    `previous_approved_by_user_id == A`, `previous_approved_at` == A's timestamp,
    `generated_by_user_id == B`, `approved_by_user_id is None`, `status == draft`. This is US5 AS4.
15. Regenerating an already-`draft` report does **not** blank a pre-existing `previous_approved_*`.
16. Approve → regenerate → approve → regenerate: `previous_approved_*` always holds the most recent
    superseded approval, never the first one.
17. Approving writes `approved_by_user_id` / `approved_at` / `updated_by_user_id` (no attribution at
    all today).
18. Audit: the regeneration emits `update` + `unapprove` sharing one `request_id`, and no
    `diff_json` key falls outside `VALUE_ALLOWLIST["monthly_report"]`.
19. `previous_approved_*` is absent from the parent projection of `MonthlyReportRead`.
20. **SC-009 guard**: the DOCX/PDF produced for a fixed month before and after this change is
    byte-identical in section headings and signature block — the approval evidence is UI-only.

### Backend — `backend/tests/test_cors_etag.py` (new)

21. A preflight `OPTIONS` for `PATCH` with `Access-Control-Request-Headers: if-match` is allowed, and
    a `GET` response advertises `access-control-expose-headers` containing **both** `ETag` and
    `X-Request-Id` (the single CORS edit of `contracts/audit-recording.md` §3.1 carries both values;
    asserting only one lets the other be dropped). Without this the whole feature degrades
    silently (R-15). `audit-log-api.md` §13 T11 defers its cross-origin assertion to this test.

### Frontend — `frontend/src/routes/training/AthleteNewsletterStudioPage.test.tsx` (extended)

22. MSW returns `409` with `{detail, current_version}` on PATCH → `newsletter-conflict-dialog` is
    shown with the exact Spanish copy of §6.5.
23. **The draft is not lost**: after the 409, the edited text is still in the textarea, no refetch
    fired, and `overridesDraft` is unchanged.
24. "Seguir editando" closes the dialog, keeps `newsletter-conflict-banner` mounted and keeps the draft.
25. "Recargar" invalidates the query exactly once, clears the banner, and the reseeded draft matches
    the server payload.
26. `428` renders the missing-version toast, not the conflict dialog.
27. The mutation does not retry on 400/409/428 (assert a single network call).
28. `coach-note-byline` renders `Nota escrita por … · …` for coach and is absent when there is no note.
29. `jest-axe` — zero violations with the conflict dialog open and closed.

### Frontend — `frontend/src/routes/training/ReportDetailPage.test.tsx` (extended)

30. `previous_approved_by` + `status: "draft"` → `report-previous-approval` reads
    `Aprobado anteriormente por Ana Coach el 03 abr 2026`; absent when the field is `null`.
31. No surface on either page renders a bare numeric user id (FR-013).
