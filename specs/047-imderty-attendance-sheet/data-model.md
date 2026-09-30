# Data model — 047 IMDERTY monthly attendance sheet

There is one Alembic migration. Its `down_revision` is the current single head. `alembic heads` showed `be4595de1ad2` on 2026-09-28; re-check before writing the migration. Enums use `values_callable` (lower-case stored values), following project convention. All new tables carry `created_at`/`updated_at` and, where editable, `UpdatedByMixin`.

## Enums

| Enum | Stored values → label written to the sheet |
|---|---|
| `ImdertyDocumentType` | `rc`→`R.C`, `ti`→`T.I`, `cc`→`C.C`, `ce`→`C.E`, `ppt`→`PPT`, `pep`→`PEP`, `nes`→`NES` |
| `ImdertyGrade` | `prejardin`, `jardin`, `transicion`, `g1`…`g11`, `no_escolarizado`, `otro` → `PREJARDIN`, `JARDIN`, `TRANSICION`, `1`…`11`, `NO ESCOLARIZADO`, `OTRO` |
| `ImdertyEthnicity` | 9 official values: `AFROCOLOMBIANO`, `INDÍGENA`, `MESTIZO`, `MULATO`, `NO SABE NO RESPONDE`, `OTRO`, `PALENQUERO`, `RAIZAL`, `ROM GITANO` |
| `ImdertyDisability` | 10 official values: `OLFATIVA Y TACTO`, `MENTAL`, `MOVILIDAD`, `MULTIPLE`, `ORAL`, `PSICOSOCIAL`, `VISUAL`, `VOZ Y HABLA`, `NO SABE NOMBRARLA`, `N/A` |
| `ImdertyYesNo` | `si`→`SI`, `no`→`NO` (armed-conflict victim) |
| `ImdertyProgram` | 11 official programs: `masificacion`, `educacion_fisica_deporte_escolar`, `primera_infancia`, `hevs`, `recreacion`, `deporte_social_comunitario`, `lecyd_cda`, `competencia`, `conjunto`, `individual`, `adaptado` |

There is deliberately **no sexual-orientation enum or column anywhere** (FR-009).

## `athlete_imderty_profiles` (1:1 athlete, new)

| Column | Type | Rules |
|---|---|---|
| `athlete_id` | PK, FK `athletes.id` ON DELETE CASCADE | one profile per athlete; created lazily on first save |
| `first_surname` | String(100) NULL | required once the split is confirmed |
| `second_surname` | String(100) NULL | optional |
| `surname_split_confirmed_at` | DateTime NULL | cleared when `athletes.last_name` changes |
| `surname_split_confirmed_by_user_id` | FK users NULL | |
| `document_type` | `ImdertyDocumentType` NULL | |
| `document_number` | String(20) NULL | digits only for `rc`/`ti`/`cc` (FR-004); duplicate in the same club gives a warning, not a constraint |
| `address` | String(200) NULL | |
| `barrio_id` | FK `imderty_barrios.id` NULL, ON DELETE RESTRICT | mutually exclusive with `other_municipality` |
| `other_municipality` | Boolean default false | true ⇒ `barrio_id IS NULL` (CHECK) |
| `school` | String(150) NULL | the "I.E - COLEGIO - GRUPO - CLUB" column |
| `grade` | `ImdertyGrade` NULL | |
| `eps` | String(100) NULL | |
| `phone` | String(20) NULL | athlete's own phone, optional (FR-022) |

Invariant (service-level): a confirmed split must satisfy `normalize(first_surname + " " + second_surname) == normalize(athletes.last_name)`. The athlete `PATCH` clears `surname_split_confirmed_at` when `last_name` changes (research R7).

## `athlete_sensitive_authorizations` (append-only, new)

| Column | Type | Rules |
|---|---|---|
| `id` | PK | |
| `athlete_id` | FK athletes ON DELETE CASCADE | |
| `guardian_user_id` | FK users | must be a guardian linked to the athlete (`parent_athlete`) at record time |
| `authorized_on` | Date | not in the future |
| `recorded_by_user_id` | FK users | admin or coach |
| `recorded_at` | DateTime | |
| `withdrawn_at` | DateTime NULL | |
| `withdrawn_by_user_id` | FK users NULL | |
| `active_key` | Integer NULL, **UNIQUE** | equals `athlete_id` while active, NULL once withdrawn → at most one active authorization per athlete |

