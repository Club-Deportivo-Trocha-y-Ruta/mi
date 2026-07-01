# Quickstart / Validation: Coach Dashboard — Phase A

Frontend-only feature. Backend unchanged. Validate via vitest + manual smoke.

## Prerequisites

```bash
cd frontend && npm install
```

## Run tests

```bash
cd frontend && npm run test -- dashboard        # unit/integration for the changed surfaces
cd frontend && npm run test -- MeasurementAlerts
```

## Validation scenarios (map to spec acceptance)

### V1 — No N+1 (US1 / FR-001, FR-002)
- Mock `GET /api/alerts` returning N athletes; render `DashboardPage`.
- **Expect**: request spy shows the `/alerts` call and **zero** `GET /api/athletes/{id}` calls; the three cards render correct values.

### V2 — Cards derive correctly (US1-AC2)
- Given alerts with known `last_measurement_date`s and statuses.
- **Expect**: "Total atletas" = athletes count; "Última evaluación" = max date (or "--"); "Estado PHV" = "V de A con medición vigente".

### V3 — Truncation + sort + link (US2 / FR-003)
- Given 40 actionable athletes across `overdue`/`due_soon`/`never`.
- **Expect**: ≤8 rows; order overdue(desc days)→due_soon(asc)→never; "Ver todas (40)" links to `/athletes`. With ≤8 actionable → no link.

### V4 — Cross-club isolation (US3 / FR-005, NFR-003) — PRIVACY
- Mock `/alerts` for coach of club X returning only club X athletes (backend guarantee G1); include a separate fixture proving club Y / seed athletes are absent from the payload.
- **Expect**: no club Y / seed athlete (`ConsentTest`, `<script>…</script> Test`) renders in any block. This test encodes the access-control guarantee.

**T010 privacy sign-off (2026-07-01):**
- (a) Field surface check: `DashboardPage` / `useDashboardStats` / `MeasurementAlerts` read only `athlete_id`, `athlete_name`, `measurement_status`, `last_measurement_date`, `days_overdue`, `current_phv_status`, `growth_velocity_cm_month`, `growth_alerts`, `training_implications` — all declared on `AthleteAlert` (`frontend/src/types/alerts.types.ts`). No DOB, document ID, address, contact, or CRITICAL-category field is read or rendered. `athlete_name` (MEDIUM) is appropriate for a coach-only view. PASS.
- (b) Log check: `grep -rn "console\." frontend/src/hooks/athletes/useDashboardStats.ts frontend/src/hooks/athletes/useAlerts.ts frontend/src/components/dashboard/MeasurementAlerts.tsx frontend/src/routes/dashboard/DashboardPage.tsx` plus the new test files under `__tests__/` → zero matches. No PII in logs/console. PASS.
- (c) V4 test inspection (`frontend/src/routes/dashboard/__tests__/DashboardClubScope.test.tsx`): confirmed by manual mutation (temporarily injecting a forbidden name into an `overdue` fixture, observed the assertion fail, then reverted) that the negative assertions (`queryByText`/`innerHTML` checks for `ConsentTest`, `<script>…</script> Test`, `"Club Y Atleta Ficticio"`) are load-bearing, not tautological. Scope note: since this feature is frontend-only, actual cross-club filtering (backend guarantee G1) is out of scope for this test — it verifies (1) the frontend renders nothing beyond what `getAlerts` returns (no accidental XSS-payload/leaked-fixture rendering) and (2) `getAlerts` is called with no explicit `club_id` param, so scoping is never weakened by an unintended frontend override of the backend's JWT-derived scope. This is the correct and complete guarantee achievable at the frontend layer.

**Overall: PASS.**

### V5 — Explicit states (US3-AC3/4, FR-006)
- alerts pending → loading placeholders; alerts error → error state; `athletes: []` → explicit empty state ("No tienes atletas…"); cards show "--" consistently, never other-club/seed data.

### V6 — PHV formula (US4 / FR-004)
- A athletes, V with status ∉ {overdue, never} → card shows "V de A con medición vigente"; A=0 → "--".

### V7 — training_implications (US5 / FR-007)
- Rapid-growth athlete with non-null `training_implications` → text rendered; null → existing generic guidance, no empty gap.

### V8 — Accessibility
- `jest-axe` on `DashboardPage` → no violations; touch targets and links keyboard-reachable.

## Manual smoke (optional)

```bash
cd frontend && npm run dev
# login as entrenador@trochyruta.com / Coach2026! → /dashboard
# DevTools Network: confirm one /api/alerts, zero /api/athletes/{id}; list ≤8 rows + "Ver todas".
```

## Definition of done

- [x] V1 — No N+1 (`DashboardPage.test.tsx`, `DashboardClubScope.test.tsx`)
- [x] V2 — Cards derive correctly (`useDashboardStats.test.ts`, `DashboardPage.test.tsx`)
- [x] V3 — Truncation + sort + link (`MeasurementAlerts.test.tsx`)
- [x] V4 — Cross-club isolation (`DashboardClubScope.test.tsx`) — privacy sign-off T010 above, PASS
- [x] V5 — Explicit states (`DashboardPage.test.tsx`)
- [x] V6 — PHV formula (`useDashboardStats.test.ts`)
- [x] V7 — training_implications (`MeasurementAlerts.test.tsx`)
- [x] V8 — Accessibility (`DashboardPage.a11y.test.tsx`, jest-axe, 0 violations)
- [x] `npx tsc --noEmit` clean (no `eslint` script exists in `frontend/package.json`)
- [x] No backend/migration diff; no new sensitive field surfaced (T010 field-surface check)
- [x] `npm run test -- dashboard MeasurementAlerts useDashboardStats` → **9 test files, 54/54 tests passed**, 0 regressions (2026-07-01)
- [x] Final observed dashboard request count: **1× `GET /api/alerts`, 0× `GET /api/athletes/{id}`** (asserted via request spy in `DashboardPage.test.tsx` / `DashboardClubScope.test.tsx`, matches manual smoke expectation above)
