# Contract — Staff administration (US3 · FR-019 … FR-023)

**Scope**: creating, listing and activating/deactivating the club's staff accounts
(`coach`, `admin`) from the app, plus the admin-only `/admin/usuarios` screen that drives
it. Everything here is a *delta* on endpoints that already exist; no new route is added on
the backend.

**Owned by sibling contracts, referenced but not respecified here**

| Concern | Owner |
|---|---|
| `record_audit(...)` signature, request-id context, `AuditAction` / `AuditEntityType` / `AuditReasonCode` semantics | `contracts/audit-recording.md` |
| `GET /api/audit/reason-codes` catalogue endpoint (consumed in §10) | `contracts/audit-log-api.md` §14 |
| `DELETE /api/users/{id}` refusal copy and status, and removing the `created_by = NULL` cascade (`backend/app/routers/users.py:343-345`) | `contracts/athlete-archive.md` |
| Attribution columns `users.updated_at` / `users.updated_by_user_id`, `club_members.added_by_user_id` | `data-model.md` §4.1, §4.8 |
| The single new `gobierno` `NavArea` literal in `frontend/src/lib/navigation.ts` (including this contract's `gobierno.staff` item) and the `navigation.test.ts` area-count updates | `contracts/coach-activity-report.md` §8.2 |

Column names, enum values and reason codes are those fixed in `data-model.md` §2 and §4;
decisions R-20, R-21, R-22, R-28, R-29, R-30, R-31 in `research.md` are binding.

---

## 1. `POST /api/users` — staff creation

**Router**: `backend/app/routers/users.py:36-134` (`create_user`).
**Auth**: `require_role([UserRole.admin, UserRole.coach])` (`backend/app/dependencies.py:77-85`) — unchanged.
**Schemas**: `backend/app/schemas/user.py::UserCreate` (`:8-22`) → `UserOut` (`:32-43`).

### 1.1 Request (staff variant)

```json
{
  "first_name": "Ana",
  "last_name": "Rivera",
  "email": "ana.rivera@example.org",
  "phone": "3001234567",
  "role": "coach",
  "club_id": 1
}
```

`password` MUST NOT be sent for `role ∈ {coach, admin}` (FR-023). `UserCreate.password`
stays on the schema because `role=parent` still uses it (`backend/app/routers/users.py:78-79`),
but the router rejects it for staff (§1.2).

### 1.2 Validation order and error matrix

The order is load-bearing: the first matching row wins, so the currently-403 paths keep
their status even when the body is also invalid.

| # | Rule | Code | `detail` (es-CO) | Site today |
|---|---|---|---|---|
| 1 | target role not creatable by the caller | `403` | `No tienes permisos para crear usuarios con rol '{role}'` | `users.py:43-48` (unchanged) |
| 2 | caller is `coach` and `club_id` is missing | `422` | `Debes indicar el club (club_id) al que pertenece el nuevo usuario` | `users.py:53-58` (unchanged) |
| 3 | caller is `coach` and `club_id` is not one of their clubs | `403` | `No perteneces al club indicado como coach` | `users.py:59-64` (unchanged) |
| 4 | **target** role ∈ {`coach`, `admin`} and `club_id` is missing | `422` | `El club es obligatorio para las cuentas de entrenador y administrador` | **new** — replaces the caller-scoped rule (R-20) |
| 5 | target role ∈ {`coach`, `admin`} and `email` is empty | `422` | `El correo electrónico es obligatorio para las cuentas de entrenador y administrador` | `users.py:67-73`, narrowed (drops the password half) |
| 6 | target role ∈ {`coach`, `admin`} and `password` is present | `422` | `La contraseña no se define aquí: la persona la crea desde el correo que recibirá` | **new** (FR-023) |
| 7 | `club_id` does not exist | `404` | `Club no encontrado` | **new** — see note below |
| 8 | email already taken | `409` | `Ya existe un usuario con ese correo electrónico` | `users.py:100-107` (unchanged) |
| 9 | user already a member of the club | `409` | `El usuario ya es miembro de ese club` | `users.py:125-132` (unchanged) |

Row 7 is new because the club FK is only exercised at the membership `flush()`; today an
unknown `club_id` raises `IntegrityError` and is reported through the row-9 handler
(`users.py:127-132`), i.e. with the wrong message. With `club_id` now mandatory for staff,
that mislabelled path becomes reachable in the normal flow, so the club is loaded and
checked before any insert (same copy as `backend/app/routers/clubs.py:128-131`).

Row 4 replaces, it does not extend, the caller-scoped check: the readiness-audit bug is
that the club requirement lives inside `if current_user.role == UserRole.coach:`
(`users.py:53`), so an **admin** creating a **coach** skips it and the whole membership
block (`users.py:110-132`, guarded by `if body.club_id is not None`), leaving a coach who
signs in to an empty app. `backend/tests/test_users.py:32-57` currently asserts `201` for
exactly that request and MUST be updated in the same change (§14.1).

`role=admin` is unreachable today — `_ALLOWED_CREATIONS[UserRole.admin]`
(`users.py:23-26`) does not contain `admin`, so row 1 fires first. This feature does **not**
open admin self-creation; rows 4–6 name both roles so the rule reads as a property of the
account being created, not of the caller.

The branch at `users.py:80-85` (`Se requiere contraseña para este rol`) is **deleted**: its
only reachable roles are `coach`/`admin`, and both now legitimately arrive without a
password.

### 1.3 Account and membership in one unit of work (FR-019, FR-022)

`get_db` opens one transaction per request and commits on the way out
(`backend/app/dependencies.py:17-24`), so "same transaction" means: no extra `commit()`,
and the membership insert stays where it is, unconditionally executed for staff.

```text
users row      : hashed_password = None      # no credential is ever chosen by the admin
                 can_login       = True      # role != athlete (users.py:76)
                 is_active       = True      # column default (models/user.py:38)
                 created_by      = current_user.id   (users.py:96)
club_members   : club_id      = body.club_id
                 user_id      = new_user.id
                 role_in_club = role_in_club_for(body.role)
                 added_by_user_id = current_user.id  # data-model.md §4.8
```

`role_in_club_for` is the shared helper extracted from the inline map at
`backend/app/routers/users.py:112-117` into
`backend/app/services/permissions.py` (next to `coach_club_ids`, `:71`):

```python
_ROLE_IN_CLUB: dict[UserRole, ClubRole] = {
    UserRole.admin: ClubRole.admin,
    UserRole.coach: ClubRole.coach,
    UserRole.parent: ClubRole.parent,
    UserRole.athlete: ClubRole.athlete,
}

def role_in_club_for(role: UserRole) -> ClubRole:
    """Single mapping account role → role in club (FR-022)."""
    return _ROLE_IN_CLUB[role]
```

The map must be **total**. The inline version uses `.get(body.role, ClubRole.parent)`
(`users.py:117`) and has no `admin` key, so an admin account created with a club would
silently become a club `parent` — `ClubRole.admin` exists (`backend/app/models/club.py:17-21`)
and the seed uses it (`backend/scripts/seed.py:151-157`).

### 1.4 Set-password email (FR-023)

No `welcome_coach` template is introduced. The existing reset flow is reused, exactly as in
`backend/app/routers/auth.py:283-321`:

1. `password_reset_service.request_reset(new_user.email, db)` → `(user, reset_url)`
   (`backend/app/services/password_reset.py:57-117`).
2. `notification_service.send(NotificationRequest(..., template=NotificationTemplate.PASSWORD_RESET, context={"reset_url", "club_name", "ttl_minutes"}, send_async=True), dispatcher=get_task_dispatcher(background_tasks))`
   — the spec of that template is `backend/app/services/notification/template_registry.py:307-323`;
   DI helpers at `backend/app/dependencies.py:186,202`.

`send_async=True` + `BackgroundTasks` means the mail is dispatched **after** the response,
therefore after `get_db` commits: a rolled-back creation never mails anybody.

One guard must be relaxed. `request_reset` early-returns for `not user.hashed_password`
(`password_reset.py:76-83`), which is precisely the state a fresh staff account is in. The
condition becomes role-scoped:

```python
if (
    user is None
    or not user.is_active
    or not user.can_login
    or (not user.hashed_password and user.role not in (UserRole.coach, UserRole.admin))
):
    return None
```

Role-scoping (rather than an `allow_unset_password` flag passed only by `create_user`) is
deliberate: it also fixes the dead end where the first link expires
(`password_reset_token_ttl_minutes`) and the new coach cannot self-serve
`POST /api/auth/password-reset/request`. Parent and athlete behaviour is byte-identical —
a pre-created parent still has no password path and must go through `parent_invites`.

The public endpoint keeps its neutral response (`auth.py:283-321`), so nothing about
account existence leaks.

### 1.5 Audit rows

Two rows sharing one `request_id` (FR-002, AS5). Values are limited to
`VALUE_ALLOWLIST` (`data-model.md` §2.5): `user → {role, is_active, can_login}`,
`club_member → {club_id, role_in_club}`. `first_name`, `last_name`, `email` and `phone`
appear in `changed_fields` **as names only** and never in `diff_json`.

| `entity_type` | `action` | `entity_id` | `club_id` | `changed_fields` | `reason_code` | `meta_json` |
|---|---|---|---|---|---|---|
| `user` | `create` | `new_user.id` | `body.club_id` | `["email","first_name","last_name","phone","role","can_login"]` | — | `{"set_password_email": true}` |
| `club_member` | `create` | `membership.id` | `body.club_id` | `["club_id","user_id","role_in_club"]` | — | — |

### 1.6 Response `201`

```json
{
  "id": 12,
  "email": "ana.rivera@example.org",
  "first_name": "Ana",
  "last_name": "Rivera",
  "phone": "3001234567",
  "role": "coach",
  "is_active": true,
  "can_login": true,
  "created_at": "2026-09-09T14:03:11",
  "created_by_display_name": "Laura Méndez"
}
```

`UserOut` (`backend/app/schemas/user.py:32-43`) gains one optional field:

```python
created_by_display_name: str | None = None
```

It is never resolved by lazy-loading `User.creator` (`backend/app/models/user.py:46-51`) —
that would raise `MissingGreenlet` on the async session. `create_user` sets it from the
already-loaded `current_user`; `list_users` eager-loads (§3). The formatter is a plain
property on the model, reused by every author surface of FR-013:

```python
# backend/app/models/user.py
@property
def display_name(self) -> str:
    return f"{self.first_name} {self.last_name}".strip()
```

`created_by_display_name` is `null` when `users.created_by` is `NULL` (the seeded admin).
Adding an optional field is backwards compatible for the existing consumers
(`frontend/src/api/parents.ts:15-22`, `:89`).

---

## 2. `POST /api/clubs/{club_id}/members` — role coherence (FR-022)

**Router**: `backend/app/routers/clubs.py:114-160` (`add_member`), admin-only (`:123`).
**Schema**: `ClubMemberAdd` (`backend/app/schemas/club.py:32-34`).

Today the only checks are "club exists" (`clubs.py:125-131`) and "user exists and is
active" (`clubs.py:133-142`); `body.role_in_club` is written verbatim (`clubs.py:144-148`),
so a `parent` account can be filed as a club `coach`.

New rule, inserted between the user lookup (`clubs.py:137`) and the insert (`clubs.py:144`):

```python
expected = role_in_club_for(target_user.role)
if body.role_in_club != expected:
    raise HTTPException(
        status_code=422,
        detail=f"El rol en el club debe coincidir con el rol de la cuenta (se esperaba '{expected.value}')",
    )
```

| Situation | Code | `detail` |
|---|---|---|
| `role_in_club` matches the account role | `201` | `ClubMemberOut` (unchanged, `clubs.py:158-160`) |
| `role_in_club` contradicts the account role | `422` | `El rol en el club debe coincidir con el rol de la cuenta (se esperaba 'coach')` |
| user is inactive or unknown | `404` | `Usuario no encontrado` (unchanged) |
| club unknown | `404` | `Club no encontrado` (unchanged) |
| already a member | `409` | `El usuario ya es miembro de este club` (unchanged) |
| caller is not admin | `403` | `No tienes permisos para esta acción` (unchanged) |

Audit: one row, `entity_type=club_member`, `action=create`, `changed_fields=["club_id","user_id","role_in_club"]`.

There is no membership *update* or *delete* endpoint (`backend/app/routers/clubs.py` exposes
only `POST /{club_id}/members`, `:114`), so `role_in_club` can never change after creation
and this feature adds none.

---

## 3. `GET /api/users` — staff list (FR-020)

**Router**: `backend/app/routers/users.py:140-217` (`list_users`).
**Auth**: `require_role([UserRole.admin, UserRole.coach])` — unchanged. The coach branch
(`users.py:181-209`) is untouched; the staff screen is admin-only at the route level (§7),
and a coach calling this endpoint keeps seeing only members of their own clubs.

### 3.1 Query parameters

| Param | Type | Default | Notes |
|---|---|---|---|
| `role` | repeatable `UserRole` | none | **changed** from a single value to `Annotated[list[UserRole] \| None, Query()]`. `?role=coach&role=admin` is the staff query. Backwards compatible: `?role=parent` still parses (one-element list), so `getParentUsers` (`frontend/src/api/parents.ts:15-22`) needs no change. `athlete` anywhere in the list keeps returning `400` with `Los atletas se gestionan a través de /api/athletes` (`users.py:151-156`). |
| `club_id` | `int` | none | unchanged; joins `club_members` (`users.py:162-173`). |
| `is_active` | `bool` | none | **new**. Absent → both states. |

### 3.2 Response `200`

```json
{
  "items": [
    {
      "id": 3,
      "email": "coach.principal@example.org",
      "first_name": "Laura",
      "last_name": "Méndez",
      "phone": null,
      "role": "coach",
      "is_active": true,
      "can_login": true,
      "created_at": "2026-02-01T09:12:44",
      "created_by_display_name": null
    },
    {
      "id": 12,
      "email": "ana.rivera@example.org",
      "first_name": "Ana",
      "last_name": "Rivera",
      "phone": "3001234567",
      "role": "coach",
      "is_active": false,
      "can_login": true,
      "created_at": "2026-09-09T14:03:11",
      "created_by_display_name": "Laura Méndez"
    }
  ],
  "total": 2
}
```

`UserListOut` (`backend/app/schemas/user.py:46-48`) is unchanged in shape.

### 3.3 Query construction

- Add `.options(selectinload(User.creator))` next to the existing
  `selectinload(User.club_memberships)` (`users.py:166`, `:178`, `:201`). One extra
  `SELECT … WHERE users.id IN (…)`, no N+1 — asserted by a query-count test (§14.1).
- Add a deterministic order, which the endpoint lacks today:
  `ORDER BY users.is_active DESC, users.last_name, users.first_name, users.id`.
  Ordering by `role` is avoided on purpose: `Enum(UserRole)` is a MySQL `ENUM` (declaration
  order) but a `VARCHAR` on the aiosqlite lane (alphabetical), so it would not be stable
  across the two test lanes.
- `items` are built explicitly (`UserOut(..., created_by_display_name=u.creator.display_name if u.creator else None)`)
  instead of relying on `from_attributes` coercion of the ORM rows (`users.py:217`).
- **No pagination is added.** Staff cardinality is 3 for this club and the endpoint's other
  caller (`role=parent`) tops out around 40 rows; `UserListOut` already reports `total`.
  This is the one read surface of feature 041 that is *not* paginated — the history and
  per-coach views are (R-28).

### 3.4 Interaction with `club_id`

The `club_id` filter is an inner join on `club_members` (`users.py:162-173`), so an account
with **no** membership is invisible under it. That is exactly the population §1.2 row 4
exists to prevent, but pre-041 rows can already be in that state. The staff page therefore
does **not** send `club_id` (§8), so a legacy club-less coach is still listed and can be
deactivated. `club_id` remains supported for multi-club callers.

---

## 4. `PATCH /api/users/{user_id}` — deactivate / reactivate (FR-020)

**Router**: `backend/app/routers/users.py:223-274` (`update_user`). No new action endpoints
(R-21): the role guard for a coach editing a peer coach/admin (`users.py:245-251`), the
club-membership check (`users.py:252-259`) and the self-deactivation refusal
(`users.py:260-265`) all already exist and are reused verbatim.

### 4.1 Request

```json
{ "is_active": false, "reason_code": "account_end_of_engagement" }
```

`UserUpdate` (`backend/app/schemas/user.py:25-29`) gains:

```python
reason_code: AccountStateReasonCode | None = None   # never persisted on `users`
```

**`reason_code` must be excluded from the write loop.** `update_user` applies the body
blindly — `update_data = body.model_dump(exclude_none=True)` then `setattr(target, field, value)`
(`users.py:267-270`) — so an unfiltered `reason_code` would be set as a stray attribute on
the ORM object. The loop becomes `body.model_dump(exclude_none=True, exclude={"reason_code"})`.

`role` is **not** added to `UserUpdate`: no US3 scenario changes an account's role, and
doing so would require rewriting `club_members.role_in_club` in the same transaction and
invalidating tokens (the JWT carries `role`, `backend/app/routers/auth.py:81`).
Consequently `AuditAction.role_change` has no writer in this feature; it stays in the
diff-driven action mapper (§4.3) and is covered by a mapper unit test, not a route test.

### 4.2 Rules

| Situation | Code | `detail` |
|---|---|---|
| admin sets `is_active` on a coach/admin, with a valid `reason_code` | `200` | `UserOut` |
| `is_active: false` without `reason_code` | `422` | `Debes indicar el motivo de la desactivación` |
| `reason_code` outside the `account_*` / `parent_*` groups | `422` | `Motivo no válido` |
| `is_active: true` without `reason_code` | `200` | allowed; the client sends `account_reactivation` (§10) |
| coach targets a coach/admin | `403` | `No tienes permisos para editar este usuario` (`users.py:247-251`) |
| coach targets a user outside their clubs | `403` | `Este usuario no pertenece a ninguno de tus clubes` (`users.py:255-259`) |
| anyone deactivates themselves | `403` | `No puedes desactivarte a ti mismo` (`users.py:261-265`) — see note |
| unknown user | `404` | `Usuario no encontrado` (`users.py:238-242`) |

Note on self-deactivation: the guard at `users.py:260-265` is nested inside
`if current_user.role == UserRole.coach:` (`users.py:245`), so an **admin** can currently
deactivate their own account and lock everyone out of `/admin/usuarios`. The guard is
hoisted out of the coach branch to apply to every caller. Copy unchanged.

`reason_code` is mandatory for `deactivate` on `user` per `data-model.md` §2.4; the accepted
values are the account group (`account_staff_rotation`, `account_end_of_engagement`,
`account_security`, `account_reactivation`) plus the parent group
(`parent_family_request`, `parent_duplicate_account`) so a coach deactivating a family
account has a truthful option.

### 4.3 Audit action mapping

One row per request, `entity_type=user`, `entity_id=user_id`, `club_id` = the target's
first membership (or `NULL` for a club-less admin):

| Diff | `action` | `changed_fields` | `diff_json` |
|---|---|---|---|
| `is_active: true → false` | `deactivate` | `["is_active"]` | `{"is_active": {"before": true, "after": false}}` |
| `is_active: false → true` | `activate` | `["is_active"]` | `{"is_active": {"before": false, "after": true}}` |
| `role` differs | `role_change` | `["role"]` | `{"role": {"before": "coach", "after": "admin"}}` |
| anything else | `update` | e.g. `["first_name","phone"]` | `null` — those fields are not allow-listed (`data-model.md` §2.5) |
| no field actually changes | — | no row is written | — |

### 4.4 Effect of deactivation (US3 AC6)

Nothing new is written. Sign-in already fails with the existing message
`Usuario desactivado` (`backend/app/routers/auth.py:68-72`) — that is the message US3 AC6
requires to be preserved — and any live access token stops working at the next request,
because `get_current_user` rejects `not user.is_active` with `Token inválido`
(`backend/app/dependencies.py:68-72`). The person's name keeps resolving on past audit rows
through `audit_log.actor_user_id` (`ondelete=RESTRICT`, `data-model.md` §1), never through
a denormalised copy.

---

## 5. What deliberately does not change

| Behaviour | Site | Why |
|---|---|---|
| `DELETE /api/users/{id}` refuses `admin`/`coach` targets | `backend/app/routers/users.py:317-321` | Kept unconditional (R-21). Only the copy changes, and that change is owned by `contracts/athlete-archive.md` together with the status-code decision (§0). The staff screen shows **no** delete affordance (FR-018). |
| Parent creation via `POST /api/users` | `users.py:78-79`, `frontend/src/api/parents.ts:89` | `password`/`club_id` rules for `role=parent` are untouched; `backend/tests/test_users.py:60-90,194-229` must stay green as written. |
| The coach branch of `GET /api/users` | `users.py:181-209` | The staff screen is admin-only; coaches keep their club-scoped view for the Padres page. |
| `_coach_club_ids` duplicated in `users.py:29-30` vs `permissions.py:71` | — | Two copies only; the constitution's rule of three is not met, so it is left alone rather than churned in this feature. |

---

## 6. Frontend — route, guard and navigation (FR-021)

**Path**: `/admin/usuarios`. **Page**: `frontend/src/routes/admin/StaffPage.tsx` (new).

Declared exactly like every other route in `frontend/src/App.tsx` — `React.lazy` +
`Suspense` + `ProtectedRoute` (R-30), modelled on the `/admin/ai` block at
`frontend/src/App.tsx:116-121` and `:427-436`:

```tsx
const StaffPage = lazy(() =>
  import("@/routes/admin/StaffPage").then((m) => ({ default: m.StaffPage })),
);

<Route
  path="/admin/usuarios"
  element={
    <ProtectedRoute allowedRoles={[UserRole.admin]}>
      <Suspense fallback={<RouteFallback label="Cargando personal..." />}>
        <StaffPage />
      </Suspense>
    </ProtectedRoute>
  }
/>
```

`ProtectedRoute` (`frontend/src/routes/ProtectedRoute.tsx:14-57`) redirects a coach to
`/dashboard` via `ROLE_FALLBACKS` (`:46-51`). That is the *guard*; hiding the entry is the
separate config layer.

**Navigation entry** — the staff screen is reached through the config-driven model in
`frontend/src/lib/navigation.ts` (`NAV_AREAS`, `:76-201`), **not** through ad-hoc JSX. This
is the explicit correction of the `/admin/ai` precedent, which has no `NAV_AREAS` entry and
is hand-wired twice (`frontend/src/components/layout/UserMenu.tsx:233-243`,
`frontend/src/components/layout/MoreSheet.tsx:77-84`).

Feature 041 adds **exactly one** new area — `gobierno` ("Gobierno", `group: "club"`,
`roles: ["coach", "admin"]`) — shared by the three governance screens. Its full literal
(area fields, the three items and their order) is declared **once**, in
`contracts/coach-activity-report.md` §8.2; that contract also owns the
`frontend/src/lib/__tests__/navigation.test.ts` count and id-list updates. This contract
adds **no** area of its own and MUST NOT re-declare the literal.

What this contract owns inside that shared area is a single item, cross-referenced here so
the staff screen is traceable from end to end:

| Field | Value | Declared in |
|---|---|---|
| Item id | `gobierno.staff` | `contracts/coach-activity-report.md` §8.2 |
| Label | "Personal del club" | idem |
| `to` | `/admin/usuarios` | idem |
| `roles` | `["admin"]` — item-level, so a coach never sees it | idem |

Consequences, all automatic. The `gobierno` area itself **is** visible to a coach (it is how
a coach reaches `/club/historial`), so the coach-side guarantee of FR-021 is item-level, not
area-level: `SidebarNav` filters sub-items by `item.roles.includes(role)`
(`frontend/src/components/layout/SidebarNav.tsx:286`), so "Personal del club" is absent from
a coach's sidebar; and `resolveAreaDefaultTo` (`frontend/src/lib/navigation.ts:208-215`)
resolves the area's row in `MoreSheet` (`MoreSheet.tsx:39-62`, which renders
`getMoreSheetAreas(role)` generically) to the first item visible to the role — `/club/historial`
for a coach, never `/admin/usuarios`. The area's `matchPrefixes` list the literal
`/admin/usuarios`, not `/admin`, so it never claims an active state for `/admin/ai`; moving
`/admin/ai` into this area is a follow-up, not part of this contract. `ProtectedRoute`
remains the enforcement layer regardless of what the navigation renders.

