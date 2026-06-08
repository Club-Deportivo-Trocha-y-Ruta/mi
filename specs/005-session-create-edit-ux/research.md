# Phase 0 — Research: Session Create/Edit Flow & UX Overhaul

This phase resolves the open technical questions for the wizard rebuild. There were no
`NEEDS CLARIFICATION` markers left in the spec (resolved during `/speckit-clarify`), so the
research focuses on best-practice confirmation for the chosen approaches, grounded in the
existing codebase and current React Hook Form (RHF) guidance (Context7 `/react-hook-form/
documentation`) and 2025 multi-step/autosave write-ups.

## Decision 1 — Multi-step wizard with a single RHF form instance

**Decision**: Use ONE `useForm` instance for the whole wizard (not one form per step), with
`mode: "onTouched"` for inline validation, and gate "Next" with
`await trigger(fieldsForStep, { shouldFocus: true })` to validate only the current step's
fields before advancing. Final submit runs full-form validation via `handleSubmit`.

**Rationale**: A single instance keeps all values in one place (simplifies draft autosave
and the review step), and `trigger(name[])` is the RHF-sanctioned way to validate a subset
of fields per step (Context7). `onTouched` gives inline feedback as the coach works without
the jarring "everything red on submit" of the current `onSubmit`-only form. Mirrors the
existing `ImportWizard` mental model (numbered `Stepper` with `aria-current="step"`).

**Alternatives considered**: (a) One form per step with a parent state aggregator — more
boilerplate, harder to autosave atomically, rejected. (b) Keeping the single long page with
just a sticky summary — rejected per clarification (stepped wizard chosen) and weaker field
orientation on mobile.

## Decision 2 — Step decomposition

**Decision**: Four steps:
1. **General** — date, start time, duration (`DurationPicker`), location, technical focus,
   description, `session_kind` (`ToggleGroup` chips), objectives.
2. **Athletes** — enhanced `AthletesMultiSelect` (≥1 required).
3. **Route & Notes** — route text, Strava URL, route file (`.gpx/.fit`), coach notes.
4. **Review** — read-only summary (date, kind, athlete count, notification choice) + the
   notify-parents decision, then submit.

**Rationale**: Groups required-to-create fields first (so a minimal session can be created
fast), isolates the long athlete list, and puts optional/secondary inputs (route, private
notes) together. The Review step is where FR-015's notification choice and the
constitution's "no silent failure" outcome live. Step boundaries map cleanly onto Zod
per-step field lists for `trigger`.

**Alternatives considered**: Three steps (folding Route/Notes into General) — rejected;
General becomes long again on mobile, defeating the purpose.

## Decision 3 — Draft autosave & restore (no new dependency)

