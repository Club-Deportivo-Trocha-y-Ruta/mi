# Competitions in one place (feature 045) — Reference

Status as of 2026-09-23: Wave 1 (metrics engine) is committed (`71eb816`). Waves 2–5 (imports and pending work, athlete «Carreras» tab, «Competencias» area, family copy) and the owner-decision follow-ups are implemented and uncommitted. Phase 8 is in progress (deferred lanes T069–T072 open). The owner decisions of 2026-09-23 are resolved; five items stay open (see [Open items](#open-items)).

Spec, plan, research, data model and contracts live in `specs/045-competitions-one-place/`. This document is the stable reference: what the area looks like, what each label means, how each metric is computed and who may see it, and which old addresses still work. It does not repeat the design rationale; follow the links.

## 1. Area map

### 1.1 Coach menu

One menu area, «Competencias», with three sections (spec FR-005). No race page is orphaned.

| Section | Address | Content |
|---|---|---|
| Competencias | `/competitions` | Competitions list (season and filters in the URL) and each competition's detail |
| Temporada | `/competitions/season/:year` | Season panorama plus the analyses lists (`?analisis=por-aprobar\|desactualizados`) |
| Cargas e identidades | `/competitions/imports` | One inbox with sections `?seccion=cargas\|identidades\|sin-enlazar` |

The «Cargas e identidades» menu badge is `identity_decisions_pending + imports_in_progress`, read from `GET /api/dashboard/coach-summary` (no extra requests).

### 1.2 Competition detail (`/competitions/:id`)

| Tab (`?tab=`) | Label | Notes |
|---|---|---|
| `info` | Información | — |
| `results` | Resultados | Per-row Parrilla, Percentil and Brecha vs. mediana; coach also sees Brecha vs. 1.ª posición and Brecha vs. podio |
| `standings` | Clasificación | Cup válidas only; hidden for championships |
| `circuito` | Circuito y condiciones | Course profile and race conditions in one tab (was two) |
| `insights` | Análisis IA | Coach only |

### 1.3 Athlete «Carreras» tab

One race tab for coach and family (`?tab=races`), replacing «Insights IA» and the previous «Carreras».

| View (`&view=`) | Label | Coach | Family |
|---|---|---|---|
| `progresion` (default) | Progresión | All seasons, cup line with category-change markers, championship cards, metric selector (default «Brecha vs. mediana») | Same, metrics limited to Brecha vs. mediana, Percentil and Puesto |
| `analisis` | Análisis IA | Pending approval first, then latest approved, then history; launch form, analyst chat and season summary live here | Approved analyses only, each labelled as AI-generated and reviewed by the coach |
| `comparar` | Comparar | Distribution chart and comparator | Not available; falls back to `progresion` |

`&insight=<id>` forces `analisis` and expands that analysis. Each view is a separate lazy chunk, so first paint on Progresión fires only the history request (FR-062).

### 1.4 Home «Pendientes» (coach)

Each row lands on a screen that lists exactly the items it counted (FR-041, SC-005). A `null` count omits the row; it is never shown as zero.

| Row | Count field (`CoachSummaryOut`) | Destination |
|---|---|---|
| Results to import | existing | `/competitions?filter=needs-results` |
| Identity decisions | `identity_decisions_pending` | `/competitions/imports?seccion=identidades` |
| Analyses to approve | `analyses_awaiting_approval` | `/competitions/season/:year?analisis=por-aprobar` |
| Stale analyses | `insights_stale` | `/competitions/season/:year?analisis=desactualizados` (offers re-run or dismiss; a season summary re-runs through `season-summary` for its own season, a válida through `runs` with its `event_id`) |

## 2. Glossary

Product copy stays in neutral Colombian Spanish. Source of truth: `specs/045-competitions-one-place/contracts/ui-copy.md`.

| Term | Meaning | Field |
|---|---|---|
| Competencia | Any race event | — |
| Válida | A numbered round of a cup | — |
| Campeonato | A standalone race, never compared with válidas (`race_series.kind = championship`) | — |
| Parrilla | Classified finishers of the category, including riders who lost laps | `field_size` |
| Puesto | Official finishing position | `position` |
| Percentil | Time-based standing between the fastest and slowest full-distance times of the category (100 = fastest) | `percentile` |
| Brecha vs. mediana | Percentage difference to the category median time; negative = faster | `gap_to_median_pct` |
| Brecha vs. 1.ª posición | Percentage over the official winner's time. Coach only | `gap_to_winner_pct` |
| Brecha vs. podio | Percentage over the official third-placed time. Coach only | `gap_to_podium_pct` |
| Carreras | The single athlete race tab | `?tab=races` |
| Temporada | Season panorama section | — |
| Cargas e identidades | Import and identity inbox | — |
| ¿Es la misma persona? | A coach-reviewed identity decision | `race_identity_candidates` |
| Revisión automática | The AI critic's line on the approval card (was «Crítico LLM dice») | — |

Statuses shown to families are words, never codes: «No terminó» (`dnf`), «No salió» (`dns`), «Descalificado» (`dsq`), «Perdió vueltas» (`minus_laps`).

Retired everywhere: «Válidas» as an area name, «Gap al P1», «Diferencia al podio», «Pelotón», «Insights IA» as a tab name, «Editar metadata» (now «Editar datos»).

## 3. Metric definitions and gates

One engine computes every metric: `backend/app/services/race/field_metrics.py`. No screen, chart, newsletter or AI context computes its own version (FR-020, FR-021). Design and rejected alternatives: `specs/045-competitions-one-place/research.md` §R-01..R-04 and `data-model.md` §1.

### 3.1 Definitions

| Metric | Definition | Rounding | Gate (`null` when) |
|---|---|---|---|
| Parrilla (`field_size`) | Rows with status `FINISHED` or `MINUS_LAPS` in the (competition, category) | integer | — |
| Timed finishers (`timed_finishers`) | Rows `FINISHED` with `race_time_ms`. Denominator of percentile and median gap | integer | — |
| Puesto (`position`) | Official position, only for field members | integer | DNF, DNS, DSQ |
| Percentil | `100 × (1 − (t − t_min) ÷ (t_max − t_min))` over timed finishers | integer | `timed_finishers < MIN_FIELD`, own result not `FINISHED` with a time (includes `MINUS_LAPS`), or `t_max == t_min` |
| Brecha vs. mediana | `100 × (t − median) ÷ median` over timed finishers | 1 decimal | Same as Percentil |
| Brecha vs. 1.ª posición | Against the **official** P1 time | 1 decimal | No P1 time or own result has no time. No minimum field |
| Brecha vs. podio | Against the **official** P3 time | 1 decimal | No P3 time or own result has no time. No minimum field |

- `MIN_FIELD = 5` timed finishers, applied inside the engine. Consumers do not re-gate.
- «sin dato» is shown for `null`, never 0 and never a dash.
- Ties in time get the same percentile. One very slow finisher stretches the range and pushes everyone else's percentile toward 100; the median gap resists this.
- Percentile references the fastest and slowest times; the two gaps reference the official P1 and P3. They differ only when the organiser's order does not follow time (penalties).
- Riders who lost laps count in Parrilla and are excluded from percentile, median and gaps.

### 3.2 Entry points

| Function | Use |
|---|---|
| `compute_field_metrics(...)` | Per athlete and season, keyed by `event_id`. Serves history, evolution, the AI analyst context and newsletters. Keeps the pre-045 names `gap_pct`, `gap_to_p1_ms`, `gap_to_p3_ms` |
| `compute_category_metrics(results, event_id, category_id)` | Pure, no DB. One `MetricSet` per result, keyed by `result_id`. Serves the competition results read |

Consumers that delegate to the engine: `analytics_charts.py` (evolution, distribution), `history.py`, `results_read.py`, `race/ai/nodes/compute_metrics.py`, `stage_log_builder.py`, `newsletter_builder.py`. Cross-consumer equality is pinned by `backend/tests/services/race/test_metrics_consistency.py`.

### 3.3 Audience rules

Policy lives in `backend/app/services/race/audience.py` (`Audience.COACH` for coach and admin; `Audience.FAMILY` for every other role, fail-closed).

| Rule | Behaviour |
|---|---|
| Excluded, not nulled | Family payloads **omit** the keys in `FAMILY_EXCLUDED_METRIC_FIELDS`: `gap_to_winner_pct`, `gap_to_winner_ms`, `gap_to_podium_pct`, `gap_to_podium_ms`, `gap_pct`, `gap_to_p1_ms`, `gap_to_p3_ms` and the chart series `gap_pcts` |
| Family results row | Only `field_size`, `timed_finishers`, `position`, `percentile`, `gap_to_median_pct` |
| Evolution | A parent requesting `metric=podium_gap_ms` gets `403`; parent points omit `gap_pct` |
| Distribution and Comparar | Coach/admin only. `GET /athletes/{id}/race-analysis/distribution` answers `403` to a parent (own child included) before any query, because `points[].time_ms` lists every rider's time |
| Athlete insight, parent variant | `metrics_snapshot` is an allow-list (`progression_assessment` only). For a v3 row, `summary_text` (list and detail), top-level `recommendations` and top-level `principles_cited` are omitted (keys absent); `structured.principles_cited` stays. Pre-v3 and fallback rows keep their text. Coach/admin keep the full payload |
| Approved AI text | Structured gap fields are omitted for families. When the family-visible text mentions the leader, winner, P1/P3, first or third place or the podium, the coach sees a warning on the approval card with up to 3 snippets (`family_gap_mentions`, `services/race/family_gap_mentions.py`) and can still approve or reject. This notice is the only guard for free text without figures |
| Persisted stage logs | Scrubbed at read time in `to_parent_dto` (`services/training/stage_log.py`); the stored `stage_log_json` is not rewritten. The pattern is numeric only («N % al P1», «N % del primer lugar»); `coach_note`, `analyst_reading` and `family_compass` are not scrubbed |
| Family templates and LLM context | Stage-log PDF templates receive `race_results` and `charts_context` through `redact_for_audience(FAMILY)` (`athlete_newsletter_pdf.py`). The newsletter v2 prompt cites only «Brecha vs. mediana» and its context excludes winner and podium gaps |
| Approval | Approving an analysis sends no email; it makes the analysis visible in the app |

## 4. Imports and identity gate

- **Per-import gate.** A commit (`/commit`, `/commit-pending`) is blocked only by pending identity candidates that involve that import's record keys. Keys come from the rows the commit ingests, matched by the name/club/city triple and ignoring the category discriminator (`identity_review.import_record_keys`, `pending_candidates_for_import`, `routers/race_imports.py::_identity_gate`). Candidates about other imports do not block.
- **GENERAL sheet.** The gate keys and the identity universe include GENERAL-sheet triples of every category, because the ingestor resolves competitors from all of them. A GENERAL-only triple enters the universe as a single appearance with `GENERAL_VALIDA_NUM = 0` (GENERAL is the season accumulation, not a válida), so a near-duplicate of a club athlete raises a candidate before the commit. An already `committed` import contributes no GENERAL.
- **Corrections.** `_identity_rebuild_needed` takes `latest_correction_at` (newest correction of the import being committed) and rebuilds the queue when it is later than the newest candidate. If the rebuild yields no new candidate, the next commit of that import rebuilds again; a persistent marker would need a migration (open item 3).
- **Blocked response.** `409` with `{"detail": "identity_pending", "pending_for_import": <n>, "review_path": "/competitions/imports?seccion=identidades&import=<id>"}`. Counts and ids only, never names.
- **Resumable imports.** `GET /api/race-analysis/imports/{import_id}` rehydrates the wizard from `?import=<id>` (`pending` → review, `dry_run` → confirm). `POST .../discard` moves `pending|dry_run` to `discarded` (idempotent; `committed` returns `409`).
- **Migration.** `backend/alembic/versions/a76c264449a5_race_import_discarded.py` adds `discarded` to `race_imports.status` (`down_revision` `b4e8d2f61a93`). The downgrade maps `discarded` to `failed` first. Run `alembic heads` and expect exactly one head before adding another migration. The `pytest -m mysql` lane ran on `trocha_ruta_test` (T068, 2026-09-23): 35 passed, single head `a76c264449a5`, upgrade → downgrade -1 → upgrade clean.

## 5. New and changed endpoints

Contract: `specs/045-competitions-one-place/contracts/api.md`. URL prefixes are unchanged.

| Endpoint | Change | Denied path |
|---|---|---|
| `GET /api/athletes/{id}/race-analysis/history?series_kind=cup\|championship\|all` | Time-based `percentile`; adds `gap_to_podium_pct`; parent variant omits winner and podium fields | Another parent's athlete |
| `GET /api/athletes/{id}/race-analysis/evolution` | Every value from the engine; percentile gated at 5 | Parent + `podium_gap_ms` → 403 |
| `GET /api/athletes/{id}/race-analysis/distribution` | Percentile from the engine; coach/admin only | Parent → 403 (own child included) |
| `GET /api/athletes/{id}/race-analysis/insights` and `.../insights/{insight_id}` | Parent variant omits v3 `summary_text`, `recommendations` and top-level `principles_cited`; detail `metrics_snapshot` is an allow-list | Another parent's athlete |
| Competition results read (`results_read.py`) | Rows gain `metrics` (family subset for parents) | Parent |
| `GET /api/dashboard/coach-summary` | Adds `identity_decisions_pending`, `imports_in_progress`, `analyses_awaiting_approval` | Parent |
| `GET /api/race-analysis/imports/{import_id}` | New; returns `parent_committed_at` for the revision notice | Parent 403, other club 404 |
| `POST /api/race-analysis/imports/{import_id}/discard` | New | Parent 403 |
| `GET /api/race-analysis/pending-analyses?season=&state=awaiting_approval\|stale` | New; items carry `kind` (`valida` \| `season_summary` \| `null`) for presentation only | Parent 403, unknown state 422 |
| `POST /api/race-analysis/runs/{run_id}/dismiss-stale` | New | Parent 403, not stale 409 |
| `GET /api/race-analysis/runs/{run_id}/status` | Awaiting-HITL event gains `family_gap_mentions` (coach only) | Never sent to parents |

## 6. Alias and redirect table

Every previous address keeps working (FR-050). Addresses under `/competitions` keep their form (FR-051). Sources: `frontend/src/App.tsx`, `frontend/src/lib/carrerasTabAlias.ts`, `frontend/src/routes/RaceInsightEmailRedirect.tsx`, `frontend/src/routes/competitions/CompetitionDetailPage.tsx`.

### 6.1 Routes

| Old address | Resolves to | Notes |
|---|---|---|
| `/competitions/insights/season/:year` | `/competitions/season/:year` | Query string preserved |
| `/competitions/history` | `/competitions/imports?seccion=cargas` | |
| `/competitions/identity-review` | `/competitions/imports?seccion=identidades` | |
| `/competitions/unlinked` | `/competitions/imports?seccion=sin-enlazar` | |
| `/athletes/:athleteId/race-analysis/insights/:insightId` (email link) | Coach/admin: `/athletes/:athleteId?tab=races&view=analisis&insight=:insightId`. Parent: `/my-athletes/:athleteId?tab=races&view=analisis&insight=:insightId` | Other roles get the not-found page |

Unchanged legacy redirects: `/training/races/:id/club-insights` and `/coach/race-analysis`. `/competitions/insights` still resolves to the not-found page.

### 6.2 Query parameters

| Old parameter | Where | Resolves to |
|---|---|---|
| `?tab=ai_analysis[&insight=<id>]` | `/athletes/:id` | `?tab=races&view=analisis[&insight=<id>]` |
| `?tab=ai-analysis[&insight=<id>]` | `/my-athletes/:id` | `?tab=races&view=analisis[&insight=<id>]` |
| `?tab=conditions` | `/competitions/:id` | `?tab=circuito` |
| `?tab=races&view=comparar` | `/my-athletes/:id` | `?view=progresion` (coach-only view; never an error) |
| Unknown `view` | Both athlete pages | `progresion` |

Both athlete pages accept both spellings of the legacy tab in both roles, so a link that crosses roles does not end in a silent 404. Other query parameters are preserved when the alias is applied. Competition-tab and athlete-tab test coverage: `frontend/src/routes/__tests__/competitionsRedirects.test.tsx` and the athlete detail page tests.

### 6.3 New addresses

| Address | Purpose |
|---|---|
| `/competitions/season/:year[?analisis=por-aprobar\|desactualizados]` | «Temporada» and its analyses lists |
| `/competitions/imports?seccion=cargas\|identidades\|sin-enlazar[&import=<id>]` | «Cargas e identidades» |
| `/competitions/import?import=<id>`, `/competitions/:id/import?import=<id>` | Import wizard resumed from a persisted import |
| `/athletes/:id?tab=races[&view=…][&insight=<id>]` | Coach «Carreras» |
| `/my-athletes/:id?tab=races[&view=progresion\|analisis][&insight=<id>]` | Family «Carreras» |
| `/parents/competitions/:raceEventId` | Family competition results (family metric subset) |

## 7. Family communication

The bitácora editor offers a one-click «Insertar aviso de cambios» that pre-fills `coach_note` with a notice explaining the median-gap reference and the time-based percentile (`frontend/src/components/newsletter/studio/changeNotice.ts`). The coach edits it and publishes; nothing is sent automatically. A dismissal is remembered per coach in `localStorage` under `tyr:045-notice-dismissed:v1:{userId}`. The inserted text is condensed to 60 words or fewer because the backend caps `coach_note`; it differs from the longer wording in `contracts/ui-copy.md` (accepted by the owner, 2026-09-23). Coordinate with the pending feature-044 family announcement so families get one message.

## Open items

Owner decisions of 2026-09-23 are resolved and implemented (identity gate for GENERAL rows and corrections; v3 free text, `distribution`, stage logs, family templates and the newsletter prompt closed for families; «Aviso de cambios» copy, «Análisis IA» tab name, `dismiss-stale` audit as `update` and `insights_stale` counting runs accepted; `parent_committed_at`; `kind` on pending analyses; fictitious test names). Tracking: `docs/implementation-status.md`, «Competitions in one place (specs/045-competitions-one-place)».

| # | Item | Reference |
|---|---|---|
| 1 | Season summaries never become stale automatically: `run_staleness.invalidate_runs_for_event` only covers insights with an `event_id` | `services/race/run_staleness.py` |
| 2 | The read-time scrub is numeric-pattern only. Free text without figures, `coach_note`, `analyst_reading` and `family_compass` rely on the FR-022 notice | `services/training/stage_log.py`, `services/race/family_gap_mentions.py` |
| 3 | The correction-triggered queue rebuild repeats when it yields no new candidate; a persistent marker needs a migration | `routers/race_imports.py::_identity_rebuild_needed` |
| 4 | Golden fixtures need regeneration with the time-based percentile | `research.md` §R-02 |
| 5 | Deferred lanes T069–T072 (see below) | `tasks.md`, `qa.md` |

## Verification status

- Run offline (default lane): per-task gates G1–G4 in `specs/045-competitions-one-place/tasks.md`; pre-existing failures in `baseline.md`; privacy audit (T065, PASS-WITH-FINDINGS) and the follow-up fixes in `qa.md`.
- `pytest -m mysql` (T068): 35 passed on `trocha_ruta_test`; migration `a76c264449a5` upgrade/downgrade round trip clean.
- Final gate (T073): backend 214 failed / 5794 passed (the `baseline.md` set plus two environment-dependent tests outside 045); frontend 4732 passed / 1 failed (`SessionWizardRouteNotify`, baseline); `npm run typecheck` and `npm run build` clean.
- In progress: `pytest -m golden` (T069) and Playwright (T070). Pending, manual: family «Carreras» LCP on a mid-tier Android over 3G (T071) and coach tablet check (T072). Results are recorded in `qa.md`.
- G2 verdict on the identity gate (PASS-WITH-NOTES, notes closed by the follow-up): `research.md` §R-08.

## References

- `specs/045-competitions-one-place/spec.md`, `plan.md`, `research.md`, `data-model.md`, `tasks.md`
- `specs/045-competitions-one-place/contracts/api.md`, `contracts/ui-routes.md`, `contracts/ui-copy.md`
- `backend/app/services/race/field_metrics.py`, `backend/app/services/race/audience.py`
- `docs/10-race-results/competitions-module.md` (feature 007 module this area builds on)
- `docs/10-race-results/history-backfill-design.md` (feature 044 history and identity review)
