# Research: Competitions in one place (045)

**Sources**:
- the product review of 2026-09-23 (product-manager agent);
- three read-only research passes the same day: metrics engine, athlete tab merge, and area/imports/pending;
- the phase-0 changes now in the working tree.

Line numbers were valid on 2026-09-23. A concurrent design-token migration is editing many frontend files, so re-check every location before editing.

---

## R-01 One metrics engine

**Decision**: `backend/app/services/race/field_metrics.py` becomes the only place where Parrilla, Percentil, Brecha vs. mediana, Brecha vs. 1.ª posición and Brecha vs. podio are computed. Every other computation either delegates to it or is deleted.

The engine gains four things:
1. **Time-based percentile**, using the owner's formula (spec FR-020, the coach's request of 2026-05-25): `100 × (1 − (t − t_fastest) ÷ (t_slowest − t_fastest))`, rounded. It is computed only over FINISHED rows with a time. It returns `None` when there are fewer than 5 such rows (`MIN_FIELD`), when the athlete is not FINISHED with a time, or when all times are equal.
2. **`gap_to_podium_pct`**, next to the existing `gap_to_p3_ms`.
3. **`timed_finishers`**. Today `history.py` and `build_evolution` count it separately.
4. **A category batch entry point**, so the competition detail can attach metrics to every row of a category in one pass.

The engine itself applies the `MIN_FIELD` gate, and consumers stop re-gating.

**Inventory of today's computations** (research pass 1):

| # | Where | Percentile | Gaps | Field size | 045 action |
|---|---|---|---|---|---|
| A | `field_metrics.py::compute_field_metrics` | by position (~l.161), no n≥5 gate | P1 %/ms, P3 ms, median % | FINISHED + MINUS_LAPS | **becomes the engine** |
| B | `analytics_charts.py::build_evolution` | position duplicate (~l.563), min–max time interpolation (~l.492-514, n≥5), no gate on the exposed field | own winner gap (~l.579-589); median already delegates to A (phase 0) | `status='finished'` only | delegate everything to A; drop the homegrown formulas and the `cat_size` query |
| C | `analytics_charts.py::build_distribution` | count ≥ own ÷ sample (~l.827-831, n≥2) | — | sample size | take the percentile from A |
| D | `analytics.py::athlete_progression` | — | winner gap (~l.224-229) | — | keep (AI season table); not a user surface |
| E | `analytics.py::podium_gap` | — | P1/P3 per category (~l.391-405) | — | keep (AI peer stats); template for the batch mode |
| F | `race/ai/nodes/load_race_data.py` | — | winner gap (~l.147-153) | — | keep (AI only) |
| G | `history.py::build_history_points` | reuses A, gates at 5 | reuses A | reuses A | simplifies once A gates |
| TS | `frontend/src/lib/raceMetrics.ts` | normalizes a legacy snapshot; no raw computation | deltas between server points | — | delete once `ComparatorPanel` reads server points |

**Rationale**:
- Principle I (rule of three): there are 3+ copies of the same gap and 3 percentile formulas.
- SC-002 needs one source.
- A already serves the history table and the AI analyst context, so the fewest consumers change.

**Alternatives considered**:
- A new `race/metrics.py` module. Rejected: A is already the reference that `history.py` and the analyst use.
- Keeping B's interpolation where it lives and having A call B. Rejected: B is a chart builder, and the dependency would point the wrong way.

**Live bug found**: B exposes `percentile` without the n≥5 gate, so a 2-rider category shows a percentile on the evolution chart while the history table shows «sin dato». The unification fixes this and gets a regression test.

## R-02 Effect on the AI analyst and the golden eval

**Decision**: accept that the analyst's context line `- Percentil: N` and the season-table percentile column become time-based. Prompts stay unchanged.

**Evidence**: the analyst field block (`race/agents/analyst.py::_v3_field_block`, `_render_season_table`) reads A through `compute_metrics.py` (~l.378-385). The golden cases (`backend/evals/race_analyst/golden_v3/case_*.json`) embed metrics as static numbers, and `backend/tests/evals/test_race_analyst_eval.py` builds inputs straight from the JSON. The eval is therefore mechanically insulated, and SC-008 cannot move because of this change.

