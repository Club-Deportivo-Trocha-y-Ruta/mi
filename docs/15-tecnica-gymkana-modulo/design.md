# Technique & Gymkhana Library — Module Design

**Feature**: specs/018-technique-gymkhana-library  
**Status**: Backend + frontend complete — deploy pending (migration `e1f2a3b4c5d6`)  
**Date**: 2026-06-25  
**Research source**: [docs/14-tecnica-gymkana-7-15/research.md](../14-tecnica-gymkana-7-15/research.md)

---

## Purpose

The module turns the club's scattered technique knowledge into a single, searchable in-app resource and ties it to real planning and per-athlete tracking. The coach browses a catalog of ~24 pre-seeded technique drills and gymkhana exercises, assembles them into a training session through the existing Training Sessions module, and records each athlete's progress per skill across the season.

It operationalizes the club's first non-negotiable: **skills before fitness**. It is not a fitness-prescription tool, not a comparison surface, and does not use AI/LLM.

---

## Data model

All tables are prefixed `technique_*` plus `athlete_skill_progress`. No new dependencies. Reuses `training_sessions`, `athletes`, `clubs`, `users`.

### Enums (stored string values, `values_callable` convention)

| Enum | Stored values | Notes |
|---|---|---|
| `AgeBand` | `7-9`, `10-12`, `13-15` | Content reach extends to 7; athlete records center on 10–15. |
| `ExerciseDifficulty` | `facil`, `media`, `avanzada` | Maps to ①/②/③ in the UI. |
| `SessionSegment` | `calentamiento`, `principal`, `vuelta_calma` | Warm-up / main set / cool-down. |
| `SkillProgressStatus` | `introducido`, `en_progreso`, `dominado` | 3-state per spec Assumption. |

### Core tables

#### `technique_skills` (seeded A–H taxonomy)

| Column | Type | Notes |
|---|---|---|
| `id` | PK int | |
| `code` | `CHAR(1)` UNIQUE | A–H (research §2). |
| `name` | `String(80)` | español neutro, e.g., "Frenado modulado". |
| `focus` | `String(200)` | Short focus line from the taxonomy table. |
| `slug` | `String(60)` UNIQUE | Filter key, e.g., `frenado`. |
| `sort_order` | int | Progression order. |

Taxonomy A–H: Posición y equilibrio · Visión · Frenado modulado · Control a baja velocidad · Trazado de curvas · Separación cuerpo-bici · Presión/terreno · Marcha y cadencia.

#### `technique_materials` (seeded)

| Column | Type | Notes |
|---|---|---|
| `id` | PK int | |
| `slug` | `String(40)` UNIQUE | e.g., `conos`, `llantas`, `estacas`, `topes`, `sin_material`. |
| `name` | `String(80)` | español neutro display label. |
| `is_none` | bool | `true` for the "sin material" sentinel. |

#### `technique_exercises`

| Column | Type | Notes |
|---|---|---|
| `id` | PK int | |
| `slug` | `String(80)` UNIQUE | Stable seed key for idempotency. |
| `name` | `String(120)` | e.g., "Limbo en bici". |
| `summary` | `String(300)` | One-line description for the card. |
| `how_to` | `Text` | Step-by-step coaching method (NICA Dilo→Muéstralo→Háganlo→Revísenlo) + mastery-climate framing. |
| `difficulty` | `ExerciseDifficulty` | |
| `is_game` | bool | Engagement/game exercises. |
| `is_gymkhana` | bool | Gymkhana exercises carry a layout. |
| `layout_ascii` | `Text` null | Preformatted monospace croquis from research §4; null for non-gymkhana. |
| `layout_alt` | `Text` null | Plain-language text alternative (WCAG). |
| `confidence` | `String(40)` null | Research confidence tag (strong/guia/comun), informational. |
| `is_seeded` | bool | `true` for rows from the research report. |
| `is_hidden` | bool | Soft-hide from default catalog; never hard-deleted. |
| `club_id` | FK `clubs.id` null | `null` = shared/seeded; set for club-custom exercises. |
| `created_by_user_id` | FK `users.id` null | null for seeded rows. |
| `created_at` / `updated_at` | datetime | UTC. |

Index: `idx_technique_exercise_visibility (is_hidden, difficulty)`.

