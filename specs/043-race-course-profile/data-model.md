# Data model — Race course profile (043)

Only the deltas, in the style of `specs/042-traceable-growth-ai/data-model.md`. Existing entities are referenced by their current names, verified in the working tree on 2026-09-15 (`path:line`). Binding sources: `spec.md` (FR-003…FR-013, FR-027, Key Entities) and `research.md` (R-02, R-07, R-08, R-14).

Conventions reused: enums as `str, enum.Enum` with lowercase values (`backend/app/models/race_event.py:56-67`, `SurfaceCondition`); JSON columns as `from sqlalchemy import JSON` + `Mapped[... | None] = mapped_column(JSON, nullable=True)` (`backend/app/models/ai_explanation.py:89`); attribution via `ActorTimestampMixin` (`backend/app/models/mixins.py:33-45`) **and** `record_audit(...)` at the router (`backend/app/routers/race_events.py:919-1004`); one Alembic revision, `down_revision = "d5b125474e2b"` (current single head, `backend/alembic/versions/*d5b125474e2b*.py`).

---

## 1. New table `race_course_variants` — `backend/app/models/race_course_variant.py` (new)

One row per route variant of one válida ("Circuito completo", "Recorrido reducido", …). Holds the **extracted single lap only** — never a file, never a timestamp, never a physiological field (FR-003, FR-025).

