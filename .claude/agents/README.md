# Subagent Fleet — Model Tiers & Teams

This directory holds the project's Claude Code subagents. They follow one policy so
behavior, cost, and discoverability stay predictable. When you add or edit an agent,
keep it consistent with the rules below.

## Model tiering policy

Each agent declares an **explicit** `model` (never relies on the inherited default).
The tier follows the agent's **primary role**:

| Role | Model | Why |
|---|---|---|
| **Lead / orchestrator** — decomposes requests and delegates to other agents | `opus` | Strong multi-step reasoning for planning and delegation. |
| **Specialist worker** — executes a bounded task (coding, content, review/audit, analytics, advisory) | `sonnet` | Capable and cost/latency-efficient for well-defined execution. |

This matches Claude Code's documented guidance (orchestrators → Opus, specialists →
Sonnet). It is intentionally expressed in role terms so it survives model renames.

> Safety/privacy-critical workers (e.g. `data-privacy-guard`) stay on `sonnet` by
> design: their guardrails live in their **instructions**, and they run under an
> Opus-tier lead's review. Model tier is not the safety control — the written
> guardrails and the minors'-privacy rules in `CLAUDE.md` / the constitution are.

## Teams (one color per team)

Every agent belongs to exactly one team and carries that team's `color`. The lead and
its workers share the color, so a team reads as one unit ("teams at the same level").

| Team | Color | Lead (`opus`) | Workers (`sonnet`) |
|---|---|---|---|
| **Engineering** | `blue` | `engineering-lead` | `fastapi-architect`, `react-ui-engineer`, `devops-engineer`, `qa-engineer`, `database-architect`, `integration-engineer` |
| **Sports / Head-Coach** | `green` | `head-coach-lead` | `training-planner`, `nutrition-advisor`, `injury-prevention-advisor`, `technique-coach`, `mental-performance-coach`, `competition-strategist`, `sports-science-advisor` |
| **Data-Platform** | `cyan` | `data-platform-lead` | `data-analyst`, `data-privacy-guard`, `analytics-reporter` |
| **Family / Communications** | `orange` | `family-relations-lead` | `parent-communicator`, `event-coordinator`, `community-content-creator` |
| **Product** | `purple` | `product-manager` | `ux-researcher`, `release-manager`, `technical-writer` |

## Adding a new agent

1. Decide the role: does it mainly **delegate** (lead → `opus`) or **execute**
   (worker → `sonnet`)? Set `model` accordingly.
2. Assign it to the closest of the five teams and use that team's `color`. If it fits
   no team, extend the taxonomy explicitly here — never leave it uncolored or untiered.
3. Use only recognized frontmatter fields (`name`, `description`, `tools`, `model`,
   `color`, `memory`, …). Keep the existing valid fields and body instructions intact.

See `specs/005-subagent-model-tiers/spec.md` for the full specification behind this policy.