#### Join tables

| Table | Columns | Notes |
|---|---|---|
| `technique_exercise_age_bands` | `(exercise_id FK CASCADE, age_band AgeBand)` | PK `(exercise_id, age_band)`. One row per band an exercise targets. |
| `technique_exercise_skills` | `(exercise_id FK CASCADE, skill_id FK RESTRICT)` | M2M. PK `(exercise_id, skill_id)`. |
| `technique_exercise_materials` | `(exercise_id FK CASCADE, material_id FK RESTRICT)` | M2M. PK `(exercise_id, material_id)`. "Sin material" exercise links the `is_none` sentinel. |

#### `technique_session_exercises` (session reuse link table)

| Column | Type | Notes |
|---|---|---|
| `id` | PK int | |
| `training_session_id` | FK `training_sessions.id` ON DELETE CASCADE | The **existing** session record; no parallel store (FR-011). |
| `exercise_id` | FK `technique_exercises.id` ON DELETE RESTRICT | RESTRICT ensures hiding never corrupts saved sessions (FR-020). |
| `segment` | `SessionSegment` enum | |
| `position` | int | Order within the segment. |

Index: `idx_tse_session (training_session_id)`.

#### `athlete_skill_progress` (append-only — minors data)

| Column | Type | Notes |
|---|---|---|
| `id` | PK int | |
| `athlete_id` | FK `athletes.id` ON DELETE CASCADE | Tracking only for athletes with a record (FR-018). |
| `skill_id` | FK `technique_skills.id` ON DELETE RESTRICT | |
| `status` | `SkillProgressStatus` enum | |
| `coach_note` | `String(300)` null | Optional mastery-climate note; minors-safe. |
| `season` | int | Year for season scoping. |
| `recorded_by_user_id` | FK `users.id` RESTRICT | Coach/admin only. |
| `recorded_at` | datetime | UTC. Latest per `(athlete, skill)` = current status. |

Index: `idx_asp_athlete_skill_time (athlete_id, skill_id, recorded_at)`.

Current status = latest event per `(athlete_id, skill_id)` within a season. Evolution = the ordered row set.

### Relationships and loading

`TechniqueExercise.skills` / `.materials` via `secondary=` association tables; `.age_bands` one-to-many. All eager-loaded with `selectinload` in list/detail reads (avoids N+1). `TrainingSession` gains a back-ref `technique_exercises` collection via the link table.

---

## REST API — `/api/technique`

All endpoints require authenticated coach or admin (`require_role([admin, coach])`). No parent or athlete endpoints exist. All copy in responses is español neutro.

### Catalog and discovery (US1)

| Method + Path | Description |
|---|---|
| `GET /api/technique/exercises` | List/filter catalog. Optional params: `skill` (slug), `age_band`, `difficulty`, `materials` (CSV slugs — subset filter), `include_hidden`, `is_game`. Returns `{ items: [ExerciseListItem], total: int }`. Empty result → 200 empty list, never 404 (FR-004). |
| `GET /api/technique/skills` | Seeded A–H taxonomy (for building filter controls). |
| `GET /api/technique/materials` | Seeded materials list. |

`ExerciseListItem`: `{ id, slug, name, summary, difficulty, is_game, is_gymkhana, age_bands, skills, materials, is_seeded, is_hidden }`.

### Exercise detail (US2)

| Method + Path | Description |
|---|---|
| `GET /api/technique/exercises/{id}` | Full detail = `ExerciseListItem` + `{ how_to, layout_ascii, layout_alt, confidence, created_at, updated_at }`. Gymkhana exercises include non-null `layout_ascii` + `layout_alt` (FR-008). |

### Session assembly via existing Training Sessions (US3)

| Method + Path | Description |
|---|---|
| `POST /api/technique/sessions` | Assembles exercises into a normal `TrainingSession` by calling `training_svc.create_session`, then writes `technique_session_exercises` rows in the same transaction. Returns `{ training_session_id, mixes_age_bands: bool, items }`. `mixes_age_bands=true` triggers the visible age-mix notice (FR-014); session still saves. |
| `GET /api/technique/sessions/{training_session_id}/exercises` | Returns the ordered `[TechniqueSessionItem]` a session was built from, grouped by segment. Survives later hide/edit of an exercise (FR-020). |

