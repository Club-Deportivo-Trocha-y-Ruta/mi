# Contract — measurement / PHV analysis API (v1|v2 discriminated response, family gating)

**Router**: `backend/app/routers/ai.py` (existing file, extended — W2 per `plan.md`).
**Schemas**: `backend/app/schemas/ai.py` (existing file, extended).
**Pipeline**: `backend/app/services/ai/anthro/pipeline.py` (new) replaces
`PHVExplainerUseCase` / `AnthropometricRecordExplainerUseCase` as the thing these two endpoint
pairs call — both use cases are deleted at the end of W2 (`architecture.md` §Wave 1, confirmed by
lead ruling 3/plan.md Project Structure).
**Related contracts**: `insight-schema.md` (the `structured` object), `data-model.md` §3 (the
`critic_verdict` state machine this contract exposes), `analysis-context.md` (the input the
pipeline builds before calling the model).
**Requirements covered**: FR-001–FR-016 (analysis content and review), FR-026, FR-029, FR-033
(UI-facing shape); User Stories 1, 2, 3.

---

## 0. Endpoints — paths unchanged, both gain `?audience=`

| Method | Path | Change from today |
|---|---|---|
| `GET` | `/api/ai/athletes/{athlete_id}/phv-explanation?audience=family\|coach` | Response body gains v1\|v2 discriminated fields (§2). Family-role gating added (§3). |
| `POST` | `/api/ai/athletes/{athlete_id}/phv-explanation?audience=family\|coach` | Calls the new pipeline instead of `PHVExplainerUseCase`. Response shape per §2. |
| `GET` | `/api/ai/athletes/{athlete_id}/measurements/{record_id}/explanation?audience=family\|coach` | **New query param** — see §0.1. Everything else as above. |
| `POST` | `/api/ai/athletes/{athlete_id}/measurements/{record_id}/explanation?audience=family\|coach` | Idem. Calls the pipeline instead of `AnthropometricRecordExplainerUseCase`. |

### 0.1 Why the per-measurement endpoint gains `?audience=`

Today `measurement_explanation` (`ai.py:657`) has no audience split — one cache row per
`(athlete_id, record_id)`, one `use_case = RECORD_USE_CASE` (`"anthropometric_record_explainer"`,
`anthropometric_record_explainer.py::USE_CASE_KEY`). FR-002 requires the per-measurement analysis
to exist "in two audiences: family and coach" with different content (family: no cm/year, no
months-to-PHV; coach: both allowed) — not just for the PHV explanation. The only existing
precedent for expressing two audiences of the same underlying analysis is the PHV endpoint's
`_use_case_for_audience()` pattern (`ai.py:88-89`), so this contract extends the measurement
endpoint to the identical shape rather than inventing a second mechanism:

```python
_RECORD_USE_CASE = "anthropometric_record_explainer"          # UNCHANGED string — keeps existing
                                                                # v1 rows addressable, so a coach's
                                                                # first "Regenerar" after this
                                                                # feature ships upgrades the SAME
                                                                # cache row to schema_version="v2"
                                                                # in place (no new row, no orphaned
                                                                # v1 row left behind).
_RECORD_COACH_USE_CASE = "anthropometric_record_explainer_coach"   # NEW — no legacy rows exist
                                                                    # under this key, since the
                                                                    # coach audience did not exist
                                                                    # for this endpoint before 042.
```

`_ensure_audience_allowed()` (`ai.py:92-113`) is reused unchanged: only coach/admin may request
`audience=coach`; a parent requesting it gets `403` regardless of athlete ownership, exactly as
the PHV endpoint already enforces.

## 1. Request

No change to path parameters or body (both POSTs remain bodiless). `audience` is an optional
query parameter, `Literal["family", "coach"]`, default `"family"` — identical semantics on both
endpoints now.

## 2. Response — discriminated on the row-format `schema_version`

Both `PHVExplanationResponse` and `AnthropometricRecordExplanationResponse`
(`backend/app/schemas/ai.py:35,46`) gain the same four fields. `text`, `model`, `provider`,
`generated_at`, `age_group`, `maturation_status` (and, for the record endpoint, `record_id`/
`num_previous_measurements`/`delta_height_cm`/`delta_weight_kg`) are **unchanged in name and
meaning** for both schema versions — v1 rows keep populating them exactly as before.

