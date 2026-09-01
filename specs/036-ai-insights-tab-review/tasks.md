---
description: "Task list for feature 036 — AI Insights tab full-stack review"
---

# Tasks: AI Insights Tab — Full-Stack Review

**Input**: `specs/036-ai-insights-tab-review/spec.md` and `plan.md`

**Tests**: Included and mandatory. Constitution Principle II is non-negotiable, and this feature exists partly because the existing suite failed to catch these defects. Each story carries the test that would have caught its bug.

**Note**: the AI-consent gate for `POST /runs` and `POST /season-summary` (a confirmed critical finding — see `spec.md` Evidence base) is tracked outside this feature at the user's request. No task in this file implements it, and no task below depends on it.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel — different files, no dependency on a sibling task
- **[Story]**: which user story the task serves

---

## Wave 1 — Correctness (US3, US4). T010–T015 and T020–T027 are independent of each other.

### State isolation (US3)

- [X] T010 [US3] Add `key={athlete.id}` to the `<AthleteAIAnalysisTab>` mount at `frontend/src/routes/athletes/AthleteDetailPage.tsx:888`.
- [X] T011 [US3] Integration test that fails before T010: mount the tab with athlete A, select insights, start a run, rerender with athlete B, assert selection empty, no run timeline, no HITL card, and no detail request for A's insight ID. Must mount the real subcomponent tree — mock only the network via MSW.
- [X] T012 [US3] Clear `activeRunId` on run completion in `frontend/src/components/athletes/ai/AthleteAIAnalysisTab.tsx:165-169`; today it is never set back to `null`, leaving a completed timeline pinned above the sub-tabs indefinitely.
- [X] T013 [US3] Fix the `useEffect` at `AthleteAIAnalysisTab.tsx:129-136`: it depends on the whole `attachMutation` object, which TanStack Query v5 recreates every render, so the 3-second success timer restarts on every poll tick and the confirmation never clears while a run is active. Depend on `attachMutation.isSuccess` and a stable `reset` reference.
- [X] T014 [US3] Fix the HITL derivation at `AthleteAIAnalysisTab.tsx:171-191`: `showHITL` derives from an accumulated event array that is never purged and whose resolved interruption is never superseded, so the approval card can persist after the coach has decided. Memoise `lastHitlEvent` while fixing it.
- [X] T015 [P] [US3] Unit tests for T012–T014 in the tab's own test file, mounting the real `AnalysisRunTimeline` and `HITLApprovalCard` rather than the current mocks.
- [X] T016 [US3] Backend: reconcile orphan runs at startup in `backend/app/main.py` lifespan — mark rows in `running`/`awaiting_hitl` older than a threshold as failed with an explanatory `error_message`. The run registry in `services/race/ai/runner.py` is in-memory and Render redeploys on every push to `main`.
- [X] T017 [P] [US3] Add a hard client-side polling ceiling in `frontend/src/hooks/ai/useRaceRun.ts` so a run that never reaches a terminal state surfaces as "not responding" rather than polling forever.
- [X] T018 [P] [US3] Tests for T016 and T017.

### Failed analyses are marked (US4)

- [X] T020 [US4] Add an explicit `is_fallback` discriminator to `backend/app/models/athlete_ai_insight.py` (do not sniff the markdown string). Note there is already an indirect signal: fallback output leaves `sections` empty, and `backend/app/services/race/ai/nodes/critic_agent.py:136` uses exactly that to force low confidence. But low confidence also arises for other reasons, so the coach cannot distinguish a failure from a real analysis with incomplete data — hence an explicit field.
- [X] T021 [US4] Alembic migration for T020. Verify there is no second head before generating — feature 007 left `e5f6a7b8c9d0` dangling per `docs/implementation-status.md`.
- [X] T022 [US4] Set the discriminator in `backend/app/services/race/ai/fallback.py` for both `deterministic_fallback` and `deterministic_fallback_n1`. Note these are different cases: the N=1 variant is a legitimate analysis under the N=1 rule, not a failure — mark only the failure path.
- [X] T023 [US4] One-off backfill for existing rows matching the known fallback text (a compile-time constant at `fallback.py:19-22`, so matching is safe here).
- [X] T024 [US4] Expose the discriminator through the insight schema and TS type.
- [X] T025 [US4] In `frontend/src/components/athletes/ai/InsightsTimeline.tsx`: render failed rows visually distinct and labelled, suppress the newsletter checkbox, and offer a retry action.
- [X] T026 [P] [US4] Guard the attach path in `backend/app/routers/athlete_monthly_newsletters.py` so a failed-analysis row cannot be attached even if the client sends its ID. Client-side suppression alone is not sufficient.
- [X] T027 [P] [US4] Tests: fallback row renders marked, cannot be selected, is rejected by the attach endpoint, and the retry action starts a new run.

