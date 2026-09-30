# Quickstart / validation guide: feature 048

## Prerequisites

- Backend venv at `backend/.venv`. The frontend needs `npm ci`.
- For e2e, Docker must be running. The isolated stack uses `docker-compose.e2e.yml`, with the API on :8001 and MySQL on :3307.
- WeasyPrint on macOS needs `DYLD_FALLBACK_LIBRARY_PATH` and must run with `python -m pytest` (see memory note "WeasyPrint y pytest en local").
- Do not run anything against the local backend when it points to the production MySQL. Use the isolated e2e stack or aiosqlite tests.

## 1. Offline lanes (must be green)

```bash
cd backend && source .venv/bin/activate
python -m pytest tests/anthropometry tests/test_audit*.py tests/body_composition -q
python -m pytest -q          # full default lane
ruff check

cd ../frontend
npm run typecheck
npx vitest run src/components/athletes/anthropometry-capture src/lib/anthropometry src/store src/routes/anthropometry
npm test
npm run build                # fails if any illustration webp is missing (FR-031)
```

## 2. API scenarios (from `contracts/api.md`)

| # | Action | Expected |
|---|---|---|
| A1 | POST twice, same athlete, same date, same values | Second call → 409 with `same_values: true`; exactly one record exists |
| A2 | POST sitting 112 / standing 150 | 422 `sitting_ratio_impossible` |
| A3 | PUT sitting height as the evaluator | 200; `maturity_offset` and `maturation_status` change; AI explanation rows for the record are gone; audit `update` has `changed_fields=["sitting_height_cm"]` and no values |
| A4 | PUT as `coach2` (not the evaluator) | 403 `not_record_author` |
| A5 | PUT as a parent | 403 |
| A6 | DELETE a record with a skinfold set, as admin | 204; skinfold set and AI explanation rows gone; audit `delete` has `had_skinfolds: true` |
| A7 | Plausibility: previous 150 cm, current 148.5 cm | `height_decreased` |
| A8 | Plausibility: interval 30 days, +3 cm | No velocity warning (interval < 60 days) |
| A9 | GET list as a parent | No `can_modify` or `plausibility_flags` keys |
| A10 | Roster for a 30-athlete club | ≤ 4 queries; `has_record_on_date` is correct |
| A11 | PUT a date that breaks the skinfold 90-day rule | 409 `skinfold_interval_too_short` |
| A12 | Field-guide PDF | Starts with «Antes de medir» and the four measures, then the skinfold sections |

## 3. E2E in local (owner request)

```bash
cd frontend
./scripts/e2e-stack.sh up          # isolated backend :8001 + MySQL :3307 (seeded demo data)
npm run test:e2e:isolated -- e2e/anthropometry-capture.spec.ts e2e/anthropometry-edit-delete.spec.ts e2e/anthropometry-session.spec.ts e2e/anthropometry.spec.ts e2e/body-composition.spec.ts
./scripts/e2e-stack.sh down
```

Expected results:
- **Guided capture**: the pre-check is shown; the bench subtraction shows the net value; an injected +20 % weight produces the warning on Revisar; the PHV plain label is visible; save lands on the history with the new row.
- **Quick mode**: the preference survives a reload.
- **360 px variant** of the capture and session specs: no page-level horizontal scroll (`document.documentElement.scrollWidth <= 360`), and the illustration sits above the input.
- **Edit/delete**: the evaluator edits and deletes. `coach2` sees no actions, and a direct API call returns 403.
- **Session**: 3 athletes selected; the flow is measure → skip → measure; the summary is correct; the skinfold detour returns to the queue.
- **Regression**: «Guardar y agregar pliegues» still opens the 046 wizard.

If the stack cannot start, report e2e as **not run**. Never report it as passed.

## 4. Illustrations (clarification 5)

These are generated in the owner's Chrome session (Claude in Chrome), using Gemini or ChatGPT web.

**Upload** `frontend/src/assets/skinfolds/triceps.webp` as the style reference, and start each prompt with this style block:

> Instructional medical line-art illustration matching the attached reference exactly: flat light-grey body silhouette with thin dark-slate outlines, no facial features, slate-blue gloved hands for the measurer, teal dashed guide lines and small teal target markers. Square 1:1, pure white background, no text, no letters, no numbers, no logos, no shadows, no gradients. Generic ~12-year-old proportions, neutral athletic shorts and t-shirt, not identifiable.

Then add the subject for each file:

| File | Subject |
|---|---|
| `weight.webp` | Side view of a barefoot child standing still in the centre of a flat digital scale, arms relaxed, looking forward; shoes set aside on the floor. |
| `standing_height.webp` | Side view of a barefoot child against a wall stadiometer: heels, buttocks and upper back touching the board, feet together, head in the Frankfort plane (teal dashed horizontal line ear-to-eye), headboard on the crown, the measurer's gloved hand lightly under the jaw. |
| `sitting_height.webp` | Side view of a child sitting upright on a flat box against the stadiometer, buttocks and upper back on the board, hands on thighs, knees at 90°, Frankfort plane line, headboard on the crown, a teal bracket marking the box height. |
| `arm_span.webp` | Front view of a child with their back to a wall, arms horizontal at shoulder height, palms forward, teal dashed line from middle fingertip to middle fingertip, tape measure along the wall. |
| `precheck.webp` (optional) | Flat-lay of a stadiometer headboard, a digital scale, a flat wooden box, a tape measure and a clipboard. |

**Post-process** each image:
- Frontend: `cwebp -q 82 -resize 768 768 in.png -o frontend/src/assets/anthropometry/<key>.webp`
- PDF: Pillow to `backend/templates/documents/pdf/diagrams/img/anthro_<key>.png`, at the same size as the skinfold PNGs.

**Gate**: the owner approves each image in chat before it is committed. Stop after 3 failed attempts on one image and ask.

## 5. Manual check on a tablet (owner)

Measure one real athlete in guided mode and time it (SC-003: under 2 minutes). Then run a 3-athlete session and confirm the summary.

## 6. Deferred

- The `pytest -m mysql` lane is optional: there is no migration. It is still recommended once for the cascade delete on MySQL (A6).
- `pytest -m golden` is not required, because no prompt or model changed.
- The post-deploy smoke test is: `/health`, plus GET anthropometry for the demo athlete.
