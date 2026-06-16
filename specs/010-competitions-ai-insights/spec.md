# Feature Specification: AI Race Analysis in the Competitions Module — Restore Access and Enhance Insights

**Feature Branch**: `010-competitions-ai-insights`

**Created**: 2026-06-09

**Status**: Draft

**Input**: User description: "AI race analysis in the competitions module — restore access and enhance insights. The club's AI race-analysis capability is fully built on the backend (it can analyze each athlete's Copa Valle results, produce coach-reviewed insights, and answer questions in chat) but the coach cannot reach it from the competitions screen — there is no 'launch analysis' control there, only a read-only insights view. Beyond restoring access, the coach wants the insights themselves to be richer: not just a per-race read, but season-level context that helps guide each rider's development."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Launch group AI analysis from the competition's Insights tab (Priority: P1)

The coach opens a competition that already has imported results, goes to the Insights tab, and presses a single "Analizar con IA" action that starts an AI analysis covering every club athlete with results in that válida. The existing coach-approval (human-in-the-loop) step is preserved: the coach reviews and approves intermediate steps before insights are persisted. When the run completes, the resulting insights appear in the same Insights tab.

**Why this priority**: This is the root cause of the reported problem ("there are no AI options in competitions"). It restores access to an already-built capability and removes the current workaround of visiting each athlete's profile one by one. Without it, the rest of the feature has no anchor.

**Independent Test**: Can be fully tested by importing results for a competition, pressing the launch action in the Insights tab, completing the approval step, and verifying reviewed insights appear for every athlete with results — without ever leaving the competition screen.

**Acceptance Scenarios**:

1. **Given** a competition with committed results and no prior analysis, **When** the coach opens the Insights tab, **Then** a clearly visible launch action is available (coach/admin only).
2. **Given** the coach launches the group analysis, **When** the run reaches a step that requires human review, **Then** the coach is prompted to approve or correct it before the run continues, exactly as in the existing per-athlete flow.
3. **Given** the run completes successfully, **When** the coach views the Insights tab, **Then** insights for all analyzed athletes of that válida are listed without a page reload being required.
4. **Given** a competition with no committed results, **When** the coach opens the Insights tab, **Then** the launch action is disabled with a message explaining that results must be imported first.
5. **Given** a parent-role user views the competition, **When** they open any tab, **Then** no AI launch controls are visible to them.

---

### User Story 2 - Season-aware, richer insights (Priority: P2)

When an analysis runs for a válida, each athlete's insight includes season-level context: how this result compares with the athlete's previous válidas of the calendar year (position, category, field size), the direction of their progression, and a narrative that frames the result within the rider's development — always aligned with the club's non-negotiable principles (fun first, skills before fitness, biological age over chronological age).

**Why this priority**: This is the "potencializar" half of the request. Restoring access alone gives the coach what already existed; the coach explicitly asked for insights that answer "how is the rider progressing across the season", not just "how did the rider do today".

**Independent Test**: Can be tested by running an analysis for an athlete who has results in at least two válidas of the season and verifying the produced insight references the prior válidas, states a progression direction, and contains a development-framed narrative; and by running it for an athlete with a single válida and verifying the insight degrades gracefully (no fabricated comparisons).

**Acceptance Scenarios**:

1. **Given** an athlete with results in two or more válidas this season, **When** an analysis runs, **Then** the insight includes a comparison with the athlete's prior válidas and an explicit progression read (improving, stable, declining, or mixed).
2. **Given** an athlete whose only result this season is the analyzed válida, **When** the analysis runs, **Then** the insight states that this is the rider's first reference of the season and makes no cross-race comparison.
3. **Given** any produced insight, **When** the coach reads it, **Then** the narrative never recommends actions that contradict the club's non-negotiable principles (e.g., no high-intensity prescriptions for 10–12, no supplement mentions, no result-over-enjoyment framing).
4. **Given** insights produced before this feature, **When** the coach views them, **Then** they remain readable alongside new-format insights without errors.

---

### User Story 3 - Launch analysis right after importing results (Priority: P3)

Immediately after the coach commits a results import for a válida, the system offers to launch the AI analysis for that competition in the same flow, so "import results → produce insights" becomes one continuous action instead of two separate journeys.

**Why this priority**: It is a convenience accelerator for the most common real-world sequence (the coach imports results the evening after a race). Valuable, but the coach can achieve the same outcome through User Story 1.

**Independent Test**: Can be tested by completing a results import commit and verifying the confirmation step offers a launch option that, when accepted, starts the same group analysis as User Story 1; when declined, nothing runs.