**Persistence**: the new query keys are **not** added to `PERSIST_ALLOWLIST_PREFIXES`
(`frontend/src/lib/persistAllowList.ts:49-64`). The persister is default-deny, so staff
names and emails never reach the device cache; the omission is intentional and should be
stated in the PR so a reviewer does not read it as an oversight.

---

## 7. Frontend — data layer

New modules, following the existing per-domain layout (`src/api/*.ts` + `src/hooks/<domain>/*`;
`plan.md` sketches `hooks/useStaff.ts` at the hooks root — this contract places the hooks in
`hooks/admin/` to match `hooks/parents/`, `hooks/athletes/`, …):

| File | Exports |
|---|---|
| `frontend/src/api/users.ts` (new) | `listUsers(params)`, `createStaffUser(payload)`, `setUserActive(id, body)` |
| `frontend/src/api/clubs.ts` (new) | `listClubs()` → `GET /api/clubs/` (`backend/app/routers/clubs.py:50-57`) |
| `frontend/src/hooks/admin/useStaff.ts` | `useStaff({ isActive })` |
| `frontend/src/hooks/admin/useCreateStaff.ts` | `useCreateStaff()` |
| `frontend/src/hooks/admin/useSetStaffActive.ts` | `useSetStaffActive()` |
| `frontend/src/hooks/admin/useClubs.ts` | `useClubs()` |
| `frontend/src/types/user.types.ts` (`:3-18`) | `UserOut` gains `created_by_display_name: string \| null` |

