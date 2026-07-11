# Quickstart — Validating 029 Coach Surface Subtraction

Validation guide only — no implementation code. Full removal/relocation table: `contracts/removal-and-redirect-manifest.md`. Tab contract: `contracts/progreso-tab.md`. Interpretation states: `contracts/anxiety-interpretation-ui.md`.

## Prerequisites

- `frontend/` deps installed (`npm install` — will pick up the `konva`/`react-konva` removal from `package.json`).
- Backend running with seed data (`docker compose up`, or `cd backend && uvicorn app.main:app --reload` against a dev DB) for the manual scenarios — no migration to run for this feature.
- At least one athlete with: an anthropometric record (growth tab non-empty), a completed anxiety assessment for a consented athlete, and (ideally) one for a non-consented athlete, to exercise both interpretation paths.

## Automated checks

```bash
# Frontend — full suite (includes updated/deleted test files from research.md R5)
cd frontend && npm test

# Frontend — targeted suites most affected by this feature
npx vitest run src/routes/athletes/AthleteDetailPage.test.tsx src/routes/athletes/AthleteDetailPage.progreso.test.tsx
npx vitest run src/components/anxiety/__tests__/IndividualPanel.test.tsx
npx vitest run src/routes/competitions/__tests__/SeasonInsightsPage.test.tsx   # new path after the move
npx vitest run src/__tests__/competitions-routing.test.tsx src/__tests__/competitionsRedirects.test.tsx src/__tests__/T049-wave-f-cleanup.test.tsx

# Typecheck — catches any dangling import to a deleted file/component immediately
npm run typecheck

# Build — verifies bundle shrink (SC-007) and that konva is gone
npm run build
grep -ril "konva" dist/assets || echo "OK: no konva in bundle"
grep -n "konva" package.json || echo "OK: konva/react-konva not in package.json"

# Backend — unaffected by this feature, run as a regression check only (no anxiety/technique/strength schema changes)
cd ../backend && pytest
```

**Expected outcomes**: all suites green; `npm run typecheck` reports zero errors (in particular zero "Cannot find module" for any of the removed paths in `contracts/removal-and-redirect-manifest.md`); the built bundle contains no `konva` chunk and `frontend/package.json` no longer lists `konva`/`react-konva`; a route-level bundle-size comparison against the pre-feature build shows the technique area's chunk shrinking (composer + session-builder removed) and no route's initial chunk growing.

## Manual scenarios (mapped to spec.md acceptance scenarios / success criteria)

### 1. Old bookmarks and shared links still resolve (SC-003, US1 AC6)

- Visit `/coach/race-analysis` directly → lands on `/competitions` (Competencias list), not a blank page or 404. *(Changed target — previously `/competitions/insights`.)*
- Visit `/training/races/1/club-insights` (use a real `raceEventId`) → lands on `/competitions/1?tab=insights` (unchanged — this redirect is untouched by this feature).
- Visit each removed route directly (`/technique/composer`, `/technique/sessions/new`, `/intervals/templates`, `/competitions/insights`, `/competitions/insights/club`, `/competitions/insights/athletes/1`, `/technique/athletes/1/progress`, `/strength/athletes/1/progress`) → each resolves to `NotFoundPage` (`*` catch-all) rather than throwing — expected, since none of these had external links to preserve (confirmed in `research.md` R1); this is intentionally different from the two Wave-B redirects above, which *do* have to keep resolving because they were shared externally.

### 2. Season panorama reachable from Competencias (SC-002, US1 AC2)

- From `/competitions`, find and click "Panorama de temporada" in the header action row → lands on `/competitions/insights/season/{currentYear}` (URL unchanged from before this feature; only the entry point and the file location changed).
- On that page: click the "Análisis IA" back-link → lands on `/competitions` (not a 404 — this is the fixed dead link from `research.md` R2).
- Click any athlete row → lands on `/athletes/{id}?tab=ai_analysis` and shows that athlete's `AthleteAIAnalysisTab` content (not a 404 — the other fixed dead link).

### 3. Progreso tab (SC-004, SC-005, US2 all ACs)

- Open any athlete's profile (`/athletes/{id}`). Count the top-level tabs → exactly 7 (`Info general`, `Antropometría`, `Crecimiento`*, `Análisis IA`, `Boletines`*, `Actividades`, `Progreso`). *(`Crecimiento` only shows with ≥1 anthropometric record; `Boletines` hidden for parent role — both pre-existing conditions, unchanged.)*
- Click `Progreso` → default view is "Técnica" (`SkillProgressBoard` content); toggle to "Fuerza" → `ProgressNotesBoard` content. Both boards behave exactly as their old standalone pages did (same forms, same history).
- From the same tab, click "Ver ansiedad competitiva" → lands on `/anxiety` with the "Individual" sub-tab active and this athlete already selected (not the empty selector) — confirms the two-interaction path from profile to wellbeing (SC-004: profile → Progreso tab → pointer = 2 interactions).
- Confirm the two old URLs (`/technique/athletes/{id}/progress`, `/strength/athletes/{id}/progress`) no longer exist as working routes (covered in scenario 1).

### 4. Anxiety interpretation, with and without consent (SC-006, US3 all ACs)

- As coach, open `/anxiety` → Individual tab → select a **consented** athlete with a completed assessment. Click "Analizar con IA". Verify: in-progress feedback appears immediately (button disabled, "Analizando…" label, cold-start helper text); within the interaction, the interpretation renders with baseline-referenced wording, no clinical/diagnostic terms, a mastery-climate athlete-facing message, and (if applicable) an amber attention box — never a red/error tone for flags.
- Repeat with the AI service unreachable (e.g., stop/misconfigure the AI provider locally) → interpretation still renders, tagged "Reglas" instead of "IA", with plain-language framing — not an error banner.
- Select an athlete/instrument combination with **no completed assessment yet** (all points still pending) → confirm the "Analizar con IA" button does not render at all (not merely disabled) — see `contracts/anxiety-interpretation-ui.md`'s "Not interpretable" state.
- Timing check for SC-006: from clicking "Analizar con IA" to the interpretation being visible, under 60 seconds end-to-end (allow for the ~50 s Render cold-start case explicitly).

### 5. No-capability-loss sweep (SC-001, SC-002, FR-010)

- Confirm every capability that existed before this feature and is not one of the two explicitly-approved losses (gymkhana composer; standalone technique-session-assembly path, pending feature 032) is still reachable: interval templates from session detail, per-válida AI insights from the competition detail "Insights IA" tab, per-athlete AI analysis from the athlete profile's "Análisis IA" tab, season panorama from Competencias.
- Spot-check the technique exercise catalog and session-planning flow still work end-to-end (create/edit a training session, attach an interval template) — these must be completely unaffected by the technique-builder/composer removals per the "no capability regression window" edge case in spec.md.
