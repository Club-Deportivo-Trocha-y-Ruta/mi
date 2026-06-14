# Phase 0 Research: Coach Per-Athlete Qualitative Notes on Competition Results

**Feature**: 013-race-result-athlete-notes
**Date**: 2026-06-14
**Inputs**: spec.md, CLAUDE.md, constitution.md, context7 docs (SQLAlchemy 2.0, TanStack Query v5), web search (FastAPI PATCH semantics)

This document records the technical decisions that resolve the unknowns for the implementation
plan. Each entry follows Decision / Rationale / Alternatives considered.

---

## R1 — Where the note is persisted (storage strategy)

**Decision**: Reuse the **existing unused `notes` column on `race_results`** is **rejected**; instead add a
dedicated nullable column `coach_note` (TEXT/`String`) plus authorship/timestamp metadata to the
`race_results` row, OR — if metadata (author, updated_at) is required by the spec entity — model a
separate one-to-one table. Final choice deferred to data-model.md, but the **column-on-`race_results`**
approach is preferred because the relationship is strictly 1 note ↔ 1 result row.

**Rationale**:
- The spec's Key Entity ("Coach Race Note") requires *authoring coach* and *created/updated timestamps*.
  The pre-existing `notes` column (300 chars, import-pipeline artifact) carries no author/timestamp and
  is already written by the PDF/CSV importer, so reusing it would conflate machine-extracted import notes
  with coach-authored qualitative notes — a correctness and privacy hazard. We therefore introduce a
  **new, clearly-named** field (`coach_note`) and keep the importer's `notes` untouched.
- One note per rider per válida (FR-002) maps exactly to one `race_results` row `(event_id, category_id,
  competitor_id)` → `athlete_id`. A 1:1 column avoids an extra join on the hot results-list path.
- Authorship + timestamps fit as sibling columns (`coach_note_author_id`, `coach_note_updated_at`) without
  a new table, keeping the migration and queries simple (rule-of-three: no premature table abstraction).

**Alternatives considered**:
- *Reuse `notes`*: rejected — semantic collision with importer output, no author/timestamp, risk of the
  importer overwriting a coach note on re-import (the spec's edge case requires the note to survive
  re-imports).
- *Separate `coach_race_notes` table (1:1)*: viable and cleaner for audit, but adds a join to the
  results-list endpoint and an extra model/migration for no current multi-note need. Revisit only if
  history/threading is ever required (explicitly out of scope per spec Assumptions).

---

## R2 — SQLAlchemy 2.0 async column modelling

**Decision**: Model the new field as `coach_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)`
(length finalized in data-model.md), authored-by as `Mapped[Optional[int]]` FK to `users.id`, and
`coach_note_updated_at: Mapped[Optional[datetime]]`. Update via attribute assignment on the loaded ORM
object inside the existing `AsyncSession`, then `await session.commit()` (with `expire_on_commit=False`
already configured project-wide).

**Rationale**: Context7 (SQLAlchemy 2.0 docs) confirms the idiomatic async ORM pattern:
`Mapped[Optional[str]]` yields a NULL-able column; partial single-row updates are done by loading the row,
assigning the attribute, and committing — no bulk `update()` construct needed for a single edited row.
This matches the existing codebase conventions (declarative `Mapped[...]` models).

**Alternatives considered**: Core `update()` statement — unnecessary for single-row edits and less readable
than ORM attribute assignment; rejected for the common path.

---

## R3 — API contract for create/edit/clear (PATCH semantics)

**Decision**: Expose the note through a **single idempotent endpoint that upserts the note on a result row**:
`PUT /race-results/{result_id}/coach-note` with body `{ "coach_note": "<text>" }` to set/replace, and
`DELETE /race-results/{result_id}/coach-note` to clear. The read path returns `coach_note` (and updated_at)
embedded in the existing per-athlete result row schema so the results view renders it without an extra call.

**Rationale**:
- Single editable text field → no need for sparse-PATCH disambiguation across many fields. Web research
  (FastAPI `body-updates`, Pydantic `model_fields_set` / 2.12 `MISSING` sentinel) shows the null-vs-absent
  problem only matters for multi-field partial updates; with one field we sidestep it entirely by giving
  "clear" its own DELETE verb. This keeps the contract unambiguous and easy to test.
