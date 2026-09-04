# WHO 2007 Growth Reference LMS data (vendored)

These CSV files are the **WHO Growth Reference 5–19 years (2007)** LMS
parameters, vendored (committed to the repo) so that seeding the
`growth_reference_lms` table with `source=WHO` is **deterministic and
offline** — no network call at deploy time (Render free tier, cold start).

| File | Indicator | Rows |
|------|-----------|------|
| `who_height_for_age.csv` | `height_for_age` | 336 (168 ages × M/F), 61.5–228.5 months |
| `who_bmi_for_age.csv` | `bmi_for_age` | 336 (168 ages × M/F), 61.5–228.5 months |
| `who_weight_for_age.csv` | `weight_for_age` | 120 (60 ages × M/F), 61.5–120.5 months (WHO does not publish weight-for-age beyond 10 years) |

## Provenance

Source: WHO Growth Reference data for 5–19 years, indicators
`height_for_age`, `bmi_for_age`, `weight_for_age`
(https://www.who.int/tools/growth-reference-data-for-5to19-years/indicators).
Colombia compliance reference: Resolución 2465/2016 MinSalud.

These CSVs are **not** downloaded directly from `who.int` at build/seed time.
They are exported by `backend/scripts/export_who_lms_csv.py` from the
already-reviewed client copy `frontend/src/data/growth-reference-who.json`
(`generated: 2026-05-06`), which is the single source of truth for the WHO
L/M/S tables in this repository — both the browser chart and the server seed
read the same numbers, exported deterministically to two formats.

## Columns

Each CSV has a header row: `sex,age_months,L,M,S`.

- `sex`: `M` or `F` (already normalized; no numeric sex codes as in the CDC
  vendored files).
- `age_months`: age in months, one decimal (e.g. `61.5`).
- `L`, `M`, `S`: Cole & Green (1992) Box-Cox parameters. `height_for_age` has
  `L = 1` for every row (WHO publishes a fixed Box-Cox power of 1 for
  height); `bmi_for_age` and `weight_for_age` have `L` varying by age/sex.

`app/seed_growth_data.py` consumes these columns to upsert
`growth_reference_lms` rows with `source='WHO'`.

## Privacy

These files contain **only population reference constants** (the L/M/S
parameters of the Cole & Green LMS distribution by age and sex). They
contain **no athlete data**, no minor data, and no personally identifiable
information of any kind. They are public-domain WHO reference data.

## Refreshing

The WHO 2007 reference tables are stable and are not expected to change. If
`frontend/src/data/growth-reference-who.json` is ever regenerated (e.g. to
correct a transcription error), re-run the exporter to keep both copies in
sync:

```sh
cd backend
.venv/bin/python scripts/export_who_lms_csv.py
```

The exporter is deterministic: re-running it without changing the source
JSON produces byte-identical CSV files. Then re-run the offline seed
(`python -m app.seed_growth_data`) to upsert any changes — the seed is
idempotent (upsert on `uq_lms_source_indicator_sex_age`).