**Follow-up (out of scope)**: regenerate the golden fixtures so their percentiles match production semantics. File it in `docs/implementation-status.md` as an open item.

## R-03 Parrilla vs. the percentile denominator

**Decision**: «Parrilla» keeps A's definition (FINISHED + MINUS_LAPS, shown to both roles). A new `timed_finishers` field carries the percentile and median denominator. `HistoryPoint` already exposes that name, so the engine adopts it and the other consumers reuse it.

**Alternatives considered**: redefining `field_size` as timed finishers only. Rejected: it would silently change a published figure and break the glossary.

## R-04 Which "first place" the gaps use

**Decision**: «Brecha vs. 1.ª posición» and «Brecha vs. podio» reference the **official** 1st and 3rd positions, as A does today. The percentile references the **fastest and slowest times**. They differ only when the organiser's order does not follow time (penalties). The spec's glossary already separates the two concepts.

## R-05 Family surfaces that show the winner or podium gap today

| Surface | Evidence | 045 action |
|---|---|---|
| AI analysis card, `gap_to_p3_hhmmss` | `InsightV3Card.tsx` ~l.379-384 renders it with no mode check; `routers/athlete_race_analysis.py` parent redaction (~l.304-308) omits it | **Fixed now (phase 0b)** in backend redaction and frontend gate, with regression tests |
| Bitácora waypoint sublabel «±N% al P1» | `stage_log_builder.py` ~l.180-190 | switch to «Brecha vs. mediana» computed live from the engine at render time |
| Newsletter gap chart | `newsletter_builder.py` ~l.1460-1554 (`gap_pcts`) | same switch |
| Evolution chart and championship card | fixed in phase 0 (`audience` prop) | the merge keeps the gate |
| Family competition page | shows no gap today | adds only family-allowed metrics |
| History endpoint payload | `history.py` ~l.272 returns `gap_to_winner_pct` to parents; the family UI hides it, but it is in the response | W1: omitted from the parent payload server-side |

Newsletters read a **persisted** `metrics_snapshot` written by the AI pipeline. The switch applies to renders made after 045 ships; documents already sent are not rewritten.

## R-06 The FR-022 approval warning

**Decision**: compute it **server-side**. When the HITL payload for an athlete analysis is served to the coach, the backend scans the family-visible text fields for leader, winner, podium and 1st/3rd-place mentions and returns `family_gap_mentions: list[str]` (matched snippets, maximum 3). `HITLApprovalCard` shows a warning plus the existing «Rechazar»/revision path when the list is non-empty.

**Rationale**: the keyword list lives in one place and is testable with pytest. A frontend scan would duplicate it and drift.

**Alternative considered**: rewriting the text automatically. Rejected, because it changes AI output after the critic.

## R-07 The athlete «Carreras» tab

**Decision**: keep the tab key `races` for both roles and add `view=progresion|analisis|comparar` and `insight=<id>`.
- **Aliases:**
  - coach `?tab=ai_analysis` → `?tab=races&view=analisis`;
  - family `?tab=ai-analysis` → the same.
  - The existing `insight=` parameter is carried over.
- **Deep link:** `insight=<id>` feeds the `controlledInsightId` hook that already exists in `InsightsTimeline.tsx` (~l.366-379); today only `HeroLastInsightCard` uses it. Nothing reads `insight` today, although `RaceInsightEmailRedirect` already emits it.

**Component tree**:
- **Progresión**:
  - `HistoryProgressionCard` becomes the view shell, requesting `series_kind=all` (the endpoint already supports it, `history.py` ~l.123-169).
  - Cup points feed a `HistoryChart` extended with a metric selector (median default; the family subset is Brecha vs. mediana, Percentil and Puesto). It reuses `EvolutionChart`'s axis logic for signed and inverted metrics.
  - Championships render as `ChampionshipReadingCard`s, which are already audience-gated.
  - `HistoryTable` stays underneath. `EvolutionChart` is removed from the athlete tab once Progresión covers it; the evolution endpoint stays for `PanoramaView` KPIs and the comparator.
