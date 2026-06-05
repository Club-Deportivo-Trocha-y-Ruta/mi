# Research: Growth Percentiles for Youth Athletes Ages 10-19

**Date:** 2026-04-14
**Depth:** deep
**Sources consulted:** 12+

## Executive Summary

Colombia officially adopts the WHO 2006-2007 growth patterns (Resolution 2465/2016 from MinSalud). For the **5 to 17 age group**, two main indicators are used: **Height-for-Age (H/A)** and **BMI-for-Age (BMI/A)**. Data with LMS parameters is freely available from both the WHO and CDC, enabling exact percentile calculation for each athlete and plotting reference curves.

---

## 1. Colombian Regulatory Framework

### Resolution 2465 of 2016 — MinSalud

**Article 1:** Adopts the WHO 2006-2007 growth patterns for children under 18 years of age.

**Indicators for ages 5-17 (Table No. 3):**

| Indicator | Cut-off point (Z-score) | Classification |
|-----------|--------------------------|----------------|
| **Height/Age (H/A)** | Z >= -1 | Height adequate for age |
| | -2 <= Z < -1 | Risk of height delay |
| | Z < -2 | Low height / Height delay |
| **BMI/Age (BMI/A)** | Z > +2 | Obesity |
| | +1 < Z <= +2 | Overweight |
| | -1 <= Z <= +1 | BMI adequate for age |
| | -2 <= Z < -1 | Risk of thinness |
| | Z < -2 | Thinness |

> **Note:** For ages 5-17 Weight/Height (W/H) is NOT used. BMI/A is used as the tracking indicator.
> At age 19, +1 SD is equivalent to BMI 25 kg/m2 and +2 SD to BMI 30 kg/m2.

### Z-score <-> Percentile Equivalences

| Z-score | Percentile | | Percentile | Z-score |
|---------|-----------|---|-----------|---------|
| -3 | 0.1 | | 3 | -1.88 |
| -2 | 2.3 | | 10 | -1.29 |
| -1 | 15.8 | | 25 | -0.67 |
| 0 | 50.0 | | 50 | 0.00 |
| +1 | 84.2 | | 75 | +0.67 |
| +2 | 97.7 | | 90 | +1.29 |
| +3 | 99.9 | | 97 | +1.88 |

---

## 2. Data Sources

### 2.1 WHO — Growth Reference 5-19 Years

- **Base URL:** https://www.who.int/tools/growth-reference-data-for-5to19-years/indicators
- **Available indicators:**
  - Height for Age (5-19 years) — both sexes
  - BMI for Age (5-19 years) — both sexes
  - Weight for Age (5-10 years ONLY)
- **Format:** PDF (charts, tables) + XLSX (expanded tables with LMS and percentiles)
- **Temporal resolution:** Data by age in months
- **Recommendation for Colombia:** This is the official standard. USE THIS.

### 2.2 CDC — Growth Charts (2-20 Years)

- **Data URL:** https://www.cdc.gov/growthcharts/cdc-data-files.htm
- **CSV files downloaded and verified:**
  - `statage.csv` — Height for age (2-20 years)
  - `wtage.csv` — Weight for age (2-20 years)
  - `bmiagerev.csv` — BMI for age (2-20 years)
- **Format:** CSV with columns: Sex, Agemos, L, M, S, P3, P5, P10, P25, P50, P75, [P85], P90, P95, P97
- **Temporal resolution:** Every 0.5 months (very granular)
- **Advantage over WHO:** Has Weight for Age up to 20 years (WHO only up to 10)

### 2.3 Recommendation: Which to Use?

| Criterion | WHO | CDC |
|----------|-----|-----|
| Official Colombia standard | YES | No |
| Height/Age 10-19 | YES | YES |
| BMI/Age 10-19 | YES | YES |
| Weight/Age 10-19 | NO (only up to 10) | YES (up to 20) |
| Granularity | Monthly | Every 0.5 months |
| Data format | XLSX | CSV |

**Recommendation:** Use **WHO as primary** (meets Colombian regulations) and **CDC as supplementary** for Weight/Age in children over 10 years.

---

## 3. Percentile Tables — CDC Data (Ages 10-19)

### 3.1 Height (cm) for Age — Boys (Male Sex)