`TechniqueSessionItem`: `{ exercise_id, name, segment, position, age_bands, skills }`.

### Per-athlete skill progress (US4 — minors data, coach/admin only)

| Method + Path | Description |
|---|---|
| `GET /api/technique/athletes/{athlete_id}/progress` | Returns `{ athlete_id, current: [...], history: [SkillProgressEvent] }`. Current = latest event per skill; history = season-ordered events. No other athlete appears in the response (FR-017, SC-005). |
| `POST /api/technique/athletes/{athlete_id}/progress` | Appends a progress event. Body: `{ skill_id, status, coach_note?, season }`. Returns the created `SkillProgressEvent`. |

`SkillProgressEvent`: `{ id, skill: {code, slug, name}, status, coach_note, season, recorded_at }`. No minor PII beyond what the authenticated coach/admin may see in-app.

There is intentionally no endpoint that ranks or compares athletes (SC-005).

### Curation (US5 — coach/admin)

| Method + Path | Description |
|---|---|
| `POST /api/technique/exercises` | Create a custom exercise. Validation: gymkhana implies `layout_ascii` required; ≥1 age band; ≥1 skill. Returns `ExerciseDetail` with `is_seeded=false`, `club_id` set. |
| `PUT /api/technique/exercises/{id}` | Edit any exercise including seeded ones. Edits never alter a saved session's stored items (FR-020). |
| `PATCH /api/technique/exercises/{id}/visibility` | Hide/unhide. Body: `{ is_hidden: bool }`. Hidden rows leave the default catalog but are not destroyed. |

---

## Session reuse approach

A technique session is not a separate record type. When the coach saves an assembled session:

1. `assembler.py` calls `training_svc.create_session(db, club_id, session_data)` — the same service function used by the regular session wizard. This creates a `TrainingSession` row.
2. In the same transaction, `technique_session_exercises` rows are written linking the session to each selected exercise with its segment and position.
3. The result is an ordinary `TrainingSession` that appears in the existing calendar/list and supports the existing attendance and rubric flows (FR-012).

The link table uses `ON DELETE CASCADE` on the session FK (deleting the session removes the links) and `ON DELETE RESTRICT` on the exercise FK (hiding/editing never blanks a saved session, per FR-020).

---

## Illustrative circuit layout decision

**Decision**: store the ASCII croquis from the research report as preformatted monospace text (`layout_ascii`) and render it in a responsive `<pre>` element. A plain-language text alternative (`layout_alt`) is always present for screen readers (WCAG 2.1 AA).

**Alternatives considered and rejected**:

| Alternative | Why rejected |
|---|---|
| SVG generated from coordinates | Requires a layout coordinate schema and a rendering engine; significant complexity for v1 with no clear UX benefit over legible ASCII on a tablet. |
| Uploaded image (coach-provided PNG/JPEG) | Requires file upload infrastructure, storage, and alt-text authoring discipline; deferred to v2. |
| D3 / Canvas render | Same complexity argument as SVG; the ASCII source from the research report is already tablet-legible. |

The monospace layout is tablet-tested: the coach reads it at the field on a mid-tier Android device over 3G. `<pre>` with `overflow-x: auto` and a visible horizontal scroll cue (shadow or indicator) handles long rows. The screen-reader text alternative describes the circuit in plain language (e.g., "Slalom de 6 conos en línea recta, separados 2 m. El ciclista sigue un trayecto en zigzag entre los conos de inicio a fin.").

---

## Per-athlete progress: privacy and no-comparison design

The `athlete_skill_progress` table is the only minors-data surface in this module. Enforced invariants:

- Every progress endpoint checks club scope via `_require_athlete_club_scope()` (coach from Club B cannot read or write progress for an athlete in Club A).
- Progress responses carry no minor PII beyond `{ skill, status, coach_note, season, recorded_at }`. No name, DOB, identity document, or address.
- Error messages expose only the numeric `athlete_id`, never a name.
- `coach_note` is not logged anywhere in the backend.
- No endpoint, service function, UI component, or schema field provides cross-athlete comparison (SC-005). Verified by privacy audit + `SkillProgressBoard` frontend tests that explicitly assert absence of ranking/leaderboard/comparison elements.
- Test fixtures use clearly fictitious data (marked as such) with no real TyR athlete data.
- All Zod response schemas use `.strip()` (allowlist pattern) to prevent accidental deserialization of undeclared PII fields.