**Decision**: A small `useFormDraft` hook: subscribe via RHF `watch()`, debounce (~800 ms),
and persist `{ values, step, updatedAt, version }` to `localStorage` under a key scoped per
user and per target — `tyr:session-draft:v1:{userId}:{new|<sessionId>}`. On mount, if a
draft exists and is newer than the server `updated_at` (edit mode) or simply present (create
mode), show a non-blocking restore banner ("Tienes un borrador sin guardar — Restaurar /
Descartar"). Restore calls `reset(draft.values)` and sets the step. Clear the key on
successful save and on explicit discard. Guard for SSR/quota with try/catch; ignore unknown
fields on restore (forward-compatible).

**Rationale**: Matches 2025 guidance (store values + step index, prompt before prefilling,
`removeItem` on submit/reset, guard quota/SSR). Avoids a new runtime dependency (Principle:
stack discipline). Scoping by `userId` mirrors the existing TanStack "Privacy R2" cache
isolation so a shared family tablet never restores another account's draft.

**Privacy note**: Drafts may contain athlete ids → treated as sensitive: cleared on
save/discard, never logged, key namespaced per user.

**Alternatives considered**: (a) Zustand `persist` middleware — viable but heavier and
couples drafts to global store; the localized hook is simpler and disposable. (b)
`react-form-autosave` library — rejected (new dependency for a small need).

## Decision 4 — Route file in the create pass (auto-upload after create)

**Decision**: In the Route & Notes step the coach picks a `.gpx/.fit` file
(`RouteFileDropzone`, held in component state, not in RHF). On final submit: create the
session first (`POST /training-sessions`), then if a file was chosen, call the existing
`POST /training-sessions/{id}/route-file` (`uploadRouteFile`). Surface a distinct result if
the upload fails: the session is already saved (don't roll back), show a non-blocking error
with a "Reintentar subida" action on the detail page navigation target. In edit mode the
file uploads immediately against the known id.

**Rationale**: Clarification chose "auto-upload after save" → no new backend contract; reuses
the validated endpoint (magic-bytes + size checks live server-side). Honors FR-014/FR-016
(notification/upload failure must not hide a saved session).

**Alternatives considered**: New multipart create endpoint accepting the file atomically —
rejected per clarification (expands backend scope beyond the minimal contract fix).

## Decision 5 — Backend contract fix for `session_kind` and `objectives`

**Decision**: Add `session_kind: SessionKind | None` and `objectives: str | None`
(max 1000) to `TrainingSessionCreate` and `TrainingSessionUpdate`; set them in
`create_session` (default `session_kind` to the model's server default when omitted);
include both in `TrainingSessionRead` and `TrainingSessionReadParent`; add `_FIELD_LABELS`
entries ("Tipo de sesión", "Objetivos") so update-diff emails render them. `update_session`
already applies arbitrary `model_dump(exclude_unset=True)` fields generically, so adding the
schema fields is sufficient there.

**Rationale**: This is the confirmed root-cause defect. The model columns already exist
(`training_sessions.session_kind` enum + `objectives` text, migration `d4e5f6a7b8c9`), so
**no Alembic migration** is needed — verified against `models/training_session.py` and the
Phase 1.9 changelog. Enum uses `values_callable` convention already in the model.

**Alternatives considered**: Storing `objectives` only client-side — rejected; that is the
very bug being fixed.

## Decision 6 — Athlete selection UX & shared Strava validation

**Decision**: Enhance `AthletesMultiSelect`: selected athletes shown as removable chips
above the list, a **sticky** selected-count, ≥48 px row targets, keep search + select-all/
clear-all. Extract the Strava regex into one shared constant used by the Zod schema so the
client rule matches the server rule (`^https://www\.strava\.com/activities/\d+$`); the
current client regex is looser (`https?`, optional path) than the server's — align to the
server's stricter form to avoid "valid on client, 422 on server".

**Rationale**: Directly addresses FR-011 and FR-013 and the spec's documented divergence.

**Alternatives considered**: Virtualized list — unnecessary at this roster scale (tens, max
~60); deferred.

## Decision 7 — Concurrent-edit detection

**Decision**: In edit mode, capture the session `updated_at` at load; on save, if the
re-fetched/returned `updated_at` differs from what was loaded (or use it to compare before
mutation), warn the coach before overwriting (FR-019). Lightweight optimistic-concurrency
check using the existing `updated_at` field — no new column.

**Rationale**: Meets FR-019 with existing data; avoids server changes.

**Alternatives considered**: ETag/If-Match headers — heavier; deferred.

## Sources

- Context7 `/react-hook-form/documentation` — `trigger`, `watch`, `reset`, `useFormContext`.
- [Building a reusable multi-step form with RHF and Zod — LogRocket](https://blog.logrocket.com/building-reusable-multi-step-form-react-hook-form-zod/)
- [Advanced Multistep Forms with React Hook Form — ClarityDev](https://claritydev.net/blog/advanced-multistep-forms-with-react)
- [Multistep Forms with Awesome UX — Persistent State — Andy Fry](https://andyfry.co/multi-step-form-persistent-state/)
- [Implementing Auto-Save with Custom Hooks — Stackademic](https://stackademic.com/blog/react-hooks-in-action-implementing-auto-save-with-custom-hooks-b0be405766c5)
- Existing code: `components/competitions/import/ImportWizard.tsx`, `components/training/AthletesMultiSelect.tsx`, `services/training/sessions.py`, `schemas/training_session.py`.
