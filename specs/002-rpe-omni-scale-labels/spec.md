# Feature Specification: RPE OMNI Scale Labels Refactor

**Feature Branch**: `002-rpe-omni-scale-labels`

**Created**: 2026-06-05

**Status**: Draft

**Input**: User description: "Refactor of RPE OMNI in its scale of text in frontend. it´s so confuse to say that de moderate it´s 3 level. Moderate could be 6 or 7, so re-evaluate the text or scale."

## Context

When the coach records a training session's perceived exertion, the interface shows an OMNI scale from 0 to 10. Each number is paired with a text descriptor and an emoji face. Today the descriptor "Moderado" (Moderate) is attached to level **3**, while the remaining descriptors escalate ("Algo difícil", "Difícil", "Muy difícil", "Muy muy difícil", "Extremo", "Máximo casi", "Máximo") in a way that does not match how a person naturally maps effort words onto a 0–10 scale.

The problem reported by the coach: on a 0–10 scale, "moderate" effort is intuitively somewhere around the **middle (6–7)**, not near the low end (3). The current wording makes the coach hesitate and second-guess which number to pick, which undermines the reliability of the single most important intensity-monitoring metric for youth athletes (RPE is the primary tool per the club's training principles; heart rate is secondary).

This is a **wording/labeling change only**. The underlying stored value remains an integer from 0 to 10. No change to data storage, history, calculations, or how RPE feeds into reports.

## Clarifications

### Session 2026-06-05

- Q: Which exact descriptor strings are canonical for the 0–10 scale? → A: The research-ratified OMNI ramp (defines all 11 values): `0 Reposo · 1 Muy fácil · 2 Fácil · 3 Ligero · 4 Algo fácil · 5 Moderado · 6 Algo duro · 7 Duro · 8 Muy duro · 9 Muy muy duro · 10 Máximo`. This supersedes the earlier illustrative mapping and is the canonical wording used by plan.md, research.md, and tasks.md.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Coach reads an effort descriptor that matches the number (Priority: P1)

The coach finishes a session and opens the attendance/rubric panel to record each athlete's perceived exertion. As they move the OMNI slider, the text descriptor next to the number reads in a way that feels natural: low numbers describe light effort, the middle of the scale describes moderate effort, and high numbers describe maximal effort. The coach can pick a value confidently without mentally re-mapping the word against the number.

**Why this priority**: This is the core of the request. If the descriptors do not align intuitively with the numbers, the coach enters inconsistent RPE values, degrading the quality of every downstream metric and report that relies on perceived exertion.

**Independent Test**: Open the rubric panel, move the OMNI control across all values 0 through 10, and confirm each number shows a descriptor whose intensity sense increases monotonically and places "moderate" effort at the middle of the scale rather than near the bottom.

**Acceptance Scenarios**:

1. **Given** the coach is recording perceived exertion, **When** they select the middle of the scale (around 5–7), **Then** the descriptor communicates a moderate / sustained effort rather than a near-rest effort.
2. **Given** the coach moves the control from 0 to 10, **When** they read each descriptor in sequence, **Then** the perceived intensity of the wording never decreases as the number increases (monotonic ordering).
3. **Given** the coach selects 0, **When** they read the descriptor, **Then** it clearly communicates rest / no effort; **and** at 10 it clearly communicates maximal effort.

---

### User Story 2 - Descriptors stay consistent with the club's training language (Priority: P2)

The descriptors and any accompanying conversational cues use the same simplified effort language the club already uses with young athletes (e.g., the "talk test" framing: easy conversation pace, can say short sentences, can only say a word or two, cannot speak), so the coach and athletes share one vocabulary.

**Why this priority**: Consistency reduces ambiguity and reinforces the coaching method, but the feature still delivers value even if only the numeric alignment from Story 1 is shipped.

**Independent Test**: Compare the on-screen descriptors against the club's documented RPE / talk-test language and confirm they are compatible and non-contradictory.

**Acceptance Scenarios**:

1. **Given** the refreshed scale, **When** the coach reads a mid-to-high descriptor, **Then** the wording is consistent with the club's existing effort vocabulary and does not introduce conflicting terminology.

---

### Edge Cases

- **Existing records**: Sessions already saved with a given RPE number keep that exact number. Only the displayed descriptor for that number changes; no historical value is rewritten or migrated.
- **No value selected**: When no RPE has been entered yet, the control shows its neutral/default state without implying a recorded effort.
- **Boundary values**: 0 and 10 must each have an unambiguous descriptor (rest and maximal, respectively).
- **Accompanying emoji/faces**: If pictorial faces accompany the descriptors, their progression must stay aligned with the refreshed wording so face and text never contradict each other.
- **Parent-facing view**: Where parents see RPE as a bare number (e.g., "7/10"), behavior is unchanged; this feature does not add descriptors to the parent view.
- **Automated checks**: Any existing UI tests that assert specific descriptor text will need updating to the new wording (implementation concern, flagged here for awareness).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The OMNI effort scale displayed to the coach MUST keep the numeric range 0 to 10 inclusive, with integer steps.
- **FR-002**: Each numeric value 0–10 MUST display exactly one text descriptor.
- **FR-003**: The descriptors MUST be ordered so that perceived intensity is non-decreasing as the number increases (monotonic), with 0 = rest/no effort and 10 = maximal effort.
- **FR-004**: The word for "moderate" effort (and equivalent mid-range wording) MUST be positioned at the middle of the scale (approximately the 5–7 band), not at the low end.
- **FR-005**: Descriptors MUST be written in español neutro (Colombia), consistent with all other product-facing copy.
- **FR-006**: The change MUST NOT alter the stored RPE value, its data type, its valid range, or how previously recorded values are interpreted.
- **FR-007**: Previously recorded sessions MUST continue to display their stored numeric value; only the descriptor text shown for that number may differ from before.
- **FR-008**: If pictorial faces/emoji accompany the scale, their visual progression MUST remain consistent with the refreshed descriptors (no face that contradicts its text).
- **FR-009**: The descriptors MUST be understandable to the coach without training, such that selecting a value requires no mental re-mapping between word and number.
- **FR-010**: The refreshed wording MUST be compatible with the club's existing simplified effort language (talk-test cues) and MUST NOT contradict the club's training principles documentation.

### Key Entities *(include if feature involves data)*

- **Perceived Exertion (RPE OMNI) value**: An integer 0–10 recorded per athlete per session. Unchanged by this feature. Only its human-readable descriptor presentation is affected.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every value 0 through 10, a reviewer confirms the descriptor's intensity sense is non-decreasing across the full scale (0 ordering errors).
- **SC-002**: "Moderate"-class wording appears in the middle band of the scale (within values 5–7) and no longer at value 3.
- **SC-003**: In a quick usability check, the coach selects an RPE value for a described effort without expressing confusion or re-mapping the word against the number (qualitative pass).
- **SC-004**: 100% of previously recorded RPE values still display their original number after the change (no data drift).
- **SC-005**: The descriptors are reviewed against the club's documented effort language and found non-contradictory (qualitative pass).

## Assumptions

- The change is limited to the coach-facing perceived-exertion control; the parent-facing view (bare number) is out of scope.
- The numeric 0–10 OMNI scale is retained; the request is to fix the **wording**, not to switch to a different scale (e.g., 1–10 or 6–20 Borg). Retaining the validated children's OMNI 0–10 range is consistent with the club's training reference material.
- No database migration is required because no stored values change.
- **Chosen direction (confirmed with coach)**: keep the existing short-word descriptor style and the 0–10 scale, but **redistribute the words** so they spread evenly and "Moderado" lands at the middle of the scale. This is the "re-map words to numbers" approach (smallest change), not a switch to talk-test phrasing or a different numeric scale. **Canonical mapping** (ratified — see Clarifications 2026-06-05): `0 Reposo · 1 Muy fácil · 2 Fácil · 3 Ligero · 4 Algo fácil · 5 Moderado · 6 Algo duro · 7 Duro · 8 Muy duro · 9 Muy muy duro · 10 Máximo`. Every value 0–10 carries exactly one word (FR-002).
- The talk-test cues from the reference doc may still be used as secondary/helper text but are not the primary descriptor wording for this change.
- Existing automated UI tests referencing descriptor text will be updated as part of implementation.
