# API contract — 047 IMDERTY monthly attendance sheet

All routes are mounted under `/api` and require an authenticated **admin**, or a **coach** who is a member of the athlete's or club's club. Parents and athletes always get **403**, and each route has a denied-path test. Error bodies never echo field values of minors. `{club_id}` routes check club membership exactly as `routers/athletes.py` does.

## Athlete IMDERTY profile

### `GET /api/athletes/{athlete_id}/imderty-profile`
200 →
```json
{
  "athlete_id": 12,
  "first_surname": "…", "second_surname": "…",
  "surname_split": {"confirmed": false, "proposed_first": "…", "proposed_second": "…"},
  "document_type": "ti", "document_number": "…",
  "address": "…", "barrio": {"id": 5, "name": "…", "zone": "2"} , "other_municipality": false,
  "school": "…", "grade": "g5", "eps": "…", "phone": null,
  "guardians": [{"user_id": 40, "display_name": "…", "has_phone": true, "is_primary_contact": true}],
  "effective_phone_source": "primary_guardian",
  "sensitive": {"authorization": {"id": 3, "guardian_user_id": 40, "authorized_on": "2026-09-01", "active": true} | null}
}
```
An empty profile returns 200 with nulls; it is never a 404. Sensitive **values** are not included here (see below).

### `PUT /api/athletes/{athlete_id}/imderty-profile`
The body carries the editable fields above, plus `confirm_surname_split: bool`.
- **422 validation errors**:
  - digits-only for `rc`/`ti`/`cc`;
  - `barrio_id` together with `other_municipality=true`;
  - a confirmed split that does not rebuild `last_name`.
- **200** → the profile, plus `warnings: ["duplicate_document_in_club"]` when applicable.
- **Audit**: `update`, `changed_fields` only.

### `PUT /api/athletes/{athlete_id}/primary-contact`
Body `{"guardian_user_id": 40 | null}`. Returns 422 when the user is not a guardian linked to the athlete, and 200 → the guardians list.

## Sensitive data

### `POST /api/athletes/{athlete_id}/sensitive-authorizations`
Body `{"guardian_user_id": 40, "authorized_on": "2026-09-01"}`. It returns 409 if an active authorization exists, and 422 if the guardian is not linked or the date is in the future. On success it returns 201, creates the `athlete_sensitive_data` row with the defaults, and writes an audit `create` entry.

### `POST /api/athletes/{athlete_id}/sensitive-authorizations/withdraw`
Takes no body. It returns 404 if there is no active authorization. On success it returns 200, sets `withdrawn_at` and **deletes** the sensitive data row. The audit entry is `update` with `reason_code=withdrawn` and carries no values.

### `GET /api/athletes/{athlete_id}/sensitive-data`
Returns 200 → `{"ethnicity": "NO SABE NO RESPONDE", "disability": "N/A", "conflict_victim": null}`, or **404** when no active authorization exists.

### `PUT /api/athletes/{athlete_id}/sensitive-data`
Takes the three fields, each validated against the official lists. It returns **403** without an active authorization and 200 on success. The audit entry carries `changed_fields` only.

## Barrio catalog

- **`GET /api/imderty/barrios?include_inactive=false`**: open to admin and coach. Returns 200 → `[{id, name, zone, is_active}]`, ordered by name.
- **`POST /api/imderty/barrios`** and **`PATCH /api/imderty/barrios/{id}`**: **admin only**. Coaches get 403.
  - Body: `{name, zone, is_active}`.
  - Returns 409 when the name is duplicated.
  - Writes an audit entry.

## Club IMDERTY settings

- **`GET /api/clubs/{club_id}/imderty-settings`**: returns 200 → `{contractor_name, venue, training_days, schedule, programs: [...]}`, with nulls or an empty list when the club has never saved them.
- **`PUT /api/clubs/{club_id}/imderty-settings`**: get-or-create. Returns 200 and writes an audit entry with `changed_fields`.

## Sheet

### `GET /api/clubs/{club_id}/imderty-sheet/readiness?from=2026-08&to=2026-08`
- Returns 422 when `to < from`, when the range is longer than 12 months, or when it contains more than 480 athletes in a month.
- Returns 200 →
```json
{
  "months": ["2026-08"],
  "month_in_progress": false,
  "months_without_activity": [],
  "athlete_count": 27,
  "gaps": [{"athlete_id": 12, "display_name": "…", "codes": ["missing_document", "activity_without_record"], "activity_dates": ["2026-08-15"]}]
}
```
`display_name` is shown only to admin and coach, on screen, and is never logged.

### `POST /api/clubs/{club_id}/imderty-sheet`
Body:
```json
{"from": "2026-08", "to": "2026-12",
 "header": {"contractor_name": "…", "venue": "…", "training_days": "…", "schedule": "…", "programs": ["individual"]},
 "save_header_as_default": false}
```
- `header` is optional; when absent, the stored settings are used (FR-012).
- The same validation as the readiness endpoint applies.
- **200 response**:
  - body: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`;
  - header: `Content-Disposition: attachment; filename="FO-GDD-057_asistencia_2026-08_2026-12.xlsx"`. The file name holds only months, never personal data.
- The file is not stored.
- Audit `export` with `meta={document_kind:"imderty_attendance_xlsx", from_month, to_month, row_count, gap_count}`.

## Existing routes touched

- `PATCH /api/athletes/{id}`: when `last_name` changes, clear `surname_split_confirmed_at`.
- `GET /api/athletes/{id}` for a parent (`AthleteParentView`): unchanged; it MUST NOT include any key from this feature (test).
