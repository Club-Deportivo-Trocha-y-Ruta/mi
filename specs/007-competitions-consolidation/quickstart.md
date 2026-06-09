# Quickstart: Unified Competitions Module

**Feature**: 007-competitions-consolidation

## What this delivers
One `/competitions` module that is the only place for the full race lifecycle:
plan → import results + general standings → **view both tables** (club highlighted)
→ fix via diff re-ingest → link athletes + manage call-up roster → sync to calendar →
read AI insights. The separate `/coach/race-analysis` destination goes away.

## Coach happy path (manual verification)
1. **Create** a round at `/competitions/new` (leave "Crear evento en calendario" checked) → competition + linked calendar event exist.
2. **Import** at `/competitions/:id/import`: upload RESULTADOS (+ optional GENERAL) → parse → resolve matches → commit.
3. **Results tab**: see the finishing table per category; club athletes highlighted; toggle "solo mi club".
4. **Standings tab**: see season cumulative points; club highlighted.
5. **Athletes tab**: confirm/fix matches; build a call-up roster; see reconciliation (called-up vs results).
6. **Fix**: re-upload a corrected PDF at `/competitions/:id/import` → confirm diff → applied atomically; affected AI runs marked outdated.
7. **Edit** date/venue → linked calendar event updates.
8. **Insights tab** + `/competitions/insights/{athletes/:id,club,season/:year}` → AI views, no minor names.
9. Old links `/coach/race-analysis` and `/training/races/:id/club-insights` redirect into the module.

## Parent path
- Open a competition where their child raced → see only their child's result row; no other minors; no cross-round/club/season insights (403).

## Dev commands
```bash
# backend
source backend/.venv/bin/activate && cd backend
alembic upgrade head        # applies race_event_roster migration
uvicorn app.main:app --reload
pytest tests/routers/test_race_events_crud.py tests/routers/test_race_results_read.py -q

# frontend
cd frontend && npm run dev
npm run test -- competitions
npm run build               # check bundle budgets
```

## Done-when (acceptance, ties to spec SC-001..008)
- Full lifecycle completed without leaving `/competitions` (SC-001).
- Exactly one race sidebar entry; no duplicate/orphaned pages (SC-002).
- Per-event results + season standings viewable in-app, club highlighted (SC-003).
- Old deep links resolve during transition (SC-004).
- Correct-via-reupload in <3 min, atomic, downstream marked stale (SC-005).
- Parent never sees another minor; no minor names in AI output (SC-006).
- Full-field round renders responsively on mid-tier mobile (SC-007).
- Existing race tests pass; new capabilities covered incl. privacy + a11y (SC-008).
