# Skinfold-based body composition: research protocol

**Status:** research only — not yet specified/implemented. **Audience:** engineering + coaching staff. **Scope:** whether/how to add skinfold-derived body composition to the anthropometry module (`backend/app/models/anthropometry.py`, `app/services/growth.py`, `app/services/measurement_alerts.py`, `app/services/ai/anthro/context.py`) for Club Deportivo Trocha y Ruta, ~20 XCO athletes aged 9–15, mixed sex, Valle del Cauca, Colombia. Measurer: the coach or a club volunteer, **not ISAK-certified**. This is a wellbeing/monitoring tool for minors, never a diagnostic instrument — it extends the spirit of the project constitution's Principle V (wellbeing not diagnosis, baseline-anchored interpretation, mastery climate, human-in-the-loop, referral on persistence) from psychological assessment to body composition.

Where a claim below could not be independently verified against a primary source in this research pass, it is flagged **[unverified]**.

---

## 1. Which sites and why

ISAK's full profile uses 8 standard sites: triceps, biceps, subscapular, iliac crest, supraspinale, abdominal, front (anterior) thigh, medial calf (Ackland et al., 2012; Marfell-Jones et al. ISAK manual, cited throughout the secondary literature as "Standards for Anthropometry Assessment"). For a non-certified measurer working with minors, accessibility (no torso/abdomen exposure beyond the back), novice reliability, and evidence-base compatibility matter as much as anatomical completeness.

| Site | Body area | Undressing needed | Novice reliability | Scientific payoff | Recommendation |
|---|---|---|---|---|---|
| **Triceps** | Upper arm, posterior | None | Good — the classic pediatric site | Core input to Slaughter–Lohman equations and to Addo & Himes (2010) / Bogotá reference percentiles | **Core** |
| **Biceps** | Upper arm, anterior | None | Good | Adds a Σ4 without extra exposure; near-zero marginal burden next to triceps | **Core** |
| **Subscapular** | Upper back, below scapula | Shirt hem lifted at the back only (front stays covered) | Moderate | The other half of the two most-validated pediatric equations (Slaughter triceps+subscapular) and of Addo & Himes / Bogotá FUPRECOL reference data | **Core** |
| **Medial calf** | Lower leg | None (shorts/cycling kit already expose it) | Good | Enables the Slaughter triceps+calf equation (cross-check against triceps+subscapular); mechanically relevant muscle group for cyclists | **Core** |
| **Iliac crest** | Waistline/hip | Waistband eased down slightly | Flagged as one of the two hardest sites for novices to landmark correctly [unverified: exact study, see §2] | Needed for Σ6/Σ8 comparability with sport-science literature (e.g. youth XCO cyclist studies) | **Optional**, only after demonstrated measurer reliability (§6) |
| **Supraspinale** | Just above iliac crest, anterior axillary line | Same as iliac crest | Similar concerns to iliac crest | Same Σ6/Σ8 comparability benefit | **Optional**, same conditions |
| **Abdominal** | Beside the umbilicus | Front abdomen exposed | Flagged as one of the two hardest sites for novices | Not required by any equation recommended here | **Excluded** for this context |
| **Front thigh** | Anterior thigh | Shorts raised / cycling-short line | Notoriously difficult even for experts on lean, muscular legs (high tissue tension) | Not required by any equation recommended here | **Excluded** for this context |

**Recommended core set (Σ4): triceps + biceps + subscapular + medial calf.** This is the minimum set that (a) computes both Slaughter–Lohman formulas, (b) matches the two largest pediatric skinfold reference datasets found (Addo & Himes 2010; Bogotá FUPRECOL), and (c) avoids the two sites flagged as hardest for novices and the two sites with the most dignity exposure (abdominal, front thigh).

**Exact ISAK-style landmark descriptions (right side of the body by convention, for comparability across time and with reference populations — not because the right side is inherently more accurate):**

