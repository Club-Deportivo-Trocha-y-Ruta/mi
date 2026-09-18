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
    "category_changed": true, "previous_category_label": "INFANTIL B",
    "status": "finished", "position": 9, "field_size": 23, "timed_finishers": 21,
    "percentile": 63.6, "gap_to_median_pct": -4.2, "gap_to_winner_pct": 11.8,
    "avg_speed_kmh": null, "points_awarded": 18
  }],
  "seasons": [{"season": 2025, "started": 7, "finished": 6}],
  "caveats": ["different_courses", "weather_surface", "small_fields", "non_finishers_excluded", "three_rider_categories"]
}
```

Rules

- `field_size` = finishers including lapped riders; `timed_finishers` = strict `FINISHED` with a time (feature 037 definitions, reused through `compute_field_metrics`).
- `percentile = null` when `field_size < 5`. `gap_to_median_pct = null` when `timed_finishers < 5`, or the athlete's status is not `finished`, or the athlete has no time. `gap_to_winner_pct` follows the same status rule (no threshold; kept for continuity).
- `avg_speed_kmh` from `course/derived.py::derive_figures`; `null` without a course setup. Never estimated.
- `category_changed` compares `category_id` with the athlete's previous point in date order; the first point is `false`. `category_label` prefers the frozen label.
- `seasons[].started` excludes DNS; `finished` counts `finished` and `minus_laps`.
- No cross-season aggregate of any kind; no points total across seasons (FR-039).
- **Parent filter**: when the caller is a parent and the policy gate is closed (`RACE_HISTORY_FAMILY_POLICY_VERSION` empty or not yet effective), points with `event_date < athlete.created_at.date()` are removed, `seasons` is recomputed from what remains, and nothing signals the removal.
- Budget: ≤ 4 SQL statements (asserted), p95 ≤ 500 ms for ≤ 30 points.

## Pure builder

`app/services/race/history.py::build_history_points(results, events, series, categories, setups, competitor_id) -> list[HistoryPoint]` — no I/O; calls `compute_field_metrics` per season; unit-tested with in-memory ORM objects like `test_field_metrics.py`.

## Tests

Category-change flag (real change vs rename); thresholds at 4/5 finishers; lapped athlete; DNF/DSQ/DNS; position without time; skipped válida and skipped season; even-sized median; speed only with a setup; statement count; parent gate closed/open; parent of another athlete 403/404; response schema contains no third-party field; 2026 `GET /evolution` responses byte-identical with and without historical data loaded.
