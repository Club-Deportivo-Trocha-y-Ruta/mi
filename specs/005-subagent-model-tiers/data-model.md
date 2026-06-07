# Phase 1 Data Model: Subagent Fleet Model Tiers & Team Grouping

**Feature**: 005-subagent-model-tiers · **Date**: 2026-06-07

This feature has **no database entities**. The "data model" here is the configuration
schema of the agent fleet: the structure of an agent definition, the team taxonomy, and
the invariants that bind them. These are stored as flat files under `.claude/agents/`.

## Entity: Agent Definition

One Markdown file `.claude/agents/<name>.md` = one agent. Frontmatter fields used by this
feature (all recognized Claude Code subagent fields):

| Field | Type | Required | Set by this feature? | Rule |
|---|---|---|---|---|
| `name` | slug (lowercase + hyphens) | Yes | No (preserved) | Unique across fleet; unchanged. |
| `description` | string | Yes | No (preserved) | Unchanged. |
| `tools` | comma list | No | No (preserved) | Present only on leads (restricted set); unchanged. |
| `model` | `opus` \| `sonnet` | Yes (this feature makes it explicit) | **Yes** | `opus` iff role = lead; `sonnet` iff role = worker. |
| `color` | enum (blue/green/cyan/orange/purple/…) | Yes (this feature) | **Yes** | Equals the agent's team color. |
| `memory` | `user` \| `project` \| `local` | No | No (preserved) | Currently `user` on all; unchanged. |
| *body* | Markdown | Yes | No (preserved) | System-prompt instructions; unchanged. |

**Derived attribute** — `role ∈ {lead, worker}`: an agent is a **lead** iff its primary
function is to decompose requests and delegate to other agents (the five `*-lead` /
`product-manager` agents). Otherwise it is a **worker**. `role` is not a stored field; it
is determined by the agent's purpose and recorded in the policy table.

## Entity: Team

A logical grouping; not a stored file. Attributes:

| Attribute | Type | Rule |
|---|---|---|
| `team_name` | enum | One of: Engineering, Sports/Head-Coach, Data-Platform, Family-Communications, Product. |
| `color` | enum | Exactly one per team; the five colors are distinct. |
| `lead` | agent name | Exactly one lead per team (model = opus). |
| `workers` | agent names | ≥1 workers (model = sonnet); all share the team `color`. |

### Team membership (the canonical mapping)

| Team | color | Lead (opus) | Workers (sonnet) |
|---|---|---|---|
| Engineering | blue | engineering-lead | fastapi-architect, react-ui-engineer, devops-engineer, qa-engineer, database-architect, integration-engineer |
| Sports/Head-Coach | green | head-coach-lead | training-planner, nutrition-advisor, injury-prevention-advisor, technique-coach, mental-performance-coach, competition-strategist, sports-science-advisor |
| Data-Platform | cyan | data-platform-lead | data-analyst, results-analyst, data-privacy-guard, analytics-reporter |
| Family-Communications | orange | family-relations-lead | parent-communicator, event-coordinator, community-content-creator |
| Product | purple | product-manager | ux-researcher, release-manager, technical-writer |

Totals: 5 teams · 5 leads · 23 workers · 28 agents.

## Entity: Tiering Policy

The ruleset (documented in `.claude/agents/README.md`) mapping role→model and
function→team/color, plus the rule for classifying a new agent. Not a data record; it is
the governing document that makes the invariants below auditable.

## Invariants (validation targets)

- **INV-1**: Every agent declares an explicit `model` ∈ {`opus`,`sonnet`} (none inherit). → SC-001
- **INV-2**: `model == opus` iff `role == lead`; `model == sonnet` iff `role == worker`. → SC-002
- **INV-3**: Every agent declares exactly one `color`; all members of a team (incl. lead) share it. → SC-003
- **INV-4**: The five teams use five distinct colors. → SC-004
- **INV-5**: For every agent, `name`/`description`/`tools`/`memory`/body are byte-identical to the pre-change file (only `model`/`color` lines differ). → SC-005
- **INV-6**: Only recognized frontmatter keys appear (no invented keys). → FR-009
- **INV-7**: Every file's frontmatter parses as valid YAML and the agent loads. → SC-005/FR-012

## State / transitions

Agent definitions are effectively static config; there is no runtime state machine. The
only "transition" is an edit lifecycle: an agent is *added* (must be placed per policy) or
*re-tiered/re-colored* (must keep INV-1…INV-7). No data persists between sessions beyond
the optional `memory` directory, which this feature does not alter.
