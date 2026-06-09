# Quickstart / Manual Verification: One-click associate a competition to the calendar

**Feature**: 008-associate-competition-calendar

Verifies the feature end-to-end in the dev environment. Run as the **coach** (`entrenador@trochyruta.com` / `Coach2026!`).

## Prerequisites

```bash
docker compose up          # backend + MySQL + migrations + seed
cd frontend && npm run dev  # frontend
```

You need at least one competition (válida) **without** a linked calendar event. Create one via Competitions → "Crear competencia" with the "Crear evento en calendario" checkbox **unchecked**, or use a seeded válida that has no event.

## Scenario A — One-click associate (User Story 1, P1)

1. Open the competition detail page for the unlinked válida (`/competitions/:id`).
2. Confirm the **"Asociar a calendario"** action is visible and there is **no** "En calendario" badge.
3. Click the primary one-click action.
4. **Expect**: a success toast; the action disappears and the **"En calendario"** badge appears — with **no form and no typing**.
5. Open the club calendar on the válida's date.
6. **Expect**: an **all-day** event whose title = the competition name and whose location = the competition venue.

✅ Pass criteria: SC-001 (one action, zero entry), SC-002 (matches name/date/venue, all-day), SC-003 (linked state reflected).

## Scenario B — Edit details first (User Story 2, P2)

1. On another unlinked válida's detail page, choose the **"Editar detalles primero"** option.
2. **Expect**: the calendar event form opens **pre-filled** with the competition's title, date, and venue (event type = Competencia, válida preselected, all-day on).
3. Change the title (e.g., append " — XCO"), then save.
4. **Expect**: event created and linked with the edited title; returning to the competition shows "En calendario".

## Scenario C — No duplicate (FR-009)

1. On a válida already linked (e.g., after Scenario A), confirm the "Asociar a calendario" action is **gone**.
2. (API) `POST /api/race-analysis/race-events/{id}/calendar-event` for an already-linked válida → **409**, no second event created.

## Scenario D — Coach-only (FR-008)

1. Log in as **admin** or **parent** and open the same válida (admin) — the one-click action MUST NOT perform the association; `POST .../calendar-event` with a non-coach token → **403**.

## Automated tests

```bash
# Backend
cd backend && pytest tests/routers/test_race_event_calendar_autocreate.py tests/services/test_calendar_sync_all_day.py

# Frontend
cd frontend && npm run test -- CompetitionDetailPage
```
