# Quickstart — 032 Session Content Unification

Validation guide only — no implementation code. Cross-references `data-model.md` and `contracts/*` instead of repeating their content. Test obligations map to Constitution II (backend pytest + frontend vitest + jest-axe) and to the feature's SC-001..SC-007.

## Prerequisites

```bash
# Backend
source backend/.venv/bin/activate
cd backend && alembic upgrade head   # no new migration expected for this feature — confirms that assumption
cd backend && pytest                 # full suite green before starting

# Frontend
cd frontend && npm install
cd frontend && npm run test          # vitest, full suite green before starting
```

## Backend validation (new endpoint — contracts/attach-technique-to-session.md)

Test file: `backend/tests/technique/test_technique_attach_to_session.py` (new; follows the existing `backend/tests/technique/test_technique_assemble_combined_gymkhana.py` naming convention).

Run: `cd backend && pytest tests/technique/test_technique_attach_to_session.py -v`

Required cases (Constitution II: happy path + at least one negative path; this endpoint additionally needs the idempotency case since FR-009 is the reason it exists):

1. **Happy path**: coach attaches 2 new items to an existing session with no prior technique content → `201`, response `items` length 2, `mixes_age_bands` computed correctly for a mixed-age-band pair.
2. **Append onto existing content**: attach 1 item to a session that already has technique items from a prior call → `201`, response `items` includes both the old and new rows, old rows' `position` unchanged.
3. **RBAC negative**: parent and athlete roles → `403`.
4. **Not-found negative**: `training_session_id` belonging to another club → `404` (never `403` — club-existence must not leak).
5. **Validation negative**: empty `items` → `422`; unknown `exercise_id` → `422` with the id listed in `detail`.
6. **Idempotency (the regression test this endpoint exists to satisfy, FR-009)**: submit the identical `items` payload twice in a row → both calls `201`, final row count equals the first call's count (no duplicates). Assert directly against the DB row count, not just the response shape.
7. **Query-count / timing guard** (Constitution IV, no N+1): assert the endpoint issues a bounded, small number of queries regardless of `items` length (e.g. parametrize with 1 vs 5 items and assert query count does not scale linearly per item beyond the expected pattern).

## Backend regression — existing endpoints untouched

No new tests required for strength or intervals routers (no contract change — research.md R2/R3), but re-run their existing suites as a regression gate:

```bash
cd backend && pytest tests/strength -v
cd backend && pytest tests/technique -v   # existing tests must still pass unmodified
```

## Frontend validation

### Attach flows (MSW-mocked)

- `frontend/src/components/training/session-plan/__tests__/TechniqueAttachPicker.test.tsx` (new): multi-select → attach → success updates the Plan section's list; error preserves selections and allows retry; retry does not duplicate list items (mock the endpoint to simulate a "succeeded-but-client-saw-error" retry and assert the final rendered list is not duplicated).
- `frontend/src/components/training/session-plan/__tests__/StrengthBlockPicker.test.tsx` (new): list renders, attach succeeds, 409 (already-attached) renders as a soft notice not a blocking error.
- `frontend/src/routes/strength/__tests__/BlockBuilderPage.test.tsx` (extend or create): with `?session_id=123` present, the session is shown locked/read-only and the existing searchable radio list (`:355-377`) does not render; without it, the "which session?" picker (research.md R6) appears first; successful attach navigates to `/training/sessions/123?section=plan`.

### Session sections

- `frontend/src/routes/training/__tests__/SessionDetailPage.test.tsx` (extend or create): `?section=` sync — set each of the 4 values, assert the corresponding content renders and the others do not; omit `?section=` with a session dated today → `asistencia` renders by default; omit it with a session dated in the future → `resumen` renders by default; click a tab, assert `history` gained an entry (not `replace`-only) so back-navigation returns to the previous section; simulate a refresh (re-mount with the same URL) and assert the same section is still active (SC-006).
- Deep-link regression: mount with `?section=plan` directly (simulating a return-from-attach navigation) and assert `plan` is active without requiring a click.

### "Hoy" shortcut

- `frontend/src/components/training/__tests__/SessionFiltersBar.test.tsx` (extend): clicking "Hoy" sets the filter store to today's date (club timezone — assert against a fixed mocked `Date`, not wall-clock, to keep the test deterministic); with a seeded session today, the list shows exactly that session; with none today, the fallback shows the next upcoming session with the "no hay sesión hoy" label (US3 AC2).
- `frontend/src/components/training/__tests__/SessionsTable.test.tsx` (extend): today's row/card carries both the icon/marker AND the text label — assert on the accessible text, not on a CSS class alone (guards against a color-only regression).

### Gate regression (FR-006, SC-007 — zero regression tolerance)

