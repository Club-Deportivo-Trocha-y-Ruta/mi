# Feature Specification: AI Insights Tab — Full-Stack Review

**Feature Branch**: `036-ai-insights-tab-review`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User request — review the athlete AI Insights tab (`/athletes/:id?tab=ai_analysis`) end to end, from the simplest components to the most complex, covering unit-level concerns first and end-to-end flows after, and produce a work plan covering corrections, redesigns, improvements and net-new implementations. Scope agreed with the user: full-stack (frontend + the 8 endpoints of `athlete_race_analysis.py` + the LangGraph agentic pipeline), both roles (coach and parent). Deliverable is this Spec Kit feature; **no implementation was performed**.

## Evidence base

This spec is grounded in a live inspection of the running app (coach role, seeded athlete, 2026 season) plus six parallel read-only audits: frontend architecture, FE/BE data contracts, test coverage, minors' privacy, the agentic pipeline, and UX/accessibility. Every finding below carries a `file:line` reference verified against the current tree. Findings that turned out to be false were dropped — for example, the duplicated network requests observed in the browser are React `StrictMode` in dev (`frontend/src/main.tsx:9`), not a double-fetch bug.

**Surface under review**: ~5,400 lines of frontend components (`components/athletes/ai/*`, `components/ai/*`), 9 TanStack Query hooks, 8 REST endpoints, and the `services/race/agents/` LangGraph pipeline.

**Deliberately out of this spec**: the missing AI-consent gate on `POST /runs` and `POST /season-summary` (`backend/app/routers/athlete_race_analysis.py:523-539,838-873`) is a confirmed, severity-critical finding — data about a minor can reach an AI provider without verified `third_party_sharing` consent, in violation of `.specify/memory/constitution.md:220-223`. It is tracked separately from this feature at the user's request, not implemented here, and not resolved by anything in this document.

## User Scenarios & Testing *(mandatory)*

### User Story 2 - The AI analysis actually analyses (Priority: P1)

The text a coach reads for a válida tells them something they could not get by looking at the results table: how this ride compares to the athlete's previous ones, what changed, and what to work on next — in language a coach can act on and a family can understand.

**Why this priority**: This is the module's reason to exist, and today it does not deliver it. All five insights generated for the inspected athlete across the 2026 season are the same template with the numbers swapped. Two verbatim samples:

> "La deportista completó la válida 1, registrando un tiempo de 0:36:19 y finalizando en la posición 4. El tiempo de carrera fue 0:36:19, con un gap al líder de 0:04:17 (13.4%). Alcanzó el número máximo de vueltas previsto para la categoría. Las condiciones de carrera fueron de clima parcialmente nublado, temperatura de 28 °C, pista seca y altitud de 1080 msnm."

> "La deportista completó la válida 4, registrando un tiempo de 0:59:05 y finalizando en la posición 3. El tiempo de carrera fue 0:59:05, con un gap al líder de 0:04:06 (7.5%). Alcanzó el número máximo de vueltas previsto para la categoría. Las condiciones de carrera fueron de clima nublado, temperatura de 25 °C, pista húmeda y altitud de 1000 msnm."

The race time is stated twice in consecutive sentences, the lap sentence is a fixed filler, and there is no comparison, no trend and no recommendation. The UI's own confidence badge reads "Confianza baja". The coach is paying LLM budget to have the results table read back to them.

The cause is confirmed, not suspected. `backend/app/services/race/prompts/race_analyst_v2.md:44` instructs the model to include five named fields and permits five verbs, with no few-shot example anywhere in either prompt version — so the model recites. Line 44 also demands "número de vueltas completadas" while no lap field exists in `backend/app/services/race/schemas.py`, so the filler sentence is a hallucination the prompt requires. And `race_analyst_v2.md:220-245` forbids all cross-race comparison whenever `is_first_in_season` is true, which may be true on every single-válida launch. The critic is not at fault; the fallback is not involved.

Compounding all of it: the golden eval that blocks CI has never tested any of this. `backend/tests/evals/test_race_analyst_eval.py:173` invokes the v1 method against the five-section v1 prompt, and `.github/workflows/race-eval.yml:53-54` pins Google Gemini — while production runs the v2 per-válida method against Anthropic `claude-sonnet-5` (`config.py:112`, `_llm.py:33`). The gate measures a pipeline that no coach uses.

