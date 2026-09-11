# Contract — `AnthropometryInsightV1` schema (Pydantic + Zod), word budgets, prose rendering

**Backend module**: `backend/app/services/ai/anthro/schemas.py` (new).
**Frontend module**: `frontend/src/schemas/ai.schemas.ts` (extended — a discriminated union).
**Related contracts**: `analysis-context.md` (the input), `measurement-analysis-api.md` (the
transport), `data-model.md` §2 (how these types map onto the persisted row), `trace-metadata-
allowlist.md` (what of this schema, if anything, may appear in a trace — answer: nothing; see
that contract §1).

Read `data-model.md` §0 before this file: **`AnthropometryInsightV1.schema_version` is a
different axis from `AthleteAIExplanation.schema_version`.** Every occurrence of the word
"schema_version" below refers to the *insight-payload* version unless explicitly qualified as
"the row-format discriminator".

---

## 1. Pydantic models (verbatim, lead ruling 7 / `analysis-design.md` §4)

```python
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Confidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: ConfidenceLevel
    reason: str = Field(..., min_length=3, max_length=200)


class AnthropometryInsightV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["v1"] = "v1"
    audience: Literal["family", "coach"]
    summary_line: str = Field(..., min_length=3, max_length=140)
    changes: list[str] = Field(..., min_length=1, max_length=4)
    meaning: list[str] = Field(..., min_length=1, max_length=4)
    next_weeks: list[str] = Field(..., min_length=1, max_length=3)
    warning_signs: list[str] = Field(default_factory=list, max_length=2)
    confidence: Confidence
    data_gaps: list[str] = Field(default_factory=list, max_length=3)
    word_count: int = Field(..., ge=0)   # telemetry only, never used to enforce the budget


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
    revised_output: Optional[AnthropometryInsightV1] = None
```

`extra="forbid"` on every model — a hallucinated extra key (the model inventing a field the
schema does not declare) is a `ValidationError`, not a silent pass-through. Matches the race
stack's `InsightV3` convention (`backend/app/services/race/insight_v3.py:63`).

**`AnthropometryCriticVerdict.verdict` is not what gets persisted.** The pipeline folds this raw
three-value critic vocabulary, the precheck result and the (at most one) retry outcome into the
five-value persisted `critic_verdict` column (`approved | revised | flagged | fallback |
skipped`) — the full mapping is `data-model.md` §3, not restated here.

## 2. Zod mirror (frontend)

`frontend/src/schemas/ai.schemas.ts` extends the existing file (which today ends every object
schema in `.strip()`, per `ai.schemas.ts:23,31,40,58`). The new schemas follow the same
convention:

```typescript
import { z } from "zod";

export const confidenceLevelSchema = z.enum(["high", "medium", "low"]);

export const confidenceSchema = z
  .object({
    level: confidenceLevelSchema,
    reason: z.string().min(3).max(200),
  })
  .strip();

export const anthropometryInsightV1Schema = z
  .object({
    schema_version: z.literal("v1"),
    audience: z.enum(["family", "coach"]),
    summary_line: z.string().min(3).max(140),
    changes: z.array(z.string()).min(1).max(4),
    meaning: z.array(z.string()).min(1).max(4),
    next_weeks: z.array(z.string()).min(1).max(3),
    warning_signs: z.array(z.string()).max(2),
    confidence: confidenceSchema,
    data_gaps: z.array(z.string()).max(3),
    word_count: z.number().int().nonnegative(),
  })
  .strip();

export const criticVerdictSchema = z.enum([
  "approved",
  "revised",
  "flagged",
  "fallback",
  "skipped",
]);
```

`criticVerdictSchema` is the **row-format** verdict (five values, `data-model.md` §3) — a
separate export from anything mirroring `AnthropometryCriticVerdict.verdict` (three values),
because the frontend never receives the raw critic vocabulary; the API only ever exposes the
persisted one (`measurement-analysis-api.md` §2).

