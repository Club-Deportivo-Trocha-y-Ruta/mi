# Privacy audit — feature 039 (season comparison groups)

T045 — mandatory `data-privacy-guard` audit per `CLAUDE.md` ("The
`data-privacy-guard` audit is mandatory for any feature touching
athlete-identifiable data"). Scope: `git diff main` on
`feat/039-season-comparison-groups` (41 files, +3965/-227).

Reviewed against Ley 1581/1098 categories (CRITICAL: DOB, ID docs, address,
medical data, guardian contacts, identifiable photos; HIGH: individual
anthropometry, maturation status, individual performance, attendance).

## Findings

| Severity | File:line | Finding | Status |
|---|---|---|---|
| — | — | No CRITICAL or HIGH findings in the reviewed diff. | N/A |

No findings required a code fix. Nothing was changed by this audit.

### LOW-severity notes for the reviewer (informational only, no action required)

| # | File:line | Note |
|---|---|---|
| L1 | `backend/tests/services/race/test_mysql_dialect.py:199-206` | Pre-existing fixture (`first_name="Maria", last_name="Lopez"`) uses a plausible-but-generic name without a "Ficticio/a" marker, unlike every fixture added by 039. Not touched by this diff (confirmed via `git diff main`), so out of scope for T045 — flagging only so a future pass normalizes it to the project's fictional-data convention. |
| L2 | `backend/tests/routers/test_athlete_race_analysis.py:181-198` (pre-existing) | Same pattern (`display_name="Winner Test"`, `display_name="Athlete Real Name"`) — pre-existing, untouched by 039, not a real name, just an unmarked test label. No action needed for this feature. |
| L3 | `backend/app/services/race/prompts/race_analyst_v3.md` rule 10 / `agents/analyst.py::_progression_series_label` | Confirms the v3 prompt and the season table keep using `{{ athlete_ref }}` ("el deportista") exclusively — no regression here, noted as a positive confirmation since it's the highest-risk touch point (AI provider prompt). |

## What was checked

- **Championship readings** (`newsletter_builder.py::_build_race_block`,
  `championship_card.html.jinja`, `athlete_stage_log.html`,
  `ChampionshipReadingCard.tsx`): expose only the athlete's own position,
  field size (peloton count), gap-to-P1 %, and percentile. No competitor
  names, bibs, or club text reach the template context or the component
  props.
- **New schema fields** (`schemas/athlete_race_analysis.py`):
  `ComparisonGroupOption`, `EvolutionPoint` additions (`series_id`,
  `series_name`, `series_level`, `comparison_group`, `field_size`,
  `percentile`) are all aggregate/public-federation or the athlete's own
  derived stats — none are PII. `AthleteInsightOut.series_level` mirrors
  the existing `series_kind` field (T030 pattern).
- **`GET /evolution` `series_id` + RBAC** (`routers/athlete_race_analysis.py`):
  the new query param is validated (`ge=1`) and passed straight through to
  `build_evolution`; access control still runs entirely through the
  unmodified `verify_athlete_access` dependency — a parent of a different
  athlete gets 403/404 with or without `series_id` (asserted by the new
  test `test_athlete_race_analysis_evolution_groups.py`, and by the
  existing whitelist test `test_evolution_response_only_exposes_aggregated_fields`
  which now also covers the new fields and `groups[]`).
- **AI pipeline inputs** (`compute_metrics.py`, `analyst_agent.py`,
  `load_race_data.py`, `agents/analyst.py`, `prompts/race_analyst_v3.md`,
  `evals/race_analyst/golden_v3/case_009.json`): all new columns
  (`series_id`, `series_kind`, `series_level`, `event_id`, `event_date`)
  are event/series metadata, never athlete/competitor identity. The new
  golden case uses `"athlete_ref": "el deportista"` throughout and its
  `forbidden_terms` list intentionally includes three names
  (`Mariana`/`Thiago`/`Valentina`) as a guardrail regression check that the
  model never emits a real-looking name — this is the existing feature-036
  pattern, not a leak.
- **Frontend components/types/mocks**: `ChampionshipReadingCard.tsx`,
  `EvolutionChart.tsx`, `MiniSparkline.tsx`, `evolutionFormat.ts`,
  `insights.ts`, `athleteRaceAnalysis.types.ts`, `athleteRaceAnalysis.ts`
  (api), `useAthleteEvolution.ts`. No `localStorage`/`sessionStorage` usage
  introduced, no identifiable data placed in the `series_id` query param
  (it addresses a race series, not a person), no other-competitor field
  rendered. A new regression test
  (`AthleteAIAnalysisTab.parent.test.tsx`: "modo parent nunca expone el
  nombre de un competidor en el widget de evolución") explicitly asserts a
  simulated backend leak (`competitor_display_name`) never reaches the DOM
  in parent mode.
- **Fixtures/tests added**: `tests/fixtures/race_groups.py` (module
  docstring + inline comments explicitly cite CLAUDE.md/Ley 1581; all
  names use the club's "Ficticio/a" convention — athlete "Camila Ficticia
  Salazar", rivals "Rival Ficticio Líder/Dos/Tres", club "Club Ficticio de
  Prueba"), `test_athlete_race_analysis_evolution_groups.py`,
  `test_analyst_agent_resolution.py`, `test_graph_championship.py`,
  `test_comparison_groups.py`, `test_newsletter_pdf_groups.py`, and the MSW
  handlers in `athleteRaceAnalysisHandlers.ts` — all synthetic, no real
  club data, no real DOB tied to any exposed output (fixture `birth_date`
  values are internal-only, never logged or serialized in any assertion).
- **No `.env` or key content**: grep across the full diff for
  `api[_-]?key|secret|password|token=|\.env|AIza|sk-ant|sk-proj` found
  only unrelated matches (`accessToken`/`Authorization: Bearer fake` in
  tests, and a changelog line in `CLAUDE.md` naming a pre-existing
  migration revision `a1b2c3d4e5f8` for "password-reset-tokens" — a schema
  name, not a secret value).
- **Logs/error messages**: no new `logger.*`/`print(` calls were added by
  this feature; the two touched call sites in `newsletter_builder.py`
  (`_build_race_block`'s except-branch) log only `type(exc).__name__`,
  consistent with the pre-existing convention.

## Result

Files reviewed: 41 (diff vs `main`)
Findings: 0 critical, 0 high, 0 medium (3 low, informational, pre-existing/out-of-scope)

Status: **APPROVED**