- **Análisis IA**: pending runs (`HITLApprovalCard`, `AnalysisRunTimeline`) → latest (`HeroLastInsightCard`, with the `PanoramaView` KPI cards folded into this header) → history (`InsightsTimeline`) → coach-only `LaunchAnalysisForm`, `AthleteAnalystChatPanel` and `SeasonSummaryButton`. The family label is «Análisis IA», with a line saying it was generated with AI and reviewed by the coach.
- **Comparar** (coach only): `DistributionChart` + `ComparatorPanel`. Remove the dead `viewMode="parent"` prop (`ComparatorPanel.tsx` ~l.230).

**Loading (FR-062, SC-007)**: one `React.lazy` chunk per view (lazy loading is already established four times in this area).
- Move `useAthleteInsights(latest)` and `useAthleteRuns`, which today fire on every mount of `AthleteAIAnalysisTab` (~l.196-239), into the Análisis IA chunk.
- Opening on Progresión then fires only the history query.

**History note**: feature 044 pulled the progression card *out* of «Insights IA» after a UX blocker ("data first"). 045 brings them into one tab with Progresión first, which satisfies the same principle. This is deliberate, not a regression.

## R-08 Per-import identity gate

**Decision**:
- **Rule**: an import is blocked only by pending candidates where `left_record.key` or `right_record.key` belongs to the set of record keys of this import's own rows.
- **Where the keys come from**: `load_identity_rows` plus `signature_triple`/discriminator, the same `record_key` that `identity_review.py` uses (~l.227-249, ~l.329-333).
- **Implementation pattern**: follow `remove_out_of_scope` (~l.984-1027), which already filters pending candidates in Python.
- **Call sites** that change: commit (~l.1223) and commit-pending (~l.1506) in `routers/race_imports.py`.
- **New competitors**: they have no `competitor_id` yet but have a key, so they are covered with no special case.
- **Candidates spanning two imports**: covered, because either side matching this import is enough (OR).

**No migration.** The response to a blocked commit changes from a bare 409 to one that includes `pending_for_import` and a link target (see contracts).

**Validation required**: `data-platform-lead` must confirm (a) that `record_key` is stable before commit, and (b) that fetching the pending set in Python is cheap at club scale. `data-privacy-guard` audits the invariant. A dedicated test covers "a candidate spans this import and another one".

### G2 verdict (2026-09-23)

Validated by `data-platform-lead` against the T021–T023 diff (`identity_review.py`, `routers/race_imports.py`), `tests/routers/test_race_imports_identity_gate.py` and the T022 additions in `tests/services/race/test_identity_review.py`. Lanes run: identity gate + identity review, 68 passed; neighbouring `test_race_imports.py` + `test_race_imports_history.py`, 91 passed. `pytest -m mysql` not run.

**(a) `record_key` stability and `base_key` matching — PASS-WITH-NOTES.**

What holds:
- **Key parity.** The gate's keys come from `row_triple` (the function `load_universe` now uses) over rows from `_reload_parsed_from_storage`, i.e. the same corrected rows `load_identity_rows` feeds the queue. The triple is a pure function of normalized (name, club, city), so it does not change between dry-run and commit unless a correction edits the row or the normalizer is redeployed in between. `test_import_record_keys_are_the_keys_of_the_queue_universe` pins the parity.
- **`base_key` is the safe direction.** The discriminator is derived from category sex/age/season and can appear or vanish between rebuilds (a triple becomes "split" when a second appearance arrives), so exact-key matching would under-block. Over-blocking is bounded: two people sharing a triple (parent/child) carry the same `base_key`, so a candidate on either blocks an import row with that triple — correct, because the row resolves through that same signature family and that candidate is exactly the open question. It is strictly narrower than the pre-045 global count.
- **`eligible_codes` scoping has no hole for RESULTS rows.** The ingestor only inserts eligible categories (`only_categories`); triples of pending categories are re-gated at `/commit-pending` (test (c) there covers it). An empty key set means no block, and such a file ingests nothing.

