# Body composition (skinfolds) — coach runbook

Feature `specs/046-body-composition-skinfolds`. Audience: the coach who will actually hold the
caliper and read the traffic light in-app. This document is English prose with Spanish quoted
copy (the copy the coach and family actually see), per the project's language-split rule.

See `docs/21-body-composition/proposal.md` for the decision record and
`docs/21-body-composition/research-protocol.md` / `research-safeguards-referral.md` for the
underlying research this runbook operationalizes. Nothing here overrides those documents; if a
number below and a contract in `specs/046-body-composition-skinfolds/contracts/` disagree, the
contract wins.

## 0. Before touching the app — W0, no software involved

W0 is a one-time, no-software checklist the coach must complete before the first real
measurement is trusted for a trend. Skipping it does not block the app (there is no
technical gate), but every reading taken before W0 is complete should be treated as
uncalibrated and never discussed with a family as a trend.

### 0.1 Identify and check the caliper

1. Confirm the club's caliper is a **Slim Guide-class plastic caliper** (visible spring,
   analog dial, 0–40/0–60 mm range, ≤0.5 mm graduations) — not a pen-style
   Accu-Measure-type device. See `research-protocol.md` §9 for the full identification
   checklist and photos-to-look-for guide. A pen-style caliper is not adequate; replace it
   (~USD 30–150) before proceeding.
2. **Zero check**: with the jaws fully closed, the dial must read exactly 0.0 mm. Do this
   before every measurement session, not only once.
3. **Spring-tension check**: squeeze the jaws through their full range; resistance should
   feel consistent, with no binding or wobble, and the jaws should return smoothly to zero.
