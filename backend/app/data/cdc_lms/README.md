# CDC LMS Growth Reference Data (vendored)

These CSV files are the official **CDC growth-chart LMS parameters** used to compute
age/sex z-scores and percentiles for height, BMI, and weight. They are vendored
(committed to the repo) so that seeding the `growth_reference_lms` table is
**deterministic and offline** — no network call to `cdc.gov` at deploy time
(Render free tier, cold start).

| File             | Indicator         | Source URL |
|------------------|-------------------|------------|
| `statage.csv`    | `height_for_age`  | https://www.cdc.gov/growthcharts/data/zscore/statage.csv |
| `bmiagerev.csv`  | `bmi_for_age`     | https://www.cdc.gov/growthcharts/data/zscore/bmiagerev.csv |
| `wtage.csv`      | `weight_for_age`  | https://www.cdc.gov/growthcharts/data/zscore/wtage.csv |

## Columns

Each CSV has a header row. Only `Sex` (1=male, 2=female), `Agemos` (age in months),
and `L`, `M`, `S` are consumed by `app/seed_growth_data.py`. The remaining `P*`
percentile columns are ignored (we recompute them from L/M/S).

## Privacy

**These files contain ONLY population reference constants** (the L/M/S parameters of
the Cole & Green LMS distribution by age and sex). They contain **no athlete data**,
no minor data, and no personally identifiable information of any kind. They are
public domain U.S. government data.

## Refreshing

To re-vendor from the upstream source (rare — CDC reference charts are stable):

```sh
cd backend/app/data/cdc_lms
for f in statage bmiagerev wtage; do
  curl -fsSL -o "$f.csv" "https://www.cdc.gov/growthcharts/data/zscore/$f.csv"
done
```

Then re-run the offline seed (`python -m app.seed_growth_data`) to upsert any changes.
