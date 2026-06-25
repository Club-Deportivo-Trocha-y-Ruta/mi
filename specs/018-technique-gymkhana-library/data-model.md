# Phase 1 Data Model: Technique & Gymkhana Library + Session Builder

All new tables are prefixed `technique_*` (plus `athlete_skill_progress`). Enums use `values_callable` so the **string value** (not the Python name) is stored, per the project convention. Reused tables: `training_sessions`, `athletes`, `clubs`, `users`.

## Enums

| Enum | Values (stored strings) | Notes |
|---|---|---|
| `AgeBand` | `7-9`, `10-12`, `13-15` | Content reach 7–15; used on the age-band join. |
| `ExerciseDifficulty` | `facil`, `media`, `avanzada` | Maps to ①/②/③. Progression ranges live in `how_to`. |
| `SessionSegment` | `calentamiento`, `principal`, `vuelta_calma` | Warm-up / main set / cool-down. |
| `SkillProgressStatus` | `introducido`, `en_progreso`, `dominado` | 3-state per spec Assumption. |

## Tables

### `technique_skills` (seeded taxonomy A–H)
| Column | Type | Notes |
|---|---|---|
| `id` | PK int | |
| `code` | `CHAR(1)` | A–H (research §2). **Unique.** |
| `name` | `String(80)` | español neutro, e.g. "Frenado modulado". |
| `focus` | `String(200)` | short focus line from the taxonomy table. |
| `slug` | `String(60)` | filter key, e.g. `frenado`. **Unique.** |
| `sort_order` | int | progression order. |

### `technique_materials` (seeded)
| Column | Type | Notes |
|---|---|---|
| `id` | PK int | |
| `slug` | `String(40)` | e.g. `conos`, `llantas`, `estacas`, `topes`, `sin_material`. **Unique.** |
| `name` | `String(80)` | español neutro display label. |
| `is_none` | bool | `true` for the "sin material" sentinel. |

### `technique_exercises`
| Column | Type | Notes |
|---|---|---|
| `id` | PK int | |
| `slug` | `String(80)` | **Unique**; stable seed key for idempotency. |
| `name` | `String(120)` | e.g. "Limbo en bici". |
| `summary` | `String(300)` | one-line description for the card. |
| `how_to` | `Text` | "cómo correrlo": step-by-step coaching method (NICA Dilo→Muéstralo→Háganlo→Revísenlo) + mastery-climate framing (FR-007). |
| `difficulty` | `ExerciseDifficulty` | enum. |
| `is_game` | bool | "🎉 juego puro" engagement exercises. |
| `is_gymkhana` | bool | gymkhana exercises carry a layout (FR-008). |
| `layout_ascii` | `Text` null | preformatted monospace croquis (research §4); null for non-gymkhana. |
| `layout_alt` | `Text` null | plain-language text alternative for screen readers (WCAG). |
| `confidence` | `String(40)` null | research confidence tag (🟢/🟡/⚪ + refs), informational. |
| `is_seeded` | bool | `true` for rows from the research report. |
| `is_hidden` | bool | soft-hide from default catalog (FR-019); never hard-deleted. |
| `club_id` | FK `clubs.id` null | `null` = shared/seeded; set for club-custom exercises. |
| `created_by_user_id` | FK `users.id` null | null for seeded. |
| `created_at` / `updated_at` | datetime | UTC, `onupdate`. |

Indexes: `idx_technique_exercise_visibility (is_hidden, difficulty)`; unique `slug`.

### `technique_exercise_age_bands` (exercise ↔ age band)
| Column | Type | Notes |
|---|---|---|
| `exercise_id` | FK `technique_exercises.id` `ON DELETE CASCADE` | |
| `age_band` | `AgeBand` enum | |

PK `(exercise_id, age_band)`. One row per band an exercise targets (e.g. "7-15" → three rows).

### `technique_exercise_skills` (secondary M2M)
Core `Table`: `exercise_id` FK `technique_exercises.id` CASCADE, `skill_id` FK `technique_skills.id` RESTRICT. PK `(exercise_id, skill_id)`.

### `technique_exercise_materials` (secondary M2M)
Core `Table`: `exercise_id` FK `technique_exercises.id` CASCADE, `material_id` FK `technique_materials.id` RESTRICT. PK `(exercise_id, material_id)`. A "sin material" exercise links the `is_none` material.

### `technique_session_exercises` (link to the reused TrainingSession — FR-011/013/020)
| Column | Type | Notes |
|---|---|---|
| `id` | PK int | |
| `training_session_id` | FK `training_sessions.id` `ON DELETE CASCADE` | the **existing** session; no parallel store. |
| `exercise_id` | FK `technique_exercises.id` `ON DELETE RESTRICT` | hide-not-delete keeps saved sessions intact. |
| `segment` | `SessionSegment` enum | warm-up / main / cool-down. |
| `position` | int | order within the segment. |

Index `idx_tse_session (training_session_id)`. Presence of ≥1 row marks a TrainingSession as "technique-assembled".

### `athlete_skill_progress` (append-only events — US4, minors data)
| Column | Type | Notes |
|---|---|---|
| `id` | PK int | |
| `athlete_id` | FK `athletes.id` `ON DELETE CASCADE` | tracking only for athletes with a record (FR-018). |
| `skill_id` | FK `technique_skills.id` `ON DELETE RESTRICT` | |
| `status` | `SkillProgressStatus` enum | introducido / en_progreso / dominado. |
| `coach_note` | `String(300)` null | optional, mastery-climate phrasing; minors-safe. |
| `season` | int | year, for season scoping. |
| `recorded_by_user_id` | FK `users.id` RESTRICT | coach/admin. |
| `recorded_at` | datetime | UTC. **Latest per `(athlete, skill)` = current status.** |

Index `idx_asp_athlete_skill_time (athlete_id, skill_id, recorded_at)`.

## Relationships & loading

- `TechniqueExercise.skills` / `.materials` via `secondary=` association tables; `.age_bands` one-to-many. All eager-loaded with **`selectinload`** in list/detail reads (avoids N+1; Constitution IV).
- `TrainingSession` ⇄ `technique_session_exercises` (existing model gains a back-ref collection); reading a session can `selectinload` its technique exercises.

## Validation & invariant rules

1. **Gymkhana ⇒ layout** (FR-008): if `is_gymkhana` is true, `layout_ascii` MUST be non-null; non-gymkhana exercises may omit it.
2. **Materials subset filter** (FR-002, AC US1-4): an exercise matches an "available materials" set when **all** its required materials are within that set (correlated `NOT EXISTS`); `is_none` exercises always match (FR-009).
3. **At least one age band** per exercise; **at least one skill** per exercise (FR-003/006).
4. **Hide, never delete** (FR-019/020): curation sets `is_hidden = true`; `RESTRICT` FKs from sessions/progress prevent destroying referenced exercises/skills.
5. **Mixed-age notice** (FR-014): server computes `mixes_age_bands` from the assembled exercises' age bands; the session still saves.
6. **Current vs. history** (FR-016): current status = latest `athlete_skill_progress` row per `(athlete, skill)`; evolution = the ordered rows within a season.
7. **No comparison** (FR-017, SC-005): no endpoint or response returns cross-athlete skill rankings/aggregates; enforced by API shape (per-athlete only) and tests.
8. **Coach/admin only** (FR-021): every route gated by `require_role([admin, coach])` + club scope; no parent/athlete serializer exists.
