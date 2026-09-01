# Quickstart: Validating Feature 036 — AI Insights Tab Review

How to prove each wave works end to end. References: [spec.md](./spec.md) (acceptance scenarios), [contracts/athlete-race-analysis-api.md](./contracts/athlete-race-analysis-api.md), [data-model.md](./data-model.md).

## Prerequisites

```bash
# Backend
cd backend && source .venv/bin/activate
alembic heads          # MUST show a single head before and after the T021 migration
alembic upgrade head
uvicorn app.main:app --reload          # :8000

# Frontend
cd frontend && npm run dev             # :5173

# Full stack with MySQL + MailHog (seeded demo data)
docker compose up
```

AI stack: use `AI_ENABLED=false` / the `fake` provider for every flow test except the golden eval, which needs a real race AI key (`pytest -m golden`).

## Wave 1 — Correctness (US3, US4)

**Athlete switch (US3)** — coach role, tab open on athlete A with insights selected and a run active → navigate client-side to athlete B with `?tab=ai_analysis` preserved. Expect: empty selection, no sticky bar, no run timeline, no HITL card, no network request pairing A's insight IDs with B's athlete ID (check the browser network panel).

**Orphan runs (US3)** — start a run, kill the backend process, restart. Expect: the run row is `failed` with an explanatory `error_message`; the frontend stops polling and shows the failure, not an infinite spinner.

**Fallback marking (US4)** — force a provider failure (fake provider error mode). Expect: history row visibly marked as unavailable, no newsletter checkbox, retry affordance present; `POST` attach with the fallback ID via API directly returns 422.

```bash
pytest tests/routers/test_athlete_race_analysis.py -k "fallback or orphan"
npx vitest run src/components/athletes/ai/AthleteAIAnalysisTab.test.tsx
```

## Wave 2 — Truth on screen (US5)

Walk the tab as coach and as parent against the checklist in spec.md US5. Fast checks: two Departmental Championships render distinguishably in the picker; "Válida N" formatting identical across sub-tabs; history ordered by race date; Distribution sub-tab opens with data; no "TODO Sprint 3" note anywhere; parent empty state is gender-neutral; a 409 from `POST /runs` shows the backend's Spanish detail.

## Wave 3 — Analysis quality (US2)

```bash
# 1. The eval must exercise production's pipeline (v2 + anthropic/claude-sonnet-5)
pytest -m golden          # BEFORE the prompt fix: must FAIL on the new sub-rubrics
# 2. After T054–T057 land:
pytest -m golden          # composite ≥ 0.75 with repeated-figure + connector rubrics included
```

Manual: regenerate analyses for a seeded athlete with ≥ 4 válidas. Each text must reference a prior ride, name a direction of change, close with a recommendation, repeat no figure, and contain no lap filler sentence. N=1 athlete: no invented trend.

## Wave 4 — Devices and accessibility (US6)

```bash
npm run test:e2e -- target-size.spec.ts      # now includes /athletes/:id?tab=ai_analysis
npx vitest run src/components/ai/HITLApprovalCard.test.tsx   # axe() resting + dialog-open
```

Manual at 360 px (devtools): every sub-tab reachable, sticky bar announced (`role="status"`), keyboard-only pass through sub-tabs → comparator → HITL with no trap. Verify `recharts` is out of the initial bundle: `npm run build` and check the athlete-detail chunk.

## Wave 5 — E2E safety net (US7)

```bash
npm run test:e2e          # coach happy path, launch→HITL→approve, parent path, athlete switch
pytest                    # admin-role + parent-denial coverage on all 8 endpoints
```

Final gate (SC-007): cherry-pick each Story 3–5 defect onto a scratch branch and confirm at least one new test fails per defect.

## Definition of done per wave

Lint + typecheck green (`ruff check`, `npm run build`), suites green, and the wave's spec acceptance scenarios pass manually. Update `docs/implementation-status.md` and `docs/technical-notes.md` at feature close — not `CLAUDE.md`.
