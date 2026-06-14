# Quickstart: Coach Per-Athlete Qualitative Notes on Competition Results

**Feature**: 013-race-result-athlete-notes

This is the implementer's checklist. Order matters (migration → model → schema → router → AI → frontend →
tests). All product copy in español neutro (Colombia); code/docs in English.

## Backend

1. **Model** — `backend/app/models/race_result.py`: add `coach_note: Mapped[Optional[str]]`
   (`String(500)`), `coach_note_author_id: Mapped[Optional[int]]` (FK `users.id`, `ondelete="SET NULL"`),
   `coach_note_updated_at: Mapped[Optional[datetime]]`, and optional read-only relationship
   `coach_note_author`.

2. **Migration** — `cd backend && alembic revision -m "add coach_note to race_results"` (revises
   `f9a0b1c2d3e4`). Add the three columns + FK; downgrade drops them. Verify with `alembic upgrade head`
   on a scratch DB.

3. **Schemas** — `backend/app/schemas/race_results.py`:
   - `ResultRow`: add `result_id: int`, `coach_note: str | None = None`, `coach_note_updated_at:
     datetime | None = None`.
   - New `CoachNoteUpdate`: `coach_note: str` with a `field_validator` that strips and enforces
     `1 ≤ len ≤ 500` (raise on whitespace-only).

4. **Router** — `backend/app/routers/race_events.py` (mirror `update_race_event_conditions`, lines
   ~714-786):
   - `PUT /race-results/{result_id}/coach-note` → load row (404 if missing/soft-deleted), reject if
     `athlete_id is None`, set `coach_note`/author/`updated_at`, commit, return `ResultRow`.
   - `DELETE /race-results/{result_id}/coach-note` → null the three fields, commit, return `ResultRow`.
   - Both guarded by `require_role([UserRole.coach, UserRole.admin])`.
   - Ensure `_serialize`/result-row builder includes `result_id`, `coach_note`, `coach_note_updated_at`.

5. **AI grounding** — reuse the `weather_notes` scrub path:
   - `services/race/ai/nodes/load_race_data.py::_serialize_result`: add `"coach_note": r.coach_note`.
   - `services/race/ai/nodes/anonymize.py`: scrub `coach_note` with the same forbidden-name logic as
     `_scrub_event_conditions` (use `load_forbidden_names`); omit when null.
   - `services/race/ai/nodes/analyst_agent.py` + the coach-only chat per-athlete tool: include the
     **scrubbed** note in context. When null, change nothing (FR-009).

6. **Backend tests** — `backend/tests/routers/`:
   - `test_race_result_coach_note.py`: PUT sets (200 + GET shows it), PUT replaces, DELETE clears;
     422 empty/whitespace + > 500; 403 parent & athlete; 4xx note on non-club row; 404 missing row.
   - Extend `test_race_analysis_privacy.py`: note scrubbed of real names before serialization; raw note
     never in prompt; note null → AI context identical to baseline.

## Frontend

7. **Types** — `frontend/src/types/raceResults.types.ts`: add `result_id: number`,
   `coach_note: string | null`, `coach_note_updated_at: string | null` to `RaceResultRow`.

8. **API** — `frontend/src/api/raceResults.ts`: add `setResultCoachNote` (PUT) and `clearResultCoachNote`
   (DELETE) per the contract.

9. **Hooks** — `frontend/src/hooks/race/useRaceResults.ts`: add `useSetResultCoachNote` /
   `useClearResultCoachNote` (`useMutation`, optimistic `onMutate`/`onError`/`onSettled` invalidating
   `raceResultsKeys.byEventFiltered`).

10. **Editor component** — `frontend/src/components/race/EditResultNoteDialog.tsx` (mirror
    `EditConditionsDialog.tsx`): shadcn `Sheet`/Dialog + `Textarea`, React Hook Form + `zodResolver`, Zod
    schema (strip, `max(500)`, localized messages), explicit saving/error/save-failure states, focus trap,
    Escape-dismiss, 48×48 targets.

11. **Table wiring** — `frontend/src/components/competitions/results/ResultsTable.tsx`: for club rows
    (coach/admin only), show a note affordance (add/edit icon + truncated note preview/tooltip) opening the
    dialog. Hidden entirely for parent role.

12. **Frontend tests** — mirror `EditConditionsDialog.test.tsx`: editor renders for coach, hidden for
    parent; Zod localized validation (empty / > 500); optimistic update + rollback on failure; `jest-axe`
    zero violations on the dialog.

## Verify

```bash
# Backend
cd backend && alembic upgrade head && pytest tests/routers/test_race_result_coach_note.py \
  tests/routers/test_race_analysis_privacy.py -q && ruff check . && mypy app

# Frontend
cd frontend && npx vitest run src/components/race/__tests__/EditResultNoteDialog.test.tsx \
  && npx tsc --noEmit && npx eslint src
```

**Manual smoke**: open a completed válida's Results → add a note to a club rider → reopen → note persists;
run that rider's AI insight → narrative reflects the note; ask the competition chat about the rider →
answer reflects the note; clear the note → AI reverts to numbers-only. Confirm a parent login sees no note
affordance or text anywhere.

## Done when

- [ ] Migration applies cleanly; columns present; importer `notes` untouched.
- [ ] PUT/DELETE work with RBAC; note embedded in results read for coach/admin only.
- [ ] AI insight and coach-only chat incorporate the scrubbed note; null note = unchanged behaviour.
- [ ] All backend + frontend tests (incl. privacy + a11y) pass; linters/type-checks clean.
