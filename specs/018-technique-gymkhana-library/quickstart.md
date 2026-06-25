# Quickstart & Validation: Technique & Gymkhana Library + Session Builder

End-to-end validation scenarios that prove the feature works, mapped to the spec's user stories and success criteria. See [data-model.md](./data-model.md) and [contracts/rest-api.md](./contracts/rest-api.md) for details; this file is a run/validate guide, not implementation.

## Prerequisites

```bash
# Backend
source backend/.venv/bin/activate
cd backend && alembic upgrade head     # creates technique_* tables AND seeds the catalog (idempotent)
uvicorn app.main:app --reload

# Frontend
cd frontend && npm run dev

# Or full stack (runs migrations + seed automatically)
docker compose up
```

Sign in as the coach (`entrenador@trochyruta.com` / `Coach2026!`) or admin. The catalog must be populated **with no manual data entry** on first run (SC-002).

## Scenario 1 — Catalog is pre-seeded & filterable (US1 · SC-002/SC-003)

1. Open `/technique`. **Expect** ≈24 exercises across the 7–9, 10–12, 13–15 bands already present (`is_seeded=true`).
2. Filter `age_band=7-9` → only 7–9-appropriate exercises.
3. Combine `skill=frenado` + `difficulty=facil` → only matches both.
4. Filter `materials=conos,llantas` → only exercises runnable with cones and/or tires, **including `sin_material` exercises** (FR-009).
5. Choose a no-match combination → a **clear empty state** with a "limpiar filtros" affordance (FR-004), not a blank screen or error.

**API check**: `GET /api/technique/exercises?age_band=7-9&skill=frenado` returns `200` with `items`/`total`; an unauthenticated or parent token returns `403`.

## Scenario 2 — Exercise detail with illustrative layout (US2)

1. Open any seeded **gymkhana** exercise (e.g. "Limbo en bici"). **Expect** skill(s), age band(s), difficulty, materials, a "cómo correrlo" section with the NICA 4-step method + mastery-climate framing (FR-007), and the **illustrative ASCII circuit layout** rendered in a responsive monospace block (FR-008).
2. With a screen reader, the layout exposes a text alternative (`layout_alt`) — WCAG AA.
3. Open a **no-equipment** exercise (e.g. "Semáforo") → materials clearly say "sin material" (FR-009).

## Scenario 3 — Assemble a session through the EXISTING module (US3 · SC-001/SC-006)

1. From the catalog, add ≥2 exercises into warm-up / main / cool-down via the SessionAssembler.
2. Save. **Expect** a normal **training session** in the existing calendar/session list — **no parallel record** (FR-011, SC-006).
3. Open it from the session list → the chosen exercises are listed (FR-013) and the session supports the existing **attendance + rubric** flows (FR-012).
4. Assemble exercises from more than one age band → the session saves **and** shows a visible "mezcla bandas de edad" notice (FR-014, `mixes_age_bands=true`).
5. Time the find→assemble flow: completes in **under 3 minutes** (SC-001).

**API check**: `POST /api/technique/sessions` returns `201` with `training_session_id`; that id is retrievable via the existing `GET /api/training-sessions/{id}`.

## Scenario 4 — Per-athlete skill progress, never comparative (US4 · SC-004/SC-005)

1. For an athlete **with a record**, set skill "Frenado modulado" → `en_progreso`; later set `dominado`.
2. Open the athlete's progress view → current status per skill **and** its evolution across the season (FR-016, SC-004), anchored to the athlete's own trajectory/biological age.
3. **Verify**: no view or export ranks or compares this athlete against another (FR-017, SC-005) — the progress response contains only this athlete.
4. For a 7–9 rider **without a record**, per-athlete tracking is gracefully unavailable (`404`, FR-018) — catalog/detail/assembly still work (FR-025).
5. **Privacy**: no minor PII appears in logs or responses beyond in-app coach authorization (SC-007); this feature uses **no AI prompt**.

**API check**: `GET /api/technique/athletes/{id}/progress` → `200` for a coach, `403` for a parent.

## Scenario 5 — Curate the catalog (US5)

1. Create a custom exercise (skill, age band, difficulty, materials, how-to, layout) → appears in browse/filters (`is_seeded=false`).
2. Edit a **seeded** exercise (e.g. adjust materials) → change persists in detail + filters.
3. Hide an exercise → it drops from the default catalog but is **not destroyed** (FR-019); a previously saved session that referenced it **remains intact and viewable** (FR-020).

## Automated test gates (Constitution II)

- **Backend** (`pytest` + `httpx.AsyncClient` + `aiosqlite`): catalog filter matrix incl. materials-subset & empty state; RBAC negative paths (parent/athlete/cross-club → 403); **assemble creates a real `TrainingSession`** visible in the existing list (no parallel store); hide/edit leaves a saved session's items intact; progress append → current/history; **privacy invariant** (no minor PII / no second athlete in a progress response).
- **Frontend** (`vitest` + Testing Library + `jest-axe`): FilterBar branching, CircuitLayout text alternative, SessionAssembler segments + mixed-age notice, SkillProgressBoard (no comparison UI), empty/loading/cold-start states; **zero axe violations** on each page/dialog.

## Success-criteria trace

| SC | Validated by |
|---|---|
| SC-001 (<3 min assemble) | Scenario 3.5 |
| SC-002 (seeded ~24, no manual entry) | Prereqs + Scenario 1.1 |
| SC-003 (filter returns matches/empty first try, 100% reachable) | Scenario 1.2–1.5 |
| SC-004 (introduced/in-progress/mastered at a glance + evolution) | Scenario 4.2 |
| SC-005 (zero comparison surfaces) | Scenario 4.3 + frontend test |
| SC-006 (100% sessions are normal club sessions) | Scenario 3.2 + backend test |
| SC-007 (no athlete/parent exposure, no minor-PII leak) | Scenario 4.5 + privacy test |
