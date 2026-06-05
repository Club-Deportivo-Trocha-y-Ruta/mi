# Feature 003 — Offline LMS seed + anthropometry backfill

**Branch**: `003-improve-individual-newsletter-pdf` · **Date**: 2026-06-05

## What changed

The CDC LMS growth-reference data is now seeded **deterministically and offline**,
and historical anthropometric records are **backfilled** so derived values
(BMI, percentiles, z-scores) are populated everywhere.

### 1. Vendored CDC LMS data

The three CDC LMS datasets are committed as CSVs under
`backend/app/data/cdc_lms/` (`statage.csv`, `bmiagerev.csv`, `wtage.csv`). They
contain only population reference constants (L/M/S by age/sex) — **no minor
data**. See that folder's `README.md` for source URLs and refresh instructions.

`app/seed_growth_data.py` reads these vendored files (no `cdc.gov` download). The
upsert is dialect-aware (MySQL `ON DUPLICATE KEY UPDATE` in prod, SQLite
`ON CONFLICT` in tests) and idempotent via `uq_lms_source_indicator_sex_age`.

### 2. BMI decoupled from LMS (bug fix)

`routers/anthropometry.create_anthropometry` previously nulled `bmi` whenever the
LMS table was empty (`bmi = growth.bmi if growth else None`). BMI needs no
reference table, so it is now **always** computed and persisted when weight and
height are present. Percentiles/z-scores remain gated on LMS availability.

### 3. Idempotent backfill

`python -m app.scripts.backfill_anthropometry` recomputes missing derived values
for existing rows using `services/growth.py` + the BMI formula. It **never**
touches raw measurement columns, skips already-populated rows, and logs only
aggregate counts (no minor identifiers). Re-running is a no-op.

## Deploy wiring

`backend/entrypoint.sh` runs, after `alembic upgrade head`:

```sh
python -m app.seed_growth_data || echo "WARN: seed LMS falló; el servidor continúa."
python -m app.scripts.backfill_anthropometry || echo "WARN: backfill ... continúa."
```

Both are idempotent, offline, and guarded so a failure cannot crash startup.

## Tests

- `tests/services/test_growth_seed.py` — offline seed coverage + idempotency.
- `tests/routers/test_anthropometry_bmi.py` — BMI persists with empty LMS; percentiles persist when seeded.
- `tests/scripts/test_backfill_anthropometry.py` — fills NULLs, raw untouched, re-run no-op, no PII in logs.
