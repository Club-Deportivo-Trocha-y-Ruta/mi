---
description: "Task list for Subagent Fleet Model Tiers & Team Grouping"
---

# Tasks: Subagent Fleet Model Tiers & Team Grouping

**Input**: Design documents from `specs/005-subagent-model-tiers/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: This feature has no application code, so there are no `pytest`/`vitest`
suites. Its correctness is enforced by **static invariant checks** (INV-1…INV-7 in
data-model.md, the contract tests in `contracts/`, and the runnable validator in
`quickstart.md`). Those verification steps are included as explicit tasks.

**Organization**: Tasks are grouped by the three user stories so each can be delivered
and validated independently.

**Status (2026-06-07): ✅ COMPLETE** — all 24 tasks done. US1/US2 edits were applied in a
single mechanical pass; US3 docs authored; INV-1…INV-7 verified green (5 opus leads, 23
sonnet workers, 5 distinct team colors; only `model`/`color` lines changed vs. baseline).

**Scope note**: Work is confined to `.claude/agents/` and the feature's `specs/` docs,
on the pinned branch `claude/project-agents-setup-i8sTT`. No `backend/`/`frontend/` code,
no schema/migration, no product copy.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 / US2 / US3 (maps to spec.md user stories)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the canonical reference and a baseline for change-scope validation.

- [X] T001 Establish the authoritative fleet mapping (role→model, team→color for all 28 agents) in `specs/005-subagent-model-tiers/contracts/agent-definition.frontmatter.md`
- [X] T002 Record the pre-change git revision of `.claude/agents/*.md` to diff against later (used by INV-5 in `specs/005-subagent-model-tiers/quickstart.md`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Lock the policy decisions that every per-agent edit depends on.

**⚠️ CRITICAL**: The tier/color rules must be fixed before editing any agent file.

- [X] T003 Confirm recognized frontmatter fields and that `memory`/`color` are valid (so edits touch only `model`/`color` and preserve `memory`), per `specs/005-subagent-model-tiers/research.md` (R3)
- [X] T004 Confirm the tier rule (lead→opus, worker→sonnet) and the five team colors in `specs/005-subagent-model-tiers/data-model.md`

**Checkpoint**: Policy fixed — per-agent edits can begin.

---

## Phase 3: User Story 1 - Predictable, cost-right model per agent (Priority: P1) 🎯 MVP

**Goal**: Every agent declares an explicit `model`; leads on `opus`, workers on `sonnet`.

**Independent Test**: Inspect all 28 files — exactly 5 `opus` (leads) and 23 `sonnet`
(workers), none relying on an inherited default (INV-1, INV-2 / SC-001, SC-002).

### Implementation for User Story 1

- [X] T005 [P] [US1] Set `model: opus` on the 5 lead files: `.claude/agents/{engineering-lead,head-coach-lead,data-platform-lead,family-relations-lead,product-manager}.md`
- [X] T006 [P] [US1] Set `model: sonnet` on Engineering workers: `.claude/agents/{fastapi-architect,react-ui-engineer,devops-engineer,qa-engineer,database-architect,integration-engineer}.md`
- [X] T007 [P] [US1] Set `model: sonnet` on Sports/Head-Coach workers: `.claude/agents/{training-planner,nutrition-advisor,injury-prevention-advisor,technique-coach,mental-performance-coach,competition-strategist,sports-science-advisor}.md`
- [X] T008 [P] [US1] Set `model: sonnet` on Data-Platform workers: `.claude/agents/{data-analyst,results-analyst,data-privacy-guard,analytics-reporter}.md`
- [X] T009 [P] [US1] Set `model: sonnet` on Family-Communications workers: `.claude/agents/{parent-communicator,event-coordinator,community-content-creator}.md`
- [X] T010 [P] [US1] Set `model: sonnet` on Product workers: `.claude/agents/{ux-researcher,release-manager,technical-writer}.md`
- [X] T011 [US1] Verify INV-1 + INV-2: every agent has an explicit `model`; 5 opus leads + 23 sonnet workers (run the model checks in `specs/005-subagent-model-tiers/quickstart.md`)

**Checkpoint**: MVP — the fleet is correctly tiered and cost-right, independent of color/docs.

---

## Phase 4: User Story 2 - Visually consistent teams (Priority: P2)

**Goal**: Every agent carries exactly one team `color`; lead + members of a team share it; five teams use five distinct colors.

**Independent Test**: Inspect all 28 files — each has one `color`; per team the color is
uniform; the five team colors are distinct (INV-3, INV-4 / SC-003, SC-004).

### Implementation for User Story 2

- [X] T012 [P] [US2] Set `color: blue` on all 7 Engineering files (`engineering-lead` + 6 workers) in `.claude/agents/`
- [X] T013 [P] [US2] Set `color: green` on all 8 Sports/Head-Coach files (`head-coach-lead` + 7 workers) in `.claude/agents/`
- [X] T014 [P] [US2] Set `color: cyan` on all 5 Data-Platform files (`data-platform-lead` + 4 workers) in `.claude/agents/`
- [X] T015 [P] [US2] Set `color: orange` on all 4 Family-Communications files (`family-relations-lead` + 3 workers) in `.claude/agents/`
- [X] T016 [P] [US2] Set `color: purple` on all 4 Product files (`product-manager` + 3 workers) in `.claude/agents/`
- [X] T017 [US2] Verify INV-3 + INV-4: one color per agent, uniform per team, five distinct team colors (run the color checks in `specs/005-subagent-model-tiers/quickstart.md`)

**Checkpoint**: Teams are visually unified ("teams at the same level"), tiers still green.

---

## Phase 5: User Story 3 - Documented, auditable policy (Priority: P3)

**Goal**: The tiering + team policy is written down so new agents are placed correctly and drift is detectable.

**Independent Test**: A maintainer can determine the correct tier and color for any new
agent from the policy alone, without reading other agents' files (SC-006).

### Implementation for User Story 3

- [X] T018 [US3] Author the policy doc `.claude/agents/README.md` (tier rule, five-team color table, add-a-new-agent rule)
- [X] T019 [P] [US3] Ensure the feature spec set is complete and consistent in `specs/005-subagent-model-tiers/` (spec.md, research.md, plan.md, data-model.md, contracts/, quickstart.md)
- [X] T020 [US3] Point the Spec Kit marker in `CLAUDE.md` (between `<!-- SPECKIT START -->` / `<!-- SPECKIT END -->`) at `specs/005-subagent-model-tiers/plan.md`

**Checkpoint**: Policy is discoverable and authoritative; the fleet is auditable against it.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final verification of the safety/scope invariants and delivery.

- [X] T021 Verify INV-5: `git diff` of `.claude/agents/*.md` vs. the T002 baseline shows **only** `model`/`color` lines changed — names, descriptions, tools, memory, and bodies untouched (guardrails preserved, SC-005/SC-007)
- [X] T022 Verify INV-6 + INV-7: no unrecognized frontmatter keys; every file parses as valid YAML and loads
- [X] T023 Run the full validator in `specs/005-subagent-model-tiers/quickstart.md` — expect `PASS: all invariants hold`
- [X] T024 Commit and push to `claude/project-agents-setup-i8sTT`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — fixes the rules that BLOCK all edits.
- **User Stories (Phase 3+)**: All depend on Foundational. US1 and US2 edit *different
  frontmatter fields in the same files*, so they are independently testable but should
  not run as literally-parallel concurrent writes on the same file (sequence US1 → US2,
  or apply both fields per file in one pass). US3 (docs) is independent of US1/US2 content.
- **Polish (Phase 6)**: Depends on US1–US3 being complete.

### User Story Dependencies

- **US1 (P1)**: Independent — the MVP. Delivers the cost/quality benefit on its own.
- **US2 (P2)**: Independent outcome (color), but edits the same files as US1 — coordinate
  writes (see above). Does not change behavior.
- **US3 (P3)**: Independent — documents the policy US1/US2 realize.

### Within Each User Story

- The per-team edit tasks ([P]) touch disjoint file sets and can run in parallel **within
  the same story**.
- Each story ends with its verification task (T011, T017) before moving on.

### Parallel Opportunities

- US1: T005–T010 are disjoint file sets → parallelizable.
- US2: T012–T016 are disjoint file sets → parallelizable.
- Across stories: avoid concurrent writes to the same file for US1 vs US2 (same files,
  different fields) — either sequence the stories or set both fields per file in one edit.

---

## Parallel Example: User Story 1

```bash
# Disjoint file sets — safe to apply together:
Task: "Set model: opus on the 5 lead files"                 # T005
Task: "Set model: sonnet on Engineering workers (6 files)"  # T006
Task: "Set model: sonnet on Sports workers (7 files)"       # T007
Task: "Set model: sonnet on Data workers (4 files)"         # T008
Task: "Set model: sonnet on Family workers (3 files)"       # T009
Task: "Set model: sonnet on Product workers (3 files)"      # T010
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 Setup → Phase 2 Foundational (fix the rules).
2. Phase 3 US1 (model tiers) → run T011 verification.
3. **STOP and VALIDATE**: 5 opus leads + 23 sonnet workers, all explicit. This alone
   delivers the cost/quality benefit and is shippable.

### Incremental Delivery

1. US1 (tiers) → validate → ship (MVP).
2. US2 (team colors) → validate → ship.
3. US3 (policy docs) → validate → ship.
4. Polish: scope/guardrail verification + push.

---

## Notes

- This feature was implemented as a single mechanical pass (one script set both `model`
  and `color` per file), which satisfies US1 and US2 together while honoring the
  "avoid concurrent same-file writes" guidance.
- [P] = disjoint files, no dependency. Verification tasks are intentionally sequential.
- Safety: re-tiering does not touch minors' data or relax any guardrail (enforced by
  agent instructions + RBAC + constitution, independent of model tier).