Notes (none blocks G2):
1. **GENERAL rows bypass the gate.** Ingestor step 5 upserts competitors from `general_by_category` through the same resolver for ALL categories (not filtered by `eligible_codes`/`only_categories`). Those triples are neither in the gate's key set nor in the identity universe (`load_identity_rows` drops GENERAL). The old global count covered them incidentally. Risk is low (exact-triple resolution; GENERAL-only new names never had queue candidates, a 044 gap) but it is a real narrowing. Follow-up: add `parsed_general` triples (`GeneralRow` has name/club/city) to the gate key set, or record it as accepted in the privacy audit. Test to add: a pending candidate whose only in-import side is a GENERAL-only row.
2. **Queue freshness vs. corrections.** `_identity_rebuild_needed` compares only the newest staged `imported_at` with the newest candidate `created_at`; `POST /corrections` (edit/add rows; `ResultsRowIn` carries name/club/city) bumps neither. If a rebuild ran after upload and a correction then edits or adds a row, that triple has no candidates until the next rebuild, so the gate passes. Pre-existing from 044, but under R-08 the gate is the only barrier. Suggested fix: also treat `max(corrections[*].at) > newest candidate created_at` as "rebuild needed" (the parse cache is keyed by `(sha256, len(corrections))`, so it is cheap). Test to add: queue up to date, `POST /corrections` adds a near-duplicate of a club-linked competitor, `/commit` must return 409 (today it would return 200).
3. **Test gap.** The router tests hand-seed snapshots with `ir.record_key(triple)` (and the 044 history tests seed `{"key": own_key}`), so a candidate persisted by a real `rebuild` is only covered through the `load_universe` subset test. Add one end-to-end test: club-linked competitor + staged near-duplicate row, no seeding → 409 → decide → 200. Also add a `/commit` (not only `/commit-pending`) test with a candidate about a row that exists only in a gap category → 200; "partial commits proceed" is implemented but not exercised.
4. A stale pending candidate on a pre-correction triple no longer blocks — correct, since that row is gone — and lingers harmlessly until decided or pruned.

**(b) Python-side filtering and club scoping — PASS.**
- **Scale.** Only `state = 'pending'` rows are read (`ix_race_identity_candidates_state`); the queue is bounded by `in_club_scope` (at least one club-linked side) and `remove_out_of_scope` prunes never-decided out-of-scope rows, so it is tens to low hundreds of small JSON rows. Negligible next to the gate's real cost (SFTP download + parse). Same pattern as `remove_out_of_scope`. Revisit (denormalized `base_key` columns) only if pending exceeds a few thousand.
- **Club scoping.** `race_identity_candidates` has no `club_id` and `race_identity.py` has no club logic, so the queue is global. Scoping comes from the import (`_load_pending_import` → club access) plus the key intersection, which is strictly narrower than before; a cross-club effect requires a shared normalized triple. The 409 body and the log line carry only `parse_id` and counts (no names), so privacy holds.

**Contract coupling (not a G2 blocker).** The flat 409 replaces `{detail: {code: "identity_review_pending", ...}}`. The frontend still keys on the old code (`ImportWizard.tsx` ~l.310/325, `HistoricalLoadPage.tsx` ~l.155, `raceImportsHistoryHandlers.ts`, `raceImports.types.ts`) until T054, so the wizard degrades to a generic error in the meantime. Stale docstrings still name the old code in `race_identity_candidate.py`, `identity_resolver.py` and `test_race_imports.py`. Grep for `identity_review_pending` when T054 lands.

### Follow-up (2026-09-23): notes 1–3 closed

The owner chose to close both gaps rather than record them as accepted.

