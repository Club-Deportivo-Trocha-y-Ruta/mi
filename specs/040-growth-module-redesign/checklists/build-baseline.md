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

## After (T071 fills in)

| Chunk | Raw | Gzip | Notes |
|---|---|---|---|
| entry | _pending_ | _pending_ | |
| growth chunk | _pending_ | _pending_ | |
| recharts chunk | _pending_ | _pending_ | must be lazy |

- [x] T001 baseline recorded
- [ ] T071 after-numbers recorded and gate green
