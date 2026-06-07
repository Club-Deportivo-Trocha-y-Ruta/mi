# Implementation Plan: Subagent Fleet Model Tiers & Team Grouping

**Branch**: `claude/project-agents-setup-i8sTT` | **Date**: 2026-06-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-subagent-model-tiers/spec.md`

## Summary

Standardize the 28 Claude Code subagent definitions under `.claude/agents/` so that
model tier follows role and the fleet is organized into five visually-unified teams.
Orchestrator **leads** run on `opus`; all specialist **workers** run on `sonnet`; each
of the five teams (Engineering=blue, Sports/Head-Coach=green, Data-Platform=cyan,
Family-Communications=orange, Product=purple) shares one `color` so the lead and its
members read as a single unit. The change touches only the `model` and `color`
frontmatter fields — every agent's `name`, `description`, `tools`, `memory`, and body
instructions are preserved — and is backed by a written policy in `.claude/agents/README.md`.
The technical approach (Phase 0 research) is grounded in official Claude Code guidance:
lock an explicit model per agent for predictable cost, route execution to cheaper models,
and keep teams as a logical (`color`-based) grouping because the runtime "agent teams"
feature is experimental and has no project-level config.

## Technical Context

**Language/Version**: N/A (no application code). Artifacts are Markdown files with YAML frontmatter — Claude Code subagent definitions under `.claude/agents/`.

**Primary Dependencies**: Claude Code subagent loader (frontmatter contract: `name`, `description`, `tools`, `model`, `memory`, `color`). No new runtime or package dependency.

**Storage**: N/A — flat files in the repository. No database, no migration.

**Testing**: Static validation — YAML frontmatter parses; every agent declares an explicit `model`; tier matches role; color is uniform per team; `name`/`description`/`tools`/`memory`/body unchanged vs. pre-change. Verified by inspection script + `git diff` review (see quickstart.md).

**Target Platform**: Claude Code (CLI / web / desktop / IDE) reading project-scoped `.claude/agents/`.

**Project Type**: Repository configuration / developer-tooling governance (not a product feature).

**Performance Goals**: N/A for end users. Indirect: ~40% lower assistant operating cost vs. all-Opus for delegated execution (per Phase 0 research), with no meaningful quality loss.

**Constraints**: Touch only `model` + `color`; preserve all other valid frontmatter and bodies; introduce no unrecognized keys; do not weaken any minors' privacy/safety guardrail; all 28 definitions remain valid/loadable. Work stays on the pinned branch `claude/project-agents-setup-i8sTT` (no separate feature branch pushed).

**Scale/Scope**: 28 agent definition files; 5 leads + 23 workers; 5 teams. No product code, schema, or copy affected.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The constitution (v1.1.0) defines four principles plus Quality Gates. This feature is
configuration-only (no application code, tests, UI, schema, or product copy), so most
gates are satisfied trivially; the relevant ones are mapped explicitly.

- **I. Code Quality & Maintainability** — PASS. The change makes the fleet *more*
  consistent and readable: explicit model per agent, one color per team, and a written
  policy (`.claude/agents/README.md`) so future edits don't re-derive the rule. No
  duplication introduced. (Project linters/type-checkers don't apply to agent Markdown;
  validation is the inspection script in quickstart.md.)
- **II. Testing Standards (NON-NEGOTIABLE)** — PASS (adapted). No application code
  changes, so no `pytest`/`vitest`. The deliverable's correctness is verified by a
  deterministic static check (frontmatter validity + tier/color invariants + "body and
  other fields unchanged"), documented and runnable from quickstart.md. The privacy
  invariant ("guardrails preserved") is checked by diffing that only `model`/`color`
  lines changed.
- **III. User Experience Consistency** — PASS / N/A. No product end-user copy, UI, or
  forms change. **Language policy upheld**: this corpus (`.claude/agents/*`) is part of
  the English AI-instruction corpus per Principle III; editing tier/color does not alter
  any español product copy. Color semantics here are *team identity* for the agent
  roster, a separate namespace from the product's success/attention/error status colors,
  so no token-meaning collision occurs.
- **IV. Performance Requirements** — N/A. No API endpoints, queries, or frontend bundles.
- **Quality Gates — Privacy (Ley 1581, minors)** — PASS. No minor's data is touched,
  logged, or moved. Crucially, the model-tier change does **not** relax any privacy
  control: the mandatory `data-privacy-guard` audit, PII-free logging, RBAC, and
  `AI_LOG_PROMPTS=false` are guardrails independent of model tier (Phase 0 R5).
- **Quality Gates — Stack discipline / Security / AI guardrails** — N/A or PASS. No new
  dependency, no auth/upload change. AI guardrails for minors remain enforced by agent
  instructions and the constitution, unchanged.

**Result**: PASS. One deliberate trade-off is logged in Complexity Tracking (chose the
clean 2-tier policy over a per-agent risk-based tiering).

## Project Structure

### Documentation (this feature)

```text
specs/005-subagent-model-tiers/
├── plan.md              # This file
├── research.md          # Phase 0 output — web-sourced policy decisions
├── data-model.md        # Phase 1 output — config entities (agent, team, policy)
├── quickstart.md        # Phase 1 output — how to validate / add an agent
├── contracts/
│   └── agent-definition.frontmatter.md  # frontmatter contract + full fleet mapping
└── checklists/
    └── requirements.md  # spec quality checklist (from /speckit-specify)
```

### Source Code (repository root)

This feature changes repository **configuration**, not source code. The affected and
authored paths are:

```text
.claude/agents/
├── README.md                     # NEW — model-tiering & team policy (authored)
├── <5 lead definitions>.md       # model: opus  + team color   (frontmatter edited)
└── <23 worker definitions>.md    # model: sonnet + team color   (frontmatter edited)
```

No `backend/` or `frontend/` source is touched. No Alembic migration. No product copy.

**Structure Decision**: Configuration-only change scoped to `.claude/agents/`. The five
teams are expressed *logically* (a lead plus its workers, unified by a shared `color`
and a consistent worker model tier) and documented in `.claude/agents/README.md` — not
as a runtime `teams.json`, which Claude Code's experimental agent-teams feature does not
read at project scope (Phase 0 R4).

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified.

No constitution violations. One **design trade-off** recorded for transparency:

| Decision | Why chosen | Simpler/other alternative rejected because |
|---|---|---|
| Uniform 2-tier policy (all workers → `sonnet`), including safety/privacy-critical workers like `data-privacy-guard` | Cleanest, auditable, cost-efficient; matches documented best practice; safety is enforced by guardrails + RBAC + Opus-lead review, not by tier | *Risk-based hybrid* (privacy/health teams on Opus) was rejected: it mixes tiers within the fleet, complicates the "team at the same level" invariant and audits, for a safety benefit already covered by non-model controls. Owner explicitly chose the 2-tier policy. |