- **Note 1 (GENERAL).** The gate keys and the identity universe now both include GENERAL. `identity_review.import_record_keys(rows, general_by_category)` unions the GENERAL triples of every category (the ingestor resolves competitors from all of them), and `_identity_gate` passes `parsed_general` at `/commit` and `/commit-pending` (both re-feed GENERAL to the ingestor). For candidates to exist before the commit, `load_identity_rows` now returns `ImportRows(results, general)` (a plain `Mapping` is still a valid `RowsLoader` result) and `load_universe` adds a **GENERAL-only** triple — one not in any staged RESULTS row and with no signature — as a record with a single appearance. Three deliberate choices: (1) that appearance uses `GENERAL_VALIDA_NUM = 0`, because GENERAL is the season accumulation and not a válida: with the real válida number `_shared_valida` would treat the near-duplicate and the athlete who raced that válida in the same category as two people and switch off the exact candidate the gate looks for (pinned by `test_general_appearance_is_never_a_valida_shared_with_the_results`); (2) triples already present through RESULTS or a signature get no extra appearance, since a different category would split one person into two; (3) an import already `committed` (partial) contributes no GENERAL, because its GENERAL competitors were created at the first commit and enter through their signature. Unknown-category GENERAL rows are conservatively included in the gate keys (the ingestor only warns and skips them); over-blocking is bounded to that data anomaly.
- **Note 2 (corrections).** `_identity_rebuild_needed` takes `latest_correction_at` (the newest `parse_meta_json["corrections"][*]["at"]` of the import being committed, normalised to naive UTC) and reports "rebuild needed" when it is later than the newest candidate `created_at`. Only this import's corrections count: the gate only looks at its own rows. Known cost, same as the pre-existing `imported_at` rule: if the rebuild yields no new candidate, `max(created_at)` does not move, so a later commit of the same import rebuilds again (bounded to that import; a persistent "last rebuild" marker would need a migration and was not added).
- **Note 3 (tests).** `tests/routers/test_race_imports_identity_gate.py` now covers: near-duplicate of a club athlete with a real rebuild (409 → decide → 200), the same via a GENERAL-only row, a `/commit` with a candidate on a row that exists only in a gap category (200, `pending_categories` kept), a correction adding a near-duplicate after the queue was up to date (409), a harmless correction (200), a queue newer than the last correction (no rebuild), and the `/commit-pending` GENERAL case. Service-level GENERAL tests live in `tests/services/race/test_identity_review.py`.

Also in this pass: `GET /api/race-analysis/imports/{id}` returns `parent_committed_at` (see contracts/api.md), so the resumed wizard shows the date in the revision notice instead of «—».

## R-09 Resumable imports

**Decision**:
- **Rehydrate**: add `GET /api/race-analysis/imports/{import_id}`, returning the status and `parse_meta_json` needed to rebuild the wizard. `ImportWizard` reads `?import=<id>` and resumes at the step implied by the status: `pending` → review, `dry_run` → confirm. Today the wizard deliberately does not persist anything (`ImportWizard.tsx` ~l.15, DT-5).
- **Discard**: add `POST /api/race-analysis/imports/{import_id}/discard` and a new `RaceImportStatus.discarded`. This needs **one Alembic migration**: an enum value added on `race_imports.status`, with a downgrade that maps `discarded` → `failed`. The current single head is `b4e8d2f61a93`; re-check with `alembic heads` first.

**Alternative considered**: reuse `failed` for discards. Rejected, because the inbox would then show abandoned imports as errors.

## R-10 «Cargas e identidades»

**Decision**: one page at `/competitions/imports` with sections `?seccion=cargas|identidades|sin-enlazar`.
- It reuses the bodies of `HistoricalLoadPage` (imports list plus identity summary), which is already the closest prototype, `IdentityReviewPage` and `UnlinkedCompetitorsPage`.
- The old routes redirect: `/competitions/history`, `/competitions/identity-review` and `/competitions/unlinked`.
- **Menu badge**: `CoachSummaryOut` gains `identity_decisions_pending`, `imports_in_progress` and (convergence T081) `unlinked_competitors_pending`, counted with the same predicate as the «Sin enlazar» list. `useNavBadges` shows the sum of the three on «Cargas e identidades», so there are no extra requests.

## R-11 Home «Pendientes» and stale analyses

