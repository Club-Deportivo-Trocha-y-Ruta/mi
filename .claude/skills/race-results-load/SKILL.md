---
name: race-results-load
description: Load an official Copa Valle results file (PDF or CSV/TSV) into the platform without ever showing a rider's name, club, city or time to the LLM. Drives `python -m scripts.race_results` (mask, profile-check, apply, stage, compare) end to end: write or reuse a reading profile from the masked view, stage locally, and stage in production only when the operator explicitly asks in this session. Use when the coach or operator says "carga los resultados de la válida <N>", "load the results PDF/acta for válida <N>", "procesa el acta de la copa", or pastes a path to an official results file. Never commits, corrects or decides rider identity — that stays the coach's job in the web app.
---

# Loading race results with the skill

You never read the official file, `private/`, or `.env*`. The engine (`app/services/race/results_skill/`) does all of that outside your reach; you only ever read `masked/` and `report.json`, and you only ever run `python -m scripts.race_results <subcommand>` from `backend/` with the venv active. `contracts/results-skill-cli.md` (specs/044-race-history-backfill/) is the authoritative contract this skill implements — the eight rules below are quoted from its "Skill procedure" section; if this file and that contract ever disagree, the contract wins and this file is out of date.

## Prerequisites (check once per session)

1. Backend venv active: `cd backend && source .venv/bin/activate`.
2. The local database is up (`docker compose up`, or however this checkout runs MySQL locally).
3. `backend/.env.production` is present **only** when production is actually intended this session. Never open it, never print it, never quote a value from it — refer to it by name only ("`.env.production`"), the same convention `bitacora-pdf` uses for the same file.
4. You know the operator's user id in each target database (local and, if relevant, production) — that id becomes `--user-id`.
5. The official results file and its manifest (see `references/manifest.md`) live **outside** this repository. `mask` refuses a path inside it.

## The eight rules (verbatim from the contract)

1. **Prerequisites, checked once per session:** backend venv; the local database up; `backend/.env.production` present only when production is intended (never opened or printed; refer to it by name); the operator's user id in each target; official files and manifests outside the repository.
2. **Read only `masked/` and `report.json`.** Never open the official file (not with Read, `cat`, `pdftotext` or anything else), `private/`, the manifest's source file, or `.env*`. If the operator pastes rider data into the chat, stop, do not repeat it, and ask them to remove it from the conversation.
3. **Profile first, from the view.** Reuse an existing profile when `profile-check` plus `apply` succeed. Otherwise write a new `backend/race_reading_profiles/<id>.json` from the masked view (`references/reading-profile.md`). Words that are masked and needed (an unknown category word) are asked of the operator, who reads them on the printed file; the answer goes into `category_aliases` or a vocabulary pull request, only if it is a category or column word.
4. **`apply` until clean.** Zero rows, unreadable rows or unrecognised categories are fixed by adjusting the profile. Inconsistent categories are **not** fixed by the skill: they are left for the coach's preview.
5. **Local first.** `stage` (local) → tell the operator the review path → the coach reviews and commits in the local app → optionally `compare` for válidas already loaded.
6. **Production only on request.** Run `stage --target production --confirm produccion` only after the operator explicitly asks for production in this session. Show the exact command first, never include a value from `.env.production`, and do one válida at a time.
7. **Report.** One line per válida: import id, revision or not, rows, categories, pending categories, and the review path. No names, and no times.
8. **Never** commit, correct, acknowledge or decide identities through the database or the API. Those are the coach's actions in the app.

## Step by step

### 1. `mask`

```bash
python -m scripts.race_results mask --file <absolute path outside the repo>
```

Read the run folder it prints. Open `masked/view.txt` and `masked/summary.json` with the Read tool — nothing else in that folder. `references/masked-view.md` explains how to read the geometry (positions, run counts, line kind) and, just as importantly, what you can never conclude from it — the view never shows a real word, even on a structural line, so you never "read off" a category or column name from it.

### 2. `profile-check` and `apply`

