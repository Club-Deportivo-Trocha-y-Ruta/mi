# Quickstart: Cleanup Duplicate Competition

## What this feature does
A coach can remove a **no-results** duplicate competition together with its linked calendar event in
one confirmed action, from `/competitions`. Competitions that hold results are protected.

## Try it locally

1. Start the stack: `docker compose up` (runs migrations + seed). No new migration for this feature.
2. Log in as the coach: `entrenador@trochyruta.com` / `Coach2026!`.
3. Create the duplicate scenario (if not present): create a competition with no results and associate
   it to the calendar (kebab → "Asociar a calendario"). It now shows the "Calendario" badge and no
   "Con resultados" badge.
4. Open the kebab "..." on that competition → **"Eliminar duplicado"** (only visible to a coach on a
   competition without results).
5. Confirm in the dialog (it states the competition **and** its calendar event will be permanently
   removed).
6. Verify: the competition disappears from the list; open `/calendar` and confirm the duplicate
   calendar event is gone.

## Manual API check
```bash
# As coach (JWT in $TOKEN). Replace 42 with the duplicate's id.
curl -i -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/race-analysis/race-events/42/cleanup
# → 204 No Content

# A competition WITH results → 409
# A non-coach (admin/parent) → 403
# An already-removed id → 404
```

## Acceptance smoke (maps to spec)
- US1: coach removes a no-results competition + its calendar event in one step → list and calendar both
  updated. (SC-001, SC-002, SC-004)
- US2: a competition WITH results offers no "Eliminar duplicado" action; API returns 409 if forced.
  (SC-003, SC-005)
- Edge: no-calendar-event duplicate → only the competition is removed, no error. Already-deleted → 404.

## Tests to run
```bash
# Backend
cd backend && pytest tests -k "cleanup" -q
# Frontend
cd frontend && npm run test -- CompetitionsListPage
```
