# Spec — AI Analysis per-round v2 (Race Insights)

## 1. Metadata

| Field | Value |
|---|---|
| Version | v2 |
| Status | Approved |
| Owner | `product-manager` |
| Approver (coach) | Juan Diego (Trocha y Ruta) |
| Approval date | 2026-05-25 |
| Phase | 1.9 — AI Analysis per-round |
| Feature flag | n/a — always active (single gate: `AI_ENABLED`) |
| Replaces | Analysis v1 (single global narrative replicated across N rows) |
| Internal dependencies | Task #4 `head-coach` (guardrails and veto), Task #3 `data-platform` (schema, scrubbing, privacy policy), Task #5 `family-relations` (parent email, label) |
| Related documents | `docs/10-race-results/runbook-v2.md` (devops-engineer), `backend/app/services/race/prompts/race_analyst_v2.md` (fastapi-architect) |
| PM memory | `~/.claude/agent-memory/product-manager/project_race_analysis_v2_spec.md` |

## 2. Problem

v1 generated a single global narrative per analysis and replicated it as `analysis_text` in the N rows of `athlete_ai_insight` corresponding to the N rounds of the athlete. Observed consequences:

- In the coach UI, the 5 previews of an athlete showed identical text, confusing the user about which round they were viewing.
- The data model violates 1NF: the same narrative string is stored duplicated N times, complicating individual edits (correcting an analysis from Round III requires rewriting all 5 rows).
- The single narrative could not simultaneously describe each event, synthesize longitudinal trends, and project forward: it ended up being either too generic or biased toward the last round.
- The monthly newsletter to parents (Phase 1.8) and the coach dashboard were coupled to a narrative that could not be specialized by audience or temporal focus.

## 3. Decision

Each AI analysis per-athlete will produce, for each round covered in the run, **3 independent sections** and, optionally, **1 season summary** generated on-demand:

1. **What happened (Round N)** — descriptive of event N.
2. **Journey so far** — trend analysis V1 → N.
3. **Where they're heading** — actionable prescriptions for rounds N+1 to end of season.
4. **Season summary** — executive synthesis, generated only on explicit request (not in every run).

The 4 existing rows in `athlete_ai_insight` per athlete-season are preserved; each row will store the 3 sections in discrete columns/JSON (no schema refactor — see §10).

## 4. Contract per section

| Section | Max words | Tone | Temporal focus | Prohibitions |
|---|---|---|---|---|
| What happened (round N) | 120 | Descriptive, objective | Only event N | Value-laden adjectives, comparisons between athletes, use "the athlete" instead of pseudonym |
| Journey so far | 120 | Analytical trend | V1 → N | Absolute ranking ("is N° X"), "rivals with", competitive language between athletes |
| Where they're heading | 120 | Actionable prescriptive | N+1 to end of season | "Goal podium", prescribe intervals for <13 year olds, any phrase from the hard veto list (§7) |
| Season summary (on-demand) | 200 | Executive synthesis | Entire season | Real names, comparative between club athletes |

All sections also apply global guardrails: no real names (use pseudonym `forbidden_names`), no medical terms without context, no nutritional recommendations for minors, no outcome promises.

## 5. Acceptance criteria

| ID | Criterion | How measured |
|---|---|---|
| CA-1 | 0 identical narratives between the 3 sections of the same round | `hash(text)` different in the 3 sections; assertion in integration test per run |
| CA-2 | 0 narratives with similarity ≥0.85 between "What happened" sections of different rounds in the same analysis | Levenshtein normalized by length over pairs of sections in the same analysis |
| CA-3 | 100% of sections respect `max_words + 10%` | Word count post-render; truncated or regenerated if exceeded |
| CA-4 | 0 occurrences of real name in any section | Regex against dynamic `forbidden_names` loaded from DB at run time |
| CA-5 | "Where they're heading" contains ≥1 actionable verb (prioritize/reduce/maintain/incorporate/adjust/consolidate) and ≥1 reference to the theoretical framework (`docs/01-marco-teorico.md`) | Post-generation lint |
| CA-6 | "Journey so far" references ≥N-1 prior rounds when N≥2 | Count of explicit mentions of "Round I/II/III/..." |
| CA-7 | p95 analysis time ≤25s in Render Free (4 rounds, 1 athlete) | Metric in Langfuse + runbook dashboard |
| CA-8 | Head Coach guardrails approved (sample 5 analyses) | Sign-off documented by `head-coach` in `project_race_analysis_v2_spec.md` |
| CA-9 | Privacy policy approved by Data Platform (180d scrubbing, `pii_scrubbed_at`) | Sign-off documented by `data-platform` |
| CA-10 | Coach validates sample of 5 analyses pre-GA rollout | Checklist signed by Juan Diego before Stage 3 |

