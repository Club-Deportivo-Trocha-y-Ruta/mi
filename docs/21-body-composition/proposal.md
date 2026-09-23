# Body composition (skinfolds) — Proposal and open decisions

**Status**: research synthesis, 2026-09-23. Nothing implemented. Input for a future Spec Kit feature (next free number at the time of writing: `specs/046-…`).
**Inputs**: `research-protocol.md` (science, equations, references), `research-safeguards-referral.md` (ethics, bands, referral, Spanish copy), `research-measurer-ux.md` (capture flow, illustrations, family view), `technical-fit.md` (data model, API, AI pipeline, waves). Read those for evidence; this file only decides and lists what is still open.

## 1. The problem

The club owns a skinfold caliper ("plicómetro"/"adipómetro") and wants a next level of anthropometry for athletes aged 9 and up. The motivating case: a female athlete measured about six months apart; with weight, height and BMI alone the coach could not tell whether she gained lean mass, fat mass, or both. Weight and BMI cannot separate the two, and a rising weight in a girl around her growth peak is ambiguous by construction. The coach also wants charts, a clear sense of how each athlete is doing, a way to notice something that deserves a nutrition professional, and a capture flow that teaches the measurer exactly where and how to measure.

## 2. Recommendation (one paragraph)

Add an **optional, guided "Composición corporal" step** to the existing anthropometric evaluation: same record and date, offered after the fast weight/height save, one screen per site with a line-art illustration (six sites by default), two readings per site, per-site opt-out, autosave. Track the **sum of four skinfolds in millimetres (Σ4: triceps, biceps, subscapular, medial calf)** as the primary charted metric, with Σ6 (adding iliac crest and supraspinale) when the full set was taken, with a **coach-only "estimated" % body fat and fat-free mass** from the race-free Slaughter–Lohman triceps+calf equation. Flag six-month changes below about 7 mm as "within measurement noise". Give the coach a **traffic light** (verde/ámbar/rojo) built from the athlete's own trend, the Colombian FUPRECOL percentiles for triceps and subscapular, BMI-z drift and height velocity, where "rojo" means "talk to the family and consider a referral", never a label. Families see a band and one sentence, **no numbers**; athletes see nothing numeric. Measure at most every 90 days.

## 3. Decisions taken in this synthesis