- **Triceps** — posterior midline of the upper arm, midway between the acromion process and the olecranon process, located with the elbow flexed 90° and marked, then measured with the arm relaxed at the side. Fold is **vertical**, parallel to the arm's long axis.
- **Biceps** — anterior midline of the upper arm, at the same horizontal level as the triceps mark, arm relaxed at the side. Fold is **vertical**.
- **Subscapular** — at the inferior angle of the scapula, located by palpation (arm may be drawn gently behind the back to expose the angle, then returned to a relaxed position for the actual pinch). Fold runs **diagonally**, infero-laterally, following the natural skin cleavage line (~45° downward-outward).
- **Medial calf** — athlete seated or standing with the foot on a raised support, knee flexed 90°, calf relaxed (not flexed). Landmark is the point of maximum calf girth on the medial border. Fold is **vertical**, parallel to the tibia.
- **Iliac crest** (optional) — at the iliocristale, the most lateral point of the iliac crest on the midaxillary line, located by palpating the crest from front to back. Fold runs **diagonally forward-downward** (~45°), following the natural fold direction at that point; arm abducted or across the chest for access.
- **Supraspinale** (optional) — at the intersection of the line from the iliospinale (anterior superior iliac spine) to the anterior axillary border, at the level of the superior border of the iliac crest — just above and medial to the ASIS. Fold runs **obliquely, medially-downward** toward the groin.

**Uncertain:** these descriptions are consistent across several secondary sources that cite the ISAK manual (Marfell-Jones et al.), but the official ISAK manual itself is a restricted/paid publication and was not directly accessible in this research pass — validate against an ISAK Level 1 course or manual before treating these as final SOP.

---

## 2. Measurement technique for a novice

**Pre-conditions:** not immediately post-exercise (fluid shifts increase compressibility and change readings) — the club's plan to measure **before training** is correct; dry skin, no lotion/sunscreen; consistent time of day if possible; right side of the body; the muscle at the site relaxed, not flexed.

**Pinch technique:**
1. Grasp a full double-fold of skin + subcutaneous tissue (not muscle) firmly with thumb and index finger at the marked site, pulling it away from the underlying muscle.
2. Apply the caliper jaws perpendicular to the fold, at the marked point, with the jaw head placed **about 1 cm away from the fingers** (this specific "1 cm" convention is widely cited in ISAK-derived sources but was not independently confirmed against the official ISAK manual **[unverified]** — the NHANES protocol, a separate but comparable standard, specifies 2 cm instead. Pick one distance and keep it constant for the whole club).
3. Release full caliper pressure onto the fold (not gradually).
4. Read the dial/display at **about 2 seconds** after full pressure is applied — commonly cited as "the third second" after closure. Reading later systematically under-reads because tissue keeps compressing under sustained pressure.
5. Release the caliper, then release the pinch.

**Number of readings:** take 2 measurements per site in **rotational order** (measure every site once in a fixed sequence, then repeat the whole sequence for the second reading), never twice in immediate succession at the same site — an immediate repeat lets the tissue "remember" the first compression and falsely inflates agreement. If the two readings agree within about 5%, record the mean; if they differ by more than ~5%, take a third (also non-consecutive) and use the **median of the three**. These specific tolerances are the ISAK-cited standard found in multiple secondary sources (see §6 for the same 5%/7.5% figures applied to aggregate reliability).

**Caliper calibration / jaw-pressure check:** ISAK-spec calipers should exert a constant ~10 g/mm² across the jaw-opening range. For a basic plastic caliper without professional servicing, at minimum: (a) verify the dial reads exactly 0.0 mm with jaws fully closed before each session; (b) check the spring tension feels consistent (no binding/wobble) across the range; (c) if available, measure a fixed-thickness reference block (a folded rubber block or similar) at the start of every session and log the reading, to catch spring drift over months. This DIY routine is a **practical adaptation, not an ISAK-validated protocol in itself** — flagged as the club's own pragmatic substitute for professional caliper certification.

**Hygiene:** wipe caliper jaws between athletes; measurer sanitizes hands before each athlete.

**Training reality check:** a single exposure to skinfold technique is documented as inadequate — one training-effect study found that ~5 hours of supervised practice plus ~25 hours of practice time were needed to materially improve reliability, and a separate reliability study found untrained/novice measurers overestimated body fat in 55% of cases with technical error of measurement (TEM) 2–4× higher than an expert's. **Practical implication: the coach/volunteer should self-calibrate before trusting any single number** — see the worked example in §6.

---

## 3. Which equations are valid for ages 9–15

### Slaughter–Lohman (1988) — the only child/adolescent-specific equations recommended here

Derived on 310 subjects aged 8–29 with maturation assessed by secondary sex characteristics (Tanner-based, not Mirwald offset).

**Triceps + subscapular (Σ2 ≤ 35 mm):**

