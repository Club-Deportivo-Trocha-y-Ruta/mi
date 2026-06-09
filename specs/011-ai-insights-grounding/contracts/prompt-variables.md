# Contract: Prompt Template Variables (011-ai-insights-grounding)

Jinja2 variable contracts for the three affected prompts. Product-facing prose stays
in español neutro (Colombia).

## race_analyst_v2.md (edited)

| Variable | Type | Change | Rendering rule |
|---|---|---|---|
| `race_meta` | `str \| None` | now actually populated (was always `""`) | `{% if race_meta %}` section renders the formatted conditions block; **when falsy, a veto block renders instead**: mentioning clima/pista/terreno is PROHIBIDO |
| `maturation_status` | `str \| None` | now real (was hardcoded default "Pre-PHV") | `None` → the "Fase madurativa" context line is omitted and the prompt instructs: no maturation-phase claims |
| `ltad_group` | `str` | now injected from real age mapping | unchanged rendering; differentiation block now receives correct group |

Section-1 instruction change: "SÍ incluir … condiciones de clima, tipo de pista"
becomes conditional — included only when `race_meta` is provided; otherwise replaced
by the explicit prohibition.

## race_critic_v2.md (NEW)

| Variable | Type | Purpose |
|---|---|---|
| `draft_analysis` | `str` | the draft markdown under review (same as v1) |
| `expected_sections` | implicit | v2 headings: "Qué pasó en esta válida", "Recorrido hasta acá", "Hacia dónde va" |
| `ground_truth` | `str` | formatted block: recorded conditions (or "sin condiciones registradas"), athlete result row, podium times for THIS válida |

New quality rules (severity high): any factual statement contradicting
`ground_truth`; any clima/pista/terreno mention when ground truth says no conditions
recorded. Output JSON schema identical to v1 (`approved/severity/issues/must_block`).

## race_chat_v1.md (edited)

Adds the grounding rule: questions about event facts (conditions, results) MUST be
answered from tool results (`obtener_condiciones_evento`, `fetch_results`,
`obtener_insights_atleta`); when a tool reports no record, answer
"no quedó registrado para esa válida" — inventing values is PROHIBIDO.
