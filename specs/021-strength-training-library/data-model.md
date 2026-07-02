# Data Model: Strength Training Exercise Library (021)

**Migration**: `a7b8c9d0e1f2_strength_training_library.py` · `down_revision = "f1a2b3c4d5e6"` · schema + seed in one migration (018 pattern).

All models in `backend/app/models/strength.py`. Enums persisted via `SAEnum(..., values_callable=lambda e: [x.value for x in e])` (project convention). `AgeBand` is **reused** from `app.models.technique_exercise` (values `7-9`/`10-12`/`13-15`; 021 seeds and UI use only `10-12`/`13-15`).

## Enums (new)

| Enum | Values | Notes |
|---|---|---|
| `EquipmentKind` | `sin_equipo`, `equipo_gym` | FR-002. `equipo_gym` covers bands/dumbbells/machines; per-exercise `equipment_detail` text carries specifics |
| `MovementCategory` | `empuje_superior`, `traccion_superior`, `inferior_bilateral`, `inferior_unilateral`, `core_estabilidad` | FR-004; RT4T 5-category taxonomy (research D1) |
| `StrengthProgressStatus` | `introducido`, `en_progreso`, `dominado` | Same vocabulary as 018 `SkillProgressStatus` |

## Tables

### `strength_exercises`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | int PK | autoincrement | |
| `slug` | varchar(80) | unique, not null | Idempotent seed key (018 pattern) |
| `name` | varchar(120) | not null | Español neutro |
| `summary` | varchar(300) | not null | Card text |
| `how_to` | text | not null | Step-by-step execution (FR-007) |
| `common_errors` | text | not null | Newline-separated list (FR-007) |
| `illustration_ascii` | text | not null | Original ASCII figure (FR-006) |
| `illustration_alt` | varchar(500) | not null | a11y alt text — mandatory (Constitution III) |
| `equipment` | EquipmentKind | not null, indexed | FR-002 filter facet |
| `equipment_detail` | varchar(200) | nullable | e.g. "banda elástica", "mancuernas ligeras" |
| `movement_category` | MovementCategory | not null | FR-004 |
| `suggested_duration_min` | smallint | not null | Default per-entry minutes for running total (FR-010) |
| `suggested_reps` | varchar(60) | not null | e.g. "2×10-15" — text, honors RM ranges without prescribing load |
| `is_seeded` | bool | default false | |
| `is_hidden` | bool | default false | Soft-hide; never hard-delete (018) |
| `club_id` | FK clubs.id | nullable | null = shared seed |
| `created_by_user_id` | FK users.id | nullable | |
| `created_at` / `updated_at` | datetime | | |

Index: `idx_strength_exercise_visibility (is_hidden, equipment)`.

### `strength_exercise_age_bands`

Composite PK `(exercise_id, age_band)` — child table, one row per band (018 pattern; an exercise MAY carry both bands, FR-003).

| Column | Type | Constraints |
|---|---|---|
| `exercise_id` | FK strength_exercises.id | CASCADE |
| `age_band` | AgeBand (reused) | PK part |

### `strength_blocks`

Reusable, first-class block (research D5).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | int PK | | |
| `name` | varchar(120) | not null | FR-008 |
| `target_age_band` | AgeBand | not null | Guardrail context (FR-011) |
| `duration_target_min` | smallint | not null, default 30 | Configurable business rule (FR-009, research D2) |
| `club_id` | FK clubs.id | not null | |
| `created_by_user_id` | FK users.id | not null | |
| `is_archived` | bool | default false | Soft-archive |
| `created_at` / `updated_at` | datetime | | |

### `strength_block_entries`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | int PK | | |
| `block_id` | FK strength_blocks.id | CASCADE, indexed | |
| `exercise_id` | FK strength_exercises.id | **RESTRICT** | Hide-not-delete keeps saved blocks intact (018) |
| `position` | smallint | not null | Order within block |
| `duration_min` | smallint | not null | Per-block override of suggested default (FR-010) |
| `reps` | varchar(60) | nullable | Per-block override |
| `is_age_override` | bool | default false | FR-011 recorded override |
| `override_note` | varchar(300) | nullable | Coach's stated reason (optional) |

Unique `(block_id, position)`. Invariant: `is_age_override = true` **iff** the exercise's age bands do not include the block's `target_age_band` at insert time — enforced in `services/strength/blocks.py`, not by DB constraint.

### `strength_session_blocks`

Attach join — a block is reusable across sessions (FR-012/FR-013, assumption "no copy-on-attach").

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | int PK | | |
| `training_session_id` | FK training_sessions.id | **CASCADE**, indexed | Session deletion detaches cleanly (edge case: no orphaning) |
| `block_id` | FK strength_blocks.id | **RESTRICT** | Block survives session deletion |
| `position` | smallint | not null, default 0 | If multiple blocks per session |
| `attached_by_user_id` | FK users.id | not null | |
| `attached_at` | datetime | not null | |

Unique `(training_session_id, block_id)`.

### `strength_progress_notes`

Append-only (research D8); current state = latest row per `(athlete_id, exercise_id)`.

| Column | Type | Constraints |
|---|---|---|
| `id` | int PK | |
| `athlete_id` | FK athletes.id | CASCADE |
| `exercise_id` | FK strength_exercises.id | RESTRICT |
| `status` | StrengthProgressStatus | not null |
| `coach_note` | varchar(500) | nullable |
| `season` | smallint | not null |
| `recorded_by_user_id` | FK users.id | not null |
| `recorded_at` | datetime | not null |

Index: `idx_spn_athlete_exercise_time (athlete_id, exercise_id, recorded_at)`.

## Relationships (ORM)

- `StrengthExercise.age_bands` → child rows (selectinload in catalog query — Constitution IV, no N+1).
- `StrengthBlock.entries` → ordered by `position`, selectinload; `StrengthBlock.sessions` viewonly via join.
- `TrainingSession.strength_blocks` → back-populated on existing model (additive relationship only; `training_sessions` table untouched).

## Validation rules (service layer)

1. Block create/update: entries re-positioned 0..n-1; running total = Σ `duration_min` (indicator thresholds: `< target` within, `== target` at, `> target` over — computed client-side, echoed server-side in block read schema as `total_duration_min`).
2. Age guardrail (FR-011): on entry add where exercise bands ∌ `target_age_band` → API requires `is_age_override=true` in payload, else **422** with explanatory Spanish detail; override persisted.
3. Progress notes: athlete must belong to coach's club (`_require_athlete_club_scope` pattern from `technique.py:417`); responses never include athlete PII beyond id.
4. Catalog: `is_hidden=true` excluded unless `include_hidden` (admin curation later); free-text `q` matches `name`/`summary` LIKE, AND-combined with facets.

## State transitions

- Exercise: `visible ⇄ hidden` (soft). Never deleted once referenced (RESTRICT).
- Block: `active ⇄ archived` (soft). Entries mutable while active.
- Progress: append-only; no transitions, latest-wins read.

## Seed (in-migration, `app/data/strength_catalog.py`)

~22 exercises. Distribution commitment (SC-007): every non-empty valid filter combination has ≥1 exercise — `sin_equipo × 10-12`, `sin_equipo × 13-15`, `equipo_gym × 13-15` across all 5 movement categories; `equipo_gym × 10-12` intentionally empty (club rule) → UI empty-state. **Excluded content**: clean/snatch/deadlift/back-squat, 1RM protocols (FR-019).