---

## Seeding

The catalog is seeded through an idempotent Alembic data migration (migration `e1f2a3b4c5d6`). The seed payload lives in `backend/app/data/technique_catalog.py`, which is loaded by the migration's `upgrade()` function. The seeding pattern mirrors `alembic/versions/c4d5e6f7a8b9_seed_race_categories.py`.

Seed content is loaded verbatim from [docs/14-tecnica-gymkana-7-15/research.md](../14-tecnica-gymkana-7-15/research.md) — nothing is invented. All content is in español neutro (Colombia). The migration is idempotent: re-running it on an environment that already has the seed data is safe (upsert-on-slug).

**Seed content corrections applied by audits (2026-06-25)**:

- Exercise 7 (Slalom de conos): dual-lane variant label changed from "slalom doble (dos filas, carrera de velocidad)" to "slalom doble (dos filas, duelo lado a lado)" to remove speed-race framing inconsistent with the mastery-climate non-negotiable.
- Exercises 8, 14, 24: `Revísenlo` questions corrected from Castilian vosotros conjugations to español neutro (ustedes form).
- Exercise 15 (Levantar rueda delantera → manual): difficulty changed from `avanzada` to `media`; PHV-awareness note added.
- Exercises 16, 17: PHV-awareness notes added covering growth-spurt load reduction and physeal vulnerability.
- Exercise 17 (Subir/bajar bordillo/drop): explicit prerequisite gate for the 10-12 band (skills A, C, F must be solid before introducing this exercise).
- Age-band mapping comment expanded to document the `11-15 → [10-12, 13-15]` approximation rationale and the sub-range interpretation.

---

## Content correctness alignment

The seeded catalog was reviewed against `docs/01-marco-teorico.md` and the club non-negotiables (2026-06-25 audit, `technique-coach` + `sports-science-advisor`):

- 80/20 play-based split for 7–12 bands: all exercises tagged for 7–9 are games or low-structure drills; no structured intervals appear anywhere.
- Skills-before-fitness sequencing: the A–H taxonomy follows the PMBIA/NICA progression order.
- Mastery climate: all 24 exercises carry a "Clima de maestría" paragraph emphasizing personal progress over peer comparison.
- Cadence: Skill H focus field prescribes ≥70 rpm, satisfying the ≥60 rpm non-negotiable with appropriate conservatism. Exercise 21 (Subida técnica corta) also references ≥70 rpm.
- RPE-primary/no-HR: Exercise 3 (Circuito de control) explicitly says "sin pulsómetro ni cronómetro"; no exercise references heart rate zones or power meters.
- Drop heights: Exercise 17 maximum 20–30 cm for 10+, well under the 50 cm hard limit for under-13.
- Bunny-hop gating: Exercise 16 correctly restricted to `age_bands=['13-15']` only, with j-hop progression enforced before full hop.
- Max 2 high-intensity sessions per week for 13–15: the gymkhana session example for that band is designed around skill circuits, not load accumulation.

---

## Frontend structure

```
frontend/src/
├── routes/technique/
│   ├── CatalogPage.tsx             # Browsable catalog with FilterBar
│   ├── ExerciseDetailPage.tsx      # Full detail + circuit layout
│   ├── SessionBuilderPage.tsx      # Assemble warm-up / main / cool-down
│   ├── AthleteProgressPage.tsx     # Per-athlete progress board (US4)
│   └── CatalogAdminPage.tsx        # Curation form (US5)
├── components/technique/
│   ├── CatalogGrid.tsx             # Exercise card grid
│   ├── FilterBar.tsx               # Skill / age band / difficulty / materials filters
│   ├── ExerciseCard.tsx            # List-item card
│   ├── CircuitLayout.tsx           # <pre> + layout_alt text alternative
│   ├── SessionAssembler.tsx        # Drag-and-drop segment builder
│   ├── MixedAgeNotice.tsx          # Visible flag when age bands mix (FR-014)
│   ├── SkillProgressBoard.tsx      # Per-athlete skill grid (US4, no comparison)
│   └── ExerciseForm.tsx            # Create/edit form (US5)
├── hooks/
│   ├── useTechniqueCatalog.ts
│   ├── useTechniqueExercise.ts
│   ├── useAssembleTechniqueSession.ts
│   └── useAthleteSkillProgress.ts
└── api/technique.ts                # Technique API client
```