```python
class AnthropometryInsightOut(BaseModel):
    """Mirrors AnthropometryInsightV1 (insight-schema.md §1) for the wire —
    kept as a separate Pydantic class so the API contract does not silently
    change shape if the internal analyst schema gains an analyst-only field."""
    model_config = ConfigDict(extra="forbid")
    summary_line: str
    changes: list[str]
    meaning: list[str]
    next_weeks: list[str]
    warning_signs: list[str]
    confidence: Confidence          # {level, reason} — insight-schema.md §1
    data_gaps: list[str]


# Added to BOTH PHVExplanationResponse and AnthropometricRecordExplanationResponse:
class _StructuredAdditions(BaseModel):
    schema_version: Literal["v1", "v2"] = "v1"     # row-format discriminator — data-model.md §0
    structured: AnthropometryInsightOut | None = None      # None for v1 rows, always set for v2
    critic_verdict: Literal[
        "approved", "revised", "flagged", "fallback", "skipped"
    ] | None = None                                 # None for v1 rows
    is_fallback: bool = False                        # True iff critic_verdict == "fallback"
    prompt_version: str | None = None                # None for v1 rows
    trace_id: str | None = None                       # coach-only (§4); always None to a parent,
                                                       # always None in production (LANGFUSE_ENABLED
                                                       # is a startup failure there)
```

`text` remains **required and always populated** on both versions — a v2 response's `text` is the
prose rendering of `structured` (`insight-schema.md` §4), never empty, so any consumer reading
only `.text` (an old mobile client, a script) keeps working with zero code change.

### 2.1 Example — v1 (legacy row, unaffected by this feature)

```json
{
  "text": "En las últimas semanas se observó un crecimiento acorde a lo esperado para su edad...",
  "model": "gemini-3.1-flash-lite",
  "provider": "google",
  "generated_at": "2026-06-02T14:03:00Z",
  "age_group": "13-15",
  "maturation_status": "Circa-PHV",
  "record_id": 4821,
  "num_previous_measurements": 2,
  "delta_height_cm": 1.1,
  "delta_weight_kg": 0.4,
  "schema_version": "v1",
  "structured": null,
  "critic_verdict": null,
  "is_fallback": false,
  "prompt_version": null,
  "trace_id": null
}
```

### 2.2 Example — v2, coach audience, `critic_verdict="approved"`

```json
{
  "text": "En 14 semanas se registró un cambio de talla de +1.0 cm, dentro de lo esperable...",
  "model": "gemini-3.8-flash",
  "provider": "google",
  "generated_at": "2026-09-10T11:56:00Z",
  "age_group": "13-15",
  "maturation_status": "Circa-PHV",
  "record_id": 4900,
  "num_previous_measurements": 3,
  "delta_height_cm": 1.0,
  "delta_weight_kg": 0.0,
  "schema_version": "v2",
  "structured": {
    "summary_line": "Talla +1.0 cm en 14 semanas, dentro del rango esperado para su fase Circa-PHV.",
    "changes": ["El cambio de talla supera el ruido instrumental y se mantiene en la fase Circa-PHV."],
    "meaning": ["La velocidad estimada de 3.7 cm/año está por encima de lo típico para esta fase (2-3 cm/año esperado)."],
    "next_weeks": ["Esta fase es compatible con fuerza progresiva y mayor estructura de sesión."],
    "warning_signs": [],
    "confidence": {"level": "high", "reason": "Intervalo de 14 semanas confirma un patrón consistente con la medición previa."},
    "data_gaps": []
  },
  "critic_verdict": "approved",
  "is_fallback": false,
  "prompt_version": "anthropometry_analyst_v1",
  "trace_id": "a1b2c3d4e5f60718"
}
```

### 2.3 Example — v2, coach audience, `critic_verdict="flagged"` (family blocked, coach sees it)