**Acceptance Scenarios**:

1. **Given** the coach commits a results import, **When** the commit succeeds, **Then** the confirmation view offers an option to launch the AI analysis for that competition now.
2. **Given** the coach accepts the offer, **When** the analysis starts, **Then** the coach is taken to (or shown) the same run-progress experience as a launch from the Insights tab.
3. **Given** the coach declines the offer, **When** the flow ends, **Then** no analysis runs and the offer can still be fulfilled later from the Insights tab.

---

### User Story 4 - Launch or re-launch analysis for a single athlete inside the competition (Priority: P4)

From the competition's results list **and from each athlete card in the Insights tab**, the coach can launch (or re-launch after a correction) the AI analysis for one specific athlete without navigating to that athlete's profile.

**Why this priority**: Covers the correction loop (a result was fixed, one rider's analysis is stale) without forcing a full group re-run or a context switch to the athlete profile. Lower priority because the existing athlete-profile launcher and the stale-insight re-execute control already cover this with extra navigation.

**Independent Test**: Can be tested by choosing one athlete in the competition's results list (or their card in the Insights tab), launching their analysis from there, and verifying only that athlete's insight is produced/refreshed.

**Acceptance Scenarios**:

1. **Given** a competition with committed results, **When** the coach uses the per-athlete action on a rider's result row, **Then** an analysis run starts scoped to that athlete and that válida.
2. **Given** an athlete already has a fresh insight for this válida, **When** the coach triggers the per-athlete action, **Then** the system asks for confirmation before re-running, indicating an analysis already exists.
3. **Given** the coach is on the Insights tab, **When** they use the per-athlete "Analizar con IA" / "Re-analizar" button on an athlete card, **Then** an analysis run starts scoped to that athlete and that válida (same launch + confirm-on-fresh behavior as the results row action). Masked athlete cards (parent view) expose no launch button.

---

### User Story 5 - Ask the AI follow-up questions from the competitions module (Priority: P5)

The coach can open the existing conversational AI tool from within the competitions module to ask follow-up questions about the válida's results and the produced insights (e.g., "¿quién mejoró más respecto a Ginebra?"), without leaving the competition context.

**Why this priority**: The chat capability already exists in the backend; surfacing it in context is additive value. It is last because all other stories produce or refresh insights, while this one only consumes them.

**Independent Test**: Can be tested by opening the chat from a competition view, asking a question about that válida, and receiving an answer grounded in the competition's results and insights.

**Acceptance Scenarios**:

1. **Given** a competition with results and insights, **When** the coach opens the AI chat from the competitions module, **Then** the conversation starts pre-scoped to that competition's context.
2. **Given** the AI service is disabled or unavailable, **When** the coach opens the chat, **Then** a clear Spanish message explains the assistant is not available, and the rest of the module remains usable.

---

### Edge Cases

- **Budget exhausted**: When the monthly AI budget is spent, every launch action (group, post-import, per-athlete) is blocked before any run starts, with a Spanish message explaining the budget state; the read-only insights remain visible.
- **Concurrency limit reached**: If the maximum number of simultaneous runs is active, a new launch is rejected with a "try again shortly" message rather than queuing silently.
- **Partial group failure**: If the group analysis fails for some athletes but succeeds for others, the completed insights are kept, and the coach sees which athletes failed with the option to retry only those.
- **Results re-imported after analysis**: Insights produced before a re-import are marked as outdated (existing stale-marking behavior) and the coach can re-run from the competition without hunting through athlete profiles.
- **Duplicate launch**: If a run is already in progress for the competition, the launch action shows the in-progress state instead of starting a second run.
- **AI disabled in the environment**: All launch and chat entry points are hidden or disabled with an explanatory message; nothing errors.
- **First válida of the season**: Season comparatives must not fabricate history (covered in User Story 2, scenario 2).
- **Cold start / slow backend**: A launch issued while the backend is waking from idle must surface progress feedback rather than appearing frozen; the run's status is recoverable after a page refresh.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The competitions module MUST present a launch action in a competition's Insights tab that starts an AI analysis covering all club athletes with committed results in that competition, visible and usable only by coach and admin roles.
- **FR-002**: The launch action MUST be disabled, with an explanatory Spanish message, when the competition has no committed results.
- **FR-003**: Group, post-import, and per-athlete launches MUST reuse the existing human-in-the-loop approval flow; no insight may be persisted without passing the same review steps as the existing per-athlete analysis.
- **FR-004**: After a successful results-import commit, the system MUST offer the coach the option to launch the analysis for that competition immediately; declining MUST have no side effects.
- **FR-005**: The competition's results list MUST provide a per-athlete action to launch or re-launch the analysis scoped to that athlete and válida; re-launch over a fresh insight MUST require confirmation.
- **FR-006**: The competitions module MUST provide access to the existing conversational AI tool, pre-scoped to the competition being viewed.
- **FR-007**: Produced insights MUST include season context when available: comparison against the athlete's prior válidas of the same calendar year and an explicit progression assessment; when no prior válida exists, the insight MUST state so instead of comparing.
- **FR-008**: Insight narratives MUST remain consistent with the club's non-negotiable training principles; content that contradicts them is a defect.
- **FR-009**: All existing safeguards MUST continue to apply unchanged to every new entry point: AI feature flag, monthly budget guard, concurrent-run limit, coach/admin authorization, and athlete-identity anonymization before any prompt.
- **FR-010**: When a launch is blocked (budget exhausted, concurrency limit, AI disabled), the coach MUST see a specific Spanish explanation of why, and the rest of the competitions module MUST remain fully usable.
- **FR-011**: A group run MUST report per-athlete outcomes; failures for some athletes MUST NOT discard successful insights, and the coach MUST be able to retry only the failed athletes.
- **FR-012**: While a run is in progress for a competition, its launch actions MUST reflect the in-progress state and prevent duplicate concurrent runs for the same scope; run progress MUST survive a page refresh.
- **FR-013**: Insights produced before this feature MUST remain viewable alongside season-aware insights without migration of historical content.
- **FR-014**: Every persisted insight MUST record which run produced it and remain attributable in the existing AI usage metrics; the currently configured AI model remains unchanged by this feature.
- **FR-015**: All coach-facing copy introduced by this feature MUST be in español neutro (Colombia); no minor's personal data may appear in logs or in prompts (existing anonymization preserved).

### Key Entities

- **Competition (válida)**: An existing race event with committed results; the anchor context for launching analyses and viewing insights.
- **Analysis Run**: An execution of the AI race analysis with a scope (whole competition group, or a single athlete + competition), a lifecycle (launched → in review → completed/failed/partial), the coach approvals it received, and the model that served it.
- **Insight**: A coach-reviewed, per-athlete narrative produced by a run, now optionally carrying season context (references to prior válidas, progression assessment); can be marked outdated when underlying results change.
- **Season Context**: The athlete's set of results across the calendar year's válidas used to ground comparatives and progression; derived from existing results data, not newly captured.
- **AI Conversation**: A coach-only chat session scoped to a competition, grounded in its results and insights.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After importing a válida's results, the coach can produce reviewed AI insights for the whole group in a single flow, with zero visits to individual athlete profiles (today this requires one profile visit per athlete — about 15 navigations for a full squad).
- **SC-002**: 100% of insights for athletes with two or more válidas in the season include a season comparison and an explicit progression assessment; 0% of single-válida insights contain fabricated comparisons.
- **SC-003**: The coach can locate and trigger the analysis from a competition screen on the first attempt, without documentation or support (the original complaint "no veo opciones para usar IA" is no longer reproducible).
- **SC-004**: 100% of launches attempted while safeguards apply (budget exhausted, concurrency cap, AI disabled) are blocked before any model usage occurs and show a specific explanation.
- **SC-005**: A partial group failure never destroys completed work: in any failed batch, all successfully reviewed insights remain available and the retry affects only failed athletes.
- **SC-006**: Monthly AI spend stays within the existing configured budget; this feature introduces no path that bypasses the budget or concurrency guards.

## Assumptions

- The currently configured AI provider and model remain unchanged; this feature neither switches nor adds models (a possible future feature may introduce Claude Fable 5 support — explicitly out of scope here).
- The existing human-in-the-loop approval flow, budget guard, concurrency limit, stale-insight marking, and anonymization pipeline are reused as-is; this feature adds entry points and enriches insight content, not new control mechanisms.
- "Season" means the current Copa Valle calendar year; comparatives draw only on results already stored in the system.
- The group analysis covers club athletes with committed results in the competition; external (non-club) riders appearing in results are not analyzed.
- The coach primarily uses a desktop browser for this workflow; the entry points must not break the module on mobile but are not optimized for it in this feature.
- Minors never log in and never see AI output directly; all surfaces introduced here are coach/admin-only.
- PDF parsing/import behavior is unchanged; this feature begins after results are committed.
