# Contract — Chart Visual Style (DistributionChart, EvolutionChart)

Applies to `frontend/src/components/athletes/ai/DistributionChart.tsx` and `EvolutionChart.tsx` (recharts 3.8). Every rule below cites the `dataviz` skill file it comes from. No data/query changes — this is a rendering-prop contract only.

## Grid

- **Solid hairline**, one-step-off-surface gray: keep the existing `rgba(34,42,53,0.08)` (already `--color-border-gray` per `specs/028-frontend-design-foundation/research.md` R5c) on `<CartesianGrid stroke=.../>`, **remove `strokeDasharray="3 3"`** at `DistributionChart.tsx:304` and `EvolutionChart.tsx:213`.
  - Cites `references/anti-patterns.md`: *"❌ Dashed gridlines or axis rules. Dashing adds visual noise and reads as 'projection' or 'threshold' when it's just a grid. ✅ Gridlines and axes are solid hairlines, one shade off the surface."*
- **Axis ink**: replace the one-off `#5a6172` (used nowhere else in the app) with `--color-mid-gray` (`#717171`) on every `XAxis`/`YAxis` `tick.fill` and axis `label.style.fill` (`DistributionChart.tsx:309,315,320,327`; `EvolutionChart.tsx:216,224,228`).
  - Cites `references/marks-and-anatomy.md`: *"Text never wears the data color... labels, values, legends, and axis text use text tokens (primary/secondary/muted)."*

## Color roles

| Role | Token | Hex | Replaces |
|---|---|---|---|
| Own series (self) | `--color-primary` | `#20b7c9` | `DistributionChart.tsx:338` area/curve `#131316`; its separate self-reference-line `#0ea5e9`/label `#0369a1` (`:345,354`); `EvolutionChart.tsx:244,246` line/dot `#131316` |
| Best reference | `--color-success` | `#0ca30c` | `DistributionChart.tsx:493-494` `#16a34a`/`#15803d` |
| Worst reference | `--color-danger` | `#d03b3b` | `DistributionChart.tsx:493-494` `#dc2626`/`#b91c1c` |
| Other riders (neutral) | `--color-mid-gray` | `#717171` | `DistributionChart.tsx:493-494` `#94a3b8`/`#64748b` |

Distribution currently encodes "self" with **two unrelated blues** in the same chart (the curve fill and the dedicated "Tú" reference line) before best/worst even enter the picture — this contract collapses all "self" marks to the one accent.

