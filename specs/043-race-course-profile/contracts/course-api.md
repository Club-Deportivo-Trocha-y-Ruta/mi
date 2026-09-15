# Contract — Course API (variants, category setups, description, parent read)

**Router**: `backend/app/routers/race_events.py` (existing, extended) — all paths below hang off the existing prefix `/api/race-analysis/race-events/{race_event_id}` (`backend/app/main.py:177`). Do not confuse with the helper router at `/api/race-events`.
**Service**: `backend/app/services/race/course/service.py` (new) + `gpx_processing.py` (new, see `gpx-processing.md`).
**Schemas**: `backend/app/schemas/race_course.py` (new).
**Requirements covered**: FR-001, FR-002, FR-007–FR-013, FR-023, FR-026, FR-027; User Stories 1, 3, 5.

---

## 0. Endpoints

| Method | Path (relative to `/{race_event_id}`) | Roles | Purpose |
|---|---|---|---|
| `GET` | `/course` | admin, coach, parent (scoped) | Whole course: variants (with geometry), setups, description, prefill suggestion, parent highlights. |
| `POST` | `/course/variants` | admin, coach | Multipart upload → process → create variant. |
| `PUT` | `/course/variants/{variant_id}/file` | admin, coach | Multipart upload → process → replace geometry and figures in place. |
| `PATCH` | `/course/variants/{variant_id}` | admin, coach | Rename (`label`). |
| `DELETE` | `/course/variants/{variant_id}` | admin, coach | Delete; 409 when referenced by a setup. |
| `PUT` | `/course/setups` | admin, coach | Replace the full laps table. |
| `PATCH` | `/course/description` | admin, coach | Partial update of the four description fields. |

Coach access follows the existing `require_role([UserRole.admin, UserRole.coach])` dependency used by `PATCH /{id}/conditions`; the club-membership check for coaches is the same one the router already applies. All mutations call `record_audit(...)` with `entity_type=AuditEntityType.race_event`, `entity_id=race_event_id`, `changed_fields` naming the sub-entity (`course_variant:{id}`, `course_setups`, `course_description:<field,…>`).

Every mutation returns the **full `CourseRead`** (§1) so the client replaces one query key (`["race-course", race_event_id]`) instead of merging partials.

---

## 1. `CourseRead` (response of `GET /course` and of every mutation)

```jsonc
{
  "race_event_id": 41,
  "has_course_data": true,                  // any variant OR any description field
  "variants": [
    {
      "id": 7,
      "label": "Circuito completo",
      "lap_distance_km": 4.2,               // lap_distance_m / 1000, 1 decimal
      "lap_distance_m": 4213,
      "elevation_gain_m": 110,              // null when has_elevation=false
      "has_elevation": true,
      "point_count": 486,
      "geometry": [[3.4516, -76.5320, 995.4], ...],   // [lat, lon, ele|null]
      "detection": { "method": "closed_loop", "laps_detected": 3, "total_distance_m": 12640 },
      "created_at": "2026-09-15T14:02:11Z",
      "updated_at": null
    }
  ],
  "setups": [
    { "category_id": 12, "category_code": "INF_M", "category_label": "Infantil masculino", "laps": 3, "variant_id": 7 }
  ],
  "suggested_setups": [                     // only when `setups` is empty; from the previous válida of the series (R-14)
    { "category_id": 12, "laps": 3, "variant_label": "Circuito completo", "source_event_id": 38 }
  ],
  "description": {
    "terrain_type": "mixto",                // enum | null
    "technical_difficulty": 4,              // 1..5 | null
    "key_sectors": ["subida_larga", "rock_garden"],
    "course_notes": "…"                     // ≤ 1000 chars | null
  },
  "my_categories": [                        // parents only; [] for coach/admin
    { "athlete_id": 305, "category_id": 12 }
  ]
}
```

- For coach/admin, `my_categories` is always `[]` and `suggested_setups` is present as described.
- For parents: `suggested_setups` is always `[]`, `my_categories` is derived from roster entries **and** results of the caller's own athletes (`allowed_athlete_ids_for`), and the response is `404 course_not_available` when none of the caller's athletes is on the roster or in the results. `course_notes` is included for parents (spec US5: description is course information).
- `404 race_event_not_found` when the válida does not exist (coach/admin).
- When the válida has nothing: `200` with `has_course_data=false`, empty lists, all description fields `null`. The frontend renders the tab's empty state from this, never from a 404.

---

## 2. `POST /course/variants` and `PUT /course/variants/{id}/file`

Multipart form: `file` (required, `.gpx`), `label` (required on POST, ignored on PUT; 1–60 chars, trimmed), `recorded_laps` (optional int 1–20; when present forces `detection.method="manual"`).

Router-level guards, in order (same style as `training_sessions.py:885`): content-type in `{application/gpx+xml, application/xml, text/xml, application/octet-stream}` (some browsers send octet-stream for `.gpx`) → else `415 unsupported_media_type`; filename extension `.gpx` → else `422 not_gpx`; sniff first bytes for gzip/zip magic (`1f 8b`, `50 4b`) → `422 compressed_not_allowed`; read with cap `_MAX_GPX_SIZE_BYTES` (5 MB) → `413 file_too_large`. Then `process_gpx(content, recorded_laps=…)`; any `CourseProcessingError` → `422 {code, message}` (§6). Then in one transaction: check `source_sha256` not already used by another variant of the same válida → else `409 duplicate_recording {variant_id}`; check label unique → else `409 variant_label_taken`; insert/update; `record_audit`; log `race_course_variant_processed`. The upload bytes are not written anywhere and are released after processing.

