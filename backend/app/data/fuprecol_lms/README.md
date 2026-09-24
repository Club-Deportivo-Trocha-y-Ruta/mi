# FUPRECOL skinfold LMS reference data (vendored)

This CSV is the **FUPRECOL study** LMS (Cole & Green Box-Cox) reference for
triceps, subscapular and triceps+subscapular-sum skinfold thickness by sex
and age, vendored (committed to the repo) so that seeding the
`growth_reference_lms` table with `source='FUPRECOL'` is **deterministic and
offline** — no network call at deploy time (Render free tier, cold start).

## Citation

Ramírez-Vélez R, Correa-Bautista JE, Martínez-Torres J, González-Ruíz K,
González-Jiménez E, Schmidt-RioValle J, Garcia-Hermoso A. **Percentile
Values for Anthropometric Body Composition Indices among Colombian Children
and Adolescents: The FUPRECOL Study.** *Nutrients.* 2016;8(10):595.
DOI: [10.3390/nu8100595](https://doi.org/10.3390/nu8100595)
PMC: [PMC5083983](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5083983/)

Licence: CC BY 4.0 (open access, no restriction on re-use with attribution).

## Population

Bogotá schoolchildren, n = 9 618 (4 253 boys, 5 365 girls), ages 9–17.9
years. Skinfolds measured with a **Holtain caliper** on the **left side** of
the body (standard anthropometric convention).

## Columns

`indicator,sex,age_months,L,M,S` (one header row, 54 data rows = 3
indicators × 2 sexes × 9 one-year age bands).

- `indicator`: `triceps_skinfold_for_age` (article Table 2),
  `subscapular_skinfold_for_age` (article Table 3), or
  `triceps_subscapular_sum_for_age` (article Table 4).
- `sex`: `M` or `F` (matches the `Sex` enum convention already used by
  `who_lms/*.csv` — no numeric sex codes as in the CDC vendored files).
- `age_months`: the **midpoint** of the article's one-year age band, e.g.
  band `9 to 9.9` → `114` (9.5 years × 12), band `10 to 10.9` → `126`, …
  through band `17 to 17.9` → `210`. This midpoint convention mirrors how
  `app/services/growth.py` already interpolates between vendored LMS rows
  for WHO/CDC; it is *not* the article's own reporting age.
- `L`, `M`, `S`: the Cole & Green (1992) Box-Cox parameters transcribed
  directly from the article's tables — `L` and `S` as published, `M` taken
  from the article's `P50 (M)` column (the LMS median, which is what the
  published percentile table reports as `M`).

## Extraction method

Fetched the PMC HTML rendering of the article
(`https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5083983/`) and parsed Tables
2–4 programmatically with `pandas.read_html`, matching each parsed table
back to its caption (`Table 2.` = triceps, `Table 3.` = subscapular,
`Table 4.` = triceps + subscapular sum) before transcribing `L`, `S` and
`P50 (M)` per sex/age-band row. The `Total` row (all ages pooled) in each
article table is not vendored — only the nine per-age-band rows per sex.

Six values were spot-checked by hand against the raw extracted HTML text
(not just the pandas parse) to catch column-alignment errors:

| Indicator | Sex | Band | L | M (P50) | S |
|---|---|---|---|---|---|
| Triceps | Boys | 9–9.9 | −0.30 | 10.0 | 0.37 |
| Triceps | Girls | 17–17.9 | −0.93 | 21.4 | 0.39 |
| Subscapular | Boys | 9–9.9 | −0.06 | 10.0 | 0.35 |
| Sum (T+SS) | Boys | 9–9.9 | −0.30 | 23.0 | 0.37 |
| Sum (T+SS) | Boys | 16–16.9 | −0.37 | 27.0 | 0.49 |
| Sum (T+SS) | Girls | 9–9.9 | −0.97 | 28.0 | 0.34 |

All six matched the vendored CSV exactly.

Note: as published, the article reports **identical `L` and `S` values for
the Triceps table and the Sum (T+SS) table**, row for row, per sex/age band
(only `SD` and the percentile columns differ). This was verified against
the raw HTML twice (it is not a transcription artefact on our side) and is
transcribed faithfully — we do not correct or second-guess the source
article's published Box-Cox parameters.

## Privacy

This file contains **only population reference constants** (LMS parameters
by age and sex from a published, de-identified epidemiological study). It
contains no athlete data, no minor-identifying data, and no data from this
club's roster.

## Refreshing

The source article is a fixed, published dataset (not a live feed like
CDC's growth-chart CSVs) — there is no refresh script. If a future erratum
to the FUPRECOL tables is published, re-fetch
`https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5083983/`, re-parse Tables
2–4 the same way, and re-run `python -m app.seed_growth_data` (the seed
upserts on `uq_lms_source_indicator_sex_age`, so corrected rows overwrite
in place).
