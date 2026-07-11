# Data Model — 032 Session Content Unification

**Schema changes expected: NONE.** Verified against every model this feature touches — see per-entity notes below. This feature reorganizes *how* existing relationships are created (attach interaction) and *presented* (session sections); it adds exactly one new backend request/response payload shape (Pydantic schemas only, no table). Confirmed no Alembic migration is required (Constitution's stack-discipline note: "Adding a new runtime dependency requires written justification" does not apply either — no new dependency is added, `@radix-ui/react-tabs` is already installed and in use).

## Existing entities and relationships (unchanged; cited from the real models)

### TrainingSession (`backend/app/models/training_session.py:62-166`)

The parent of all three content types. Relevant relationships, each already declared on this model:

| Relationship | Attribute | Cardinality (per session) | Cascade | Cite |
|---|---|---|---|---|
| → `TechniqueSessionExercise` | `technique_exercises` | **1:N** (many rows per session) | `all, delete-orphan` | `training_session.py:146-151` |
| → `StrengthSessionBlock` | `strength_blocks` | **1:N** (many *link rows* per session; each link references a block that is itself reusable across sessions, i.e. N:N at the block level, 1:N from the session's point of view) | `all, delete-orphan` | `training_session.py:152-158` |
| → `IntervalStructure` | `interval_structure` | **1:1** (`uselist=False`) | `all, delete-orphan` | `training_session.py:159-166` |

### TechniqueSessionExercise (`backend/app/models/technique_exercise.py:256-293`)

- Columns: `id`, `training_session_id` (FK → `training_sessions.id`, `ondelete="CASCADE"`), `exercise_id` (FK → `technique_exercises.id`, `ondelete="RESTRICT"`), `segment` (`SessionSegment` enum: `calentamiento|principal|vuelta_calma`), `position` (int).
- **No unique constraint** on `(training_session_id, exercise_id, segment)` — only `Index("idx_tse_session", "training_session_id")` (line 266). This is the idempotency gap the new endpoint's service layer must defend against in application code (research.md R4) since there is no DB-level backstop.
- **Cardinality**: 1:N. A session may accumulate exercises across multiple attach calls over time; there is no natural upper bound and no "replace" semantics anywhere in the current model or services.

### StrengthBlock / StrengthBlockEntry / StrengthSessionBlock (`backend/app/models/strength.py`)

- `StrengthBlock` (`:196-249`): a first-class, club-owned, reusable object. `entries` (`StrengthBlockEntry`, `:257-297`) are 1:N *within* a block, ordered by `position`, unique per `(block_id, position)` (`:265`).
- `StrengthSessionBlock` (`:305-350`): the attach link table. `UniqueConstraint("training_session_id", "block_id", name="uq_strength_session_block")` (`:314-318`) — a given block cannot attach to the same session twice, but the **same session can hold many distinct blocks** (1:N from the session's side) and the **same block can attach to many sessions** (reusable, no copy-on-attach — confirmed by `services/strength/blocks.py:536-542` docstring: "Un bloque es reutilizable entre sesiones (sin copy-on-attach)").
- **Cardinality**: 1:N per session (many blocks attachable), append-only in practice — attaching a second block never touches the first block's link row.

### IntervalStructure / IntervalStructureBlock (`backend/app/models/interval_structure.py:80-205`)

- `UniqueConstraint("training_session_id", name="uq_interval_structure_session")` (`:90-95`) — **1:1**, enforced at the DB level. A session can have *at most one* structure; "attaching" an interval template (`POST /api/intervals/templates/{id}/attach`) copies the template's blocks into a **new** `IntervalStructure` row only when none exists yet (409 otherwise, per `routers/intervals.py` docstrings) — this is why intervals' UI shows either a create/pick-template empty state OR an edit view, never a second attach action once content exists.
- **Cardinality**: 1:1. Not affected by this feature (reference pattern, unchanged).

## Append vs. replace semantics — decided per type from the cardinalities above

| Content type | Cardinality | When a session already has content of this type | Verified from |
|---|---|---|---|
| Technique exercises | 1:N | **Append.** New attach calls add more `TechniqueSessionExercise` rows (deduplicated per R4); existing rows are untouched. There is no "replace all technique content" action anywhere in scope. | `technique_exercise.py:256-293` (no unique/1:1 constraint blocking multiple rows) |
| Strength blocks | 1:N (per session) | **Append.** Attaching a second/third block is a new `StrengthSessionBlock` link row; the first block's link is untouched. Editing the *content* of an already-attached block (its own exercises) is a separate action against `StrengthBlock`/`StrengthBlockEntry` (PUT `/blocks/{id}`), independent of session-attach, and affects every session that block is attached to (shared object, not a copy). | `strength.py:305-318`, `services/strength/blocks.py:536-542` |
| Interval structure | 1:1 | **Replace is structurally impossible** — the unique constraint guarantees at most one row. "Already has content" flips the UI from create/pick-template to edit/view; this is already implemented exactly this way in `SessionDetailPage.tsx:855-1037` (`structureQuery.data ? <edit/view> : <create or TemplatePicker>`) and is unchanged by this feature. | `interval_structure.py:90-95` |

## New payload shapes (Pydantic schemas only — no new tables)

Added to `backend/app/schemas/technique.py`, reusing the existing `AssembleItem` and `TechniqueSessionItem` models (`technique.py:360-365, 418-440`) rather than inventing new item shapes:

```python
class AttachExercisesRequest(BaseModel):
    """Body for POST /api/technique/sessions/{training_session_id}/exercises."""
    items: list[AssembleItem] = Field(min_length=1)


class AttachExercisesResponse(BaseModel):
    """201 response — mirrors GET's shape plus the age-mix notice."""
    mixes_age_bands: bool
    items: list[TechniqueSessionItem]
```

`AssembleItem` is unchanged (`exercise_id: int`, `segment: SessionSegment`, `position: int`) — no new fields, no new enum values. `training_session_id` is **not** part of the request body (it is the path parameter, unlike `AssembleSessionRequest` which needs it in the body because that endpoint creates the session itself).

No changes to `AssembleSessionRequest`, `AssembleSessionResponse`, or any model file. `TechniqueSessionExercise`, `StrengthSessionBlock`, `IntervalStructure` are all reused exactly as they exist today.

## Frontend state shapes touched (no new persisted state)

- `useTrainingFiltersStore` (`frontend/src/store/trainingFiltersStore.ts:18-46`) gains one new action for the "hoy" quick filter (sets `from_date = to_date = today`, club-timezone-derived) — no new persisted fields, reuses the existing `from_date`/`to_date`/`status` shape already persisted to `localStorage` under `"training-filters"` (`:42-44`).
- Session detail's active section (`?section=`) is URL state only, exactly like `AthleteDetailPage.tsx`'s `?tab=` (`:390-426`) — not persisted to `localStorage`, not a new store.
- No new TanStack Query cache shapes beyond one new mutation (`useAttachTechniqueItems`, invalidating `techniqueKeys.sessionExercises(sessionId)` — key already defined at `frontend/src/hooks/technique/useTechnique.ts:43-44`) and, for strength, reuse of the existing `useAttachBlock`/`strengthKeys.sessionBlocks` pair (`frontend/src/hooks/strength/useStrength.ts:165-184`).
