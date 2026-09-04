# Contract — WHO 2007 LMS vendored data

## Files

```text
backend/app/data/who_lms/
├── README.md
├── who_height_for_age.csv    # sex,age_months,L,M,S — 336 rows (168 × M/F), 61.5 … 228.5
├── who_bmi_for_age.csv       # 336 rows
└── who_weight_for_age.csv    # 120 rows (60 × M/F), 61.5 … 120.5
backend/scripts/export_who_lms_csv.py   # deterministic exporter from frontend/src/data/growth-reference-who.json
```

## Provenance

WHO Growth Reference 5–19 years (2007), height-for-age, BMI-for-age (5–19 y), weight-for-age (5–10 y): https://www.who.int/tools/growth-reference-data-for-5to19-years/indicators. The repository copy was produced on 2026-05-06 as `growth-reference-who.json` (client) and is exported unchanged to CSV for the server. Population constants only — no athlete data.

## Invariants (tested)

1. Every `(indicator, sex, age_months)` in the CSVs exists in the JSON with identical `L`, `M`, `S` (6 decimals).
2. Ages are strictly increasing per (indicator, sex); no gaps > 1 month.
3. `height_for_age` has `L = 1.0` for all rows (WHO publishes Box-Cox power 1 for height); `bmi_for_age` `L` varies.
4. Seed is idempotent: running twice yields the same row count.
5. `get_lms_params(..., source=WHO)` at an in-between age interpolates linearly between the two neighbouring rows (existing behaviour, now covered for WHO).
