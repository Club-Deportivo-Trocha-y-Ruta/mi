# Quickstart / Validation Guide: Competitive Anxiety Assessment

End-to-end scenarios proving the feature works. Run against the dev stack. No production minor data.

## Prerequisites

```bash
# Backend (from repo root)
source backend/.venv/bin/activate
cd backend && alembic upgrade head        # applies the new anxiety_* migration
uvicorn app.main:app --reload

# Frontend
cd frontend && npm run dev

# Or full stack (runs migrations + seed)
docker compose up
```

Seed provides: coach `entrenador@trochyruta.com` / `Coach2026!`; athletes across both age bands; Copa Valle calendar (Race A events: IV-Cali, Dptal-Ginebra, VI-Roldanillo). Ensure each test athlete has an active `psychological_assessment` guardian consent (set via the consent flow / seed).

## Scenario 1 — Age-driven selection + under-13 guard (US1, FR-002/003)

1. As coach, create an assessment for an 11-year-old → instrument is **SAS-2** automatically.
2. Create one for a 14-year-old → **CSAI-2R** by default.
3. Try to override the 11-year-old to CSAI-2R → expect a **warning** (422) and success only with `override=true` (recorded).

**Expected**: correct auto-selection; override blocked without acknowledgment.

## Scenario 2 — Group pre-race config in < 2 min (SC-001)

1. As coach, `POST /assessments/batch` for a group linked to a Race A event.
2. Confirm each athlete gets an assessment + a one-time answer token; consent-missing/override-needed athletes are flagged but don't fail the batch.

**Expected**: full configure-and-send completes under 2 minutes.

## Scenario 3 — Athlete answers via token (US2, FR-007/008/010)

1. Open `GET /answer/{token}` on a phone-sized viewport → items shown one at a time, 1–4 scale, español, no clinical text.
2. Submit complete answers → `status: completed`, short encouraging message only.
3. Reopen the same token → **410** (single-use).
4. Verify `answers_json` persisted item-by-item.

**Expected**: mobile-accessible (WCAG AA, no horizontal scroll); token single-use; item answers stored.

## Scenario 4 — Scoring correctness (US3, FR-009/011/012)

1. Submit a known CSAI-2R answer set → each subscale = (sum/n)×10 in range 10–40 (7 somatic / 5 cognitive / 5 self-confidence).
2. Submit a partial set → averaged over answered, `is_partial=true`.
3. `POST /recompute` → identical scores from stored answers.
4. Confirm self-confidence is **not** reverse-scored.

**Expected**: deterministic, recomputable scores matching the official key.

## Scenario 5 — On-demand interpretation + fallback (US4, FR-013/014/015/016)

1. With `AI_ENABLED=true`, `POST /assessments/{id}/interpret` → JSON with `resumen`, `por_dimension`, `estrategias` (2–3), `mensaje_para_el_atleta`, `banderas`; `source: "llm"`; result cached.
2. Verify no diagnostic language; mastery-climate framing; interpretation references the athlete's baseline.
3. Set `AI_ENABLED=false` (or simulate provider failure) and interpret another assessment → valid same-schema result with `source: "rule"`.
4. Feed sustained high-anxiety + low-confidence → a flag recommending an individual conversation / professional referral appears.

**Expected**: actionable, safe, baseline-anchored output; fallback always returns the schema.

## Scenario 6 — Dashboards (US5)

1. Open the individual panel → three scores, evolution vs. April baseline, interpretation, flags.
2. Open the group panel for a Race A event → athletes grouped by dominant pattern (somatic / cognitive / confidence) for warm-up + huddle.

**Expected**: clear three-pattern triage; alerts surfaced.

## Scenario 7 — Historical import (US6, FR-021)

1. `POST /import` a CSV with item-by-item columns + metadata (include a CSAI-2 27-item file).
2. Confirm rows scored with the correct key, baselines seeded where data permits, series charted.

**Expected**: 100% of valid rows scored and charted (SC-004).

## Scenario 8 — Privacy & consent gates (FR-023/024/027)

1. Remove `psychological_assessment` consent for an athlete → assessment creation returns **409**.
2. Inspect logs and AI provider prompt payloads → **no** real athlete names/DOB (pseudonyms only).
3. Confirm **no** automatic messages were sent to athletes or parents.

**Expected**: consent enforced; minors privacy upheld; human-in-the-loop preserved.

## Automated checks

```bash
cd backend && pytest tests/ -k anxiety        # scoring, selection, interpretation, routers, import
cd frontend && npm run test -- anxiety        # vitest + axe for questionnaire & dashboards
```
