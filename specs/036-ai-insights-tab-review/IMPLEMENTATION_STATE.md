# Implementation state — feature 036 (AI Insights Tab review)

**Last updated**: 2026-09-01, end of Wave 5 — all 5 waves done. Feature functionally complete, not deployed.
**Working branch**: `main` (user's explicit choice). Everything is **uncommitted** in the working tree.

> Read this file first when resuming. It records decisions that are NOT derivable from
> `spec.md` / `plan.md` / `tasks.md`, because several of them **override** those documents.

---

## How the work is being executed

`/speckit-implement 036` via the Workflow tool, **one workflow per wave**, Sonnet agents at
`effort: max`, partitioned by strict file ownership so concurrent agents never edit the same file.
Each wave ends with a single integration agent that owns the whole tree, resolves the blockers the
parallel agents were forbidden from touching, and runs the real suites.

Waves are **serialized on purpose**: they share `AthleteAIAnalysisTab.tsx`, `lib/insights.ts` and
`InsightsTimeline.tsx`. Running them concurrently produces overwritten edits, not parallelism.

---

## Decisions taken with the user (these OVERRIDE spec.md / plan.md / research.md)

| # | Decision | Consequence |
|---|---|---|
| D1 | **Stay on Gemini.** No migration to Anthropic — the user relies on Gemini's free quota. | **Rewrites T051 and research.md R5.** See "The Gemini correction" below. |
| D2 | **T037 stays deferred** (naming other clubs' minors in the Distribution chart). | Only the false claims get corrected (T036). Data behaviour untouched. |
| D3 | **T041 → delete `stale_run_id`**, do not populate it. | Field + badge removed from both sides. |
| D4 | **T064 → correct `CLAUDE.md` only.** Do not implement Langfuse. | Matches research.md R3. |
| D5 | **T098 NOT done** — do not collapse 5 sub-tabs into 3. | It is an IA redesign mixed into a bug-fix feature; Open Question 3 was never approved. Belongs in its own feature. |
| D6 | Work directly on `main`, no feature branch. | ⚠️ `main` auto-deploys to Render on push. Nothing has been committed or pushed yet. |

### The Gemini correction (important — the spec is wrong about this)

`spec.md`, `plan.md` and `research.md` all assert that production runs `anthropic`/`claude-sonnet-5`.
**It does not.** Verified against the real config:

| Layer | Provider | Model |
|---|---|---|
| `backend/.env` (what actually runs) | `google` | `gemini-3.1-flash-lite` |
| Code defaults (`config.py:112`, `services/race/agents/_llm.py`) | `anthropic` | `claude-sonnet-5` |
| CI golden eval (`.github/workflows/race-eval.yml:53-54`) | `google` | `gemini-2.5-flash-lite` |

US2's root finding — *the golden eval measures a pipeline no coach uses* — is still real, but the fix
resolves **toward Gemini**, not toward Anthropic:

- **T051 becomes**: align the code defaults *and* the CI eval on `google` / `gemini-3.1-flash-lite`.
- **T062**: no recalibration needed. `race_ai_budget_usd_30d = 20.0` is generous at Gemini Flash Lite rates.
- **Still to verify before touching the eval**: whether the Render service has `RACE_AI_PROVIDER` /
  `RACE_AI_MODEL` set to something other than `backend/.env`. If it does, align to Render's values,
  not to the local `.env`. (`mcp__render__*` tools are available for this.)

---

## Progress

| Wave | Tasks | Status |
|---|---|---|
| 1 — US3 state isolation + US4 fallback marking | T010–T027 | ✅ **Done**, marked `[X]` in `tasks.md`, suites verified |
| 2 — US5 truth on screen | T030–T046 (minus T037) | ✅ **Done**, all marked `[X]`, suites verified green |
| 3 — US2 analysis quality | T050–T065 | 🟠 **All tasks done EXCEPT T059** — the golden eval now runs the real v2 pipeline but scores **0.651 < 0.75 gate**. See "The golden gate failure" below. |
| 4 — US6 devices + a11y | T090–T097 (**T098 excluded**) | ✅ **Done**, all marked `[X]`; real bundle win measured (main chunk −92 kB raw / −24.8 kB gzip) |
| 5 — US7 e2e safety net | T070–T082 | ✅ **Done** — 4 new e2e specs (9 tests) + `target-size.spec.ts` repaired/extended, backend admin/denial tests, frontend unit tests, 2 real `HITLApprovalCard` bugs found+fixed, T071/T075 proven load-bearing by sabotage/restore. See "Wave 5 — done" below. |

### Wave 1 — done

All of T010–T027. Beyond the literal task list, the integration agent found and fixed three gaps
**without which US4 would have been cosmetic only**:

1. `routers/athlete_race_analysis.py::_insight_to_out()` never passed `is_fallback` into the response
   schema — the badge and checkbox suppression would only ever have fired against MSW mocks, never
   against real data.
2. `create_season_summary()` builds its `AthleteAiInsight` by hand, bypassing `persist_insight.py`,
   and never set `is_fallback` — even though `invoke_season_summary()` can itself return the
   failure-path fallback.
3. `HeroLastInsightCard.tsx` had its **own** newsletter toggle with no fallback guard — a second
   route by which a coach could mail an error placeholder to a family.

Migration added: `backend/alembic/versions/463c1f0ccb38_add_is_fallback_to_ai_insights.py`.
`alembic heads` = single head. New backend module: `app/services/race/ai/run_reconciliation.py`.

### Wave 2 — Foundation done, rest pending

**Done and in the tree** (frontend label agent, T030-fe / T031 / T032 / T041-fe):
- `getValidaLabel` deleted from `lib/raceCalendar.ts`; one surviving **`validaLabel` in `lib/insights.ts`**,
  roman-numeral format (`Válida III`), with a numeric-shorthand overload for legacy callers.
  All call sites updated (HeroLastInsightCard, InsightsTimeline ×6, AthleteAIAnalysisTab,
  ComparatorPanel ×3, competitions InsightsTab/AthletesTab).
- TS type gained `event_date: string|null` and `series_kind: "cup"|"championship"|null`.
- Race picker renders championship chips as `CD · 12 jun` so two Departmental Championships are
  distinguishable.
- `stale_run_id` removed from the TS type, `<StaleAnalysisBadge>` render block removed from
  competitions `InsightsTab.tsx`, `InsightsTabStale.test.tsx` deleted.
  **Note**: `StaleAnalysisBadge.tsx` itself was deliberately kept — it is wired to a *different*,
  real, backend-supported staleness concept (`AgentRun.stale_since` / `run_staleness.py`).
- Verified: `npm run typecheck` clean; full suite 3942/3943 (only the known `datetime.test.ts` failure).

**Done and in the tree** (backend agent, T030-be / T033-be / T041-be / T043 / T044 + the privacy fix).
It finished cleanly before the workflow was stopped — **no partial edits**; the tree was verified.
- `AthleteInsightOut` (and therefore the detail response) gained `event_date: string|null` (ISO,
  from `race_events.event_date`) and `series_kind: "cup"|"championship"|null` (from
  `race_series.kind`), both resolved server-side through the existing `event_id` FK. **No migration.**
  Both are null exactly when `event_id` is null (season aggregate).
- `valida_num`'s **type is unchanged**; only its documented semantics changed — storage / back-compat
  only, never a label or identity source client-side.
- `insights_history.list_athlete_insights` now orders by `event_date DESC` (LEFT JOIN +
  `contains_eager`). Season-aggregate rows (`valida_num=0`, `event_id=NULL`) sort **last** — a
  deliberate, documented choice.
- `POST .../runs`: new **409** when a run is already active for the same athlete+válida, reusing
  `services/race/group_launch.find_active_run` rather than inventing a second mechanism.
- `POST .../season-summary`: the dedup lock now runs and commits **before** the LLM call; a double
  submit returns **409** (`IntegrityError` caught) instead of a generic 500 after spending budget.
- Privacy fix landed: `forbidden_names` is built from `first_name`/`last_name`, the bare `except`
  was narrowed, and a test asserts it is non-empty.
- Verified: `ruff check` clean on the 3 owned files; `python -m pytest tests/routers/test_athlete_race_analysis*.py tests/services/race/ -q`
  → 818 passed (+13 new tests); full suite at the known 196-failure baseline.

**Correction to `tasks.md` T041** (found by that agent, worth knowing): `ClubInsightByRaceItem.stale_run_id`
was **never declared in the backend at all** — not in the Pydantic schema, nowhere. The task text
saying it sits at `schemas/athlete_race_analysis.py:~470` is wrong. It existed **only** in the TS
type. So T041 was purely a frontend deletion; there was no populate-vs-delete decision on the server.
Related loose end, deliberately left alone: `backend/app/services/dashboard_summary.py:129` has a
docstring claiming "el campo por-atleta `stale_run_id` ya expone al frontend" — inaccurate, and now
more so.

**NOT run**: Wave 2's Surfaces phase (**T034, T035, T035b, T035c, T036, T038, T039, T040, T042,
T045**) and its Integrate phase (**T046**). The workflow was stopped deliberately, right after
Foundation returned and before any Surfaces agent edited a file.

---

## Wave 5 — done (US7 e2e safety net + feature close)

Ran as 4 parallel spec-writing agents (each owning a distinct new e2e file) + 2 backend/frontend unit
test agents, followed by one integration agent that owned the whole tree for the wave and did the
feature-close verification pass.

**New e2e specs** (`frontend/e2e/`, all self-contained — `page.route()` mocks, no backend, synthetic
athlete names only): `ai-insights-coach.spec.ts` (T070 happy path, T071 launch→timeline→HITL→approve,
T075 athlete-switch regression — 3 tests), `ai-insights-hitl.spec.ts` (T073 reject + edit, driven to
their real terminal state, not just the click — 2 tests), `ai-insights-newsletter.spec.ts` (T074
sticky bar end to end, following the real `newsletter_id` to a navigable resource — 2 tests),
`ai-insights-parent.spec.ts` (T072 parent view as a privacy boundary: DOM absence + a network
safety net asserting coach-only endpoints are never requested, plus the other-child-403 case — 2
tests). All 9 pass. **T071 and T075 verified genuinely load-bearing** by live sabotage/restore during
the close pass: reverting `handleRunComplete`'s `setActiveRunId(null)` and separately removing
`key={athlete.id}` each turned the corresponding spec red for exactly the expected reason, then both
were restored and reverified green, with `grep -n SABOTAGE` confirming no residue.

**`target-size.spec.ts`**: repaired (T090/T091's fixture dates were fixed-calendar 2026 values that
had rotted into the past — bumped to 2099 with a comment explaining why) and extended with 5 new
tests for the AI tab. The "fails 8/9 with element-not-found" symptom a Wave 4 agent reported was two
different things conflated: the 4 pre-existing (feature-028) tests failing on the date-rot bug (fixed
this wave), and the 5 new tests never having had a bug at all — see "The e2e environment limitation"
section below for why the whole file appeared broken in the first place.

**Backend**: admin-role tests for the 6 endpoints that lacked them (T076) and parent-denial tests for
`/distribution`/`/evolution` (T077), all exercising the real `verify_athlete_access` dependency (not
mocked away). **Frontend**: `useRaceRun.ts`'s 304-not-modified branch, event dedupe by `seq`, and
`resetEvents` gained unit tests (T078); the full "Editar" flow in `HITLApprovalCard` gained real
open-dialog/type/save/cancel coverage (T079) — and while writing it, found and fixed two real bugs
that had zero coverage before: (1) `handleSaveEdit` closed the edit dialog by reading `mutation.isError`
from a stale closure captured at the pre-click render, so it was structurally always `false` — a
failed save silently closed the dialog as if it had succeeded (fixed: `submit()` now returns a success
boolean instead). (2) the error banner rendered in the component's background `<section>`, which Radix
marks `aria-hidden` once the edit `Dialog`'s portal opens, so a coach whose save failed mid-edit never
saw why (fixed: the error text also renders inside `DialogBody`). Panorama→detail→History composition
gained an integration test that mounts the real subcomponents instead of MSW-mocking them away (T080).
T081's two named obsolete `xfail` markers in `test_persist_insight_per_valida_v2.py` were confirmed
removed. T082 was resolved by keeping `resetEvents` (tested by a co-equal task in the same wave, has
an obvious near-term use unlike `useRunResult`/`useInvalidateRun`) and documenting `PdfDownloadButton`
as a complete, unwired component for a future task to mount.

**Feature-close additions** (same wave, by the integration agent, beyond the literal task list):

1. `key={athlete.id}` mirrored onto `MyAthleteDetailPage.tsx`'s parent-only mount of the tab — T010
   only named the coach page (`AthleteDetailPage.tsx:888`); the parent page had the identical latent
   defect (not reachable by clicking today on either surface, same as the coach one, but symmetric and
   a one-line, zero-risk fix).
2. Two more obsolete `xfail` markers removed in `test_season_summary_endpoint.py`
   (`test_season_summary_returns_422_with_less_than_3_validas`, `test_season_summary_parent_forbidden`)
   — same smell T081 named, found only because the full suite was re-read closely at close time. Left
   alone: `test_guardrails_race_v2.py`'s 6 xpassed tests — that file has zero uncommitted changes, so
   it predates and is unrelated to 036.
3. US7 acceptance scenario 3 ("every endpoint has an admin-role test and a denied-path test") had one
   gap: of the router's 8 endpoints, `GET .../insights/{insight_id}` (detail) was the only one without
   its own cross-athlete denied-path test — T076/T077 named 6 endpoints explicitly, season-summary
   already had one pre-dating 036, and `races` had one too, but insight-detail's existing parent test
   only covered "insight not active/approved" (404), not "insight belongs to a different child" (403,
   via the shared `verify_athlete_access` dependency). Added
   `test_get_insight_detail_as_parent_other_child_returns_403`; proven load-bearing by temporarily
   no-op-ing the ownership-denial branch in `app/dependencies.py::verify_athlete_access` (reverted, `git
   diff` confirms byte-identical).
4. 17 real, confirmed touch-target violations owned by this feature (16px/35px/36px/44px controls
   against the project's 48px floor) fixed and re-verified via a live Playwright re-run: `SeasonSummaryButton.tsx`
   ("Generar resumen de temporada"), `HeroLastInsightCard.tsx` ("Releer último", "Agregar al boletín",
   and the "Ver club en esta válida" link — the last one had *zero* padding at all, 144×16px),
   `LaunchAnalysisForm.tsx` (the season `<select>` and `launch-submit`), `DistributionChart.tsx` (both
   its `<select>`s), `ComparatorPanel.tsx` (fixed at its single shared `TAP_TARGET_CLASSES` constant,
   `min-h-[44px]` → `min-h-[48px]` — the file already had a tap-target abstraction, it was just
   calibrated to iOS HIG's 44px instead of this project's 48px — correcting all 4 of its call sites:
   season select, swap button, both válida selects, the CTA link), and `AthleteAIAnalysisTab.tsx`'s
   newsletter action bar (`Limpiar`, submit, `Reintentar`) and comparator-sheet trigger. Re-running the
   4 AI-tab `target-size.spec.ts` tests afterward shows **zero** feature-036-owned entries left in the
   violation dump — only pre-existing, shared, out-of-blast-radius controls remain (see below), so the
   tests still fail overall but for reasons this feature does not own.
5. Left alone, confirmed via `git diff` to have **zero** uncommitted changes (i.e. genuinely
   pre-existing, not this feature's to fix): `AppShell`'s `SidebarNav.tsx` (nav links at 44px, expand/
   collapse chevrons at 44×44, the master collapse toggle at 28×28 — rendered on every authenticated
   page, the single largest source of `target-size.spec.ts`'s remaining redness), `AthleteDetailPage.tsx`'s
   own top-of-page chrome ("Volver a lista", "Editar", the 4 top-level tab triggers, "Enviar informe" —
   shared by every tab on that page, not specific to the AI Insights tab), and `components/ui/sheet.tsx`'s
   28×28 "Cerrar panel" close button (shared by 6+ unrelated features' side panels — `ParentEventDrawer`,
   `EventDrawer`, `MoreSheet`, `EditResultNoteDialog`, `EditConditionsDialog`, plus this feature's own
   `ComparatorPanel`/newsletter Sheet). Also left alone: the parent-only `hero-valida-info-trigger`
   (16×16 inline info icon in `HeroLastInsightCard.tsx`) — it is a byte-identical copy of a pre-existing
   sitewide pattern (`ParentSessionCard.tsx`'s `InfoIcon`), so fixing only this feature's copy would
   create a one-off inconsistency rather than address the actual (sitewide, out-of-scope) pattern
   decision.
6. Full backend suite re-run and reconciled to zero unexplained residue: 3670 passed, 196 failed + 5
   errors, all three pre-existing buckets (`MYSQL_HOST=mysql`, WeasyPrint's missing `libgobject-2.0-0`,
   and the 3 named unrelated bugs) confirmed by directly reproducing each failure's traceback — none
   touch a file this feature changed in a way that matters (the one hit inside a 036-touched file,
   `test_athlete_monthly_newsletters_router.py::TestLegacySnapshotBackwardCompat`, is the WeasyPrint
   failure, unrelated to the `attach-insights` logic 036 actually changed in that file).
7. Full frontend suite re-run: 4025/4026, the one failure being the pre-existing `datetime.test.ts`
   UTC-5 assumption, unchanged.

---

## Out-of-band defect found and folded into Wave 2

**Confirmed live privacy defect, pre-existing, outside the 036 task list.**

`backend/app/routers/athlete_race_analysis.py:919,937` calls `sa_select(UserModel.full_name)`, but
`app/models/user.py` has **no `full_name` attribute** — only `first_name` and `last_name`. The
resulting `AttributeError` is swallowed by a bare `except` that logs at WARNING level, so
**`forbidden_names` is always empty for every real `POST /season-summary`**. The guardrail meant to
stop the LLM from emitting the minor's and their parents' real names has never been populated in
production, and no test goes red.

Assigned to the Wave 2 backend agent (it already owns that file): rebuild the name from
`first_name`/`last_name`, narrow the bare `except` so a future breakage cannot be silent, and add a
test asserting `forbidden_names` is non-empty. **Verify this landed** when resuming.

---

## Environment gotchas (cost the agents real time — don't rediscover them)

- **`pytest` alone fails** with `ModuleNotFoundError: No module named 'app'`: the local
  `backend/.venv` was never `pip install -e .`'d (CI does it). Use **`python -m pytest`**.
  `pip install -e .` also fails — setuptools flat-layout discovery trips on `data/`, `sandbox/`,
  `static/` at the repo root. Untouched: it's a repo-wide packaging decision, not part of 036.
- **~196 backend test failures are pre-existing and environmental**: `backend/.env` sets
  `MYSQL_HOST=mysql`, a docker-compose-only hostname that does not resolve on the host. Plus
  WeasyPrint cannot load `libgobject-2.0-0` (needs Pango/cairo via the OS package manager).
  Three more are unrelated real bugs in `test_ai_factory.py`, `test_calendar_audiences.py`,
  `test_calendar_models.py`.
- **1 frontend failure is pre-existing**: `src/lib/__tests__/datetime.test.ts` — its own control
  assertion assumes a UTC-or-positive-offset timezone; this machine is UTC-5 (Bogotá).
- Fixtures across this codebase use **fixed calendar dates** (e.g. `2026-05-20T10:00:00Z`) that are
  now months stale against the real clock. Any timeout/ceiling measured from a server `started_at`
  will treat every such fixture as already-expired. T017's polling ceiling therefore measures from a
  **client-side** clock (`useRef`, reset on `runId` change), deliberately **not** synchronized to the
  server's `started_at`.
- `backend/.env` is gitignored and untracked, but it holds a live `RACE_AI_API_KEY` in plaintext.

---

## How to resume (historical — kept for the record; all 5 waves are done as of 2026-09-01)

1. `git status` — confirm the tree still holds Waves 1–2 uncommitted, and inspect the three backend
   files listed above for partial edits from the interrupted agent.
2. Re-run Wave 2's remaining phases. The workflow script is saved at:
   `~/.claude/projects/-Users-juadiga-Documents-Personal-Trocha-y-Ruta-me-specs-036-ai-insights-tab-review/33fa4a96-a323-4de6-9d0d-ebfe4ebc459c/workflows/scripts/speckit-036-wave2-wf_1f2732e7-376.js`
   Resume with `Workflow({scriptPath: <above>, resumeFromRunId: "wf_1f2732e7-376"})` — the two
   Foundation agents replay from cache **only if their prompts are unchanged**; edit the script and
   the cache invalidates from the first changed call onward.
   Wave 1's script (for reference on the working prompt shape) is at
   `.../workflows/scripts/speckit-036-wave1-wf_acbbfedf-d08.js`.
3. Then Waves 3 → 4 → 5, same shape. **Wave 3 must apply the Gemini correction (D1) — do not follow
   `tasks.md` T051 literally.**
4. At feature close, update `docs/implementation-status.md` and `docs/technical-notes.md`
   (per CLAUDE.md, history does **not** go in `CLAUDE.md`), and run the mandatory
   `data-privacy-guard` audit — this feature touches athlete-identifiable data.

Steps 1–3 are done (this file's own "Wave 5 — done" section above is the record). Step 4 is also
done: see `docs/implementation-status.md`'s "AI Insights Tab Review" entry and the matching
`docs/technical-notes.md` entry dated 2026-09-01. The privacy audit ran as part of Wave 5's close
(grepped every file this feature added/changed, including the git-committed e2e fixtures, for
real-looking names/birth dates/medical detail and for PII reaching logs — see the findings folded
into this file and reported to the user at close).

## Still owed at the end of the feature

- `tasks.md` checkboxes for Waves 2–5 (Wave 1's are already `[X]`) — left unmarked deliberately: this
  closing pass was instructed not to edit `tasks.md`.
- The `after_implement` hook in `.specify/extensions.yml`: `speckit.git.commit` (optional) — nothing
  in this feature has been committed; everything is still uncommitted on `main` per Decision D6.
- `CLAUDE.md` currently has uncommitted modifications predating this feature.
- **Not done, by design** — belongs to someone else: T059's golden-eval gate (0.651 < 0.75, see
  below), Render's `RACE_AI_PROVIDER`/`RACE_AI_MODEL` verification against the Gemini correction (D1),
  a GitHub Actions `RACE_AI_API_KEY` secret so `race-eval.yml` can run in CI at all, the newsletter
  attach-insights confirmation-surface gap, and wiring up `PdfDownloadButton.tsx` — all detailed in
  `docs/implementation-status.md`'s entry.


---

## The golden gate failure (Wave 3, T059 — OPEN, needs a decision)

The eval was migrated off the v1 pipeline onto the real v2 `invoke_per_valida`, the three v2 sections
replaced the five v1 ones in `scorer.py::_CANONICAL_SECTIONS`, and three new sub-rubrics were added
(repeated figures, analytical connectors, lap-muletilla). It then ran **once**, for real, against live
Gemini: **composite 0.651**, below the blocking 0.75 gate.

Per-case (rule | judge | composite): 001 .70|.90|.82 · 002 .50|.70|.62 · 003 .70|.70|.70 ·
004 .70|.60|.64 · 005 .70|.70|.70 · 006 .70|.60|.64 · 007 .70|.60|.64 · 008 .80|.60|.68 ·
009 .70|.80|.76 · 010 .50|.00|**.20** · 011 .70|.80|.76. Total cost of the run: ~$0.014.

Two things to know before deciding:

1. **Case 010 produced a full deterministic fallback** (16 words, 0 tokens, $0) — the analyst hit a
   hard veto twice and gave up. Hypothesis (unconfirmed, would need another run to check): the veto
   regexes in the SHARED `app/services/ai/guardrails.py` (e.g. `\bnecesita\s+m[aá]s\s+horas\b`)
   are naive substrings with **no negation awareness**, so "no necesita más horas" trips them.
2. **Excluding case 010 entirely, the other ten still average ≈0.696** — the gate fails on the merits,
   not on one outlier. Likely systematic drag: `expected_themes` are strict all-or-nothing
   exact-substring lists (case_004 needs all of "transici"+"juvenil"+"fuerza"+"volumen"+"primer podio"),
   so one paraphrase zeroes 0.20 at a stroke.

The eval persists only aggregate rule/judge/composite — **no raw model output** — so the per-rubric
breakdown cannot be reconstructed without another paid run.

Options: (a) a dedicated prompt-iteration pass with its own eval budget; (b) fix the negation-blind
veto regexes in `guardrails.py` first, since that alone recovers case 010's 0.20 → ~0.7;
(c) loosen `expected_themes` to any-of / stem matching; (d) accept and revisit the threshold with the club.

## Open items only the user can resolve

- **GitHub**: the repo has **zero Actions secrets and zero runs of `race-eval.yml` ever**. Until a
  `RACE_AI_API_KEY` secret is added, the blocking eval cannot execute in CI at all.
- **Render**: `RACE_AI_PROVIDER` / `RACE_AI_MODEL` on the live service are still unverified. The MCP
  exposes only a write-only env-var tool, so it was deliberately not called. Check the dashboard
  (service `mi`, `srv-d7sk2b50lvsc73cp5ku0` → Environment).
- **Render autoDeploy is currently `off`** (confirmed live). `CLAUDE.md`'s Deploy Topology line still
  claims "Backend auto-deploys to Render free tier from `main`". If the change is permanent, that line
  needs correcting; if it is a temporary guard while 036 sits uncommitted, leave it.


---

## The e2e "environment limitation" was not one (found 2026-09-01, FIXED)

A Wave 4 agent concluded that "Playwright's `page.route()` interception does not work in this sandbox",
having reproduced identical ECONNREFUSED failures on two unrelated specs. The reproduction was real; the
diagnosis was wrong.

**Actual cause**: `frontend/.env.local` (gitignored, the user's local dev config) sets
`VITE_API_BASE_URL=` — an **empty string**. `src/api/client.ts:5` reads
`import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"`, and `??` falls back only on
null/undefined, **not** on `""`. So axios' baseURL was relative, every request went out through Vite's
proxy on :5173, and every spec's `page.route()` predicate — which filters on `url.port !== "5173"` —
matched nothing.

**Fix applied**: `frontend/playwright.config.ts`'s `webServer` block now sets
`env: { VITE_API_BASE_URL: 'http://localhost:8000' }`, making the e2e suite self-contained without
touching the user's dev config. Verified: `e2e/cold-start.spec.ts` went from 0/3 to **3/3**.

**Still broken, separately**: `e2e/target-size.spec.ts` fails 8/9 even after the fix, with
"element not found" — and its 4 pre-existing tests fail too, so it predates feature 036. Assigned to
Wave 5.

Worth remembering as a pattern: an agent reproducing a failure twice is evidence the failure is real,
not evidence its explanation is.
