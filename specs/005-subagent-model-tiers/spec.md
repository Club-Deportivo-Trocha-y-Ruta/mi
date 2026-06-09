# Feature Specification: Subagent Fleet Model Tiers & Team Grouping

**Feature Branch**: `005-subagent-model-tiers`

**Created**: 2026-06-07

**Status**: Draft

**Input**: User description: "Standardize the project's Claude Code subagent fleet (.claude/agents) into consistent model tiers and visually-grouped teams. Orchestrator lead agents run on Opus; all specialist worker agents run on Sonnet. The fleet is organized into five teams, each sharing one color: Engineering (blue), Sports/Head-Coach (green), Data-Platform (cyan), Family-Communications (orange), and Product (purple). Every team must be internally consistent in model tier and color. Preserve existing valid frontmatter (name, description, tools, memory) and the agents' body instructions. Goal: a documented, best-practice model-tiering and team-grouping policy so the coach gets capable orchestration where it matters and cost-efficient execution everywhere else, without weakening minors' privacy/safety guardrails."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Predictable, cost-right model per agent (Priority: P1)

As the project owner (coach/maintainer), when I or any orchestrator delegates work to one of the project's specialized assistants, I want each assistant to run on the model tier that matches its role — the most capable model for the assistants that plan and delegate, and a fast, cost-efficient model for the assistants that execute well-defined work — so that planning quality stays high while routine execution stays cheap and fast.

**Why this priority**: Model selection is the single biggest lever on both response quality and operating cost for the assistant fleet. Getting it right is the core value of this feature; everything else is consistency and discoverability around it.

**Independent Test**: Inspect every agent definition under `.claude/agents/` and confirm that each orchestrator/lead assistant is assigned the high-capability tier and each specialist worker is assigned the cost-efficient tier, with no exceptions and no missing assignments.

**Acceptance Scenarios**:

1. **Given** the fleet of assistant definitions, **When** I list each assistant's assigned model tier, **Then** every lead/orchestrator assistant is on the high-capability tier and every specialist worker is on the cost-efficient tier.
2. **Given** an assistant whose role is to decompose and delegate (a "lead"), **When** its definition is read, **Then** its model tier is the high-capability tier.
3. **Given** an assistant whose role is to execute a bounded task (coding, content drafting, review, analytics), **When** its definition is read, **Then** its model tier is the cost-efficient tier.

---

### User Story 2 - Visually consistent teams (Priority: P2)

As the maintainer browsing the assistant roster, I want each assistant to carry a team color so that members of the same team are immediately recognizable as a group and the lead and its members are visually unified ("teams at the same level").

**Why this priority**: Grouping is a discoverability and maintenance aid that makes future audits and additions obvious. It depends on the team taxonomy established in P1 but does not change behavior, so it ranks below the model policy.

**Independent Test**: Inspect every agent definition and confirm each carries exactly one team color, that all members of a given team share the same color, and that the five teams use five distinct colors.

**Acceptance Scenarios**:

1. **Given** the five teams (Engineering, Sports/Head-Coach, Data-Platform, Family-Communications, Product), **When** I read each assistant's color, **Then** all members of a team — including its lead — share one color, and the five teams use five distinct colors.
2. **Given** any single assistant definition, **When** it is read, **Then** it declares exactly one team color (never zero, never conflicting).

---

### User Story 3 - Documented, auditable policy (Priority: P3)

As a future maintainer (human or AI) adding or revising an assistant, I want the model-tiering and team-grouping rules written down so that new assistants are placed in the correct tier and team without re-deriving the policy, and so that any drift is easy to detect.

**Why this priority**: Documentation prevents regression and onboarding cost but is not required for the immediate behavioral benefit; it protects the investment made in P1 and P2.

**Independent Test**: Locate the written policy and confirm it states the tiering rule, the five-team taxonomy with each team's color, and the rule for placing a new assistant — sufficiently that a reviewer can audit any assistant against it.

**Acceptance Scenarios**:

1. **Given** the written policy, **When** a new assistant is proposed, **Then** the policy unambiguously determines its model tier and team color.
2. **Given** an assistant definition and the policy, **When** a reviewer compares them, **Then** any mismatch (wrong tier or color) is detectable from the policy alone.

---

### Edge Cases

