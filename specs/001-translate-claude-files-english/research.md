# Phase 0 Research: Translate Claude/AI Instruction & Documentation Files to English

This document resolves the open decisions for the translation refactor. There were no `NEEDS CLARIFICATION` tokens left in Technical Context; the items below capture the deliberate approach decisions.

## Decision 1 — Translation method: section-aware manual/AI translation, not machine find-replace

**Decision**: Translate file-by-file with an AI pass that distinguishes *prose* (translate) from *machine-significant tokens* (preserve byte-for-byte), guided by a shared glossary. Do **not** use blunt global find-replace or an opaque MT service over whole files.

**Rationale**: The corpus interleaves prose with code identifiers, paths, env vars, enum stored values (`Pre-PHV`, `Circa-PHV`, `Post-PHV`), template names (`training_session_invite`), and seed data. A naive translator would corrupt these and break the running system or links. A section-aware pass preserves structure (FR-004, FR-006, FR-007) and keeps meaning faithful (FR-012).

**Alternatives considered**:
- *Whole-file machine translation* — rejected: mangles code blocks, identifiers, and YAML; non-idempotent.
- *Global sed/grep replacement of common words* — rejected: produces unidiomatic English and corrupts substrings inside identifiers.

## Decision 2 — Terminology consistency via an authoritative glossary

**Decision**: Establish the glossary in `data-model.md` first and apply it across all 63 files. Canonical mappings (e.g., entrenador→coach, atleta→athlete, asistencia→attendance, sesión de entrenamiento→training session, antropometría→anthropometry, padre/acudiente→parent/guardian) are fixed before bulk translation.

**Rationale**: FR-010 and SC consistency require the same English term everywhere; a glossary prevents synonym drift across 28 agents + docs.

**Alternatives considered**: Per-file ad-hoc word choice — rejected: yields inconsistent vocabulary and harder review.

## Decision 3 — Output-language policy and constitution coherence (resolves clarify Q1 → Option A)

**Decision**: After translation, both `CLAUDE.md` ("Idioma/Language" section) and the constitution (Principle III) express one policy: **AI dev-assistant working language = English**; **product end-user copy (backend Jinja email/PDF templates, frontend UI strings) = Spanish (Colombia)**. The constitution amendment uses its governance procedure (version bump + Sync Impact Report).

**Rationale**: The user chose full English for the dev assistant; leaving the constitution mandating Spanish would create a direct contradiction (SC-008). Amending Principle III is the minimal coherent fix and keeps the future `/speckit-plan` Constitution Check green.

**Alternatives considered**:
- Leave constitution untouched + document exception — rejected by user (Option B).
- Nuanced flip without touching constitution — rejected by user (Option C).

## Decision 4 — Verification method (planning assumption for clarify Q2 → Option A)

**Decision**: AI self-verifies every translated file (fidelity/back-translation sanity pass + automated invariant checks), and the bilingual user spot-checks a high-leverage sample (`CLAUDE.md` + the agent files) before merge. Definition of Done = all automated gates green **and** user sign-off.

**Rationale**: ~63 files + constitution is too large for mandatory 100% human review, but `CLAUDE.md` and agents have the highest behavioral impact and warrant a human spot-check. This balances throughput with assurance and makes the DoD testable.

**Status**: Confirmed by user on 2026-06-05 (Option A). DoD = automated gates green + bilingual user spot-check sign-off on the P1/P2 sample.

**Alternatives considered**: Automated-only (Option B) — faster, lower assurance on nuance; Full human review (Option C) — highest assurance, slowest.

## Decision 5 — Verification gates (how "done" is proven)

**Decision**: Enforce six deterministic checks per file, detailed in `contracts/translation-invariants.md`:
1. **Token-preservation diff** — extract code spans/paths/URLs/env vars/enum values/dates from source and target; assert identical sets.
2. **YAML frontmatter parses** — all 28 agent files load; `name`/`model`/`memory` keys byte-identical; only `description` changed.
3. **Section/heading parity** — heading count and order match source.
4. **Residual-Spanish prose scan** — heuristic scan (common Spanish stopwords/diacritic patterns outside code spans) flags untranslated prose for review.
5. **Idempotency** — a second translation pass yields an empty diff.
6. **Link resolution** — every relative link/anchor target still exists.

**Rationale**: Encodes FR-004/006/009/011 and SC-001..008 as runnable acceptance, satisfying the Constitution's testing-equivalent assurance for a no-code change.

**Alternatives considered**: Eyeball-only review — rejected: not reproducible, misses token corruption.

## Decision 6 — Sequencing and reviewability

**Decision**: Execute in the spec's priority order — P1 `CLAUDE.md` → P2 `.claude/agents/*` → P3 `docs/**` → constitution amendment — grouped into reviewable commits (e.g., CLAUDE.md alone; agents in small batches; docs by numbered folder).

**Rationale**: Each slice is independently valuable and testable (spec user stories), and small commits keep the bilingual spot-check tractable.

**Alternatives considered**: One giant commit — rejected: unreviewable, risky rollback.

## Decision 7 — Privacy preservation during translation

**Decision**: Treat every file as potentially privacy-sensitive. Translation MUST NOT add minor names/DOB/medical detail; existing placeholders and privacy notes are translated faithfully without de-anonymizing anything. Commit messages carry no minor PII.

**Rationale**: Constitution privacy gate + FR-013. Some docs discuss privacy audits and use placeholders that must remain placeholders.

**Alternatives considered**: None — non-negotiable.