**Independent Test**: Regenerate analyses for an athlete with at least four completed válidas and confirm each text references prior rides, names a concrete change, and closes with an actionable recommendation — with no sentence repeating a datum already given.

**Acceptance Scenarios**:

1. **Given** an athlete with three or more analysed válidas, **When** a new analysis is generated, **Then** the text explicitly compares against at least one earlier ride and names the direction of change.
2. **Given** any generated analysis, **When** read, **Then** no single figure (time, position, gap) is restated in more than one sentence.
3. **Given** an athlete with exactly one válida, **When** analysed, **Then** the existing N=1 rule holds: no trend is asserted, and the text says so rather than inventing one.
4. **Given** any generated analysis about a minor, **When** read, **Then** it contains no judgement about the child's body and no diagnostic language.
5. **Given** the golden eval suite, **When** run against the current templated output, **Then** it fails — today it does not, which is itself a gap in the eval.

---

### User Story 3 - The tab never shows one athlete's data under another's name (Priority: P2)

Navigating from one athlete's profile to another resets the tab completely: no leftover selection, no stale run timeline, no detail fetch against the wrong athlete.

**Why this priority**: `frontend/src/routes/athletes/AthleteDetailPage.tsx:888` mounts the tab without `key={athlete.id}`, and `AthleteAIAnalysisTab` resets none of its state on `athlete.id` change. React Router does not unmount on a param-only change, and the codebase documents cross-athlete navigation with `?tab=ai_analysis` preserved (`AthleteDetailPage.tsx:495-497`). The worst case is sending athlete A's insights to athlete B's family newsletter, because `newsletterSelection` is a `Set<number>` of insight IDs that survives the switch. Zero tests cover this at any level.

**Independent Test**: With the tab open on athlete A, select insights and start a run; navigate client-side to athlete B; assert the selection is empty, no run timeline is shown, and no request carries A's insight IDs with B's athlete ID.

**Acceptance Scenarios**:

1. **Given** insights selected for the newsletter on athlete A, **When** the coach navigates to athlete B with the tab open, **Then** the selection is empty and the sticky action bar is gone.
2. **Given** an analysis running for athlete A, **When** the coach navigates to athlete B, **Then** B's profile shows no run timeline and no HITL card belonging to A.
3. **Given** an insight opened in detail for athlete A, **When** the coach navigates to athlete B, **Then** no detail request is issued for A's insight ID under B's path.

---

### User Story 4 - Failed analyses are never mistaken for real ones (Priority: P2)

When the pipeline falls back because the model failed, the result is clearly marked as unavailable, cannot be attached to a family newsletter, and offers the coach a retry.

**Why this priority**: `backend/app/services/race/ai/fallback.py:19-22` persists the string "Análisis IA no disponible en este momento. Revisa los datos crudos en la sección de resultados." as an ordinary insight row with empty `sections`, `citations_used` and `recommendations`. In the live app it appears in the history indistinguishable from a real analysis, carrying a selection checkbox — so today a coach can attach an error message to the newsletter that families receive. The module's own docstring says the coach should "decide whether to retry or publish as unavailable", but the UI gives them no way to tell the difference.

**Independent Test**: Force a provider failure, confirm the resulting row is visibly marked as failed, is not selectable for the newsletter, and offers a retry affordance.

**Acceptance Scenarios**:

1. **Given** a fallback insight, **When** the history renders, **Then** it is visually distinct from a successful analysis and labelled as unavailable.
2. **Given** a fallback insight, **When** the coach attempts bulk newsletter selection, **Then** it cannot be selected.
3. **Given** a fallback insight, **When** the coach views it, **Then** a retry action is offered.
4. **Given** existing fallback rows already in the database, **When** the fix ships, **Then** they are classified correctly without a manual data migration by the coach.

---

### User Story 5 - What the screen says is true (Priority: P2)

Every label, subtitle and figure in the tab states something the system actually does, and identifies races unambiguously.

**Why this priority**: several visible statements are false or ambiguous today, which erodes the coach's trust in the whole module:

