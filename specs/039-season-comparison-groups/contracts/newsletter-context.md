# Contract: newsletter race block and chart context

**Feature**: 039 · **Builder**: `backend/app/services/training/newsletter_builder.py` (`_build_race_block`, `_build_charts_context`) · **Template**: `backend/templates/documents/pdf/athlete_stage_log.html` + new partial `charts/championship_card.html.jinja`

## `email_blocks.race_results` (additive)

```jsonc
{
  "has_races": true,
  "competitor_id": 501,
  "results": [ /* month rows — unchanged shape, label/short_label already level-aware */ ],
  "progression_history": [ /* flat season rows — kept one release */ ],
  "cups": [
    {
      "series_id": 12,
      "label": "Copa Valle de Ciclomontañismo 2026",
      "history": [
        { "event_id": 91, "valida_num": 1, "event_date": "2026-01-31", "position": 4, "points_awarded": 30,
          "gap_to_winner_pct": 13.4, "series_kind": "cup", "series_level": "departmental",
          "location": "Sevilla", "label": "V1" }
      ]
    }
  ],
  "championships": [
    {
      "event_id": 120, "label": "Campeonato Nacional", "short_label": "Cto. Nal. — Pereira",
      "level": "national", "location": "Pereira", "event_date": "2026-08-22",
      "category_label": "Infantil A", "finished": true,
      "position": 11, "field_size": 34, "gap_pct": 35.6, "percentile": 69.7
    }
  ],
  "projection": null
}
```

Rules: dedupe across linked competitors by `event_id`; `cups` ordered by earliest raced round; `championships` chronological; a not-finished championship has `finished=false` and null numbers. No names, bibs or competitor ids of third parties.

## `pdf_only_blocks.charts_context` (additive)

```jsonc
{
  "has_data": true,                 // at least one cup with rows
  "has_championship": true,         // kept for existing consumers
  "cups": [
    {
      "series_id": 12,
      "label": "Copa Valle de Ciclomontañismo 2026",
      "n_samples": 5,
      "low_confidence": false,      // n_samples < 5
      "positions":          [ { "x": 1, "label": "V1", "y": 4 } ],
      "gap_pcts":           [ { "x": 1, "label": "V1", "y": 13.4 } ],
      "points_accumulated": [ { "x": 1, "label": "V1", "y": 30 } ]
    }
  ]
}
```

`x` is the ordinal within the cup (1..N); accumulated points sum only that cup's `points_awarded` and MUST equal the athlete's cup total in `standings` (test).

## Template behavior

- For each `charts_context.cups[]`: heading `Evolución en la {label}` + the three existing SVG macros (`line_positions`, `gap_pct`, `points_accumulated`), `break-inside: avoid` per cup block.
- After the cup blocks, when `race_results.championships` is non-empty: section `Campeonatos`, one `championship_card` per entry, then the note sentence (research D13). Hidden otherwise.
- Missing keys (old snapshots) → treated as empty lists; no error.
- Email template (`templates/email/athlete_stage_log.html`) unchanged.

## Card partial (`championship_card.html.jinja`)

Inputs: one `ChampionshipReading`. Renders a stat-tile row: `Posición` (`P{n}` or `—`), `Pelotón` (`{field_size} en {category_label}`), `Gap al P1` (`+{gap_pct} %` or `—`), `Percentil` (`{percentile}`) with the heading `{label} · {location} · {event_date}`. When `finished` is false the four values are replaced by `No completó la prueba.` Text uses the document text colors, never the chart series colors.
