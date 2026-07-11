# Feature Specification: Visual Coherence & Polish

**Feature Branch**: `claude/coach-profile-ux-analysis-kaar7d`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "Run /speckit-specify for each feature until 033" — feature 6 of 6. Covers the visual half of phase 1 plus phase 6 (polish) of the coach experience redesign program (`docs/17-coach-ux-redesign/proposal.md` §8, §11, §13; evidence: `docs/17-coach-ux-redesign/agent-reports/04-product-design-modern-patterns.md`; program spec: `specs/027-coach-experience-redesign/spec.md`, Stories 6–7).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One meaning per color, everywhere (Priority: P1)

Wherever the coach sees a status — sync state, session state, consent state, analysis freshness, newsletter state, chart reference — the colors mean exactly one thing: green = success/complete, amber = partial/attention, red = error/blocking, neutral gray = informational; always paired with an icon or label, never color alone. Race classes A/B/C read as an ordered intensity scale, never as good/bad.

**Why this priority**: Six independent status-label systems and ad-hoc chart colors currently dilute meaning, and the constitution mandates these exact semantics. One vocabulary applied everywhere is the highest-leverage visual fix and unblocks the chart and module work below.

**Independent Test**: Inventory every status presentation across coach modules and charts: each maps to the shared vocabulary, pairs color with icon/label, and no color is used with a conflicting meaning anywhere; A/B/C badges read as an ordered ramp.

**Acceptance Scenarios**:

1. **Given** any status anywhere in the coach app, **When** it renders, **Then** it uses the shared status vocabulary (green/amber/red/neutral) with an icon or text label — never color alone.
2. **Given** the race-class labels A/B/C, **When** colored, **Then** they present as an ordered intensity scale (taper effort), not as status colors.
3. **Given** the same state shown in two modules (e.g., "outdated" for an analysis and for a consent), **When** compared, **Then** the presentation is identical in color, shape, and wording convention.

---

### User Story 2 - Charts that read correctly (Priority: P2)

The performance charts follow one honest, legible style: solid hairline grids, the athlete's own series in the product accent, best/worst references in the shared status colors, the championship point marked on the data point itself, crowded reference labels capped before they overlap, and the existing small-sample table fallback preserved — with a table view available for the main chart data.

**Why this priority**: The charts carry sensitive judgments about children's performance; today they use dashed "projection-style" grids, four ad-hoc color sets, and a championship marker that exists only in a text legend. Reading errors here have real coaching consequences.

**Independent Test**: Render the distribution and evolution charts across data shapes (normal field, 10–15-rider field, small sample, championship present): verify grid style, color roles, on-point championship marking, label capping, table fallback, and table view.

**Acceptance Scenarios**:

1. **Given** any performance chart, **When** it renders, **Then** grids are solid hairlines, the athlete's own series uses the product accent, and best/worst references use the shared status colors.
2. **Given** a season evolution including a championship, **When** rendered, **Then** the championship point is visually distinct on the data point itself, not only in text below.
3. **Given** a category with many riders, **When** reference lines render, **Then** labels are capped/decluttered before overlapping into unreadability.
4. **Given** a small sample, **When** the chart would mislead, **Then** the existing table fallback continues to appear; **and** for normal samples a table view of the same data is available.

---

### User Story 3 - The newer modules stop looking bolted-on (Priority: P2)

The technique, strength, intervals, and anxiety modules look and feel like the same product as the rest: same text colors, same headings, same shared components — indistinguishable in style from the competitions module.

**Why this priority**: These four modules (built later) use an off-brand style throughout, which reads as a different application inside the sidebar. With the shared foundation from 028 in place, this is a mechanical but high-visibility alignment pass.

**Independent Test**: Side-by-side visual audit of a screen from each of the four modules against a competitions screen: typography, text colors, headers, empty/error states, and status labels are indistinguishable in style.

**Acceptance Scenarios**:

1. **Given** any screen in técnica, fuerza, intervalos, or ansiedad, **When** compared with the rest of the app, **Then** text colors, headings, components, and state presentations match the shared system (no off-brand styling remains).
2. **Given** the near-identical catalog experiences of técnica and fuerza, **When** the pass completes, **Then** they present one consistent library experience (same filtering, cards, detail layout) differing only in domain content.

---

### User Story 4 - AI that presents one identity (Priority: P2)

Every AI capability the coach meets presents one identity: named "Insights IA", launched with "Analizar con IA", marked with one icon, showing one freshness vocabulary (none / fresh / outdated with manual re-run), the same in-progress run view at every entry point, and — before launching — the expected wait and remaining monthly AI budget, instead of only failing afterward.

**Why this priority**: AI appears in seven-plus places under five names with mixed icons and per-surface freshness models; budget and concurrency limits surface only as errors after the click. Unifying identity and making cost/latency proactive builds warranted trust in the program's most novel capability.

**Independent Test**: Visit every AI entry point (session assistant, per-competition insights, per-athlete analysis, race chat, anxiety interpretation): one name, one verb, one icon, one freshness presentation, the same run-progress view, and a pre-launch wait/budget hint; exhaust the budget in a test environment and verify the state is communicated before launch.

**Acceptance Scenarios**:

1. **Given** any AI entry point, **When** the coach encounters it, **Then** the naming is "Insights IA" (noun) / "Analizar con IA" (action) with one consistent icon.
2. **Given** an analysis in progress, **When** viewed from any entry point, **Then** the same run-progress presentation appears (full or compact variant of one view).
3. **Given** an existing analysis, **When** its inputs have changed, **Then** the shared freshness vocabulary marks it outdated everywhere it appears, and re-running is always an explicit manual action.
4. **Given** the monthly AI budget near or at its limit, **When** the coach views any launch control, **Then** expected wait and remaining budget are communicated before launching, and an exhausted budget disables launch with a plain-language explanation.
5. **Given** the race chat, **When** opened, **Then** a brief notice explains the conversation is not saved.

