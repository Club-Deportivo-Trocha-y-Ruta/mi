# Phase 1 Data Model: AI Session Clarify & Draft

**No database changes.** All entities are transient request/response Pydantic schemas in
`backend/app/schemas/session_assistant.py` (and mirrored TS types). Nothing is persisted;
the only DB reads are existing `athletes.birth_date` / `athletes.sex` to compute aggregate
age-mix counts.

## Enums

### `AthleteCallUpCriterion` (str enum)
Non-identifying athlete proposal. Resolved to ids by the frontend.

| Value | Meaning |
|---|---|
| `todos_convocados` | All athletes the coach has already selected / all club athletes in roster |
| `grupo_10_12` | Only the 10–12 age group |
| `grupo_13_15` | Only the 13–15 age group |
| `ninguno` | No proposal; coach selects manually |

`SessionKind` and `SessionStatus` are reused from `app.models.training_session` (no change).

## Request schemas

### `SessionClarifyRequest`
| Field | Type | Rules |
|---|---|---|
| `intent_text` | `str \| None` | optional; `max_length=500`; coach free-text, any language |
| `selected_athlete_ids` | `list[int]` | default `[]`; used only to compute aggregate age-mix; never echoed to AI as ids/names |

### `SessionAnswer`
One answer to one returned question.
| Field | Type | Rules |
|---|---|---|
| `question_id` | `str` | matches a returned question's `id` |
| `selected_labels` | `list[str]` | option labels chosen (0..n); single-select → ≤1 |
| `other_text` | `str \| None` | `max_length=300`; free-text when "Otro" chosen; empty → treated as unanswered |

### `SessionDraftRequest`
| Field | Type | Rules |
|---|---|---|
| `intent_text` | `str \| None` | same as clarify; `max_length=500` |
| `selected_athlete_ids` | `list[int]` | default `[]`; aggregate-only |
| `answers` | `list[SessionAnswer]` | default `[]`; may be partial/empty (FR-015) |

## Response schemas

### `ClarifyOption`
| Field | Type | Rules |
|---|---|---|
| `label` | `str` | `1..40` chars; español; guardrail-scrubbed |
| `description` | `str` | `1..120` chars; español; guardrail-scrubbed |

### `ClarifyQuestion`
| Field | Type | Rules |
|---|---|---|
| `id` | `str` | stable id for answer mapping (e.g., `q1`) |
| `header` | `str` | `1..12` chars chip label (mirrors AskUserQuestion) |
| `question` | `str` | `1..160` chars; español; scrubbed |
| `multi_select` | `bool` | single vs multiple |
| `allow_other` | `bool` | render free-text "Otro" |
| `options` | `list[ClarifyOption]` | **2–4** items |

### `SessionClarifyResponse`
| Field | Type | Rules |
|---|---|---|
| `questions` | `list[ClarifyQuestion]` | **0–4** items (0 ⇒ go straight to draft) |
| `model` | `str` | echo of model id (no PII) |

### `SessionDraftResponse`
Maps 1:1 onto wizard fields; every field editable downstream.
| Field | Type | Rules / source |
|---|---|---|
| `technical_focus` | `str` | `1..200`; scrubbed |
| `objectives` | `str \| None` | `≤1000`; scrubbed |
| `description` | `str \| None` | `≤2000`; structured warm-up / main / cool-down; scrubbed |
| `duration_min` | `int` | `15..240` |
| `session_kind` | `SessionKind` | valid enum; default `entrenamiento` |
| `location` | `str \| None` | `≤200`; only if inferable from intent |
| `scheduled_date` | `date \| None` | only if stated in intent |
| `scheduled_start_time` | `time \| None` | only if stated in intent |
| `athlete_call_up` | `AthleteCallUpCriterion` | criterion only — no ids/names |
| `notes` | `str \| None` | optional rationale shown to coach; scrubbed |
| `model` | `str` | echo of model id |

> The frontend converts `SessionDraftResponse` → `TrainingSessionFormValues`:
> resolves `athlete_call_up` → `convocados_athlete_ids` from the local roster, maps the
> rest field-for-field, then `reset(values, { keepDirtyValues: true })`.

## Validation & invariants

- **Counts**: `0 ≤ len(questions) ≤ 4`; `2 ≤ len(options) ≤ 4`. Violations → `LLMSchemaError`.
- **Privacy**: no field in any request *sent to the model* contains athlete ids or names —
  `selected_athlete_ids` is consumed server-side to produce counts and discarded before
  prompt render. Guardrail name-redaction runs on all output strings as defense-in-depth.
- **Principle compliance**: scrubbed text must not contain prohibited content (supplements,
  cadence <60, power-meter <13, calorie counting). Enforced by `Guardrails` + tests.
- **Determinism for tests**: with `FakeLLMProvider`, the use case returns a canned JSON
  fixture so schema/guardrail/validation paths are exercised without a live model.

## Aggregate context object (internal, not exposed)
Built by `session_assistant_context.py`, passed to the prompt — **never returned to client**:
`age_mix: dict[str,int]`, `total_athletes: int`, `season_phase: str`,
`days_to_next_race: int | None`, `next_race_priority: str | None`, `today: date`.