| # | Decision | Why | Source |
|---|---|---|---|
| D1 | Skinfolds attach to the existing `anthropometric_records` row (same `evaluation_date`), captured as an optional step after the fast save | Fat-free mass needs the same-day weight; two records for one date is the exact bug class feature 040 fixed | UX §2, tech §2 |
| D2 | Default wizard takes **six sites: triceps, biceps, subscapular, medial calf, iliac crest, supraspinale** (coach decision C3, 2026-09-23); abdominal and front thigh excluded. The four easy sites form the **Σ4 backbone** that is always comparable; Σ6 is shown when all six were taken | Covers both Slaughter equations and the Colombian reference (triceps, subscapular); iliac crest and supraspinale are the two sites novices landmark worst, so their illustrations and the W0 calibration must cover them explicitly | protocol §1, C3 |
| D3 | Primary metric = **Σ4 in mm** (triceps + biceps + subscapular + calf), charted over time, with **Σ6** as a second series when complete; if a backbone site is skipped the record shows "suma incompleta" and sites still trend individually | ISAK/IOC and Kasper 2021: raw sums track change better than converted %BF; a Colombian DXA study found Slaughter underestimates fat by 9–11 points in high-adiposity adolescents | protocol §3–4 |
| D4 | %BF and FFM computed with **Slaughter–Lohman triceps+calf** (no race intercept, no maturation split), persisted with `equation_version`, shown **coach-only** and labelled "estimado (±4 puntos)"; never a target | The triceps+subscapular boys' equations require a White/Black intercept that has no valid mapping to a Colombian child | protocol §3 |
| D5 | Noise threshold: **default 7 mm per ~6 months for Σ4 and ~10 mm for Σ6** (ISAK novice TEM 7.5 % propagated over a ~35 mm / ~50 mm sum), configurable constants, to be replaced by the club's own TEM after the calibration sessions (§5, W0) | Same pattern as the height ≥0.7 cm / weight ≥1.5 kg significance flags in `ai/anthro/context.py` | protocol §6 |
| D6 | Reference percentiles: seed **FUPRECOL 2016 (Bogotá, ages 9–17.9, CC BY)** LMS tables for triceps, subscapular and triceps+subscapular into `growth_reference_lms` as new `GrowthIndicator` values; coach-only context, never a verdict; state that the reference is a school population measured on the left side | Verified 2026-09-23: the article prints L, M (P50) and S per sex and one-year band; the existing LMS machinery needs no schema change | protocol §5, tech §4 |
| D7 | Cadence: skinfolds offered when **≥90 days** since the last skinfold set, independent of the PHV-driven 30/90/120-day height/weight cadence; never more often | Skinfolds change slowly and each session is a sensitive procedure on a minor | protocol §8, safeguards §6 |
| D8 | Coach traffic light per `research-safeguards-referral.md` §2, derived at read time (not persisted), "coarse guidance only"; **rojo never fires from a rising Σ4 alone** | Girls gain fat mass through puberty as a normal pattern; the concerning pattern is falling Σ4 + flat weight + continuing height growth (energy-availability signal) | safeguards §2–3 |
| D9 | Audiences: coach = full numbers; **family = band + one sentence, no %BF and no mm**; athlete = nothing numeric | Adolescent body-image evidence; extends feature 040 decision D3 ("never obesidad as a headline") | safeguards §1, §5; UX §8 |
| D10 | Capture UX: pre-check screen (conditions + private space + second adult as a **reminder, not a gate** — coach decision C4) → one step per site (illustration + "Dónde"/"Cómo" + two readings with live difference, third reading when the difference exceeds **the greater of 5 % of the mean or 1 mm**, median of three) → review; inputs in 0.5 mm steps; "Omitir sitio" as a first-class 48 px action; `useFormDraft` autosave; reuse `SessionWizard`/`Stepper` | The measurer is not ISAK-certified; the flow must teach. The club's caliper reads in 1 mm graduations, so a flat "> 1 mm" rule would fire a third reading on almost every small fold | UX §2–5, C1, C4 |
| D11 | Illustrations: **hand-authored inline SVG per site** (shared silhouette + landmark + fold orientation + caliper + "D" for right side), one schema rendered both in React and in a Jinja partial for a **printable club-wide instructivo PDF**; no photos, no GIF | Follows the feature-019 gymkhana diagram decision; ISAK images are copyrighted, the descriptions are not | UX §3, §6 |
| D12 | Data: child table **`skinfold_measurements` 1:1** with the record; per-site median as `Numeric`, raw readings as a JSON array, `{site}_skipped` booleans, `equation_version`, `caliper_model`; Σ4/%BF/FM/FFM persisted at write; band derived at read | Keeps the parent table stable, explicit skip semantics, recomputation possible | tech §2–3 |
| D13 | API: **`PUT /api/athletes/{id}/anthropometry/{record_id}/skinfolds`** (idempotent create/replace) + `DELETE`; `POST …/anthropometry` unchanged; `growth-summary` gains an optional `body_composition` block; parent reads filtered per D9; Pydantic ranges per site (new for this file: the backend validates no ranges today) | The guided flow runs after the fast save and may be resumed from a draft; a wizard failure must never lose the weight/height record. This reconciles UX §2 (post-save step) with tech §5 (single payload) in favour of the sub-resource | UX §2, tech §5 |
| D14 | The anthropometry PDF (`templates/documents/pdf/anthropometry_report.html`) is downloadable by parents today; it must apply the same D9 rule (no %BF, no mm) or the PDF becomes a bypass | Real gap found by the technical analysis | tech §8 |
| D15 | AI explainer: extend the feature-042 pipeline with **qualitative codes only** (`skinfold_sum_band`, `ffm_trend_direction`, `sites_skipped_count`), never raw mm or %BF; new precheck R13 (no body-fat number in family text); golden cases added. Scheduled as the last wave, **included in the first release by coach decision C7** | The pipeline already falls back on ~10/12 golden cases; charts and bands answer the coach's need without narrative | tech §6 |
| D16 | Consent: reuse the existing `ParentalConsent.anthropometry` scope; **no privacy-policy version bump** (a bump forces every family through a blocking re-consent). Families are informed with the consent addendum text from safeguards §5 through the family app; the athlete may decline any site at any time | Skinfolds are anthropometry data; sharing with an external professional stays behind `third_party_sharing` and an explicit per-case authorization | tech §8, safeguards §4, §7 |
| D17 | Regulatory framing: Resolución 2465/2016 classifies only height, weight and BMI; the skinfold tool is an **internal monitoring aid**, never an "official classification" | safeguards §7 | — |

## 4. What the feature would have said in the motivating case

`research-protocol.md` §7, scenario A (illustrative numbers, not real data): a girl crossing from circa- to post-PHV over six months, weight +4.5 kg, height +4.5 cm, Σ4 +7 mm. The tool would show: Σ4 change at the noise threshold (plausibly real), estimated fat-free mass +2.8 kg and fat mass +1.7 kg, maturity offset crossing PHV, band **verde** with the reading "most of the gain is structural/lean tissue plus the expected pubertal rise in fat mass". Without skinfolds the same six months read as "weight up 4.5 kg", which is exactly the ambiguity the coach hit. Scenario C in the same section shows the opposite pattern (weight flat, height up, Σ4 −8 mm) firing **rojo**.

