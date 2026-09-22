# Data Model — Race history backfill (044)

One Alembic revision, `down_revision = c2314ccd7927` (single head preserved). No new enum type on an existing table; the two new tables use string-valued enums declared with `values_callable`, as elsewhere in the race module.

## 1. `race_results` — three new nullable columns

| Column | Type | Rule |
|---|---|---|
| `category_label_raw` | `VARCHAR(100) NULL` | Category header exactly as printed in the source. Written once at insert; never updated. |
| `category_age_min_raw` | `SMALLINT NULL` | Copy of the catalogue `age_min` at insert time. |
| `category_age_max_raw` | `SMALLINT NULL` | Copy of the catalogue `age_max` at insert time. |

Backfill in the same revision: `UPDATE race_results r JOIN race_categories c ON c.id = r.category_id SET r.category_label_raw = c.label, r.category_age_min_raw = c.age_min, r.category_age_max_raw = c.age_max WHERE r.category_label_raw IS NULL` (dialect-neutral form for the aiosqlite lane). `uq_race_results_event_category_competitor` and all indexes are untouched. Nullable trailing columns are `ALGORITHM=INSTANT` on MySQL 8.4.

## 2. `race_competitors`

| Change | Detail |
|---|---|
| drop | `uq_race_competitors_normalized_name` |
| add | `ix_race_competitors_normalized_name` (non-unique) |
| add | `city_text VARCHAR(100) NULL` — disambiguation signal only (FR-014); never serialised outside the identity-review schemas |

Two competitors may now share `normalized_name`. Uniqueness of identity moves to §3.

## 3. `race_competitor_signatures` (new)

An observed way a competitor is printed. Owned by exactly one competitor.

| Column | Type | Notes |
|---|---|---|
| `id` | `INT PK` | |
| `competitor_id` | `INT NOT NULL FK → race_competitors.id ON DELETE CASCADE` | indexed |
| `normalized_name` | `VARCHAR(160) NOT NULL` | `normalize_name` |
| `club_norm` | `VARCHAR(150) NOT NULL DEFAULT ''` | `normalize_club` (placeholders → `''`) |
| `city_norm` | `VARCHAR(100) NOT NULL DEFAULT ''` | same normalisation |
| `discriminator` | `VARCHAR(32) NOT NULL DEFAULT ''` | revision `a7c3e5d91f20` (owner decision 2026-09-21). `''` for every signature that needs no tie-break; otherwise `"<sex>:<age_min>-<age_max>@<season>"` from the catalogue row of the category (see research R-06 §9); for third-party same-válida collisions also `"bib:<bib>@<season>"` or `"row:<code>-<index>@<season>"` (owner decision 2026-09-22, R-06 §10) — never category-compatible |
| `first_season` / `last_season` | `SMALLINT NOT NULL` | widened on each sighting |
| `source_candidate_id` | `INT NULL FK → race_identity_candidates.id ON DELETE SET NULL` | set when a `same_person` decision attached this signature (enables exact reversal) |
| `created_at` | `DATETIME NOT NULL` | |

`UNIQUE(normalized_name, club_norm, city_norm, discriminator)` — `uq_race_competitor_signatures_identity` (revision `a7c3e5d91f20`, replacing the original `uq_race_competitor_signatures_triple` of `8efe1618cb83`). `NOT NULL DEFAULT ''` on purpose: MySQL treats `NULL`s as distinct in a unique key, which would void the guard. The downgrade of `a7c3e5d91f20` refuses while any triple has more than one signature.

Backfill: one signature per existing competitor from `(normalized_name, normalize_club(club_text), '')`, seasons from its results (fallback: current season).

## 4. `race_identity_candidates` (new)

Review queue and decision audit in one table.

