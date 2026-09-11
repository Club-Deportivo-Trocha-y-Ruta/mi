# Contract — Langfuse trace metadata allow-list, mask, tags, session id

**Module**: `backend/app/services/llm/observability_metadata.py` (new, per lead ruling 9 —
supersedes `architecture.md` §5.1's `app/services/ai/observability_metadata.py` naming and
`redaction.py`/`LANGFUSE_METADATA_ALLOWLIST` proposal, both withdrawn).
**Companion module**: `backend/app/services/llm/observability.py` (new — moved from
`backend/app/services/race/observability.py`, which becomes a re-export shim, per
`llm-transport.md` §2).
**Source of truth for the field table**: `privacy.md` §2, reproduced exactly in §2 below (per
lead ruling 9: "Fields exactly per privacy.md §2 table"). Do not re-derive this table from
`architecture.md` §5 — that document's own §11.6 explicitly withdraws its initial tag list in
favour of `privacy.md`.
**Requirements covered**: FR-017–FR-024; User Story 2.

---

## 0. What must never be re-litigated (privacy audit, §1.3 of `privacy.md`)

For a ~20-minor club, `sex × age_group` alone gives a mean equivalence-class size of 5 — already
at the threshold the codebase treats as unsafe (`monthly_report.py`'s
`MIN_ATHLETES_FOR_INDIVIDUAL_ROWS = 5`). Adding `maturation_status` drops the mean cell size below
2. **No rounding or bucketing scheme rescues `sex`, `age_group`, `maturation_status`, `category`,
`phv_offset`, `months_from_phv`, `growth_velocity_cm_per_year`, or any delta magnitude as
combinable trace metadata or tags at this club's size** — the only field-level mitigation that
works is exclusion. This is why the table in §2 has so many hard `no`s where a first-pass reading
of the spec's own wording ("age → 2-year bucket, deltas → rounded") might suggest otherwise; the
privacy audit explicitly overrides that literal reading (`privacy.md` §0, "headline finding").

## 1. The mask — sentinel type, not a shape heuristic

