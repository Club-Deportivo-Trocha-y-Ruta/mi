# Feature Specification: Coach Surface Subtraction

**Feature Branch**: `claude/coach-profile-ux-analysis-kaar7d`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "Run /speckit-specify for each feature until 033" — feature 2 of 6. Covers phase 2 (subtraction) of the coach experience redesign program (`docs/17-coach-ux-redesign/proposal.md` §10, §12; evidence: `docs/17-coach-ux-redesign/agent-reports/05-simplification-subtraction.md`; program spec: `specs/027-coach-experience-redesign/spec.md`, Story 3).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Remove what nobody can reach (Priority: P1)

The coach uses a product where every visible feature is finished and reachable: the unreachable duplicated screens are gone (cross-race AI hub trio, standalone interval-template screen, standalone technique session builder, gymkhana composer, superseded upload widget), and the one genuinely unique view among them — the season panorama — survives with a visible entry point.

**Why this priority**: ~3,500 lines of confirmed dead or duplicated surface (plus two heavy drawing dependencies) cost maintenance, download size, and coherence on every future change. Removing them first shrinks everything the rest of the program must touch. All removals were confirmed unreachable or duplicated with file-level evidence, and the removal decisions (D1, D4, D6) were approved on 2026-07-11.

**Independent Test**: After the removals: no coach screen is unreachable, the removed screens are gone, the season panorama opens from Competencias, previously shared external links still resolve, and the app's download size is measurably smaller. Every capability reachable before the change is still reachable (except the composer, whose removal was explicitly approved).

**Acceptance Scenarios**:

1. **Given** the duplicated cross-race AI screens (hub, club-by-race view, per-athlete view), **When** the cleanup ships, **Then** they are removed and the per-competition insights view and per-athlete analysis view remain the single homes of that content.
2. **Given** the season panorama (the only unique view among the removed set), **When** the cleanup ships, **Then** it remains fully functional and gains a visible entry from the Competencias area.
3. **Given** the standalone interval-template screen, **When** removed, **Then** browsing and attaching templates remains available where it is actually used — inside session planning.
4. **Given** the standalone technique session builder (which creates a duplicate second session through a parallel path), **When** removed (decision D4), **Then** no coach-visible capability is lost that is not restored by the unified attach flow (feature 032), and until 032 ships, technique content remains manageable through the existing exercise catalog.
5. **Given** the gymkhana circuit composer (decision D1: delete), **When** removed together with its drawing dependencies, **Then** the technique library's existing circuit diagrams remain unchanged.
6. **Given** any previously bookmarked or externally shared address touched by the removals, **When** opened, **Then** it resolves to the appropriate surviving screen under the preserved legacy-redirect policy — never a blank error.

---

### User Story 2 - The athlete profile is the one place for athlete information (Priority: P2)

The coach reviews everything about an athlete from the athlete's profile: technique-skill progress and strength progress appear there under one consolidated "Progreso" area, and the athlete's wellbeing (competitive anxiety) view is one tap away with the athlete preselected.

**Why this priority**: Both progress boards are fully built, their own back-links assume arrival from the athlete profile, yet no forward link exists anywhere — the coach literally cannot reach them today. Consolidating them where they belong fixes two orphans and strengthens the athlete-360 mental model.

**Independent Test**: From an athlete's profile, open technique progress, strength progress, and the anxiety view (athlete preselected) without typing a URL; verify the profile does not exceed 7 sections.

**Acceptance Scenarios**:

1. **Given** an athlete's profile, **When** the coach reviews it, **Then** technique and strength progress are available under one consolidated "Progreso" area (an internal toggle, not two extra top-level sections), and the profile's top-level sections do not exceed 7.
2. **Given** the consolidated progress area, **When** it ships, **Then** the two standalone progress screens are removed and their content lives on in the profile.
3. **Given** an athlete's profile, **When** the coach opens the wellbeing pointer, **Then** the anxiety view opens with that athlete preselected (today it always starts from an empty selector).

---

### User Story 3 - Finish the half-built anxiety interpretation (Priority: P2)

For an athlete with guardian consent, the coach can request an on-demand interpretation of a completed anxiety questionnaire directly from the individual anxiety view — a capability fully built on the server but never connected to any screen (decision D2: wire it in).

**Why this priority**: The work is already paid for (service, safeguards, fallback, tests all exist); one small connection completes an approved capability of the anxiety module. Leaving it half-built was the only alternative and was rejected.

**Independent Test**: As coach, open a consented athlete's completed assessment in the individual anxiety view, request the interpretation, and verify: baseline-anchored wording, no diagnostic labels, coach-only visibility, and a graceful rule-based fallback when the AI service is unavailable.

**Acceptance Scenarios**:

1. **Given** a completed assessment for a consented athlete, **When** the coach requests an interpretation, **Then** it appears in the individual anxiety view with in-progress feedback while generating.
2. **Given** the generated interpretation, **When** displayed, **Then** it is baseline-anchored, framed in process/effort/coping language, contains no diagnostic labels, and is visible to the coach only.
3. **Given** the AI service is unavailable or the monthly budget is exhausted, **When** the coach requests an interpretation, **Then** the rule-based fallback interpretation is shown and the limitation is explained in plain language.
4. **Given** an athlete without the required guardian consent, **When** the coach views their record, **Then** no interpretation can be requested and the reason is stated.

