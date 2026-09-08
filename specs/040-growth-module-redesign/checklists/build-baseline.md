# Build baseline — feature 040

**Created**: 2026-09-04 · **Branch**: `feat/040-growth-module-redesign` · **Command**: `cd frontend && npm run build` (Vite 8)

## Before (T001, measured on the pre-feature tree)

| Chunk | Raw | Gzip | Notes |
|---|---|---|---|
| `dist/assets/index-*.js` (entry) | 1,292.02 kB | 336.68 kB | contains the WHO JSON (`WHO 2007 Growth Reference` string present) and `GrowthCharts`/`PercentileCurves` code |
| `dist/assets/useAthleteInsights-*.js` | 367.65 kB | 107.39 kB | contains recharts (`recharts-wrapper`); **statically imported by the entry chunk and module-preloaded in `index.html`** |
| `dist/assets/AthleteAIAnalysisTab-*.js` | 90.56 kB | 24.38 kB | lazy (feature 036) |

Effective first-paint JS ≈ 336.68 + 107.39 kB gzip. Constitution IV budget for the entry route: 250 kB gzip (pre-existing violation, recorded in `plan.md` Complexity Tracking).

## Target (SC-005, verified by `npm run check:chunks` in T071)

- Entry chunk does not statically import, and `index.html` does not module-preload, the chunk containing `recharts-wrapper`.
- Entry chunk does not contain `WHO 2007 Growth Reference`.
- Growth lazy chunk ≤ 150 kB gzip.
- Entry gzip reduced by ≥ 100 kB versus the table above.

## After (T071, measured 2026-09-04 on `feat/040-growth-module-redesign`)

`npm run check:chunks` → `OK — recharts chunk and WHO growth reference are not on the entry path.`

| Chunk | Raw | Gzip | Notes |
|---|---|---|---|
| `dist/assets/index-*.js` (entry) | 1,093.90 kB | 283.38 kB | no longer statically imports the recharts chunk; no longer contains `WHO 2007 Growth Reference` |
| `dist/assets/GrowthTab-*.js` (growth chunk) | 61.61 kB | 17.42 kB | lazy from both `AthleteDetailPage.tsx` and `MyAthleteDetailPage.tsx`; well under the 150 kB gzip budget |
| `dist/assets/CartesianChart-*.js` (recharts) | 331.08 kB | 98.12 kB | shared chunk (growth + Insights IA charts); reached only via dynamic `import()`, no longer module-preloaded nor statically imported by the entry |
| `dist/assets/growth-reference-who-*.js` | 106.54 kB | 27.84 kB | WHO LMS JSON; dynamic `import()` inside `PercentileChart.tsx`, not in the entry |
| `dist/assets/useAthleteInsights-*.js` | 5.00 kB | 1.79 kB | was 367.65 kB / 107.39 kB gzip in the Before table (it bundled recharts); still module-preloaded by `index.html`, now negligible |

**Effective first-paint JS** (same methodology as the Before table: entry + the module-preloaded `useAthleteInsights` chunk):
- Before: 336.68 + 107.39 = 444.07 kB gzip
- After: 283.38 + 1.79 = 285.17 kB gzip
- **Reduction: 158.90 kB gzip** (target was ≥ 100 kB) → SC-005's transfer-size clause met.

The entry chunk alone dropped 53.30 kB gzip (336.68 → 283.38); the rest of the ≥ 100 kB reduction came from `useAthleteInsights` no longer carrying recharts once it stopped being reachable from the entry — same root cause the chunk gate checks for.

> **Methodology caveat (added by the T073 gate, 2026-09-04)** — "effective first-paint JS" above counts only the entry chunk plus `useAthleteInsights`, because that is what the Before table counted; the **delta** is apples-to-apples and real, but the absolute figure is not the full first-paint payload. `dist/index.html` module-preloads ~85 JS files; summing all of them plus the entry gives **≈ 491 kB gzip** today. Neither `CartesianChart-*.js` (recharts) nor `growth-reference-who-*.js` is in that preload list — the entry's only reference to the recharts chunk is inside the `__vitePreload` dependency string array of a **dynamic** `import()`, which is exactly what the gate requires. The remaining entry-route overage against Constitution IV's 250 kB is the pre-existing violation already recorded in `plan.md` Complexity Tracking; closing it needs the route-level `App.tsx` code-splitting pass that plan.md scopes out of this feature.

Fix applied to reach a green gate: `frontend/src/components/newsletter/StageLogView.tsx` lazy-wraps `EffortProfile` (`React.lazy` + `Suspense`) — it was the last static path from the entry to recharts (`ParentNewsletterPage.tsx` and `training/studio/BlockPanel.tsx` import `StageLogView` statically from `App.tsx`, which has no lazy boundary of its own). `PanoramaView.tsx` → `MiniSparkline` did **not** need the same treatment: its only real importer, `AthleteAIAnalysisTab.tsx`, was already behind `React.lazy` in both detail pages, so it was not reachable from the entry to begin with — confirmed by re-running `npm run check:chunks` after the `StageLogView.tsx` fix alone, which already passed.

- [x] T001 baseline recorded
- [x] T071 after-numbers recorded and gate green