- `components/athletes/ai/DistributionChart.tsx:155` tells the coach the comparison is "pseudonimizada", and the file docstring at `:5-6` claims the backend "nunca expone nombres reales". For coach and admin the backend does send `display_name` for every rider in the category, including minors from other clubs (`backend/app/services/race/analytics_charts.py:501`), rendered at `:472` and `:543-545`. Parents correctly receive `None` (`routers/athlete_race_analysis.py:757`), so this is not a leak toward families — but the coach is promised a protection that does not exist, and the product decision about showing other clubs' minors was never made explicitly.
- The "Analizar con IA" race picker renders two identical `CD` chips with no date, because `lib/insights.ts:110` still branches on the retired `valida_num === 99` convention. Features 014/016 moved race identity to `event_id` + `race_series.kind`; the AI payload stayed behind. Its own comment admits the exception.
- The same datum renders in two formats depending on the sub-tab: `validaLabel` (`lib/insights.ts:110-115`) produces "Válida 3" while `getValidaLabel` (`lib/raceCalendar.ts:149-160`) produces "Válida III".
- The history is ordered by generation timestamp, not race date, producing the sequence Válida 1 → Resumen de temporada → Válida 4 → Válida 3 → Válida 2, and the header shows "Último análisis: Válida 1" beside a KPI reading "7 válidas completadas" with nothing explaining the gap.
- The Distribution sub-tab opens empty: its selector defaults to "Temporada (todas)", a value that produces the "select a race" placeholder rather than data.

**Independent Test**: Walk every visible string and figure in both roles against actual system behaviour; each claim holds, each race is uniquely identifiable, and the default state of every sub-tab shows data.

**Acceptance Scenarios**:

1. **Given** the Distribution sub-tab as a coach, **When** it renders, **Then** its wording matches what is actually shown, and the decision about displaying other clubs' minors is explicit and recorded.
2. **Given** a season containing two Departmental Championship events, **When** the race picker renders, **Then** each is uniquely identifiable.
3. **Given** any válida label anywhere in the tab, **When** compared across sub-tabs, **Then** the format is identical.
4. **Given** the history list, **When** it renders, **Then** ordering and dates are anchored to race date, and analysed-versus-completed counts are reconciled for the coach.
5. **Given** the Distribution sub-tab, **When** first opened, **Then** it shows data without requiring a selector change.

---

### User Story 6 - The tab works on the devices these users actually hold (Priority: P3)

The coach can operate the tab on a tablet with gloves in daylight; the parent can reach everything on a mid-range Android phone.

**Why this priority**: at 400 px the sub-tab row clips at "Distribució…" with the scrollbar deliberately hidden (`components/athletes/ai/AthleteAIAnalysisTab.tsx:291`), leaving "Analizar con IA" unreachable unless the user discovers the swipe; the bottom navigation bar overlaps the profile tab row. The history checkboxes and the "Modo explicativo" checkbox are far below the project's 48×48 touch floor, which `frontend/e2e/target-size.spec.ts` already enforces elsewhere and which feature 032 previously had to fix for the same reason. The sticky action bar (`:396-460`) announces nothing to screen readers, and `HITLApprovalCard` — a dialog-bearing component — has no `axe()` check in any test file.

**Independent Test**: Exercise the tab at 360–400 px and with keyboard only, in both roles; every sub-tab is reachable, every control meets the touch floor, and dynamic status changes are announced.

**Acceptance Scenarios**:

1. **Given** a 360 px viewport, **When** the tab renders, **Then** every sub-tab is reachable and discoverable without relying on a hidden scroll affordance.
2. **Given** keyboard-only navigation, **When** the coach moves through sub-tabs, the comparator sheet and the HITL card, **Then** focus order is sensible and no trap occurs.
3. **Given** the newsletter action bar changing state, **When** it appears or reports success or failure, **Then** the change is announced to assistive technology.
4. **Given** any interactive control in the tab, **When** measured, **Then** it meets the project's 48×48 floor.

---

### User Story 7 - A safety net that would catch these bugs (Priority: P3)

The flows that span several components have automated coverage, so the defects in stories 3, 4 and 5 cannot silently return.