Query shape follows the established filtered-list convention
(`frontend/src/hooks/parents/useParentUsers.ts:6-14`, plus `keepPreviousData` from R-28 so
the table does not flash empty on a filter change):

```ts
useQuery({
  queryKey: ["staff", "list", { isActive }],
  queryFn: () => listUsers({ role: ["coach", "admin"], is_active: isActive }),
  placeholderData: keepPreviousData,
  enabled: !!accessToken,
});
```

Mutations invalidate `["staff"]`, mirroring
`frontend/src/hooks/parents/useCreateParentUser.ts:5-13`.

The list request sends **no** `club_id` (§3.4). `listClubs()` is used only to populate the
club field of the creation sheet.

---

## 8. Frontend — "Personal del club" page

`StaffPage` composition, built from shared components only (constitution III):

```text
StaffPage
├── PageHeader  title="Personal del club"
│                subtitle="Entrenadores y administradores con acceso al club."
│                actions=<Button>+ Nuevo entrenador</Button>
├── filter row  ── Select "Estado": Todos · Activos · Inactivos
├── StaffTable  ── ui/table.tsx (Table/TableHeader/TableRow/TableHead/TableBody/TableCell)
│                  columns: Nombre · Rol · Estado · Creado el · Creado por · Acciones
├── StaffCreateSheet   (§9)
└── StaffStateDialog   (§10)
```

