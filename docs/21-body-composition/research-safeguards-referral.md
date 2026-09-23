# Body composition in minors — safeguards, interpretation bands, and referral criteria

**Status:** research only — not yet specified/implemented. **Audience:** coaching staff + engineering. **Scope:** the ethical, interpretive, and referral safeguards for adding skinfold-based body composition to the anthropometry module, for ~20 XCO athletes aged 9–15, mixed sex, Valle del Cauca, Colombia, measured by the coach (not ISAK-certified). This document is the safeguards/bands/referral companion to `research-protocol.md` (measurement protocol, equations, reference values) and `research-measurer-ux.md` (capture flow, family view); read together with `technical-fit.md` (data model, consent, privacy checklist).

This is a wellbeing/monitoring tool for a growing minor, never a diagnostic instrument. It translates the same spirit the project constitution already applies to psychological assessment (`.specify/memory/constitution.md`, Principle V) to a new data type: **wellbeing tool, not diagnosis; baseline-anchored interpretation; mastery climate; human in the loop; refer on persistence, never treat.**

Following `research-protocol.md`'s own convention, claims not independently verified against a primary source in this research pass are flagged **[unverified]**. Two of the three research sub-agents commissioned for this document returned unusable or incomplete output before the deadline for this draft; where their intended coverage (specific IOC REDs-2023 wording on minors, LEAF-Q's validated age range, and Colombia's institutional referral guidance) could not be independently confirmed, this is stated plainly as **[pending]** rather than papered over with invented citations.

---

## 1. Ethical position

Sport-science bodies converge on a small set of rules for assessing body composition in minors/adolescent athletes:

- **Who may measure, and how well.** ISAK accreditation sets a technical-error-of-measurement (TEM) ceiling of ≤7.5% (inter-tester) even for a certified Level 1 anthropometrist; untrained measurers have been found to run 2–4× that error and to overestimate body fat in the majority of cases (`research-protocol.md` §2/§6, citing a novice-vs-expert reliability study). **Practical consequence for this club: raw skinfold numbers from a non-certified coach are directional, single-measurer trend data — never a precise clinical figure** — and the coach should complete the structured self-calibration practice `research-protocol.md` §2 describes before any number is treated as trend-worthy.
- **Consent is active and revocable, not a one-time checkbox.** The AIS/National Eating Disorders Collaboration (NEDC) body-composition guidance (verified by fetch) requires parental/guardian consent for minors and states consent must be voluntary, "with no actual or perceived ramifications for self-exclusion" — an athlete or family can decline any single measurement or the practice altogether, with zero consequence to selection or standing.
- **Privacy of setting.** The same AIS-aligned guidance states group-setting assessment "should be avoided" and warns against "unjustified routine periodic screening." A 2024 systematic review of body image and anthropometry in athletes (PMC11129708, verified by fetch) recommends measuring away from teammates *and* coaches where feasible — stricter than what a small club can realistically implement, which is why private space, a chaperone, and a same-sex measurer preference (where feasible) are treated as first-class flow requirements, not settings buried in a menu (`research-measurer-ux.md` §9).
- **Body composition is confidential health information, addressed by a team, not a single adult's judgment call.** The IOC's 2023 RED-S consensus update and its companion "Best practice recommendations for body composition considerations in sport" (Mountjoy et al. 2023) state body composition data "should be treated as confidential medical information" and is "best addressed by a multidisciplinary healthcare team"; the REDs Clinical Assessment Tool (CAT2) is explicitly a screen → risk-stratify → **physician-led diagnosis** pipeline — a coach or screener never issues the diagnosis.
- **Feedback practice is the single biggest lever on harm.** The same 2024 systematic review found team weigh-ins associated with increased dietary restriction, and — in the subset of studies on adolescents specifically (ages 12–19) — 4 of 6 found a significant association between BMI/body-fat feedback and negative body image. The IOC 2023 consensus adds that "overfocus on being lighter or leaner increases the risk of REDs and disordered eating." Cyclist-specific disordered-eating risk evidence exists only for adult elite riders (a leanness-demand endurance sport); extrapolating that risk profile downward to 9–15-year-old XCO athletes is this document's own inference, not a youth-cycling-specific finding.
- **What could not be confirmed:** a distinct UK Sport body-composition protocol was not found — current UK material defers to the IOC framework (justification → consent → method selection → capture/interpretation → reporting). No distinct NCAA or USOPC body-composition *measurement* protocol was found (NCAA's disordered-eating resource documents high prevalence in college athletes but is silent on protocol). The 2013 BJSM Meyer/Sundgot-Borgen/Lohman survey paper was only accessible at abstract level; its 2023 IOC successor above is the citable, current standard and supersedes it in practice.

## 2. Interpretation bands (traffic light) — coach-only, never shown to the athlete

The scheme below is this document's own construction, built from `research-protocol.md`'s measurement-error and reference-value research. It exists to give the coach a consistent, honest read — **not** a diagnostic cutoff. Every "rojo" outcome routes to a conversation and, if it persists, a referral (§4) — never to a label, a goal, or self-management by the coach.

| Signal | 🟢 Verde | 🟡 Ámbar (coach conversation) | 🔴 Rojo (family conversation → consider referral) | Source | Confidence |
|---|---|---|---|---|---|
| Σ4 skinfold change (triceps+biceps+subscapular+calf), 6-month window | Change < ~7 mm in either direction — within measurement noise | Real change ≥ ~7–8 mm not explained by a concurrent growth pattern (see combined row below) | Real **fall** ≥ ~7–8 mm co-occurring with flat/falling weight and continuing height velocity | `research-protocol.md` §6: minimum-detectable-change derived from the ISAK 7.5% novice TEM ceiling (illustrative propagation, not a published figure for this exact site combination) | Reasonable club-specific construction from a published TEM formula — **not** an independently validated clinical cutoff. Coarse guidance only. |
| Percentile position, triceps+subscapular vs. Colombian reference | Roughly P10–P85 | P85–P95 (higher adiposity) or P5–P10 (lower adiposity) | ≥P95 or ≤P5, especially if the trend keeps moving further in that direction | Ramírez-Vélez et al. 2016, FUPRECOL study, Bogotá schoolchildren n=9,618 ages 9–17.9, CC BY (`research-protocol.md` §5/§11) | Best available *Colombian* reference — but a school population, not an athlete population, and measured on the left side (ISAK convention is right). Treat percentile as context, never a verdict. |
| BMI-for-age Z-score change | Drop < 0.5 SD over ~6 months | Drop of 0.5–1.0 SD over ~6 months | Drop ≥ 1.0 SD over ~6 months, or a full downward crossing of `classify_nutritional_status_bmi`'s bands (`backend/app/services/growth.py`) | General pediatric growth-monitoring convention | **[Unverified/pending]** — this document's extrapolation; no youth-*athlete*-specific validated cutoff was confirmed this pass. Never read alone — always alongside height velocity. |
| Height velocity vs. stage-expected range | Within or above the club's typical range | Below typical range for one measurement cycle | Below typical range for 2+ consecutive cycles, especially paired with the skinfold or BMI-z rojo rows | `docs/01-marco-teorico.md` §1 (Tanner & Davies 1985 envelope); already-implemented `EXPECTED_VELOCITY_CM_YEAR` in `growth_summary.py` | Solid, already club-canon for the velocity leg alone; combining it with the other rows is this document's own construction. |
| Combined pattern: weight flat/↓ **and** height still climbing **and** Σ4 falling ≥ MDC | Pattern absent (any leg missing) | Two of the three legs present | All three legs present, or two legs plus any RED-S warning sign from §3 | `research-protocol.md` §7, explicitly cross-linked to the RED-S framework in `docs/01-marco-teorico.md` §1/§7 | Explicitly a **pragmatic, non-validated combination rule.** Each leg has its own separate evidence base; no study validates this exact three-part screen. Coarse guidance only — a prompt to talk, never a diagnosis. |

**The single most important interpretive fact for the motivating case:** Loomba-Albrecht & Styne (2009), *Effect of puberty on body composition* (Curr Opin Endocrinol Diabetes Obes 16(1):10–15) — during puberty, boys gain disproportionately more fat-free/skeletal mass while **girls gain significantly more fat mass**, a normal, hormonally-driven divergence. A rising Σ4 in a girl at/after her growth peak is, on its own, very often the *expected* pattern — not evidence of a training or nutrition problem. This is why the table above never fires "rojo" from a rising Σ4 alone; it fires from a **falling** Σ4 combined with stalled weight and continuing height growth, the RED-S-consistent pattern.

## 3. RED-S / low energy availability in 9–15-year-olds

The club's own theoretical framework already treats RED-S as club-canon (`docs/01-marco-teorico.md` §1/§7): the IOC's low-energy-availability threshold of **<30 kcal/kg fat-free mass/day** and the growing-athlete target of **≥45 kcal/kg FFM/day**. Two extensions for this document, both should be read as caveated:

- **IOC REDs 2023 update and the CAT2 clinical assessment tool.** CAT2 is a physician-facing screen → stratify → diagnose pathway (§1) built primarily around adult and late-adolescent athlete presentations (menstrual history, bone density, lab markers). **[Pending]** — whether the 2023 consensus text itself contains explicit guidance for applying CAT2, or a modified version of it, to pre-pubertal or early-adolescent (9–13) athletes was not independently confirmed in this research pass; do not assume CAT2 is validated as a stand-alone pediatric instrument until this is checked directly against the published consensus.
- **LEAF-Q.** The Low Energy Availability in Females Questionnaire (Melin et al. 2014) was developed and validated on adult/late-adolescent female athletes. **[Pending]** — the exact lower age bound stated in the validation literature was not independently re-confirmed this pass, but every secondary description of LEAF-Q this document's authors are aware of ties it to post-menarcheal, adult-pattern menstrual history questions, which are structurally inapplicable to a pre-menarcheal 9–12-year-old. **Do not administer LEAF-Q, or any adapted version of it, to this club's athletes** until that validation gap is closed by a professional — the instrument's own item content assumes a physiology this age group frequently does not yet have.

What a coach *can* legitimately observe, without any instrument, questionnaire, or diagnosis — this list is already club-canon (`docs/01-marco-teorico.md` §8, "Sleep, recovery, and warning signs"): persistent fatigue, recurring/chronic pain, decreased performance, frequent illness, loss of appetite, elevated resting heart rate, loss of enthusiasm, irritability, sleep disorders, social withdrawal, academic decline. Two additions specific to body composition, both to be *received if disclosed*, never *proactively asked* in a way that compromises dignity: delayed or absent menarche, or a menstrual irregularity, in a girl who has already disclosed her cycle to a trusted adult; and a Σ4/weight pattern matching §2's rojo row.

**Escalation ladder — same shape as Principle V's for psychological signals:** an isolated ámbar signal → a private, food-first coach conversation with the athlete, no numbers, no calories, no diet language → if it persists past one more measurement cycle (~90 days, per `research-protocol.md` §8) or a rojo signal appears → a conversation with the family sharing a neutral pattern (never a label) → referral to a health professional via `head-coach-lead` (§4). **The coach never diagnoses and never treats; the coach notices, talks, and — when the pattern warrants it — refers.**

## 4. Referral pathway in Colombia / Valle del Cauca

**Routes available (general Colombian healthcare-system structure — not sport-specific)** [pending sport-specific institutional confirmation]:

- **EPS (public insurance) route:** medicina general first, requesting remisión to pediatría (or pediatría with an endocrinología/nutrición focus if the general pediatrician flags a growth concern) or to nutrición y dietética. This is typically the accessible default for most club families in Valle del Cauca.
- **Particular/private route:** direct consultation with a **nutricionista-dietista**, ideally with pediatric or sports experience, or a **pediatra** (general, or pediatra endocrinólogo for a growth-specific concern). Faster, but out-of-pocket — the club should present both routes neutrally and let the family choose.
- **Ministerio del Deporte / talent-identification guidance:** **[gap — not found]**. This research pass did not locate a substantive, citable Ministerio del Deporte (or legacy Coldeportes) document on youth body-composition assessment or talent identification. Treat this as an open gap, not evidence that no such guidance exists — worth a direct inquiry to the Liga Vallecaucana de Ciclismo or Ministerio del Deporte before publishing anything that claims institutional backing.
- **Colegio Colombiano de Nutricionistas y Dietistas** or an equivalent professional body: **[gap — not found]** in this pass; a professional referral does not require citing one, but it would strengthen the club's printed referral-note template if a directory or endorsed-professional list exists.

**What the coach hands over — never a label, always a neutral pattern:**

1. A plain description of the observed pattern (e.g., "stable weight, continuing height gain, and a skinfold-sum decrease beyond our measurement margin, over the last 6 months") — no clinical or diagnostic terms.
2. The raw longitudinal series (height, weight, Σ4, dates) **only with family authorization** to share it outside the club (Ley 1581 third-party-sharing rule, §7).
3. Training context (approximate weekly hours/sessions) so the professional can weigh energy expenditure.
4. Explicit acknowledgment that this is a coach observation, not a clinical impression.

**Sample referral note (Spanish — this is a real end-user artifact, handed to a family/professional):**

```
Nota de remisión — seguimiento de crecimiento y composición corporal

Deportista: [iniciales o identificador interno — nunca el nombre completo en un
sistema digital; el nombre completo solo si el documento se entrega en papel,
en mano, con autorización de la familia]
Edad: [rango, ej. 12-13 años]      Sexo: [M/F]

Motivo de la nota: El club ha observado [patrón objetivo, ej. "una disminución
en la suma de pliegues cutáneos por encima de nuestro margen de medición,
junto con un peso estable y una talla que continúa aumentando dentro de lo
esperado, en los últimos 6 meses"], en el contexto de entrenamiento de
ciclismo de montaña (aprox. [X] horas/semana).

Esta nota NO incluye un diagnóstico, una clasificación de peso o de
composición corporal, ni una recomendación clínica — esas decisiones quedan
en manos del profesional tratante.

Se adjunta (con autorización expresa de la familia): historial de mediciones
de talla, peso y pliegues cutáneos de los últimos [periodo].

Contacto para coordinar: [acudiente / entrenador a cargo], [teléfono o correo]
```

## 5. What families and athletes should see

| Audience | Sees | Rationale |
|---|---|---|
| **Coach** | Full numbers: Σ4 in mm with sparkline, %BF/FFM estimate labeled "estimado," per-site history, the traffic-light band and its trigger reason | The coach is the human in the loop who must be able to judge, question, and act on the pattern — hiding numbers from the person responsible for noticing would defeat the tool's purpose. |
| **Family** | Band + one narrative sentence only — **no %BF numeral, no Σ mm numeral** | `research-measurer-ux.md` §8's own recommendation, extending the existing "never *obesidad* as a headline" precedent (`docs/18-growth-module-redesign/proposal.md`, decision D3) to an even more sensitive number: a raw Σ mm is still a comparable, gameable figure even without a %BF conversion. This is a recommendation to confirm with the coach (open question in `research-measurer-ux.md` §10.5), not a settled decision. |
| **Athlete** | Nothing numeric, ever, automatically. A conversation only if and when the coach judges it appropriate, always framed as process/effort, never a body-fat number, a weight-loss goal, or a comparison to teammates | Mirrors Principle V's "human in the loop" and "mastery climate always" rules verbatim, and this agent's own non-negotiable against calorie/number talk with a minor. |

**Sample Spanish copy — family band card ("Composición corporal"), band + narrative only, mirroring `FamilyBandCards.tsx`'s existing tone:**

- 🟢 **Verde** — Etiqueta: *"En su curva esperada"*. Narrativa: *"La composición corporal de tu hijo/a se mantiene dentro de lo esperado para su etapa de desarrollo. Sigue acompañando el proceso — esto va de la mano de un crecimiento saludable."*
- 🟡 **Ámbar** — Etiqueta: *"En observación"*. Narrativa: *"Notamos un cambio que vale la pena conversar. El entrenador se pondrá en contacto contigo para revisarlo juntos — no es una alarma, es una oportunidad de acompañar mejor a tu hijo/a."*
- 🔴 **Rojo** — Etiqueta: *"Requiere acompañamiento profesional"*. Narrativa: *"Identificamos una señal que amerita una valoración con un profesional de la salud. El entrenador ya está coordinando contigo los siguientes pasos — este acompañamiento adicional es normal y forma parte de cuidar bien a los deportistas en crecimiento."*

**Sample Spanish copy — coach-only in-app prompt (never shown to family/athlete):**

- Ámbar: *"⚠️ Cambio a revisar — Composición corporal. La suma de pliegues de [atleta] cambió más allá del margen de medición desde la última toma, sin un patrón de crecimiento claro que lo explique. Sugerencia: conversa en privado con el/la deportista y la familia, sin mencionar números ni porcentajes. Si el patrón se repite en la próxima medición o aparecen otras señales (fatiga persistente, cambios de ánimo, enfermedad frecuente), pasa a seguimiento con la familia."*
- Rojo: *"🔴 Señal combinada — considerar remisión. El patrón de [atleta] combina peso estable, talla que sigue creciendo y una caída real en la suma de pliegues — compatible con baja disponibilidad energética. Esto NO es un diagnóstico. Conversa con la familia en lenguaje neutro (nunca calorías ni peso frente al/a la deportista) y coordina con head-coach-lead la remisión a un profesional de salud."*

**Sample Spanish copy — consent addendum (append to the existing anthropometry consent explanation, `ParentalConsent.anthropometry`):**

> *"Además de talla y peso, el club también podría tomar pliegues cutáneos (una medición no invasiva con un instrumento tipo pinza, en sitios como el brazo, la espalda y la pantorrilla) para acompañar el proceso de crecimiento de tu hijo/a. La realiza el entrenador en un espacio privado, respetando siempre el derecho de tu hijo/a a decir que no en cualquier momento, sin ninguna consecuencia. Los resultados se usan solo para el seguimiento individual — nunca para comparar deportistas entre sí, ni como una meta a alcanzar. Si en algún momento identificamos una señal que amerite la opinión de un profesional de la salud, te la compartiremos directamente para decidir juntos los siguientes pasos."*

(Whether this addendum requires a privacy-policy version bump, per `technical-fit.md` §8, is a product decision for `head-coach-lead`/the real coach — flagged here, not decided.)

## 6. Anti-patterns

Each item below is traceable to a source in §1 or to `research-protocol.md` §10 (marked accordingly), and each is a hard *must not*, not a preference:

1. **Never show %BF, FFM, or the raw Σ mm number to the athlete, or on any parent-facing screen.** (§1 body-image evidence; `research-protocol.md` §4/§10)
2. **Never rank or publicly compare athletes by leanness; no leaderboard.** (§1 IOC 2023 confidentiality; `research-protocol.md` §10; club's existing mastery-climate rule)
3. **Never use skinfold or body-composition data for talent identification or team/roster selection.** (`research-protocol.md` §10)
4. **Never measure in public or in front of teammates; private space, chaperone, same-sex measurer where feasible.** (§1 AIS-aligned guidance; `research-measurer-ux.md` §9)
5. **Never make a measurement mandatory or penalize a decline — full or per-site.** (§1 AIS consent rule: voluntary, "no ramifications for self-exclusion")
6. **Never schedule measurement on an unjustified routine — cap at every 90 days, never more often.** (§1 "unjustified routine periodic screening should be avoided"; `research-protocol.md` §8)
7. **Never treat a single measurement as diagnostic — always require ≥2 points and a trend.** (`research-protocol.md` §10, same philosophy already used for height/weight/PHV)
8. **Never let the coach diagnose, label, or "treat" a concerning pattern — notice, talk, and refer.** (§1 IOC CAT2 physician-led diagnosis; constitution Principle V; this agent's own non-negotiable)
9. **Never guess a "race" category to pick a Slaughter-equation intercept for a Colombian child.** (`research-protocol.md` §3 — no scientific basis for the choice in this population; use the race-free triceps+calf equation)
10. **Never pair body-composition tracking with a weight-loss goal, calorie talk, or restrictive-diet language directed at the minor.** (§1 IOC 2023 REDs/disordered-eating link; this agent's "no calorie counting," "no caloric restriction," "no forbidden foods" non-negotiables)
11. **Never substitute a BIA scale/handheld device for skinfolds with minors.** (`research-protocol.md` §10 — hydration and puberty itself swing BIA readings exactly when precision matters most)
12. **Never trust a raw number from an uncalibrated measurer as precise.** Require the self-calibration practice period (§1; `research-protocol.md` §2/§6) before treating any figure as more than directional.

## 7. Colombian regulatory context

- **Resolución 2465 de 2016 (MinSalud).** Confirmed directly from the club's own implementation (`backend/app/services/growth.py`, docstrings citing "Artículo 1, Cuadro No. 3"): the resolution defines classification only for **height-for-age, BMI-for-age, and weight-for-age**, ages 5–17. It defines **no** skinfold or body-fat-percentage classification. **This matters operationally: the club's skinfold/Σ4 tool is not, and cannot be presented as, an "official classification" under Colombian law** — it must stay framed as an internal, educational/operational monitoring tool, exactly the same posture the constitution already requires for the psychological-assessment module (a wellbeing tool, not a diagnosis).
- **ENSIN (Encuesta Nacional de la Situación Nutricional).** Per `research-protocol.md` §5 (citing the club's own `docs/04-percentiles/research.md`), ENSIN's routinely published child/adolescent indicators are height/weight/BMI-based; no confirmed evidence surfaced in either research pass that ENSIN nationally collects skinfold data. A specific numeric claim about national skinfold trends was found during research but could not be confidently attributed to ENSIN — **[unverified, excluded here]**.
- **Ley 1581 de 2012 (protección de datos personales).** Already treated as bedrock throughout this codebase and constitution (health data of a minor is sensitive data; Ley 1581 governs it). For this feature specifically: sharing a minor's growth/skinfold history with an external professional (§4) is a **third-party transfer of sensitive health data belonging to a minor**, which requires the parent/guardian's explicit authorization for that specific purpose — the consent addendum in §5 and the "solo con autorización expresa" line in the referral-note template (§4) are how this document operationalizes that requirement. The exact article-level citation was not re-verified live in this pass; the general principle (sensitive-data category, minor's-data extra protection, purpose-bound third-party sharing) is not in question given how the rest of this project already relies on it, but a precise article number should not be asserted without checking the statute text directly.
- **Ministerio del Deporte de Colombia.** No substantive youth-talent/body-composition guidance document was located in either research pass — see §4's gap note.

## 8. References

- AIS/NEDC — Body Composition Considerations. https://www.ausport.gov.au/ais/disorderedeating/resources/ais-resources/body-composition-assessment
- AIS/NEDC position statement on disordered eating in high-performance sport (PMC). https://pmc.ncbi.nlm.nih.gov/articles/PMC7588409/
- Australian Athletics — Body Composition Assessment Guidelines. https://coachathletics.com.au/coaching-education/body-composition-assessment-guidelines
- 2023 IOC consensus statement on Relative Energy Deficiency in Sport (REDs) — Mountjoy et al. https://www.olympics.com/ioc/news/ioc-publishes-new-consensus-statement-on-relative-energy-deficiency-in-sport-reds-to-protect-athlete-health
- Best practice recommendations for body composition considerations in sport (IOC REDs subgroup, 2023). https://www.researchgate.net/publication/374201888
- Body composition for health and performance (Meyer, Sundgot-Borgen, Lohman et al., 2013 — abstract-level access only). https://pubmed.ncbi.nlm.nih.gov/24124039/
- How to minimise the health risks to athletes who compete in weight-sensitive sports (Sundgot-Borgen, Meyer et al., 2013). https://www.semanticscholar.org/paper/f5e16b9e53880532d0537ed5131f6beb467d3afd
- Associations between anthropometry, body composition, and body image in athletes: a systematic review (2024). https://pmc.ncbi.nlm.nih.gov/articles/PMC11129708/
- Eating disorder risks and awareness among female elite cyclists (2022). https://link.springer.com/article/10.1186/s13102-022-00563-6
- Muscularity-oriented disordered eating in cyclists (2024). https://link.springer.com/article/10.1186/s40337-024-01109-6
- ISAK — International Society for the Advancement of Kinanthropometry. https://www.isak.global/
- Standards for Anthropometry Assessment (TEM standards). https://www.researchgate.net/publication/333585249
- NCAA — Disordered Eating. https://www.ncaa.org/sports/2025/2/27/disordered-eating.aspx
- Ramírez-Vélez R, et al. (2016). Triceps and Subscapular Skinfold Thickness Percentiles and Cut-Offs for Overweight and Obesity in Schoolchildren and Adolescents in Bogotá, Colombia (FUPRECOL). *Nutrients* 8(10), 595. https://pmc.ncbi.nlm.nih.gov/articles/PMC5083983/
- González-Ruíz K, et al. (2018). Comparison of BIA, Slaughter Skinfold-Thickness Equations, and DXA for Estimating Body Fat in Colombian Children/Adolescents with Excess Adiposity. *Nutrients* 10(8), 1086. https://pmc.ncbi.nlm.nih.gov/articles/PMC6115719/
- Loomba-Albrecht LA, Styne DM (2009). Effect of puberty on body composition. *Curr Opin Endocrinol Diabetes Obes* 16(1), 10–15. https://pubmed.ncbi.nlm.nih.gov/19115520/
- Kasper AM, et al. (2021). Come Back Skinfolds, All Is Forgiven. *Nutrients* 13(4), 1075. https://www.mdpi.com/2072-6643/13/4/1075
- Ackland TR, et al. (2012). Current Status of Body Composition Assessment in Sport (IOC position statement). *Sports Medicine* 42(3), 227–249. https://pubmed.ncbi.nlm.nih.gov/22303996/
- Sibling documents (this feature, same folder): `research-protocol.md`, `research-measurer-ux.md`, `technical-fit.md`.
- Existing project references: `docs/01-marco-teorico.md` (§1 RED-S/maturity-offset uncertainty, §7 nutrition/RED-S, §8 warning signs), `docs/04-percentiles/research.md`, `docs/18-growth-module-redesign/proposal.md` (decision D3), `.specify/memory/constitution.md` (Principle V, lines 160–200).

**Open gaps for a follow-up research pass** (do not treat as resolved): (a) live-verified text from the 2023 IOC REDs consensus on CAT2's applicability to pre-pubertal/early-adolescent athletes; (b) LEAF-Q's exact stated validated age range; (c) any Ministerio del Deporte de Colombia or Colegio Colombiano de Nutricionistas y Dietistas guidance; (d) a precise Ley 1581 article-level citation for minor's sensitive-data third-party sharing.