| Age | P3 | P10 | P25 | P50 | P75 | P90 | P97 |
|-----|-----|------|------|------|------|------|------|
| 10 | 126.7 | 130.5 | 134.4 | 138.8 | 143.3 | 147.4 | 151.5 |
| 11 | 130.8 | 134.9 | 139.0 | 143.7 | 148.5 | 152.9 | 157.3 |
| 12 | 135.7 | 139.9 | 144.3 | 149.3 | 154.4 | 159.0 | 163.7 |
| 13 | 141.7 | 146.4 | 151.1 | 156.4 | 161.7 | 166.6 | 171.3 |
| 14 | 148.5 | 153.6 | 158.7 | 164.1 | 169.5 | 174.2 | 178.8 |
| 15 | 154.6 | 159.8 | 164.8 | 170.1 | 175.3 | 179.8 | 184.1 |
| 16 | 158.8 | 163.7 | 168.5 | 173.6 | 178.6 | 182.9 | 187.1 |
| 17 | 161.3 | 165.8 | 170.4 | 175.3 | 180.2 | 184.5 | 188.6 |
| 18 | 162.5 | 166.9 | 171.3 | 176.2 | 181.0 | 185.3 | 189.5 |
| 19 | 163.1 | 167.4 | 171.8 | 176.6 | 181.4 | 185.7 | 189.9 |

### 3.2 Height (cm) for Age — Girls (Female Sex)

| Age | P3 | P10 | P25 | P50 | P75 | P90 | P97 |
|-----|-----|------|------|------|------|------|------|
| 10 | 126.0 | 129.8 | 133.7 | 138.2 | 142.8 | 147.0 | 151.3 |
| 11 | 130.7 | 135.0 | 139.4 | 144.3 | 149.2 | 153.7 | 158.1 |
| 12 | 137.4 | 142.0 | 146.5 | 151.5 | 156.4 | 160.8 | 165.2 |
| 13 | 144.2 | 148.4 | 152.7 | 157.3 | 162.0 | 166.1 | 170.2 |
| 14 | 148.1 | 152.1 | 156.0 | 160.5 | 164.9 | 168.9 | 172.9 |
| 15 | 149.7 | 153.6 | 157.5 | 161.9 | 166.3 | 170.2 | 174.2 |
| 16 | 150.4 | 154.3 | 158.2 | 162.6 | 166.9 | 170.9 | 174.8 |
| 17 | 150.7 | 154.6 | 158.6 | 162.9 | 167.3 | 171.2 | 175.1 |
| 18 | 150.9 | 154.8 | 158.8 | 163.1 | 167.5 | 171.4 | 175.3 |
| 19 | 151.0 | 154.9 | 158.9 | 163.3 | 167.6 | 171.5 | 175.4 |

### 3.3 Weight (kg) for Age — Boys

| Age | P3 | P10 | P25 | P50 | P75 | P90 | P97 |
|-----|-----|------|------|------|------|------|------|
| 10 | 24.2 | 26.2 | 28.7 | 32.1 | 36.6 | 42.0 | 49.4 |
| 11 | 26.6 | 29.0 | 32.0 | 36.1 | 41.4 | 47.7 | 56.3 |
| 12 | 29.5 | 32.4 | 35.9 | 40.7 | 46.8 | 54.0 | 63.3 |
| 13 | 33.0 | 36.3 | 40.4 | 45.8 | 52.7 | 60.4 | 70.3 |
| 14 | 37.1 | 40.8 | 45.3 | 51.2 | 58.6 | 66.8 | 77.0 |
| 15 | 41.5 | 45.5 | 50.2 | 56.5 | 64.2 | 72.8 | 83.2 |
| 16 | 45.8 | 49.8 | 54.7 | 61.1 | 69.0 | 77.9 | 89.0 |
| 17 | 49.3 | 53.3 | 58.2 | 64.7 | 72.8 | 82.1 | 93.8 |
| 18 | 51.7 | 55.8 | 60.7 | 67.3 | 75.6 | 85.1 | 97.2 |
| 19 | 53.2 | 57.4 | 62.5 | 69.2 | 77.6 | 87.1 | 99.2 |

### 3.4 Weight (kg) for Age — Girls

| Age | P3 | P10 | P25 | P50 | P75 | P90 | P97 |
|-----|-----|------|------|------|------|------|------|
| 10 | 24.0 | 26.3 | 29.2 | 33.1 | 38.0 | 43.9 | 51.4 |
| 11 | 26.8 | 29.5 | 32.9 | 37.4 | 43.2 | 49.9 | 58.7 |
| 12 | 30.0 | 33.1 | 36.7 | 41.8 | 48.3 | 56.0 | 65.9 |
| 13 | 33.4 | 36.6 | 40.6 | 46.0 | 53.0 | 61.3 | 72.4 |
| 14 | 36.7 | 40.0 | 43.9 | 49.5 | 56.8 | 65.6 | 77.7 |
| 15 | 39.6 | 42.8 | 46.7 | 52.1 | 59.4 | 68.5 | 81.6 |
| 16 | 41.8 | 44.9 | 48.6 | 53.9 | 61.2 | 70.4 | 84.4 |
| 17 | 43.3 | 46.3 | 50.0 | 55.2 | 62.3 | 71.6 | 86.2 |
| 18 | 44.2 | 47.2 | 51.0 | 56.2 | 63.4 | 72.8 | 87.4 |
| 19 | 44.8 | 48.0 | 51.8 | 57.4 | 64.8 | 74.2 | 88.4 |

