# Phase 1 Data Model: Competitive Anxiety Assessment

New tables prefixed `anxiety_`. Reuses `athletes`, `race_events`, `users`, `parental_consents`. One Alembic migration. All enums use `values_callable` (store values, not names), per project convention.

## Reused tables

- **athletes**: source of identity + `date_of_birth` → age band (10–12 / 13–15). No schema change.
- **race_events**: event linkage + A/B/C priority. FK target. No schema change.
- **parental_consents**: consent gate. **Change**: add `psychological_assessment: bool` (default false) consent scope (Alembic). Assessment blocked unless athlete has an active (not withdrawn) consent with this flag true.

## `anxiety_instruments`

Definition + scoring key for an instrument version (seeded, not user-edited).

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| type | enum(`csai2`,`csai2r`,`sas2`) | `values_callable` |
| version | str(20) | e.g., `es-andrade-2007` |
| age_band | enum(`10-12`,`13-15`,`import`) | default selection target |
| item_count | smallint | 27 / 17 / 15 |
| scoring_key_json | JSON | per-item → subscale + reverse flag; subscale ranges; loaded from `data/anxiety_keys/` |
| is_active | bool | enable/disable |

**Rules**: exactly one active default per age band; `scoring_key_json` is the single source for scoring (FR-004). Item *text* is provisioned via the licensed source, referenced by key — not invented.

## `anxiety_assessments`

One administration to one athlete.

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| athlete_id | FK athletes ON DELETE CASCADE | |
| instrument_id | FK anxiety_instruments | resolved at create |
| event_id | FK race_events ON DELETE SET NULL, nullable | calendar link |
| priority | enum(`A`,`B`,`C`), nullable | copied from event for history |
| scheduled_at | datetime | intended ~1–2 h pre-race for A |
| status | enum(`pending`,`partial`,`completed`) | `values_callable` |
| answers_json | JSON | item-by-item answers (FR-010); always stored |
| score_cognitive | float, nullable | computed |
| score_somatic | float, nullable | computed |
| score_selfconfidence | float, nullable | nullable (N/A for SAS-2) |
| is_partial | bool default false | averaged over answered |
| instrument_override | bool default false | age-inappropriate override used |
| override_ack_at | datetime, nullable | coach acknowledged warning |
| interpretation_json | JSON, nullable | cached on-demand result (fixed schema) |
| interpretation_source | enum(`llm`,`rule`), nullable | fallback traceability |
| interpretation_model | str(128), nullable | model + prompt_version |
| flags_json | JSON, nullable | alert flags (e.g., high-anx+low-conf) |
| created_by_user_id | FK users (coach) | RBAC owner |
| created_at / updated_at | datetime | |

**Indexes**: `(athlete_id, scheduled_at)`, `(event_id)`, `(status)`.
**State**: `pending` → (`completed` | `partial`) on submit → interpretation attached on coach "Analizar".

## `anxiety_response_tokens`

Single-use athlete access (no login).

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| assessment_id | FK anxiety_assessments ON DELETE CASCADE | one active token per assessment |
| token_hash | str(128) unique | store hash, not raw |
| expires_at | datetime | |
| consumed_at | datetime, nullable | set on submit (single-use) |
| created_at | datetime | |

**Rules**: token invalid if consumed or expired; submitting answers consumes it.

## `anxiety_baselines`

Per athlete + subscale baseline (April / first qualifying assessment).

| Field | Type | Notes |
|---|---|---|
| id | int PK | |
| athlete_id | FK athletes ON DELETE CASCADE | |
| subscale | enum(`cognitive`,`somatic`,`selfconfidence`) | |
| instrument_type | enum(`csai2`,`csai2r`,`sas2`) | baselines are per instrument family |
| value | float | baseline score |
| source_assessment_id | FK anxiety_assessments | which assessment set it |
| established_at | datetime | |

**Constraint**: unique `(athlete_id, subscale, instrument_type)`. First qualifying assessment seeds it; instrument change creates a new baseline family (non-comparable, FR-022).

## Interpretation JSON schema (cached in `interpretation_json`)

Matches the club runtime prompt contract (Spanish keys):

```json
{
  "resumen": "string",
  "por_dimension": { "cognitiva": "string", "somatica": "string", "autoconfianza": "string" },
  "estrategias": ["string", "string"],
  "mensaje_para_el_atleta": "string",
  "banderas": ["string"]
}
```

Same schema is produced by both the LLM use case and `rule_interpreter.py` (FR-016).
