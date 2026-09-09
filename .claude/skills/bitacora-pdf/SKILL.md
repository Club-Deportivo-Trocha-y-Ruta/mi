---
name: bitacora-pdf
description: Generate the monthly family newsletter ("Bitácora de etapa") PDF for one or all athletes straight from the production database, with the narrative written by Claude Code instead of the Gemini pipeline. Use when the coach asks to "generar el boletín / la bitácora de <mes>", "hacer el PDF del boletín", or wants a more professional newsletter than the in-app one. Reads MySQL in read-only mode, never writes to the DB, never sends email.
---

# Bitácora de etapa — PDF desde Claude Code

Three steps: **snapshot** (Python, reads prod) → **narrative** (you write JSON per athlete) → **render** (Python validates guardrails and produces the PDF). Nothing is persisted to the database and no email is sent; the coach reviews the PDFs and distributes them.

## Prerequisites (check once per session)

- `backend/.env.production` exists with `MYSQL_HOST/PORT/USER/PASS/DB` (gitignored). Never print its contents. If missing, ask the coach to create it with `!` in the prompt.
- Local Alembic head must match prod. If the snapshot fails with `Unknown column …`, prod is behind `main`: tell the coach which migration is pending (`alembic history -r <prod_version>:head`) and run the snapshot from a worktree (`git worktree add --detach /tmp/tyr-snap <sha>` + copy the two scripts). **Pick the newest commit whose migrations prod already has, not simply the deployed one** — an older commit silently changes what the snapshot contains. Concretely: a snapshot taken before `84c8061` (feature 039) has no `cups` key, and the PDF template then falls back to a single mixed season chart that puts Copa Valle válidas, the Campeonato Departamental and the Campeonato Nacional on one axis. A cup is never comparable with another cup or with a championship. After any snapshot, verify `race_results.cups` and `race_results.championships` exist before writing narratives. The render step can always run from the main checkout.
- WeasyPrint needs Homebrew `pango`/`cairo`; the render script re-execs itself with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` on macOS.

## Step 1 — Snapshot (read-only)

```bash
cd backend && source .venv/bin/activate
python scripts/bitacora_snapshot.py --year 2026 --month 8 --all            # every athlete
python scripts/bitacora_snapshot.py --year 2026 --month 8 --athlete-id 6   # one athlete (repeatable)
```

Output: `output/bitacora/<YYYY-MM>/athlete-<id>/{snapshot.json, brief.md}` plus `index.json`. The script prints one line per athlete (initials only). The session always ends in `rollback()`.

`brief.md` is the **only** input you read to write the narrative. It is anonymized (`su hijo` / `su hija`), redacts club names inside coach feedback, and is the grounding source: every number you write must appear verbatim in it. `snapshot.json` contains the real name — do not open it, do not quote it.

Beyond the product's own metrics, the brief includes what the in-app newsletter ignores: the coach's per-session feedback, Strava volume (when connected), real race calendar and roster status, race coach notes and course conditions, and the season progression for context.

## Step 2 — Narrative (you)

For each athlete, read `brief.md` and write `narrative.json` in the same folder following `references/narrativa.md` (method, rules, JSON schema, worked example). Key constraints, enforced by the render step:

- No proper names anywhere; use the reference from the brief.
- Every number must exist in `brief.md`. Avoid dates as digits (write "a mediados de septiembre").
- Forbidden words: percentil, esperado, ranking, mejor que, por debajo, podio, ganar; no medical/nutritional terms; no comparisons with other athletes.
- Word caps: `stage_title` 20, `claim` 35, `evidence` 20, `summit_caption` 25, `next_segment_text` 40, each `family_compass` field 30 (question must end in `?`). Exactly 3 observations with `block_ref` in `attendance|technical|race|badges|streak`.
- The coach's feedback and race notes are to be **synthesized into patterns**, never quoted. Negative behavioural notes (attitude, conflicts) never reach the family text; list them in your final report for the coach instead.
- If the brief says the athlete has no AI consent, skip `narrative.json` (the render falls back to static copy) and say so.
- For 4+ athletes, fan out one `Agent` per athlete (sonnet is enough) with `references/narrativa.md` and the athlete's `brief.md` path as the whole prompt; each agent writes its own `narrative.json` and returns the JSON plus any sensitive notes it withheld.

## Step 3 — Render and verify

```bash
python scripts/bitacora_render.py --dir ../output/bitacora/2026-08/athlete-6
python scripts/bitacora_render.py --dir ... --check                      # guardrails only
python scripts/bitacora_render.py --dir ... --coach-note "…"             # optional, first person, ≤ 60 words
python scripts/bitacora_render.py --dir ... --hide photos,badges         # optional
```

Exit code 2 means a block failed guardrails and fell back to static copy; read `violations.json`, fix `narrative.json`, re-run. Then open `bitacora.pdf` with the Read tool and check: title fits in two lines, three observations, "Próximo tramo" names the real next race, no placeholder text, ≤ 3 pages.

## Final report to the coach

One line per athlete (`athlete-<id>` + initials, never full names): PDF path, blocks that stayed static, and withheld sensitive notes the coach may want to raise in person. Remind that `output/` is gitignored and must never be committed or shared as a folder.