`Langfuse`'s `mask()` callback (`MaskFunction` protocol) receives `data: Any` **without** telling
the caller which field (`input`/`output`/`metadata`) it is masking (`langfuse.md` §1, confirmed
against the Langfuse v4 SDK source via Context7). A shape-based heuristic ("if it's a dict, allow
it") is unsafe: LangChain message `content` can itself be `list[dict]` for multimodal input, so a
bare `isinstance(data, dict)` check would unmask part of a real prompt. The fix is a sentinel type
constructed **only** through a validating factory, so the allow-list decision happens at
construction time, not at mask time:

```python
# backend/app/services/llm/observability_metadata.py

from dataclasses import dataclass
from typing import Any, Mapping

ALLOWED_METADATA_KEYS: frozenset[str] = frozenset({
    # exactly the "yes" rows of §2, nothing else — see the pinning test in §5
})


@dataclass(frozen=True)
class StructuralMetadata:
    """Marker wrapper. Only metadata built through this constructor survives
    the mask. Anything not on ALLOWED_METADATA_KEYS is rejected at
    construction, not merely at export, so a typo'd key never reaches
    Langfuse even if a call site forgets to route through build_structural_metadata()."""

    _data: Mapping[str, Any]

    def __init__(self, **fields: Any) -> None:
        unknown = set(fields) - ALLOWED_METADATA_KEYS
        if unknown:
            raise ValueError(f"Non-allow-listed metadata keys: {sorted(unknown)}")
        object.__setattr__(self, "_data", dict(fields))

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)


def build_structural_metadata(**fields: Any) -> StructuralMetadata | None:
    """The ONLY entry point call sites may use to attach metadata to a
    Langfuse observation. Returns None (i.e. attach nothing) when
    settings.langfuse_structural_metadata is False — callers do not
    branch on the flag themselves."""
    from app.config import settings
    if not settings.langfuse_structural_metadata:
        return None
    return StructuralMetadata(**fields)


def _mask(*, data: Any, **kwargs: Any) -> Any:
    if data is None:
        return None
    if isinstance(data, StructuralMetadata):
        return data.as_dict()          # already allow-list-validated at construction
    return "[redacted]"
```

**Four rules, non-negotiable**:

1. `input` and `output` are **unconditionally** redacted, always, regardless of
   `LANGFUSE_STRUCTURAL_METADATA`. Never wrapped in `StructuralMetadata` — that type exists only
   for the `metadata` channel.
2. A key not on `ALLOWED_METADATA_KEYS` is rejected at `StructuralMetadata.__init__` time (raises,
   not silently drops — unlike the context-builder allow-lists, which silently drop; the
   difference is deliberate: a dropped prompt key degrades a generation, a dropped-then-forgotten
   trace key is a false sense of security about what left the process. Fail loud here).
2. With `LANGFUSE_STRUCTURAL_METADATA=false` (the default, and the only legal value in
   production — `contracts/config-env.md` §1), `build_structural_metadata()` returns `None` and
   every observation's `metadata` argument is simply omitted — byte-for-byte equivalent to today's
   redact-always behaviour (`architecture.md` §5.1 rule 1, preserved).
3. **Bare dicts fall through to `"[redacted]"`, including anything LangChain's `CallbackHandler`
   auto-populates as `metadata`** (run tags, step index) — the default stays maximally strict; only
   explicit, wrapped, allow-listed data escapes it.

## 2. Allow-list table — reproduced from `privacy.md` §2 exactly

Legend: **yes** = send as-is (tag or metadata key) · **transformed** = send only via the stated
transformation · **no** = never in metadata, tags, or scores, in any form.

| Field | Allowed | Transformation / rationale |
|---|---|---|
| `athlete_id` | transformed | `HMAC-SHA256(key, "anthro:athlete:" + athlete_id)[:16]`, same keyed-hash scheme as the session id (§4) — not a per-process salt (see §4's reconciliation note). Groups traces from the same athlete across a debugging session without persisting identity. |
| `anthropometric_record_id` | transformed | Same scheme, domain string `"anthro:record:"`. |
| `user_id` (requesting coach) | transformed | Same scheme, domain string `"anthro:user:"`. Feature 041 makes "which of two coaches" a distinguishing fact worth minimizing too. |
| `club_id` | yes | Single-club deployment today; carries no extra entropy. |
| `sex` | **no** | Quasi-identifier; §0. |
| `category` | **no** | Near-1:1 derived from age+sex; adds resolution rather than independent signal. |
| `age_decimal` | **no** | Continuous, effectively unique per athlete on a given day. |
| `age_group` | **no** | Only 2 real buckets in this club; combines with anything else to sub-5 cells. **Explicitly removed from the tag list** despite being tracked as a tag candidate in earlier drafts (`architecture.md` §5.3) — closed by the privacy audit, not an open question. |
| `maturation_status` | **no** | Highest-risk field in the whole list — alone, combined with `sex`, already approaches k=1. |
| `phv_offset` / `age_at_phv` / `months_from_phv` | **no** | Continuous, near-unique. |
| `growth_velocity_cm_per_year` | **no** | Continuous, near-unique. |
| `delta_height_cm` / `delta_weight_kg` | **no** | Even rounded, reconstructs a growth curve across repeated calls for the same hashed athlete. |
| `delta_height_significant` / `delta_weight_significant` (booleans) | yes | Pure booleans against a fixed clinical threshold — reveal "was this a notable change" without magnitude. |
| `weeks_since_prev_measurement` | transformed | Bucket to `<8w` / `8-26w` / `26w+` — matches `MIN_WEEKS_FOR_VELOCITY`/`VELOCITY_RELIABLE_WEEKS`, so the boundary already has code meaning. |
| `num_previous_measurements` | transformed | Bucket to `0` / `1` / `2+`. |
| `nutritional_status` | **no** | Same risk class as `maturation_status`. |
| `crossed_phv_phase` (boolean) | **no** | Across repeated traces for the same hashed athlete, lets an observer infer the PHV-crossing timeline. |
| `velocity_confidence` | **no** | Correlates tightly with the (excluded) `weeks_since_prev_measurement` exact value and with maturation timing; not in the original brief and not worth adding — the bucketed `weeks_since_prev_measurement` above already gives the operationally useful signal ("why wasn't a velocity computed"). |
| `training_implications` (coach free text) | **no** | Never enters metadata/tags/scores, not even a length or word-count derivative. |
| session titles / dates | **no** | Independently correlatable to public race calendars and club social posts. |
| guardrail rule ids + scrub counts | yes | Describes LLM *output behaviour*, not athlete data. Closed set from `guardrails.py`. |
| precheck rule ids (`R01`–`R12`) + counts | yes | Same class as guardrail rule ids — operational, closed catalogue (`golden-eval-case.md` §3). |
| critic verdict codes | yes | Closed enum (`approved\|revised\|flagged\|fallback\|skipped`), operational. |
| cache hit/miss (create vs overwrite) | yes | Boolean, purely operational. |
| `use_case` (which endpoint/generation) | yes | Template discriminator, already a DB column. |
| `model` / `provider` / `prompt_version` / `role` (`analyst`\|`critic`) | yes | Explicitly requested; purely operational. |
| tokens (input/output/total) | yes | Explicitly requested. |
| latency | yes | Explicitly requested. |
| `cost_usd` | yes | Explicitly requested; matches the budget-guard's own unit of account. |

### 2.1 Combination rule

Even where the table says `yes`/`transformed` for an id, **never emit more than one of
`{sex, age_group, maturation_status, category}` in the same call** — moot today because all four
are hard `no`, but stated as a standing rule so a future edit cannot flip two of them to allowed
independently of re-running this club-size arithmetic (`privacy.md` §2.1).

## 3. Tags vs metadata vs scores

| Channel | Bypasses `mask()`? | What travels there |
|---|---|---|
| Trace/generation **name** | n/a, not masked data | `use_case` value, e.g. `"anthropometry-record"` (§6). |
| **Tags** | Yes, entirely | `use_case`, `audience`, `prompt_version`, `provider`, `model`, `role`, `cache:create\|cache:overwrite`, `guardrail:<outcome>`, `critic:<verdict>` — the full operational set, always sent regardless of `LANGFUSE_STRUCTURAL_METADATA` (tags are not gated by that flag; they were never part of the redact-always scope to begin with, same as the race stack today). |
| **Metadata** | No — goes through `_mask()` (§1) | Only reached via `StructuralMetadata`, only when `LANGFUSE_STRUCTURAL_METADATA=true`. |
| **Scores** | Yes, entirely (confirmed, `langfuse.md` §1: "NOT covered by mask — no docs surface show masking applied to score payloads") | Numeric/boolean only — `precheck_violation_count`, `word_count_family`, `retry_count`. **Never a `comment=` string** — that is the one field on a score that could carry model output by accident. |
| **`input` / `output`** | No, never | Nothing. Always `"[redacted]"`. |

## 4. Session id

```python
import hmac, hashlib

def keyed_session_id(*, use_case: str, athlete_id: int, record_id: int, key: str) -> str:
    domain = "langfuse-session"
    payload = f"{domain}:{use_case}:{athlete_id}:{record_id}"
    return hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
```

`key = settings.jwt_secret_key` (lead ruling 9, explicit owner choice — **not** a per-process salt
as `privacy.md` §2's literal table entry for `athlete_id` first proposed). The owner's reasoning,
recorded verbatim in the lead ruling: a per-process salt is stronger but loses cross-restart
grouping — a coach's local Langfuse traces for the same athlete should still group together after
a backend restart, which only a stable server-side key delivers. Domain-separated
(`"langfuse-session"`) from the trace id (§4.1) and from the race stack's own anonymiser key, so a
leak of one derivation does not weaken the other.

This same helper **replaces** `anonymous_session_id`'s truncated plain `sha256` in the race chat
trace (`backend/app/services/race/observability.py:114`, FR-024) — the race chat's session id is
enumerable today over a small preimage space (roughly 20 athletes × a few hundred records, under
10,000 hashes, invertible in seconds by anyone holding both the Langfuse volume and the database);
this feature fixes that as a bundled hygiene item, not a new vulnerability it introduces.

### 4.1 Trace id (deterministic, for nesting — distinct from the session id above)

```python
trace_id = Langfuse.create_trace_id(seed=keyed_session_id(
    use_case=use_case, athlete_id=athlete_id, record_id=record_id, key=jwt_secret_key,
))
```

One root span per pipeline run, opened in `pipeline.py` before any node executes:

```python
with client.start_as_current_observation(
    name=TRACE_NAME[use_case], as_type="span",
    trace_context={"trace_id": trace_id},
) as root:
    handler = CallbackHandler()   # NO trace_context here — inherits root's active OTel
                                   # context, so every step's LLM call nests under root
                                   # automatically (langfuse.md §1's documented gotcha:
                                   # setting trace_context on BOTH the manual span and the
                                   # handler produces two sibling roots, not a tree).
    config = {"callbacks": [handler]}
    state = await context(state, config)
    state = await analyst(state, config)
    state = await critic(state, config)
    state = await guardrails_step(state, config)
    state = await persist(state, config)
```

`config` is threaded **explicitly** into every step's own `ainvoke` call — not relied on via
ambient contextvar propagation, even though Python 3.13 (this repo's runtime) makes implicit
propagation reliable. `langfuse.md` §1 flags this as a real gap in the *existing* race nodes
(`nodes/analyst_agent.py` takes no `config` parameter) and recommends the new pipeline do it
correctly from the start rather than copy that shortcut.

## 5. Tests

- `test_metadata_allowlist_snapshot` — `ALLOWED_METADATA_KEYS` equals a fixed, reviewed literal
  set (same pattern as `test_ai_context_builder_privacy.py`).
- `test_structural_metadata_rejects_unlisted_key` — `StructuralMetadata(unknown_key=1)` raises.
- `test_mask_redacts_bare_dicts_including_langchain_auto_metadata` — a plain dict, and a dict
  shaped like LangChain's auto-populated run metadata, both mask to `"[redacted]"`.
- `test_mask_passes_structural_metadata_allowlisted_keys_only` — a `StructuralMetadata` instance
  masks to its own `as_dict()`, unchanged.
- `test_combination_rule_rejects_multiple_quasi_identifiers` — even though all four are `no`
  today, `build_structural_metadata` raises if more than one of `{sex, age_group,
  maturation_status, category}`-named kwargs is ever passed, so a future well-intentioned "flip
  one field to yes" PR cannot silently violate §2.1 without a test failing.
- `test_session_id_stable_across_calls_same_inputs` / `test_session_id_differs_across_athletes`.
- `test_session_id_not_enumerable_without_key` — brute-forcing the realistic id space (≈20
  athletes × a few hundred records × 3 use cases) without the key never recovers a match (contrast
  with the pre-042 `anonymous_session_id`, which the same test suite should show *was*
  enumerable, as a regression-value assertion).
- `test_langfuse_structural_metadata_forbidden_in_production` — `contracts/config-env.md` §1.
- `test_no_logger_call_embeds_metadata_dict` — static/AST-walk test over
  `observability_metadata.py` and its call sites, asserting no `logging.*` call interpolates the
  metadata dict object directly.
- `test_trace_nesting_single_root_per_run` — a fake-model integration run asserts every step's
  generation and the guardrail span share one `trace_id`, none opens a second root.
