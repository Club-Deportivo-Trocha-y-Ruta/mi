# Data Model: Structured Interval Training with Strava Correlation

**Feature**: `026-structured-interval-training` · **Migration**: `b5c6d7e8f9a0` (down_revision `a4b5c6d7e8f9`)

Six new tables, two new model modules. No changes to existing tables. Enum `ageband` is **reused** from migration `e1f2a3b4c5d6` (technique) — do not recreate/drop it (same rule feature 021 followed).

---

## 1. `interval_structures` — model `IntervalStructure` (`app/models/interval_structure.py`)

The coach-authored plan, attached 1:1 to a training session (FR-001).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | Integer PK | autoincrement | |
| `training_session_id` | FK → `training_sessions.id` | **UNIQUE**, NOT NULL, `ondelete=CASCADE` | 1:1 — a session has at most one structure |
| `target_age_band` | Enum `ageband` (`values_callable`) | NOT NULL | Coach-declared (`10-12` / `13-15`); drives age gating (D3) |
| `age_gate_confirmed` | Boolean | NOT NULL, default `false` | True only for confirmed 10-12 structures (FR-007) |
| `age_gate_confirmed_by_user_id` | FK → `users.id` | nullable, `ondelete=SET NULL` | Who confirmed |
| `age_gate_confirmed_at` | DateTime | nullable | When confirmed |
| `created_by_user_id` | FK → `users.id` | NOT NULL, `ondelete=RESTRICT` | |
| `created_at` / `updated_at` | DateTime | NOT NULL, UTC defaults | Same lambda pattern as `strava_activities` |

Relationships: `blocks` (→ `IntervalStructureBlock`, `order_by=position`, cascade delete-orphan), `training_session` (back_populates `interval_structure` added on `TrainingSession`), `match_results`.

**Validation (service layer, `services/intervals/structures.py`)**:
- Band `10-12` + any flattened block `target_zone ∈ {Z3, Z4, Z5}` → 422 `age_gate_z3_blocked` (hard, FR-006).
- Band `10-12` + all blocks Z1–Z2 + `age_gate_confirmed` missing/false → 422 `age_gate_confirmation_required` (FR-007).
- Applied identically on create, update, and template attach.

## 2. `interval_structure_blocks` — model `IntervalStructureBlock`

Ordered steps of a structure (FR-002/FR-003).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | Integer PK | | |
| `structure_id` | FK → `interval_structures.id` | NOT NULL, `ondelete=CASCADE` | |
| `position` | Integer | NOT NULL; **UNIQUE `(structure_id, position)`** | Authoring order (repeat groups count once) |
| `block_type` | Enum `intervalblocktype` (`warmup`,`work`,`recovery`,`cooldown`), `values_callable` | NOT NULL | |
| `duration_s` | Integer | NOT NULL, service check `> 0` | Planned duration; also the matching `duration_hint` |
| `target_zone` | Enum `hrzone` (`Z1`..`Z5`), `values_callable` | NOT NULL | Only target dimension besides cadence — **no power column exists** (FR-005, D2) |
| `target_cadence_rpm` | Integer | NOT NULL, service check `>= 60` | FR-004, any band, no exception |
| `repeat_group` | Integer | nullable | Blocks sharing a value form one repeat group |
| `repeat_count` | Integer | nullable, service check `>= 2` when set | Must be identical across a group's rows; NULL ⇢ block runs once |

**Flattening rule** (matching + instructivo): expand each repeat group in position order `repeat_count` times, non-grouped blocks once → the real step sequence.

## 3. `interval_templates` — model `IntervalTemplate`

Reusable, session-independent structure (FR-008).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | Integer PK | | |
| `name` | String(120) | NOT NULL | |
| `target_age_band` | Enum `ageband` | NOT NULL | Tag + gate context at attach |
| `mesocycle_phase` | String(50) | NOT NULL | Controlled vocab in frontend (e.g. `base`, `construccion`, `especifico`, `taper`, `transicion`) — string, not enum, so vocab evolves without migration |
| `competition_proximity` | String(50) | NOT NULL | e.g. `general`, `pre-competencia`, `semana-carrera` |
| `club_id` | FK → `clubs.id` | NOT NULL, `ondelete=CASCADE` | Club-scoped library |
| `created_by_user_id` | FK → `users.id` | NOT NULL, `ondelete=RESTRICT` | |
| `is_archived` | Boolean | NOT NULL, default `false` | Soft archive (mirrors `strength_blocks`) |
| `created_at` / `updated_at` | DateTime | NOT NULL | |

Relationships: `blocks` (→ `IntervalTemplateBlock`, cascade delete-orphan).

## 4. `interval_template_blocks` — model `IntervalTemplateBlock`

Identical column set to `interval_structure_blocks` with `template_id` FK instead of `structure_id`. Same validations.