Cell rendering:

| Column | Source | Rendering |
|---|---|---|
| Nombre | `first_name` + `last_name` | plain text; the email below in `text-mid-gray text-xs` |
| Rol | `role` | `Entrenador` / `Administrador` |
| Estado | `is_active` | `StatusBadge` (`frontend/src/components/shared/StatusBadge.tsx:52`) — `success` "Activo" / `neutral` "Inactivo". Colour is never the only channel (icon + label). |
| Creado el | `created_at` | `formatDateMedium` (`frontend/src/lib/datetime.ts:84`) |
| Creado por | `created_by_display_name` | the name, or `—` when `null` |
| Acciones | — | one `Button variant="outline"` per row: "Desactivar" / "Reactivar"; hidden for the signed-in admin's own row (the API refuses it, §4.2) |

`created_at` is naive UTC (`backend/app/models/user.py:40-42`), so a timestamp within five
hours of midnight UTC renders one day early in `America/Bogota`. This is the app's existing
behaviour for every stored timestamp and is not corrected here.

### States (per async surface)

| State | Rendering |
|---|---|
| Loading | 3 skeleton rows inside the table shell (same shape as `frontend/src/routes/athletes/AthletesListPage.tsx:122-129`) |
| Empty (`total === 0`) | `EmptyState` title `"Aún no hay personal registrado."`, action = the "+ Nuevo entrenador" button |
| Empty under a filter | `EmptyState` title `"No hay personal con ese estado."`, no CTA |
| Error | `ErrorState message="No se pudo cargar el personal del club." onRetry={() => void staffQuery.refetch()}` |
| Cold start | `ErrorState isColdStart` — `isColdStartError(err)` (`frontend/src/components/shared/ErrorState.tsx:101`), never a bare spinner (constitution IV) |
| Mutation error | inline (`role="alert"`) inside the sheet/dialog, text from `extractErrorDetail(err, fallback)` (`frontend/src/lib/apiError.ts:32-60`) |
| Mutation success | `toast.success(...)` (`frontend/src/components/ui/sonner.tsx`; `Toaster` mounted at `frontend/src/App.tsx:805`) |