---

### User Story 5 - Comfort polish (Priority: P3 — optional, capacity permitting)

Evening and desk use get quality-of-life improvements: a dark appearance following the device preference at the same contrast bars, and keyboard shortcuts for the desktop planning session.

**Why this priority**: Genuinely useful (dusk field sessions; desk planning) but deferrable without harming the program; explicitly last and optional. The command palette remains deferred by program decision D5.

**Independent Test**: Switch the device to dark appearance and audit coach screens for legibility and contrast; on desktop, navigate between the main areas and trigger creation via documented shortcuts.

**Acceptance Scenarios**:

1. **Given** a device set to dark appearance, **When** the coach uses any coach surface, **Then** it renders a legible dark theme meeting the same contrast bars as light mode.
2. **Given** a desktop session, **When** the coach uses the documented shortcuts, **Then** they can jump between main areas and open quick-create without the pointer.

---

### Edge Cases

- **Color-vision deficiencies**: status must remain distinguishable with icons/labels alone; charts must not encode meaning in color alone.
- **Printing/PDF exports**: report and newsletter documents keep their own established styling — this feature restyles the app, not the generated documents.
- **Dark mode with media**: photos, illustrations, and charts must remain legible on dark surfaces (no invisible dark-on-dark marks).
- **Chart extremes**: single-rider categories (no best/worst distinct from self), all-DNF fields, and missing baselines must render sensibly with the new style.
- **AI budget race conditions**: budget state shown pre-launch may be stale; launching must re-validate and fail gracefully with the standard message.
- **Anxiety module restyle**: visual alignment must not alter any Principle V safeguard, wording rule, or consent gate — style only.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: One accent color and one status vocabulary (green success / amber attention / red error / neutral informational, always icon+label) MUST apply across all coach surfaces; conflicting or duplicate status presentations MUST be consolidated into the shared system established in 028.
- **FR-002**: Race classes A/B/C MUST present as an ordered intensity scale, never as status colors.
- **FR-003**: Charts MUST use solid hairline grids, the accent for the athlete's own series, status colors for best/worst references, on-point marking for championships, capped reference labels, the preserved small-sample table fallback, and an available table view of charted data.
- **FR-004**: The técnica, fuerza, intervalos, and ansiedad modules MUST adopt the shared visual language (colors, headings, components, states) with no off-brand styling remaining; técnica and fuerza MUST present one consistent library experience.
- **FR-005**: All AI capabilities MUST share one identity: "Insights IA" (noun), "Analizar con IA" (action), one icon, one freshness vocabulary (none / fresh / outdated), manual-only re-run, and one run-progress presentation (full or compact) at every entry point.
- **FR-006**: Expected wait and remaining monthly AI budget MUST be communicated before launching an analysis; exhausted budget or concurrency limits MUST disable launch with a plain-language explanation; launch MUST re-validate limits at execution.
- **FR-007**: The race chat MUST display a brief notice that conversations are not saved.
- **FR-008** *(optional)*: All coach surfaces MUST support a dark appearance honoring the device preference, meeting the same contrast bars as light mode.
- **FR-009** *(optional)*: Desktop keyboard shortcuts MUST cover area navigation and quick-create, and be discoverable in the product. A command palette is explicitly out of scope (program decision D5) unless separately justified later.
- **FR-010**: This feature MUST NOT change generated documents (reports, newsletters, PDF instructives), stored data, permissions, or any anxiety-module safeguard — presentation only.

### Key Entities

No new domain data. All changes are visual-system and presentation consolidation over existing screens; the AI budget/wait hints read existing operational signals.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of status presentations across coach surfaces use the shared vocabulary with icon or label (today: 6 independent systems, some color-only).
- **SC-002**: A style audit finds the four newer modules indistinguishable from the rest of the app (today: they use a visibly different palette throughout).
- **SC-003**: Exactly one name, one verb, and one icon for AI across the app (today: 5+ names, 3+ icons).
- **SC-004**: 0 AI launches fail due to budget/concurrency without the coach having been shown the limit beforehand (today: limits surface only as post-click errors).
- **SC-005**: Charts pass a readability audit: no dashed grids, championship visible on the point itself, no overlapping reference labels at 15 riders, table access available for every chart (today: none of these hold).
- **SC-006**: With dark appearance enabled, 100% of audited coach screens meet the same contrast bars as light mode (if the optional story ships).
- **SC-007**: 0 regressions in generated documents and 0 changes to anxiety-module wording/safeguards, verified by existing tests.

## Assumptions

- **Program context**: feature 6 of 6 (specs 028–033), program Stories 6–7, proposal §8/§11 and phase 6. Depends on 028 (tokens, shared status vocabulary, brand font) and lands best last, as a sweep over the surfaces the earlier features stabilized.
- **Decision D5 (resolved 2026-07-11)**: the command palette stays deferred; keyboard shortcuts (optional) do not include it.
- **Chat non-persistence** is a deliberate privacy default for a minors' product — this feature labels it rather than adding persistence.
- **Accent choice**: the product's existing accent (already used by primary actions and links under two names) is formalized as *the* accent; the unused secondary brand color is retired from the app palette. The design-system document is updated to match shipped reality.
- **Dark mode sequencing**: the optional dark appearance requires the 028 token/shadow consolidation; it must not ship before it.
- **Scope boundary**: no structural, navigation, or flow changes (029–032); no changes to AI pipelines, prompts, scoring, or budgets themselves — only how their state is presented.
