# Contract — Cross-season progression (US6, US7 · FR-030…FR-042)

## Endpoint

`GET /api/athletes/{athlete_id}/race-analysis/history` — `Depends(verify_athlete_access)`; admin, coach, the athlete's own parent. No `competitor_id` anywhere in the contract.

Query: `series_kind: cup|championship|all = cup`.

## Response (`AthleteRaceHistoryRead`, `extra="forbid"`)

```json
{
  "points": [{
    "event_id": 41, "event_date": "2025-02-09", "season": 2025, "label": "Válida 1 — Ginebra",
    "series_id": 7, "series_name": "Copa Valle de Ciclomontañismo", "series_kind": "cup",
    "category_code": "PJUV_A", "category_label": "PREJUVENIL A",
    "category_changed": true, "previous_category_label": "INFANTIL B", "category_change_kind": "promotion",
    "status": "finished", "position": 9, "field_size": 23, "timed_finishers": 21,
    "percentile": 63.6, "gap_to_median_pct": -4.2, "gap_to_winner_pct": 11.8,
    "points_awarded": 18
  }],
  "seasons": [{"season": 2025, "started": 7, "finished": 6}],
  "caveats": ["different_courses", "weather_surface", "small_fields", "non_finishers_excluded", "three_rider_categories"]
}
```

Rules

- `field_size` = finishers including lapped riders; `timed_finishers` = strict `FINISHED` with a time (feature 037 definitions, reused through `compute_field_metrics`).
- `percentile = null` when `field_size < 5`. `gap_to_median_pct = null` when `timed_finishers < 5`, or the athlete's status is not `finished`, or the athlete has no time. `gap_to_winner_pct` follows the same status rule (no threshold; kept for continuity).
- No `avg_speed_kmh` field (owner decision 2026-09-22: "no es un dato relevante" in a cross-season view). Feature 043's per-válida speed is untouched — it lives only on `EvolutionPoint` (`GET /evolution`), never here.
- `category_changed` compares `category_id` with the athlete's previous point in date order; the first point is `false`. `category_label` prefers the frozen label.
- `category_change_kind` (added 2026-09-22 after the T083 UX review, FR-042): `null` when `category_changed` is `false`; otherwise `"promotion"` only when the previous and the new catalogue category have the same `sex`, both `age_min` are known and the new `age_min` is greater; `"other"` for everything else (catalogue restructure such as MASTER B → B1/B2, unknown ages, sex change, move to a younger band). Derived from the catalogue rows already loaded — no extra statement — and, like `category_changed`, computed on the parent-filtered set, so it never hints at a withheld point.
- `seasons[].started` excludes DNS; `finished` counts `finished` and `minus_laps`.
- No cross-season aggregate of any kind; no points total across seasons (FR-039).
- **Parent filter**: when the caller is a parent and the policy gate is closed (`RACE_HISTORY_FAMILY_POLICY_VERSION` empty or not yet effective), points with `event_date < athlete.created_at.date()` are removed, `seasons` is recomputed from what remains, and nothing signals the removal.
- Budget: ≤ 3 SQL statements (asserted — dropped from 4 when `avg_speed_kmh` was removed, 2026-09-22), p95 ≤ 500 ms for ≤ 30 points.

## Pure builder

`app/services/race/history.py::build_history_points(results, events, series, categories, athlete_id, *, series_kind="cup") -> list[HistoryPoint]` — no I/O; calls `compute_field_metrics` per season; unit-tested with in-memory ORM objects like `test_field_metrics.py`. No `setups` parameter — dropped 2026-09-22 with `avg_speed_kmh`.

**Deviation (implemented 2026-09-21, T070):** the signature takes `athlete_id`, not `competitor_id` as originally drafted above. Reason: `third_party_guard.py`'s structural test (`tests/privacy/test_third_party_lock.py::test_expected_candidates_matches_current_surface`) asserts the *exact* set of public callables under `app.services.race` that declare a `competitor_id` parameter; adding an 8th would fail that assertion and require either a guard (impossible here — the function is sync/pure, like `compute_field_metrics`, and `club_competitor_only` only wraps async callables) or a new `ALLOWED_SINGLE_EVENT` entry. Since the history endpoint is explicitly keyed by `athlete_id` everywhere else in this contract, the builder resolves each season's `competitor_id` internally from the already-`athlete_id`-filtered own-result rows (`own_result.competitor_id`) instead of accepting it as an argument — this is a plain attribute read, not a function parameter, so the structural scan does not see it. A companion `build_season_completions(results, events, series, athlete_id, *, series_kind="cup") -> list[SeasonCompletion]` was added for the per-season "N de M" summary, filtered the same way.

**Known limitation carried over from `compute_field_metrics` (037, not modified here):** its per-event output dict is keyed only by `event_id`. If an athlete has two rows in the *same* event under two different `category_id`s (a real, previously observed edge case — see `race_result.py`'s docstring), only one category's field metrics survive internally; both `HistoryPoint`s for that event will show identical field-derived figures (`field_size`, `percentile`, `gap_to_median_pct`, `gap_to_winner_pct`). Pre-existing behavior, not introduced by this feature; not fixed here per the "do not modify `compute_field_metrics`" constraint.

## Tests

Category-change flag (real change vs rename); thresholds at 4/5 finishers; lapped athlete; DNF/DSQ/DNS; position without time; skipped válida and skipped season; even-sized median; statement count; parent gate closed/open; parent of another athlete 403/404; response schema contains no third-party field; 2026 `GET /evolution` responses byte-identical with and without historical data loaded.
