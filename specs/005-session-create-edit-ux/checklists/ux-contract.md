# Checklist: UX & Data-Contract Requirements Quality (Release Gate)

**Purpose**: Validate that the requirements in `spec.md` for the session create/edit wizard
are complete, clear, consistent, and measurable — for UX/accessibility and the
data/contract behavior. Unit tests for the requirements, not the implementation.
**Created**: 2026-06-07
**Feature**: [spec.md](../spec.md)
**Focus**: Data & contract, UX & a11y · **Depth**: Release gate · **Audience**: PR reviewer

## Requirement Completeness

- [ ] CHK001 - Are requirements defined for persisting EVERY field shown in the flow, with `session_kind` and `objectives` named explicitly? [Completeness, Spec §FR-001]
- [ ] CHK002 - Is the requirement to expose AND persist `coach_notes` within the same create/edit pass stated (not just "after the session exists")? [Completeness, Spec §FR-002]
- [ ] CHK003 - Are the allowed `session_kind` values treated as authoritative from an existing source rather than redefined in the spec? [Completeness, Spec Assumptions]
- [ ] CHK004 - Are route-file type and size constraints referenced as authoritative (not re-specified) for the in-flow attach? [Completeness, Spec §FR-014, Assumptions]
- [ ] CHK005 - Are loading, empty, and error states required for every async surface (session/athlete load, route upload, save, notification)? [Completeness, Spec §FR-024-adjacent / Constitution III]
- [ ] CHK006 - Is the Render cold-start state required to be surfaced as an explicit state rather than a generic spinner? [Gap — present in plan, confirm spec coverage]
- [ ] CHK007 - Are requirements defined for the parent-view contract (which new fields are exposed vs omitted)? [Completeness, Spec §FR-020]

## Requirement Clarity

- [ ] CHK008 - Is "guided/stepped" resolved to a single concrete structure (multi-step wizard) with no competing interpretation remaining? [Clarity, Spec §FR-006, Clarifications 2026-06-07]
- [ ] CHK009 - Is "in one pass" for the route file defined precisely (auto-upload after create), removing ambiguity about an atomic create-with-file call? [Clarity, Spec §FR-014, Clarifications]
- [ ] CHK010 - Is "inline validation" specified with respect to WHEN errors appear (as the coach progresses vs only on submit)? [Clarity, Spec §FR-007]
- [ ] CHK011 - Is the single, shared Strava-URL rule defined unambiguously and identical for client and server? [Clarity, Spec §FR-013]
- [ ] CHK012 - Is "draft" scoping defined precisely (per user AND per target new/<id>) so the key is unambiguous? [Clarity, Spec §FR-005]
- [ ] CHK013 - Are the three notification outcomes (success / send-failure-retry / no-recipients) each defined as distinct, named states? [Clarity, Spec §FR-015]
- [ ] CHK014 - Is "blocked save" behavior clear about both the summary AND focusing the relevant field? [Clarity, Spec §FR-008]

## Requirement Consistency

- [ ] CHK015 - Do the persistence requirements (FR-001/002) align with the contract delta (`contracts/training-session-api.md`) on which fields create/update accept and read returns? [Consistency, Spec §FR-001 ↔ contracts]
- [ ] CHK016 - Are the parent-privacy requirements consistent across FR-020, FR-021, and the data-model parent-view note (session_kind/objectives exposed; coach_notes/route_file_path omitted)? [Consistency, Spec §FR-020/§FR-021]
- [ ] CHK017 - Is the "notification failure must not roll back a saved session" requirement consistent with the route-upload-failure requirement (both keep the saved session)? [Consistency, Spec §FR-016 ↔ §FR-014]
- [ ] CHK018 - Are touch-target and accessibility requirements stated once and applied consistently to all interactive elements (chips, athlete rows, file picker, step controls)? [Consistency, Spec §FR-009/§FR-010]
- [ ] CHK019 - Does the "no native HTML5 vs Zod competition" requirement align with the inline-validation requirement without conflict? [Consistency, Spec §FR-007]

## Acceptance Criteria Quality (Measurability)

