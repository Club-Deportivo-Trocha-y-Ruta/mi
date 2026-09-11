# Data model — Traceable AI growth analysis (042)

Only the deltas, in the style of `specs/041-multi-coach-governance/data-model.md`. Existing
entities are referenced by their current names, verified in the code at planning time
(`path:line` citations throughout). Binding source: `plan.md` (Project Structure, Phase 1) and
the lead's ruling document (`LEAD-DECISIONS.md`, referenced below as **LD-#**).

**A naming collision to hold in mind while reading this file.** Two independent things are both
called "schema_version" in this feature, and they must never be confused:

| Which "schema_version" | Lives where | Values | Means |
|---|---|---|---|
| **Row-format discriminator** | `athlete_ai_explanations.schema_version` (DB column, new); `AnthropometricRecordExplanationResponse.schema_version` / `PHVExplanationResponse.schema_version` (API, new) | `NULL` (legacy DB rows) / API always renders as `"v1"` · `"v2"` | Is this cache row **free prose** (`"v1"`, the format `AthleteAIExplanation.text` has held since feature 033) or **structured** (`"v2"`, this feature)? |
| **Insight payload version** | `AnthropometryInsightV1.schema_version` (Pydantic field, inside `structured_json`) | `Literal["v1"]` only, today | Which version of the *structured insight JSON shape* is this? Bumped only when the analyst/critic JSON contract itself changes — independent of the row-format axis above. |

A `"v2"` DB row always carries a `structured_json` blob whose *own* internal `schema_version`
field currently reads `"v1"` (LD-7). This is correct and will stay true until the insight shape
itself gets a second revision. Contracts and code MUST label the two fields distinctly in
docstrings (`AthleteAIExplanation.schema_version` vs `AnthropometryInsightV1.schema_version`) —
never a bare `schema_version` in a comment without saying which.

---

## 1. Extended `AthleteAIExplanation` — `backend/app/models/ai_explanation.py:24`

**Already present** (do not re-add): `id`, `athlete_id`, `anthropometric_record_id`, `use_case`,
`text` (`:59`, `NOT NULL`), `model` (`:60`), `provider` (`:61`), `generated_at` (`:62`),
`age_group` (`:63`), `maturation_status` (`:64`), `generated_by_user_id` (`:69`), `created_at`
(`:72`), `updated_at` (`:75`), the unique constraint `(athlete_id, anthropometric_record_id,
use_case)` (`:36-41`).

Nine new nullable columns (LD-6), all additive, no `server_default`:

| Column | Type | Null | Default | Purpose |
|---|---|---|---|---|
| `schema_version` | `String(8)` | yes | `NULL` | Row-format discriminator, see the collision note above. `NULL` = legacy prose (renders as API `"v1"`); `"v2"` = structured, this feature. Never `"v1"` in the DB — a v1-shaped row is expressed as `NULL`, not the string, so a bare `IS NOT NULL` check is a one-column "is this a 042 row" test. |
| `structured_json` | `JSON` | yes | `NULL` | `AnthropometryInsightV1.model_dump(mode="json")`. `NULL` for `schema_version IS NULL` rows; always populated when `schema_version = "v2"`, including for `critic_verdict = "fallback"` rows (the deterministic template is itself a valid `AnthropometryInsightV1`, §3). |
| `critic_verdict` | `String(16)` | yes | `NULL` | One of `approved \| revised \| flagged \| fallback \| skipped` (LD-7). `NULL` for legacy rows. See §3 for the full state machine and the mapping from the critic LLM's own `approve\|revise\|reject` vocabulary onto this persisted set — they are not the same enum. |
| `prompt_version` | `String(32)` | yes | `NULL` | The `AI_ANTHRO_PROMPT_VERSION` value active when this row was generated (e.g. `"anthropometry_analyst_v1"`), so a later rollback of the setting does not retroactively relabel old rows. |
| `tokens_in` | `Integer` | yes | `NULL` | Summed across the analyst call and, when it ran, the critic call. |
| `tokens_out` | `Integer` | yes | `NULL` | Idem. |
| `cost_usd` | `Numeric(10, 6)` | yes | `NULL` | Six decimals matches `compute_cost_usd` rounding (`backend/app/services/race/agents/pricing.py:89`, moved to `app/services/llm/pricing.py` per `contracts/llm-transport.md`). Summed across analyst + critic. |
| `latency_ms` | `Integer` | yes | `NULL` | Wall-clock time of the whole pipeline run (context build through persist), not just the LLM calls — matches what the frontend's escalating pending-message thresholds care about. |
| `langfuse_trace_id` | `String(64)` | yes | `NULL` | The deterministic trace id from `contracts/trace-metadata-allowlist.md` §4. `NULL` whenever `LANGFUSE_ENABLED=false` (always true in production, LD-9) — this is by construction, mirroring `agent_runs.langfuse_trace_id` where it exists today, not a bug to fix. |

