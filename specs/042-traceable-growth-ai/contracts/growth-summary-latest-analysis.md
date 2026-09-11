# Contract — `latest_ai_analysis` on the growth summary

**Router**: `backend/app/routers/growth.py` (existing, extended — W3).
**Schema**: `backend/app/schemas/growth.py` (existing, extended — `GrowthSummaryOut`).
**Related contracts**: `measurement-analysis-api.md` §3 (the same family-gating logic, reused
here), `data-model.md` §3/§4 (`critic_verdict` state machine, staleness rule).
**Requirements covered**: FR-027, FR-028; User Story 4.

---

## 0. Reconciling two documents that disagree on scope

The lead's ruling (`LEAD-DECISIONS.md` point 10) says the field is `null` "when consent absent,
AI disabled, or nothing approved/revised for the family audience" — read literally, that could
mean the object nulls for *every* viewer whenever the underlying generation is not
`approved`/`revised`. But the same ruling's point 11 endorses `ui-design-analysis-summary.md`
wholesale for the UI, and that document's §1 coach-states table explicitly requires: "Flagged by
critic... coach still sees the summary, with a small 'Con observaciones' note instead of hiding
it (coach is the human-in-the-loop; parents are not)". Those two statements are only consistent if
point 10's "for the family audience" qualifies the *null condition*, not the *viewer* — i.e. the
underlying generation this field is built from is always the family-audience row (§1), and
whether an unapproved family-audience row nulls the field is **role-dependent**:

| Underlying row state | Parent viewer | Coach/admin viewer |
|---|---|---|
| No row exists yet for the athlete's latest record. | `null` | `null` |
| Consent absent, or `AI_ENABLED=false`. | `null` | `null` |
| Row exists, `critic_verdict ∈ {approved, revised}`. | populated, `critic_verdict` omitted | populated, `critic_verdict` included |
| Row exists, `critic_verdict ∈ {flagged, fallback, skipped}`. | **`null`** (same family gate as `measurement-analysis-api.md` §3) | populated, `critic_verdict` included, so the coach can tell "unreviewed"/"flagged"/"fallback" apart |

This is the design this contract specifies. If the lead intended the stricter literal reading
(field nulls for everyone on any non-`approved`/`revised` state), that is a one-line change to
§2's query below — flagged here explicitly so it is not silently assumed.

## 1. Source row

Always the athlete's **latest per-measurement, family-audience, structured** row — never the PHV
card's data (a separate, pre-existing surface untouched by this field) and never the coach-
audience use case, regardless of who is viewing:

```python
select(AthleteAIExplanation)
    .where(
        AthleteAIExplanation.athlete_id == athlete.id,
        AthleteAIExplanation.use_case == RECORD_USE_CASE,   # family audience — measurement-analysis-api.md §0.1
        AthleteAIExplanation.schema_version == "v2",
    )
    .order_by(AthleteAIExplanation.generated_at.desc())
    .limit(1)
```

Family-audience is the source **precisely because** its `summary_line` is, by prompt construction
(`contracts/prompts/anthropometry_analyst_v1.md` rule 7), free of cm/year and months-to-PHV
figures — this is what makes it safe to render the *same* line on both the coach and the family
variant of the growth-tab summary line (FR-027: "one line... in both coach and family mode"). The
coach does not lose anything by this — the full coach-audience breakdown is still one click away
in the measurement dialog (`measurement-analysis-api.md`).

## 2. `GrowthSummaryOut.latest_ai_analysis`

```python
class LatestAiAnalysis(BaseModel):
    record_id: int
    generated_at: datetime
    schema_version: Literal["v2"]          # always "v2" — a null-row case never reaches this model
    summary_line: str
    has_warning_signs: bool                # len(structured_json["warning_signs"]) > 0
    critic_verdict: Literal[
        "approved", "revised", "flagged", "fallback", "skipped"
    ] | None = None                         # populated coach/admin only — see §0 table
    is_stale: bool


class GrowthSummaryOut(BaseModel):
    # ... all existing fields unchanged (backend/app/schemas/growth.py:82-96) ...
    latest_ai_analysis: LatestAiAnalysis | None = None
```

`critic_verdict` is `Optional` at the schema level and the router sets it to `None` before
serialising for a parent caller — not filtered by a response-model exclusion trick, so it is never
present in a debugger/log dump of the object either, matching the "coach-only, never partially
leaked" posture the growth-summary schemas already hold for other coach-only fields.

## 3. `is_stale`

