# Phase 1 Contracts — REST API: Technique & Gymkhana Library

Base path: `/api/technique`. **All endpoints require an authenticated coach or admin** (`require_role([admin, coach])`, club-scoped). No parent/athlete endpoints exist (FR-021). All copy in responses is español neutro. Errors use the standard `{ "detail": "..." }` envelope; every async surface has loading/empty/error semantics on the client.

Legend: ✅ = primary happy path; ⛔ = negative path that MUST be tested.

---

## Catalog & discovery (US1)

### `GET /api/technique/exercises`
List/filter the catalog. Query params (all optional, combinable — FR-002):
| Param | Type | Meaning |
|---|---|---|
| `skill` | string (slug) | filter by skill taxonomy slug. |
| `age_band` | `7-9` \| `10-12` \| `13-15` | filter by band. |
| `difficulty` | `facil` \| `media` \| `avanzada` | filter by difficulty. |
| `materials` | csv of material slugs | "available today"; returns exercises whose required materials ⊆ this set, plus `sin_material` exercises (FR-009). |
| `include_hidden` | bool (default false) | when true, also returns hidden rows (curation views). |
| `is_game` | bool | filter the 🎉 engagement exercises. |

✅ `200` → `{ "items": [ExerciseListItem], "total": int }`. Empty result returns `{ "items": [], "total": 0 }` so the client shows a clear empty state (FR-004), **not** an error.
⛔ `401/403` for unauthenticated / parent / athlete callers.

`ExerciseListItem`: `{ id, slug, name, summary, difficulty, is_game, is_gymkhana, age_bands: [AgeBand], skills: [{code, slug, name}], materials: [{slug, name, is_none}], is_seeded, is_hidden }`.

### `GET /api/technique/skills`  /  `GET /api/technique/materials`
✅ `200` → the seeded taxonomy / material list (for building filter controls).

---

## Exercise detail & layout (US2)

### `GET /api/technique/exercises/{id}`
✅ `200` → `ExerciseDetail` = `ExerciseListItem` + `{ how_to, layout_ascii, layout_alt, confidence, created_at, updated_at }`.
- Gymkhana exercises include a non-null `layout_ascii` + `layout_alt` (FR-008); no-material exercises clearly carry the `sin_material` material (FR-009).
⛔ `404` for unknown id; `403` for non-coach/admin.

---

## Session assembly via the existing Training Sessions module (US3)

### `POST /api/technique/sessions`
Assemble selected exercises into a **normal training session** (FR-011). Body:
```json
{
  "scheduled_date": "2026-07-04",
  "scheduled_start_time": "16:00:00",
  "duration_min": 70,
  "location": "Cancha del club",
  "technical_focus": "Fundamentos de equilibrio y frenado",
  "objectives": "…",
  "convocados_athlete_ids": [12, 14],
  "items": [
    { "exercise_id": 5,  "segment": "calentamiento", "position": 1 },
    { "exercise_id": 8,  "segment": "principal",      "position": 1 },
    { "exercise_id": 13, "segment": "vuelta_calma",   "position": 1 }
  ]
}
```
Server: creates a `TrainingSession` by **reusing `training_svc.create_session`** (so it appears in the existing calendar/list and supports attendance + rubric — FR-012), then writes `technique_session_exercises` rows in the same transaction.
✅ `201` → `{ "training_session_id": int, "mixes_age_bands": bool, "items": [TechniqueSessionItem] }`. `mixes_age_bands=true` surfaces the visible age-mix notice (FR-014); the session still saves.
⛔ `422` empty `items` or unknown `exercise_id`; `403` non-coach/admin; `400` if a referenced exercise is hidden? → **allowed** (hidden exercises may still be assembled by the coach who unhides/curates), but a hidden exercise referenced by a saved session never blanks it (FR-020).

### `GET /api/technique/sessions/{training_session_id}/exercises`
✅ `200` → the ordered `[TechniqueSessionItem]` a session was built from (FR-013), grouped by segment. Survives later hide/edit of an exercise (FR-020).

`TechniqueSessionItem`: `{ exercise_id, name, segment, position, age_bands, skills }`.

---

## Per-athlete skill progress (US4 — minors data, coach/admin only)

### `GET /api/technique/athletes/{athlete_id}/progress`
✅ `200` → `{ "athlete_id": int, "current": [{ skill: {code,slug,name}, status, recorded_at, coach_note }], "history": [SkillProgressEvent] }`.
- `current` = latest event per skill; `history` = season-ordered events (FR-016). Framed as individual growth anchored to biological age; **no other athlete appears** in the response (FR-017, SC-005).
⛔ `404` if the athlete has no record (graceful 7–9 handling — FR-018); `403` for parent/athlete callers; privacy test asserts no minor PII beyond what the coach may see in-app.

### `POST /api/technique/athletes/{athlete_id}/progress`
Append a progress event (FR-015). Body: `{ "skill_id": int, "status": "en_progreso", "coach_note": "…", "season": 2026 }`.
✅ `201` → the created `SkillProgressEvent`. Updating "over time" = posting a new event; current status reflects the latest.
⛔ `422` invalid status/skill; `404` no athlete record; `403` non-coach/admin.

`SkillProgressEvent`: `{ id, skill: {code,slug,name}, status, coach_note, season, recorded_at }`.

> There is intentionally **no** endpoint that ranks or compares athletes (SC-005). Group/aggregate skill views are out of scope for v1.

---

## Curation (US5 — coach/admin)

### `POST /api/technique/exercises`
Create a custom exercise (FR-019). Body carries `name, summary, how_to, difficulty, is_game, is_gymkhana, layout_ascii?, layout_alt?, age_bands:[…], skill_slugs:[…], material_slugs:[…]`. Validation: gymkhana ⇒ `layout_ascii` required; ≥1 age band; ≥1 skill.
✅ `201` → `ExerciseDetail` (with `is_seeded=false`, `club_id` set). Appears in browse/filters immediately.
⛔ `422` validation; `403` non-coach/admin.

### `PUT /api/technique/exercises/{id}`
Edit any exercise incl. seeded ones (FR-019). Partial body of the create fields.
✅ `200` → updated `ExerciseDetail`. Edits never alter a previously saved session's stored items (FR-020).
⛔ `404` unknown; `422` validation; `403`.

### `PATCH /api/technique/exercises/{id}/visibility`
Hide/unhide (FR-019). Body `{ "is_hidden": true }`.
✅ `200` → `{ id, is_hidden }`. Hidden rows drop from the default catalog but are not destroyed (FR-019) and don't corrupt saved sessions (FR-020).
⛔ `404`; `403`.

---

## Cross-cutting contract rules

- **RBAC**: every route → coach/admin + club scope; parent/athlete → `403`. (FR-021)
- **Empty vs. error**: no-match filters → `200` empty list (FR-004), never `404`/`500`.
- **Performance**: list/detail reads p95 ≤ 500 ms with `selectinload` (no N+1); writes p95 ≤ 1500 ms (Constitution IV).
- **Privacy**: progress responses/logs carry no minor PII beyond in-app coach authorization; **no AI prompt surface** in this feature (SC-007).
- **Language**: all response copy and seeded content in español neutro (FR-023).
