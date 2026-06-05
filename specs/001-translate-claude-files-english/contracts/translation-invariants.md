# Contract: Translation Invariants

This is the verifiable acceptance contract every translated file MUST satisfy. It is the no-code substitute for unit tests (Constitution Principle II equivalence). Each invariant maps to functional requirements and success criteria in `spec.md`.

For a translated file `T` derived from source `S`:

## INV-1 — Token preservation (FR-004, SC-003)

The multiset of machine-significant tokens extracted from `S` equals that of `T`.

- **Extracted tokens**: inline code spans (`` `...` ``), fenced code-block contents, URLs, email addresses, file paths, environment variable names + example values, enum stored values, template/event names, dates (`YYYY-MM-DD`), and numeric thresholds.
- **Check**: `tokens(S) == tokens(T)` as sets (order may differ only where prose reordering is unavoidable; code blocks keep order).
- **Fail action**: revert token, re-translate only surrounding prose.

## INV-2 — Frontmatter integrity (agent files) (FR-002, FR-009, SC-004)

For each `.claude/agents/*.md`:

- YAML frontmatter parses without error.
- Keys `name`, `model`, `memory` (and any non-`description` key) are **byte-identical** to source.
- Only `description` value differs and is valid English.
- **Check**: parse YAML; diff keys; assert single changed key.

## INV-3 — Structure & section parity (FR-001, SC-007)

- Heading count and nesting depth of `T` equal those of `S`.
- Table count and code-block count equal those of `S`.
- **Check**: count `^#{1,6} ` lines, fenced blocks, and table header rows; compare.

## INV-4 — No residual untranslated prose (FR-001..003, SC-001)

- Heuristic scan outside code spans for Spanish stopwords (`el, la, los, las, de, que, para, con, sin, según, atleta, entrenador, sesión, …`) and Spanish-only diacritic patterns flags candidate prose for human review.
- **Check**: scanner output reviewed; 0 confirmed untranslated prose segments remain.
- Note: deliberately-preserved Spanish (proper nouns, intentional copy) is allow-listed and excluded.

## INV-5 — Idempotency (FR-011, SC-006)

- Running the translation process again on `T` yields no diff.
- **Check**: re-run pass; `git diff --quiet`.

## INV-6 — Link resolution (FR-006, SC-004)

- Every relative link target and intra-doc anchor referenced in `T` resolves to an existing file/anchor.
- Cross-references to agent slugs and code symbols are unchanged from `S`.
- **Check**: extract links; assert targets exist; diff reference set vs. `S`.
- **Pre-existing broken links** in the source (e.g., `CLAUDE.md` → `docs/03-fase1/workflow.md`, whose folder is absent) are out of translation scope but MUST be triaged (fix the path or remove/annotate the reference), not silently passed by the gate.

## INV-7 — Out-of-scope untouched (FR-008, SC-002)

- No file outside the in-scope set is modified.
- **Check**: `git diff --name-only` ⊆ {`CLAUDE.md`, `.claude/agents/*.md`, `docs/**/*.md`, `.specify/memory/constitution.md`, `specs/001-*/**`}.

## INV-8 — Privacy preserved (Constitution privacy gate, FR-013)

- No minor's name/DOB/medical detail/identifying metadata is introduced anywhere (files, commit messages).
- Placeholders remain placeholders (no de-anonymization).
- **Check**: diff adds no new personal data; commit-message scan clean.

## INV-9 — Language-policy coherence (FR-005, FR-005a, SC-008)

- `CLAUDE.md` "Language" section and constitution Principle III state the same policy (English dev-assistant working language; Spanish product copy).
- Constitution version bumped and Sync Impact Report updated.
- **Check**: cross-read both sections; confirm version delta + report edit.

## Note on FR-012 (semantic fidelity)

FR-012 (no change of meaning/intent/constraints) has **no deterministic automated gate**. It is verified by AI self-check (back-translation sanity) plus the bilingual user spot-check (clarify Q2 Option A). Treat it as judgment-verified, not machine-asserted.

## Definition of Done

A file is **Done** when INV-1..INV-8 pass for it; the **feature** is Done when every in-scope file is Done, INV-9 passes for the policy pair, all automated gates are green, and the bilingual user has signed off on the P1/P2 spot-check sample (per research Decision 4 / clarify Q2 Option A).
