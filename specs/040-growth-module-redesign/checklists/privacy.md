# Privacy audit — feature 040 (growth module redesign)

T065 — mandatory `data-privacy-guard` audit per `CLAUDE.md` ("The
`data-privacy-guard` audit is mandatory for any feature touching
athlete-identifiable data"). Scope per the task: growth components
(`frontend/src/components/athletes/growth/**`), the growth-summary
endpoint/service (`backend/app/routers/growth.py`,
`backend/app/services/growth_summary.py`), the recompute/backfill report
and logs (`backend/app/scripts/backfill_anthropometry.py`), export file
names, the coach-audience AI prompt and its context builder
(`backend/app/services/ai/use_cases/phv_explainer.py`,
`backend/app/services/ai/prompts/phv_explanation_coach_v1.md`,
`backend/app/services/ai/context_builders.py`, `backend/app/routers/ai.py`),
and MSW/test fixtures for real-looking names. Reviewed the full working
tree (branch `feat/040-growth-module-redesign`, `git diff main` vs the
enumerated scope plus adjacent call sites wired by it).

Reviewed against Ley 1581/1098 categories (CRITICAL: DOB, ID docs, address,
medical data, guardian contacts, identifiable photos; HIGH: individual
anthropometry, maturation status, individual performance, attendance).

## Findings

| Severity | File:line | Finding | Status |
|---|---|---|---|
| — | — | No CRITICAL or HIGH findings. | N/A |

No findings required a code fix. Nothing was changed by this audit.

### LOW-severity notes (informational only, no action required)

| # | File:line | Note |
|---|---|---|
| L1 | `frontend/src/components/athletes/growth/GrowthCurveSection.tsx:149` | `console.error("Error exportando gráfica:", err)` logs the raw error object from `html-to-image`'s `toPng()` failure. In practice this is a canvas/encoding error with no athlete data in it, and it never fires in the passing test suite, but it is an unstructured `console.error` on a component that renders individual anthropometric data — flagging so a future pass considers logging only `err instanceof Error ? err.message : String(err)` for defense in depth, consistent with the `type(exc).__name__`-only convention already used in `backend/app/routers/ai.py`. |
| L2 | `frontend/src/components/athletes/growth/PercentileToolbar.tsx` (export button) / `GrowthCurveSection.tsx:132-146` | Confirms a positive: the PNG export filename is `crecimiento-${indicator}-${Date.now()}.png` (no athlete id/name/DOB) and the captured DOM region (`exportRef`) wraps only the chart/table/interpretation block — the toolbar and any athlete-identifying header sit outside it. No action needed, noted because export surfaces are a common leak vector. |
| L3 | `backend/app/services/ai/context_builders.py:63-106` (`_sanitize_training_implications`) | Confirms a positive: the coach's free-text `training_implications` is run through a name-like regex and an anti-diagnostic pattern list, truncated to 300 chars, and dropped from the context entirely if empty after sanitization — before it ever reaches the LLM prompt (family or coach audience). No action needed. |

## What was checked

- **`GET /athletes/{id}/growth-summary`** (`backend/app/routers/growth.py`,
  `backend/app/schemas/growth.py`, `backend/app/services/growth_summary.py`):
  payload is `athlete_id` + dates + numbers only — no name, no DOB, no
  notes. `build_growth_summary` is a pure function over already-fetched
  ORM rows (no extra queries, no logging). Router relies on
  `verify_athlete_access` (RBAC unchanged) for admin/coach/parent scoping.
  Existing regression test `backend/tests/routers/test_growth_summary.py`
  (11 cases, incl. explicit privacy invariant asserting
  `"first_name"`/`"last_name"`/`"birth_date"` never appear in the response
  body) and `backend/tests/services/test_growth_summary.py` (19 cases) —
  both re-run green (37/37, see Tests below).
- **`backend/app/scripts/backfill_anthropometry.py`**: `recompute_to_source`
  writes `growth_band_changes_<YYYYMMDD>.json` under `backend/data/`
  (gitignored) containing only `athlete_id`/`record_id`/indicator/band
  transition — no name, no DOB. The one `logger.info` call and the two
  `print()` statements in `run()` emit aggregate counts only
  (`scanned`/`recomputed`/`unchanged_status`/`len(band_changes)`). Verified
  against `backend/tests/scripts/test_backfill_anthropometry.py`, which
  asserts fictional first/last name and DOB constants
  (`_ATHLETE_FIRST`/`_ATHLETE_LAST`/`_ATHLETE_DOB`,
  `_RECOMPUTE_ATHLETE_FIRST`/`_RECOMPUTE_ATHLETE_LAST`/`_RECOMPUTE_ATHLETE_DOB`)
  never leak into captured stdout, the JSON report, or the report's string
  serialization.
- **Growth components** (`frontend/src/components/athletes/growth/**`):
  no component renders `athlete.first_name`/`last_name`/`birth_date`.
  Evaluation dates are consistently obfuscated to "mes año"
  (`formatMonthYear`, duplicated on purpose in `PercentileChart.tsx`,
  `PercentileTable.tsx`, `FamilyStageCard.tsx` per each file's own
  docstring) — never the exact day. `PercentileChart`/`PercentileTable`
  show Z-score/percentile/clinical band label (HIGH-category data) only in
  coach mode (`preset="coach"`, the default); `preset="family"` /
  `FamilyBandCards.tsx` show only an icon + `StatusBadge` + narrative
  sentence from `getBandVocabulary(...).familyLabel`/`.narrative` — never
  the numeric Z-score/percentile or the clinical `coachLabel`, matching
  FR-016. No `localStorage`/`sessionStorage` usage anywhere in the folder.
  No raw hex colors (colors are all `var(--color-*)` tokens, confirmed by
  the module docstrings and spot-checks in `PercentileChart.tsx`).
- **AI audience split** (`backend/app/services/ai/use_cases/phv_explainer.py`,
  `backend/app/services/ai/prompts/phv_explanation_coach_v1.md`,
  `backend/app/services/ai/context_builders.py`,
  `backend/app/routers/ai.py`): the coach prompt adds velocity (cm/año) and
  months-from-PHV but stays within the same
  `ATHLETE_CONTEXT_ALLOWED_KEYS` allowlist as the family prompt — no
  z-score/percentile, no name, no exact DOB (only `age_decimal` rounded to
  1 decimal and `age_group`/`category` buckets). Both prompt templates
  instruct the model to never use the athlete's name ("tu deportista" /
  "su hijo/a") and never compare against other athletes or the club
  population. `_ensure_audience_allowed` is a real 403 barrier in both the
  cached-read (`GET`) and generate (`POST`) endpoints — a parent requesting
  `?audience=coach` is rejected even though `verify_athlete_access` would
  otherwise grant them the athlete. Frontend (`PHVExplanationCard.tsx`,
  `usePHVExplanation.ts`, `api/ai.ts`) partitions the React Query cache by
  `(athleteId, audience)` and the parent-mode call site
  (`GrowthTab.tsx::ParentGrowthTab`) hardcodes `audience="family"` +
  `readOnly` — never lets a parent request the coach variant from the UI.
  `PHVExplanationResponse` schema carries no name/DOB/z-score.
