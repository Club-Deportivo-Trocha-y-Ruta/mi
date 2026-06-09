# Contract: Graph State & AnalysisInput (011-ai-insights-grounding)

Internal contract between the analysis graph nodes (`app/services/race/ai/`), the
agents (`app/services/race/agents/`), and the routers. No public HTTP API changes.

## initial_state (routers → graph)

Both launch paths (`athlete_race_analysis.py` per-athlete v2, `race_analysis.py`
global) MUST inject:

```python
initial_state = {
    # ... existing keys (athlete_id, season, valida_nums, coach_id,
    #     explain_mode, run_id, prompt_version, athlete_age) ...
    "ltad_group": str,              # LTADGroup value from age_decimal mapping (REQUIRED)
    "maturation_status": str | None # latest anthropometric record, None if no records
}
```

Backward compatibility: `_resolve_ltad` keeps its BAMBINO fallback but it becomes an
exceptional path that logs a warning (same pattern as `_resolve_age` / Fix 1).

## load_race_data → state

```python
{
    # ... existing keys ...
    "event_conditions": {           # NEW — one entry per launched válida
        <valida_num:int>: {
            "climate": str | None,
            "temperature_c": float | None,
            "surface_condition": str | None,   # SurfaceCondition value
            "altitude_msnm": int | None,
            "weather_notes": str | None,       # RAW here; scrubbed by anonymize
        }
    }
}
```

Invariant: keys cover exactly the válidas resolved for the launched set; an event
with no recorded conditions yields an entry whose fields are all `None` (the absence
must be representable — FR-003).

## anonymize → state

- `event_conditions[*].weather_notes` replaced by name-scrubbed text
  (`weather_notes_scrubbed` semantics); structured fields pass through unchanged.
- Invariant (property-tested): no string in `forbidden_names` appears anywhere in
  `event_conditions` after this node.

## analyst_agent (per válida)

For each `(valida_num, AnalysisInput)` pair, the node MUST populate:

```python
AnalysisInput(
    # ... existing fields ...
    race_meta=format_race_meta(event_conditions[valida_num]),  # str | None
    maturation_status=state["maturation_status"],              # str | None
)
```

`format_race_meta` returns `None` when every condition field is `None` (never an
empty/placeholder string). Rendering invariants:

- `race_meta is None` → prompt contains NO conditions section and includes the
  anti-fabrication veto.
- `race_meta` mentions ONLY non-None fields.

## critic_agent → state

```python
{
    "per_valida_verdicts": { <valida_num:int>: CriticFeedback },  # NEW — one per draft
    "critic_feedback": CriticFeedback,   # kept: verdict of first válida (v1 compat)
}
```

Critic input contract (per draft): the v2 critic prompt receives `draft_analysis`
PLUS a ground-truth block: the válida's `event_conditions`, the athlete's result row
(position, race_time, gap), and podium times. Verdict JSON schema unchanged
(`approved/severity/issues/must_block`).

## confidence → persist_insight

```python
{ "confidence": { <valida_num:int>: InsightConfidence } }  # computed, per draft
```

`persist_insight` MUST read the per-válida value for each row it writes; the
`or InsightConfidence.medium` constant-default remains only for v1 runs.

## Chat tool (agents/chat.py)

New tool, factory-built like the existing two:

```
obtener_condiciones_evento(valida_num: int, season: int) -> str
  → JSON of recorded conditions, or {"registro": false} when none/all-None
```

Prompt rule (race_chat_v1.md): event-fact answers MUST derive from tool output;
`registro: false` → answer "no quedó registrado", never invent.