## 5. Waves and effort

| Wave | Scope | Size | Depends on |
|---|---|---|---|
| **W0 (no software)** | Identify the caliper model (protocol §9 checklist; replace if it is a pen-style device); measurer self-calibration on **adult volunteers** (two sessions, 5–10 people, compute TEM; never repeat sessions on minors for practice); define the private space + second-adult process; send families the addendum text | — | Coach |
| W1 | `skinfold_measurements` model + migration, `services/body_composition.py` (median, Σ4, Slaughter triceps+calf, FM/FFM, noise flag, band classifier), unit tests | M | D2–D5, D8 |
| W2 | `PUT/DELETE …/skinfolds`, schemas with per-site ranges, `growth-summary.body_composition`, parent filtering, PDF rule (D14), RBAC denied-path tests | S–M | D9, D13 |
| W3 | Guided capture wizard (pre-check, per-site steps, review), 4–6 SVG site illustrations, autosave, printable instructivo PDF, vitest + jest-axe | L | D10–D11 |
| W4 | Σ4/FFM sparklines and per-site history, FUPRECOL LMS seed + percentile context, family band card, coach traffic-light card | M | D6, D8 |
| W5 | AI context leaf, prompts, R13, privacy-seam property, golden cases, `data-privacy-guard` audit — **in scope of the first release (C7)** | L | D15 |

Comparable in size to features 040 and 042 together. Deferred real-infrastructure checks (`pytest -m mysql`, golden eval, Playwright) apply as usual.

## 6. Risks

- **Measurer error dominates the signal** until the coach completes W0; the UI must keep saying "dentro del margen de medición" rather than inventing trends.
- **Body-image harm** if any number leaks to athletes or families through a screen, a PDF or a conversation; D9 and D14 exist for that reason, and the anti-pattern list in safeguards §6 should become spec requirements.
- **Reference misuse**: FUPRECOL is a Bogotá school population, left side, Holtain caliper; percentile position is context only.
- **AI regression**: a new guardrail on an already fallback-prone pipeline; hence W5 last and optional.
- **Open research gaps** (safeguards §8): CAT2 applicability under 14, LEAF-Q age bound, Ministerio del Deporte guidance, Ley 1581 article-level citation. None blocks W1–W4.

## 7. Coach decisions (2026-09-23)

| # | Question | Answer | Design consequence |
|---|---|---|---|
| C1 | Which caliper | Photo identified as a **Slim Guide-class plastic caliper**: white body, pistol grip, fan-shaped "skinfold thickness mm" scale, external coil spring, 1 mm graduations | Adequate (ISAK-style constant-pressure jaws, ICC 0.93–0.97 in the literature). Protocol: zero check before each session, read to the nearest 0.5 mm, log a reference-block reading per session; `caliper_model = "slim_guide"` stored on every skinfold row |
| C2 | Family visibility | **Band + one sentence only, no numbers** | D9 and D14 confirmed as written |
| C3 | Default sites | **Six**: triceps, biceps, subscapular, medial calf, iliac crest, supraspinale | D2/D3/D5 updated: Σ4 backbone + Σ6 series; W0 calibration and the SVG set must cover the two hip sites; private space matters more (waistband eased down) |
| C4 | Second adult | **Reminder only**, no hard gate | D10 updated; the private-space + second-adult practice stays a club process, stated on the pre-check screen and in the printable instructivo |

## 8. Coach decisions, second round (2026-09-23)

| # | Question | Answer | Design consequence |
|---|---|---|---|
| C5 | Cadence | **90 days for everyone**, no 120-day stretch | D7 confirmed |
| C6 | Referral partner | **None yet**; the referral note stays generic (family chooses EPS or private) | safeguards §4 note as written |
| C7 | AI narrative in the first release | **Yes** | W5 is **in scope** of the first release, not optional: qualitative codes only, R13 precheck, golden cases, privacy-seam property; plan prompt-iteration time given the pipeline's fallback rate |
| C8 | Consent | **In-app notice, no policy version bump** | D16 confirmed; the addendum text from safeguards §5 ships as a family-facing notice |

Nothing remains open for the spec.

## 9. Next step

All decisions are taken; run `/speckit-spec-author` with this folder as input to produce `specs/046-body-composition-skinfolds` (spec → plan → tasks), keeping the anti-patterns of `research-safeguards-referral.md` §6 as non-functional requirements and the `data-privacy-guard` audit as mandatory.