- **An assistant fits no existing team**: the policy must direct the maintainer to either assign it to the closest existing team or extend the taxonomy explicitly, never leave it uncolored or untiered.
- **An assistant is both a coordinator and a doer**: classify by primary function — if it decomposes and delegates as its main job, it is a lead (high-capability tier); otherwise it is a worker (cost-efficient tier).
- **A safety/privacy-critical worker** (e.g., the minors'-data privacy auditor): it stays in the worker tier under this policy, but the policy must record that this trade-off was deliberate and that the assistant's written guardrails — not the model tier — are the primary safety control.
- **Existing valid configuration must survive**: changing tier/color must not delete or alter an assistant's name, description, tool restrictions, memory setting, or body instructions.
- **Invalid configuration keys**: only recognized assistant-definition fields may be used; an unrecognized field must not be introduced by this change.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every assistant definition in the fleet MUST declare an explicit model tier; none may rely on an implicit or inherited default.
- **FR-002**: Every assistant whose primary role is orchestration (decomposing requests and delegating to other assistants — the "leads") MUST be assigned the high-capability model tier.
- **FR-003**: Every assistant whose primary role is bounded execution (coding, content drafting, review/audit, analytics, advisory-within-guardrails) MUST be assigned the cost-efficient model tier.
- **FR-004**: Every assistant MUST be assigned to exactly one of the five teams: Engineering, Sports/Head-Coach, Data-Platform, Family-Communications, or Product.
- **FR-005**: Every assistant MUST declare exactly one team color, and all members of the same team (including the team's lead) MUST share the same color.
- **FR-006**: The five teams MUST use five distinct colors: Engineering = blue, Sports/Head-Coach = green, Data-Platform = cyan, Family-Communications = orange, Product = purple.
- **FR-007**: Within any single team, all worker members MUST share the same model tier, so that no team is internally inconsistent in tiering.
- **FR-008**: The change MUST preserve each assistant's existing valid configuration (name, description, tool restrictions, memory setting) and its body instructions unchanged, except for the model-tier and team-color fields.
- **FR-009**: Only recognized assistant-definition fields MUST be used; the change MUST NOT introduce unrecognized configuration keys.
- **FR-010**: The model-tiering and team-grouping policy MUST be documented in a durable, discoverable location, including the placement rule for any newly added assistant.
- **FR-011**: The change MUST NOT weaken any minors' privacy or safety guardrail; safety and privacy controls remain enforced by each assistant's written instructions regardless of model tier.
- **FR-012**: Every assistant definition MUST remain valid and loadable after the change (no malformed configuration).

### Key Entities *(include if feature involves data)*

- **Assistant definition**: One specialized assistant in the fleet. Key attributes: role (lead vs. worker), model tier, team membership, team color, tool restrictions, memory setting, and body instructions. Stored as individual definition files under the project's assistant directory.
- **Team**: A named grouping of one lead assistant and its worker members. Key attributes: team name, single shared color, and the model tier its workers use. Five teams exist: Engineering, Sports/Head-Coach, Data-Platform, Family-Communications, Product.
- **Tiering policy**: The written ruleset mapping an assistant's role to its model tier and its function to its team and color, plus the rule for classifying new assistants.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of assistant definitions declare an explicit model tier (zero rely on an inherited default).
- **SC-002**: 100% of lead/orchestrator assistants are on the high-capability tier and 100% of specialist workers are on the cost-efficient tier (zero exceptions).
- **SC-003**: 100% of assistant definitions declare exactly one team color, and each of the five teams is internally uniform in both color and worker model tier (zero internally mixed teams).
- **SC-004**: The five teams use five distinct colors with no collisions.
- **SC-005**: 100% of assistant definitions remain valid/loadable after the change, and 0 assistants lose their prior name, description, tool restrictions, memory setting, or body instructions.
- **SC-006**: A maintainer can determine the correct tier and color for any new assistant using only the written policy, in under 2 minutes, without reading other assistants' files.
- **SC-007**: 0 minors'-privacy or safety guardrails are removed or weakened relative to the pre-change fleet.

## Assumptions

- The role split is binary for tiering purposes: an assistant is either a "lead" (orchestrates/delegates) or a "worker" (executes). The five current leads are the orchestration assistants named in the existing roster; all other assistants are workers.
- "High-capability tier" and "cost-efficient tier" map to the platform's most-capable and balanced general model tiers respectively; the policy is expressed in role terms so it survives future model renames.
- Safety/privacy-critical workers (notably the minors'-data privacy auditor) are acceptable on the cost-efficient tier because their guardrails are encoded in their written instructions and they operate under an Opus-tier lead's review; this trade-off was chosen deliberately over a per-agent risk-based tiering.
- The team taxonomy is fixed at five teams for this feature; adding a sixth team is out of scope and would be a follow-up.
- This feature concerns only the AI development-assistant fleet configuration; it changes no product end-user copy, no application code, and no database schema, and therefore introduces no runtime or migration impact.
- The existing `memory` setting on each assistant is a recognized, valid field and is retained as-is.