Responses: `201` (POST) / `200` (PUT) with `CourseRead`.

Detection confirmation is a **UI** step (`ui-course.md` §2): the server stores the variant immediately with what it detected; if the coach disagrees they re-upload with `recorded_laps` via `PUT …/file`, which is the only way to recompute because the original is not retained.

---

## 3. `PATCH /course/variants/{id}` — body `{ "label": "Recorrido reducido" }`

`409 variant_label_taken` on collision; `404 variant_not_found` when the id does not belong to this válida (never leak a variant of another válida).

## 4. `DELETE /course/variants/{id}`

`204`-equivalent → returns `CourseRead` (`200`) for consistency. `409 variant_in_use { "categories": ["Infantil masculino", "Infantil femenino"] }` when any setup references it (FR-008); the labels come from `race_categories.label`.

## 5. `PUT /course/setups` — body

```jsonc
{ "setups": [ { "category_id": 12, "laps": 3, "variant_id": 7 }, ... ] }
```

Full replace. Validation: `laps` 1–20; every `variant_id` belongs to this válida → else `422 variant_not_in_event`; every `category_id` exists and is active → else `422 unknown_category`; duplicate `category_id` in the payload → `422 duplicate_category`. Categories are **not** required to have results in the válida (edge case "configured but no results: allowed"). Empty list clears the table.

## 5b. `PATCH /course/description` — body (all optional, `extra="forbid"`, like `RaceEventConditionsUpdate`)

```jsonc
{ "terrain_type": "mixto" | null, "technical_difficulty": 4 | null, "key_sectors": ["subida_larga"] | null, "course_notes": "…" | null }
```

`422` on notes > 1 000 chars (message states the limit; no truncation), difficulty outside 1–5, unknown sector code, more than 8 sectors or duplicates. `exclude_unset` semantics: a field absent from the body is untouched; an explicit `null` clears it.

---

## 6. Error table (code → Spanish message shown by the UI)

| HTTP | code | message (español neutro) |
|---|---|---|
| 415 | `unsupported_media_type` | El archivo debe ser un GPX. |
| 422 | `not_gpx` | El archivo no es un GPX válido. |
| 422 | `compressed_not_allowed` | No se aceptan archivos comprimidos; sube el GPX sin comprimir. |
| 413 | `file_too_large` | El archivo supera los 5 MB permitidos. |
| 422 | `xml_unsafe` | El archivo contiene estructuras XML no permitidas. |
| 422 | `malformed` | No pudimos leer el archivo; verifica que sea un GPX completo. |
| 422 | `no_track_points` | El GPX no contiene puntos de recorrido. |
| 422 | `no_position` | El GPX no contiene coordenadas válidas. |
| 422 | `too_short` | El recorrido es demasiado corto para ser una vuelta (menos de 300 m). |
| 422 | `too_long` | La vuelta supera los 15 km; indica cuántas vueltas contiene la grabación. |
| 422 | `too_few_points` | La grabación tiene muy pocos puntos para dibujar el circuito. |
| 409 | `duplicate_recording` | Ya subiste esta misma grabación como "{label}". |
| 409 | `variant_label_taken` | Ya existe una variante con ese nombre en esta válida. |
| 409 | `variant_in_use` | No se puede eliminar: la usan {categorías}. |
| 422 | `variant_not_in_event` | La variante no pertenece a esta válida. |
| 404 | `course_not_available` | (parents) rendered as "card absent", no toast. |

Error bodies follow the router's existing `{"detail": {"code": …, "message": …}}` shape used by the conditions PATCH.

---

## 7. Tests (Principle II) — `backend/tests/routers/test_race_course.py` (new), pattern of `tests/routers/test_race_event_conditions.py`

Happy: upload single-lap GPX → 201 with figures; upload 3-lap GPX → `closed_loop`, `laps_detected=3`; upload with `recorded_laps=2` → `manual`; PUT setups then GET; PATCH description; parent with child on roster → 200 with `my_categories`; parent with child only in results → 200.
Negative: parent without child → 404; athlete/unknown role → 403; coach of another club → 403 (existing membership check); `.fit` → 422; gzip → 422; 6 MB → 413; XXE payload → 422 `xml_unsafe`; label collision → 409; delete referenced → 409 with labels; setups with foreign variant → 422; notes 1 001 chars → 422; same file twice → 409 `duplicate_recording`.
Privacy: GPX with `<time>`, `<extensions>` hr/cad/atemp, `<metadata><author>` → response and DB row contain none of those strings (assert on `json.dumps(row)` and on the response body); caplog contains no filename and no coordinates.
Query count: `GET /course` ≤ 3 statements (event, variants, setups+categories) asserted with the SQLAlchemy event counter used in feature 041 tests.