**Why this priority**: coverage is high but hollow in exactly the wrong places. There are 466 frontend tests and 51 backend router tests, with genuinely good practices (recursive PII assertions, typed MSW factories). But `AthleteAIAnalysisTab.test.tsx` mocks `AnalysisRunTimeline`, `HITLApprovalCard`, `PanoramaView` and `InsightsTimeline`, so the HITL derivation logic at `AthleteAIAnalysisTab.tsx:165-191` has 0% real coverage at every level. `HITLApprovalCard.test.tsx:38-49` asserts the "Editar" button exists but never clicks it — deleting its `onClick` (`HITLApprovalCard.tsx:188`) leaves the suite green. Admin role is untested on 6 of the 8 endpoints. Two `xfail` tests in `test_persist_insight_per_valida_v2.py` now pass and nobody removed the marker. One e2e spec touches the tab (`frontend/e2e/race-analysis-championship.spec.ts`) but only for three Copa-versus-Championship picker scenarios.

**Independent Test**: Introduce each of the defects from stories 3–5 deliberately into a scratch branch and confirm the new tests fail.

**Acceptance Scenarios**:

1. **Given** the integration suite, **When** the tab is mounted without mocking its own subcomponents, **Then** the launch → timeline → HITL → approve flow is exercised end to end.
2. **Given** the e2e suite, **When** run, **Then** the coach happy path, the launch-to-HITL-approval flow, and the parent path are each covered.
3. **Given** the backend suite, **When** run, **Then** every endpoint has an admin-role test and a denied-path test.
4. **Given** the athlete-switch scenario of Story 3, **When** the regression test runs, **Then** it fails against the current code and passes after the fix.

## Success Criteria *(mandatory)*

- **SC-002**: For athletes with three or more analysed válidas, generated analyses reference prior rides and close with an actionable recommendation, with no repeated figures. Measured by an extended golden eval that fails on the current templated output.
- **SC-002b**: The golden eval exercises the prompt, method and model that production actually uses. Until this holds, SC-002 cannot be measured at all.
- **SC-003**: Switching athletes with the tab open carries over zero state. Measured by the Story 3 regression test.
- **SC-004**: No failed-analysis placeholder can reach a family newsletter.
- **SC-005**: Every visible claim in the tab is true, and every race in the picker is uniquely identifiable.
- **SC-006**: The tab passes the project's touch-target and accessibility gates at 360 px and with keyboard-only navigation, in both roles.
- **SC-007**: Deliberately reintroducing any Story 3–5 defect causes at least one automated test to fail.

## Open Questions

1. **Other clubs' minors in the Distribution chart** — the source is a public federation PDF, but re-exposing named minors inside the club app is a distinct decision. Options: keep names for coach, pseudonymise everyone except the athlete in question, or make it a per-club setting.
2. **Parent access to absolute times and podium gaps** — `GET /insights/{id}` does not filter `metrics_snapshot` by role, so a parent calling the API directly receives `race_time_ms` and `podium_gap_ms`. The UI hides these deliberately, citing the psychological safeguard in Principle V. Is the client-side-only presentation acceptable, or must the backend filter by role?
3. **Sub-tab count** — *answered by the UX audit, pending your approval*: collapse five sub-tabs to three — **Resumen** (Panorama and Histórico merged, since Panorama already shows the latest insight in full), **Rendimiento** (Evolución and Distribución merged, comparator as a control), and **Analizar con IA**. This partially reverts BB3, which is called out explicitly in the plan.
4. **Langfuse** — `CLAUDE.md` describes Langfuse observability as part of the race AI stack, but it is not implemented; the only occurrence is a string in a docstring at `backend/app/models/agent_run.py:22`. Either implement it or correct the documentation.
5. **Insight provenance already recorded is wrong** — `backend/app/services/race/ai/nodes/persist_insight.py:359,417` hardcodes `model="gemini-2.5-flash-lite"` on every row regardless of the provider that generated it. Existing rows misreport their origin. Fixing it forward is trivial; whether to backfill or annotate the historical rows is a decision, since the true model for past runs may not be recoverable.

## Out of Scope

- Race results ingestion and the import wizard.
- The competitions-side AI surfaces (`components/competitions/`), except where a shared helper must change.
- The session assistant and monthly newsletter AI stacks, except as reference patterns for the consent gate.
- Any change to the anxiety module (Principle V wording and consent logic are untouched).