- **`MyAthleteDetailPage.tsx` (T062 wiring)**: the diff *removes* a
  previously-existing exact-date exposure to parents
  (`Evaluado: {latest.evaluation_date}`, full ISO day) in favor of
  `GrowthTab`'s `FamilyStageCard`, which shows the same fact obfuscated to
  month-year — a privacy improvement, not a regression.
- **MSW/test fixtures**: `frontend/src/test/msw/growthSummaryHandlers.ts`
  and every fixture under `frontend/src/components/athletes/growth/__tests__/`
  use clearly fictional labels (`"Atleta Ficticio/Ficticia"`,
  `"Persona Ficticia"`, `"Atleta Prueba"`). Backend fixtures in
  `backend/tests/scripts/test_backfill_anthropometry.py` use
  `"Juan Pérez Ficticio"` / `"Andrés Gómez Ficticio"` — same
  already-established project convention (explicit "Ficticio/a" marker), no
  unmarked plausible-real name introduced by this feature.
- **WHO LMS reference data** (`backend/app/data/who_lms/*.csv`,
  `backend/app/seed_growth_data.py`): public WHO population statistics
  (L/M/S parameters by age/sex), not athlete data — no PII risk.
- **No `.env` or key content**: grep across the reviewed scope for
  `api[_-]?key|secret|password|token=|\.env|AIza|sk-ant|sk-proj` found no
  matches outside the standard `Depends`/auth plumbing already in the
  codebase.

## Tests re-run as part of this audit

- `cd backend && .venv/bin/python -m pytest tests/routers/test_growth_summary.py tests/services/test_growth_summary.py tests/scripts/test_backfill_anthropometry.py -q` → **37 passed**.
- `cd frontend && npx vitest run src/components/athletes/growth/__tests__` → **13 files / 135 tests passed**.

## Result

Files reviewed: growth components (24 files incl. tests), `routers/growth.py`,
`services/growth_summary.py`, `scripts/backfill_anthropometry.py`,
`schemas/growth.py`, AI audience stack (`phv_explainer.py`,
`phv_explanation_coach_v1.md`, `context_builders.py`, `routers/ai.py`,
`PHVExplanationCard.tsx`, `usePHVExplanation.ts`, `api/ai.ts`),
`MyAthleteDetailPage.tsx` (T062 wiring), MSW/test fixtures.

Findings: 0 critical, 0 high, 0 medium (3 low, informational, no fix required)

Status: **APPROVED**