---

## Wave 2 — Truth on screen (US5).

- [X] T030 [US5] Migrate the AI insight payload off the retired `valida_num === 99` convention onto `event_id` + `race_series.kind`, following what features 014/016 did for the rest of the system. This is the shared root cause of T031 and T032. Backend schema plus `frontend/src/lib/insights.ts:110-115`.
- [X] T031 [US5] Make each race uniquely identifiable in the launch picker (`LaunchAnalysisForm.tsx`) — two Departmental Championships currently render as two identical `CD` chips with no date.
- [X] T032 [US5] Collapse `validaLabel` (`lib/insights.ts:110-115`) and `getValidaLabel` (`lib/raceCalendar.ts:149-160`) into one helper; adopt the roman formatting already used by `MiniSparkline`. Update all call sites.
- [X] T033 [P] [US5] Order the history by race date rather than generation timestamp, and show the race date; today the list reads Válida 1 → Resumen → Válida 4 → Válida 3 → Válida 2. `InsightsTimeline.tsx` plus the ordering in `backend/app/services/race/insights_history.py`.
- [X] T034 [P] [US5] Reconcile the header counters: "Último análisis: Válida 1" sits beside "7 válidas completadas / 5 análisis aprobados" with nothing explaining the gap. Either label the header by race date or surface which válidas are unanalysed.
- [X] T035 [P] [US5] Default the Distribution selector to the most recent race so the sub-tab opens with data instead of the "select a race" placeholder (`DistributionChart.tsx:158-218`).
- [X] T035b [US5] Remove the internal backlog note rendered in production at `frontend/src/components/athletes/ai/PanoramaView.tsx:149` — the third KPI card ships with `note="Podios: TODO Sprint 3"`, visible to coaches **and to parents**. Either drop the note or replace it with user-facing wording; the KPI itself is unimplemented pending a backend field (`:133`).
- [X] T035c [P] [US5] Fix the gendered empty state at `frontend/src/components/athletes/ai/HeroLastInsightCard.tsx:75` — "Cuando se aprueben análisis de tu hijo" assumes the child's gender in the parent-facing view.
- [X] T036 [US5] Correct the false claims at `DistributionChart.tsx:155` (subtitle) and `:5-6` (docstring), which promise pseudonymisation that does not apply to the coach path.
- [ ] T037 [US5] Take Open Question 2 to the club: whether to keep other clubs' minors named in the Distribution chart, pseudonymise all but the athlete in question, or make it configurable. Implement whatever is decided. **Do not implement before the decision.**
- [X] T038 [P] [US5] Add `isError` handling to all three queries in `frontend/src/components/athletes/ai/ComparatorPanel.tsx` (only `isLoading` exists today, at `:203` and `:479`) — a failed query currently renders nothing at all.
- [X] T039 [P] [US5] Adopt the shared `components/shared/ErrorState.tsx` across the tab's error blocks. It carries the cold-start variant the project requires for Render's ~50 s wake, which the tab's hand-rolled red boxes do not.
- [X] T040 [P] [US5] Fix `SeasonSummaryResponse` in `frontend/src/api/athleteRaceAnalysis.ts:111-125`, which declares `run_id`/`status`/`started_at` that the backend never sends; the real response carries `insight_id` and `summary_text`. Use `insight_id` to deep-link to the new insight, and correct the misleading "Resumen en proceso" copy — the call is synchronous and already finished.
- [X] T041 [P] [US5] Populate `stale_run_id` in `ClubInsightByRaceItem` or remove the field and its UI. The frontend built a "stale analysis" badge around a field the backend never sets, so the badge has never rendered. Decide which way, then do it fully.
- [X] T042 [P] [US5] Extract a single `invalidateAthleteAiQueries` helper. The same decision is implemented three ways today: `AthleteAIAnalysisTab.tsx:150-161` misses `club-insights-by-race` and `season-panorama`, `useAthleteRunOutcome.ts:69-80` includes them, and `useRaceRun.ts:240-249` has the first gap again. Replace the `startsWith("athlete-")` predicate with an explicit key list — it currently also invalidates Strava and newsletter queries.
- [X] T043 [P] [US5] Add a guard to `POST /runs` rejecting a launch when a run is already active for the same athlete and válida; the group-launch flow already models this outcome and it can be reused.
- [X] T044 [US5] Acquire the deduplication lock in `POST /season-summary` **before** invoking the LLM, not after (`athlete_race_analysis.py:1002-1076`). Today a double submit runs the pipeline twice and the loser hits a unique constraint and returns a generic 500, having already spent budget. Catch `IntegrityError` and return 409.
- [X] T045 [P] [US5] Use the backend's `detail` in `LaunchAnalysisForm.tsx:143-146`; because `AxiosError` extends `Error`, the current code shows "Request failed with status code 409" instead of the specific message the backend carefully provides. `SeasonSummaryButton.tsx:30-47` already has the right helper — extract and reuse it.
- [X] T046 [P] [US5] Tests for T030–T045.