Identical rule to `data-model.md` §4, evaluated against `latest_ai_analysis.record_id` (not
necessarily the athlete's true latest `AnthropometricRecord`, since the cached row can lag
behind):

```text
is_stale ⟺  EXISTS (an AnthropometricRecord for this athlete newer than latest_ai_analysis.record_id)
          OR  (that record's AnthropometricRecord.updated_at > latest_ai_analysis.generated_at)
```

Computed in the same query pass as the rest of `build_growth_summary()` — no second round trip
(SC-008: "the tab's summary line adds no additional request beyond the growth summary already
fetched"). `FR-027`'s coach-mode "Desactualizado" label and the family mode's silent
non-advancement (`ui-design-analysis-summary.md` §2: no badge for family, the line simply keeps
showing the older analysis with its own honest date) are both frontend renderings of this single
boolean — the backend does not compute two different staleness values per role.

## 4. Null conditions — full list

`latest_ai_analysis` is `null` when **any** of:

1. No `schema_version="v2"` row exists yet for `(athlete_id, RECORD_USE_CASE)` — nothing generated
   under this feature yet, regardless of how much legacy v1 history exists.
2. The athlete has no active AI-processing consent (`athlete_has_ai_processing_consent`, the same
   predicate `_ensure_ai_consent` uses in `ai.py:137-148` — **read-only** here, this endpoint
   never raises `451`, it just nulls the field; growth-summary itself has no consent gate today
   and this feature does not add one to the endpoint as a whole, only to this embedded field).
3. `settings.ai_enabled` is `false`.
4. The caller is a parent **and** the row's `critic_verdict ∉ {approved, revised}` (§0).

## 5. Non-fatal computation (§11.4 point 5, `architecture.md`)

```python
try:
    latest_ai_analysis = await _compute_latest_ai_analysis(db, athlete, current_user)
except Exception:
    logger.warning("growth_summary.latest_ai_analysis_failed", extra={"athlete_id": athlete.id})
    latest_ai_analysis = None
```

A failure computing this field **must not** raise past `get_growth_summary` — the Crecimiento tab
is the primary coach surface and must render fully with AI off, misconfigured, or erroring
(mirrors the same non-fatal posture `ai.py:335-348`'s `_recent_p50_latency_seconds` already takes
for a different AI-adjacent read). Only the outer `try/except` in the router changes; nothing
about `build_growth_summary()`'s existing non-AI computation is touched.

## 6. Router signature change

`get_growth_summary` (`growth.py:104-134`) gains `current_user: User = Depends(get_current_user)`
— required for the role branch in §0/§1 and not present in the function signature today (it only
takes `db` and the RBAC-resolved `athlete`). `verify_athlete_access` still does the actual
authorization; `current_user` here is read-only, for role branching after access is already
granted.

## 7. Example — coach view, flagged

```json
{
  "athlete_id": 214,
  "computed_at": "2026-09-11",
  "records_count": 4,
  "latest_evaluation_date": "2026-09-10",
  "stage": "Circa-PHV",
  "maturity_offset": -0.3,
  "latest_ai_analysis": {
    "record_id": 4901,
    "generated_at": "2026-09-10T09:12:00Z",
    "schema_version": "v2",
    "summary_line": "Cambio de talla dentro del ruido instrumental; sin tendencia nueva que reportar.",
    "has_warning_signs": false,
    "critic_verdict": "flagged",
    "is_stale": false
  }
}
```

Same fixture, parent view: `latest_ai_analysis` is `null` (§0).

## 8. Tests

- `test_latest_ai_analysis_null_when_never_generated` / `_no_consent` / `_ai_disabled`.
- `test_latest_ai_analysis_family_gate_by_role` — one fixture row per `critic_verdict` value,
  asserting the §0 table exactly: parent gets `null` for the three adverse states and populated
  (no `critic_verdict` key) for `approved`/`revised`; coach gets populated with `critic_verdict`
  set for all five states.
- `test_is_stale_true_on_newer_record` / `test_is_stale_true_on_corrected_record` /
  `test_is_stale_false_when_current`.
- `test_growth_summary_survives_latest_ai_analysis_exception` — monkeypatch the internal
  computation to raise, assert `200` with `latest_ai_analysis: null` and the rest of the payload
  intact.
- `test_growth_summary_no_extra_round_trip` — assert the AI-analysis lookup is folded into the
  existing query/transaction, not a second `SELECT` issued from a separate connection (SC-008).
