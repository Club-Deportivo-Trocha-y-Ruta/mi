# Contract — audit-log read API (`GET /api/clubs/{club_id}/audit-log`, `GET /api/athletes/{athlete_id}/audit-log`, `GET /api/audit/reason-codes`)

**Covers**: FR-006 (club history, filtered, newest first, actor names resolved, parents and
other-club coaches refused), FR-007 (per-athlete "historial" panel), FR-008 (plain-Spanish
sentence, raw identifiers and field names only in an expandable detail), FR-013 (author
display name, including deactivated accounts), FR-003 (no minor's PII in any entry, and the
closed reason catalogue every picker of this feature reads — §14).

**Router**: `backend/app/routers/audit.py` (new). Three `APIRouter` objects in one module —
`clubs_router`, `athletes_router` and `catalog_router` (prefix `/api/audit`, §14) — mounted in
`backend/app/main.py` next to the existing club/athlete pairs (`app/main.py:104`, `:112-114`,
which already prove the "one module, several prefixed routers" idiom). The
`/clubs/{club_id}/coach-activity` route of this module (FR-032) rides on `clubs_router` and is
specified in `contracts/coach-activity-report.md`; it is out of scope here.

**Reads only**. These endpoints never write, and in particular they never write an audit row
of their own — FR-005 excludes plain reads.

**Depends on**: `data-model.md` §1 (table `audit_log`), §2 (`AuditAction`, `AuditActorKind`,
`AuditEntityType`, `AuditReasonCode`, `AUDIT_REASON_LABELS`, `VALUE_ALLOWLIST`), §8.3 Q1/Q2
(the two queries), and `contracts/audit-recording.md` (which `(entity_type, action)` pairs are
actually produced). No column, enum value or label is redefined here.

---

## 1. Surface

| Method | Path | Who | Returns | Serves |
|---|---|---|---|---|
| `GET` | `/api/clubs/{club_id}/audit-log` | admin, coach **of that club** | `AuditListOut` | FR-006, US1 AS8 |
| `GET` | `/api/athletes/{athlete_id}/audit-log` | admin, coach **of the athlete's club** | `AuditListOut` | FR-007, US7 AS6 |
| `GET` | `/api/audit/reason-codes` | admin, coach (any club — the catalogue carries no club data) | `AuditReasonCodeListOut` | FR-003, and the pickers of FR-015 / FR-017 / FR-020 (§14) |

The two audit-log endpoints share one response schema, one query builder, one sentence renderer
and one RBAC helper. The athlete endpoint is the club endpoint with `athlete_id` pinned and the
club predicate dropped (the athlete determines the club — `data-model.md` §8.3 Q2). The third
endpoint is a pure catalogue read that touches no table at all (§14).

Deliberately **not** in this contract: any `POST`/`PATCH`/`DELETE` on `audit_log` (FR-004
forbids them; the single removal path is the purge CLI of `contracts/retention-purge.md`), and
any parent-facing variant (FR-006 refuses parents outright — there is no filtered parent view
to build).

---

## 2. `GET /api/clubs/{club_id}/audit-log`

### 2.1 Query parameters

| Name | Type | Default | Bounds | Notes |
|---|---|---|---|---|
| `actor_user_id` | `int` | — | `ge=1` | FR-006 "filter by actor". Served by `ix_audit_actor_time`. |
| `athlete_id` | `int` | — | `ge=1` | FR-006 "filter by athlete". Archived athletes are **not** excluded (Edge Case spec.md:176). |
| `entity_type` | `AuditEntityType` | — | closed enum | FR-006 "filter by record type". Unknown value → `422` from FastAPI's own enum validation. |
| `action` | `AuditAction` | — | closed enum | Not required by FR-006, but free: `action` is on every row and the filter is what makes "documentos aprobados o enviados" (FR-032) reachable from this endpoint. |
| `from` | `date` | — | — | Inclusive. Translated to `occurred_at >= datetime(from, 00:00:00)` (naive UTC). |
| `to` | `date` | — | — | **Inclusive of the whole day**: translated to `occurred_at < datetime(to + 1 day, 00:00:00)`. Documented explicitly because a coach filtering `to=2026-03-31` expects March 31 entries to appear. |
| `request_id` | `str` | — | 32 hex chars | Groups every row of one logical operation (FR-002, US1 AS5). Served by `ix_audit_request_id`. A malformed value returns an empty page, never `422` — it is an opaque token pasted from the detail panel. |
| `limit` | `int` | `25` | `ge=1, le=50` | Ceiling fixed by `data-model.md` §8.3 ("limit ≤ 50") and by the p95 ≤ 500 ms read budget. |
| `offset` | `int` | `0` | `ge=0` | |

`from` is a Python reserved word, so the signature must alias it:

```python
from_date: date | None = Query(default=None, alias="from"),
to_date:   date | None = Query(default=None, alias="to"),
```

Validation: `from > to` → `422` with `{"detail": "El rango de fechas es inválido: 'from' debe ser anterior o igual a 'to'."}`.

