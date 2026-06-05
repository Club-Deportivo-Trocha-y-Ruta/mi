# Quickstart: Translating the Claude/AI Corpus to English

Audience: whoever (human or AI agent) executes the translation. Assumes you are on branch `001-translate-claude-files-english`.

## 0. Prerequisites

- Clean working tree on the feature branch.
- Read `research.md` (approach), `data-model.md` (glossary + token taxonomy), and `contracts/translation-invariants.md` (acceptance gates).

## 1. Lock the glossary

Confirm the glossary in `data-model.md` is complete for the terms in the corpus. Add any missing recurring term **before** bulk translating so vocabulary stays consistent.

## 2. Translate in priority order (one reviewable group at a time)

1. **P1 — `CLAUDE.md`** (highest leverage). Translate prose, preserve tokens, flip the "Idioma" → "Language" directive to English working language while affirming Spanish product copy.
2. **P2 — `.claude/agents/*.md`** (28 files, batch in small groups). Translate `description` frontmatter + body; preserve `name`/`model`/`memory` and all slugs/paths.
3. **P3 — `docs/**/*.md`** (34 files, by numbered folder).
4. **Constitution amendment** — edit `.specify/memory/constitution.md` Principle III to the coherent policy; bump version (MINOR per its policy) and update the Sync Impact Report comment.

For each file: translate prose only; keep every token-class item from `data-model.md` byte-identical.

## 3. Verify each file against the contract

Run the checks from `contracts/translation-invariants.md`. Suggested commands (adapt as needed):

```bash
# INV-2: every agent frontmatter still parses
for f in .claude/agents/*.md; do
  python3 - "$f" <<'PY'
import sys,yaml
s=open(sys.argv[1],encoding='utf-8').read()
fm=s.split('---',2)[1]
d=yaml.safe_load(fm)
assert 'name' in d and 'description' in d, sys.argv[1]
print("ok", d['name'])
PY
done

# INV-7: only in-scope files changed
git diff --name-only

# INV-5: idempotency — after a second pass there should be no diff
git diff --quiet && echo "no further changes"

# INV-6: relative links resolve (spot example)
grep -oE '\]\(([^)]+\.md)' CLAUDE.md
```

- **INV-1 / INV-3 / INV-4**: extract code/token spans and headings from source vs. target and compare counts/sets; run the residual-Spanish scan and review flags.
- **INV-8**: confirm the diff introduces no personal data; scan commit messages.
- **INV-9**: cross-read `CLAUDE.md` "Language" + constitution Principle III for one coherent policy; confirm version bump + Sync Impact Report edit.

## 4. Commit in reviewable slices

Conventional Commits, no AI-tool references, no minor PII. Example grouping:

- `docs(claude): translate CLAUDE.md to English`
- `docs(agents): translate <batch> agent definitions to English`
- `docs: translate docs/<NN-folder> to English`
- `docs(constitution): align language policy (Principle III) — vX.Y.Z`

## 5. Sign-off (Definition of Done)

- All automated gates green for every in-scope file.
- INV-9 coherence confirmed.
- Bilingual user spot-check of `CLAUDE.md` + agents complete (clarify Q2 Option A).

When all of the above hold, the feature is Done and ready for PR/merge.