- Upsert-via-PUT matches FR-002 (a subsequent save updates the existing note, never duplicates).
- Embedding `coach_note` in the read schema satisfies FR-004 and SC-002 (notes shown on reopen) with no
  N+1 fetches on the results list — important for the coach's tablet/3G constraint.

**Alternatives considered**:
- `PATCH` with `exclude_unset` + treating explicit `null` as clear: more "RESTful" but introduces the
  null-vs-absent ambiguity for a one-field resource and is harder to validate/test; rejected.
- Empty-string PUT to clear: rejected — FR-006 normalizes whitespace-only to "no note", so an explicit
  DELETE is clearer than overloading empty text.

---

## R4 — Validation (length + whitespace)

**Decision**: Pydantic request schema enforces `min_length`/`max_length` and a validator that `.strip()`s
input; a whitespace-only payload to PUT is rejected with 422 (localized message surfaced by the frontend
Zod schema), and the frontend mirrors the same bounds in Zod (React Hook Form). Proposed max length: 500
characters (a brief observation, larger than the importer's legacy 300 to allow a full sentence or two).

**Rationale**: FR-006 mandates a max length and rejection/normalization of empty/whitespace input with
localized messages. Constitution III requires React Hook Form + Zod with inline localized errors and
forbids native HTML5 validation competing with Zod. Bounds are duplicated (Zod client + Pydantic server)
so the server remains authoritative while the client gives immediate feedback offline.

**Alternatives considered**: Server-only validation — rejected, violates the UX requirement for inline
localized feedback before submit.

---

## R5 — Feeding the note to the AI (per-athlete insight + coach-only chat)

**Decision**: Treat `coach_note` exactly like the existing `race_conditions.weather_notes` free-text field:
inject it into the race-analyst grounding context **after** passing it through the established real-name
scrub + pseudonymization path, for BOTH (a) the automatic per-athlete/per-válida insight serialization and
(b) the coach-only competition chat tools. Concretely: extend the per-athlete result serializer to carry a
`coach_note` field (scrubbed), and ensure the chat tool that returns per-athlete data includes the scrubbed
note. When no note exists, emit nothing (no placeholder) so the model never fabricates context (FR-009).

**Rationale**:
- FR-007/FR-008/SC-003 require the note to reach both AI surfaces. The repo already has a proven, audited
  privacy path for the *only* other free-text input (`weather_notes`): it is scrubbed against the club's
  real-name list and athletes are pseudonymized before any prompt (`anonymize.py`, chat `_scrub_weather_notes`).
  Reusing that exact path satisfies FR-010 / SC-004 (no PII in prompts/logs) and the constitution's minors
  privacy invariant with the least new risk surface.
- `AI_LOG_PROMPTS` stays `false` in prod (CLAUDE.md) — the note must never be logged. The scrub path plus
  the prompt-logging flag together enforce this.
- Emitting nothing when the note is absent preserves current behaviour exactly (FR-009) and keeps the
  insight deterministic for riders without notes.

**Alternatives considered**:
- Sending the raw note to the model and relying on the system prompt to "not repeat names": rejected —
  contradicts the established scrub-before-prompt guarantee and is not defensible for minors' data.
- A separate new AI tool just for notes: rejected — the note is grounding context for the existing
  per-athlete analysis, not a new capability; adding a tool increases prompt surface for no benefit.

---

## R6 — RBAC (coach/admin only; never parent/athlete)

**Decision**: Guard the note write endpoints and the note field in read responses with the existing
coach/admin permission dependency used by other race endpoints (RBAC service). The results read schema
returns `coach_note` only for coach/admin principals; parent-facing serializers omit it entirely.

**Rationale**: FR-005 / SC-005 require zero parent/athlete exposure. The project already centralizes
coach/admin enforcement in a permissions service/dependency; reusing it avoids a bespoke check and keeps
the guarantee consistent and testable (constitution II requires a negative-path test for auth denial).

**Alternatives considered**: Field-level filtering only (no endpoint guard) — rejected, both the write
endpoints and the read field must be gated.

---

## R7 — Frontend pattern (results view inline note editor)

**Decision**: Add the note affordance to the existing competition **Results tab** per-athlete row using the
shared shadcn/ui components (Dialog or inline Textarea + Save), React Hook Form + Zod for validation, and a
TanStack Query `useMutation` with **optimistic update** (`onMutate` cancels in-flight result queries,
snapshots, `setQueryData`; `onError` rolls back; `onSettled` invalidates the results query key) mirroring
the existing race-conditions/weather-notes editing pattern. Loading/empty/error/failure states are explicit
(constitution III), including an unambiguous save-failure indication for intermittent connectivity (FR-011/SC-006).

**Rationale**: Context7 (TanStack Query v5) confirms the optimistic `onMutate/onError/onSettled` pattern and
that returning the invalidation Promise from `onSettled` keeps the mutation pending until refetch — giving
honest save/failure feedback over flaky 3G. Reusing the existing weather-notes editor pattern satisfies the
"reuse shared component system" constitution rule and minimizes new UI surface.

**Alternatives considered**: A separate notes page/route — rejected, the spec requires capture in the same
results screen without leaving it (User Story 1, SC-001 "under one minute").

---

## R8 — Testing approach

**Decision**:
- Backend (`pytest` + `httpx.AsyncClient` + `aiosqlite`): happy path (set, then GET shows note; update
  replaces; DELETE clears), negative paths (parent/athlete 403; whitespace-only 422; over-length 422;
  note on non-club competitor rejected), and **privacy invariants** (note scrubbed of real names before AI
  serialization; note never appears in any parent-facing serializer; note absent → AI context unchanged).
- AI: unit test that `_serialize_result` includes the scrubbed note when present and omits it when absent;
  chat per-athlete tool returns scrubbed note.
- Frontend (`vitest` + Testing Library + `jest-axe`): note editor renders for coach, hidden for parent;
  Zod validation messages (localized) for empty/over-length; optimistic update + rollback on failure;
  zero a11y violations on the dialog.

**Rationale**: Constitution II is NON-NEGOTIABLE and explicitly requires privacy-invariant tests for code
handling minors' data, happy + negative paths per router/service/permission, and `jest-axe` on dialogs.

**Alternatives considered**: None — testing scope is mandated.

---

## Resolved unknowns

| Unknown | Resolution |
|---|---|
| Reuse legacy `notes` vs new field | New `coach_note` (+ author/updated_at); legacy importer `notes` untouched (R1) |
| Async column + update pattern | `Mapped[Optional[str]]`, attribute assign + commit (R2) |
| Create/edit/clear contract | PUT upsert + DELETE clear, note embedded in read schema (R3) |
| Validation rules | strip + min/max (≤500), 422 + Zod localized mirror (R4) |
| AI grounding for both surfaces | Reuse weather_notes scrub+pseudonymize path; emit nothing when absent (R5) |
| RBAC | Existing coach/admin dependency on writes + field gating on reads (R6) |
| Frontend editor | Results-tab inline editor, RHF+Zod, optimistic TanStack mutation (R7) |
| Tests | pytest happy/negative/privacy + vitest/jest-axe (R8) |

No `NEEDS CLARIFICATION` markers remain.

## Sources

- SQLAlchemy 2.0 async ORM & column nullability — context7 `/websites/sqlalchemy_en_20`
  (https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html, .../declarative_tables.html)
- TanStack Query v5 optimistic updates — context7 `/tanstack/query/v5.90.3`
  (https://github.com/tanstack/query/blob/v5.90.3/docs/framework/react/guides/optimistic-updates.md)
- FastAPI partial-update / Pydantic null-vs-unset — https://fastapi.tiangolo.com/tutorial/body-updates/ ,
  https://roman.pt/posts/handling-unset-values-in-fastapi-with-pydantic/ ,
  https://cuboimposible.me/2025/10/02/fastapi-pydantic-patch/
