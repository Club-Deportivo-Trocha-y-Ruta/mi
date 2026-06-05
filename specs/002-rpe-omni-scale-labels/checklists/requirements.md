# Specification Quality Checklist: RPE OMNI Scale Labels Refactor

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-06-05
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`
- The exact final descriptor strings are intentionally deferred to planning; the spec fixes the structural contract (monotonic ordering, mid-scale "moderate", 0–10 range retained, no data change). This is an assumption, not an unresolved clarification.

---

# Pre-Merge Review Gate: RPE OMNI Scale Labels Refactor

**Purpose**: Validate that the shipped wording satisfies the written requirements before merging the PR. Focus: wording/UX requirements quality (primary) + cross-artifact consistency with `research.md`, `contracts/rpe-omni-labels.md`, and `docs/01-marco-teorico.md`.
**Created**: 2026-06-05
**Depth**: Standard pre-merge gate
**Audience**: Reviewer (PR)

## Requirement Completeness

- [ ] CHK001 Are all 11 descriptor strings (values 0–10) listed verbatim somewhere in the spec, rather than only referenced implicitly through the Clarifications section? [Completeness, Spec §FR-002, §Clarifications]
- [ ] CHK002 Does FR-008 (emoji/face alignment) include a concrete acceptance criterion for the face at index 5 — e.g., specifying it must read as "neutral/moderate" — or is the visual mapping left entirely to implementor judgment? [Completeness, Spec §FR-008]
- [ ] CHK003 Is the display requirement for the "no value selected" state (neutral/default) defined for both the label and the face, or only mentioned as an edge case without a required behavior? [Completeness, Edge Case, Spec §Edge Cases]

## Requirement Clarity

- [ ] CHK004 Does FR-004's "approximately the 5–7 band" conflict with the contract's exact guarantee G1 (`RPE_LABELS[5] === "Moderado"`)? If the intent is exactly index 5, is FR-004 precise enough to prevent a reviewer from accepting index 6 or 7 as also compliant? [Clarity, Conflict, Spec §FR-004 vs contracts/rpe-omni-labels.md §G1]
- [ ] CHK005 Is FR-009 ("understandable to the coach without training, no mental re-mapping required") operationalized by a measurable acceptance scenario — or is SC-003 ("selects a value without expressing confusion") the only criterion, and is that criterion's method of evaluation (who conducts it, how) defined? [Clarity, Measurability, Spec §FR-009, §SC-003]
- [ ] CHK006 Does FR-003 specify "non-decreasing" or "strictly increasing"? Is the distinction documented so a reviewer can tell whether two adjacent identical labels (e.g., two synonyms at consecutive integers) would pass or fail? [Clarity, Spec §FR-003, §SC-001]
- [ ] CHK007 Is FR-005 ("español neutro, Colombia") accompanied by a testable criterion (e.g., "diacritics required, no clinical or judgmental terms") in the spec body, or does the verifier have to cross-reference the contract's G6 and the Constitution for the definition? [Clarity, Spec §FR-005 vs contracts/rpe-omni-labels.md §G6]

## Cross-Artifact Consistency

- [ ] CHK008 Does the 11-label mapping in spec.md §Clarifications match verbatim the table in `research.md` §Decision and the table in `contracts/rpe-omni-labels.md` §Required mapping, with no label differing in spelling, diacritics, or index position? [Consistency, Spec §Clarifications vs research.md §Decision vs contracts §Required mapping]
- [ ] CHK009 Does FR-006 ("MUST NOT alter the stored RPE value, its data type, its valid range, or how previously recorded values are interpreted") cover the slider attribute guarantees in contract G5 (`min`, `max`, `aria-valuenow`, no behavioral regression), or does G5 introduce requirements not traceable to any spec FR? [Consistency, Gap, Spec §FR-006 vs contracts/rpe-omni-labels.md §G5]
- [ ] CHK010 Are the talk-test cues listed in `research.md` §Decision (e.g., "frases cortas" at 5–6, "1–2 palabras" at 7–8) consistent with the Z1–Z5 zone descriptions in `docs/01-marco-teorico.md`, and is any discrepancy explicitly documented as an acceptable simplification? [Consistency, research.md §Decision vs docs/01-marco-teorico.md]
- [ ] CHK011 Is the out-of-scope boundary for the parent view ("bare number `v/10`, no descriptor") stated consistently in the spec §Assumptions, the contract §Out of scope, and the plan, with no contradiction between them? [Consistency, Spec §Assumptions vs contracts/rpe-omni-labels.md §Out of scope]

## Edge Case Coverage

- [ ] CHK012 Does FR-008 define requirements for emoji/faces at boundary values 0 and 10 with the same specificity as for the labels (FR-003 endpoints), or does the face contract rely solely on `research.md`'s informal guidance ("calm/rested at 0, strained at 10")? [Coverage, Edge Case, Spec §FR-008 vs contracts §G4]
- [ ] CHK013 Is there a spec requirement (or contract guarantee) that both `RPE_LABELS` and `RPE_FACES` must have length exactly 11, and that an array length mismatch is a defect rather than a degraded-but-acceptable state? [Edge Case, Completeness, contracts/rpe-omni-labels.md §G4]

## Non-Functional Requirements

- [ ] CHK014 Is the WCAG 2.1 AA requirement for the descriptor text (contrast, keyboard navigability, focus ring) explicitly stated in the spec, or does a reviewer have to import it from Constitution §III? If imported, is the import path unambiguous? [Completeness, Gap, Spec vs Constitution §III]
- [ ] CHK015 Does the spec include an explicit requirement to preserve `aria-label`/`aria-valuenow` and the slider's ARIA semantics, or is this only expressed in contract G5 and plan.md — outside the spec boundary? [Completeness, Gap, Spec §FR-006 vs contracts/rpe-omni-labels.md §G5]

## Test and Invariant Requirements

- [ ] CHK016 Is each contract guarantee (G1–G3: Moderado@5, not-Moderado@3, Reposo@0/Máximo@10) traceable to a specific spec success criterion (SC-001/SC-002), such that a failing test maps unambiguously to a violated requirement? [Traceability, Spec §SC-001, §SC-002 vs contracts/rpe-omni-labels.md §Guarantees]
- [ ] CHK017 Does the spec explicitly require that existing UI tests asserting old descriptor text ("Moderado" at 3, etc.) be updated as part of the change, or is this addressed only in plan.md §Testing and spec §Edge Cases as an "awareness" flag rather than a mandatory deliverable? [Completeness, Spec §Edge Cases vs plan.md §Testing]

## Merge Readiness Gate

- [ ] CHK018 Are the four key assumptions still valid at merge — (a) no DB migration required, (b) parent view unchanged, (c) 0–10 range retained, (d) canonical mapping coach-confirmed — and is there a stated verification step in the spec or plan for each? [Measurability, Spec §Assumptions]
- [ ] CHK019 Does SC-003 ("coach selects an RPE value without expressing confusion") define the evaluator, the method (e.g., in-person walkthrough, recorded session), and a binary pass/fail criterion — or is "without confusion" too subjective to gate a merge? [Measurability, Spec §SC-003]
- [ ] CHK020 Is SC-004 ("100% of previously recorded RPE values display their original number after the change") testable within the PR review environment (e.g., against local seed data), or does it require production database access — and if the latter, is a substitute verification method defined? [Measurability, Spec §SC-004]
