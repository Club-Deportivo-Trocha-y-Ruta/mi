# Quickstart — Validating 033 Visual Coherence & Polish

Presentation-only feature: there is no new user flow to "get started" with — this quickstart is the **validation walkthrough**, organized by Success Criterion. Each section names the automated check first, then the manual/visual pass that automated tooling cannot cover (per Constitution II: automated tests are mandatory; per the `dataviz` skill step 7: "Render it and look at it" — the validator/tests check color and structure, not layout).

## SC-001 — 100% of status presentations use the shared vocabulary with icon or label

**Automated (vitest)**:
- Adapter tests: one per domain in `contracts/status-vocabulary-sweep.md` (8 adapters + 2 sub-adapters = 10 test files/suites), each asserting the full state→`{status,label}` table.
- Regression guard: `SessionStatusBadge` and `AthleteNewslettersDashboardPage`'s badge no longer render a raw hand-styled `<span>` (DOM query for the old className patterns should find zero matches).
- `jest-axe`: zero violations on every updated badge-rendering component (icon+label pairing, never color-alone, is an accessibility property — encode it as a real assertion, not an eyeball check).

**Manual/visual audit checklist** (one pass per module, screenshot or live click-through):
- [ ] Activities (Strava badges): none/active/broken/disconnected all render icon+label
- [ ] Competitions list + detail (3 sub-badges): resultados/calendario/condiciones
- [ ] Sessions list/detail: planned/executed/cancelled
- [ ] Athlete AI tab: confidence badges (high/medium/low)
- [ ] Newsletters dashboard: all 5 states incl. approved/failed
- [ ] Consent panel: 4 states + the embedded AI sub-toggle pill
- [ ] Insights: stale badge (amber, "Análisis desactualizado")
- [ ] Group analysis panel: every `GroupRunRow` state
- [ ] Same state shown in two modules (e.g. "outdated" for consent vs. "stale" for analysis) reads identical in color/shape/icon placement (spec acceptance scenario 3) — side-by-side screenshot comparison

## SC-002 — The four newer modules are indistinguishable from the rest of the app