No new index: nothing queries on these nine columns (LD-6, mirroring `specs/041` §6.4's identical
call for its own additive columns). The existing `on_duplicate_key_update` lists at
`backend/app/routers/ai.py:562-570` and `:736-744` each grow by nine entries.

`text` stays `NOT NULL` and is **always** populated, including for `schema_version = "v2"` rows,
by rendering `AnthropometryInsightV1` to plain prose — the same move `insight_v3.py` makes with
`_action_bullet`/`_field_reading_line` (`backend/app/services/race/insight_v3.py:280-356`). This
is what makes every existing reader of `AthleteAIExplanation.text` (email templates, PDF
generation, any code that has not been touched by this feature) keep working unchanged, and what
makes v1 rows renderable forever without a backfill (invariant, §6).

---

## 2. Value objects

### 2.1 `AnthropometryInsightV1` — `backend/app/services/ai/anthro/schemas.py` (new, per `plan.md`)

The LLM-facing structured insight. Verbatim from LD-7 / `analysis-design.md` §4:

```python
class ConfidenceLevel(str, Enum):
    HIGH = "high"; MEDIUM = "medium"; LOW = "low"

class Confidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: ConfidenceLevel
    reason: str = Field(..., min_length=3, max_length=200)

class AnthropometryInsightV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["v1"] = "v1"          # insight-payload version, see §0 collision note
    audience: Literal["family", "coach"]
    summary_line: str = Field(..., min_length=3, max_length=140)
    changes: list[str] = Field(..., min_length=1, max_length=4)
    meaning: list[str] = Field(..., min_length=1, max_length=4)
    next_weeks: list[str] = Field(..., min_length=1, max_length=3)
    warning_signs: list[str] = Field(default_factory=list, max_length=2)
    confidence: Confidence
    data_gaps: list[str] = Field(default_factory=list, max_length=3)
    word_count: int = Field(..., ge=0)   # telemetry only — the system recomputes the real count
```

`extra="forbid"` everywhere, matching the race stack's `InsightV3` (`insight_v3.py:63`) — turns a
hallucinated extra key into a `ValidationError`, never a silent pass-through.

### 2.2 `AnalysisContext` — `backend/app/services/ai/anthro/context.py`

The deterministic, allow-listed input the analyst prompt renders from. Full key list, types and
privacy rationale are `contracts/analysis-context.md` in full; not restated here beyond the
top-level shape:

```python
@dataclass(frozen=True)
class AnalysisContext:
    identity: dict            # age_decimal, age_group, sex, category, audience
    measurement_deltas: dict | None     # None on the first-ever measurement
    longitudinal_series: list[dict]     # possibly empty; compacted per HISTORY_MAX_POINTS
    growth_summary: dict                # qualitative codes only, never raw bands
    training_load_window: dict | None   # None when no sessions in the last 28 days
    previous_analysis: dict | None      # None when no prior schema_version="v2" row exists
```