---

## 9. Frontend — "Nuevo entrenador" sheet

`frontend/src/components/admin/StaffCreateSheet.tsx`, on `ui/sheet.tsx`
(`side="right"`, exports at `frontend/src/components/ui/sheet.tsx:137-149`). Radix supplies
the focus trap, Escape dismissal and scroll lock; a `SheetTitle` is mandatory (R-29). The
bespoke `role="dialog"` panel of `frontend/src/components/parents/ParentFormDialog.tsx:69-107`
is **not** copied — only its React Hook Form + Zod wiring (`:1-33`, `:45-67`) is.

### Schema — `frontend/src/schemas/staff.schema.ts`

```ts
export const staffCreateSchema = z
  .object({
    first_name: z.string().trim().min(2, "Mínimo 2 caracteres"),
    last_name: z.string().trim().min(2, "Mínimo 2 caracteres"),
    email: z.string().trim().email("Correo electrónico inválido"),
    phone: z.string().trim().optional().or(z.literal("")),
    role: z.enum(["coach", "admin"]).default("coach"),
    club_id: z.number().int().positive().nullable().default(null),
  })
  .superRefine((val, ctx) => {
    if ((val.role === "coach" || val.role === "admin") && !val.club_id) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "El club es obligatorio para un entrenador",
        path: ["club_id"],
      });
    }
  });

export type StaffCreateValues = z.infer<typeof staffCreateSchema>;
```

