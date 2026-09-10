# Night run — feature 041, phases 6 to 11

Instructions for the unattended cloud sessions of the night of 2026-09-09 (three runs, 9:30pm, 12:30am and 3:30am Colombia time, about 2h45m each). Each run resumes where the previous one stopped. You work alone; nobody will answer a question, so decide and record the decision.

## Start of every run

1. `git checkout feat/041-multi-coach-governance && git pull`
2. Read `CLAUDE.md` at the repository root. It is authoritative on architecture, commands and the three hard project rules: minors' privacy under Colombian Ley 1581, secrets never entering the transcript, and the language split.
3. Read `specs/041-multi-coach-governance/tasks.md`. Tasks marked `[X]` are done, `[ ]` are not. Work in order from the first unchecked one.
4. Read `specs/041-multi-coach-governance/checklists/integration-review.md`. It holds the open gaps left by the earlier phases.
5. Each task cites its contract under `specs/041-multi-coach-governance/contracts/`. Those files are long: use `grep` or `sed -n` to jump to the cited section only. Do not read them whole.

Phases 1 to 5 are complete: the audit foundation (`audit_log`, `record_audit`, request context, one Alembic revision, attribution columns), instrumentation of every write, the history read API with its pages (US1), athlete archiving that preserves parental-consent evidence (US2), and club staff onboarding (US3).

## Order of work

1. Redo **T050** — the US2 integration review. Its earlier run was invalid because the backend could not import at the time.
2. **T059 to T068** — US4: co-coached sessions, the acting coach named in family e-mails, attendance attribution.
3. **T069 to T074** — US5: optimistic concurrency on the newsletter studio, coach-note author, approval evidence.
4. **T075 to T080** — US6: club-scoped rule for AI runs and import parses, spend per coach.
5. **T081 to T086** — US7: per-coach activity report and author names.
6. **T087 to T090** — US8: 24-month retention purge as a Typer CLI plus its GitHub Actions workflow.
7. **T091 to T098** — polish: privacy audit, Playwright specs, docs, gates, PR description.

## Environment

Create the backend virtualenv on the first run: `cd backend && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt`. Frontend: `cd frontend && npm install`.

- Run backend tests from `backend/` with `./.venv/bin/python -m pytest -q`.
- **There is very likely no MySQL and no Docker.** The `client` fixture in `backend/tests/conftest.py` starts the app against the real database, so about 225 tests already fail on `main` for that reason alone. That is pre-existing and environmental: do not try to fix it and never count it as a regression. Establish the baseline once per run by checking out `main` into a separate worktree under `/tmp` and running the suite there, then compare failure lists. **Never** use `git stash`, `git checkout`, `git reset`, `git clean` or `git restore` on the working tree: in an earlier wave a `git stash` destroyed eleven agents' uncommitted work. Read-only comparison only, via `git show HEAD:<file>` or a separate worktree.
- Tests marked `-m mysql` cannot run. Write them, do not execute them, and say so.
- **T097 (post-deploy smoke) cannot be done**: it needs production credentials that are not available here. Leave it unchecked and record why.
- New test files should avoid the `client` fixture. Use the own-sqlite-engine-with-table-subset pattern of `backend/tests/routers/test_audit_log_api.py`, reusing `backend/tests/helpers/audit_tables.py`.

## Owner decisions — settled, never re-open

1. Both coaches see and edit everything club-wide. Only attribution is added, no portfolios, no owner-only guards.
2. The log records writes plus document exports and sends involving a minor's data. Never reads.
3. A session can have two or more coaches, hence the bridge table.
4. A minimal `/admin/usuarios` screen. No coach-invitation flow.
5. Retention is 24 months, purged manually with a preview, readable only by an admin or a coach of the club.
6. The newsletter coach-note author is visible to coaches only. Families keep the institutional voice.

## Rules while working

- Minors' privacy: audit rows carry identifiers, column names and catalogue codes. Never a name, birth date, measurement, or narrative text of a minor. Respect `VALUE_ALLOWLIST` and `META_ALLOWLIST` in `backend/app/services/audit.py`.
- Product copy in neutral Colombian Spanish with full diacritics. New comments and docstrings in Spanish with diacritics too.
- Use subagents (the Agent tool) to parallelise independent tasks, giving each one a disjoint set of files. Never let two agents own the same file.
- Mark each finished task `[X]` in `tasks.md` yourself; that file is the durable progress record across runs.

## Commit and push

Authorised by the owner: commit and push **only** to `feat/041-multi-coach-governance`. Never to `main`, and do not open a pull request.

Commit at the end of every phase, and again before your window closes. Conventional Commits: type in English, description in Spanish, never mentioning AI tooling. End each commit message with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## Before your window closes

Leave about fifteen minutes. Then:

1. Commit and push whatever is finished.
2. Append a dated section to `specs/041-multi-coach-governance/checklists/integration-review.md` with: which tasks you completed, the real test counts (total failures, how many are the environmental MySQL problem, how many are genuine regressions with their names), and every open gap with file and line.
3. Push that too, so the next run starts from it.

Report honestly. If a phase is half done, say which half. Never report a passing suite you did not actually run.