**Automated**:
- Grep regression test (CI-runnable): `\bslate-\d` returns zero matches under `routes/technique`, `routes/strength`, `routes/intervals`, `routes/anxiety`, `components/technique`, `components/strength`, `components/intervals`, `components/anxiety` (excluding any files feature 029 already deleted — re-run the count from `research.md` R4 and assert it's 0, not just "lower").
- `vitest` snapshot or class-name assertion on `CatalogGrid`/`FilterBar`/`ExerciseCard` confirming técnica and fuerza both render through the same shared component (`frontend/src/components/shared/CatalogGrid.tsx` etc.), not two parallel implementations.

**Manual/visual audit checklist** (side-by-side against a Competitions screen, per spec's Independent Test for User Story 3):
- [ ] Técnica catalog vs. Competitions list: same heading style, same text colors, same empty/error/loading states
- [ ] Fuerza catalog vs. técnica catalog: same filter bar behavior, same card layout, same detail-page structure — differing only in domain fields (skill taxonomy vs. equipment/age-band)
- [ ] Intervalos (structure editor, block row, template picker): charcoal/mid-gray vocabulary, no slate
- [ ] Ansiedad (dashboard, individual/group panels, questionnaire, assessment wizard): same, **and** confirm zero change to any Principle-V-protected wording (see SC-007)
- [ ] The two stray out-of-module hits (`ProtectedRoute.tsx`, `MorphologyCard.tsx`) fixed as a bonus, if included

## SC-003 — Exactly one name, one verb, one icon for AI

**Automated**:
- `vitest` per rename-table row (`contracts/ai-identity.md` §1): each file renders the new label/icon, not the old one.
- A repo-wide grep-based test asserting `BrainCircuit` and the "Lanzar" launch label no longer appear in any AI-related component (the two confirmed-retired variants); `MessageSquare` is allowlisted for the chat entry point only (the one deliberate exception, documented in the contract).

**Manual walk** (one continuous session, per spec's Independent Test for User Story 4):
- [ ] Session assistant → "Insights IA" / `Sparkles`
- [ ] Competition detail → Insights tab → "Insights IA" / `Sparkles` (unchanged, already correct)
- [ ] Group launch panel → "Analizar con IA" / `Sparkles`
- [ ] Athlete AI tab (both coach and parent mode) → "Insights IA" header in both modes; mode-specific description text still differs appropriately
- [ ] Athlete AI tab → renamed "Analizar con IA" sub-tab (was "Lanzar")
- [ ] Per-athlete button (table row + insight card) → "Analizar con IA" / `Sparkles`
- [ ] Race chat → "Preguntar a la IA" / `MessageSquare` (confirmed intentional exception) + non-persistence caption visible on open
- [ ] In-progress run: full `AnalysisRunTimeline` on the athlete tab, compact variant inside `GroupRunRow` — same visual language, different density

## SC-004 — 0 AI launches fail due to budget/concurrency without a beforehand warning

**Automated**:
- `pytest`: `GET /api/ai/status` happy path (ok/warning/exhausted, seeded cost sums); RBAC-negative (parent → 403); the property test asserting `budget_status="exhausted"` if-and-only-if a subsequent real launch would 503 (keeps hint and hard block from drifting apart — this is the load-bearing regression test for this SC).
- `vitest`: `useAIStatus` hook happy-path + graceful-degradation-on-fetch-error; `AnalyzeAthleteButton`/`GroupAnalysisPanel` render the three budget-status presentations and the concurrency wait hint.

**Manual walk (requires a test environment where budget can be forced to threshold)**:
- [ ] Budget `ok`: launch button shows only the "≈Ns" duration hint, no budget copy
- [ ] Budget `warning` (≥80% used): amber inline hint visible before click, launch still enabled
- [ ] Budget `exhausted`: launch button disabled, plain-language explanation visible **before** any click (not just after)
- [ ] Force concurrency full (10 active runs in the test env): "Alta demanda — espera ≈Ns" shown, launch remains enabled, clicking may still 429 → existing reactive copy still fires correctly
- [ ] Kill the status endpoint (simulate network failure): launch button still works, falls back to today's reactive-only behavior, never hard-blocked by the hint's absence

## SC-005 — Chart readability audit

**Automated**:
- A palette-validation test (can literally shell out to `node scripts/validate_palette.js` in CI, or port its `validate`/`validateOrdinal` logic into a small vitest-runnable check) asserting the chart role palette (`#20b7c9,#0ca30c,#d03b3b`) and the A/B/C ordinal ramp both still pass, guarding against a future color edit silently breaking CVD/contrast.
- `vitest`: no `strokeDasharray` prop on either `<CartesianGrid>`; championship point dot renders the diamond path when `series_kind==="championship"` is present in fixture data; reference-line label is absent for non-extreme riders when fixture data has >8 riders, present when ≤8.
- `jest-axe` on both charts' table-view twin (this is the point of the twin — it must be the WCAG-clean equivalent, not just "also present").

**Scenario matrix** (manual render + look, per the skill's step 7 — "the validator checks color, not layout"):

| Scenario | Fixture | Check |
|---|---|---|
| Normal field | 5-9 riders, mid confidence | Solid grid; 3 color roles present; all labels visible; table toggle present |
| Large field | 10-15 riders | Only self/best/worst labeled; other reference lines still positioned correctly; no label collision |
| Small sample | n<5 (Distribution) / n<3 (Evolution) | Existing table/disclaimer fallback, unchanged; no chart or toggle rendered |
| Championship | a season including the Departmental Championship | Diamond marker on the point itself + on-point label + `<ol>` legend entry, all three simultaneously |
| Single-rider category | only the athlete competed | No best/worst reference lines (nothing to contrast); self line renders correctly in accent |
| All-DNF field | every rider including self DNF'd | Existing "no participó"/DNF messaging, unchanged, no fitted curve attempted |

## SC-006 — Dark appearance contrast parity (if shipped)

**Automated**:
- Contrast-audit script re-run for every token pair in `contracts/dark-theme-tokens.md`, both `data-theme="light"` (explicit) and `data-theme="dark"`, asserting the same WCAG floor holds in both.
- `jest-axe` on every page-level/dialog-level coach component with `data-theme="dark"` forced.

**Manual/visual audit checklist**:
- [ ] Toggle to "Oscuro" via the user menu; confirm no flash-of-wrong-theme on reload
- [ ] Sweep every coach module for dark-on-dark invisible marks (spec's own edge case) — especially chart marks, status badges, and any photo/illustration
- [ ] Toggle "Sistema" with OS set to dark; confirm it follows automatically; set OS to light, confirm it follows back
- [ ] Confirm parent-portal routes are unaffected regardless of the coach's stored preference

## SC-007 — Zero regressions in generated documents; zero anxiety-module safeguard changes

**Automated (regression, not new)**:
- Existing PDF/newsletter/instructivo render tests still pass unmodified (this feature must not touch their templates at all — a diff touching any Jinja template under `backend/app/services/*/templates` for a document is itself a review-blocking signal).
- Existing anxiety-module tests (Principle V: age-driven instrument selection, no-diagnosis wording, baseline-anchored interpretation, mastery-climate framing, consent gate, human-in-the-loop) all still pass **unmodified assertions** — only className/token diffs are permitted in the anxiety module's diff; any changed string assertion in an anxiety test is a regression, not an intended update.

**Manual checklist**:
- [ ] Generate one report/newsletter/instructivo before and after the change; byte-diff (or visual diff) the output — must be identical
- [ ] Read the full diff of every `components/anxiety/*` and `routes/anxiety/*` file touched; confirm every change is a className/token swap, never a copy/wording/threshold/consent-gate change

## Cross-cutting: constitution re-check

- [ ] Lint + type-check pass (Principle I)
- [ ] Every new/changed component with branching logic has a `vitest` test; every bug-shaped fix (e.g. the duplicate `confidenceVariant`) ships with its own regression test (Principle II)
- [ ] `AI_LOG_PROMPTS` unchanged (`false`); no PII in the new `/api/ai/status` payload or its logs (Quality Gates)
- [ ] No new runtime dependency added anywhere in this feature (chart table-toggle reuses `ui/tabs.tsx`; keyboard-shortcut help reuses `ui/dialog.tsx`; dark mode is CSS-only)