The conditional-required idiom is the one already in the codebase
(`frontend/src/schemas/calendar.schema.ts:143-154`), per R-31. `role` stays in the schema —
mirroring the backend rule, which is a property of the created role — even though the sheet
renders no role control: `_ALLOWED_CREATIONS[admin]` (`backend/app/routers/users.py:23-26`)
lets an admin create only a coach, so `role` is fixed to `"coach"` and the sheet is titled
accordingly. Native HTML5 `required` is never used alongside Zod (constitution III).

### Fields

| Field | Control | Notes |
|---|---|---|
| Nombres | `input` | `autoComplete="off"` |
| Apellidos | `input` | |
| Correo electrónico | `input type="email"` | the address the set-password link goes to |
| Teléfono (opcional) | `input type="tel"` | sent as `null` when blank |
| Club | `ui/select.tsx` (`Select`/`SelectTrigger`/`SelectContent`/`SelectItem`) fed by `useClubs()` | **starts empty** with placeholder `"Selecciona un club"`, even when the account has exactly one club — otherwise US3 AS1 ("submit without a club → inline error") is unreachable from the UI |

### Submit

`createStaffUser({ first_name, last_name, email, phone: phone || null, role: "coach", club_id })`
— `password` is never in the payload.

| Outcome | UI |
|---|---|
| `201` | close the sheet, invalidate `["staff"]`, `toast.success("Se creó la cuenta y se envió el correo para definir la contraseña.")` |
| `422` on `club_id` | `form.setError("club_id", { message: detail })`; sheet stays open |
| `409` duplicate email | `form.setError("email", { message: "Ya existe un usuario con ese correo electrónico" })` |
| `403` / `404` / network | inline `role="alert"` block above the footer, text from `extractErrorDetail` |

Submit is disabled while `isPending` and shows a spinner; the sheet cannot be dismissed
mid-flight.

---

## 10. Frontend — deactivate / reactivate confirmation

Reuses `frontend/src/components/shared/ConfirmDialog.tsx` (built on `ui/alert-dialog.tsx`,
so it never dismisses on overlay click and already restores focus to the trigger,
`:53-73`, `:84-97`). One additive change to that shared component: an optional
`children?: ReactNode` slot rendered between the header and the footer
(`ConfirmDialog.tsx:106` … `:114`), so the reason picker is a sibling of — not nested
inside — `AlertDialogDescription`, which is an `aria-describedby` target and must stay
non-interactive.

| Action | Dialog |
|---|---|
| Deactivate | `tone="danger"` (focus starts on "Cancelar"), title `"¿Desactivar esta cuenta?"`, description `"La persona no podrá volver a iniciar sesión. Su nombre seguirá visible en el historial de lo que hizo."`, **required** reason `Select`, confirm `"Desactivar"` |
| Reactivate | `tone="default"`, title `"¿Reactivar esta cuenta?"`, description `"La persona podrá iniciar sesión de nuevo con su contraseña actual."`, no reason control, confirm `"Reactivar"` |

Reason options come from the shared catalogue endpoint owned by
`contracts/audit-log-api.md` §14, consumed exactly like
`frontend/src/hooks/race/useRevisionReasons.ts:12` (the existing closed-catalogue
precedent), requested as `GET /api/audit/reason-codes?group=account`. Expected values and
labels:

| `reason_code` | Label |
|---|---|
| `account_staff_rotation` | Cambio de personal |
| `account_end_of_engagement` | Fin de vinculación |
| `account_security` | Motivo de seguridad |

Reactivation always sends `reason_code: "account_reactivation"` ("Reincorporación") so the
history sentence reads naturally, even though the API accepts its absence (§4.2).

Confirm is disabled until a reason is picked (deactivate only). The dialog stays open on
error and renders `extractErrorDetail(err)` through `ConfirmDialog`'s existing
`errorMessage` prop (`ConfirmDialog.tsx:36`, `:108-112`).

---

## 11. Copy (español neutro, with diacritics)