**Pagination style**: `limit`/`offset` + `total`, not a cursor and not `page`/`page_size`.
Fixed by research `R-28` ("cursor pagination — rejected, offset/limit composes with arbitrary
filters and is what every existing paginated endpoint uses") and by the dominant repo idiom
(`backend/app/routers/race_imports.py:1196-1200`, `backend/app/routers/monthly_reports.py:219-220`,
`backend/app/routers/training_sessions.py:328-329`, `backend/app/routers/athlete_race_analysis.py:322-323`).
`backend/app/routers/activities.py:122-123` is the lone `page`/`page_size` outlier and is not
copied.

### 2.2 Request

```http
GET /api/clubs/1/audit-log?actor_user_id=7&entity_type=training_session&from=2026-03-01&to=2026-03-31&limit=25&offset=0 HTTP/1.1
Authorization: Bearer <access token>
Accept: application/json
```

### 2.3 Response `200`

```json
{
  "items": [
    {
      "id": 4821,
      "occurred_at": "2026-03-14T22:05:41.482913",
      "actor_user_id": 7,
      "actor_kind": "user",
      "actor_role": "coach",
      "actor_display_name": "Ana Coach",
      "action": "cancel",
      "entity_type": "training_session",
      "entity_id": 318,
      "entity_label": "la sesión de entrenamiento",
      "club_id": 1,
      "athlete_id": null,
      "reason_code": "cancel_weather",
      "reason_label": "Clima adverso",
      "sentence_es": "Ana Coach canceló la sesión de entrenamiento del 15 de marzo de 2026 (Clima adverso).",
      "request_id": "9f1c2b7a4d5e46a8b0c3d9e2f1a7b6c4",
      "detail": {
        "changed_fields": ["status", "cancellation_reason_code"],
        "changed_field_labels": ["Estado", "Motivo de cancelación"],
        "diff": {
          "status": { "before": "programada", "after": "cancelada" }
        },
        "meta": { "event_date": "2026-03-15" }
      }
    },
    {
      "id": 4820,
      "occurred_at": "2026-03-14T21:58:03.117204",
      "actor_user_id": 7,
      "actor_kind": "user",
      "actor_role": "coach",
      "actor_display_name": "Ana Coach",
      "action": "export",
      "entity_type": "athlete",
      "entity_id": 12,
      "entity_label": "la ficha del deportista",
      "club_id": 1,
      "athlete_id": 12,
      "reason_code": null,
      "reason_label": null,
      "sentence_es": "Ana Coach descargó el PDF de crecimiento de un deportista.",
      "request_id": "3d0aa1c9be7f42d1a6e58b2c7f04d913",
      "detail": {
        "changed_fields": [],
        "changed_field_labels": [],
        "diff": null,
        "meta": { "document_kind": "growth_pdf" }
      }
    }
  ],
  "total": 143,
  "limit": 25,
  "offset": 0
}
```

Values above are illustrative. `entity_id: 12` and `athlete_id: 12` are synthetic.

### 2.4 Ordering

`ORDER BY occurred_at DESC, id DESC` — `data-model.md` §8.3 Q1. `id` is the tie-breaker so the
total order is deterministic even when two coaches act inside the same microsecond, which is
what makes `offset` pagination stable.

### 2.5 Variants

| Situation | Response |
|---|---|
| Club has no entries yet, or filters match nothing | `200` with `items: []`, `total: 0`; the UI shows the shared `EmptyState`, never an error |
| `offset` beyond `total` | `200` with `items: []` and the real `total` (no `404`) |
| Club id does not exist, caller is admin | `200` with `items: []`, `total: 0`. No existence check is performed: a coach can never reach a foreign club id (§4), so there is nothing to probe, and adding a `SELECT clubs` would spend a query the read budget does not need |
| Row whose `actor_kind != user` | `actor_user_id`, `actor_role` are `null`; `actor_display_name` is the actor-kind label (§6.2) |
| Row whose `athlete_id` points at an archived athlete | returned normally (Edge Case spec.md:176) |
| Row produced by a deactivated coach | returned normally with the name resolved — the FK is `ondelete=RESTRICT` (`data-model.md` §1) so the `users` row always survives (FR-013) |
| Row whose `(entity_type, action)` has no exact template | `sentence_es` falls back to the generic sentence (§7.4) — never `null`, never a raw `{placeholder}` |

---

## 3. `GET /api/athletes/{athlete_id}/audit-log`

Same schema, same ordering, same pagination. Differences only:

| Aspect | Value |
|---|---|
| Path parameter | `athlete_id` |
| Base predicate | `audit_log.athlete_id = :athlete_id` (no `club_id` predicate — `data-model.md` §8.3 Q2) |
| Query parameters | `actor_user_id`, `entity_type`, `action`, `from`, `to`, `request_id`, `limit`, `offset` — the `athlete_id` filter is dropped (it is the path) |
| `limit` default | `15` (the panel is a card inside the athlete detail page, not a full-page table); same `le=50` ceiling |
| Index used | `ix_audit_athlete_time` |
| Archived athlete | still readable by admin and coach of the club — the panel is exactly where an archive/restore history must be visible (US2 AS2) |

```http
GET /api/athletes/12/audit-log?limit=15&offset=0 HTTP/1.1
Authorization: Bearer <access token>
```

The response body is byte-identical in shape to §2.3.

---

## 4. RBAC

### 4.1 Matrix

| Caller | `GET /api/clubs/{club_id}/audit-log` | `GET /api/athletes/{athlete_id}/audit-log` | `GET /api/audit/reason-codes` | Source of truth |
|---|---|---|---|---|
| `admin` | `200` — any club | `200` — any athlete | `200` | FR-006, FR-007, FR-003 |
| `coach`, member of the club | `200` | `200` when `athlete.club_id` ∈ their coach clubs | `200` | FR-006 ("Administrators and coaches of the club") |
| `coach`, **other** club | `403` | `403` | `200` — the catalogue is club-agnostic (§14.1) | FR-006, US1 AS7 |
| `coach` with no club membership | `403` | `403` | `200` | US3 AS3 rationale — a clubless coach sees no club data; the catalogue holds none (§14.1) |
| `parent` (even for their own child) | `403` | `403` | `403` | FR-006, US1 AS6 |
| `athlete` role account | `403` | `403` | `403` | not granted anywhere in the spec |
| no / invalid / expired token | `401` | `401` | `401` | `backend/app/dependencies.py:27-72` |

`can_view_audit` (§4.2) guards the first two columns only; the catalogue endpoint has nothing to
scope and stops at `require_role([UserRole.admin, UserRole.coach])`.

### 4.2 New permission helper

`backend/app/services/permissions.py` gains one **synchronous, DB-free** helper (name fixed by
`plan.md` → "permissions.py # can_view_audit"):

```python
def can_view_audit(user: User, club_id: int) -> bool:
    """FR-006/FR-007: solo admin y coaches del propio club leen el historial.

    Síncrona a propósito: `get_current_user` ya trae `club_memberships` con
    `selectinload` (app/dependencies.py:60-64), así que resolver la membresía
    en memoria evita el SELECT extra que sí paga `user_club_role`
    (app/services/permissions.py:76-88) y deja el endpoint en 2 queries.
    """
    if user.role == UserRole.admin:
        return True
    if user.role == UserRole.coach:
        return club_id in coach_club_ids(user)
    return False
```

It reuses `coach_club_ids` (`backend/app/services/permissions.py:71-73`), which already filters
`role_in_club == ClubRole.coach`.

**Do not reuse `can_view_monthly_report`** (`backend/app/services/permissions.py:205-226`): it
returns `True` for every parent on the aggregate view, which is precisely the behaviour FR-006
forbids. That function is the nearest-looking helper in the file and is the likely copy-paste
mistake; the denied-path tests of §13 exist to catch it.

### 4.3 Wiring, and the ordering trap on the athlete endpoint

`verify_athlete_access` (`backend/app/dependencies.py:88-98`) **grants parents access to their
linked athletes** — it is the wrong gate on its own for FR-007. Two guards are needed, and the
role guard must run *first* so a parent probing an unknown `athlete_id` gets `403`, not the
`404 "Atleta no encontrado"` of `backend/app/dependencies.py:106-110` (which would confirm
whether an id exists).

```python
@athletes_router.get(
    "/{athlete_id}/audit-log",
    response_model=AuditListOut,
    dependencies=[Depends(require_role([UserRole.admin, UserRole.coach]))],
)
async def list_athlete_audit_log(
    athlete: Athlete = Depends(verify_athlete_access),   # 404 desconocido, 403 coach de otro club
    ...
)
```

FastAPI resolves the decorator's `dependencies=[...]` before the path-operation's own
parameters, so `require_role` (`backend/app/dependencies.py:77-85`, detail
`"No tienes permisos para esta acción"`) fires before the athlete is loaded. The coach's
club scoping is then handled by `verify_athlete_access` itself
(`backend/app/dependencies.py:115-125`, detail `"No tienes acceso a este atleta"`), so no
second club check is needed on this route.

The club endpoint takes the plain `get_current_user` and calls `can_view_audit(current_user, club_id)`,
mirroring the shape of `backend/app/routers/monthly_reports.py:221-230` but with the audit
helper instead of the report one.

### 4.4 Refusal copy (español neutro)

| Case | Status | `detail` |
|---|---|---|
| parent / athlete role on either endpoint | `403` | `"No tienes permisos para esta acción"` (reused verbatim from `backend/app/dependencies.py:81`) |
| coach of another club, club endpoint | `403` | `"No tienes permisos para ver el historial de este club."` |
| coach of another club, athlete endpoint | `403` | `"No tienes acceso a este atleta"` (reused verbatim from `backend/app/dependencies.py:123`) |
| unknown athlete, admin or coach | `404` | `"Atleta no encontrado"` (reused verbatim from `backend/app/dependencies.py:109`) |

A refusal never states whether the club, the athlete or any entry exists.

---

## 5. Pydantic schemas — `backend/app/schemas/audit.py` (new)

Pydantic v2, project style (`backend/app/schemas/growth.py:82-96`). The enums are imported from
`backend/app/models/audit_log.py` (`data-model.md` §2), never redeclared.

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.audit_log import AuditAction, AuditActorKind, AuditEntityType
from app.models.user import UserRole

#: Tipos admitidos dentro de `diff` — garantizados por VALUE_ALLOWLIST
#: (data-model §2.5): enums/estados, banderas, fechas de evento, FKs,
#: contadores, y la única lista permitida (`hidden_blocks`).
DiffScalar = str | int | float | bool | list[str] | None


class AuditDiffValue(BaseModel):
    """Valor antes/después de un campo permitido por la allow-list."""

    before: DiffScalar = None
    after: DiffScalar = None


class AuditEntryDetail(BaseModel):
    """Detalle expandible ("Ver detalle"). FR-008: los nombres crudos de
    columna y los identificadores viven aquí, nunca en `sentence_es`.
    """

    changed_fields: list[str] = Field(default_factory=list)
    changed_field_labels: list[str] = Field(default_factory=list)  # 1:1 con changed_fields
    diff: dict[str, AuditDiffValue] | None = None
    meta: dict[str, Any] | None = None


class AuditEntryOut(BaseModel):
    """Una entrada del historial, lista para renderizar.

    Privacidad (Ley 1581, FR-003): el único nombre propio que puede aparecer
    es el del actor (adulto: coach o administrador). Ningún campo lleva el
    nombre, la fecha de nacimiento ni datos del deportista; el atleta viaja
    solo como `athlete_id`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime           # UTC naive, ISO 8601 con microsegundos
    actor_user_id: int | None = None
    actor_kind: AuditActorKind
    actor_role: UserRole | None = None
    actor_display_name: str         # resuelto por JOIN o etiqueta de actor automático
    action: AuditAction
    entity_type: AuditEntityType
    entity_id: int
    entity_label: str               # etiqueta es-CO del tipo de registro
    club_id: int | None = None
    athlete_id: int | None = None
    reason_code: str | None = None
    reason_label: str | None = None  # AUDIT_REASON_LABELS[reason_code]
    sentence_es: str                # frase FR-008, siempre presente
    request_id: str
    detail: AuditEntryDetail


class AuditListOut(BaseModel):
    """Página del historial, más reciente primero."""

    items: list[AuditEntryOut]
    total: int
    limit: int
    offset: int
```

`AuditListOut` carries `limit`/`offset` alongside `total`; `ImportListResponse`
(`backend/app/schemas/race_imports.py:361-367`) returns only `items`/`total` and forces the
client to remember what it asked for. Echoing the window back is what lets the shared
Prev/Next + "Página N de M" control of research `R-28` render from the response alone.

Frontend mirrors (`contracts/coach-activity-report.md` covers the shared UI pieces):
`frontend/src/schemas/audit.ts` (Zod, same field names) and `frontend/src/types/audit.types.ts`.

---

## 6. `actor_display_name` — resolution

### 6.1 Human actors: one `LEFT JOIN`, never a second round trip

```sql
SELECT a.*, u.first_name, u.last_name
  FROM audit_log a
  LEFT JOIN users u ON u.id = a.actor_user_id
 WHERE ...
 ORDER BY a.occurred_at DESC, a.id DESC
 LIMIT :limit OFFSET :offset
```

`display_name = f"{first_name} {last_name}".strip()`, the formatting already used for the
importer chip at `backend/app/routers/race_imports.py:1243-1247`. Two differences from that
site, both deliberate:

- **One `LEFT JOIN`, not a second batched `SELECT users`.** `data-model.md` §8.3 Q1 fixes the
  budget at exactly two queries (rows + count); the batched-users pattern would make it three.
- **`LEFT`, not `INNER`.** `actor_user_id` is `NULL` for every automated actor
  (`data-model.md` §1); an inner join would silently drop those rows and break US1 AS4.

`users.first_name` / `users.last_name` are `NOT NULL` (`backend/app/models/user.py:34-35`) and
the actor FK is `ondelete=RESTRICT`, so the name always resolves — including for a deactivated
coach (`users.is_active = false`, `backend/app/models/user.py:38`), which is FR-013's explicit
requirement. Deactivation state is **not** exposed by this endpoint: the reader needs the name,
not the account's current status, and the staff screen already owns that.

The name is **never denormalised into the row** (`data-model.md` §1, `actor_user_id` note): a
stored name would be a second copy to keep in sync and, for a future athlete-role account,
a stored minor's name.

### 6.2 Automated actors: fixed labels, resolved from `actor_kind`

| `actor_kind` | `actor_display_name` | Typical writer |
|---|---|---|
| `user` | `"{first_name} {last_name}"` | any authenticated request |
| `system` | `"Sistema"` | lifespan orphan-run reconciliation, boot backfills, LangGraph completion callbacks |
| `webhook` | `"Servicio externo"` | Resend delivery webhook, Strava webhook |
| `cron` | `"Tarea programada"` | daily Strava reconcile, monthly retention purge |

Defensive case: `actor_kind = user` but the join yields no row (impossible under `RESTRICT`;
possible against a hand-edited database) → `"Usuario no disponible"`, and the row is still
returned. Never `null`, never `"user#7"` — FR-013 forbids a raw identifier reaching the reader.

---

## 7. Spanish sentence catalogue (FR-008)

### 7.1 Where the sentence is built — and the delta from research `R-08`

`sentence_es` is **composed at read time and never stored** — the load-bearing half of `R-08`
(a stored sentence couples storage to copy and is the exact vector by which a name could reach
a row). This contract moves the composition from the client to the response builder
(`backend/app/services/audit.py::render_sentence`). Rationale for the delta:

1. **One place to audit.** The FR-003 privacy scan already runs server-side over `diff_json`
   and `meta_json`; rendering there lets the same scan assert the *rendered sentence* is
   PII-free (§13 T8). A client-side renderer is invisible to that test.
2. **One place to keep in sync** with the `(entity_type, action)` pairs the instrumentation
   matrix produces, enforced by the coverage test of §13 T7. A TypeScript map in
   `frontend/src/components/audit/` cannot be checked against the Python action catalogue.
3. **No behaviour is lost.** The frontend keeps the `Collapsible` "Ver detalle" of `R-08` for
   `changed_fields`/`diff`/`entity_id`, and keeps rendering `occurred_at` with
   `frontend/src/lib/datetime.ts` (§11). Only the sentence string moves.

`research.md` R-08 must be updated to record this; the invariant it protects is unchanged.

### 7.2 Placeholders — the closed set

A template may only interpolate these. Anything else is a defect.

| Placeholder | Source | Example |
|---|---|---|
| `{actor}` | `actor_display_name` (§6) | `Ana Coach` |
| `{motivo}` | `AUDIT_REASON_LABELS[reason_code]` (`data-model.md` §2.4) | `Clima adverso` |
| `{periodo}` | `meta_json.period` (`"2026-03"`) → month name + year | `marzo de 2026` |
| `{documento}` | `AUDIT_DOCUMENT_LABELS[meta_json.document_kind]` (§7.6) | `el PDF de crecimiento` |
| `{fecha}` | `meta_json.event_date`, else the allow-listed `diff.scheduled_date.after` / `diff.start_at.after` | `15 de marzo de 2026` |
| `{rol}` | `UserRole` label from `diff.role.after` or `meta_json.role` | `entrenador` |
| `{rol_club}` | `ClubRole` label from `diff.role_in_club.after` | `entrenador` |
| `{conteo}` | `meta_json.removed_count`, rendered **with its noun** by `format_count_es` (§7.3) | `143 registros` · `1 registro` |

Role labels (es-CO): `admin` → "administrador", `coach` → "entrenador", `parent` → "familia",
`athlete` → "deportista" (same four values in `UserRole`, `backend/app/models/user.py:17-21`,
and `ClubRole`, `backend/app/models/club.py:17-21`).

**Never a placeholder, at any level**: the athlete's name, the target account's name or email,
free text, a measurement, a narrative, `entity_id`. The sentence names exactly **one** person —
the actor, always an adult (coach or administrator). The athlete travels as `athlete_id` and the
coach-facing UI resolves the name from the athlete list it already holds, so the audit response
itself stays free of minors' PII.

### 7.3 Building blocks

**Action verbs** (`AUDIT_ACTION_VERBS`, third person singular, pretérito):

| Action | Verb | Action | Verb |
|---|---|---|---|
| `create` | creó | `cancel` | canceló |
| `update` | actualizó | `execute` | ejecutó |
| `archive` | archivó | `link` | vinculó |
| `delete` | eliminó | `unlink` | desvinculó |
| `restore` | restauró | `role_change` | cambió el rol de |
| `approve` | aprobó | `activate` | activó |
| `unapprove` | quitó la aprobación de | `deactivate` | desactivó |
| `send` | envió | `purge` | purgó |
| `export` | descargó | | |

**Entity labels** (`AUDIT_ENTITY_LABELS`, definite article included so the generic fallback
agrees in gender; one entry per `AuditEntityType` of `data-model.md` §2.3):

| `entity_type` | Label (es-CO) | `entity_type` | Label (es-CO) |
|---|---|---|---|
| `user` | la cuenta | `monthly_report` | el informe mensual del club |
| `club` | el club | `club_project_profile` | el perfil de proyecto del club |
| `club_member` | la membresía del club | `athlete_monthly_newsletter` | el boletín familiar |
| `athlete` | la ficha del deportista | `athlete_ai_insight` | el análisis de IA |
| `parent_athlete` | el vínculo con la familia | `agent_run` | el análisis de carrera |
| `parent_invite` | la invitación a la familia | `race_import` | la importación de resultados |
| `parental_consent` | el consentimiento de la familia | `race_series` | la serie de válidas |
| `anthropometric_record` | la medición antropométrica | `race_event` | la válida |
| `training_session` | la sesión de entrenamiento | `race_event_roster` | la convocatoria de la válida |
| `training_session_coach` | el equipo técnico de la sesión | `race_result` | el resultado de carrera |
| `session_attendance` | el registro de asistencia | `race_competitor` | el competidor de la carrera |
| `session_media` | el material de la sesión | `interval_structure` | la estructura de intervalos |
| `calendar_event` | el evento del calendario | `interval_template` | la plantilla de intervalos |
| `event_attendance` | la asistencia al evento | `strava_connection` | la conexión con Strava |
| `athlete_ai_explanation` | la explicación de IA | `strava_activity` | la actividad de Strava |
| `audit_log` | el historial de cambios | | |

Product-copy anchors: "Sesiones", "Calendario", "Boletines", "Informes del club", "Válidas"
are the coach's own nav labels (`frontend/src/lib/navigation.ts:110,104,189,195,133`); the coach
surface says "boletín" while the parent surface says "Bitácora"
(`frontend/src/routes/training/AthleteNewslettersDashboardPage.tsx:131`,
`frontend/src/components/parents/ParentSidebar.tsx:260`) — the history is a coach/admin surface,
so it says **boletín familiar**.

**Count phrase** (`format_count_es`, the single building block `{conteo}` goes through): the
number and its noun are rendered together so the sentence agrees in number — `1` →
`"1 registro"`, any other `n` → `"{n} registros"`. A template therefore interpolates `{conteo}`
**without** writing the noun after it: `{conteo} registros` in a template re-introduces the
ungrammatical *"purgó 1 registros"*, which Constitution III forbids in product end-user copy.
The `0` case (`"0 registros"`) is reachable only from a hand-written row — the purge skips the
INSERT when nothing was deleted (`contracts/retention-purge.md` §1.5). The name echoes the
existing `format_date_es` (`backend/app/services/utils/dates_es.py:33`); the function itself
lives with the catalogue in `backend/app/services/audit.py` (§7.7), since it is sentence copy,
not general number formatting.

### 7.4 Resolution algorithm

```text
1. template = SENTENCE_TEMPLATES.get((entity_type, action))
2. if template is None or any placeholder it uses cannot be resolved:
       template = "{actor} {verbo} {etiqueta}."          # generic fallback
3. interpolate; capitalise nothing (the actor name is already capitalised);
   ensure a single trailing "."
```

Step 2's second clause is what guarantees no reader ever sees `{periodo}` or `None`: a
`(monthly_report, approve)` row whose `meta_json.period` is missing degrades to
*"Ana Coach aprobó el informe mensual del club."* instead of breaking. Tested (§13 T9).

Templates are written to stay **≤ 140 characters** after interpolation so a row fits one line on
the coach's tablet; a test asserts the bound over the whole catalogue (§13 T7).

### 7.5 Template catalogue — `SENTENCE_TEMPLATES: dict[tuple[AuditEntityType, AuditAction], str]`

Every pair not listed uses the generic fallback of §7.4. The pairs listed are the ones the
instrumentation matrix of `contracts/audit-recording.md` actually produces, or where the generic
sentence would read badly.

| `entity_type` | `action` | Template | Rendered example |
|---|---|---|---|
| `athlete` | `create` | `{actor} creó la ficha de un deportista.` | Ana Coach creó la ficha de un deportista. |
| `athlete` | `update` | `{actor} actualizó la ficha de un deportista.` | Ana Coach actualizó la ficha de un deportista. |
| `athlete` | `archive` | `{actor} archivó la ficha de un deportista ({motivo}).` | Ana Coach archivó la ficha de un deportista (Se retiró del club). |
| `athlete` | `restore` | `{actor} restauró la ficha de un deportista ({motivo}).` | Beto Coach restauró la ficha de un deportista (Archivado por error). |
| `athlete` | `export` | `{actor} descargó {documento} de un deportista.` | Ana Coach descargó el PDF de crecimiento de un deportista. |
| `athlete` | `link` | `{actor} vinculó una cuenta de familia con un deportista.` | Admin Club vinculó una cuenta de familia con un deportista. |
| `athlete` | `unlink` | `{actor} desvinculó una cuenta de familia de un deportista.` | Admin Club desvinculó una cuenta de familia de un deportista. |
| `parental_consent` | `create` | `{actor} registró el consentimiento de la familia.` | Ana Coach registró el consentimiento de la familia. |
| `parental_consent` | `update` | `{actor} actualizó el consentimiento de la familia.` | Ana Coach actualizó el consentimiento de la familia. |
| `parent_athlete` | `link` | `{actor} vinculó una cuenta de familia con un deportista.` | Admin Club vinculó una cuenta de familia con un deportista. |
| `parent_athlete` | `unlink` | `{actor} desvinculó una cuenta de familia de un deportista.` | Admin Club desvinculó una cuenta de familia de un deportista. |
| `parent_invite` | `create` | `{actor} envió una invitación a una familia.` | Ana Coach envió una invitación a una familia. |
| `parent_invite` | `delete` | `{actor} anuló una invitación a una familia.` | Ana Coach anuló una invitación a una familia. |
| `anthropometric_record` | `create` | `{actor} registró una medición antropométrica del {fecha}.` | Ana Coach registró una medición antropométrica del 14 de marzo de 2026. |
| `anthropometric_record` | `update` | `{actor} actualizó una medición antropométrica del {fecha}.` | Ana Coach actualizó una medición antropométrica del 14 de marzo de 2026. |
| `anthropometric_record` | `delete` | `{actor} eliminó una medición antropométrica del {fecha}.` | Ana Coach eliminó una medición antropométrica del 14 de marzo de 2026. |
| `training_session` | `create` | `{actor} creó la sesión de entrenamiento del {fecha}.` | Ana Coach creó la sesión de entrenamiento del 15 de marzo de 2026. |
| `training_session` | `update` | `{actor} actualizó la sesión de entrenamiento del {fecha}.` | Beto Coach actualizó la sesión de entrenamiento del 15 de marzo de 2026. |
| `training_session` | `cancel` | `{actor} canceló la sesión de entrenamiento del {fecha} ({motivo}).` | Beto Coach canceló la sesión de entrenamiento del 15 de marzo de 2026 (Clima adverso). |
| `training_session` | `execute` | `{actor} marcó como ejecutada la sesión de entrenamiento del {fecha}.` | Beto Coach marcó como ejecutada la sesión de entrenamiento del 15 de marzo de 2026. |
| `training_session` | `delete` | `{actor} eliminó la sesión de entrenamiento del {fecha}.` | Admin Club eliminó la sesión de entrenamiento del 15 de marzo de 2026. |
| `training_session` | `export` | `{actor} descargó {documento}.` | Ana Coach descargó el instructivo de la sesión en PDF. |
| `training_session_coach` | `create` | `{actor} agregó un entrenador a la sesión.` | Ana Coach agregó un entrenador a la sesión. |
| `training_session_coach` | `delete` | `{actor} quitó un entrenador de la sesión.` | Ana Coach quitó un entrenador de la sesión. |
| `session_attendance` | `create` | `{actor} registró la asistencia de un deportista en la sesión.` | Ana Coach registró la asistencia de un deportista en la sesión. |
| `session_attendance` | `update` | `{actor} actualizó el registro de asistencia de un deportista.` | Beto Coach actualizó el registro de asistencia de un deportista. |
| `session_attendance` | `archive` | `{actor} archivó el registro de asistencia de un deportista retirado de la convocatoria.` | Beto Coach archivó el registro de asistencia de un deportista retirado de la convocatoria. |
| `session_media` | `create` | `{actor} subió material a una sesión.` | Ana Coach subió material a una sesión. |
| `session_media` | `archive` | `{actor} archivó material de una sesión.` | Ana Coach archivó material de una sesión. |
| `session_media` | `delete` | `{actor} eliminó material de una sesión.` | Admin Club eliminó material de una sesión. |
| `calendar_event` | `create` | `{actor} creó el evento del calendario del {fecha}.` | Ana Coach creó el evento del calendario del 22 de marzo de 2026. |
| `calendar_event` | `update` | `{actor} actualizó el evento del calendario del {fecha}.` | Beto Coach actualizó el evento del calendario del 22 de marzo de 2026. |
| `calendar_event` | `cancel` | `{actor} canceló el evento del calendario del {fecha} ({motivo}).` | Beto Coach canceló el evento del calendario del 22 de marzo de 2026 (Sede no disponible). |
| `calendar_event` | `delete` | `{actor} eliminó el evento del calendario del {fecha}.` | Admin Club eliminó el evento del calendario del 22 de marzo de 2026. |
| `calendar_event` | `link` | `{actor} vinculó el evento del calendario con una válida.` | Ana Coach vinculó el evento del calendario con una válida. |
| `calendar_event` | `unlink` | `{actor} desvinculó el evento del calendario de una válida.` | Ana Coach desvinculó el evento del calendario de una válida. |
| `event_attendance` | `create` | `{actor} registró la asistencia a un evento.` | Ana Coach registró la asistencia a un evento. |
| `event_attendance` | `update` | `{actor} actualizó la asistencia a un evento.` | Ana Coach actualizó la asistencia a un evento. |
| `monthly_report` | `create` | `{actor} generó el informe mensual de {periodo}.` | Ana Coach generó el informe mensual de marzo de 2026. |
| `monthly_report` | `update` | `{actor} actualizó el informe mensual de {periodo}.` | Beto Coach actualizó el informe mensual de marzo de 2026. |
| `monthly_report` | `approve` | `{actor} aprobó el informe mensual de {periodo}.` | Ana Coach aprobó el informe mensual de marzo de 2026. |
| `monthly_report` | `unapprove` | `{actor} quitó la aprobación del informe mensual de {periodo}.` | Beto Coach quitó la aprobación del informe mensual de marzo de 2026. |
| `monthly_report` | `export` | `{actor} descargó {documento} de {periodo}.` | Ana Coach descargó el informe mensual en DOCX de marzo de 2026. |
| `monthly_report` | `send` | `{actor} envió el informe mensual de {periodo}.` | Ana Coach envió el informe mensual de marzo de 2026. |
| `club_project_profile` | `create` | `{actor} creó el perfil de proyecto del club.` | Admin Club creó el perfil de proyecto del club. |
| `club_project_profile` | `update` | `{actor} actualizó el perfil de proyecto del club.` | Admin Club actualizó el perfil de proyecto del club. |
| `athlete_monthly_newsletter` | `create` | `{actor} generó el boletín familiar de {periodo}.` | Ana Coach generó el boletín familiar de marzo de 2026. |
| `athlete_monthly_newsletter` | `update` | `{actor} editó el boletín familiar de {periodo}.` | Beto Coach editó el boletín familiar de marzo de 2026. |
| `athlete_monthly_newsletter` | `approve` | `{actor} aprobó el boletín familiar de {periodo}.` | Ana Coach aprobó el boletín familiar de marzo de 2026. |
| `athlete_monthly_newsletter` | `unapprove` | `{actor} quitó la aprobación del boletín familiar de {periodo}.` | Beto Coach quitó la aprobación del boletín familiar de marzo de 2026. |
| `athlete_monthly_newsletter` | `send` | `{actor} envió a la familia el boletín de {periodo}.` | Ana Coach envió a la familia el boletín de marzo de 2026. |
| `athlete_monthly_newsletter` | `export` | `{actor} descargó {documento} de {periodo}.` | Ana Coach descargó el boletín familiar en PDF de marzo de 2026. |
| `athlete_ai_insight` | `create` | `{actor} generó un análisis de IA para un deportista.` | Ana Coach generó un análisis de IA para un deportista. |
| `athlete_ai_insight` | `update` | `{actor} actualizó un análisis de IA.` | Beto Coach actualizó un análisis de IA. |
| `athlete_ai_insight` | `approve` | `{actor} aprobó un análisis de IA.` | Ana Coach aprobó un análisis de IA. |
| `athlete_ai_insight` | `archive` | `{actor} archivó un análisis de IA.` | Beto Coach archivó un análisis de IA. |
| `athlete_ai_explanation` | `create` | `{actor} generó una explicación de IA.` | Ana Coach generó una explicación de IA. |
| `agent_run` | `create` | `{actor} lanzó un análisis de carrera.` | Ana Coach lanzó un análisis de carrera. |
| `agent_run` | `approve` | `{actor} resolvió la decisión pendiente de un análisis de carrera.` | Beto Coach resolvió la decisión pendiente de un análisis de carrera. |
| `agent_run` | `unapprove` | `{actor} rechazó la decisión pendiente de un análisis de carrera.` | Beto Coach rechazó la decisión pendiente de un análisis de carrera. |
| `agent_run` | `cancel` | `{actor} canceló un análisis de carrera.` | Beto Coach canceló un análisis de carrera. |
| `agent_run` | `execute` | `{actor} volvió a ejecutar un análisis de carrera.` | Beto Coach volvió a ejecutar un análisis de carrera. |
| `agent_run` | `export` | `{actor} descargó {documento}.` | Ana Coach descargó el análisis de carrera en PDF. |
| `race_import` | `create` | `{actor} inició una importación de resultados.` | Ana Coach inició una importación de resultados. |
| `race_import` | `execute` | `{actor} confirmó una importación de resultados.` | Beto Coach confirmó una importación de resultados. |
| `race_import` | `update` | `{actor} actualizó una importación de resultados.` | Beto Coach actualizó una importación de resultados. |
| `race_import` | `delete` | `{actor} eliminó una importación de resultados.` | Admin Club eliminó una importación de resultados. |
| `race_series` | `create` | `{actor} creó una serie de válidas.` | Ana Coach creó una serie de válidas. |
| `race_series` | `update` | `{actor} actualizó una serie de válidas.` | Ana Coach actualizó una serie de válidas. |
| `race_event` | `create` | `{actor} creó una válida.` | Ana Coach creó una válida. |
| `race_event` | `update` | `{actor} actualizó una válida.` | Ana Coach actualizó una válida. |
| `race_event` | `cancel` | `{actor} canceló una válida ({motivo}).` | Ana Coach canceló una válida (Cancelado por el organizador). |
| `race_event_roster` | `create` | `{actor} convocó a un deportista a una válida.` | Ana Coach convocó a un deportista a una válida. |
| `race_event_roster` | `delete` | `{actor} retiró a un deportista de la convocatoria de una válida.` | Ana Coach retiró a un deportista de la convocatoria de una válida. |
| `race_result` | `create` | `{actor} agregó un resultado al acta.` | Ana Coach agregó un resultado al acta. |
| `race_result` | `update` | `{actor} corrigió un resultado del acta.` | Beto Coach corrigió un resultado del acta. |
| `race_result` | `delete` | `{actor} retiró un resultado del acta.` | Beto Coach retiró un resultado del acta. |
| `race_result` | `restore` | `{actor} restauró un resultado del acta.` | Beto Coach restauró un resultado del acta. |
| `race_competitor` | `link` | `{actor} enlazó un competidor con un deportista del club.` | Ana Coach enlazó un competidor con un deportista del club. |
| `race_competitor` | `unlink` | `{actor} deshizo el enlace de un competidor con un deportista del club.` | Beto Coach deshizo el enlace de un competidor con un deportista del club. |
| `interval_structure` | `create` | `{actor} creó una estructura de intervalos.` | Ana Coach creó una estructura de intervalos. |
| `interval_structure` | `update` | `{actor} actualizó una estructura de intervalos.` | Ana Coach actualizó una estructura de intervalos. |
| `interval_template` | `create` | `{actor} creó una plantilla de intervalos.` | Ana Coach creó una plantilla de intervalos. |
| `interval_template` | `update` | `{actor} actualizó una plantilla de intervalos.` | Ana Coach actualizó una plantilla de intervalos. |
| `strava_connection` | `link` | `{actor} conectó una cuenta de Strava a un deportista.` | Ana Coach conectó una cuenta de Strava a un deportista. |
| `strava_connection` | `unlink` | `{actor} desconectó la cuenta de Strava de un deportista.` | Ana Coach desconectó la cuenta de Strava de un deportista. |
| `strava_activity` | `create` | `{actor} registró una actividad de Strava.` | Servicio externo registró una actividad de Strava. |
| `strava_activity` | `link` | `{actor} vinculó una actividad de Strava con una sesión.` | Ana Coach vinculó una actividad de Strava con una sesión. |
| `strava_activity` | `unlink` | `{actor} desvinculó una actividad de Strava de una sesión.` | Ana Coach desvinculó una actividad de Strava de una sesión. |
| `user` | `create` | `{actor} creó una cuenta de {rol}.` | Admin Club creó una cuenta de entrenador. |
| `user` | `update` | `{actor} actualizó los datos de una cuenta.` | Admin Club actualizó los datos de una cuenta. |
| `user` | `activate` | `{actor} activó una cuenta ({motivo}).` | Admin Club activó una cuenta (Reincorporación). |
| `user` | `deactivate` | `{actor} desactivó una cuenta ({motivo}).` | Admin Club desactivó una cuenta (Fin de vinculación). |
| `user` | `role_change` | `{actor} cambió el rol de una cuenta a {rol}.` | Admin Club cambió el rol de una cuenta a entrenador. |
| `user` | `delete` | `{actor} eliminó una cuenta de familia ({motivo}).` | Admin Club eliminó una cuenta de familia (Solicitud de la familia). |
| `club_member` | `create` | `{actor} agregó una cuenta al club como {rol_club}.` | Admin Club agregó una cuenta al club como entrenador. |
| `club_member` | `role_change` | `{actor} cambió el rol en el club de una cuenta a {rol_club}.` | Admin Club cambió el rol en el club de una cuenta a entrenador. |
| `club_member` | `delete` | `{actor} quitó una cuenta del club.` | Admin Club quitó una cuenta del club. |
| `club` | `update` | `{actor} actualizó los datos del club.` | Admin Club actualizó los datos del club. |
| `audit_log` | `purge` | `{actor} purgó {conteo} del historial ({motivo}).` | Tarea programada purgó 143 registros del historial (Retención: 24 meses cumplidos). · Con `removed_count = 1`: Tarea programada purgó 1 registro del historial (Retención: 24 meses cumplidos). |

Names in the examples ("Ana Coach", "Beto Coach", "Admin Club") are the synthetic two-coach
fixture identities of research `R-32`, not real people.

### 7.6 `AUDIT_DOCUMENT_LABELS` — `{documento}`

Keys are the `AuditDocumentKind` values fixed by `data-model.md` §2.3.

| `meta_json.document_kind` | Label (es-CO) |
|---|---|
| `growth_pdf` | el PDF de crecimiento |
| `clearance_docx` | la autorización médica en DOCX |
| `monthly_report_pdf` | el informe mensual en PDF |
| `monthly_report_docx` | el informe mensual en DOCX |
| `newsletter_pdf` | el boletín familiar en PDF |
| `newsletter_email` | el boletín familiar por correo |
| `race_analysis_pdf` | el análisis de carrera en PDF |
| `session_instructivo_pdf` | el instructivo de la sesión en PDF |

### 7.7 Where the catalogue lives

`backend/app/services/audit.py`, next to `VALUE_ALLOWLIST` and the reason catalogue — the same
"closed enum + `*_LABELS` dict, only the code is persisted" shape as
`RevisionReasonCode` / `REVISION_REASON_LABELS` (`backend/app/schemas/race_imports.py:38-67`),
which exists for exactly this reason: a coach cannot type a minor's name into a catalogue.

---

## 8. `detail` — the expandable block

FR-008 confines raw identifiers and column names to this block. It is returned on every row
(the client decides when to reveal it), but it carries nothing the sentence could not have
carried safely.

| Field | Rule |
|---|---|
| `changed_fields` | verbatim from `audit_log.changed_fields` — a JSON array of **column-name strings only**, never values (`data-model.md` §1). `[]` for actions with no field diff (`export`, `send`, `link`). |
| `changed_field_labels` | best-effort es-CO labels from `AUDIT_FIELD_LABELS: dict[str, str]`, positionally aligned with `changed_fields`; an unknown column falls back to its own name so the array length always matches. Examples: `status` → "Estado", `scheduled_date` → "Fecha programada", `cancellation_reason_code` → "Motivo de cancelación", `is_active` → "Cuenta activa", `role_in_club` → "Rol en el club", `edit_version` → "Versión de edición", `approved_by_user_id` → "Aprobado por". |
| `diff` | from `audit_log.diff_json`, **re-filtered at read time** through `VALUE_ALLOWLIST[entity_type]` (`data-model.md` §2.5). `null` when the row has no diff or every key was dropped. |
| `meta` | from `audit_log.meta_json`, re-filtered through **`META_ALLOWLIST`** — the single closed key set of `audit-recording.md` §1.7, imported, never re-listed here. An earlier draft repeated a partial list (`document_kind`, `period`, `event_date`, `removed_count`, `cutoff`, `recipients_count`, `job`, `role`) and would have silently dropped `step_id`, `block`, `is_revision` and the rest on the way out. |

**The read path never trusts stored JSON.** Re-applying the allow-list on the way out is
defence in depth against a row written by an earlier, buggier version of `record_audit`, or by
a future entity type whose allow-list entry lands after its instrumentation. A dropped key logs
one WARNING carrying `audit_log.id` and the offending **key name** — never the value:

```text
audit_read_dropped_field | audit_id=4821 entity_type=session_attendance field=individual_feedback
```

This keeps the constitution's Observability gate (no PII in logs) while making the anomaly
visible. A dropped key never fails the request.

---

## 9. `X-Request-Id` response header

Every response of both endpoints carries the correlation id of the *read* request:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-Id: 9f1c2b7a4d5e46a8b0c3d9e2f1a7b6c4
```

- **Set by the middleware, not by these routes.** `app/services/request_context.py` (pure ASGI,
  research `R-05`) generates `uuid4().hex` — 32 chars, matching `audit_log.request_id`
  `String(32)` (`data-model.md` §1) — stores it in a `ContextVar` and echoes it on the way out.
  It applies to the whole API, not just this contract; it is specified in full in
  `contracts/audit-recording.md`.
- **Inbound `X-Request-Id` is honoured only for server-to-server callers** (research `R-05`);
  browser requests always get a fresh value, so a client cannot forge a correlation.
- **Casing.** Canonical spelling `X-Request-Id` (as in research `R-05`); HTTP field names are
  case-insensitive, so `X-Request-ID` is the same header. Tests must match case-insensitively.
- **Not the same id as the rows.** The header identifies this GET; `AuditEntryOut.request_id`
  identifies the write that produced the row. They are never equal, because reads write nothing.
  The UI labels the row field "Operación" and the header is used only in support tickets.
- **CORS**: `backend/app/main.py:59-64` sets no `expose_headers`, so today a browser on
  Cloudflare Pages cannot read this header at all. The fix is one line in the `CORSMiddleware`
  call, and it is the **same** line that research `R-15` needs for `ETag`, so it is written
  once and only once — the authoritative block is **`contracts/audit-recording.md` §3.1**
  (`expose_headers=["ETag", "X-Request-Id"]`, `allow_headers` gaining `If-Match`). This
  contract deliberately restates no snippet: a partial copy here is how one of the two values
  gets dropped. Cross-origin readability is asserted by `backend/tests/test_cors_etag.py`
  (`concurrency-and-approvals.md` §9 T21) for both values; §13 T11 covers the header's presence
  and shape.

---

## 10. Errors

| Code | When | Body |
|---|---|---|
| `401` | missing / invalid / expired token, or the account is inactive | `{"detail": "Token inválido"}` / `{"detail": "Token expirado"}` (`backend/app/dependencies.py:36-71`) |
| `403` | parent or athlete role, either endpoint | `{"detail": "No tienes permisos para esta acción"}` |
| `403` | coach of another club, club endpoint | `{"detail": "No tienes permisos para ver el historial de este club."}` |
| `403` | coach of another club, athlete endpoint | `{"detail": "No tienes acceso a este atleta"}` |
| `404` | unknown `athlete_id`, caller is admin or coach | `{"detail": "Atleta no encontrado"}` |
| `422` | `entity_type` / `action` outside the closed enum, `limit > 50`, `from > to` | FastAPI validation body; the `from > to` case uses the explicit Spanish detail of §2.1 |
| `500` | unexpected | `{"detail": "Error interno del servidor"}` (`backend/app/main.py:68-81`) — the handler already logs without the body, so no audit payload can leak into a 500 |

There is no `404` for an unknown `club_id` (§2.5).

---

## 11. Non-functional

- **Exactly two queries per request**: the paged `SELECT … LEFT JOIN users` and a
  `select(func.count()).select_from(AuditLog).where(<same filters>)`. Asserted by a query-count
  test (`data-model.md` §8.3 Q1). Do **not** copy `backend/app/routers/race_imports.py:1220-1221`,
  which computes `total` by materialising every matching row — at 16 000 audit rows that is the
  one way this endpoint could blow the p95 ≤ 500 ms read budget.
- **No N+1 on names**: one `LEFT JOIN`, never a per-row lookup (§6.1). Constitution IV.
- **Index coverage**: `ix_audit_club_time` (default club read), `ix_audit_actor_time`,
  `ix_audit_entity_time`, `ix_audit_athlete_time`, `ix_audit_request_id`
  (`data-model.md` §1.1). No filter combination in §2.1 falls outside them.
- **Timestamps**: `occurred_at` is naive UTC with microseconds
  (`mysql.DATETIME(fsp=6)`), serialised as `2026-03-14T22:05:41.482913`. The frontend's
  `ISO_DATETIME_NAIVE_RE` (`frontend/src/lib/datetime.ts:13-21`) already matches that shape,
  including the fractional part, and appends `Z` — so `formatDateTime` renders it in
  `America/Bogota` with no change. Do not add a `Z` server-side; it would diverge from every
  other datetime in this API.
- **Device persistence**: `frontend/src/lib/persistAllowList.ts` is default-deny
  (`:44-52`), so `["audit", …]` query keys are not written to `localStorage` without an explicit
  prefix. **Do not add one** — history rows carry `athlete_id` and coach names.
- **Cold start**: these are new lazy routes; the existing "starting the server" state
  (Principle IV) covers them with no extra work.
- **These endpoints write nothing** — no audit row, no `updated_at` touch. FR-005 excludes
  plain reads, and FR-004 forbids anything but the purge from touching the table.

---

## 12. Client consumption (summary)

Full UI specification lives in `contracts/coach-activity-report.md`; only the API-facing
contract is fixed here.

- `frontend/src/api/audit.ts` — `getClubAuditLog(clubId, filters)` and
  `getAthleteAuditLog(athleteId, filters)` on the shared `apiClient`
  (`frontend/src/api/client.ts:7-12`).
- `frontend/src/hooks/useAuditLog.ts` — `useQuery({ queryKey: ["audit", "club", clubId, filters], placeholderData: keepPreviousData, enabled: !!accessToken })`, the filtered-list convention of research `R-28`.
- `frontend/src/schemas/audit.ts` — Zod mirror of §5; parsing failure is a bug, not a UI state.
- Rendering: the row prints `sentence_es` as-is plus `formatDateTime(occurred_at)`; `detail`
  goes inside a `Collapsible` labelled **"Ver detalle"**; the athlete link is built from
  `athlete_id` against the athlete list the coach surface already holds — the response never
  carries an athlete name.

---

## 13. Required tests

Backend, `backend/tests/routers/test_audit_log_api.py`, on the offline aiosqlite lane with the
two-coach fixture of research `R-32` (coach A and coach B in club 1, coach C in club 2, one
parent linked to an athlete of club 1, one admin).

| # | Test | Asserts |
|---|---|---|
| T1 | **Happy — club, coach A** | `200`; `items` newest-first by `(occurred_at, id)`; `total` matches the seeded count; every row has a non-empty `sentence_es`, a non-empty `actor_display_name` and a 32-char `request_id` |
| T2 | **Happy — club, admin** | `200` for a club the admin is not a member of |
| T3 | **Happy — athlete panel, coach A** | `200`; every row's `athlete_id` equals the path athlete; `limit` defaults to 15 |
| T4 | **403 parent — club endpoint** | parent token → `403`, body `{"detail": "No tienes permisos para esta acción"}`, response contains no `items` key |
| T5 | **403 parent — athlete endpoint, own child** | parent linked to the athlete → still `403` (this is the regression that `verify_athlete_access` alone would let through, §4.3) |
| T6 | **403 cross-club coach** | coach C on club 1 → `403`; coach C on an athlete of club 1 → `403`; neither body reveals whether the club/athlete exists |
| T7 | **Sentence catalogue integrity — both directions** | (a) every `(entity_type, action)` pair declared in `contracts/audit-recording.md`'s instrumentation matrix (§4.1–§4.13) resolves to a sentence; (b) **every template in §7.5 corresponds to a pair the matrix actually produces** — a template with no producer is a stale or renamed tuple and fails, naming it. (b) is the half that catches a matrix drifting to a different verb (e.g. a run launch mapped to `execute` while the catalogue reserves `execute` for the re-execution): with only (a), the wrong tuple still resolves and the reader gets a misleading sentence. Also: every template uses only §7.2 placeholders; every rendered example ≤ 140 chars; every `AuditEntityType` has an entry in `AUDIT_ENTITY_LABELS` and every `AuditAction` one in `AUDIT_ACTION_VERBS`. Plus the `{conteo}` pluraliser of §7.3: `(audit_log, purge)` with `meta_json.removed_count = 1` renders *"Tarea programada purgó 1 registro del historial (Retención: 24 meses cumplidos)."* — singular noun, no `1 registros` — and with `143` renders *"… purgó 143 registros del historial …"*; no template concatenates `{conteo}` with a literal `registro`/`registros` |
| T8 | **No PII in the response (SC-001)** | run the multi-action scenario with the fixture's synthetic athlete, then scan the whole serialised JSON of both endpoints for: the athlete's `first_name`/`last_name`, an ISO birth-date pattern, any measurement-shaped numeric, and the keys `first_name`/`last_name`/`birth_date`/`sex`/`email`/`individual_feedback`/`coach_note`. Zero hits. Also asserts no `diff`/`meta` key outside `VALUE_ALLOWLIST[entity_type]` survives the read filter (§8) |
| T9 | **Sentence fallback** | a row with `(monthly_report, approve)` and no `meta_json.period` renders the generic sentence, with no `{` or `None` in the output; a row with an unmapped `(entity_type, action)` also renders the generic sentence |
| T10 | **Automated actor** | a `webhook` row returns `actor_user_id: null`, `actor_role: null`, `actor_display_name: "Servicio externo"` and is **not** dropped by the join (the `LEFT`-join regression) |
| T11 | **`X-Request-Id`** | present on `200`, `403` and `404`; 32 hex chars; different between two consecutive calls. The cross-origin assertion (`Access-Control-Expose-Headers` listing `X-Request-Id` **and** `ETag`) is **not** duplicated here — it lives in `backend/tests/test_cors_etag.py` (`concurrency-and-approvals.md` §9 T21), which owns the single CORS edit of `audit-recording.md` §3.1 |
| T12 | **Filters** | `actor_user_id` returns only coach B's rows (US1 Independent Test: "filtering by coach B shows exactly two"); `entity_type`, `action`, `athlete_id` each narrow correctly; `request_id` returns every row of one roster save and nothing else (US1 AS5); `from`/`to` are day-inclusive at both ends |
| T13 | **Pagination** | `limit=1` twice with `offset=0,1` yields disjoint rows and a stable `total`; `limit=51` → `422`; `offset` past `total` → empty `items` with the real `total` |
| T14 | **Query count (Principle IV)** | exactly 2 SQL statements per request regardless of page size, and no extra `SELECT users` per row |
| T15 | **Deactivated actor still resolves (FR-013)** | deactivate coach B, re-read: `actor_display_name` is still their full name and the row is still returned |
| T16 | **Archived athlete still visible (Edge Case spec.md:176)** | archive the athlete, then `GET /api/athletes/{id}/audit-log` as coach and admin → `200`, entries include the `archive` row |
| T17 | **Read writes nothing (FR-004/FR-005)** | snapshot `SELECT COUNT(*) FROM audit_log` and `MAX(id)` before and after 10 reads → unchanged |
| T18 | **Invalid input** | `entity_type=banana` → `422`; `action=frobnicate` → `422`; `from=2026-03-31&to=2026-03-01` → `422` with the Spanish detail of §2.1 |
| T19 | **Reason catalogue is exactly the group (§14)** | for each member of `AuditReasonGroup`, `GET /api/audit/reason-codes?group=<g>` returns codes that are **set-equal** to the members of `AUDIT_REASON_GROUPS[g]` (no extra, none missing), every `group` field equals `g`, and every `label` equals `AUDIT_REASON_LABELS[code]`. Omitting `group` returns the union of the five groups — 20 rows — and never `retention_24m`. `group=banana` → `422`, not an empty list. Order is stable across two calls |
| T20 | **Reason catalogue RBAC and read-only (§14.4)** | parent → `403` with `{"detail": "No tienes permisos para esta acción"}`; athlete role → `403`; no token → `401`; coach C (other club) and a coach with no club membership both → `200` with the same body as coach A; `SELECT COUNT(*) FROM audit_log` is unchanged after 10 calls |

Frontend, `frontend/src/hooks/__tests__/useAuditLog.test.ts` + the page/panel tests owned by
`contracts/coach-activity-report.md`: MSW handlers under `frontend/src/test/msw/auditHandlers.ts`
built from synthetic fixtures (research `R-33`), Zod-schema round-trip on the sample bodies of
§2.3 and §14.3, and `jest-axe` with zero violations on the history page and the "Ver detalle"
collapsible. The same `auditHandlers.ts` exports the `/api/audit/reason-codes` handler that the
reason-picker tests of `contracts/athlete-archive.md` §12.6 and `contracts/staff-admin.md` §14.2
reuse, so no test file declares its own array of reason codes either.

Not owned here (listed so nothing falls between contracts): the `record_audit` write path,
the route-coverage meta-test and the append-only test live in `contracts/audit-recording.md`;
the purge lives in `contracts/retention-purge.md`.

---

## 14. `GET /api/audit/reason-codes` — the shared reason catalogue

Every reason `Select` in this feature reads its options from this one endpoint: athlete archive
and restore (`contracts/athlete-archive.md` §3.2, §10, §11), training-session cancel
(`contracts/session-coaches.md` §7.1), calendar-event cancel
(`contracts/session-coaches.md` §7.2), and staff
deactivate / reactivate (`contracts/staff-admin.md` §10). It exists so the closed catalogue of
`data-model.md` §2.4 has exactly one source of truth and no frontend ships a second, drifting
copy of the codes or of their Spanish labels — the drift being the way a picker silently loses
the "no free text" guarantee that FR-003 rests on.

Direct analogue of `GET /api/race-analysis/imports/revision-reasons`
(`backend/app/routers/race_imports.py:1266-1285`), the closed-catalogue precedent this project
already runs in production.

### 14.1 Surface

| Method | Path | Router | Auth |
|---|---|---|---|
| `GET` | `/api/audit/reason-codes` | `catalog_router` in `backend/app/routers/audit.py`, mounted `prefix="/api/audit"`, `tags=["audit"]` | `require_role([UserRole.admin, UserRole.coach])` (`backend/app/dependencies.py:77-85`) |

Club-agnostic on purpose. The response carries no club, athlete or person data — only enum
members and their es-CO labels — so there is nothing to scope: `can_view_audit` (§4.2) is **not**
called here, and a coach with no club membership still gets `200` (they need the picker the
moment an admin assigns them a club).

### 14.2 Query parameters

| Name | Type | Default | Notes |
|---|---|---|---|
| `group` | `AuditReasonGroup` | — (omitted → every group) | Closed enum: `athlete_archive`, `athlete_restore`, `cancel`, `account`, `parent_removal`. An unknown value is `422` from FastAPI's own enum validation — never a silently empty list, which would render an empty picker and look like a data problem. |

`AuditReasonGroup` and `AUDIT_REASON_GROUPS: dict[AuditReasonGroup, type[StrEnum]]` are the five
sub-enums fixed in `contracts/athlete-archive.md` §3.1; this endpoint iterates them and adds
nothing of its own. `retention_24m` (`data-model.md` §2.4, Retention group) is **not** reachable
here: it belongs to the purge CLI (`contracts/retention-purge.md`) and is never offered in a
picker.

### 14.3 Response `200`

```json
{
  "items": [
    { "code": "athlete_left_club",        "group": "athlete_archive", "label": "Se retiró del club" },
    { "code": "athlete_transferred",      "group": "athlete_archive", "label": "Traslado a otro club" },
    { "code": "athlete_season_inactive",  "group": "athlete_archive", "label": "Inactivo esta temporada" },
    { "code": "athlete_family_request",   "group": "athlete_archive", "label": "Solicitud de la familia" },
    { "code": "athlete_duplicate_record", "group": "athlete_archive", "label": "Registro duplicado" },
    { "code": "athlete_data_correction",  "group": "athlete_archive", "label": "Corrección de datos" }
  ]
}
```

Schemas, in the same `backend/app/schemas/audit.py` as §5:

```python
class AuditReasonCodeOut(BaseModel):
    """Una opción del catálogo cerrado de motivos (data-model §2.4)."""

    code: str                 # valor de AuditReasonCode
    label: str                # AUDIT_REASON_LABELS[code], es-CO con tildes
    group: AuditReasonGroup


class AuditReasonCodeListOut(BaseModel):
    """Catálogo completo o filtrado por grupo. Nunca paginado."""

    items: list[AuditReasonCodeOut]
```

- The key is `items`, not the `options` of `RevisionReasonsResponse`
  (`backend/app/schemas/race_imports.py:246-250`), so every list response in this contract has the
  same shape.
- No `total` / `limit` / `offset`: the whole catalogue is 20 rows (6 + 2 + 6 + 4 + 2) and is
  never paged.
- Order is deterministic — groups in the order of `data-model.md` §2.4, members in declaration
  order inside each sub-enum — so a picker never reshuffles between renders.
- The handler is pure Python over the two catalogues: **zero SQL statements**, which is why this
  endpoint is exempt from the two-query rule of §11 rather than an exception to it.

### 14.4 Errors, and what is not written

| Code | When | Body |
|---|---|---|
| `401` | no / invalid / expired token | standard |
| `403` | `parent` or `athlete` role | `{"detail": "No tienes permisos para esta acción"}` (reused verbatim from `backend/app/dependencies.py:81`) |
| `422` | `group` outside the closed enum | Pydantic validation error |

**No audit row is ever written.** This is a plain read (FR-005 excludes them) and FR-004 forbids
anything but the purge from touching `audit_log`.

### 14.5 Client consumption

- `frontend/src/api/audit.ts::getAuditReasonCodes(group?)` on the shared `apiClient`
  (`frontend/src/api/client.ts:7-12`).
- `frontend/src/hooks/useAuditReasonCodes.ts` —
  `useQuery({ queryKey: ["audit-reason-codes", group], staleTime: 60 * 60_000 })`, the shape of
  `frontend/src/hooks/race/useRevisionReasons.ts:10-16`: the catalogue is closed and changes only
  with a deploy, so an hour of staleness costs nothing and saves a request per dialog open.
- `frontend/src/schemas/audit.ts` — Zod mirror of §14.3; a parse failure is a bug, not a UI state.
- Every consumer renders `label`, submits `code`, and **never** declares its own array of reason
  codes. The reason `Select` stays disabled — with the picker's loading state, not a bare spinner
  (Principle III) — until the catalogue resolves, and the confirm button stays disabled until a
  code is chosen.
- The catalogue is not added to `frontend/src/lib/persistAllowList.ts`: it is cheap to refetch and
  the allow-list is default-deny by design (`:44-52`).
