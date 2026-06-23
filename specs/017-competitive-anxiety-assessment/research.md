# Phase 0 Research: Competitive Anxiety Assessment

Research process used **MCP** (Context7 for FastAPI/SQLAlchemy/React patterns) and **web search** (instrument validation literature). No minor data was used in any query.

## R1. Instrument structure & scoring keys

**Decision**: Ship the official item→subscale keys as **loaded data** (`backend/app/data/anxiety_keys/*.json`), not hard-coded item text; scoring reads the key. Verified structure against literature; item wording comes from the licensed source (Human Kinetics for CSAI-2/2R) and is not committed if license-restricted (the repo stores the *mapping* and ranges, with item text provisioned by the club).

- **CSAI-2R (17 items, default, 13–15)**: 3 subscales — Somatic (7), Cognitive (5), Self-confidence (5). Subscale score = (sum of items / n items) × 10 → range **10–40**. Published item mapping: somatic = {1,4,6,9,12,15,17}, cognitive = {2,5,8,11,14}, self-confidence = {3,7,10,13,16} (verify against the club's licensed copy before enabling).
- **CSAI-2 (27 items, import-only)**: 9 items per subscale; subscale = sum → range **9–36**; total 27–108. Note: classic CSAI-2 self-confidence items are scored positively; some legacy datasets reverse-key item 14 — the loader records per-item reverse flags so historical imports compute correctly.
- **SAS-2 (15 items, 10–12)**: Somatic (5) + Cognitive split into Worry (5) + Concentration Disruption (5). Follow the SAS-2 official key; we expose Cognitive = Worry + Concentration Disruption to keep the 3-dimension UI (cognitive/somatic/self-confidence), noting SAS-2 has no self-confidence subscale → self-confidence shown as N/A for that instrument.

**Rationale**: Keeps scoring deterministic, recomputable (FR-010), and license-clean. **Alternatives considered**: hard-coding items (rejected — license + maintainability), computing only totals (rejected — loses subscale triage, the core value).

**Open verification (to /implement)**: exact SAS-2 reverse items and the club's licensed CSAI-2R Spanish wording (Andrade et al. 2007 validated the Spanish version, 4-point Likert 1="nada"–4="mucho").

## R2. Self-confidence is not reverse-scored

**Decision**: Treat self-confidence as an independent positive dimension (higher = better); never invert it into "anxiety". **Rationale**: matches the instruments and Constitution V. **Alternative**: folding it into an anxiety total — rejected (psychometrically wrong, breaks interpretation).

## R3. Baseline & trend

**Decision**: Baseline = the athlete's first qualifying assessment (target April / early-season diagnostic window), stored per athlete **and per subscale** in `anxiety_baselines`. Interpretation compares each new subscale vs. baseline (relative change); absolute coarse bands (10–40: low ≤19 / moderate 20–29 / high ≥30; 9–36: low ≤17 / moderate 18–27 / high ≥28) are guidance only. When no baseline exists, the first assessment becomes baseline and the interpretation flags "sin línea base". **Rationale**: FR-014, Constitution V. **Alternative**: population cutoffs — rejected (none exist; clinical-looking).

## R4. Instrument change across age band

**Decision**: When an athlete crosses 12→13 mid-season, switch instrument (SAS-2→CSAI-2R), keep both series but mark them non-comparable; do **not** stitch a single trend line across instruments. **Rationale**: FR-022 edge case. **Alternative**: rescaling SAS-2 to CSAI-2R units — rejected (no validated cross-walk).

## R5. On-demand interpretation + cache (LLM)

**Decision**: Mirror the existing agentic insight pattern (`athlete_ai_insight` + `AgentRun` + `app/services/ai`): a new `AnxietyInterpretationUseCase(BaseUseCase)` with a Jinja prompt (`anxiety_interpretation_v1.j2`) returning the fixed JSON schema; triggered by a coach "Analizar" action and cached on the assessment (regenerate supersedes). Always run output through `Guardrails.scrub` (pseudonyms; no real names to the provider) and validate JSON; on provider error/timeout/invalid JSON, fall back to `rule_interpreter.py` producing the **same schema**. `AI_LOG_PROMPTS=false` in prod. **Rationale**: cost/latency control, human-in-the-loop, reuse, FR-013/015/016. **Alternatives**: auto-run on submit (rejected — cost, contradicts human-in-loop) or no-LLM rule-only (rejected — loses nuance, but kept as fallback).

**Context7 confirmation**: SQLAlchemy 2 async `selectinload` for dashboard eager-loading; FastAPI dependency-injected `get_db` + RBAC dependency — both already standard in this repo.

## R6. Guardian consent reuse

**Decision**: Reuse `parental_consents` rather than a new consent table. Add a `psychological_assessment` consent scope (new boolean column on `parental_consents`, defaulting false; Alembic migration). Per clarification, the **coach** verifies/records that consent exists before creating an assessment; the canonical consent grant remains the parent's. Assessment creation is blocked (HTTP 409/422) when the athlete lacks an active `psychological_assessment` consent. **Rationale**: FR-023, data minimization, single source of truth for consent. **Alternative**: standalone consent record (rejected — duplicates the existing privacy model and its withdrawal logic).

## R7. Athlete access via one-time token

**Decision**: `anxiety_response_tokens` — opaque, single-use, assessment-scoped, expiring token (no athlete login; athletes stay `can_login=false`). The coach shares the link; submitting consumes the token. **Rationale**: clarification CL-002 (no athlete app this version). **Alternatives**: enabling athlete login (rejected — scope/auth surface for minors) or coach-entered answers only (kept as a secondary path but not primary).

## R8. CSV historical import shape

**Decision**: CSV with one column per item (e.g., `i1..i17`) plus metadata columns (`athlete_ref`, `instrument`, `date`, `event_ref?`); instrument inferred from column count/`instrument` column; per-item answers persisted; scored via the same `scoring.py`. Partial rows averaged + flagged. **Rationale**: CL-001, FR-010/021, recomputable. **Alternatives**: per-subscale-only CSV (rejected — not recomputable) or JSON (rejected — coaches export from spreadsheets).

## Sources

- [CSAI-2 / CSAI-2R database entry — ArabPsychology](https://db.arabpsychology.com/scales/competitive-sport-anxiety-inventory-2-csai-2-2/)
- [Propiedades psicométricas de la versión española del CSAI-2R (Andrade et al.) — ResearchGate](https://www.researchgate.net/publication/28170321_Propiedades_psicometricas_de_la_version_espanola_del_Inventariode_Ansiedad_Competitiva_CSAI-2R_en_deportistas)
- [Validation of the French version of the CSAI-2R (incl. direction scales) — ResearchGate](https://www.researchgate.net/publication/223882499_Validation_of_the_French_version_of_the_Competitive_State_Anxiety_Inventory-2_Revised_CSAI-2R_including_frequency_and_direction_scales)
- [Psychometric re-evaluation of the CSAI-2R — ResearchGate](https://www.researchgate.net/publication/235925589_Psychometric_re-evaluation_of_the_revised_version_of_the_Competitive_State_Anxiety_Inventory-2)