- Re-run (unmodified expectations) `frontend/src/components/strength/__tests__/AgeBandGuardrailDialog.test.tsx`-equivalent and `frontend/src/components/intervals/__tests__/AgeGateDialog.test.tsx` (already exists per the repo glob). Additionally, add one assertion in the new `StrengthBlockPicker`/`BlockBuilderPage` tests and in the (unchanged) intervals flow test that the gate dialogs still open from the *unified* entry points exactly as they did from the old ones — i.e., a test that fails if the unification accidentally introduced a code path that bypasses `_validate_age_band_guardrail` or the interval 422 codes.

### Accessibility

```bash
cd frontend && npm run test -- --grep a11y   # or the project's existing jest-axe invocation convention
```

Zero violations required (Constitution II) on: the sectioned `SessionDetailPage`, the new `TechniqueAttachPicker`, the new `StrengthBlockPicker`, and the "which session?" picker component. Confirm `ui/tabs.tsx`'s `TabsTrigger` renders at ≥48×48px in the sectioned page specifically (contracts/session-sections.md flags the primitive's current 44px default as needing a bump) — `jest-axe` cannot measure rendered pixel size (structural limitation noted in `docs/17-coach-ux-redesign/agent-reports/01-ux-heuristics-workflows.md`), so this is a target-size assertion in the Playwright pass below, not a jest-axe assertion.

## Playwright end-to-end flow

Extend `frontend/e2e/target-size.spec.ts` (existing infra, `@playwright/test` per `specs/028-frontend-design-foundation/research.md` R7) or add a new spec, `frontend/e2e/session-content-unification.spec.ts`:

1. Log in as coach (existing seed credentials, `entrenador@trochyruta.com` / `Coach2026!`).
2. Create a session (existing wizard, unchanged by this feature).
3. From the session's Plan section: attach technique exercises (multi-select 2+ items) → assert they appear, no new session row was created in `/training/sessions` (SC-002: 0 duplicate sessions).
4. Attach a strength block via "pick existing" → assert it appears.
5. Create an interval structure inline → assert it appears (unchanged reference flow, included as a regression check).
6. Assert all three now show in the Plan section as one coherent list, and total elapsed interaction count for all three combined stays low (SC-003: "under 3 minutes with library content prepared" — timing assertion or a documented manual-timing note if Playwright timing is too environment-sensitive to assert hard).
7. Assert every interactive control exercised above has a rendered bounding box ≥48×48px (extends the existing target-size sweep to the new components).
8. Navigate away and back (or refresh) mid-flow; assert the active `?section=` persisted (SC-006).

## Manual validation scenarios (tie to spec acceptance scenarios)

Run these against a local Docker stack (`docker compose up`) with seed data, on an actual tablet or a throttled-network desktop emulation (per CLAUDE.md's field-conditions non-negotiables):

- **US1 AC1-4**: build a session, attach technique + strength + intervals from within it; confirm each attach uses a visibly identical interaction (picker → confirm → inline result), confirm the session count in `/training/sessions` did not grow.
- **US1 AC5**: start a strength block build from `/strength/blocks/new` directly (no session in URL); confirm the "which session?" step appears before/alongside the build form.
- **US2 AC1-4**: open a session dated today → lands on Asistencia; open one dated in the future → lands on Resumen; refresh and back-navigate between sections, confirm persistence; open a session with zero attached content → confirm the combined empty state with all three attach actions.
- **US3 AC1-2**: seed a session for today, use the "Hoy" shortcut, confirm one-interaction reach and a non-color-only marker; delete/move today's session, confirm the fallback to "next upcoming" with clear labeling.
- **Edge case — mid-attach connection loss**: throttle network to failure mid-request during a technique or strength attach, confirm the coach's selections remain, retry succeeds, and the final Plan section shows no duplicate entries (SC-002 adjacent, FR-009).
- **Edge case — age-band gates**: attempt a strength block entry outside its age band (confirm `AgeBandGuardrailDialog` still fires, override still records); attempt a Z3+ interval structure for age 10-12 (confirm `AgeGateDialog` blocked mode still fires with no override option) — both from the unified entry points, per SC-007's zero-regression bar.

## Success criteria cross-reference

| SC | Validated by |
|---|---|
| SC-001 | Playwright flow steps 3-5 (≤3 interactions each) |
| SC-002 | Playwright flow step 3 assertion + backend idempotency test |
| SC-003 | Playwright flow step 6 |
| SC-004 | `SessionDetailPage` section test — Asistencia reachable via one tab click from page load |
| SC-005 | `SessionFiltersBar`/`SessionsTable` "hoy" tests + manual scenario |
| SC-006 | `SessionDetailPage` refresh/back-navigation test + Playwright step 8 |
| SC-007 | Gate regression tests (backend + frontend) + manual edge-case scenarios |
