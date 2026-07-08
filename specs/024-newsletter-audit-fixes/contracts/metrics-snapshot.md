# Contract — metrics_snapshot / render context (feature 024)

Internal contract between `newsletter_builder` (producer) and: PDF template, email template, frontend preview (`NewsletterPreviewBlocks`), AI use case (consumers). No new HTTP endpoints; existing routes (`POST /api/athletes/{id}/monthly-newsletters`, batch, PDF download) keep their schemas — `metrics_snapshot` is opaque JSON to the API layer.

## Producer guarantees (new snapshots, ≥024)

```jsonc
{
  "email_blocks": {
    "attendance": {
      "sessions_total": 14,
      "sessions_present": 14,
      "attendance_pct": 100.0,
      "attendance_pct_prev_month": 100.0,
      "streak_sessions": 14            // RENAMED (was streak_days)
    },
    "technical": {
      "focos_tecnicos": ["..."],       // kept (AI prompt, backward compat)
      "focus_groups": [                 // NEW
        {"slug": "curvas", "name": "Trazado de curvas", "session_count": 5}
      ],
      "avg_rpe": 4.8,
      "avg_rubric_effort": 4.9,
      "avg_rubric_attitude": 5.0,
      "avg_rubric_technique": 4.9,
      "total_training_hours": 27.5,
      "weekly_hours_avg": 6.4,         // NEW
      "ltad_limit_hours": 13.9,        // NEW
      "ltad_status": "ok"              // NEW: "ok" | "review" | null
    },
    "race_results": {
      "results": [{
        "label": "Campeonato Departamental",
        "short_label": "CD",           // NEW
        "category_code": "PJUV_A_F",
        "category_label": "..."        // NEW, null si no mapea
        // ...resto sin cambio
      }]
    },
    "support_at_home": {
      "age_band": "13-15",             // NEW
      "rotation_index": 2,             // NEW
      "tips": [{"category": "...", "title": "...", "text": "..."}]
    }
    // calendar/photos/badges: sin cambio de shape (fechas siguen ISO)
  },
  "pdf_only_blocks": {
    "charts_context": {
      "has_championship": true         // NEW
      // ...resto sin cambio
    }
    // anthropometry / percentile_curves: sin cambio
  }
}
```

## Consumer rules

| Consumer | Rule |
|---|---|
| PDF template | Read `streak_sessions`, fallback `streak_days` (old snapshots). Prefer `focus_groups`; fallback `focos_tecnicos`. Prefer `short_label`/`category_label`; fallback `valida_num`/`category_code`. Localize ISO dates via `format_date_es`. |
| Email template | Same fallback rules for labels/dates. MUST NOT read `pdf_only_blocks`, photos, or any `data_uri`. |
| Frontend preview | Already reads `streak_sessions` — contract now satisfied. New fields optional (`?.`), no breaking change. |
| AI use case | Context gains `athlete_reference` + renamed `streak_sessions`. Output schema unchanged. |

## Render-time-only context (never persisted, never emailed)

```jsonc
"photos_render": {
  "eligible_count": 3,
  "embeddable_count": 2,
  "items": [{"data_uri": "data:image/jpeg;base64,...", "caption": null}]
}
```

Gallery gate: `eligible_count==0` → no section · `embeddable_count==0` → placeholder con conteo · else → imágenes.

## Compatibility invariants

1. Every new field optional; absence == pre-024 snapshot; both templates render without error.
2. `streak_days` never emitted by new builder, but tolerated by templates on read.
3. `metrics_snapshot` MUST NOT contain `data:` URIs (privacy test enforces).
4. Email blocks MUST NOT gain anthropometry, photos, or data URIs (existing dispatcher pops unchanged).