---

### Edge Cases

- **External deep links** (parent emails, Spond posts) to removed screens: must resolve via the preserved legacy-redirect policy; the planned final transition of old redirects must not strand any address.
- **In-flight browser tabs**: a coach with a removed screen already open must, on next navigation, land somewhere sensible — not a blank error.
- **Season panorama entry with no season data**: the new entry point must show a purposeful empty state.
- **Anxiety safeguards under failure**: repeated interpretation requests must not queue duplicate generations; consent revocation mid-session must immediately block further requests.
- **Profile section limit**: consolidating progress must not push the athlete profile beyond 7 sections on any viewport.
- **No capability regression window**: the technique builder's removal (this feature) precedes the unified attach flow (032); during that window the exercise catalog remains fully usable and session planning is unaffected — only the (previously unreachable) standalone assembly path is gone.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The duplicated cross-race AI screens (hub, club-by-race, per-athlete) MUST be removed; the per-competition insights view and per-athlete analysis view remain the single homes of that content.
- **FR-002**: The season panorama MUST be retained, relocated out of the removed set, and given a visible entry from the Competencias area (program decision D6).
- **FR-003**: The standalone interval-template screen MUST be removed; template browsing/attaching remains available inside session planning.
- **FR-004**: The standalone technique session builder MUST be removed (program decision D4); it MUST NOT be removed in a way that blocks the later unified attach flow (feature 032) from restoring session-assembly capability.
- **FR-005**: The gymkhana circuit composer MUST be removed together with its drawing-specific dependencies (program decision D1); the technique library's existing circuit diagrams remain unchanged.
- **FR-006**: The superseded upload widget and other confirmed-dead presentation code identified in the audit MUST be removed; duplicated confirmation dialogs and duplicated label helpers MUST be consolidated to single implementations, including retiring the obsolete "round 99" championship convention in presentation code.
- **FR-007**: The athlete profile MUST consolidate technique and strength progress under one "Progreso" area (internal toggle; profile sections ≤ 7) and the two standalone progress screens MUST then be removed.
- **FR-008**: The athlete profile MUST offer a wellbeing pointer that opens the anxiety view with the athlete preselected.
- **FR-009**: The anxiety on-demand interpretation MUST be wired into the individual anxiety view (program decision D2) preserving every existing safeguard: coach-only access, guardian-consent gate, baseline-anchored wording, no diagnostic labels, and the rule-based fallback when the AI service is unavailable. This is presentation wiring of an existing, tested capability — no server-side changes.
- **FR-010**: All removals combined MUST NOT reduce reachable user capability beyond the explicitly approved removals (composer; standalone builder pending 032), MUST NOT change stored data, and MUST keep every previously shared address resolving under the legacy-redirect policy.

### Key Entities

No new domain data. Removals affect presentation surface only; all stored records (exercises, sessions, assessments, analyses) are untouched.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 6 screens and roughly 3,500 lines of presentation code are removed, including two heavy drawing dependencies dropped from the app's payload.
- **SC-002**: 0 unreachable screens remain among retained features (today: 9 unreachable).
- **SC-003**: 0 previously shared external links break: 100% of affected addresses resolve to a sensible surviving screen.
- **SC-004**: The coach reaches an athlete's technique or strength progress from the athlete profile in at most 2 interactions (today: impossible without typing a URL).
- **SC-005**: The athlete profile has at most 7 top-level sections after consolidation.
- **SC-006**: For a consented athlete with a completed assessment, the coach obtains an interpretation (AI or fallback) in under 60 seconds end-to-end, with zero diagnostic-language violations in generated output.
- **SC-007**: The app's initial download size does not increase, and the technique area's payload shrinks measurably after the composer and builder removals.

## Assumptions

- **Program context**: feature 2 of 6 (specs 028–033), derived from program spec `specs/027-coach-experience-redesign` (Story 3) and proposal §10; recommended to ship after 028 and before the navigation regroup (030) so the new navigation only presents surviving screens.
- **Decisions applied (all resolved 2026-07-11)**: D1 delete composer; D2 wire anxiety interpretation; D4 remove standalone technique builder; D6 remove duplicated insights screens, keep season panorama. No open decisions remain.
- **Ordering note**: the unified attach flow is feature 032; between 029 and 032 the only capability gap is the previously unreachable standalone assembly path, which no user could reach anyway.
- **Anxiety module (constitution Principle V)**: all safeguards are preserved verbatim — this feature adds no new interpretation logic, changes no scoring, and never auto-messages athletes or parents.
- **Test bookkeeping**: routing-guard and navigation tests that assert the removed screens' behavior are updated as part of this feature — expected churn, not user-facing risk.
- **Scope boundary**: no navigation regrouping (030), no new home content (031), no visual re-theming (033); folder reorganizations invisible to users are allowed where they fall out of the removals.
