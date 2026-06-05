# Phase 0 Research: RPE OMNI Scale Labels

**Question driving this research** (from the coach, via `/speckit-plan` input "research the web for a better answer"): On a 0–10 perceived-exertion scale, where should "moderate" sit, and what are the scientifically validated verbal anchors? The current UI labels value **3** as "Moderado", which the coach finds confusing.

## Evidence gathered (web)

### Finding 1 — Validated OMNI scales place "moderate" at the MIDDLE, not at 3

The OMNI Picture System (Robertson et al.) uses a 0–10 numeric range with verbal descriptors placed **at equal intervals**. The **adult OMNI** verbal anchors are, by construction, symmetric around the midpoint:

| Value | Adult OMNI anchor |
|------:|-------------------|
| 0 | Extremely easy |
| 2 | Easy |
| 4 | Somewhat easy |
| 6 | Somewhat hard |
| 8 | Hard |
| 10 | Extremely hard |

The "easy↔hard" transition (the perceptual midpoint, i.e. "moderate" effort) lands at **5–6**, never at 3. This directly confirms the coach's intuition.

### Finding 2 — Children's OMNI-Cycle uses a fatigue framing, rest→max

The **children's OMNI-Cycle** version (validated for ages 8–12, the closest to our 10–15 riders, with HR/VO₂ correlations of 0.85–0.94 in children 9+) anchors **0 = "not tired at all"** and **10 = "very, very tired"**, with intermediate tiredness wording rising monotonically. Same shape: the mild/moderate band is in the lower-middle, the heavy band in the upper.

### Finding 3 — The modern 0–10 "training" scale agrees

Contemporary 0–10 RPE guidance maps: **3–4 = easy** (full conversation), **5–6 = moderate** (phrases), **7–8 = hard/threshold** (few words), **9–10 = very hard to max** (single words). "Moderate" = 5–6. This also dovetails with the club's own talk-test cues in `docs/01-marco-teorico.md` (Z1–2 easy conversation, Z3 short sentences, Z4 1–2 words, Z5 cannot speak).

### Finding 4 — The current implementation is scientifically wrong

The current `RPE_LABELS` array places "Moderado" at index 3 and compresses the entire upper half into near-synonyms of "difícil"/"máximo" (Algo difícil, Difícil, Muy difícil, Muy muy difícil, Extremo, Máximo casi, Máximo). This both mis-locates "moderate" and gives the coach almost no usable discrimination across 4–10.

## Decision

**Decision**: Re-map the descriptor words across 0–10 so they rise symmetrically with "Moderado" centered at **5**, grounded in the adult-OMNI easy↔hard structure and compatible with the children's fatigue framing and the club's talk-test language. Keep one short word per integer (the coach's chosen "re-map words to numbers" approach), keep the 0–10 numeric scale, and keep the stored value semantics unchanged.

**Final Spanish mapping** (español neutro, Colombia):

| Value | Descriptor (`RPE_LABELS`) | OMNI/training reference | Talk-test cue |
|------:|---------------------------|-------------------------|---------------|
| 0 | Reposo | Extremely easy / not tired | — |
| 1 | Muy fácil | — | conversación total |
| 2 | Fácil | Easy | conversación total |
| 3 | Ligero | — | conversación cómoda |
| 4 | Algo fácil | Somewhat easy | frases completas |
| 5 | **Moderado** | **midpoint (easy↔hard)** | frases cortas |
| 6 | Algo duro | Somewhat hard | frases cortas |
| 7 | Duro | hard / threshold | 1–2 palabras |
| 8 | Muy duro | Hard | 1–2 palabras |
| 9 | Muy muy duro | — | casi sin hablar |
| 10 | Máximo | Extremely hard / very, very tired | no puedo hablar |

**Rationale**:
- Places "Moderado" at the center (value 5), resolving the reported confusion and matching three independent validated references.
- Monotonic, evenly spread, symmetric (fácil ↔ duro around Moderado) — satisfies spec FR-003 and FR-004.
- Uses "duro" (effort) rather than only "difícil" (difficulty/judgment) for the upper half, which reads more neutrally to a young athlete and gives the coach real discrimination across 6–10.
- Even-indexed words (0,2,4,6,8,10) map onto the validated adult-OMNI anchors; odd-indexed words are deliberate interpolations so every integer still shows exactly one word (spec FR-002). This is a documented UX choice, not a deviation from the science.
- Talk-test column is optional secondary/helper copy if the team later wants tooltips; not required for the core change.

**Emoji faces (`RPE_FACES`)**: realign so the face progression matches the new wording (calm/rested at 0, neutral around 5, strained at 10) — spec FR-008. Current array is already an 11-emoji rest→exhaustion ramp; verify the midpoint face reads as "moderate/neutral" rather than "tired" and adjust if needed.

## Alternatives considered

- **Talk-test phrasing as the primary descriptor** (e.g., "Solo 1–2 palabras"): scientifically clean and consistent with the reference doc, but longer strings crowd the slider on a tablet and change the visual style more than the coach asked for. Rejected as primary; kept as optional helper copy.
- **Switch to a different scale (Borg 6–20, or 1–10)**: rejected — the OMNI 0–10 is the validated scale the club already standardized on; changing the numeric range would invalidate stored history and the `BETWEEN 0 AND 10` contract.
- **Anchor only even values, blank the odd ones** (most literal to the validated scale): rejected because the UI is a continuous slider with a face per integer; blanks would read as missing data. We interpolate odd values instead and document it.

## Sources

- [Children's OMNI Scale of Perceived Exertion: mixed gender and race validation (Med Sci Sports Exerc)](https://journals.lww.com/acsm-msse/Fulltext/2000/02000/Children_s_OMNI_Scale_of_Perceived_Exertion__mixed.29.aspx) / [PDF](https://paulogentil.com/pdf/Children's%20OMNI%20scale%20of%20perceived%20exertion%20mixed%20gender%20and%20race%20validation.pdf)
- [Children's OMNI Scale: Walking/running evaluation (PDF)](https://paulogentil.com/pdf/Children's%20OMNI%20Scale%20of%20Perceived%20Exertion%20walking-running%20evaluation.pdf)
- [Exercise Intensity Self-Regulation using the OMNI Scale in Children (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3541455/)
- [OMNI Exertion Scale / OMNI Picture System (APTA)](https://www.apta.org/patient-care/evidence-based-practice-resources/test-measures/omni-exertion-scale)
- [Rate of Perceived Exertion: Practical Guide (BodySpec)](https://www.bodyspec.com/blog/post/rate_of_perceived_exertion_practical_guide_and_calculator)
- Internal: `docs/01-marco-teorico.md` §"RPE as the primary tool" (talk-test cues, OMNI 0–10 validation).
