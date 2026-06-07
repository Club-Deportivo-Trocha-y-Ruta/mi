# Phase 0 Research: Subagent Fleet Model Tiers & Team Grouping

**Feature**: 005-subagent-model-tiers
**Date**: 2026-06-07
**Method**: Official Claude Code documentation (code.claude.com/docs) + current (2026) practitioner sources, fetched on the web.

This feature has no traditional "unknown technologies" to resolve. The research instead
confirms the **policy decisions** behind the tiering and grouping, so the plan rests on
documented best practice rather than preference.

---

## R1 — Model tier per agent role (leads vs workers)

- **Decision**: Orchestrator/lead agents → `opus`; specialist worker agents → `sonnet`. Tier is chosen by *primary role*, not by topic.
- **Rationale**:
  - Official subagents guidance lists "**Control costs by routing tasks to faster, cheaper models**" as a first-class reason to define subagents, and frames Sonnet as the model for "focused execution" — exactly what worker subagents do.
  - The orchestrator-subagent pattern (expensive frontier model reasons/reviews and delegates; cheaper models execute) is the documented norm. Current (2026) cost analysis: a team of **one Opus orchestrator + four Sonnet workers costs ≈40% less than five Opus agents**, "without meaningful quality loss."
  - There is an open Claude Code issue arguing subagents should **default to Sonnet rather than inherit Opus**, reinforcing that Opus-everywhere is wasteful for execution work.
- **Alternatives considered**:
  - *All-Opus*: highest quality ceiling, but documented as overkill for bounded execution and ~40%+ more expensive. Rejected.
  - *Risk-based hybrid* (safety/privacy teams on Opus, build/comms/product on Sonnet): defensible, but mixes tiers within the fleet and makes the policy harder to audit; the project owner chose the cleaner 2-tier model. Recorded as the rejected alternative in Complexity Tracking.
  - *Haiku for trivial workers*: viable per docs ("high-volume, straightforward tasks — classification, simple formatting"), but every agent here operates in a minors'-privacy/safety context where stronger reasoning is justified; no agent is purely mechanical. Rejected for now; left as a future option in the policy doc.

## R2 — Explicit model vs `inherit`

- **Decision**: Every agent declares an explicit `model`; none rely on `inherit`/default.
- **Rationale**: `inherit` makes an agent's effective tier depend on whatever model the parent session happens to run, which defeats cost-predictability and makes audits non-deterministic. Pinning the model gives "consistent, cost-predictable invocations" (the documented reason to lock a subagent's model in YAML).
- **Alternatives considered**: `inherit` for workers (so they ride the session model) — rejected: non-deterministic cost and tier.

## R3 — Valid frontmatter fields (what we may touch)

- **Decision**: Use only recognized fields. We set/normalize `model` and `color`; we preserve `name`, `description`, `tools`, `memory`, and the body verbatim.
- **Rationale**: The subagents doc enumerates supported frontmatter — `name`, `description`, `tools`, `model`, `memory` (`user`/`project`/`local`), `color`, plus advanced keys (`disallowedTools`, `permissionMode`, `maxTurns`, `skills`, `mcpServers`, `hooks`, etc.). `memory: user` is **valid** (shared `~/.claude/agent-memory/<name>/`), so it stays. `color` is a valid display field, which makes it the right vehicle for visual team grouping with **zero behavioral risk**.
- **Alternatives considered**: Encoding team in `name` prefixes or `description` tags — rejected: mutating `name` breaks references and delegation; `color` is purpose-built and behavior-neutral.

## R4 — How "teams" should be expressed

- **Decision**: Express teams *logically* — one lead + its workers, unified by a shared `color` and consistent worker tier — documented in `.claude/agents/README.md`. Do **not** depend on the experimental "agent teams" runtime.
- **Rationale**: Claude Code's official **agent teams** feature is **experimental, disabled by default** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`), has a runtime-managed config under `~/.claude/teams/` that must **not** be hand-authored, and explicitly states there is **no project-level team config** (`.claude/teams/teams.json` is treated as an ordinary file). So teams cannot be statically declared in-repo. However, the same doc says a teammate spawned from a subagent definition **"honors that definition's `tools` allowlist and `model`"** — meaning our per-agent tiering and tool scoping *carry over* if the coach ever enables agent teams. Our logical grouping is therefore both the only repo-durable option **and** forward-compatible with the runtime feature.
- **Alternatives considered**: Committing a `teams.json` — rejected: not recognized as config, overwritten/ignored, and runtime-only.

## R5 — Safety posture under a cheaper worker tier

- **Decision**: Moving workers to Sonnet does not weaken minors' privacy/safety, because safety is enforced by **written guardrails + RBAC + the constitution**, with `data-privacy-guard` review under an Opus lead — not by model tier.
- **Rationale**: The constitution (Quality Gates) mandates the `data-privacy-guard` audit for any athlete-identifiable change, forbids PII in logs/commits/AI prompts, and requires `AI_LOG_PROMPTS=false` in prod. None of these controls is a function of which model a worker runs. Sonnet 4.6 is highly capable for the bounded advisory/coding tasks these workers perform.
- **Alternatives considered**: Keeping safety-advisory agents on Opus "to be safe" — considered but not required; the control is the guardrail, not the tier. Captured as the risk-based alternative in R1.

---

## Consolidated decisions

| # | Decision | Source basis |
|---|---|---|
| R1 | Leads → opus, workers → sonnet | Subagents doc (cost routing); 2026 cost analysis (~40% cheaper); model-config guidance |
| R2 | Explicit model on every agent | Subagents doc (lock model for predictable cost) |
| R3 | Touch only `model`/`color`; keep `name`/`description`/`tools`/`memory`/body | Subagents frontmatter reference (`memory`, `color` valid) |
| R4 | Logical teams via `color` + README; no `teams.json` | Agent-teams doc (experimental, runtime-only, no project config; model/tools honored) |
| R5 | Safety unchanged by tier | Project constitution Quality Gates |

## Sources

- [Create custom subagents — Claude Code Docs](https://code.claude.com/docs/en/sub-agents)
- [Orchestrate teams of Claude Code sessions (agent teams) — Claude Code Docs](https://code.claude.com/docs/en/agent-teams)
- [Model configuration — Claude Code Docs](https://code.claude.com/docs/en/model-config)
- [Claude Code Agents in 2026: Agent View, Subagents, Teams, and What Parallel Sessions Cost — CloudZero](https://www.cloudzero.com/blog/claude-code-agents/)
- [Subagents should default to Sonnet, not inherit Opus — anthropics/claude-code Issue #26179](https://github.com/anthropics/claude-code/issues/26179)
- [Using Opus as an adviser with Sonnet/Haiku — MindStudio](https://www.mindstudio.ai/blog/claude-code-advisor-strategy-opus-sonnet-haiku)