```json
{
  "text": "El cambio de talla registrado no supera el margen de error habitual del instrumento...",
  "model": "gemini-3.8-flash",
  "provider": "google",
  "generated_at": "2026-09-10T09:12:00Z",
  "age_group": "10-12",
  "maturation_status": "Pre-PHV",
  "record_id": 4901,
  "num_previous_measurements": 1,
  "delta_height_cm": 0.2,
  "delta_weight_kg": 0.1,
  "schema_version": "v2",
  "structured": {
    "summary_line": "Cambio de talla dentro del ruido instrumental; sin tendencia nueva que reportar.",
    "changes": ["El cambio de 0.2 cm está por debajo del umbral de 0.7 cm y no se interpreta como crecimiento real."],
    "meaning": ["No hay suficiente base para hablar de una tendencia en esta fase."],
    "next_weeks": ["Mantener la rutina actual; la próxima medición dará más contexto."],
    "warning_signs": [],
    "confidence": {"level": "low", "reason": "Un solo cambio pequeño no permite una lectura firme."},
    "data_gaps": ["Solo una medición previa registrada."]
  },
  "critic_verdict": "flagged",
  "is_fallback": false,
  "prompt_version": "anthropometry_analyst_v1",
  "trace_id": "9f8e7d6c5b4a3210"
}
```

A parent `GET`ting the family-audience row backing this same record receives `204 No Content`
(§3), never this payload.

## 3. Family gating — server-side, on every read

