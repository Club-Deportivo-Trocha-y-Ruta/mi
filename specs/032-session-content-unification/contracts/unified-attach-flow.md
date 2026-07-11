# Contract — Unified Attach Flow (technique / strength / intervals)

**Purpose**: One interaction contract covering all three "attach training content to a session" flows, generalized from the existing interval reference pattern (`frontend/src/components/intervals/TemplatePicker.tsx`, research.md R3). Satisfies FR-001 (one identical pattern), FR-002 (preselect + no duplicate sessions), FR-003 (library-initiated asks which session), FR-006 (gates unchanged), FR-009 (028 feedback standards).

## Entry points

| # | Entry point | Session known? | Landing behavior |
|---|---|---|---|
| 1 | From the session's **Plan** section (`?section=plan`), each content type's own "Agregar…" action | Yes — route param `:id` | Picker/build opens inline or preselected; the session is never re-asked. |
| 2 | From the technique catalog ("Biblioteca") | No | Coach is asked which session (session picker, research.md R6) before/at attach. |
| 3 | From `/strength/blocks/new` with no `?session_id=` (bookmarked or top-nav "Armar bloque") | No | Same session picker as #2, converges to entry point 1's preselected state once chosen. |

Exactly one preselect mechanism across all three content types: **`?session_id=` query parameter** (research.md R5), never `location.state`. When entry point 1 opens a build screen (strength only — technique and intervals never navigate away from the session), the link/button carries `?session_id={id}`; the target screen locks that session as a read-only, resolved summary (same "locked read-only summary" convention feature 015 established — CLAUDE.md's `specs/015-prefill-import-from-competition` note: "locked read-only summary — static text + Lock/Pencil, not disabled inputs").

## Per-content-type interaction

### Technique (new: fully inline, no page navigation — FR-001, FR-002)

1. In the Plan section, "Agregar ejercicios de técnica" expands an inline picker (new component, mirrors `TemplatePicker`'s filter-bar-plus-grid shape but adapted to catalog exercises: filter by skill/age-band/material — reusing `useTechniqueCatalog`, `frontend/src/hooks/technique/useTechnique.ts:57-64` — then multi-select with a per-item segment assignment, mirroring `SessionAssembler`'s `SegmentSection` pattern, `frontend/src/components/technique/SessionAssembler.tsx:116-288`, minus the session-metadata fields that component also collects — the session already exists).
2. Confirm calls the new `POST /api/technique/sessions/{id}/exercises` (contracts/attach-technique-to-session.md) via `useAttachTechniqueItems`.
3. States: idle → pending ("Agregando…", spinner, mirrors `TemplatePicker`'s "Adjuntando…" convention) → success (picker collapses, new items appear in the Plan section's technique list, `sonner` success toast) → error (inline `role="alert"`, selections preserved, retry re-submits the identical payload — safe due to server-side dedupe, research.md R4/R11).
4. `mixes_age_bands: true` in the response renders the same informational notice the create flow already implies (non-blocking, research.md R9) — no gate.
5. No "compose new catalog exercise" sub-path here: technique exercises are the catalog itself (there is no reusable intermediate object one level above, unlike strength blocks/interval templates); creating a brand-new custom exercise remains the separate curation flow (`POST /api/technique/exercises`, out of scope for session-attach).

### Strength (existing backend, new frontend preselect + new pick-existing picker — FR-001, FR-002, FR-003)

Two sub-paths, both ending in the same place, mirroring intervals' create-vs-pick-template duality:

- **Pick existing block** (new component, mirrors `TemplatePicker` almost exactly): list of the club's non-archived `StrengthBlock`s (`GET /api/strength/blocks`) with a per-card "Adjuntar a la sesión" button calling the already-existing `POST /api/strength/blocks/{id}/attach` (`useAttachBlock`, `frontend/src/hooks/strength/useStrength.ts:165-184`). States identical to `TemplatePicker`'s (idle/pending/success/error), including a 409 ("ya está adjunto") rendered as a soft "already attached" notice rather than a hard error, since the pair-uniqueness 409 is itself the idempotency backstop (research.md R2/R11).
- **Build new block**: `BlockBuilderPage` at `/strength/blocks/new?session_id={id}` (entry point 1) or `/strength/blocks/new` (entry points 2/3, session picker shown first). Reads `session_id` from `useSearchParams`, skips the current unfiltered/searchable radio list (`BlockBuilderPage.tsx:355-377`) entirely when present, and calls `useAttachBlock` automatically once the block save succeeds — no second manual "choose a session" step for the common case. On success, `navigate('/training/sessions/{id}?section=plan')` (FR-002: "returns the coach to the session") instead of today's "Ver sesión / Seguir editando" choice (`BlockBuilderPage.tsx:303-329`).
- `AgeBandGuardrailDialog` fires exactly where it fires today (block create/update, `services/strength/blocks.py:145-197`) — untouched by either sub-path (research.md R9).

### Intervals (unchanged reference pattern — FR-001 baseline)

No changes. "Crear estructura" (inline `StructureEditor`) and "elegí un template" (`TemplatePicker`, entry point 1 only — intervals has no library-initiated entry point since `/intervals/templates` is removed by spec 029, per `docs/17-coach-ux-redesign/proposal.md` §10 K4) continue exactly as implemented in `SessionDetailPage.tsx:855-1037`. `AgeGateDialog` fires exactly where it fires today.

## Age-gate invocation points (must survive unchanged — FR-006, SC-007)

| Gate | Component | Fires on | Touched by this feature? |
|---|---|---|---|
| Strength age-band guardrail | `AgeBandGuardrailDialog` | 422 `AGE_BAND_GUARDRAIL` from block create/update | No — neither new sub-path touches block create/update logic |
| Intervals age gate (confirm) | `AgeGateDialog` mode=`confirmation` | 422 `age_gate_confirmation_required` from structure/template create/attach | No — unchanged reference pattern |
| Intervals age gate (block) | `AgeGateDialog` mode=`blocked` | 422 `age_gate_z3_blocked` | No — unchanged reference pattern |
| Technique | *(none exists)* | — | Not introduced by this feature (scope boundary, research.md R9) |

## States (all three flows, per 028 standards — FR-009)

| State | Rendering |
|---|---|
| Idle | Picker/form visible, primary action enabled |
| Pending | Primary action shows spinner + in-progress label (e.g. "Adjuntando…", "Agregando…"), disabled; selections/inputs remain visible (not cleared) |
| Success | `sonner` success toast; picker collapses or form resets; Plan section's affected block re-renders with the new content (query invalidation, not a full page reload) |
| Error (network/5xx/cold-start) | Inline `role="alert"` message (cold-start variant reuses `ErrorState`'s `isColdStartError` detector per `specs/028-frontend-design-foundation/contracts/shared-components.md`); selections preserved; retry re-submits the identical payload |
| Error (409 already-attached, strength only) | Soft notice, not a blocking error — the attach is, from the coach's point of view, already done |
| Error (422 age gate) | The relevant gate dialog opens (table above); on cancel, the coach's other selections in the surrounding picker/form are preserved |

## Empty states offering all three actions (FR-005)

Per contracts/session-sections.md, the Plan section's combined empty state (no content of any type yet) surfaces all three attach entry points together, using `specs/028-frontend-design-foundation/contracts/shared-components.md`'s `EmptyState` component (`icon`, `title`, `description`, `action` slot — three instances or one `EmptyState` with a multi-action slot, decided at implementation time).

## Idempotency summary (FR-009)

| Content type | Backstop | Mechanism |
|---|---|---|
| Technique | New (this feature) | Server-side de-dupe on `(training_session_id, exercise_id, segment)` before insert — contracts/attach-technique-to-session.md |
| Strength | Existing | DB `UniqueConstraint(training_session_id, block_id)` → 409 on repeat, caught and rendered as a soft "already attached" notice, not an error |
| Intervals | Existing | DB `UniqueConstraint(training_session_id)` on the structure itself → 409 on repeat attach-template; `age_gate_confirmed` resubmission is itself idempotent (same structure, updated flag) |

All three additionally rely on the client disabling the action while `isPending` (TanStack Query default) as the first line of defense; the table above is the second line, covering the connection-loss-after-server-commit case a disabled button cannot detect (research.md R11).
