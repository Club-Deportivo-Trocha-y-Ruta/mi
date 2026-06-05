# Implementation Plan: Translate Claude/AI Instruction & Documentation Files to English

**Branch**: `001-translate-claude-files-english` | **Date**: 2026-06-05 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-translate-claude-files-english/spec.md`

## Summary

Translate the project's AI-facing instruction and documentation corpus from Spanish to natural English to improve prompt-engineering quality, while preserving all machine-significant tokens (paths, identifiers, env vars, enum values, dates, template names, Markdown/YAML structure) and all cross-references. Scope: `CLAUDE.md`, the 28 agent definitions under `.claude/agents/`, the 34 markdown pages under `docs/`, plus a coherence amendment to `.specify/memory/constitution.md` (Principle III) so the language policy is non-contradictory: **AI dev-assistant working language = English; product end-user copy (in code) = Spanish**. The work is a content refactor — no application code, schema, or runtime behavior changes. Verification relies on a glossary for terminology consistency and automated invariant checks (token diff, YAML/Markdown validity, idempotency, section parity), with AI self-verification plus a human (bilingual user) spot-check before merge.

## Technical Context

**Language/Version**: N/A (content/Markdown + YAML frontmatter refactor; no programming language change). Verification helpers may use POSIX shell + standard CLI (`git`, `grep`, `diff`, `python3 -c` for YAML parse).

**Primary Dependencies**: None new. Existing repo tooling only. YAML frontmatter validated with the already-present Python (`pyyaml`) or a Markdown frontmatter parse; Markdown validated by render/lint already available.

**Storage**: N/A (files on disk, versioned in git).

**Testing**: No code unit tests. Acceptance is enforced via verification gates: (a) token-preservation diff, (b) YAML frontmatter parses for all 28 agents, (c) Markdown structure/section-count parity, (d) idempotency re-run yields no diff, (e) link-resolution check, (f) residual-Spanish prose scan.

**Target Platform**: Repository working tree (developer machines + Claude Code runtime that loads `CLAUDE.md` and `.claude/agents/*`).

**Project Type**: Documentation / configuration localization refactor (single repository).

**Performance Goals**: N/A (one-time batch translation). Soft target: complete the corpus in a reviewable, well-chunked set of commits.

**Constraints**:
- Zero changes to non-prose tokens (byte-identical preservation).
- Zero broken cross-references (filenames/anchors used as link targets unchanged).
- No minors' PII introduced; preserve existing privacy posture of all files.
- Idempotent: re-translation produces no further changes.
- Out-of-scope files untouched (`.claude/skills/**`, rest of `.specify/**`, `.claude/settings.json`, binary/fixture assets).

**Scale/Scope**: 63 in-scope content files (1 `CLAUDE.md` + 28 agents + 34 docs ≈ 17,800 lines) + 1 constitution amendment (Principle III + version/Sync Impact Report).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applicability & Compliance |
|---|---|
| **I. Code Quality & Maintainability** | No source code changes, so linters/type-checkers are N/A. The analogous quality bar applies to content: Markdown MUST render and YAML frontmatter MUST parse (FR-009). Translation preserves structure and meaning (FR-012). **PASS.** |
| **II. Testing Standards (NON-NEGOTIABLE)** | No shippable code → no `pytest`/`vitest` deltas. The principle targets code that ships; this ships none. Equivalent assurance is provided by deterministic verification gates (token diff, YAML parse, section parity, idempotency, link check) defined in `contracts/`. Privacy invariant applies: no minor PII introduced (mapped to the privacy gate below). **PASS (no code under test).** |
| **III. User Experience Consistency** | Directly engaged. This feature **amends** Principle III's localization clause so it no longer mandates a single language ambiguously. New policy: product end-user copy stays **español neutro (Colombia)**; the AI dev-assistant working language becomes **English**. No product-facing copy in code is changed by this feature. Amendment follows governance (version bump + Sync Impact Report) per FR-005a. **PASS (with governed amendment).** |
| **IV. Performance Requirements** | N/A. No endpoints, bundles, queries, or runtime paths are modified. **PASS.** |

**Privacy / Compliance gate (Quality Gates & Compliance Constraints)**: Translation MUST NOT add any name, DOB, medical detail, or identifying metadata of a minor to any file, log, or commit message; existing privacy posture is preserved verbatim (FR-004, FR-012, FR-013). Commit messages for this feature follow Conventional Commits and contain no minor PII. **PASS.**

**Result**: All gates pass. No unjustified violations. Complexity Tracking not required (see note below for the one governed, non-violating amendment).

## Project Structure

### Documentation (this feature)

```text
specs/001-translate-claude-files-english/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output — translation approach, glossary policy, verification method
├── data-model.md        # Phase 1 output — file inventory + glossary + token-class taxonomy
├── quickstart.md        # Phase 1 output — how to run and verify the translation
├── contracts/
│   └── translation-invariants.md   # Phase 1 output — the verifiable contract every translated file must satisfy
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

No application source code is modified. The files changed by this feature are content/config:

```text
CLAUDE.md                              # translated (prose → English; tokens preserved)
.claude/agents/*.md                    # 28 files translated (frontmatter description + body)
docs/**/*.md                           # 34 files translated
.specify/memory/constitution.md        # Principle III amended + version/Sync Impact Report

# Explicitly NOT touched:
.claude/skills/**                      # third-party tooling, already English
.claude/settings.json                  # no prose
.specify/** (except constitution.md)   # already English / tooling
docs/**/*.{docx,pdf,yml,png,jpg}       # binary & fixture assets
```

**Structure Decision**: This is a content-localization refactor over an existing repository; there is no new code structure. Changes are confined to the file sets listed above. Work is organized by the three user-story slices (P1 `CLAUDE.md` → P2 agents → P3 docs) plus the constitution amendment, each independently reviewable as its own commit/group.

## Complexity Tracking

No constitution violations requiring justification. One **governed amendment** (not a violation): `.specify/memory/constitution.md` Principle III. Per the project's governance and the `/speckit-analyze` rule that principle changes occur outside the feature flow, this amendment MUST be executed as a **standalone** constitution update (via `/speckit-constitution`) sequenced BEFORE implementation of this feature begins. The feature's tasks then only *reference and verify* the amended principle; they do not perform the principle change inline. Because it resolves — rather than introduces — a contradiction, it does not require a Complexity Tracking exception.
