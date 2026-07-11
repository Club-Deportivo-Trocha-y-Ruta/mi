# Quickstart — 028 Frontend Design Foundation & Everyday Reliability

Validation guide proving the feature end-to-end. Details live in [plan.md](plan.md), [research.md](research.md), [contracts/](contracts/).

## Prerequisites

```bash
cd frontend && npm install          # brings sonner, @fontsource/cal-sans, new ui/ primitives
cd backend && source .venv/bin/activate && pip install -r requirements.txt   # no new deps expected
docker compose up                   # full stack with seed data (dev credentials in CLAUDE.md)
```

## Automated validation

```bash
# Frontend: unit + a11y (jest-axe on new/changed pages & dialogs must be zero-violation)
cd frontend && npm run typecheck && npm test

# Regression tests that MUST exist and pass (fail on unfixed code):
#  - AthleteLink renders span for admin / link for coach (4 call sites covered)
#  - CalendarPage day click navigates with ?date= prefill
#  - ConfirmDialog tone="danger" focuses Cancel on open; Escape dismisses; focus returns
#  - Season helper derives current year (no 2026 literal)
#  - AthleteNewslettersDashboardPage issues exactly ONE summary request (MSW spy), not N
#  - RubricSteppers: 4 groups render discrete options with accessible names/values

# Backend: summary endpoint (happy + RBAC 403 + validation 422 + no-N+1 assertion)
cd backend && pytest tests/ -k newsletter_summary

# E2E (Chromium preinstalled; do NOT run playwright install)
cd frontend && npm run test:e2e -- e2e/target-size.spec.ts   # every interactive target ≥48×48
```

## Manual validation scenarios

1. **Rubric with gloves (US1)**: open today's session → Asistencia → rubric: all four scales are tap-steps ≥48 px; values save per row with visible confirmation. On a 360 px viewport steps wrap, never shrink.
2. **Dead-end sweep (US2)**: as `admin@trochyruta.com`, from Dashboard alerts and a competition's Atletas/Insights tabs, athlete names render as plain text (no silent bounce). Throttle network to "Offline" on Sesiones/Atletas/Dashboard/Calendario → each shows "Reintentar" and recovers when back online; during backend cold start the waking banner shows instead of errors.
3. **Feedback language (US3)**: delete a media item → ConfirmDialog (not `window.confirm`), Cancel focused, Escape works. Generate a newsletter → button shows "Generando…" spinner → sonner toast on completion. Walk both wizards with a screen reader: each step change announces its heading.
4. **One product (US4)**: headings across Dashboard/Sesiones/Competencias render Cal Sans (inspect: `font-family` starts with "Cal Sans", loaded from the app bundle, zero external font requests in the Network tab). Status badges on newsletters/consents/sync show icon+label with token colors.
5. **Calendar prefill (US2)**: tap an empty day → event form opens with that date filled.
6. **Performance guard (SC-009)**: Lighthouse (mid-tier mobile, slow 4G/3G) on `/dashboard` and `/athletes`: LCP ≤ 2.5 s; `npm run build` route-bundle sizes within +10% of baseline.

## Expected outcomes

All checklist items in [spec.md](spec.md) Success Criteria SC-001…SC-009 hold; zero jest-axe violations; target-size spec green; newsletter overview issues exactly one status request regardless of roster size.