| Sex | Maturation | Equation |
|---|---|---|
| Boys | Prepubescent, White | %BF = 1.21·Σ2 − 0.008·Σ2² − 1.7 |
| Boys | Prepubescent, Black | %BF = 1.21·Σ2 − 0.008·Σ2² − 3.2 |
| Boys | Pubescent, White | %BF = 1.21·Σ2 − 0.008·Σ2² − 3.4 |
| Boys | Pubescent, Black | %BF = 1.21·Σ2 − 0.008·Σ2² − 5.2 |
| Boys | Postpubescent, White | %BF = 1.21·Σ2 − 0.008·Σ2² − 5.5 |
| Boys | Postpubescent, Black | %BF = 1.21·Σ2 − 0.008·Σ2² − 6.8 |
| Girls | Any maturation | %BF = 1.33·Σ2 − 0.013·Σ2² − 2.5 |

**Triceps + subscapular (Σ2 > 35 mm):** Boys: %BF = 0.783·Σ2 + 1.6. Girls: %BF = 0.546·Σ2 + 9.7.

**Triceps + calf (generalized, no maturation/race split, ages 6–17):** Boys: %BF = 0.735·Σ2 + 1.0. Girls: %BF = 0.610·Σ2 + 5.0.

**Critical caveat on the race-based intercepts:** the White/Black split reflects the binary racial categorization of the original 1988 US sample and has no validated mapping onto Colombia's Afro-Colombian/mestizo/mixed-ancestry population. **Do not** attempt to pick a race intercept for a Colombian child — there is no scientific basis for the choice in this population. Prefer the triceps+calf generalized equation (no race term at all) as the default, and treat the triceps+subscapular equation, if used, as a single rough estimate rather than choosing a specific race branch.

**Mapping maturation to the club's existing Mirwald status:** Slaughter's categories are Tanner-based; the club only has Mirwald `maturation_status`. The pragmatic mapping — **Pre-PHV → prepubescent, Circa-PHV → pubescent, Post-PHV → postpubescent** — is a reasonable proxy but **not a peer-reviewed validated crosswalk [unverified]**; treat the resulting %BF as a wider-error estimate, appropriate for trend monitoring, never for a precise one-time figure. Girls need no such mapping (single equation).

