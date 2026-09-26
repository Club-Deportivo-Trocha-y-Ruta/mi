# Contract — Results-loading CLI (amendment 2026-09-26 · FR-045 · FR-047 · FR-048 · FR-049)

The operator runs one script, from `backend/` with the venv active, and the `race-results-load` skill drives it. The same code runs against the local database and against production; only the target changes. Research: R-20…R-23, R-29, R-30.

```bash
python -m scripts.race_results <subcommand> [options]
```

## Run folder

`mask` creates one folder per file, `output/race-results/<YYYYMMDD-HHMMSS>-<sha8>/` (`output/` is git-ignored). It contains:

| Path | Content | May the LLM read it? |
|---|---|---|
| `masked/view.txt` | masked layout view (`masked-view.md`) | **yes**, the only file it reads |
| `masked/summary.json` | counts | yes |
| `private/source.json` | absolute path and SHA-256 of the official file | **never** |
| `private/document.json` | extracted rows (`ParsedResults`) | **never** |
| `report.json` | counts, codes, ordinals and exit status of the last subcommand | yes |

The official file and the manifest stay outside the repository; `mask` refuses a path inside it.

## Subcommands

### `mask --file <path>`

- Validates the file (magic bytes, text layer, 8 MB cap), creates the run folder and writes `masked/*` and `private/source.json`.
- Stdout: the run folder, format, pages or rows, and structural/content line counts.
- Exit codes: 0; 2 (refused file); 4 (no text layer).

### `profile-check --profile <profile_id | path>`

- Validates a profile against schema v1 (`reading-profile.md`).
- Stdout: `ok` or the list of rule violations (key paths and rule names).
- Exit codes: 0; 2.

### `apply --run <dir> --profile <profile_id | path>`

- Re-checks the source file's SHA-256 against `private/source.json`, applies the profile, writes `private/document.json` and runs the leak check.
- Stdout, per category: index, label (verbatim only if structural, otherwise `⟨no reconocida #k⟩`), code or `—`, rows, completeness (`ok` / `faltan [3]` / `repetidas [20]`), status counts. Then unreadable rows as `(page, ordinal)`, the totals, and `fuga: 0`.
- Exit codes:
  - 0: done; inconsistent categories are not an error, the coach resolves them in the app;
  - 3: leak;
  - 5: zero rows;
  - 6: source file changed since `mask`.

### `compare --run <dir> --target … [--confirm produccion] (--race-event-id N | --manifest <path>)`

- Read-only. It opens its session in read-only mode and always ends in `rollback()`.
- Compares `private/document.json` with the committed, non-deleted results of the same válida.
- Stdout, per category code: matched, changed, missing and extra counts. No row is printed.
- Exit codes: 0; 7 (válida not found in the target).

### `stage --run <dir> --manifest <path> --user-id <id> [--target local|production] [--confirm produccion] [--dry]`

- Stages the import (`staged-import.md`): evidence upload, then import plus staged document in one transaction, then audit, then revision detection.
- Never commits, corrects, acknowledges or decides identities (FR-048).
- Stdout:
  - import id and status;
  - `revisión de la importación #N` when it is a revision;
  - rows and categories counts, and warning codes;
  - the review path `/competitions/import?import=<id>`.
- Exit codes:
  - 0: staged, or already staged (same file, still pending);
  - 8: `already_committed`, when the same file is committed;
  - 9: target refused;
  - 10: user refused;
  - 11: schema head mismatch;
  - 2: manifest invalid;
  - 12: `revision_not_available`, only while the revision phase has not shipped (plan, Complexity Tracking). In that state a different reading of a committed válida is refused instead of being staged as a revision whose commit would only add rows.

## Manifest (JSON file outside the repository)

A manifest takes one of two forms.

**Explicit.** The fields and rules of the removed form:

```json
{"series_name": "Copa Valle", "series_kind": "cup", "series_level": "departmental",
 "season": 2024, "valida_num": 3, "event_name": "Válida III", "event_date": "2024-05-12", "location": "…"}
```

**Existing event.** Replaces the calendar prefill of feature 015:

```json
{"race_event_id": 42}
```

In the second form, series, kind, level, season, válida, date and venue are read from the event and its series in the target database.

Rules for both forms:
- `series_kind` and `series_level` use the enums of the removed route.
- `event_date` is an ISO date.
- Unknown keys are refused. Nothing is inferred from the file (FR-025).
- Race conditions are not accepted: the coach enters them on the válida's *Condiciones* tab (R-31).

## Target rules (FR-047, R-21)

