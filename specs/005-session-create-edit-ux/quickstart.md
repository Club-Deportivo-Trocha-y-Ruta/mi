# Quickstart — Session Create/Edit Flow & UX Overhaul

How to build, run, and validate this feature locally.

## Prerequisites

```bash
# Backend
source backend/.venv/bin/activate
cd backend && uvicorn app.main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

Dev login (coach): `entrenador@trochyruta.com` / `Coach2026!`.

## What changed (at a glance)

- **Backend** (no migration): `session_kind` + `objectives` now accepted/persisted/returned
  by create & update; `coach_notes` surfaced in the UI.
- **Frontend**: `SessionFormPage` becomes a 4-step wizard (General → Athletes → Route &
  Notes → Review) with inline validation, a blocking error summary, draft autosave/restore,
  enhanced athlete call-up, in-form route-file attach (auto-uploaded after create), and a
  clear parent-notification outcome.

## Manual verification (happy path)

1. Go to **Entrenamiento → Sesiones → Nueva sesión**.
2. **Step 1 General**: fill date, time, duration, location, focus, description; pick a
   **Tipo de sesión** chip and write **Objetivos**. Try "Siguiente" with a blank required
   field → inline error + step stays. Fill it → advances.
3. Reload the page mid-form → a **restore banner** appears; choose **Restaurar** → all
   fields (incl. tipo/objetivos) come back.
4. **Step 2 Athletes**: search, select several (chips appear, sticky count updates), try to
   advance with none selected → blocked with message.
5. **Step 3 Route & Notes**: add route text, a valid Strava URL, attach a `.gpx`, write
   coach notes.
6. **Step 4 Review**: confirm the summary (date, kind, athlete count), choose **Notificar a
   familias**, **Crear sesión**.
7. Expect: session created, route file uploaded, a clear notification outcome toast, draft
   cleared, navigation to the detail page.
8. Open the session detail and **Editar** → confirm **Tipo de sesión** and **Objetivos**
   persisted (the previously dropped fields).

## Automated checks

```bash
# Backend — the persistence regression + privacy tests
cd backend && pytest tests/routers/test_training_sessions*.py -q

# Frontend — wizard, draft, athlete select, a11y
cd frontend && npx vitest run src/**/*session*  && npm run lint && npx tsc --noEmit
```

## Acceptance gates (from spec Success Criteria)

- SC-001/008: `session_kind` + `objectives` round-trip on create AND edit (regression test
  goes red on pre-fix backend).
- SC-002: reload mid-form restores 100% of entered fields.
- SC-005: 0 axe violations on page + dialogs; all targets ≥48 px.
- SC-007: notification choice always yields an explicit outcome (success / failure-retry /
  no-recipients) — no silent failure.
- SC-010: route file attached during initial creation, no manual save-then-return.