**Copy-on-attach (FR-009, interview-locked)**: attaching a template to a session **clones** rows into `interval_structure_blocks` under a new/updated `interval_structures` row. No FK from structures to templates — editing or deleting a template never touches sessions that used it (spec US4-AC3).

## 5. `strava_activity_laps` — model `StravaActivityLap` (`app/models/strava_activity_lap.py`)

Persisted laps of a synced activity (FR-012/FR-013, D4).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | Integer PK | | |
| `strava_activity_id` | FK → `strava_activities.id` | NOT NULL, `ondelete=CASCADE`; **UNIQUE `(strava_activity_id, lap_index)`** | Owned by the activity, not by any structure/match (D7) |
| `lap_index` | Integer | NOT NULL | Device order (Strava `lap_index`) |
| `elapsed_time_s` | Integer | NOT NULL | |
| `moving_time_s` | Integer | nullable | |
| `average_heartrate` | Float | nullable | Device may not record HR |
| `average_speed_m_s` | Float | nullable | Strava `average_speed` |
| `fetched_at` | DateTime | NOT NULL | Refresh watermark |

**Explicitly ABSENT columns (privacy + scope — same doctrine as `strava_activities`)**: `start_latlng`, `end_latlng`, polyline/map of any kind, lap `name` free text, `average_cadence` (deferred to v2 by interview P9), `average_watts` (no power for this population). The ingest path (`services/intervals/match_runner.py`) allow-lists exactly the persisted fields — everything else in the raw payload is dropped before flush, and tests assert the model has no geo attributes (`tests/privacy/test_laps_privacy.py`).

Refresh semantics: recalculation replaces an activity's laps (delete-and-insert within one transaction) so `lap_index` uniqueness always reflects the latest upstream state (spec edge case: re-synced laps).

## 6. `interval_match_results` — model `IntervalMatchResult`

Persisted plan-vs-actual comparison (FR-014..FR-017), one per structure↔activity pair.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | Integer PK | | |
| `structure_id` | FK → `interval_structures.id` | NOT NULL, `ondelete=CASCADE` | Derived artifact — dies with the plan (D7) |
| `strava_activity_id` | FK → `strava_activities.id` | NOT NULL, `ondelete=CASCADE` | |
| — | — | **UNIQUE `(structure_id, strava_activity_id)`** | Recompute = upsert |
| `engine_version` | Integer | NOT NULL, default `1` | Bump when matching rules change |
| `computed_at` | DateTime | NOT NULL | |
| `result_json` | JSON | NOT NULL | See shape below |
| `triggered_by` | Enum `matchtrigger` (`link`,`structure_change`,`manual`), `values_callable` | NOT NULL | Observability |

**`result_json` shape** (validated by Pydantic before persist):

```json
{
  "blocks": [
    {
      "flat_index": 0,
      "block_id": 12,
      "block_type": "warmup",
      "repeat_iteration": null,
      "planned_duration_s": 300,
      "target_zone": "Z1",
      "target_cadence_rpm": 70,
      "lap_index": 0,
      "lap_elapsed_time_s": 312,
      "lap_average_heartrate": 128.4,
      "status": "cumplido"
    }
  ],
  "extra_laps": [{ "lap_index": 6, "elapsed_time_s": 45 }],
  "summary": { "cumplido": 5, "fuera_tolerancia": 1, "sin_dato": 0, "extra": 1 },
  "tolerance_pct": 30,
  "laps_discarded_under_10s": 1
}
```

Status vocabulary (badge semantics per Constitution III): `cumplido` = green, `fuera_tolerancia` = amber, `sin_dato` = neutral gray. `extra` laps render as informational rows, never errors.

---

## Entity relationship summary

```text
training_sessions 1 ──── 0..1 interval_structures 1 ──── * interval_structure_blocks
                                     │ 1
                                     │
                                     * interval_match_results * ──── 1 strava_activities
                                                                          │ 1
interval_templates 1 ── * interval_template_blocks                       * strava_activity_laps
        (copy-on-attach → interval_structure_blocks; no FK link retained)
```

## State transitions

- **Structure**: created → edited (revalidated each save) → deleted (cascades blocks + match results; laps untouched).
- **Match result**: absent → `computing` (transient UI state, no DB row) → row present (upserted on each recompute trigger: `link`, `structure_change`, `manual`).
- **Template**: active → archived (`is_archived=true`, hidden from picker, never hard-deleted while referenced by nothing — copies live independently).

## Access control invariants (FR-018)

Every read/write on all six tables flows through `/api/intervals` (or the deferred runner) gated by `require_role([admin, coach])` + club scope via the session's (or template's) `club_id`. Laps are only serialized inside match-detail responses. Parents/athletes: 403 on every route — asserted in `tests/intervals/test_rbac.py` and `tests/privacy/test_laps_privacy.py`.