4. **Reference-block reading**: at the start of every session, pinch a fixed-thickness
   reference object (a folded rubber block or similar item that does not compress further
   under the caliper's own pressure) and log the reading. This is a practical, club-level
   substitute for professional caliper certification — not an ISAK-validated protocol in
   itself — and its purpose is to catch spring drift over months, not to certify the
   instrument once.

### 0.2 Two calibration sessions on adult volunteers, and the TEM formula

Practice **only on adult volunteers (5–10 people, two separate sessions)** — never repeat
practice sessions on a minor for the coach's own training purposes. This mirrors the
project's non-negotiable against unjustified repeated measurement of a child.

To compute the coach's own technical error of measurement (TEM) from the two sessions:

1. For each volunteer, take one full measurement (all six sites, following §2 of
   `research-protocol.md`: 2 readings per site in rotational order, median of 3 if the first
   two disagree by more than ~5 %) in session 1, and repeat independently in session 2 —
   same volunteer, same sites, different day or at least a meaningful gap, without looking
   at the session-1 numbers.
2. For each volunteer and site, compute the difference `d = session1 − session2` (mm).
3. Compute TEM as:

   ```
   TEM = sqrt( Σ(d²) / (2 × n) )
   ```

   where `n` is the number of volunteers (or volunteer-site pairs, if computing a
   combined figure across sites) and `d` is each paired difference from step 2.
4. Express TEM as a percentage of the mean sum-of-skinfolds value across both sessions
   (`%TEM = TEM / mean(Σ) × 100`) to compare against the ISAK targets: **≤ 5 %** for a
   certified/experienced anthropometrist, **≤ 7.5 %** for a novice. A genuinely untrained
   measurer can exceed even the 7.5 % ceiling until this practice is complete — one cited
   reliability study found untrained measurers' TEM ran 2–4× an expert's.
5. Until the club's own measured TEM is available and stable, the app uses the
   **illustrative planning default of ~7 mm/6 months** for the four-site backbone sum noise
   threshold (derived in `research-protocol.md` §6 from the ISAK novice 7.5 % ceiling on a
   35 mm Σ4). This default is a starting value, not a claim about the club's actual
   measurer error — replace it once real TEM data exists (see `data-model.md` for where the
   threshold lives).

Repeat the two-session practice periodically (at minimum once a year, or after any long gap
without measuring) — TEM drifts with disuse just as it improves with practice.

### 0.3 Private space and the second-adult practice

- Measure in a private space, never in front of teammates. A same-sex measurer is preferred
  where feasible.
- The **second-adult presence is a reminder, not a gate** (owner decision, 2026-09-23): the
  app does not block a measurement session for the absence of a second adult, but the coach
  should default to having one present — a parent, another coach, or another club adult — as
  a matter of practice, not only for a minor who asks for it.
- Measurement is voluntary site by site. A declined site is recorded as declined, never
  treated as a failure or pushed on.
- Never measure post-exercise (fluid shifts change readings); measure before training, with
  dry skin and no lotion/sunscreen, and always on the right side of the body.

### 0.4 Family notice

Before the first skinfold measurement, families receive the consent-addendum notice (fixed
copy, no new consent signature required — see `research-safeguards-referral.md` §5 for the
approved Spanish wording). The in-app notice on the growth view repeats the same explanation:
what the measurement is, that it is voluntary per site, that it happens in a private space,
and how results are used.

## 1. Reading the traffic light — verde / ámbar / rojo

The traffic light is coach-only; families only ever see a capped projection of it (§2).

| Color | What it means | What the app shows the coach |
|---|---|---|
| **Verde** | Change is within the measurement-noise margin, or a real change fully explained by an expected growth pattern (e.g. a rising backbone sum in a girl at/after her growth peak, or a flat sum during a boy's post-PHV strength spurt). | "Sin cambio real desde la última toma" or a one-sentence explanation naming the expected pattern. |
| **Ámbar** | Either a real change (beyond the noise margin) that no growth pattern explains, or — coach-only — a single set landing at a Colombian-reference extreme (e.g. ≥ P95) with no trend data yet. | A one-sentence reason plus a coach-only prompt: have a private, food-first conversation with the athlete, no numbers, no diet language. |
| **Rojo** | Requires at least two sets and all three legs of the combined pattern: backbone sum falling beyond the noise margin, weight flat or falling, height still growing (the pattern consistent with low energy availability). A rising sum alone can never produce rojo. | The combined pattern, worded without numbers, plus the escalation prompt (private conversation → family conversation → referral if it persists) and the option to generate a referral note. |

Any leg the app could not evaluate (fewer than two sets, no height-velocity data yet) is
named explicitly in the reason sentence — rojo can never fire while a leg is missing.

**A single set is never enough for a trend.** With only one set, the reading is verde or
ámbar (from the reference-percentile context only) and says a second set is needed — it can
never be rojo.

## 2. What the family sees

Families never see verde/ámbar/rojo directly, and never see a number (no percentage, no
millimetre value, no sum). The family band is capped at ámbar:

- Coach-side **verde**, or coach-side **ámbar from the reference context only** (no real
  change over time) → family sees **"En su curva esperada"**.
- Coach-side **ámbar from a real trend**, or coach-side **rojo** → family sees
  **"En observación"** with the ámbar-level sentence. **"Requiere acompañamiento
  profesional" never appears automatically on any family surface** — the coach communicates
  that in person, following the escalation ladder in §3.

The same capped band and sentence appear in the monthly newsletter (Bitácora de etapa), but
only in the month a skinfold set with at least one measured site was taken — the newsletter's
AI-written narrative never receives body-composition data and never mentions it.

## 3. Escalation ladder and the referral note

1. **Ámbar (any cause)**: a private, food-first conversation with the athlete — no numbers,
   no calories, no diet language, framed as process and effort.
2. **Persists past the next measurement cycle (~90 days), or a rojo reading appears**: a
   conversation with the family, sharing the observed pattern in neutral terms — never a
   label, never a diagnosis.
3. **Rojo that persists, or other warning signs accumulate** (persistent fatigue, mood
   changes, frequent illness, sleep disruption, a disclosed menstrual irregularity): refer to
   a health professional. The coach never diagnoses or treats — notice, talk, and refer.

**When to generate the referral note**: only from a rojo reading, via "Generar nota de
remisión" (`GET /api/athletes/{athlete_id}/body-composition/referral-note.pdf`, coach/admin
only). The note describes the observed pattern neutrally — initials only, age band, sex,
the pattern's reason codes, approximate weekly training hours — contains no diagnosis, label,
percentage, millimetre value or target, names no professional or institution, and states that
raw measurement history is attached only with the family's explicit authorization. Generating
it is logged as `skinfolds.referral_note_generated`.

## 4. Anti-patterns (non-negotiable)

See `research-safeguards-referral.md` §6 for the full list and its sourcing. In short: never
show a number to the athlete or on a family surface; never rank or compare athletes by
leanness; never use this data for talent selection; never measure in public; never make a
measurement mandatory or penalize a decline; never measure more than every 90 days; never
treat a single set as a trend; never let the coach diagnose or "treat" a pattern; never pick
a race-based equation intercept; never pair this data with calorie or weight-loss talk aimed
at the athlete; never substitute a BIA scale for skinfolds with a minor; never trust an
uncalibrated measurer's number as precise — complete §0 first.