Rendered into the Jinja prompt as the six blocks the template (`contracts/prompts/
anthropometry_analyst_v1.md`) expects — `measurement_deltas_block`, `longitudinal_series_block`,
`growth_summary_block`, `training_load_block`, `previous_analysis_block` are pre-formatted text,
never the raw dict, so the allow-list boundary and the prompt-rendering boundary are the same
function call and cannot drift apart.

### 2.3 `PrecheckResult` — `backend/app/services/ai/anthro/prechecks.py`

```python
@dataclass(frozen=True)
class PrecheckViolation:
    rule_id: str                 # "R01".."R12"
    category: Literal["privacy", "ltad", "grounding", "style"]
    must_block: bool
    detail: str                  # short, never echoes the offending text verbatim into logs

@dataclass(frozen=True)
class PrecheckResult:
    violations: tuple[PrecheckViolation, ...]
    must_block: bool             # True iff any violation has must_block=True
```

Rule catalogue (R01–R12, category and blocking behaviour) is `contracts/golden-eval-case.md` §3 —
restated there because the golden eval scores against the same catalogue, not duplicated here.

### 2.4 `CriticVerdict` (raw LLM output) vs persisted `critic_verdict` (DB/API enum)

Two more colliding names, deliberately kept apart:

```python
# The critic LLM's own vocabulary — app/services/ai/anthro/schemas.py
class AnthropometryCriticIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str
    section: str
    problem: str = Field(..., min_length=3, max_length=200)
    suggested_fix: str = Field(..., min_length=3, max_length=200)

class AnthropometryCriticVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["approve", "revise", "reject"]
    violations: list[AnthropometryCriticIssue] = Field(default_factory=list)
    revised_output: AnthropometryInsightV1 | None = None
```

`AnthropometryCriticVerdict.verdict` (`approve|revise|reject`) is what the critic prompt
(`contracts/prompts/anthropometry_critic_v1.md`) returns per call. It is **not** what gets
persisted. The pipeline (`app/services/ai/anthro/pipeline.py`) folds this raw verdict, the
precheck result and the retry outcome into the five-value **persisted** `critic_verdict` column —
see the state machine in §3.

---

## 3. Generation state machine

A single generation (one POST to either analysis endpoint) moves through these states before a
row is written. States in **bold** are the five values `AthleteAIExplanation.critic_verdict` may
hold; the others are transient, in-process only.

```text
draft ──► prechecked ──► reviewed ──► ┬─► APPROVED
                                      ├─► REVISED
                                      ├─► FLAGGED
                                      ├─► FALLBACK
                                      └─► SKIPPED
```

| Transient state | What happened | Next step |
|---|---|---|
| `draft` | Analyst call (`AI_ANALYST_MODEL`) returned parseable `AnthropometryInsightV1` JSON. | → `prechecked` |
| `draft` (failure) | Analyst call errored, timed out, or returned unparseable JSON twice (one retry with the validation error appended, FR-009/analysis-design §5.1). | → **`FALLBACK`** directly, critic never invoked. |
| `prechecked` | `PrecheckResult` computed (§2.3) against the draft and `AnalysisContext`. | If `must_block` → **`FALLBACK`** directly (FR-014: "if a blocking issue was found, the fallback must be delivered regardless of the review" — the critic call is skipped to avoid spending a call whose verdict cannot change the outcome). Else → `reviewed`. |
| `reviewed` | Critic call (`AI_CRITIC_MODEL`) attempted, fed `precheck_summary`. | See the verdict table below. |

Critic-call outcome → persisted `critic_verdict` (only reached when the precheck found no
`must_block`):