**Validated as a set** (not eyeballed — `node scripts/validate_palette.js "#20b7c9,#0ca30c,#d03b3b" --mode light --surface "#ffffff" --pairs all`, `pairs:"all"` because any two reference lines can sit adjacent on one curve, per `color-formula.md` check 4's small-multiples/scatter rule):

```
[PASS] Lightness band      — all 3 inside L 0.43–0.77
[PASS] Chroma floor        — all 3 >= 0.10
[PASS] CVD separation      — worst all-pairs danger↔success ΔE 12.4 (deutan); clears the ≥12 target
[WARN] Contrast vs surface — #20b7c9 (own series) at 2.42:1, below 3:1 — relief required
```

**The contrast WARN on the accent is the reason the table-view twin (below) is mandatory, not optional** — per `color-formula.md`: *"A WARN on contrast is not dismissable — it obligates a relief channel (visible direct labels or the table view)."* Best/worst (`--color-success`/`--color-danger`) are a **status job** (they mean good/bad), not identity, so they correctly take status tokens rather than hand-picked hues — cites `color-formula.md`'s collision rule: *"when a series means good/bad... it wears status tokens; when it's just 'series 4' it wears categorical — never both in one chart."*

## Championship on-point marking

Today: every `EvolutionChart` point renders identically (`dot={{r:4, fill:"#131316"}}`, `:246`); the championship is distinguished only by amber text in the `<ol>` legend below (`:263-267`). Contract:

- Custom `dot` render (recharts `dot` accepts a function/component) — for the point where `series_kind === "championship"`:
  - **Shape**: diamond (rotated-square SVG path), not a new color — championship-ness is an occasion/identity fact, not polarity, so per `color-formula.md`'s "assign color by the job it does" it must not consume a status hue or invent a 4th/5th categorical color needing its own CVD re-validation.
  - **Fill**: `--color-primary` (same as the self series — it is still the athlete's own data point).
  - **Size**: radius ~6 (diameter ≥8px, clearing the marker floor: *"Marker/end-dot ≥ 8px (r ≥ 4)"*, `marks-and-anatomy.md`).
  - **2px surface-color ring**, per the documented "surface ring" mechanism for marks that must stay legible where they cross a line (`marks-and-anatomy.md` §"The two spacers").
  - **Direct label** ("Cto. Dep.") anchored at/above the point itself, **in addition to** (not replacing) the existing accessible `<ol>` legend below — satisfies FR-003 acceptance scenario 2 ("visually distinct on the data point itself, not only in text below") without regressing the already-accessible list.

## Reference-label capping

`RiderReferenceLines` (`DistributionChart.tsx:482-519`) direct-labels every non-self rider today — at 10-15 riders this risks the anti-pattern *"❌ A number on every data point... A value beside every dot or segment is chaos and goes unread."*

- **Rule**: when the category's rider count (`points.length`) is **> 8**, only self/best/worst keep a visible text label; every other rider's `ReferenceLine` still renders (position stays informative — a reader can still see where a rider's time falls) but its `label` prop is omitted.
- At `points.length <= 8`, all riders keep labels, using the existing alternating top/bottom placement (`:496-497`) to avoid collisions — unchanged.
- Cites `marks-and-anatomy.md`: *"Label selectively — never a number on every point... label the endpoint, the extreme, or the one series the story is about; let the axis, the legend, and the tooltip/table carry the rest."*

## Table-view twin

FR-003: *"an available table view of charted data."* Because the accent's contrast WARN (above) applies identically to both charts' own-series mark, both get a twin:

- **Distribution** (n≥5, "medium/high confidence" path — today has no table at all, only the chart): add a "Gráfica"/"Tabla" toggle (built on the already-installed `ui/tabs.tsx`, no new dependency) that swaps the `AreaChart` for a **generalized** version of the existing `LowConfidenceTable` (`DistributionChart.tsx:399-463` — already exactly the right shape: position / name-or-pseudonym / time, self-row highlighted). One component, two call sites (the existing `n<5` fallback, unconditional; the new `n≥5` toggle target).
- **Evolution**: add the same toggle; table columns mirror the fields its own tooltip already shows (`EvolutionChart.tsx:321-341`: label, event date, value) — one row per plotted point, championship row flagged the same way the `<ol>` legend already flags it.
- The existing `n<5` (Distribution) / `n<3` (Evolution) **low-confidence fallbacks are preserved exactly as they render today** — cites `references/choosing-a-form.md`'s "is it even a chart?" heuristic, which this fallback already correctly implements; the toggle only appears once there is a chart to toggle away from (i.e., never shown alongside the low-confidence table).

## Tooltips

Unchanged in structure (`DistributionTooltip`/`EvolutionTooltip` custom `content` renderers already follow the value-leads-label hierarchy correctly) — only their `text-charcoal`/`text-mid-gray` classes are already-correct tokens, no edit needed. The inline `boxShadow` on the tooltip container is swept by 028's shadow-token consolidation, not re-specified here.

## Explicitly not touched by this contract

- The inline `cardShadow` constant duplicated at the top of both files — owned by `specs/028-frontend-design-foundation` (shadow/token consolidation).
- Query logic, data shapes, `useAthleteDistribution`/`useAthleteEvolution`/`useAthleteRaces` hooks — untouched.
- The `n<5`/`n<3` disclaimer copy and thresholds — untouched (only their color tokens, if any, are swept; the thresholds are a data-science decision out of this feature's scope).

## Scenario matrix (validation — see `quickstart.md`)

| Scenario | What must hold |
|---|---|
| Normal field (5-9 riders) | Solid grid, correct 3 color roles, all rider labels visible, table toggle present |
| Large field (10-15 riders) | Labels capped to self/best/worst only; non-labeled lines still render at correct position |
| Small sample (n<5 Distribution / n<3 Evolution) | Existing table/disclaimer fallback unchanged; no chart/toggle rendered |
| Championship present (Evolution) | Diamond marker + on-point label + legend entry, all three present simultaneously |
| Single-rider category (no distinct best/worst) | No worst/best reference lines render (nothing to contrast against); self line still renders in accent |