**Gate is keyed on requester role, not on the `audience` query param.** A coach may request
`?audience=family` to preview what a parent would see and still receives the actual row content
(including `critic_verdict="flagged"`) — the coach is the human in the loop (FR-016: "the coach
MUST see it marked 'Con observaciones'") and is never blind to what the system produced. Only a
`UserRole.parent` caller is gated.

```python
# get_phv_explanation_cached / get_measurement_explanation_cached — both GET handlers
if current_user.role == UserRole.parent and cached is not None:
    verdict = cached.critic_verdict   # None (legacy) | "approved" | "revised" | "flagged" | "fallback" | "skipped"
    if verdict not in (None, "approved", "revised"):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
```

`None` (legacy prose rows) is treated as always-deliverable — this feature does not retroactively
gate content that predates the critic (`data-model.md` §6 invariant 3; `ui-design-analysis-
summary.md` §3: "v1 rows have no critic verdict... treat `null` as 'not flagged'").

The frontend never has to branch on this — a `204` renders through the exact same "no analysis
yet" path FR-033 already requires for a genuinely absent analysis (`AnthropometricRecordExplanation
Card`/`PHVExplanationCard`'s shared empty-state component, `ui-design-analysis-summary.md` §2).
Parents cannot `POST` at all (`_forbid_parents`, `ai.py:128-134`, unchanged), so there is no path
where a parent triggers a generation and needs the result gated mid-flight — gating only ever
applies to a cache read.

**Independent Test** (User Story 3): with a fixture athlete whose latest family-audience row has
`critic_verdict` cycling through `approved`, `flagged`, `fallback`, and no row at all, assert a
parent's `GET` returns `200` only for `approved`/`revised` and `204` in every other case,
including the three adverse `critic_verdict` values and the missing-row case — all four render the
identical placeholder client-side.

## 4. Coach technical-details disclosure (FR-029)

`trace_id` is populated **only** when: the requester is coach/admin, `LANGFUSE_ENABLED=true` (dev
only — a hard startup failure in production, `contracts/config-env.md` §1), and the generation
actually produced a trace (not the case for a `fallback`-path generation that short-circuited
before the pipeline reached the point that opens the root span — see `contracts/trace-metadata-
allowlist.md` §4 for exactly when the trace id is minted). In every other combination — parent
caller, production, tracing disabled/misconfigured — `trace_id` is `null`. The frontend's
"detalles técnicos" disclosure (coach-only, `ui-design-analysis-summary.md` §1) reads `model`,
`prompt_version` and `trace_id` from this same response; no new endpoint.

## 5. Status codes and denied paths (unchanged from today, verified still correct)

| Code | Cause | Note |
|---|---|---|
| `200` | Success (GET cache hit, POST generation). | |
| `204` | GET, no cache row for that record+use_case+audience, **or** family gating fired (§3). | Both indistinguishable to the client by design. |
| `403` | Parent calls `POST` (`_forbid_parents`); any caller requests `audience=coach` without coach/admin role (`_ensure_audience_allowed`). | Unchanged. |
| `404` | `record_id` does not belong to `athlete_id` (measurement endpoint only). | Unchanged, `_get_record_or_404`. |
| `422` | PHV endpoint, athlete has zero anthropometric records. | Unchanged. |
| `451` | Athlete has no active AI-processing consent. | Unchanged, `_ensure_ai_consent`. |
| `502` | Guardrail rejection on the rendered text (`LLMSchemaError`). | Unchanged mapping; now can also fire from `guardrails_step.py`, not just the legacy use case. |
| `503` | `AI_ENABLED=false`, or the analyst call itself is unavailable/timed out **and** the pipeline's own deterministic-fallback path also could not produce a valid insight (should not happen — the fallback template is not model-dependent; treat a `503` here as a genuine bug if it fires post-042). | Narrower than today: a plain analyst timeout no longer surfaces as `503` — it resolves to a `200` with `critic_verdict="fallback"` (`data-model.md` §3), which is the whole point of the fallback design. `503` is reserved for `AI_ENABLED=false` and truly catastrophic pipeline failures. |
| `500` | `LLMConfigError` (bad provider config). | Unchanged. |

**Behaviour change to flag explicitly**: pre-042, an LLM timeout on either endpoint surfaced as
`503 Servicio de IA no disponible` to the coach. Post-042, the same timeout resolves to a `200`
carrying the deterministic fallback insight with `critic_verdict="fallback"` and
`confidence.level="low"` — this is intentional (FR-013/FR-014: "the user sees the fallback, not
an error page", Edge Case spec.md:128) and must be called out in the migration notes for anyone
who wrote a test asserting the old `503` behaviour on timeout.

## 6. Audit trail — unchanged

`_record_explanation_audit()` (`ai.py:211-259`) and `_EXPLANATION_REWRITTEN_FIELDS`
(`ai.py:177-185`) are **not** touched by this feature. The nine new columns (`data-model.md` §1)
are telemetry about the generation, not facts about the athlete, and stay outside
`VALUE_ALLOWLIST` scope entirely — the audit row for `athlete_ai_explanation` continues to record
only the create/update fact and the two identifiers (`related_entity_id` = the measurement),
never a token count, cost, or trace id. Extending `_EXPLANATION_REWRITTEN_FIELDS` with any of the
nine new column names is explicitly **out of scope** — they are cache metadata, not "what
changed" in the sense that list already tracks (`model`/`provider`/`text`/etc., all pre-existing).

## 7. Tests

- Denied paths re-run against the new pipeline, unchanged expectations: parent `POST` → 403;
  `audience=coach` from a parent → 403; no consent → 451; `AI_ENABLED=false` → 503; unknown
  `record_id` → 404.
- `test_family_gate_blocks_flagged_fallback_skipped_verdicts` — table-driven over the four
  non-deliverable states (`flagged`, `fallback`, `skipped`, and a row that does not exist) plus the
  two deliverable ones (`approved`, `revised`), asserting `204` vs `200` for a parent caller.
- `test_coach_sees_flagged_content_unfiltered` — same fixture, coach caller, asserts `200` with
  the real `structured`/`critic_verdict` in every case.
- `test_v1_row_renders_without_structured_fields` — a legacy fixture row asserts
  `schema_version="v1"`, `structured=null`, `critic_verdict=null`, exact byte-for-byte `text` as
  stored (FR-026, Edge Case spec.md:129).
- `test_regenerate_v1_row_upgrades_in_place` — a `POST` against a record with an existing v1 row
  asserts the **same** `AthleteAIExplanation.id` now carries `schema_version="v2"` (upsert, not a
  new row).
- `test_trace_id_null_for_parent_and_in_production` — `trace_id` is `null` for a parent caller
  regardless of role-independent Langfuse state, and `null` for a coach caller when
  `LANGFUSE_ENABLED=false`.
- `test_timeout_resolves_to_200_fallback_not_503` — analyst timeout fixture asserts `200`,
  `critic_verdict="fallback"`, `confidence.level="low"`, not the pre-042 `503`.
