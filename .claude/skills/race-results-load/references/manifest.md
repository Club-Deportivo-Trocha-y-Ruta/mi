# Writing a manifest

Full contract: `specs/044-race-history-backfill/contracts/results-skill-cli.md` § Manifest. The manifest is a JSON file **outside this repository**, next to (or wherever the operator keeps) the official results file — `mask` and `stage` never write it for you, and the skill never infers its content from anything it read in `masked/` or `report.json` (FR-025: nothing in the manifest is inferred from the file).

It takes exactly one of two forms. Unknown keys are refused — do not add a field "just in case".

## Form 1 — explicit (new event)

Use this the first time a válida is loaded, when no calendar event exists for it yet.

```json
{
  "series_name": "<placeholder — e.g. Copa Valle>",
  "series_kind": "<placeholder — \"cup\" or \"championship\">",
  "series_level": "<placeholder — \"departmental\" or \"national\">",
  "season": 0000,
  "valida_num": 0,
  "event_name": "<placeholder — e.g. Válida III>",
  "event_date": "0000-00-00",
  "location": "<placeholder>"
}
```

- `season`: integer year.
- `valida_num`: integer, the válida number within the series/season.
- `event_date`: ISO date (`YYYY-MM-DD`).
- `series_kind`: exactly `"cup"` or `"championship"`. `series_level`: exactly `"departmental"` or `"national"`. These are the same two enums used across the platform's race schemas (e.g. `app/schemas/athlete_race_analysis.py`) — do not invent a third value.
- Every other field is a plain string the operator gives you; you never fill it in from the masked view.

## Form 2 — existing event

Use this when the coach has already created the calendar event for this válida in the app (feature 015's prefill, now replaced by this form).

```json
{"race_event_id": 42}
```

Series, kind, level, season, válida, date and venue are then read from that event and its series in the **target** database — local or production, matching whatever `--target` you pass to `stage`. Get the id from the operator (they created the event in the app) — never guess it or list events yourself to find one; if you are unsure which event, ask.

## Rules that apply to both forms

- Unknown keys are refused by `stage` — copy one of the two shapes above exactly, do not merge fields from both.
- Race conditions (weather, surface, altitude) are **never** in the manifest — the coach enters them on the válida's *Condiciones* tab in the app after the import is reviewed (R-31). Do not ask the operator for them here, and do not accept them if offered.
- The manifest never contains a rider's name, club, city, bib or time — there is no field for any of that in either form, and none should be added.
- Write the manifest to a path outside the repository, the same folder discipline as the official file itself (rule 5) — never under `backend/` or anywhere `git status` would see it.

## Placeholder discipline

Everything in the JSON blocks above marked `<placeholder — …>` or `0000`/`0` is exactly that — a placeholder to replace with what the operator tells you for *this* válida, never a real value carried over from a previous run or guessed from the masked view. If the operator does not know a value (e.g. the exact `event_date`), ask; do not leave it out (unknown keys are refused, but so is a missing required key) and do not invent one.
