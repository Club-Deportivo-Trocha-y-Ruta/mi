# Contract — AI explainer extension: `body_composition` leaf (feature 046)

Extends the feature-042 anthropometry pipeline (`context → analyst → prechecks → critic → guardrails → persist`). Nothing numeric about body composition ever reaches the provider or a family text.

## 1. Context leaf (`AnalysisContext.body_composition: dict | None`)

Built by `context.py::_build_body_composition_dict(latest_record, previous_record, reading)`; `None` when the latest record has no skinfold set with data. Keys (all qualitative, all added to `ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS`):

| Key | Values |
|---|---|
| `sets_count` | int (capped at 9) |
| `weeks_since_prev_set` | int or null |
| `sum_change_code` | `none` \| `within_noise` \| `up_real` \| `down_real` |
| `growth_explanation_code` | `expected_pubertal_gain` \| `pre_spurt_accumulation` \| `post_phv_lean_gain` \| `none` |
| `ffm_trend_code` | `up` \| `flat` \| `down` \| `unavailable` |
| `band` | `verde` \| `ambar` \| `rojo` |
| `band_reason_code` | as in `body-composition-reading.md` §3 |
| `reference_context_code` | `low` \| `normal` \| `high` \| `unavailable` (worst of triceps/subscapular, extremes collapsed into low/high) |
| `sites_declined_count` | int 0–6 |

Forbidden in the leaf (tested): any `*_mm`, `*_pct`, `*_kg`, percentile numbers, readings, names.

## 2. Prompt rendering

`_render_body_composition_block(leaf)` produces a Spanish block "Composición corporal (códigos cualitativos)" listing the codes with one-line meanings; appended to `context_blocks` only when the leaf exists. Prompts `anthropometry_analyst_v2.md` and `anthropometry_critic_v2.md` add:

- an optional section instructing the analyst to weave body composition into `changes`/`meaning` (family: reassurance-first, process language; coach: pattern + suggested conversation), **never** stating a percentage, a millimetre value, a weight goal or diet advice;
- the critic rule list gains R13 and R14 descriptions.

`AI_ANTHRO_PROMPT_VERSION` default `v2`; `v1` remains valid for rollback (prompt version is persisted per explanation row).

## 3. Prechecks (must_block)

| Rule | Audience | Pattern |
|---|---|---|
| R13 `body_comp_numeric_leak_to_family` | family | `\d+(?:[.,]\d+)?\s*%` or `\d+(?:[.,]\d+)?\s*mm` anywhere in the joined family text |
| R14 `diet_or_weight_loss_language` | family and coach | lexicon (case/diacritic-insensitive): `dieta`, `bajar de peso`, `perder peso`, `adelgazar`, `calor[ií]as`, `d[ée]ficit cal[oó]rico`, `quemar grasa`, `restricci[oó]n`, `porcentaje de grasa` followed by a number |

Both feed the critic feedback loop like R01–R12 and count toward the fallback decision.

## 4. Fallback

`fallback.build_fallback_insight` adds one sentence per audience when the leaf exists, from `band_reason_code` (family: the family sentence of the band; coach: the coach reason), never numbers.

## 5. Guardrails and persistence

Unchanged: forbidden-names scrub, word budgets (family 180, coach 110), `critic_verdict` gating (`approved|revised` only reach families). `structured_json` keeps the `AnthropometryInsightV1` shape (no new fields).

## 6. Golden evaluation

Add `backend/evals/anthropometry_analyst/golden/case_013…case_016.json` with a `body_composition` input leaf: (13) family, verde `expected_pubertal_gain`; (14) coach, rojo `energy_availability_pattern` (expected theme: conversation + referral, forbidden: numbers, "dieta"); (15) family, ámbar `sum_up_unexplained` (forbidden: any `%`/`mm`); (16) coach, `first_set` with `sites_declined_count = 2` (theme: second set needed, respect the decline). Extend every existing case's `forbidden_terms` with `%` patterns where audience is family. Refresh `baseline.json` after the prompt change (requires an AI key; `pytest -m golden` composite ≥ 0.75 remains the gate).

## 7. Tests

- `tests/anthro/test_context_body_composition.py`: leaf presence/absence, key allow-list, no numeric keys, renderer output.
- `tests/anthro/test_prechecks_r13_r14.py`: positive/negative texts for both rules, both audiences.
- `tests/anthro/test_privacy_seam.py` property #5: for adversarial synthetic sets, the rendered family prompt and any fake-provider request contain no `mm`/`%` numbers and no name.
- Fake-provider assertions: `fake.last_request` never contains `_mm`, `_pct`, `_kg` keys.
