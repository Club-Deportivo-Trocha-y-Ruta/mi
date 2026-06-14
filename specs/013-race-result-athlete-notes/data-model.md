# Phase 1 Data Model: Coach Per-Athlete Qualitative Notes

**Feature**: 013-race-result-athlete-notes | **Date**: 2026-06-14

## Entity: Coach Race Note (modeled as columns on `race_results`)

The spec's "Coach Race Note" is a 1:1 attribute of an existing per-athlete result row
(`race_results`, unique on `(event_id, category_id, competitor_id)`, linked to a club athlete via
`athlete_id`). It is therefore modeled as **new columns on `race_results`**, not a separate table
(no multi-note / threading need — explicitly out of scope).

> The pre-existing `notes: String(300)` column on `race_results` is an **importer artifact** and is
> intentionally **left untouched** — it is written by the PDF/CSV ingest pipeline and could be
> overwritten on re-import, which would violate the spec edge case "the note remains tied to the rider
> and válida regardless of result re-imports." The coach note lives in its own clearly-named columns.

### New columns on `race_results`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `coach_note` | `String(500)` | YES | NULL | Coach-authored qualitative observation. NULL = no note. Stored stripped. |
| `coach_note_author_id` | `Integer` FK→`users.id` (ON DELETE SET NULL) | YES | NULL | Authoring coach/admin. |
| `coach_note_updated_at` | `DateTime` | YES | NULL | Set on each upsert; cleared on delete. |

**ORM (SQLAlchemy 2.0, async)** — `backend/app/models/race_result.py`:

```python
coach_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
coach_note_author_id: Mapped[Optional[int]] = mapped_column(
    ForeignKey("users.id", ondelete="SET NULL"), nullable=True
)
coach_note_updated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
# relationship (optional, read-only convenience):
coach_note_author: Mapped[Optional["User"]] = relationship(foreign_keys=[coach_note_author_id])
```

### Validation rules (FR-006)

- Server (Pydantic) and client (Zod) both enforce: text is `.strip()`-ed; after stripping,
  `1 ≤ len ≤ 500`. Whitespace-only / empty → rejected (422) on PUT; clearing is done via DELETE.
- `coach_note` is only ever set on a result row whose `athlete_id IS NOT NULL` (club-managed rider).
  Attempting to set a note on a non-club result row → 4xx (FR edge case; non-managed entries offer no
  notes).

### State transitions

```
(no note)  --PUT {coach_note}-->  (note: text, author=current_user, updated_at=now)
(note)     --PUT {coach_note}-->  (note replaced; author=current_user, updated_at=now)   # FR-002 upsert
(note)     --DELETE----------->   (no note: coach_note=NULL, author=NULL, updated_at=NULL)
```

At most one note per `race_results` row (one per rider per válida) — guaranteed structurally by the
row's existing uniqueness constraint `uq_race_results_event_category_competitor`.

### Migration

- New Alembic revision, **revises `f9a0b1c2d3e4`** (current head).
- `op.add_column("race_results", sa.Column("coach_note", sa.String(500), nullable=True))`
- `op.add_column("race_results", sa.Column("coach_note_author_id", sa.Integer(), nullable=True))`
- `op.add_column("race_results", sa.Column("coach_note_updated_at", sa.DateTime(), nullable=True))`
- `op.create_foreign_key("fk_race_results_coach_note_author", "race_results", "users",
  ["coach_note_author_id"], ["id"], ondelete="SET NULL")`
- Downgrade drops the FK and the three columns. No data backfill (all NULL initially).
- Runs automatically via `entrypoint.sh` (`alembic upgrade head`) on Render startup.

## Read exposure (RBAC-gated)

- `ResultRow` (`backend/app/schemas/race_results.py`) gains `coach_note: str | None = None` and
  `coach_note_updated_at: datetime | None = None`. These fields are populated **only** for
  coach/admin principals; the results endpoint already requires `require_role([coach, admin])`, so
  parents/athletes never reach this serializer. (FR-005 / SC-005.)

## AI grounding shape (scrubbed)

The per-athlete serializer used by the race-analyst graph
(`backend/app/services/race/ai/nodes/load_race_data.py::_serialize_result`) gains a `coach_note` key:

```python
{ ..., "status": r.status.value, "coach_note": r.coach_note }   # raw at load time
```

`backend/app/services/race/ai/nodes/anonymize.py` then scrubs `coach_note` against the same
forbidden-real-name list used for `weather_notes` (`_scrub_event_conditions` / `load_forbidden_names`)
**before** the analyst agent or any chat tool sees it. When `coach_note` is NULL the key is omitted /
left null so the model receives no qualitative context and behaves exactly as today (FR-009).

The coach-only competition chat per-athlete tool likewise returns the **scrubbed** note (never the raw
text, never real names). `AI_LOG_PROMPTS` stays `false` in prod; the note is never logged.

## Relationships summary

- `race_results.coach_note_author_id` → `users.id` (the coach/admin who last wrote the note).
- `race_results.athlete_id` → `athletes.id` (the club rider the note describes; must be non-NULL to
  accept a note).
- `race_results.event_id` → `race_events.id` (the válida).
