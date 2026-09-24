# Contract — Skinfolds API (feature 046)

All routes require authentication. Roles: `admin`, `coach` (must have access to the athlete via `verify_athlete_access`), `parent` (own linked athletes only). Errors follow the existing `{"detail": ...}` shape; interval and state conflicts add a machine-readable `code`.

## 1. `PUT /api/athletes/{athlete_id}/anthropometry/{record_id}/skinfolds`

Create or replace the skinfold set of one evaluation. **Roles**: admin, coach.

Request `SkinfoldSetIn`:

```json
{
  "caliper_model": "slim_guide",
  "sites": {
    "triceps":      {"readings": [8.5, 9.0]},
    "biceps":       {"readings": [5.0, 5.0]},
    "subscapular":  {"readings": [7.0, 8.0, 7.5]},
    "medial_calf":  {"readings": [10.0, 10.5]},
    "iliac_crest":  {"declined": true},
    "supraspinale": {"readings": [6.0, 6.5]}
  }
}
```

Validation (422 unless stated):
- every one of the six sites present; each is either `{"declined": true}` or `{"readings": [2–3 numbers]}` with each value in `[2.0, 60.0]` and at most one decimal (half-millimetre steps);
- `readings` length 3 only when the first two exceed tolerance is **not** enforced (a third reading is always accepted); length 1 or > 3 rejected;
- record must belong to `athlete_id` (404 otherwise); athlete age at the record's `evaluation_date` ≥ 9 (409 `code: "athlete_too_young"`);
- interval rule: 409 `code: "skinfold_interval_too_short"`, body includes `"previous_set_date"` and `"next_allowed_date"` (see research R4);
- parent → 403; coach without access → 403.

Response 200 `SkinfoldSetOut`:

```json
{
  "record_id": 812, "athlete_id": 17, "evaluation_date": "2026-09-20",
  "caliper_model": "slim_guide", "protocol_version": "v1",
  "sites": {
    "triceps": {"value_mm": 8.8, "readings": [8.5, 9.0], "declined": false, "unconfirmed": false},
    "iliac_crest": {"value_mm": null, "readings": null, "declined": true, "unconfirmed": false},
    "...": {}
  },
  "sum4_mm": 31.8, "sum6_mm": null,
  "body_fat_pct": 16.5, "fat_mass_kg": 6.9, "fat_free_mass_kg": 35.0,
  "equation_version": "slaughter_tc_1988_v1", "margin_pct": 4,
  "measured_by": 3, "updated_at": "2026-09-20T15:02:11Z"
}
```

Side effects: recompute sums/estimates; audit-log entry `skinfolds.saved` (record id, athlete id, site count, no values); invalidates nothing server-side (no cache).

## 2. `DELETE /api/athletes/{athlete_id}/anthropometry/{record_id}/skinfolds`

**Roles**: admin, coach. 204 on success; 404 when no set. Audit-log `skinfolds.deleted`.

## 3. `GET /api/athletes/{athlete_id}/anthropometry` (existing, extended)

Each item gains `skinfolds: SkinfoldSetOut | null`. For `parent` the field is always `null` (same projection block that nulls `notes` and `morphology`). Eager-loaded (no N+1; covered by the existing query-count test pattern).

## 4. `GET /api/athletes/{athlete_id}/body-composition`

**Roles**: admin, coach; parent → 403. Response `BodyCompositionOut` (see data-model §6): `sets`, `series` (`sum4`, `sum6`, `per_site`), `reading` (`BodyCompositionReading`, data-model §5), `estimates_latest`, `reference` (`{source: "FUPRECOL", population: "escolares de Bogotá 2016", side: "izquierdo", age_range: "9–17.9"}`). `has_data=false` shape when the athlete has no set: `{"athlete_id": 17, "sets": [], "series": null, "reading": null, "next_due_date": null}`.

## 5. `GET /api/athletes/{athlete_id}/growth-summary` (existing, extended)

Adds `body_composition`:

- coach/admin → `BodyCompositionSummary` (all fields);
- parent → `BodyCompositionFamilySummary` = `{has_data, latest_set_date, family_band, family_label, family_sentence}` and **no other keys** (schema-level, not null-filled). `family_band` ∈ {`verde`, `ambar`} — never `rojo`, never the coach `band` (projection rules in `contracts/body-composition-reading.md` §3c). `latest_set_date` is the latest **counted** set; a later fully declined attempt is invisible to parents (§3b). When `has_data=false` → `{"has_data": false}`.
- coach/admin additionally receive `latest_attempt_declined: {date} | null` (§3b) and both `band` and `family_band` (so the coach can see what the family sees).

`family_band`, `family_label` and `family_sentence` values come from `contracts/body-composition-reading.md` §3c–§4.

## 5b. Monthly newsletter (existing, extended — spec FR-036)

No new endpoint. `newsletter_builder.py` gains a deterministic `body_composition` block (`{family_label, family_sentence, notice_text}` only) built from the same family projection, present only when a counted set's `evaluation_date` falls in the newsletter month; absent otherwise. The block is rendered by the newsletter PDF template from fixed copy (`contracts/body-composition-reading.md` §4 "Newsletter block") and is **never** added to the newsletter AI context or prompt.

## 6. `GET /api/athletes/{athlete_id}/body-composition/referral-note.pdf`

**Roles**: admin, coach. 200 `application/pdf`; 409 `code: "no_skinfold_data"` when the athlete has no set. Content (Spanish): initials only, age band, sex, observed pattern sentences from `band_reason_code` and leg codes, approximate weekly training hours (28-day window), the fixed "no incluye diagnóstico" paragraph, the "se adjunta historial solo con autorización expresa de la familia" line, contact placeholder. Never contains a percentage, a millimetre value, a label or an institution name. Audit-log `skinfolds.referral_note_generated`.

## 7. `GET /api/body-composition/field-guide.pdf`

**Roles**: admin, coach; parent → 403. Static content; `Cache-Control: private, max-age=86400`. Sections: title, pre-check list, six site sections (SVG partial + "Dónde"/"Cómo"), reading protocol box, footer "Este instructivo no contiene datos de ningún deportista".

## 8. Frontend API module (`api/bodyComposition.ts`)

`getBodyComposition(athleteId)`, `saveSkinfolds(athleteId, recordId, payload)`, `deleteSkinfolds(athleteId, recordId)`, `downloadReferralNote(athleteId)`, `downloadFieldGuide()`. Query keys: `["body-composition", athleteId]`; mutations invalidate `["body-composition", id]`, `["anthropometry", id]`, `["growth-summary", id]`, `["ai", "phv", id]`. `body-composition` is **not** added to `persistAllowList.ts`.

## 9. Required tests (constitution II)

Backend: `tests/routers/test_body_composition.py` — coach happy path (create, replace, delete); parent `PUT` 403; foreign-club coach 403; parent `GET body-composition` 403; interval 409 with `next_allowed_date`; age < 9 → 409; invalid readings 422; parent list projection `skinfolds == null`; parent growth-summary block has exactly the five allowed keys and `family_band != "rojo"`; newsletter block present only in the set's month, fixed copy, absent from the AI request; referral note 409 without data; field guide 403 for parent. `tests/services/test_body_composition.py` — readings → value, tolerance, sums, equation by sex, recomputation on weight change, delta codes at 6.9/7.0 mm, band scenarios (SC-004). Frontend: MSW handlers for every route; vitest for hooks and wizard; jest-axe on page, cards and dialog.
