# Data Model — Newsletter Audit Fixes (024)

**No Alembic migration.** All changes are additive fields inside existing JSON columns (`athlete_monthly_newsletters.metrics_snapshot`, `athlete_monthly_newsletters.ai_narrative`) plus in-memory render context. Persisted pre-024 snapshots remain valid (fields optional, template guards).

## 1. `metrics_snapshot.email_blocks` — deltas

### 1.1 `attendance` (modified)

| Field | Type | Change | Notes |
|---|---|---|---|
| `streak_sessions` | int | **RENAMED** from `streak_days` | Counts consecutive sessions, not days. Fixes existing backend/frontend key mismatch (frontend already reads `streak_sessions`). Templates read `streak_sessions` with fallback to legacy `streak_days` for old snapshots. |

### 1.2 `technical` (extended)

| Field | Type | New? | Notes |
|---|---|---|---|
| `weekly_hours_avg` | float \| null | NEW | `total_training_hours / (days_in_month / 7)`, round 1. Null when no sessions. |
| `ltad_limit_hours` | float \| null | NEW | Age decimal at generation date (`compute_age_decimal(birth_date, generation_date)`), round 1. Null if birth_date missing. |
| `ltad_status` | `"ok"` \| `"review"` \| null | NEW | `ok` iff `weekly_hours_avg ≤ ltad_limit_hours`. Null when either side null. |
| `focus_groups` | list[FocusGroup] | NEW | See §3. Ordered by `session_count` desc. Max ~10 groups. |
| `focos_tecnicos` | list[str] | kept | Unchanged — still feeds AI prompt and old templates. |

### 1.3 `race_results.results[]` (extended per item)

| Field | Type | New? | Notes |
|---|---|---|---|
| `short_label` | str | NEW | Via `_race_short_label` → `"CD"`, `"CN"`, `"V{n}"`. KPI card identity. |
| `category_label` | str \| null | NEW | From `race_categories.label` by `category_code`; null/absent → template shows raw `category_code`. |
| `label` | str | kept | Readable form, already present. |

### 1.4 `race_results.progression_history[]` (unchanged fields; consumed flag)

No new per-row fields. `charts_context` (pdf_only) gains `has_championship` (§2.2).

### 1.5 `calendar` (formatted at render, not re-stored)

`next_training_sessions[].date` and `next_race_events[].date` stay ISO in snapshot; Spanish formatting (`format_date_es`) applies at template render via Jinja filter/context helper. **Rule: snapshot stores machine formats; templates localize.**

### 1.6 `support_at_home` (rebuilt)

| Field | Type | Change | Notes |
|---|---|---|---|
| `tips[]` | list[Tip] | content change | Selected by age band + month rotation at build time. Same shape (`category`, `title`, `text`). |
| `age_band` | `"10-12"` \| `"13-15"` | NEW | Band used; cutoff: age_decimal < 13 → `10-12`. |
| `rotation_index` | int | NEW | `month % variants` — traceability of deterministic rotation. |

## 2. `metrics_snapshot.pdf_only_blocks` — deltas

### 2.1 `photos` / gallery (render-time only — NOT persisted)

Snapshot keeps current `photos` block (media_id, thumbnail_url, storage_url, caption, media_type). **Data URIs are computed at PDF render time and never written to the snapshot or email blocks** (privacy + row-size). Render context adds:

| Context var | Type | Notes |
|---|---|---|
| `photos_render.items[].data_uri` | str \| null | base64 JPEG from SFTP thumb (spec-022 pattern, ≤2 MB total budget). |
| `photos_render.embeddable_count` | int | Items with non-null data_uri. |
| `photos_render.eligible_count` | int | From snapshot `photos.count`. |

Gallery gate: `eligible_count == 0` → omit section; `eligible_count > 0 and embeddable_count == 0` → placeholder ("N fotos del mes disponibles en la plataforma"); else render embeddable items.

### 2.2 `charts_context` (extended)

| Field | Type | New? | Notes |
|---|---|---|---|
| `has_championship` | bool | NEW | `any(series_kind == "championship")` over history → renders no-points footnote. |

## 3. FocusGroup (new value object — `focus_grouping.py`)

```
FocusGroup:
  slug: str            # 'posicion' | 'vision' | 'frenado' | 'control_baja_velocidad' |
                       # 'curvas' | 'separacion' | 'presion_terreno' | 'cambios_cadencia' |
                       # 'resistencia_acondicionamiento' | 'otros'
  name: str            # Spanish display name (A–H names from technique_catalog.SKILLS;
                       # 'Resistencia y acondicionamiento'; 'Otros')
  session_count: int   # ≥1 — groups with 0 sessions are not emitted
```

Mapping rule: accent-insensitive lowercase keyword sets per family, evaluated in priority order; first match wins; no match → `otros`. Pure function `group_focus_texts(focus_list: list[str]) -> list[FocusGroup]`. A focus string counts once per session occurrence (input is per-session list, not deduped).

## 4. `ai_narrative` context (input-side delta, same output shape)

| Prompt context field | Type | New? | Notes |
|---|---|---|---|
| `athlete_reference` | `"su hijo"` \| `"su hija"` \| `"su hijo/a"` | NEW | Derived from `Athlete.sex` (M/F/None). Prompt instructs exact usage + grammatical agreement. Never combined with real name (forbidden_names scrub unchanged). |
| `streak_sessions` | int | RENAMED | Follows §1.1 rename (registry + .j2). |

Output schema (`strengths`, `area_to_develop`, `milestone`, `block_captions`, `month_highlights`, `confidence`, …) **unchanged**.

## 5. Validation rules

- `weekly_hours_avg`, `ltad_limit_hours` ≥ 0; one decimal.
- `ltad_status` present iff both inputs present.
- `short_label` always non-empty for new snapshots (`"—"` fallback preserved).
- `focus_groups` total `session_count` == number of sessions with non-empty `technical_focus`.
- `support_at_home.tips` never mention supplements/calories (static content review + existing guardrail tests).
- Data URIs: forbidden in `metrics_snapshot` and in any email-rendered block (new privacy test).
- Old snapshot (missing every new field) renders both templates without exception (regression fixture).

## 6. State transitions

None — newsletter lifecycle (draft → sent) untouched.