### 3.5 BMI (kg/m2) for Age — Boys

| Age | P3 | P10 | P25 | P50 | P75 | P85 | P90 | P95 | P97 |
|-----|-----|------|------|------|------|------|------|------|------|
| 10 | 14.0 | 14.6 | 15.5 | 16.6 | 18.2 | 19.4 | 20.3 | 22.2 | 23.7 |
| 11 | 14.3 | 15.0 | 15.9 | 17.2 | 18.9 | 20.2 | 21.2 | 23.2 | 24.9 |
| 12 | 14.7 | 15.5 | 16.4 | 17.8 | 19.7 | 21.0 | 22.1 | 24.2 | 26.0 |
| 13 | 15.1 | 16.0 | 17.0 | 18.5 | 20.4 | 21.9 | 23.0 | 25.2 | 27.0 |
| 14 | 15.7 | 16.5 | 17.6 | 19.2 | 21.2 | 22.7 | 23.8 | 26.0 | 27.9 |
| 15 | 16.2 | 17.1 | 18.3 | 19.9 | 22.0 | 23.5 | 24.6 | 26.8 | 28.6 |
| 16 | 16.8 | 17.7 | 18.9 | 20.6 | 22.7 | 24.2 | 25.4 | 27.6 | 29.3 |
| 17 | 17.3 | 18.3 | 19.6 | 21.2 | 23.4 | 24.9 | 26.1 | 28.3 | 29.9 |
| 18 | 17.9 | 18.9 | 20.2 | 21.9 | 24.1 | 25.7 | 26.9 | 29.0 | 30.6 |
| 19 | 18.3 | 19.4 | 20.7 | 22.5 | 24.8 | 26.4 | 27.6 | 29.7 | 31.4 |

### 3.6 BMI (kg/m2) for Age — Girls

| Age | P3 | P10 | P25 | P50 | P75 | P85 | P90 | P95 | P97 |
|-----|-----|------|------|------|------|------|------|------|------|
| 10 | 13.7 | 14.5 | 15.5 | 16.9 | 18.7 | 20.0 | 21.0 | 23.0 | 24.6 |
| 11 | 14.1 | 14.9 | 16.0 | 17.5 | 19.5 | 20.9 | 22.0 | 24.1 | 25.9 |
| 12 | 14.5 | 15.4 | 16.5 | 18.1 | 20.2 | 21.7 | 23.0 | 25.3 | 27.2 |
| 13 | 15.0 | 15.9 | 17.1 | 18.7 | 21.0 | 22.6 | 23.9 | 26.3 | 28.3 |
| 14 | 15.4 | 16.4 | 17.6 | 19.4 | 21.7 | 23.3 | 24.7 | 27.3 | 29.4 |
| 15 | 15.9 | 16.9 | 18.2 | 19.9 | 22.3 | 24.0 | 25.5 | 28.1 | 30.4 |
| 16 | 16.4 | 17.4 | 18.7 | 20.5 | 22.9 | 24.7 | 26.1 | 28.9 | 31.3 |
| 17 | 16.8 | 17.8 | 19.1 | 20.9 | 23.4 | 25.2 | 26.7 | 29.6 | 32.2 |
| 18 | 17.2 | 18.2 | 19.5 | 21.3 | 23.8 | 25.7 | 27.3 | 30.3 | 33.1 |
| 19 | 17.4 | 18.4 | 19.7 | 21.6 | 24.2 | 26.1 | 27.8 | 31.0 | 34.0 |

---

## 4. Programmatic Percentile Calculation (LMS Method)

### 4.1 Z-score Formula

Given a measured value (e.g., height = 145 cm), and the L, M, S parameters for that age and sex:

```
When L != 0:
  Z = ((value / M)^L - 1) / (L * S)

When L == 0:
  Z = ln(value / M) / S
```

### 4.2 Inverse Formula (percentile -> value)

```
When L != 0:
  value = M * (1 + L * S * Z)^(1/L)

When L == 0:
  value = M * exp(S * Z)
```