| Surface | Text |
|---|---|
| Page title / subtitle | `Personal del club` · `Entrenadores y administradores con acceso al club.` |
| Primary action | `+ Nuevo entrenador` |
| Filter | `Estado` · `Todos` · `Activos` · `Inactivos` |
| Table headers | `Nombre` · `Rol` · `Estado` · `Creado el` · `Creado por` · `Acciones` |
| Role values | `Entrenador` · `Administrador` |
| State badges | `Activo` · `Inactivo` |
| Row actions | `Desactivar` · `Reactivar` |
| Empty | `Aún no hay personal registrado.` · `No hay personal con ese estado.` |
| Error | `No se pudo cargar el personal del club.` |
| Sheet title | `Nuevo entrenador` |
| Sheet description | `La persona recibirá un correo para definir su contraseña.` |
| Sheet fields | `Nombres` · `Apellidos` · `Correo electrónico` · `Teléfono (opcional)` · `Club` |
| Club placeholder | `Selecciona un club` |
| Sheet footer | `Cancelar` · `Crear entrenador` |
| Create success | `Se creó la cuenta y se envió el correo para definir la contraseña.` |
| Zod messages | `Mínimo 2 caracteres` · `Correo electrónico inválido` · `El club es obligatorio para un entrenador` |
| Deactivate dialog | `¿Desactivar esta cuenta?` · `La persona no podrá volver a iniciar sesión. Su nombre seguirá visible en el historial de lo que hizo.` · `Motivo` · `Desactivar` |
| Reactivate dialog | `¿Reactivar esta cuenta?` · `La persona podrá iniciar sesión de nuevo con su contraseña actual.` · `Reactivar` |
| State-change success | `Se desactivó la cuenta.` · `Se reactivó la cuenta.` |
| Nav | item `Personal del club`, inside the shared `Gobierno` area (area label owned by `contracts/coach-activity-report.md` §8.2) |

Backend `detail` strings are those in §1.2, §2 and §4.2. No copy on this screen mentions a
minor, and no minor's data reaches it.

---

## 12. Accessibility and performance

- Every interactive target is ≥ 48 px: `min-h-12` on the primary button, the filter
  `SelectTrigger`, the per-row action buttons and both dialog buttons (already the case in
  `ConfirmDialog.tsx:118`, `:132`).
- The table is a real `<table>` with `<caption class="sr-only">Personal del club</caption>`
  and `scope="col"` headers; row actions carry an accessible name that includes the person
  (`aria-label="Desactivar a Ana Rivera"`), so the button is not a bare "Desactivar" out of
  context.
- The state filter is a labelled `Select`; changing it announces the new row count through
  an `aria-live="polite"` region ("N cuentas").
- `StatusBadge` conveys state with icon + text, never colour alone.
- Sheet and dialog inherit the Radix focus trap, Escape dismissal and focus return.
- jest-axe: zero violations on `StaffPage` (loaded, empty and error states), on the open
  `StaffCreateSheet` and on the open deactivate dialog (§14.2).
- Bundle: `/admin/usuarios` is a lazy chunk with no charts and no new dependency — well
  inside the 150 KB gzip budget for an additional lazy route.
- Backend: the list is one indexed query plus one `selectinload`; the write paths add one
  audit `INSERT` inside the existing transaction (constitution IV: reads p95 ≤ 500 ms,
  writes p95 ≤ 1500 ms).

---

## 13. Test ids (stable)

`staff-page`, `staff-state-filter`, `staff-table`, `staff-row-{id}`, `staff-row-state-{id}`,
`staff-row-created-by-{id}`, `staff-toggle-active-{id}`, `staff-new-button`,
`staff-create-sheet`, `staff-create-submit`, `staff-club-select`, `staff-state-dialog`,
`staff-reason-select`.

---

## 14. Required tests

### 14.1 Backend — `backend/tests/test_staff_admin.py` (new), plus updates

Two-coach fixture from R-32 (coach A and coach B in one club, a coach of another club, an
admin, a parent).

**`POST /api/users`**

1. admin + `role=coach` + `club_id` → `201`; the `club_members` row exists with
   `role_in_club="coach"` and `added_by_user_id` = the admin.
2. admin + `role=coach` **without** `club_id` → `422`, message of §1.2 row 4. *(This is the
   regression test for the readiness-audit bug; `backend/tests/test_users.py:32-57` asserts
   `201` today and must be rewritten in the same change.)*
3. admin + `role=coach` + `password` → `422` (FR-023).
4. admin + `role=coach` without `email` → `422`.
5. admin + `role=coach` + unknown `club_id` → `404` `Club no encontrado` (not the
   misleading `409`).
6. duplicate email → `409`, and **no** `club_members` row is left behind.
7. coach caller + `role=coach` → `403` (`_ALLOWED_CREATIONS`), asserted *before* the
   missing-club `422`.
8. `role=parent` paths unchanged: `backend/tests/test_users.py:60-83,84-106,107-133,134-153,174-193,194-229`
   stay green untouched.
9. the created account has `hashed_password IS NULL`, `is_active`, `can_login`.
10. a `PASSWORD_RESET` notification is dispatched exactly once with a `reset_url` (fake
    notification service / dispatcher); the response body never contains a password.
11. `request_reset` accepts a staff account with no password and still returns `None` for a
    password-less **parent** (regression on `password_reset.py:76-83`).
12. audit: two rows share one `request_id`, with `entity_type` `user` and `club_member`,
    `action=create`; `diff_json` contains no `first_name`/`last_name`/`email`/`phone` key.
13. new coach signs in and `GET /api/athletes` returns the club's athletes (US3 AC3 — the
    "empty app" regression).

**Existing tests that MUST be rewritten in the same change** — every one of them encodes a
behaviour FR-019/FR-023 invert, so leaving them alone either fails the suite or leaves a
green test asserting the old bug:

| Test | Today | After |
|---|---|---|
| `backend/tests/test_users.py:32-57` `test_admin_creates_coach` | posts a coach with **no** `club_id` and asserts `201` | must send `club_id`, must not send `password`, and asserts the membership row |
| `backend/tests/test_users.py:231-249` `test_create_coach_without_password_fails` | asserts `422` for a coach with no password | inverted: a coach with `club_id` + `email` and **no** password is now `201`. (It would stay green by accident — the body also omits `club_id` — which is exactly why it must be rewritten rather than left.) |
| `backend/tests/test_users.py:251-285` `test_duplicate_email_fails` | creates two coaches with `password` and no `club_id`, expecting `201` then `409` | both requests now `422`; add `club_id`, drop `password`, keep the `409` assertion |
| `backend/tests/test_users.py:289-308` `test_weak_password_returns_422` | asserts the `<8 chars` validator (`backend/app/schemas/user.py:17-22`) using `role=coach` | still `422`, but now for two reasons; re-point it at `role=parent` so it keeps testing the validator it was written for |

**`POST /api/clubs/{id}/members`**

14. coherent `role_in_club` → `201`.
15. `role_in_club="coach"` on a `parent` account → `422` (FR-022).
16. `role_in_club="parent"` on a `coach` account → `422`.
17. coach caller → `403`; unknown club → `404`; duplicate → `409` (unchanged).
18. unit test on `role_in_club_for`: total over `UserRole`, and `admin → ClubRole.admin`.

**`GET /api/users`**

19. `?role=coach&role=admin` returns only staff; `?role=parent` (single value) still works.
20. `?role=athlete` → `400` (unchanged).
21. `?is_active=false` returns only deactivated accounts; omitted → both.
22. `created_by_display_name` resolves the creator's name, is `null` for a creator-less
    account, and still resolves for a **deactivated** creator (FR-013).
23. query count is constant for 1 vs 10 staff rows (no N+1 on `User.creator`).
24. ordering is deterministic (active first, then surname).
25. coach caller sees only their clubs' users; parent → `403`.

**`PATCH /api/users/{id}`**

26. admin deactivates a coach with a reason → `200`, `is_active=false`, audit
    `action=deactivate` with `reason_code`.
27. deactivate without `reason_code` → `422`.
28. deactivate with a reason outside the accepted groups → `422`.
29. reactivate → `200`, audit `action=activate`.
30. `reason_code` is not persisted on `users` (no stray attribute; regression on the blind
    `setattr` loop, `users.py:267-270`).
31. admin cannot deactivate themselves → `403` (regression: the guard is currently
    coach-only, `users.py:260-265`).
32. coach cannot deactivate a coach/admin → `403`; coach cannot touch a user outside their
    clubs → `403`.
33. a body that changes nothing writes no audit row.
34. after deactivation, `POST /api/auth/login` → `401` `Usuario desactivado` (US3 AC6,
    exact string) and a previously issued access token → `401`.
35. unit test on the action mapper: `role` diff → `role_change` (the branch has no route
    writer, §4.1).

**Privacy**

36. every `audit_log` row produced by the whole staff scenario passes the allow-list scan of
    `backend/tests/test_audit_privacy.py` (no name, no email, no phone in `diff_json` /
    `meta_json`).

### 14.2 Frontend

| File | Covers |
|---|---|
| `frontend/src/schemas/staff.schema.test.ts` | `club_id` missing → issue on `["club_id"]` with the exact message; valid payload passes; invalid email rejected; `role` defaults to `"coach"` |
| `frontend/src/routes/admin/__tests__/StaffPage.test.tsx` | loading skeleton → rows; the six columns render name, role label, `StatusBadge`, formatted date and creator name (`—` when `null`); the state filter refetches with `is_active`; empty and filtered-empty states; error state + retry; own row shows no action button |
| `frontend/src/routes/admin/__tests__/StaffPage.a11y.test.tsx` | jest-axe zero violations: loaded, empty, error; open create sheet; open deactivate dialog |
| `frontend/src/components/admin/__tests__/StaffCreateSheet.test.tsx` | submit without club → inline error, **no** request fired (US3 AS1); happy path posts without `password` and with `role: "coach"`; `409` maps to the email field; `422` maps to the club field; Escape closes; focus returns to `+ Nuevo entrenador` |
| `frontend/src/components/admin/__tests__/StaffStateDialog.test.tsx` | confirm disabled until a reason is chosen; PATCH body carries `is_active` + `reason_code`; reactivate sends `account_reactivation`; error keeps the dialog open |
| `frontend/src/lib/__tests__/navigation.test.ts` (update) | staff-side assertion only: `gobierno.staff` is among the items an `admin` sees and absent from the items a `coach` sees. The area count / id-list / grouped-area updates are made once, by `contracts/coach-activity-report.md` §8.2 |
| `frontend/src/components/layout/__tests__/{SidebarNav,BottomNav}.test.tsx` (update) | a coach rendering the `gobierno` area shows no "Personal del club" sub-item (item-level filter, `SidebarNav.tsx:286`); area counts, if asserted |
| `frontend/src/lib/__tests__/persistAllowList.test.ts` (update) | `isPersistableKey(["staff", "list", {}])` is `false` |
| `frontend/src/routes/__tests__/…` route guard | a coach navigating to `/admin/usuarios` lands on `/dashboard` (FR-021) |

MSW handlers live in `frontend/src/test/msw/staffHandlers.ts` (new), exporting synthetic
fixture factories in the style of `frontend/src/test/msw/growthSummaryHandlers.ts`, and are
registered in the shared `setupServer` at `frontend/src/test/setup.ts:18-25`. Fixtures use
invented adult names only — no minor appears anywhere in this feature's fixtures.

### 14.3 e2e (Playwright)

Deferred with the rest of feature 041's e2e work: the isolated stack cannot boot on a fresh
MySQL volume because of the pre-existing broken-import migrations documented in R-34. When
it is unblocked, the staff spec is: admin creates a coach → the row appears as active with
today's date and the admin as creator → the seeded `coach2` identity
(`frontend/e2e/helpers/session.ts`) signs in and sees the club's athletes → admin
deactivates → sign-in fails with `Usuario desactivado` → the coach session opens the
`Gobierno` area and finds no `Personal del club` entry in it.
