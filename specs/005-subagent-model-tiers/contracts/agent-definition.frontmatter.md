# Contract: Agent Definition Frontmatter

**Feature**: 005-subagent-model-tiers · **Date**: 2026-06-07

The "interface" this feature exposes is the **frontmatter contract** that every
`.claude/agents/<name>.md` file must satisfy, plus the **fleet mapping** that pins each
agent's tier and team color. Claude Code's subagent loader is the consumer; a maintainer
(human or AI) is the producer.

## 1. Frontmatter schema (the contract)

```yaml
---
name: <slug>                 # required; lowercase + hyphens; unique; PRESERVED
description: "<string>"      # required; PRESERVED
model: opus | sonnet         # required (explicit); opus=lead, sonnet=worker  ← managed
color: blue|green|cyan|orange|purple  # required; = team color                ← managed
memory: user                 # optional; PRESERVED if present
tools: <comma list>          # optional; present on leads only; PRESERVED
# (body follows the closing --- : system-prompt instructions; PRESERVED)
---
```

Rules:
- `model` and `color` are the **only** fields this feature writes. All other fields and
  the body are preserved verbatim.
- No unrecognized keys may be introduced. Recognized keys (per Claude Code docs) include
  `name`, `description`, `tools`, `disallowedTools`, `model`, `color`, `memory`,
  `permissionMode`, `maxTurns`, `skills`, `mcpServers`, `hooks`, `background`, `effort`,
  `isolation`, `initialPrompt`. This feature uses only the first set above.
- `model` MUST be an explicit alias (`opus`/`sonnet`), never `inherit`/absent.

## 2. Tier rule

| role | predicate | model |
|---|---|---|
| lead | primary job = decompose & delegate to other agents | `opus` |
| worker | primary job = execute a bounded task (code, content, review, analytics, advisory) | `sonnet` |

## 3. Fleet mapping (authoritative)

> If an agent file disagrees with this table, the file is wrong. Keep this table and
> `.claude/agents/README.md` in sync.

| agent | role | model | team | color |
|---|---|---|---|---|
| engineering-lead | lead | opus | Engineering | blue |
| fastapi-architect | worker | sonnet | Engineering | blue |
| react-ui-engineer | worker | sonnet | Engineering | blue |
| devops-engineer | worker | sonnet | Engineering | blue |
| qa-engineer | worker | sonnet | Engineering | blue |
| database-architect | worker | sonnet | Engineering | blue |
| integration-engineer | worker | sonnet | Engineering | blue |
| head-coach-lead | lead | opus | Sports/Head-Coach | green |
| training-planner | worker | sonnet | Sports/Head-Coach | green |
| nutrition-advisor | worker | sonnet | Sports/Head-Coach | green |
| injury-prevention-advisor | worker | sonnet | Sports/Head-Coach | green |
| technique-coach | worker | sonnet | Sports/Head-Coach | green |
| mental-performance-coach | worker | sonnet | Sports/Head-Coach | green |
| competition-strategist | worker | sonnet | Sports/Head-Coach | green |
| sports-science-advisor | worker | sonnet | Sports/Head-Coach | green |
| data-platform-lead | lead | opus | Data-Platform | cyan |
| data-analyst | worker | sonnet | Data-Platform | cyan |
| results-analyst | worker | sonnet | Data-Platform | cyan |
| data-privacy-guard | worker | sonnet | Data-Platform | cyan |
| analytics-reporter | worker | sonnet | Data-Platform | cyan |
| family-relations-lead | lead | opus | Family-Communications | orange |
| parent-communicator | worker | sonnet | Family-Communications | orange |
| event-coordinator | worker | sonnet | Family-Communications | orange |
| community-content-creator | worker | sonnet | Family-Communications | orange |
| product-manager | lead | opus | Product | purple |
| ux-researcher | worker | sonnet | Product | purple |
| release-manager | worker | sonnet | Product | purple |
| technical-writer | worker | sonnet | Product | purple |

## 4. Contract tests (must all hold)

1. Each of the 28 files parses as valid YAML frontmatter and loads as an agent.
2. Each file's `model` equals the mapping above (5×opus, 23×sonnet).
3. Each file's `color` equals its team color; per team all colors identical; 5 distinct colors.
4. `name`, `description`, `tools`, `memory`, and body are unchanged vs. the pre-change
   revision (only `model`/`color` lines differ in `git diff`).
5. No file contains an unrecognized frontmatter key.