| | Local (default) | Production |
|---|---|---|
| How it is selected | no `--target`, or `--target local` | `--target production --confirm produccion` |
| Settings source | `backend/.env` through `app.config` | only `MYSQL_*`, `HOSTINGER_SFTP_*` and `HOSTINGER_PUBLIC_BASE_URL` from `backend/.env.production`, loaded before `app.*` is imported; `APP_ENV=development`, `AI_ENABLED=false`, `STRAVA_ENABLED=false` |
| Refused when | `MYSQL_HOST` is not local (`localhost`, `127.0.0.1`, `::1`, `mysql`, `host.docker.internal`); or `APP_ENV=production`; or `(MYSQL_HOST, MYSQL_DB)` equals the pair in `backend/.env.production` | SFTP not fully configured; or the database `alembic_version` differs from the repository head; or `--confirm` missing or wrong |
| Evidence storage | SFTP if configured, otherwise the local fallback | Hostinger SFTP only |

- No environment value is ever printed. Errors are scrubbed of every value loaded from either file (the `bitacora_snapshot` pattern).
- `--dry` resolves the target, validates the manifest, the user and the document, and prints what would happen; it writes nothing.

## Actor (FR-048, R-22)

- `--user-id` must be an active user with role `admin` or `coach` in the target database. That user becomes `imported_by_user_id`, which drives club scope and the dry-run roster, as before.
- Audit: `record_audit(create, race_import)` with `AuditContext.for_user(actor)` and `meta.via = "results_skill"`.
- This check prevents mistakes, not attackers. Whoever holds the database credentials can already write anything, and this contract does not pretend otherwise.

## Stdout and logs

- Every subcommand prints only paths, ids, counts, codes, ordinals, page numbers and structural labels. It never prints a name, club, city, bib, time or points value, even on error.
- Python logging from the engine follows the same rule, and exception messages are replaced by their class name plus a code.
- `test_race_results_cli.py` runs every subcommand on synthetic files and sweeps stdout, stderr and `report.json` against the fake-name list.

## Tests

`backend/tests/scripts/test_race_results_cli.py`:
- **Happy path:** `mask` → `profile-check` → `apply` → `stage --target local` on aiosqlite, with storage on the local fallback.
- **Local guard:** refused when `MYSQL_HOST` is remote, when `APP_ENV=production`, and when the pair equals the production pair.
- **Production guard:** `--target production` refused without `--confirm`, without SFTP, and on an Alembic head mismatch. These use a fake `.env.production` in a tmp dir and never touch a network.
- **Actor:** unknown, inactive, parent and athlete users refused.
- **Duplicates:** same file staged twice gives one import; the committed same file exits 8.
- **Revision:** a different reading of a committed válida is staged as a revision.
- **`--dry`:** writes nothing (row counts unchanged in every race table).
- **Files:** in-repo file refused; scanned PDF refused.
- **Output:** the stdout sweep.

## Skill procedure (`.claude/skills/race-results-load/SKILL.md`)

The skill is instruction corpus, written in English. It mirrors the structure of `bitacora-pdf` and must state the rules below. `data-privacy-guard` reviews it before it is used on a real file.

1. **Prerequisites, checked once per session:** backend venv; the local database up (`docker compose up`); `backend/.env.production` present only when production is intended (never opened or printed; the skill refers to it by name); the operator's user id in each target; official files and manifests outside the repository.
2. **Read only `masked/` and `report.json`.** Never open the official file (not with Read, `cat`, `pdftotext` or anything else), `private/`, the manifest's source file, or `.env*`. If the operator pastes rider data into the chat, stop, do not repeat it, and ask them to remove it from the conversation.
3. **Profile first, from the view.** Reuse an existing profile when `profile-check` plus `apply` succeed. Otherwise write a new `backend/race_reading_profiles/<id>.json` from the masked view. Words that are masked and needed (an unknown category word) are asked of the operator, who reads them on the printed file; the answer goes into `category_aliases` or a vocabulary pull request, only if it is a category or column word.
4. **`apply` until clean.** Zero rows, unreadable rows or unrecognised categories are fixed by adjusting the profile. Inconsistent categories are **not** fixed by the skill: they are left for the coach's preview (FR-004/FR-005). Exit 3 (leak) stops everything and the runbook §3.5 procedure applies.
5. **Local first.** `stage` (local) → tell the operator the review path → the coach reviews and commits in the local app → optionally `compare` for válidas already loaded.
6. **Production only on request.** Run `stage --target production --confirm produccion` only after the operator explicitly asks for production in this session. Show the exact command first, never include a value from `.env.production`, and do one válida at a time.
7. **Report.** One line per válida: import id, revision or not, rows, categories, pending categories, and the review path. No names, and no times.
8. **Never** commit, correct, acknowledge or decide identities through the database or the API. Those are the coach's actions in the app (FR-048).