| Column | Type | Null | Default | Purpose |
|---|---|---|---|---|
| `id` | `BigInteger` PK autoincrement | no | — | |
| `race_event_id` | `BigInteger` FK `race_events.id` `ondelete=CASCADE` | no | — | Owner válida (FR-027: deleted with it). |
| `label` | `String(60)` | no | — | Coach-given name. Unique per válida (`uq_race_course_variants_event_label`). Trimmed, 1–60 chars. |
| `lap_distance_m` | `Integer` | no | — | Length of one lap in metres, measured on the **unsimplified** lap (R-06). Range 300–15 000 enforced in the service (FR-007). Displayed as km to 0.1. |
| `elevation_gain_m` | `SmallInteger` | yes | `NULL` | Smoothed positive gain per lap, whole metres (R-05). `NULL` when the recording had no elevation (`has_elevation = false`). |
| `has_elevation` | `Boolean` | no | `false` | Whether every stored point carries an elevation. |
| `point_count` | `SmallInteger` | no | — | Number of points in `geometry` (≥ 20, normally ≤ 800). |
| `geometry` | `JSON` | no | — | `list[[lat: float, lon: float, ele: float \| null]]` — the simplified lap, first point = start line, last point ≈ first point for closed loops. Lat/lon rounded to 6 decimals, ele to 1 decimal. |
| `detection_method` | `String(16)` | no | — | `closed_loop` \| `manual` \| `single` (R-04). `single` = the recording was one lap and no closure search was needed (total distance below 2× the first closure or `recorded_laps = 1` explicitly). |
| `recorded_laps` | `SmallInteger` | no | `1` | Laps the platform believes the recording contained (`laps_detected` for `closed_loop`, the coach's value for `manual`, `1` for `single`). Informational; enables the confirmation message. |
| `source_sha256` | `String(64)` | no | — | SHA-256 of the discarded upload. Used only to answer "you already uploaded this exact file as variant X" (409 on the same válida); never used to retrieve anything because nothing is retained. |
| `created_by_user_id` | `Integer` FK `users.id` `ondelete=RESTRICT` | no | — | Uploader. Same convention as `race_events.created_by_user_id` (`race_event.py`). |
| `created_at` | `DateTime` | no | `now(utc)` | |
| `updated_by_user_id` | from `ActorTimestampMixin` | yes | `NULL` | Last actor (label rename or file replacement). |
| `updated_at` | from `ActorTimestampMixin` | yes | `NULL` | |

Indexes: PK; `uq_race_course_variants_event_label (race_event_id, label)`; `ix_race_course_variants_event (race_event_id)` (implicit through the unique index on MySQL, declared explicitly for aiosqlite parity).

Relationships: `event: RaceEvent` (back-populates `RaceEvent.course_variants`, cascade `all, delete-orphan` from the event side); `setups: list[RaceCourseCategorySetup]` (viewonly, for the delete guard message).

Validation (service layer, `app/services/race/course/service.py`): label uniqueness → 409 `variant_label_taken`; delete while referenced → 409 `variant_in_use` with `categories: [label…]` (FR-008); replace file → same processing, all derived fields overwritten in place, `id` stable (FR-009).

---

## 2. New table `race_course_category_setups` — `backend/app/models/race_course_category_setup.py` (new)

One row per (válida, category): the laps ridden and the variant used.

| Column | Type | Null | Default | Purpose |
|---|---|---|---|---|
| `id` | `BigInteger` PK | no | — | |
| `race_event_id` | `BigInteger` FK `race_events.id` `ondelete=CASCADE` | no | — | |
| `category_id` | `Integer` FK `race_categories.id` `ondelete=RESTRICT` | no | — | Catalogue category (`backend/app/models/race_category.py`). |
| `variant_id` | `BigInteger` FK `race_course_variants.id` `ondelete=RESTRICT` | no | — | Which variant this category rode. `RESTRICT` is what backs the FR-008 guard at the database level; the service checks first to return a friendly 409. |
| `laps` | `SmallInteger` | no | — | 1–20 (FR-010); `CheckConstraint("laps BETWEEN 1 AND 20", name="ck_race_course_setups_laps_range")`. |
| `created_at` | `DateTime` | no | `now(utc)` | |
| `updated_by_user_id`, `updated_at` | from `ActorTimestampMixin` | yes | `NULL` | |

Constraints: `uq_race_course_setups_event_category (race_event_id, category_id)`; application-level check that `variant.race_event_id == race_event_id` (a setup may only point at a variant of its own válida) → 422 `variant_not_in_event`.

Write model: `PUT /course/setups` replaces the full list for the válida in one transaction (rows not in the payload are deleted, present ones upserted by `category_id`), which is how "each válida keeps its own configuration" (FR-012) and prefill confirmation (R-14) stay simple.

Read model for results (R-08): `dict[category_id, (laps, variant)]` loaded with one `select(RaceCourseCategorySetup).options(selectinload(variant)).where(race_event_id == …)` — no N+1.

---

## 3. Extended `race_events` — `backend/app/models/race_event.py:71-166`

Four nullable, additive columns for the track description (FR-013). No `server_default`; nothing is backfilled; a válida without any of them is "no description" and the UI shows the tri-state empty card.

| Column | Type | Null | Purpose |
|---|---|---|---|
| `terrain_type` | `Enum(TerrainType)` (`sendero \| trocha \| mixto \| pista \| pavimento`), native enum name `terraintype`, `values_callable` like `SurfaceCondition` | yes | Fixed list; labels are frontend copy. |
| `technical_difficulty` | `SmallInteger` | yes | 1–5; `CheckConstraint("technical_difficulty IS NULL OR technical_difficulty BETWEEN 1 AND 5", name="ck_race_events_difficulty_range")`. |
| `key_sectors` | `JSON` | yes | `list[str]` of codes from `KeySector` (`subida_larga \| bajada_tecnica \| rock_garden \| singletrack \| plano_rapido \| paso_quebrada \| raices \| escalones`), validated in the Pydantic schema (unique, ≤ 8). Stored as JSON (not a join table) because it is a small closed vocabulary read as a whole. |
| `course_notes` | `Text` | yes | Free notes, ≤ 1 000 chars enforced in the schema (FR-013). **Never** passed to the AI analysis (FR-020) and never traced. |

New relationships on `RaceEvent`: `course_variants: list[RaceCourseVariant]` (cascade `all, delete-orphan`), `course_setups: list[RaceCourseCategorySetup]` (cascade `all, delete-orphan`). `RaceEventRead` (`backend/app/schemas/race_event.py:167`) gains the four description fields **and** `has_course_data: bool` (true when at least one variant exists or any description field is set) so list/detail pages can show a marker without fetching the course.

Attribution for the description: `PATCH /course/description` calls `record_audit(action=update, entity_type=race_event, changed_fields=[…])` exactly like the conditions PATCH; `RaceEvent` does not gain `updated_by_user_id` in this feature (R-07).

---

## 4. Value objects (not persisted)

### 4.1 `ProcessedLap` — `app/services/race/course/gpx_processing.py`

```text
ProcessedLap
  geometry: list[tuple[float, float, float | None]]   # simplified lap
  lap_distance_m: int                                  # unsimplified length
  elevation_gain_m: int | None
  has_elevation: bool
  point_count: int
  detection: LapDetection
LapDetection
  method: Literal["closed_loop", "manual", "single"]
  laps_detected: int            # closed_loop: laps found; manual: recorded_laps; single: 1
  total_distance_m: int         # whole recording
  closure_radius_m: int = 30    # constants echoed for the UI copy
  min_lap_m: int = 300
```

`CourseProcessingError(reason_code)` with reason codes: `not_gpx`, `xml_unsafe`, `malformed`, `no_track_points`, `no_position`, `too_short` (< 300 m), `too_long` (> 15 km), `too_few_points` (< 20 after simplification), `compressed_not_allowed`, `file_too_large`. The router maps every code to `422` with a Spanish message from a fixed table (`contracts/course-api.md` §6); logs carry only the code.

### 4.2 Derived result figures — computed in `results_read.get_event_results` (R-08)

```text
laps_completed = laps − (laps_behind or 0)      if status in {finished, minus_laps} and race_time_ms
                = None                           if status == minus_laps and laps_behind is None
                = None                           for dnf / dns / dsq or missing setup
distance_km     = round(laps_completed × lap_distance_m / 1000, 1)
avg_speed_kmh   = round(distance_km / (race_time_ms / 3_600_000), 1)
```

Exposed on `ResultRow` (`backend/app/schemas/race_results.py:27`) as four `Optional` fields (`distance_km`, `avg_speed_kmh`, `lap_distance_km`, `elevation_gain_m`), on `CategoryResults` as `laps: int | None` and `variant_label: str | None`, on `EventResultsRead` as `has_course_data: bool`. Never stored (staleness), never estimated (FR-015).

### 4.3 `CourseContext` for the AI (R-10)

Per válida, per rider category: `{lap_distance_m, elevation_gain_m | None, laps | None, terrain_type | None, technical_difficulty | None, key_sectors: list[str]}`; absent key = "SIN DATO". `course_notes` is structurally excluded (the loader never selects the column).

---

## 5. Migration — `backend/alembic/versions/<rev>_race_course_profile.py` (new)

`down_revision = "d5b125474e2b"`. Upgrade order: (1) create `race_course_variants`; (2) create `race_course_category_setups` with its three FKs and check constraint; (3) `batch_alter_table("race_events")` adding the four description columns and the difficulty check. Downgrade in reverse. MySQL enum `terraintype` created explicitly in `upgrade` and dropped in `downgrade` (aiosqlite lane creates tables from the ORM, so the migration is exercised only by `pytest -m mysql` and the local `alembic upgrade head` — both listed in `quickstart.md`). After this feature the single head is the new revision; `CLAUDE.md`'s head note is updated in the same change.

---

## 6. State and lifecycle

```text
Variant:  (none) --POST variants--> stored --PUT variants/{id}/file--> stored (same id, new figures)
                                      |--PATCH label--> stored
                                      |--DELETE (no setup references)--> gone
                                      |--DELETE (referenced)--> 409 variant_in_use
Setups:   PUT replaces the whole list; a variant referenced by any row cannot be deleted.
Event delete (admin): cascades variants and setups; description columns go with the row.
Results revision: derived figures follow automatically (computed at read).
```

---

## 7. Privacy invariants (tests must assert)

- A processed variant never contains keys other than the schema above; `geometry` entries are 3-tuples of numbers/null; no `time`, `hr`, `cad`, `atemp`, `power`, `creator`, `author` anywhere in the row or the response (hypothesis test over synthetic GPX with random Garmin extensions).
- Logs from the processing path contain only `race_event_id`, `variant_id`, `point_count`, `lap_distance_m`, `detection_method`, `reason_code`.
- `course_notes` is absent from every AI prompt render and from every trace payload (existing redact-always tracing; add a prompt-render assertion).
- Parent responses to `GET /course` never include roster rows, results or other athletes' ids; `my_categories` lists only the caller's own athletes.
