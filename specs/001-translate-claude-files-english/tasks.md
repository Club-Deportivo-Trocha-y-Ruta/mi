---
description: "Task list for translating the Claude/AI corpus to English"
---

# Tasks: Translate Claude/AI Instruction & Documentation Files to English

**Input**: Design documents from `/specs/001-translate-claude-files-english/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/translation-invariants.md, quickstart.md

**Tests**: No code tests (no-code content refactor). Acceptance is enforced by the verification invariants in `contracts/translation-invariants.md` (INV-1…INV-9), surfaced as explicit verification tasks per phase.

**Organization**: Tasks are grouped by user story (P1 → P2 → P3) plus a governed constitution amendment, so each slice is independently translatable, verifiable, and reviewable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1 = CLAUDE.md, US2 = agents, US3 = docs
- All paths are repo-relative from project root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Lock terminology and prepare the verification approach before any translation.

- [ ] T001 Review and finalize the canonical glossary in `specs/001-translate-claude-files-english/data-model.md` (add any recurring Spanish term missing from the corpus; confirm "do not translate" list for stack/proper nouns)
- [ ] T002 [P] Build the preserved-token allow-list (proper nouns, enum values `Pre-PHV`/`Circa-PHV`/`Post-PHV`, template names, seed emails, stack names) as a reference note in `specs/001-translate-claude-files-english/data-model.md`
- [ ] T003 [P] Confirm verification commands from `specs/001-translate-claude-files-english/quickstart.md` run in this environment (`python3` + `pyyaml` available for INV-2; `git diff`, `grep` for INV-5/INV-7)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Stand up the reusable verification harness that every story depends on.

**⚠️ CRITICAL**: No file may be marked "verified" until these checks exist and run.

- [ ] T004 Create verification helper script `specs/001-translate-claude-files-english/verify.sh` implementing INV-1 (token diff), INV-3 (heading/table/code-block parity), and INV-4 (residual-Spanish prose scan) per `contracts/translation-invariants.md`
- [ ] T005 [P] Add INV-2 frontmatter check (parse all `.claude/agents/*.md`, assert only `description` changed) to `specs/001-translate-claude-files-english/verify.sh`
- [ ] T006 [P] Add INV-6 (link resolution) and INV-7 (out-of-scope guard via `git diff --name-only` allow-list) to `specs/001-translate-claude-files-english/verify.sh`
- [ ] T007 Capture a baseline token/heading snapshot of all in-scope source files (pre-translation) so INV-1/INV-3 can diff source vs. target

**Checkpoint**: Verification harness ready — translation of any story can begin.

---

## Phase 3: User Story 1 - Central runtime guidance in English (Priority: P1) 🎯 MVP

**Goal**: `CLAUDE.md` reads natively in English with all tokens, tables, and structure preserved; the "Idioma" directive becomes an English working-language directive that affirms Spanish product copy.

**Independent Test**: Open translated `CLAUDE.md` — no residual Spanish prose, every original section present, all paths/tables/env vars/dates/calendar byte-identical; a fresh Claude Code session operates correctly on the English guidance.

- [ ] T008 [US1] Translate `CLAUDE.md` prose to English (Identity, Reference docs, Stack, Architecture, Data model, Production, Deploy, all Implementation-status sections, Dev credentials note, Technical notes, Dev commands, Calendar labels, Non-negotiable principles, Age-group differentiation, Session format labels, Privacy, Context-compaction) applying the glossary; preserve all code blocks, paths, env vars, enum values, dates, URLs, and the Copa Valle calendar data per `data-model.md`
- [ ] T009 [US1] Rewrite the `CLAUDE.md` "## Idioma" section as "## Language": instruct the AI dev-assistant to operate and respond in English, and explicitly affirm that product end-user copy (emails/PDF/UI in code) stays Spanish (Colombia) — implements FR-005 (must mirror the amended constitution Principle III from T031)
- [ ] T010 [US1] Translate the mandatory "Formato de sesiones de entrenamiento" template: section labels to English (`CALENTAMIENTO`→`WARM-UP`, `PARTE PRINCIPAL`→`MAIN SET`, `VUELTA A LA CALMA`→`COOL-DOWN`, `Notas`→`Notes`) while preserving 🚴/📅/⏱/💡 markers (FR-007)
- [ ] T011 [US1] Run `verify.sh` against `CLAUDE.md` (INV-1, INV-3, INV-4, INV-6); fix any token/structure/link regressions
- [ ] T011a [US1] Triage INV-6 link findings on `CLAUDE.md`: the reference to `docs/03-fase1/workflow.md` is a PRE-EXISTING broken link (folder absent). Decide per ref — correct the path, or remove/annotate the stale reference — and record the decision. Do not let a pre-existing break silently fail the gate

**Checkpoint**: `CLAUDE.md` fully translated and verified — MVP deliverable.

---

## Phase 4: User Story 2 - Agent instruction files in English (Priority: P2)

**Goal**: All 28 `.claude/agents/*.md` translated (frontmatter `description` + body), preserving `name`/`model`/`memory`, agent-slug cross-references, paths, and output formats.

**Independent Test**: Every agent file's body is English, frontmatter parses, only `description` changed, all referenced slugs/paths preserved, required output formats intact; no residual Spanish prose.

> Batches are split by file set so they can run in parallel; within a batch, files are independent.

- [ ] T012 [P] [US2] Translate sports-ops agents: `.claude/agents/head-coach-lead.md`, `training-planner.md`, `nutrition-advisor.md`, `injury-prevention-advisor.md`, `technique-coach.md`, `mental-performance-coach.md`, `competition-strategist.md`, `sports-science-advisor.md` (translate `description` + body; preserve 🚴 format labels per FR-007, slugs, and `docs/` paths)
- [ ] T013 [P] [US2] Translate data/privacy agents: `.claude/agents/data-platform-lead.md`, `data-analyst.md`, `results-analyst.md`, `data-privacy-guard.md`, `analytics-reporter.md` (preserve `services/race/*`, CLI command names, enum values)
- [ ] T014 [P] [US2] Translate engineering agents: `.claude/agents/engineering-lead.md`, `fastapi-architect.md`, `react-ui-engineer.md`, `devops-engineer.md`, `qa-engineer.md`, `database-architect.md`, `integration-engineer.md` (preserve stack names, file paths, identifiers)
- [ ] T015 [P] [US2] Translate family/comms agents: `.claude/agents/family-relations-lead.md`, `parent-communicator.md`, `community-content-creator.md`, `event-coordinator.md` (preserve Resend template names, privacy notes; keep Spanish product copy examples flagged as deliberate)
- [ ] T016 [P] [US2] Translate product agents: `.claude/agents/product-manager.md`, `release-manager.md`, `technical-writer.md`, `ux-researcher.md` (preserve doc paths, convention references)
- [ ] T017 [US2] Run `verify.sh` INV-2 (frontmatter integrity, only `description` changed) across all 28 agent files; fix regressions
- [ ] T018 [US2] Run `verify.sh` INV-1/INV-3/INV-4/INV-6 across all 28 agent files; confirm 0 broken slug/path references and 0 residual Spanish prose

**Checkpoint**: All agents translated, frontmatter valid, references intact.

---

## Phase 5: User Story 3 - Reference documentation in English (Priority: P3)

**Goal**: All 34 `docs/**/*.md` translated, structure/diagrams/code preserved, binary & fixture assets untouched, links resolving.

**Independent Test**: Each doc's prose is English with identical structure; `.docx`/`.pdf`/`.yml`/images unchanged; intra-doc and inbound links still resolve.

> One task per numbered folder (and root files); all parallelizable since folders are disjoint.

- [ ] T019 [P] [US3] Translate root docs: `docs/01-marco-teorico.md` and `docs/README.md`
- [ ] T020 [P] [US3] Translate `docs/02-scaffolding/` markdown files
- [ ] T021 [P] [US3] Translate `docs/04-percentiles/` markdown files
- [ ] T022 [P] [US3] Translate `docs/05-design-system/` markdown files
- [ ] T023 [P] [US3] Translate `docs/06-parents/` markdown files
- [ ] T024 [P] [US3] Translate `docs/07-notifications/` markdown files
- [ ] T025 [P] [US3] Translate `docs/08-onboarding/` markdown files
- [ ] T026 [P] [US3] Translate `docs/09-training-planning/` markdown files (preserve `snapshots/*.yml` fixtures untouched)
- [ ] T027 [P] [US3] Translate `docs/10-race-results/` markdown files (preserve `snapshots/*.pdf` and any fixtures untouched)
- [ ] T028 [P] [US3] Translate `docs/11-informe-tecnico-mensual/` markdown files
- [ ] T029 [P] [US3] Translate `docs/12-competitions-unification/` markdown files
- [ ] T030 [US3] Run `verify.sh` INV-1/INV-3/INV-4/INV-6/INV-7 across `docs/**`; confirm binary/fixture assets are byte-identical and all links resolve

**Checkpoint**: Entire docs corpus translated; out-of-scope assets confirmed untouched.

---

## Phase 0 (Prerequisite): Constitution Amendment (Governed — FR-005a)

> ⚠️ Execute as a **standalone `/speckit-constitution` update**, not as part of this feature's translation commits. Must land BEFORE US1's "Language" wording (T009) so the two stay coherent.

**Goal**: Eliminate the language-policy contradiction by amending the constitution to match the planned `CLAUDE.md` policy.

**Independent Test**: Constitution Principle III and `CLAUDE.md` "Language" section state the same policy; constitution version bumped and Sync Impact Report updated.

- [ ] T031 Via `/speckit-constitution`, amend `.specify/memory/constitution.md` Principle III ("User Experience Consistency") to codify: AI dev-assistant working language = English; product end-user copy = español neutro (Colombia). Do not change other principles
- [ ] T032 (handled by `/speckit-constitution`) Verify the Sync Impact Report comment is updated and the version is bumped (MINOR per its versioning policy) with Ratified/Last-Amended dates
- [ ] T033 Run INV-9 (language-policy coherence): cross-read `CLAUDE.md` "Language" + amended constitution Principle III; confirm single coherent policy + version/report delta

**Checkpoint**: Governance documents coherent; SC-008 satisfied. (Run T031–T032 before Phase 1; T033 runs after T009.)

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Whole-corpus acceptance, idempotency, privacy, and sign-off.

- [ ] T034 Run full `verify.sh` across the entire in-scope set (INV-1…INV-7) and confirm all green
- [ ] T035 INV-5 idempotency: run a second translation pass over all translated files; assert `git diff --quiet` (no further changes)
- [ ] T036 [P] INV-8 privacy sweep: confirm no minor PII introduced in any file or commit message; placeholders remain placeholders
- [ ] T037 [P] Execute `specs/001-translate-claude-files-english/quickstart.md` end-to-end as a final validation walkthrough
- [ ] T038 Update `specs/001-translate-claude-files-english/checklists/requirements.md` if any item state changed; record final pass counts
- [ ] T039 Bilingual user spot-check sign-off on the P1/P2 sample (`CLAUDE.md` + agents) per clarify Q2 Option A; record sign-off (Definition of Done gate)
- [ ] T040 Prepare reviewable commits (Conventional Commits, no AI-tool references, no minor PII): CLAUDE.md; agent batches; docs by folder; constitution amendment

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately
- **Foundational (Phase 2)**: depends on Phase 1 — BLOCKS all stories (verification harness)
- **Constitution (Phase 0, prerequisite)**: T031–T032 run as a standalone `/speckit-constitution` update BEFORE Phase 1; T033 (coherence check) runs after T009
- **US1 / US2 / US3 (Phases 3–5)**: each depends only on Phase 2; mutually independent (different file sets) — can run in parallel. US1's T009 must mirror the Phase 0 amendment
- **Polish (Phase 7)**: depends on all desired stories + Phase 0 being complete

### User Story Dependencies

- **US1 (P1)**: independent — MVP
- **US2 (P2)**: independent of US1 (separate files); shares the glossary + harness
- **US3 (P3)**: independent of US1/US2 (separate files); shares the glossary + harness

### Within Each User Story

- Translate → run per-story `verify.sh` → fix regressions → checkpoint

### Parallel Opportunities

- Phase 1: T002, T003 in parallel
- Phase 2: T005, T006 in parallel (after T004 scaffolds the script)
- Phase 4: T012–T016 (agent batches) all in parallel
- Phase 5: T019–T029 (docs folders) all in parallel
- Across stories: US1, US2, US3 can be worked simultaneously by different agents/people once Phase 2 is done

---

## Parallel Example: User Story 2 (agents)

```bash
# Translate all agent batches concurrently (disjoint file sets):
Task: "Translate sports-ops agents (T012)"
Task: "Translate data/privacy agents (T013)"
Task: "Translate engineering agents (T014)"
Task: "Translate family/comms agents (T015)"
Task: "Translate product agents (T016)"
# Then converge on T017/T018 verification.
```

## Parallel Example: User Story 3 (docs)

```bash
# Each numbered docs folder is independent:
Task: "Translate docs/02-scaffolding (T020)"
Task: "Translate docs/05-design-system (T022)"
Task: "Translate docs/10-race-results (T027)"
# ... then T030 verification.
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

0. Phase 0 constitution amendment (standalone) → 1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 `CLAUDE.md` (+ T033 INV-9) → 4. **STOP & VALIDATE** (`verify.sh` green, fresh session works) → 5. Demo MVP.

### Incremental Delivery

1. Constitution amendment (Phase 0, standalone `/speckit-constitution`) → commit
2. Setup + Foundational → harness ready
3. US1 (`CLAUDE.md`) → T033 INV-9 coherence → verify → commit (MVP)
4. US2 (agents) → verify → commit
5. US3 (docs) → verify → commit
6. Polish (idempotency, privacy, sign-off)

### Parallel Team Strategy

After Phase 2: Agent/Dev A → US1; B → US2 batches; C → US3 folders. Converge on Phase 6–7.

---

## Notes

- [P] = different files, no incomplete-task dependency
- Every translation task pairs with a verification task before its checkpoint
- Commit per logical group; Conventional Commits; no AI-tool references; no minor PII
- The only out-of-`.claude`/`docs` edit is the governed constitution amendment (Phase 6)
- Stop at any checkpoint to validate a story independently