State: `active` → (withdraw) → `withdrawn`. A new authorization after a withdrawal is a new row.

## `athlete_sensitive_data` (1:1 athlete, new)

| Column | Type | Rules |
|---|---|---|
| `athlete_id` | PK, FK athletes ON DELETE CASCADE | |
| `authorization_id` | FK `athlete_sensitive_authorizations.id` | must be the active one |
| `ethnicity` | `ImdertyEthnicity` NOT NULL | default `NO SABE NO RESPONDE` on creation |
| `disability` | `ImdertyDisability` NOT NULL | default `N/A` on creation |
| `conflict_victim` | `ImdertyYesNo` NULL | no default; must be chosen explicitly |

Rules:
- A row may exist only while an active authorization exists. Withdrawal **deletes** this row in the same transaction (FR-007).
- Values never appear in logs, audit `diff_json` or AI context. The audit stores only `changed_fields`.

## `imderty_barrios` (platform-wide catalog, new)

| Column | Type | Rules |
|---|---|---|
| `id` | PK | |
| `name` | String(120), UNIQUE | upper case, diacritics kept |
| `zone` | String(20) | one of `1`,`2`,`3`,`4`,`ZONA NORTE`,`ZONA CENTRO`,`ZONA SUR` (CHECK) |
| `is_active` | Boolean default true | inactive entries are hidden from the picker but kept for existing profiles |

The migration seeds the entries of the official SECTOR sheet (82 unique entries after collapsing duplicate spellings) (public geography; the seed list lives in `app/services/imderty/barrios_seed.py`). Only the admin can create, rename, re-map or deactivate entries.

## `club_imderty_settings` (1:1 club, new)

| Column | Type | Rules |
|---|---|---|
| `club_id` | PK, FK clubs ON DELETE CASCADE | |
| `contractor_name` | String(200) NULL | adult contractor (coach); not a minor's data |
| `venue` | String(200) NULL | |
| `training_days` | String(120) NULL | e.g. "LUNES A VIERNES" |
| `schedule` | String(120) NULL | e.g. "4:00 PM A 6:00 PM" |
| `programs` | JSON list of `ImdertyProgram` values | at least one to mark "X"; may be empty |

## `parent_athlete` (existing, altered)

| Column | Type | Rules |
|---|---|---|
| `primary_contact_key` | Integer NULL, **UNIQUE** | equals `athlete_id` when this guardian is the athlete's "contacto principal"; at most one per athlete (FR-022a) |

## Derived, not stored

- **Day mark** `(athlete_id, date) → A | E | F | blank`: see research R4.
- **Active-in-month**: see research R5.
- **Sheet row** (all values upper-cased):
  - numbering and first name;
  - first surname: the confirmed value, or `last_name` while unconfirmed;
  - second surname;
  - birth date, and age as the formula already in the template;
  - document type label and number;
  - sex (`HOMBRE`/`MUJER`);
  - school and grade label;
  - disability, orientation and victim: disability and victim filled only with an active authorization, orientation always blank;
  - ethnicity: filled only with an active authorization;
  - address;
  - barrio name or `OTRO MUNICIPIO`;
  - comuna: the formula already in the template;
  - EPS, and phone following the fallback chain;
  - day cells, and totals as the formula already in the template.
- **Readiness gap** (per athlete):
  - `missing_document`;
  - `missing_barrio`;
  - `missing_eps`;
  - `missing_phone`;
  - `no_guardian`;
  - `multiple_guardians_no_primary`;
  - `surname_split_unconfirmed`;
  - `activity_without_record` (with dates).

## Audit (existing `audit_log`, new catalogue values)

- **`AuditEntityType`**: `athlete_imderty_profile`, `athlete_sensitive_authorization`, `athlete_sensitive_data`, `imderty_barrio`, `club_imderty_settings`, `imderty_attendance_sheet`.
- **`AuditDocumentKind`**: `imderty_attendance_xlsx`.
- **Export entry** (`action=export`): `meta = {document_kind, from_month, to_month, row_count, gap_count}`. It never carries names, document numbers or any value of the new fields.