| Column | Type | Notes |
|---|---|---|
| `id` | `INT PK` | |
| `kind` | `ENUM('same_person_suspect','homonym_suspect')` | |
| `pair_hash` | `CHAR(64) NOT NULL UNIQUE` | SHA-256 of the two ordered record keys; makes rebuilds idempotent and "never ask again" structural |
| `left_record` / `right_record` | `JSON NOT NULL` | snapshot: `name_printed`, `normalized_name`, `club`, `city`, `seasons[]`, `category_codes[]`, `sex`, `competitor_id?`, `athlete_linked: bool`; internal keys never serialised: `key`, `club_norm`, `city_norm`, `discriminator` and `result_ids` (records split by category), `attached_result_ids` (results a `same_person` decision attached or merged, for exact reversal) |
| `score` | `SMALLINT NOT NULL` | 0–100 |
| `signals` | `JSON NOT NULL` | e.g. `["extra_surname"]`, `["same_valida_two_categories"]`, `["club_and_city_differ"]` |
| `state` | `ENUM('pending','same_person','different_people')` | default `pending` |
| `linked_athlete_involved` | `BOOL NOT NULL DEFAULT 0` | FR-022 |
| `decided_by_user_id` / `decided_at` | `INT NULL FK users` / `DATETIME NULL` | |
| `reversed_by_user_id` / `reversed_at` | same | a reversed decision returns to `pending`; the row keeps the reversal stamps, and `record_audit` holds the full sequence |
| `created_at` / `updated_at` | `DATETIME` | |

Index `ix_race_identity_candidates_state (state)`.

State transitions: `pending → same_person | different_people`; `same_person | different_people → pending` (reversal, audited). No deletion: a candidate that disappears from a later rebuild stays as history.

## 5. `race_categories` — three seeded rows, no schema change

`MAS_B_2025`, `MAS_C_2025`, `PRE_F_U`, all `is_active = false`, added to `scripts/seed_race_categories.py` (idempotent upsert). Header aliases live in `normalizer.HEADER_TO_CODE` (see `contracts/category-mapping.md`).

## 6. `race_points_schemes` — two seeded descriptive rows

`copa_valle_2024`, `copa_valle_2025`: `is_official = false`, `position_points = {}`, description "Puntos tal como fueron impresos por el organizador; no se recalculan".

## 7. `race_imports.parse_meta_json` — new keys (no schema change)

```json
{
  "categories": [{"header_raw": "…", "code": "PJUV_A_F", "mapping_kind": "rename", "rows": 14,
                  "completeness": {"status": "inconsistent", "missing": [6], "duplicated": []}}],
  "unreadable_rows": [{"page": 3, "ordinal": 12}],
  "corrections": [{"op": "add", "category_header": "…", "ordinal": 6, "row": {…}, "by": 3, "at": "…"}],
  "acknowledged": [{"category_header": "…", "reason": "source_missing_ordinal", "by": 3, "at": "…"}],
  "pending_categories": ["…"]
}
```

Rows inside `corrections` hold rider names; this JSON is database-only and is excluded from every log, trace and list response.

## 8. Settings

`RACE_HISTORY_FAMILY_POLICY_VERSION: str = ""` — empty keeps pre-joining results hidden from families.

## 9. Value objects (not persisted)

- `CompletenessReport(status: ok|inconsistent|acknowledged, missing: list[int], duplicated: list[int])`
- `HistoryPoint` — see `contracts/history-progression-api.md`.
- `SeasonCompletion(season, started, finished)`.

## 10. Invariants (each has a test)

1. A result's frozen label and age range never change after insert, including through the revision flow and catalogue edits.
2. No two signatures share `(normalized_name, club_norm, city_norm, discriminator)`; concurrent ingests of the same new rider yield one competitor.
3. No historical import is committed while any candidate is `pending`.
4. No function returns cross-válida data for a competitor whose `athlete_id IS NULL`.
5. `city_text`, `city_norm` and candidate snapshots are serialised only by the identity-review schemas (coach/admin).
6. A parent response never contains a result dated before the athlete's registration while the policy gate is closed, and never a count of withheld rows.
7. Season-specific categories never appear in a selector for current-season data.
8. Re-staging or re-committing an identical file creates no row in any table.
9. No log line, trace or exception message produced by any new code path contains a rider name, club or city.