Try the existing `copa-valle-results-pdf` profile first:

```bash
python -m scripts.race_results profile-check --profile copa-valle-results-pdf
python -m scripts.race_results apply --run <run dir> --profile copa-valle-results-pdf
```

If `apply` reports zero rows, unreadable rows, or an unrecognised category, adjust the profile (or write a new one under `backend/race_reading_profiles/<id>.json` per `references/reading-profile.md`) and re-run `apply`. Keep iterating from the counts `apply` prints — never from a guess about what the file "probably" says. An inconsistent category (missing/duplicated ordinals) is **not** a profile problem — leave it for the coach's preview in the app.

If `apply` exits 3 (leak), stop immediately, do not run anything else in that run folder, and follow `docs/10-race-results/runbook-ops.md` §3.5.

### 3. `stage` — local first

```bash
python -m scripts.race_results stage --run <run dir> --manifest <path outside the repo> --user-id <id> --target local
```

Read the manifest's two forms in `references/manifest.md` before writing one. On success, tell the operator the review path the CLI prints (`/competitions/import?import=<id>`) and stop — the coach reviews and commits in the local web app. You never call `compare` to "check the coach's work" pre-emptively; use it only for a válida already loaded, on request.

### 4. Production — only when the operator asks, in this session

Do not run this on your own initiative, and do not run it just because the local stage succeeded. When the operator explicitly asks for production:

```bash
python -m scripts.race_results stage --run <run dir> --manifest <path> --user-id <id> --target production --confirm produccion
```

Show this exact command to the operator before running it. Never substitute or print a value from `.env.production`. One válida per invocation.

### 5. Report to the operator

One line per válida, no more:

> `import #<id>` — <revisión de la importación #N | primera carga> — `<rows>` filas, `<categories>` categorías, `<pending>` pendientes — revisar en `<review path>`

No rider name. No time. No club or city, even in aggregate ("the fastest club") — that is the coach's read of the review page, not yours.

## Refusals you will see, and what they mean

- `mask` exit 2/4: file location, format or scanned-PDF refusal — tell the operator, do not retry with a workaround (never `pdftotext`, never open the file yourself).
- `apply` exit 3: leak — stop, `runbook-ops.md` §3.5.
- `apply` exit 5: zero rows — the profile is wrong for this file.
- `apply` exit 6: the source file changed since `mask` — re-run `mask`.
- `stage` exit 8: `already_committed` — the same file is already committed; nothing to do.
- `stage` exit 9/10/11: target, actor, or schema-head refusal — read the message, do not retry with `--force` (there is no such flag).
- `stage` exit 12: `revision_not_available` — only possible in a checkout where `REVISION_STAGING_AVAILABLE` is off (it is on since T175). A different reading of a committed válida is normally staged as a revision: the coach reviews the diff and commits it with a reason in the app.

## Optional: an operator-side deny rule for the official-files folder

`permissions.deny` in `.claude/settings.json` already blocks `Read(./output/race-results/**/private/**)` — the run folder's own private half, inside this repo. That is not enough by itself to keep you off the *official file itself*, which lives outside the repo (rule 5) at a path only the operator knows. If the operator keeps official files and manifests under one fixed folder (e.g. `~/copa-valle/actas/`), they can add a matching deny rule in their own `.claude/settings.local.json` (never the committed `settings.json`, since that path is personal to their machine):

```json
{
  "permissions": {
    "deny": [
      "Read(~/copa-valle/actas/**)"
    ]
  }
}
```

This is a second, independent guardrail — the skill's own rule 2 ("never open the official file") is the one that actually matters, this just makes an accidental Read fail loudly instead of silently succeeding.

## Trigger description

- **Español**: Usa esta skill cuando el entrenador u operador pida "cargar los resultados de la válida <N>", "procesar el acta/PDF de resultados", "subir la copa" o pegue la ruta de un archivo oficial de resultados.
- **English**: Use this skill when the coach or operator asks to load, process or stage a válida's official results file (PDF, CSV or TSV), or pastes a path to one.