**Discriminated response union** (mirrors the race stack's precedent at
`src/types/insightV3.types.ts:100` / `src/types/athleteRaceAnalysis.types.ts:81`, per
`ui-design-analysis-summary.md` §0): the response schemas in `measurement-analysis-api.md` §2
discriminate on the row-format `schema_version` field (`"v1" | "v2"`), defaulting to `"v1"` when
the backend omits the field entirely (pre-042 wire shape) so rows written before this feature's
deploy still parse without a client update being strictly synchronous with the backend deploy.

## 3. Word budgets (FR-002)

| Audience | Budget | Enforced by |
|---|---|---|
| `family` | ≤ 180 words | System count over the rendered prose (`text` column, §4), **not** the model's self-reported `word_count` field — that field is telemetry only. Counted after guardrail scrubbing, so a scrubbed-out phrase does not count toward the budget it was removed from. |
| `coach` | ≤ 110 words | Idem. |

Enforcement point: `app/services/ai/anthro/prechecks.py`, rule **R07** (word budget exceeded, 10%
tolerance — matches the race stack's own tolerance convention). R07 is a **style** rule (degrades
confidence, does not block delivery outright) — see `golden-eval-case.md` §3 for the full R01–R12
catalogue and its must-block/degrade split. A draft that exceeds budget is not silently truncated
by the pipeline; it is flagged to the critic, which may adopt a mechanically shortened
`revised_output` (`data-model.md` §3, the "mechanical" revision path).

These budgets are **tighter** than the pre-042 free-prose budgets (family 200/250 words
historically, coach 120 — `analysis-design.md` §2) because structured fields remove the
connective prose a single paragraph needed; this is an intentional, not incidental, reduction.

## 4. Prose rendering rule (`text` column)

`AthleteAIExplanation.text` stays `NOT NULL` for every row, including `schema_version="v2"` rows
(`data-model.md` §1). The renderer (`app/services/ai/anthro/persist.py`, or a dedicated
`render_markdown_free(insight: AnthropometryInsightV1) -> str` helper it calls) produces the same
kind of flat, Markdown-free prose the legacy use cases wrote directly, in this fixed section
order:

```text
{summary_line}

{" ".join(changes)}
{" ".join(meaning)}
{" ".join(next_weeks)}
{" ".join(warning_signs) if warning_signs else ""}
```

No headings, no bullet characters, no bold — every field of `AnthropometryInsightV1` is already
plain prose per rule 9 of the analyst prompt (`contracts/prompts/anthropometry_analyst_v1.md`),
so the renderer is string concatenation with paragraph breaks, not a Markdown-to-text conversion.
This is what lets every existing reader of `.text` (email templates, PDF generation, any code
outside this feature's touched modules) work unchanged — the exact same move
`app/services/race/insight_v3.py:280-356` makes with `_action_bullet`/`_field_reading_line` to
keep `AthleteAiInsight`'s legacy consumers alive across the v2→v3 schema jump.

`confidence.reason` and `data_gaps` are **not** rendered into `.text` — they are metadata about
the analysis, not part of its narrative content, and stay accessible only through
`structured_json` / the API's `confidence`/`data_gaps` fields (`measurement-analysis-api.md` §2).

## 5. Tests

- `test_insight_schema_rejects_extra_fields` — a payload with one undeclared key raises
  `ValidationError` (`extra="forbid"` regression guard).
- `test_insight_schema_cardinality_bounds` — table-driven over `changes`/`meaning`/`next_weeks`/
  `warning_signs`/`data_gaps` at their min/max ± 1, asserting the exact accept/reject boundary.
- `test_word_budget_counts_rendered_text_not_self_reported` — a draft whose `word_count` field
  under-reports its own length is still flagged by R07 against the real count.
- `test_prose_render_is_markdown_free` — no `#`, `*`, `-` list markers, or `**` survive
  `render_markdown_free()` on a representative insight.
- Frontend: `anthropometryInsightV1Schema` round-trips a fixture identical to the backend's
  `AnthropometryInsightV1.model_dump(mode="json")` output for at least one case per
  `golden-eval-case.md`'s twelve cases (contract-drift guard between the two schema definitions).
- Frontend: the discriminated response union parses a wire payload with `schema_version` absent
  as `"v1"` (backward-compatibility regression guard, `measurement-analysis-api.md` §2).