## 6. Cap 4 rounds per run

Each analysis covers **maximum 4 rounds per execution**, regardless of how many rounds the athlete has in the season.

**Justification**:
- Gemini quota (`gemini-2.5-flash-lite`) on the free tier: the sum of prompt tokens (statistics + context + 4 target sections) and response (≈ 480 words + JSON wrapper per round) fits within `AI_MAX_TOKENS=8192` without truncation.
- p95 ≤25s in Render Free is only achievable with ≤4 concurrent rounds in the agentic graph.
- If the season has >4 covered rounds, the coach explicitly selects which ones enter the run; the rest remain with the prior version and can be regenerated in a second run.

## 7. Hard veto phrases (closed literal list)

Closed list; any expansion requires a new version of the prompt (`prompt_version`). If the model emits any of these phrases (case-insensitive and normalized matching), the section output is invalidated and regenerated (max 1 retry):

- "debe ganar"
- "tiene que llegar al podio"
- "necesita más horas"
- "más intensidad"
- "trabajo de potencia para superar a"

## 8. Rollout plan (4 stages)

v2 deploys as always-on (no feature flag). Emergency rollback: redeploy of the previous binary in Render Dashboard (see `runbook-v2.md` §1). If CA-4 fails (real name) in production: immediate rollback + post-mortem.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Gemini quota exhausted in peak hours | Cap 4 rounds/run + serialized queue per club + alert when monthly usage exceeds 70% |
| asyncio timeout in agentic graph under load | Hard timeout 30s per node + circuit breaker in `race_analyst_v2` |
| Infinite loop when regenerating due to hard veto | Max 1 retry per section; if fails, mark section as `manual_review` and notify coach |
| Migration incompatible with MySQL Hostinger 8.4 | Test migration on prod clone before Stage 2; rollback script prepared |
| Parent UI shows "v2" badge by mistake | The visible label to the parent is always "Coach Analysis" — the `prompt_version` badge is internal and not serialized in parent endpoints |
| Silent regression from v1 on deploying v2 | Contract tests on v1 rows read (not written) during Stage 4 |
| `forbidden_names` with loose regex that lets through variants (uppercase/accents/diminutives) | Unicode normalization + expanded list with known nicknames loaded from DB in each run |

## 10. Non-goals

- **NO** comparison between club athletes in any section.
- **NO** AI-generated charts — the already-implemented SVG macros (Phase 1.8) are reused.
- **NO** "for parents" version of the analysis: parent communication lives in the monthly newsletter (Phase 1.8) with its own narrative.
- **NO** schema refactor of `athlete_ai_insight` in this scope: the 4 rows per athlete-season are maintained; the 3 sections live in columns/JSON within each row.
- **NO** expansion of the hard veto list without a `prompt_version` bump.
- **NO** parent email outside of A rounds (IV, CD, VI).

## 11. Family communication

- Parent email: triggered only for **A** rounds in the 2026 calendar (IV Cali 17-May, CD Ginebra 12-Jun, VI Roldanillo 12-Sep).
- Label visible to parent: **"Coach Analysis"** (never "AI Analysis", never the `prompt_version` badge).
- Any internal identifier (`prompt_version=race_analyst_v2`, Langfuse run IDs) is kept out of parent role payloads.

## 12. Cross-references

- Operational runbook: `docs/10-race-results/runbook-v2.md` (owner `devops-engineer`).
- System prompt and few-shots: `backend/app/services/race/prompts/race_analyst_v2.md` (owner `fastapi-architect`).
- PM consolidated decisions: `~/.claude/agent-memory/product-manager/project_race_analysis_v2_spec.md`.
- Theoretical framework (citations for "Where they're heading"): `docs/01-marco-teorico.md`.
- Monthly newsletter (parent audience): `docs/` Phase 1.8, `AthleteMonthlyNewsletter` module.

## 13. Implementation calendar

Phase 1.9 — AI Analysis per-round. Start after spec approval; sequence will depend on the workflow generated by `fastapi-architect` and `devops-engineer` based on this document.