**Decision**:
- **New counts**: `CoachSummaryOut` gains `analyses_awaiting_approval`, computed like `compute_insights_stale` (`dashboard_summary.py` ~l.122-165) as `AgentRun.status == awaiting_hitl` joined to the club's athletes. It also reuses `identity_decisions_pending` from R-10.
- **New rows**: «Identidades por decidir» → `/competitions/imports?seccion=identidades`; «Análisis por aprobar» → the analyses list (below).
- **Analyses list**: stale and awaiting-approval analyses are listed in **«Temporada»**, at `/competitions/season/:year?analisis=por-aprobar|desactualizados`. The stale row already pointed to the season page, so this fulfils its original intent without a fourth section (FR-005).
- **Actions**: re-run uses the existing launch. **Dismiss** is new, `POST /api/race-analysis/runs/{run_id}/dismiss-stale`, wrapping `run_staleness.mark_run_fresh` with an audit event.

**Alternative considered**: a fourth «Análisis» section. Rejected by FR-005.

## R-12 Competition detail tabs

**Decision**: merge `ConditionsTab` and `race/course/CourseTab` into one tab, «Circuito y condiciones» (`?tab=circuito`), with `?tab=conditions` as an alias. The other tabs stay as they are. «Clasificación» shows only for cup válidas.

## R-13 Vocabulary and touch targets

**Decision**:
- **Vocabulary**:
  - «Válidas» → «Competencias» (`navigation.ts` ~l.133, `UnlinkedCompetitorsPage.tsx` ~l.24, `CompetitionsListPage.tsx` ~l.135, `SeasonInsightsPage.tsx` ~l.91).
  - «Editar metadata» → «Editar datos» (4 hits).
  - «Crítico LLM dice» → «Revisión automática» (`HITLApprovalCard.tsx` ~l.207).
  - Priority codes are spelled out through one label map.
  - «Perdió vueltas» becomes the single label for `minus_laps` (phase 0b).
- **Touch targets**: «Editar»/«Rechazar» on `HITLApprovalCard` (~l.263/273) and the competitions header buttons get `min-h-12`. The shadcn default is 44 px and `sm` is 36 px. The size is overridden on these surfaces only, not by changing the global button.

## R-14 Communication to families (FR-023)

**Decision**: reuse the bitácora `coach_note` (`stage_log.py` ~l.320-334, 600 characters or fewer, with EMPTY/HIDDEN/EDITED states). The coach's bitácora editor offers a one-click «Insertar aviso de cambios» that pre-fills a drafted note (Spanish copy in `contracts/ui-copy.md`). The coach edits it and publishes. Nothing is sent automatically. The offer stays until the coach inserts or dismisses it.

## R-15 Tests and verification lanes

- **Unit**: about 14 frontend files are keyed on tab identifiers, about 26 `athletes/ai/__tests__` suites are affected by re-homing, and `aiIdentityRenameSweep.test.ts` guards the component name.
- **Backend**: the tests of the engine, evolution, history, race imports, the dashboard summary, the dispatcher and the redaction are affected. Around 105 files reference metric symbols; that is an upper bound.
- **E2E**: `ai-insights-coach|parent|hitl|newsletter.spec.ts`, `race-analysis-championship.spec.ts`, `race-history.spec.ts`, `race-course.spec.ts`, `prefill-import-from-competition.spec.ts`, and `target-size.spec.ts` (~l.1054-1201, one 48 px sweep per sub-tab). `competitions-unification.spec.ts` describes older 410 behaviour and must be checked for staleness before it is reused.
- **Pre-existing, not caused by 045**:
  - a frontend failure in `SessionWizardRouteNotify.test.tsx`, which appeared during the concurrent token migration;
  - an ImportError in `tests/test_langchain_provider.py` (`ModelError` missing from `langchain_core.exceptions`);
  - a known failure in `test_invariants_v2.py::test_resolve_age_*`.
  
  All three are recorded and left as they are.
- **Deferred real-infrastructure lanes**: `pytest -m mysql` (the new migration's upgrade and downgrade), `pytest -m golden`, Playwright, and the LCP measurement on a device. They must be reported as not run if they are not run.
