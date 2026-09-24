# Anthropometry analyst — golden evaluation

Golden dataset and baseline for the anthropometry explainer pipeline
(`app/services/ai/anthro/`: context → analyst → prechecks → critic →
fallback). The runner is `backend/tests/evals/test_anthropometry_analyst_eval.py`;
the scorer and LLM judge live in `app/services/ai/anthro/eval/`.

## Layout

| Path | Content |
|---|---|
| `golden/case_001.json` … `case_012.json` | Feature 042 cases: growth, velocity calibration, phase crossings, audiences |
| `golden/case_013.json` … `case_018.json` | Feature 046 cases: optional `input.body_composition` qualitative leaf (`specs/046-body-composition-skinfolds/contracts/ai-body-composition-leaf.md` §6) |
| `baseline.json` | Last real run (composite threshold 0.75, the blocking gate) |
| `results/last_run.md` | Scoreboard written by the last golden run |

Every case is synthetic — no real name, birth date or identifying detail of
a minor (Ley 1581). `test_case_dataset_contains_no_real_athlete_data` enforces
it offline.

## Body-composition cases (feature 046)

| Case | Audience | Leaf | What it checks |
|---|---|---|---|
| 013 | family | verde, `expected_pubertal_gain` | reassurance-first, growth/process language |
| 014 | coach | rojo, `energy_availability_pattern` | pattern + conversation + referral, never a diagnosis, no diet |
| 015 | family | ámbar, `sum_up_unexplained` | "en observación", coach follows up, no `%`/`mm` |
| 016 | coach | `first_set`, `sites_declined_count = 2` | second set needed, decline respected |
| 017 | family | coach-side rojo → `family_band = ambar` | no "profesional de la salud" / "remisión" / "requiere acompañamiento" |
| 018 | family | reference-only ámbar → `family_band = verde` | no "observación" / "extremo" / "percentil" |

The leaf carries only the ten qualitative keys of the contract (§1) — never a
`*_mm`, `*_pct` or `*_kg` value. Every family case (old and new) lists `%` and
`mm` in `forbidden_terms` (plain case-insensitive substrings, as the scorer
matches them).

## Commands

Offline sanity checks (loader, schema, scenario coverage, privacy) — always
safe, no model calls:

```bash
cd backend
PYTHONPATH=. python -m pytest tests/evals/test_anthropometry_analyst_eval.py -m "not golden" -q
```

Real golden run (spends provider tokens; needs `AI_API_KEY`):

```bash
cd backend
PYTHONPATH=. python -m pytest tests/evals/test_anthropometry_analyst_eval.py -m golden -k anthropometry -v
```

Caution: the runner has no default marker exclusion. Running the file
**without** `-m "not golden"` in a session where an AI key is configured
runs the real golden cases.

## Refreshing `baseline.json`

`baseline.json` must be refreshed with `pytest -m golden` (command above) in a
session that has an AI key whenever the prompt pair or the dataset changes.
Feature 046 changed both (`AI_ANTHRO_PROMPT_VERSION` default `v2`: prompts
`anthropometry_analyst_v2.md` / `anthropometry_critic_v2.md`, and cases
013–018); `baseline.json` was refreshed for it on 2026-09-24 (T068, v2
prompts, 18 cases, `gemini-3.1-flash-lite`, composite 0.786). Update `prompt_version`, `critic_prompt_version`,
`date`, the averages and `per_case` from the run; composite ≥ 0.75 remains the
gate. If no key is available, record the deferral explicitly (feature 046:
`docs/21-body-composition/qa.md`) instead of editing the numbers by hand.