---

## Backend structure

```
backend/app/
├── models/
│   ├── technique_skill.py          # TechniqueSkill + AgeBand enum
│   ├── technique_material.py       # TechniqueMaterial
│   └── technique_exercise.py       # TechniqueExercise, age-band/skill/material joins,
│                                   #   TechniqueSessionExercise, AthleteSkillProgress
├── schemas/
│   └── technique.py                # catalog filter/read, detail, assemble, progress, curation
├── routers/
│   └── technique.py                # 11 endpoints under /api/technique
├── services/technique/
│   ├── catalog.py                  # filter query (skill/age/difficulty/material subset)
│   ├── assembler.py                # build a TrainingSession via training_svc + join rows
│   └── progress.py                 # append progress event; current + season history
└── data/
    └── technique_catalog.py        # seed payload (skills, materials, ~24 exercises, layouts)
```

Migration: `backend/alembic/versions/e1f2a3b4c5d6_technique_gymkhana_library.py`.  
Tests: `backend/tests/technique/` (178 backend tests after privacy fix; see audit notes above).

---

## Test coverage summary

| Suite | Count | Notes |
|---|---|---|
| Backend technique tests | 178 | Filter, RBAC, assemble creates real session, progress append/current/history, no-comparison invariant, privacy (cross-club 403, no PII in response/log), migration idempotency |
| Performance query tests | 2 | `test_list_exercises_service_no_n1` + `test_list_exercises_endpoint_no_n1` assert ≤10 SELECT statements for 12 exercises (O(1) = 4 selects: main table + 3 selectinloads) |
| Frontend vitest + jest-axe | 230 | Catalog/detail/assembler/progress/curation + a11y zero violations; `SkillProgressBoard` explicitly asserts absence of ranking/leaderboard/comparison elements |

---

## Performance invariants

- Catalog + detail reads: p95 ≤ 500 ms (target). `selectinload` for all M2M relationships prevents N+1 (`O(1) = 4 SELECT` statements verified by `test_perf_queries.py`).
- Session assemble + progress writes: p95 ≤ 1500 ms (target).
- Catalog route LCP ≤ 2.5 s on mid-tier Android/3G.
- Cold-start banner present on every async surface (Render free tier ~50 s wake-up).
- All seeded data fits in a small TanStack Query cache; catalog responses are aggressively cached client-side.

---

## Access control

| Role | Catalog read | Progress read/write | Curation |
|---|---|---|---|
| Admin | Yes | Yes | Yes |
| Coach | Yes | Yes (own club only) | Yes |
| Parent | No (403) | No (403) | No (403) |
| Athlete | No (403) | No (403) | No (403) |
| Unauthenticated | No (401) | No (401) | No (401) |

Cross-club coach access to progress endpoints blocked by `_require_athlete_club_scope()` helper, verified by `test_progress_read_cross_club_coach_receives_403` and `test_progress_write_cross_club_coach_receives_403`.

---

## References

- Research source: [docs/14-tecnica-gymkana-7-15/research.md](../14-tecnica-gymkana-7-15/research.md)
- Spec: [specs/018-technique-gymkhana-library/spec.md](../../specs/018-technique-gymkhana-library/spec.md)
- Data model: [specs/018-technique-gymkhana-library/data-model.md](../../specs/018-technique-gymkhana-library/data-model.md)
- REST contracts: [specs/018-technique-gymkhana-library/contracts/rest-api.md](../../specs/018-technique-gymkhana-library/contracts/rest-api.md)
- Plan: [specs/018-technique-gymkhana-library/plan.md](../../specs/018-technique-gymkhana-library/plan.md)
- Seed data: `backend/app/data/technique_catalog.py`
- Migration: `backend/alembic/versions/e1f2a3b4c5d6_technique_gymkhana_library.py`
- Backend tests: `backend/tests/technique/`