**Colombian validation — important, working against naive use of %BF:** a DXA-validation study in Colombian children/adolescents with excess adiposity (n=127, 70% girls, ages 11–17, DXA-measured body fat >30%) found the Slaughter equations had **poor concordance with DXA** (ρc < 0.5 both sexes) and **systematically underestimated** body fat by 9.0 percentage points in boys (95% CI −3.2–21.3) and 11.1 points in girls (95% CI 3.9–18.3), concluding the equations "are not interchangeable methods for assessing BF% in Latin American children and adolescents with excess of adiposity" (González-Ruíz et al., 2018, PMC6115719). This sample was obesity-referred (higher adiposity than Slaughter's derivation cohort), so bias for the club's likely leaner, active XCO athletes should be smaller — but it is a direct, local demonstration that these equations degrade exactly where precision matters most, and is the strongest argument for §4's recommendation.

### Why NOT Durnin–Womersley, Jackson–Pollock, Faulkner, or Yuhasz

All four were derived and validated on **adult** samples and rely on the Siri/Brozek two-compartment density-to-%BF conversion, which assumes an adult, fixed fat-free-mass (FFM) density (~1.1 g/cm³) and fixed hydration (~73.2%). Children's FFM has higher water content and lower mineral density, especially pre- and peri-puberty, so applying an adult density constant systematically distorts the result — precisely the problem Slaughter et al. (1988) built child-specific equations to fix.

### Fat-free mass and error propagation

FFM = weight × (1 − %BF/100). Any error in %BF scales directly with body weight. Using Slaughter's own cross-validation error (~3.5–4 percentage-point SEE under favorable, lean conditions) as an input: for a 40 kg athlete, a ±4-point %BF error alone produces roughly **±1.6 kg of FFM uncertainty** — and using the Colombian study's 9–11 point bias for higher-adiposity cases, the error could exceed **±4 kg**, larger than many real 6-month changes (see §6). *This calculation is this document's own propagation exercise, not a published figure — flagged as illustrative.* It is the central reason §4 recommends never reporting a bare %BF/FFM number without an uncertainty caveat.

### Density-based two-compartment models — do not build these manually

Lohman's age-adjusted Siri constants (age/maturation-specific FFM density and hydration, rather than fixed adult values) reduce, but do not eliminate, bias against 4-compartment criterion models in peripubertal children. Slaughter's equations already incorporate this age-adjustment internally — there is no reason for the club to separately compute body density and apply a Siri/Brozek conversion by hand; doing so would just reintroduce the adult-assumption problem this whole section exists to avoid.

---

## 4. Sum of skinfolds as the primary longitudinal metric

Two independent bodies of guidance converge on the same recommendation, and the Colombian validation study in §3 gives it local teeth:

- **Kasper et al. (2021)**, *"Come Back Skinfolds, All Is Forgiven"* (Nutrients 13(4):1075): recommends **against** converting skinfold thickness to %BF for tracking, favoring the raw **ISAK sum of 8 sites** as more accurate and reliable, and notes skinfolds show the least day-to-day variability of common field methods.
- **Ackland et al. (2012)**, IOC position statement (Sports Medicine 42(3):227–49): frames sums of skinfolds (Σ7/Σ8) as the primary tracking tool in athlete monitoring, with %BF conversion equations understood as population-average estimators, not instruments built to detect one athlete's small individual change.

**Recommendation for the club:**
- **Primary, graphed, longitudinal metric: Σ4 (triceps + biceps + subscapular + medial calf), raw millimeters**, plotted over time exactly like the existing height/weight series.
- **%BF/FFM (Slaughter): secondary, coach-only, clearly labeled "estimate."** Useful for one-time orientation and for the "how much of this weight gain is fat vs. lean" question the motivating case raises — never the headline number.
- **Never show %BF or FFM to the athlete or in any parent-facing screen.** This directly extends the club's existing "no calorie counting with athletes" rule and the constitution's Principle V mastery-climate spirit: a body-fat percentage shown to an adolescent is a well-documented body-image risk, not a data-visualization luxury. Coach-only, same restriction pattern already used for other sensitive derived fields.
- **Never a %BF or Σ-skinfolds target/goal.** Track direction and magnitude of change only.

---

## 5. Reference values / percentiles

| Source | Population | Indicator | Status |
|---|---|---|---|
| **Addo & Himes (2010)**, AJCN 91(3):635–642, doi:10.3945/ajcn.2009.28385 | US children/adolescents, n=32,783, ~1.5–19.9y (age bounds as reported by the requester; not independently re-verified here) | Triceps & subscapular LMS percentile curves | Widely cited standard. **Supplementary LMS table download not confirmed** — the AJCN article page returned a 403 (subscription-gated) in this pass, and no public supplementary-data URL was located by search. Treat as **unresolved**; a follow-up attempt via institutional access or direct author contact is needed before assuming it is seedable like the WHO/CDC height-weight-BMI tables already in `growth_reference_lms`. |
| **Frisancho (1990 / 2008)**, *Anthropometric Standards for the Assessment of Growth and Nutritional Status*, Univ. of Michigan Press | US NHANES-derived, broad skinfold-site coverage | Multiple skinfold percentiles | Commercial book (not a free download); a lending scan exists at archive.org. Not a ready machine-readable table. |
| **CDC NHANES III** | US | Raw skinfold data (triceps, subscapular, others in some cycles) | Public microdata exists but is **not** pre-packaged as an LMS/percentile table the way the growth charts are — replicating Addo & Himes' methodology from raw NHANES III would be a non-trivial independent analysis, not a drop-in seed. |
| **Spanish AVENA / Moreno group** | Spain, ages ~13–18.5y | Fitness + skinfolds | Referenced in the literature; **specific percentile numbers not retrieved in this pass [unverified]** — flagged for follow-up, low direct relevance to a Colombian population regardless. |
| **Argentina / Brazil / Chile** | — | — | **Not located in this research pass.** Flagged as a gap, not evidence of absence. |
| **Bogotá, Colombia — FUPRECOL study** (PMC5083983) | n=9,618 (55.7% girls), ages 9–17.9y, public-school children, Bogotá | Triceps & subscapular, LMS percentile curves (P3–P97), Holtain calipers | **Best-fit Colombian reference found.** Open access via PMC. 50th-percentile combined triceps+subscapular runs roughly 23–28 mm (boys) and 28–42 mm (girls) across the age range; the study found Bogotá children had **higher** adiposity by these skinfolds than UK/US/Spain/Germany comparators, reinforcing that a US or European reference should not be used unmodified for this population. The article is CC BY 4.0 and **prints the LMS (L, M, S) parameters by sex and age** for triceps, subscapular and triceps+subscapular (verified 2026-09-23 against the PMC full text), so it is directly seedable into `growth_reference_lms` — extracting the tables into a vendored CSV is a small, well-defined engineering task. Caveat: FUPRECOL measured the **left** side; ISAK convention is the right side (side differences are small but should be stated wherever the reference is displayed). |
| **ENSIN (Colombia's national nutrition survey)** | Colombia | Height/weight/BMI (WHO Z-scores) | ENSIN's routinely published indicators are height/weight/BMI-based (see `docs/04-percentiles/research.md`); **no confirmed evidence in this pass that ENSIN itself routinely collects skinfolds nationally** — a separate numeric claim surfaced by search (Σskinfolds ~28→36.6mm girls, ~24→28.8mm boys across early-childhood age bands) could not be confidently attributed to ENSIN specifically and is **flagged as unverified/needs source disambiguation**, not asserted as fact here. |
| **Youth XCO cyclists** (PMC8196776, Argentine National Junior Team) | n=10, male, age 16.3±0.95y | Σ6 (triceps+subscapular+suprailiac+thigh+abdominal+calf) = 47.71±8.24mm; adipose mass 22.91±2.6% | **Not a pediatric norm** — older/junior elite riders, small n, male-only. Useful only as distant orientation for "what a lean, trained older junior XCO rider looks like," not a comparison target for a 12-year-old. Notably, none of the anthropometric variables correlated with race performance in that sample. |

**Practical conclusion:** the Bogotá FUPRECOL article (CC BY) is the one Colombian reference with published LMS parameters for triceps and subscapular skinfolds (ages 9–17.9), and it can be vendored and seeded like the WHO tables. It remains a Bogotá school population, not an athlete population, so percentile position is context, not a verdict — §4's recommendation stands: track **individual change over time** as the primary output, with the population percentile as a secondary, coach-only orientation.

---

## 6. Measurement error and minimum detectable change (MDC)

**ISAK TEM targets:** intra-tester TEM ≤5% for a certified/experienced anthropometrist (ISAK Level 2/3), ≤7.5% for a novice/Level 1; inter-tester ≤7.5%. A genuinely untrained measurer can exceed even the 7.5% novice ceiling until they complete structured practice (§2) — one reliability study found untrained measurers' TEM ran 2–4× an expert's.

**Worked example (illustrative — not a published figure for this exact site combination):**

Assume, after practice, the club's measurer reaches the ISAK "novice" ceiling of 7.5% intra-tester TEM (a conservative planning assumption).

1. For a Σ4 (triceps+biceps+subscapular+calf) around 35 mm in a 12-year-old: absolute TEM ≈ 0.075 × 35 mm ≈ **2.6 mm** per measurement session.
2. Two independent sessions (baseline + 6-month follow-up) each carry this error; the error of the *difference* = TEM × √2 ≈ **3.7 mm**.
3. At a 95% confidence convention (±1.96 SD), the smallest real (non-noise) change ≈ 1.96 × 3.7 mm ≈ **7 mm**.

**Practical rule for the coach:** *a Σ4 change smaller than about 7 mm over 6 months is plausibly instrument/measurer noise; only discuss changes at or above roughly 7–8 mm as a likely real change.* This mirrors, and should be implemented the same way as, the existing height (≥0.7 cm) / weight (≥1.5 kg) "significant vs. dentro del ruido instrumental" logic in `_build_measurement_deltas` (`app/services/ai/anthro/context.py`) — a `delta_sum_skinfolds_significant` boolean using a ~7 mm/6-month default, to be replaced with the club's own empirically-measured TEM once available via the self-calibration routine in §2. Note this simplified whole-sum approach treats error as one lump sum; a more rigorous version would combine each site's own TEM in quadrature, which requires data the club does not have yet.

---

## 7. Interpreting change in growing athletes

**Loomba-Albrecht & Styne (2009)**, *Effect of puberty on body composition* (Curr Opin Endocrinol Diabetes Obes 16(1):10–15): during puberty, **boys gain disproportionately more fat-free mass and skeletal mass**, while **girls gain significantly more fat mass** — a direct, hormonally-driven (estrogen vs. testosterone) divergence. This is the essential lens: **a rise in Σ skinfolds in a girl around/after PHV is very often the expected physiological pattern, not a training or nutrition problem** — directly answering the motivating question this protocol was commissioned to address.

**Reading combined signals** (Σ skinfolds + weight + height velocity + `maturity_offset`, all already computed by the existing growth module):

| Pattern | Typical read |
|---|---|
| Weight↑ + height↑ (typical/above-typical velocity) + Σskinfolds stable-or-↑ + Circa/Post-PHV + female | Expected puberty-associated fat gain alongside growth — normal, not a concern. |
| Weight↑ + height↑ (typical velocity) + Σskinfolds stable-or-↓ + Post-PHV + male | Classic post-PHV "strength spurt" (testosterone-driven FFM gain) — normal. |
| Weight↑ + height flat/low-velocity + Σskinfolds sharply↑ | Weight gain not explained by growth — worth a coach conversation, not an alarm. |
| Weight flat/↓ + height↑ (continuing) + Σskinfolds↓ meaningfully (≥ MDC, §6) + heavy training/academic load | Matches the RED-S / energy-availability pattern already documented in `docs/01-marco-teorico.md` §1/§7 — the pattern that should trigger a food-first family conversation and, if persistent or joined by other warning signs (fatigue, missed training, mood/sleep, menstrual changes if disclosed), referral to a pediatrician/sports-medicine physician or dietitian. Same wellbeing-not-diagnosis, human-in-the-loop, refer-on-persistence pattern as the constitution's Principle V. |

**Three worked scenarios** (all figures invented/illustrative — no real athlete data; ages/sex only, no other identifying detail):

**A — the motivating pattern: girl, Circa→Post-PHV crossing, 6 months.** Weight 38.0→42.5 kg (+4.5 kg); height 148→152.5 cm (+4.5 cm, at/slightly above the club's typical 7–9 cm/year girls' range prorated to 6 months); Σ4 32→39 mm (+7 mm, at the illustrative MDC threshold from §6 — plausibly real); maturity offset −0.3→+0.4 (Circa→Post-PHV, corroborated). Illustrative %BF (generalized triceps+calf equation) ~19%→~21%; FFM ~30.8→~33.6 kg (**≈+2.8 kg estimated lean mass**) alongside **≈+1.7 kg estimated fat mass**. Read: most of the weight gain is still structural/lean tissue, with a normal, expected uptick in fat mass typical of this exact maturation window — reassurance, not concern, for the coach to relay.

**B — boy, 12–18 months post-PHV (strength-spurt window), 6 months.** Weight 45→49.5 kg (+4.5 kg); height 158→161 cm (+3 cm, below the 8–10 cm/year range prorated to 6 months, consistent with expected deceleration well past PHV); Σ4 28→27 mm (flat, within noise). Read: classic post-PHV strength-spurt — FFM/muscle accretion, skinfolds flat — no concern.

**C — energy-availability pattern, Pre/Circa-PHV, heavy exam + training load, 6 months.** Weight 40.0→40.5 kg (essentially flat); height 145→148.5 cm (+3.5 cm, roughly typical, continuing); Σ4 30→22 mm (**−8 mm, a real fall** by the illustrative MDC). Read: height still climbing normally while weight stalls and skinfolds fall meaningfully is exactly the combination that should raise the RED-S/energy-availability flag — coach-family conversation, food-first review (never calorie counting with the athlete), and referral if it persists or other warning signs appear.

---

## 8. Cadence (measurement frequency — not pedaling cadence)

The existing height/weight interval logic (`measurement_alerts.py`) is Pre-PHV 90 days, Circa-PHV 30 days, Post-PHV 120 days — tuned to how fast **height** changes. Skinfolds change more slowly and carry more short-term noise (hydration, recent training, gut content) than height, and §6's illustrative MDC (~7 mm/Σ4) would almost never be cleared over a 30-day gap — measuring that often would mostly generate noise while also increasing how often a sensitive procedure is repeated on a minor, which is itself a cost, not just a statistical one.

**Recommendation (this document's own synthesis — no specific published youth-athlete skinfold remeasurement-interval guideline was found in this pass [unverified]):** a **flat 90-day skinfold interval regardless of maturation phase**, decoupled from the height/weight cadence above. Post-PHV athletes (slower-changing) may safely stretch to 120 days if the coach prefers fewer sessions; **never more often than every 90 days** for anyone.

---

## 9. Equipment

| Caliper class | Material | Typical precision | Notes |
|---|---|---|---|
| **Harpenden** | Metal | ±0.2 mm | Historical "gold standard"; used in most validation studies including Slaughter's original sample; expensive. |
| **Lange** | Metal | ~±1.0 mm | Different jaw geometry/pressure than Harpenden — not directly interchangeable with it. |
| **Slim Guide** | Plastic | ~±1.0 mm | Good inter/intra-examiner reliability (ICC 0.93–0.97) approaching Harpenden despite lower manufacturing precision — the realistic "good enough" option for a club budget. |
| **Cescorf** | Metal | Not independently verified here [unverified] | Brazilian-made, commonly used in Latin American ISAK courses as an affordable metal alternative — noted by regional reputation, not a citation checked in this pass. |
| **Generic plastic "adipómetro"**| Plastic | Highly variable | Unregulated commodity category; quality ranges from reasonable Slim-Guide clones to poorly-calibrated novelty items. Run the calibration check in §2 regardless of brand. |

**Terminology:** "picómetro" is almost certainly a mishearing/mistyping of **"plicómetro"** (from Latin *plica*, "fold"). **Plicómetro and adipómetro are synonyms** for "skinfold caliper" in everyday Spanish — no meaningful technical difference.

**Checklist to identify a caliper's class from a photo:**
1. **Body material** — metal (Harpenden/Lange/Cescorf-class) vs. plastic (Slim-Guide/generic-class).
2. **Jaw faces** — rounded contact tips ~6 mm diameter is the ISAK-compliant norm; flat/sharp or oversized tips suggest a non-compliant novelty item.
3. **Readout** — analog dial gauge or digital LCD is acceptable; a passive ruler-only scale with no spring mechanism is **not** appropriate (ISAK requires constant-pressure pinch, not passive measurement).
4. **Spring mechanism** — squeeze the jaws; resistance should feel consistent across the full opening range, returning smoothly to zero.
5. **Graduation** — should read to ≤0.5 mm (analog) or 0.1 mm (digital) over a 0–40/0–60 mm range; coarser than 1 mm is inadequate.
6. **Recognizable models** — Harpenden (large dial, metal, premium); Lange (boxy metal dial housing); Slim Guide (bright plastic, simple dial); Cescorf (metal, Brazilian branding); Accu-Measure-style pen calipers (cheap, pinch-and-read-directly, **not** built for the jaw geometry this protocol assumes — inadequate here even though marketed for skinfolds).

If the club's existing caliper is a plastic model with a visible spring and an analog dial reading 0–40/0–60 mm at ≤0.5 mm graduations, it is very likely Slim-Guide-class and adequate — verify with §2's calibration routine. A pen-style Accu-Measure-type device is not appropriate; budget for a proper replacement (~USD 30–150) if that is what the club owns.

---

## 10. What NOT to do

- **BIA scales/handheld devices for minors** — hydration status alone swings BIA-derived %BF by 2–3 points, and puberty itself shifts body water (the very thing driving the artifact), making BIA especially unreliable exactly when it matters most. Never a substitute for skinfolds; at most a rough, clearly-labeled cross-check.
- **Adult equations** (Durnin–Womersley, Jackson–Pollock, Faulkner, Yuhasz) — see §3. Never use these on a 9–15-year-old.
- **%BF or Σ-skinfolds as a target/goal** — track direction and magnitude only, never a number to "hit."
- **Comparing athletes to each other** — no leaderboard of leanness, no public discussion of one athlete's numbers relative to another's, matching the club's existing mastery-climate principle.
- **Measuring in public / in front of teammates** — private space or a discreet corner; same-sex measurer where feasible, especially if the optional sites in §1 are ever added.
- **Measuring more often than every 90 days** (§8) — more frequent sessions mostly add noise and unnecessary repeated exposure.
- **Showing %BF or FFM to the athlete or on any parent-facing screen** — coach-only (§4).
- **Guessing a "race" category to select a Slaughter intercept** for a Colombian child — no scientific basis (§3); use the race-free triceps+calf equation instead.
- **Treating a single measurement as diagnostic** — always require ≥2 points / a trend, exactly like the system's existing philosophy for height, weight, and PHV.
- **Using skinfolds or any body-composition number for talent or team selection** — extends the club's fun-first, skills-over-fitness non-negotiables to this new data type explicitly.

---

## 11. Reference list

- Ackland TR, Lohman TG, Sundgot-Borgen J, Maughan RJ, Meyer NL, Stewart AD, Müller W (2012). Current Status of Body Composition Assessment in Sport: Review and Position Statement on Behalf of the Ad Hoc Research Working Group on Body Composition Health and Performance, Under the Auspices of the I.O.C. Medical Commission. *Sports Medicine* 42(3), 227–249. https://pubmed.ncbi.nlm.nih.gov/22303996/ · PDF: https://stillmed.olympics.com/media/Documents/Athletes/Medical-Scientific/Consensus-Statements/2012_current-status-body-composition-assessment-sport.pdf
- Addo OY, Himes JH (2010). Reference curves for triceps and subscapular skinfold thicknesses in US children and adolescents. *American Journal of Clinical Nutrition* 91(3), 635–642. doi:10.3945/ajcn.2009.28385. https://pubmed.ncbi.nlm.nih.gov/20053877/
- Ramírez-Vélez R, et al. (2016). Triceps and Subscapular Skinfold Thickness Percentiles and Cut-Offs for Overweight and Obesity in a Population-Based Sample of Schoolchildren and Adolescents in Bogotá, Colombia (FUPRECOL study). *Nutrients* 8(10), 595. doi:10.3390/nu8100595. https://pmc.ncbi.nlm.nih.gov/articles/PMC5083983/ — open access, CC BY 4.0; **publishes the LMS (L, M, S) tables** for triceps, subscapular and triceps+subscapular by sex and age (verified 2026-09-23 against the PMC full text). Note: skinfolds were taken on the **left** side with a Holtain caliper.
- González-Ruíz K, et al. (2018). Comparison of Bioelectrical Impedance Analysis, Slaughter Skinfold-Thickness Equations, and Dual-Energy X-ray Absorptiometry for Estimating Body Fat Percentage in Colombian Children and Adolescents with Excess of Adiposity. *Nutrients* 10(8), 1086. doi:10.3390/nu10081086. https://pmc.ncbi.nlm.nih.gov/articles/PMC6115719/ — open access, CC BY 4.0 (verified 2026-09-23).
- Frisancho AR (1990). *Anthropometric Standards for the Assessment of Growth and Nutritional Status*. University of Michigan Press. Lending copy: https://archive.org/details/anthropometricst0000fris
- Kasper AM, Langan-Evans C, Hudson JF, et al. (2021). Come Back Skinfolds, All Is Forgiven: A Narrative Review of the Efficacy of Common Body Composition Methods in Applied Sports Practice. *Nutrients* 13(4), 1075. https://pubmed.ncbi.nlm.nih.gov/33806245/ · https://www.mdpi.com/2072-6643/13/4/1075
- Loomba-Albrecht LA, Styne DM (2009). Effect of puberty on body composition. *Current Opinion in Endocrinology, Diabetes and Obesity* 16(1), 10–15. https://pubmed.ncbi.nlm.nih.gov/19115520/
- NHANES Anthropometry Procedures Manual (various years) — skinfold pinch/read technique. https://wwwn.cdc.gov/nchs/data/nhanes/public/2007/manuals/manual_an.pdf
- Race Performance Prediction from the Physiological Profile in National Level Youth Cross-Country Cyclists. *International Journal of Environmental Research and Public Health* 18(11), 5535. doi:10.3390/ijerph18115535. https://pmc.ncbi.nlm.nih.gov/articles/PMC8196776/
- Reliability of skinfold measurements and body fat prediction depends on the rater's experience: a cross-sectional analysis comparing expert and novice anthropometrists. https://www.researchgate.net/publication/393163533 · https://www.researchsquare.com/article/rs-4540605
- Slaughter MH, Lohman TG, Boileau RA, Horswill CA, Stillman RJ, Van Loan MD, Bemben DA (1988). Skinfold equations for estimation of body fatness in children and youth. *Human Biology* 60(5), 709–723. https://pubmed.ncbi.nlm.nih.gov/3224965/ · https://digitalcommons.wayne.edu/humbiol/vol60/iss5/4/
- A comparison of the Slaughter skinfold-thickness equations and BMI in predicting body fatness and cardiovascular disease risk factor levels in children (tabulates the full 1988 equation set used in §3). https://pmc.ncbi.nlm.nih.gov/articles/PMC3831534/ · original table sourced via https://pmc.ncbi.nlm.nih.gov/articles/PMC2859115/
- Standards for Anthropometry Assessment (ISAK protocol, secondary source). https://www.researchgate.net/publication/333585249_Standards_for_Anthropometry_Assessment
- Skinfold calipers: which instrument to use? *Journal of Nutritional Science*. https://www.cambridge.org/core/journals/journal-of-nutritional-science/article/skinfold-calipers-which-instrument-to-use/7D5830AA438DF5541C8CA5D49035E317
- Comparison of methods to assess change in children's body composition (Lohman age-adjusted Siri vs. 4-compartment model). *American Journal of Clinical Nutrition* 80(1), 64. https://academic.oup.com/ajcn/article/80/1/64/4690296
- Alterations in growth and body composition during puberty. I. Comparing multicompartment body composition models. *Journal of Applied Physiology* 83(3), 927. https://journals.physiology.org/doi/full/10.1152/jappl.1997.83.3.927
- Using bioelectrical impedance analysis in children and adolescents: Pressing issues. *European Journal of Clinical Nutrition*. https://www.nature.com/articles/s41430-021-01018-w
- Existing project references: `docs/01-marco-teorico.md` (§1 maturity-offset uncertainty, RED-S; §7 nutrition/RED-S), `docs/04-percentiles/research.md` (§6 interpretation for youth athletes; Colombian growth-reference context), `.specify/memory/constitution.md` (Principle V, lines 160–200).