### 4.3 Z-score to Percentile

```python
from scipy.stats import norm
percentile = norm.cdf(z_score) * 100
```

### 4.4 Example LMS Parameters (CDC, Height, Boys)

| Age (months) | L | M | S |
|--------------|------|--------|--------|
| 120.5 (10y) | 0.5056 | 138.82 | 0.0476 |
| 132.5 (11y) | 0.4879 | 143.73 | 0.0489 |
| 144.5 (12y) | 0.4471 | 149.30 | 0.0504 |
| 156.5 (13y) | 0.3973 | 156.41 | 0.0510 |
| 168.5 (14y) | 0.3581 | 164.14 | 0.0494 |
| 180.5 (15y) | 0.3409 | 170.10 | 0.0462 |

### 4.5 Correction for Extreme Values (|Z| > 3)

The WHO limits the Box-Cox distribution to the interval z = [-3, +3]. Beyond this range, the standard deviation is fixed as the difference between z=3 and z=2 (upper extreme) or z=-3 and z=-2 (lower extreme).

### 4.6 Available Python Libraries

#### Option A: Custom Implementation (recommended for this project)

Using `scipy.stats.norm` and LMS data in a table (JSON or DB):

```python
import math
from scipy.stats import norm

def calculate_z_score(value: float, L: float, M: float, S: float) -> float:
    """Calculates Z-score using LMS method."""
    if abs(L) < 1e-6:  # L approximately 0
        return math.log(value / M) / S
    return ((value / M) ** L - 1) / (L * S)

def z_to_percentile(z: float) -> float:
    """Converts Z-score to percentile."""
    return round(norm.cdf(z) * 100, 1)

def percentile_value(z: float, L: float, M: float, S: float) -> float:
    """Calculates the value corresponding to a given Z-score."""
    if abs(L) < 1e-6:
        return M * math.exp(S * z)
    return M * (1 + L * S * z) ** (1 / L)
```

#### Option B: pygrowup (existing library)

- **Installation:** `pip install pygrowup`
- **GitHub:** https://github.com/ewheeler/pygrowup
- **Indicators:** `lhfa()` (height-for-age), `wfa()` (weight-for-age), `bfa()` (bmi-for-age)
- **Returns:** z-score, convertible to percentile with `scipy.stats.norm.cdf()`
- Parameter `include_cdc=True` enables CDC reference

#### Option C: R package anthroplus (official WHO reference)

- **Official WHO GitHub:** https://github.com/WorldHealthOrganization/anthroplus
- **CRAN:** `install.packages("anthroplus")`
- Contains the original WHO LMS tables in `/data-raw`
- Useful for extracting LMS data and porting them to Python/JSON

---

## 5. Current Project Status (Code Exploration)

### What ALREADY exists:
- Table `anthropometric_records` with: weight_kg, standing_height_cm, sitting_height_cm, arm_span_cm
- Calculated fields: leg_length_cm, maturity_offset, age_at_phv, maturation_status
- Validated PHV Mirwald service (`services/phv.py`)
- POST/GET endpoints for anthropometric records
- Longitudinal history per athlete

### What does NOT exist (critical gap):
- No reference to WHO/CDC tables
- No z-score or percentile calculation
- No percentile storage in DB
- No longitudinal growth trajectory analysis
- No graphical visualization of growth curves
- No perimeters or skinfold measurements

---

## 6. Interpretation for Youth Athletes (XCO Cycling)

### 6.1 Special Considerations

1. **Reference percentiles are population-based** — trained athletes may differ from P50 without that being pathological.
2. **BMI in athletes overestimates adiposity** — up to 62% of adolescents classified as "obese" by BMI are false positives when measured with skinfolds (PMC 2012). In XCO cyclists this is less common (endurance sport), but should be considered.
3. **Growth velocity is more important than the static point** — an athlete at P25 who stays in their channel is normal; one at P50 who drops to P10 needs evaluation. Crossing two or more percentile lines rapidly is a sign of a growth spurt, not necessarily a problem.
4. **Relationship with PHV:** Height percentiles show "where they are" but PHV (already implemented in the system) shows "how fast they are growing". Together they provide a complete picture.
5. **Weight-for-age unusable > 10 years:** From age 10 onward, weight does not discriminate between tall-normal-weight and normal height-overweight. Use only BMI/Age and H/Age.
6. **Biological age vs. chronological age:** A 12-year-old chronological athlete who is Post-PHV is better compared with the 14-year-old curve. Percentiles complement maturation status, not replace it.
7. **Valle del Cauca population:** The significant Afro-descendant component of Valle del Cauca (chronic malnutrition prevalence of 13.9% vs. 10.8% national) reinforces that WHO tables are an appropriate normative aspiration for evaluating growth potential.

