# Contract: `GET /api/athletes/{athlete_id}/race-analysis/evolution` (additive)

**Feature**: 039 · **Router**: `backend/app/routers/athlete_race_analysis.py::get_evolution` · **Service**: `services/race/analytics_charts.build_evolution`

## Request

| Param | Type | Required | Notes |
|---|---|---|---|
| `season` | int (2020..2100) | yes | unchanged |
| `metric` | `podium_gap_ms \| ranking \| time_ms \| percentile` | no (default `podium_gap_ms`) | unchanged |
| `series_id` | int ≥ 1 | no | **NEW**. Restricts `series` to that comparison group. Unknown / not-raced `series_id` → `series = []`, `groups` still populated, `confidence = low`, HTTP 200 (never 404). |

RBAC unchanged: admin, coach, parent (own athletes only via `verify_athlete_access`). A parent requesting another athlete with `series_id` MUST still receive 403/404 exactly as without it (denied-path test).

## Response `200`

```jsonc
{
  "season": 2026,
  "metric": "ranking",
  "selected_group": "cup:12",            // NEW — null when no series_id was sent
  "groups": [                            // NEW — cups first (earliest raced round), then championships by date
    { "comparison_group": "cup:12", "series_id": 12, "kind": "cup", "level": "departmental",
      "label": "Copa Valle de Ciclomontañismo 2026", "n_points": 5 },
    { "comparison_group": "championship:31", "series_id": 31, "kind": "championship", "level": "departmental",
      "label": "Cto. Dep. — Ginebra", "n_points": 1 },
    { "comparison_group": "championship:44", "series_id": 44, "kind": "championship", "level": "national",
      "label": "Cto. Nal. — Pereira", "n_points": 1 }
  ],
  "series": [                            // filtered by series_id when given; chronological
    {
      "valida_num": 1, "event_id": 91, "event_date": "2026-01-31", "value": 4.0, "unit": "position",
      "series_kind": "cup", "label": "Válida I — Sevilla",
      "series_id": 12, "series_name": "Copa Valle de Ciclomontañismo",   // NEW
      "series_level": "departmental", "comparison_group": "cup:12",       // NEW
      "field_size": 11, "percentile": 70.0,                              // NEW (null when not finished)
      "position": 4, "gap_pct": 4.2                                      // NEW (null when not finished; exposed for every metric, not just ranking/podium_gap_ms)
    }
  ],
  "confidence": "medium"                 // computed over the returned series (n<3 low, ≥8 high)
}
```

Back-compat: every pre-existing field keeps its name, type and semantics; `valida_num` remains (0..99). Clients that ignore `groups` keep working (they receive the full season when `series_id` is omitted).

## Errors

Unchanged: 401 unauthenticated, 403/404 per `verify_athlete_access`, 422 on invalid query values.

---

# Contract: `GET /api/athletes/{athlete_id}/race-analysis/races` (additive)

`RaceParticipationOption` gains `series_id: int`, `series_name: str`, `series_level: "departmental" | "national"`. Ordering and RBAC unchanged. The Distribution picker keeps listing every raced race (cup rounds and championships) — FR-017.

---

# Frontend client

```ts
getAthleteEvolution(athleteId, season, metric, seriesId?: number): Promise<EvolutionResponse>
useAthleteEvolution(athleteId, season, metric, seriesId?)   // queryKey includes seriesId; staleTime 5 min unchanged
```

TS types mirror the Pydantic schema field-for-field (`types/athleteRaceAnalysis.types.ts`: `EvolutionPoint`, `EvolutionResponse`, new `ComparisonGroupOption`).