---

## Wave 3 — Analysis quality (US2). T050–T052 are hard prerequisites for everything after them.

### Make the eval see production first

- [X] T050 [US2] Point the golden eval at the pipeline that actually runs. `backend/tests/evals/test_race_analyst_eval.py:173` calls `agent.invoke` (the v1 method, five-section prompt); production calls `invoke_per_valida` against v2. Migrate the runner and update `_CANONICAL_SECTIONS` in `backend/app/services/race/eval/scorer.py:41-60` from the five v1 sections to the three v2 sections — today they are structurally incompatible, so the structure sub-score would fail on schema mismatch alone.
- [X] T051 [US2] Change the CI matrix in `.github/workflows/race-eval.yml:53-54` from `google`/`gemini-2.5-flash-lite` to the production default `anthropic`/`claude-sonnet-5` (`config.py:112`, `_llm.py:33`). Update the skip-guard at `test_race_analyst_eval.py:122-129`, which only looks for `RACE_AI_API_KEY`/`GOOGLE_API_KEY`.
- [X] T052 [US2] Add eval sub-rubrics that **fail on today's output**: (a) repeated-figure detection — the same time or gap appearing in two separate sentences of Section 1; (b) analytical connectors — require at least one relational construction per section as a cheap proxy for "not a checklist"; (c) a negative assertion that the lap muletilla never appears when no lap field is present.
- [X] T053 [P] [US2] Add a golden case with `season_comparative` populated (2+ válidas) to exercise the path where history *is* available. The current ten cases are mostly single-válida or aggregate, so the rich-analysis path is never evaluated.

### Then fix the causes

- [X] T054 [US2] Rewrite Section 1 of `backend/app/services/race/prompts/race_analyst_v2.md:43-48` to require synthesis instead of enumeration: combine at least two data points per idea, forbid restating a figure in consecutive sentences, and forbid the lap sentence outright when no lap datum exists. Widen the permitted verb list beyond the current five without reintroducing evaluative judgement. The audit supplied a ready-to-paste draft.
- [X] T055 [US2] Resolve the lap contradiction at its source: `race_analyst_v2.md:44` requires "número de vueltas completadas" but no lap field exists in `backend/app/services/race/schemas.py` (grep for `lap` returns nothing). Either add the real field to `AnalysisInput` or drop the instruction. Do not leave the model required to produce a datum it does not have.
- [X] T056 [US2] Add a contrastive few-shot block (one checklist-style "bad", one interpretive "good") to `race_analyst_v2.md`. Neither prompt version has a single example today, which is the largest single gap in the prompt.
- [X] T057 [US2] **Verify how `is_first_in_season` is computed for single-válida launches** (`backend/app/services/race/ai/nodes/analyst_agent.py:184`, and whether `full_season_results` is populated in `load_race_data`). The N=1 rule at `race_analyst_v2.md:220-245` forbids all cross-race comparison when that flag is true; if it is wrongly true on every individual launch, no prompt change will produce comparison. Do this before T054 ships, not after.
- [X] T058 [P] [US2] Confirm the prompt's tone constraints for minors are intact after the rewrite: no body judgement, no diagnostic language. The audit rates this as the current prompt's strongest point — do not regress it.
- [ ] T059 [US2] Re-run the golden eval; the composite must clear the 0.75 gate with the new sub-rubrics included.

### Provenance and configuration