### 6.2 Suggested Visualization Zones for Charts

| Zone | Suggested color | Z range | Percentile range | Meaning |
|------|-----------------|---------|-----------------|---------|
| Red alert | Light red | < -2 or > +2 | < P2.3 or > P97.7 | Requires medical evaluation |
| Caution | Yellow | -2 to -1 or +1 to +2 | P2.3-P15.8 or P84.2-P97.7 | Close monitoring |
| Normal | Light green | -1 to +1 | P15.8 to P84.2 | Expected range |
| Median | Green line | 0 | P50 | Central reference |

### 6.3 What to Show on the Athlete's Chart

On the athlete's height or weight charts over time, overlay:
- **P50 line** (median) as central reference
- **P25-P75 band** (green zone) as "typical" range
- **P3-P97 band** (yellow zone) as normal limits
- **Athlete's point** highlighted with their exact percentile calculated via LMS
- **Colombian regulatory reference lines:** Z=-2, Z=-1, Z=+1, Z=+2

---

## 7. Data Available for Implementation

### CDC CSV Files (already downloaded and verified)

The three files contain complete data with the structure:
```
Sex,Agemos,L,M,S,P3,P5,P10,P25,P50,P75,[P85],P90,P95,P97
```

- **statage.csv** — Height for age (24-240.5 months, both sexes)
- **bmiagerev.csv** — BMI for age (24-240.5 months, both sexes)
- **wtage.csv** — Weight for age (24-240 months, both sexes)

Total: ~218 records per sex per indicator (every 0.5 months from 120 to 228.5 = 109 points for the 10-19 age range)

### For backend implementation

Options:
1. **Table in DB** (`growth_reference_lms`) with columns: source, indicator, sex, age_months, L, M, S — then calculate percentiles on the fly
2. **Static JSON file** served by the frontend — lower DB load
3. **Both:** JSON for plotting curves + backend service to calculate the athlete's exact percentile

---

## 8. Sources

1. [WHO — Growth Reference 5-19 years](https://www.who.int/tools/growth-reference-data-for-5to19-years/indicators) — Official reference
2. [WHO — Application Tools (AnthroPlus)](https://www.who.int/tools/growth-reference-data-for-5to19-years/application-tools) — Software and data
3. [CDC — Growth Charts Data Files](https://www.cdc.gov/growthcharts/cdc-data-files.htm) — CSV data with LMS
4. [Resolution 2465 of 2016 — MinSalud Colombia](https://www.icbf.gov.co/sites/default/files/resolucion_no._2465_del_14_de_junio_de_2016.pdf) — Colombian regulations
5. [ConsultorSalud — Resolution 2465 Summary](https://consultorsalud.com/nuevos-indicadores-antropometricos-del-estado-nutricional-resolucion-2465-de-2016/)
6. [Centro Sequoia — Growth Charts](https://centrosequoia.com.mx/aprende-del-crecimiento-infantil/graficas-de-crecimiento/) — Visual reference
7. [PMC — Development of WHO Growth Reference 2007](https://pmc.ncbi.nlm.nih.gov/articles/PMC2636412/) — Scientific article
8. [Duran et al. 2016 — Colombian curves](https://onlinelibrary.wiley.com/doi/10.1111/apa.13269) — Acta Paediatrica (n=27,209)
9. [PMC — Height in Colombia 60-year review](https://pmc.ncbi.nlm.nih.gov/articles/PMC8392461/) — Valle del Cauca data
10. [PMC — BMI vs fat in adolescent athletes](https://pmc.ncbi.nlm.nih.gov/articles/PMC3445161/) — BMI false positives
11. [WHO anthroplus R package (official GitHub)](https://github.com/WorldHealthOrganization/anthroplus) — Original LMS data
12. [pygrowup (PyPI)](https://pypi.org/project/pygrowup/) — Python library for calculation
13. [Professional health guide for WHO curves](https://pmc.ncbi.nlm.nih.gov/articles/PMC2865941/) — PMC

## 9. Next Step Recommendations

| After this... | Use | For |
|--------------------|------|------|
| Design the DB table | `/sc:design` | Schema `growth_reference_lms` |
| Implement service | `/sc:implement` | Percentile calculation service |
| Design chart component | `/sc:design` | React component with percentile curves |
| Validate data | `/sc:test` | Unit tests for LMS calculation |