- [ ] CHK020 - Can "every field round-trips" be objectively verified, with a measurable success criterion tied to create AND edit? [Measurability, Spec §SC-001]
- [ ] CHK021 - Is draft restoration measurable (100% of entered fields recovered after interruption)? [Measurability, Spec §SC-002]
- [ ] CHK022 - Are accessibility outcomes measurable (zero automated violations) and target sizes quantified (≥48×48 px)? [Measurability, Spec §SC-005]
- [ ] CHK023 - Is the "no silent notification failure" outcome measurable (100% of notify choices produce an explicit outcome)? [Measurability, Spec §SC-007]
- [ ] CHK024 - Is "single pass, zero save-then-return round-trips" stated as a verifiable criterion for route file + coach notes? [Measurability, Spec §SC-010]
- [ ] CHK025 - Are the time-to-complete targets (tablet <2 min, phone/3G <3 min) bounded enough to be testable? [Measurability, Spec §SC-003]

## Scenario Coverage (Primary / Alternate / Exception / Recovery)

- [ ] CHK026 - Are requirements defined for the create primary flow AND the edit primary flow distinctly (defaults loaded, fields editable)? [Coverage, Spec US1/US2]
- [ ] CHK027 - Are exception-path requirements defined for a failed save (form populated + draft intact, retry possible)? [Coverage/Exception, Spec §FR-017]
- [ ] CHK028 - Are recovery requirements defined for a partial/failed route-file upload that does not block the saved session? [Coverage/Recovery, Spec §FR-014/§FR-016]
- [ ] CHK029 - Are requirements defined for editing an executed/cancelled session (which fields are editable; no silent state change)? [Coverage, Spec §FR-018]
- [ ] CHK030 - Are concurrent-edit requirements defined (warn before overwrite when the session changed server-side)? [Coverage, Spec §FR-019]

## Edge Case Coverage

- [ ] CHK031 - Is the stale/forward-incompatible draft case specified (restore what it can, ignore unknown fields, no crash)? [Edge Case, Spec Edge Cases]
- [ ] CHK032 - Is the "athlete removed/deactivated between draft and save" case specified (coach told which entries were dropped)? [Edge Case, Spec Edge Cases]
- [ ] CHK033 - Is the "no parent has a valid contact" case distinguished from a send failure in the requirements? [Edge Case, Spec §FR-015, Edge Cases]
- [ ] CHK034 - Is the empty athlete selection case specified to block save with a clear message (≥1 required)? [Edge Case, Spec §FR-012]
- [ ] CHK035 - Is the connectivity-drop-mid-save case specified to preserve form + draft for retry? [Edge Case, Spec §FR-017, Edge Cases]

## Non-Functional Requirements (UX, a11y, privacy, performance)

- [ ] CHK036 - Are español-neutro copy requirements stated for all new UI strings, with avoidance of clinical/judgmental language about minors? [Non-Functional, Spec §FR-022]
- [ ] CHK037 - Are minors'-privacy requirements explicit for drafts (sensitive, cleared on save/discard, never logged)? [Non-Functional/Privacy, Spec §FR-021]
- [ ] CHK038 - Are dialog/sheet requirements (focus trap, Escape, explicit close) specified for any modal surface in the flow? [Non-Functional/a11y, Spec §FR-009]
- [ ] CHK039 - Is the bundle/perf expectation for the wizard captured (lazy-load heavy pieces, stay within budget)? [Non-Functional, plan §Performance — confirm spec/SC linkage]

## Dependencies, Assumptions & Boundaries

- [ ] CHK040 - Is the "no Alembic migration / columns already exist" assumption documented and validated against the data model? [Assumption, data-model.md]
- [ ] CHK041 - Is the dependency on the existing route-file upload endpoint and notification mechanism stated rather than assumed? [Dependency, Spec Assumptions]
- [ ] CHK042 - Are the out-of-scope items (clone, prefills, review summary = US5) explicitly excluded so reviewers don't expect them? [Boundary, Spec Out of Scope]

## Ambiguities & Conflicts

- [ ] CHK043 - Is there any remaining ambiguity about whether `objectives`/`session_kind` are visible to parents, or is it explicitly resolved? [Ambiguity, Spec §FR-020]
- [ ] CHK044 - Is the draft-retention/expiry window defined, or explicitly deferred, so reviewers know it is intentional? [Ambiguity/Gap, Clarifications coverage note]
- [ ] CHK045 - Are there conflicting expectations between "notification choice part of the flow" (FR-015) and any residual two-stage save language elsewhere in the spec? [Conflict, Spec §FR-015]

## Notes

- Items reference `spec.md` requirement IDs (FR-/SC-), `contracts/training-session-api.md`,
  `data-model.md`, and `plan.md` where relevant.
- An unchecked item means the requirement text needs tightening before merge — it does NOT
  assert the implementation is wrong.