| Critic outcome | Persisted `critic_verdict` | Family-deliverable? | What `structured_json` holds |
|---|---|---|---|
| Critic call failed, timed out, or returned unparseable JSON (FR-014). | **`SKIPPED`** | No | The analyst's original draft, unrevised. `confidence.level` forced to `"low"`; `confidence.reason` amended with "revisión no disponible" (or equivalent, guardrail-scrubbed). `critic_skipped=true` recorded in the trace tags only, never in the persisted row (redundant with `critic_verdict`). |
| `verdict="approve"`, no precheck confidence-only violations (R03/R05/R07/R08/R10). | **`APPROVED`** | Yes | The analyst's draft, unmodified. |
| `verdict="approve"`, but one or more confidence-only precheck violations fired (non-blocking). | **`APPROVED`** | Yes | The analyst's draft; `confidence.level` deterministically forced to `"low"` regardless of what the analyst reported (mirrors race's `state.py:99` post-critic confidence override, per `architecture.md` §4.2). |
| `verdict="revise"`, every violation is mechanical (R04/R06/R07/R09/R10/R12 — see `analysis-design.md` §3.3 step 5) and the critic supplied a schema-valid `revised_output`. | **`REVISED`** | Yes | `revised_output`, adopted directly. No second analyst call. |
| `verdict="revise"` with any interpretive violation (R01/R02/R03/R05/R08/R11/CTX01/CTX02), analyst re-invoked once with the violations appended, and the second attempt's own precheck+critic pass now lands on `approve` or a mechanical `revise`. | **`REVISED`** | Yes | The second attempt's (possibly critic-revised) draft. |
| `verdict="revise"` with an interpretive violation, analyst re-invoked once, and the second attempt still does not reach `approve`/mechanical-`revise` (FR-013: "at most one revision"). | **`FLAGGED`** | **No** | The second attempt's own draft (not the fallback template) — the coach sees real, if imperfect, content marked "Con observaciones" (FR-016, `ui-design-analysis-summary.md` §3). |
| `verdict="reject"`. | **`FLAGGED`** | **No** | The last draft produced (first attempt; `reject` does not trigger a second analyst call — FR-013's "at most one revision" is spent on `revise`, not `reject`). |

Deterministic-fallback path, reached from either `draft` (analyst failure) or `prechecked`
(`must_block`):

| Reached from | Persisted `critic_verdict` | `structured_json` |
|---|---|---|
| Analyst failed twice, or precheck `must_block` fired. | **`FALLBACK`** | The deterministic per-audience template (analysis-design §5.3), itself a valid `AnthropometryInsightV1` with `confidence.level="low"`, `data_gaps=["análisis automático no disponible para esta medición"]`. Never a hand-written string outside the schema — this is what lets the frontend's v2 renderer handle a fallback row with zero special-casing. |

**Family delivery gate (FR-016, LD-7).** The family-facing surfaces (both parent AI cards, the
family variant of the growth-tab summary line) treat `critic_verdict ∈ {APPROVED, REVISED}` as
the only deliverable set. `FLAGGED`, `FALLBACK` and `SKIPPED` are rendered **identically** to "no
analysis yet" on every family surface — the shared passive message from
`ui-design-analysis-summary.md` §2/§3 (D-1, accepted: gate rather than caveat). The coach surface
shows all five states, with `FLAGGED` and `FALLBACK` labelled distinctly ("Con observaciones" vs
the fallback copy) so the coach can tell "the model said something questionable" from "the model
didn't run at all."

---

## 4. Staleness rule (LD-10, feeds `contracts/growth-summary-latest-analysis.md`)

```text
is_stale ⟺  EXISTS (a newer AnthropometricRecord for this athlete than the analysed record_id)
          OR  AnthropometricRecord.updated_at > AthleteAIExplanation.generated_at
```

Computed server-side, inside the same query the growth summary already runs
(`backend/app/services/growth_summary.py`, called from `backend/app/routers/growth.py:129`) —
never re-derived client-side (the exact class of bug `docs/18-growth-module-redesign/
proposal.md` G-02 already documented once for this module, per `ui-design-analysis-summary.md`
§0). A corrected measurement (edited `evaluation_date`/values on the *same* `record_id`) is
covered by the second disjunct without needing a new column: `anthropometric_records.updated_at`
already exists (`backend/app/models/anthropometry.py`, confirmed via `context_builders.py`
imports) and is bumped by the existing edit path.

---

## 5. Alembic revision sketch

```python
"""ai_explanations traceability — feature 042

Revision ID: <generated>
Revises: 45cd705c6b54
"""

revision: str = "<generated>"
down_revision: str | None = "45cd705c6b54"   # verified single head, backend/alembic/versions/
                                              # 45cd705c6b54_multi_coach_governance.py:80
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("athlete_ai_explanations") as batch_op:
        batch_op.add_column(sa.Column("schema_version", sa.String(8), nullable=True))
        batch_op.add_column(sa.Column("structured_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("critic_verdict", sa.String(16), nullable=True))
        batch_op.add_column(sa.Column("prompt_version", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("tokens_in", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("tokens_out", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True))
        batch_op.add_column(sa.Column("latency_ms", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("langfuse_trace_id", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("athlete_ai_explanations") as batch_op:
        batch_op.drop_column("langfuse_trace_id")
        batch_op.drop_column("latency_ms")
        batch_op.drop_column("cost_usd")
        batch_op.drop_column("tokens_out")
        batch_op.drop_column("tokens_in")
        batch_op.drop_column("prompt_version")
        batch_op.drop_column("critic_verdict")
        batch_op.drop_column("structured_json")
        batch_op.drop_column("schema_version")
```

`batch_alter_table` (not a bare `op.add_column`) for parity with the SQLite offline test lane —
`aiosqlite` cannot always `ALTER TABLE … ADD COLUMN` outside a batch context when a table has
named constraints, and every existing migration in this area already uses the batch form
(`specs/041-multi-coach-governance/data-model.md` §6.4 documents the same reasoning). All nine
columns are nullable with no `server_default`, so this is INSTANT DDL on MySQL 8.0+ — no backfill,
no table rewrite, no downtime coordination beyond the standard "coordinate before running prod
DDL" note.

CLAUDE.md's Alembic-head line is corrected in the same feature (W4, `docs` wave) from the stale
`2a8baa967cc6` to `45cd705c6b54` and then to this revision's id once generated (LD-13).

---

## 6. Invariants

1. **`text` is `NOT NULL` on every row, always populated, including `schema_version="v2"` and
   `critic_verdict="fallback"` rows.** This is what lets every pre-existing reader of
   `AthleteAIExplanation.text` — email templates, PDF generation, the family cards before their
   W2 update ships — keep functioning with zero code changes during the rollout window.
2. **Family delivery is `critic_verdict ∈ {APPROVED, REVISED}` and nothing else, full stop.**
   Not "flagged with a caveat", not "fallback text is still better than nothing" — §3's table is
   exhaustive; any future state added to the enum must default to *not* family-deliverable until
   explicitly reviewed (mirrors the audit-log allow-list's "unlisted = excluded" posture from
   `specs/041-multi-coach-governance/data-model.md` §2.5).
3. **Legacy rows (`schema_version IS NULL`) never get `structured_json`, `critic_verdict` or any
   of the seven telemetry columns backfilled.** They render exactly as before this feature (FR-
   026, Edge Case spec.md:129) through the unchanged prose path. No migration script ever writes
   to a pre-042 row.
4. **`AnthropometryInsightV1.schema_version` and `AthleteAIExplanation.schema_version` are never
   compared to each other, assigned from one another, or documented without naming which one is
   meant** (§0). A code review or `data-privacy-guard` pass that finds a bare `schema_version ==
   "v1"` check without a qualifying comment in `app/services/ai/anthro/**` or `app/routers/ai.py`
   should treat it as a defect.
5. **The nine new columns are read-only outside `app/services/ai/anthro/persist.py`.** No other
   module writes them — mirrors `specs/041`'s append-only discipline for `audit_log`, scoped here
   to "one writer function" rather than "no writer at all" because this table is a cache, not a
   ledger.