- [X] T060 [US2] Fix `backend/app/services/race/ai/nodes/persist_insight.py:359,417`, which writes `model="gemini-2.5-flash-lite"` hardcoded into `AthleteAiInsight.model` regardless of which provider generated the analysis. With Anthropic as today's default, **every insight row in the database misreports its own provenance**, which defeats any attempt to correlate output quality with model. Trivial fix, high value for the rest of this wave.
- [X] T061 [P] [US2] Sync the stale Google default at `_llm.py:34` (`gemini-2.5-flash-lite`) with the model documented as active in `pricing.py:17-19`.
- [X] T062 [P] [US2] Verify the budget guard (`race_ai_budget_usd_30d=20.0`, `config.py:130`) is calibrated for Anthropic rather than the legacy Gemini rates — Anthropic is roughly ten times more expensive per token and v2 issues up to five calls per analysis.
- [X] T063 [P] [US2] Add a non-blocking "enumeration without analytical connection" quality rule to `race_critic_v2.md`, visible in `metrics_snapshot_json.critic_verdict`. The critic is correctly not the cause here, but it could become the safety net.
- [X] T064 [P] [US2] Resolve Open Question 5: either implement Langfuse or correct `CLAUDE.md`, which describes observability that does not exist (only occurrence is a docstring string at `backend/app/models/agent_run.py:22`).
- [X] T065 [US2] Confirm whether the HITL sqlite checkpoint at `./data/langgraph_state.sqlite` survives a Render deploy. The checkpointer is on disk, so decisions survive a restart in principle — but Render's free tier filesystem is ephemeral, which would silently lose pending HITL decisions.

## Wave 4 — Devices and accessibility (US6). Independent of waves 1–3; can be pulled earlier.

- [X] T090 [US6] Make sub-tab overflow discoverable at 360–400 px in `AthleteAIAnalysisTab.tsx:291`; the scrollbar is hidden by design, so "Analizar con IA" is currently unreachable without guessing the swipe.
- [X] T091 [P] [US6] Raise sub-48px targets to the floor, using the pattern feature 032 already proved: the race chips at `LaunchAnalysisForm.tsx:311` are `min-h-9` (36 px) against the `MIN_TARGET_SIZE = 48` fixed at `frontend/e2e/target-size.spec.ts:44`; the history checkboxes and the "Modo explicativo" checkbox are also below it.
- [X] T091b [US6] Add `/athletes/:id?tab=ai_analysis` to the touch-target sweep. `frontend/e2e/target-size.spec.ts` currently visits only `/training/sessions/:id`, `/competitions/:id?tab=results`, `/dashboard` and `/training/sessions` (`:633,658,677,722`) — this tab has never been measured, which is why T091's violations survived. Include the comparator sheet open state.
- [X] T092 [P] [US6] Move the "Modo explicativo" checkbox next to its label; at desktop width it sits at the far right edge, visually detached from the text it governs.
- [X] T093 [P] [US6] Add `role="status"` / `aria-live` to the sticky newsletter bar (`AthleteAIAnalysisTab.tsx:396-460`), whose state changes are announced to nobody today.
- [X] T094 [P] [US6] Add `axe()` coverage for `HITLApprovalCard` in resting and dialog-open states — a dialog-bearing component with no accessibility check in any test file — and for `InsightsTimeline.v2.test.tsx`.
- [X] T095 [P] [US6] Give `PanoramaView` and `InsightsTimeline` real headings; both use an `aria-label` on a `div` while the other three sub-views have `<h3>`, so heading navigation loses the user in two of five.
- [X] T096 [US6] Lazy-load the tab from `AthleteDetailPage.tsx:26`, following the `lazy()` pattern the same file already uses for the Progreso tab at `:57-66`. Today `recharts` enters the bundle on every athlete profile visit even if the tab is never opened.
- [X] T096b [US6] Apply the microcopy rewrites from the UX audit. Highest-value items: the coach subtitle "Pipeline agéntico: análisis, comparaciones y proyecciones…" (`AthleteAIAnalysisTab.tsx:210`) → "Análisis generado con IA a partir de los resultados oficiales de carrera."; the parent subtitle (`:207-209`) → "Resumen del rendimiento en carreras, revisado por el entrenador antes de publicarse."; "Modo explicativo / El agente pausará…" (`LaunchAnalysisForm.tsx:246-253`) → "Revisión paso a paso / El análisis se detendrá en cada etapa para que lo apruebes antes de continuar."; "Máximo 4 por lanzamiento" (`:270-273`) → "Máximo 4 a la vez". "Insight" and "confianza" are already correctly kept off the parent surface.
- [X] T096c [P] [US6] Decide how "válida" reads for parents. It appears unexplained in the parent view (`HeroLastInsightCard.tsx:96` and badges throughout); a parent has no reason to know it means a Copa Valle round that counts toward the season ranking. Either a first-use tooltip or "Carrera N" on the parent surface with "Válida N" reserved for the coach.
- [X] T097 [P] [US6] Fix the visual hierarchy of "Releer último" and "Regenerar": two primary-weight buttons compete in one card. Note the turquoise itself is **correct** — it is the product's primary brand colour (`frontend/src/style.css:36`, documented at `frontend/src/components/ui/button.tsx:11`), not an off-palette accent. Demote the secondary action, do not recolour both.
- [ ] T098 [US6] Collapse five sub-tabs into three, per the UX audit: **Resumen** (Panorama and Histórico merged — Panorama already shows the latest insight in full, so the two overlap heavily), **Rendimiento** (Evolución and Distribución merged behind an internal toggle, with the comparator as a control rather than a separate sheet), and **Analizar con IA**. This partially reverts BB3: its removal of the comparator from the tab list stands, but the Evolución/Distribución merge was never decided in any spec. Feature 029 set the subtraction precedent. Note the parent sees only three sub-tabs today and suffers the same Panorama/Histórico redundancy with none of the extra data that might justify it.

