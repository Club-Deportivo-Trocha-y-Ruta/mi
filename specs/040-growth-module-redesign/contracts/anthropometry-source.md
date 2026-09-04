# Contract — reference source on anthropometry records, seed and recompute

## 1. `AnthropometryOut` (existing, additive)

New field: `growth_source: "WHO" | "CDC" | null`. Emitted by `POST /athletes/{id}/anthropometry`, `GET /athletes/{id}/anthropometry`, and `AthleteDetailOut.latest_anthropometry`. Clients that ignore it keep working. Frontend type `AnthropometricRecord.growth_source?: "WHO" | "CDC" | null`.

Behavioural change on `POST`: derived values are computed with `source=GrowthSource.WHO`; `weight_z_score`/`weight_percentile` are `null` when age at evaluation > 120.5 months; `growth_source` is stored as `"WHO"`. Request body unchanged.

## 2. WHO seed

- Module: `app/seed_growth_data.py` — loops over CDC sources (unchanged) **and** WHO sources: `app/data/who_lms/who_height_for_age.csv`, `who_bmi_for_age.csv`, `who_weight_for_age.csv`.
- CSV columns: `sex` (M/F), `age_months` (float, one decimal), `L`, `M`, `S` (floats as in the client JSON). Header row required.
- Upsert on `uq_lms_source_indicator_sex_age`; idempotent; dialect-aware like the CDC path.
- Exporter: `backend/scripts/export_who_lms_csv.py` reads `frontend/src/data/growth-reference-who.json` and writes the three CSVs deterministically (sorted by sex, age). Committed output; re-running produces a byte-identical file.
- `app/data/who_lms/README.md`: provenance (WHO 2007 reference tables URL, JSON `generated` date), columns, privacy note (population constants only), refresh instructions.
- Test `tests/services/test_growth_seed.py`: WHO row counts (168/168/60 per sex), idempotency, and **parity**: for 6 (indicator, sex, age) samples, backend `get_lms_params(..., source=WHO)` equals the client JSON L/M/S to 6 decimals.

## 3. Recompute (backfill v2)

- Module: `app/scripts/backfill_anthropometry.py` — after the existing "fill NULLs" pass, run `recompute_to_source(session, target=GrowthSource.WHO)`.
- Selection: `growth_source IS NULL OR growth_source != 'WHO'` and raw values present.
- Writes: `bmi` (unchanged formula), `height_z_score`, `height_percentile`, `bmi_z_score`, `bmi_percentile`, `nutritional_status`, `weight_z_score`/`weight_percentile` (WHO ≤ 120.5 months, else `NULL`), `growth_source = 'WHO'`.
- Never writes: `weight_kg`, `standing_height_cm`, `sitting_height_cm`, `arm_span_cm`, `evaluation_date`, `notes`, `maturity_offset`, `age_at_phv`, `maturation_status`, `training_implications`.
- Output: stdout summary `{scanned, recomputed, unchanged_status, band_changes}`; file `./data/growth_band_changes_<YYYYMMDD>.json` with `[{"athlete_id", "record_id", "indicator", "previous", "current"}]` — ids only. Logging uses aggregate counts and ids.
- Idempotent: second run selects zero rows.
- Wiring: unchanged (`entrypoint.sh` already runs `python -m app.scripts.backfill_anthropometry` after the seed).
- Tests `tests/scripts/test_backfill_anthropometry.py`: recompute switches a CDC row to WHO values; raw untouched; re-run no-op; band-change report shape; no PII in logs (caplog).

## 4. Family newsletter PDF

`services/training/growth_chart_builder.py` requests `GrowthSource.WHO`; the weight chart is omitted for athletes > 10 y. Existing tests updated; one real PDF regenerated as a manual gate (see `quickstart.md`).
