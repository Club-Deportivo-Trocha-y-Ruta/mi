# Quickstart — validating feature 046 end to end

Prerequisites: backend venv (`backend/.venv`, Python 3.13), MySQL only for the `-m mysql` lane, Node for the frontend, no AI key needed except for the golden lane. Work happens on `main` (no branch, no auto-commits).

## 0. Migration and seed

```bash
cd backend && source .venv/bin/activate
alembic heads                       # exactly one head before adding the revision
alembic upgrade head                # local MySQL (docker compose up) — creates skinfold_measurements, extends the two enums
python -m app.seed_growth_data      # loads FUPRECOL rows (idempotent)
pytest -m mysql tests/test_migration_skinfolds.py   # upgrade → seed → downgrade → upgrade
```

Expected: `growth_reference_lms` contains `FUPRECOL` rows for three indicators × 2 sexes × 9 age bands; downgrade removes them and shrinks the enums.

## 1. Backend unit and router lanes (offline)

```bash
pytest tests/services/test_body_composition.py tests/services/test_reference_skinfolds.py
pytest tests/routers/test_body_composition.py
pytest tests/anthro -k "body_composition or r13 or r14 or privacy_seam"
ruff check
```

Expected: scenario set A–I of `contracts/body-composition-reading.md` §5 passes; parent `PUT` 403, parent `GET body-composition` 403, interval 409 with `next_allowed_date`, parent growth-summary block has exactly five keys; no numeric key in the AI leaf.

## 2. Manual API check (local, synthetic athlete only)

1. `POST /api/athletes/{id}/anthropometry` as coach → note `record_id`.
2. `PUT /api/athletes/{id}/anthropometry/{record_id}/skinfolds` with the sample body of `contracts/skinfolds-api.md` §1 → 200 with `sum4_mm` and estimates; `sum6_mm` null (one site declined).
3. `GET /api/athletes/{id}/body-composition` as coach → one set, `reading.band_reason_code == "first_set"`.
4. Repeat 1–2 with an evaluation dated 100 days later and a Σ4 8 mm lower, weight +0.3 kg, height +3 cm → `reading.band == "rojo"`, `band_reason_code == "energy_availability_pattern"`.
5. `GET …/growth-summary` as the linked parent → `body_composition` has only `has_data, latest_set_date, family_band, family_label, family_sentence`, with `family_band == "ambar"` for the rojo athlete of step 4 and no "Requiere acompañamiento profesional" text.
6. `GET …/body-composition/referral-note.pdf` as coach → PDF without `%` or `mm`; as parent → 403.
7. `GET /api/body-composition/field-guide.pdf` as coach → PDF with six sites; as parent → 403.
8. Try `PUT` on a third record dated 30 days after the second → 409 `skinfold_interval_too_short`.

## 3. Frontend

```bash
cd frontend
npm run typecheck
npx vitest run src/components/athletes/body-composition src/lib/bodyComposition src/hooks/athletes
npm run build     # capture route chunk ≤ 150 KB gzipped
```

Manual (dev server + backend): as coach, save a weight/height evaluation → choose "Guardar y agregar pliegues" → pre-check (nothing blocks) → six site steps (enter 8.5 / 9.0 on triceps; enter 7.0 / 8.5 on subscapular and confirm the third-reading prompt; skip iliac crest) → reload the tab mid-way and confirm the draft restore banner → review → save → growth tab shows the "Composición corporal" card with Σ4, estimates labelled "estimado", "Sin toma anterior comparable" and the first-set reason. As parent: the card shows band + sentence only; the notice block is present; no number anywhere.

## 4. AI lane

```bash
pytest tests/anthro                              # offline, fake provider
pytest -m golden tests/evals/test_anthropometry_analyst_eval.py   # needs AI key; composite ≥ 0.75
```

Expected: R13/R14 block adversarial texts; golden composite at or above baseline after the `v2` prompts; `AI_ANTHRO_PROMPT_VERSION=v1` restores the previous behaviour without a deploy.

## 5. End to end (isolated e2e stack)

```bash
npm run test:e2e -- e2e/body-composition.spec.ts
```

Covers: capture with a skip and a third reading, draft restore, coach card, family card without numbers, interval message before 90 days.

## 6. Report

State explicitly which lanes ran and which were deferred (`-m mysql`, `-m golden`, Playwright). Update `docs/implementation-status.md`, `docs/technical-notes.md` and `docs/21-body-composition/` (as-built notes) — never `CLAUDE.md` history.