---

## Wave 5 — End-to-end safety net (US7). Last, because it asserts against fixed behaviour.

- [X] T070 [US7] E2E: coach happy path — enter the tab, Panorama with KPIs, each sub-tab, open and close the comparator sheet.
- [X] T071 [US7] E2E: launch → run timeline → HITL card → approve → new insight appears in history. This is the module's central business flow and has no e2e today. Use `AI_ENABLED=false` for the fake provider.
- [X] T072 [P] [US7] E2E: parent path — Distribución and "Analizar con IA" absent from the DOM, no newsletter checkboxes, data filtered to their own child.
- [X] T073 [P] [US7] E2E: HITL reject and HITL edit — the two decisions with no unit coverage either.
- [X] T074 [P] [US7] E2E: newsletter sticky bar end to end, ending at the athlete's newsletter actually containing the insights.
- [X] T075 [P] [US7] E2E: switching athletes with the tab open (the US3 regression, at the outermost level).
- [X] T076 [P] [US7] Backend: admin-role tests for the 6 endpoints that lack them — insights, insight detail, runs GET and POST, distribution, evolution.
- [X] T077 [P] [US7] Backend: parent-with-someone-else's-child denial tests for `/distribution` and `/evolution`, the two endpoints missing that case.
- [X] T078 [P] [US7] Unit: the 304-Not-Modified branch, event dedupe by `seq`, and `resetEvents` in `hooks/ai/useRaceRun.ts` — all uncovered.
- [X] T079 [P] [US7] Unit: the full "Editar" flow in `HITLApprovalCard` (open dialog, type, save, cancel). Today `HITLApprovalCard.test.tsx:38-49` only asserts the button exists, so deleting its `onClick` at `:188` would leave the suite green.
- [X] T080 [P] [US7] Integration: Panorama → open detail → History with the insight preselected. The composition is never exercised because the tab's tests mock `PanoramaView`.
- [X] T081 [P] [US7] Remove the obsolete `xfail` markers on the two now-passing tests in `backend/tests/services/race/ai/test_persist_insight_per_valida_v2.py`, after confirming the contract really is implemented.
- [X] T082 [P] [US7] Decide whether `useRunResult`, `useInvalidateRun` and `resetEvents` in `useRaceRun.ts` — none used by any component — get wired up or deleted. Same question for `PdfDownloadButton`, which is integrated nowhere.

---

## Dependencies

- **T011** must be written to fail before T010 lands.
- **T024, T025** depend on T020–T022.
- **T031, T032** depend on T030.
- **T037** is blocked on a club decision; do not start it speculatively.
- **T053–T055** depend on T050 and T051.
- **T098** depends on the UX audit.
- **Wave 5** depends on waves 1–4 for the behaviour it asserts.

## Deliberately deferred

Decomposing the oversized components — `ComparatorPanel.tsx` (958 lines), `InsightsTimeline.tsx` (806), `DistributionChart.tsx` (661) — is real and documented technical debt, but it is refactoring without a user-visible defect attached. Doing it inside this feature would mix behavioural fixes with large mechanical diffs and make review harder. It belongs in its own feature, ideally after wave 5 gives it a test net to refactor against.
